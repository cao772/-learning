// Progressive enhancement: server-rendered content remains readable without JavaScript.
(() => {
  'use strict';
  const input = document.getElementById('public-search');
  const status = document.getElementById('public-status');
  const reset = document.getElementById('public-reset');
  const tabs = [...document.querySelectorAll('.content-tabs [data-category]')];
  let category = 'all';
  if (!input || !status || !reset) return;
  const entries = [...document.querySelectorAll('[data-public-item]')];
  const fold = value => String(value ?? '').normalize('NFKC').toLocaleLowerCase();
  const apply = () => {
    const term = fold(input.value.trim());
    const kind = status.value;
    let shown = 0;
    for (const article of entries) {
      const textMatches = !term || fold(article.textContent).includes(term);
      const kindMatches = kind === 'all' || article.dataset.kind === kind;
      const categoryMatches = category === 'all' || article.dataset.category === category;
      article.hidden = !(textMatches && kindMatches && categoryMatches);
      if (!article.hidden) shown++;
    }
    for (const section of document.querySelectorAll('section[id="reviewed"], section[id="candidate"]')) {
      const hasItems = section.querySelectorAll('[data-public-item]').length > 0;
      const hasVisible = [...section.querySelectorAll('[data-public-item]')].some(node => !node.hidden);
      const noMatch = section.querySelector('.public-no-match');
      if (noMatch) noMatch.hidden = !hasItems || hasVisible;
    }
    for (const tab of tabs) { const active = tab.dataset.category === category; tab.classList.toggle('active',active); tab.setAttribute('aria-pressed',String(active)); }
  };
  for (const tab of tabs) tab.addEventListener('click', () => { category = tab.dataset.category; apply(); });
  input.addEventListener('input', apply);
  status.addEventListener('change', apply);
  reset.addEventListener('click', () => { input.value = ''; status.value = 'all'; category = 'all'; apply(); input.focus(); });
  apply();
})();
