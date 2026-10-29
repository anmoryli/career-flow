const {test,expect}=require('@playwright/test');
const {randomUUID}=require('node:crypto');
test('document workspace creation, search, responsive themes and editor',async({page})=>{
 await page.goto('/');
 await expect(page.getByRole('heading',{name:/把经历写清楚/ })).toBeVisible();
 await page.getByRole('link',{name:'开始创建简历'}).click();
 await expect(page.locator('[data-save-resume]')).toBeVisible();
 await page.goto('/login');
 const headers={'X-CSRFToken':await page.locator('meta[name="csrf-token"]').getAttribute('content')};
 const session=await page.request.post('/__test/session',{headers,data:{}});const {user_id}=await session.json();
 try{
  for(const title of ['产品经理简历','工程师简历']){
   const result=await page.request.post('/api/resumes',{headers,data:{request_key:randomUUID(),revision:0,title,document:{name:'测试姓名',summary:'真实经历'}}});expect(result.ok()).toBeTruthy();
  }
  await page.goto('/workspace?view=resumes');
  await expect(page.locator('[data-library-document]')).toHaveCount(2);
  await page.locator('[data-library-search]').fill('产品');
  await expect(page.locator('[data-library-document]:visible')).toHaveCount(1);
  await page.locator('[data-library-search]').fill('不存在');
  await expect(page.locator('[data-library-empty]')).toBeVisible();
  await page.locator('[data-library-search]').fill('');
  for(const theme of ['light','dark']){
   await page.locator('#theme-select').selectOption(theme);
   await expect(page.locator('html')).toHaveAttribute('data-theme',theme);
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
   await page.screenshot({path:`output/redesign-library-${test.info().project.name}-${theme}.png`,fullPage:true,animations:'disabled'});
  }
  await page.locator('.document-info h2 a').first().click();
  await expect(page.locator('#resume-name')).toHaveValue('测试姓名');
  await page.locator('#resume-name').fill('修改姓名');
  await page.locator('[data-save-resume]').click();
  await expect(page.locator('#resume-draft-status')).toContainText('已保存');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 }finally{await page.request.post('/__test/cleanup',{headers,data:{user_id}});}
});
test('job input leads to analysis, filterable evidence and paragraph review',async({page})=>{
 await page.goto('/login');
 const headers={'X-CSRFToken':await page.locator('meta[name="csrf-token"]').getAttribute('content')};
 const session=await page.request.post('/__test/session',{headers,data:{}});const {user_id}=await session.json();
 try{
  await page.goto('/workspace?view=billing');
  await page.locator('.billing-plan-card.is-featured button[type="submit"]').click();
  await page.waitForLoadState('networkidle');
  const result=await page.request.post('/api/resumes',{headers,data:{request_key:randomUUID(),revision:0,title:'岗位流程测试',document:{name:'测试姓名',summary:'真实产品经验'}}});expect(result.ok()).toBeTruthy();const resume=await result.json();
  await page.goto(`/workspace?view=jobs&resume_id=${resume.id}`);
  await page.locator('#job-title').fill('产品经理');
  await page.locator('#job-description').fill('需要产品规划与业务需求分析经验。');
  const review = page.locator('[data-ui-form="job"] button[type="submit"]');
  if (await review.count()) await review.click();
  await page.locator('[data-save-job]').click();
  await expect(page).toHaveURL(/\/jobs\/\d+/);
  await expect(page.locator('[data-evidence-category]').first()).toBeVisible({timeout:20000});
  await page.locator('[data-evidence-filter="missing"]').click();
  await expect(page.locator('[data-evidence-filter="missing"]')).toHaveAttribute('aria-pressed','true');
  await expect(page.locator('[data-evidence-category="hard"]')).toBeHidden();
  await page.locator('[data-evidence-filter="all"]').click();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await page.screenshot({path:`output/redesign-analysis-${test.info().project.name}.png`,fullPage:true,animations:'disabled'});
  await page.getByRole('link',{name:'审阅并修改简历'}).click();
  await expect(page.locator('[data-review-path]')).toHaveCount(1);
  for(const view of ['reports','history','settings','billing','resume-template']){
   await page.goto(`/workspace?view=${view}`);
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
   await page.screenshot({path:`output/redesign-${view}-${test.info().project.name}.png`,fullPage:true,animations:'disabled'});
  }
  await page.goto('/workspace?view=reports');
  await page.locator('[data-report-filter="active"]').click();
  await expect(page.locator('[data-report-filter-empty]')).toBeVisible();
  await page.locator('[data-report-filter="succeeded"]').click();
  await expect(page.locator('[data-report-operation]:visible')).toHaveCount(1);
 }finally{await page.request.post('/__test/cleanup',{headers,data:{user_id}});}
});
