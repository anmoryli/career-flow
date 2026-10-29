(() => {
  const form = document.querySelector('[data-review-workbench]');
  if (!form) return;
  const rows = [...form.querySelectorAll('[data-review-path]')];
  const feedback = document.querySelector('#diagnosis-feedback');
  const toggleAll = form.querySelector('[data-review-select-all]');
  const count = form.querySelector('[data-review-count]');
  let requestKey = crypto.randomUUID();
  let running = false;
  const original = row => row.querySelector('[data-review-original]').textContent;
  const text = row => row.querySelector('[data-review-text]');
  const check = row => row.querySelector('[name="suggestion"]');
  const changed = row => text(row).value.trim() !== original(row).trim();
  const update = () => {
    const selected = rows.filter(row => check(row).checked);
    const changes = rows.filter(changed);
    count.textContent = `已选 ${selected.length} 段`;
    toggleAll.checked = changes.length > 0 && changes.every(row => check(row).checked);
    toggleAll.indeterminate = selected.length > 0 && !toggleAll.checked;
  };
  const busy = value => {
    running = value;
    form.querySelectorAll('[data-review-rewrite],button[type="submit"]').forEach(button => { button.disabled = value; });
  };
  const rowStatus = (row, message) => {
    const status = row.querySelector('[data-review-status]');
    status.hidden = !message;
    status.textContent = message;
  };
  toggleAll.addEventListener('change', () => {
    rows.forEach(row => { check(row).checked = toggleAll.checked && changed(row); });
    requestKey = crypto.randomUUID();
    update();
  });
  form.addEventListener('input', () => { requestKey = crypto.randomUUID(); });
  rows.forEach(row => {
    text(row).addEventListener('input', () => { check(row).checked = changed(row); update(); });
    check(row).addEventListener('change', update);
    const candidate = row.querySelector('[data-review-candidate]');
    row.querySelector('[data-review-reset]').addEventListener('click', () => {
      text(row).value = original(row); check(row).checked = false; candidate.hidden = true;
      requestKey = crypto.randomUUID(); update();
    });
    row.querySelector('[data-review-dismiss]').addEventListener('click', () => { candidate.hidden = true; });
    row.querySelector('[data-review-adopt]').addEventListener('click', () => {
      text(row).value = row.querySelector('[data-review-candidate-text]').textContent;
      check(row).checked = changed(row); candidate.hidden = true;
      requestKey = crypto.randomUUID(); update();
    });
    row.querySelector('[data-review-rewrite]').addEventListener('click', async () => {
      if (running) return;
      busy(true); candidate.hidden = true;
      rowStatus(row, '正在改写这一段…');
      try {
        const operation = await window.cfApi(`/api/resumes/${form.dataset.resumeId}/ai/start`, {
          request_key: crypto.randomUUID(), revision: Number(form.dataset.resumeRevision),
          path: row.dataset.reviewPath, mode: 'professional',
        });
        const deadline = Date.now() + 180000;
        while (Date.now() < deadline) {
          const response = await fetch(`/api/resume-ai/${operation.id}`, { credentials: 'same-origin', redirect: 'error' });
          const result = await response.json();
          if (!response.ok) throw new Error(result.error || '无法读取改写结果，请重试。');
          if (result.state === 'succeeded') {
            const proposed = result.result?.proposed;
            if (!proposed || result.result.original !== original(row)) throw new Error('原文版本已变化，请打开完整编辑器核对。');
            if (proposed.length > text(row).maxLength) throw new Error('新稿超过此字段长度，请在完整编辑器中精简。');
            row.querySelector('[data-review-candidate-text]').textContent = proposed;
            row.querySelector('[data-review-candidate-reason]').textContent = result.result.reason || '';
            candidate.hidden = false; rowStatus(row, '改写已完成，采用前可与当前内容比较。');
            return;
          }
          if (['failed', 'cancelled'].includes(result.state)) throw new Error(result.error || '这次改写未完成，请重试。');
          await new Promise(resolve => setTimeout(resolve, 700));
        }
        throw new Error('改写仍在处理中，请到历史记录查看结果。');
      } catch (error) { rowStatus(row, error.message); }
      finally { busy(false); }
    });
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (running) return;
    const selected = rows.filter(row => check(row).checked);
    if (!selected.length) { feedback.textContent = '请选择要保存的段落。'; return; }
    if (selected.length > 30) { feedback.textContent = '一次最多保存 30 段，请减少选择后再保存。'; return; }
    if (!form.elements.confirmed.checked) { form.elements.confirmed.focus(); return; }
    busy(true); feedback.textContent = '';
    try {
      const result = await window.cfApi(`/api/operations/${form.dataset.applySuggestions}/apply`, {
        request_key: requestKey, confirmed: 'yes', title: form.elements.title.value,
        paragraph_edits: Object.fromEntries(selected.map(row => [row.dataset.reviewPath, text(row).value])),
      });
      location.href = `/workspace?view=resume-new&resume_id=${result.id}`;
    } catch (error) { feedback.textContent = error.message; }
    finally { busy(false); }
  });
  update();
})();
