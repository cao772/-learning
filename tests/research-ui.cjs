const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

test('private research tabs escape source titles and preserve evidence limits', () => {
  const handlers={};
  const root={contains:()=>true};
  const board={innerHTML:''};
  const close={addEventListener:()=>{}};
  const elements={'content':root,'research-board':board,'research-close':close};
  const document={
    getElementById:id=>elements[id],
    addEventListener:(name,fn)=>{handlers[name]=fn;}
  };
  const sandbox={document,window:{},URL};
  const code=fs.readFileSync(path.join(__dirname,'../hub/static/research-ui.js'),'utf8');
  vm.runInNewContext(code,sandbox,{filename:'research-ui.js'});
  assert.equal(typeof sandbox.window.renderResearchAddon,'function');
  const x='<img src=x onerror=alert(1)>';
  const data={
    connections:{
      same_link:[{basis:'同一规范链接，非独立来源证明', members:[
        {id:'a',title:x,url:'https://example.org/article',source:'AIHOT',origin:'feed',verification_status:'candidate'},
        {id:'b',title:'转载',url:'https://example.org/article',source:'手动收集',origin:'private_capture'}]}],
      similar_title:[]
    },
    topic_groups:[{label:'Agent 工具',source_count:2,basis:'关键词共享，不代表结论一致',members:[
      {id:'a',url:'https://example.org/a',title:'Agent 工具研究',source:'BestBlogs'},
      {id:'b',url:'https://example.org/b',title:'Agent 项目',source:'AIHOT'}]}],
    research_suggestions:[{id:'b',title:'需要实测的工具',reason:'你已收藏',status:'仅建议，尚未加入计划'}],
    research_records:[{key:'a',title:x,url:'https://github.com/a/b',decision:'待复现',test_status:'未运行',
      project:'<script>private</script>',question:'复现基线'}],
    ranking:[],captures:[]
  };
  sandbox.window.renderResearchAddon({data,mode:'connections',api:async()=>({})});
  assert.match(board.innerHTML,/同一规范链接，非独立来源证明/);
  assert.match(board.innerHTML,/&lt;img/);
  assert.doesNotMatch(board.innerHTML,/<img src=x/);
  assert.match(board.innerHTML,/非独立来源证明/);
  sandbox.window.renderResearchAddon({data,mode:'plans',api:async()=>({})});
  assert.match(board.innerHTML,/待复现/);
  assert.match(board.innerHTML,/未运行/);
  assert.match(board.innerHTML,/&lt;script&gt;private/);
  assert.doesNotMatch(board.innerHTML,/<script>private/);
  assert.match(board.innerHTML,/需要实测的工具/);
  assert.match(board.innerHTML,/仅建议，尚未加入计划/);
  sandbox.window.renderResearchAddon({data,mode:'connections',api:async()=>({})});
  assert.match(board.innerHTML,/跨来源兴趣专题/);
  assert.match(board.innerHTML,/关键词共享，不代表结论一致/);
  assert.equal(typeof handlers.click,'function');
});
