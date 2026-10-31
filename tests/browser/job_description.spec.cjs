/*
 * 岗位描述的 Markdown 渲染是安全边界：只允许白名单语法，链接强制 noopener，
 * 不执行原始 HTML，也不渲染图片。用例走新界面（分析详情页的岗位描述折叠区）。
 */
const {test,expect}=require('@playwright/test');
const {randomUUID}=require('node:crypto');
let uid;

const csrf=async page=>{
  const meta=page.locator('meta[name="csrf-token"]');
  if(await meta.count())return {'X-CSRFToken':await meta.getAttribute('content')};
  const html=await (await page.request.get('/')).text();
  return {'X-CSRFToken':html.match(/name="csrf-token" content="([^"]+)"/)[1]};
};

const markdown=[
  '## 岗位职责',
  '- 负责 **产品分析** 与需求拆解',
  '- 使用 `Python` 处理数据',
  '',
  '参考 [项目主页](https://example.com/roles) 与 ![占位图](https://example.com/x.png)',
  '<script>window.__xss=1</script>',
].join('\n');

test.beforeEach(async({page})=>{
  await page.goto('/login');
  const session=await page.request.post('/__test/session',{headers:await csrf(page),data:{}});
  uid=(await session.json()).user_id;
});

test.afterEach(async({page})=>{
  if(uid)await page.request.post('/__test/cleanup',{headers:await csrf(page),data:{user_id:uid}});
});

test('job description renders the safe markdown subset only',async({page})=>{
  const created=await page.request.post('/api/resumes',{
    headers:await csrf(page),
    data:{
      request_key:randomUUID(),
      revision:0,
      title:'合成验收简历',
      document:{
        name:'合成验收姓名',
        email:'synthetic@example.com',
        summary:'负责用户访谈与需求分析',
        experiences:[{company:'合成企业',bullets:['整理访谈记录']}],
      },
    },
  });
  expect(created.ok()).toBeTruthy();
  const resume=await created.json();
  const job=await page.request.post('/api/jobs',{
    headers:await csrf(page),
    data:{
      request_key:randomUUID(),
      resume_id:resume.id,
      resume_revision:resume.revision,
      title:'合成目标岗位',
      description:markdown,
    },
  });
  expect(job.ok()).toBeTruthy();
  const {id}=await job.json();

  await page.goto(`/jobs/${id}`);
  await page.locator('.cfa-jd summary').click();
  const body=page.locator('.cfa-jd .job-markdown');
  await expect(body.locator('h4')).toHaveText('岗位职责');
  await expect(body.locator('li')).toHaveCount(2);
  await expect(body.locator('strong')).toHaveText('产品分析');
  await expect(body.locator('code')).toHaveText('Python');
  await expect(body.locator('a')).toHaveCount(2);
  const rels=await body.locator('a').evaluateAll(els=>els.map(el=>el.getAttribute('rel')));
  expect(rels.every(rel=>rel==='noopener noreferrer'),'外链都带 noopener noreferrer').toBe(true);
  await expect(body.locator('img')).toHaveCount(0);
  await expect(body.locator('script')).toHaveCount(0);
  expect(await page.evaluate(()=>window.__xss)).toBeUndefined();
});
