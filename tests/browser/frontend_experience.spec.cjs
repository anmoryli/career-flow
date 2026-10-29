const {test,expect}=require('@playwright/test');
const {randomUUID}=require('node:crypto');
let userId;
const headers=async page=>({'X-CSRFToken':await page.locator('meta[name="csrf-token"]').getAttribute('content')});
test.beforeEach(async({page})=>{await page.goto('/login');const response=await page.request.post('/__test/session',{headers:await headers(page),data:{}});expect(response.ok()).toBeTruthy();userId=(await response.json()).user_id;});
test.afterEach(async({page})=>{if(userId)await page.request.post('/__test/cleanup',{headers:await headers(page),data:{user_id:userId}});});

test('all user and admin pages remain readable in light, dark and system themes',async({page})=>{
 test.setTimeout(180000);
 const errors=[];page.on('pageerror',error=>errors.push(error.message));
 await page.request.post('/__test/promote',{headers:await headers(page),data:{user_id:userId}});
 const routes=[...['dashboard','resumes','resume-template','resume-new','resume-import','optimize','jobs','reports','history','settings','billing'].map(view=>`/workspace?view=${view}`),'/admin','/admin/users','/admin/orders','/admin/settings','/admin/audit'];
 for(const preference of ['light','dark','system']){
  await page.emulateMedia({colorScheme:'dark',reducedMotion:'reduce'});
  for(const route of routes){
   const response=await page.goto(route,{timeout:15000});expect(response.status(),route).toBe(200);
   await page.evaluate(preference=>window.cfTheme(preference),preference);
   await expect(page.locator('html')).toHaveAttribute('data-theme',preference==='light'?'light':'dark');
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${route}: ${preference} overflow`).toBeTruthy();
   if(route.includes('resume-new')){
    await expect(page.locator('#resume-title')).toBeVisible();await expect(page.locator('[data-save-resume]')).toBeVisible();
   }else{
    await expect(page.locator('h1').first()).toBeVisible();
    expect(await page.locator('h1').first().evaluate(node=>parseFloat(getComputedStyle(node).fontSize)),route).toBeGreaterThanOrEqual(23);
   }
   await page.screenshot({path:`output/experience-${route.replaceAll(/[^a-zA-Z0-9]/g,'-')}-${test.info().project.name}-${preference}.png`,fullPage:!route.includes('resume-new'),animations:'disabled',timeout:10000});
  }
 }
 expect(errors).toEqual([]);
});

test('overview preparation path reflects saved work and supports keyboard navigation',async({page})=>{
 await page.goto('/workspace');
 await expect(page.locator('[data-dashboard-path] [aria-current=step]')).toHaveCount(1);
 await expect(page.locator('[data-dashboard-path] [aria-current=step]')).toContainText('开始编辑');
 await page.keyboard.press('Tab');await expect(page.locator('.cf-skip')).toBeFocused();
 const created=await page.request.post('/api/resumes',{headers:await headers(page),data:{request_key:randomUUID(),revision:0,title:'路径核对简历',document:{name:'真实姓名',summary:'实际负责过的工作'}}});expect(created.ok()).toBeTruthy();
 await page.reload();
 await expect(page.locator('[data-dashboard-path] [aria-current=step]')).toContainText('开始岗位准备');
 await expect(page.locator('.cf-landing-continue')).toContainText('路径核对简历');
 await page.emulateMedia({reducedMotion:'reduce'});
 expect(await page.locator('[data-dashboard-path]').evaluate(node=>node.getAnimations({subtree:true}).some(animation=>animation.playState==='running'))).toBeFalsy();
});

test('product process, reduced motion and linked field errors stay usable',async({page})=>{
 await page.context().clearCookies();await page.emulateMedia({reducedMotion:'reduce'});
 for(const route of ['/','/login','/register','/password/reset']){
  await page.goto(route);
  for(const preference of ['light','dark','system']){
   await page.emulateMedia({colorScheme:'dark'});await page.evaluate(value=>window.cfTheme(value),preference);
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
   await page.screenshot({path:`output/experience-public-${route.replaceAll('/','')||'home'}-${test.info().project.name}-${preference}.png`,animations:'disabled',fullPage:true});
  }
 }
 await page.goto('/');
 const steps=page.locator('.cf-public-process-steps>details');await expect(steps).toHaveCount(3);
 await steps.nth(1).locator('summary').focus();await page.keyboard.press('Enter');await expect(steps.nth(1)).toHaveAttribute('open','');await expect(steps.first()).not.toHaveAttribute('open','');
 await expect(steps.nth(1)).toContainText('示例');
 expect(await page.locator('#main').evaluate(node=>node.getAnimations({subtree:true}).some(animation=>animation.playState==='running'))).toBeFalsy();
 await page.goto('/login');
 await page.evaluate(()=>window.cfFieldErrors(document.querySelector('[data-ui-form="auth"]'),{fields:{email:'请使用有效的邮箱地址。'}}));
 const email=page.locator('[data-ui-form="auth"] [name=email]');await expect(email).toBeFocused();await expect(email).toHaveAttribute('aria-invalid','true');
 const hint=await email.getAttribute('aria-describedby');await expect(page.locator(`#${hint}`)).toHaveText('请使用有效的邮箱地址。');await email.fill('candidate@example.com');await expect(email).not.toHaveAttribute('aria-invalid');
});

test('preview explains sample content, search can recover and invalid uploads stay local',async({page})=>{
 await page.goto('/workspace?view=resume-new&fresh=1');
 const previewTab=page.locator('[data-editor-tab=preview]');if(await previewTab.isVisible())await previewTab.click();
 await expect(page.locator('[data-preview-context-badge]')).toHaveText('模板示例');
 await expect(page.locator('[data-preview-context-text]')).toContainText('不会保存');
 await page.locator('[data-preview-use-draft]').click();await expect(page.locator('[data-preview-context-badge]')).toHaveText('当前简历');
 const editTab=page.locator('[data-editor-tab=edit]');if(await editTab.isVisible())await editTab.click();
 await expect(page.locator('#resume-name')).toHaveValue('');
 await page.locator('#resume-name').fill('真实预览姓名');
 await expect(page.locator('[data-resume-stage]')).toHaveAttribute('data-preview-focus','basics');
 await page.locator('[data-save-resume]').click();await expect(page.locator('[data-resume-editor]')).toHaveAttribute('data-dirty','false');
 await page.goto('/workspace?view=resumes');await page.locator('[data-library-search]').fill('找不到的内容');await expect(page.locator('[data-library-empty]')).toBeVisible();
 await page.locator('[data-library-reset-search]').click();await expect(page.locator('[data-library-search]')).toHaveValue('');await expect(page.locator('[data-library-search]')).toBeFocused();
 await page.goto('/workspace?view=resume-import');let sent=0;page.on('request',request=>{if(request.url().endsWith('/api/imports')&&request.method()==='POST')sent++;});
 await page.locator('#resume-file').setInputFiles({name:'invalid.txt',mimeType:'text/plain',buffer:Buffer.from('not a PDF')});
 await expect(page.locator('#file-selection')).toHaveAttribute('data-state','invalid');await expect(page.locator('[data-upload-pdf]')).toBeDisabled();expect(sent).toBe(0);
});

test('touch editing keeps primary controls reachable without horizontal overflow',async({page,browser})=>{
 const viewport=page.viewportSize();
 const context=await browser.newContext({baseURL:'http://127.0.0.1:8011',viewport,hasTouch:true,isMobile:viewport.width<700,storageState:await page.context().storageState()});
 try{
  const touch=await context.newPage();await touch.goto('/workspace?view=resume-new&fresh=1');
  await expect(touch.locator('[data-save-resume]')).toBeVisible();
  for(const selector of ['[data-save-resume]','[data-studio-tab=content]','[data-studio-tab=design]']){
   const bounds=await touch.locator(selector).boundingBox();expect(bounds.height,selector).toBeGreaterThanOrEqual(44);
  }
  expect(await touch.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await touch.locator('[data-studio-tab=design]').tap();
  await touch.screenshot({path:`output/experience-touch-editor-${test.info().project.name}.png`,animations:'disabled',timeout:10000});
 }finally{await context.close();}
});
