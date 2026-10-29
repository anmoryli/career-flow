const {test,expect}=require('@playwright/test');
const {randomUUID}=require('node:crypto');
let userId;
const headers=async p=>({'X-CSRFToken':await p.locator('meta[name="csrf-token"]').getAttribute('content')});
async function member(p){await p.goto('/workspace?view=billing');await p.locator('[data-membership-plan="membership_quarterly"] button[type=submit]').click();await p.waitForLoadState('networkidle');}
async function create(p){const r=await p.request.post('/api/resumes',{headers:await headers(p),data:{request_key:randomUUID(),revision:0,title:'真实基础简历',document:{name:'真实姓名',email:'candidate@example.com',role:'产品经理',summary:'负责用户访谈与产品需求分析',experiences:[{company:'测试企业',role:'产品经理',bullets:['梳理业务需求并跟进上线']}],projects:[{name:'测试项目',description:'整理用户反馈'}]}}});expect(r.ok()).toBeTruthy();return r.json();}
test.beforeEach(async({page})=>{await page.goto('/login');const r=await page.request.post('/__test/session',{headers:await headers(page),data:{}});userId=(await r.json()).user_id;});
test.afterEach(async({page})=>{if(userId)await page.request.post('/__test/cleanup',{headers:await headers(page),data:{user_id:userId}});});
test('every live page uses the new template and resource tree',async({page})=>{
 const errors=[];page.on('pageerror',error=>errors.push(error.message));
 for(const view of ['dashboard','resumes','resume-template','resume-new','resume-import','optimize','jobs','reports','history','settings','billing']){
  const response=await page.goto(`/workspace?view=${view}`);expect(response.status()).toBe(200);
  await expect(page.locator('body')).toHaveAttribute('data-frontend','refactored');
  const assets=await page.locator('link[rel=stylesheet],script[src]').evaluateAll(es=>es.map(e=>e.href||e.src));
  expect(assets.every(url=>url.includes('/frontend/')||url.includes('/vendor/'))).toBeTruthy();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await page.screenshot({path:`output/refactor-${view}-${test.info().project.name}.png`,animations:'disabled',fullPage:view!=='resume-new'});
 }
 expect(errors).toEqual([]);
 await page.request.post('/__test/promote',{headers:await headers(page),data:{user_id:userId}});
 for(const path of ['/admin','/admin/users','/admin/orders','/admin/settings','/admin/audit']){
  const response=await page.goto(path);expect(response.status()).toBe(200);await expect(page.locator('body')).toHaveAttribute('data-frontend','refactored');expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await page.screenshot({path:`output/refactor-${path.replaceAll('/','-')}-${test.info().project.name}.png`,animations:'disabled',fullPage:true});
 }
});
test('new resume library and editor persist real edits and design',async({page})=>{
 await member(page);const resume=await create(page);await page.goto('/workspace?view=resumes');
 await expect(page.locator('[data-library-document]')).toHaveCount(1);
 await page.locator('[data-library-search]').fill('不存在');await expect(page.locator('[data-library-empty]')).toBeVisible();await page.locator('[data-library-search]').fill('');
 await page.goto(`/workspace?view=resume-new&resume_id=${resume.id}`);await expect(page.locator('#resume-name')).toHaveValue('真实姓名');
 await page.locator('#resume-name').fill('更新姓名');await page.locator('[data-save-resume]').click();await expect(page.locator('[data-resume-editor]')).toHaveAttribute('data-dirty','false',{timeout:10000});
 const stored=await (await page.request.get(`/api/resumes/${resume.id}`)).json();expect(stored.document.name).toBe('更新姓名');
 await page.locator('[data-studio-tab="design"]').click();await page.locator('[data-template-card="technical"]').click();
 await expect(page.locator('#resume-template-quick')).toHaveValue('technical');
 await page.locator('[data-design-tab="colors"]').click();await page.locator('[data-design-accent="navy"]').click();
 await page.locator('[data-studio-tab="content"]').click();await page.locator('[data-save-resume]').click();await expect(page.locator('[data-resume-editor]')).toHaveAttribute('data-dirty','false');
 const designed=await (await page.request.get(`/api/resumes/${resume.id}`)).json();expect(designed.template).toBe('technical');expect(designed.document.accent).toBe('navy');
 await page.locator('[data-version-history]').click();await expect(page.locator('#version-history button').first()).toBeVisible();
});
test('new analysis and paragraph review preserve the original resume',async({page})=>{
 await member(page);const resume=await create(page);await page.goto(`/workspace?view=jobs&resume_id=${resume.id}`);
 await page.locator('#job-title').fill('产品经理');await page.locator('#job-description').fill('需要产品规划与业务需求分析经验。');await page.locator('[data-save-job]').click();await expect(page).toHaveURL(/\/jobs\/\d+/);
 await expect(page.locator('[data-evidence-category]').first()).toBeVisible({timeout:20000});await page.locator('[data-evidence-filter="missing"]').click();await expect(page.locator('[data-evidence-filter="missing"]')).toHaveAttribute('aria-pressed','true');
 const review=page.locator('a[href*="/suggestions"]').first();await review.click();await expect(page.locator('[data-review-path]')).toHaveCount(3);
 const row=page.locator('[data-review-path="projects.0.description"]');await row.locator('textarea').fill('整理并核对用户反馈。');await page.locator('[name="confirmed"]').check();await page.locator('[data-apply-suggestions] button[type=submit]').click();await expect(page).toHaveURL(/resume_id=/);
 const copiedId=new URL(page.url()).searchParams.get('resume_id');expect(Number(copiedId)).not.toBe(resume.id);const original=await (await page.request.get(`/api/resumes/${resume.id}`)).json();expect(original.document.projects[0].description).toBe('整理用户反馈');
});
