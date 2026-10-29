const { test, expect } = require('@playwright/test');
const { randomUUID } = require('node:crypto');
let userId;
const document = { name:'测试', summary:'真实产品经验', experiences:[{company:'示例科技',role:'工程师',bullets:['负责产品需求梳理','整理用户访谈','梳理业务流程','维护项目文档','跟进功能测试']}], projects:[{name:'组件项目',description:'维护页面组件'},{name:'接口项目',description:'编写接口用例'}] };
async function headers(page) { return {'X-CSRFToken': await page.locator('meta[name="csrf-token"]').getAttribute('content')}; }
test.beforeEach(async ({page}) => {
  await page.goto('/login');
  const session=await page.request.post('/__test/session',{data:{},headers:await headers(page)});
  userId=(await session.json()).user_id;
});
test.afterEach(async ({page}) => { if(userId) await page.request.post('/__test/cleanup',{data:{user_id:userId},headers:await headers(page)}); });
async function review(page) {
  await page.goto('/workspace?view=billing');
  await page.locator('.billing-plan-card.is-featured button[type="submit"]').click();
  await page.waitForLoadState('networkidle');
  const h=await headers(page);
  const response=await page.request.post('/api/resumes',{headers:h,data:{request_key:randomUUID(),revision:0,title:'工作台测试',document}});
  expect(response.ok()).toBeTruthy();
  const resume=await response.json();
  const jobResponse=await page.request.post('/api/jobs',{headers:h,data:{request_key:randomUUID(),resume_id:resume.id,resume_revision:resume.revision,title:'产品经理',description:'要求产品经验'}});
  const job=await jobResponse.json();
  await page.goto(`/jobs/${job.id}`);
  const id=await page.locator('[data-diagnostic]').getAttribute('data-diagnostic');
  const start=await page.request.post(`/api/diagnostics/${id}/start`,{headers:await headers(page),data:{request_key:randomUUID(),kind:'analysis'}});
  expect(start.ok()).toBeTruthy();
  const op=await start.json();
  await expect.poll(async()=> (await (await page.request.get(`/api/operations/${op.id}`)).json()).state).toBe('succeeded');
  await page.goto(`/jobs/${job.id}/suggestions?operation_id=${op.id}`);
  return resume;
}
test('paragraph workbench covers text beyond initial suggestions and saves manual changes',async({page})=>{
  const source=await review(page);
  await expect(page.locator('[data-review-path]')).toHaveCount(8);
  await expect(page.locator('.suggestion-context-strip')).toContainText('2 条已有建议');
  await page.locator('[name="confirmed"]').check();
  await page.getByRole('button',{name:'保存所选建议',exact:true}).click();
  await expect(page.locator('#diagnosis-feedback')).toContainText('请选择要保存的段落');
  await expect(page.getByRole('button',{name:'保存所选建议',exact:true})).toBeEnabled();
  const row=page.locator('[data-review-path="experiences.0.bullets.4"]');
  await row.locator('textarea').fill('跟进功能测试并记录问题。');
  await expect(row.locator('[name="suggestion"]')).toBeChecked();
  await page.locator('[name="confirmed"]').check();
  await page.getByRole('button',{name:'保存所选建议',exact:true}).click();
  await expect(page).toHaveURL(/resume_id=/);
  const copiedId=new URL(page.url()).searchParams.get('resume_id');
  expect(Number(copiedId)).not.toBe(source.id);
  const copied=await (await page.request.get(`/api/resumes/${copiedId}`)).json();
  expect(copied.document.experiences[0].bullets[4]).toBe('跟进功能测试并记录问题。');
  const original=await (await page.request.get(`/api/resumes/${source.id}`)).json();
  expect(original.document.experiences[0].bullets[4]).toBe('跟进功能测试');
});
test('single paragraph rewrite is compared and explicitly adopted',async({page})=>{
  await review(page);
  const row=page.locator('[data-review-path="projects.0.description"]');
  const before=await row.locator('textarea').inputValue();
  await row.getByRole('button',{name:'重写这一段',exact:true}).click();
  await expect(row.locator('[data-review-candidate]')).toBeVisible();
  await expect(row.locator('textarea')).toHaveValue(before);
  await row.getByRole('button',{name:'采用这版',exact:true}).click();
  await expect(row.locator('textarea')).toHaveValue(before+'，表达更清晰');
  await expect(row.locator('[name="suggestion"]')).toBeChecked();
  await row.getByRole('button',{name:'还原原文',exact:true}).click();
  await expect(row.locator('textarea')).toHaveValue(before);
  await expect(row.locator('[name="suggestion"]')).not.toBeChecked();
});
test('custom controls support keyboard and all themes without overflow',async({page})=>{
  await review(page);
  const checkbox=page.locator('[name="suggestion"]').first();
  await expect(checkbox).toHaveCSS('appearance','none');
  await checkbox.focus(); await checkbox.press('Space');
  await expect(checkbox).toBeChecked();
  await expect(checkbox).toHaveCSS('outline-style','solid');
  for(const theme of ['light','dark','system']) {
    await page.locator('#theme-select').selectOption(theme);
    await expect(checkbox).toHaveCSS('appearance','none');
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
    await page.screenshot({path:`output/review-${test.info().project.name}-${theme}.png`,fullPage:true,animations:'disabled'});
  }
  const promoted=await page.request.post('/__test/promote',{data:{user_id:userId},headers:await headers(page)});
  expect(promoted.ok()).toBeTruthy();
  await page.goto('/admin/settings');
  const adminCheckbox=page.locator('input[type="checkbox"]').first();
  await expect(adminCheckbox).toHaveCSS('appearance','none');
  await page.screenshot({path:`output/review-controls-admin-${test.info().project.name}.png`,fullPage:true,animations:'disabled'});
});
