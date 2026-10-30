/* Paragraph review owns selection, local edits, candidates and version creation. */
(() => {
  'use strict';
  const streamText=(node,text,complete=false)=>{if(window.cfStreamText)window.cfStreamText(node,text,complete);else node.textContent=text;};
  const form=document.querySelector('[data-review-workbench]');
  if(!form)return;
  class ParagraphReview {
    constructor(element){
      this.form=element;this.rows=[...element.querySelectorAll('[data-review-path]')];
      this.feedback=document.querySelector('#diagnosis-feedback');this.toggleAll=element.querySelector('[data-review-select-all]');this.count=element.querySelector('[data-review-count]');
      this.requestKey=crypto.randomUUID();this.filter='all';this.busy=false;this.aborted=false;this.controller=new AbortController();
      this.bind();this.bindSupplement();this.update();
      window.addEventListener('pagehide',()=>{this.aborted=true;this.controller.abort();},{once:true});
    }
    original(row){return row.querySelector('[data-review-original]').textContent;}
    text(row){return row.querySelector('[data-review-text]');}
    check(row){return row.querySelector('[name="suggestion"]');}
    changed(row){return this.text(row).value.trim()!==this.original(row).trim();}
    status(row,message){const element=row.querySelector('[data-review-status]');element.hidden=!message;element.textContent=message;}
    setBusy(value){this.busy=value;this.form.querySelectorAll('[data-review-rewrite],button[type="submit"]').forEach(button=>{button.disabled=value;button.setAttribute('aria-busy',String(value));});}
    update(){
      const selected=this.rows.filter(row=>this.check(row).checked),changed=this.rows.filter(row=>this.changed(row));
      const extra=Boolean(this.form.querySelector('[data-supplement-text]')?.value.trim());this.count.textContent=`已选 ${selected.length} 段${extra?'，另有1段补充':''}`;this.toggleAll.checked=changed.length>0&&changed.every(row=>this.check(row).checked);this.toggleAll.indeterminate=selected.length>0&&!this.toggleAll.checked;
      this.rows.forEach(row=>{
        row.classList.toggle('is-selected',this.check(row).checked);
        row.querySelector('[data-review-row-state]').textContent=this.changed(row)?'已改动':'与原文一致';
        const field=this.text(row),count=row.querySelector('[data-review-length]');
        count.textContent=`${field.value.length} / ${field.maxLength} 字`;
      });
      this.form.querySelector('[data-review-save-count]').textContent=(selected.length||extra)?`已选择 ${selected.length} 段${extra?' + 1段补充':''}`:'尚未选择段落';
      this.applyFilter();
    }
    applyFilter(){
      let visible=0;
      this.rows.forEach(row=>{row.hidden=this.filter==='changed'?!this.changed(row):this.filter==='selected'?!this.check(row).checked:false;if(!row.hidden)visible++;});
      this.form.querySelectorAll('[data-review-section]').forEach(section=>{section.hidden=![...section.querySelectorAll('[data-review-path]')].some(row=>!row.hidden);});
      this.form.querySelector('[data-review-filter-empty]').hidden=visible>0;
      this.form.querySelectorAll('[data-review-filter]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.reviewFilter===this.filter)));
    }
    bind(){
      this.form.querySelectorAll('[data-review-filter]').forEach(button=>button.addEventListener('click',()=>{this.filter=button.dataset.reviewFilter;this.applyFilter();}));
      this.form.addEventListener('invalid',event=>{this.feedback.dataset.feedbackState='error';this.feedback.textContent=event.target.name==='confirmed'?'请核实所选内容，并勾选真实性确认。':event.target.name==='title'?'请填写岗位简历名称。':'请检查需要保存的替换正文。';},true);
      this.form.querySelectorAll('.cfa-review-nav nav>a').forEach(link=>link.addEventListener('click',()=>{const target=document.getElementById(link.hash.slice(1));if(target?.hidden){this.filter='all';this.applyFilter();}}));
      this.toggleAll.addEventListener('change',()=>{this.rows.forEach(row=>{this.check(row).checked=this.toggleAll.checked&&this.changed(row);});this.requestKey=crypto.randomUUID();this.update();});
      this.form.addEventListener('input',()=>{this.requestKey=crypto.randomUUID();this.update();});
      this.rows.forEach(row=>{
        const textarea=this.text(row),checkbox=this.check(row),candidate=row.querySelector('[data-review-candidate]');
        textarea.addEventListener('input',()=>{checkbox.checked=this.changed(row);this.update();});checkbox.addEventListener('change',()=>this.update());
        row.querySelector('[data-review-reset]').addEventListener('click',()=>{textarea.value=this.original(row);checkbox.checked=false;candidate.hidden=true;this.requestKey=crypto.randomUUID();this.status(row,'已还原原文。');this.update();});
        row.querySelector('[data-review-dismiss]').addEventListener('click',()=>{candidate.hidden=true;});
        row.querySelector('[data-review-adopt]').addEventListener('click',()=>{
          if(candidate.dataset.state!=='succeeded')return;
          textarea.value=row.querySelector('[data-review-candidate-text]').textContent;checkbox.checked=this.changed(row);candidate.hidden=true;this.requestKey=crypto.randomUUID();this.status(row,'已放入替换正文，核实后保存。');this.update();
        });
        row.querySelector('[data-review-rewrite]').addEventListener('click',()=>this.rewrite(row));
      });
      this.form.addEventListener('submit',event=>{event.preventDefault();this.save();});
    }
    bindSupplement(){
      const button=this.form.querySelector('[data-supplement-generate]'),facts=this.form.querySelector('[data-supplement-facts]'),draft=this.form.querySelector('[data-supplement-text]'),status=this.form.querySelector('[data-supplement-status]');
      button.addEventListener('click',async()=>{
        if(this.busy)return;if(!facts.value.trim()){status.textContent='请先写下真实信息，不能仅凭岗位要求生成经历。';facts.focus();return;}
        this.setBusy(true);button.disabled=true;status.textContent='正在整理，你可以在完成后核实正文…';
        try{
          const original=facts.value.trim(),previousDraft=draft.value;const started=await window.cfApi(`/api/resumes/${this.form.dataset.resumeId}/ai/start`,{request_key:crypto.randomUUID(),revision:Number(this.form.dataset.resumeRevision),path:'summary',mode:'generate',source_facts:original,requirement:this.form.querySelector('[data-supplement-requirement]').textContent});
          const deadline=Date.now()+180000;
          while(Date.now()<deadline&&!this.aborted){
            const result=await window.cfGet(`/api/resume-ai/${started.id}`);
            if(result.state==='succeeded'){
              if(facts.value.trim()!==original||draft.value!==previousDraft)throw new Error('真实信息已修改，请重新整理，当前正文没有被覆盖。');
              if(!result.result?.proposed||result.result.proposed.length>2000)throw new Error('补充正文过长，请精简真实信息后重试。');
              draft.value=result.result.proposed;this.requestKey=crypto.randomUUID();this.update();status.textContent='请核实正文，再勾选真实性确认并保存。';return;
            }
            if(['failed','cancelled'].includes(result.state))throw new Error(result.error||'整理未完成，请重试。');
            await new Promise(resolve=>setTimeout(resolve,700));
          }
          throw new Error('任务仍在处理中，请稍后查看记录。');
        }catch(error){status.textContent=error.message;}finally{this.setBusy(false);button.disabled=false;}
      });
    }
    async rewrite(row){
      if(this.busy)return;this.setBusy(true);
      const candidate=row.querySelector('[data-review-candidate]'),adopt=row.querySelector('[data-review-adopt]');candidate.hidden=true;candidate.dataset.state='running';row.setAttribute('aria-busy','true');row.querySelector('[data-review-candidate-state]').textContent='✦ 正在生成';adopt.disabled=true;this.status(row,'正在改写这一段…');
      try{
        const started=await window.cfApi(`/api/resumes/${this.form.dataset.resumeId}/ai/start`,{request_key:crypto.randomUUID(),revision:Number(this.form.dataset.resumeRevision),path:row.dataset.reviewPath,mode:'professional'});
        const deadline=Date.now()+180000;
        while(Date.now()<deadline&&!this.aborted){
          const response=await fetch(`/api/resume-ai/${started.id}`,{credentials:'same-origin',redirect:'error',signal:this.controller.signal});
          const result=await response.json();if(!response.ok)throw new Error(result.error||'暂时无法读取改写结果。');
          if(result.partial?.proposed){streamText(row.querySelector('[data-review-candidate-text]'),result.partial.proposed);row.querySelector('[data-review-candidate-reason]').textContent='正在生成，完整结果尚未校验。';candidate.hidden=false;}
          if(result.state==='succeeded'){
            const output=result.result;
            if(!output?.proposed||output.original!==this.original(row))throw new Error('原文版本已变化，请打开完整编辑器核对。');
            if(output.proposed.length>this.text(row).maxLength)throw new Error('建议超过本段长度上限，请在完整编辑器中精简。');
            streamText(row.querySelector('[data-review-candidate-text]'),output.proposed,true);row.querySelector('[data-review-candidate-reason]').textContent=output.reason||'';
            candidate.dataset.state='succeeded';row.querySelector('[data-review-candidate-state]').textContent='✦ 已完成校验';candidate.hidden=false;adopt.disabled=false;this.status(row,'改写已完成。先比较，再决定是否采用。');return;
          }
          if(['failed','cancelled'].includes(result.state))throw new Error(result.error||'这次改写未完成，请重试。');
          await new Promise(resolve=>setTimeout(resolve,700));
        }
        if(!this.aborted)throw new Error('任务仍在处理中，请稍后到历史记录查看。');
      }catch(error){if(!this.aborted){candidate.dataset.state='failed';row.querySelector('[data-review-candidate-state]').textContent='本次改写未完成';this.status(row,error.message);}}
      finally{if(!this.aborted){row.setAttribute('aria-busy','false');this.setBusy(false);}}
    }
    async save(){
      if(this.busy)return;
      const selected=this.rows.filter(row=>this.check(row).checked);
      const addition=this.form.querySelector('[data-supplement-text]').value.trim();
      if(!selected.length&&!addition){this.feedback.dataset.feedbackState='error';this.feedback.textContent='请选择要保存的段落。';this.feedback.focus();return;}
      if(selected.length>30){this.feedback.dataset.feedbackState='error';this.feedback.textContent='一次最多保存 30 段，请减少选择后再保存。';this.feedback.focus();return;}
      if(!this.form.reportValidity())return;
      this.setBusy(true);this.feedback.dataset.feedbackState='neutral';this.feedback.textContent='正在创建岗位简历版本…';
      try{
        const result=await window.cfApi(`/api/operations/${this.form.dataset.applySuggestions}/apply`,{request_key:this.requestKey,confirmed:'yes',title:this.form.elements.title.value,additions:addition?[addition]:[],paragraph_edits:Object.fromEntries(selected.map(row=>[row.dataset.reviewPath,this.text(row).value]))});
        location.href=`/workspace?view=resume-new&resume_id=${result.id}`;
      }catch(error){this.feedback.dataset.feedbackState='error';this.feedback.textContent=error.message;this.feedback.focus();window.cfFieldErrors?.(this.form,error);this.setBusy(false);}
    }
  }
  new ParagraphReview(form);
})();
