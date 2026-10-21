(() => {
  let preference = document.documentElement.dataset.userTheme;
  if (!preference) {
    try { preference = localStorage.getItem('cf-theme'); } catch (_) { /* optional storage */ }
  }
  if (!['light', 'dark', 'system'].includes(preference)) preference = 'system';
  const media = window.matchMedia('(prefers-color-scheme: dark)');
  const apply = () => {
    document.documentElement.dataset.theme = preference === 'system'
      ? (media.matches ? 'dark' : 'light') : preference;
    document.documentElement.dataset.preference = preference;
  };
  window.cfTheme = (next) => { preference = next; apply(); };
  media.addEventListener('change', apply);
  apply();
})();
