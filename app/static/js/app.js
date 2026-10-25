document.addEventListener('alpine:init', () => {
  Alpine.data('shell', () => ({
    init() {
      const selector = document.querySelector('#theme-select');
      if (selector) selector.value = document.documentElement.dataset.preference;
      refreshThemeChoices(document.documentElement.dataset.preference);
    },
    async changeTheme(event) {
      const theme = event.target.value;
      window.cfTheme(theme);
      refreshThemeChoices(theme);
      try { localStorage.setItem('cf-theme', theme); } catch (_) { /* optional storage */ }
      if (document.body.dataset.authenticated !== 'yes') return;
      const feedback = document.querySelector('#theme-feedback');
      try {
        const response = await fetch('/settings/theme', {
          method: 'POST', credentials: 'same-origin', redirect: 'error', keepalive: true,
          headers: { 'Content-Type': 'application/json',
            'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content },
          body: JSON.stringify({ theme }),
        });
        if (!response.ok) throw new Error('sync');
        feedback.textContent = '外观偏好已同步';
      } catch (_) { feedback.textContent = '已在本机切换，跨设备同步暂未完成'; }
      const status = document.querySelector('#settings-theme-status');
      if (status) status.textContent = feedback.textContent;
      feedback.hidden = false;
      window.setTimeout(() => { feedback.hidden = true; }, 3500);
    },
  }));
});
document.addEventListener('submit', (event) => {
  if (event.target.matches('[data-ui-form]')) return;
  const button = event.target.querySelector('button[type="submit"]');
  if (button) { button.disabled = true; button.setAttribute('aria-busy', 'true'); }
});
document.addEventListener('htmx:configRequest', (event) => {
  event.detail.headers['X-CSRFToken'] = document.querySelector('meta[name="csrf-token"]').content;
});
window.addEventListener('pageshow', () => {
  document.querySelectorAll('button[aria-busy="true"]').forEach((button) => {
    button.disabled = false; button.removeAttribute('aria-busy');
  });
});

function refreshThemeChoices(theme) {
  document.querySelectorAll('[data-theme-choice]').forEach(button => {
    button.setAttribute('aria-pressed', String(button.dataset.themeChoice === theme));
  });
}

document.querySelectorAll('[data-theme-choice]').forEach(button => {
  button.addEventListener('click', () => {
    const selector = document.querySelector('#theme-select');
    if (!selector) return;
    selector.value = button.dataset.themeChoice;
    selector.dispatchEvent(new Event('change', { bubbles: true }));
  });
});

(() => {
  const sidebar = document.querySelector('#workbench-sidebar');
  if (!sidebar) return;
  const main = document.querySelector('#workbench-main');
  const opener = document.querySelector('[data-sidebar-open]');
  const backdrop = document.querySelector('.sidebar-backdrop');
  const collapse = document.querySelector('[data-sidebar-collapse]');
  const mobile = matchMedia('(max-width: 760px)');
  let lastFocus = null;
  const focusables = () => Array.from(sidebar.querySelectorAll('a,button,select,input')).filter(
    element => !element.disabled && element.getClientRects().length > 0
  );
  const close = (restoreFocus = true) => {
    document.body.classList.remove('nav-open');
    backdrop.hidden = true;
    main.inert = false;
    sidebar.removeAttribute('role');
    sidebar.removeAttribute('aria-modal');
    opener.setAttribute('aria-expanded', 'false');
    if (restoreFocus && lastFocus?.getClientRects().length) lastFocus.focus();
  };
  opener.addEventListener('click', () => {
    if (!mobile.matches) return;
    lastFocus = document.activeElement;
    document.body.classList.add('nav-open');
    backdrop.hidden = false;
    main.inert = true;
    sidebar.setAttribute('role', 'dialog');
    sidebar.setAttribute('aria-modal', 'true');
    opener.setAttribute('aria-expanded', 'true');
    focusables()[0]?.focus();
  });
  document.querySelectorAll('[data-sidebar-close]').forEach(button => {
    button.addEventListener('click', () => close());
  });
  document.addEventListener('keydown', event => {
    if (!document.body.classList.contains('nav-open')) return;
    if (event.key === 'Escape') { event.preventDefault(); close(); }
    if (event.key !== 'Tab') return;
    const targets = focusables();
    const first = targets[0]; const last = targets[targets.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
    if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
  });
  sidebar.querySelectorAll('a').forEach(link => link.addEventListener('click', () => close(false)));
  mobile.addEventListener('change', () => close(false));
  const setCollapsed = collapsed => {
    document.body.classList.toggle('sidebar-collapsed', collapsed);
    collapse.setAttribute('aria-expanded', String(!collapsed));
    collapse.setAttribute('aria-label', collapsed ? '展开侧栏' : '折叠侧栏');
  };
  try { setCollapsed(sessionStorage.getItem('cf-sidebar-collapsed') === 'yes'); } catch (_) { /* optional UI preference */ }
  collapse.addEventListener('click', () => {
    const collapsed = !document.body.classList.contains('sidebar-collapsed');
    setCollapsed(collapsed);
    try { sessionStorage.setItem('cf-sidebar-collapsed', collapsed ? 'yes' : 'no'); } catch (_) { /* optional UI preference */ }
  });
})();

(() => {
  const search = document.querySelector('#history-search');
  if (!search) return;
  let category = 'all';
  const rows = Array.from(document.querySelectorAll('[data-history-row]'));
  const update = () => {
    const term = search.value.trim().toLocaleLowerCase();
    let visible = 0;
    rows.forEach(row => {
      const matches = (category === 'all' || row.dataset.recordType === category)
        && row.dataset.recordTitle.includes(term);
      row.hidden = !matches;
      if (matches) visible++;
    });
    document.querySelector('#history-empty').hidden = visible > 0;
    document.querySelector('.history-table-head').hidden = visible === 0;
  };
  document.querySelectorAll('[data-history-filter]').forEach(button => {
    button.addEventListener('click', () => {
      category = button.dataset.historyFilter;
      document.querySelectorAll('[data-history-filter]').forEach(item => {
        item.classList.toggle('is-active', item === button);
        item.setAttribute('aria-pressed', String(item === button));
      });
      update();
    });
  });
  search.addEventListener('input', update);
  update();
})();

(() => {
  const editor = document.querySelector('[data-resume-editor]');
  if (!editor) return;
  const stage = document.querySelector('[data-resume-stage]');
  const emptyHint = document.querySelector('[data-resume-empty]');
  const draftStatus = document.querySelector('#resume-draft-status');
  const photoStatus = document.querySelector('#resume-photo-status');
  const data = {};
  let sampleActive = !JSON.parse(editor.dataset.saved || "null");
  const example = JSON.parse(stage.dataset.example);
  let previewData = example;
  const previewMode = document.querySelector('#resume-preview-mode');
  const contactKeys = ['phone', 'email', 'city', 'website', 'github', 'linkedin'];

  const getPath = (root, path) => path.split('.').reduce(
    (value, part) => (value == null ? value : value[/^\d+$/.test(part) ? Number(part) : part]),
    root,
  );
  const setPath = (root, path, value) => {
    const parts = path.split('.');
    let current = root;
    parts.forEach((part, index) => {
      const key = /^\d+$/.test(part) ? Number(part) : part;
      if (index === parts.length - 1) { current[key] = value; return; }
      if (current[key] == null) current[key] = /^\d+$/.test(parts[index + 1]) ? [] : {};
      current = current[key];
    });
  };
  const flatten = value => {
    if (typeof value === 'string') return [value];
    if (Array.isArray(value)) return value.flatMap(flatten);
    if (value && typeof value === 'object') return Object.values(value).flatMap(flatten);
    return [];
  };
  const hasText = value => flatten(value).some(item => typeof item === 'string' && item.trim());
  const splitLines = value => value.split('\n').map(item => item.trim()).filter(Boolean);
  const splitItems = value => value.split(/[,，、]/).map(item => item.trim()).filter(Boolean);
  const read = (input, path) => {
    const value = input.value.trim();
    if (path.endsWith('.bullets') || path === 'certificates' || path === 'languages') {
      return splitLines(value);
    }
    if (path.endsWith('.items')) return splitItems(value);
    return value;
  };
  const hasContent = path => {
    if (path === 'contacts') return contactKeys.some(key => (previewData[key] || '').trim());
    if (path === 'skills' || path.startsWith('skills.')) {
      const groups = path === 'skills' ? (previewData.skills || []) : [getPath(previewData, path)];
      return groups.some(group => group && Array.isArray(group.items) && group.items.length);
    }
    return hasText(getPath(previewData, path));
  };
  const fill = () => {
    Object.keys(data).forEach(key => { delete data[key]; });
    editor.querySelectorAll('[data-rf-field]').forEach(input => {
      setPath(data, input.dataset.rfField, read(input, input.dataset.rfField));
    });
    if (photoStatus && photoStatus.dataset.photo) data.photo = photoStatus.dataset.photo;
  };
  const paint = () => {
    previewData = sampleActive ? example : data;
    stage.dataset.previewMode = sampleActive ? 'sample' : 'draft';
    if (previewMode) previewMode.value = stage.dataset.previewMode;
    const scope = stage || document;
    const order = JSON.parse(editor.dataset.sectionOrder || '[]');
    scope.querySelectorAll('[data-section-flow]').forEach(flow => {
      order.forEach(key => {
        const section = flow.querySelector(`[data-rf-section="${key}"]`);
        if (section) flow.append(section);
      });
    });
    scope.querySelectorAll('[data-rf-photo]').forEach(image => {
      const source = previewData.photo || '';
      if (source) image.src = source;
      else image.removeAttribute('src');
      image.hidden = !source;
    });
    scope.querySelectorAll('[data-photo-placeholder]').forEach(element => {
      element.hidden = Boolean(previewData.photo);
    });
    scope.querySelectorAll('[data-rf]').forEach(element => {
      const value = getPath(previewData, element.dataset.rf);
      const text = Array.isArray(value) ? value.join('、') : (value || '');
      element.textContent = text;
      element.hidden = !String(text).trim();
    });
    scope.querySelectorAll('[data-rf-list]').forEach(element => {
      const value = getPath(previewData, element.dataset.rfList);
      const items = Array.isArray(value) ? value : [];
      const mode = element.dataset.rfListMode || 'lines';
      element.replaceChildren();
      items.forEach(item => {
        const node = document.createElement(mode === 'inline' || mode === 'tags' ? 'span' : 'li');
        node.textContent = item;
        element.appendChild(node);
      });
    });
    scope.querySelectorAll('[data-rf-if]').forEach(element => {
      element.hidden = !hasContent(element.dataset.rfIf);
    });
    scope.querySelectorAll('[data-rf-entry]').forEach(element => {
      element.hidden = !hasContent(element.dataset.rfEntry);
    });
    scope.querySelectorAll('[data-rf-section]').forEach(element => {
      const hidden = sampleActive ? [] : JSON.parse(editor.dataset.hiddenSections || '[]');
      element.hidden = !hasContent(element.dataset.rfSection) || hidden.includes(element.dataset.rfSection);
    });
    scope.querySelectorAll('[data-rf-initial]').forEach(element => {
      const initial = String(getPath(previewData, element.dataset.rfInitial) || '').trim().slice(0, 1);
      element.textContent = initial;
      element.hidden = !initial;
    });
    if (emptyHint) {
      const core = ['name', 'role', 'summary'].some(key => (previewData[key] || '').trim());
      emptyHint.hidden = core || hasContent('experiences') || hasContent('projects') || hasContent('education') || hasContent('skills');
    }
  };
  const update = () => {
    sampleActive = false;
    fill();
    paint();
    if (draftStatus) draftStatus.textContent = '正在保存…';
    editor.dispatchEvent(new CustomEvent('cf:change', { detail: { ...data } }));
  };
  fill();
  paint();
  if (previewMode) previewMode.addEventListener('change', () => {
    sampleActive = previewMode.value === 'sample';
    fill();
    paint();
  });
  editor.addEventListener('input', event => { if (event.target.matches('[data-rf-field]')) update(); });
  editor.addEventListener('cf:refresh', update);
  editor.addEventListener('cf:load', event => {
    const documentData = event.detail.document;
    editor.querySelectorAll('[data-rf-field]').forEach(input => {
      const value = getPath(documentData, input.dataset.rfField);
      input.value = Array.isArray(value) ? value.join(input.dataset.rfField.endsWith('.items') ? '?' : '\n') : (value || '');
    });
    applyPhoto(documentData.photo || '');
    switchTemplate(event.detail.template);
    sampleActive = false; fill(); paint();
  });
  const clearButton = document.querySelector('[data-clear-sample]');
  if (clearButton) {
    clearButton.addEventListener('click', () => {
      if (!window.confirm('确认清空当前填写？保存后仍可从版本历史恢复。')) return;
      editor.querySelectorAll('[data-rf-field]').forEach(input => { input.value = ''; });
      photoGeneration++;
      applyPhoto('');
      if (photoInput) photoInput.value = '';
      if (photoStatus) photoStatus.textContent = '照片已清除，保存时同步到账号。';
      sampleActive = false;
      update();
      if (draftStatus) draftStatus.textContent = '空白草稿 · 尚未保存';
    });
  }

  const switchTemplate = value => {
    if (!stage) return;
    if (!['classic', 'technical', 'modern'].includes(value)) return;
    stage.dataset.activeTemplate = value;
    const quickSelect = document.querySelector('#resume-template-quick');
    if (quickSelect) quickSelect.value = value;
    document.querySelectorAll('[name="resume-template"]').forEach(input => {
      input.checked = input.value === value;
    });
    document.querySelectorAll('[data-resume-panel]').forEach(panel => {
      panel.hidden = panel.dataset.resumePanel !== value;
    });
    document.querySelectorAll('[data-template-card]').forEach(card => {
      card.classList.toggle('is-selected', card.dataset.templateCard === value);
    });
  };
  document.querySelectorAll('[name="resume-template"]').forEach(input => {
    input.addEventListener('change', () => switchTemplate(input.value));
  });
  const activeTemplate = document.querySelector('[name="resume-template"]:checked');
  if (activeTemplate) switchTemplate(activeTemplate.value);
  const quickSelect = document.querySelector('#resume-template-quick');
  if (quickSelect) quickSelect.addEventListener('change', () => switchTemplate(quickSelect.value));

  const size = document.querySelector('#resume-size');
  if (size) size.addEventListener('change', () => { if (stage) stage.dataset.size = size.value; });
  document.querySelectorAll('[data-accent-choice]').forEach(button => {
    button.addEventListener('click', () => {
      if (stage) stage.dataset.accent = button.dataset.accentChoice;
      document.querySelectorAll('[data-accent-choice]').forEach(item => {
        item.setAttribute('aria-pressed', String(item === button));
      });
    });
  });

  const photoInput = document.querySelector('#resume-photo');
  const photoControl = document.querySelector('[data-photo-control-image]');
  const photoControlEmpty = document.querySelector('[data-photo-control-placeholder]');
  const photoRemove = document.querySelector('[data-remove-photo]');
  let photoGeneration = 0;
  const applyPhoto = source => {
    (stage || document).querySelectorAll('[data-rf-photo]').forEach(image => {
      if (source) image.src = source;
      else image.removeAttribute('src');
      image.hidden = !source;
    });
    (stage || document).querySelectorAll('[data-photo-placeholder]').forEach(element => {
      element.hidden = Boolean(source);
    });
    if (photoControl) {
      if (source) photoControl.src = source;
      else photoControl.removeAttribute('src');
      photoControl.hidden = !source;
    }
    if (photoControlEmpty) photoControlEmpty.hidden = Boolean(source);
    if (photoRemove) photoRemove.disabled = !source;
    if (photoStatus) {
      if (source) photoStatus.dataset.photo = source;
      else delete photoStatus.dataset.photo;
    }
  };
  // 照片在浏览器内压缩：目标约 400 KB、边长 1200px以内，质量阶梯从视觉无损的
  // 0.95 开始递减，普通手机照片一般落在几百 KB；小图不重新编码保留原画质。
  const PHOTO_TARGET = 400 * 1024;
  const PHOTO_MAX_EDGE = 1200;
  const shrinkPhoto = (source, image) => {
    const data = source.split(',')[1] || '';
    const bytes = Math.floor(data.length * 3 / 4);
    const edge = Math.max(image.naturalWidth, image.naturalHeight);
    if (bytes <= PHOTO_TARGET && edge <= PHOTO_MAX_EDGE) {
      return { source, width: image.naturalWidth, height: image.naturalHeight, compressed: false };
    }
    const scale = Math.min(1, PHOTO_MAX_EDGE / edge);
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(image.naturalWidth * scale);
    canvas.height = Math.round(image.naturalHeight * scale);
    canvas.getContext('2d').drawImage(image, 0, 0, canvas.width, canvas.height);
    for (const quality of [0.95, 0.9, 0.85, 0.8]) {
      const out = canvas.toDataURL('image/jpeg', quality);
      const outBytes = Math.floor((out.split(',')[1] || '').length * 3 / 4);
      if (outBytes <= PHOTO_TARGET) {
        return { source: out, width: canvas.width, height: canvas.height, compressed: true };
      }
    }
    // 极少出现：即便 0.8 质量仍超标的超大图，继续缩小尺寸直到达标。
    for (let scale = 0.8; scale >= 0.3; scale -= 0.1) {
      const width = Math.round(canvas.width * scale);
      const height = Math.round(canvas.height * scale);
      const small = document.createElement('canvas');
      small.width = width; small.height = height;
      small.getContext('2d').drawImage(canvas, 0, 0, width, height);
      const out = small.toDataURL('image/jpeg', 0.85);
      const outBytes = Math.floor((out.split(',')[1] || '').length * 3 / 4);
      if (outBytes <= PHOTO_TARGET) {
        return { source: out, width, height, compressed: true };
      }
    }
    throw new Error('too-large');
  };
  const photoFeedback = (message, tone) => {
    if (!photoStatus) return;
    photoStatus.dataset.tone = tone;
    photoStatus.textContent = message;
  };
  if (photoInput) {
    photoInput.addEventListener('change', async () => {
      const generation = ++photoGeneration;
      const file = photoInput.files[0];
      if (!file) return;
      const types = new Set(['image/jpeg', 'image/png', 'image/webp']);
      if (!types.has(file.type)) {
        photoFeedback('\u8bf7\u9009\u62e9 JPG\u3001PNG \u6216 WebP \u56fe\u7247\uff1b\u539f\u6709\u7167\u7247\u5df2\u4fdd\u7559\u3002', 'error');
        photoInput.value = '';
        return;
      }
      photoFeedback('\u6b63\u5728\u8bfb\u53d6\u7167\u7247\u2026', 'info');
      try {
        const source = await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result);
          reader.onerror = reject;
          reader.readAsDataURL(file);
        });
        const decoded = new Image();
        decoded.src = source;
        await decoded.decode();
        if (generation !== photoGeneration) return;
        if (decoded.naturalWidth < 96 || decoded.naturalHeight < 96
            || Math.max(decoded.naturalWidth, decoded.naturalHeight) > 8000) {
          throw new Error('dimensions');
        }
        const result = shrinkPhoto(source, decoded);
        if (generation !== photoGeneration) return;
        applyPhoto(result.source);
        photoFeedback(
          `\u5df2\u8f7d\u5165 ${file.name} \u00b7 ${result.width} \u00d7 ${result.height}`
          + `${result.compressed ? '\uff08\u5df2\u538b\u7f29\uff09' : ''}\u3002\u4fdd\u5b58\u7b80\u5386\u65f6\u540c\u6b65\u5230\u8d26\u53f7\u3002`,
          'info',
        );
        update();
      } catch (_) {
        if (generation === photoGeneration) {
          photoFeedback(
            '\u7167\u7247\u5904\u7406\u5931\u8d25\uff0c\u8bf7\u9009\u62e9\u53ef\u89e3\u7801\u3001\u8fb9\u957f\u4e0d\u5c0f\u4e8e 96 \u50cf\u7d20\u4e14\u8fb9\u957f\u4e0d\u8d85\u8fc7 8000 \u50cf\u7d20\u7684\u56fe\u7247\uff1b\u539f\u6709\u7167\u7247\u5df2\u4fdd\u7559\u3002',
            'error',
          );
        }
      }
    });
  }
  if (photoRemove) photoRemove.addEventListener('click', () => {
    photoGeneration++;
    applyPhoto('');
    if (photoInput) photoInput.value = '';
    photoStatus.textContent = '照片已移除，三套模板的照片区域已恢复。';
    update();
  });
  const photoPosition = document.querySelector('#resume-photo-position');
  if (photoPosition) photoPosition.addEventListener('change', () => {
    if (stage) stage.dataset.photoPosition = photoPosition.value;
  });
  // ResizeObserver keeps the whole A4 page visible without an overflowing preview.
  const fitDocuments = () => {
    if (stage && stage.clientWidth) {
      const scale = Math.min(stage.clientWidth / 794, 1);
      stage.querySelectorAll('.resume-panel').forEach(panel => { panel.style.zoom = String(scale); });
    }
    document.querySelectorAll('.template-choice-preview').forEach(preview => {
      const thumbnail = preview.querySelector('.template-thumb');
      if (thumbnail && preview.clientWidth) thumbnail.style.zoom = String(preview.clientWidth / 794);
    });
  };
  const sizing = new ResizeObserver(fitDocuments);
  if (stage) sizing.observe(stage);
  document.querySelectorAll('.template-choice-preview').forEach(element => sizing.observe(element));
  fitDocuments();

  const switchView = view => {
    editor.dataset.editorView = view;
    document.querySelectorAll('[data-editor-tab]').forEach(button => {
      const active = button.dataset.editorTab === view;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', String(active));
    });
  };
  document.querySelectorAll('[data-editor-tab]').forEach(button => {
    button.addEventListener('click', () => switchView(button.dataset.editorTab));
  });
  const previewButton = document.querySelector('[data-editor-preview]');
  if (previewButton) {
    previewButton.addEventListener('click', () => {
      switchView('preview');
      document.querySelector('.resume-preview-panel').scrollIntoView({ block: 'start', behavior: 'instant' });
    });
  }
  const expandButton = document.querySelector('[data-preview-expand]');
  const previewPanel = document.querySelector('.resume-preview-panel');
  const setExpanded = expanded => {
    if (!previewPanel || !expandButton) return;
    previewPanel.classList.toggle('is-expanded', expanded);
    document.body.classList.toggle('preview-expanded', expanded);
    expandButton.setAttribute('aria-pressed', String(expanded));
    expandButton.textContent = expanded ? '退出放大' : '放大预览';
  };
  if (expandButton) {
    expandButton.addEventListener('click', () => setExpanded(!previewPanel.classList.contains('is-expanded')));
  }
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && previewPanel?.classList.contains('is-expanded')) setExpanded(false);
  });
  const printButton = document.querySelector('[data-print-resume]');
  if (printButton) {
    printButton.addEventListener('click', () => {
      if (sampleActive && !window.confirm('当前预览为虚构模板示例，确认打印示例吗？打印自己的简历请切换到“我的填写”。')) return;
      if (!sampleActive && (!data.name || (!data.phone && !data.email)) &&
          !window.confirm('姓名或联系方式尚未填写完整，仍要打印当前内容吗？')) return;
      window.print();
    });
  }
  editor.dispatchEvent(new CustomEvent('cf:ready'));
})();

(() => {
  const input = document.querySelector('#resume-file');
  if (!input) return;
  input.addEventListener('change', async () => {
    const status = document.querySelector('#file-selection');
    const file = input.files[0];
    if (!file) { status.hidden = true; return; }
    status.hidden = false;
    status.textContent = '正在检查所选文件…';
    try {
      const header = new TextDecoder().decode(await file.slice(0, 5).arrayBuffer());
      status.textContent = header === '%PDF-'
        ? `已选择 ${file.name}（${Math.ceil(file.size / 1024)} KB）。文件仍在本机，尚未上传或解析。`
        : '所选文件不是可识别的 PDF，请重新选择一份 PDF 文件。';
    } catch (_) { status.textContent = '无法读取文件信息，请重新选择。'; }
  });
})();

(() => {
  const form = document.querySelector('[data-ui-form="job"]');
  if (!form) return;
  const description = document.querySelector('#job-description');
  description.addEventListener('input', () => {
    document.querySelector('#jd-character-count').textContent = `${description.value.length} 字`;
  });
  form.addEventListener('submit', event => {
    event.preventDefault();
    if (!description.value.trim()) { description.setCustomValidity('请先粘贴完整的岗位描述。'); description.reportValidity(); return; }
    description.setCustomValidity('');
    document.querySelector('#review-job-title').textContent = document.querySelector('#job-title').value.trim() || '未填写岗位名称';
    document.querySelector('#review-job-company').textContent = document.querySelector('#job-company').value.trim() || '未填写公司名称';
    document.querySelector('#review-job-description').textContent = description.value;
    const review = document.querySelector('#job-review');
    review.hidden = false;
    review.scrollIntoView({ block: 'start', behavior: 'instant' });
  });
  description.addEventListener('input', () => description.setCustomValidity(''));
})();
