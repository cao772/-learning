const fs=require('fs');
const path=require('path');
const root=path.resolve(__dirname,'..');
const folder=path.join(root,'src/new-knowledge');
const lessons=require(path.join(folder,'lessons.cjs'));
const sources=require(path.join(folder,'sources.cjs'));
const walkthroughs=require(path.join(folder,'walkthroughs.cjs'));
for(const l of lessons){l.walkthrough=walkthroughs[l.id];if(!l.walkthrough||!l.walkthrough.scene||!l.walkthrough.steps?.length||l.walkthrough.steps.some(s=>s.length!==2||s.some(x=>typeof x!=='string'||!x.trim()))||l.walkthrough.check?.length!==2)throw Error('Incomplete walkthrough '+l.id);}

const groups=[{title:'读懂信息',subtitle:'从资讯到可用证据',range:'01—04'},{title:'让 Agent 做成事',subtitle:'从工具到可靠评测',range:'05—08'},{title:'看清系统的代价',subtitle:'从失败轨迹到内存预算',range:'09—12'},{title:'理解新方法，做出选择',subtitle:'从生成加速到系统取舍',range:'13—16'}];
if(lessons.length!==16)throw Error('Expected 16 lessons');
const ids=new Set();
for(const l of lessons){
 if(ids.has(l.id))throw Error('Duplicate '+l.id);ids.add(l.id);
 for(const key of ['id','group','title','question','time','tag','refs','intro','concepts','example','lab','labTitle','labDesc','prediction','quiz','recap'])if(l[key]===undefined)throw Error(l.id+' missing '+key);
 if(l.intro.length!==4||!l.concepts.length||!l.example.steps.length||l.quiz.options.length!==3)throw Error('Incomplete '+l.id);
 if(!Number.isInteger(l.quiz.correct)||l.quiz.correct<0||l.quiz.correct>2)throw Error('Quiz '+l.id);
 for(const c of l.concepts)if(c.length!==4)throw Error('Concept '+l.id);
 for(const ref of l.refs)if(!sources[ref])throw Error('Source '+ref);
}
const base=fs.readFileSync(path.join(root,'src/course-template.html'),'utf8').match(/<style>([\s\S]*?)<\/style>/)[1];
const js=x=>JSON.stringify(x).replace(/</g,'\\u003c');
const html=fs.readFileSync(path.join(folder,'template.html'),'utf8').replace('/* BASE_STYLE */',()=>base).replace('/* COURSE_DATA */',()=>`const LESSONS=${js(lessons)};\nconst SOURCES=${js(sources)};\nconst GROUPS=${js(groups)};`).replace('/* APP_CODE */',()=>fs.readFileSync(path.join(folder,'app.js'),'utf8')).replace('/* LAB_CODE */',()=>fs.readFileSync(path.join(folder,'labs.js'),'utf8'));
if(/<script[^>]+src=|<link[^>]+(?:stylesheet|https?:)|fetch\(|XMLHttpRequest|@import/.test(html))throw Error('Unexpected runtime network dependency');
for(const match of html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g))new (require('vm').Script)(match[1]);
fs.writeFileSync(path.join(root,'new-knowledge.html'),html);
const chars=JSON.stringify(lessons).match(/[\u3400-\u9fff]/g).length;
fs.writeFileSync(path.join(root,'新知实验室-目录.md'),'# 循序 · 新知实验室\n\n2026-10-13 编排，16 个单元。完整建议学习时间约 '+Math.round(lessons.reduce((n,l)=>n+l.time,0)/60*10)/10+' 小时，按理解速度调整。\n\n'+groups.map((g,i)=>'## '+g.title+'\n\n'+lessons.filter(l=>l.group===i).map(l=>`${String(lessons.indexOf(l)+1).padStart(2,'0')}. **${l.title}**（约 ${l.time} 分钟）\n   - 问题：${l.question}\n   - 实验：${l.labTitle}\n   - 入口：[打开课程](new-knowledge.html#${l.id}/0)`).join('\n')+'\n').join('\n'));
console.log(JSON.stringify({file:'new-knowledge.html',bytes:Buffer.byteLength(html),lessons:lessons.length,walkthroughSteps:lessons.reduce((n,l)=>n+l.walkthrough.steps.length,0),concepts:lessons.reduce((n,l)=>n+l.concepts.length,0),workedSteps:lessons.reduce((n,l)=>n+l.example.steps.length,0),labs:lessons.length,quizzes:lessons.length,chineseCharacters:chars,sources:Object.keys(sources).length}));
