/* Shared resume domain helpers. User/model content is always inserted as text. */
(() => {
  'use strict';
  const groups=['summary','experiences','projects','education','skills','certificates','languages'];
  const labels={basics:'个人信息',photo:'个人照片',summary:'个人总结',education:'教育经历',experiences:'工作经历',projects:'项目经历',skills:'技能特长',certificates:'证书资质',languages:'语言能力'};
  const blank=()=>({name:'',role:'',phone:'',email:'',city:'',website:'',github:'',linkedin:'',summary:'',photo:'',experiences:[],projects:[],education:[],skills:[],certificates:[],languages:[],custom_sections:[],section_order:[...groups],hidden_sections:[],size:'standard',accent:'default',photo_position:'center'});
  const clone=value=>structuredClone(value);
  const normalize=value=>{
    const data={...blank(),...clone(value||{})};
    for(const key of ['experiences','projects','education','skills','certificates','languages','custom_sections','hidden_sections'])if(!Array.isArray(data[key]))data[key]=[];
    data.section_order=[...new Set([...(Array.isArray(data.section_order)?data.section_order:[]),...groups,...data.custom_sections.map(item=>`custom:${item.id}`)])];
    return data;
  };
  const get=(root,path)=>path.split('.').reduce((value,key)=>value?.[/^\d+$/.test(key)?Number(key):key],root);
  const set=(root,path,value)=>{const keys=path.split('.');let node=root;keys.forEach((part,index)=>{const key=/^\d+$/.test(part)?Number(part):part;if(index===keys.length-1)node[key]=value;else{node[key]??=/^\d+$/.test(keys[index+1])?[]:{};node=node[key];}});};
  const has=value=>Array.isArray(value)?value.some(has):value&&typeof value==='object'?Object.values(value).some(has):typeof value==='string'?!!value.trim():false;
  const clean=value=>{
    const data=normalize(value);
    for(const key of ['name','role','phone','email','city','website','github','linkedin','summary'])data[key]=String(data[key]||'').trim();
    for(const key of ['experiences','projects','education'])data[key]=data[key].map(item=>Object.fromEntries(Object.entries(item).map(([k,v])=>[k,Array.isArray(v)?v.map(x=>String(x).trim()).filter(Boolean):String(v||'').trim()]))).filter(has);
    data.skills=data.skills.map(item=>({label:String(item.label||'').trim(),items:(item.items||[]).map(x=>String(x).trim()).filter(Boolean)})).filter(item=>item.items.length);
    for(const key of ['certificates','languages'])data[key]=data[key].map(x=>String(x).trim()).filter(Boolean);
    data.custom_sections=data.custom_sections.filter(item=>item.content?.trim());
    data.section_order=data.section_order.filter(key=>!key.startsWith('custom:')||data.custom_sections.some(item=>key===`custom:${item.id}`));
    return data;
  };
  const el=(tag,cls,text)=>{const node=document.createElement(tag);if(cls)node.className=cls;if(text!=null)node.textContent=text;return node;};
  const link=(text,url)=>{if(!/^https?:\/\//i.test(url||''))return document.createTextNode(text);const node=el('a','',text);node.href=url;node.target='_blank';node.rel='noopener noreferrer';return node;};
  const inline=(node,text)=>{
    node.replaceChildren();const pattern=/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)|\*\*([^*]+)\*\*|__([^_]+)__|`([^`]+)`|\*([^*]+)\*/g;let last=0;
    for(const match of String(text||'').matchAll(pattern)){node.append(document.createTextNode(text.slice(last,match.index)));let child;if(match[1])child=link(match[1],match[2]);else child=el(match[5]?'code':match[3]||match[4]?'strong':'em','',match[3]||match[4]||match[5]||match[6]);node.append(child);last=match.index+match[0].length;}
    node.append(document.createTextNode(String(text||'').slice(last)));return node;
  };
  const markdown=(node,text)=>{
    node.replaceChildren();let list=null,type='';
    String(text||'').split(/\r?\n/).forEach(line=>{const heading=/^(#{1,3})\s+(.+)$/.exec(line),bullet=/^\s*[-*+]\s+(.+)$/.exec(line),number=/^\s*\d+[.)]\s+(.+)$/.exec(line);if(!line.trim()){list=null;type='';return;}if(bullet||number){const next=bullet?'ul':'ol';if(type!==next){list=el(next);node.append(list);type=next;}list.append(inline(el('li'),(bullet||number)[1]));}else{list=null;type='';node.append(inline(el(heading?'h'+(heading[1].length+2):'p'),heading?heading[2]:line));}});return node;
  };
  const templates=JSON.parse(document.body.dataset.templateCatalog||'[]');
  const labelsFor=template=>({...labels,...(templates.find(item=>item.id===template)?.labels||{})});
  const layoutFor=template=>{const entry=templates.find(item=>item.id===template);return{layout:entry?.layout||'linear',options:entry?.options||{}};};
  const RAIL_SECTIONS=['skills','certificates','languages'];
  const BILINGUAL_TITLES={summary:'个人总结 / Profile',experiences:'工作经历 / Experience',projects:'项目经历 / Projects',education:'教育经历 / Education',certificates:'证书与资质 / Certificates',languages:'语言能力 / Languages'};
  const render=(value,template='classic')=>{
    const data=normalize(value),{layout,options}=layoutFor(template),doc=el('article',`resume-doc tpl-${template} lay-${layout}`);doc.dataset.resumeDoc=template;doc.dataset.layout=layout;doc.dataset.size=data.size;doc.dataset.accent=data.accent;doc.dataset.photoPosition=data.photo_position;
    const L=labelsFor(template),bilingual=template==='bilingual',title=key=>bilingual?BILINGUAL_TITLES[key]||key:L[key]||key;
    const photoFrame=(variant='default')=>{const frame=el('figure',`rd-photo-frame rd-photo-${variant}`);frame.dataset.photoSlot='';const image=el('img','rd-photo');image.alt='个人照片';image.dataset.rfPhoto='';if(data.photo){image.src=data.photo;}else{image.hidden=true;const placeholder=el('span','rd-photo-placeholder');placeholder.dataset.photoPlaceholder='';placeholder.append(el('b','rd-photo-mark',(data.name||'照片').slice(0,1)),el('i','rd-photo-hint','照片'));frame.append(placeholder);}frame.append(image);return frame;};
    const contactRow=cls=>{const row=el('div',cls||'rd-header-contact');for(const key of ['phone','email','city','website','github','linkedin'])if(data[key])row.append(el('span','rd-contact-item',data[key]));return row;};
    const section=(key,titleText,no)=>{const node=el('section','rd-section');node.dataset.rfSection=key;const head=el('h2','rd-section-title');if(no!=null)head.append(el('span','rd-section-no',no));head.append(document.createTextNode(titleText));node.append(head);return node;};
    const entryNode=(key,item,index)=>{const entry=el('article','rd-entry');entry.dataset.rfEntry=`${key}.${index}`;const top=el('div','rd-entry-top');top.append(el('h3','',item.company||item.name||item.school||''));if(item.period)top.append(el('span','rd-period',item.period));entry.append(top);const sub=[item.role,item.degree,item.location,item.tech].filter(Boolean);if(sub.length)entry.append(el('p','rd-entry-sub',sub.join(' · ')));if(item.bullets?.length){const list=el('ul','rd-bullets');item.bullets.forEach(text=>list.append(inline(el('li'),text)));entry.append(list);}if(item.description||item.detail)entry.append(markdown(el('div','rd-markdown'),item.description||item.detail));if(item.link)entry.append(link(item.link,/^https?:\/\//.test(item.link)?item.link:`https://${item.link}`));return entry;};
    const skillNode=(key,mode)=>{const node=section(key,title(key));const listMode=mode||'list';data.skills.filter(item=>item.items?.length).forEach((item,index)=>{const row=el('div','rd-skill-group');row.dataset.rfEntry=`skills.${index}`;row.append(el('strong','rd-skill-label',item.label));const items=el('span',listMode==='pills'?'rd-pills':listMode==='meter'?'rd-meters':listMode==='dots'?'rd-dots':'rd-skill-items');items.dataset.rfList=`skills.${index}.items`;items.dataset.rfListMode=listMode;item.items.forEach((text,dot)=>{if(listMode==='pills')items.append(el('span','rd-pill',text));else if(listMode==='meter'){const rowM=el('span','rd-meter-row');rowM.append(el('span','rd-meter-text',text));const track=el('i','rd-meter-track');const bar=el('b','rd-meter-bar');track.append(bar);bar.dataset.level=String([92,84,76,68,60][dot%5]);rowM.append(track);items.append(rowM);}else if(listMode==='dots'){const item2=el('span','rd-dots-item');item2.append(el('span','rd-dots-text',text));const track=el('i','rd-dots-track');for(let d=0;d<5;d++)track.append(el('b',d<5-(dot%2)?'is-on':'','●'));item2.append(track);items.append(item2);}else items.append(el('span','',text));});row.append(items);node.append(row);});return node;};
    const listNode=(key,titleText)=>{const node=section(key,titleText);const list=el('ul','rd-compact-list');list.dataset.rfList=key;data[key].forEach(text=>list.append(el('li','',text)));node.append(list);return node;};
    const summaryNode=no=>{const node=section('summary',title('summary'),no);node.append(markdown(el('div','rd-markdown rd-summary'),data.summary));return node;};
    const sectionNode=(key,no)=>{if(key==='summary')return data.summary?summaryNode(no):null;
      if(['experiences','projects','education'].includes(key)&&data[key].some(has)){const node=section(key,title(key),no);data[key].forEach((item,index)=>{if(has(item))node.append(entryNode(key,item,index));});return node;}
      if(key==='skills')return data.skills.some(item=>item.items?.length)?skillNode(key,'list'):null;
      if(['certificates','languages'].includes(key)&&data[key].length)return listNode(key,title(key));
      if(key.startsWith('custom:')){const item=data.custom_sections.find(item=>key===`custom:${item.id}`);if(!item?.content)return null;const node=section(key,item.title||'补充经历',no);node.append(markdown(el('div','rd-markdown'),item.content));return node;}
      return null;};
    const flowSections=(order,skip,withNumber)=>{const flow=el('div','rd-document-content');flow.dataset.sectionFlow='';let counter=0;for(const key of order){if(data.hidden_sections.includes(key)||skip?.includes(key))continue;const node=sectionNode(key,withNumber?String(++counter).padStart(2,'0'):null);if(node)flow.append(node);}return flow;};
    const linearHead=(eyebrow,headCls)=>{const header=el('header',`rd-head${headCls?` ${headCls}`:''}`),identity=el('div','rd-identity');identity.append(el('p','rd-eyebrow',eyebrow),el('h1','',data.name||''));if(data.role)identity.append(el('p','rd-role',data.role));header.append(photoFrame('head'),identity,contactRow());return header;};
    if(layout==='split'){
      const railOrder=data.section_order.filter(key=>RAIL_SECTIONS.includes(key)),mainOrder=data.section_order.filter(key=>!RAIL_SECTIONS.includes(key));
      const split=el('div',`rd-split rd-split-${options.side||'left'} rd-rail-${options.rail||'soft'} rd-skills-${options.skills||'list'}`);
      const rail=el('aside','rd-split-rail');rail.append(photoFrame('rail'));
      const identity=el('div','rd-identity');identity.append(el('h1','',data.name||''));if(data.role)identity.append(el('p','rd-role',data.role));rail.append(identity);
      rail.append(contactRow('rd-rail-contact'));
      const railFlow=el('div','rd-split-rail-sections');railFlow.dataset.sectionFlow='';
      railOrder.forEach(key=>{if(data.hidden_sections.includes(key))return;if(key==='skills'&&data.skills.some(item=>item.items?.length)){railFlow.append(skillNode(key,options.skills||'list'));}else if(['certificates','languages'].includes(key)&&data[key].length){railFlow.append(listNode(key,title(key)));}});
      rail.append(railFlow);
      const main=el('div','rd-split-main');main.append(flowSections(mainOrder));split.append(rail,main);doc.append(split);return doc;
    }
    if(layout==='banner'){
      const lead=data.summary&&data.section_order.includes('summary')&&!data.hidden_sections.includes('summary');
      const banner=el('header',`rd-banner rd-banner-${options.tone||'solid'}`);banner.append(photoFrame('banner'));
      const text=el('div','rd-banner-text');text.append(el('p','rd-eyebrow','个人简历'),el('h1','',data.name||''));if(data.role)text.append(el('p','rd-role',data.role));if(lead)text.append(el('p','rd-banner-lead',data.summary));banner.append(text,contactRow('rd-banner-contact'));doc.append(banner);
      doc.append(flowSections(data.section_order,lead?['summary']:null));return doc;
    }
    if(layout==='editorial'){
      const lead=data.summary&&data.section_order.includes('summary')&&!data.hidden_sections.includes('summary');
      const head=el('header','rd-editorial-head'),main=el('div','rd-editorial-main');main.append(el('p','rd-editorial-eyebrow','CURRICULUM VITAE'),el('h1','',data.name||''));if(data.role)main.append(el('p','rd-editorial-role',data.role));main.append(contactRow('rd-editorial-meta'));head.append(main,photoFrame('editorial'));doc.append(head);
      if(lead)doc.append(el('p','rd-editorial-lead',data.summary));
      doc.append(flowSections(data.section_order,lead?['summary']:null,options.numbered!==false));return doc;
    }
    doc.append(linearHead(bilingual?'简历 / Résumé':'个人简历',`rd-head-${template}`));
    doc.append(flowSections(data.section_order,null,false));
    if(layout==='timeline')doc.querySelector('.rd-document-content')?.classList.add('rd-timeline-body');
    return doc;
  };
  const fit=host=>{const sheet=host.querySelector('.resume-doc');if(sheet){const s=getComputedStyle(host);const width=host.clientWidth-parseFloat(s.paddingLeft)-parseFloat(s.paddingRight);if(width)sheet.style.zoom=String(Math.min(width/794,1));}};
  const thumbnails=()=>{const observer=new ResizeObserver(entries=>entries.forEach(entry=>fit(entry.target)));document.querySelectorAll('[data-document-thumbnail]').forEach(host=>{observer.observe(host);fit(host);});};
  const open=id=>{const dialog=typeof id==='string'?document.getElementById(id):id;if(dialog&&!dialog.open)dialog.showModal();};
  const error=(host,message)=>{host.textContent=message;host.hidden=false;};
  const poll=async(id,onPartial)=>{for(let i=0;i<240;i++){const response=await fetch(`/api/resume-ai/${id}`,{credentials:'same-origin',redirect:'error'});const value=await response.json();if(!response.ok)throw new Error(value.error||'无法读取任务');if(value.partial)onPartial?.(value.partial);if(['succeeded','failed','cancelled'].includes(value.state)){if(value.state!=='succeeded')throw new Error(value.error||'任务未完成，请重试。');return value.result;}await new Promise(resolve=>setTimeout(resolve,500));}throw new Error('任务仍在处理中，请稍后查看。');};
  window.CFResume={templates,groups,labels,labelsFor,blank,normalize,clone,get,set,has,clean,el,markdown,inline,render,fit,thumbnails,open,error,poll};
  thumbnails();
})();
