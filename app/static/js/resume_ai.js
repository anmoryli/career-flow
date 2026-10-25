/* Paid resume suggestions stay separate from the original until the user accepts one. */
(() => {
  const editor = document.querySelector('[data-resume-editor]');
  const dialog = document.querySelector('[data-resume-ai-dialog]');
  if (!editor || !dialog) return;
  const api = window.cfApi;
  const modes = [
    ['optimize', 'AI 优化'], ['expand', 'AI 扩写'], ['generate', 'AI 生成'],
    ['professional', '更专业'], ['concise', '更凝练'],
  ];
  const status = dialog.querySelector('[data-resume-ai-status]');
  const comparison = dialog.querySelector('[data-resume-ai-comparison]');
  const accept = dialog.querySelector('[data-resume-ai-accept]');
  const reject = dialog.querySelector('[data-resume-ai-reject]');
  let active = null;
  let running = false;
  dialog.addEventListener('cancel', event => { if (running) event.preventDefault(); });
  reject.addEventListener('click', () => { if (!running) dialog.close(); });
  accept.addEventListener('click', () => {
    if (!active) return;
    const { input, index, result } = active;
    const lines = input.dataset.rfField.endsWith('.bullets')
      ? input.value.split('\n').map(line => line.trim()).filter(Boolean) : null;
    const current = lines ? lines[index] : input.value.trim();
    if (current !== result.original) {
      status.textContent = '原文已改变，请重新生成建议。'; return;
    }
    if (lines) { lines[index] = result.proposed; input.value = lines.join('\n'); }
    else input.value = result.proposed;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    dialog.close(); active = null;
  });
  const quoteCache = new Map();
  const waitForResult = async id => {
    for (let attempt = 0; attempt < 65; attempt++) {
      const response = await fetch(`/api/resume-ai/${id}`, { credentials: 'same-origin' });
      const item = await response.json();
      if (!response.ok) throw new Error(item.error || '读取任务失败');
      if (['succeeded', 'failed', 'cancelled'].includes(item.state)) return item;
      await new Promise(resolve => setTimeout(resolve, 2000));
    }
    throw new Error('任务等待超时，请稍后刷新页面查看结果。');
  };
  const showResult = async (button, input, index, item) => {
    button.disabled = true; running = true;
    comparison.hidden = true; accept.hidden = true;
    status.textContent = `已确认最多冻结 ${item.ceiling} 积分，正在生成建议…`;
    dialog.showModal();
    try {
      const started = await api(`/api/resume-ai/${item.id}/confirm`, {});
      const finished = await waitForResult(started.id);
      if (finished.state !== 'succeeded') throw new Error(finished.error || '任务未完成，积分已释放。');
      active = { input, index, result: finished.result };
      dialog.querySelector('[data-resume-ai-original]').textContent = finished.result.original || '（原文为空）';
      dialog.querySelector('[data-resume-ai-proposed]').textContent = finished.result.proposed;
      dialog.querySelector('[data-resume-ai-reason]').textContent = finished.result.reason;
      comparison.hidden = false; accept.hidden = false;
      status.textContent = `生成完成，实际消费 ${finished.charged} 积分。请核对真实信息后决定是否替换。`;
    } catch (error) {
      status.textContent = error.message;
      if (error.message.includes('过期')) {
        quoteCache.clear();
        const panel = panels.get(input);
        if (panel?.details.open) refreshQuotes(panel);
      }
    }
    finally { running = false; button.disabled = false; }
  };
  const panels = new Map();
  const refreshQuotes = async panel => {
    const { input, buttons, info } = panel;
    buttons.forEach(button => { button.disabled = true; button.textContent = `${button.dataset.modeLabel} · 预估中`; });
    const id = editor.dataset.resumeId, revision = Number(editor.dataset.resumeRevision);
    if (!id || !revision || editor.dataset.dirty === 'true') {
      info.textContent = '请等待简历保存后使用 AI。'; return;
    }
    const lines = input.dataset.rfField.endsWith('.bullets')
      ? input.value.split('\n').map(line => line.trim()).filter(Boolean) : null;
    const index = Number(panel.selected || 0);
    if (lines && !lines[index]) { info.textContent = '请先填写一条真实工作内容。'; return; }
    const path = lines ? input.dataset.rfField.replace(/\.bullets$/, `.bullets.${index}`) : input.dataset.rfField;
    info.textContent = '正在获取积分预估…';
    await Promise.all(buttons.map(async button => {
      const mode = button.dataset.resumeAiMode;
      const cacheKey = `${revision}:${path}:${mode}`;
      try {
        let item = quoteCache.get(cacheKey);
        if (item?.expires_at && Date.parse(item.expires_at) <= Date.now() + 5000) {
          quoteCache.delete(cacheKey); item = null;
        }
        if (!item) {
          item = await api(`/api/resumes/${id}/ai/quote`, {
            request_key: crypto.randomUUID(), revision, path, mode,
          });
          quoteCache.set(cacheKey, item);
        }
        if (panel.selected !== index || Number(editor.dataset.resumeRevision) !== revision) return;
        button.textContent = `${button.dataset.modeLabel} · 预估 ${item.ceiling} 积分`;
        button.disabled = false;
        button.onclick = () => showResult(button, input, lines ? index : null, item);
        info.textContent = '点击按钮即确认所示预估积分；失败后释放冻结积分。';
      } catch (error) { info.textContent = error.message; button.textContent = button.dataset.modeLabel; }
    }));
  };
  const setup = input => {
    if (panels.has(input)) return;
    const details = document.createElement('details'); details.className = 'resume-ai-panel';
    const summary = document.createElement('summary'); summary.textContent = '逐条 AI 建议'; details.append(summary);
    const tabs = document.createElement('div'); tabs.className = 'resume-ai-tabs'; details.append(tabs);
    const actions = document.createElement('div'); actions.className = 'resume-ai-actions'; details.append(actions);
    const info = document.createElement('p'); info.className = 'small-text muted'; details.append(info);
    const buttons = modes.map(([mode, label]) => {
      const button = document.createElement('button'); button.type = 'button';
      button.className = 'button secondary small'; button.dataset.resumeAiMode = mode;
      button.dataset.modeLabel = label; button.textContent = `${label} · 预估中`; button.disabled = true;
      actions.append(button); return button;
    });
    const panel = { input, details, tabs, buttons, info, selected: 0 };
    panels.set(input, panel);
    input.closest('label').after(details);
    const updateTabs = () => {
      tabs.replaceChildren();
      if (!input.dataset.rfField.endsWith('.bullets')) { tabs.hidden = true; return; }
      const lines = input.value.split('\n').map(line => line.trim()).filter(Boolean);
      tabs.hidden = false;
      lines.forEach((_, index) => {
        const tab = document.createElement('button'); tab.type = 'button';
        tab.textContent = `第 ${index + 1} 条`; tab.setAttribute('aria-pressed', String(index === panel.selected));
        tab.addEventListener('click', () => { panel.selected = index; updateTabs(); refreshQuotes(panel); });
        tabs.append(tab);
      });
    };
    details.addEventListener('toggle', () => { if (details.open) { updateTabs(); refreshQuotes(panel); } });
    input.addEventListener('input', () => { if (details.open) { updateTabs(); buttons.forEach(button => { button.disabled = true; }); } });
  };
  const scan = () => editor.querySelectorAll(
    '[data-rf-field="summary"],[data-rf-field$=".bullets"],[data-rf-field$=".description"],[data-rf-field$=".detail"]'
  ).forEach(setup);
  scan();
  editor.addEventListener('cf:refresh', scan);
  editor.addEventListener('cf:dirty', () => {
    quoteCache.clear();
    panels.forEach(panel => panel.buttons.forEach(button => { button.disabled = true; }));
  });
  editor.addEventListener('cf:saved', () => panels.forEach(panel => {
    if (panel.details.open) refreshQuotes(panel);
  }));
})();
