/* Owner-only discovery UI. All links/notes are escaped; scoring is server-side deterministic. */
(() => {
  'use strict';
  const root = () => document.getElementById('content');
  let mode = 'ranking';
  let categoryMode = 'all';
  let keyword = '';
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
    const renderItems = rows => `<div class="discovery-cards">${rows.map((r,i) => {
      const x = r.item, reviewed = x.verification_status === 'reviewed';
      return `<article class="discovery-card">
        <div class="meta"><strong>#${i+1}</strong><span class="tag ${reviewed ? 'reviewed' : 'candidate'}">${reviewed ? '编辑核验' : '待核验'}</span>
          <span class="tag reviewed">${esc(r.category_label || '待分类')}</span><span>${esc(x.source||'来源未知')}</span><span>${esc(x.published_at?.slice(0,10) || '发布日期未知')}</span></div>
        <h2>${esc(x.title)}</h2><p>${esc(x.summary || '当前只有标题/元信息，尚无可核验的正文摘要。')}</p>
        <p class="muted">${esc(r.category_reason || '分类待核验')}${(r.topic_tags||[]).length ? ' · 技术标签：'+(r.topic_tags||[]).map(esc).join(' / ') : ''}</p><div class="reason-line">${r.reasons.map(m=>`<span class="reason">${esc(m)}</span>`).join('')}</div>
        ${r.possible_project ? `<p class="project-hint">可能关联：${esc(r.possible_project)} <small>· 仅依据关键词提示，需自己验证</small></p>` : ''}
        <div class="actions"><button class="quiet" type="button" data-recommend-detail="${esc(x.id)}">精读 / 记录 / 收藏</button>
          <button class="quiet" type="button" data-research-item="${esc(x.id)}">评估 / 列入计划</button><button class="quiet" type="button" data-correct-category="${esc(x.id)}">纠正分类</button><button class="quiet" type="button" data-translate-item="${esc(x.id)}">中英双语</button><a href="${safeHref(x.url)}" target="_blank" rel="noopener noreferrer">看原文 ↗</a></div>
      </article>`; }).join('')}</div>`;
    const choices = (data.categories || []).filter(c => c.count > 0);
    if (categoryMode !== 'all') {
      const subset = data.ranking.filter(r => (r.category || 'other') === categoryMode);
      return subset.length ? renderItems(subset) : '<p class="empty">这个分类暂无内容。试试其他类别，或先补充有效来源。</p>';
    }
    if (!choices.length) return renderItems(data.ranking);
    return choices.map(category => {
      const subset = data.ranking.filter(r => (r.category || 'other') === category.key);
      return '<section class="discovery-category-section"><h3>'+
          esc(category.label)+' · '+subset.length+' 条</h3><p class="muted">'+
          esc(category.description || '')+'</p>'+renderItems(subset)+'</section>';
    }).join('');
  }
  function categoryTabs(data) {
    const cats = data.categories || [];
    if (!cats.length) return '';
    return '<section class="category-navigation" aria-label="内容主分类"><h2>分门别类发现</h2>'+
      '<p class="muted">Agent、论文、GitHub 代码、产品和教程分开呈现。每条只归入一个主分类，技术标签可交叉；分类是规则初判，不是人工核验结论。</p>'+
      '<div class="category-pills" role="group" aria-label="选择内容类别">'+
      [{key:'all',label:'全部分类',count:data.ranking.length},...cats].map(c =>
        '<button type="button" data-discovery-category="'+esc(c.key)+'" aria-pressed="'+(categoryMode===c.key)+'" class="'+
        (categoryMode===c.key?'':'quiet')+'">'+esc(c.label)+' <span>'+Number(c.count || 0)+'</span></button>'
      ).join('')+'</div>'+
      '<label class="category-search">筛选当前类别 <input id="discovery-search" type="search" placeholder="搜索标题、来源、摘要" value="'+esc(keyword)+'" aria-label="搜索兴趣发现内容"></label>'+
      '<p class="muted" id="category-search-count" role="status"></p></section>';
  }
  function capturedCards(data) {
    if (!data.captures.length) return '<p class="empty">你从小红书或 GitHub 看到的新鲜东西，可以先保存在上面的私人清单中。</p>';
    return data.captures.map(x => `<article class="captured-card">
      <div class="meta"><span class="tag candidate">私人线索 · 未核验</span> <span class="tag reviewed">${esc(x.category_label || "待分类")}</span> <span>${esc(x.source)}</span> <span>${esc(x.added_at?.slice(0,10)||'')}</span></div>
      <h3>${esc(x.title)}</h3><p>${esc(x.note)}</p>
      <div class="actions"><button class="quiet" type="button" data-research-item="${esc(x.id)}">做验证计划</button><button class="quiet" type="button" data-correct-category="${esc(x.id)}">纠正分类</button><button class="quiet" type="button" data-translate-item="${esc(x.id)}">中英双语</button><a href="${safeHref(x.url)}" target="_blank" rel="noopener noreferrer">查看保存的原文 ↗</a></div></article>`).join('');
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
         <button type="button" class="${mode==='connections'?'':'quiet'}" data-discover-mode="connections">跨来源线索</button>
         <button type="button" class="${mode==='plans'?'':'quiet'}" data-discover-mode="plans">验证与学习计划</button>
         <button type="button" class="${mode==='sources'?'':'quiet'}" data-discover-mode="sources">信息源地图</button></div>
       ${mode==='ranking' ? categoryTabs(data) + rankedCards(data) + topicSummary(data) :
          mode==='saved' ? captureForm + '<h2>我的私人待核验清单</h2>'+capturedCards(data) :
          mode==='connections' || mode==='plans' ? '<section id="research-board" class="discovery-panel"></section>' : sourceDirectory(data)}
       </div>`;
  }
  function applySearch() {
    if (mode !== 'ranking') return;
    const main = root();
    const query = keyword.trim().normalize('NFKC').toLocaleLowerCase();
    if (!main || typeof main.querySelectorAll !== 'function') return;
    const cards = [...main.querySelectorAll('.discovery-card')];
    let shown = 0;
    for (const card of cards) {
      card.hidden = !!query && !card.textContent.normalize('NFKC').toLocaleLowerCase().includes(query);
      if (!card.hidden) shown++;
    }
    for (const section of main.querySelectorAll('.discovery-category-section')) {
      section.hidden = ![...section.querySelectorAll('.discovery-card')].some(card=>!card.hidden);
    }
    const output = byId('category-search-count');
    if (output) output.textContent = query ?
      '找到 '+shown+' 条匹配内容（仅检索当前已加载的结果）' :
      '当前展示 '+shown+' 条内容';
  }

  async function correctCategory(id) {
    if (!cached || !serverApi) return;
    const record = cached.ranking.find(row=>String(row.item.id)===String(id)) ||
      cached.captures.find(row=>String(row.id)===String(id));
    if (!record) return;
    const item = record.item || record;
    const dlg = byId('category-dialog');
    const target = byId('category-detail');
    if (!dlg || !target) return;
    const key = 'category:' + id;
    const saved = await serverApi('/api/state/'+encodeURIComponent(key));
    const initial = saved.value || {};
    const selected = initial.category || 'auto';
    const options = [{key:'auto',label:'自动判断'},...(cached.categories||[])];
    target.innerHTML = '<h2>纠正内容分类</h2><p>'+esc(item.title||'')+'</p>'+
      '<p class="muted">这里只更改你自己看到的主分类，不会改变原始来源、编辑核验结果或公开精选。</p>'+
      '<form id="category-form"><label>主分类<select name="category">'+
      options.map(o=>'<option value="'+esc(o.key)+'" '+(o.key===selected?'selected':'')+'>'+esc(o.label)+'</option>').join('')+
      '</select></label><label>分类说明（可选，最多 200 字）'+
      '<textarea name="note" maxlength="200" rows="2">'+esc(initial.note||'')+'</textarea></label>'+
      '<div class="actions"><button type="submit">保存分类</button><button type="button" class="quiet" id="category-reset">恢复自动分类</button></div>'+
      '<p class="muted" id="category-message" role="status"></p></form>';
    dlg.showModal();
    const save = async (category,note) => {
      const message = byId('category-message');
      try {
        await serverApi('/api/state/'+encodeURIComponent(key),'PUT',{
          revision:saved.revision,
          value:{category,note}
        });
        dlg.close();
        await refresh();
      } catch(err) {
        if(message) message.textContent=err.message || '保存未完成，请刷新后重试';
      }
    };
    byId('category-form').onsubmit = async ev=>{
      ev.preventDefault();
      const form = ev.currentTarget;
      await save(form.elements.category.value,form.elements.note.value.trim());
    };
    byId('category-reset').onclick = async()=>save('auto','');
  }

  async function refresh() {
    cached = await serverApi('/api/discover');
    root().innerHTML = markup(cached);
    if (mode === 'ranking' && keyword) applySearch();
    if (typeof window.renderResearchAddon === 'function')
      window.renderResearchAddon({data:cached, mode, api:serverApi});
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
              custom_interests:byId('custom-interest-input').value.split(/[,，、\n]+/).map(s=>s.trim()).filter(Boolean).slice(0,12)}
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
    const button = e.target.closest('[data-discover-mode], [data-recommend-detail], [data-discovery-category], [data-correct-category]');
    if (!button || !root()?.contains(button)) return;
    if (button.dataset.discoveryCategory && cached) {
      categoryMode = button.dataset.discoveryCategory;
      refresh().catch(err => {root().textContent=err.message;});
    } else if (button.dataset.discoverMode) {
      mode=button.dataset.discoverMode;
      refresh().catch(err=>{root().textContent=err.message;});
    } else if (button.dataset.correctCategory && cached) {
      correctCategory(button.dataset.correctCategory).catch(err=>{root().textContent=err.message;});
    } else if (button.dataset.recommendDetail && cached) {
      const found=cached.ranking.find(r=>r.item.id===button.dataset.recommendDetail);
      if (found) Promise.resolve(openDetail(found.item)).catch(err=>{root().textContent=err.message;});
    }
  });
  document.addEventListener('input',event => {
    if (event.target?.id !== 'discovery-search') return;
    keyword = event.target.value;
    applySearch();
  });
  byId('category-close')?.addEventListener('click',()=>byId('category-dialog')?.close());
  window.renderDiscovery = show;
  window.refreshDiscovery = refresh;
})();
