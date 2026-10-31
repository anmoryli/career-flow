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
  const render=(value,template='classic')=>{
    const data=normalize(value),doc=el('article',`resume-doc tpl-${template}`);doc.dataset.resumeDoc=template;doc.dataset.size=data.size;doc.dataset.accent=data.accent;doc.dataset.photoPosition=data.photo_position;
    const header=el('header','rd-head'),identity=el('div','rd-identity');identity.append(el('p','rd-eyebrow',template==='technical'?'TECHNICAL RESUME':template==='modern'?'CAREER PROFILE':template==='bilingual'?'简历 / Résumé':'个人简历'),el('h1','',data.name||''));if(data.role)identity.append(el('p','rd-role',data.role));header.append(identity);
    if(data.photo){const frame=el('figure','rd-photo-frame'),image=el('img','rd-photo');image.src=data.photo;image.alt='个人照片';image.dataset.rfPhoto='';frame.append(image);header.append(frame);}
    const contacts=el('div','rd-header-contact');for(const key of ['phone','email','city','website','github','linkedin'])if(data[key])contacts.append(el('span','rd-contact-item',data[key]));header.append(contacts);doc.append(header);
    const flow=el('div','rd-document-content');flow.dataset.sectionFlow='';
    const section=(key,title)=>{const node=el('section','rd-section');node.dataset.rfSection=key;node.append(el('h2','rd-section-title',title));return node;};
    for(const key of data.section_order){if(data.hidden_sections.includes(key))continue;let node;
      if(key==='summary'&&data.summary){node=section(key,template==='bilingual'?'个人总结 / Profile':'个人总结');node.append(markdown(el('div','rd-markdown rd-summary'),data.summary));}
      else if(['experiences','projects','education'].includes(key)&&data[key].some(has)){node=section(key,template==='bilingual'?({experiences:'工作经历 / Experience',projects:'项目经历 / Projects',education:'教育经历 / Education',certificates:'证书与资质 / Certificates',languages:'语言能力 / Languages'}[key]):labels[key]);data[key].forEach((item,index)=>{if(!has(item))return;const entry=el('article','rd-entry');entry.dataset.rfEntry=`${key}.${index}`;const top=el('div','rd-entry-top');top.append(el('h3','',item.company||item.name||item.school||''));if(item.period)top.append(el('span','rd-period',item.period));entry.append(top);const sub=[item.role,item.degree,item.location,item.tech].filter(Boolean);if(sub.length)entry.append(el('p','rd-entry-sub',sub.join(' · ')));if(item.bullets?.length){const list=el('ul','rd-bullets');item.bullets.forEach(text=>list.append(inline(el('li'),text)));entry.append(list);}if(item.description||item.detail)entry.append(markdown(el('div','rd-markdown'),item.description||item.detail));if(item.link)entry.append(link(item.link,/^https?:\/\//.test(item.link)?item.link:`https://${item.link}`));node.append(entry);});}
      else if(key==='skills'&&data.skills.some(item=>item.items?.length)){node=section(key,template==='bilingual'?'专业技能 / Skills':'专业技能');data.skills.filter(item=>item.items?.length).forEach(item=>{const row=el('div','rd-skill-group');row.append(el('strong','rd-skill-label',item.label),el('span','rd-skill-items',item.items.join(' · ')));node.append(row);});}
      else if(['certificates','languages'].includes(key)&&data[key].length){node=section(key,template==='bilingual'?({experiences:'工作经历 / Experience',projects:'项目经历 / Projects',education:'教育经历 / Education',certificates:'证书与资质 / Certificates',languages:'语言能力 / Languages'}[key]):labels[key]);const list=el('ul','rd-compact-list');data[key].forEach(text=>list.append(el('li','',text)));node.append(list);}
      else if(key.startsWith('custom:')){const item=data.custom_sections.find(item=>key===`custom:${item.id}`);if(item?.content){node=section(key,item.title||'补充经历');node.append(markdown(el('div','rd-markdown'),item.content));}}
      if(node)flow.append(node);
    }
    doc.append(flow);return doc;
  };
  const fit=host=>{const sheet=host.querySelector('.resume-doc');if(sheet){const s=getComputedStyle(host);const width=host.clientWidth-parseFloat(s.paddingLeft)-parseFloat(s.paddingRight);if(width)sheet.style.zoom=String(Math.min(width/794,1));}};
  const thumbnails=()=>{const observer=new ResizeObserver(entries=>entries.forEach(entry=>fit(entry.target)));document.querySelectorAll('[data-document-thumbnail]').forEach(host=>{observer.observe(host);fit(host);});};
  const open=id=>{const dialog=typeof id==='string'?document.getElementById(id):id;if(dialog&&!dialog.open)dialog.showModal();};
  const error=(host,message)=>{host.textContent=message;host.hidden=false;};
  const poll=async(id,onPartial)=>{for(let i=0;i<240;i++){const response=await fetch(`/api/resume-ai/${id}`,{credentials:'same-origin',redirect:'error'});const value=await response.json();if(!response.ok)throw new Error(value.error||'无法读取任务');if(value.partial)onPartial?.(value.partial);if(['succeeded','failed','cancelled'].includes(value.state)){if(value.state!=='succeeded')throw new Error(value.error||'任务未完成，请重试。');return value.result;}await new Promise(resolve=>setTimeout(resolve,500));}throw new Error('任务仍在处理中，请稍后查看。');};
  window.CFResume={templates,groups,labels,blank,normalize,clone,get,set,has,clean,el,markdown,inline,render,fit,thumbnails,open,error,poll};
  thumbnails();
})();
