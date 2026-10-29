/* Accessible single-select presentation. The original field remains the form source. */
(() => {
  'use strict';
  const widgets=new WeakMap();
  let serial=0,opened=null;
  class SelectControl {
    constructor(source){
      this.source=source;this.active=-1;this.buffer='';this.bufferAt=0;
      this.wrapper=document.createElement('span');this.wrapper.className='cf-select';
      this.wrapper.dataset.selectFor=source.id||source.name||'choice';
      source.before(this.wrapper);this.wrapper.append(source);
      this.trigger=document.createElement('button');this.trigger.type='button';this.trigger.className='cf-select-trigger';
      this.trigger.setAttribute('role','combobox');this.trigger.setAttribute('aria-haspopup','listbox');this.trigger.setAttribute('aria-expanded','false');
      this.label=document.createElement('span');this.label.className='cf-select-value';
      const chevron=document.createElement('span');chevron.className='cf-select-chevron';chevron.setAttribute('aria-hidden','true');
      this.trigger.append(this.label,chevron);this.wrapper.append(this.trigger);
      this.popup=document.createElement('div');this.popup.className='cf-select-popover';this.popup.id=`cf-select-list-${++serial}`;
      this.popup.setAttribute('role','listbox');this.popup.setAttribute('popover','manual');this.popup.hidden=true;
      (source.closest('dialog')||document.body).append(this.popup);this.trigger.setAttribute('aria-controls',this.popup.id);
      const explicit=source.getAttribute('aria-label');
      const labels=[...source.labels||[]].map(label=>{const copy=label.cloneNode(true);copy.querySelectorAll('select,button,input,textarea,small').forEach(node=>node.remove());return copy.textContent.trim();}).filter(Boolean).join(' ');
      this.trigger.setAttribute('aria-label',explicit||labels||source.name||'选择选项');
      if(source.getAttribute('aria-labelledby'))this.trigger.setAttribute('aria-labelledby',source.getAttribute('aria-labelledby'));
      this.popup.setAttribute('aria-label',this.trigger.getAttribute('aria-label'));
      source.classList.add('cf-select-source');source.tabIndex=-1;source.setAttribute('aria-hidden','true');
      // Existing controllers assign value/index directly, including theme and template changes.
      for(const name of ['value','selectedIndex']){
        const descriptor=Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,name);
        Object.defineProperty(source,name,{configurable:true,get:()=>descriptor.get.call(source),set:value=>{descriptor.set.call(source,value);this.sync();}});
      }
      this.observer=new MutationObserver(()=>this.sync());
      this.observer.observe(source,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['disabled','selected','label','required','aria-invalid','aria-describedby']});
      source.addEventListener('change',()=>this.sync());source.addEventListener('focus',()=>this.trigger.focus());
      source.addEventListener('invalid',event=>{event.preventDefault();this.trigger.setAttribute('aria-invalid','true');this.trigger.focus();});
      source.addEventListener('input',()=>this.trigger.removeAttribute('aria-invalid'));
      source.form?.addEventListener('reset',()=>requestAnimationFrame(()=>this.sync()));
      this.trigger.addEventListener('click',()=>this.isOpen?this.close():this.open());
      this.trigger.addEventListener('keydown',event=>this.keydown(event));
      this.popup.addEventListener('pointerdown',event=>event.preventDefault());
      this.popup.addEventListener('click',event=>{const option=event.target.closest('[data-select-index]');if(option)this.choose(Number(option.dataset.selectIndex));});
      this.sync();
    }
    get isOpen(){return this.trigger.getAttribute('aria-expanded')==='true';}
    get options(){return [...this.source.options];}
    get enabled(){return this.options.map((option,index)=>({option,index})).filter(({option})=>!option.disabled&&!option.parentElement.disabled&&!option.hidden).map(({index})=>index);}
    sync(){
      this.label.textContent=this.source.selectedOptions[0]?.textContent||'请选择';
      this.trigger.disabled=this.source.disabled;this.wrapper.dataset.disabled=String(this.source.disabled);
      this.trigger.setAttribute('aria-required',String(this.source.required));
      for(const name of ['aria-invalid','aria-describedby']){const value=this.source.getAttribute(name);if(value)this.trigger.setAttribute(name,value);else this.trigger.removeAttribute(name);}
      if(this.isOpen){if(this.source.disabled)this.close();else this.render();}
    }
    render(){
      this.popup.replaceChildren();let group=null;
      this.options.forEach((option,index)=>{
        if(option.hidden)return;
        if(option.parentElement.tagName==='OPTGROUP'&&group!==option.parentElement){group=option.parentElement;const title=document.createElement('div');title.className='cf-select-group';title.textContent=group.label;this.popup.append(title);}
        const row=document.createElement('div');row.id=`${this.popup.id}-option-${index}`;row.className='cf-select-option';row.dataset.selectIndex=String(index);row.textContent=option.label;
        row.setAttribute('role','option');row.setAttribute('aria-selected',String(index===this.source.selectedIndex));
        row.setAttribute('aria-disabled',String(option.disabled||option.parentElement.disabled||false));this.popup.append(row);
      });this.highlight();
    }
    highlight(){
      this.popup.querySelectorAll('[data-select-index]').forEach(row=>row.dataset.active=String(Number(row.dataset.selectIndex)===this.active));
      const row=this.popup.querySelector(`[data-select-index="${this.active}"]`);
      if(row){this.trigger.setAttribute('aria-activedescendant',row.id);row.scrollIntoView({block:'nearest'});}else this.trigger.removeAttribute('aria-activedescendant');
    }
    place(){
      const rect=this.trigger.getBoundingClientRect(),gap=6,margin=10;
      const width=Math.min(Math.max(rect.width,180),innerWidth-margin*2);this.popup.style.width=`${width}px`;
      const height=Math.min(this.popup.scrollHeight,300);
      const room=innerHeight-rect.bottom-margin-gap;
      this.popup.style.width=`${width}px`;this.popup.style.maxHeight=`${Math.max(80,Math.min(300,room>=height?room:rect.top-margin-gap))}px`;
      this.popup.style.left=`${Math.max(margin,Math.min(rect.left,innerWidth-width-margin))}px`;
      this.popup.style.top=`${room>=height||room>=rect.top?rect.bottom+gap:Math.max(margin,rect.top-Math.min(height,rect.top-margin-gap)-gap)}px`;
    }
    open(){
      if(this.source.disabled)return;
      if(opened&&opened!==this)opened.close();opened=this;
      this.active=this.enabled.includes(this.source.selectedIndex)?this.source.selectedIndex:(this.enabled[0]??-1);
      this.trigger.setAttribute('aria-expanded','true');this.popup.hidden=false;this.render();
      if(this.popup.showPopover)this.popup.showPopover();this.place();this.highlight();
    }
    close(){
      if(!this.isOpen)return;
      this.trigger.setAttribute('aria-expanded','false');this.trigger.removeAttribute('aria-activedescendant');
      if(this.popup.hidePopover&&this.popup.matches(':popover-open'))this.popup.hidePopover();this.popup.hidden=true;if(opened===this)opened=null;
    }
    choose(index){
      if(!this.enabled.includes(index))return;
      this.source.selectedIndex=index;this.close();this.trigger.focus();
      this.source.dispatchEvent(new Event('input',{bubbles:true}));this.source.dispatchEvent(new Event('change',{bubbles:true}));
    }
    keydown(event){
      const key=event.key;
      if(['ArrowDown','ArrowUp','Home','End','Enter',' ','Escape'].includes(key)){
        if(key==='Escape'){if(this.isOpen){event.preventDefault();event.stopPropagation();this.close();}return;}
        event.preventDefault();event.stopPropagation();
        if(key==='Enter'||key===' '){if(this.isOpen)this.choose(this.active);else this.open();return;}
        if(!this.isOpen){this.open();if(key==='ArrowDown'||key==='ArrowUp')return;}
        const enabled=this.enabled,position=enabled.indexOf(this.active);
        this.active=key==='Home'?enabled[0]:key==='End'?enabled.at(-1):enabled[Math.max(0,Math.min(enabled.length-1,position+(key==='ArrowDown'?1:-1)))];this.highlight();
      }else if(key==='Tab')this.close();
      else if(key.length===1&&!event.ctrlKey&&!event.metaKey&&!event.altKey){
        event.preventDefault();const now=Date.now();this.buffer=(now-this.bufferAt>650?'':this.buffer)+key.toLocaleLowerCase();this.bufferAt=now;
        if(!this.isOpen)this.open();const index=this.enabled.find(index=>this.options[index].textContent.trim().toLocaleLowerCase().startsWith(this.buffer));if(index!==undefined){this.active=index;this.highlight();}
      }
    }
    destroy(){this.close();this.observer.disconnect();this.popup.remove();}
  }
  const enhance=root=>{
    const sources=root instanceof HTMLSelectElement?[root]:root.querySelectorAll?.('select')||[];
    for(const source of sources)if(!source.multiple&&!widgets.has(source)){const widget=new SelectControl(source);widgets.set(source,widget);}
  };
  enhance(document);
  const mutations=new MutationObserver(records=>{
    for(const record of records){for(const node of record.addedNodes)if(node instanceof Element)enhance(node);for(const node of record.removedNodes)if(node instanceof Element){const sources=node instanceof HTMLSelectElement?[node]:node.querySelectorAll('select');for(const source of sources)if(!source.isConnected)widgets.get(source)?.destroy();}}
  });mutations.observe(document.body,{subtree:true,childList:true});
  document.addEventListener('pointerdown',event=>{if(opened&&!opened.wrapper.contains(event.target)&&!opened.popup.contains(event.target))opened.close();});
  document.addEventListener('scroll',event=>{if(opened&&!opened.popup.contains(event.target))opened.close();},true);
  addEventListener('resize',()=>opened?.close());
})();
