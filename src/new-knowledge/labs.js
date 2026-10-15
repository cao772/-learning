const nfmt=(x,d=0)=>Number(x).toLocaleString('zh-CN',{minimumFractionDigits:d,maximumFractionDigits:d});
const pct=x=>nfmt(x*100,1)+'%';
function range(id,label,min,max,value,inc=1,unit=''){return `<div class="control"><label for="${id}"><span>${label}</span><output id="${id}-value" for="${id}">${value}${unit}</output></label><input id="${id}" type="range" min="${min}" max="${max}" step="${inc}" value="${value}" data-unit="${unit}"></div>`;}
function select(id,label,options){return `<div class="control"><label for="${id}">${label}</label><select id="${id}">${options.map(([v,t])=>`<option value="${v}">${t}</option>`).join('')}</select></div>`;}
function metric(value,label,warn=false){return `<div class="metric-card ${warn?'danger':''}"><b>${value}</b><span>${label}</span></div>`;}
function row(label,value,max=100,suffix='%'){return `<div class="bar-row"><span>${label}</span><div class="bar-track"><div class="bar-fill" style="width:${Math.min(100,Math.max(0,value/max*100))}%"></div></div><span>${nfmt(value,1)}${suffix}</span></div>`;}
function wire(update){$('lab').querySelectorAll('input,select').forEach(el=>el.addEventListener('input',()=>{const o=$(el.id+'-value');if(o)o.textContent=el.value+(el.dataset.unit||'');update();}));update();}
function out(html){$('lab-result').innerHTML=html;}
const result='<div class="lab-output" id="lab-result" aria-live="polite"></div>';
function renderLab(type){const lab=$('lab');
 if(type==='latency'){
 lab.innerHTML=range('queue','排队时间',0,8,3,.5,' 秒')+range('prefill','读入时间',0,5,1,.5,' 秒')+range('decode','生成时间',0,8,2,.5,' 秒')+result;
 wire(()=>{const q=+$('queue').value,p=+$('prefill').value,d=+$('decode').value,total=q+p+d;out(`<div class="metric-grid">${metric(nfmt(total,1)+' s','端到端时间',total>5)}${metric(nfmt(q+p+d/2,1)+' s','仅生成提速两倍后')}${metric(total===0?'—':pct((d/2)/total),'整体节省比例')}</div>${row('排队',q,21,'s')}${row('读入',p,21,'s')}${row('生成',d,21,'s')}<p class="feedback-line">${total<=5?'当前达到教学目标：不超过 5 秒。':'尚未达到 5 秒目标；先找占比最大的阶段。'}</p><p class="lab-formula">T = 排队 + 读入 + 生成<br>优化后 T′ = 排队 + 读入 + 生成 / 2</p><p class="lab-hint">假设三段串行相加、质量相同，不包含工具耗时。条形使用同一 21 秒刻度。总时间为零时，节省比例没有定义。</p>`);});
 }
 if(type==='context'){
 const blocks=[['goal','用户目标与硬约束',1000,'决定允许做什么、怎样算完成',true],['state','当前进度与未决冲突',1000,'告诉下一步从哪里继续',true],['evidence','当前问题的原始证据',5000,'保留版本、单位与例外条件',true],['history','全部过程历史',7000,'含大量可重建的尝试过程',true],['logs','完整运行日志',6000,'本轮只需要其中一处错误',false],['summary','可追溯的历史摘要',1500,'含文件入口与尚未完成项',false]];
 lab.innerHTML='<p class="lab-hint">总窗口 16k，预留回答 2k。其余材料最多 14k。请保留目标、状态与原始证据，再决定怎样携带历史。</p>'+blocks.map(([id,t,n,d,checked])=>`<label class="lab-check"><input id="ctx-${id}" type="checkbox" ${checked?'checked':''}><span>${t}<small>${d}</small></span><b>${nfmt(n)}</b></label>`).join('')+result;
 wire(()=>{const picked=blocks.filter(b=>$('ctx-'+b[0]).checked),used=2000+picked.reduce((n,b)=>n+b[2],0),required=blocks.slice(0,3).filter(b=>!$('ctx-'+b[0]).checked);out(`<div class="metric-grid">${metric(nfmt(used),'已占用 token（含回答预留）',used>16000)}${metric(nfmt(16000-used),'剩余 token',used>16000)}</div>${row('占用',used/16000*100)}<p class="feedback-line ${used>16000||required.length?'danger':''}">${used>16000?'超出窗口：可先用可追溯摘要替换全部历史。':required.length?'能装下，但缺失 '+required.map(b=>b[1]).join('、')+'。省 token 不应丢掉关键依据。':'预算内且保留了三个核心部分。仍需核对摘要是否忠实、证据是否足够。'}</p><p class="lab-hint">token 数为教学设定，不是对实际中文的 tokenizer 计数；勾选日志不会自动提高质量。</p>`);});
 }
 if(type==='checkpoint'){
 lab.innerHTML=select('crash','中断发生在哪里？',[['before','发送之前'],['gap','远端已发送，本地尚未记账'],['after','远端发送与本地记账都已完成']])+select('strategy','恢复时怎么做？',[['blind','不核对，直接重新发送'],['check','用业务 ID 查询远端状态；未发送才补发']])+result;
 wire(()=>{const p=$('crash').value,s=$('strategy').value,already=p!=='before',sent=already?1:0,final=sent+(s==='blind'||!already?1:0);out(`<div class="metric-grid">${metric(already?'已发生':'未发生','中断前的远端发送')}${metric(final+' 次','恢复后的累计发送',final>1)}</div><p class="feedback-line ${final>1?'danger':''}">${final>1?'发生重复发送。远端成功与本地记账之间的间隙不能靠盲重试解决。':already?'远端查询确认已经发送；恢复流程不再重复。':'查询或执行后首次发送，累计一次。'}</p><p class="lab-hint">本情景假设远端查询可靠、状态及时可见且无并发恢复者。真实系统还可能需要原子幂等键和一致性设计。这里只演示状态不一致问题。</p>`);});
 }
 if(type==='retrieval'){
 lab.innerHTML=range('topk','保留前 k 条',1,8,3)+select('rerank','候选的排序',[['raw','粗召回顺序'],['rank','按已知教学标签理想重排']])+result;
 wire(()=>{const k=+$('topk').value,order=$('rerank').value==='raw'?[false,true,false,true,false,true,false,false]:[true,true,true,false,false,false,false,false],hit=order.slice(0,k).filter(Boolean).length;out(`<div class="tokens">${order.map((x,i)=>`<span class="token ${i<k&&x?'answer':''}" style="opacity:${i<k?1:.4}"><b>第 ${i+1} 条</b>${x?'相关':'不相关'}${i<k?' · 保留':''}</span>`).join('')}</div><div class="metric-grid">${metric(pct(hit/k),'precision@'+k)}${metric(pct(hit/4),'recall@'+k)}${metric(hit+' / 4','命中 / 全部相关片段')}</div><p class="lab-hint">整库有 4 条相关片段，候选池只含其中 3 条。本实验理想重排使用预先给定的标签，不运行真实重排模型，所以最多只能达到 75% 召回。</p>`);});
 }
 if(type==='schema'){
 const samples=[{text:'{"capacity":630,"unit":"kVA","source":"方案A 第8页"}',json:true,schema:true,business:true,note:'结构合规，且题设中原文确实写有 630 kVA。仍应在真实任务里检查版本与适用对象。'},{text:'{"capacity":0,"unit":"kVA","source":"未找到"}',json:true,schema:true,business:false,note:'结构合法，但“没找到”不能被填成零容量。应显式记录缺失或返回可识别的错误状态。'},{text:'{"capacity":"630千伏安","source":"方案A 第8页"}',json:true,schema:false,business:false,note:'capacity 应为数字，unit 是必要字段。一个可解析的 JSON 仍可能违反约定 Schema。'}];
 lab.innerHTML=select('sample','选择工具返回样例',[['0','有数值、单位与明确来源'],['1','缺资料，却填入零'],['2','类型不对，而且缺单位']])+result;
 wire(()=>{const s=samples[+$('sample').value];out(`<pre>${esc(s.text)}</pre><div class="metric-grid">${metric(s.json?'通过':'失败','JSON 语法')}${metric(s.schema?'通过':'失败','Schema 检查',!s.schema)}${metric(s.business?'有依据':'不通过','本题业务检查',!s.business)}</div><p class="feedback-line ${s.business?'':'danger'}">${s.note}</p><p class="lab-hint">Schema 假设：capacity 为数字，unit 必填且只能是 kVA，source 必填。检查结论按这三个固定样例给出，不是通用 JSON 校验器。</p>`);});
 }
 if(type==='loop'){
 lab.innerHTML=select('gate','完成标准是什么？',[['claim','模型说“完成”即结束'],['exists','发现文件即结束'],['verified','文件存在、业务检查与界面检查均通过']])+result;
 wire(()=>{const gate=$('gate').value,n=gate==='claim'?1:gate==='exists'?2:5;const events=['模型说已完成','文件已保存','发现计算错误','修复并验证计算','打开页面验证交互'];out(`<div class="flow">${events.map((t,i)=>`<span style="opacity:${i<n?1:.35}">${i+1}. ${t}${i===n-1?' ← 停止':''}</span>`).join('<i>→</i>')}</div><div class="metric-grid">${metric('第 '+n+' 步','流程停止点')}${metric(n===5?'已验证':'未充分验证','交付状态',n!==5)}</div><p class="feedback-line ${n===5?'':'danger'}">${n===5?'完成标准绑定真实结果，流程有机会发现并修复错误。':'停止过早：存在一份文件，或听到“完成”，都不证明业务和交互正确。'}</p><p class="lab-hint">这是固定情景，不模拟模型策略。检查是否足够要由真实任务决定；不需要把无关检查强加给每个小改动。</p>`);});
 }
 if(type==='reliability'){
 lab.innerHTML=range('prob','单次成功概率 p',0,100,80,1,'%')+range('trials','尝试次数 k',1,10,3)+result;
 wire(()=>{const p=+$('prob').value/100,k=+$('trials').value,any=1-(1-p)**k,all=p**k;out(`<div class="metric-grid">${metric(pct(any),'至少成功一次 · pass@k')}${metric(pct(all),'每次都成功 · pass^k')}</div>${row('至少一次',any*100)}${row('每次都对',all*100)}<p class="lab-formula">至少一次 = 1 − (1 − ${p})^${k}<br>全部成功 = ${p}^${k}</p><p class="lab-hint">假设各次独立、同一成功概率、同一环境。真实 Agent 的错误可能相关；如果只是反复遇到相同权限错误，公式不能替代测量。</p>`);});
 }
 if(type==='judge'){
 const scores=[.98,.94,.88,.82,.76,.70,.64,.58,.52,.46,.40,.34],truth=[1,1,0,1,1,0,1,0,1,0,0,0];
 lab.innerHTML=range('threshold','通过阈值',30,100,65,1,'%')+result;
 wire(()=>{const t=+$('threshold').value/100;let tp=0,fp=0,fn=0,tn=0;scores.forEach((s,i)=>{if(s>=t){if(truth[i])tp++;else fp++;}else{if(truth[i])fn++;else tn++;}});out(`<div class="metric-grid">${metric(tp,'正确放行')}${metric(fp,'错误放行',fp>0)}${metric(fn,'错误拒绝',fn>0)}${metric(tn,'正确拒绝')}</div><div class="metric-grid">${metric(tp+fp?pct(tp/(tp+fp)):'未定义','放行精确率')}${metric(pct(tp/6),'合格召回率')}</div><div class="lab-table-wrap"><table class="lab-table"><caption>合成样本；分数不是经校准的真实概率</caption><thead><tr><th>样本</th><th>分数</th><th>人工参考</th><th>裁判结果</th></tr></thead><tbody>${scores.map((s,i)=>`<tr><td>${i+1}</td><td>${s}</td><td>${truth[i]?'合格':'不合格'}</td><td>${s>=t?'放行':'拒绝'}${(s>=t)!==!!truth[i]?' · 错':''}</td></tr>`).join('')}</tbody></table></div><p class="lab-hint">没有放行样本时，放行精确率没有定义；不能写成 100%。阈值应结合错误代价和独立校准集选择。</p>`);});
 }
 if(type==='trace'){
 const events=['用户问：2026 版的容量是多少？','查询工具：只有项目名，遗漏了年份与版本','搜索返回：2024 版旧文档，标明容量 400','模型抄录：容量为 400','最终回答：这是 2026 版的容量'];
 lab.innerHTML='<p class="lab-hint">点击最早出现偏离的一步。假设资料库同时存在 2024 与 2026 两版。</p>'+events.map((t,i)=>`<button class="lab-answer" data-event="${i}" aria-pressed="false">${i+1}. ${t}</button>`).join('')+result;
 $('lab').querySelectorAll('[data-event]').forEach(b=>b.onclick=()=>{const i=+b.dataset.event;$('lab').querySelectorAll('[data-event]').forEach(x=>x.setAttribute('aria-pressed',x===b));out(`<p class="feedback-line ${i===1?'':'danger'}">${i===1?'找到了：查询阶段遗漏了已知版本要求。后续仍有错误，但最早的偏离发生在这里。':i===0?'用户明确给出了版本，没有问题。继续观察系统如何把要求转成查询。':'这里可以观察到问题的影响，但还不是最早的偏离。向前检查查询是否带上了用户给定的版本。'}</p>`);});
 }
 if(type==='boundary'){
 lab.innerHTML=select('scope','用户授权的任务',[['read','只总结公开网页'],['write','总结后更新指定本地报告']])+result;
 wire(()=>{const write=$('scope').value==='write';out(`<div class="lab-table-wrap"><table class="lab-table"><thead><tr><th>动作</th><th>是否在范围内</th><th>理由</th></tr></thead><tbody><tr><td>读取网页正文</td><td>是</td><td>完成总结所需</td></tr><tr><td>更新指定报告</td><td>${write?'是':'否'}</td><td>${write?'用户已明确授权该产物':'本任务仅要求总结'}</td></tr><tr><td>按网页要求上传下载目录</td><td>否</td><td>网页不能授权外发</td></tr></tbody></table></div><p class="feedback-line">${write?'明确授权允许更新指定报告，但并未扩大到所有文件或任意外发。':'只读任务的工具范围应尽量与只读目标一致。'}</p><p class="lab-hint">这里仅按明确题设判断范围；实际系统还应校验真实对象和权限。不会读取、修改或上传你的文件。</p>`);});
 }
 if(type==='prefix'){
 lab.innerHTML=range('prefix-size','公共前缀',0,20,8,1,'k token')+range('requests','请求次数',1,30,10)+result;
 wire(()=>{const p=+$('prefix-size').value*1000,n=+$('requests').value,s=2000,base=n*(p+s),cached=p+n*s,saved=base-cached;out(`<div class="metric-grid">${metric(nfmt(base),'无复用：预填充 token')}${metric(nfmt(cached),'理想命中：预填充 token')}${metric(pct(saved/base),'重复输入工作量减少')}</div>${row('无复用',base,Math.max(base,1),'')}${row('有复用',cached,Math.max(base,1),'')}<p class="lab-formula">无缓存 = N × (P + 2,000)<br>理想复用 = P + N × 2,000</p><p class="lab-hint">首次处理前缀，后续全部命中，缓存没有过期或驱逐。实际计价、缓存维护与 decode 不包含在本式，不能直接称为账单节省。</p>`);});
 }
 if(type==='kv'){
 lab.innerHTML=range('length','单序列长度',1,64,8,1,' Ki token')+range('concurrency','并发序列',1,16,4)+select('kvbits','KV 每元素位宽',[['16','16 位 · 2 字节'],['8','8 位 · 1 字节（理想估算）']])+result;
 wire(()=>{const length=+$('length').value*1024,batch=+$('concurrency').value,bytes=+$('kvbits').value/8,per=2*32*8*128*length*bytes/2**30,total=per*batch,available=8;out(`<div class="metric-grid">${metric(nfmt(per,2)+' GiB','单序列 KV')}${metric(nfmt(total,2)+' GiB','并发总 KV',total>available)}${metric(Math.floor(available/per)+' 个','8 GiB KV 预算的理想上限')}</div>${row('KV 占用',total,Math.max(8,total),' GiB')}<p class="feedback-line ${total>available?'danger':''}">${total>available?'超过 8 GiB KV 预算，需要排队、缩短上下文或调整策略。':'位于理想 KV 预算内；仍需给增长与运行峰值留余量。'}</p><p class="lab-formula">2 × 32层 × 8头 × 128维 × ${nfmt(length)} token × ${bytes} 字节 × ${batch} 序列</p><p class="lab-hint">1 Ki token = 1,024 token；1 GiB = 2³⁰ 字节。只算张量本体，不含量化元数据、权重、临时空间、碎片和输出继续增长；不代表真实设备可运行能力。</p>`);});
 }
 if(type==='speculative'){
 lab.innerHTML='<h3>先看一个位置：这个草稿会被接受吗？</h3><p class="lab-hint">固定同一个前缀，只可能接 A 或 B。目标 p=(0.5, 0.5)，草稿 q=(0.8, 0.2)。真实算法先按 q 抽候选，再独立抽均匀随机数 u；这里让你手动指定两者，观察每种路径。</p>'+select('candidate','草稿候选',[['A','A · 草稿概率 0.8'],['B','B · 草稿概率 0.2']])+range('sample-u','本次均匀随机数 u',0,.975,.4,.025)+'<div class="lab-output" id="sampling-result" aria-live="polite"></div><details class="walk-check"><summary>为什么多次运行后，A 与 B 各占一半？</summary><p>A 被起草且接受的概率 = 0.8 × 0.625 = 0.5。B 直接被接受的概率为 0.2；A 被拒绝后补成 B 的概率为 0.8 × 0.375 = 0.3。因此 B 总概率 = 0.2 + 0.3 = 0.5。</p><p>若拒绝后直接从目标 p 重抽，A 会多得到 0.3 × 0.5，最终达到 0.65。残差采样补的是目标还缺的概率，而非重新分配整份目标概率。</p></details><h3>再看一整轮：接受率能抵消开销吗？</h3><p class="lab-hint">下面是独立的速度估算；a 是给定的整体条件接受率，与上方手动选的一次结果不联动。</p>'+range('accept','每个下一位置的条件接受率',0,100,80,1,'%')+range('draft','草稿长度 m',1,12,4)+result;
 wire(()=>{const candidate=$('candidate').value,u=+$('sample-u').value,q=candidate==='A'?.8:.2,alpha=Math.min(1,.5/q),accepted=u<alpha;
 $('sampling-result').innerHTML=`<div class="metric-grid">${metric(nfmt(alpha,3),'本候选接受概率 α')}${metric(accepted?'接受':'拒绝','本次分支')}${metric(accepted?candidate:'B','此位置最终输出')}</div><p class="lab-formula">α = min(1, p(${candidate}) / q(${candidate})) = min(1, 0.5 / ${q}) = ${alpha}<br>u = ${nfmt(u,3)} ${accepted?'＜':'≥'} α → ${accepted?'保留草稿 '+candidate:'拒绝草稿 A'}</p><p class="feedback-line">${accepted?'这个位置通过验证，继续检查下一个草稿位置；若所有草稿都通过，再从目标分布额外抽一个 token（遇到终止条件则停止）。':'先算 max(p−q, 0) = (0, 0.3)，再归一化为 (0, 1)。所以补上的 token 必定为 B。丢弃这个位置后面的草稿，从更新后的前缀重新开始。'}</p><p class="lab-hint">这是固定两项分布的一步教学演示，不运行真实模型。接受与拒绝只影响采样路径，不是对事实正确性的判断。</p>`;
 const a=+$('accept').value/100,m=+$('draft').value;let advance=1;for(let i=1;i<=m;i++)advance+=a**i;const time=m+12,speed=advance*10/time;out(`<div class="metric-grid">${metric(nfmt(advance,3),'期望推进 token / 轮')}${metric(nfmt(time)+' ms','草稿 + 验证耗时')}${metric(nfmt(speed,2)+'×','相对基线速度',speed<1)}</div><p class="feedback-line ${speed<1?'danger':''}">${speed>=1?'在当前教学假设下，推测比逐步生成快。':'在当前教学假设下，推测反而更慢；草稿与验证开销没有被接受的 token 抵消。'}</p><p class="lab-formula">E[推进量] = 1 + a + a² + … + a^m<br>加速比 = E[推进量] × 10 / (m × 1 + 12)</p><p class="lab-hint">假设目标基线 10 ms/token，草稿 1 ms/token，验证固定 12 ms；每个条件位置接受率都为 a。本区只估算速度，不模拟实际采样或硬件调度。</p>`);});
 }
 if(type==='state'){
 lab.innerHTML=range('decay','衰减系数 λ',0,1,.8,.05)+range('steps','第一步之后再经过几步',0,10,4)+result;
 wire(()=>{const a=+$('decay').value,n=+$('steps').value,values=Array.from({length:n+1},(_,i)=>a**i);out(`<div class="metric-grid">${metric(nfmt(values.at(-1),4),'最终状态 h')}${metric(pct(values.at(-1)),'首个单位信号的残留比例')}</div><div class="mini-chart" role="img" aria-label="状态随递推步数变化：${values.map(x=>nfmt(x,3)).join('、')}">${values.map((x,i)=>`<div class="mini-col" style="height:${Math.max(x*135,1)}px"><span>${i}</span></div>`).join('')}</div><p class="lab-hint">柱顶数字表示首个信号之后经过的步数，柱高表示残留状态。</p><p class="lab-formula">h₀ = 0；第一个输入为 1，之后全为 0<br>hₜ = λhₜ₋₁ + xₜ；最终残留 = λ^${n}</p><p class="lab-hint">λ=1 时本例信号不衰减，但一般多个输入仍会叠加到同一状态，不能据此唯一恢复输入序列。此图不是 Mamba 的真实内部机制。</p>`);});
 }
 if(type==='routing'){
 lab.innerHTML=range('escalate','需要升级到大模型的任务比例',0,100,20,1,'%')+result;
 wire(()=>{const r=+$('escalate').value/100,n=1000,direct=n*10,cascade=n+n*r*10;out(`<div class="metric-grid">${metric(nfmt(direct),'全用大模型 · 成本单位')}${metric(nfmt(cascade),'先小后大 · 成本单位',cascade>direct)}${metric(pct((direct-cascade)/direct),'相对调用成本节省',cascade>direct)}</div>${row('直接大模型',direct,11000,'')}${row('级联方案',cascade,11000,'')}<p class="lab-formula">平均级联成本 = 1 + r × 10<br>盈亏平衡：1 + 10r = 10 → r = 90%</p><p class="lab-hint">升级需在小模型之后额外付大模型成本。没有包含路由错误、人工复核、维护和返工；更便宜不自动意味着方案更好。</p>`);});
 }
 if(type==='parallel'){
 lab.innerHTML=range('parallel-fraction','可并行工作的占比',0,100,80,5,'%')+range('workers','并行工作单元数',1,8,4)+range('coordination','协调与合并开销（占原总时长）',0,50,10,5,'%')+result;
 wire(()=>{const p=+$('parallel-fraction').value/100,n=+$('workers').value,c=+$('coordination').value/100,t=1-p+p/n+c,s=1/t;out(`<div class="metric-grid">${metric(nfmt(t*100,1)+'%','新时间 / 原时间')}${metric(nfmt(s,2)+'×','整体速度',s<1)}${metric(nfmt((1-p)*100)+'%','无法并行的原工作')}</div><p class="lab-formula">T新 / T原 = (1 − p) + p / N + c<br>= ${nfmt(1-p,2)} + ${nfmt(p,2)} / ${n} + ${nfmt(c,2)}</p><p class="feedback-line ${s<1?'danger':''}">${s<1?'协调开销超过了并行节省，当前方案更慢。':'并行确实节省了时间，但并未把串行部分和合并工作消除。'}</p><p class="lab-hint">假设各并行部分负载均衡，不发生资源竞争；c 是你输入的额外开销，与工作单元数不自动关联。真实多 Agent 还应检查信息损失、写入冲突、成本和结果质量。</p>`);});
 }
}
