/* Owner-only translation reading: original stays visible, only explicit click makes API call. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id);
  const esc=v=>String(v??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const safeUrl=value=>{try{const u=new URL(value);return ['http:','https:'].includes(u.protocol)?esc(u.href):'#';}catch(_){return '#'}};
  const token=()=>document.querySelector('meta[name="csrf"]')?.content || '';
  async function request(url,method,body) {
    const r=await fetch(url,{method:method||'GET',
      headers:{'Content-Type':'application/json','X-CSRF-Token':token()},
      body:body===undefined?undefined:JSON.stringify(body)});
    const data=await r.json().catch(()=>({}));
    if(!r.ok)throw Error(data.error||'翻译操作失败（'+r.status+'）');
    return data;
  }
  async function show(id) {
    const dialog=$('translation-dialog'), panel=$('translation-detail');
    if(!dialog||!panel)return;
    panel.textContent='正在读取现有翻译缓存…';
    dialog.showModal();
    try {
      const path='/api/translation/'+encodeURIComponent(id);
      const data=await request(path);
      const source=data.source||{};
      const stored=data.translation||{};
      let currentRevision=data.revision||0;
      panel.innerHTML='<h2>中英双语阅读</h2><p class="muted">仅处理已收集的标题和摘要，不抓取原文全文。机器译文可能误译术语，请核对原文。</p>'+
        '<div class="bilingual-columns"><section><h3>原始内容</h3><h4>'+esc(source.title||'')+'</h4>'+
        '<p class="translation-source">'+esc(source.summary||'原记录只有标题')+'</p><p><a href="'+safeUrl(source.url)+'" target="_blank" rel="noopener noreferrer">原文链接 ↗</a></p></section>'+
        '<section><h3>中文译文（可修订）</h3><form id="translation-form">'+
        '<label>标题译文<textarea name="title_zh" maxlength="1000" rows="2" required>'+esc(stored.title_zh||'')+'</textarea></label>'+
        '<label>摘要译文<textarea name="summary_zh" maxlength="5000" rows="6">'+esc(stored.summary_zh||'')+'</textarea></label>'+
        '<p class="muted" id="translation-provenance">'+esc(stored.label||(data.stale?'原文已有更新，旧译文不再适用':'尚无译文'))+'</p>'+
        '<div class="actions"><button type="submit">保存我的译文 / 修订</button>'+
        '<button type="button" id="auto-translate" class="quiet" '+(!data.automatic_available?'disabled':'')+'>按需机器翻译</button></div>'+
        '<p class="muted">自动翻译'+(data.automatic_available?'需将标题和摘要发给 DeepL；每天最多 10 次，重复原文使用缓存。':'暂未配置。仍可人工填写并保存，不调用外部接口。')+'</p>'+
        '<p id="translation-status" role="status" class="muted"></p></form></section></div>';
      const form=$('translation-form'), notice=$('translation-status');
      const update=record=>{
        form.elements.title_zh.value=record.title_zh||'';
        form.elements.summary_zh.value=record.summary_zh||'';
        $('translation-provenance').textContent=record.label||'译文已保存';
      };
      form.onsubmit=async e=>{
        e.preventDefault();
        notice.textContent='正在保存私人译文…';
        try {
          const result=await request(path,'POST',{
            mode:'manual',revision:currentRevision,title_zh:form.elements.title_zh.value,
            summary_zh:form.elements.summary_zh.value});
          update(result.translation);currentRevision=result.revision;
          notice.textContent='已保存到私人数据库，原文和编辑核验记录未改变。';
        }catch(err){notice.textContent=err.message;}
      };
      const button=$('auto-translate');
      button.onclick=async()=>{
        if(!data.automatic_available)return;
        button.disabled=true;notice.textContent='正在发送当前标题与摘要进行按需翻译…';
        try {
          const result=await request(path,'POST',{mode:'automatic'});
          update(result.translation);currentRevision=result.revision;
          notice.textContent=result.cached?'已有缓存，未重复请求翻译服务。':'已获得机器译文；请核对技术术语和准确性。';
        }catch(err){notice.textContent=err.message;}
        finally{button.disabled=false;}
      };
    }catch(err){panel.textContent=err.message||'读取失败';}
  }
  document.addEventListener('click',event=>{
    const target=event.target.closest?.('[data-translate-item]');
    if(target)show(target.dataset.translateItem);
  });
  $('translation-close')?.addEventListener('click',()=>$('translation-dialog')?.close());
  window.openTranslation=show;
})();
