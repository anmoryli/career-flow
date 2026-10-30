/* Explicitly illustrative product walkthrough, never a simulated live AI task. */
(() => {
  const root=document.querySelector('[data-product-demo]');if(!root)return;
  const tabs=[...root.querySelectorAll('[data-demo-step]')],panels=[...root.querySelectorAll('[data-demo-panel]')];
  const select=index=>{
    tabs.forEach((tab,i)=>{tab.setAttribute('aria-selected',String(i===index));tab.tabIndex=i===index?0:-1;});
    panels.forEach((panel,i)=>{panel.hidden=i!==index;});
    if(!matchMedia('(prefers-reduced-motion: reduce)').matches)panels[index].animate([{opacity:.65,transform:'translateY(6px)'},{opacity:1,transform:'translateY(0)'}],{duration:180,easing:'cubic-bezier(.215,.61,.355,1)'});
  };
  tabs.forEach((tab,index)=>{
    tab.addEventListener('click',()=>select(index));
    tab.addEventListener('keydown',event=>{
      if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();
      const next=event.key==='Home'?0:event.key==='End'?tabs.length-1:(index+(event.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;
      select(next);tabs[next].focus();
    });
  });
})();
