const { test, expect } = require('@playwright/test');
let uid;
async function csrf(page) {
  return page.locator('meta[name="csrf-token"]').getAttribute('content');
}
test.beforeEach(async ({ page }) => {
  await page.goto('/login');
  const response = await page.request.post('/__test/session', { data: {}, headers: { 'X-CSRFToken': await csrf(page) } });
  uid = (await response.json()).user_id;
});
test.afterEach(async ({ page }) => {
  if (uid) await page.request.post('/__test/cleanup', { data: { user_id: uid }, headers: { 'X-CSRFToken': await csrf(page) } });
});
async function saved(page) { await expect(page.locator('#resume-draft-status')).toContainText('已保存到账号'); }
async function create(page) {
  await page.goto('/workspace?view=resume-new');
  await page.locator('#resume-name').fill('林测试');
  await page.locator('#resume-summary').fill('真实产品经验');
  await saved(page);
}
test('draft autosave, refresh, templates, repeat entries, history, export', async ({ page }) => {
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await create(page);
  await page.locator('#resume-experience [data-add-entry]').click();
  await page.locator('[data-rf-field="experiences.2.company"]').fill('第三家公司');
  await saved(page);
  await page.reload();
  await expect(page.locator('#resume-name')).toHaveValue('林测试');
  await expect(page.locator('[data-rf-field="experiences.2.company"]')).toHaveValue('第三家公司');
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
  await expect(page.locator('#resume-draft-status')).toContainText('保存失败');
  await expect(page.locator('#resume-name')).toHaveValue('不会丢失');
  await page.unroute('**/api/resumes');
  await page.locator('[data-save-resume]').click(); await saved(page);
  page.once('dialog', dialog => dialog.dismiss());
  await page.locator('[data-clear-sample]').click();
  await expect(page.locator('#resume-name')).toHaveValue('不会丢失');
});
test('resume to job to fee confirmation to report and accepted version', async ({ page }) => {
  await create(page);
  const rid = new URL(page.url()).searchParams.get('resume_id');
  await page.goto(`/workspace?view=jobs&resume_id=${rid}`);
  await page.locator('#job-title').fill('产品经理');
  await page.locator('#job-description').fill('具备真实产品经验');
  await page.locator('[data-ui-form="job"] button[type="submit"]').click();
  await page.locator('[data-save-job]').click();
  await expect(page).toHaveURL(/\/jobs\/\d+/);
  await page.locator('[data-quote="report"]').click();
  await expect(page.locator('#fee-description')).toContainText('最多冻结');
  await page.locator('[data-confirm-operation]').click();
  await expect(page.getByText('报告已完成，对话只读', { exact: false })).toBeVisible({ timeout: 20000 });
  await expect(page.getByText('开发测试结果，非真实模型输出')).toBeVisible();
  await page.locator('[name="suggestion"]').check();
  await page.locator('[name="confirmed"]').check();
  await page.locator('[data-apply-suggestions] button[type="submit"]').click();
  await expect(page).toHaveURL(/resume_id=/);
  await expect(page.locator('#resume-summary')).toHaveValue('真实产品经验。');
  await page.goto('/workspace?view=reports');
  await expect(page.getByText('查看证据与建议')).toBeVisible();
});
test('themes, navigation, registration single email and keyboard', async ({ page }) => {
  await page.goto('/workspace');
  if (test.info().project.name === 'mobile') await page.locator('[data-sidebar-open]').click();
  for (const theme of ['dark', 'light', 'system']) {
    await Promise.all([page.waitForResponse(response => response.url().endsWith('/settings/theme') && response.request().method() === 'POST'), page.locator('#theme-select').selectOption(theme)]);
    await expect(page.locator('html')).toHaveAttribute('data-preference', theme);
  }
  await page.emulateMedia({ colorScheme: 'dark' });
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.emulateMedia({ colorScheme: 'light' });
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  if (test.info().project.name === 'mobile') { await page.keyboard.press('Escape'); await expect(page.locator('[data-sidebar-open]')).toBeFocused(); }
  await page.goto('/register');
  await expect(page.locator('input[type="email"]')).toHaveCount(1);
  await page.locator('[data-password-toggle]').click();
  await expect(page.locator('#password')).toHaveAttribute('type', 'text');
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

test('autosave conflict, new copy, original preserved', async ({ page }) => {
  await create(page);
  const rid = new URL(page.url()).searchParams.get('resume_id');
  const current = await (await page.request.get(`/api/resumes/${rid}`)).json();
  await page.request.post(`/api/resumes/${rid}`, { data: { request_key: require('crypto').randomUUID(),
    revision: current.revision, title: current.title, document: { ...current.document, summary: '另一个窗口的修改' } },
    headers: { 'X-CSRFToken': await csrf(page) } });
  await page.locator('#resume-summary').fill('当前窗口尚未保存的修改');
  await expect(page.locator('#resume-draft-status')).toContainText('其他窗口');
  await expect(page.locator('#resume-summary')).toHaveValue('当前窗口尚未保存的修改');
  await page.locator('[data-save-copy]').click(); await saved(page);
  expect(new URL(page.url()).searchParams.get('resume_id')).not.toBe(rid);
  const original = await (await page.request.get(`/api/resumes/${rid}`)).json();
  expect(original.document.summary).toBe('另一个窗口的修改');
});

test('reorder, confirmed deletion, layout and photo survive refresh', async ({ page }) => {
  await create(page);
  await page.locator('[data-rf-field="experiences.0.company"]').fill('第一段');
  await page.locator('[data-rf-field="experiences.1.company"]').fill('第二段');
  await page.locator('#resume-experience .repeat-block').nth(1).getByRole('button', { name: '上移' }).click();
  await expect(page.locator('[data-rf-field="experiences.0.company"]')).toHaveValue('第二段');
  page.once('dialog', dialog => dialog.accept());
  await page.locator('#resume-experience .repeat-block').nth(1).getByRole('button', { name: '删除', exact: true }).click();
  await expect(page.locator('#resume-experience .repeat-block')).toHaveCount(1);
  await page.locator('[data-section-visibility="experiences"]').uncheck();
  const png = await page.evaluate(() => {
    const canvas = document.createElement('canvas'); canvas.width = 128; canvas.height = 128;
    const context = canvas.getContext('2d'); context.fillStyle = '#64856f'; context.fillRect(0, 0, 128, 128);
    return canvas.toDataURL('image/png').split(',')[1];
  });
  await page.locator('.resume-photo-editor summary').click();
  await page.locator('#resume-photo').setInputFiles({ name: 'test.png', mimeType: 'image/png', buffer: Buffer.from(png, 'base64') });
  await expect(page.locator('#resume-photo-status')).toContainText('已载入'); await saved(page);
  await page.reload();
  await expect(page.locator('[data-section-visibility="experiences"]')).not.toBeChecked();
  await expect(page.locator('[data-photo-control-image]')).toHaveAttribute('src', /^data:image\/png/);
  await page.locator('#resume-photo').setInputFiles({ name: 'invalid.png', mimeType: 'image/png', buffer: Buffer.from('invalid') });
  await expect(page.locator('#resume-photo-status')).toContainText('原有照片已保留');
  await expect(page.locator('[data-photo-control-image]')).toHaveAttribute('src', /^data:image\/png/);
});

test('oversized photo is compressed in the browser and shows at once', async ({ page }) => {
  await create(page);
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

test('resume editor sections are cards that can collapse without clearing content', async ({ page }) => {
  await create(page);
  const section = page.locator('#resume-summary-section');
  await section.locator('textarea').fill('真实的个人简介');
  const toggle = section.getByRole('button', { name: '折叠个人简介' });
  await toggle.click();
  await expect(section).toHaveClass(/is-collapsed/);
  await expect(section.locator('textarea')).toBeHidden();
  await section.getByRole('button', { name: '展开个人简介' }).click();
  await expect(section.locator('textarea')).toHaveValue('真实的个人简介');
});

for (const theme of ['light', 'dark', 'system']) {
  test(`page navigation and layout in ${theme} theme`, async ({ page }) => {
    await page.goto('/workspace');
    if (test.info().project.name === 'mobile') await page.locator('[data-sidebar-open]').click();
    await Promise.all([page.waitForResponse(response => response.url().endsWith('/settings/theme') && response.request().method() === 'POST'), page.locator('#theme-select').selectOption(theme)]);
    for (const view of ['dashboard','resumes','resume-new','resume-import','optimize','jobs','reports','history','billing','settings']) {
      const response = await page.goto(`/workspace?view=${view}`);
      expect(response.status()).toBe(200);
      await expect(page.locator('html')).toHaveAttribute('data-preference', theme);
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
  await form.locator('[name="label"]').fill('测试模型');
  await form.locator('[name="provider"]').fill('测试供应商');
  await form.locator('[name="model_id"]').fill('model-for-browser-test');
  await form.locator('[name="base_url"]').fill('https://models.example.com/v1');
  await form.locator('[name="secret"]').fill('browser-only-secret');
  await form.locator('[name="enabled"]').check();
  await form.locator('[type="submit"]').click();
  const section = page.locator('[data-admin-section="model"]');
  await expect(section).toContainText('第 1 版 · 测试模型');
  page.once('dialog', dialog => dialog.accept());
  await section.locator('[data-admin-publish]').click();
  await expect(section).toContainText('当前：第 1 版 · 测试模型');
  await expect(page.locator('body')).not.toContainText('browser-only-secret');
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
  await routes.locator('[name="label"]').fill('任务分配');
  await routes.locator('[name="route_analysis"]').fill('analysis-model');
  await routes.locator('[name="route_report"]').fill('report-model');
  await routes.locator('[name="enabled"]').check();
  await routes.locator('[type="submit"]').click();
  const routeSection = page.locator('[data-admin-section="model_routes"]');
  await expect(routeSection).toContainText('第 1 版 · 任务分配');
  page.once('dialog', dialog => dialog.accept());
  await routeSection.locator('[data-admin-publish]').click();
  await expect(routeSection).toContainText('当前：第 1 版 · 任务分配');
  const prompt = page.locator('[data-admin-config-form="prompt_diagnosis"]');
  await prompt.locator('[name="label"]').fill('证据优先');
  await prompt.locator('[name="instructions"]').fill('先核对简历证据，再说明岗位要求中的不确定信息。');
  await prompt.locator('[name="enabled"]').check();
  await prompt.locator('[type="submit"]').click();
  const promptSection = page.locator('[data-admin-section="prompt_diagnosis"]');
  await expect(promptSection).toContainText('第 1 版 · 证据优先');
  page.once('dialog', dialog => dialog.accept());
  await promptSection.locator('[data-admin-publish]').click();
  await expect(promptSection).toContainText('当前：第 1 版 · 证据优先');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});

test('administrator can publish membership and credit offers', async ({ page }) => {
  const promoted = await page.request.post('/__test/promote', {
    data: { user_id: uid }, headers: { 'X-CSRFToken': await csrf(page) },
  });
  expect(promoted.status()).toBe(200);
  await page.goto('/admin/settings');
  const form = page.locator('[data-admin-config-form="commerce"]');
  await expect(form.locator('[name="offer_membership_30_price_yuan"]')).toHaveValue('19.90');
  await form.locator('[name="label"]').fill('测试套餐');
  await form.locator('[name="enabled"]').check();
  await form.locator('[type="submit"]').click();
  const section = page.locator('[data-admin-section="commerce"]');
  await expect(section).toContainText('第 1 版 · 测试套餐');
  page.once('dialog', dialog => dialog.accept());
  await section.locator('[data-admin-publish]').click();
  await expect(section).toContainText('当前：第 1 版 · 测试套餐');
  await page.goto('/workspace?view=billing');
  const pack = page.locator('.billing-offer').filter({ has: page.locator('[name="plan_code"][value="credit_pack_1"]') });
  await expect(pack).toContainText('¥9.90');
  await pack.getByRole('button', { name: '创建订单' }).click();
  await expect(page.locator('.billing-order').first()).toContainText('待模拟支付');
  await page.locator('.billing-order').first().getByRole('button', { name: '模拟成功' }).click();
  await expect(page.locator('.billing-order').first()).toContainText('模拟成功');
  await expect(page.locator('.account-section').first()).toContainText('购买 100');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({ path: `output/billing-${test.info().project.name}.png`, fullPage: true });
  await page.goto('/admin/orders');
  await expect(page.locator('.admin-list')).toContainText('credit_pack_1');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});
