/* Account-backed drafts. Failed requests retain both content and their idempotency key. */
(() => {
  const csrf = () => document.querySelector('meta[name="csrf-token"]').content;
  async function api(url, payload) {
    const response = await fetch(url, { method: 'POST', credentials: 'same-origin', redirect: 'error',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
      body: JSON.stringify(payload) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || '请求失败，请稍后重试');
    return result;
  }
  window.cfApi = api;
  const saveJob = document.querySelector('[data-save-job]');
  let jobKey = crypto.randomUUID();
  saveJob?.addEventListener('click', async () => {
    const select = document.querySelector('#analysis-resume');
    const status = document.querySelector('#job-save-status');
    if (!select.value) { status.textContent = '请先选择一份已保存简历'; select.focus(); return; }
    saveJob.disabled = true;
    try {
      const result = await api('/api/jobs', { request_key: jobKey, resume_id: Number(select.value),
        resume_revision: Number(select.selectedOptions[0].dataset.revision),
        title: document.querySelector('#job-title').value, company: document.querySelector('#job-company').value,
        description: document.querySelector('#job-description').value, url: document.querySelector('#job-url').value });
      location.href = `/jobs/${result.id}`;
    } catch (error) { status.textContent = error.message; saveJob.disabled = false; }
  });
  document.querySelector('[data-ui-form="job"]')?.addEventListener('input', () => {
    jobKey = crypto.randomUUID(); document.querySelector('#job-review').hidden = true;
  });
  const feedback = document.querySelector('[data-list-feedback]');
  document.querySelectorAll('[data-copy-resume]').forEach(button => button.addEventListener('click', async () => {
    const title = window.prompt('新版本名称', '岗位版本');
    if (!title?.trim()) return;
    button.disabled = true;
    try {
      const result = await api(`/api/resumes/${button.dataset.copyResume}/copy`, { title, request_key: crypto.randomUUID() });
      location.href = `/workspace?view=resume-new&resume_id=${result.id}`;
    } catch (error) { feedback.textContent = error.message; button.disabled = false; }
  }));
  document.querySelectorAll('[data-delete-resume],[data-delete-job]').forEach(button => button.addEventListener('click', async () => {
    if (!window.confirm('确认删除这条记录？此操作不可撤销。')) return;
    button.disabled = true;
    try {
      const type = button.dataset.deleteResume ? 'resumes' : 'jobs';
      await api(`/api/${type}/${button.dataset.deleteResume || button.dataset.deleteJob}/delete`, { confirm: 'delete' });
      location.reload();
    } catch (error) { feedback.textContent = error.message; button.disabled = false; }
  }));
  const editor = document.querySelector('[data-resume-editor]');
  if (!editor) return;
  const status = document.querySelector('#resume-draft-status');
  const title = document.querySelector('#resume-title');
  const saveButton = document.querySelector('[data-save-resume]');
  const saved = JSON.parse(editor.dataset.saved || 'null');
  const stage = document.querySelector('[data-resume-stage]');
  const hidden = new Set(saved?.document.hidden_sections || []);
  const defaultOrder = ['summary', 'experiences', 'projects', 'education', 'skills', 'certificates', 'languages'];
  let sectionOrder = [...defaultOrder];
  editor.dataset.hiddenSections = JSON.stringify([...hidden]);
  const setHidden = (key, isHidden) => {
    if (isHidden) hidden.add(key); else hidden.delete(key);
    editor.dataset.hiddenSections = JSON.stringify([...hidden]);
    visibility.querySelectorAll('input').forEach(input => {
      input.checked = !hidden.has(input.dataset.sectionVisibility);
    });
    editor.querySelectorAll('[data-editor-section]').forEach(section => {
      const removed = hidden.has(section.dataset.editorSection);
      section.classList.toggle('is-removed', removed);
      const button = section.querySelector('[data-section-toggle]');
      if (button) button.textContent = removed ? '添加到简历' : '从简历移除';
    });
    editor.dispatchEvent(new Event('cf:refresh'));
  };
  const visibility = document.createElement('fieldset');
  const legend = document.createElement('legend'); legend.textContent = '显示的模块（取消勾选保留内容）'; visibility.append(legend);
  for (const [key, text] of Object.entries({ summary:'简介', experiences:'工作经历', projects:'项目', education:'教育', skills:'技能', certificates:'证书', languages:'语言' })) {
    const label = document.createElement('label'); const input = document.createElement('input');
    input.type = 'checkbox'; input.checked = !hidden.has(key); input.dataset.sectionVisibility = key;
    input.addEventListener('change', () => {
      setHidden(key, !input.checked);
    });
    label.append(input, document.createTextNode(text)); visibility.append(label);
  }
  editor.querySelector('#resume-template').before(visibility);
  let id = saved?.id, revision = saved?.revision || 0;
  let dirty = false, saving = false, timer, pending = null, generation = 0, pendingGeneration = 0;
  let conflict = false;
  const limits = { experiences: 20, projects: 20, education: 10 };
  const sections = { experiences: '#resume-experience', projects: '#resume-projects', education: '#resume-education' };
  function reindex(group) {
    const blocks = editor.querySelectorAll(`${sections[group]} .repeat-block`);
    blocks.forEach((block, index) => {
      const legend = block.querySelector('legend');
      if (legend) legend.textContent = `${{experiences:'工作经历',projects:'项目',education:'教育经历'}[group]} ${index + 1}`;
      block.querySelectorAll('[data-rf-field]').forEach(field => {
        field.dataset.rfField = field.dataset.rfField.replace(/\.\d+\./, `.${index}.`);
      });
    });
    document.querySelectorAll('[data-resume-panel]').forEach(panel => {
      const section = panel.querySelector(`[data-rf-section="${group}"]`);
      const source = section.querySelector('[data-rf-entry]');
      const prototype = source?.cloneNode(true);
      if (!prototype) return;
      section.querySelectorAll('[data-rf-entry]').forEach(node => node.remove());
      blocks.forEach((_, index) => {
        const node = prototype.cloneNode(true);
        node.dataset.rfEntry = `${group}.${index}`;
        node.querySelectorAll('[data-rf],[data-rf-list],[data-rf-if]').forEach(element => {
          ['rf', 'rfList', 'rfIf'].forEach(key => {
            if (element.dataset[key]) element.dataset[key] = element.dataset[key].replace(/\.\d+\./, `.${index}.`);
          });
        });
        section.append(node);
      });
    });
  }
  function controls(block, group) {
    block.querySelector('[data-repeat-actions]')?.remove();
    const actions = document.createElement('div'); actions.dataset.repeatActions = '';
    for (const [label, direction] of [['上移', -1], ['下移', 1], ['删除', 0]]) {
      const button = document.createElement('button'); button.type = 'button'; button.textContent = label;
      button.addEventListener('click', () => {
        if (direction === 0) {
          if (!window.confirm('删除这段经历？可从已保存版本恢复。')) return;
          const count = block.parentElement.querySelectorAll('.repeat-block').length;
          if (count === 1) block.querySelectorAll('input,textarea').forEach(input => { input.value = ''; });
          else block.remove();
        } else {
          const sibling = direction < 0 ? block.previousElementSibling : block.nextElementSibling;
          if (!sibling?.matches('.repeat-block')) return;
          if (direction < 0) sibling.before(block); else sibling.after(block);
        }
        reindex(group); editor.dispatchEvent(new Event('cf:refresh'));
      });
      actions.append(button);
    }
    block.append(actions);
  }
  function add(group) {
    const section = editor.querySelector(sections[group]);
    if (section.querySelectorAll('.repeat-block').length >= limits[group]) return;
    const block = section.querySelector('.repeat-block').cloneNode(true);
    block.querySelectorAll('input,textarea').forEach(input => { input.value = ''; input.removeAttribute('id'); });
    section.querySelector('[data-add-entry]').before(block);
    controls(block, group); reindex(group);
  }
  for (const group of Object.keys(sections)) {
    const section = editor.querySelector(sections[group]);
    section.querySelectorAll('.repeat-block').forEach(block => controls(block, group));
    const button = document.createElement('button'); button.type = 'button'; button.dataset.addEntry = group;
    button.textContent = '新增一段经历'; button.className = 'button secondary';
    button.addEventListener('click', () => { add(group); editor.dispatchEvent(new Event('cf:refresh')); });
    section.append(button);
    if (saved) {
      const needed = Math.max(saved.document[group].length, 1);
      while (section.querySelectorAll('.repeat-block').length > needed) section.querySelector('.repeat-block:last-of-type').remove();
      while (section.querySelectorAll('.repeat-block').length < needed) add(group);
      reindex(group);
    }
  }
  function documentData() {
    const result = { photo: document.querySelector('#resume-photo-status')?.dataset.photo || '',
      hidden_sections: [...hidden], section_order: [...sectionOrder], size: stage.dataset.size || 'standard',
      accent: stage.dataset.accent || 'default', photo_position: stage.dataset.photoPosition || 'center' };
    editor.querySelectorAll('[data-rf-field]').forEach(input => {
      const path = input.dataset.rfField.split('.'); let current = result;
      path.forEach((part, index) => {
        if (index === path.length - 1) {
          const v = input.value.trim();
          current[part] = part === 'bullets' || ['certificates', 'languages'].includes(part)
            ? v.split('\n').map(x => x.trim()).filter(Boolean)
            : part === 'items' ? v.split(/[,，、]/).map(x => x.trim()).filter(Boolean) : v;
        } else { current[part] ??= /^\d+$/.test(path[index + 1]) ? [] : {}; current = current[part]; }
      });
    });
    return result;
  }
  async function save() {
    if (saving || !dirty || conflict) return;
    saving = true; saveButton.disabled = true;
    if (!pending) pendingGeneration = generation;
    pending ??= { request_key: crypto.randomUUID(), revision, title: title.value.trim() || '未命名简历',
      template: document.querySelector('#resume-template-quick').value, document: documentData() };
    status.textContent = '正在保存…';
    try {
      const result = await api(id ? `/api/resumes/${id}` : '/api/resumes', pending);
      id = result.id; revision = result.revision; pending = null;
      dirty = pendingGeneration !== generation;
      history.replaceState(null, '', `/workspace?view=resume-new&resume_id=${id}`);
      status.textContent = dirty ? '正在保存后续修改…' : `已保存到账号 · 第 ${revision} 版`;
    } catch (error) {
      status.textContent = `保存失败：${error.message}。填写仍在本页，请重试。`;
      if (error.message.includes('其他窗口')) conflict = true;
    } finally {
      saving = false; saveButton.disabled = false;
      if (dirty && !pending && !conflict) timer = setTimeout(save, 800);
    }
  }
  function changed() {
    dirty = true; generation++; clearTimeout(timer); timer = setTimeout(save, 900);
    status.textContent = '有修改尚未保存';
  }
  function loadLayout(documentData) {
    hidden.clear(); (documentData.hidden_sections || []).forEach(key => hidden.add(key));
    editor.dataset.hiddenSections = JSON.stringify([...hidden]);
    visibility.querySelectorAll('input').forEach(input => { input.checked = !hidden.has(input.dataset.sectionVisibility); });
    sectionOrder = [...defaultOrder].sort((a, b) => {
      const order = documentData.section_order || defaultOrder;
      return order.indexOf(a) - order.indexOf(b);
    });
    applySectionOrder();
    editor.querySelectorAll('[data-editor-section]').forEach(section => {
      const removed = hidden.has(section.dataset.editorSection);
      section.classList.toggle('is-removed', removed);
      const button = section.querySelector('[data-section-toggle]');
      if (button) button.textContent = removed ? '添加到简历' : '从简历移除';
    });
    stage.dataset.size = documentData.size || 'standard';
    stage.dataset.accent = documentData.accent || 'default';
    stage.dataset.photoPosition = documentData.photo_position || 'center';
    document.querySelector('#resume-size').value = stage.dataset.size;
    document.querySelector('#resume-photo-position').value = stage.dataset.photoPosition;
  }
  editor.addEventListener('cf:change', changed);
  title.addEventListener('input', changed);
  document.querySelectorAll('[name="resume-template"],#resume-template-quick').forEach(input => input.addEventListener('change', changed));
  document.querySelectorAll('#resume-size,#resume-photo-position').forEach(input => input.addEventListener('change', changed));
  document.querySelectorAll('[data-accent-choice]').forEach(input => input.addEventListener('click', changed));
  saveButton.addEventListener('click', () => { dirty = true; save(); });
  const saveCopy = document.createElement('button'); saveCopy.type = 'button';
  saveCopy.textContent = '另存新简历'; saveCopy.dataset.saveCopy = '';
  saveCopy.addEventListener('click', () => {
    if (saving) return;
    id = null; revision = 0; pending = null; conflict = false;
    title.value = `${title.value.slice(0, 110)} · 副本`; dirty = true; generation++; save();
  });
  const backup = document.createElement('button'); backup.type = 'button';
  backup.textContent = '下载本地备份';
  backup.addEventListener('click', () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify({ title: title.value, document: documentData() }, null, 2)], { type: 'application/json' }));
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'careerflow-draft.json';
    anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  saveButton.after(saveCopy, backup);
  window.addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
  if (saved) {
    title.value = saved.title;
    loadLayout(saved.document);
    editor.dispatchEvent(new CustomEvent('cf:load', { detail: saved }));
    status.textContent = `已保存到账号 · 第 ${revision} 版`;
    editor.querySelector('.resume-photo-editor').open = Boolean(saved.document.photo);
  }
  const chapters = Array.from(editor.querySelectorAll('.editor-section'));
  let draggedSection = null;
  function applySectionOrder() {
    const fields = editor.querySelector('.resume-fields');
    const template = editor.querySelector('#resume-template');
    sectionOrder.forEach(key => fields.insertBefore(editor.querySelector(`[data-editor-section="${key}"]`), visibility));
    editor.dataset.sectionOrder = JSON.stringify(sectionOrder);
    template.before(visibility);
  }
  applySectionOrder();
  chapters.forEach(chapter => {
    const heading = chapter.querySelector('.work-section-heading');
    const key = chapter.dataset.editorSection;
    if (key) {
      chapter.classList.toggle('is-removed', hidden.has(key));
      const grip = document.createElement('span'); grip.className = 'editor-section-grip';
      grip.textContent = '⠿'; grip.title = '拖动调整板块顺序';
      grip.draggable = true; grip.setAttribute('role', 'img'); grip.setAttribute('aria-label', '拖动排序');
      grip.addEventListener('dragstart', event => {
        draggedSection = key;
        event.dataTransfer.setData('text/plain', key); event.dataTransfer.effectAllowed = 'move';
      });
      grip.addEventListener('dragend', () => { draggedSection = null; });
      chapter.addEventListener('dragover', event => { event.preventDefault(); event.dataTransfer.dropEffect = 'move'; });
      chapter.addEventListener('drop', event => {
        event.preventDefault(); const source = draggedSection || event.dataTransfer.getData('text/plain');
        if (!sectionOrder.includes(source) || source === key) return;
        sectionOrder.splice(sectionOrder.indexOf(source), 1);
        sectionOrder.splice(sectionOrder.indexOf(key), 0, source);
        applySectionOrder(); editor.dispatchEvent(new Event('cf:refresh'));
      });
      heading.prepend(grip);
      for (const [label, offset] of [['上移', -1], ['下移', 1]]) {
        const button = document.createElement('button'); button.type = 'button';
        button.className = 'editor-section-move'; button.textContent = label;
        button.setAttribute('aria-label', `${heading.querySelector('h2').textContent}${label}`);
        button.addEventListener('click', () => {
          const index = sectionOrder.indexOf(key), target = index + offset;
          if (target < 0 || target >= sectionOrder.length) return;
          [sectionOrder[index], sectionOrder[target]] = [sectionOrder[target], sectionOrder[index]];
          applySectionOrder(); editor.dispatchEvent(new Event('cf:refresh'));
        }); heading.append(button);
      }
      const remove = document.createElement('button'); remove.type = 'button';
      remove.className = 'editor-section-visibility'; remove.dataset.sectionToggle = key;
      remove.textContent = hidden.has(key) ? '添加到简历' : '从简历移除';
      remove.addEventListener('click', () => setHidden(key, !hidden.has(key)));
      heading.append(remove);
    }
    const toggle = document.createElement('button');
    toggle.type = 'button'; toggle.className = 'editor-section-toggle';
    toggle.setAttribute('aria-expanded', 'true');
    toggle.setAttribute('aria-label', `折叠${heading.querySelector('h2').textContent}`);
    toggle.textContent = '收起';
    toggle.addEventListener('click', () => {
      const collapsed = chapter.classList.toggle('is-collapsed');
      toggle.setAttribute('aria-expanded', String(!collapsed));
      toggle.setAttribute('aria-label', `${collapsed ? '展开' : '折叠'}${heading.querySelector('h2').textContent}`);
      toggle.textContent = collapsed ? '展开' : '收起';
    });
    heading.append(toggle);
  });
  document.querySelector('[data-version-history]').addEventListener('click', async () => {
    const container = document.querySelector('#version-history');
    container.hidden = false; container.replaceChildren();
    if (!id) { container.textContent = '保存后可查看版本历史'; return; }
    try {
      const response = await fetch(`/api/resumes/${id}/versions`, { redirect: 'error' });
      if (!response.ok) throw new Error('读取版本失败');
      const result = await response.json();
      result.versions.forEach(version => {
        const button = document.createElement('button'); button.type = 'button';
        button.textContent = `载入第 ${version.revision} 版（保存后成为新版本）`;
        button.addEventListener('click', () => {
          if (!window.confirm('载入历史内容替换当前填写？已保存的版本仍保留。')) return;
          for (const group of Object.keys(sections)) {
            const section = editor.querySelector(sections[group]);
            const needed = Math.max(version.document[group].length, 1);
            while (section.querySelectorAll('.repeat-block').length > needed) section.querySelector('.repeat-block:last-of-type').remove();
            while (section.querySelectorAll('.repeat-block').length < version.document[group].length) add(group);
            reindex(group);
          }
          title.value = version.title;
          loadLayout(version.document);
          editor.dispatchEvent(new CustomEvent('cf:load', { detail: version })); changed();
        }); container.append(button);
      });
    } catch (error) { container.textContent = error.message; }
  });
})();
