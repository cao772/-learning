/* Owner-only discovery UI. All links/notes are escaped; scoring is server-side deterministic. */
(() => {
  'use strict';
  const root = () => document.getElementById('content');
  let mode = 'ranking';
  let cached = null;
  const byId = id => document.getElementById(id);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c =>
      ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','"':'&quot;',"'":'&#39;'}[c]));
  const safeHref = s => { try {
      const u = new URL(s);
      return ['https:','http:'].includes(u.protocol) ? esc(u.href) : '#';
    } catch (_) { return '#'; }
  };
  let serverApi, openDetail;
  const captureForm = `
    <section class="discovery-panel" aria-label="随手收集">
      <h2>看到一个好东西，就先存进来</h2>
      <p class="muted">支持粘贴 GitHub、公众号、小红书分享或论文链接。只保存到站主的私人清单，<strong>不会抓取网页，也不会自动标记为核验精选</strong>。</p>
      <form id="capture-form" class="capture-form">
        <label>原始链接 <input name="url" type="url" required maxlength="2048" placeholder="https://github.com/owner/repo"></label>
        <label>名称或我关注的点 <input name="title" required maxlength="200" placeholder="这个仓库想解决什么问题？"></label>
        <label>从哪里看到的 <select name="source"><option>GitHub</option><option>小红书</option><option>微信公众号</option><option>其它网站</option></select></label>
        <label>我为什么感兴趣（可选） <textarea name="note" maxlength="3000" rows="2" placeholder="适合哪个项目？我准备验证什么？"></textarea></label>
        <button type="submit">保存到私人待核验清单</button>
      </form><p id="capture-message" role="status" class="muted"></p>
    </section>`;

  function topicSummary(data) {
    const weights = data.profile.weights;
    return `<section class="discovery-panel" aria-label="兴趣偏好">
      <div class="heading"><h2>我的兴趣权重</h2><span class="tag reviewed">随时可以改变</span></div>
      <p class="muted">0 为暂时不关注，5 为特别关注。仅为透明的规则排序，<strong>不是对内容质量的模型评判</strong>。</p>
      <form id="interest-form"><div class="interest-grid">${data.topics.map(t =>
       `<label>${esc(t.label)} <select data-weight="${esc(t.key)}" aria-label="${esc(t.label)} 权重">${[0,1,2,3,4,5].map(v =>
          `<option value="${v}" ${weights[t.key] === v ? 'selected' : ''}>${v}</option>`).join('')}</select></label>`).join('')}</div>
       <label class="interest-extra">新的探索兴趣（用逗号隔开，最多 12 个）
         <input id="custom-interest-input" type="text" maxlength="360" value="${esc((data.profile.custom_interests||[]).join('、'))}" placeholder="例如：天体物理、蛋白质结构、编程语言"></label>
       <button type="submit" class="quiet">保存偏好并重新排序</button></form>
       <p id="profile-message" role="status" class="muted"></p>
    </section>`;
  }
  function rankedCards(data) {
    if (!data.ranking.length) return '<p class="empty">还没有可匹配的内容。可以先从现有来源收集几条线索。</p>';
    return `<div class="discovery-cards">${data.ranking.map((r,i) => {
      const x = r.item, reviewed = x.verification_status === 'reviewed';
      return `<article class="discovery-card">
        <div class="meta"><strong>#${i+1}</strong><span class="tag ${reviewed ? 'reviewed' : 'candidate'}">${reviewed ? '编辑核验' : '待核验'}</span>
          <span>${esc(x.source||'来源未知')}</span><span>${esc(x.published_at?.slice(0,10) || '发布日期未知')}</span></div>
        <h2>${esc(x.title)}</h2><p>${esc(x.summary || '当前只有标题/元信息，尚无可核验的正文摘要。')}</p>
        <div class="reason-line">${r.reasons.map(m=>`<span class="reason">${esc(m)}</span>`).join('')}</div>
        ${r.possible_project ? `<p class="project-hint">可能关联：${esc(r.possible_project)} <small>· 仅依据关键词提示，需自己验证</small></p>` : ''}
        <div class="actions"><button class="quiet" type="button" data-recommend-detail="${esc(x.id)}">精读 / 记录 / 收藏</button>
          <a href="${safeHref(x.url)}" target="_blank" rel="noopener noreferrer">看原文 ↗</a></div>
      </article>`; }).join('')}</div>`;
  }
  function capturedCards(data) {
    if (!data.captures.length) return '<p class="empty">你从小红书或 GitHub 看到的新鲜东西，可以先保存在上面的私人清单中。</p>';
    return data.captures.map(x => `<article class="captured-card">
      <div class="meta"><span class="tag candidate">私人线索 · 未核验</span> <span>${esc(x.source)}</span> <span>${esc(x.added_at?.slice(0,10)||'')}</span></div>
      <h3>${esc(x.title)}</h3><p>${esc(x.note)}</p>
      <a href="${safeHref(x.url)}" target="_blank" rel="noopener noreferrer">查看保存的原文 ↗</a></article>`).join('');
  }
  function sourceDirectory(data) {
    const grouped = new Map();
    for (const entry of data.sources) {
      if (!grouped.has(entry.kind)) grouped.set(entry.kind, []);
      grouped.get(entry.kind).push(entry);
    }
    return `<section class="discovery-panel"><h2>已关注的信息来源</h2>
       <p class="muted">源自现有 Notion 清单与这次补充的入口。下面的来源目录<strong>不表示全部已成功采集</strong>；受限公众号和小红书目前通过手工收集链接。</p>
       ${[...grouped].map(([kind, sources]) => `<div class="source-group"><h3>${esc(kind)}</h3><div class="source-grid">${sources.map(s =>
         `<div class="source"><strong>${esc(s.name)}</strong><small>${esc(s.access)}</small>
             ${s.url ? `<a href="${safeHref(s.url)}" target="_blank" rel="noopener noreferrer">查看来源 ↗</a>` : '<span class="muted">暂无验证入口</span>'}</div>`).join('')}</div></div>`).join('')}
     </section>`;
  }
  function markup(data) {
    return `<div id="discovery" class="discovery">
       <section class="discovery-intro"><p class="eyebrow">DISCOVERY / CURATION / LEARNING</p>
        <h2>不追完所有热点，只寻找对你有价值的东西。</h2>
        <p class="muted">${esc(data.ranking_method)}</p></section>
       <div class="discovery-tabs" role="group" aria-label="发现工作台视图">
         <button type="button" class="${mode==='ranking'?'':'quiet'}" data-discover-mode="ranking">为我发现</button>
         <button type="button" class="${mode==='saved'?'':'quiet'}" data-discover-mode="saved">我从别处看到的</button>
         <button type="button" class="${mode==='sources'?'':'quiet'}" data-discover-mode="sources">信息源地图</button></div>
       ${mode==='ranking' ? topicSummary(data) + `<h2>按我的兴趣排列 · ${data.ranking.length} 条</h2>`+rankedCards(data) :
          mode==='saved' ? captureForm + '<h2>我的私人待核验清单</h2>'+capturedCards(data) : sourceDirectory(data)}
       </div>`;
  }
  async function refresh() {
    cached = await serverApi('/api/discover');
    root().innerHTML = markup(cached);
    if (mode==='ranking') {
      const form = byId('interest-form');
      form.onsubmit = async e => {
        e.preventDefault();
        const weights = {};
        for (const select of form.querySelectorAll('[data-weight]')) weights[select.dataset.weight] = Number(select.value);
        const message = byId('profile-message');
        try {
          await serverApi('/api/state/profile%3Ainterests','PUT',{
            revision:cached.profile_revision,value:{weights,
              custom_interests:byId('custom-interest-input').value.split(/[,，、\\n]+/).map(s=>s.trim()).filter(Boolean).slice(0,12)}
          });
          await refresh();
        } catch(err) { message.textContent = err.message; }
      };
    }
    if (mode==='saved') {
      byId('capture-form').onsubmit = async e => {
        e.preventDefault();
        const form = e.currentTarget, message = byId('capture-message');
        const data = Object.fromEntries(new FormData(form).entries());
        try {
          const result = await serverApi('/api/capture','POST',data);
          await refresh();
          byId('capture-message').textContent = result.duplicate ?
            '这条链接之前已保存，保留原有记录，不会重复添加。' : '已保存到私人清单；尚未核验原文。';
        } catch(err) { message.textContent = err.message; }
      };
    }
  }
  async function show({api, onDetail}) {
    serverApi=api;
    openDetail=onDetail;
    await refresh();
  }
  document.addEventListener('click', e => {
    const button = e.target.closest('[data-discover-mode], [data-recommend-detail]');
    if (!button || !root()?.contains(button)) return;
    if (button.dataset.discoverMode) {
      mode=button.dataset.discoverMode;
      refresh().catch(err=>{root().textContent=err.message;});
    } else if (button.dataset.recommendDetail && cached) {
      const found=cached.ranking.find(r=>r.item.id===button.dataset.recommendDetail);
      if (found) Promise.resolve(openDetail(found.item)).catch(err=>{root().textContent=err.message;});
    }
  });
  window.renderDiscovery = show;
})();
