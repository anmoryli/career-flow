document.addEventListener('alpine:init', () => {
  Alpine.data('shell', () => ({
    init() {
      document.querySelector('#theme-select').value = document.documentElement.dataset.preference;
    },
    async changeTheme(event) {
      const theme = event.target.value;
      window.cfTheme(theme);
      try { localStorage.setItem('cf-theme', theme); } catch (_) { /* optional storage */ }
      if (document.body.dataset.authenticated !== 'yes') return;
      const feedback = document.querySelector('#theme-feedback');
      try {
        const response = await fetch('/settings/theme', {
          method: 'POST', credentials: 'same-origin', redirect: 'error',
          headers: { 'Content-Type': 'application/json',
            'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content },
          body: JSON.stringify({ theme }),
        });
        if (!response.ok) throw new Error('sync');
        feedback.textContent = '外观偏好已同步';
      } catch (_) { feedback.textContent = '已在本机切换，跨设备同步暂未完成'; }
      feedback.hidden = false;
      window.setTimeout(() => { feedback.hidden = true; }, 3500);
    },
  }));
});
document.addEventListener('submit', (event) => {
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
