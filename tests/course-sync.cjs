// Run the actual browser bridge with deterministic storage/network/timers.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const key='xunxu-llm-course-v1';
function harness(){
 class Storage{constructor(){this.data={}}setItem(k,v){this.data[k]=v}getItem(k){return this.data[k]||null}}
 const queue=new Map(),requests=[];let counter=0;
 const context={Storage,localStorage:new Storage(),JSON,Error,confirm:()=>true,
 setTimeout(fn){queue.set(++counter,fn);return counter},clearTimeout(id){queue.delete(id)},
 document:{getElementById:()=>({}),addEventListener(){}},
 DOMParser:class{parseFromString(){return {querySelector:()=>({content:'test-csrf'})}}},
 XMLHttpRequest:class{open(m,url){this.url=url}send(){this.status=200;this.responseText=this.url==='/'?'':JSON.stringify({value:null,revision:0})}},
 fetch:(url,options)=>new Promise((resolve,reject)=>requests.push({body:JSON.parse(options.body),resolve,reject}))};
 vm.runInNewContext(fs.readFileSync('hub/static/course-sync.js','utf8'),context);
 return {requests,write:n=>context.localStorage.setItem(key,JSON.stringify({notes:n})),
 async timers(){const batch=[...queue.values()];queue.clear();batch.forEach(fn=>fn());await new Promise(setImmediate)},
 async settle(){await new Promise(setImmediate)}};
}
test('failed older request preserves newer edit and retries newest state',async()=>{
 const h=harness();h.write('old');await h.timers();h.write('new');
 h.requests[0].resolve({ok:false,status:503});await h.settle();await h.timers();
 assert.equal(h.requests[1].body.value.notes,'new');
});
test('offline failure retries without another edit',async()=>{
 const h=harness();h.write('offline');await h.timers();h.requests[0].reject(Error('Failed to fetch'));
 await h.settle();await h.timers();assert.equal(h.requests[1].body.value.notes,'offline');
});
test('conflict blocks retries and further edits until reload',async()=>{
 const h=harness();h.write('old');await h.timers();h.write('new');h.requests[0].resolve({ok:false,status:409});
 await h.settle();await h.timers();h.write('newest');await h.timers();assert.equal(h.requests.length,1);
});
test('queued edit uses the revision returned by previous save',async()=>{
 const h=harness();h.write('old');await h.timers();h.write('new');h.requests[0].resolve({ok:true,json:async()=>({revision:7})});
 await h.settle();await h.timers();assert.equal(h.requests[1].body.revision,7);assert.equal(h.requests[1].body.value.notes,'new');
});
