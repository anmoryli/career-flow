const { test, expect } = require('@playwright/test');
const { randomUUID } = require('node:crypto');
let userId;
async function headers(page) {
  return { 'X-CSRFToken': await page.locator('meta[name="csrf-token"]').getAttribute('content') };
}
test.beforeEach(async ({ page }) => {
  await page.goto('/login');
  const response = await page.request.post('/__test/session', { data: {}, headers: await headers(page) });
  userId = (await response.json()).user_id;
});
test.afterEach(async ({ page }) => {
  if (userId) await page.request.post('/__test/cleanup', { data: { user_id: userId }, headers: await headers(page) });
});
test('overview restores large personal name and continuous motion', async ({ page }) => {
  await page.goto('/workspace');
  const name = page.locator('.workspace-home-greeting');
  await expect(name).toContainText('浏览器测试');
  expect(await name.evaluate(element => parseFloat(getComputedStyle(element).fontSize))).toBeGreaterThanOrEqual(34);
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await expect(page.locator('.overview-orbit-a')).toHaveCSS('animation-name', 'overview-orbit');
  for (const theme of ['light', 'dark', 'system']) {
    await page.locator('#theme-select').selectOption(theme);
    await expect(page.locator('.overview-intelligence')).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await page.screenshot({ path: `output/overview-v2-${test.info().project.name}-${theme}.png`, fullPage: true, animations: 'disabled' });
  }
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await expect(page.locator('.overview-orbit-a')).toHaveCSS('animation-name', 'none');
});
test('job description renders safe markdown', async ({ page }) => {
  await page.goto('/workspace');
  const requestHeaders = await headers(page);
  const resumeResponse = await page.request.post('/api/resumes', { headers: requestHeaders, data: {
    request_key: randomUUID(), revision: 0, title: '排版测试', template: 'classic', document: { name: '测试', summary: '真实产品经验' },
  }});
  expect(resumeResponse.ok()).toBeTruthy();
  const resume = await resumeResponse.json();
  const jobResponse = await page.request.post('/api/jobs', { headers: requestHeaders, data: {
    request_key: randomUUID(), resume_id: resume.id, resume_revision: resume.revision, title: 'Markdown 岗位',
    description: '## 岗位职责\n- **产品分析**\n- 使用 `Python`\n\n[公司介绍](https://example.com)\n\n<img src=x onerror=alert(1)>',
  }});
  expect(jobResponse.ok()).toBeTruthy();
  const job = await jobResponse.json();
  await page.goto(`/jobs/${job.id}`);
  await page.locator('.diagnosis-jd-details summary').click();
  const markdown = page.locator('.job-markdown');
  await expect(markdown.locator('h4')).toHaveText('岗位职责');
  await expect(markdown.locator('li')).toHaveCount(2);
  await expect(markdown.locator('strong')).toHaveText('产品分析');
  await expect(markdown.locator('code')).toHaveText('Python');
  await expect(markdown.locator('a')).toHaveAttribute('rel', 'noopener noreferrer');
  await expect(markdown.locator('img')).toHaveCount(0);
  await expect(markdown).toContainText('<img src=x onerror=alert(1)>');
});
