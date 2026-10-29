/* Account forms and resumable login share one implementation and fresh CSRF state. */
(() => {
  'use strict';
  const dialog=document.querySelector('#auth-dialog');
  let continuation=null;
  const show=(form,message)=>{const node=form.querySelector('[data-auth-feedback],#auth-feedback');if(node){node.textContent=message;node.hidden=false;}};
  const setMode=mode=>{
    if(!dialog)return;
    dialog.querySelectorAll('[data-auth-modal-form]').forEach(form=>{form.hidden=form.dataset.authModalForm!==mode;});
    dialog.querySelectorAll('[data-auth-mode]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.authMode===mode)));
    dialog.querySelector('#auth-dialog-title').textContent=mode==='register'?'创建你的账号':'登录后继续';
  };
  const open=(mode='login',callback=null)=>{if(!dialog){location.href='/login';return;}continuation=callback;setMode(mode);window.cfOpenDialog(dialog);};
  window.cfRequireAuth=callback=>open('login',callback);
  document.addEventListener('click',event=>{
    const mode=event.target.closest('[data-auth-mode]');if(mode){event.preventDefault();setMode(mode.dataset.authMode);}
    const trigger=event.target.closest('[data-auth-open]');if(trigger&&dialog){event.preventDefault();open(trigger.dataset.authOpen);}
    if(event.target.closest('[data-auth-close]'))dialog?.close();
  });
  const sendCode=async(button,form)=>{
    if(!form.elements.email.reportValidity())return;
    button.disabled=true;
    try{
      const result=await window.cfApi('/auth/code',{email:form.elements.email.value});show(form,result.message||'验证码已发送，请查看邮箱。');
      let seconds=result.retry_after||60;const tick=()=>{button.textContent=seconds>0?`${seconds} 秒后重发`:'重新发送验证码';};tick();
      const timer=setInterval(()=>{seconds--;tick();if(seconds<=0){clearInterval(timer);button.disabled=false;}},1000);
    }catch(error){show(form,error.message);button.disabled=false;}
  };
  document.querySelectorAll('[data-auth-send-code],[data-send-code]').forEach(button=>button.addEventListener('click',()=>sendCode(button,button.closest('form'))));
  document.querySelectorAll('[data-password-toggle]').forEach(button=>button.addEventListener('click',()=>{
    const input=document.getElementById(button.getAttribute('aria-controls')||'password');input.type=input.type==='password'?'text':'password';button.setAttribute('aria-pressed',String(input.type==='text'));button.textContent=input.type==='text'?'隐藏密码':'显示密码';
  }));
  document.querySelectorAll('[data-auth-modal-form],[data-ui-form="auth"]').forEach(form=>form.addEventListener('submit',async event=>{
    event.preventDefault();if(!form.reportValidity())return;
    const button=form.querySelector('[type="submit"]');button.disabled=true;
    const mode=form.dataset.authModalForm||form.dataset.authMode||(location.pathname==='/register'?'register':'login');
    const data=Object.fromEntries(new FormData(form));delete data.csrf_token;
    const next=new URLSearchParams(location.search).get('next')||'/workspace';
    try{
      const target=(mode==='register'?'/register':'/login')+'?next='+encodeURIComponent(next);
      const result=await window.cfApi(target,data);
      if(continuation&&form.hasAttribute('data-auth-modal-form')){
        await window.cfRefreshCSRF();document.body.dataset.authenticated='yes';dialog.close();const callback=continuation;continuation=null;await callback();
      }else location.assign(result.next||'/workspace');
    }catch(error){show(form,error.message);form.querySelectorAll('[data-field-error]').forEach(node=>node.remove());form.querySelectorAll('[aria-invalid]').forEach(input=>input.removeAttribute('aria-invalid'));for(const [name,message] of Object.entries(error.fields||{})){const input=form.elements[name];if(!input)continue;input.setAttribute('aria-invalid','true');const hint=document.createElement('small');hint.dataset.fieldError=name;hint.textContent=message;input.after(hint);}}
    finally{button.disabled=false;}
  }));
  const params=new URLSearchParams(location.search);
  if(params.has('auth')&&dialog){open(params.get('auth')==='register'?'register':'login');params.delete('auth');history.replaceState(null,'',location.pathname+(params.size?'?'+params:'')+location.hash);}
})();
