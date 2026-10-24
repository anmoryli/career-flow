(() => {
  const root = document.querySelector('[data-diagnostic]');
  if (!root) return;
  const status = document.querySelector('#diagnosis-feedback');
  let quoted = null;
  const keys = {};
  const call = async (button, url, data) => {
    button.disabled = true;
    try { return await window.cfApi(url, data); }
    catch (error) { status.textContent = error.message; return null; }
    finally { button.disabled = false; }
  };
  root.querySelectorAll('[data-quote]').forEach(button => button.addEventListener('click', async () => {
    const kind = button.dataset.quote;
    keys[kind] ||= crypto.randomUUID();
    const result = await call(button, `/api/diagnostics/${root.dataset.diagnostic}/quote`, { kind, request_key: keys[kind] });
    if (!result) return;
    delete keys[kind];
    quoted = result.id;
    document.querySelector('#fee-confirmation').hidden = false;
    document.querySelector('#fee-description').textContent = `本次最多冻结 ${result.ceiling} 积分，按实际 Token 结算并释放剩余；失败重试一次，仍失败全额释放。预估十分钟内有效。`;
  }));
  root.querySelector('[data-dismiss-quote]')?.addEventListener('click', () => {
    quoted = null; document.querySelector('#fee-confirmation').hidden = true;
  });
  root.querySelector('[data-confirm-operation]')?.addEventListener('click', async event => {
    if (!quoted) return;
    if (await call(event.target, `/api/operations/${quoted}/confirm`, {})) location.reload();
  });
  root.querySelectorAll('[data-cancel-operation]').forEach(button => button.addEventListener('click', async () => {
    if (!window.confirm('取消本次任务并释放冻结积分？')) return;
    if (await call(button, `/api/operations/${button.dataset.cancelOperation}/cancel`, {})) location.reload();
  }));
  let answerKey = crypto.randomUUID();
  document.querySelector('#diagnostic-answer')?.addEventListener('input', () => { answerKey = crypto.randomUUID(); });
  root.querySelectorAll('[data-answer]').forEach(button => button.addEventListener('click', async () => {
    if (await call(button, `/api/diagnostics/${root.dataset.diagnostic}/answer`, {
      request_key: answerKey, revision: Number(root.dataset.revision),
      skipped: button.dataset.answer === 'skip', answer: document.querySelector('#diagnostic-answer').value,
    })) location.reload();
  }));
  root.querySelectorAll('[data-apply-suggestions]').forEach(form => {
    let key = crypto.randomUUID();
    form.addEventListener('input', () => { key = crypto.randomUUID(); });
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const indices = Array.from(form.querySelectorAll('[name="suggestion"]:checked'), input => Number(input.value));
      if (!indices.length) { status.textContent = '请至少选择一条建议'; return; }
      const result = await call(form.querySelector('button'), `/api/operations/${form.dataset.applySuggestions}/apply`, {
        request_key: key, indices, confirmed: 'yes', title: form.elements.title.value,
        edits: Object.fromEntries(indices.map(index => [index, form.elements[`edit-${index}`].value])),
      });
      if (result) location.href = `/workspace?view=resume-new&resume_id=${result.id}`;
    });
  });
  const running = root.querySelector('[data-operation-state="queued"],[data-operation-state="running"]');
  if (running) {
    const interval = setInterval(async () => {
      try {
        const response = await fetch(`/api/operations/${running.dataset.operation}`, { redirect: 'error' });
        if (!response.ok) throw new Error('读取任务失败，请稍后刷新');
        const result = await response.json();
        if (!['queued', 'running'].includes(result.state)) { clearInterval(interval); location.reload(); }
      } catch (error) { clearInterval(interval); status.textContent = error.message; }
    }, 2500);
  }
})();
