/* Single-field AI suggestions stay beside their source and update while streaming. */
(() => {
  const editor = document.querySelector('[data-resume-editor]');
  if (!editor) return;
  const api = window.cfApi;
  const modes = [
    ['optimize', '\u4f18\u5316'], ['expand', '\u6269\u5199'], ['generate', '\u751f\u6210'],
    ['professional', '\u66f4\u4e13\u4e1a'], ['concise', '\u66f4\u51dd\u7ec3'],
  ];
  let running = false;
  let floatingPanel = null;
  const panels = new Map();

  const positionSuggestion = panel => {
    if (!panel || panel.suggestion.hidden) return;
    const bounds = panel.input.getBoundingClientRect();
    const width = Math.min(420, window.innerWidth - 24);
    const left = Math.max(12, Math.min(bounds.left, window.innerWidth - width - 12));
    const height = panel.suggestion.offsetHeight;
    let top = bounds.bottom + 10;
    if (top + height > window.innerHeight - 12) top = bounds.top - height - 10;
    top = Math.max(12, Math.min(top, window.innerHeight - height - 12));
    panel.suggestion.style.left = `${left}px`;
    panel.suggestion.style.top = `${top}px`;
  };

  const showSuggestion = panel => {
    if (floatingPanel && floatingPanel !== panel) floatingPanel.suggestion.hidden = true;
    floatingPanel = panel;
    panel.suggestion.hidden = false;
    positionSuggestion(panel);
  };

  const closeSuggestion = panel => {
    panel.suggestion.hidden = true;
    if (floatingPanel === panel) floatingPanel = null;
  };

  const selectedText = panel => {
    if (!panel.input.dataset.rfField.endsWith('.bullets')) return panel.input.value.trim();
    return panel.input.value.split('\n').map(line => line.trim()).filter(Boolean)[Number(panel.selected || 0)] || '';
  };

  const waitForResult = async (id, panel) => {
    for (let attempt = 0; attempt < 220; attempt++) {
      const response = await fetch(`/api/resume-ai/${id}`, { credentials:'same-origin', redirect:'error' });
      const item = await response.json();
      if (!response.ok) throw new Error(item.error || '\u8bfb\u53d6\u4efb\u52a1\u5931\u8d25');
      if (item.partial) {
        showSuggestion(panel);
        panel.proposed.textContent = item.partial.proposed || '';
        panel.reason.textContent = item.partial.reason || '\u6b63\u5728\u6574\u7406\u5efa\u8bae\u2026';
        panel.status.textContent = '\u6b63\u5728\u751f\u6210\uff0c\u5b8c\u6574\u7ed3\u679c\u5c1a\u672a\u6821\u9a8c\u3002';
        positionSuggestion(panel);
      }
      if (['succeeded','failed','cancelled'].includes(item.state)) return item;
      await new Promise(resolve => setTimeout(resolve, 400));
    }
    throw new Error('\u4efb\u52a1\u7b49\u5f85\u8d85\u65f6\uff0c\u8bf7\u7a0d\u540e\u5237\u65b0\u67e5\u770b\u3002');
  };

  const refreshPanel = panel => {
    const ready = Boolean(editor.dataset.resumeId && Number(editor.dataset.resumeRevision) && editor.dataset.dirty === 'false');
    const hasText = Boolean(selectedText(panel) || panel.input.dataset.rfField === 'summary');
    panel.buttons.forEach(button => {
      button.disabled = !ready || !hasText || running;
      button.textContent = `AI ${button.dataset.modeLabel}`;
    });
    if (!ready) panel.info.textContent = '\u7b80\u5386\u4fdd\u5b58\u540e\u53ef\u4f7f\u7528 AI \u5efa\u8bae\u3002';
    else if (!hasText) panel.info.textContent = '\u8bf7\u5148\u586b\u5199\u8fd9\u4e00\u6761\u771f\u5b9e\u5185\u5bb9\u3002';
    else panel.info.textContent = '\u5efa\u8bae\u4f1a\u5728\u672c\u6a21\u5757\u65c1\u8fb9\u9010\u6bb5\u663e\u793a\u3002';
  };

  const acceptSuggestion = panel => {
    if (!panel.result) return;
    const lines = panel.input.dataset.rfField.endsWith('.bullets')
      ? panel.input.value.split('\n').map(line => line.trim()).filter(Boolean) : null;
    const index = Number(panel.selected || 0);
    const current = lines ? (lines[index] || '') : panel.input.value.trim();
    if (current !== panel.result.original) {
      panel.status.textContent = '\u539f\u6587\u5df2\u6539\u53d8\uff0c\u8bf7\u91cd\u65b0\u751f\u6210\u5efa\u8bae\u3002';
      return;
    }
    if (lines) {
      lines[index] = panel.result.proposed;
      panel.input.value = lines.join('\n');
    } else panel.input.value = panel.result.proposed;
    panel.input.dispatchEvent(new Event('input', { bubbles:true }));
    closeSuggestion(panel);
    panel.result = null;
  };

  const run = async (panel, button) => {
    if (button.disabled || running) return;
    if (editor.dataset.dirty === 'true') {
      panel.info.textContent = '\u8bf7\u5148\u7b49\u5f85\u7b80\u5386\u4fdd\u5b58\u5b8c\u6210\u3002';
      return;
    }
    const lines = panel.input.dataset.rfField.endsWith('.bullets')
      ? panel.input.value.split('\n').map(line => line.trim()).filter(Boolean) : null;
    const index = lines ? Number(panel.selected || 0) : null;
    const path = lines ? panel.input.dataset.rfField.replace(/\.bullets$/, `.bullets.${index}`) : panel.input.dataset.rfField;
    running = true;
    panels.forEach(refreshPanel);
    panel.details.open = true;
    showSuggestion(panel);
    panel.proposed.textContent = '';
    panel.reason.textContent = '';
    panel.status.textContent = '\u6b63\u5728\u8fde\u63a5 AI\u2026';
    panel.original.textContent = selectedText(panel);
    panel.accept.disabled = true;
    panel.reject.hidden = false;
    panel.result = null;
    try {
      const started = await api(`/api/resumes/${editor.dataset.resumeId}/ai/start`, {
        request_key:crypto.randomUUID(), revision:Number(editor.dataset.resumeRevision), path,
        mode:button.dataset.resumeAiMode,
      });
      panel.status.textContent = '\u6b63\u5728\u751f\u6210\uff0c\u5efa\u8bae\u4f1a\u5728\u8fd9\u91cc\u9010\u6bb5\u663e\u793a\u3002';
      const finished = await waitForResult(started.id, panel);
      if (finished.state !== 'succeeded') throw new Error(finished.error || '\u4efb\u52a1\u672a\u5b8c\u6210\uff0c\u672c\u6b21\u672a\u6d88\u8017 AI \u4f18\u5316\u6b21\u6570\u3002');
      panel.result = finished.result;
      panel.proposed.textContent = finished.result.proposed;
      panel.reason.textContent = finished.result.reason;
      panel.status.textContent = '\u5b8c\u6210\uff0c\u6838\u5bf9\u5185\u5bb9\u540e\u53ef\u5e94\u7528\u5efa\u8bae\u3002';
      panel.accept.disabled = false;
    } catch (error) {
      panel.status.textContent = error.message;
    } finally {
      running = false;
      panels.forEach(refreshPanel);
    }
  };

  const setup = input => {
    if (panels.has(input)) return;
    const details = document.createElement('details'); details.className = 'resume-ai-panel';
    const summary = document.createElement('summary'); summary.textContent = '\u9010\u6761 AI \u5efa\u8bae'; details.append(summary);
    const tabs = document.createElement('div'); tabs.className = 'resume-ai-tabs'; details.append(tabs);
    const actions = document.createElement('div'); actions.className = 'resume-ai-actions'; details.append(actions);
    const info = document.createElement('p'); info.className = 'small-text muted'; details.append(info);
    const suggestion = document.createElement('section');
    suggestion.className = 'resume-ai-floating-suggestion';
    suggestion.setAttribute('aria-label', '\u6539\u5199\u5efa\u8bae');
    suggestion.dataset.resumeAiDialog = '';
    suggestion.setAttribute('role', 'dialog');
    suggestion.hidden = true;
    const suggestionHeading = document.createElement('strong'); suggestionHeading.textContent = '\u6539\u5199\u5efa\u8bae'; suggestion.append(suggestionHeading);
    const originalLabel = document.createElement('span'); originalLabel.className = 'resume-ai-inline-label'; originalLabel.textContent = '\u539f\u6587'; suggestion.append(originalLabel);
    const original = document.createElement('p'); original.className = 'resume-ai-inline-original'; original.dataset.resumeAiOriginal = ''; suggestion.append(original);
    const proposedLabel = document.createElement('span'); proposedLabel.className = 'resume-ai-inline-label'; proposedLabel.textContent = '\u5efa\u8bae\u6539\u5199'; suggestion.append(proposedLabel);
    const proposed = document.createElement('p'); proposed.className = 'resume-ai-inline-text'; proposed.dataset.resumeAiProposed = ''; proposed.setAttribute('aria-live', 'polite'); suggestion.append(proposed);
    const reason = document.createElement('p'); reason.className = 'resume-ai-inline-reason'; suggestion.append(reason);
    const status = document.createElement('p'); status.className = 'small-text muted'; status.dataset.resumeAiStatus = ''; status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite'); suggestion.append(status);
    const suggestionActions = document.createElement('div'); suggestionActions.className = 'resume-ai-inline-actions'; suggestion.append(suggestionActions);
    const accept = document.createElement('button'); accept.type = 'button'; accept.className = 'button small'; accept.dataset.resumeAiAccept = ''; accept.textContent = '\u786e\u8ba4\u5e76\u5e94\u7528'; accept.disabled = true;
    const reject = document.createElement('button'); reject.type = 'button'; reject.className = 'button secondary small'; reject.dataset.resumeAiReject = ''; reject.textContent = '\u5173\u95ed';
    suggestionActions.append(accept, reject);
    document.body.append(suggestion);
    const buttons = modes.map(([mode, label]) => {
      const button = document.createElement('button'); button.type = 'button';
      button.className = 'button secondary small'; button.dataset.resumeAiMode = mode;
      button.dataset.modeLabel = label; button.textContent = `AI ${label}`; button.disabled = true;
      button.addEventListener('click', () => run(panel, button));
      actions.append(button); return button;
    });
    const panel = { input, details, tabs, buttons, info, selected:0, suggestion, original, proposed, reason, status, accept, reject, result:null };
    panels.set(input, panel);
    input.closest('label').after(details);
    accept.addEventListener('click', () => acceptSuggestion(panel));
    reject.addEventListener('click', () => closeSuggestion(panel));
    const updateTabs = () => {
      tabs.replaceChildren();
      if (!input.dataset.rfField.endsWith('.bullets')) { tabs.hidden = true; return; }
      const lines = input.value.split('\n').map(line => line.trim()).filter(Boolean);
      tabs.hidden = false;
      if (panel.selected >= lines.length) panel.selected = Math.max(0, lines.length - 1);
      lines.forEach((_, index) => {
        const tab = document.createElement('button'); tab.type = 'button';
        tab.textContent = `\u7b2c ${index + 1} \u6761`; tab.setAttribute('aria-pressed', String(index === panel.selected));
        tab.addEventListener('click', () => { panel.selected = index; updateTabs(); refreshPanel(panel); });
        tabs.append(tab);
      });
    };
    details.addEventListener('toggle', () => { if (details.open) { updateTabs(); refreshPanel(panel); } });
    input.addEventListener('input', () => { if (details.open) { updateTabs(); refreshPanel(panel); } });
    refreshPanel(panel);
  };

  const scan = () => editor.querySelectorAll(
    '[data-rf-field="summary"],[data-rf-field$=".bullets"],[data-rf-field$=".description"],[data-rf-field$=".detail"],[data-rf-field^="custom_sections."][data-rf-field$=".content"]'
  ).forEach(setup);
  scan();
  editor.addEventListener('cf:refresh', scan);
  editor.addEventListener('cf:dirty', () => panels.forEach(refreshPanel));
  editor.addEventListener('cf:saved', () => panels.forEach(refreshPanel));
  window.addEventListener('resize', () => positionSuggestion(floatingPanel));
  window.addEventListener('scroll', () => positionSuggestion(floatingPanel), true);
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && floatingPanel) closeSuggestion(floatingPanel);
  });
})();
