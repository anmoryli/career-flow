(() => {
  const form = document.querySelector('[data-ui-form="auth"]');
  if (!form) return;
  const feedback = document.querySelector('#auth-feedback');
  const show = message => { feedback.hidden = false; feedback.textContent = message; };
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
      show(result.message);
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
