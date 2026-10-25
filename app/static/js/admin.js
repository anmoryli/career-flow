(() => {
  const feedback = document.querySelector('#admin-config-feedback');
  if (!feedback) return;
  const show = message => { feedback.textContent = message; };
  document.querySelector('[data-admin-load-models]')?.addEventListener('click', async event => {
    const button = event.currentTarget;
    const select = document.querySelector('[data-admin-model-list]');
    button.disabled = true;
    try {
      const response = await fetch('/admin/api/models', { credentials: 'same-origin', redirect: 'error' });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || '读取模型失败');
      select.replaceChildren(new Option('选择模型 ID', ''));
      result.models.forEach(id => select.add(new Option(id, id)));
      select.hidden = result.models.length === 0;
      if (!result.models.length) show('服务商没有返回可用模型，请手动填写模型 ID。');
      else show(`已读取 ${result.models.length} 个模型。`);
    } catch (error) { show(error.message); }
    finally { button.disabled = false; }
  });
  document.querySelector('[data-admin-model-list]')?.addEventListener('change', event => {
    if (event.target.value) document.querySelector('[data-admin-config-form="model"] [name="model_id"]').value = event.target.value;
  });
  document.querySelectorAll('[data-admin-config-form]').forEach(form => {
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (!form.reportValidity()) return;
      const category = form.dataset.adminConfigForm;
      const button = form.querySelector('[type="submit"]'); button.disabled = true;
      const values = Object.fromEntries(new FormData(form));
      const { label, secret, ...settings } = values;
      settings.enabled = form.elements.enabled.checked;
      if (category === 'mail') {
        settings.use_tls = form.elements.use_tls.checked;
        settings.use_ssl = form.elements.use_ssl.checked;
        settings.port = Number(settings.port);
      } else if (category === 'model') { settings.tokens_per_credit = Number(settings.tokens_per_credit); }
      else if (category === 'prompt_diagnosis') { settings.variables = settings.variables.split(',').map(value => value.trim()); }
      else if (category === 'commerce') {
        Object.entries(settings).forEach(([key, value]) => {
          const match = /^offer_(.+)_(price_yuan|credits)$/.exec(key);
          if (!match) return;
          settings[match[1]] ||= {};
          settings[match[1]][match[2]] = match[2] === 'credits' ? Number(value) : value;
          delete settings[key];
        });
      }
      else {
        settings.routes = Object.fromEntries(Object.entries(settings)
          .filter(([key, value]) => key.startsWith('route_') && value.trim())
          .map(([key, value]) => [key.slice(6), value.trim()]));
        Object.keys(settings).filter(key => key.startsWith('route_')).forEach(key => delete settings[key]);
      }
      try {
        await window.cfApi(`/admin/api/config/${category}/draft`, { label, settings, secret });
        show('草稿已保存，请核对后发布。'); location.reload();
      } catch (error) { show(error.message); button.disabled = false; }
    });
  });
  document.querySelectorAll('[data-admin-publish]').forEach(button => button.addEventListener('click', async () => {
    if (!confirm('发布后，新请求将使用此配置。确认发布？')) return;
    const [category, id] = button.dataset.adminPublish.split(':'); button.disabled = true;
    try { await window.cfApi(`/admin/api/config/${category}/${id}/publish`, { confirm: true }); location.reload(); }
    catch (error) { show(error.message); button.disabled = false; }
  }));
  document.querySelectorAll('[data-admin-rollback]').forEach(button => button.addEventListener('click', async () => {
    if (!confirm('回滚会创建新的发布版本。确认继续？')) return;
    const [category, id] = button.dataset.adminRollback.split(':'); button.disabled = true;
    try { await window.cfApi(`/admin/api/config/${category}/rollback`, { revision_id: Number(id), confirm: true }); location.reload(); }
    catch (error) { show(error.message); button.disabled = false; }
  }));
})();
