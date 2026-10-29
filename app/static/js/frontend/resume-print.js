(() => {
  const canvas=document.querySelector('[data-resume-print]');
  const data=JSON.parse(canvas.dataset.resumePrint),doc=canvas.querySelector('.resume-doc');doc.dataset.size=data.size||'standard';doc.dataset.accent=data.accent||'default';
  const position=data.photo_position||'center';doc.querySelectorAll('[data-rf-photo]').forEach(image=>{image.style.objectPosition=position==='top'?'center top':position==='bottom'?'center bottom':'center';});
  document.querySelector('#print-document').addEventListener('click',async()=>{if(document.fonts?.ready)await document.fonts.ready;await Promise.all([...doc.querySelectorAll('img')].map(image=>image.decode?.().catch(()=>{})));window.print();});
})();
