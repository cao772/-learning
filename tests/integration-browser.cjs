/* Real Chromium smoke: synthetic data only; never connects to user cloud/private files. */
const { chromium } = require('playwright');
const { spawn } = require('node:child_process');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const BASE='http://127.0.0.1:8765';
const evidence=path.join(__dirname,'browser-evidence');
fs.mkdirSync(evidence,{recursive:true});
const sleep = ms => new Promise(resolve=>setTimeout(resolve,ms));

async function waitForServer(proc) {
  for (let attempt=0;attempt<90;attempt++) {
    if (proc.exitCode!==null) throw Error('Synthetic Flask server exited: '+proc.exitCode);
    try {
      const response=await fetch(BASE+'/healthz');
      if(response.ok)return;
    }catch(_){}
    await sleep(500);
  }
  throw Error('Synthetic Flask server failed to become healthy');
}

(async () => {
  const proc=spawn('python',['scripts/integration-smoke-server.py'],{
    cwd:path.join(__dirname,'..'),
    env:{...process.env,SMOKE_PORT:'8765'},
    stdio:['ignore','pipe','pipe']
  });
  let output='';
  proc.stderr.on('data',chunk=>{output+=String(chunk).slice(0,1500);});
  let browser;
  try {
    await waitForServer(proc);
    browser=await chromium.launch({headless:true,args:['--no-sandbox']});
    const guest=await browser.newContext({viewport:{width:1440,height:900}});
    const page=await guest.newPage();

    let response=await page.goto(BASE+'/');
    assert.equal(response.status(),200,'guest homepage');
    await page.getByRole('heading',{name:'把好奇变成理解。'}).waitFor();
    assert.equal(await page.locator('[data-public-item]').count(),2);
    await page.locator('#public-search').fill('Harness');
    assert.equal(await page.locator('[data-public-item]:visible').count(),1);
    await page.locator('#public-search').fill('');
    await page.locator('#public-status').selectOption('candidate');
    assert.equal(await page.locator('[data-public-item]:visible').count(),1);
    await page.locator('#public-reset').click();
    assert.equal(await page.locator('[data-public-item]:visible').count(),2);
    await page.screenshot({path:path.join(evidence,'01-public-desktop.png'),fullPage:true});

    assert.equal((await guest.request.get(BASE+'/api/discover')).status(),401,'private discover');
    assert.equal((await guest.request.get(BASE+'/api/export')).status(),401,'private data export');
    assert.equal((await guest.request.get(BASE+'/api/state/research%3Atest')).status(),401,'private research');
    for (const route of ['/learn/llm','/learn/lab']) {
      response=await page.goto(BASE+route);
      assert.equal(response.status(),200,'course '+route);
      assert.equal(await page.locator('body').count(),1);
    }

    await page.goto(BASE+'/admin');
    await page.locator('input[name="password"]').fill('browser-test-password');
    await page.locator('form button').click();
    await page.locator('button[data-view="discover"]').waitFor();
    await page.locator('button[data-view="discover"]').click();
    await page.getByRole('heading',{name:'我的兴趣权重'}).waitFor();
    await page.locator('button[data-discovery-category="paper"]').waitFor();
    await page.locator('button[data-discovery-category="agent"]').waitFor();
    await page.locator('button[data-discovery-category="paper"]').click();
    await page.waitForFunction(() => {
      const cards=document.querySelectorAll('.discovery-card');
      return cards.length===1 && cards[0].textContent.includes('RNA');
    });
    await page.locator('button[data-discovery-category="code"]').click();
    await page.getByText('这个分类暂无内容。').waitFor();
    await page.locator('button[data-discovery-category="all"]').click();
    await page.waitForFunction(() => document.querySelectorAll('.discovery-card').length===2);
    // Browser-only category search should never send the query to public pages.
    await page.locator('#discovery-search').fill('RNA');
    await page.waitForFunction(() => document.querySelectorAll('.discovery-card:not([hidden])').length===1);
    await page.locator('#discovery-search').fill('');
    await page.waitForFunction(() => document.querySelectorAll('.discovery-card:not([hidden])').length===2);
    // Correct an arXiv paper to Agent in the owner's view without editing feed data.
    await page.locator('[data-correct-category="browser-candidate-rna"]').click();
    await page.locator('#category-dialog[open]').waitFor();
    await page.locator('#category-form select[name="category"]').selectOption('agent');
    await page.locator('#category-form textarea[name="note"]').fill('人工检查后调整展示类别');
    await page.locator('#category-form button[type="submit"]').click();
    await page.locator('#category-dialog').waitFor({state:'hidden'});
    await page.locator('button[data-discovery-category="agent"]').click();
    await page.waitForFunction(() => document.querySelectorAll('.discovery-card').length===2);
    await page.locator('[data-correct-category="browser-candidate-rna"]').click();
    await page.locator('#category-form select[name="category"]').waitFor();
    assert.equal(await page.locator('#category-form select[name="category"]').inputValue(),'agent');
    await page.locator('#category-reset').click();
    await page.locator('#category-dialog').waitFor({state:'hidden'});
    await page.locator('button[data-discovery-category="paper"]').click();
    await page.waitForFunction(() => document.querySelectorAll('.discovery-card').length===1);
    await page.locator('button[data-discovery-category="all"]').click();
    await page.screenshot({path:path.join(evidence,'02-private-discovery.png'),fullPage:true});

    await page.locator('button[data-discover-mode="saved"]').click();
    await page.locator('input[name="url"]').fill('https://github.com/example/repro-project?utm_source=xhs');
    await page.locator('input[name="title"]').fill('通过小红书发现的 GitHub 工具');
    await page.locator('select[name="source"]').selectOption({label:'小红书'});
    await page.locator('textarea[name="note"]').fill('先核实许可证、可部署性和学习价值');
    await page.locator('#capture-form button[type="submit"]').click();
    await page.getByRole('heading',{name:'通过小红书发现的 GitHub 工具'}).waitFor();
    await page.locator('[data-research-item]').first().click();
    await page.locator('#research-dialog[open]').waitFor();
    await page.locator('select[name="decision"]').selectOption('待复现');
    await page.locator('select[name="test_status"]').selectOption('未运行');
    await page.locator('textarea[name="question"]').fill('是否能在隔离环境部署并用于 Agent 项目？');
    await page.locator('#research-form button[type="submit"]').click();
    await page.locator('#research-dialog').waitFor({state:'hidden'});
    await page.locator('button[data-discover-mode="plans"]').click();
    await page.getByRole('heading',{name:'我的学习与项目验证计划'}).waitFor();
    await page.getByRole('heading',{name:'通过小红书发现的 GitHub 工具'}).waitFor();
    await page.screenshot({path:path.join(evidence,'03-private-study-plan.png'),fullPage:true});

    const outsider=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
    const phone=await outsider.newPage();
    response=await phone.goto(BASE+'/');
    assert.equal(response.status(),200,'mobile guest');
    assert.equal(await phone.locator('[data-public-item]').count(),2);
    await phone.screenshot({path:path.join(evidence,'04-mobile-public.png'),fullPage:true});
    const body=await outsider.request.get(BASE+'/api/items');
    const text=await body.text();
    assert(!text.includes('通过小红书发现的 GitHub 工具'),'private capture leaked to public API');
    assert(!text.includes('是否能在隔离环境部署'),'research note leaked to public API');
    assert.equal((await outsider.request.get(BASE+'/api/discover')).status(),401);
    await outsider.close();
    await guest.close();
    console.log('BROWSER PASS: public filter, two course routes, anonymous isolation, owner discovery/capture/research plan, mobile');
    console.log('Evidence: tests/browser-evidence (synthetic fixtures only)');
  } catch (error) {
    console.error('Browser smoke failed:',error);
    console.error('Flask startup/stderr:',output.slice(-2500));
    process.exitCode=1;
  } finally {
    if (browser) await browser.close();
    proc.kill('SIGTERM');
  }
})();
