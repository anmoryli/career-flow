/* Account-backed drafts. Failed requests retain both content and their idempotency key. */
(() => {
  const csrf = () => document.querySelector('meta[name="csrf-token"]').content;
  async function api(url, payload) {
    const response = await fetch(url, { method: 'POST', credentials: 'same-origin', redirect: 'error',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
      body: JSON.stringify(payload) });
    const result = await response.json();
    if (!response.ok) { const error = new Error(result.error || 'Request failed'); error.loginRequired = Boolean(result.login_required); throw error; }
    return result;
  }
  window.cfApi = api;
  const saveJob = document.querySelector('[data-save-job]');
  const jobSaveDialog = document.querySelector('#job-save-dialog');
  let jobKey = crypto.randomUUID();
  let guestResume = null;
  const guestFile = document.querySelector('#guest-resume-file');
  guestFile?.addEventListener('change', async () => {
    const file = guestFile.files[0];
    const status = document.querySelector('#guest-resume-status');
    if (!file) return;
    if (file.size > 4 * 1024 * 1024) { status.textContent = 'PDF 不能超过 4 MB'; return; }
    status.textContent = '正在提取简历内容…';
    const form = new FormData(); form.set('file', file);
    try {
      const response = await fetch('/api/guest/resume/parse', { method: 'POST', body: form,
        headers: { 'X-CSRFToken': csrf() }, credentials: 'same-origin' });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'PDF 解析失败');
      guestResume = result;
      status.textContent = `已读取「${result.title}」，确认岗位后点击开始分析`;
    } catch (error) { guestResume = null; status.textContent = error.message; }
  });
  document.querySelector('[data-import-saved-job]')?.addEventListener('click', async event => {
    const button = event.currentTarget;
    const picker = document.querySelector('#saved-job-select');
    const status = document.querySelector('[data-import-job-status]');
    if (!picker?.value) { status.textContent = '请先选择一个已保存的岗位'; picker?.focus(); return; }
    const fields = ['#job-title', '#job-company', '#job-description', '#job-url'].map(selector => document.querySelector(selector));
    if (fields.some(field => field?.value.trim()) && !window.confirm('导入会替换当前填写的岗位信息，是否继续？')) return;
    button.disabled = true;
    status.textContent = '正在导入岗位…';
    try {
      const response = await fetch(`/api/jobs/${picker.value}`, { credentials: 'same-origin', redirect: 'error' });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || '导入失败，请稍后重试');
      fields.forEach((field, index) => {
        if (field) {
          field.value = [result.title, result.company, result.description, result.url][index] || '';
          field.dispatchEvent(new Event('input', { bubbles: true }));
        }
      });
      const resume = document.querySelector('#analysis-resume');
      if (resume && [...resume.options].some(option => option.value === String(result.resume_id))) {
        resume.value = String(result.resume_id);
        resume.dispatchEvent(new Event('change', { bubbles: true }));
      }
      if (result.url) document.querySelector('.job-optional-link')?.setAttribute('open', '');
      status.textContent = `已导入「${result.title || '未命名岗位'}」，核对信息后可继续分析`;
      document.querySelector('#job-title')?.focus();
    } catch (error) { status.textContent = error.message; }
    finally { button.disabled = false; }
  });
  saveJob?.addEventListener('click', () => {
    const select = document.querySelector('#analysis-resume');
    const status = document.querySelector('#job-save-status');
    if (!select && !guestResume) { status.textContent = '\u8bf7\u5148\u4e0a\u4f20\u4e00\u4efd PDF \u7b80\u5386'; guestFile?.focus(); return; }
    if (select && !select.value) { status.textContent = '\u8bf7\u5148\u9009\u62e9\u4e00\u4efd\u7b80\u5386'; select.focus(); return; }
    jobSaveDialog?.showModal();
  });
  const startJobAnalysis = async saveForLater => {
    const select = document.querySelector('#analysis-resume');
    const status = document.querySelector('#job-save-status');
    const button = saveJob;
    button.disabled = true;
    const submit = async () => {
      let resumeId = Number(select?.value);
      let revision = Number(select?.selectedOptions[0]?.dataset.revision);
      if (!select && guestResume) {
        const resume = await api('/api/resumes', { request_key: crypto.randomUUID(), title: guestResume.title || '\u5bfc\u5165\u7684\u7b80\u5386', template: 'classic', document: guestResume.document });
        resumeId = resume.id; revision = resume.revision;
      }
      const result = await api('/api/jobs', { request_key: jobKey, resume_id: resumeId,
        resume_revision: revision, title: document.querySelector('#job-title').value,
        company: document.querySelector('#job-company').value,
        description: document.querySelector('#job-description').value, url: document.querySelector('#job-url').value,
        save_for_later: saveForLater });
      location.href = `/jobs/${result.id}?start=analysis`;
    };
    try { await submit(); }
    catch (error) {
      if (error.loginRequired && window.cfRequireAuth) {
        button.disabled = false;
        status.textContent = '\u767b\u5f55\u540e\u7ee7\u7eed\u4fdd\u5b58\u5e76\u5f00\u59cb\u5206\u6790';
        window.cfRequireAuth(async () => { button.disabled = true; try { await submit(); } catch (nextError) { status.textContent = nextError.message; button.disabled = false; } });
        return;
      }
      status.textContent = error.message; button.disabled = false;
    }
  };
  jobSaveDialog?.querySelectorAll('[data-job-save-choice]').forEach(choice => {
    choice.addEventListener('click', async () => {
      jobSaveDialog.close();
      await startJobAnalysis(choice.dataset.jobSaveChoice === 'yes');
    });
  });
  jobSaveDialog?.querySelector('[data-job-save-cancel]')?.addEventListener('click', () => jobSaveDialog.close());
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
  let customSections = structuredClone(saved?.document.custom_sections || []).map(section => ({
    ...section,
    title: section.title === '自定义板块' ? '' : section.title,
  }));
  let sectionOrder = [...defaultOrder];
  const tabs = editor.querySelector('[data-resume-section-tabs]');
  editor.dataset.hiddenSections = JSON.stringify([...hidden]);
  const setHidden = (key, isHidden) => {
    if (isHidden) hidden.add(key); else hidden.delete(key);
    editor.dataset.hiddenSections = JSON.stringify([...hidden]);
    const visibilityButton = tabs?.querySelector(`[data-tab-visibility="${key}"]`);
    visibilityButton?.setAttribute('aria-pressed', String(!hidden.has(key)));
    if (visibilityButton) {
      visibilityButton.textContent = hidden.has(key) ? '加入' : '隐藏';
      visibilityButton.setAttribute('aria-label', `${sectionLabel(key)}${hidden.has(key) ? '加入简历' : '从简历隐藏'}`);
    }
    editor.querySelectorAll('[data-editor-section]').forEach(section => {
      const removed = hidden.has(section.dataset.editorSection);
      section.classList.toggle('is-removed', removed);
    });
    editor.dispatchEvent(new Event('cf:refresh'));
    changed();
  };
  let id = saved?.id, revision = saved?.revision || 0;
  editor.dataset.resumeId = id || '';
  editor.dataset.resumeRevision = String(revision);
  editor.dataset.dirty = 'false';
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
    block.querySelectorAll('.resume-ai-panel').forEach(panel => panel.remove());
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
    const result = { custom_sections: customSections.map(section => ({ ...section })),
      photo: document.querySelector('#resume-photo-status')?.dataset.photo || '',
      hidden_sections: [...hidden], section_order: [...sectionOrder], size: stage.dataset.size || 'standard',
      accent: stage.dataset.accent || 'default', photo_position: stage.dataset.photoPosition || 'center' };
    editor.querySelectorAll('[data-rf-field]').forEach(input => {
      const path = input.dataset.rfField.split('.'); let current = result;
      path.forEach((part, index) => {
        if (index === path.length - 1) {
          const raw = input.value.trim();
          const v = part === 'link' && /^https?:\/\/$/i.test(raw) ? '' : raw;
          current[part] = part === 'bullets' || ['certificates', 'languages'].includes(part)
            ? v.split('\n').map(x => x.trim()).filter(Boolean)
            : part === 'items' ? v.split(/[,，、]/).map(x => x.trim()).filter(Boolean) : v;
        } else { current[part] ??= /^\d+$/.test(path[index + 1]) ? [] : {}; current = current[part]; }
      });
    });
    const hasValue = value => Array.isArray(value)
      ? value.some(hasValue)
      : value && typeof value === 'object'
        ? Object.values(value).some(hasValue)
        : typeof value === 'string' && Boolean(value.trim());
    for (const group of ['experiences', 'projects', 'education']) {
      result[group] = result[group].filter(hasValue);
    }
    result.skills = result.skills.filter(group => group.items.length > 0);
    result.certificates = result.certificates.filter(Boolean);
    result.languages = result.languages.filter(Boolean);
    result.custom_sections = result.custom_sections.filter(section => section.content.trim());
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
      editor.dataset.resumeId = String(id);
      editor.dataset.resumeRevision = String(revision);
      dirty = pendingGeneration !== generation;
      editor.dataset.dirty = String(dirty);
      editor.dispatchEvent(new Event('cf:saved'));
      try { localStorage.removeItem('cf-resume-guest-draft'); } catch (_) {}
      history.replaceState(null, '', `/workspace?view=resume-new&resume_id=${id}`);
      status.textContent = dirty ? '正在保存后续修改…' : `已保存到账号 · 第 ${revision} 版`;
    } catch (error) {
      if (error.loginRequired && window.cfRequireAuth) {
        status.textContent = '\u767b\u5f55\u540e\u4f1a\u7ee7\u7eed\u4fdd\u5b58\u8fd9\u4efd\u7b80\u5386';
        window.cfRequireAuth(async () => { saving = false; await save(); });
        return;
      }
      status.textContent = `保存失败：${error.message}。填写仍在本页，请重试。`;
      if (error.message.includes('其他窗口')) conflict = true;
    } finally {
      saving = false; saveButton.disabled = false;
      if (dirty && !pending && !conflict) timer = setTimeout(save, 800);
    }
  }
  function changed() {
    dirty = true; generation++; clearTimeout(timer);
    editor.dataset.dirty = 'true';
    editor.dispatchEvent(new Event('cf:dirty'));
    status.textContent = '有修改尚未保存';
    if (document.body.dataset.authenticated === 'yes') timer = setTimeout(save, 900);
    else { try { localStorage.setItem('cf-resume-guest-draft', JSON.stringify({ title: title.value, template: document.querySelector('#resume-template-quick').value, document: documentData() })); } catch (_) {} }
  }
  function loadLayout(documentData) {
    hidden.clear(); (documentData.hidden_sections || []).forEach(key => hidden.add(key));
    editor.dataset.hiddenSections = JSON.stringify([...hidden]);
    customSections = structuredClone(documentData.custom_sections || []);
    const order = documentData.section_order || defaultOrder;
    sectionOrder = order.filter(key => defaultOrder.includes(key) || customSections.some(section => key === `custom:${section.id}`));
    defaultOrder.forEach(key => { if (!sectionOrder.includes(key)) sectionOrder.push(key); });
    customSections.forEach(section => { const key = `custom:${section.id}`; if (!sectionOrder.includes(key)) sectionOrder.push(key); });
    renderCustomEditors();
    renderCustomPreviews();
    applySectionOrder();
    editor.querySelectorAll('[data-editor-section]').forEach(section => {
      const removed = hidden.has(section.dataset.editorSection);
      section.classList.toggle('is-removed', removed);
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
  window.addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
  if (saved) {
    title.value = saved.title;
    loadLayout(saved.document);
    editor.dispatchEvent(new CustomEvent('cf:load', { detail: saved }));
    status.textContent = `已保存到账号 · 第 ${revision} 版`;
    editor.querySelector('.resume-photo-editor').open = Boolean(saved.document.photo);
  } else if (document.body.dataset.authenticated !== 'yes') {
    try {
      const guestDraft = JSON.parse(localStorage.getItem('cf-resume-guest-draft') || 'null');
      if (guestDraft) {
        title.value = guestDraft.title || '';
        editor.querySelector('#resume-template-quick').value = guestDraft.template || 'classic';
        for (const field of editor.querySelectorAll('[data-rf-field]')) {
          const value = field.dataset.rfField.split('.').reduce((node, key) => node == null ? node : node[/^\d+$/.test(key) ? Number(key) : key], guestDraft.document);
          field.value = Array.isArray(value) ? value.join('\n') : value || '';
        }
        editor.dispatchEvent(new Event('cf:refresh'));
        dirty = true; editor.dataset.dirty = 'true'; status.textContent = '\u672c\u673a\u8349\u7a3f\u5df2\u6062\u590d';
      }
    } catch (_) {}
  }
  const startTemplate = editor.querySelector('[data-start-template]');
  const quickTemplate = document.querySelector('#resume-template-quick');
  if (startTemplate && quickTemplate) {
    startTemplate.value = quickTemplate.value;
    startTemplate.addEventListener('change', () => {
      quickTemplate.value = startTemplate.value;
      quickTemplate.dispatchEvent(new Event('change', { bubbles:true }));
    });
    editor.addEventListener('cf:load', () => { startTemplate.value = quickTemplate.value; });
  }
  const chapters = Array.from(editor.querySelectorAll('.editor-section'));
  let activeSection = 'basics';
  let draggedSection = null;
  const sectionLabels = { summary:'个人简介', experiences:'工作经历', projects:'项目经历', education:'教育经历', skills:'专业技能', certificates:'证书与资格', languages:'语言能力' };
  const sectionTargets = { basics:'resume-basics', photo:'resume-photo-section', summary:'resume-summary-section', experiences:'resume-experience', projects:'resume-projects', education:'resume-education', skills:'resume-skills', certificates:'resume-certificates', languages:'resume-languages', template:'resume-template' };
  function sectionLabel(key) {
    return sectionLabels[key] || customSections.find(section => key === `custom:${section.id}`)?.title || '自定义板块';
  }
  function renderCustomEditors() {
    const fields = editor.querySelector('.resume-fields');
    fields.querySelectorAll('[data-custom-section-editor]').forEach(section => section.remove());
    customSections.forEach((custom, index) => {
      const key = `custom:${custom.id}`;
      const section = document.createElement('section');
      section.id = `custom-section-${custom.id}`;
      section.className = 'editor-section custom-resume-section';
      section.dataset.editorSection = key;
      section.dataset.customSectionEditor = '';
      const heading = document.createElement('div'); heading.className = 'work-section-heading';
      const headingTitle = document.createElement('h2'); headingTitle.textContent = custom.title || '自定义板块';
      const headingNumber = document.createElement('span'); headingNumber.textContent = '＋';
      heading.append(headingTitle, headingNumber);
      const titleLabel = document.createElement('label'); titleLabel.className = 'editor-field';
      titleLabel.append(document.createTextNode('板块名称'));
      const titleInput = document.createElement('input'); titleInput.maxLength = 80;
      titleInput.value = custom.title || '';
      titleInput.placeholder = '例如：获奖经历';
      titleInput.addEventListener('input', () => {
        custom.title = titleInput.value.trim();
        headingTitle.textContent = custom.title || '自定义板块';
        const tab = [...tabs.querySelectorAll('[data-section-tab]')].find(button => button.dataset.sectionTab === key);
        if (tab) tab.textContent = custom.title || '自定义板块';
        stage.querySelectorAll('[data-custom-preview]').forEach(preview => {
          if (preview.dataset.rfSection === key) {
            const previewTitle = preview.querySelector('.rd-section-title');
            previewTitle.hidden = !custom.title;
            previewTitle.querySelector('span').textContent = custom.title;
          }
        });
        changed();
      });
      titleLabel.append(titleInput);
      const contentLabel = document.createElement('label'); contentLabel.className = 'editor-field';
      contentLabel.append(document.createTextNode('内容'));
      const content = document.createElement('textarea'); content.rows = 7; content.maxLength = 4000;
      content.placeholder = '填写你希望展示的内容'; content.value = custom.content || '';
      content.dataset.rfField = `custom_sections.${index}.content`;
      contentLabel.append(content);
      const remove = document.createElement('button'); remove.type = 'button';
      remove.className = 'button secondary custom-section-delete'; remove.textContent = '删除板块';
      remove.addEventListener('click', () => {
        if (!window.confirm(`删除“${custom.title || '自定义板块'}”？`)) return;
        customSections = customSections.filter(item => item.id !== custom.id);
        sectionOrder = sectionOrder.filter(item => item !== key);
        hidden.delete(key);
        activeSection = 'basics';
        renderCustomEditors(); renderCustomPreviews(); applySectionOrder(); renderSectionTabs();
        activateSection(activeSection); editor.dispatchEvent(new Event('cf:refresh'));
      });
      section.append(heading, titleLabel, contentLabel, remove);
      fields.querySelector('#resume-template').before(section);
    });
    const addButton = editor.querySelector('[data-add-custom-section]');
    addButton.disabled = customSections.length >= 10;
    addButton.textContent = customSections.length >= 10 ? '已添加 10 个自定义板块' : '＋ 添加自定义板块';
  }
  function renderCustomPreviews() {
    stage.querySelectorAll('[data-section-flow]').forEach(flow => {
      flow.querySelectorAll('[data-custom-preview]').forEach(section => section.remove());
      customSections.forEach((custom, index) => {
        const section = document.createElement('section');
        section.className = 'rd-section'; section.dataset.rfSection = `custom:${custom.id}`;
        section.dataset.customPreview = '';
        const heading = document.createElement('h2'); heading.className = 'rd-section-title'; heading.hidden = !custom.title;
        const title = document.createElement('span'); title.textContent = custom.title || '自定义板块'; heading.append(title);
        const content = document.createElement('div'); content.className = 'rd-markdown';
        content.dataset.rf = `custom_sections.${index}.content`; content.textContent = custom.content || '';
        section.append(heading, content); flow.append(section);
      });
    });
  }
  editor.querySelector('[data-add-custom-section]').addEventListener('click', () => {
    if (customSections.length >= 10) return;
    const custom = { id: crypto.randomUUID(), title: '', content: '' };
    customSections.push(custom);
    const key = `custom:${custom.id}`; sectionOrder.push(key);
    renderCustomEditors(); renderCustomPreviews(); applySectionOrder(); renderSectionTabs();
    activateSection(key); editor.dispatchEvent(new Event('cf:refresh'));
    editor.querySelector(`[data-editor-section="${key}"] input`)?.focus();
  });
  function activateSection(key) {
    activeSection = key;
    editor.querySelectorAll('.resume-fields > .editor-section, .resume-fields > .resume-photo-editor').forEach(section => {
      section.hidden = section.dataset.editorSection ? section.dataset.editorSection !== key
        : section.id !== (key === 'photo' ? 'resume-photo-section' : `resume-${key}`);
    });
    tabs.querySelectorAll('[data-section-tab]').forEach(button => {
      const selected = button.dataset.sectionTab === key;
      button.classList.toggle('is-active', selected);
      button.setAttribute('aria-current', selected ? 'step' : 'false');
    });
  }
  function moveSection(key, offset) {
    const from = sectionOrder.indexOf(key);
    const to = from + offset;
    if (from < 0 || to < 0 || to >= sectionOrder.length) return;
    sectionOrder.splice(from, 1);
    sectionOrder.splice(to, 0, key);
    applySectionOrder(); renderSectionTabs(); activateSection(activeSection);
    editor.dispatchEvent(new Event('cf:refresh'));
    changed();
  }
  function renderSectionTabs() {
    tabs.replaceChildren();
    const addTab = (key, label, reorderable = false) => {
      const item = document.createElement('div'); item.className = 'resume-section-tab';
      if (reorderable) item.dataset.sortableSection = key;
      const button = document.createElement('button'); button.type = 'button';
      button.dataset.sectionTab = key; button.textContent = label;
      button.setAttribute('aria-controls', sectionTargets[key] || `custom-section-${key.slice('custom:'.length)}`);
      button.addEventListener('click', () => activateSection(key));
      item.append(button);
      if (reorderable) {
        const visibilityButton = document.createElement('button'); visibilityButton.type = 'button';
        visibilityButton.className = 'resume-tab-visibility'; visibilityButton.dataset.tabVisibility = key;
        visibilityButton.setAttribute('aria-pressed', String(!hidden.has(key)));
        visibilityButton.setAttribute('aria-label', `${label}${hidden.has(key) ? '加入简历' : '从简历隐藏'}`);
        visibilityButton.textContent = hidden.has(key) ? '加入' : '隐藏';
        visibilityButton.addEventListener('click', () => setHidden(key, !hidden.has(key)));
        item.append(visibilityButton);
        for (const [label, offset] of [['上移', -1], ['下移', 1]]) {
          const moveButton = document.createElement('button'); moveButton.type = 'button';
          moveButton.className = 'resume-tab-move'; moveButton.textContent = label;
          moveButton.setAttribute('aria-label', `${sectionLabel(key)}${label}`);
          moveButton.disabled = sectionOrder.indexOf(key) + offset < 0 || sectionOrder.indexOf(key) + offset >= sectionOrder.length;
          moveButton.addEventListener('click', () => moveSection(key, offset));
          item.append(moveButton);
        }
        const dragHandle = document.createElement('button'); dragHandle.type = 'button';
        dragHandle.className = 'resume-tab-drag'; dragHandle.textContent = '⠿ 拖动';
        dragHandle.title = '拖动此手柄调整板块顺序'; dragHandle.draggable = true;
        dragHandle.setAttribute('aria-label', `拖动${label}调整顺序`);
        dragHandle.addEventListener('dragstart', event => {
          draggedSection = key; item.classList.add('is-dragging');
          event.dataTransfer.setData('text/plain', key); event.dataTransfer.effectAllowed = 'move';
        });
        dragHandle.addEventListener('dragend', () => { draggedSection = null; item.classList.remove('is-dragging'); });
        item.append(dragHandle);
        item.addEventListener('dragover', event => { event.preventDefault(); item.classList.add('is-drop-target'); event.dataTransfer.dropEffect = 'move'; });
        item.addEventListener('dragleave', () => item.classList.remove('is-drop-target'));
        item.addEventListener('drop', event => {
          event.preventDefault(); item.classList.remove('is-drop-target');
          const source = draggedSection || event.dataTransfer.getData('text/plain');
          if (!sectionOrder.includes(source) || source === key) return;
          moveSection(source, sectionOrder.indexOf(key) - sectionOrder.indexOf(source));
        });
      }
      tabs.append(item);
    };
    addTab('basics', '基本信息');
    addTab('photo', '个人照片');
    sectionOrder.forEach(key => addTab(key, sectionLabel(key), true));
    addTab('template', '简历模板');
    activateSection(activeSection);
  }
  function applySectionOrder() {
    const fields = editor.querySelector('.resume-fields');
    sectionOrder.forEach(key => {
      const section = [...fields.querySelectorAll('[data-editor-section]')].find(item => item.dataset.editorSection === key);
      if (section) fields.append(section);
    });
    fields.append(editor.querySelector('#resume-template'));
    editor.dataset.sectionOrder = JSON.stringify(sectionOrder);
  }
  applySectionOrder();
  renderSectionTabs();
  chapters.forEach(chapter => chapter.classList.toggle('is-removed', hidden.has(chapter.dataset.editorSection)));
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
        if (version.created_at) {
          const localTime = new Date(new Date(version.created_at).getTime() + 8 * 60 * 60 * 1000)
            .toISOString().slice(0, 16).replace('T', ' ');
          button.textContent += ` · ${localTime} UTC+8`;
        }
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
          renderSectionTabs(); activateSection(activeSection);
          editor.dispatchEvent(new CustomEvent('cf:load', { detail: version })); changed();
        }); container.append(button);
      });
    } catch (error) { container.textContent = error.message; }
  });
  document.querySelector('[data-extract-contact]')?.addEventListener('click', () => {
    const source = document.querySelector('#resume-source-text').value;
    const feedback = document.querySelector('#resume-source-feedback');
    if (!source.trim()) { feedback.textContent = '请先粘贴真实经历或简历文字。'; return; }
    const email = source.match(/[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}/);
    const phone = source.match(/(?<!\d)1[3-9]\d{9}(?!\d)/);
    const found = [];
    for (const [key, match] of [['email', email], ['phone', phone]]) {
      const input = editor.querySelector(`[data-rf-field="${key}"]`);
      if (match && input && !input.value.trim()) {
        input.value = match[0]; input.dispatchEvent(new Event('input', { bubbles:true }));
        found.push(key === 'email' ? '邮箱' : '手机');
      }
    }
    feedback.textContent = found.length ? `已提取${found.join('和')}。请对照原文核实，再填写其他板块。` : '没有找到可提取的联系方式；请对照原文填写各板块。';
  });
  editor.addEventListener('cf:apply-document', event => {
    const data = { ...event.detail,
      custom_sections: customSections.map(section => ({ ...section })),
      photo:document.querySelector('#resume-photo-status')?.dataset.photo || '',
      hidden_sections:[...hidden], section_order:[...sectionOrder],
      size:stage.dataset.size || 'standard', accent:stage.dataset.accent || 'default',
      photo_position:stage.dataset.photoPosition || 'center' };
    for (const group of Object.keys(sections)) {
      const section = editor.querySelector(sections[group]);
      const needed = Math.max(data[group]?.length || 0, 1);
      while (section.querySelectorAll('.repeat-block').length > needed) section.querySelector('.repeat-block:last-of-type').remove();
      while (section.querySelectorAll('.repeat-block').length < needed) add(group);
      reindex(group);
    }
    loadLayout(data);
    renderSectionTabs(); activateSection(activeSection);
    editor.dispatchEvent(new CustomEvent('cf:load', { detail: { document:data, template:document.querySelector('#resume-template-quick').value } }));
    changed();
  });
})();
