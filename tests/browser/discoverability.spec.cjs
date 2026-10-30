const {test,expect}=require('@playwright/test');
const {randomUUID}=require('node:crypto');let uid;
const headers=async page=>({'X-CSRFToken':await page.locator('meta[name="csrf-token"]').getAttribute('content')});
test.beforeEach(async({page})=>{await page.goto('/login');const r=await page.request.post('/__test/session',{headers:await headers(page),data:{}});uid=(await r.json()).user_id;});
test.afterEach(async({page})=>{if(uid)await page.request.post('/__test/cleanup',{headers:await headers(page),data:{user_id:uid}});});
const inViewport=async(page,locator)=>{const box=await locator.boundingBox();expect(box).not.toBeNull();expect(box.x).toBeGreaterThanOrEqual(0);expect(box.y).toBeGreaterThanOrEqual(0);expect(box.x+box.width).toBeLessThanOrEqual(page.viewportSize().width+1);expect(box.y+box.height).toBeLessThanOrEqual(page.viewportSize().height+1);};
test('frequent destinations and editor actions have visible labels',async({page})=>{
 await page.goto('/workspace');for(const name of ['我的简历','岗位分析','分析报告'])await expect(page.locator('.cf-product-nav').getByRole('link',{name,exact:true})).toBeVisible();
 await page.goto('/workspace?view=resume-new&fresh=1');
 for(const selector of ['[data-editor-analyze]','[data-save-resume]','[data-version-history]','[data-dialog-open="cf-resume-source"]']){const control=page.locator(selector);await expect(control).toBeVisible();await inViewport(page,control);}
 await expect(page.locator('[data-editor-analyze] span')).toHaveText('岗位分析');await expect(page.locator('[data-editor-analyze] span')).toBeVisible();await expect(page.locator('[data-save-resume]')).toHaveText('保存简历');expect(await page.locator('[data-save-resume]').getAttribute('class')).not.toContain('is-secondary');
 await page.screenshot({path:`output/actions-editor-${test.info().project.name}.png`,animations:'disabled'});
});
test('analysis action stays reachable and review exposes its save destination',async({page})=>{
 await page.goto('/workspace?view=billing');await page.locator('[data-membership-plan="membership_quarterly"] button[type=submit]').click();
 const created=await page.request.post('/api/resumes',{headers:await headers(page),data:{request_key:randomUUID(),revision:0,title:'操作可见性简历',document:{name:'真实姓名',summary:'负责需求分析',experiences:[{company:'真实企业',role:'产品经理',bullets:Array.from({length:8},(_,i)=>`实际工作内容${i+1}`)}]}}});expect(created.ok()).toBeTruthy();const resume=await created.json();
 await page.goto('/workspace?view=resumes');await inViewport(page,page.locator('.cf-library-featured-actions a').first());const direct=page.locator('.cf-directory-analyze');await expect(direct).toBeVisible();expect(await direct.evaluate(node=>!!node.closest('details'))).toBeFalsy();await direct.click();await expect(page).toHaveURL(new RegExp(`view=jobs&resume_id=${resume.id}`));await expect(page.locator('[data-save-job]')).toBeVisible();await inViewport(page,page.locator('[data-save-job]'));await page.screenshot({path:`output/actions-job-${test.info().project.name}.png`,animations:'disabled'});
 await page.locator('#job-description').fill('岗位要求：需求分析与跨团队协作。');await page.locator('[data-save-job]').click();await expect(page.locator('[data-evidence-category]').first()).toBeVisible({timeout:20000});await page.locator('a[href*="/suggestions"]').first().click();
 await expect(page.locator('.cf-review-actionbar')).toBeVisible();await inViewport(page,page.locator('.cf-review-actionbar a'));await page.screenshot({path:`output/actions-review-${test.info().project.name}.png`,animations:'disabled'});await page.locator('[data-review-text]').first().fill('经过核实的需求分析经历。');await expect(page.locator('[data-review-quick-count]')).toContainText('1 段');
 await page.locator('.cf-review-actionbar a').click();await expect(page.locator('#save-version button[type=submit]')).toBeInViewport();await page.locator('[name=confirmed]').check();await page.locator('#save-version button[type=submit]').click();await expect(page).toHaveURL(/resume_id=/);
 const original=await(await page.request.get(`/api/resumes/${resume.id}`)).json();expect(original.document.summary).toBe('负责需求分析');
});
