// Progressive enhancement: server-rendered content remains readable without JavaScript.
(() => {
  'use strict';
  const input = document.getElementById('public-search');
  const status = document.getElementById('public-status');
  const reset = document.getElementById('public-reset');
  const count = document.getElementById('public-count');
  if (!input || !status || !reset || !count) return;
  const entries = [...document.querySelectorAll('[data-public-item]')];
  const fold = value => String(value ?? '').normalize('NFKC').toLocaleLowerCase();
  const apply = () => {
    const term = fold(input.value.trim());
    const kind = status.value;
    let shown = 0;
    for (const article of entries) {
      const textMatches = !term || fold(article.textContent).includes(term);
      const kindMatches = kind === 'all' || article.dataset.kind === kind;
      article.hidden = !(textMatches && kindMatches);
      if (!article.hidden) shown++;
    }
    for (const section of document.querySelectorAll('section[id="reviewed"], section[id="candidate"]')) {
      const hasItems = section.querySelectorAll('[data-public-item]').length > 0;
      const hasVisible = [...section.querySelectorAll('[data-public-item]')].some(node => !node.hidden);
      const noMatch = section.querySelector('.public-no-match');
      if (noMatch) noMatch.hidden = !hasItems || hasVisible;
    }
    count.textContent = '当前显示 ' + shown + ' / ' + entries.length + ' 条内容';
  };
  input.addEventListener('input', apply);
  status.addEventListener('change', apply);
  reset.addEventListener('click', () => { input.value = ''; status.value = 'all'; apply(); input.focus(); });
  apply();
})();
