const {test,expect}=require('@playwright/test');
const {randomUUID}=require('node:crypto');
const fs=require('node:fs');
const headers=async page=>{const meta=page.locator('meta[name="csrf-token"]');if(await meta.count())return {'X-CSRFToken':await meta.getAttribute('content')};const html=await(await page.request.get('/')).text();return {'X-CSRFToken':html.match(/name="csrf-token" content="([^"]+)"/)[1]};};
test('preview density choices keep distinct readable sizes',async({page})=>{
  await page.goto('/login');const session=await page.request.post('/__test/session',{headers:await headers(page),data:{}});const uid=(await session.json()).user_id;
  try{
    await page.goto('/workspace?view=resume-new&fresh=1');
    if(page.viewportSize().width<=760)await page.getByRole('button',{name:'预览',exact:true}).click();
    for(const [label,size,pixels] of [['紧凑','compact','11px'],['标准','standard','12px'],['宽松','large','13px']]){
      await page.locator('[data-select-for="resume-size"] .cf-select-trigger').click();
      await page.locator('.cf-select-popover:visible').getByRole('option',{name:label,exact:true}).click();
      const doc=page.locator('[data-resume-stage] .cf-resume-panel:not([hidden]) .resume-doc');
      await expect(doc).toHaveAttribute('data-size',size);
      expect(await doc.evaluate(node=>getComputedStyle(node).fontSize)).toBe(pixels);
    }
  }finally{await page.request.post('/__test/cleanup',{headers:await headers(page),data:{user_id:uid}});}
});
test('all industry templates render complete single-page PDFs and review images',async({page})=>{
  test.setTimeout(180000);
  await page.goto('/login');
  const session=await page.request.post('/__test/session',{headers:await headers(page),data:{}});
  const uid=(await session.json()).user_id;
  const out=`output/resume-design/${test.info().project.name}`;fs.mkdirSync(out,{recursive:true});
  try{
    await page.goto('/workspace?view=billing');
    await page.locator('[data-membership-plan="membership_monthly"] button[type=submit]').click();
    await page.goto('/workspace?view=resume-new&fresh=1');
    const {templates,examples}=await page.evaluate(()=>({templates:window.CFResume.templates,examples:JSON.parse(document.querySelector('[data-resume-stage]').dataset.examples)}));
    expect(templates).toHaveLength(20);
    let saved=null;
    for(const template of templates){
      const response=await page.request.post(saved?`/api/resumes/${saved.id}`:'/api/resumes',{headers:await headers(page),data:{request_key:randomUUID(),revision:saved?.revision||0,title:'模板视觉验收',template:template.id,document:examples[template.id]}});
      expect(response.ok(),`${template.id}: ${await response.text()}`).toBeTruthy();saved=await response.json();
      await page.goto(`/workspace?view=resume-new&resume_id=${saved.id}`);
      if(page.viewportSize().width<=760)await page.getByRole('button',{name:'预览',exact:true}).click();
      const editor=page.locator('[data-resume-stage] .cf-resume-panel:not([hidden]) .resume-doc');
      await expect(editor).toContainText(examples[template.id].name);
      await page.evaluate(async()=>{await document.fonts.ready;await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));});
      const editorSections=await editor.evaluate(doc=>{const r=doc.getBoundingClientRect();return [...doc.querySelectorAll('.rd-section')].filter(node=>node.getClientRects().length).map(node=>{const n=node.getBoundingClientRect();return {key:node.dataset.rfSection,x:(n.left-r.left)/r.width,y:(n.top-r.top)/r.width,width:n.width/r.width};});});
      await page.screenshot({path:`${out}/${template.id}-editor.png`});
      await page.goto(`/resumes/${saved.id}/print`);
      await expect(page.locator('.resume-doc')).toContainText(examples[template.id].name);
      await expect(page.locator('.rd-dots-track,.rd-meter-track')).toHaveCount(0);
      await page.evaluate(async()=>{await document.fonts.ready;await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));});
      const screenSections=await page.locator('.resume-doc').evaluate(doc=>{const r=doc.getBoundingClientRect();return [...doc.querySelectorAll('.rd-section')].filter(node=>node.getClientRects().length).map(node=>{const n=node.getBoundingClientRect();return {key:node.dataset.rfSection,x:(n.left-r.left)/r.width,y:(n.top-r.top)/r.width,width:n.width/r.width};});});
      const previewBounds=await page.locator('.resume-doc').boundingBox();
      expect(screenSections.map(item=>item.key)).toEqual(editorSections.map(item=>item.key));
      for(let index=0;index<screenSections.length;index++){for(const metric of ['x','y','width'])expect(Math.abs(screenSections[index][metric]-editorSections[index][metric]),`${template.id} ${screenSections[index].key} editor/export ${metric}`).toBeLessThan(.04);}
      expect(previewBounds.x+previewBounds.width,`${template.id} complete screen preview`).toBeLessThanOrEqual(page.viewportSize().width+1);
      await page.emulateMedia({media:'print'});
      await page.evaluate(async()=>{await document.fonts.ready;window.cfFitShortResumePage();});
      const printSections=await page.locator('.resume-doc').evaluate(doc=>{const r=doc.getBoundingClientRect();return [...doc.querySelectorAll('.rd-section')].filter(node=>node.getClientRects().length).map(node=>{const n=node.getBoundingClientRect();return {key:node.dataset.rfSection,x:(n.left-r.left)/r.width,y:(n.top-r.top)/r.width,width:n.width/r.width};});});
      expect(printSections.map(item=>item.key)).toEqual(screenSections.map(item=>item.key));
      for(let index=0;index<printSections.length;index++){for(const metric of ['x','y','width'])expect(Math.abs(printSections[index][metric]-screenSections[index][metric]),`${template.id} ${printSections[index].key} screen/print ${metric}`).toBeLessThan(.04);}
      const pdf=await page.pdf({path:`${out}/${template.id}.pdf`,format:'A4',printBackground:true,preferCSSPageSize:true});
      expect((pdf.toString('latin1').match(/\/Type\s*\/Page\b/g)||[]).length,`${template.id} PDF page count`).toBe(1);
      await page.locator('.resume-doc').screenshot({path:`${out}/${template.id}.png`});
      await page.emulateMedia({media:'screen'});
    }
    await page.goto('/workspace?view=resume-template');
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
    await page.screenshot({path:`${out}/catalogue.png`,fullPage:true});
  }finally{
    await page.goto('/workspace');
    await page.request.post('/__test/cleanup',{headers:await headers(page),data:{user_id:uid}});
  }
});
