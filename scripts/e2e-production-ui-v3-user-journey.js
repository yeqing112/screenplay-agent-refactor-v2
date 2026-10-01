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
  page.setDefaultTimeout(5000);
  const mutations = [];
  const externalHosts = [];
  const consoleErrors = [];
  let disposableProjectId = null;
  const disposableTitle = `V3 UI Journey Mock Run ${index}`;
  page.on('request', request => {
    const url = new URL(request.url());
    if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method())) {
      mutations.push({ method: request.method(), path: `${url.pathname}${url.search}`, host: url.host });
    }
    if (!['127.0.0.1:5176', '127.0.0.1:18768'].includes(url.host)) externalHosts.push(url.host);
  });
  page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()); });
  const evidence = { run: index, started_at: new Date().toISOString(), steps: [], blockers: [], screenshot_paths: [], mutations, external_hosts: externalHosts, console_errors: consoleErrors };
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
    const cardId = await page.locator('[data-book-id]').first().getAttribute('data-book-id').catch(() => null);
    disposableProjectId = cardId ? Number(cardId) : null;
    await shot('created-project');
  });
  await step('content-preparation', async () => { await clickIfVisible('button', '内容准备'); await shot('content-preparation'); });
  await step('director-and-shot-workbench-observation', async () => {
    await clickIfVisible('button', '剧本工作台');
    await page.getByText('导演运行时', { exact: false }).waitFor().catch(() => {});
    await shot('director-runtime');
    await clickIfVisible('button', '镜头工作台');
    await page.getByRole('heading', { name: '镜头工作台' }).waitFor();
    await shot('shot-workbench');
  });
  await step('asset-blocker-evidence', async () => { await clickIfVisible('button', '资产中心'); await shot('asset-blocker'); const body = await page.locator('body').innerText(); if (!body.includes('缺少真实视觉资产') && !body.includes('当前没有 Production Asset')) throw new Error('asset blocker was not visible'); });
  await step('return-and-dispose-project-through-ui', async () => {
    await clickIfVisible('button', '项目列表');
    {
      const card = page.getByLabel(`打开项目 ${disposableTitle}`).first();
      if (await card.count()) {
        page.once('dialog', dialog => dialog.accept());
        await card.locator('button[title="删除项目"]').click();
        await page.waitForTimeout(300);
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
