/* Document workbench: native dialogs, local formatting, saved-state transitions. */
(() => {
  'use strict';
  const reducedMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
  const openDialog = dialog => { if (dialog && !dialog.open) dialog.showModal(); };
  document.addEventListener('click', event => {
    const opener = event.target.closest('[data-studio-open]');
    if (opener) openDialog(document.querySelector(`[data-studio-dialog="${opener.dataset.studioOpen}"]`));
    const closer = event.target.closest('[data-studio-close]');
    if (closer) closer.closest('dialog').close();
    if (event.target instanceof HTMLDialogElement) {
      const bounds = event.target.getBoundingClientRect();
      if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) event.target.close();
    }
    const preview = event.target.closest('[data-template-preview]');
    if (preview) openDialog(document.querySelector(`[data-template-preview-dialog="${preview.dataset.templatePreview}"]`));
  });
  // Scale actual document markup, not a generic cover illustration.
  const fitThumbnail = element => {
    const sheet = element.querySelector('.resume-doc');
    if (sheet && element.clientWidth) {
      const style = getComputedStyle(element);
      sheet.style.zoom = String((element.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight)) / 794);
    }
  };
  const thumbnails = new ResizeObserver(entries => entries.forEach(entry => fitThumbnail(entry.target)));
  document.querySelectorAll('[data-document-thumbnail]').forEach(element => { thumbnails.observe(element); fitThumbnail(element); });
  document.querySelector('[data-library-sort]')?.addEventListener('change', event => {
    const grid = document.querySelector('.document-library');
    const items = [...grid.querySelectorAll('[data-library-document]')];
    items.sort((a, b) => event.target.value === 'name'
      ? a.dataset.documentTitle.localeCompare(b.dataset.documentTitle, 'zh-CN')
      : Number(a.dataset.documentOrder) - Number(b.dataset.documentOrder));
    items.forEach(item => grid.insertBefore(item, grid.querySelector('.studio-new-document')));
  });
  const createDialog = document.querySelector('[data-create-dialog]');
  let createMode = 'blank';
  const setCreateMode = mode => {
    createMode = mode;
    createDialog.querySelectorAll('[data-create-mode]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.createMode === mode)));
    const source = createDialog.querySelector('[name="source"]');
    source.closest('label').hidden = mode !== 'paste';
    source.required = mode === 'paste'; source.minLength = mode === 'paste' ? 20 : 0;
    createDialog.querySelector('[data-create-submit]').textContent = mode === 'paste' ? 'AI 整理并创建 →' : '进入编辑器 →';
    createDialog.querySelector('[data-create-hint]').textContent = mode === 'paste'
      ? '点击后会进入工作台并启动 AI 整理，登录后继续，结果先核对再采用。'
      : '从空白字段开始填写，预览中的模板示例不会保存到你的简历。';
  };
  document.querySelectorAll('[data-create-resume]').forEach(button => button.addEventListener('click', () => {
    setCreateMode(button.dataset.createResume); openDialog(createDialog);
  }));
  createDialog?.querySelectorAll('[data-create-mode]').forEach(button => button.addEventListener('click', () => setCreateMode(button.dataset.createMode)));
  createDialog?.querySelector('form').addEventListener('submit', event => {
    event.preventDefault();
    const values = new FormData(event.target);
    const query = new URLSearchParams({view:'resume-new',title:String(values.get('title')).trim(),template:values.get('template')});
    if (createMode === 'paste') {
      try { sessionStorage.setItem('cf-studio-paste', JSON.stringify({source:String(values.get('source')).trim(),start:true})); }
      catch { createDialog.querySelector('[data-create-hint]').textContent = '浏览器暂时无法保留文本，请允许站点存储后重试。'; return; }
      query.set('start','paste');
    }
    location.href = `/workspace?${query}`;
  });
  const renameDialog = document.querySelector('[data-library-rename-dialog]');
  let renameId = null;
  document.querySelectorAll('[data-library-rename]').forEach(button => button.addEventListener('click', () => {
    renameId = button.dataset.libraryRename;
    renameDialog.querySelector('[name="title"]').value = button.dataset.resumeTitle;
    renameDialog.querySelector('[data-library-operation-status]').textContent = '';
    button.closest('details').open = false; openDialog(renameDialog);
  }));
  renameDialog?.querySelector('form').addEventListener('submit', async event => {
    event.preventDefault(); const button = event.target.querySelector('[type="submit"]'); button.disabled = true;
    const status = renameDialog.querySelector('[data-library-operation-status]');
    try {
      const response = await fetch(`/api/resumes/${renameId}`, {credentials:'same-origin',redirect:'error'});
      const resume = await response.json(); if (!response.ok) throw new Error(resume.error || '读取简历失败');
      await window.cfApi(`/api/resumes/${renameId}`, {request_key:crypto.randomUUID(),revision:resume.revision,title:event.target.elements.title.value.trim(),template:resume.template,document:resume.document});
      location.reload();
    } catch(error) { status.textContent = error.message; button.disabled = false; }
  });
  document.querySelectorAll('[data-library-copy]').forEach(button => button.addEventListener('click', async () => {
    button.disabled = true;
    try { await window.cfApi(`/api/resumes/${button.dataset.libraryCopy}/copy`, {request_key:crypto.randomUUID(),title:`${button.dataset.resumeTitle.slice(0,110)} · 副本`}); location.reload(); }
    catch(error) { document.querySelector('[data-list-feedback]').textContent = error.message; button.disabled = false; }
  }));
  const deleteDialog=document.querySelector('[data-library-delete-dialog]');
  let deleteId=null;
  document.addEventListener('click',event=>{
    const button=event.target.closest('.document-library [data-delete-resume]');
    if(!button)return;
    event.preventDefault();event.stopImmediatePropagation();
    deleteId=button.dataset.deleteResume;
    deleteDialog.querySelector('[data-library-delete-title]').textContent=button.closest('[data-library-document]').dataset.documentTitle;
    deleteDialog.querySelector('[data-library-delete-status]').textContent='';
    deleteDialog.querySelector('[data-library-delete-confirm]').disabled=false;
    button.closest('details').open=false;openDialog(deleteDialog);
  },true);
  deleteDialog?.querySelector('[data-library-delete-confirm]').addEventListener('click',async event=>{
    event.currentTarget.disabled=true;
    try{await window.cfApi(`/api/resumes/${deleteId}/delete`,{confirm:'delete'});location.reload();}
    catch(error){deleteDialog.querySelector('[data-library-delete-status]').textContent=error.message;deleteDialog.querySelector('[data-library-delete-confirm]').disabled=false;}
  });
  // Close document menus when another one is opened or focus leaves the menu.
  document.querySelectorAll('.document-menu').forEach(menu => {
    menu.addEventListener('toggle', () => { if(menu.open) document.querySelectorAll('.document-menu').forEach(other => { if(other !== menu) other.open = false; }); });
    menu.addEventListener('keydown', event => { if(event.key === 'Escape'){ menu.open = false; menu.querySelector('summary').focus(); } });
  });
  document.addEventListener('click', event => { if(!event.target.closest('.document-menu')) document.querySelectorAll('.document-menu').forEach(menu => {menu.open = false;}); });
  document.querySelectorAll('[data-demo-section]').forEach(button => button.addEventListener('click', () => {
    const root = button.closest('[data-landing-demo]');
    root.querySelectorAll('[data-demo-section]').forEach(other => other.setAttribute('aria-pressed', String(other === button)));
    root.querySelectorAll('.rd-section').forEach(section => section.classList.toggle('is-demo-highlight', section.dataset.rfSection === button.dataset.demoSection));
  }));
  document.querySelectorAll('[data-template-filter]').forEach(button => button.addEventListener('click', () => {
    document.querySelectorAll('[data-template-filter]').forEach(other => other.setAttribute('aria-pressed',String(other === button)));
    document.querySelectorAll('[data-template-kind]').forEach(item => {item.hidden = button.dataset.templateFilter !== 'all' && item.dataset.templateKind !== button.dataset.templateFilter;});
  }));
  const dropZone = document.querySelector('.file-drop');
  if (dropZone) {
    ['dragenter','dragover'].forEach(name => dropZone.addEventListener(name, event => {event.preventDefault(); dropZone.classList.add('is-drag-over');}));
    ['dragleave','drop'].forEach(name => dropZone.addEventListener(name, event => {event.preventDefault(); dropZone.classList.remove('is-drag-over');}));
    dropZone.addEventListener('drop', event => {const file = event.dataTransfer.files[0]; if(!file) return; const transfer = new DataTransfer(); transfer.items.add(file); const input = document.querySelector('#resume-file'); input.files = transfer.files; input.dispatchEvent(new Event('change',{bubbles:true}));});
  }
  const editor = document.querySelector('[data-resume-editor]');
  if (!editor) return;
  const ensureSaved = async () => {
    if (editor.dataset.resumeId && editor.dataset.dirty === 'false') return;
    document.querySelector('[data-save-resume]').click();
    const started = Date.now();
    while (Date.now() - started < 30000) {
      if (editor.dataset.resumeId && editor.dataset.dirty === 'false') return;
      const status = document.querySelector('#resume-draft-status').textContent;
      if (status.startsWith('保存失败')) throw new Error(status);
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    throw new Error('尚未完成保存。请先完成登录或重试保存，再继续。');
  };
  window.cfEnsureResumeSaved = ensureSaved;
  document.querySelector('[data-editor-analyze]').addEventListener('click', async event => {
    const button = event.currentTarget; button.disabled = true;
    try {await ensureSaved(); const dialog=document.querySelector('[data-studio-dialog="job"]');dialog.querySelector('[data-studio-job-source]').textContent=`${document.querySelector('#resume-title').value} · 第 ${editor.dataset.resumeRevision} 版`;openDialog(dialog);button.disabled=false;}
    catch(error){ document.querySelector('#resume-draft-status').textContent = error.message; button.disabled = false; }
  });
  const jobForm=document.querySelector('[data-studio-job-form]');
  let jobRequestKey=crypto.randomUUID();
  jobForm.addEventListener('input',()=>{jobRequestKey=crypto.randomUUID();});
  jobForm.addEventListener('submit',async event=>{
    event.preventDefault();const button=jobForm.querySelector('[type="submit"]');button.disabled=true;
    const status=jobForm.querySelector('[data-studio-job-status]');status.textContent='正在保存岗位并准备分析…';
    try{
      await ensureSaved();const data=new FormData(jobForm);
      const job=await window.cfApi('/api/jobs',{request_key:jobRequestKey,resume_id:Number(editor.dataset.resumeId),resume_revision:Number(editor.dataset.resumeRevision),title:data.get('title'),company:data.get('company'),description:data.get('description'),url:'',save_for_later:data.has('save_for_later')});
      location.href=`/jobs/${job.id}?start=analysis`;
    }catch(error){status.textContent=error.message;button.disabled=false;}
  });
  document.querySelector('[data-version-history]').addEventListener('click', () => openDialog(document.querySelector('[data-studio-dialog="history"]')));
  const designRoot=editor.querySelector('#resume-template');
  designRoot.querySelectorAll('[data-design-tab]').forEach(button=>button.addEventListener('click',()=>{
    designRoot.querySelectorAll('[data-design-tab]').forEach(other=>other.setAttribute('aria-pressed',String(other===button)));
    designRoot.querySelectorAll('[data-design-panel]').forEach(panel=>{panel.hidden=panel.dataset.designPanel!==button.dataset.designTab;});
  }));
  const syncDesign=()=>{
    const stage=editor.querySelector('[data-resume-stage]');
    designRoot.querySelectorAll('[data-design-accent]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.designAccent===stage.dataset.accent)));
    designRoot.querySelectorAll('[data-design-size]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.designSize===stage.dataset.size)));
    const host=designRoot.querySelector('[data-design-sections]');host.replaceChildren();
    editor.querySelectorAll('[data-sortable-section]').forEach(item=>{
      const key=item.dataset.sortableSection;
      const row=document.createElement('div');row.className='studio-design-section';
      const label=document.createElement('span');label.textContent=item.querySelector('[data-section-tab]').textContent;
      const original=editor.querySelector(`[data-tab-visibility="${key}"]`);
      if(!original)return;
      const toggle=document.createElement('button');toggle.type='button';toggle.textContent=original.getAttribute('aria-pressed')==='true'?'已显示':'已隐藏';toggle.setAttribute('aria-pressed',original.getAttribute('aria-pressed'));toggle.setAttribute('aria-label',`${label.textContent}显示状态`);toggle.addEventListener('click',()=>{original.click();syncDesign();});
      const up=document.createElement('button');up.type='button';up.textContent='↑';up.setAttribute('aria-label',`${label.textContent}上移`);
      const down=document.createElement('button');down.type='button';down.textContent='↓';down.setAttribute('aria-label',`${label.textContent}下移`);
      const source=editor.querySelector(`[data-editor-section="${key}"] [data-section-options]`);
      const moves=source?.querySelectorAll('.resume-tab-move');
      [up,down].forEach((button,index)=>{button.disabled=!moves?.[index]||moves[index].disabled;button.addEventListener('click',()=>{moves[index].click();syncDesign();});});
      row.append(label,toggle,up,down);host.append(row);
    });
  };
  designRoot.querySelectorAll('[data-design-accent]').forEach(button=>button.addEventListener('click',()=>{editor.querySelector(`[data-accent-choice="${button.dataset.designAccent}"]`).click();syncDesign();}));
  designRoot.querySelectorAll('[data-design-size]').forEach(button=>button.addEventListener('click',()=>{const size=editor.querySelector('#resume-size');size.value=button.dataset.designSize;size.dispatchEvent(new Event('change',{bubbles:true}));syncDesign();}));
  syncDesign();editor.addEventListener('cf:load',syncDesign);editor.addEventListener('cf:section-activate',syncDesign);
  document.querySelectorAll('[data-studio-tab]').forEach(button => button.addEventListener('click', () => {
    editor.querySelector(`[data-section-tab="${button.dataset.studioTab === 'design' ? 'template' : 'basics'}"]`).click();
  }));
  document.querySelector('[data-studio-login]')?.addEventListener('click', event => {
    if (window.cfRequireAuth) {event.preventDefault(); window.cfRequireAuth(async()=>{document.querySelector('[data-save-resume]').click();});}
  });
  // Keep native textareas and selections, with a small Markdown toolbar above them.
  const decorated = new WeakSet();
  const decorate = () => editor.querySelectorAll('textarea[data-rf-field]').forEach(input => {
    if (decorated.has(input)) return; decorated.add(input);
    const tools = document.createElement('div'); tools.className = 'studio-text-tools'; tools.setAttribute('role','group'); tools.setAttribute('aria-label','文本格式');
    for(const [label,mark,kind] of [['粗体','B','bold'],['斜体','I','italic'],['项目符号','☷','list'],['链接','↗','link']]){
      const button = document.createElement('button'); button.type='button'; button.textContent=mark; button.setAttribute('aria-label',label); button.title=label;
      button.addEventListener('click',()=>{
        const start=input.selectionStart,end=input.selectionEnd,text=input.value.slice(start,end);
        const replacement=kind==='bold'?`**${text || '文字'}**`:kind==='italic'?`*${text || '文字'}*`:kind==='link'?`[${text || '链接文字'}](https://example.com)`: (text || '条目').split('\n').map(line=>`- ${line}`).join('\n');
        input.setRangeText(replacement,start,end,'select'); input.dispatchEvent(new Event('input',{bubbles:true})); input.focus();
      }); tools.append(button);
    }
    const hint=document.createElement('span'); hint.textContent='支持 Markdown'; tools.append(hint); input.before(tools);
    const count=document.createElement('small'); count.className='studio-text-count';
    const updateCount=()=>{count.textContent=`${input.value.length} / ${input.maxLength}`;}; input.after(count); input.addEventListener('input',updateCount); editor.addEventListener('cf:load',updateCount);updateCount();
  });
  decorate();editor.addEventListener('cf:refresh',decorate);
  const navIcons={basics:'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8 M4 21v-2a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v2',photo:'M3 6h5l2-3h4l2 3h5v15H3z M12 17a4 4 0 1 0 0-8 4 4 0 0 0 0 8',experiences:'M3 7h18v14H3z M8 7V3h8v4 M3 12h18',education:'m2 9 10-6 10 6-10 6z M6 12v6l6 3 6-3v-6',projects:'M3 5h7l2 3h9v13H3z',skills:'m12 3-8 11h7l-1 7 10-12h-8z',template:'M3 3h18v18H3z M3 8h18 M9 8v13',default:'M5 3h14v18H5z M8 8h8 M8 12h8 M8 16h5'};
  const decorateNav = () => editor.querySelectorAll('[data-section-tab]').forEach(button => {
    if(button.querySelector('svg'))return;
    const label=button.textContent; button.textContent=''; const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('aria-hidden','true');
    const path=document.createElementNS('http://www.w3.org/2000/svg','path');path.setAttribute('d',navIcons[button.dataset.sectionTab]||navIcons.default);svg.append(path);const span=document.createElement('span');span.textContent=label;button.append(svg,span);
  });decorateNav();editor.addEventListener('cf:refresh',decorateNav);editor.addEventListener('cf:section-activate',decorateNav);
  // Native view transitions keep the paper anchored while its actual template changes.
  let transitioning=false;
  editor.addEventListener('change', event => {
    if (!event.target.matches('#resume-template-quick,[name="resume-template"]') || !document.startViewTransition || reducedMotion() || transitioning) return;
    event.stopImmediatePropagation();
    const target=event.target; transitioning=true;
    document.startViewTransition(()=>target.dispatchEvent(new Event('change',{bubbles:true}))).finished.finally(()=>{transitioning=false;});
  },true);
  const historyDialog=document.querySelector('[data-studio-dialog="history"]');
  historyDialog.addEventListener('click',event=>{if(event.target.closest('#version-history button')) historyDialog.close();});
  let paste=null;
  try{paste=JSON.parse(sessionStorage.getItem('cf-studio-paste')||'null');sessionStorage.removeItem('cf-studio-paste');}catch{}
  const source=document.querySelector('#resume-source-text');
  if(paste?.source) source.value=paste.source;
  if(new URLSearchParams(location.search).get('start')==='paste'||source.value){openDialog(document.querySelector('[data-studio-dialog="source"]'));if(paste?.start) requestAnimationFrame(()=>document.querySelector('[data-compose-resume]').click());}
  // Scroll spy changes only navigation state; it never modifies resume data.
  const fields=editor.querySelector('.resume-fields');
  const basics=editor.querySelector('#resume-basics'), photo=editor.querySelector('#resume-photo-section');
  if (basics && photo) basics.after(photo);
  // The divider resizes the real editor/preview panes, including keyboard control.
  const divider=document.createElement('button'); divider.type='button'; divider.className='studio-splitter';
  divider.setAttribute('role','separator'); divider.setAttribute('aria-orientation','vertical'); divider.setAttribute('aria-label','调整内容与预览宽度');
  divider.setAttribute('aria-valuemin','28'); divider.setAttribute('aria-valuemax','65');
  editor.append(divider);
  let fraction=.45;
  try {const value=Number(localStorage.getItem('cf-editor-split')); if(value>=.28 && value<=.65)fraction=value;}catch{}
  const placeDivider=()=>{divider.style.left=`${fields.getBoundingClientRect().right-editor.getBoundingClientRect().left-3}px`;};
  const resizePanes=value=>{
    fraction=Math.max(.28,Math.min(.65,value));
    if(innerWidth>760){const available=editor.clientWidth-(innerWidth>960?66:58);const width=Math.max(290,Math.min(available-290,available*fraction));editor.style.gridTemplateColumns=`${innerWidth>960?66:58}px minmax(0,${width}px) minmax(0,1fr)`;}
    else editor.style.gridTemplateColumns='';
    divider.setAttribute('aria-valuenow',String(Math.round(fraction*100)));placeDivider();
  };
  divider.addEventListener('pointerdown',event=>{divider.setPointerCapture(event.pointerId);editor.classList.add('is-resizing');});
  divider.addEventListener('pointermove',event=>{if(!divider.hasPointerCapture(event.pointerId))return;const bounds=editor.getBoundingClientRect();resizePanes((event.clientX-bounds.left-66)/(bounds.width-66));});
  divider.addEventListener('pointerup',event=>{divider.releasePointerCapture(event.pointerId);editor.classList.remove('is-resizing');try{localStorage.setItem('cf-editor-split',String(fraction));}catch{}});
  divider.addEventListener('lostpointercapture',()=>editor.classList.remove('is-resizing'));
  divider.addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();resizePanes(event.key==='Home'?.28:event.key==='End'?.65:fraction+(event.key==='ArrowRight'?.02:-.02));try{localStorage.setItem('cf-editor-split',String(fraction));}catch{}});
  const paneObserver=new ResizeObserver(()=>placeDivider());paneObserver.observe(fields);window.addEventListener('resize',()=>resizePanes(fraction));resizePanes(fraction);
  const spy=new IntersectionObserver(entries=>{
    if(editor.dataset.studioMode!=='content') return;
    const visible=entries.filter(entry=>entry.isIntersecting).sort((a,b)=>a.boundingClientRect.top-b.boundingClientRect.top)[0];
    if(!visible)return;
    const current=visible.target.dataset.editorSection || (visible.target.id==='resume-basics'?'basics':'photo');
    editor.querySelectorAll('[data-section-tab]').forEach(button=>{button.classList.toggle('is-active',button.dataset.sectionTab===current);button.setAttribute('aria-current',button.dataset.sectionTab===current?'step':'false');});
  },{root:fields,rootMargin:'0px 0px -65% 0px'});
  const observeSections=()=>fields.querySelectorAll('.editor-section,.resume-photo-editor').forEach(section=>spy.observe(section));observeSections();editor.addEventListener('cf:refresh',observeSections);
})();
