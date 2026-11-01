/**
 * Real-model UI walkthrough against the live development server.
 *
 * Unlike tests/browser/*, this never injects a fixture provider: it signs in
 * with a real account and waits for the actual DeepSeek responses, so the
 * screenshots show what a member really sees after a 20-40s model call.
 *
 *   node scripts/verify-real-ui.cjs
 */
const { chromium } = require('playwright');

const BASE = 'http://127.0.0.1:8000';
const EMAIL = 'ui-real@example.com';
const PASSWORD = 'Real-ui-flow-2026';
const SOURCE = '我叫林望舒，做 B 端产品 6 年。2021 年 4 月到现在在杭州云链科技做高级产品经理，负责供应商协同平台的订单与对账模块，覆盖 320 家供应商，把月度对账周期从 7 天压缩到 2 天。本科是浙江工业大学信息管理与信息系统，2014 到 2018 年。';
const JD = `岗位：供应链产品经理（B 端）
职责：负责供应商协同与对账产品的规划与迭代；梳理流程并输出需求文档。
要求：3 年以上 B 端产品经验，熟悉供应链或财务对账场景，具备数据分析能力。`;

const results = [];
const step = (name, ok, detail = '') => {
  results.push({ name, ok, detail });
  console.log(`  ${ok ? 'OK  ' : 'FAIL'} ${name}${detail ? ' :: ' + detail : ''}`);
};

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const shot = async (name) => {
    // Scroll through the page first so the scroll-reveal layer (opacity gate)
    // fires for every section; otherwise a fullPage capture looks blank.
    await page.evaluate(async () => {
      const height = document.body.scrollHeight;
      for (let y = 0; y < height; y += 400) {
        window.scrollTo(0, y);
        await new Promise((resolve) => setTimeout(resolve, 100));
      }
      window.scrollTo(0, 0);
    });
    await page.waitForTimeout(500);
    await page.screenshot({ path: `output/real-model/ui-${name}.png`, fullPage: true, animations: 'disabled' });
  };

  try {
    await page.goto(`${BASE}/`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(900);
    const landingGuest = await page.locator('[data-product-landing], .cf-landing').count();
    await shot('01-landing-guest');
    step('游客落地页', landingGuest > 0, `landing 节点 ${landingGuest} 个`);

    await page.goto(`${BASE}/login`);
    await page.fill('input[name=email]', EMAIL);
    await page.fill('input[name=password]', PASSWORD);
    await Promise.all([page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 20000 }), page.click('button[type=submit]')]);
    await page.waitForTimeout(900);
    const signedInLanding = await page.locator('[data-product-landing], .cf-landing').count();
    const consoleShell = await page.locator('.cf-topnav, .cf-admin-sidebar').count();
    await shot('02-landing-signed-in');
    step('登录后仍是 landing', page.url().endsWith('/') && signedInLanding > 0, `url=${page.url()} 控制台外壳=${consoleShell}`);

    await page.goto(`${BASE}/workspace?view=resume-new`, { waitUntil: 'networkidle' });
    await page.click('[data-dialog-open="cf-resume-source"]');
    await page.fill('#resume-source-text', SOURCE);
    await page.click('[data-compose-resume]');
    await page.waitForSelector('[data-compose-accept]:not([hidden]):not([disabled])', { timeout: 180000 });
    await page.waitForFunction(() => document.querySelector('[data-compose-sections]').innerText.trim().length > 10, null, { timeout: 30000 });
    const draftText = await page.locator('[data-compose-sections]').innerText();
    await shot('03-compose-draft');
    step('粘贴文字 → AI 草稿', draftText.length > 10, draftText.replace(/\s+/g, ' ').slice(0, 60));
    await page.click('[data-compose-accept]');
    await page.waitForTimeout(1200);

    const csrf = await page.locator('meta[name="csrf-token"]').getAttribute('content');
    const saved = await page.request.post(`${BASE}/api/resumes`, {
      headers: { 'X-CSRFToken': csrf },
      data: { request_key: crypto.randomUUID(), revision: 0, title: 'UI 真实链路简历', document: { name: '林望舒', role: '产品经理' } },
    });
    const resume = await saved.json();
    const jobResp = await page.request.post(`${BASE}/api/jobs`, {
      headers: { 'X-CSRFToken': csrf },
      data: { request_key: crypto.randomUUID(), resume_id: resume.id, resume_revision: resume.revision, title: '供应链产品经理', description: JD },
    });
    const job = await jobResp.json();
    step('准备岗位', jobResp.ok(), `job_id=${job.id}`);

    await page.goto(`${BASE}/jobs/${job.id}`, { waitUntil: 'networkidle' });
    await page.click('[data-start-ai="analysis"]');
    await page.waitForSelector('[data-operation-state="succeeded"]', { timeout: 240000 });
    await page.waitForTimeout(800);
    await shot('04-analysis-result');
    step('岗位分析（真实模型）', true, '页面出现 succeeded 状态');

    const reloaded = await page.goto(`${BASE}/jobs/${job.id}`, { waitUntil: 'networkidle' });
    step('诊断页可重进', reloaded.status() === 200, `status=${reloaded.status()}`);
    await shot('05-analysis-after-reload');

    const reportBtn = page.locator('[data-start-ai="report"]');
    if (await reportBtn.count()) {
      await reportBtn.click();
      await page.waitForTimeout(1500);
    }
  } catch (error) {
    step('UI 流程异常', false, `${error.name}: ${String(error.message).slice(0, 160)}`);
    await page.screenshot({ path: 'output/real-model/ui-99-failure.png', fullPage: true }).catch(() => {});
  } finally {
    await browser.close();
    const failed = results.filter((item) => !item.ok);
    console.log(`\n${results.length - failed.length}/${results.length} 步通过`);
    process.exitCode = failed.length ? 1 : 0;
  }
})();
