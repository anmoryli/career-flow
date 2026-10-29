/* CareerFlow analysis feature: jobs, immutable diagnostic snapshots and document records. */
(() => {
  'use strict';
  const page = document.querySelector('[data-analysis-page]');
  if (!page) return;
  const csrf = () => document.querySelector('meta[name="csrf-token"]').content;
  const text = (element, value) => { if (element) element.textContent = value; };
  const read = async (url, options = {}) => {
    const response = await fetch(url, { credentials:'same-origin',redirect:'error',...options });
    let result;
    try { result = await response.json(); } catch { throw new Error('服务暂时没有返回有效结果，请稍后重试。'); }
    if (!response.ok) throw new Error(result.error || '读取失败，请稍后重试。');
    return result;
  };
  const lock = (button, value) => { if (!button) return; button.disabled = value; button.setAttribute('aria-busy', String(value)); };
  const confirmAction = (message, acceptLabel = '确认') => new Promise(resolve => {
    const dialog = document.createElement('dialog'); dialog.className = 'cf-dialog cfa-confirm-dialog';
    const header = document.createElement('header'), title = document.createElement('h2'); title.textContent = '确认操作'; header.append(title);
    const content = document.createElement('p'); content.textContent = message;
    const footer = document.createElement('footer');
    const cancel = document.createElement('button'); cancel.type = 'button'; cancel.className = 'cf-button is-secondary is-small'; cancel.textContent = '返回';
    const accept = document.createElement('button'); accept.type = 'button'; accept.className = 'cf-button is-small'; accept.textContent = acceptLabel;
    footer.append(cancel, accept); dialog.append(header, content, footer); document.body.append(dialog);
    let accepted = false;
    cancel.addEventListener('click', () => dialog.close());
    accept.addEventListener('click', () => { accepted = true; dialog.close(); });
    dialog.addEventListener('close', () => { resolve(accepted); dialog.remove(); }, { once:true });
    dialog.showModal(); cancel.focus();
  });

  const jobForm = page.querySelector('[data-job-form]');
  if (jobForm) {
    const status = page.querySelector('#job-save-status'), submit = page.querySelector('[data-save-job]');
    const resumeSelect = page.querySelector('#analysis-resume');
    const guestInput = page.querySelector('#guest-resume-file');
    const description = page.querySelector('#job-description');
    const fields = ['#job-title','#job-company','#job-description','#job-url'].map(selector => page.querySelector(selector));
    let requestKey = crypto.randomUUID(), resumeRequestKey = crypto.randomUUID(), guestResume = null, busy = false, uploadGeneration = 0;
    const changed = () => { requestKey = crypto.randomUUID();text(page.querySelector('#jd-character-count'), `${description.value.length} 字`); };
    jobForm.addEventListener('input', changed); changed();
    guestInput?.addEventListener('change', async () => {
      guestResume = null; resumeRequestKey = crypto.randomUUID(); const generation = ++uploadGeneration;
      const file = guestInput.files[0], feedback = page.querySelector('#guest-resume-status');
      if (!file) { text(feedback,''); return; }
      if (file.size > 4*1024*1024 || !file.name.toLowerCase().endsWith('.pdf')) {text(feedback,'请选择不超过 4 MB 的 PDF 简历。');return;}
      text(feedback,'正在提取简历内容…'); const data = new FormData(); data.set('file',file);
      try {
        const result = await read('/api/guest/resume/parse',{method:'POST',body:data,headers:{'X-CSRFToken':csrf()}});
        if (generation !== uploadGeneration) return;
        guestResume = result; text(feedback,`已读取「${result.title || file.name}」，开始分析时登录。`);
      } catch(error) { if(generation===uploadGeneration)text(feedback,error.message); }
    });
    const loadJob = async (id, button) => {
      const feedback = page.querySelector('[data-import-job-status]') || status;
      if (!id) {text(feedback,'先选择一个已保存岗位。');return;}
      if (fields.some(field=>field.value.trim()) && !await confirmAction('载入将替换当前填写的岗位信息，是否继续？','载入岗位')) return;
      lock(button,true);text(feedback,'正在载入…');
      try {
        const result=await read(`/api/jobs/${id}`);
        fields.forEach((field,index)=>{field.value=[result.title,result.company,result.description,result.url][index]||'';});
        if(resumeSelect && [...resumeSelect.options].some(option=>option.value===String(result.resume_id)))resumeSelect.value=String(result.resume_id);
        changed();text(feedback,`已载入「${result.title || '未命名岗位'}」，核对后开始分析。`);description.focus();
      } catch(error){text(feedback,error.message);}finally{lock(button,false);}
    };
    page.querySelector('[data-import-saved-job]')?.addEventListener('click',event=>loadJob(page.querySelector('#saved-job-select').value,event.currentTarget));
    page.querySelectorAll('[data-load-job]').forEach(button=>button.addEventListener('click',()=>loadJob(button.dataset.loadJob,button)));
    const start = async () => {
      if(busy)return;
      if(!jobForm.reportValidity())return;
      if(!resumeSelect && !guestResume){text(status,'请先上传一份 PDF 简历。');guestInput?.focus();return;}
      busy=true;lock(submit,true);text(status,'正在保存岗位并准备分析…');
      const perform = async () => {
        let resumeId=Number(resumeSelect?.value),revision=Number(resumeSelect?.selectedOptions[0]?.dataset.revision);
        if(!resumeSelect){const saved=await window.cfApi('/api/resumes',{request_key:resumeRequestKey,title:guestResume.title || '导入的简历',template:'classic',document:guestResume.document});resumeId=saved.id;revision=saved.revision;}
        const result=await window.cfApi('/api/jobs',{request_key:requestKey,resume_id:resumeId,resume_revision:revision,title:fields[0].value,company:fields[1].value,description:description.value,url:fields[3].value,save_for_later:page.querySelector('[data-save-job-for-later]').checked});
        location.href=`/jobs/${result.id}?start=analysis`;
      };
      try {await perform();}catch(error){
        if(error.loginRequired && window.cfRequireAuth){text(status,'登录后继续刚才的分析。');window.cfRequireAuth(async()=>{busy=true;lock(submit,true);try{await perform();}catch(next){text(status,next.message);busy=false;lock(submit,false);}});}
        else text(status,error.message);
        busy=false;lock(submit,false);
      }
    };
    submit?.addEventListener('click',start);
    jobForm.addEventListener('submit',event=>{event.preventDefault();start();});
    page.querySelectorAll('[data-delete-job]').forEach(button=>button.addEventListener('click',async()=>{
      if(!await confirmAction(`删除「${button.dataset.recordTitle}」？此操作无法撤销。`,'确认删除'))return;
      lock(button,true);
      try{await window.cfApi(`/api/jobs/${button.dataset.deleteJob}/delete`,{confirm:'delete'});location.reload();}
      catch(error){text(page.querySelector('[data-list-feedback]'),error.message);lock(button,false);}
    }));
  }

  const reportRows = [...page.querySelectorAll('[data-report-operation]')];
  if(page.dataset.analysisPage==='reports'){
    let filter='all';const search=page.querySelector('[data-report-search]');
    const update=()=>{let visible=0;const query=search.value.trim().toLocaleLowerCase();reportRows.forEach(row=>{const state=row.dataset.operationState;const match=filter==='all'||filter===state||filter==='active'&&['queued','running'].includes(state)||filter==='failed'&&['failed','cancelled'].includes(state);row.hidden=!(match&&row.dataset.recordSearch.toLocaleLowerCase().includes(query));if(!row.hidden)visible++;});page.querySelector('[data-report-filter-empty]').hidden=visible>0||(!reportRows.length&&!query&&filter==='all');};
    page.querySelectorAll('[data-report-filter]').forEach(button=>button.addEventListener('click',()=>{filter=button.dataset.reportFilter;page.querySelectorAll('[data-report-filter]').forEach(other=>other.setAttribute('aria-pressed',String(other===button)));update();}));search.addEventListener('input',update);
  }
  if(page.dataset.analysisPage==='history'){
    let filter='all';const search=page.querySelector('#history-search'),rows=[...page.querySelectorAll('[data-history-row]')];
    const update=()=>{const query=search.value.trim().toLocaleLowerCase();let visible=0;rows.forEach(row=>{row.hidden=!((filter==='all'||filter===row.dataset.recordType)&&row.dataset.recordTitle.toLocaleLowerCase().includes(query));if(!row.hidden)visible++;});page.querySelector('#history-empty').hidden=visible>0;text(page.querySelector('[data-history-empty-text]'),rows.length?'没有找到匹配内容，试试其他分类或关键词。':'创建简历或添加岗位后，相关内容会显示在这里。');};
    page.querySelectorAll('[data-history-filter]').forEach(button=>button.addEventListener('click',()=>{filter=button.dataset.historyFilter;page.querySelectorAll('[data-history-filter]').forEach(other=>other.setAttribute('aria-pressed',String(other===button)));update();}));search.addEventListener('input',update);update();
  }
  page.querySelectorAll('[data-evidence-filter]').forEach(button=>button.addEventListener('click',()=>{
    const scope=button.closest('.cfa-evidence');let visible=0;
    scope.querySelectorAll('[data-evidence-filter]').forEach(other=>other.setAttribute('aria-pressed',String(other===button)));
    scope.querySelectorAll('[data-evidence-category]').forEach(row=>{row.hidden=button.dataset.evidenceFilter!=='all'&&row.dataset.evidenceCategory!==button.dataset.evidenceFilter;if(!row.hidden)visible++;});scope.querySelector('[data-evidence-empty]').hidden=visible>0;
  }));

  const diagnostic=page.dataset.analysisPage==='detail'?page:null;
  if(diagnostic){
    const feedback=page.querySelector('#diagnosis-feedback');let starting=false;const keys=new Map();
    const start=async button=>{
      if(starting||button.disabled)return;starting=true;text(feedback,'');
      const kind=button.dataset.startAi;keys.set(kind,keys.get(kind)||crypto.randomUUID());
      const startButtons=[...page.querySelectorAll('[data-start-ai]')];startButtons.forEach(item=>lock(item,true));
      const panel=button.closest('[data-start-panel],.cfa-failure,.cfa-next-actions,.cfa-finish-shortcut');
      const running=page.querySelector('#diagnosis-running-template').content.firstElementChild.cloneNode(true);
      if(panel){panel.hidden=true;panel.after(running);}else page.querySelector('.cfa-diagnostic-main').prepend(running);
      try {await window.cfApi(`/api/diagnostics/${page.dataset.diagnostic}/start`,{kind,request_key:keys.get(kind)});location.reload();}
      catch(error){text(feedback,error.message);running.remove();if(panel)panel.hidden=false;startButtons.forEach(item=>lock(item,false));starting=false;}
    };
    page.querySelectorAll('[data-start-ai]').forEach(button=>button.addEventListener('click',()=>start(button)));
    page.querySelectorAll('[data-cancel-operation]').forEach(button=>button.addEventListener('click',async()=>{
      if(!await confirmAction('取消本次分析任务？已完成的记录仍会保留。','取消任务'))return;
      lock(button,true);try{await window.cfApi(`/api/operations/${button.dataset.cancelOperation}/cancel`,{});location.reload();}catch(error){text(feedback,error.message);lock(button,false);}
    }));
    const answer=page.querySelector('#diagnostic-answer');let answerKey=crypto.randomUUID(),answering=false;
    answer?.addEventListener('input',()=>{answerKey=crypto.randomUUID();answer.setCustomValidity('');});
    answer?.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key==='Enter'){event.preventDefault();page.querySelector('[data-answer="answer"]')?.click();}});
    page.querySelectorAll('[data-answer]').forEach(button=>button.addEventListener('click',async()=>{
      if(answering)return;const skipped=button.dataset.answer==='skip';
      if(!skipped&&!answer.value.trim()){answer.setCustomValidity('请补充真实经历，或跳过本轮。');answer.reportValidity();return;}
      answering=true;page.querySelectorAll('[data-answer]').forEach(item=>lock(item,true));text(feedback,'');
      try{await window.cfApi(`/api/diagnostics/${page.dataset.diagnostic}/answer`,{request_key:answerKey,revision:Number(page.dataset.revision),skipped,answer:answer.value});location.reload();}
      catch(error){text(feedback,error.message);answering=false;page.querySelectorAll('[data-answer]').forEach(item=>lock(item,false));}
    }));
    if(new URLSearchParams(location.search).get('start')==='analysis'){
      history.replaceState(null,'',location.pathname);
      if(!page.querySelector('[data-operation-state="queued"],[data-operation-state="running"]'))requestAnimationFrame(()=>page.querySelector('[data-start-ai="analysis"]')?.click());
    }
  }

  // One visibility-aware poller per page, with no overlapping network ticks.
  const active=[...page.querySelectorAll('[data-active-operation],[data-report-operation],[data-operation]')].filter(card=>['queued','running'].includes(card.dataset.operationState));
  if(active.length){
    let timer=null,stopped=false,errors=0;const abort=new AbortController();
    const tick=async()=>{
      if(stopped)return;if(document.hidden){timer=setTimeout(tick,2500);return;}
      try{
        const ids=[...new Set(active.map(card=>card.dataset.activeOperation||card.dataset.reportOperation||card.dataset.operation))];
        const states=await Promise.all(ids.map(id=>read(`/api/operations/${id}`,{signal:abort.signal})));
        errors=0;
        if(states.some((result,index)=>!['queued','running'].includes(result.state)||(diagnostic&&active.some(card=>String(ids[index])===card.dataset.operation&&result.state!==card.dataset.operationState)))){location.reload();return;}
      }catch(error){if(stopped)return;errors++;if(errors>=3)text(page.querySelector('#diagnosis-feedback')||page.querySelector('[data-list-feedback]'),'暂时无法读取最新进度，正在尝试重新连接。也可以刷新本页。');}
      timer=setTimeout(tick,errors?5000:2000);
    };
    timer=setTimeout(tick,1200);window.addEventListener('pagehide',()=>{stopped=true;clearTimeout(timer);abort.abort();},{once:true});
  }
})();
