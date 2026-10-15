const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

test('owner discovery renders profile, private source directory, and escaped unverified content', async () => {
  const elements = {
    content: {innerHTML: '', contains: () => true},
    'interest-form': {onsubmit: null},
    'profile-message': {textContent: ''}
  };
  const listeners = {};
  const doc = {
    getElementById: id => elements[id],
    addEventListener: (name, handler) => {listeners[name] = handler;}
  };
  const page = {
    topics: [{key:'agent',label:'Agent / MCP'}],
    profile: {weights:{agent:5}},
    profile_revision:0,
    ranking_method:'规则匹配，没有调用模型',
    sources:[{name:'GitHub',kind:'开源发现',access:'可人工保存',url:'https://github.com/trending'}],
    captures:[],
    ranking:[{
      item:{
        id:'a',title:'<script>alert(1)</script>',summary:'尚未核验',
        verification_status:'candidate',source:'测试',url:'https://example.com',personal:{}
      },
      reasons:['匹配：Agent / MCP'],possible_project:'Muse'
    }]
  };
  const win = {};
  const code=fs.readFileSync(path.join(__dirname,'../hub/static/discovery-ui.js'),'utf8');
  vm.runInNewContext(code,{document:doc,window:win,URL},{filename:'discovery-ui.js'});
  assert.equal(typeof win.renderDiscovery,'function');
  await win.renderDiscovery({api:async url => {assert.equal(url,'/api/discover');return page;},onDetail:()=>{}});
  const html=elements.content.innerHTML;
  assert.match(html,/兴趣权重/);
  assert.match(html,/Agent \/ MCP/);
  assert.match(html,/&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
  assert.doesNotMatch(html,/<script>alert\(1\)<\/script>/);
  assert.match(html,/待核验/);
  assert.match(html,/仅依据关键词提示/);
  assert.ok(listeners.click);
});


test('Agent, paper, and code appear in separate groups with switchable category filters', async () => {
  const listeners = {};
  const elements = {
    content: {innerHTML:'',contains:()=>true},
    'interest-form': {onsubmit:null},
    'profile-message': {textContent:''},
  };
  const document = {
    getElementById:id=>elements[id],
    addEventListener:(type,fn)=>{listeners[type]=fn}
  };
  const row=(id,title,category,categoryLabel)=>({
    item:{id,title,url:'https://example.org/'+id,source:'测试',summary:'合成样本',personal:{},
      verification_status:'candidate'},
    category,category_label:categoryLabel,category_reason:'规则暂分',topic_tags:['Agent'],
    reasons:['尚待核验原文'],possible_project:null
  });
  const page={
    profile:{weights:{agent:5},custom_interests:[]},
    topics:[{key:'agent',label:'Agent / MCP'}], profile_revision:0,
    categories:[
      {key:'agent',label:'Agent 与智能体',description:'Agent 技术',count:1},
      {key:'paper',label:'论文与科研',description:'科研论文',count:1},
      {key:'code',label:'开源工具与代码项目',description:'GitHub 项目',count:1},
      {key:'other',label:'待分类',description:'未知',count:0}
    ],
    ranking:[
      row('agent','Agent 技术解读','agent','Agent 与智能体'),
      row('paper','Agent 论文研究','paper','论文与科研'),
      row('repo','Agent 源码仓库','code','开源工具与代码项目')
    ],
    ranking_method:'测试规则',sources:[],captures:[]
  };
  const win={};
  vm.runInNewContext(
    fs.readFileSync(path.join(__dirname,'../hub/static/discovery-ui.js'),'utf8'),
    {document,window:win,URL}, {filename:'discovery-ui.js'});
  await win.renderDiscovery({api:async()=>page,onDetail:()=>{}});
  assert.match(elements.content.innerHTML,/data-discovery-category="paper"/);
  assert.match(elements.content.innerHTML,/data-discovery-category="code"/);
  assert.match(elements.content.innerHTML,/data-discovery-category="agent"/);
  assert.equal((elements.content.innerHTML.match(/class="discovery-category-section"/g)||[]).length,3);
  assert.equal((elements.content.innerHTML.match(/class="discovery-card"/g)||[]).length,3);
  function select(category) {
    listeners.click({target:{closest:()=>({dataset:{discoveryCategory:category}})}});
    return new Promise(resolve=>setImmediate(resolve));
  }
  await select('paper');
  assert.match(elements.content.innerHTML,/Agent 论文研究/);
  assert.doesNotMatch(elements.content.innerHTML,/<h2>Agent 技术解读<\/h2>/);
  assert.doesNotMatch(elements.content.innerHTML,/<h2>Agent 源码仓库<\/h2>/);
  assert.equal((elements.content.innerHTML.match(/class="discovery-card"/g)||[]).length,1);
  await select('code');
  assert.match(elements.content.innerHTML,/<h2>Agent 源码仓库<\/h2>/);
  assert.equal((elements.content.innerHTML.match(/class="discovery-card"/g)||[]).length,1);
  await select('all');
  assert.equal((elements.content.innerHTML.match(/class="discovery-card"/g)||[]).length,3);
});
