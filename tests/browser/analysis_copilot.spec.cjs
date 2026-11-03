const {test,expect}=require('@playwright/test');
const {randomUUID}=require('node:crypto');
let uid;
const csrf=async page=>{const meta=page.locator('meta[name="csrf-token"]');if(await meta.count())return {'X-CSRFToken':await meta.getAttribute('content')};const html=await (await page.request.get('/')).text();return {'X-CSRFToken':html.match(/name="csrf-token" content="([^"]+)"/)[1]};};
const synthetic={name:'合成验收姓名',email:'synthetic@example.com',summary:'负责用户访谈与需求分析',experiences:[{company:'合成企业',bullets:['整理访谈记录','协调需求评审']}],education:[{school:'合成大学',degree:'本科'}],hidden_sections:['education']};
async function resume(page){const r=await page.request.post('/api/resumes',{headers:await csrf(page),data:{request_key:randomUUID(),title:'合成验收简历',document:synthetic}});expect(r.ok()).toBeTruthy();return r.json();}
// The chat only exists for members: free_preview deliberately clears question
// and suggestions, so a non-member never sees a follow-up to answer.
async function member(page){await page.goto('/workspace?view=billing');await page.locator('[data-membership-plan="membership_monthly"] button[type=submit]').click();await page.waitForLoadState('networkidle');}
async function openJob(page,r){const headers=await csrf(page);const j=await page.request.post('/api/jobs',{headers,data:{request_key:randomUUID(),resume_id:r.id,resume_revision:r.revision,title:'合成目标岗位',description:'负责用户访谈；负责需求分析；需要SQL经验'}});expect(j.ok()).toBeTruthy();const job=await j.json();await page.goto(`/jobs/${job.id}`);return job;}
async function screenshots(page,label){for(const theme of ['light','dark']){await page.emulateMedia({colorScheme:'dark',reducedMotion:'reduce'});await page.evaluate(value=>window.cfTheme(value),theme);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${label} ${theme} overflow`).toBeTruthy();await page.screenshot({path:`output/copilot-${label}-${test.info().project.name}-${theme}.png`,fullPage:true,animations:'disabled'});}}

test.beforeEach(async({page})=>{await page.goto('/login');const r=await page.request.post('/__test/session',{headers:await csrf(page),data:{}});uid=(await r.json()).user_id;await page.goto('/workspace');});
test.afterEach(async({page})=>{if(uid)await page.request.post('/__test/cleanup',{headers:await csrf(page),data:{user_id:uid}});});

test('analysis streams into a copilot while results fill the left column',async({page})=>{
  test.setTimeout(120000);
  await member(page);
  const r=await resume(page);
  const job=await openJob(page,r);
  const copilot=page.locator('[data-copilot]');
  const column=page.locator('.cfa-diagnostic-column');
  await expect(copilot).toBeVisible();
  await expect(column).toBeVisible();

  await page.locator('[data-start-ai="analysis"]').click();
  // The stream opens before the provider says anything.
  await expect(page.locator('[data-copilot-live]')).toBeVisible();

  // The recap is persisted on the operation, so the reload replays it.
  await expect(page.locator('[data-copilot-note]')).toContainText('匹配度 60 分',{timeout:60000});
  await expect(page.locator('#match-result')).toContainText('匹配总览');
  // The follow-up question arrives in the thread, with a composer under it.
  await expect(page.locator('[data-copilot-question]')).toContainText('可以补充一个真实项目吗');
  await expect(page.locator('#diagnostic-answer')).toBeVisible();

  // Wide viewports sit side by side; narrow ones stack with the conversation first.
  const box=await copilot.boundingBox(),left=await column.boundingBox();
  if(page.viewportSize().width>960)expect(box.x).toBeGreaterThan(left.x);
  else expect(box.y).toBeLessThan(left.y);
  await screenshots(page,'answer');

  await page.locator('#diagnostic-answer').fill('我负责过用户访谈和需求评审。');
  await page.getByRole('button',{name:'提交并继续'}).click();
  await expect(page.locator('[data-copilot-msg="user"]')).toContainText('我负责过用户访谈和需求评审');
  // Answering starts the next round by itself instead of needing another click.
  await expect(page.locator('[data-copilot-live]')).toBeVisible();
  await expect(page.locator('.cfa-diagnostic-state')).toContainText('已补充 1 / 10 轮经历',{timeout:60000});
  await expect(page.locator('[data-copilot-note]')).toHaveCount(1,{timeout:60000});
  await screenshots(page,'follow-up');
});
