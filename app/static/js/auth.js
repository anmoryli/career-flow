(() => {
  const dialog = document.querySelector('#auth-dialog');
  if (dialog) {
    let continuation = null;
    const forms = [...dialog.querySelectorAll('[data-auth-modal-form]')];
    const setMode = mode => {
      forms.forEach(form => { form.hidden = form.dataset.authModalForm !== mode; });
      dialog.querySelector('#auth-dialog-title').textContent = mode === 'register' ? '创建账号' : '登录后继续';
      dialog.querySelector('[data-auth-description]').textContent = mode === 'register'
        ? '创建账号后，刚才填写的内容会继续保存。'
        : '保存简历和开始岗位分析时，需要先登录账号。';
    };
    const open = (mode = 'login', resume = null) => {
      continuation = resume;
      setMode(mode);
      dialog.showModal();
      dialog.querySelector(`[data-auth-modal-form="${mode}"] input`)?.focus();
    };
    window.cfRequireAuth = resume => open('login', resume);
    document.addEventListener('click', event => {
      const modeLink = event.target.closest('[data-auth-mode]');
      if (modeLink) { event.preventDefault(); setMode(modeLink.dataset.authMode); return; }
      const link = event.target.closest('a[href]');
      if (link && !document.body.dataset.authenticated?.includes('yes')) {
        const url = new URL(link.href, location.href);
        if (url.origin === location.origin && ['/login', '/register'].includes(url.pathname)) {
          event.preventDefault(); open(url.pathname === '/register' ? 'register' : 'login');
        }
      }
      if (event.target.closest('[data-auth-close]')) dialog.close();
    });
    dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
    dialog.querySelector('[data-auth-send-code]')?.addEventListener('click', async event => {
      const form = event.currentTarget.closest('form');
      const email = form.elements.email;
      if (!email.reportValidity()) return;
      const button = event.currentTarget;
      button.disabled = true;
      try {
        const response = await fetch('/auth/code', { method: 'POST', headers: {
          'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content,
        }, body: JSON.stringify({ email: email.value }) });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || '验证码发送失败');
        const original = button.textContent;
        let remaining = result.retry_after || 60;
        button.textContent = `${remaining} 秒后重发`;
        const timer = setInterval(() => { remaining--; button.textContent = `${remaining} 秒后重发`; if (remaining <= 0) { clearInterval(timer); button.disabled = false; button.textContent = original; } }, 1000);
      } catch (error) { form.querySelector('[data-auth-feedback]').hidden = false; form.querySelector('[data-auth-feedback]').textContent = error.message; button.disabled = false; }
    });
    forms.forEach(form => form.addEventListener('submit', async event => {
      event.preventDefault();
      const button = form.querySelector('[type="submit"]');
      const feedback = form.querySelector('[data-auth-feedback]');
      const data = Object.fromEntries(new FormData(form));
      data.next = new URLSearchParams(location.search).get('next') || `${location.pathname}${location.search}`;
      button.disabled = true; feedback.hidden = true;
      try {
        const mode = form.dataset.authModalForm;
        const response = await fetch(mode === 'register' ? '/register' : '/login', { method: 'POST', credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content },
          body: JSON.stringify(data) });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || '登录失败，请检查邮箱和密码');
        dialog.close();
        document.body.dataset.authenticated = 'yes';
        if (continuation) await continuation();
        else location.assign(result.next || `${location.pathname}${location.search}`);
      } catch (error) { feedback.hidden = false; feedback.textContent = error.message; }
      finally { button.disabled = false; }
    }));
    const params = new URLSearchParams(location.search);
    if (params.has('auth')) {
      open(params.get('auth') === 'register' ? 'register' : 'login');
      params.delete('auth');
      const clean = `${location.pathname}${params.size ? `?${params}` : ''}${location.hash}`;
      history.replaceState(null, '', clean);
    }
  }
})();

(() => {
  const form = document.querySelector('[data-ui-form="auth"]');
  if (!form) return;
  const feedback = document.querySelector('#auth-feedback');
  const show = (message, tone = 'error') => { feedback.hidden = false; feedback.dataset.tone = tone; feedback.textContent = message; };
  document.querySelector('[data-password-toggle]')?.addEventListener('click', event => {
    const input = document.querySelector('#password');
    input.type = input.type === 'password' ? 'text' : 'password';
    event.target.textContent = input.type === 'password' ? '显示密码' : '隐藏密码';
    event.target.setAttribute('aria-pressed', String(input.type === 'text'));
  });
  document.querySelector('[data-send-code]')?.addEventListener('click', async event => {
    const email = form.elements.email;
    if (!email.reportValidity()) return;
    const button = event.target; button.disabled = true;
    try {
      const result = await window.cfApi('/auth/code', { email: email.value });
      show(result.message, 'info');
      let remaining = result.retry_after;
      button.textContent = `${remaining} 秒后重发`;
      const timer = setInterval(() => {
        remaining--; button.textContent = `${remaining} 秒后重发`;
        if (remaining <= 0) { clearInterval(timer); button.disabled = false; button.textContent = '重新发送验证码'; }
      }, 1000);
    } catch (error) { show(error.message); button.disabled = false; }
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const button = form.querySelector('[type="submit"]'); button.disabled = true;
    const data = Object.fromEntries(new FormData(form)); delete data.csrf_token;
    try {
      const response = await fetch(location.pathname, { method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': form.elements.csrf_token.value },
        body: JSON.stringify(data), credentials: 'same-origin' });
      if (response.ok && response.redirected) { location.href = response.url; return; }
      const result = await response.json(); show(result.error || '提交失败，请检查填写内容');
      form.querySelectorAll('[data-field-error]').forEach(node => node.remove());
      form.querySelectorAll('[aria-invalid]').forEach(node => node.removeAttribute('aria-invalid'));
      Object.entries(result.fields || {}).forEach(([name, message]) => {
        const input = form.elements[name]; if (!input) return;
        const error = document.createElement('small'); error.dataset.fieldError = name;
        error.id = `error-${name}`; error.textContent = message; input.after(error);
        input.setAttribute('aria-invalid', 'true'); input.setAttribute('aria-describedby', error.id);
      });
    } catch (_) { show('连接失败，填写内容已保留，请重试。'); }
    finally { button.disabled = false; }
  });
})();
