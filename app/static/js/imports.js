(() => {
  const fileInput = document.querySelector('#resume-file');
  const upload = document.querySelector('[data-upload-pdf]');
  let uploadKey = crypto.randomUUID();
  fileInput?.addEventListener('change', () => {
    uploadKey = crypto.randomUUID();
    const status = document.querySelector('#file-selection');
    if (!status) return;
    status.hidden = false;
    const file = fileInput.files[0];
    status.textContent = file ? `${file.name} · ${(file.size / 1024 / 1024).toFixed(2)} MB` : '尚未选择文件';
  });
  const submitUpload = async () => {
    const status = document.querySelector('#file-selection'); status.hidden = false;
    const file = fileInput.files[0];
    if (file && !file.name.toLowerCase().endsWith('.pdf')) { status.textContent = '请选择 PDF 格式的简历文件'; return; }
    if (!file || file.size > 4 * 1024 * 1024) { status.textContent = '请选择不超过 4 MB 的 PDF'; return; }
    upload.disabled = true;
    const payload = new FormData(); payload.set('file', file); payload.set('request_key', uploadKey);
    try {
      const response = await fetch('/api/imports', { method: 'POST', body: payload, redirect: 'error',
        headers: { 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content } });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || '上传失败');
      const query = new URLSearchParams({ title: result.title || '导入的简历' });
      const resumeId = new URLSearchParams(location.search).get('resume_id');
      if (resumeId) query.set('resume_id', resumeId);
      location.href = `/imports/${result.id}?${query}`;
    } catch (error) { status.textContent = error.message; upload.disabled = false; }
  };
  upload?.addEventListener('click', () => {
    if (document.body.dataset.authenticated !== 'yes' && window.cfRequireAuth) {
      if (!fileInput.files[0]) { const status = document.querySelector('#file-selection'); status.hidden = false; status.textContent = '请先选择一份 PDF 简历'; return; }
      window.cfRequireAuth(submitUpload);
      return;
    }
    submitUpload();
  });
  const root = document.querySelector('[data-import-id]');
  if (!root) return;
  const feedback = document.querySelector('#import-feedback');
  if (['queued', 'running'].includes(root.dataset.importState)) {
    const timer = setInterval(async () => {
      try {
        const response = await fetch(`/api/imports/${root.dataset.importId}`, { redirect: 'error' });
        if (!response.ok) throw new Error('读取解析状态失败，请刷新重试');
        const result = await response.json();
        if (!['queued', 'running'].includes(result.state)) { clearInterval(timer); location.reload(); }
      } catch (error) { clearInterval(timer); feedback.textContent = error.message; }
    }, 2000);
  }
  const form = root.querySelector('[data-import-confirm]');
  let key = crypto.randomUUID();
  form?.addEventListener('input', () => { key = crypto.randomUUID(); });
  form?.addEventListener('submit', async event => {
    event.preventDefault(); const button = form.querySelector('button'); button.disabled = true;
    const data = Object.fromEntries(new FormData(form)); const title = data.title; delete data.title;
    const revision = Number(data.revision || 0); delete data.revision;
    data.confirmed = 'yes'; delete data.confirmed;
    try {
      const result = await window.cfApi(`/api/imports/${root.dataset.importId}/confirm`, {
        request_key: key, title, revision, confirmed: 'yes', resume_id: root.dataset.resumeId || undefined, document: data,
      });
      const extracted = root.querySelector('.import-extracted')?.textContent;
      if (extracted) sessionStorage.setItem('cf-import-source', extracted.slice(0, 12000));
      location.href = `/workspace?view=resume-new&resume_id=${result.id}`;
    } catch (error) { feedback.textContent = error.message; button.disabled = false; }
  });
})();
