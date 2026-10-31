(() => {
 'use strict';
 document.querySelectorAll('[data-copy-link]').forEach(button=>{let timer;button.addEventListener('click',async()=>{const input=button.parentElement.querySelector('[data-share-link]');try{await navigator.clipboard.writeText(input.value);clearTimeout(timer);button.textContent='✓ 已复制';window.cfSpring?.(button,'confirm',.94,1);timer=setTimeout(()=>{button.textContent='复制链接';},2500);}catch{input.focus();input.select();window.cfToast?.('请复制选中的链接。');}});});
 document.querySelectorAll('[data-print-report]').forEach(button=>button.addEventListener('click',()=>window.print()));
 const share=document.querySelector('[data-share-form]');share?.querySelectorAll('[name=fields],[name=days]').forEach(input=>input.addEventListener('change',()=>{share.querySelector('[data-share-submit]').disabled=true;share.querySelector('[data-share-change-note]').hidden=false;}));
})();
