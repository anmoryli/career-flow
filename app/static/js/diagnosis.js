(() => {
  const root = document.querySelector('[data-diagnostic]');
  const reportList = document.querySelector('[data-report-list]');
  const activeReportCards = [...(reportList?.querySelectorAll('[data-operation-state="queued"],[data-operation-state="running"]') || [])];
  if (activeReportCards.length) {
    const interval = window.setInterval(async () => {
      const states = await Promise.all(activeReportCards.map(async card => {
        try {
          const response = await fetch(`/api/operations/${card.dataset.reportOperation}`, {
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
  const waitForResult = async id => {
    for (let attempt = 0; attempt < 65; attempt++) {
      const response = await fetch(`/api/operations/${id}`, {
        credentials: 'same-origin', redirect: 'error',
      });
      const item = await response.json();
      if (!response.ok) throw new Error(item.error || '读取任务失败');
      if (!['queued', 'running'].includes(item.state)) return item;
      setProgress(item.state === 'queued' ? '已加入处理队列，正在准备分析…' : '正在对照岗位要求与简历证据…');
      await new Promise(resolve => setTimeout(resolve, 1200));
    }
    throw new Error('任务仍在运行，稍后可在本页查看结果。');
  };

  root.querySelectorAll('[data-start-ai]').forEach(button => button.addEventListener('click', async () => {
    const kind = button.dataset.startAi;
    root.querySelectorAll('[data-start-ai]').forEach(item => { item.disabled = true; });
    if (status) status.textContent = '';
    setProgress(kind === 'report' ? '正在准备生成完整岗位报告…' : '正在启动匹配分析…');
    const started = await call(button, `/api/diagnostics/${root.dataset.diagnostic}/start`, {
      kind, request_key: crypto.randomUUID(),
    });
    if (!started) {
      root.querySelectorAll('[data-start-ai]').forEach(item => { item.disabled = false; });
      setProgress(status?.textContent || 'Analysis could not start. Please try again.', false);
      return;
    }
    try {
      const finished = await waitForResult(started.id);
      if (finished.state === 'succeeded') {
        setProgress('分析完成，正在整理结果…');
      } else {
      setProgress(finished.error || '任务未完成，请稍后重试。');
      }
      window.setTimeout(() => window.location.reload(), 450);
    } catch (error) {
      setProgress(error.message, false);
      root.querySelectorAll('[data-start-ai]').forEach(item => { item.disabled = false; });
    }
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
        if (!['queued', 'running'].includes(result.state)) {
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
