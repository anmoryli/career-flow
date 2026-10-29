(() => {
  'use strict';const R=window.CFResume;
  document.querySelectorAll('[data-template-filter]').forEach(button=>button.addEventListener('click',()=>{document.querySelectorAll('[data-template-filter]').forEach(other=>other.setAttribute('aria-pressed',String(other===button)));document.querySelectorAll('[data-template-kind]').forEach(card=>{card.hidden=button.dataset.templateFilter!=='all'&&card.dataset.templateKind!==button.dataset.templateFilter;});}));
  document.querySelectorAll('[data-template-preview]').forEach(button=>button.addEventListener('click',()=>{const dialog=document.querySelector(`[data-template-preview-dialog="${button.dataset.templatePreview}"]`);R.open(dialog);R.thumbnails();}));
})();
