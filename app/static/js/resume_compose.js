/* Pasted source starts AI drafting in one step; users review before applying it. */
(() => {
  const editor = document.querySelector('[data-resume-editor]');
  const button = document.querySelector('[data-compose-resume]');
  const dialog = document.querySelector('[data-resume-compose-dialog]');
  if (!editor || !button || !dialog) return;
  const source = document.querySelector('#resume-source-text');
  const imported = sessionStorage.getItem('cf-import-source');
  if (imported) { source.value = imported; source.closest('details').open = true; sessionStorage.removeItem('cf-import-source'); }
  const feedback = document.querySelector('#resume-source-feedback');
  const status = dialog.querySelector('[data-compose-status]');
  const accept = dialog.querySelector('[data-compose-accept]');
  const review = dialog.querySelector('[data-compose-review]');
  let proposed = null, running = false;
  const ensureSaved = async () => {
    if (editor.dataset.dirty === 'false' && editor.dataset.resumeId) return;
    const saved = new Promise((resolve, reject) => {
      const timeout = setTimeout(() => { editor.removeEventListener('cf:saved', onSaved); reject(new Error('\u4fdd\u5b58\u7b80\u5386\u8d85\u65f6\uff0c\u8bf7\u91cd\u8bd5\u3002')); }, 12000);
      const onSaved = () => { clearTimeout(timeout); resolve(); };
      editor.addEventListener('cf:saved', onSaved, { once:true });
    });
    document.querySelector('[data-save-resume]').click();
    await saved;
    if (!editor.dataset.resumeId || editor.dataset.dirty !== 'false') throw new Error('\u8bf7\u7b49\u5f85\u7b80\u5386\u4fdd\u5b58\u5b8c\u6210\u3002');
  };
  const waitForResult = async id => {
    for (let attempt = 0; attempt < 65; attempt++) {
      const response = await fetch(`/api/resume-ai/${id}`, { credentials:'same-origin', redirect:'error' });
      const item = await response.json();
      if (!response.ok) throw new Error(item.error || '\u8bfb\u53d6\u4efb\u52a1\u5931\u8d25');
      if (['succeeded','failed','cancelled'].includes(item.state)) return item;
      await new Promise(resolve => setTimeout(resolve, 1200));
    }
    throw new Error('\u4efb\u52a1\u4ecd\u5728\u8fd0\u884c\uff0c\u8bf7\u7a0d\u540e\u5237\u65b0\u3002');
  };
  dialog.addEventListener('cancel', event => { if (running) event.preventDefault(); });
  dialog.querySelector('[data-compose-reject]').addEventListener('click', () => { if (!running) dialog.close(); });
  button.addEventListener('click', async () => {
    if (source.value.trim().length < 20) { feedback.textContent = '\u8bf7\u81f3\u5c11\u7c98\u8d34 20 \u5b57\u771f\u5b9e\u7ecf\u5386\u3002'; return; }
    button.disabled = true; feedback.textContent = '';
    running = true; review.hidden = true; accept.hidden = true;
    document.querySelector('[data-studio-dialog="source"]')?.close();
    status.textContent = '正在准备 AI 草稿…'; dialog.showModal();
    try {
      await ensureSaved();
      const started = await window.cfApi(`/api/resumes/${editor.dataset.resumeId}/ai/compose/start`, {
        request_key:crypto.randomUUID(), revision:Number(editor.dataset.resumeRevision), source:source.value.trim(),
      });
      status.textContent = '\u6b63\u5728\u6574\u7406\uff0c\u5b8c\u6210\u540e\u8bf7\u6838\u5bf9\u771f\u5b9e\u4fe1\u606f\u3002';
      const finished = await waitForResult(started.id);
      if (finished.state !== 'succeeded') throw new Error(finished.error || '整理未完成，本次不消耗 AI 优化次数。');
      proposed = finished.result.document;
      dialog.querySelector('[data-compose-reason]').textContent = finished.result.reason;
      dialog.querySelector('[data-compose-name]').textContent = [proposed.name, proposed.role].filter(Boolean).join(' \u00b7 ') || '\u5f85\u586b\u5199';
      dialog.querySelector('[data-compose-summary]').textContent = proposed.summary || '\u5f85\u586b\u5199';
      dialog.querySelector('[data-compose-counts]').textContent = `${proposed.experiences.length} \u6bb5\u5de5\u4f5c\u7ecf\u5386 \u00b7 ${proposed.projects.length} \u4e2a\u9879\u76ee \u00b7 ${proposed.education.length} \u6bb5\u6559\u80b2\u7ecf\u5386`;
      const sections = dialog.querySelector('[data-compose-sections]'); sections.replaceChildren();
      for (const [label, entries, render] of [
        ['\u5de5\u4f5c\u7ecf\u5386', proposed.experiences, item => [item.company,item.role,...item.bullets].filter(Boolean).join(' \u00b7 ')],
        ['\u9879\u76ee\u7ecf\u5386', proposed.projects, item => [item.name,item.role,item.description].filter(Boolean).join(' \u00b7 ')],
        ['\u6559\u80b2\u7ecf\u5386', proposed.education, item => [item.school,item.degree,item.detail].filter(Boolean).join(' \u00b7 ')],
        ['\u6280\u80fd', proposed.skills, item => [item.label,...item.items].filter(Boolean).join(' \u00b7 ')],
      ]) {
        if (!entries.length) continue;
        const heading = document.createElement('h3'); heading.textContent = label; sections.append(heading);
        entries.forEach(item => { const p = document.createElement('p'); p.textContent = render(item); sections.append(p); });
      }
      status.textContent = '\u6574\u7406\u5b8c\u6210\uff0c\u5e94\u7528\u524d\u8bf7\u6838\u5bf9\u63d0\u53d6\u7ed3\u679c\u3002';
      review.hidden = false; accept.hidden = false;
    } catch (error) { status.textContent = error.message; }
    finally { running = false; button.disabled = false; }
  });
  accept.addEventListener('click', () => {
    if (!proposed) return;
    if (editor.dataset.dirty === 'true') { status.textContent = '\u5f53\u524d\u7b80\u5386\u6709\u672a\u4fdd\u5b58\u4fee\u6539\uff0c\u8bf7\u4fdd\u5b58\u540e\u91cd\u65b0\u5e94\u7528\u3002'; return; }
    editor.dispatchEvent(new CustomEvent('cf:apply-document', { detail:proposed }));
    dialog.close(); document.querySelector('#resume-basics').scrollIntoView({ behavior:'smooth' });
  });
})();
