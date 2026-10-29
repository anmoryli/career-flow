(() => {
  const root = document.querySelector('[data-diagnostic]');
  const reportList = document.querySelector('[data-report-list]');
  const activeOperationCards = [
    ...(reportList?.querySelectorAll('[data-operation-state="queued"],[data-operation-state="running"]') || []),
    ...document.querySelectorAll('[data-active-operation]'),
  ];
  if (activeOperationCards.length) {
    const interval = window.setInterval(async () => {
      const states = await Promise.all(activeOperationCards.map(async card => {
        const operationId = card.dataset.reportOperation || card.dataset.activeOperation;
        try {
          const response = await fetch(`/api/operations/${operationId}`, {
            credentials: 'same-origin', redirect: 'error',
          });
          if (!response.ok) return 'running';
          return (await response.json()).state;
        } catch { return 'running'; }
      }));
      if (states.some(state => !['queued', 'running'].includes(state))) {
        window.clearInterval(interval);
        window.location.reload();
      }
    }, 2500);
  }
  if (!root) return;
  const status = document.querySelector('#diagnosis-feedback');
  const progress = root.querySelector('[data-start-status]');
  const call = async (button, url, data) => {
    if (button) {
      button.disabled = true;
      button.setAttribute('aria-busy', 'true');
    }
    try { return await window.cfApi(url, data); }
    catch (error) {
      if (status) status.textContent = error.message;
      return null;
    } finally {
      if (button) {
        button.disabled = false;
        button.removeAttribute('aria-busy');
      }
    }
  };
  const setProgress = (message, active = true) => {
    if (!progress) return;
    progress.hidden = false;
    progress.textContent = message;
    progress.dataset.active = String(active);
    root.querySelector('.diagnosis-start-panel')?.classList.toggle('is-analysis-starting', active);
  };
  root.querySelectorAll('[data-start-ai]').forEach(button => button.addEventListener('click', async () => {
    const kind = button.dataset.startAi;
    const startPanel = root.querySelector('.diagnosis-start-panel');
    const animationTemplate = root.querySelector('#diagnosis-running-template');
    const animation = animationTemplate?.content.firstElementChild.cloneNode(true);
    root.querySelectorAll('[data-start-ai]').forEach(item => { item.disabled = true; });
    if (status) status.textContent = '';
    if (startPanel && animation) {
      startPanel.hidden = true;
      startPanel.after(animation);
    } else {
      setProgress('Preparing the analysis?');
    }
    const started = await call(button, `/api/diagnostics/${root.dataset.diagnostic}/start`, {
      kind, request_key: crypto.randomUUID(),
    });
    if (!started) {
      animation?.remove();
      if (startPanel) startPanel.hidden = false;
      root.querySelectorAll('[data-start-ai]').forEach(item => { item.disabled = false; });
      return;
    }
    window.location.reload();
  }));

  root.querySelectorAll('[data-cancel-operation]').forEach(button => button.addEventListener('click', async () => {
    if (!window.confirm('取消本次任务？')) return;
    if (await call(button, `/api/operations/${button.dataset.cancelOperation}/cancel`, {})) {
      window.location.reload();
    }
  }));

  let answerKey = crypto.randomUUID();
  const answerField = document.querySelector('#diagnostic-answer');
  answerField?.addEventListener('input', () => { answerKey = crypto.randomUUID(); });
  answerField?.addEventListener('keydown', event => {
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
      root.querySelector('[data-answer="answer"]')?.click();
    }
  });
  root.querySelectorAll('[data-answer]').forEach(button => button.addEventListener('click', async () => {
    const skipped = button.dataset.answer === 'skip';
    if (!skipped && !answerField.value.trim()) {
      answerField.focus();
      answerField.setCustomValidity('请补充实际经历，或选择跳过本题。');
      answerField.reportValidity();
      return;
    }
    answerField?.setCustomValidity('');
    const result = await call(button, `/api/diagnostics/${root.dataset.diagnostic}/answer`, {
      request_key: answerKey,
      revision: Number(root.dataset.revision),
      skipped,
      answer: answerField?.value || '',
    });
    if (result) window.location.reload();
  }));

  root.querySelectorAll('[data-apply-suggestions]').forEach(form => {
    if (form.matches('[data-review-workbench]')) return;
    let key = crypto.randomUUID();
    form.addEventListener('input', () => { key = crypto.randomUUID(); });
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const indices = Array.from(
        form.querySelectorAll('[name="suggestion"]:checked'),
        input => Number(input.value),
      );
      if (!indices.length) {
        if (status) status.textContent = '先勾选至少一条要采纳的建议。';
        return;
      }
      if (!form.elements.confirmed.checked) {
        form.elements.confirmed.focus();
        if (status) status.textContent = '请先确认所选内容符合你的真实经历。';
        return;
      }
      const submit = form.querySelector('button[type="submit"]');
      const result = await call(submit, `/api/operations/${form.dataset.applySuggestions}/apply`, {
        request_key: key,
        indices,
        confirmed: 'yes',
        title: form.elements.title.value,
        edits: Object.fromEntries(indices.map(index => [index, form.elements[`edit-${index}`].value])),
      });
      if (result) window.location.href = `/workspace?view=resume-new&resume_id=${result.id}`;
    });
  });

  if (new URLSearchParams(location.search).get('start') === 'analysis') {
    history.replaceState(null, '', location.pathname);
    window.setTimeout(() => root.querySelector('[data-start-ai="analysis"]')?.click(), 120);
  }

  const running = root.querySelector('[data-operation-state="queued"],[data-operation-state="running"]');
  if (running) {
    const interval = window.setInterval(async () => {
      try {
        const response = await fetch(`/api/operations/${running.dataset.operation}`, {
          credentials: 'same-origin', redirect: 'error',
        });
        if (!response.ok) throw new Error('读取任务失败，请稍后刷新');
        const result = await response.json();
        if (result.state !== running.dataset.operationState) {
          window.clearInterval(interval);
          window.location.reload();
        }
      } catch (error) {
        window.clearInterval(interval);
        if (status) status.textContent = error.message;
      }
    }, 2500);
  }
})();
