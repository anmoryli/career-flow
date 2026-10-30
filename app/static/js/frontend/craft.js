/* Shared visual behavior. No generated text is interpreted as markup or code. */
(() => {
  'use strict';
  const reduced=matchMedia('(prefers-reduced-motion: reduce)'),streams=new WeakMap(),motionAnimations=new Set();
  const springFrames=(stiffness,damping)=>{
    let value=0,velocity=0;const frames=[];const dt=1/240;
    for(let step=0;step<=240;step++){
      if(step%4===0)frames.push(value);
      velocity+=(stiffness*(1-value)-damping*velocity)*dt;value+=velocity*dt;
    }
    frames[0]=0;frames[frames.length-1]=1;return frames;
  };
  const compositionEnd=new WeakMap();document.addEventListener('compositionend',event=>compositionEnd.set(event.target,Date.now()));
  window.cfImeGuard=event=>{if(event.isComposing)return true;const ended=compositionEnd.get(event.target);if(ended&&Date.now()-ended<500){compositionEnd.delete(event.target);return true;}return false;};
  const physics={drag:springFrames(1200,80),confirm:springFrames(380,18)};
  window.cfSpring=(element,kind,from=0,to=1)=>{
    if(!element||reduced.matches)return;
    const values=physics[kind]||physics.drag;
    const animation=element.animate(values.map(value=>kind==='confirm'?{transform:`scale(${from+(to-from)*value})`}:{transform:`translateX(${from+(to-from)*value}px)`}),{duration:1000,easing:'linear'});motionAnimations.add(animation);animation.finished.catch(()=>{}).finally(()=>motionAnimations.delete(animation));return animation;
  };
  window.cfStreamText=(element,value,complete=false)=>{
    if(!element)return;value=String(value||'');
    let previous=streams.get(element)||{text:element.textContent,next:0};if(previous.text!==element.textContent)previous={text:element.textContent,next:0};
    if(complete||reduced.matches||!value.startsWith(previous.text)){
      element.textContent=value;streams.set(element,{text:value,next:0});return;
    }
    if(value===previous.text)return;
    const fragment=document.createDocumentFragment(),now=performance.now();let next=Math.max(now,previous.next);
    for(const glyph of Array.from(value.slice(previous.text.length))){
      const span=document.createElement('span');span.className='cf-stream-glyph';span.textContent=glyph;
      span.style.animationDelay=`${Math.max(0,next-now)}ms`;fragment.append(span);next+=30;
      span.addEventListener('animationend',()=>{if(span.isConnected){span.replaceWith(document.createTextNode(glyph));element.normalize();}},{once:true});
    }
    element.append(fragment);streams.set(element,{text:value,next});
  };
  reduced.addEventListener('change',()=>{
    if(reduced.matches){motionAnimations.forEach(animation=>animation.cancel());}
    if(reduced.matches)document.querySelectorAll('.cf-stream-glyph').forEach(span=>span.replaceWith(document.createTextNode(span.textContent)));
  });
  const enhanceDetails=root=>{
    const nodes=root instanceof HTMLDetailsElement?[root]:root.querySelectorAll?.('details')||[];
    for(const details of nodes){
      if(details.dataset.cfFold||details.matches('.cf-account-menu,.cf-task-menu,.cf-document-menu'))continue;
      const summary=[...details.children].find(node=>node.tagName==='SUMMARY');if(!summary)continue;
      details.dataset.cfFold='true';const grid=document.createElement('div'),inner=document.createElement('div');grid.className='cf-fold';inner.className='cf-fold-content';
      while(summary.nextSibling)inner.append(summary.nextSibling);grid.append(inner);details.append(grid);inner.inert=!details.open;
      details.addEventListener('toggle',()=>{inner.inert=!details.open;});
    }
  };
  const addCopy=root=>{
    const nodes=root.matches?.('[data-resume-ai-proposed],[data-review-candidate-text]')?[root]:root.querySelectorAll?.('[data-resume-ai-proposed],[data-review-candidate-text]')||[];
    for(const source of nodes){
      if(source.dataset.cfCopy)continue;source.dataset.cfCopy='true';
      const button=document.createElement('button');button.type='button';button.className='cf-button is-quiet is-small cf-copy-button';button.textContent='复制正文';button.hidden=!source.textContent;source.after(button);let timer,animation;
      new MutationObserver(()=>{button.hidden=!source.textContent;}).observe(source,{childList:true,subtree:true});
      button.addEventListener('click',async()=>{
        try{await navigator.clipboard.writeText(source.textContent);}catch{window.cfToast?.('复制未完成，请选中文字手动复制。');return;}
        clearTimeout(timer);animation?.cancel();button.textContent='✓ 已复制';button.dataset.copied='true';window.cfSpring(button,'confirm',.94,1);
        timer=setTimeout(async()=>{if(!reduced.matches){animation=button.animate([{opacity:1},{opacity:0}],{duration:140});await animation.finished.catch(()=>{});}button.textContent='复制正文';delete button.dataset.copied;},2500);
      });
    }
  };
  enhanceDetails(document);addCopy(document);
  new MutationObserver(records=>{for(const record of records)for(const node of record.addedNodes)if(node instanceof Element){enhanceDetails(node);addCopy(node);}}).observe(document.body,{childList:true,subtree:true});
  document.addEventListener('change',event=>{if(event.target.matches('input[type=checkbox]:checked,input[type=radio]:checked'))window.cfSpring(event.target,'confirm',.82,1);});
  document.addEventListener('focusin',event=>{
    const field=event.target;if(!matchMedia('(pointer: coarse)').matches||!field.matches('input:not([type=checkbox]):not([type=radio]),textarea'))return;
    setTimeout(()=>{if(document.activeElement===field)field.scrollIntoView({block:'center',behavior:reduced.matches?'instant':'smooth'});},300);
  });
})();
