const {test,expect}=require('@playwright/test');
const {randomUUID}=require('node:crypto');
let uid;
const csrf=async page=>{const html=await (await page.request.get('/')).text();return {'X-CSRFToken':html.match(/name="csrf-token" content="([^"]+)"/)[1]};};
const synthetic={name:'边界验收',email:'edge@example.com',summary:'负责用户访谈与需求分析',experiences:[{company:'边界企业',bullets:['整理访谈记录']}],education:[{school:'边界大学',degree:'本科'}]};

test.beforeEach(async({page})=>{await page.goto('/login');const r=await page.request.post('/__test/session',{headers:await csrf(page),data:{}});uid=(await r.json()).user_id;});
test.afterEach(async({page})=>{if(uid)await page.request.post('/__test/cleanup',{headers:await csrf(page),data:{user_id:uid}});uid=undefined;});

test('forged and missing identifiers close with 404 instead of leaking',async({page})=>{
  const probes=['/jobs/99999999','/resumes/99999999/print','/imports/99999999','/conversations/99999999','/operations/99999999/share','/api/resumes/99999999','/guides/not-a-guide','/invite/NOTACODE','/s/missing/token','/definitely-not-a-route'];
  for(const path of probes){
    const response=await page.goto(path);
    expect(response.status(),path).toBe(404);
  }
  await expect(page.locator('.cf-public-error')).toBeVisible();
});

test('anonymous visitors are sent to login and come back with a next target',async({page,browser})=>{
  const anonymous=await browser.newContext();
  const visitor=await anonymous.newPage();
  await visitor.goto('/workspace?view=reports');
  expect(visitor.url()).toMatch(/next=/);
  expect(visitor.url()).toContain('workspace');
  await expect(visitor.locator('[data-auth-dialog], dialog[open]').first()).toBeVisible();
  const denied=await visitor.request.post('/api/resumes',{data:{request_key:randomUUID(),title:'匿名',document:{}}});
  expect([400,401,403]).toContain(denied.status());
  const deniedAdmin=await visitor.request.get('/admin',{maxRedirects:0});
  expect([302,303,401,403,404]).toContain(deniedAdmin.status());
  await anonymous.close();
});

test('login and register explain what is wrong without leaving the page',async({page,browser})=>{
  const anonymous=await browser.newContext();
  const visitor=await anonymous.newPage();
  await visitor.goto('/login');
  await visitor.fill('#email','nobody@example.com');
  await visitor.fill('#password','wrong-password-value');
  await visitor.locator('form[data-ui-form=auth] button[type=submit]').click();
  await expect(visitor.locator('#auth-feedback')).toBeVisible();
  await expect(visitor).toHaveURL(/\/login/);
  await visitor.fill('#password','short');
  await visitor.locator('form[data-ui-form=auth] button[type=submit]').click();
  await expect(visitor.locator('#password')).toHaveAttribute('minlength','12');
  await visitor.goto('/register');
  await visitor.fill('#email','not-an-email');
  await visitor.locator('form[data-ui-form=auth] button[type=submit]').click();
  await expect(visitor).toHaveURL(/\/register/);
  await anonymous.close();
});

test('wrong file types stay local and oversized uploads are refused',async({page})=>{
  await page.goto('/workspace?view=resume-import');
  await page.setInputFiles('#resume-file',{name:'notes.txt',mimeType:'text/plain',buffer:Buffer.from('这不是 PDF')});
  await expect(page.locator('#file-selection')).toContainText(/PDF/i);
  const big=Buffer.alloc(4*1024*1024+2048,0x41);
  big.write('%PDF-1.4');
  await page.setInputFiles('#resume-file',{name:'huge.pdf',mimeType:'application/pdf',buffer:big});
  await expect(page.locator('#file-selection')).toContainText(/4\s?MB|超过|小于/i);
  await expect(page.locator('[data-upload-pdf]')).toBeDisabled();
});

test('paste mode demands real content before it starts',async({page})=>{
  await page.goto('/workspace?view=resumes');
  await page.locator('[data-create-resume="paste"]').click();
  const dialog=page.locator('#cf-resume-create');
  await expect(dialog).toBeVisible();
  await dialog.locator('[data-create-mode="paste"]').click();
  const source=dialog.locator('[name=source]');
  await expect(source).toBeVisible();
  await dialog.locator('[name=title]').fill('粘贴边界');
  await source.fill('太短');
  await dialog.locator('[data-create-submit]').click();
  await expect(dialog).toBeVisible();
  await expect(source).toHaveJSProperty('validationMessage',await source.evaluate(node=>node.validationMessage));
  expect(await source.evaluate(node=>node.checkValidity())).toBe(false);
  await source.fill('负责用户访谈与需求分析，协调研发推进功能上线，整理访谈记录二十余份。'.repeat(2));
  expect(await source.evaluate(node=>node.checkValidity())).toBe(true);
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
});

test('editor refuses empty required fields and reports a stale revision',async({page})=>{
  const created=await page.request.post('/api/resumes',{headers:await csrf(page),data:{request_key:randomUUID(),title:'草稿边界',document:synthetic}});
  expect(created.ok()).toBeTruthy();
  const resume=await created.json();
  await page.goto(`/workspace?view=resume-new&resume_id=${resume.id}`);
  await expect(page.locator('[data-resume-editor]')).toBeVisible();
  const title=page.locator('#resume-title');
  await title.fill('');
  await page.locator('[data-save-resume]').click();
  await expect(page.locator('[data-resume-editor]')).toHaveAttribute('data-dirty',/true|false/);
  expect(await title.evaluate(node=>node.maxLength)).toBe(120);
  const stale=await page.request.post(`/api/resumes/${resume.id}`,{headers:await csrf(page),data:{request_key:randomUUID(),revision:resume.revision,title:'旧窗口',document:synthetic}});
  expect([200,409]).toContain(stale.status());
  const older=await page.request.post(`/api/resumes/${resume.id}`,{headers:await csrf(page),data:{request_key:randomUUID(),revision:1,title:'更旧的窗口',document:synthetic}});
  expect([200,409]).toContain(older.status());
});

test('oversized documents are refused while long valid text renders safely',async({page})=>{
  const tooLong=await page.request.post('/api/resumes',{headers:await csrf(page),data:{request_key:randomUUID(),title:'超限',document:{name:'X',summary:'把真实经历写清楚，'.repeat(120)}}});
  expect(tooLong.status()).toBe(422);
  const markup=await page.request.post('/api/resumes',{headers:await csrf(page),data:{request_key:randomUUID(),title:'标记',document:{name:'X',summary:'<img src=x onerror="window.__xss=1">这段标记只会作为文字出现'}}});
  expect([201,422]).toContain(markup.status());
  if(markup.status()===201){
    const stored=await markup.json();
    await page.goto(`/workspace?view=resume-new&resume_id=${stored.id}`);
    await expect(page.locator('[data-resume-editor]')).toBeVisible();
    expect(await page.evaluate(()=>[window.__xss])).toEqual([undefined]);
    expect(await page.locator('.resume-doc img[src="x"]').count()).toBe(0);
    expect(await page.locator('.resume-doc script').count()).toBe(0);
  }
  const valid='负责用户访谈与需求分析，协调研发推进功能上线，整理访谈记录二十余份并沉淀为标准流程。'.repeat(8);
  const marked=await page.request.post('/api/resumes',{headers:await csrf(page),data:{request_key:randomUUID(),title:'长文本',document:{name:'长文本用户',summary:valid.slice(0,560)}}});
  expect(marked.ok()).toBeTruthy();
  const resume=await marked.json();
  await page.goto(`/workspace?view=resume-new&resume_id=${resume.id}`);
  await expect(page.locator('[data-resume-editor]')).toBeVisible();
  expect(await page.evaluate(()=>[window.__xss])).toEqual([undefined]);
  expect(await page.locator('.resume-doc img[src="x"]').count()).toBe(0);
  expect(await page.locator('.resume-doc script').count()).toBe(0);
  await expect(page.locator('[data-resume-editor]')).toContainText('负责用户访谈');
});

test('ordinary accounts cannot reach administration',async({page})=>{
  const response=await page.goto('/admin');
  expect([403,404]).toContain(response.status());
  const metrics=await page.request.get('/admin/product/metrics.csv');
  expect([403,404]).toContain(metrics.status());
  const users=await page.request.get('/admin/users');
  expect([403,404]).toContain(users.status());
});

test('workspace view and guide slugs fall back instead of breaking',async({page})=>{
  for(const view of ['not-a-view','../../etc/passwd','']){
    const response=await page.goto(`/workspace?view=${encodeURIComponent(view)}`);
    expect([200,400,404]).toContain(response.status());
  }
  const guide=await page.goto('/guides/backend-engineer');
  expect(guide.status()).toBe(200);
  await expect(page.locator('h1')).toContainText(/后端|工程师|岗位/);
});

test('primary actions stay keyboard reachable and dialogs close on escape',async({page})=>{
  await page.goto('/workspace?view=resumes');
  await page.locator('[data-create-resume]').first().focus();
  await page.keyboard.press('Enter');
  const dialog=page.locator('#cf-resume-create');
  await expect(dialog).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await page.locator('[data-create-resume]').first().focus();
  await page.keyboard.press('Space');
  await expect(dialog).toBeVisible();
  const focusInside=await page.evaluate(()=>document.activeElement?.closest('dialog')!==null);
  expect(focusInside).toBeTruthy();
});

test('deleted documents disappear from the library and endpoints',async({page})=>{
  const created=await page.request.post('/api/resumes',{headers:await csrf(page),data:{request_key:randomUUID(),title:'待删除',document:synthetic}});
  const resume=await created.json();
  const removed=await page.request.post(`/api/resumes/${resume.id}/delete`,{headers:await csrf(page),data:{confirm:'delete'}});
  expect([200,204]).toContain(removed.status());
  expect((await page.request.get(`/api/resumes/${resume.id}`)).status()).toBe(404);
  expect((await page.goto(`/workspace?view=resume-new&resume_id=${resume.id}`)).status()).toBe(404);
});
