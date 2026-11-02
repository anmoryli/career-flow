(() => {
  'use strict';const R=window.CFResume;
  document.querySelectorAll('[data-template-filter]').forEach(button=>button.addEventListener('click',()=>{
    const filter=button.dataset.templateFilter;
    document.querySelectorAll('[data-template-filter]').forEach(other=>other.setAttribute('aria-pressed',String(other===button)));
    document.querySelectorAll('[data-template-track-group]').forEach(group=>{group.hidden=filter!=='all'&&group.dataset.templateTrackGroup!==filter;});
    document.querySelectorAll('[data-template-kind]').forEach(card=>{card.hidden=filter!=='all'&&card.dataset.templateTrack!==filter;});
  }));
  document.querySelectorAll('[data-template-preview]').forEach(button=>button.addEventListener('click',()=>{
    const dialog=document.querySelector(`[data-template-preview-dialog="${button.dataset.templatePreview}"]`),card=button.closest('[data-template-kind]'),host=dialog?.querySelector('[data-template-copy]'),doc=card?.querySelector('.resume-doc');
    if(dialog&&host&&doc)host.replaceChildren(doc.cloneNode(true));
    R.open(dialog);R.thumbnails();
  }));
})();
