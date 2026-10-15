labs.tokenizer=()=>{
 $('lab-body').innerHTML='<div class="choices"><button class="btn" data-split="0" aria-pressed="true">字符级</button><button class="btn" data-split="1" aria-pressed="false">子词合并</button><button class="btn" data-split="2" aria-pressed="false">整个词</button></div><div class="tokens" id="split-tokens"></div><div class="metrics" id="split-metrics"></div>'+resultBox();
 const forms=[['l','e','a','r','n','i','n','g'],['learn','ing'],['learning']];
 function update(i){$('split-tokens').innerHTML=forms[i].map(t=>`<span class="token answer">${t}</span>`).join('');$('split-metrics').innerHTML=metric('这个词的 token 数',forms[i].length)+metric('原始字符数',8);$('lab-result').textContent=['字符级覆盖灵活，但序列更长。此处按英文字符拆分，不代表真实字节级实现。','这里假设词表中已有 learn 和 ing。需要遵循训练时学到的合并规则，不是按人类语义临时拆分。','整词变成一个 token，需要词表包含它。为所有词都建立独立条目会扩大词表，且仍需处理新词。'][i];document.querySelectorAll('[data-split]').forEach(b=>b.setAttribute('aria-pressed',+b.dataset.split===i?'true':'false'))}
 document.querySelectorAll('[data-split]').forEach(b=>b.onclick=()=>update(+b.dataset.split));update(0);
};
labs.embedding=()=>{
 $('lab-body').innerHTML=range('vx','v 的 x 坐标',-2,2,.1,1)+range('vy','v 的 y 坐标',-2,2,.1,1)+'<div class="math-note">固定 u=(1,0)，v=(x,y)</div><div class="metrics" id="emb-metrics"></div>'+resultBox();
 watch(['vx','vy'],()=>{const x=+$('vx').value,y=+$('vy').value,n=Math.hypot(x,y);$('vx-value').textContent=fixed(x,1);$('vy-value').textContent=fixed(y,1);$('emb-metrics').innerHTML=metric('点积 u·v',fixed(x,2))+metric('v 的长度',fixed(n,3))+metric('余弦相似度',n?fixed(x/n,3):'未定义');$('lab-result').textContent=n?`点积=${fixed(x,1)}。余弦=${fixed(x,1)} / ${fixed(n,3)} = ${fixed(x/n,3)}。它比较方向，不是自动识别两个概念是否相同。`:'v=(0,0) 是零向量，余弦分母为0，不能把结果当成0或1。'});
};
labs.loss=()=>{
 $('lab-body').innerHTML=range('target-p','所有目标位置的概率 p',.05,.95,.05,.25)+'<div class="metrics" id="loss-metrics"></div>'+resultBox();
 watch(['target-p'],()=>{const p=+$('target-p').value,L=-Math.log(p);$('target-p-value').textContent=pct(p);$('loss-metrics').innerHTML=metric('平均交叉熵 · nats',fixed(L))+metric('困惑度',fixed(Math.exp(L),2));$('lab-result').textContent=`−ln(${fixed(p,2)})=${fixed(L)}；exp(L)=1/p=${fixed(1/p,2)}。这里各目标位置概率相同；一般情形要先平均 log 概率，不能先平均原始概率。`});
};
labs.shapes=()=>{
 $('lab-body').innerHTML=range('shape-t','序列长度 T',2,16,1,4)+'<div class="math-note" id="shape-path"></div><div class="metrics" id="shape-metrics"></div>'+resultBox();
 watch(['shape-t'],()=>{const t=+$('shape-t').value;$('shape-t-value').textContent=t;$('shape-path').innerHTML=`ID [2,${t}]<br>Embedding [2,${t},8]<br>每头 Q/K/V [2,2,${t},4]<br>注意力分数 [2,2,${t},${t}]<br>Logits [2,${t},10]`;$('shape-metrics').innerHTML=metric('分数矩阵元素数',4*t*t)+metric('Logits 元素数',20*t);$('lab-result').textContent=`注意力分数为 2×2×${t}²=${4*t*t}，输出分数为 2×${t}×10=${20*t}。T翻倍时前者4倍、后者2倍；高效注意力实现可避免完整存储T×T矩阵，但这个关系仍帮助理解运算。`});
};
labs.position=()=>{
 $('lab-body').innerHTML=range('pos-m','查询位置 m',0,12,1,1)+range('pos-n','键位置 n',0,12,1,3)+'<div class="metrics" id="pos-metrics"></div>'+resultBox();
 watch(['pos-m','pos-n'],()=>{const m=+$('pos-m').value,n=+$('pos-n').value,angle=(n-m)*30,score=Math.cos(angle*Math.PI/180);$('pos-m-value').textContent=m;$('pos-n-value').textContent=n;$('pos-metrics').innerHTML=metric('相对位移',n-m)+metric('相对角度',angle+'°')+metric('旋转后点积',fixed(score));$('lab-result').textContent=`cos((${n}−${m})×30°)=${fixed(score)}。向量固定且使用单频旋转；图例只计算位置关系，不计算因果掩码或最终注意力权重。`});
};
labs.optimization=()=>{
 $('lab-body').innerHTML=range('opt-lr','学习率 η',.05,1.2,.05,.1)+'<table class="calc-table"><thead><tr><th>步数</th><th>w</th><th>L(w)</th></tr></thead><tbody id="opt-rows"></tbody></table>'+resultBox();
 watch(['opt-lr'],()=>{const lr=+$('opt-lr').value;$('opt-lr-value').textContent=fixed(lr,2);let w=0;const rows=[];for(let i=0;i<=8;i++){rows.push(`<tr><td>${i}</td><td>${fixed(w,3)}</td><td>${fixed((w-3)**2,3)}</td></tr>`);w-=lr*2*(w-3)}$('opt-rows').innerHTML=rows.join('');$('lab-result').textContent=lr<.5?'参数逐步靠近3，损失下降；步长很小时会较慢。':lr===.5?'这个特殊二次函数一步到达最低点。不要把0.5当成通用最优学习率。':lr<1?'参数在最低点两侧摆动，偏差幅度逐步缩小。':lr===1?'误差因子是−1，参数在0和6之间震荡，损失不降。':'误差因子的绝对值大于1，参数在两侧越走越远，损失发散。'});
};
labs.lora=()=>{
 $('lab-body').innerHTML=range('lora-r','LoRA 秩 r',1,64,1,8)+'<div class="math-note" id="lora-shape"></div><div class="metrics" id="lora-metrics"></div>'+resultBox();
 watch(['lora-r'],()=>{const r=+$('lora-r').value,n=2048*r;$('lora-r-value').textContent=r;$('lora-shape').textContent=`A: ${r}×1024；B: 1024×${r}；BA: 1024×1024`;$('lora-metrics').innerHTML=metric('原矩阵参数','1,048,576')+metric('A+B 可训练参数',n.toLocaleString())+metric('相对比例',pct(n/1048576));$('lab-result').textContent=`r(d_in+d_out)=${r}×2048=${n}。底座矩阵仍存在；这个比例不包含其他层、激活、梯度或优化器的全部内存。`});
};
labs.baseline=()=>{
 $('lab-body').innerHTML=range('eval-n','测试样本量 n',20,1000,20,20)+'<div class="math-note">固定观察正确率 p̂=0.9<br>SE ≈ √(p̂(1−p̂)/n)</div><div class="metrics" id="base-metrics"></div>'+resultBox();
 watch(['eval-n'],()=>{const n=+$('eval-n').value,se=Math.sqrt(.09/n);$('eval-n-value').textContent=n+' 题';$('base-metrics').innerHTML=metric('正确题数 / 总数',Math.round(.9*n)+' / '+n)+metric('粗略标准误',pct(se));$('lab-result').textContent=`观察比例都是90%，但n=${n}时二项近似标准误约${pct(se)}。这里只解释样本量影响，假设样本独立且同分布；不把这个数当作正式置信区间或方法优劣检验。`});
};
labs.returns=()=>{
 $('lab-body').innerHTML=range('gamma','折扣因子 γ',0,1,.05,.9)+'<div class="math-note">短路线：[1, 0, 0]<br>长路线：[0, 0, 2]</div><div class="metrics" id="return-metrics"></div>'+resultBox();
 watch(['gamma'],()=>{const g=+$('gamma').value,long=2*g*g;$('gamma-value').textContent=fixed(g,2);$('return-metrics').innerHTML=metric('短路线回报','1.00')+metric('长路线回报',fixed(long,2));$('lab-result').textContent=`长路线=2×${fixed(g,2)}²=${fixed(long,2)}，${Math.abs(long-1)<1e-6?'两者相同':long>1?'长路线更优':'短路线更优'}。目标偏好随着折扣改变，不是路线的客观好坏突然变化。`});
};
labs.bellman=()=>{
 $('lab-body').innerHTML=range('vnext','下一状态价值 V(s′)',0,2,.1,1)+'<label class="switch"><input type="checkbox" id="terminal">下一状态已经终止（后续价值取 0）</label><div class="math-note">r=0，γ=0.9，V(s)=0.2，α=0.5</div><div class="metrics" id="td-metrics"></div>'+resultBox();
 watch(['vnext','terminal'],()=>{const v=+$('vnext').value,terminal=$('terminal').checked,target=terminal?0:.9*v,delta=target-.2,next=.2+.5*delta;$('vnext-value').textContent=fixed(v,1);$('td-metrics').innerHTML=metric('TD 目标',fixed(target,2))+metric('TD 误差',fixed(delta,2))+metric('更新后的 V(s)',fixed(next,2));$('lab-result').textContent=terminal?'本例即时奖励仍为0，终止后无未来奖励，所以目标为0，当前V向0修正。终止不代表每次奖励必须为0；这里是明确设定。':`目标=0+0.9×${fixed(v,1)}=${fixed(target,2)}；误差=${fixed(delta,2)}；V新=0.2+0.5×误差=${fixed(next,2)}。`});
};
labs.kl=()=>{
 $('lab-body').innerHTML=range('kl-p','当前第一动作概率 a',.05,.95,.05,.8)+range('kl-beta','KL 系数 β',0,3,.1,2)+'<div id="kl-bars"></div><div class="metrics" id="kl-metrics"></div>'+resultBox();
 watch(['kl-p','kl-beta'],()=>{const p=+$('kl-p').value,b=+$('kl-beta').value,k=p*Math.log(p/.5)+(1-p)*Math.log((1-p)/.5);$('kl-p-value').textContent=pct(p);$('kl-beta-value').textContent=fixed(b,1);$('kl-bars').innerHTML=bars(['当前动作1','参考动作1'],[p,.5]);$('kl-metrics').innerHTML=metric('期望奖励',fixed(p,2))+metric('KL · nats',fixed(k))+metric('奖励 − βKL',fixed(p-b*k));$('lab-result').textContent=`KL方向是当前p到参考q。参考p=q时KL=0、组合目标=0.5。当前目标${fixed(p-b*k)}，说明提高奖励与偏离参考之间要按β权衡。`});
};
labs.rewardmodel=()=>{
 $('lab-body').innerHTML=range('rm-a','奖励分数 rA',-3,6,.5,2)+range('rm-b','奖励分数 rB',-3,6,.5,1)+'<div class="metrics" id="rm-metrics"></div>'+resultBox();
 watch(['rm-a','rm-b'],()=>{const a=+$('rm-a').value,b=+$('rm-b').value,p=sigmoid(a-b);$('rm-a-value').textContent=fixed(a,1);$('rm-b-value').textContent=fixed(b,1);$('rm-metrics').innerHTML=metric('分差',fixed(a-b,1))+metric('P(A 优于 B)',pct(p))+metric('标签偏好 A 的损失',fixed(-Math.log(p)));$('lab-result').textContent=`σ(${fixed(a-b,1)})=${fixed(p,3)}。这是偏好模型预测；两分数同时加同一常数时，分差和损失不变。`});
};
labs.search=()=>{
 $('lab-body').innerHTML=range('search-c','探索权重 c',0,3,.1,1)+'<table class="lab-table"><thead><tr><th>分支</th><th>Q</th><th>P</th><th>n</th><th>选择分数</th></tr></thead><tbody><tr><td>A</td><td>0.7</td><td>0.6</td><td>9</td><td id="score-a"></td></tr><tr><td>B</td><td>0.5</td><td>0.4</td><td>1</td><td id="score-b"></td></tr></tbody></table><div class="math-note">N=10；Q+cP√N/(1+n)</div>'+resultBox();
 watch(['search-c'],()=>{const c=+$('search-c').value,a=.7+c*.6*Math.sqrt(10)/10,b=.5+c*.4*Math.sqrt(10)/2;$('search-c-value').textContent=fixed(c,1);$('score-a').textContent=fixed(a);$('score-b').textContent=fixed(b);$('lab-result').textContent=`本次优先选择 ${a>b?'A':'B'}。这是排序分数，不是概率；没有实际扩展与回传，改变c仅演示一次选择如何权衡Q与探索。`});
};
labs.tools=()=>{
 let step=0;
 $('lab-body').innerHTML='<label class="switch"><input type="checkbox" id="tool-fail">模拟工具执行失败</label><div class="step-control"><button class="btn" id="tool-back">上一步</button><button class="btn primary" id="tool-next">下一步</button><span class="small" id="tool-counter"></span></div><div class="walk-stage" id="tool-stage"></div>'+resultBox();
 function update(){const fail=$('tool-fail').checked,steps=['收到问题：37 × 24 等于多少？','形成请求：multiply(a=37, b=24)。此时尚未取得执行结果。',fail?'执行观察：工具超时，未拿到结果。':'执行观察：浏览器本地计算 37 × 24 = '+(37*24)+'。',fail?'最终状态：本次工具验证未完成。可按任务条件重试，不能声称已被工具确认。':'最终回答：37 × 24 = '+(37*24)+'。依据是上一步的真实本地计算结果。'];$('tool-stage').textContent=steps[step];$('tool-counter').textContent=(step+1)+' / 4';$('tool-back').disabled=step===0;$('tool-next').disabled=step===3;$('lab-result').textContent='这是确定性的浏览器内流程演示，不调用远程模型。工具请求、执行观察和最终回答必须分开记录。'}
 $('tool-back').onclick=()=>{step=Math.max(0,step-1);update()};$('tool-next').onclick=()=>{step=Math.min(3,step+1);update()};$('tool-fail').onchange=()=>{step=0;update()};update();
};
labs.rag=()=>{
 $('lab-body').innerHTML='<div class="math-note">问题：项目 A 的报销上限是多少？</div><div class="control"><label for="evidence">检索到的证据</label><select id="evidence"><option value="right">项目 A 上限 300 元</option><option value="wrong">只有项目 B 上限 500 元</option><option value="conflict">A 300 元，与另一个无日期版本 A 400 元</option></select></div><div class="walk-stage" id="rag-answer"></div>'+resultBox();
 watch(['evidence'],()=>{const key=$('evidence').value;$('rag-answer').textContent={right:'有依据的回答：按当前项目 A 条款，上限为 300 元。',wrong:'证据不足：当前只找到项目 B 规定，无法据此回答 A 的金额。',conflict:'存在冲突：两份材料给出不同金额，需要核对生效日期、适用范围或权威版本。'}[key];$('lab-result').textContent='固定资料演示；未运行向量数据库或生成模型。重点是证据与具体实体、金额、版本的对应关系，而不是让相似内容自动变成答案。'});
};
labs.world=()=>{
 $('lab-body').innerHTML=range('world-b','模型每步偏差 b（米）',-.5,.5,.05,.1)+range('world-n','想象步数 N',1,20,1,10)+'<div class="metrics" id="world-metrics"></div>'+resultBox();
 watch(['world-b','world-n'],()=>{const b=+$('world-b').value,n=+$('world-n').value;$('world-b-value').textContent=fixed(b,2)+' m';$('world-n-value').textContent=n;$('world-metrics').innerHTML=metric('真实位置',n+' m')+metric('模型预测',fixed(n*(1+b),2)+' m')+metric('累计偏差',fixed(n*b,2)+' m');$('lab-result').textContent=`固定加性偏差下，误差=N×b=${fixed(n*b,2)}米。实际非线性环境误差可能累积、放大或抵消；这个算例不代表所有世界模型的误差曲线。`});
};
labs.scenario=()=>{
 const l=lessons[state.lesson];const answered={};
 $('lab-body').innerHTML=l.cases.map((c,i)=>`<section class="scenario-row"><p><strong>${i+1}.</strong> ${c[0]}</p><div class="choices"><button class="btn" data-case="${i}" data-value="true" aria-pressed="false">合理</button><button class="btn" data-case="${i}" data-value="false" aria-pressed="false">不合理</button></div><p class="small" id="case-result-${i}" aria-live="polite">先判断，再看解释。</p></section>`).join('')+resultBox();
 $('lab-result').textContent='这是判断练习。操作只记录本次实验的选择，不自动标记整课完成。';
 document.querySelectorAll('[data-case]').forEach(b=>b.onclick=()=>{const i=+b.dataset.case,value=b.dataset.value==='true',ok=value===l.cases[i][1];answered[i]=ok;document.querySelectorAll(`[data-case="${i}"]`).forEach(x=>x.setAttribute('aria-pressed',x===b?'true':'false'));$('case-result-'+i).textContent=(ok?'判断正确。':'需要修正。')+l.cases[i][2];$('lab-result').textContent=`已作答 ${Object.keys(answered).length} / ${l.cases.length}，当前判断正确 ${Object.values(answered).filter(Boolean).length} 项。试着说明每个决定对应的数据、指标或授权约束。`});
};
