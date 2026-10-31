const {test,expect}=require('@playwright/test');
const {randomUUID}=require('node:crypto');
let userId;
const headers=async page=>({'X-CSRFToken':await page.locator('meta[name="csrf-token"]').getAttribute('content')});
test.beforeEach(async({page})=>{await page.goto('/login');const r=await page.request.post('/__test/session',{data:{},headers:await headers(page)});userId=(await r.json()).user_id;});
test.afterEach(async({page})=>{if(userId)await page.request.post('/__test/cleanup',{data:{user_id:userId},headers:await headers(page)});});
const document={name:'真实姓名',role:'产品经理',summary:'负责用户访谈与产品需求分析',experiences:[{company:'测试企业',role:'产品经理',bullets:['梳理业务需求并跟进上线']}],projects:[{name:'测试项目',description:'整理用户反馈'}]};
async function create(page,title='基础简历') {const r=await page.request.post('/api/resumes',{headers:await headers(page),data:{request_key:randomUUID(),revision:0,title,document}});expect(r.ok()).toBeTruthy();return r.json();}
async function member(page){await page.goto('/workspace?view=billing');await page.locator('.billing-plan-card.is-featured button[type="submit"]').click();await page.waitForLoadState('networkidle');}
test('real covers, rename, copy and create flows form one document library',async({page})=>{
 await member(page);const resume=await create(page);
 await page.goto('/workspace?view=resumes');
 await expect(page.locator('.document-cover [data-rf="name"]')).toContainText('真实姓名');
 await page.locator('.document-menu summary').click();await page.locator('[data-library-rename]').click();
 await page.locator('[data-library-rename-dialog] [name="title"]').fill('修改后的名称');
 await page.locator('[data-library-rename-form] [type="submit"]').click();
 await expect(page.locator('.document-info h2')).toContainText('修改后的名称');
 const original=await (await page.request.get(`/api/resumes/${resume.id}`)).json();expect(original.document).toMatchObject(document);
 await page.locator('.document-menu summary').click();await page.locator('[data-library-copy]').click();
 await expect(page.locator('[data-library-document]')).toHaveCount(2);
 await page.locator('[data-library-sort]').selectOption('name');
 await page.locator('.document-menu summary').first().click();await page.locator('[data-delete-resume]').first().click();
 await expect(page.locator('[data-library-delete-dialog]')).toBeVisible();await page.locator('[data-library-delete-confirm]').click();await expect(page.locator('[data-library-document]')).toHaveCount(1);
 await page.getByRole('button',{name:'空白简历',exact:true}).click();
 await page.locator('[data-create-form] [name="title"]').fill('新的空白简历');
 await page.locator('[data-create-submit]').click();
 await expect(page.locator('#resume-title')).toHaveValue('新的空白简历');
 await expect(page.locator('#resume-name')).toHaveValue('');
 await expect(page.locator('[data-studio-dialog="source"]')).not.toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});
test('continuous editor, design, Markdown, AI review, history and job handoff',async({page})=>{
 await member(page);const resume=await create(page);
 await page.goto(`/workspace?view=resume-new&resume_id=${resume.id}`);
 const editor=page.locator('[data-resume-editor]');
 await expect(page.locator('#resume-basics')).toBeVisible();await expect(page.locator('#resume-summary-section')).not.toHaveAttribute('hidden','');
 const summary=page.locator('#resume-summary');await page.locator('[data-section-tab="summary"]').click();await summary.fill('负责用户访谈与业务分析');
 await page.locator('#resume-summary-section .studio-text-tools button[aria-label="粗体"]').click();await expect(summary).toHaveValue(/\*\*/);
 await expect(editor).toHaveAttribute('data-dirty','false',{timeout:10000});
 await page.locator('#resume-summary-section [data-resume-ai-mode="professional"]').click();
 await expect(page.locator('[data-resume-ai-dialog]:visible [data-resume-ai-accept]')).toBeEnabled({timeout:15000});
 const before=await summary.inputValue();await expect(summary).toHaveValue(before);
 await page.locator('[data-resume-ai-dialog]:visible [data-resume-ai-accept]').click();await expect(summary).toHaveValue(before+'，表达更清晰');
 await page.locator('[data-studio-tab="design"]').click();await expect(editor).toHaveAttribute('data-studio-mode','design');
 await page.locator('[data-template-card="technical"]').click();await expect(page.locator('#resume-template-quick')).toHaveValue('technical');
 await page.locator('[data-design-tab="colors"]').click();await page.locator('[data-design-accent="navy"]').click();await expect(page.locator('[data-resume-stage]')).toHaveAttribute('data-accent','navy');
 await page.locator('[data-design-tab="spacing"]').click();await page.locator('[data-design-size="large"]').click();await expect(page.locator('[data-resume-stage]')).toHaveAttribute('data-size','large');
 await page.locator('[data-design-tab="sections"]').click();await page.getByRole('button',{name:'证书与资格显示状态'}).click();await expect(editor).toHaveAttribute('data-hidden-sections',/certificates/);
 await page.locator('[data-studio-tab="content"]').click();await expect(page.locator('#resume-basics')).toBeVisible();
 if(test.info().project.use.viewport.width>760){
  const splitter=page.getByRole('separator',{name:'调整内容与预览宽度'});const initial=await splitter.getAttribute('aria-valuenow');await splitter.focus();await page.keyboard.press('ArrowRight');expect(await splitter.getAttribute('aria-valuenow')).not.toBe(initial);
  const fields=await page.locator('.resume-fields').boundingBox(),preview=await page.locator('.resume-preview-panel').boundingBox();expect(Math.abs(fields.y-preview.y)).toBeLessThan(3);
 }else{await page.locator('[data-editor-tab="preview"]').click();await expect(page.locator('.resume-preview-panel')).toBeVisible();await page.locator('[data-editor-tab="edit"]').click();}
 await page.locator('[data-save-resume]').click();await expect(editor).toHaveAttribute('data-dirty','false',{timeout:10000});
 await page.locator('[data-version-history]').click();await expect(page.locator('[data-studio-dialog="history"]')).toBeVisible();await expect(page.locator('#version-history button').first()).toBeVisible();await page.keyboard.press('Escape');
 for(const theme of ['light','dark']){await page.locator('#theme-select').selectOption(theme);await expect(page.locator('html')).toHaveAttribute('data-theme',theme);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();await page.screenshot({path:`output/studio-editor-${test.info().project.name}-${theme}.png`,animations:'disabled'});}
 await page.locator('[data-editor-analyze]').click();await expect(page.locator('[data-studio-dialog="job"]')).toBeVisible();await expect(page.locator('[data-studio-job-source]')).toContainText('基础简历');
 await page.locator('[data-studio-job-form] [name="description"]').fill('需要产品经验与业务需求分析能力。');await page.locator('[data-studio-job-form] [type="submit"]').click();await expect(page).toHaveURL(/\/jobs\/\d+/);await expect(page.locator('[data-evidence-category]').first()).toBeVisible({timeout:15000});
});
test('paste creation reviews before applying and templates preview in place',async({page})=>{
 await page.goto('/workspace?view=resumes');await page.locator('[data-create-resume="paste"]').first().click();
 await page.locator('[data-create-form] [name="source"]').fill('真实姓名，产品经理，负责用户访谈与业务需求分析，维护产品迭代计划。');await page.locator('[data-create-form] [name="title"]').fill('粘贴的简历');
 await page.locator('[data-create-submit]').click();
 await expect(page.locator('[data-resume-compose-dialog]')).toBeVisible();await expect(page.locator('[data-compose-accept]')).toBeVisible({timeout:15000});
 await expect(page.locator('#resume-name')).toHaveValue('');await page.locator('[data-compose-accept]').click();await expect(page.locator('#resume-name')).toHaveValue('林测试');
 await page.goto('/workspace?view=resume-template');await page.locator('[data-template-filter="technical"]').click();await expect(page.locator('[data-template-kind]:visible')).toHaveCount(1);
 await page.locator('[data-template-preview="technical"]').click();await expect(page.locator('[data-template-preview-dialog="technical"]')).toBeVisible();await page.keyboard.press('Escape');
 await page.locator('[data-template-kind="technical"] .button.secondary').click();await expect(page.locator('#resume-template-quick')).toHaveValue('technical');
});
test('PDF import checks extracted fields and opens the saved editor',async({page})=>{
 const source=await page.context().newPage();await source.setContent('<h1>Resume Candidate</h1><p>candidate@example.com 13800138000</p><p>Verified product experience.</p>');const pdf=await source.pdf();await source.close();
 await page.goto('/workspace?view=resume-import');
 await page.locator('#resume-file').setInputFiles({name:'candidate.pdf',mimeType:'application/pdf',buffer:pdf});
 await expect(page.locator('#file-selection')).toContainText('candidate.pdf');
 await page.locator('[data-upload-pdf]').click();
 await expect(page.locator('[data-import-confirm]')).toBeVisible({timeout:20000});
 await expect(page.locator('[name="email"]')).toHaveValue('candidate@example.com');
 await page.locator('[name="name"]').fill('已核对姓名');await page.locator('[name="summary"]').fill('真实产品经验');await page.locator('[name="confirmed"]').check();
 await page.locator('[data-import-confirm] [type="submit"]').click();
 await expect(page.locator('#resume-name')).toHaveValue('已核对姓名');await expect(page.locator('#resume-email')).toHaveValue('candidate@example.com');
 await expect(page.locator('[data-studio-dialog="source"]')).toBeVisible();await page.keyboard.press('Escape');
 await expect(page.locator('[data-resume-editor]')).toHaveAttribute('data-dirty','false',{timeout:10000});
});
test('export prints the active resume without workbench chrome',async({page})=>{
 const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),{execFileSync}=require('node:child_process');
 await member(page);const resume=await create(page);await page.goto(`/workspace?view=resume-new&resume_id=${resume.id}`);
 await page.evaluate(()=>window.prepareResumePrint());await page.emulateMedia({media:'print'});
 await expect(page.locator('.studio-globalbar')).toBeHidden();await expect(page.locator('.studio-documentbar')).toBeHidden();
 await expect(page.locator('[data-resume-panel="classic"] .resume-doc')).toBeVisible();
 const pdf=await page.pdf({format:'A4',printBackground:true});const dir=fs.mkdtempSync(path.join(os.tmpdir(),'career-studio-print-'));const file=path.join(dir,'resume.pdf');
 try{fs.writeFileSync(file,pdf);const local=path.join(process.cwd(),'.venv','Scripts','python.exe');const python=process.env.CF_TEST_PYTHON||(fs.existsSync(local)?local:'python');const result=JSON.parse(execFileSync(python,['-c','import json,sys; import pdfplumber; r=pdfplumber.open(sys.argv[1]); print(json.dumps({"pages":len(r.pages),"text":"".join(p.extract_text() for p in r.pages)},ensure_ascii=True))',file],{encoding:'utf8'}));expect(result.pages).toBe(1);expect(result.text).toContain('真实姓名');expect(result.text).not.toContain('职序简历');expect(result.text).not.toContain('学校名称');}finally{fs.rmSync(dir,{recursive:true,force:true});}
});
