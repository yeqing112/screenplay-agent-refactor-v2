const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE = process.env.E2E_BASE_URL || 'http://127.0.0.1:5176';
const OUT = path.resolve(process.env.E2E_ARTIFACT_DIR || 'output/playwright/user-journey');
fs.mkdirSync(OUT, { recursive: true });

function safeName(value) { return String(value).replace(/[^a-zA-Z0-9_-]+/g, '-').slice(0, 80); }

async function runOnce(browser, index) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  page.on('dialog', dialog => dialog.accept());
  const mutations = [];
  const externalHosts = [];
  const consoleErrors = [];
  let disposableProjectId = null;
  const disposableTitle = `V3 UI Journey Mock Run ${index}`;
  page.on('request', request => {
    const url = new URL(request.url());
    if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method())) {
      mutations.push({ method: request.method(), path: `${url.pathname}${url.search}`, host: url.host, body: request.postDataJSON?.() ?? request.postData() ?? null });
    }
    if (!['127.0.0.1:5176', '127.0.0.1:18768'].includes(url.host)) externalHosts.push(url.host);
  });
  page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()); });
  const responseErrors = [];
  page.on('response', async response => {
    if (response.request().method() === 'POST' && response.status() >= 400) {
      let body = null;
      try { body = await response.json(); } catch { try { body = await response.text(); } catch { /* ignore */ } }
      responseErrors.push({ path: new URL(response.url()).pathname, status: response.status(), body });
    }
    if (response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/books') {
      try {
        const payload = await response.json();
        if (payload?.id) disposableProjectId = Number(payload.id);
      } catch { /* response may be unavailable after navigation */ }
    }
  });
  const evidence = { run: index, started_at: new Date().toISOString(), steps: [], blockers: [], screenshot_paths: [], mutations, response_errors: responseErrors, external_hosts: externalHosts, console_errors: consoleErrors };
  const shot = async (name) => { const file = path.join(OUT, `${String(index).padStart(2, '0')}-${safeName(name)}.png`); await page.screenshot({ path: file, fullPage: true }); evidence.screenshot_paths.push(file); };
  const step = async (name, action) => {
    try { await action(); evidence.steps.push({ name, status: 'passed' }); }
    catch (error) { evidence.steps.push({ name, status: 'blocked', error: String(error) }); evidence.blockers.push({ step: name, error: String(error) }); }
  };
  const clickIfVisible = async (role, name, options = {}) => {
    const locator = page.getByRole(role, { name, exact: options.exact ?? false }).first();
    if (await locator.count() === 0) throw new Error(`UI control not found: ${role} ${name}`);
    await locator.click();
  };

  await step('project-list', async () => { await page.goto(BASE); await page.getByRole('button', { name: '新建项目' }).waitFor(); await shot('project-list'); });
  await step('create-project-through-ui', async () => {
    await clickIfVisible('button', '新建项目');
    await page.getByLabel('项目名称').fill(disposableTitle);
    await clickIfVisible('button', '创建项目');
    await page.waitForTimeout(500);
    await shot('created-project');
  });
  await step('content-preparation', async () => { await clickIfVisible('button', '内容准备'); await shot('content-preparation'); });
  await step('short-story-input-and-import', async () => {
    const importSummary = page.getByText(/导入小说，建立内容基础|高级：更换内容或导入新的小说/).first();
    const title = page.getByPlaceholder('短篇标题');
    const text = page.getByPlaceholder('粘贴短篇正文');
    if (!(await title.isVisible().catch(() => false))) {
      if (await importSummary.count() && await importSummary.isVisible()) await importSummary.click();
    }
    await title.waitFor({ state: 'visible', timeout: 15000 });
    await text.waitFor({ state: 'visible', timeout: 15000 });
    await title.fill(`潮汐回声-${index}`);
    await text.fill('雨夜旧港的潮声盖过了脚步。林默在仓库门口发现一枚带血的旧钥匙，远处的灯塔忽明忽暗。她推开仓库门，看见顾言站在堆满渔网的阴影里。顾言说钥匙来自失踪的船长，林默却认出上面的刻痕属于自己的父亲。灯塔再次熄灭时，仓库外传来急促的脚步声。');
    await page.getByRole('button', { name: '创建短篇并导入' }).click();
    await page.getByText('内容准备完成', { exact: false }).waitFor({ timeout: 120000 });
    await shot('content-ready');
  });
  await step('production-skill-and-adaptation-lock', async () => {
    await clickIfVisible('button', '改编方向');
    await page.getByRole('button', { name: '锁定 Production Skill' }).waitFor({ timeout: 30000 });
    await page.getByRole('button', { name: '锁定 Production Skill' }).click();
    const candidates = page.getByRole('button', { name: /竖屏情绪悬疑短剧|都市关系流连续短剧|强反转剧情向短剧/ });
    if (await candidates.count() === 0) throw new Error('adaptation candidates were not rendered');
    await candidates.first().click();
    await candidates.first().waitFor({ state: 'visible' });
    if ((await candidates.first().getAttribute('aria-pressed')) !== 'true') throw new Error('adaptation candidate selection did not persist');
    await page.getByRole('button', { name: '锁定为主方向' }).click();
    await page.getByRole('button', { name: '进入剧本工作台' }).waitFor({ timeout: 10000 });
    await shot('adaptation-locked');
  });
  await step('script-generation-and-review', async () => {
    await clickIfVisible('button', '剧本工作台');
    await page.waitForFunction(() => {
      const text = document.body.innerText;
      return text.includes('一键生成剧本') || text.includes('锁稿 / 放行') || text.includes('第 1 集剧本详情');
    }, null, { timeout: 120000 });
    const generate = page.getByRole('button', { name: '一键生成剧本', exact: true });
    if (await generate.count() && await generate.isVisible()) {
      await generate.click();
      await page.getByText('锁稿 / 放行', { exact: true }).waitFor({ timeout: 120000 });
    } else {
      await page.getByText('锁稿 / 放行', { exact: true }).waitFor({ timeout: 120000 });
    }
    await shot('script-generated');
  });
  await step('script-lock-release-and-production-preparation', async () => {
    await page.getByText('锁稿 / 放行', { exact: true }).waitFor({ timeout: 60000 });
    const note = page.getByPlaceholder('记录锁稿理由、退回原因或放行说明');
    if (await note.count()) await note.fill('E2E mock journey: script reviewed and ready for production.');
    await page.getByRole('button', { name: '确认锁稿', exact: true }).click();
    await page.getByRole('button', { name: '放行到分镜', exact: true }).click();
    await page.getByRole('button', { name: '准备进入导演阶段', exact: true }).click();
    await page.getByText('剧本生产结构已准备完成，可以进入导演阶段。', { exact: true }).waitFor({ timeout: 30000 });
    await shot('production-prepared');
  });
  await step('director-treatment-review-and-confirm', async () => {
    await page.getByRole('button', { name: '查看导演方案', exact: true }).click();
    await page.getByText('已生成只读方案；尚未调用模型，也未写入生产数据。', { exact: true }).waitFor({ timeout: 30000 });
    await page.getByRole('button', { name: '让 AI 优化方案', exact: true }).click();
    await page.getByText(/候选草案已生成|已有相同证据的候选草案/, { exact: false }).waitFor({ timeout: 90000 });
    await page.getByRole('button', { name: '确认写入正式版本', exact: true }).click();
    await page.getByText('导演方案已写入正式版本；下一步才能进入场景调度。', { exact: true }).waitFor({ timeout: 30000 });
    await shot('director-treatment-confirmed');
  });
  await step('director-runtime-scene-blocking-shot-plan', async () => {
    await page.getByText('导演运行时', { exact: false }).waitFor({ timeout: 15000 });
    const runtime = page.locator('section').filter({ hasText: '导演运行时' }).first();
    const previews = runtime.getByRole('button', { name: '预览 / 更新', exact: true });
    await previews.nth(0).click();
    await runtime.getByRole('button', { name: '确认批准', exact: true }).click({ timeout: 60000 });
    await page.waitForTimeout(500);
    const blockingError = responseErrors.find((item) => item.path.endsWith('/scene-blocking/confirm'));
    if (blockingError) throw new Error(`SceneBlocking confirmation blocked: ${JSON.stringify(blockingError.body)}`);
    await runtime.getByText('空间调度已批准；现在可以生成 ShotPlan。', { exact: true }).waitFor({ timeout: 30000 });
    await previews.nth(1).click();
    await runtime.getByRole('button', { name: '确认写入', exact: true }).click({ timeout: 60000 });
    await runtime.getByText('ShotPlan 已批准；正式分镜生成门禁已放行。', { exact: true }).waitFor({ timeout: 30000 });
    await runtime.getByRole('button', { name: '运行 Benchmark', exact: true }).click();
    await runtime.getByText(/通过 ·/, { exact: false }).waitFor({ timeout: 30000 });
    await shot('director-runtime-approved');
  });
  await step('director-and-shot-workbench-observation', async () => {
    await clickIfVisible('button', '镜头工作台');
    await page.getByRole('heading', { name: '镜头工作台' }).waitFor({ timeout: 30000 });
    await page.waitForFunction(() => !document.body.innerText.includes('正在加载工作区...'), null, { timeout: 30000 }).catch(() => {});
    await shot('shot-workbench');
  });
  await step('asset-blocker-evidence', async () => {
    await clickIfVisible('button', '资产中心');
    await page.waitForFunction(() => !document.body.innerText.includes('正在加载工作区...') && !document.body.innerText.includes('正在同步项目数据'), null, { timeout: 30000 }).catch(() => {});
    await shot('asset-blocker');
    const body = await page.locator('body').innerText();
    if (!body.includes('缺少真实视觉资产') && !body.includes('当前没有 Production Asset')) throw new Error('asset blocker was not visible');
    if (disposableProjectId) {
      evidence.canonical_read_only = await page.evaluate(async (bookId) => {
        const response = await fetch(`/api/books/${bookId}/production-workspace-v2`, { cache: 'no-store' });
        return { status: response.status, payload: await response.json().catch(() => null) };
      }, disposableProjectId);
    }
  });
  await step('return-and-dispose-project-through-ui', async () => {
    await clickIfVisible('button', '项目列表');
    if (disposableProjectId) {
      const card = page.locator(`[data-book-id="${disposableProjectId}"]`).first();
      await card.waitFor({ state: 'visible', timeout: 10000 }).catch(() => {});
      if (await card.count() && await card.isVisible().catch(() => false)) {
        await card.locator('button[title="删除项目"]').click();
        await page.waitForTimeout(500);
      }
    }
    await shot('project-cleanup');
  });
  evidence.disposable_project_id = disposableProjectId;
  evidence.finished_at = new Date().toISOString();
  await fs.promises.writeFile(path.join(OUT, `run-${index}.json`), JSON.stringify(evidence, null, 2));
  await context.close();
  return evidence;
}

(async () => {
  const browser = await chromium.launch({ headless: process.env.E2E_HEADED !== '1' });
  const runs = [];
  for (const index of [1, 2]) runs.push(await runOnce(browser, index));
  await browser.close();
  let ledger = {};
  try { ledger = await (await fetch(`${process.env.E2E_API_URL || 'http://127.0.0.1:18768'}/api/e2e/mock-ledger`)).json(); } catch (error) { ledger = { error: String(error) }; }
  const summary = { schema_version: 'production-ui-v3-browser-user-journey-mock-v1', generated_at: new Date().toISOString(), runs, ledger, policy: { mutations_via_visible_ui_only: true, real_external_hosts_allowed: [], mock_runtime_only: true } };
  await fs.promises.writeFile(path.join(OUT, 'summary.json'), JSON.stringify(summary, null, 2));
  console.log(JSON.stringify({ output: path.join(OUT, 'summary.json'), runs: runs.length, external_hosts: [...new Set(runs.flatMap(item => item.external_hosts))] }, null, 2));
})().catch(error => { console.error(error); process.exitCode = 1; });
