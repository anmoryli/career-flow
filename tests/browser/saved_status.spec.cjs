const {test,expect}=require('@playwright/test');
const {randomUUID}=require('node:crypto');
const headers=async page=>({'X-CSRFToken':await page.locator('meta[name="csrf-token"]').getAttribute('content')});
test('repeated saves and related pages show content without revision labels',async({page})=>{
  await page.goto('/login');const session=await page.request.post('/__test/session',{headers:await headers(page),data:{}});const uid=(await session.json()).user_id;
  const cleanupHeaders=await headers(page);
  try{
    const csrf=await headers(page);let saved=null;
    for(let index=0;index<30;index++){
      const result=await page.request.post(saved?`/api/resumes/${saved.id}`:'/api/resumes',{headers:csrf,data:{request_key:randomUUID(),revision:saved?.revision||0,title:'保存提示检查',template:'classic',document:{name:'真实姓名',summary:`已核实的真实经历 ${index+1}`}}});
      expect(result.ok()).toBeTruthy();saved=await result.json();
    }
    expect(saved.revision).toBe(30);
    await page.goto(`/workspace?view=resume-new&resume_id=${saved.id}`);
    await page.locator('[data-save-resume]').click();
    await expect(page.locator('#resume-draft-status')).toHaveText('已保存到账号');
    const persisted=await(await page.request.get(`/api/resumes/${saved.id}`)).json();expect(persisted.revision).toBe(31);
    const analyze=page.locator('[data-editor-analyze]');
    if(page.viewportSize().width<=760)await page.locator('.cf-editor-mobile-menu summary').click();
    await analyze.click({timeout:8000});
    await expect(page.locator('#cf-resume-job [data-studio-job-source]')).toHaveText('保存提示检查');
    await page.locator('#cf-resume-job').evaluate(dialog=>dialog.close());
    await expect(page.locator('body')).not.toContainText(/版本|第\s*\d+\s*版/);
    for(const route of ['/','/workspace?view=billing','/workspace?view=jobs','/workspace?view=resumes']){
      await page.goto(route);await expect(page.locator('body')).not.toContainText(/版本|第\s*\d+\s*版/);
    }
    await page.request.post('/__test/promote',{headers:await headers(page),data:{user_id:uid}});
    for(const route of ['/admin/settings','/admin/product']){await page.goto(route);await expect(page.locator('body')).not.toContainText(/版本|第\s*\d+\s*版/);}
  }finally{await page.request.post('/__test/cleanup',{headers:cleanupHeaders,data:{user_id:uid}});}
});
