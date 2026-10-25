// Shared progressive reading enhancements. No private state or network requests.
(() => {
 'use strict';
 const main = document.getElementById('main-content');
 if (!main) return;
 document.querySelector('[data-clear-public]')?.addEventListener('click', () => document.getElementById('public-reset')?.click());
 const toggle = document.querySelector('.password-toggle');
 toggle?.addEventListener('click', () => {
   const input = document.getElementById('password');
   const visible = input.type === 'password';
   input.type = visible ? 'text' : 'password';
   toggle.textContent = visible ? '隐藏口令' : '显示口令';
   toggle.setAttribute('aria-pressed', String(visible));
 });
 const links = [...document.querySelectorAll('.public-page aside nav a')];
 const mark = id => links.forEach(a => {
   if (a.hash === '#' + id) a.setAttribute('aria-current', 'location');
   else a.removeAttribute('aria-current');
 });
 for (const link of links) link.addEventListener('click', () => {
   // Reveal filtered-out sections before following their anchors.
   if (link.hash !== '#courses') document.getElementById('public-reset')?.click();
   const target = document.getElementById(link.hash.slice(1));
   if (target) target.hidden = false;
   mark(link.hash.slice(1));
 });
 if (links.length && 'IntersectionObserver' in window) {
   const observer = new IntersectionObserver(entries => {
     const visible = entries.filter(e => e.isIntersecting).sort((a,b) => a.boundingClientRect.top-b.boundingClientRect.top);
     if (visible[0]) mark(visible[0].target.id);
   }, {rootMargin:'-10% 0px -55% 0px'});
   ['reviewed','candidate','courses'].forEach(id => {const el=document.getElementById(id);if(el)observer.observe(el);});
 }
 function prepareSummaries() {
   for (const p of main.querySelectorAll('.reading-summary:not([data-readable])')) {
     p.dataset.readable = 'true';
     if (p.textContent.length < 320) continue;
     p.classList.add('summary-folded');
     const button = document.createElement('button');
     button.type = 'button';button.className = 'summary-toggle quiet';
     button.textContent = '展开摘要';button.setAttribute('aria-expanded','false');
     button.addEventListener('click', () => {
       const folded=p.classList.toggle('summary-folded');
       button.textContent=folded?'展开摘要':'收起摘要';button.setAttribute('aria-expanded',String(!folded));
     });
     p.after(button);
   }
 }
 prepareSummaries();
 const content=document.getElementById('content');
 if(content) new MutationObserver(prepareSummaries).observe(content,{childList:true,subtree:true});
 const top=document.createElement('a');top.href='#main-content';top.className='back-to-top';top.textContent='回到顶部 ↑';
 main.querySelector('footer')?.append(top);
})();
