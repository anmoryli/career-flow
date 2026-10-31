const { test, expect } = require('@playwright/test');
let uid;
async function csrf(page) {
  return page.locator('meta[name="csrf-token"]').getAttribute('content');
}
async function expectPolishedSelects(page) {
  const customizable = await page.evaluate(() => CSS.supports('appearance', 'base-select'));
  for (const select of await page.locator('select').all()) {
    await expect(select).toHaveCSS('appearance', customizable ? 'base-select' : 'none');
    if (customizable) {
      expect(await select.evaluate(element => getComputedStyle(element, '::picker(select)').borderRadius)).not.toBe('0px');
    } else {
      await expect(select).not.toHaveCSS('background-image', 'none');
    }
    await expect(select).not.toHaveCSS('border-radius', '0px');
  }
}
async function activateQuarterly(page) {
  await page.goto('/workspace?view=billing');
  await expect(page.locator('.billing-plan-card')).toHaveCount(2);
  await expect(page.locator('.billing-plan-card').nth(0)).toContainText('39');
  await expect(page.locator('.billing-plan-card').nth(1)).toContainText('99');
  await page.locator('.billing-plan-card.is-featured button[type="submit"]').click();
  await expect(page.locator('.billing-member-status')).toContainText('\u5b63\u5ea6');
}
async function continueJobAnalysis(page, choice = 'yes') {
  await page.locator('[data-save-job]').click();
  await expect(page.locator('#job-save-dialog')).toBeVisible();
  await page.locator(`[data-job-save-choice="${choice}"]`).click();
}
test.beforeEach(async ({ page }) => {
  await page.goto('/login');
  const response = await page.request.post('/__test/session', { data: {}, headers: { 'X-CSRFToken': await csrf(page) } });
  uid = (await response.json()).user_id;
});
test.afterEach(async ({ page }) => {
  if (uid) await page.request.post('/__test/cleanup', { data: { user_id: uid }, headers: { 'X-CSRFToken': await csrf(page) } });
});
test('landing page remains accessible to signed-in users', async ({ page }) => {
  const response = await page.goto('/');
  expect(response.status()).toBe(200);
  await expect(page.locator('.landing-page')).toBeVisible();
  await expect(page.getByRole('heading', { name: /把经历写清楚/ })).toBeVisible();
  await expect(page.getByRole('link', { name: /进入工作空间/ }).first()).toHaveAttribute('href', '/workspace');
});
test('workspace home presents a personal next step instead of a metric dashboard', async ({ page }) => {
  await page.goto('/workspace');
  await expect(page.locator('.workspace-home-hero')).toBeVisible();
  expect(parseFloat(await page.locator('.workspace-home-hero').evaluate(element => getComputedStyle(element).paddingLeft))).toBeGreaterThan(10);
  await expect(page.locator('.workspace-path')).toHaveCount(0);
  await expect(page.locator('.workspace-entryways>a')).toHaveCount(3);
  await expect(page.locator('.workspace-home-greeting')).toContainText('浏览器测试');
  await expect(page.locator('.workspace-entryways>a>span').first()).toHaveCSS('display', 'grid');
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await expect(page.locator('.workspace-home-hero')).toHaveCSS('animation-name', 'none');
  for (const theme of ['light', 'dark', 'system']) {
    await page.locator('#theme-select').selectOption(theme);
    await expect(page.locator('.workspace-home-greeting')).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  }
  await page.screenshot({ path: `output/overview-${test.info().project.name}.png`, fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});
test('workspace home follows the current resume when one exists', async ({ page }) => {
  await create(page);
  const resumeId = new URL(page.url()).searchParams.get('resume_id');
  await page.goto('/workspace');
  await expect(page.locator('.workspace-home-hero')).toContainText('继续编辑');
  await expect(page.locator('.workspace-home-actions a').first()).toHaveAttribute('href', new RegExp(`resume_id=${resumeId}`));
  await expect(page.locator('.workspace-entryways')).toHaveCount(0);
  const longTitle = 'CareerFlowResumeWithoutSpaces'.repeat(4);
  await page.goto(`/workspace?view=resume-new&resume_id=${resumeId}`);
  await page.locator('#resume-title').fill(longTitle);
  await saved(page);
  await page.goto('/workspace');
  await expect(page.locator('.workspace-home-next')).toContainText(longTitle);
  expect(await page.locator('.workspace-home-next').evaluate(element => element.scrollWidth <= element.clientWidth)).toBeTruthy();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});
test('starting a new resume does not preload the previous resume', async ({ page }) => {
  await create(page);
  const existingId = new URL(page.url()).searchParams.get('resume_id');
  await page.goto('/workspace?view=resumes');
  await page.getByRole('link', { name: /粘贴简历文字/ }).click();
  await expect(page).toHaveURL(/view=resume-new&start=paste/);
  await expect(page.locator('[data-resume-editor]')).toHaveAttribute('data-saved', 'null');
  await expect(page.locator('#resume-name')).toHaveValue('');
  await expect(page.locator('#resume-summary')).toHaveValue('');
  expect(new URL(page.url()).searchParams.has('resume_id')).toBeFalsy();
  await page.goto(`/workspace?view=resume-new&resume_id=${existingId}`);
  await expect(page.locator('#resume-name')).toHaveValue('林测试');
});
async function saved(page) {
  await expect(page.locator('[data-resume-editor]')).toHaveAttribute('data-dirty', 'false');
}
async function create(page) {
  await page.goto('/workspace?view=resume-new');
  await expect(page.locator('[data-section-tab="summary"]')).toBeVisible({ timeout: 15000 });
  await page.locator('#resume-title').fill('林测试简历');
  await page.locator('#resume-name').fill('林测试');
  await page.locator('[data-section-tab="summary"]').click();
  await page.locator('#resume-summary').fill('真实产品经验');
  await saved(page);
}
test('saved job descriptions can be imported into a new analysis without duplicating records', async ({ page }) => {
  await create(page);
  const resumeId = new URL(page.url()).searchParams.get('resume_id');
  await page.goto(`/workspace?view=jobs&resume_id=${resumeId}`);
  await page.locator('#job-title').fill('Java 后端工程师');
  await page.locator('#job-company').fill('示例科技');
  await page.locator('#job-description').fill('负责 Java 服务开发与线上维护');
  await page.locator('.job-optional-link summary').click();
  await page.locator('#job-url').fill('https://jobs.example.com/backend');
  await continueJobAnalysis(page, 'yes');
  await expect(page).toHaveURL(/\/jobs\/\d+/);
  await page.goto('/workspace?view=jobs');
  await expect(page.locator('.job-saved-item')).toHaveCount(1);
  await page.locator('#job-title').fill('临时填写');
  await page.locator('#saved-job-select').selectOption({ index: 1 });
  page.once('dialog', dialog => dialog.accept());
  await page.locator('[data-import-saved-job]').click();
  await expect(page.locator('#job-title')).toHaveValue('Java 后端工程师');
  await expect(page.locator('#job-company')).toHaveValue('示例科技');
  await expect(page.locator('#job-description')).toHaveValue('负责 Java 服务开发与线上维护');
  await expect(page.locator('#job-url')).toHaveValue('https://jobs.example.com/backend');
  await expect(page.locator('#analysis-resume')).toHaveValue(resumeId);
  await expect(page.locator('.job-saved-item')).toHaveCount(1);
  await expect(page.locator('[data-import-job-status]')).toContainText('已导入');
});
test('job confirmation goes straight to the save choice and unsaved analysis stays out of the import library', async ({ page }) => {
  await create(page);
  const resumeId = new URL(page.url()).searchParams.get('resume_id');
  await page.goto(`/workspace?view=jobs&resume_id=${resumeId}`);
  await page.locator('#job-title').fill('临时岗位测试');
  await page.locator('#job-description').fill('负责 Java 服务开发与线上维护');
  await expect(page.locator('.job-saved-item')).toHaveCount(0);
  await expect(page.locator('[data-save-job]')).toBeVisible();
  await expect(page.locator('#job-review')).toHaveCount(0);
  await page.locator('[data-save-job]').click();
  await expect(page.locator('#job-save-dialog')).toBeVisible();
  await expect(page.locator('.job-saved-item')).toHaveCount(0);
  await page.locator('[data-job-save-choice="no"]').click();
  await expect(page).toHaveURL(/\/jobs\/\d+/);
  const jobId = new URL(page.url()).pathname.split('/').at(-1);
  const job = await (await page.request.get(`/api/jobs/${jobId}`)).json();
  expect(job.is_saved).toBe(false);
  await page.goto('/workspace?view=jobs');
  await expect(page.locator('.job-saved-item')).toHaveCount(0);
});
test('job analysis visibly asks for a resume and a job before the description form', async ({ page }) => {
  await create(page);
  const resumeId = new URL(page.url()).searchParams.get('resume_id');
  await page.goto(`/workspace?view=jobs&resume_id=${resumeId}`);
  await expect(page.getByRole('heading', { name: '选择简历' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '选择岗位' })).toBeVisible();
  await expect(page.locator('#analysis-resume')).toBeVisible();
  await expect(page.locator('#job-description')).toBeVisible();
  await expectPolishedSelects(page);
  const firstChoice = await page.locator('.job-selection-grid').boundingBox();
  const description = await page.locator('#job-description').boundingBox();
  expect(firstChoice.y).toBeLessThan(description.y);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});
test('select controls keep their theme styling in the resume editor and job workflow', async ({ page }) => {
  await create(page);
  await expectPolishedSelects(page);
  const resumeId = new URL(page.url()).searchParams.get('resume_id');
  await page.goto(`/workspace?view=jobs&resume_id=${resumeId}`);
  await expectPolishedSelects(page);
});
test('free user can save a resume but cannot export its PDF', async ({ page }) => {
  await page.addInitScript(() => { window.__printCount = 0; window.print = () => { window.__printCount += 1; }; });
  await page.goto('/workspace?view=resume-new');
  await expect(page.locator('[data-print-resume]')).toHaveCount(0);
  await expect(page.locator('.page-actions a[href*="view=billing"]')).toBeVisible();
  await page.locator('#resume-name').fill('Free account test');
  await page.locator('[data-save-resume]').click();
  await saved(page);
  const resumeId = new URL(page.url()).searchParams.get('resume_id');
  expect((await page.request.get(`/resumes/${resumeId}/print`)).status()).toBe(403);
  expect(await page.evaluate(() => window.__printCount)).toBe(0);
});
test('saving and exporting keeps only entered resume fields', async ({ page }) => {
  await activateQuarterly(page);
  await page.addInitScript(() => { window.__printCount = 0; window.print = () => { window.__printCount += 1; }; });
  await page.goto('/workspace?view=resume-new');
  await page.locator('#resume-name').fill('林测试');
  await page.locator('[data-section-tab="summary"]').click();
  await page.locator('#resume-summary').fill('真实经历简介');
  await page.locator('[data-add-custom-section]').click();
  const custom = page.locator('[data-custom-section-editor]').last();
  await expect(custom.locator('input')).toHaveValue('');
  await custom.locator('textarea').fill('额外的真实经历');
  await saved(page);
  const id = new URL(page.url()).searchParams.get('resume_id');
  const stored = await (await page.request.get(`/api/resumes/${id}`)).json();
  expect(stored.document.name).toBe('林测试');
  expect(stored.document.summary).toBe('真实经历简介');
  expect(stored.document.experiences).toEqual([]);
  expect(stored.document.projects).toEqual([]);
  expect(stored.document.education).toEqual([]);
  expect(stored.document.skills).toEqual([]);
  expect(stored.document.certificates).toEqual([]);
  expect(stored.document.languages).toEqual([]);
  expect(stored.document.custom_sections).toEqual([{ id: expect.any(String), title: '', content: '额外的真实经历' }]);
  if (test.info().project.name === 'mobile') await page.locator('[data-editor-tab="preview"]').click();
  await page.locator('#resume-preview-mode').selectOption('sample');
  await expect(page.locator('.resume-panel[data-resume-panel="classic"]')).toContainText('林澄');
  page.once('dialog', dialog => dialog.accept());
  await page.locator('[data-print-resume]').click();
  await expect(page.locator('.resume-panel[data-resume-panel="classic"]')).toContainText('林测试');
  await expect(page.locator('.resume-panel[data-resume-panel="classic"]')).not.toContainText('林澄');
  expect(await page.evaluate(() => window.__printCount)).toBe(1);
});
test('resume history timestamps include minute precision and timezone', async ({ page }) => {
  await create(page);
  const resumeId = new URL(page.url()).searchParams.get('resume_id');
  await page.goto('/workspace?view=history');
  await expect(page.locator('[data-history-row][data-record-type="resume"] time').first())
    .toHaveText(/\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC\+8/);
  await page.goto('/workspace?view=resumes');
  await expect(page.locator('.resume-list-card small').first())
    .toContainText(/\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC\+8/);
  await page.goto(`/workspace?view=resume-new&resume_id=${resumeId}`);
  await page.locator('[data-version-history]').click();
  await expect(page.locator('#version-history button').first())
    .toContainText(/\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC\+8/);
});
test('manual resume creation selects a template before opening the editor', async ({ page }) => {
  await create(page);
  const existingId = new URL(page.url()).searchParams.get('resume_id');
  await page.goto('/workspace?view=resumes');
  await page.getByRole('link', { name: /从模板创建/ }).click();
  await expect(page).toHaveURL(/view=resume-template$/);
  await expect(page.locator('[data-resume-editor]')).toHaveCount(0);
  const templateCards = page.locator('[data-template-choice]');
  await expect(templateCards).toHaveCount(3);
  const cardLayout = await templateCards.evaluateAll(cards => cards.map(card => {
    const rect = card.getBoundingClientRect();
    return { top: rect.top, height: rect.height };
  }));
  expect(cardLayout.every((item, index) => item.height < 240 && (index === 0 || item.top > cardLayout[index - 1].top))).toBeTruthy();
  await page.locator('[data-template-choice="modern"]').click();
  await expect(page).toHaveURL(/view=resume-new.*create=1.*template=modern/);
  await expect(page.locator('[data-resume-editor]')).toBeVisible();
  await expect(page.locator('[data-resume-editor]')).toHaveAttribute('data-saved', 'null');
  await expect(page.locator('[data-resume-stage]')).toHaveAttribute('data-active-template', 'modern');
  await expect(page.locator('input[name="resume-template"][value="modern"]')).toBeChecked();
  await expect(page).not.toHaveURL(new RegExp(`resume_id=${existingId}`));
});
test('resume list exposes delete and personal center navigation', async ({ page }) => {
  await create(page);
  const resumeId = new URL(page.url()).searchParams.get('resume_id');
  await page.goto('/workspace?view=resumes');
  await page.locator('.workspace-account-menu summary').click();
  await expect(page.getByRole('link', { name: '个人中心' })).toBeVisible();
  const resumeRow = page.locator('.resume-list-card').filter({ hasText: '林测试简历' });
  await expect(resumeRow.getByRole('button', { name: '删除简历：林测试简历' })).toBeVisible();
  await page.getByRole('link', { name: '个人中心' }).click();
  await expect(page.getByRole('heading', { name: '个人中心' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '个人信息' })).toBeVisible();
  await page.goto('/workspace?view=resumes');
  page.once('dialog', dialog => dialog.accept());
  await page.locator(`.resume-list-card:has([data-delete-resume="${resumeId}"])`).getByRole('button', { name: '删除简历：林测试简历' }).click();
  await expect(page.locator('.resume-list-card')).toHaveCount(0);
  expect((await page.request.get(`/api/resumes/${resumeId}`)).status()).toBe(404);
});
test('synthetic resume dataset creates distinct records and survives reload', async ({ page }) => {
  await activateQuarterly(page);
  const candidates = require('./fixtures/resume-dataset.json');
  const ids = [];
  for (const candidate of candidates) {
    await page.goto('/workspace?view=resume-new');
    await page.locator('#resume-title').fill(candidate.title);
    await page.locator('#resume-name').fill(candidate.name);
    await page.locator('#resume-role').fill(candidate.role);
    await page.locator('#resume-email').fill(candidate.email);
    await page.locator('#resume-city').fill(candidate.city);
    await page.locator('[data-section-tab="summary"]').click();
    await page.locator('#resume-summary').fill(candidate.summary);
    await page.locator('[data-section-tab="experiences"]').click();
    await page.locator('[data-rf-field="experiences.0.company"]').fill(candidate.company);
    await page.locator('[data-rf-field="experiences.0.bullets"]').fill(candidate.bullet);
    await page.locator('[data-section-tab="template"]').click();
    const templateChoice = page.locator(`.template-choice:has(input[name="resume-template"][value="${candidate.template}"])`);
    await templateChoice.click();
    await expect(templateChoice.locator('input')).toBeChecked();
    await saved(page);
    const id = new URL(page.url()).searchParams.get('resume_id');
    ids.push(id);
    const stored = await (await page.request.get(`/api/resumes/${id}`)).json();
    expect(stored.title).toBe(candidate.title);
    expect(stored.document.name).toBe(candidate.name);
    expect(stored.document.role).toBe(candidate.role);
    expect(stored.document.email).toBe(candidate.email);
    expect(stored.document.city).toBe(candidate.city);
    expect(stored.document.experiences[0].company).toBe(candidate.company);
    expect(stored.document.experiences[0].bullets).toContain(candidate.bullet);
    expect(stored.template).toBe(candidate.template);
  }
  expect(new Set(ids).size).toBe(candidates.length);
  await page.goto('/workspace?view=resumes');
  await expect(page.locator('.resume-list-card')).toHaveCount(candidates.length);
  await page.reload();
  await expect(page.locator('.resume-list-card').filter({ hasText: candidates.at(-1).title })).toHaveCount(1);
});
test('draft autosave, refresh, templates, repeat entries, history, export', async ({ page }) => {
  await activateQuarterly(page);
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await create(page);
  await page.locator('[data-section-tab="experiences"]').click();
  await page.locator('#resume-experience [data-add-entry]').click();
  await page.locator('[data-rf-field="experiences.0.company"]').fill('?????');
  await page.locator('[data-rf-field="experiences.1.company"]').fill('第三家公司');
  await saved(page);
  const storedResume = await (await page.request.get(`/api/resumes/${new URL(page.url()).searchParams.get('resume_id')}`)).json();
  expect(storedResume.document.experiences, JSON.stringify(storedResume.document.experiences)).toHaveLength(2);
  await page.reload();
  await page.locator('[data-section-tab="experiences"]').click();
  await expect(page.locator('#resume-name')).toHaveValue('林测试');
  await expect(page.locator('[data-rf-field="experiences.1.company"]')).toHaveValue('第三家公司');
  if (test.info().project.name === 'mobile') await page.locator('[data-editor-tab="preview"]').click();
  await page.locator('#resume-template-quick').selectOption('modern');
  await saved(page);
  await page.reload();
  await expect(page.locator('#resume-template-quick')).toHaveValue('modern');
  await page.locator('[data-version-history]').click();
  await expect(page.locator('#version-history button').first()).toBeVisible();
  if (test.info().project.name === 'mobile') {
    await page.locator('[data-editor-tab="preview"]').click();
    await expect(page.locator('.resume-preview-panel')).toBeVisible();
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({ path: `output/editor-${test.info().project.name}.png` });
  expect(errors).toEqual([]);
  const rid = new URL(page.url()).searchParams.get('resume_id');
  const print = await page.context().newPage();
  await print.goto(`/resumes/${rid}/print`);
  await expect(print.locator('.resume-doc')).toContainText('林测试');
  await print.pdf({ path: `output/resume-${test.info().project.name}.pdf`, format: 'A4', printBackground: true });
  await print.close();
});
test('save failure preserves input and retries, clear requires confirmation', async ({ page }) => {
  await page.goto('/workspace?view=resume-new');
  await page.route('**/api/resumes', route => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: '测试网络失败' }) }));
  await page.locator('#resume-name').fill('不会丢失');
  await expect(page.locator('[data-resume-editor]')).toHaveAttribute('data-dirty', 'true');
  await expect(page.locator('#resume-name')).toHaveValue('不会丢失');
  await page.unroute('**/api/resumes');
  await page.locator('[data-save-resume]').click(); await saved(page);
  page.once('dialog', dialog => dialog.dismiss());
  await page.locator('[data-clear-sample]').click();
  await expect(page.locator('#resume-name')).toHaveValue('不会丢失');
});
test('resume to job to report and accepted version', async ({ page }) => {
  await activateQuarterly(page);
  await create(page);
  await page.locator('[data-section-tab="experiences"]').click();
  await page.locator('[data-rf-field="experiences.0.company"]').fill('测试公司');
  await page.locator('[data-rf-field="experiences.0.bullets"]').fill('负责产品需求梳理');
  await saved(page);
  const rid = new URL(page.url()).searchParams.get('resume_id');
  await page.goto(`/workspace?view=jobs&resume_id=${rid}`);
  await page.locator('#job-title').fill('产品经理');
  await page.locator('#job-description').fill('具备真实产品经验');
  await page.locator('[data-ui-form="job"] button[type="submit"]').click();
  await continueJobAnalysis(page, 'no');
  await expect(page).toHaveURL(/\/jobs\/\d+/);
  await page.route('**/api/diagnostics/*/start', async route => {
    const response = await route.fetch();
    await page.waitForTimeout(600);
    await route.fulfill({ response });
  });
  const startResponse = page.waitForResponse(response => response.url().includes('/api/diagnostics/') && response.url().endsWith('/start'));
  await page.locator('.diagnosis-more-actions summary').click();
  await page.locator('[data-start-ai="report"]').click();
  await expect(page.locator('.diagnosis-running-stages')).toBeVisible();
  await expect(page.locator('.diagnosis-running-art')).toBeVisible();
  await expect(page.locator('.diagnosis-running-visual')).toHaveCount(0);
  await page.screenshot({ path: `output/diagnosis-running-${test.info().project.name}.png` });
  expect((await startResponse).status()).toBe(200);
  await expect(page.locator('#fee-confirmation')).toHaveCount(0);
  await expect(page.locator('[data-operation-state="succeeded"]')).toBeVisible({ timeout: 20000 });
  await expect(page.getByText('这份岗位报告已完成', { exact: false })).toBeVisible({ timeout: 20000 });
  await expect(page.getByText('开发测试结果，非真实模型输出')).toBeVisible();
  await expect(page.locator('.diagnosis-score-chip')).toContainText('/ 100');
  await expect(page.locator('.diagnosis-meter span')).toHaveCount(5);
  await expect(page.locator('[data-apply-suggestions]')).toHaveCount(0);
  await page.getByRole('link', { name: '查看并核实建议' }).click();
  await expect(page).toHaveURL(/\/jobs\/\d+\/suggestions\?operation_id=\d+/);
  await expect(page.locator('.suggestion-review-item')).toHaveCount(2);
  await page.locator('[name="suggestion"]').first().check();
  await page.locator('[name="suggestion"]').nth(1).check();
  await page.locator('[name="confirmed"]').check();
  await page.locator('[data-apply-suggestions] button[type="submit"]').click();
  await expect(page).toHaveURL(/resume_id=/);
  await expect(page.locator('#resume-summary')).toHaveValue('真实产品经验。');
  await page.locator('[data-section-tab="experiences"]').click();
  await expect(page.locator('[data-rf-field="experiences.0.bullets"]')).toHaveValue('负责产品需求梳理。');
  await page.goto('/workspace?view=reports');
  await expect(page.getByRole('heading', { name: '诊断与报告' })).toBeVisible();
  await expect(page.locator('.report-card')).toContainText('产品经理');
  await expect(page.locator('[data-apply-suggestions]')).toHaveCount(0);
  await page.locator('.report-open').first().click();
  await expect(page).toHaveURL(/\/jobs\/\d+/);
  await expect(page.locator('[data-diagnostic]')).toBeVisible();
  await expect(page.locator('[data-operation-state="succeeded"]')).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/\/workspace\?view=reports/);
  await expect(page.locator('.report-card')).toContainText('产品经理');
  await page.goto('/workspace?view=history');
  await expect(page.locator('[data-apply-suggestions]')).toHaveCount(0);
});
test('diagnosis follow-up is focused, persistent, and easy to answer or skip', async ({ page }) => {
  await activateQuarterly(page);
  await create(page);
  const rid = new URL(page.url()).searchParams.get('resume_id');
  await page.goto(`/workspace?view=jobs&resume_id=${rid}`);
  await page.locator('#job-title').fill('Java 后端工程师');
  await page.locator('#job-description').fill('负责 Java 服务开发与线上维护');
  await page.locator('[data-ui-form="job"] button[type="submit"]').click();
  await continueJobAnalysis(page, 'no');
  await expect(page).toHaveURL(/\/jobs\/\d+/);

  await expect(page.locator('[data-start-ai]:visible')).toHaveCount(1);
  await page.locator('[data-start-ai="analysis"]').click();
  await expect(page.locator('[data-operation-state="succeeded"]')).toBeVisible({ timeout: 20000 });
  await expect(page.getByRole('heading', { name: '补充一点真实经历' })).toBeVisible();
  await expect(page.locator('.diagnosis-current-question')).toContainText('可以补充一个真实项目吗？');
  await expect(page.locator('.diagnosis-context-card')).toContainText('Java 后端工程师');
  await expect(page.locator('#diagnostic-answer')).toHaveAttribute('placeholder', /实际做过/);
  await expect(page.getByRole('button', { name: '提交并继续' })).toBeVisible();
  await expect(page.getByRole('button', { name: '跳过' })).toBeVisible();

  await page.locator('#diagnostic-answer').fill('我负责过 Java 服务开发和线上故障处理。');
  await page.getByRole('button', { name: '提交并继续' }).click();
  await expect(page.locator('.diagnosis-stepper')).toContainText('1 / 10 轮');
  await page.locator('.diagnosis-answer-history summary').click();
  await expect(page.locator('.diagnosis-answer-list .is-user-answer').last()).toContainText('我负责过 Java 服务开发和线上故障处理。');

  await page.locator('[data-start-ai="analysis"]').click();
  await expect(page.locator('[data-operation-state="succeeded"]')).toHaveCount(1, { timeout: 20000 });
  await expect(page.locator('.diagnosis-history-list article')).toHaveCount(1);
  await page.getByRole('button', { name: '跳过' }).click();
  await page.locator('.diagnosis-answer-history summary').click();
  await expect(page.locator('.diagnosis-answer-list .is-user-answer').last()).toContainText('本轮已跳过');
  await expect(page.locator('.diagnosis-answer-list article')).toHaveCount(2);
});
test('themes, navigation, registration modal and keyboard', async ({ page }) => {
  await page.goto('/workspace');
  await expect(page.locator('.workspace-nav')).toBeVisible();
  for (const theme of ['dark', 'light', 'system']) {
    await Promise.all([page.waitForResponse(response => response.url().endsWith('/settings/theme') && response.request().method() === 'POST'), page.locator('#theme-select').selectOption(theme)]);
    await expect(page.locator('html')).toHaveAttribute('data-preference', theme);
  }
  await page.emulateMedia({ colorScheme: 'dark' });
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.emulateMedia({ colorScheme: 'light' });
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.context().clearCookies();
  await page.goto('/register');
  await expect(page.locator('#auth-dialog')).toBeVisible();
  await expect(page.locator('[data-auth-modal-form="register"] input[type="email"]:visible')).toHaveCount(1);
  await expect(page.locator('[data-auth-modal-form="register"] input[name="display_name"]')).toBeFocused();
});

test('password recovery is usable on each screen size', async ({ browser, page }) => {
  const context = await browser.newContext({ viewport: page.viewportSize() });
  const recovery = await context.newPage();
  try {
    await recovery.goto('/login');
    await expect(recovery.getByRole('link', { name: '忘记密码' })).toHaveAttribute('href', '/password/reset');
    await recovery.goto('/password/reset');
    await expect(recovery.getByRole('heading', { name: '找回密码' })).toBeVisible();
    await recovery.locator('#reset-email').fill(`missing-${test.info().project.name}-${uid}@example.com`);
    await expect(recovery.getByRole('button', { name: '发送验证码' })).toBeEnabled();
    await expect(recovery.locator('#reset-code')).toBeVisible();
    expect(await recovery.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  } finally {
    await context.close();
  }
});

test('PDF upload, text extraction, explicit confirmation, saved editor', async ({ page }) => {
  const source = await page.context().newPage();
  await source.setContent('<h1>Test Candidate</h1><p>candidate@example.com 13800138000</p><p>Product experience</p>');
  const pdf = await source.pdf(); await source.close();
  await page.goto('/workspace?view=resume-import');
  await page.locator('#resume-file').setInputFiles({ name: 'resume.pdf', mimeType: 'application/pdf', buffer: pdf });
  await page.locator('[data-upload-pdf]').click();
  await expect(page.locator('[data-import-confirm]')).toBeVisible({ timeout: 20000 });
  await expect(page.locator('[name="email"]')).toHaveValue('candidate@example.com');
  await page.locator('[name="name"]').fill('核对后的姓名');
  await page.locator('[name="summary"]').fill('真实产品经历');
  await page.locator('[name="confirmed"]').check();
  await page.locator('[data-import-confirm] button').click();
  await expect(page.locator('#resume-name')).toHaveValue('核对后的姓名');
  await expect(page.locator('#resume-email')).toHaveValue('candidate@example.com');
});

test('PDF import creates and names a new resume in the history', async ({ page }) => {
  await create(page);
  const originalId = new URL(page.url()).searchParams.get('resume_id');
  const original = await (await page.request.get(`/api/resumes/${originalId}`)).json();
  const source = await page.context().newPage();
  await source.setContent('<h1>PDF Import Test</h1><p>new.resume@example.test</p><p>Verified experience from the source document.</p>');
  const pdf = await source.pdf();
  await source.close();
  await page.goto('/workspace?view=resumes');
  await page.getByRole('link', { name: /上传 PDF/ }).click();
  await expect(page).toHaveURL(/view=resume-import$/);
  await page.locator('#resume-file').setInputFiles({ name: '李梦杰简历.pdf', mimeType: 'application/pdf', buffer: pdf });
  await page.locator('[data-upload-pdf]').click();
  await expect(page.locator('[data-import-confirm]')).toBeVisible({ timeout: 20000 });
  await expect(page.locator('[data-import-confirm] [name="title"]')).toHaveValue('李梦杰简历');
  await expect(page).not.toHaveURL(/resume_id=/);
  await page.locator('[data-import-confirm] [name="name"]').fill('PDF Import Test');
  await page.locator('[data-import-confirm] [name="summary"]').fill('Verified experience from the source document.');
  await page.locator('[data-import-confirm] [name="confirmed"]').check();
  await page.locator('[data-import-confirm] button[type="submit"]').click();
  await expect(page).toHaveURL(/resume_id=\d+$/);
  const newId = new URL(page.url()).searchParams.get('resume_id');
  expect(newId).not.toBe(originalId);
  const created = await (await page.request.get(`/api/resumes/${newId}`)).json();
  expect(created.title).toBe('李梦杰简历');
  expect(created.revision).toBe(1);
  expect(created.document.name).toBe('PDF Import Test');
  const unchanged = await (await page.request.get(`/api/resumes/${originalId}`)).json();
  expect(unchanged.revision).toBe(original.revision);
  expect(unchanged.title).toBe(original.title);
  await page.goto('/workspace?view=resumes');
  await expect(page.locator('.resume-list-card')).toHaveCount(2);
  await expect(page.locator('.resume-list-card').filter({ hasText: '李梦杰简历' })).toBeVisible();
  await page.goto('/workspace?view=history');
  await expect(page.locator('[data-history-row][data-record-type="resume"]').filter({ hasText: '李梦杰简历' })).toBeVisible();
});

test('PDF import replaces the selected resume instead of adding a list record', async ({ page }) => {
  await create(page);
  const resumeId = new URL(page.url()).searchParams.get('resume_id');
  const before = await (await page.request.get(`/api/resumes/${resumeId}`)).json();
  const source = await page.context().newPage();
  await source.setContent('<h1>周屿</h1><p>zhou.yu@example.test</p><p>后端开发与服务维护</p>');
  const pdf = await source.pdf();
  await source.close();
  await page.goto(`/workspace?view=resume-import&resume_id=${resumeId}`);
  await page.locator('#resume-file').setInputFiles({ name: 'zhou-resume.pdf', mimeType: 'application/pdf', buffer: pdf });
  await page.locator('[data-upload-pdf]').click();
  await expect(page.locator('[data-import-confirm]')).toBeVisible({ timeout: 20000 });
  await page.locator('[data-import-confirm] [name="title"]').fill('周屿简历');
  await page.locator('[data-import-confirm] [name="name"]').fill('周屿');
  await page.locator('[data-import-confirm] [name="summary"]').fill('后端开发与服务维护经验');
  await page.locator('[data-import-confirm] [name="confirmed"]').check();
  await page.locator('[data-import-confirm] button[type="submit"]').click();
  await expect(page).toHaveURL(new RegExp(`/workspace\\?view=resume-new&resume_id=${resumeId}$`));
  const after = await (await page.request.get(`/api/resumes/${resumeId}`)).json();
  expect(after.id).toBe(before.id);
  expect(after.revision).toBeGreaterThan(before.revision);
  expect(after.title).toBe('周屿简历');
  expect(after.document.name).toBe('周屿');
  expect(after.document.summary).toBe('后端开发与服务维护经验');
  await page.goto('/workspace?view=resumes');
  await expect(page.locator('.resume-list-card')).toHaveCount(1);
  await expect(page.locator('.resume-list-card')).toContainText('周屿简历');
});

test('autosave conflict preserves unsaved input and the saved version', async ({ page }) => {
  await create(page);
  const rid = new URL(page.url()).searchParams.get('resume_id');
  const current = await (await page.request.get(`/api/resumes/${rid}`)).json();
  await page.request.post(`/api/resumes/${rid}`, { data: { request_key: require('crypto').randomUUID(),
    revision: current.revision, title: current.title, document: { ...current.document, summary: '另一个窗口的修改' } },
    headers: { 'X-CSRFToken': await csrf(page) } });
  await page.locator('#resume-summary').fill('当前窗口尚未保存的修改');
  await expect(page.locator('[data-resume-editor]')).toHaveAttribute('data-dirty', 'true');
  await expect(page.locator('#resume-summary')).toHaveValue('当前窗口尚未保存的修改');
  const savedVersion = await (await page.request.get(`/api/resumes/${rid}`)).json();
  expect(savedVersion.document.summary).toBe('另一个窗口的修改');
  await page.reload();
  expect(new URL(page.url()).searchParams.get('resume_id')).toBe(rid);
  await expect(page.locator('#resume-summary')).toHaveValue('另一个窗口的修改');
});

test('reorder, confirmed deletion, layout and photo survive refresh', async ({ page }) => {
  await create(page);
  await page.locator('[data-section-tab="experiences"]').click();
  await page.locator('[data-rf-field="experiences.0.company"]').fill('第一段');
  await page.locator('[data-rf-field="experiences.1.company"]').fill('第二段');
  await page.locator('#resume-experience .repeat-block').nth(1).getByRole('button', { name: '上移' }).click();
  await expect(page.locator('[data-rf-field="experiences.0.company"]')).toHaveValue('第二段');
  page.once('dialog', dialog => dialog.accept());
  await page.locator('#resume-experience .repeat-block').nth(1).getByRole('button', { name: '删除', exact: true }).click();
  await expect(page.locator('#resume-experience .repeat-block')).toHaveCount(1);
  await page.locator('[data-tab-visibility="experiences"]').click();
  const png = await page.evaluate(() => {
    const canvas = document.createElement('canvas'); canvas.width = 128; canvas.height = 128;
    const context = canvas.getContext('2d'); context.fillStyle = '#64856f'; context.fillRect(0, 0, 128, 128);
    return canvas.toDataURL('image/png').split(',')[1];
  });
  await page.locator('[data-section-tab="photo"]').click();
  await page.locator('.resume-photo-editor summary').click();
  await page.locator('#resume-photo').setInputFiles({ name: 'test.png', mimeType: 'image/png', buffer: Buffer.from(png, 'base64') });
  await expect(page.locator('#resume-photo-status')).toContainText('已载入'); await saved(page);
  await page.reload();
  await expect(page.locator('[data-tab-visibility="experiences"]')).toHaveAttribute('aria-pressed', 'false');
  await expect(page.locator('[data-photo-control-image]')).toHaveAttribute('src', /^data:image\/png/);
  await page.locator('#resume-photo').setInputFiles({ name: 'invalid.png', mimeType: 'image/png', buffer: Buffer.from('invalid') });
  await expect(page.locator('#resume-photo-status')).toContainText('原有照片已保留');
  await expect(page.locator('[data-photo-control-image]')).toHaveAttribute('src', /^data:image\/png/);
});

test('oversized photo is compressed in the browser and shows at once', async ({ page }) => {
  await create(page);
  await page.locator('[data-section-tab="photo"]').click();
  await page.locator('.resume-photo-editor summary').click();
  // 3000x2000 PNG fixture exceeds the 1200px edge budget and must be re-encoded.
  await page.locator('#resume-photo').setInputFiles('tests/browser/fixtures/large-photo.png');
  await expect(page.locator('#resume-photo-status')).toContainText('已压缩');
  await saved(page);
  await expect(page.locator('[data-photo-control-image]')).toHaveAttribute('src', /^data:image\/jpeg/);
  const compressedBytes = await page.locator('[data-photo-control-image]').evaluate(image =>
    Math.floor((image.src.split(',')[1] || '').length * 3 / 4));
  expect(compressedBytes).toBeLessThanOrEqual(400 * 1024);
  if (test.info().project.name === 'mobile') await page.locator('[data-editor-tab="preview"]').click();
  await expect(page.locator('[data-resume-stage] [data-rf-photo]').first()).toBeVisible();
});

test('switching resume tabs preserves unsaved section content', async ({ page }) => {
  await create(page);
  const section = page.locator('#resume-summary-section');
  await section.locator('textarea').fill('真实的个人简介');
  await page.locator('[data-section-tab="experiences"]').click();
  await expect(section).toBeHidden();
  await page.locator('[data-section-tab="summary"]').click();
  await expect(section).toBeVisible();
  await expect(section.locator('textarea')).toHaveValue('真实的个人简介');
});

test('resume section order and visibility survive saving and printing', async ({ page }) => {
  await activateQuarterly(page);
  await create(page);
  await page.locator('[data-section-tab="experiences"]').click();
  await page.locator('#resume-experience [data-rf-field="experiences.0.company"]').fill('测试公司');
  await page.locator('[data-section-tab="projects"]').click();
  await page.locator('#resume-projects [data-rf-field="projects.0.name"]').fill('保留的项目');
  if (test.info().project.name === 'mobile') {
    await page.getByRole('button', { name: '工作经历上移' }).click();
  } else {
    await page.locator('.resume-section-tab[data-sortable-section="experiences"] .resume-tab-drag')
      .dragTo(page.locator('.resume-section-tab[data-sortable-section="summary"] .resume-tab-drag'));
  }
  await page.locator('[data-tab-visibility="projects"]').click();
  await saved(page);
  await page.reload();
  const order = await page.locator('[data-resume-panel="classic"] [data-section-flow] > [data-rf-section]')
    .evaluateAll(sections => sections.map(section => section.dataset.rfSection));
  expect(order).toEqual(['experiences', 'summary', 'projects', 'education', 'skills', 'certificates', 'languages']);
  await expect(page.locator('[data-tab-visibility="projects"]')).toHaveAttribute('aria-pressed', 'false');
  await expect(page.locator('#resume-projects [data-rf-field="projects.0.name"]')).toHaveValue('保留的项目');
  const rid = new URL(page.url()).searchParams.get('resume_id');
  const print = await page.context().newPage();
  await print.goto(`/resumes/${rid}/print`);
  const printedOrder = await print.locator('[data-section-flow] > [data-rf-section]')
    .evaluateAll(sections => sections.map(section => section.dataset.rfSection));
  expect(printedOrder).toEqual(['experiences', 'summary', 'education', 'skills', 'certificates', 'languages']);
  await print.close();
});

test('resume sections can be dragged to a new position', async ({ page }) => {
  test.skip(test.info().project.name !== 'desktop');
  await create(page);
  await page.locator('.resume-section-tab[data-sortable-section="experiences"] .resume-tab-drag')
    .dragTo(page.locator('.resume-section-tab[data-sortable-section="summary"] .resume-tab-drag'));
  const order = await page.locator('.resume-fields > [data-editor-section]')
    .evaluateAll(sections => sections.map(section => section.dataset.editorSection));
  expect(order.slice(0, 3)).toEqual(['experiences', 'summary', 'projects']);
  await saved(page);
  await page.reload();
  const stored = await page.locator('.resume-fields > [data-editor-section]')
    .evaluateAll(sections => sections.map(section => section.dataset.editorSection));
  expect(stored.slice(0, 3)).toEqual(['experiences', 'summary', 'projects']);
});

test('resume section labels stay fully readable beside their controls', async ({ page }) => {
  await create(page);
  for (const [key, label] of [
    ['basics', '基本信息'], ['experiences', '工作经历'], ['projects', '项目经历'],
    ['education', '教育经历'], ['skills', '专业技能'], ['certificates', '证书与资格'],
    ['languages', '语言能力'], ['template', '简历模板'],
  ]) {
    const tab = page.locator(`[data-section-tab="${key}"]`);
    await expect(tab).toHaveText(label);
    expect(await tab.evaluate(element => element.scrollWidth <= element.clientWidth)).toBeTruthy();
  }
});

test('custom resume sections can be added, saved, reopened, and removed', async ({ page }) => {
  await create(page);
  await page.locator('[data-add-custom-section]').click();
  const custom = page.locator('[data-custom-section-editor]').last();
  await custom.locator('input').fill('志愿服务');
  await custom.locator('textarea').fill('参与社区读书活动，负责活动签到与资料整理。');
  await saved(page);
  await page.reload();
  await expect(page.locator('[data-section-tab]').filter({ hasText: '志愿服务' })).toBeVisible();
  await expect(page.locator('[data-custom-section-editor] textarea')).toHaveValue('参与社区读书活动，负责活动签到与资料整理。');
  if (test.info().project.name === 'mobile') await page.locator('[data-editor-tab="preview"]').click();
  await expect(page.locator('[data-custom-preview]').first()).toContainText('参与社区读书活动');
  if (test.info().project.name === 'mobile') await page.locator('[data-editor-tab="edit"]').click();
  await page.locator('[data-section-tab]').filter({ hasText: '志愿服务' }).click();
  page.once('dialog', dialog => dialog.accept());
  await page.locator('[data-custom-section-editor] button.custom-section-delete').click();
  await saved(page);
  await expect(page.locator('[data-custom-section-editor]')).toHaveCount(0);
});

test('draft preview keeps guidance visible while editing but excludes it from print', async ({ page }) => {
  await create(page);
  await page.locator('[data-editor-preview]').click();
  const panel = page.locator('[data-resume-panel="classic"]');
  await expect(panel.locator('[data-rf-section="projects"]')).toBeVisible();
  await expect(panel.locator('[data-rf-section="projects"] [data-empty-section]')).toBeVisible();
  await expect(panel.locator('[data-rf="summary"]')).toContainText('真实产品经验');
  await page.emulateMedia({ media: 'print' });
  await expect(panel.locator('[data-rf-section="projects"] [data-empty-section]')).toBeHidden();
  await expect(panel.locator('[data-rf-section="projects"] .rd-placeholder-only').first()).toBeHidden();
});

test('resume name preview removes its placeholder after entering a name', async ({ page }) => {
  await page.goto('/workspace?view=resume-new');
  await page.locator('#resume-name').fill('林沐');
  const nameFields = page.locator('[data-resume-stage] [data-rf="name"]');
  await expect(nameFields.first()).toContainText('林沐');
  await expect(nameFields).toHaveCount(3);
  for (let index = 0; index < await nameFields.count(); index += 1) {
    await expect(nameFields.nth(index)).not.toHaveAttribute('data-placeholder-hint');
    await expect(nameFields.nth(index)).not.toHaveClass(/rd-placeholder-only/);
  }
});

test('resume markdown renders safely in preview and print', async ({ page }) => {
  await activateQuarterly(page);
  await create(page);
  await page.locator('[data-section-tab="summary"]').click();
  await page.locator('#resume-summary').fill('**重点** 与 *补充*\n- 第一项\n- <script>alert(1)</script>');
  await saved(page);
  await page.locator('[data-editor-preview]').click();
  await page.locator('#resume-preview-mode').selectOption('draft');
  const summary = page.locator('[data-resume-panel="classic"] [data-rf="summary"]');
  await expect(summary.locator('strong')).toHaveText('重点');
  await expect(summary.locator('em')).toHaveText('补充');
  await expect(summary.locator('li')).toHaveCount(2);
  await expect(summary.locator('script')).toHaveCount(0);
  const rid = new URL(page.url()).searchParams.get('resume_id');
  const print = await page.context().newPage();
  await print.goto(`/resumes/${rid}/print`);
  const printedSummary = print.locator('[data-rf="summary"]');
  await expect(printedSummary.locator('strong')).toHaveText('重点');
  await expect(printedSummary.locator('li')).toHaveCount(2);
  await expect(printedSummary.locator('script')).toHaveCount(0);
  await print.close();
});

test('PDF export fits substantial content onto one page and paginates oversized content', async ({ page }) => {
  await activateQuarterly(page);
  await create(page);
  const rid = new URL(page.url()).searchParams.get('resume_id');
  const csrfToken = await csrf(page);
  let response = await page.request.get('/api/resumes/' + rid);
  let current = await response.json();
  const update = async projects => page.request.post('/api/resumes/' + rid, {
    data: {
      request_key: require('crypto').randomUUID(),
      revision: current.revision,
      title: current.title,
      template: current.template,
      document: {
        ...current.document,
        projects,
        certificates: Array.from({ length: 13 }, (_, index) => 'Certificate ' + (index + 1)),
      },
    },
    headers: { 'X-CSRFToken': csrfToken },
  });
  const exportPages = async () => {
    const print = await page.context().newPage();
    await print.goto('/resumes/' + rid + '/print');
    const scale = await print.evaluate(() => window.prepareResumePrint());
    const pdf = await print.pdf({ format: 'A4', printBackground: true });
    const { execFileSync } = require('child_process');
    const fs = require('fs');
    const os = require('os');
    const path = require('path');
    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'careerflow-pdf-'));
    const pdfPath = path.join(tempDir, 'resume.pdf');
    fs.writeFileSync(pdfPath, pdf);
    let count;
    try {
      count = Number(execFileSync('python', ['-c', 'import sys; from pypdf import PdfReader; print(len(PdfReader(sys.argv[1]).pages))', pdfPath], { encoding: 'utf8' }).trim());
    } finally {
      fs.rmSync(tempDir, { recursive: true, force: true });
    }
    await print.close();
    return { scale, count };
  };

  const substantial = Array.from({ length: 4 }, (_, index) => ({
    name: 'Project ' + (index + 1),
    role: 'Engineer',
    period: '2023-2025',
    tech: 'Python, SQL, distributed systems',
    description: 'Designed and delivered a reliable product workflow with measurable outcomes. '.repeat(3),
    link: '',
  }));
  response = await update(substantial);
  expect(response.ok()).toBeTruthy();
  current = await response.json();
  await page.evaluate(() => window.prepareResumePrint());
  await page.emulateMedia({ media: 'print' });
  for (const selector of ['.editor-heading', '.resume-paste-source', '.resume-section-sidebar', '.resume-fields', '.preview-toolbar', '.preview-footnote']) {
    await expect(page.locator(selector)).toHaveCSS('display', 'none');
  }
  const fitted = await exportPages();
  expect(fitted.scale).toBeLessThan(1);
  expect(fitted.count, JSON.stringify(fitted)).toBe(1);

  const oversized = Array.from({ length: 20 }, (_, index) => ({
    name: 'Long Project ' + (index + 1),
    role: 'Engineer',
    period: '2020-2025',
    tech: 'Python, SQL, distributed systems',
    description: 'Detailed source backed project content. '.repeat(48),
    link: '',
  }));
  response = await update(oversized);
  expect(response.ok()).toBeTruthy();
  const overflow = await exportPages();
  expect(overflow.scale).toBe(0.35);
  expect(overflow.count).toBeGreaterThan(1);
});

test('paid resume suggestion shows comparison and applies only after acceptance', async ({ page }) => {
  await activateQuarterly(page);
  await create(page);
  await page.locator('[data-section-tab="summary"]').click();
  const summary = page.locator('#resume-summary-section');
  await summary.locator('.resume-ai-panel summary').click();
  const optimize = summary.locator('[data-resume-ai-mode="optimize"]');
  await expect(optimize).toBeEnabled();
  await expect(optimize).not.toContainText('\u9884\u4f30');
  const startResponse = page.waitForResponse(response => response.url().includes('/ai/start'));
  await optimize.click();
  expect(await (await startResponse).json()).not.toHaveProperty('ceiling');
  const dialog = page.locator('[data-resume-ai-dialog]:visible');
  await expect(dialog).toBeVisible();
  await expect(dialog.locator('[data-resume-ai-proposed]')).toContainText('表达更清晰', { timeout: 20000 });
  await expect(dialog.locator('[data-resume-ai-status]')).toContainText('\u5b8c\u6210');
  await expect(dialog.locator('[data-resume-ai-status]')).not.toContainText('\u79ef\u5206');
  await expect(dialog.locator('[data-resume-ai-original]')).toHaveText('真实产品经验');
  await page.screenshot({ path: `output/resume-ai-${test.info().project.name}.png` });
  await expect(summary.locator('textarea')).toHaveValue('真实产品经验');
  await dialog.locator('[data-resume-ai-reject]').click();
  await expect(summary.locator('textarea')).toHaveValue('真实产品经验');
  await optimize.click();
  await expect(dialog.locator('[data-resume-ai-accept]')).toBeVisible({ timeout: 20000 });
  await dialog.locator('[data-resume-ai-accept]').click();
  await saved(page);
  await page.reload();
  await expect(page.locator('#resume-summary')).toHaveValue(/表达更清晰/);
});

test('AI suggestion targets one experience bullet', async ({ page }) => {
  await create(page);
  await page.locator('[data-section-tab="experiences"]').click();
  const experience = page.locator('#resume-experience');
  const bullets = experience.locator('[data-rf-field="experiences.0.bullets"]');
  await bullets.fill('整理需求\n协调研发');
  await saved(page);
  await experience.locator('.resume-ai-panel summary').first().click();
  await experience.getByRole('button', { name: '第 2 条' }).click();
  const optimize = experience.locator('.resume-ai-panel [data-resume-ai-mode="optimize"]').first();
  await expect(optimize).toBeEnabled();
  await optimize.click();
  const dialog = page.locator('[data-resume-ai-dialog]:visible');
  await expect(dialog.locator('[data-resume-ai-original]')).toHaveText('协调研发', { timeout: 20000 });
  await dialog.locator('[data-resume-ai-accept]').click();
  await expect(bullets).toHaveValue('整理需求\n协调研发，表达更清晰');
});

for (const theme of ['light', 'dark', 'system']) {
  test(`page navigation and layout in ${theme} theme`, async ({ page }) => {
    await page.goto('/workspace');
    await Promise.all([page.waitForResponse(response => response.url().endsWith('/settings/theme') && response.request().method() === 'POST'), page.locator('#theme-select').selectOption(theme)]);
    for (const view of ['dashboard','resumes','resume-new','resume-import','optimize','jobs','reports','history','billing','settings']) {
      const response = await page.goto(`/workspace?view=${view}`);
      expect(response.status()).toBe(200);
      await page.waitForFunction(expected => document.documentElement.dataset.preference === expected, theme);
      await expect(page.locator('html')).toHaveAttribute('data-preference', theme);
      await expect(page.locator('.workspace-header')).toBeVisible();
      await expect(page.locator('.workbench-sidebar')).toHaveCount(0);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    }
    await page.screenshot({ path: `output/settings-${theme}-${test.info().project.name}.png` });
  });
}

test('administrator can publish a model configuration without exposing its key', async ({ page }) => {
  const promote = await page.request.post('/__test/promote', {
    data: { user_id: uid }, headers: { 'X-CSRFToken': await csrf(page) },
  });
  expect(promote.status()).toBe(200);
  await page.goto('/admin/settings');
  await expect(page.getByRole('heading', { name: '服务配置' })).toBeVisible();
  const form = page.locator('[data-admin-config-form="model"]');
  const browserModels = [
    ['测试供应商 A', 'model-for-browser-test', 'https://models.example.com/v1'],
    ['测试供应商 B', 'browser-fallback-one', 'https://backup-a.example.com/v1'],
    ['测试供应商 C', 'browser-fallback-two', 'https://backup-b.example.com/v1'],
  ];
  for (const [index, [provider, model, endpoint]] of browserModels.entries()) {
    const number = index + 1;
    await form.locator(`[name="model_provider_${number}"]`).fill(provider);
    await form.locator(`[name="model_id_${number}"]`).fill(model);
    await form.locator(`[name="base_url_${number}"]`).fill(endpoint);
    await form.locator(`[name="model_secret_${number}"]`).fill(`browser-only-secret-${number}`);
  }
  await form.locator('[name="enabled"]').check();
  await form.locator('[type="submit"]').click();
  const section = page.locator('[data-admin-section="model"]');
  await expect(section.locator('.admin-config-state')).toContainText('\u5f53\u524d\u5df2\u542f\u7528');
  await expect(section.locator('[name="model_id_1"]')).toHaveValue('model-for-browser-test');
  await expect(page.locator('body')).not.toContainText('browser-only-secret-1');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.evaluate(() => scrollTo(0, 0));
  await page.screenshot({ path: `output/admin-${test.info().project.name}.png`, fullPage: true });
});

test('administrator can publish task routing and diagnosis prompt', async ({ page }) => {
  const promote = await page.request.post('/__test/promote', {
    data: { user_id: uid }, headers: { 'X-CSRFToken': await csrf(page) },
  });
  expect(promote.status()).toBe(200);
  await page.goto('/admin/settings');
  const routes = page.locator('[data-admin-config-form="model_routes"]');
  await routes.locator('[name="route_analysis"]').fill('analysis-model');
  await routes.locator('[name="route_report"]').fill('report-model');
  await routes.locator('[name="enabled"]').check();
  await routes.locator('[type="submit"]').click();
  const routeSection = page.locator('[data-admin-section="model_routes"]');
  await expect(routeSection.locator('.admin-config-state')).toContainText('\u5f53\u524d\u5df2\u542f\u7528');
  const prompt = page.locator('[data-admin-config-form="prompt_diagnosis"]');
  await prompt.locator('[name="instructions"]').fill('先核对简历证据，再说明岗位要求中的不确定信息。');
  await prompt.locator('[name="enabled"]').check();
  await prompt.locator('[type="submit"]').click();
  const promptSection = page.locator('[data-admin-section="prompt_diagnosis"]');
  await expect(promptSection.locator('.admin-config-state')).toContainText('\u5f53\u524d\u5df2\u542f\u7528');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});

test('membership page shows fixed prices and activates the quarterly plan', async ({ page }) => {
  await page.goto('/workspace?view=billing');
  await expect(page.locator('.billing-plan-card')).toHaveCount(2);
  await expect(page.locator('.billing-plan-card').nth(0)).toContainText('39');
  await expect(page.locator('.billing-plan-card').nth(1)).toContainText('99');
  await expect(page.locator('.billing-overview')).toContainText('0 \u6b21');
  await activateQuarterly(page);
  await page.screenshot({ path: `output/billing-${test.info().project.name}.png`, fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});

test('pasted facts become a reviewed resume draft', async ({ page }) => {
  await page.goto('/workspace?view=resume-new');
  await page.locator('.resume-paste-source summary').click();
  await page.locator('#resume-source-text').fill('林测试，产品经理，在示例公司负责产品需求分析。');
  const startResponse = page.waitForResponse(response => response.url().includes('/ai/compose/start'));
  await page.locator('[data-compose-resume]').click();
  expect(await (await startResponse).json()).not.toHaveProperty('ceiling');
  const dialog = page.locator('[data-resume-compose-dialog]');
  await expect(dialog).toBeVisible();
  await expect(dialog.locator('[data-compose-name]')).toContainText('\u6797\u6d4b\u8bd5', { timeout: 20000 });
  await expect(dialog.locator('[data-compose-status]')).toContainText('\u6574\u7406\u5b8c\u6210');
  await expect(dialog.locator('[data-compose-status]')).not.toContainText('\u79ef\u5206');
  await expect(dialog.locator('[data-compose-name]')).toContainText('林测试');
  await dialog.getByRole('button', { name:'应用草稿' }).click();
  await expect(page.locator('#resume-name')).toHaveValue('林测试');
  await expect(page.locator('[data-rf-field="experiences.0.company"]')).toHaveValue('示例公司');
  await saved(page);
});
