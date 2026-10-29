/* Apply the account/system theme before first paint. */
(() => {
  const root=document.documentElement;
  const allowed=new Set(['light','dark','system']);
  let preference=root.dataset.userTheme;
  if(!allowed.has(preference)) {try {preference=localStorage.getItem('cf-theme');}catch{}}
  if(!allowed.has(preference)) preference='system';
  const media=matchMedia('(prefers-color-scheme: dark)');
  const apply=()=>{root.dataset.preference=preference;root.dataset.theme=preference==='system'?(media.matches?'dark':'light'):preference;};
  window.cfTheme=value=>{if(allowed.has(value)){preference=value;apply();}};
  media.addEventListener('change',apply);apply();
})();
