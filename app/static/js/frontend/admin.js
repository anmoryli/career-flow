/* Service configuration forms use the same protected activation endpoints. */
(() => {
  const feedback=document.querySelector('#admin-config-feedback');
  if(!feedback)return;
  const labels={mail:'邮件配置',model:'三模型配置',model_routes:'任务模型分配',prompt_diagnosis:'岗位诊断提示词'};
  const encode=form=>{
    const category=form.dataset.adminConfigForm;
    const values=Object.fromEntries(new FormData(form));
    const {secret,...settings}=values;let submittedSecret=secret||'';
    settings.enabled=Boolean(form.elements.enabled?.checked);
    if(category==='mail'){
      settings.use_tls=Boolean(form.elements.use_tls.checked);settings.use_ssl=Boolean(form.elements.use_ssl.checked);settings.port=Number(settings.port);
    }else if(category==='model'){
      settings.models=[1,2,3].map(index=>({provider:String(settings[`model_provider_${index}`]||'').trim(),model_id:String(settings[`model_id_${index}`]||'').trim(),base_url:String(settings[`base_url_${index}`]||'').trim()}));
      submittedSecret=JSON.stringify([1,2,3].map(index=>String(settings[`model_secret_${index}`]||'').trim()));
      [1,2,3].forEach(index=>['model_provider_','model_id_','base_url_','model_secret_'].forEach(prefix=>delete settings[prefix+index]));settings.tokens_per_credit=null;
    }else if(category==='prompt_diagnosis')settings.variables=String(settings.variables||'').split(',').map(value=>value.trim());
    else {
      settings.routes=Object.fromEntries(Object.entries(settings).filter(([key,value])=>key.startsWith('route_')&&String(value).trim()).map(([key,value])=>[key.slice(6),String(value).trim()]));
      Object.keys(settings).filter(key=>key.startsWith('route_')).forEach(key=>delete settings[key]);
    }
    return {label:labels[category],settings,secret:submittedSecret};
  };
  document.querySelectorAll('[data-admin-config-form]').forEach(form=>{
    form.dataset.uiForm='admin';
    const button=form.querySelector('[type=submit]');
    const update=()=>{if(button)button.textContent=form.elements.enabled.checked?'保存并启用':'保存并停用';};
    form.elements.enabled?.addEventListener('change',update);update();
    form.addEventListener('submit',async event=>{
      event.preventDefault();if(!form.reportValidity())return;button.disabled=true;feedback.textContent='正在保存配置…';
      try{await window.cfApi(`/admin/api/config/${form.dataset.adminConfigForm}/activate`,encode(form));feedback.textContent='配置已保存并立即生效。';location.reload();}
      catch(error){feedback.textContent=error.message;button.disabled=false;}
    });
  });
  document.querySelectorAll('[data-admin-section-tab]').forEach(button=>button.addEventListener('click',()=>{
    document.querySelectorAll('[data-admin-section-tab]').forEach(other=>other.setAttribute('aria-pressed',String(other===button)));
    document.querySelectorAll('[data-admin-section]').forEach(section=>{section.hidden=section.dataset.adminSection!==button.dataset.adminSectionTab;});
  }));
})();
