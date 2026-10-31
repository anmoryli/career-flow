(() => {
  const feedback = document.querySelector('#admin-config-feedback');
  if (!feedback) return;
  const show = message => { feedback.textContent = message; };
  document.querySelectorAll('[data-admin-config-form]').forEach(form => {
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (!form.reportValidity()) return;
      const category = form.dataset.adminConfigForm;
      const button = form.querySelector('[type="submit"]'); button.disabled = true;
      const values = Object.fromEntries(new FormData(form));
      const { secret, ...settings } = values;
      const label = ({ mail: '邮件配置', model: '三模型配置', model_routes: '任务模型分配', prompt_diagnosis: '岗位诊断提示词' })[category];
      settings.enabled = form.elements.enabled.checked;
      let submittedSecret = secret || '';
      if (category === 'mail') {
        settings.use_tls = form.elements.use_tls.checked;
        settings.use_ssl = form.elements.use_ssl.checked;
        settings.port = Number(settings.port);
      } else if (category === 'model') {
        settings.models = [1, 2, 3].map(index => ({
          provider: settings[`model_provider_${index}`].trim(),
          model_id: settings[`model_id_${index}`].trim(),
          base_url: settings[`base_url_${index}`].trim()
        }));
        const modelSecrets = [1, 2, 3].map(index => settings[`model_secret_${index}`].trim());
        [1, 2, 3].forEach(index => {
          delete settings[`model_provider_${index}`];
          delete settings[`model_id_${index}`];
          delete settings[`base_url_${index}`];
          delete settings[`model_secret_${index}`];
        });
        settings.tokens_per_credit = null;
        submittedSecret = JSON.stringify(modelSecrets);
      }
      else if (category === 'prompt_diagnosis') { settings.variables = settings.variables.split(',').map(value => value.trim()); }
      else {
        settings.routes = Object.fromEntries(Object.entries(settings)
          .filter(([key, value]) => key.startsWith('route_') && value.trim())
          .map(([key, value]) => [key.slice(6), value.trim()]));
        Object.keys(settings).filter(key => key.startsWith('route_')).forEach(key => delete settings[key]);
      }
      try {
        await window.cfApi(`/admin/api/config/${category}/activate`, {
          label, settings, secret: submittedSecret
        });
        show('配置已保存并立即生效。'); location.reload();
      } catch (error) { show(error.message); button.disabled = false; }
    });
  });
  document.querySelectorAll('[data-admin-config-form]').forEach(form => {
    const toggle = form.elements.enabled;
    const button = form.querySelector('[data-admin-save]');
    const updateLabel = () => { button.textContent = toggle.checked ? '保存并启用' : '保存并停用'; };
    toggle.addEventListener('change', updateLabel);
    updateLabel();
  });
})();
