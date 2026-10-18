/* Offline-only front end. No network requests, persistence or algorithm changes. */
(function(root){
'use strict';
function parseCSV(text){
 const rows=[];let row=[],cell='',quoted=false;
 text=text.replace(/^\uFEFF/,'');
 for(let i=0;i<text.length;i++){const c=text[i];if(c==='"'){if(quoted&&text[i+1]==='"'){cell+='"';i++;}else quoted=!quoted;}else if(!quoted&&(c===','||c==='\n')){row.push(cell.replace(/\r$/,''));cell='';if(c==='\n'){rows.push(row);row=[];}}else cell+=c;}
 if(quoted)throw Error('CSV 引号未闭合');if(cell||row.length){row.push(cell.replace(/\r$/,''));rows.push(row);}
 const headers=rows.shift()||[];if(new Set(headers).size!==headers.length)throw Error('CSV 列名重复');
 return {headers,rows:rows.filter(r=>r.some(Boolean)).map(r=>{if(r.length!==headers.length)throw Error('CSV 列数不一致');return Object.fromEntries(headers.map((h,i)=>[h,r[i]]));})};
}
function csv(table){return table.headers.map(quote).join(',')+'\r\n'+table.rows.map(r=>table.headers.map(h=>quote(r[h]??'')).join(',')).join('\r\n')+'\r\n';}
function quote(s){return '"'+String(s).replace(/"/g,'""')+'"';}
function validate(report,pairs,relevance){
 if(!report||typeof report.report_id!=='string'||!Array.isArray(report.items)||!Array.isArray(report.scores)||report.items.some(x=>!x||typeof x.url!=='string'||typeof x.title!=='string'||(x.summary!=null&&typeof x.summary!=='string'))||report.scores.some(x=>!x||typeof x.event_id!=='string'||!Array.isArray(x.members)))throw Error('报告格式不完整');
 const urls=new Set(report.items.map(x=>x.url)),events=new Set(report.scores.map(x=>x.event_id));
 for(const [table,required,key,values,field] of [[pairs,['report_id','pair_id','left','right','label','annotator','provenance'],'pair_id',['','same_event','different_event'],'label'],[relevance,['report_id','event_id','urls','relevant','annotator','provenance'],'event_id',['','0','1'],'relevant']]){
 if(required.some(h=>!table.headers.includes(h)))throw Error('标注 CSV 缺少必需列');
 const seen=new Set();for(const row of table.rows){if(row.report_id!==report.report_id)throw Error('材料属于不同报告，请选择同一批次文件');if(!row[key]||seen.has(row[key]))throw Error('标注 ID 缺失或重复');seen.add(row[key]);if(!values.includes(row[field]))throw Error('标注值无效');if(key==='pair_id'&&(!urls.has(row.left)||!urls.has(row.right)))throw Error('文章不在报告中');if(key==='event_id'&&!events.has(row.event_id))throw Error('推荐条目不在报告中');}}
 return true;
}
function safeLink(url){try{const u=new URL(url);return ['http:','https:'].includes(u.protocol)&&!u.username&&!u.password?u.href:null;}catch{return null;}}
const api={parseCSV,csv,validate,safeLink};if(typeof module!=='undefined')module.exports=api;
if(!root.document)return;
const $=id=>document.getElementById(id);let data=null,mode='pairs',index=0,dirty=false;let exported=new Set();
function node(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;}
function say(message){$('status').textContent=message;}
function list(){if(!data)return [];const q=$('search').value.toLowerCase();return data[mode].rows.filter(r=>{const field=mode==='pairs'?'label':'relevant';return (!$('pending').checked||!r[field])&&Object.values(r).join(' ').toLowerCase().includes(q);});}
function article(url){const item=data.report.items.find(x=>x.url===url);const a=node('article');if(!item){a.append(node('p','报告中没有这篇文章'));return a;}a.append(node('h2',item.title||'无标题'),node('p',item.published_at||'发表时间未知','meta'),node('p',item.summary||'暂无摘要，请打开来源核对。','summary'));const href=safeLink(url);if(href){const link=node('a','打开原文 ↗','source');link.href=href;link.target='_blank';link.rel='noopener noreferrer';a.append(link);}return a;}
function render(){
 const rows=list();index=Math.max(0,Math.min(index,rows.length-1));const area=$('workspace');area.replaceChildren();$('prev').disabled=!rows.length||index===0;$('next').disabled=!rows.length||index>=rows.length-1;$('position').textContent=rows.length?`${index+1} / ${rows.length}`:'';
 if(!rows.length){area.append(node('div',data?'没有符合条件的条目。可取消筛选或切换分栏。':'请先载入三份审核材料。','empty'));return;}
 const row=rows[index],field=mode==='pairs'?'label':'relevant';area.append(node('p',mode==='pairs'?'对照事件 · 判断对象、发生的事情与时间是否一致':'推荐相关性 · 判断内容是否值得进入公共精选','meta'));
 const cols=node('div',undefined,'columns');(mode==='pairs'?[row.left,row.right]:row.urls.split(' ').filter(Boolean)).forEach(u=>cols.append(article(u)));area.append(cols);
 const details=node('details');details.append(node('summary','查看模型线索与评分解释（非人工结论）'));if(mode==='pairs'){details.append(node('p',`候选类型：${row.candidate_kind||'未知'}；抽样层：${row.sampling_stratum||'未知'}；相似度：${row.cosine||'未知'}；阻断规则：${row.blockers||'无记录'}`));}else{const score=data.report.scores.find(s=>s.event_id===row.event_id);details.append(node('p',`注意力分：${score?.score??'未知'}；${(score?.explanation||[]).join(' ')}`));}area.append(details);
 const actions=node('div',undefined,'decision');const options=mode==='pairs'?[['same_event','同一事件'],['different_event','不同事件']]:[['1','值得推荐'],['0','不宜推荐']];options.push(['','暂不判断']);for(const [value,title]of options){const b=node('button',title);b.type='button';b.setAttribute('aria-pressed',String(row[field]===value));b.onclick=()=>{const who=$('reviewer').value.trim();if(value&&!who){say('请先填写审核者，再保存判断。');$('reviewer').focus();return;}row[field]=value;row.annotator=value?who:'';row.provenance=value?'human':'';dirty=true;exported.clear();render();say('判断已暂存在本页，请导出保存。');};actions.append(b);}actions.append(node('small',row[field]?`已标注 · ${row.annotator||'未知'} · ${row.provenance||'来源未知'}`:'尚未判断'));area.append(actions);
}
$('files').onchange=async()=>{if(dirty&&!confirm('本页有未导出的更改，载入新材料将替换它们。仍要继续？')){$('files').value='';return;}try{const files=Array.from($('files').files);const names=['report.json','pair-labels.csv','relevance-labels.csv'];if(names.some(n=>!files.some(f=>f.name===n)))throw Error('请一次选择三份完整材料');if(files.some(f=>f.size>30*1024*1024))throw Error('单个文件不能超过30MB');const contents=await Promise.all(names.map(n=>files.find(f=>f.name===n).text()));const next={report:JSON.parse(contents[0]),pairs:parseCSV(contents[1]),relevance:parseCSV(contents[2])};validate(next.report,next.pairs,next.relevance);data=next;index=0;dirty=false;exported.clear();$('export').disabled=false;$('export-relevance').disabled=false;say(`已载入 ${data.pairs.rows.length} 对事件、${data.relevance.rows.length} 项推荐。尚无人工质量验收结论。`);render();}catch(e){say('载入失败：'+e.message);}};
function download(name,text){const url=URL.createObjectURL(new Blob([text],{type:'text/csv;charset=utf-8'}));const a=node('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
for(const [id,table,name] of [['export','pairs','pair-labels.csv'],['export-relevance','relevance','relevance-labels.csv']])$(id).onclick=()=>{if(!data)return;download(name,csv(data[table]));exported.add(table);dirty=exported.size<2;say('已请求下载 '+name+'。请确认保存；两份标注均导出后可安全离开。');};
for(const tab of document.querySelectorAll('.tab'))tab.onclick=()=>{mode=tab.dataset.mode;index=0;document.querySelectorAll('.tab').forEach(t=>t.setAttribute('aria-pressed',String(t===tab)));render();};
$('search').oninput=()=>{index=0;render();};$('pending').onchange=()=>{index=0;render();};$('prev').onclick=()=>{index--;render();};$('next').onclick=()=>{index++;render();};addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='';}});
})(globalThis);
