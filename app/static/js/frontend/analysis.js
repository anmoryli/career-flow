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
    const header = document.createElement('header'), title = document.createElement('h2'); title.id=`analysis-confirm-${crypto.randomUUID()}`;title.textContent = '确认操作';dialog.setAttribute('aria-labelledby',title.id);header.append(title);
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
    let requestKey = crypto.randomUUID(), resumeRequestKey = crypto.randomUUID(), guestResume = null, busy = false, uploadGeneration = 0, guestReading = false;
    const submitLabel=page.querySelector('[data-job-submit-label]');
    const feedback=(message,state='neutral')=>{text(status,message);status.dataset.feedbackState=state;if(state==='error')status.focus();};
    const syncReadiness=()=>{
      const selected=resumeSelect?.selectedOptions[0],hasResume=Boolean(resumeSelect?.value||guestResume),hasDescription=Boolean(description.value.trim());
      text(page.querySelector('#jd-character-count'),`${description.value.length.toLocaleString()} / 20,000 字`);
      text(page.querySelector('[data-job-source-summary]'),hasResume?(resumeSelect?`${selected.textContent}`:guestResume.title||'已读取 PDF'):guestReading?'正在提取 PDF…':'使用已保存的简历');
      const states={resume:hasResume?'complete':'current',description:hasResume?(hasDescription?'complete':'current'):'pending',analysis:hasResume&&hasDescription?'current':'pending'};
      page.querySelectorAll('[data-job-step]').forEach(step=>{step.dataset.state=states[step.dataset.jobStep];if(states[step.dataset.jobStep]==='current')step.setAttribute('aria-current','step');else step.removeAttribute('aria-current');});
      text(page.querySelector('[data-job-ready-hint]'),guestReading?'正在提取简历，完成后即可继续。':!hasResume?'先选择本次使用的简历。':!hasDescription?'简历已就绪，粘贴岗位描述后开始。':`已准备好 · ${description.value.trim().length.toLocaleString()} 字岗位描述`);
      jobForm.dataset.ready=String(hasResume&&hasDescription);
    };
    const changed=()=>{requestKey=crypto.randomUUID();syncReadiness();};
    jobForm.addEventListener('invalid',event=>{const messages={'analysis-resume':'请选择用于本次分析的简历。','job-description':'请粘贴岗位职责与任职要求。','job-url':'请填写有效的岗位链接，或留空。'};feedback(messages[event.target.id]||'请检查表单中的必填内容。','error');},true);
    jobForm.addEventListener('input', changed); changed();
    const chooseGuest=page.querySelector('[data-choose-guest-resume]');
    chooseGuest?.addEventListener('click',()=>guestInput?.click());
    guestInput?.addEventListener('change', async () => {
      guestResume = null; guestReading=false; resumeRequestKey = crypto.randomUUID(); const generation = ++uploadGeneration;
      const file = guestInput.files[0], feedback = page.querySelector('#guest-resume-status');
      text(page.querySelector('[data-guest-file-name]'),file?.name||'尚未选择文件');text(chooseGuest,file?'更换 PDF':'选择 PDF 文件');
      if (!file) { text(feedback,'');feedback.dataset.tone='info';syncReadiness(); return; }
      if (file.size > 4*1024*1024 || !file.name.toLowerCase().endsWith('.pdf')) {feedback.dataset.tone='error';text(feedback,'请选择不超过 4 MB 的 PDF 简历。');syncReadiness();return;}
      guestReading=true;syncReadiness();feedback.dataset.tone='info';text(feedback,'正在提取简历内容…'); const data = new FormData(); data.set('file',file);
      try {
        const result = await read('/api/guest/resume/parse',{method:'POST',body:data,headers:{'X-CSRFToken':csrf()}});
        if (generation !== uploadGeneration) return;
        guestResume = result;guestReading=false;syncReadiness();feedback.dataset.tone='success';text(feedback,`已读取「${result.title || file.name}」，开始分析时登录。`);
      } catch(error) { if(generation===uploadGeneration){guestReading=false;syncReadiness();feedback.dataset.tone='error';text(feedback,error.message);} }
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
      if(guestReading){feedback('简历仍在提取中，请稍候。');return;}
      if(!resumeSelect && !guestResume){feedback('请先上传一份 PDF 简历。','error');guestInput?.focus();return;}
      busy=true;lock(submit,true);text(submitLabel,'正在准备分析…');feedback('正在保存岗位并准备分析…');
      const perform = async () => {
        let resumeId=Number(resumeSelect?.value),revision=Number(resumeSelect?.selectedOptions[0]?.dataset.revision);
        if(!resumeSelect){const saved=await window.cfApi('/api/resumes',{request_key:resumeRequestKey,title:guestResume.title || '导入的简历',template:'classic',document:guestResume.document});resumeId=saved.id;revision=saved.revision;}
        const result=await window.cfApi('/api/jobs',{request_key:requestKey,resume_id:resumeId,resume_revision:revision,title:fields[0].value,company:fields[1].value,description:description.value,url:fields[3].value,save_for_later:page.querySelector('[data-save-job-for-later]').checked});
        location.href=`/jobs/${result.id}?start=analysis`;
      };
      try {await perform();}catch(error){
        if(error.loginRequired && window.cfRequireAuth){feedback('登录后继续刚才的分析。');window.cfRequireAuth(async()=>{busy=true;lock(submit,true);try{await perform();}catch(next){feedback(next.message,'error');window.cfFieldErrors?.(jobForm,next);busy=false;lock(submit,false);text(submitLabel,'开始岗位分析');}});}
        else {feedback(error.message,'error');window.cfFieldErrors?.(jobForm,error);}
        busy=false;lock(submit,false);text(submitLabel,'开始岗位分析');
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

  const reportRows=[...page.querySelectorAll('[data-report-operation]')];
  if(page.dataset.analysisPage==='reports'){
    let filter='all';const search=page.querySelector('[data-report-search]');
    const update=()=>{
      let visible=0;const query=search.value.trim().toLocaleLowerCase();
      reportRows.forEach(row=>{const state=row.dataset.operationState;const match=filter==='all'||filter===state||filter==='active'&&['queued','running'].includes(state)||filter==='failed'&&['failed','cancelled'].includes(state);row.hidden=!(match&&row.dataset.recordSearch.toLocaleLowerCase().includes(query));if(!row.hidden)visible++;});
      const filtering=filter!=='all'||Boolean(query);
      page.querySelector('[data-report-filter-empty]').hidden=visible>0||(!reportRows.length&&!filtering);
      const initialEmpty=page.querySelector('[data-report-origin-empty]');if(initialEmpty)initialEmpty.hidden=filtering;
      text(page.querySelector('[data-report-visible-count]'),filtering?`找到 ${visible} 条记录`:`${visible} 条分析记录`);
      page.querySelector('[data-report-reset]').hidden=!filtering;
    };
    const selectFilter=value=>{filter=value;page.querySelectorAll('[data-report-filter]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.reportFilter===value)));update();};
    page.querySelectorAll('[data-report-filter]').forEach(button=>button.addEventListener('click',()=>selectFilter(button.dataset.reportFilter)));
    page.querySelector('[data-report-reset]').addEventListener('click',()=>{search.value='';selectFilter('all');});search.addEventListener('input',update);update();
  }
  if(page.dataset.analysisPage==='history'){
    let filter='all';const search=page.querySelector('#history-search'),rows=[...page.querySelectorAll('[data-history-row]')];
    const update=()=>{
      const query=search.value.trim().toLocaleLowerCase();let visible=0;
      rows.forEach(row=>{row.hidden=!((filter==='all'||filter===row.dataset.recordType)&&row.dataset.recordTitle.toLocaleLowerCase().includes(query));if(!row.hidden)visible++;});
      page.querySelector('#history-empty').hidden=visible>0;
      text(page.querySelector('[data-history-empty-text]'),rows.length?'没有找到匹配内容，试试其他分类或关键词。':'创建简历或添加岗位后，相关内容会显示在这里。');
      const filtering=filter!=='all'||Boolean(query);text(page.querySelector('[data-history-visible-count]'),filtering?`找到 ${visible} 条记录`:`${visible} 条历史记录`);page.querySelector('[data-history-reset]').hidden=!filtering;
    };
    const selectFilter=value=>{filter=value;page.querySelectorAll('[data-history-filter]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.historyFilter===value)));update();};
    page.querySelectorAll('[data-history-filter]').forEach(button=>button.addEventListener('click',()=>selectFilter(button.dataset.historyFilter)));
    page.querySelector('[data-history-reset]').addEventListener('click',()=>{search.value='';selectFilter('all');});search.addEventListener('input',update);update();
  }
  const journal=page.querySelector('.cfa-journal-composer textarea');
  if(journal){const update=()=>text(page.querySelector('[data-journal-length]'),`${journal.value.length.toLocaleString()} / 10000 字`);journal.addEventListener('input',update);update();}
  // Delegated so the buttons keep working after the result slot is swapped for
  // a freshly rendered panel; a per-node binding would die with the old nodes.
  const applyEvidenceFilter=button=>{
    const scope=button.closest('.cfa-evidence');if(!scope)return;let visible=0;
    scope.querySelectorAll('[data-evidence-filter]').forEach(other=>other.setAttribute('aria-pressed',String(other===button)));
    scope.querySelectorAll('[data-evidence-category]').forEach(row=>{row.hidden=button.dataset.evidenceFilter!=='all'&&row.dataset.evidenceCategory!==button.dataset.evidenceFilter;if(!row.hidden)visible++;});scope.querySelector('[data-evidence-empty]').hidden=visible>0;
  };
  page.addEventListener('click',event=>{const button=event.target.closest?.('[data-evidence-filter]');if(button)applyEvidenceFilter(button);});
  const pressedEvidenceFilter=()=>page.querySelector('[data-evidence-filter][aria-pressed="true"]')?.dataset.evidenceFilter||'all';

  const diagnostic=page.dataset.analysisPage==='detail'?page:null;
  if(diagnostic){
    const feedback=page.querySelector('#diagnosis-feedback');
    const copilot=page.querySelector('[data-copilot]');
    const thread=copilot?.querySelector('[data-copilot-thread]');
    const liveBubble=copilot?.querySelector('[data-copilot-live]');
    const liveText=copilot?.querySelector('[data-copilot-live-text]');
    const copilotState=copilot?.querySelector('[data-copilot-state]');
    const resultSlot=page.querySelector('[data-result-slot]');
    const column=page.querySelector('.cfa-diagnostic-column');
    let starting=false,answering=false,source=null,streamText='',streaming=false,answerKey=crypto.randomUUID();
    const setCopilotState=value=>{if(copilotState)copilotState.textContent=value;};
    const scrollThread=()=>{if(thread)thread.scrollTop=thread.scrollHeight;};
    const setLive=(visible,value)=>{if(!liveBubble)return;liveBubble.hidden=!visible;if(value!==undefined&&liveText)liveText.textContent=value;if(visible)scrollThread();};
    const pushBubble=(role,content)=>{if(!thread||!content)return;const item=document.createElement('li');item.className=`cfa-copilot-msg is-${role}`;item.dataset.copilotMsg=role;const paragraph=document.createElement('p');paragraph.textContent=content;item.append(paragraph);thread.insertBefore(item,liveBubble||null);scrollThread();};

    const closeStream=()=>{if(source){source.close();source=null;}};

    // The left column is server-rendered, so the panel swap reuses exactly the
    // markup the first paint used; no rendering rules are duplicated here.
    const applyResultPanel=async operationId=>{
      if(!resultSlot||!operationId)return;
      // The user may already be filtering while the run finishes; a swap that
      // silently reset the tabs would look like the click was ignored.
      const filter=pressedEvidenceFilter();
      try{
        const response=await fetch(`/api/operations/${operationId}/panel`,{credentials:'same-origin',redirect:'error'});
        if(response.ok){
          resultSlot.innerHTML=await response.text();
          const restored=resultSlot.querySelector(`[data-evidence-filter="${filter}"]`);
          if(restored&&filter!=='all')applyEvidenceFilter(restored);
        }
      }catch{}
      page.querySelector('[data-copilot-running]')?.remove();
    };

    const attachStream=url=>{
      closeStream();
      if(!url||typeof EventSource==='undefined')return;
      streamText='';streaming=false;setLive(true,'');setCopilotState('正在分析');
      source=new EventSource(url);
      source.addEventListener('stage',event=>{
        if(streaming)return;
        let payload={};try{payload=JSON.parse(event.data);}catch{return;}
        if(payload.message)setLive(true,payload.message);
      });
      source.addEventListener('delta',event=>{
        let payload={};try{payload=JSON.parse(event.data);}catch{return;}
        if(!streaming){streaming=true;streamText='';setLive(true);}
        streamText+=payload.text||'';setLive(true,streamText);
      });
      source.addEventListener('delta_reset',()=>{streamText='';streaming=false;setLive(true,'');});
      source.addEventListener('result',event=>{
        let payload={};try{payload=JSON.parse(event.data);}catch{}
        setCopilotState('正在整理说明');
        applyResultPanel(payload.operation_id||copilot?.dataset.copilotOperation);
      });
      source.addEventListener('done',()=>{
        closeStream();setLive(false);setCopilotState('已完成');
        // The recap is persisted with the operation, so a reload replays the
        // whole conversation instead of dropping the text just streamed in.
        setTimeout(()=>location.reload(),900);
      });
      source.addEventListener('failed',event=>{
        closeStream();setLive(false);setCopilotState('需要重试');
        let payload={};try{payload=JSON.parse(event.data);}catch{}
        pushBubble('ai',payload.message||'本次分析没有完成，可以重试。');
        refreshChat();
      });
      source.onerror=()=>{
        // A stream closed right after a terminal event is normal; only a
        // still-open connection that the browser gave up on is a real error.
        if(!source)return;
        closeStream();setLive(false);setCopilotState('连接中断');
        pushBubble('ai','与服务器的连接中断了，可以刷新本页查看最新结果。');
      };
    };

    const refreshChat=async()=>{
      const body=copilot?.querySelector('[data-copilot-body]'),url=copilot?.dataset.copilotChat;
      if(!body||!url)return;
      try{
        const response=await fetch(url,{credentials:'same-origin',redirect:'error'});
        if(response.ok)body.innerHTML=await response.text();
      }catch{}
    };

    const startKind=async(kind,button)=>{
      if(starting)return;
      starting=true;text(feedback,'');
      const startButtons=[...page.querySelectorAll('[data-start-ai]')];
      const disabledBefore=new Map(startButtons.map(item=>[item,item.disabled]));
      startButtons.forEach(item=>lock(item,true));
      const panel=button?.closest('[data-start-panel],.cfa-failure,.cfa-next-actions,.cfa-finish-shortcut');
      const running=page.querySelector('#diagnosis-running-template').content.firstElementChild.cloneNode(true);
      if(panel){panel.hidden=true;running.setAttribute('data-copilot-running','');panel.after(running);}
      else if(column)column.prepend(running);
      try{
        // A fresh request key per start: reusing one would replay the previous
        // operation instead of running a new round.
        const result=await window.cfApi(`/api/diagnostics/${page.dataset.diagnostic}/start`,{kind,request_key:crypto.randomUUID()});
        starting=false;startButtons.forEach(item=>lock(item,false));
        if(copilot)copilot.dataset.copilotOperation=String(result.id);
        pushBubble('user',kind==='report'?'生成完整报告。':'开始岗位分析。');
        attachStream(`/api/operations/${result.id}/stream`);
      }catch(error){
        text(feedback,error.message);
        running.remove();
        if(panel)panel.hidden=false;
        startButtons.forEach(item=>{item.disabled=disabledBefore.get(item);item.setAttribute('aria-busy','false');});
        feedback.dataset.feedbackState='error';feedback.focus();starting=false;
      }
    };

    const submitAnswer=async skipped=>{
      if(answering)return;
      const field=copilot?.querySelector('#diagnostic-answer');
      if(!skipped&&!field?.value.trim()){field?.setCustomValidity('请补充真实经历，或跳过本轮。');field?.reportValidity();return;}
      answering=true;text(feedback,'');
      page.querySelectorAll('[data-answer]').forEach(item=>lock(item,true));
      const content=field?.value.trim()||'';
      try{
        const result=await window.cfApi(`/api/diagnostics/${page.dataset.diagnostic}/answer`,{request_key:answerKey,revision:Number(page.dataset.revision),skipped,answer:content});
        page.dataset.revision=String(result.revision);
        answerKey=crypto.randomUUID();
        pushBubble('user',skipped?'（本轮已跳过）':content);
        copilot?.querySelector('[data-copilot-question]')?.remove();
        if(field)field.value='';
        answering=false;
        page.querySelectorAll('[data-answer]').forEach(item=>lock(item,false));
        await startKind('analysis');
      }catch(error){
        text(feedback,error.message);answering=false;
        page.querySelectorAll('[data-answer]').forEach(item=>lock(item,false));
      }
    };

    const cancelOperation=async button=>{
      if(!await confirmAction('取消本次分析任务？已完成的记录仍会保留。','取消任务'))return;
      lock(button,true);
      try{await window.cfApi(`/api/operations/${button.dataset.cancelOperation}/cancel`,{});location.reload();}
      catch(error){text(feedback,error.message);lock(button,false);}
    };

    // Delegated so a refreshed composer keeps working without rebinding.
    page.addEventListener('click',event=>{
      const startButton=event.target.closest('[data-start-ai]');
      if(startButton){startKind(startButton.dataset.startAi,startButton);return;}
      const answerButton=event.target.closest('[data-answer]');
      if(answerButton){submitAnswer(answerButton.dataset.answer==='skip');return;}
      const cancelButton=event.target.closest('[data-cancel-operation]');
      if(cancelButton)cancelOperation(cancelButton);
    });
    page.addEventListener('input',event=>{if(event.target.id==='diagnostic-answer'){answerKey=crypto.randomUUID();event.target.setCustomValidity('');}});
    page.addEventListener('keydown',event=>{
      if(event.target.id!=='diagnostic-answer'||!(event.ctrlKey||event.metaKey)||event.key!=='Enter')return;
      if(window.cfImeGuard?.(event))return;
      event.preventDefault();
      copilot?.querySelector('[data-answer="answer"]')?.click();
    });

    if(copilot?.dataset.copilotStream)attachStream(copilot.dataset.copilotStream);
    if(new URLSearchParams(location.search).get('start')==='analysis'){
      history.replaceState(null,'',location.pathname);
      if(!page.querySelector('[data-operation-state="queued"],[data-operation-state="running"]'))requestAnimationFrame(()=>page.querySelector('[data-start-ai="analysis"]')?.click());
    }
  }

  // One visibility-aware poller per page, with no overlapping network ticks.
  // The detail page is driven by its event stream instead, so it is excluded.
  if(!page.querySelector('[data-copilot]')){
  const active=[...page.querySelectorAll('[data-active-operation],[data-report-operation],[data-operation]')].filter(card=>['queued','running'].includes(card.dataset.operationState));
  if(active.length){
    let timer=null,stopped=false,errors=0;const abort=new AbortController();
    const tick=async()=>{
      if(stopped)return;if(document.hidden){timer=setTimeout(tick,2500);return;}
      try{
        const ids=[...new Set(active.map(card=>card.dataset.activeOperation||card.dataset.reportOperation||card.dataset.operation))];
        const states=await Promise.all(ids.map(id=>read(`/api/operations/${id}`,{signal:abort.signal})));
        const pollFeedback=page.querySelector('#diagnosis-feedback')||page.querySelector('[data-list-feedback]');
        if(pollFeedback?.dataset.feedbackSource==='poll'){pollFeedback.textContent='';delete pollFeedback.dataset.feedbackSource;}
        errors=0;
        if(states.some((result,index)=>!['queued','running'].includes(result.state)||(diagnostic&&active.some(card=>String(ids[index])===card.dataset.operation&&result.state!==card.dataset.operationState)))){location.reload();return;}
        states.forEach((result,index)=>active.filter(card=>String(ids[index])===(card.dataset.activeOperation||card.dataset.reportOperation||card.dataset.operation)).forEach(card=>{card.dataset.operationState=result.state;const badge=card.querySelector('.cfa-state');if(badge){badge.textContent=result.state==='queued'?'排队中':'正在分析';badge.classList.toggle('cfa-state-queued',result.state==='queued');badge.classList.toggle('cfa-state-running',result.state==='running');}}));
      }catch(error){if(stopped)return;errors++;if(errors>=3){const feedback=page.querySelector('#diagnosis-feedback')||page.querySelector('[data-list-feedback]');if(feedback){feedback.dataset.feedbackSource='poll';feedback.textContent='暂时无法读取最新进度，正在尝试重新连接。也可以刷新本页。';}}}
      timer=setTimeout(tick,errors?5000:2000);
    };
    timer=setTimeout(tick,1200);window.addEventListener('pagehide',()=>{stopped=true;clearTimeout(timer);abort.abort();},{once:true});
  }
  }
})();
