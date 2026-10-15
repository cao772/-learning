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
