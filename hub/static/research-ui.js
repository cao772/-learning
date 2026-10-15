/* Private research loop: explicit human evaluation; no model/API fetching. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const href = value => { try {
    const url = new URL(value);
    return (url.protocol === 'https:' || url.protocol === 'http:') ? esc(url.href) : '#';
  } catch (_) { return '#'; } };
  const decisions = ['未评估', '待精读', '待复现', '可能用于项目', '暂不采用'];
  const efforts = ['未估算', '半天以内', '1–3 天', '4–7 天', '超过一周'];
  const checks = ['未运行', '已复现', '复现失败', '不适用'];
  const steps = ['阅读原文', '核验证据', '动手验证', '复盘迁移'];
  let dataset = null, api = null;
  const option = (value, selected) =>
    `<option value="${esc(value)}" ${value === selected ? 'selected' : ''}>${esc(value)}</option>`;
  const marker = r => `<span class="tag candidate">${esc(r.basis)}</span>`;

  function groupMarkup(title, groups, description) {
    return `<section><h3>${esc(title)} · ${groups.length}</h3><p class="muted">${esc(description)}</p>
      ${groups.length ? groups.map(group => `<article class="research-group">${marker(group)}
        <p>共 ${group.members.length} 条线索，保留各自的核验状态和原文。</p>
        <ul>${group.members.map(member => `<li><a href="${href(member.url)}" target="_blank" rel="noopener noreferrer">${esc(member.title)}</a>
        <small>${esc(member.source)} · ${esc(member.origin === 'private_capture' ? '私人手工线索' : (member.verification_status === 'reviewed' ? '编辑核验' : '待核验'))}</small>
        <button type="button" class="quiet" data-research-item="${esc(member.id)}">验证</button></li>`).join('')}</ul>
      </article>`).join('') : '<p class="empty">当前所显示的线索中暂无符合条件的重复链接或标题。</p>'}</section>`;
  }
  function connections() {
    const groups = dataset.connections || {same_link:[], similar_title:[]};
    return `<h2>同一件事，来自哪些入口？</h2>
      <p class="muted">这里只比较本次推荐范围及私人收藏链接：相同 URL 不等于独立证据；相同标题仅作为人工复核提示。不会合并正文或自动升级为精选。</p>
      ${groupMarkup('相同原始链接',groups.same_link || [], '已规范化链接的完全一致性比较；可能是同一篇文章被重复收录。')}
      ${groupMarkup('标题一致的关联线索',groups.similar_title || [], '不同链接具有完全一致的长标题。请自行核实转载、引用或实际独立研究。')}`;
  }
  function plans() {
    const rows = [...(dataset.research_records || [])]
      .sort((a,b) => String(b.updated_at || '').localeCompare(String(a.updated_at || '')));
    return `<h2>我的学习与项目验证计划</h2>
      <p class="muted">每一条都是你主动保存的评估，不会自动改变精选核验状态。先读来源、再检验复现与项目适配；未执行的实验不得写成完成。</p>
      ${rows.length ? rows.map(r => `<article class="research-card">
        <div class="meta"><span class="tag reviewed">${esc(r.decision || '未评估')}</span>
          <span>${esc(r.updated_at?.slice(0,10)||'时间未知')}</span><span>${esc(r.test_status || '未运行')}</span></div>
        <h3>${esc(r.title || '未命名研究')}</h3>
        <p>${esc(r.question || '尚未填写核心问题')}</p>
        <p>项目场景：${esc(r.project || '待确认')} · 下一步：${esc(steps[Math.min(3,Math.max(0,Number(r.step) || 0))])}</p>
        <div class="actions"><button class="quiet" type="button" data-research-item="${esc(r.key)}">编辑验证记录</button>
          <a href="${href(r.url)}" target="_blank" rel="noopener noreferrer">来源 ↗</a></div>
      </article>`).join('') : '<p class="empty">还没有验证任务。在「为我发现」或「我从别处看到的」点「评估 / 列入计划」创建第一条。</p>'}`;
  }
  function entryFor(id) {
    for (const ranked of dataset.ranking || []) {
      if (String(ranked.item?.id) === String(id)) return ranked.item;
    }
    const found = (dataset.captures || []).find(c => String(c.id) === String(id));
    if (found) return found;
    const old = (dataset.research_records || []).find(r => String(r.key) === String(id));
    return old || null;
  }
  const field = (label,name, val, max=1200) =>
    `<label>${esc(label)}<textarea name="${esc(name)}" maxlength="${max}" rows="2">${esc(val||'')}</textarea></label>`;
  async function edit(id) {
    if (!api || !dataset) return;
    const item = entryFor(id);
    if (!item) return;
    const dialog = $('research-dialog'), target = $('research-detail');
    if (!dialog || !target) return;
    const guide = dataset.research_guides?.[id] || {kind:'general',checklist:[],metrics:{},evidence_level:'待验证'};
    const key = 'research:' + id;
    const current = await api('/api/state/' + encodeURIComponent(key));
    const v = current.value || {};
    const enumField = (label,name,items,value) => `<label>${esc(label)}<select name="${esc(name)}">${items.map(x=>option(x,value)).join('')}</select></label>`;
    target.innerHTML = `<h2>${esc(item.title || v.title || '')}</h2>
      <p class="muted">评估类型：${esc({repository:'GitHub 项目',paper:'论文',general:'产品 / 教程 / 观点'}[guide.kind] || '通用')}。
      许可证、维护、星数、论文全文和复现结果一律默认为未知，不会自行请求网络。</p>
      <p><a href="${href(item.url || v.url)}" target="_blank" rel="noopener noreferrer">打开原始来源 ↗</a></p>
      <h3>人工验证清单</h3><ol>${(guide.checklist||[]).map(x=>`<li>${esc(x)}</li>`).join('')}</ol>
      <form id="research-form" class="research-form">
      ${enumField('研究决策','decision',decisions,v.decision || decisions[0])}
      ${enumField('预计改造 / 学习工作量','effort',efforts,v.effort || efforts[0])}
      ${enumField('真实复现状态','test_status',checks,v.test_status || checks[0])}
      <label>下一步学习阶段<select name="step">${steps.map((label,i)=>option(String(i),String(v.step ?? 0)).replace('>'+i+'<','>'+esc(label)+'<')).join('')}</select></label>
      ${field('我要验证的问题','question',v.question,1500)}
      ${field('可能应用的项目及边界','project',v.project,1200)}
      ${field('事实证据与实验记录（未验证请写未验证）','evidence',v.evidence,4000)}
      ${field('结果、反例与是否值得继续','conclusion',v.conclusion,4000)}
      <div class="actions"><button type="submit">保存私人验证记录</button></div>
      <p id="research-message" role="status" class="muted"></p></form>`;
    dialog.showModal();
    $('research-form').onsubmit = async event => {
      event.preventDefault();
      const form = event.currentTarget;
      const message = $('research-message');
      const input = Object.fromEntries(new FormData(form).entries());
      const value = {
        title:item.title || v.title || '',url:item.url || v.url || '',
        source:item.source || v.source || '',
        kind:guide.kind,created_at:v.created_at || new Date().toISOString(),
        updated_at:new Date().toISOString(),
        ...input,step:Number(input.step),
      };
      try {
        await api('/api/state/' + encodeURIComponent(key),'PUT',{revision:current.revision,value});
        dialog.close();
        if (typeof window.refreshDiscovery === 'function') await window.refreshDiscovery();
      } catch (err) {
        message.textContent = err.message || '保存失败';
      }
    };
  }
  document.addEventListener('click', event => {
    const button = event.target.closest?.('[data-research-item]');
    const root = $('content');
    if (!button || !root?.contains(button)) return;
    edit(button.dataset.researchItem).catch(err => {
      const board=$('research-board');
      if (board) board.textContent = err.message || '打开记录失败';
    });
  });
  $('research-close')?.addEventListener('click', () => $('research-dialog')?.close());
  window.renderResearchAddon = ({data,mode,api:client}) => {
    dataset=data;api=client;
    const board=$('research-board');
    if (board) board.innerHTML = mode === 'connections' ? connections() : plans();
  };
})();
