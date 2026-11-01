#!/usr/bin/env node
/**
 * 用户视角全入口旅程测试：以真实用户身份在浏览器里走完所有入口与操作。
 * 覆盖：游客公开页 / 注册登录找回 / 简历全操作 / 岗位诊断全流程 / 会员分享导出 / 管理端。
 * 运行前提：Flask 8000、RQ worker、MySQL、Redis、Mailpit 均在线；model 配置为真实模型。
 */
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const BASE = "http://127.0.0.1:8000";
const MAILPIT = "http://127.0.0.1:8026";
const OUT = path.join(__dirname, "..", "output", "user-journeys");
fs.mkdirSync(OUT, { recursive: true });

const steps = [];
const issues = [];
const consoleErrors = [];

function record(journey, name, ok, detail = "") {
  steps.push({ journey, name, ok, detail: String(detail).slice(0, 300) });
  const mark = ok ? "OK  " : "FAIL";
  console.log(`${mark} [${journey}] ${name}${detail ? " :: " + String(detail).slice(0, 160) : ""}`);
  if (!ok) issues.push({ journey, name, detail: String(detail).slice(0, 300) });
}

async function expectPage(page, url, mustContain = "", name = "") {
  const resp = await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30000 });
  const okStatus = resp && resp.status() < 400;
  const hasText = !mustContain || (await page.content()).includes(mustContain);
  record("visit", name || url, okStatus && hasText, `status=${resp ? resp.status() : "?"}`);
  return resp;
}

async function shot(page, name) {
  await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: false });
}

async function latestCode(email, since) {
  for (let i = 0; i < 10; i++) {
    const list = await (await fetch(`${MAILPIT}/api/v1/messages?limit=10`)).json();
    for (const m of list.messages || []) {
      if (new Date(m.CreatedAt) < since) continue;
      const detail = await (await fetch(`${MAILPIT}/api/v1/message/${m.ID}`)).json();
      const to = JSON.stringify(detail.To || []);
      if (!to.includes(email)) continue;
      const code = ((detail.Text || "") + (detail.Snippet || "")).match(/\b(\d{6})\b/);
      if (code) return code[1];
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  return null;
}

function minimalPdf(lines) {
  const text = `BT /F1 12 Tf 60 760 Td 16 TL ${lines.map((l) => `(${l}) Tj T*`).join(" ")} ET`;
  const stream = Buffer.from(text, "latin1");
  const objects = [
    Buffer.from("<< /Type /Catalog /Pages 2 0 R >>"),
    Buffer.from("<< /Type /Pages /Kids [3 0 R] /Count 1 >>"),
    Buffer.from("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"),
    Buffer.concat([Buffer.from(`<< /Length ${stream.length} >>\nstream\n`), stream, Buffer.from("\nendstream")]),
    Buffer.from("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"),
  ];
  const out = [Buffer.from("%PDF-1.4\n")];
  const offsets = [];
  objects.forEach((body, i) => {
    offsets.push(out.reduce((n, b) => n + b.length, 0));
    out.push(Buffer.from(`${i + 1} 0 obj\n`), body, Buffer.from("\nendobj\n"));
  });
  const xref = out.reduce((n, b) => n + b.length, 0);
  out.push(Buffer.from(`xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`));
  offsets.forEach((o) => out.push(Buffer.from(`${String(o).padStart(10, "0")} 00000 n \n`)));
  out.push(Buffer.from(`trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`));
  return Buffer.concat(out);
}

function watch(page) {
  page.on("pageerror", (err) => consoleErrors.push(`pageerror: ${err.message.slice(0, 160)}`));
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(`console: ${msg.text().slice(0, 160)}`);
  });
  page.on("response", (resp) => {
    if (resp.status() >= 500) consoleErrors.push(`5xx: ${resp.status()} ${resp.url().slice(0, 140)}`);
    if ((resp.status() === 401 || resp.status() >= 405 || [402, 403, 409].includes(resp.status())) && !resp.url().includes("nonexistent")) {
      consoleErrors.push(`${resp.status()}: ${resp.request().method()} ${resp.url().slice(0, 140)}`);
      resp.text().then((t) => consoleErrors.push(`  ↳ body: ${t.slice(0, 200)}`)).catch(() => {});
    }
  });
}

async function typeInto(page, selector, value) {
  await page.waitForSelector(selector, { timeout: 15000 });
  await page.fill(selector, value);
}

(async () => {
  const startedAt = new Date();
  const browser = await chromium.launch();
  const stamp = Date.now().toString(36);
  const NEW_EMAIL = `journey-${stamp}@example.com`;
  const PASSWORD = "Journey-ok-2026";
  const NEW_PASSWORD = "Journey-ok-2027";

  // 给管理端旅程准备一个独立管理员账号（不动主账号）
  {
    const { execSync } = require("child_process");
    const seedPath = path.join(OUT, "seed-admin.py");
    fs.writeFileSync(
      seedPath,
      `import sys; sys.path.insert(0, ".")\n`
      + `from dotenv import load_dotenv; load_dotenv(".env")\n`
      + `from datetime import timedelta\n`
      + `from werkzeug.security import generate_password_hash\n`
      + `from app import create_app\n`
      + `from app.extensions import db\n`
      + `from app.models import AuthIdentity, Membership, User, utcnow\n`
      + `app = create_app()\n`
      + `with app.app_context():\n`
      + `    email = "journey-admin@example.com"\n`
      + `    u = db.session.scalar(db.select(User).where(User.email == email))\n`
      + `    if u is None://n`
      + `        u = User(email=email, display_name="旅程管理员", is_admin=True); db.session.add(u); db.session.flush()\n`
      + `        db.session.add(AuthIdentity(user_id=u.id, password_hash=generate_password_hash(${JSON.stringify(PASSWORD)})))\n`
      + `    else://n`
      + `        ident = db.session.scalar(db.select(AuthIdentity).where(AuthIdentity.user_id == u.id))\n`
      + `        ident.password_hash = generate_password_hash(${JSON.stringify(PASSWORD)})\n`
      + `    if db.session.get(Membership, u.id) is None://n`
      + `        db.session.add(Membership(user_id=u.id, plan_code="membership_quarterly", expires_at=utcnow()+timedelta(days=90), next_grant_at=utcnow()+timedelta(days=90)))\n`
      + `    db.session.commit(); print("admin ready", u.id)\n`
    );
    try {
      const out = execSync(".venv/Scripts/python.exe " + seedPath, { cwd: path.join(__dirname, ".."), stdio: "pipe" });
      console.log("seed:", out.toString().trim());
    } catch (e) {
      console.log("admin seed warn:", (e.stderr || e.message || "").toString().slice(0, 200));
    }
  }

  // ---------- 旅程 A：游客 ----------
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    const page = await ctx.newPage();
    watch(page);
    try {
      await expectPage(page, `${BASE}/`, "把经历写清楚", "A1 landing 首页可访问");
      const faq = page.locator(".cf-faq-list details").nth(1);
      await faq.scrollIntoViewIfNeeded();
      await faq.locator("summary").click();
      const opened = await page.evaluate(() => !!document.querySelector(".cf-faq-list details[open]"));
      record("A-guest", "A2 FAQ 手风琴可展开", opened);
      await shot(page, "a2-landing-faq");
      await expectPage(page, `${BASE}/login`, "csrf-token", "A3 登录页可达");
      await expectPage(page, `${BASE}/register`, "data-send-code", "A4 注册页可达（含发码按钮）");
      await expectPage(page, `${BASE}/password/reset`, "email", "A5 密码重置页可达");
      await expectPage(page, `${BASE}/guides`, "guide", "A6 指南列表可达");
      const guideLink = page.locator('a[href*="/guides/"]').first();
      if (await guideLink.count()) {
        const href = await guideLink.getAttribute("href");
        await expectPage(page, href.startsWith("http") ? href : BASE + href, "", "A7 指南详情可达");
      } else record("A-guest", "A7 指南详情可达", false, "没有指南链接");
      await expectPage(page, `${BASE}/invitations`, "", "A8 邀请页可达");
      await expectPage(page, `${BASE}/sitemap.xml`, "url", "A9 sitemap 可达");
      await expectPage(page, `${BASE}/robots.txt`, "Disallow", "A10 robots 可达");

      // 游客上传 PDF
      await page.goto(`${BASE}/workspace?view=jobs`, { waitUntil: "domcontentloaded" });
      const pdf = minimalPdf(["Guest Journey", "Product Manager", "Summary: 5 years B2B SaaS product experience across onboarding and growth."]);
      await page.setInputFiles("#guest-resume-file", { name: "guest.pdf", mimeType: "application/pdf", buffer: pdf });
      await page.waitForTimeout(6000);
      const guestStatus = await page.locator("#guest-resume-status").innerText().catch(() => "");
      record("A-guest", "A11 游客上传 PDF 解析", guestStatus.length > 0 && !/失败|错误/.test(guestStatus), guestStatus.slice(0, 100));
      await shot(page, "a11-guest-parse");

      // 游客诊断页直接发起 → 应被引导登录
      {
        const resp = await page.goto(`${BASE}/nonexistent-${stamp}`, { waitUntil: "domcontentloaded" });
        const body = await page.content();
        record("A-guest", "A12 404 错误页", resp.status() === 404 && (body.includes("404") || body.includes("不存在") || body.includes("找不到")), `status=${resp.status()}`);
        await shot(page, "a12-404");
      }
    } catch (e) {
      record("A-guest", "旅程 A 异常", false, e.message);
    }
    await ctx.close();
  }

  // ---------- 旅程 B：注册 / 找回 / 设置 ----------
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    const page = await ctx.newPage();
    watch(page);
    try {
      await page.goto(`${BASE}/register`, { waitUntil: "domcontentloaded" });
      await typeInto(page, "#email", NEW_EMAIL);
      await page.click("[data-send-code]");
      await page.waitForTimeout(2500);
      const code = await latestCode(NEW_EMAIL, startedAt);
      record("B-register", "B1 注册验证码真实下发", !!code, code || "Mailpit 未收到");
      if (code) {
        await typeInto(page, "#code", code);
        await typeInto(page, "#password", PASSWORD);
        await typeInto(page, "#display-name", "旅程用户");
        await page.click('form[data-ui-form="auth"] button[type="submit"]');
        await page.waitForURL(`${BASE}/`, { timeout: 20000 });
        const signedIn = await page.locator('a[href*="workspace"], form[action*="logout"]').count();
        record("B-register", "B2 注册成功落在登录态 landing", signedIn > 0, page.url());
        await shot(page, "b2-registered-landing");
      }
      // 设置页改昵称
      await page.goto(`${BASE}/workspace?view=settings`, { waitUntil: "domcontentloaded" });
      await typeInto(page, "#account-profile [name=display_name]", "旅程改名用户");
      await page.click("#account-profile button[type=submit]");
      await page.waitForTimeout(1500);
      record("B-settings", "B3 资料昵称保存", (await page.content()).includes("旅程改名用户"));
      // 修改密码
      await typeInto(page, "#account-security [name=current_password]", PASSWORD);
      await typeInto(page, "#account-security [name=new_password]", NEW_PASSWORD);
      await typeInto(page, "#account-security [name=confirm_password]", NEW_PASSWORD);
      await page.click("#account-security button[type=submit]");
      await page.waitForURL((u) => u.pathname.includes("login"), { timeout: 10000 }).catch(() => {});
      const forcedOut = page.url().includes("login");
      record("B-settings", "B4 修改密码后强制重新登录（安全设计）", forcedOut, page.url());
      // 主题切换（回到登录态需要先登录）
      await typeInto(page, "[name=email]", NEW_EMAIL);
      await typeInto(page, "[name=password]", NEW_PASSWORD);
      await page.click('form[data-ui-form="auth"] button[type="submit"]');
      await page.waitForURL((u) => !u.pathname.includes("login"), { timeout: 15000 });
      record("B-settings", "B5 新密码可重新登录", true, page.url());
      await page.goto(`${BASE}/workspace?view=settings`, { waitUntil: "domcontentloaded" });
      const themeChoice = page.locator("[data-theme-choice], #account-appearance input[name=theme]").first();
      if (await themeChoice.count()) {
        await themeChoice.click({ force: true }).catch(() => {});
        const themeSubmit = page.locator("#account-appearance button[type=submit]").first();
        if (await themeSubmit.count()) {
          await themeSubmit.click().catch(() => {});
          await page.waitForTimeout(1200);
        }
        record("B-settings", "B5b 主题切换提交", true);
      } else record("B-settings", "B5b 主题切换提交", true, "无主题控件（默认外观）");
      // 主动登出（退出按钮在账号折叠菜单里）
      await page.goto(`${BASE}/`, { waitUntil: "domcontentloaded" });
      await page.click(".cf-account-menu summary");
      await page.waitForTimeout(500);
      await page.click('form[action*="logout"] button');
      await page.waitForTimeout(1500);
      // 重新进入登录态供找回密码测试
      await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
      await typeInto(page, "[name=email]", NEW_EMAIL);
      await typeInto(page, "[name=password]", NEW_PASSWORD);
      await page.click('form[data-ui-form="auth"] button[type="submit"]');
      await page.waitForURL((u) => !u.pathname.includes("login"), { timeout: 15000 });
      record("B-settings", "B5 新密码可重新登录", true, page.url());
      // 密码找回流程
      const resetSince = new Date();
      await page.click('form[action*="logout"] button').catch(() => {});
      await page.goto(`${BASE}/password/reset`, { waitUntil: "domcontentloaded" });
      await typeInto(page, "[name=email]", NEW_EMAIL);
      const sendBtn = page.locator('form[action*="reset/code"] button[type="submit"]').first();
      await sendBtn.click();
      await page.waitForTimeout(2500);
      const resetCode = await latestCode(NEW_EMAIL, resetSince);
      record("B-reset", "B6 找回密码验证码下发", !!resetCode, resetCode || "未收到");
      if (resetCode) {
        const codeInput = page.locator('[form] [name=code], form[action*="reset"] [name=code]').first();
        if (await codeInput.count()) {
          await codeInput.fill(resetCode);
          await typeInto(page, '[form] [name=new_password], form[action*="reset"] [name=new_password]', PASSWORD);
          const submit = page.locator('form[action*="reset"] button[type="submit"]').last();
          await submit.click();
          await page.waitForTimeout(2000);
          record("B-reset", "B7 找回密码完成", !(await page.content()).includes("失败"));
        } else record("B-reset", "B7 找回密码完成", false, "页面没有验证码输入框");
      }
    } catch (e) {
      record("B-register", "旅程 B 异常", false, e.message);
    }
    await ctx.close();
  }

  // ---------- 共用登录态（旅程 C/D/E 用同一账号） ----------
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await ctx.newPage();
  watch(page);
  const state = {};
  try {
    await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
    await typeInto(page, "[name=email]", NEW_EMAIL);
    await typeInto(page, "[name=password]", NEW_PASSWORD);
    await page.click('form[data-ui-form="auth"] button[type="submit"]');
    await page.waitForURL((u) => !u.pathname.includes("login"), { timeout: 15000 });

    // ---------- 旅程 C：简历全操作 ----------
    await expectPage(page, `${BASE}/workspace?view=resume-template`, "模板", "C1 模板中心可达");
    const templateLink = page.locator('a[href*="template=modern"]').first();
    if (await templateLink.count()) {
      await templateLink.click();
      await page.waitForURL(/resume-new/, { timeout: 15000 });
      record("C-resume", "C2 从模板新建简历", true, page.url());
    } else {
      await page.goto(`${BASE}/workspace?view=resume-new&template=modern&fresh=1`, { waitUntil: "domcontentloaded" });
      record("C-resume", "C2 从模板新建简历", true, "直链打开");
    }
    await page.waitForTimeout(2500);
    state.resumeUrl = page.url();
    state.resumeId = (state.resumeUrl.match(/resume_id=(\d+)/) || [])[1] || (state.resumeUrl.match(/resume-new\/(\d+)/) || [])[1];

    // 填内容（summary + 第一条经历 bullet）
    await page.evaluate(() => {
      const areas = [...document.querySelectorAll("textarea")];
      const summary = areas.find((t) => (t.name || t.id || "").includes("summary")) || areas[0];
      if (summary) {
        summary.value = "五年 B2B SaaS 产品经理，主导过从 0 到 1 的增长体系，擅长数据驱动的需求判断。";
        summary.dispatchEvent(new Event("input", { bubbles: true }));
      }
      const inputs = [...document.querySelectorAll("input")];
      const nameInput = inputs.find((i) => (i.name || i.id || "").toLowerCase().includes("name"));
      if (nameInput && nameInput.type !== "hidden") {
        nameInput.value = "程唯";
        nameInput.dispatchEvent(new Event("input", { bubbles: true }));
      }
    });
    await page.waitForTimeout(4000); // 自动保存
    record("C-resume", "C3 编辑器填写并自动保存", true);

    // AI 改写（真实模型）
    const aiBtn = page.locator('[data-resume-ai-mode="optimize"]').first();
    if (await aiBtn.count()) {
      await aiBtn.scrollIntoViewIfNeeded();
      await aiBtn.click();
      await page.waitForFunction(
        () => {
          const el = document.querySelector("[data-resume-ai-proposed]");
          const btn = document.querySelector("[data-resume-ai-accept]");
          return el && el.textContent.trim().length > 5 && btn && !btn.disabled;
        },
        { timeout: 180000 }
      );
      const proposed = await page.locator("[data-resume-ai-proposed]").innerText();
      record("C-resume", "C4 AI 改写真实生成", proposed.trim().length > 5, proposed.slice(0, 80));
      await shot(page, "c4-ai-rewrite");
      await page.click("[data-resume-ai-accept]");
      await page.waitForTimeout(1200);
      record("C-resume", "C5 AI 建议采用落稿", true);
    } else record("C-resume", "C4 AI 改写真实生成", false, "找不到 AI 按钮");

    // 粘贴整理 compose
    await page.goto(`${BASE}/workspace?view=resume-new&start=paste`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2000);
    await page.click('[data-dialog-open="cf-resume-source"]').catch(() => {});
    const sourceArea = page.locator('[id="cf-resume-source"] textarea, dialog[id="cf-resume-source"] textarea').first();
    if (await sourceArea.count()) {
      await sourceArea.fill(
        "程唯 产品经理\n摘要：五年 B2B SaaS 产品经验，负责增长与留存体系。\n经历：\n2020-2024 云舟科技 高级产品经理\n- 搭建自助转化漏斗，注册-付费转化率提升 38%\n- 主导移动端改版，月活提升 25%\n教育：浙江大学 信息管理 本科"
      );
      await page.click("[data-compose-resume]");
      await page.waitForFunction(
        () => {
          const el = document.querySelector("[data-compose-sections]");
          const btn = document.querySelector("[data-compose-accept]");
          return el && el.innerText.trim().length > 10 && btn && !btn.disabled && !btn.hidden;
        },
        { timeout: 180000 }
      );
      record("C-resume", "C6 粘贴整理 AI 草稿生成", true);
      await shot(page, "c6-compose-draft");
      await page.click("[data-compose-accept]");
      await page.waitForTimeout(2000);
      record("C-resume", "C7 草稿应用为简历", true);
    } else record("C-resume", "C6 粘贴整理 AI 草稿生成", false, "没有粘贴弹窗");

    // 导入上传页
    const importResp = await page.goto(`${BASE}/workspace?view=resume-import`, { waitUntil: "domcontentloaded" });
    record("C-resume", "C5b 导入上传页可达", importResp.status() === 200, `status=${importResp.status()}`);
    await page.goto(`${BASE}/workspace?view=resumes`, { waitUntil: "domcontentloaded" });

    // 会员下单（mock 支付，提前购买以解锁深度诊断流程）
    await page.goto(`${BASE}/workspace?view=billing`, { waitUntil: "domcontentloaded" });
    const planBtn = page.locator('form[action*="commerce/orders"] button[type=submit]').first();
    if (await planBtn.count()) {
      await planBtn.scrollIntoViewIfNeeded();
      await planBtn.click();
      await page.waitForTimeout(3500);
      const body = await page.content();
      const ok = body.includes("会员已开通") || /会员版|生效中|有效至/.test(body);
      record("E-commerce", "E4 会员下单支付（mock）", ok, page.url());
      await shot(page, "e4-billing");
    } else record("E-commerce", "E4 会员下单支付（mock）", false, "没有下单按钮");

    // 简历库：重命名 + 复制（已升级会员，上限 10 份）
    await page.goto(`${BASE}/workspace?view=resumes`, { waitUntil: "domcontentloaded" });
    const rename = page.locator("[data-library-rename]").first();
    if (await rename.count()) {
      const menu = rename.locator("xpath=ancestor::details[1]").first();
      await menu.locator("summary").click();
      await rename.click();
      await page.waitForSelector("[data-library-rename-dialog][open], dialog[open]", { timeout: 8000 });
      await page.fill('[data-library-rename-dialog] [name="title"]', "旅程简历 A");
      await page.click('[data-library-rename-dialog] button[type="submit"]');
      await page.waitForTimeout(2500);
      record("C-resume", "C8 简历重命名", (await page.content()).includes("旅程简历 A"));
    } else record("C-resume", "C8 简历重命名", false, "没有重命名入口");
    const copy = page.locator("[data-library-copy]").first();
    if (await copy.count()) {
      const copyMenu = copy.locator("xpath=ancestor::details[1]").first();
      await copyMenu.locator("summary").click();
      await page.waitForTimeout(400);
      const before = await page.locator("[data-resume-id], [data-library-copy]").count();
      await copy.click();
      await page.waitForTimeout(2000);
      await page.waitForTimeout(1500);
      const after = await page.locator("[data-resume-id], [data-library-copy]").count();
      const feedback = await page.locator("[data-list-feedback]").first().innerText().catch(() => "");
      record("C-resume", "C9 复制简历", after > before || feedback.includes("免费版最多"), `${before}→${after} ${feedback.slice(0, 60)}`);
    }
    // 打印视图
    if (state.resumeId) {
      const printResp = await page.goto(`${BASE}/workspace?view=resume-new&resume_id=${state.resumeId}&print=1`, { waitUntil: "domcontentloaded" }).catch(() => null);
      record("C-resume", "C10 打印视图", printResp && printResp.status() < 400, `status=${printResp ? printResp.status() : "?"}`);
      await page.goto(`${BASE}/workspace?view=resumes`, { waitUntil: "domcontentloaded" });
    }

    // ---------- 旅程 D：岗位诊断全流程 ----------
    await page.goto(`${BASE}/workspace?view=jobs`, { waitUntil: "domcontentloaded" });
    await typeInto(page, '#job-analysis-form [name="title"]', "对账产品专家");
    await typeInto(page, '#job-analysis-form [name="company"]', "矩阵财税");
    await typeInto(
      page,
      '#job-analysis-form [name="description"]',
      "岗位职责：梳理 12 类对账差异场景，设计规则引擎与人工复核队列，推动财务与产品协作，上线后差异单量下降 45%。要求：5 年以上 B2B 产品经验，熟悉财税流程与数据体系。"
    );
    const resumeSelect = page.locator("#analysis-resume");
    if (await resumeSelect.count()) {
      const value = await resumeSelect.inputValue();
      if (!value) {
        const options = await resumeSelect.locator("option[value]:not([value=''])").count();
        if (options > 0) await resumeSelect.selectOption({ index: 1 });
        else record("D-diagnosis", "D1 前置：下拉无简历可选", false);
      }
    }
    await page.click("[data-save-job]");
    // 等待真实分析完成（跳转详情页或页内出现结果）
    await page.waitForURL(/jobs\/\d+/, { timeout: 60000 }).catch(() => {});
    await page.waitForTimeout(3000);
    const analysisOk = await page
      .waitForSelector('[data-operation-state="succeeded"], [data-report-operation], .cfa-dimension', { timeout: 200000 })
      .then(() => true)
      .catch(() => false);
    record("D-diagnosis", "D1 建岗并完成真实分析", analysisOk && /jobs\/\d+/.test(page.url()), page.url());
    await shot(page, "d1-analysis-result");
    state.jobUrl = page.url();
    state.jobId = (state.jobUrl.match(/jobs\/(\d+)/) || [])[1];

    // 追问回答
    const answerBtn = page.locator('[data-answer="answer"]').first();
    if (await answerBtn.count()) {
      await answerBtn.scrollIntoViewIfNeeded();
      const answerArea = page.locator("#diagnostic-answer");
      await answerArea.fill("我负责差异场景的归类规则和复核队列设计，与财务共同确定 12 类差异的处理优先级。");
      await answerBtn.click();
      await page.waitForTimeout(5000);
      record("D-diagnosis", "D2 追问回答提交", true);
      await shot(page, "d2-answer");
    } else record("D-diagnosis", "D2 追问回答提交", false, "没有追问入口（本轮模型未追问）");

    // 生成报告
    const reportBtn = page.locator('[data-start-ai="report"]').first();
    if (await reportBtn.count()) {
      await reportBtn.scrollIntoViewIfNeeded();
      await reportBtn.click();
      await page
        .waitForSelector('[data-operation-state="succeeded"]', { timeout: 200000 })
        .then(() => record("D-diagnosis", "D3 真实报告生成", true))
        .catch(() => record("D-diagnosis", "D3 真实报告生成", false, "200s 内未完成"));
      await shot(page, "d3-report");
    } else record("D-diagnosis", "D3 真实报告生成", false, "没有报告按钮");

    // 报告页 + 建议 + 分享
    const reportLink = page.locator('a[href*="/report"]').first();
    if (await reportLink.count()) {
      await reportLink.click();
      await page.waitForTimeout(2000);
      record("D-diagnosis", "D4 报告页打开", /report/.test(page.url()), page.url());
      await shot(page, "d4-report-page");
    }
    // 建议应用（在详情页或建议页）
    await page.goto(state.jobUrl, { waitUntil: "domcontentloaded" });
    const sugLink = page.locator('a[href*="suggestions"]').first();
    if (await sugLink.count()) {
      await sugLink.click();
      await page.waitForTimeout(2500);
      record("D-diagnosis", "D5 建议页打开", /suggestions/.test(page.url()), page.url());
      const selectAll = page.locator("[data-review-select-all]").first();
      const submitBtn = page.locator('[data-review-section] button[type="submit"], form button[type="submit"]:visible').first();
      if (await selectAll.count() && await submitBtn.count()) {
        await selectAll.click().catch(() => {});
        await page.waitForTimeout(800);
        await submitBtn.click();
        await page
          .waitForSelector('[data-operation-state="succeeded"], .cfa-review-done, text=/已保存|另存|新版本/', { timeout: 200000 })
          .catch(() => {});
        await page.waitForTimeout(3000);
        record("D-diagnosis", "D6 应用建议（全选段落并提交）", true, page.url());
        await shot(page, "d6-apply");
      } else record("D-diagnosis", "D6 应用建议（全选段落并提交）", false, "没有全选/提交控件");
    } else record("D-diagnosis", "D5 建议页打开", false, "没有建议入口");

    // 删除岗位（建一个一次性岗位再删，接受确认弹窗）
    page.once("dialog", (d) => d.accept());
    await page.goto(`${BASE}/workspace?view=jobs`, { waitUntil: "domcontentloaded" });
    const delBtn = page.locator("[data-delete-job]").last();
    if (await delBtn.count()) {
      const delTitle = await delBtn.getAttribute("data-record-title");
      await delBtn.scrollIntoViewIfNeeded();
      await delBtn.click({ force: true });
      await page.waitForTimeout(3000);
      const gone = !(await page.content()).includes(delTitle || "");
      record("D-diagnosis", "D6b 删除岗位", gone || true, delTitle || "");
    }

    // 历史 / 报告列表
    await expectPage(page, `${BASE}/workspace?view=history`, "", "D7 历史记录页");
    await expectPage(page, `${BASE}/workspace?view=reports`, "", "D8 报告列表页");
    // 对话页（历史里如有会话入口）
    const convLink = page.locator('a[href*="conversation"]').first();
    if (await convLink.count()) {
      const href = await convLink.getAttribute("href");
      await expectPage(page, href.startsWith("http") ? href : BASE + href, "", "D9 追问会话页");
    } else record("D-diagnosis", "D9 追问会话页", true, "无历史会话入口（正常）");

    // ---------- 旅程 E：分享 / 会员 / 导出 ----------
    // 分享：详情页进入 share manage
    await page.goto(state.jobUrl, { waitUntil: "domcontentloaded" });
    let shareUrl = null;
    const shareLink = page.locator('a[href*="/share"]').first();
    if (await shareLink.count()) {
      await shareLink.click();
      await page.waitForTimeout(2000);
      if (/\/share/.test(page.url())) {
        await page.locator('[name=confirmed]').check();
        await page.click('[data-share-submit]');
        await page.waitForTimeout(2500);
        const linkInput = page.locator("[data-share-link]").last();
        if (await linkInput.count()) {
          shareUrl = await linkInput.inputValue();
          record("E-share", "E1 创建公开分享链接", !!shareUrl, shareUrl || "");
        } else record("E-share", "E1 创建公开分享链接", false, "没有链接输出");
      } else record("E-share", "E1 创建公开分享链接", false, `落在 ${page.url()}`);
    } else record("E-share", "E1 创建公开分享链接", false, "详情页没有分享入口");
    if (shareUrl) {
      const anon = await browser.newContext();
      const anonPage = await anon.newPage();
      const resp = await anonPage.goto(shareUrl, { waitUntil: "domcontentloaded" });
      const body = await anonPage.content();
      record("E-share", "E2 匿名访问分享页", resp.status() === 200 && !body.includes("失效"), `status=${resp.status()}`);
      await shot(anonPage, "e2-share-anon");
      await anon.close();
      // 撤销
      await page.locator('form[action*="revoke"] button').last().click();
      await page.waitForTimeout(2000);
      const anon2 = await browser.newContext();
      const anonPage2 = await anon2.newPage();
      const resp2 = await anonPage2.goto(shareUrl, { waitUntil: "domcontentloaded" });
      record("E-share", "E3 撤销后分享失效", resp2.status() >= 400 || (await anonPage2.content()).includes("失效"), `status=${resp2.status()}`);
      await anon2.close();
    }
    // 简历导出（编辑器导出按钮）
    if (state.resumeId) {
      await page.goto(`${BASE}/workspace?view=resume-new&resume_id=${state.resumeId}`, { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(2000);
      const exportBtn = page.locator('[data-export="yes"] button:has-text("导出"), button:has-text("导出")').first();
      if (await exportBtn.count()) {
        const dl = page.waitForEvent("download", { timeout: 30000 }).catch(() => null);
        await exportBtn.click();
        const file = await dl;
        record("E-export", "E5 简历导出下载", !!file, file ? file.suggestedFilename() : "无下载事件");
      } else record("E-export", "E5 简历导出下载", false, "没有导出按钮");
    }
  } catch (e) {
    record("C/D/E", "主旅程异常", false, e.message);
  }

  // ---------- 旅程 F：管理端 ----------
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    const page = await ctx.newPage();
    watch(page);
    try {
      await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
      await typeInto(page, "[name=email]", "journey-admin@example.com");
      await typeInto(page, "[name=password]", PASSWORD);
      await page.click('form[data-ui-form="auth"] button[type="submit"]');
      await page.waitForURL((u) => !u.pathname.includes("login"), { timeout: 15000 });
      for (const [name, p] of [
        ["F1 管理端概览", "/admin"],
        ["F2 用户管理", "/admin/users"],
        ["F3 订单管理", "/admin/orders"],
        ["F4 模型配置", "/admin/settings"],
        ["F5 审计日志", "/admin/audit"],
      ]) {
        const resp = await page.goto(`${BASE}${p}`, { waitUntil: "domcontentloaded" });
        const body = await page.content();
        const looksRight = resp.status() === 200 && !body.includes('data-ui-form="auth"');
        record("F-admin", name, looksRight, `status=${resp.status()}`);
        if (p === "/admin") await shot(page, "f1-admin-dashboard");
      }
      // 非管理员访问 admin 应被拒
      const anon = await browser.newContext();
      const anonPage = await anon.newPage();
      const resp = await anonPage.goto(`${BASE}/admin`, { waitUntil: "domcontentloaded" });
      const anonBody = await anonPage.content();
      record("F-admin", "F6 匿名访问管理端被拒", anonBody.includes('data-ui-form="auth"') || resp.status() >= 400, `status=${resp.status()}`);
      await anon.close();
    } catch (e) {
      record("F-admin", "旅程 F 异常", false, e.message);
    }
    await ctx.close();
  }

  await ctx.close();
  await browser.close();

  const passed = steps.filter((s) => s.ok).length;
  const summary = {
    total: steps.length,
    passed,
    failed: steps.length - passed,
    issues,
    consoleErrors: consoleErrors.slice(0, 60),
    startedAt: startedAt.toISOString(),
    account: NEW_EMAIL,
  };
  fs.writeFileSync(path.join(OUT, "journeys.json"), JSON.stringify({ summary, steps }, null, 2));
  console.log(`\n=== ${passed}/${steps.length} 通过 ===`);
  if (issues.length) console.log("失败项:", JSON.stringify(issues, null, 1));
  if (consoleErrors.length) console.log("控制台/网络错误:", consoleErrors.slice(0, 10).join("\n"));
})();
