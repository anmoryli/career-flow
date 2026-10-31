/* Shared transport, dialog lifecycle and shell behavior. No page business state lives here. */
(() => {
  'use strict';
  const csrf=()=>document.querySelector('meta[name="csrf-token"]')?.content||'';
  const request=async(url,options={},networkRetries=0)=>{
    const target=new URL(url,location.href);
    if(target.origin!==location.origin) throw new Error('请求地址不属于当前站点。');
    let response;
    for(let attempt=0;attempt<=networkRetries;attempt++){
      try {response=await fetch(target,{credentials:'same-origin',redirect:'error',...options});break;}
      catch {if(attempt===networkRetries)throw new Error('连接暂时中断，请重试。填写内容仍会保留。');await new Promise(resolve=>setTimeout(resolve,180));}
    }
    let result;
    try {result=await response.json();}
    catch {throw new Error(`服务暂未完成请求（${response.status}），请刷新登录状态后重试。`);}
    if(!response.ok){const error=new Error(result.error==='login_required'?'请先登录后继续。':result.error||'请求暂未完成，请稍后重试。');error.status=response.status;error.fields=result.fields||{};error.loginRequired=Boolean(result.login_required)||response.status===401;throw error;}
    return result;
  };
  window.cfApi=(url,payload)=>request(url,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf()},body:JSON.stringify(payload)},typeof payload?.request_key==='string'?1:0);
  window.cfGet=url=>request(url,{},1);
  window.cfRequest=request;
  window.cfRefreshCSRF=async()=>{
    const response=await fetch(location.href,{credentials:'same-origin',cache:'no-store'});
    if(!response.ok)throw new Error('登录成功，但页面状态尚未同步，请刷新后继续。');
    const page=new DOMParser().parseFromString(await response.text(),'text/html');
    const token=page.querySelector('meta[name="csrf-token"]')?.content;
    if(!token)throw new Error('无法同步页面校验信息，请刷新后继续。');
    document.querySelector('meta[name="csrf-token"]').content=token;
    document.querySelectorAll('input[name="csrf_token"]').forEach(input=>{input.value=token;});
  };
  // Error summaries remain visible while every server-reported field gets a linked hint.
  const clearFieldError=input=>{
    const id=input.dataset.cfErrorId;
    if(!id)return;
    document.getElementById(id)?.remove();
    const described=(input.getAttribute('aria-describedby')||'').split(/\s+/).filter(value=>value&&value!==id);
    if(described.length)input.setAttribute('aria-describedby',described.join(' '));else input.removeAttribute('aria-describedby');
    input.removeAttribute('aria-invalid');delete input.dataset.cfErrorId;
  };
  let errorIndex=0;
  window.cfFieldErrors=(form,error)=>{
    form.querySelectorAll('[data-cf-error-id]').forEach(clearFieldError);
    let first;
    for(const [name,message] of Object.entries(error?.fields||{})){
      const input=form.elements.namedItem(name);
      if(!(input instanceof HTMLElement))continue;
      const hint=document.createElement('small');hint.id=`cf-field-error-${++errorIndex}`;hint.dataset.fieldError=name;hint.textContent=String(message);
      input.dataset.cfErrorId=hint.id;input.setAttribute('aria-invalid','true');
      input.setAttribute('aria-describedby',[input.getAttribute('aria-describedby'),hint.id].filter(Boolean).join(' '));input.after(hint);first||=input;
    }
    first?.focus();
  };
  document.addEventListener('input',event=>{if(event.target instanceof HTMLElement)clearFieldError(event.target);});
  let toastTimer;
  window.cfToast=message=>{const toast=document.querySelector('#theme-feedback');if(!toast)return;clearTimeout(toastTimer);toast.textContent=message;toast.hidden=false;toastTimer=setTimeout(()=>{toast.hidden=true;},2500);};
  const themeSelector=document.querySelector('#theme-select');
  const syncThemeChoices=()=>{
    const preference=document.documentElement.dataset.preference;
    if(themeSelector)themeSelector.value=preference;
    document.querySelectorAll('[data-theme-choice]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.themeChoice===preference)));
  };
  const changeTheme=async value=>{
    window.cfTheme(value);syncThemeChoices();try{localStorage.setItem('cf-theme',value);}catch{}
    const status=document.querySelector('#settings-theme-status');
    if(document.body.dataset.authenticated!=='yes'){if(status)status.textContent='外观偏好已保存到当前设备。';return;}
    let message='外观偏好已同步';
    try{await window.cfApi('/settings/theme',{theme:value});}catch{message='已在本机切换，跨设备同步暂未完成';}
    if(status)status.textContent=message;window.cfToast(message);
  };
  themeSelector?.addEventListener('change',()=>changeTheme(themeSelector.value));
  document.querySelectorAll('[data-theme-choice]').forEach(button=>button.addEventListener('click',()=>changeTheme(button.dataset.themeChoice)));
  syncThemeChoices();
  const openers=new WeakMap();
  window.cfOpenDialog=dialog=>{if(typeof dialog==='string')dialog=document.getElementById(dialog);if(!dialog||dialog.open)return;openers.set(dialog,document.activeElement);dialog.showModal();};
  window.cfCloseDialog=dialog=>{if(!dialog?.open)return;dialog.close();};
  document.addEventListener('click',event=>{
    const opener=event.target.closest('[data-dialog-open]');if(opener){event.preventDefault();window.cfOpenDialog(opener.dataset.dialogOpen);}
    const closer=event.target.closest('[data-dialog-close]');if(closer){event.preventDefault();window.cfCloseDialog(closer.closest('dialog'));}
    if(event.target instanceof HTMLDialogElement){const r=event.target.getBoundingClientRect();if(!event.target.querySelector('form')&&(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom))event.target.dispatchEvent(new Event('cancel',{cancelable:true}));}
    document.querySelectorAll('.cf-account-menu[open],.cf-task-menu[open]').forEach(menu=>{if(!menu.contains(event.target))menu.open=false;});
  });
  document.querySelectorAll('dialog').forEach(dialog=>{
    dialog.addEventListener('close',()=>{const trigger=openers.get(dialog);if(trigger?.isConnected)trigger.focus();});
    dialog.addEventListener('cancel',event=>{queueMicrotask(()=>{if(!event.defaultPrevented)window.cfCloseDialog(dialog);});});
  });
  document.addEventListener('keydown',event=>{if(event.key==='Escape')document.querySelectorAll('.cf-account-menu[open],.cf-task-menu[open]').forEach(menu=>{menu.open=false;menu.querySelector('summary').focus();});});
  document.addEventListener('htmx:configRequest',event=>{event.detail.headers['X-CSRFToken']=csrf();});
  // Disable only ordinary server forms after all page listeners had a chance to cancel submission.
  // A macrotask keeps the submitter enabled while the browser encodes the entry list; a microtask
  // would run before encoding and drop the clicked button's name/value (breaks action=... forms).
  document.addEventListener('submit',event=>{const form=event.target;if(form.matches('[data-ui-form]'))return;setTimeout(()=>{if(event.defaultPrevented)return;form.querySelectorAll('button[type="submit"]').forEach(button=>{button.disabled=true;button.setAttribute('aria-busy','true');});},0);});
  window.addEventListener('pageshow',()=>document.querySelectorAll('button[aria-busy=true]').forEach(button=>{button.disabled=false;button.removeAttribute('aria-busy');}));
  const resize=new ResizeObserver(entries=>entries.forEach(({target})=>{
    const doc=target.querySelector('.resume-doc');if(!doc||!target.clientWidth)return;
    const style=getComputedStyle(target);const width=target.clientWidth-parseFloat(style.paddingLeft)-parseFloat(style.paddingRight);
    doc.style.zoom=String(width/794);
  }));
  document.querySelectorAll('[data-document-thumbnail]').forEach(element=>resize.observe(element));
  // Progressive enhancement: no CSS starts content hidden, and failed JS cannot hide it.
  const motion=matchMedia('(prefers-reduced-motion: reduce)');
  const entrants=document.querySelectorAll('[data-reveal]');
  if('IntersectionObserver' in window){
    const observer=new IntersectionObserver(entries=>entries.forEach(entry=>{
      if(!entry.isIntersecting)return;
      observer.unobserve(entry.target);
      if(!motion.matches)entry.target.animate([{opacity:.65,transform:'translateY(12px)'},{opacity:1,transform:'translateY(0)'}],{duration:420,easing:'cubic-bezier(.2,.7,.2,1)'});
    }),{threshold:.08});
    entrants.forEach(node=>observer.observe(node));
    motion.addEventListener('change',()=>{if(motion.matches)entrants.forEach(node=>node.getAnimations().forEach(animation=>animation.cancel()));});
  }
  // Filter only the rows already rendered for this user; no external search service.
  document.querySelectorAll('[data-filter-target]').forEach(input=>input.addEventListener('input',()=>{
    const query=input.value.trim().toLocaleLowerCase();
    let matches=0;document.querySelectorAll(input.dataset.filterTarget).forEach(row=>{row.hidden=!row.textContent.toLocaleLowerCase().includes(query);if(!row.hidden)matches++;});document.querySelectorAll('[data-filter-empty-for]').forEach(node=>{if(node.dataset.filterEmptyFor===input.dataset.filterTarget)node.hidden=matches>0;});
  }));
})();
