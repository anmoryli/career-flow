/* Pointer sorting for resume sections. Document order changes only on a valid drop. */
(() => {
  'use strict';
  window.CFResumeSort=({root,scroller,getOrder,getLabel,commit,restoreBodies})=>{
    let session=null,frame=0;
    const announce=text=>{root.querySelector('[data-section-sort-status]').textContent=text;};
    const rows=context=>[...root.querySelectorAll(`[data-sort-context="${context}"]`)].filter(node=>getOrder().includes(node.dataset.sortKey));
    const inside=(x,y)=>{const box=scroller.getBoundingClientRect();return x>=box.left&&x<=box.right&&y>=box.top&&y<=box.bottom;};
    const clearMarkers=()=>root.querySelectorAll('[data-sort-edge]').forEach(node=>delete node.dataset.sortEdge);
    const locate=()=>{
      const s=session;if(!s?.active)return;clearMarkers();s.target=null;
      s.ghost.style.left=`${Math.max(8,Math.min(innerWidth-s.ghost.offsetWidth-8,s.x+14))}px`;s.ghost.style.top=`${Math.max(8,Math.min(innerHeight-52,s.y-24))}px`;
      if(!inside(s.x,s.y))return;
      const candidates=rows(s.context).filter(node=>node.dataset.sortKey!==s.key);if(!candidates.length)return;
      let target=candidates.find(node=>{const box=node.getBoundingClientRect();return s.y>=box.top&&s.y<=box.bottom;}),edge;
      if(target){const box=target.getBoundingClientRect();edge=s.y<box.top+box.height/2?'before':'after';}
      else{target=candidates.find(node=>{const box=node.getBoundingClientRect();return s.y<box.top+box.height/2;});edge=target?'before':'after';target??=candidates[candidates.length-1];}
      target.dataset.sortEdge=edge;s.target={key:target.dataset.sortKey,edge};
    };
    const scroll=()=>{
      const s=session;if(!s?.active)return;
      const box=scroller.getBoundingClientRect();let step=0;
      if(s.x>=box.left&&s.x<=box.right){if(s.y<box.top+48)step=-Math.min(16,Math.max(0,box.top+48-s.y)/3);else if(s.y>box.bottom-48)step=Math.min(16,Math.max(0,s.y-box.bottom+48)/3);}
      if(step){scroller.scrollTop+=step;locate();}frame=requestAnimationFrame(scroll);
    };
    const start=()=>{
      const s=session;s.active=true;
      const row=s.handle.closest('[data-sort-key]'),top=row.getBoundingClientRect().top;
      root.classList.add('is-section-sorting');row.classList.add('is-sort-source');
      if(s.context==='content'){root.querySelectorAll('[data-section-body]').forEach(body=>body.inert=true);scroller.scrollTop+=row.getBoundingClientRect().top-top;}
      root.querySelectorAll('.cf-section-menu[open]').forEach(menu=>menu.open=false);
      s.ghost=document.createElement('div');s.ghost.className='cf-section-drag-ghost';s.ghost.textContent=`⠿ ${getLabel(s.key)}`;s.ghost.setAttribute('aria-hidden','true');document.body.append(s.ghost);announce(`正在拖动${getLabel(s.key)}，移动到目标位置后松开。`);locate();frame=requestAnimationFrame(scroll);
    };
    const finish=apply=>{
      const s=session;if(!s)return;session=null;cancelAnimationFrame(frame);clearMarkers();root.classList.remove('is-section-sorting');root.querySelectorAll('.is-sort-source').forEach(node=>node.classList.remove('is-sort-source'));s.ghost?.remove();restoreBodies();
      if(s.handle.hasPointerCapture(s.pointer))s.handle.releasePointerCapture(s.pointer);
      if(!s.active)return;
      let changed=false;
      if(apply&&s.target){const order=getOrder().filter(key=>key!==s.key),index=order.indexOf(s.target.key)+(s.target.edge==='after'?1:0);order.splice(index,0,s.key);changed=commit(order,s.key,s.context);}
      announce(changed?`已调整${getLabel(s.key)}的顺序。`:'已取消拖动，板块顺序未改变。');
    };
    document.addEventListener('pointermove',event=>{const s=session;if(!s||event.pointerId!==s.pointer)return;s.x=event.clientX;s.y=event.clientY;if(!s.active&&Math.hypot(s.x-s.startX,s.y-s.startY)>=6)start();if(s.active){event.preventDefault();locate();}},{passive:false});
    document.addEventListener('pointerup',event=>{if(session?.pointer===event.pointerId){session.x=event.clientX;session.y=event.clientY;locate();finish(inside(event.clientX,event.clientY));}});
    document.addEventListener('pointercancel',event=>{if(session?.pointer===event.pointerId)finish(false);});
    document.addEventListener('keydown',event=>{if(event.key==='Escape'&&session){event.preventDefault();event.stopImmediatePropagation();finish(false);}},{capture:true});
    window.addEventListener('blur',()=>finish(false));
    return (key,label,context='content')=>{
      const button=document.createElement('button');button.type='button';button.className='cf-section-drag';button.dataset.sectionDrag=key;button.textContent='⠿';button.title=`拖动${label}调整顺序`;button.setAttribute('aria-label',button.title);button.setAttribute('aria-describedby','cf-section-drag-help');
      button.addEventListener('pointerdown',event=>{if(session||event.button!==0||!getOrder().includes(key))return;event.preventDefault();button.focus({preventScroll:true});session={key,context,handle:button,pointer:event.pointerId,startX:event.clientX,startY:event.clientY,x:event.clientX,y:event.clientY,active:false};button.setPointerCapture(event.pointerId);});
      button.addEventListener('lostpointercapture',event=>{if(session?.pointer===event.pointerId)finish(false);});
      button.addEventListener('keydown',event=>{if(!['ArrowUp','ArrowDown'].includes(event.key)||session)return;event.preventDefault();const order=[...getOrder()],index=order.indexOf(key),target=index+(event.key==='ArrowUp'?-1:1);if(target<0||target>=order.length)return;order.splice(index,1);order.splice(target,0,key);if(commit(order,key,context))announce(`已调整${label}的顺序。`);});
      return button;
    };
  };
})();
