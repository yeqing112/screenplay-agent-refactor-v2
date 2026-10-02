const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE = process.env.E2E_BASE_URL || 'http://127.0.0.1:5176';
const ALLOWED_HOSTS = new Set([new URL(BASE).host, new URL(process.env.E2E_API_URL || 'http://127.0.0.1:18768').host]);
const OUT = path.resolve(process.env.E2E_ARTIFACT_DIR || 'output/playwright/user-journey');
const REAL_IMAGE_STAGING = process.env.E2E_REAL_IMAGE_STAGING === '1';
const REAL_IMAGE_SINGLE_CALL = process.env.E2E_REAL_IMAGE_SINGLE_CALL === '1';
const REAL_IMAGE_PROFILE_ID = process.env.E2E_REAL_IMAGE_PROFILE_ID || 'local-image-mw4y52';
const EXISTING_CANARY_BOOK_ID = Number(process.env.E2E_EXISTING_CANARY_BOOK_ID || 0) || null;
fs.mkdirSync(OUT, { recursive: true });

function safeName(value) { return String(value).replace(/[^a-zA-Z0-9_-]+/g, '-').slice(0, 80); }

async function clickAndWaitForResponse(page, locator, predicate, timeout = 30000) {
  const responsePromise = page.waitForResponse(predicate, { timeout }).catch((error) => ({ __wait_error: error }));
  let clickError = null;
  try {
    await locator.click();
  } catch (error) {
    clickError = error;
  }
  const response = await responsePromise;
  if (clickError) throw clickError;
  if (response?.__wait_error) throw response.__wait_error;
  return response;
}

async function clickAndObserveResponse(page, locator, predicate, observationWindow = 8000) {
  const responsePromise = page.waitForResponse(predicate, { timeout: 120000 }).catch(() => null);
  let clickError = null;
  try {
    await locator.click();
  } catch (error) {
    clickError = error;
  }
  const response = await Promise.race([
    responsePromise,
    page.waitForTimeout(observationWindow).then(() => null),
  ]);
  if (clickError) throw clickError;
  return response;
}

async function readWorkspaceV2(page, bookId) {
  const response = await page.request.get(`${new URL(page.url()).origin}/api/books/${bookId}/production-workspace-v2`, { headers: { 'Cache-Control': 'no-cache' } });
  const payload = await response.json().catch(() => null);
  if (!response.ok()) throw new Error(`production workspace read failed: HTTP ${response.status()} ${JSON.stringify(payload)}`);
  return payload;
}

function findWorkspaceShot(payload, shotId) {
  const wanted = String(shotId);
  return (payload?.shots || []).find((item) => String(item?.identity?.shot_id ?? '') === wanted) || null;
}

async function waitForWorkspaceShot(page, bookId, shotId, predicate, timeout = 120000) {
  const deadline = Date.now() + timeout;
  let latest = null;
  while (Date.now() < deadline) {
    const payload = await readWorkspaceV2(page, bookId);
    latest = findWorkspaceShot(payload, shotId);
    if (latest && predicate(latest, payload)) return { shot: latest, payload };
    await page.waitForTimeout(100);
  }
  throw new Error(`timed out waiting for canonical shot ${shotId}: ${JSON.stringify(latest)}`);
}

function executionState(shot, target) {
  return String(shot?.[target]?.latest_execution?.state || shot?.[target]?.execution?.state || '').toUpperCase();
}

function executionIdentity(shot, target) {
  const execution = shot?.[target]?.latest_execution || shot?.[target]?.execution || {};
  return {
    execution_id: execution.id || null,
    provider_task_id: execution.provider_task_id || null,
    provider_request_id: execution.provider_request_id || null,
    state: String(execution.state || '').toUpperCase(),
  };
}

async function runOnce(browser, index) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  page.on('dialog', dialog => dialog.accept());
  const mutations = [];
  const externalHosts = [];
  const consoleErrors = [];
  let disposableProjectId = null;
  const disposableTitle = `${REAL_IMAGE_STAGING ? 'V3 Real SHAPI Image Staging' : 'V3 UI Journey Mock Run'} ${index} ${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
  const runToken = `${index}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  page.on('request', request => {
    const url = new URL(request.url());
    if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method())) {
      mutations.push({ method: request.method(), path: `${url.pathname}${url.search}`, host: url.host, body: request.postDataJSON?.() ?? request.postData() ?? null });
    }
    if (!ALLOWED_HOSTS.has(url.host)) externalHosts.push(url.host);
  });
  page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()); });
  const responseErrors = [];
  const httpErrors = [];
  page.on('response', async response => {
    if (response.status() >= 400) {
      httpErrors.push({ method: response.request().method(), path: new URL(response.url()).pathname, status: response.status() });
    }
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
  const evidence = { run: index, started_at: new Date().toISOString(), viewport: { width: 1440, height: 900 }, steps: [], blockers: [], screenshot_paths: [], mutations, response_errors: responseErrors, http_errors: httpErrors, external_hosts: externalHosts, console_errors: consoleErrors, policy: { ordinary_user_browser_only: true, direct_database_seed: false, business_api_response_mocking: false, workspace_fixture_used: false, legacy_ui_bypass: false, page_route_count: 0 }, reload_checks: [], viewport_smoke: [], protected_book_990400_writes: 0, delete_audit: null };
  if (EXISTING_CANARY_BOOK_ID) disposableProjectId = EXISTING_CANARY_BOOK_ID;
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

  await step('project-list', async () => { await page.goto(EXISTING_CANARY_BOOK_ID ? `${BASE}/?book_id=${EXISTING_CANARY_BOOK_ID}` : BASE); await page.getByRole('button', { name: EXISTING_CANARY_BOOK_ID ? '正式工作台' : '新建项目' }).waitFor(); await shot('project-list'); });
  await step('create-project-through-ui', async () => {
    if (EXISTING_CANARY_BOOK_ID) return;
    await clickIfVisible('button', '新建项目');
    await page.getByLabel('项目名称').fill(disposableTitle);
    await clickIfVisible('button', '创建项目');
    await page.waitForTimeout(500);
    const createdUrl = page.url();
    await page.reload();
    await page.waitForFunction(() => !document.body.innerText.includes('正在加载') && !document.body.innerText.includes('正在同步'), null, { timeout: 30000 }).catch(() => {});
    const restoredBook = await page.evaluate(async (bookId) => {
      const response = await fetch('/api/books', { cache: 'no-store' });
      const books = await response.json().catch(() => []);
      return { status: response.status, found: Array.isArray(books) && books.some((item) => Number(item.id) === Number(bookId)) };
    }, disposableProjectId);
    const restoredCanvas = page.getByText('正式工作台', { exact: true });
    if (!restoredBook.found || !(await restoredCanvas.isVisible().catch(() => false)) || !page.url().includes(`book_id=${disposableProjectId}`)) {
      throw new Error(`project reload did not preserve the created project: ${createdUrl} -> ${page.url()} / ${JSON.stringify(restoredBook)}`);
    }
    evidence.reload_checks.push({ stage: 'project-created', preserved_book_id: disposableProjectId, url: page.url(), server_backed: restoredBook });
    await shot('created-project');
  });
  await step('content-preparation', async () => { if (EXISTING_CANARY_BOOK_ID) return; await clickIfVisible('button', '内容准备'); await shot('content-preparation'); });
  await step('short-story-input-and-import', async () => {
    if (EXISTING_CANARY_BOOK_ID) return;
    const importSummary = page.getByText(/导入小说，建立内容基础|高级：更换内容或导入新的小说/).first();
    const title = page.getByPlaceholder('短篇标题');
    const text = page.getByPlaceholder('粘贴短篇正文');
    if (!(await title.isVisible().catch(() => false))) {
      if (await importSummary.count() && await importSummary.isVisible()) await importSummary.click();
    }
    await title.waitFor({ state: 'visible', timeout: 15000 });
    await text.waitFor({ state: 'visible', timeout: 15000 });
    await title.fill(`潮汐回声-${index}`);
    await text.fill(`雨夜旧港的潮声盖过了脚步。林默在仓库门口发现一枚带血的旧钥匙，远处的灯塔忽明忽暗。她推开仓库门，看见顾言站在堆满渔网的阴影里。顾言说钥匙来自失踪的船长，林默却认出上面的刻痕属于自己的父亲。灯塔再次熄灭时，仓库外传来急促的脚步声。E2E-${runToken}`);
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
    await page.evaluate((bookId) => {
      for (const key of Object.keys(localStorage)) {
        if (key === `product-workspace:adaptation:${bookId}` || key === `product-workspace:production-skill:${bookId}`) localStorage.removeItem(key);
      }
    }, disposableProjectId);
    await page.reload();
    await page.waitForFunction(() => !document.body.innerText.includes('正在加载') && !document.body.innerText.includes('正在同步'), null, { timeout: 30000 }).catch(() => {});
    await clickIfVisible('button', '改编方向');
    await page.getByText(/当前项目已经锁定主方向|当前主方向：/, { exact: false }).first().waitFor({ timeout: 30000 });
    evidence.reload_checks.push({ stage: 'adaptation-after-local-storage-clear', server_backed: true });
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
    await page.reload();
    await page.waitForFunction(() => !document.body.innerText.includes('正在加载') && !document.body.innerText.includes('正在同步'), null, { timeout: 30000 }).catch(() => {});
    await page.getByRole('button', { name: '剧本工作台', exact: true }).waitFor({ timeout: 30000 });
    evidence.reload_checks.push({ stage: 'script-production-prepared', restored: true });
    await shot('production-prepared');
  });
  await step('director-treatment-review-and-confirm', async () => {
    await clickIfVisible('button', '剧本工作台');
    await page.waitForFunction(() => document.body.innerText.includes('剧本工作台') || document.body.innerText.includes('查看导演方案'), null, { timeout: 30000 });
    await page.waitForFunction(async () => {
      const id = new URL(window.location.href).searchParams.get('book_id');
      if (!id) return false;
      const response = await fetch(`/api/books/${id}/episodes/1/script-ir`, { cache: 'no-store' });
      const payload = await response.json().catch(() => null);
      return response.ok && Boolean(payload?.payload?.scenes?.[0]?.scene_id);
    }, null, { timeout: 30000 }).catch(() => {});
    const treatmentButton = page.getByRole('button', { name: '查看导演方案', exact: true });
    const readonlyMessage = page.getByText('已生成只读方案；尚未调用模型，也未写入生产数据。', { exact: true });
    await treatmentButton.click();
    try {
      await readonlyMessage.waitFor({ timeout: 30000 });
    } catch (error) {
      const sceneIdRace = responseErrors.some((item) => item.path.endsWith('/director-treatment/preview') && item.body?.detail?.code === 'SCENE_ID_REQUIRED');
      if (!sceneIdRace) throw error;
      await page.waitForTimeout(1000);
      await treatmentButton.click();
      await readonlyMessage.waitFor({ timeout: 30000 });
    }
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
    let blockingError = responseErrors.find((item) => item.path.endsWith('/scene-blocking/confirm'));
    if (blockingError) {
      // A reused local SQLite draft can carry stale derived validation. The
      // visible preview action refreshes the draft before the second human
      // confirmation; no direct mutation bypass is used.
      await previews.nth(0).click();
      await page.waitForTimeout(500);
      await runtime.getByRole('button', { name: '确认批准', exact: true }).click({ timeout: 60000 });
      await page.waitForTimeout(500);
      const approved = await runtime.getByText('空间调度已批准；现在可以生成 ShotPlan。', { exact: true }).isVisible().catch(() => false);
      if (approved) blockingError = null;
    }
    if (blockingError) throw new Error(`SceneBlocking confirmation blocked: ${JSON.stringify(blockingError.body)}`);
    await runtime.getByText('空间调度已批准；现在可以生成 ShotPlan。', { exact: true }).waitFor({ timeout: 30000 });
    await previews.nth(1).click();
    // The deterministic mock script can produce a dense four-second plan.
    // Keep the human review path real by editing the visible duration fields
    // before confirmation, using the recommended six-second budget.
    const durationInputs = runtime.locator('input[type="number"]');
    await durationInputs.first().waitFor({ state: 'visible', timeout: 30000 });
    for (let index = 0; index < await durationInputs.count(); index += 1) {
      await durationInputs.nth(index).fill('6');
    }
    await page.waitForTimeout(300);
    await runtime.getByRole('button', { name: '确认写入', exact: true }).click({ timeout: 60000 });
    await runtime.getByText('ShotPlan 已批准；正式分镜生成门禁已放行。', { exact: true }).waitFor({ timeout: 30000 });
    const plansResponse = await page.request.get(`${new URL(page.url()).origin}/api/books/${disposableProjectId}/episodes/1/shot-plans`);
    const plansPayload = await plansResponse.json();
    evidence.shot_plan_after_confirm = plansPayload;
    const currentPlan = (plansPayload.items || []).find((item) => item.status === 'approved' && item.workflow_profile === 'production');
    if (!currentPlan || currentPlan.model_info?.phase_c_semantic_ready !== true) throw new Error(`ShotPlan confirmation did not produce Phase C semantic-ready authority: ${JSON.stringify(currentPlan?.model_info || null)}`);
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
  await step('storyboard-materialization-through-ui', async () => {
    // The default V3 empty state exposes the normal production action. The
    // click delegates to the existing canonical materializer facade.
    const generate = page.getByRole('button', { name: '生成分镜', exact: true });
    await generate.waitFor({ state: 'visible', timeout: 30000 });
    const materialize = await clickAndWaitForResponse(page, generate, (response) => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/storyboard/materialize'), 120000);
    if (!materialize.ok()) throw new Error(`Storyboard materialization failed: HTTP ${materialize.status()} ${await materialize.text()}`);
    await page.locator('[data-testid="shot-studio-v3"]').waitFor({ state: 'visible', timeout: 120000 });
    const materializedShots = page.locator('[data-testid^="shot-studio-shot-"]');
    await materializedShots.first().waitFor({ state: 'visible', timeout: 120000 });
    const materializedShotIds = await materializedShots.evaluateAll((nodes) => nodes.map((node) => String(node.getAttribute('data-testid') || '').replace(/^shot-studio-shot-/, '')).filter(Boolean));
    if (!materializedShotIds.length) throw new Error('Storyboard materialization returned no canonical shots.');
    evidence.materialized_shot_ids = materializedShotIds;
    const workspace = await readWorkspaceV2(page, disposableProjectId);
    evidence.materialized_shots = (workspace.shots || []).filter((item) => materializedShotIds.includes(String(item?.identity?.shot_id ?? ''))).map((item) => item.identity);
    if (evidence.materialized_shots.length !== materializedShotIds.length) throw new Error(`Materialized shot projection mismatch: ${JSON.stringify({ materializedShotIds, projected: evidence.materialized_shots })}`);
    await shot('storyboard-materialized');
  });
  await step('production-asset-bridge-through-ui', async () => {
    const v3Url = new URL(page.url());
    v3Url.searchParams.set('section', 'storyboard');
    v3Url.searchParams.set('ui_v3', 'shot-studio');
    await page.goto(v3Url.toString());
    await page.waitForFunction(() => !document.body.innerText.includes('正在加载工作区...') && !document.body.innerText.includes('正在同步项目数据'), null, { timeout: 30000 }).catch(() => {});
    const assetPath = path.join(OUT, `${String(index).padStart(2, '0')}-production-asset.png`);
    fs.writeFileSync(assetPath, Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64'));
    const checks = [];
    for (const shotId of evidence.materialized_shot_ids || []) {
      const shotButton = page.getByTestId(`shot-studio-shot-${shotId}`);
      await shotButton.waitFor({ state: 'visible', timeout: 30000 });
      await shotButton.click();
      await shotButton.waitFor({ state: 'attached', timeout: 30000 });
      const bridge = page.locator('[data-testid="production-asset-bridge"]');
      // The bridge is mounted asynchronously after the shot selection.  Do
      // not gate on visibility here: its upload input is intentionally
      // sr-only, while the section itself may still be settling after the
      // workspace refresh.
      await page.waitForTimeout(500);
      if (await bridge.count()) {
        const uploadInput = bridge.locator('input[type="file"]').first();
        if (await uploadInput.count()) {
          await uploadInput.setInputFiles(assetPath);
          const approve = bridge.getByRole('button', { name: '批准并激活', exact: true }).first();
          await approve.waitFor({ state: 'visible', timeout: 60000 });
          await approve.click();
        }
        const bind = bridge.getByRole('button', { name: /显式绑定到当前镜头|重新绑定当前版本/, exact: false }).first();
        // Approval refreshes bridge-state asynchronously.  Resolve the
        // locator before the refresh and wait for its eventual appearance so
        // the explicit binding POST cannot be skipped during the rerender.
        await bind.waitFor({ state: 'visible', timeout: 60000 });
        await bind.click();
      }
      const storyboardShotId = (evidence.materialized_shots || []).find((item) => String(item?.shot_id) === String(shotId))?.storyboard_shot_id;
      if (!storyboardShotId) throw new Error(`Missing storyboard_shot_id for materialized shot ${shotId}`);
      let readinessPayload = null;
      const readinessDeadline = Date.now() + 60000;
      while (Date.now() < readinessDeadline) {
        const readinessResponse = await page.request.get(`${new URL(page.url()).origin}/api/books/${disposableProjectId}/production-assets/shots/${storyboardShotId}/readiness`, { headers: { 'Cache-Control': 'no-cache' } });
        readinessPayload = await readinessResponse.json().catch(() => null);
        if (readinessResponse.ok() && readinessPayload?.asset_readiness?.current === true) break;
        await page.waitForTimeout(300);
      }
      if (!readinessPayload?.asset_readiness?.current) throw new Error(`Production Asset readiness is not current for shot ${shotId}: ${JSON.stringify(readinessPayload)}`);
      checks.push({ shot_id: String(shotId), storyboard_shot_id: storyboardShotId, current: true, readiness: readinessPayload.asset_readiness });
    }
    evidence.production_asset_checks = checks;
    if (checks.length !== (evidence.materialized_shot_ids || []).length) throw new Error('Not every materialized shot received a current Production Asset binding.');
    await shot('production-assets-bound');
  });
  await step('all-shots-prompt-media-review-through-ui', async () => {
    if (REAL_IMAGE_STAGING) {
      const imageModel = page.getByLabel('IMAGE 生成模型', { exact: true });
      await imageModel.waitFor({ state: 'visible', timeout: 30000 });
      await imageModel.selectOption(REAL_IMAGE_PROFILE_ID);
      const shotId = String((evidence.materialized_shot_ids || [])[0] || '');
      if (!shotId) throw new Error('Real IMAGE staging requires one materialized target shot.');
      const shotButton = page.getByTestId(`shot-studio-shot-${shotId}`);
      await shotButton.click();
      const prepareImage = page.getByRole('button', { name: '准备 IMAGE PromptIR', exact: true });
      const imagePrompt = await clickAndWaitForResponse(page, prepareImage, (response) => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/prompt-ir/compile'), 30000);
      if (!imagePrompt.ok()) throw new Error(`IMAGE PromptIR compilation failed: HTTP ${imagePrompt.status()} ${await imagePrompt.text()}`);
      await waitForWorkspaceShot(page, disposableProjectId, shotId, (current) => current.IMAGE?.prompt_ir?.current === true);
      await page.getByRole('button', { name: '图片', exact: true }).click();

      const generateImage = page.getByRole('button', { name: '生成 IMAGE', exact: true });
      await generateImage.waitFor({ state: 'visible', timeout: 30000 });
      const initialGeneration = await clickAndWaitForResponse(page, generateImage, (response) => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/generate-frame'), 180000);
      if (!initialGeneration.ok()) throw new Error(`Initial real IMAGE generation failed: HTTP ${initialGeneration.status()} ${await initialGeneration.text()}`);
      await page.getByText('候选媒体审核', { exact: true }).waitFor({ timeout: 180000 });
      const initialCandidate = await waitForWorkspaceShot(page, disposableProjectId, shotId, (current) => current.IMAGE?.candidate?.reviewEligibility === true && current.IMAGE?.latest_execution?.state === 'SUCCEEDED');
      const initialExecution = executionIdentity(initialCandidate.shot, 'IMAGE');
      const initialCandidateId = initialCandidate.shot.IMAGE?.candidate?.candidate?.id || initialCandidate.shot.IMAGE?.latest_execution?.raw?.candidate_id || null;
      const initialCandidatePreview = initialCandidate.shot.IMAGE?.candidate?.candidate?.preview_url || initialCandidate.shot.IMAGE?.candidate?.candidate?.preview || null;
      const approve = page.getByTestId('shot-studio-review-desk').getByRole('button', { name: '批准并继续', exact: true });
      await approve.waitFor({ state: 'visible', timeout: 30000 });
      const initialPromotion = page.waitForResponse((response) => response.request().method() === 'POST' && new URL(response.url()).pathname.includes('/api/assets/candidates/') && new URL(response.url()).pathname.endsWith('/promote'), { timeout: 60000 });
      await approve.click();
      const initialPromotionResponse = await initialPromotion;
      if (!initialPromotionResponse.ok()) throw new Error(`Initial IMAGE promotion failed: HTTP ${initialPromotionResponse.status()} ${await initialPromotionResponse.text()}`);
      await page.getByText('已建立正式版本', { exact: true }).waitFor({ timeout: 120000 });
      const officialV1State = await waitForWorkspaceShot(page, disposableProjectId, shotId, (current) => current.IMAGE?.official?.current === true && current.IMAGE?.official?.version?.candidate_id === initialCandidateId);
      const officialV1 = officialV1State.shot.IMAGE?.official?.version || {};

      if (REAL_IMAGE_SINGLE_CALL) {
        evidence.real_image_staging = {
          profile_id: REAL_IMAGE_PROFILE_ID,
          model_name: 'grok-imagine-image-quality',
          target_shot_id: shotId,
          initial: { execution: initialExecution, candidate_id: initialCandidateId, preview_present: Boolean(initialCandidatePreview), official_version_id: officialV1.id || null },
          regenerate: null,
          final: { official_v1_version_id: officialV1.id || null, official_v1_current: officialV1.current === true },
          video_status: 'FROZEN_NO_CALL',
        };
        evidence.real_provider_generation_posts = (evidence.mutations || []).filter((mutation) => mutation.method === 'POST' && mutation.path.endsWith('/generate-frame')).length;
        await shot('real-image-v1-official');
        return;
      }

      const regenerate = page.getByTestId('shot-studio-regenerate-image');
      await regenerate.waitFor({ state: 'visible', timeout: 30000 });
      const attemptPost = page.waitForResponse((response) => response.request().method() === 'POST' && new URL(response.url()).pathname.includes('/generation-attempts'), { timeout: 60000 }).catch(() => null);
      await regenerate.click();
      await attemptPost;
      const regeneratedCandidate = await waitForWorkspaceShot(page, disposableProjectId, shotId, (current) => current.IMAGE?.official?.current === true && current.IMAGE?.official?.version?.id === officialV1.id && current.IMAGE?.candidate?.reviewEligibility === true && current.IMAGE?.latest_execution?.state === 'SUCCEEDED' && current.IMAGE?.latest_execution?.id !== initialExecution.execution_id, 180000);
      const regeneratedExecution = executionIdentity(regeneratedCandidate.shot, 'IMAGE');
      const regeneratedCandidateId = regeneratedCandidate.shot.IMAGE?.candidate?.candidate?.id || regeneratedCandidate.shot.IMAGE?.latest_execution?.raw?.candidate_id || null;
      const regeneratedPreview = regeneratedCandidate.shot.IMAGE?.candidate?.candidate?.preview_url || regeneratedCandidate.shot.IMAGE?.candidate?.candidate?.preview || null;
      const duringRegenerationOfficial = regeneratedCandidate.shot.IMAGE?.official?.version || {};
      if (!duringRegenerationOfficial.current && duringRegenerationOfficial.id !== officialV1.id) throw new Error('Official v1 was not current while regenerated candidate awaited review.');
      await page.getByText('候选媒体审核', { exact: true }).waitFor({ timeout: 30000 });
      const approveV2 = page.getByTestId('shot-studio-review-desk').getByRole('button', { name: '批准并继续', exact: true });
      const v2Promotion = page.waitForResponse((response) => response.request().method() === 'POST' && new URL(response.url()).pathname.includes('/api/assets/candidates/') && new URL(response.url()).pathname.endsWith('/promote'), { timeout: 60000 });
      await approveV2.click();
      const v2PromotionResponse = await v2Promotion;
      if (!v2PromotionResponse.ok()) throw new Error(`Regenerated IMAGE promotion failed: HTTP ${v2PromotionResponse.status()} ${await v2PromotionResponse.text()}`);
      await page.getByText('已建立正式版本', { exact: true }).waitFor({ timeout: 120000 });
      const officialV2State = await waitForWorkspaceShot(page, disposableProjectId, shotId, (current) => current.IMAGE?.official?.current === true && current.IMAGE?.official?.version?.id !== officialV1.id && current.IMAGE?.official?.version?.candidate_id === regeneratedCandidateId, 120000);
      const officialV2 = officialV2State.shot.IMAGE?.official?.version || {};
      evidence.real_image_staging = {
        profile_id: REAL_IMAGE_PROFILE_ID,
        model_name: 'grok-imagine-image-quality',
        target_shot_id: shotId,
        initial: { execution: initialExecution, candidate_id: initialCandidateId, preview_present: Boolean(initialCandidatePreview), official_version_id: officialV1.id || null },
        regenerate: { execution: regeneratedExecution, candidate_id: regeneratedCandidateId, preview_present: Boolean(regeneratedPreview), official_v1_current_during_review: duringRegenerationOfficial.id === officialV1.id && duringRegenerationOfficial.current === true },
        final: { official_v2_version_id: officialV2.id || null, candidate_id: officialV2.candidate_id || null, v1_superseded: officialV2.id !== officialV1.id },
        video_status: 'BLOCKED_REAL_VIDEO_NOT_CONFIGURED',
      };
      evidence.real_provider_generation_posts = (evidence.mutations || []).filter((mutation) => mutation.method === 'POST' && (mutation.path.endsWith('/generate-frame') || mutation.path.includes('/generation-attempts'))).length;
      await shot('real-image-v2-official');
      return;
    }
    const imageModel = page.getByLabel('IMAGE 生成模型', { exact: true });
    const videoModel = page.getByLabel('VIDEO 生成模型', { exact: true });
    await imageModel.waitFor({ state: 'visible', timeout: 30000 });
    await videoModel.waitFor({ state: 'visible', timeout: 30000 });
    await imageModel.selectOption('builtin-mock-image');
    await videoModel.selectOption('builtin-mock-video');
    const checks = [];
    for (const shotId of evidence.materialized_shot_ids || []) {
      const shotButton = page.getByTestId(`shot-studio-shot-${shotId}`);
      await shotButton.click();
      const prepareImage = page.getByRole('button', { name: '准备 IMAGE PromptIR', exact: true });
      const imagePrompt = await clickAndWaitForResponse(page, prepareImage, (response) => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/prompt-ir/compile'), 30000);
      if (!imagePrompt.ok()) throw new Error(`IMAGE PromptIR compilation failed for shot ${shotId}: HTTP ${imagePrompt.status()} ${await imagePrompt.text()}`);
      await waitForWorkspaceShot(page, disposableProjectId, shotId, (current) => current.IMAGE?.prompt_ir?.current === true);
      await page.getByRole('button', { name: '图片', exact: true }).click();
      const generateImage = page.getByRole('button', { name: '生成 IMAGE', exact: true });
      await generateImage.waitFor({ state: 'visible', timeout: 30000 });
      const imageGeneration = await clickAndWaitForResponse(page, generateImage, (response) => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/generate-frame'), 120000);
      if (!imageGeneration.ok()) throw new Error(`IMAGE generation failed for shot ${shotId}: HTTP ${imageGeneration.status()} ${await imageGeneration.text()}`);
      await page.getByText('候选媒体审核', { exact: true }).waitFor({ timeout: 120000 });
      await page.getByRole('button', { name: '批准并继续', exact: true }).click();
      await page.getByText('已建立正式版本', { exact: true }).waitFor({ timeout: 120000 });
      const imageOfficial = await waitForWorkspaceShot(page, disposableProjectId, shotId, (current) => current.IMAGE?.official?.current === true);

      const prepareVideo = page.getByRole('button', { name: '准备 VIDEO PromptIR', exact: true });
      const videoPrompt = await clickAndWaitForResponse(page, prepareVideo, (response) => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/prompt-ir/compile'), 30000);
      if (!videoPrompt.ok()) throw new Error(`VIDEO PromptIR compilation failed for shot ${shotId}: HTTP ${videoPrompt.status()} ${await videoPrompt.text()}`);
      await waitForWorkspaceShot(page, disposableProjectId, shotId, (current) => current.VIDEO?.prompt_ir?.current === true && current.VIDEO?.generation_mode === 'IMAGE_TO_VIDEO');
      const imageOfficialId = imageOfficial.shot.IMAGE.official.version?.id || null;
      const generateVideo = page.getByRole('button', { name: '生成 VIDEO', exact: true });
      await page.getByRole('button', { name: '视频', exact: true }).click();
      await generateVideo.waitFor({ state: 'visible', timeout: 30000 });
      const videoResponsePromise = page.waitForResponse((response) => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/generate-video'), { timeout: 120000 }).catch((error) => ({ __wait_error: error }));
      await generateVideo.click();
      evidence.video_poll_states = evidence.video_poll_states || [];
      const runningBefore = await waitForWorkspaceShot(page, disposableProjectId, shotId, (current) => {
        if (evidence.video_poll_states.length < 40) evidence.video_poll_states.push({ state: executionState(current, 'VIDEO'), ...executionIdentity(current, 'VIDEO') });
        return ['RUNNING', 'IN_PROGRESS', 'PROVIDER_PENDING', 'PROVIDER_CALLED'].includes(executionState(current, 'VIDEO')) && Boolean(executionIdentity(current, 'VIDEO').execution_id) && Boolean(executionIdentity(current, 'VIDEO').provider_task_id);
      }, 120000);
      const runningIdentity = executionIdentity(runningBefore.shot, 'VIDEO');
      evidence.video_running_before_reload = evidence.video_running_before_reload || [];
      evidence.video_running_before_reload.push({ shot_id: String(shotId), ...runningIdentity });
      await page.reload();
      await page.waitForFunction(() => !document.body.innerText.includes('正在加载工作区...') && !document.body.innerText.includes('正在同步项目数据'), null, { timeout: 60000 }).catch(() => {});
      const runningAfter = await waitForWorkspaceShot(page, disposableProjectId, shotId, (current) => executionIdentity(current, 'VIDEO').execution_id === runningIdentity.execution_id && executionIdentity(current, 'VIDEO').provider_task_id === runningIdentity.provider_task_id && ['RUNNING', 'IN_PROGRESS', 'PROVIDER_PENDING', 'PROVIDER_CALLED', 'SUCCEEDED'].includes(executionState(current, 'VIDEO')), 120000);
      evidence.video_running_after_reload = evidence.video_running_after_reload || [];
      evidence.video_running_after_reload.push({ shot_id: String(shotId), ...executionIdentity(runningAfter.shot, 'VIDEO'), same_execution: true, same_provider_task: true });
      // A full page reload can abort the Playwright response object even
      // though the POST was accepted and the canonical execution completed.
      // The request ledger plus the V2 candidate are the durable evidence;
      // consume a response when it is available without making an aborted
      // response a false blocker.
      const videoResponse = await Promise.race([videoResponsePromise, page.waitForTimeout(5000).then(() => null)]);
      if (videoResponse && !videoResponse.__wait_error && !videoResponse.ok()) throw new Error(`VIDEO generation failed for shot ${shotId}: HTTP ${videoResponse.status()} ${await videoResponse.text()}`);
      // Reload restores canonical workspace state but not the transient lane
      // tab.  Re-select VIDEO so the review action is bound to the candidate
      // that was just produced, rather than the default IMAGE lane.
      await page.getByRole('button', { name: '视频', exact: true }).click();
      const syncShotStudio = page.getByRole('button', { name: '重新同步 Shot Studio', exact: true });
      if (await syncShotStudio.count()) {
        await syncShotStudio.click();
        await page.waitForTimeout(500);
        await page.getByRole('button', { name: '视频', exact: true }).click();
      }
      await page.getByText('候选媒体审核', { exact: true }).waitFor({ timeout: 120000 });
      const videoApprove = page.getByTestId('shot-studio-review-desk').getByRole('button', { name: '批准并继续', exact: true });
      await videoApprove.waitFor({ state: 'visible', timeout: 30000 });
      await page.waitForTimeout(500);
      if (await videoApprove.isDisabled()) throw new Error(`VIDEO candidate review action is disabled for shot ${shotId}`);
      evidence.video_review_debug = evidence.video_review_debug || [];
      evidence.video_review_debug.push({ shot_id: String(shotId), url: page.url(), text: await page.getByTestId('shot-studio-review-desk').innerText(), disabled: await videoApprove.isDisabled() });
      const videoPromotion = page.waitForResponse((response) => response.request().method() === 'POST' && new URL(response.url()).pathname.includes('/api/assets/candidates/') && new URL(response.url()).pathname.endsWith('/promote'), { timeout: 60000 }).catch((error) => ({ __wait_error: error }));
      await videoApprove.click();
      const videoPromotionResponse = await videoPromotion;
      if (videoPromotionResponse?.__wait_error) throw videoPromotionResponse.__wait_error;
      if (!videoPromotionResponse.ok()) throw new Error(`VIDEO candidate promotion failed for shot ${shotId}: HTTP ${videoPromotionResponse.status()} ${await videoPromotionResponse.text()}`);
      await page.getByText('已建立正式版本', { exact: true }).waitFor({ timeout: 120000 });
      const final = await waitForWorkspaceShot(page, disposableProjectId, shotId, (current) => current.IMAGE?.official?.current === true && current.VIDEO?.official?.current === true && current.VIDEO?.source_official_image?.version?.id === imageOfficialId);
      checks.push({ shot_id: String(shotId), prompt_ready: final.shot.IMAGE.prompt_ir.current === true && final.shot.VIDEO.prompt_ir.current === true, image_official: final.shot.IMAGE.official.current === true, video_official: final.shot.VIDEO.official.current === true, image_official_id: imageOfficialId, video_source_official_image_id: final.shot.VIDEO.source_official_image?.version?.id || null });
      await shot(`shot-${shotId}-official`);
    }
    evidence.shot_media_checks = checks;
    if (checks.length !== (evidence.materialized_shot_ids || []).length || checks.some((item) => !item.prompt_ready || !item.image_official || !item.video_official || item.image_official_id !== item.video_source_official_image_id)) throw new Error(`Not every materialized shot completed PromptIR → IMAGE Official → VIDEO Official with same-shot source: ${JSON.stringify(checks)}`);
  });
  await step('qa-and-delivery-export', async () => {
    if (REAL_IMAGE_STAGING) {
      evidence.video_status = 'REAL_PROVIDER_STAGING_IMAGE_GO_VIDEO_BLOCKED';
      evidence.delivery_readiness = { can_export: false, blocked_by: 'VIDEO_NOT_CONFIGURED', image_official_ready: true };
      return;
    }
    await clickIfVisible('button', 'QA 修复');
    await page.waitForFunction(() => !document.body.innerText.includes('正在加载工作区...') && !document.body.innerText.includes('正在同步项目数据'), null, { timeout: 60000 }).catch(() => {});
    const qaBody = await page.locator('body').innerText();
    if (/阻塞|待处理/.test(qaBody) && !/没有|已放行|通过/.test(qaBody)) throw new Error('QA still reports a delivery blocker.');
    await clickIfVisible('button', '导出中心');
    await page.getByText('交付 readiness', { exact: true }).waitFor({ timeout: 60000 });
    await page.getByText('可交付', { exact: true }).first().waitFor({ timeout: 60000 });
    const workspace = await readWorkspaceV2(page, disposableProjectId);
    const episodeShots = (workspace?.shots || []).filter((item) => Number(item?.identity?.episode) === 1);
    const adopted = (items) => Boolean(items?.official?.current);
    const references = episodeShots.reduce((sum, item) => sum + (item?.asset_readiness?.current ? 1 : 0), 0);
    const deliveryReadiness = {
      total_shots: episodeShots.length,
      prompt_ready_shots: episodeShots.filter((item) => Boolean(item.IMAGE?.prompt_ir?.current && item.VIDEO?.prompt_ir?.current)).length,
      image_ready_shots: episodeShots.filter((item) => adopted(item.IMAGE)).length,
      video_ready_shots: episodeShots.filter((item) => adopted(item.VIDEO)).length,
      referenced_asset_count: references,
    };
    deliveryReadiness.ready_shots = episodeShots.filter((item) => item.IMAGE?.prompt_ir?.current && item.VIDEO?.prompt_ir?.current && adopted(item.IMAGE) && adopted(item.VIDEO) && item.asset_readiness?.current).length;
    deliveryReadiness.can_export = deliveryReadiness.total_shots > 0 && deliveryReadiness.ready_shots === deliveryReadiness.total_shots && deliveryReadiness.prompt_ready_shots === deliveryReadiness.total_shots && deliveryReadiness.image_ready_shots === deliveryReadiness.total_shots && deliveryReadiness.video_ready_shots === deliveryReadiness.total_shots && deliveryReadiness.referenced_asset_count > 0;
    evidence.delivery_readiness = deliveryReadiness;
    if (!deliveryReadiness.can_export) throw new Error(`Delivery readiness contract failed before export: ${JSON.stringify(deliveryReadiness)}`);
    await page.getByText('更多交付格式、复制与历史刷新', { exact: true }).click().catch(() => {});
    const download = page.waitForEvent('download', { timeout: 60000 });
    await page.getByRole('button', { name: '导出 JSON 并登记', exact: true }).click();
    const file = await download;
    const suggested = file.suggestedFilename();
    const savePath = path.join(OUT, `${String(index).padStart(2, '0')}-${safeName(suggested || 'delivery.json')}`);
    await file.saveAs(savePath);
    if (!fs.statSync(savePath).size) throw new Error('Delivery export download was empty.');
    const exported = JSON.parse(fs.readFileSync(savePath, 'utf8'));
    const record = exported?.record || {};
    if (exported?.readiness?.canExport !== true || record.status !== 'completed' || Number(record.total_shots) !== deliveryReadiness.total_shots || Number(record.deliverable_shots) !== deliveryReadiness.total_shots || Number(record.pending_review_shots) !== 0 || Number(record.blocked_shots) !== 0 || String(record.meta_info?.version_label || record.metaInfo?.version_label || '').includes('阻塞')) throw new Error(`Formal delivery export is not complete: ${JSON.stringify({ readiness: exported?.readiness, record })}`);
    evidence.delivery_export = { path: savePath, readiness: exported.readiness, record };
    await page.getByText(/JSON 已导出，并登记交付记录。/, { exact: true }).waitFor({ timeout: 30000 }).catch(() => {});
    await shot('delivery-ready');
  });
  await step('delivery-read-only-contract-audit', async () => {
    const protectedBook = await page.evaluate(async () => {
      const response = await fetch('/api/books/990400/production-workspace-v2', { cache: 'no-store' });
      return { status: response.status, payload: await response.json().catch(() => null) };
    });
    evidence.protected_book_after = protectedBook;
    evidence.protected_book_990400_writes = mutations.filter((item) => item.path.includes('/990400')).length;
    if (evidence.protected_book_990400_writes !== 0) throw new Error('protected Book 990400 received a business mutation');
    if (disposableProjectId && process.env.E2E_KEEP_PROJECTS !== '1') {
      evidence.canonical_read_only = await page.evaluate(async (bookId) => {
        const response = await fetch(`/api/books/${bookId}/production-workspace-v2`, { cache: 'no-store' });
        return { status: response.status, payload: await response.json().catch(() => null) };
      }, disposableProjectId);
    }
  });
  await step('responsive-viewport-smoke', async () => {
    for (const viewport of [{ width: 1280, height: 900 }, { width: 1920, height: 1080 }]) {
      await page.setViewportSize(viewport);
      await page.reload();
      await page.waitForFunction(() => !document.body.innerText.includes('正在加载工作区...') && !document.body.innerText.includes('正在同步项目数据'), null, { timeout: 30000 }).catch(() => {});
      evidence.viewport_smoke.push({ ...viewport, restored_book_id: disposableProjectId, url: page.url() });
    }
    await page.setViewportSize({ width: 1440, height: 900 });
  });
  await step('return-and-dispose-project-through-ui', async () => {
    await clickIfVisible('button', '项目列表');
    if (disposableProjectId && process.env.E2E_KEEP_PROJECTS !== '1') {
      const card = page.locator(`[data-book-id="${disposableProjectId}"]`).first();
      await card.waitFor({ state: 'visible', timeout: 10000 }).catch(() => {});
      if (await card.count() && await card.isVisible().catch(() => false)) {
        const deleted = await clickAndWaitForResponse(page, card.locator('button[title="删除项目"]'), (response) => response.request().method() === 'DELETE' && new URL(response.url()).pathname === `/api/books/${disposableProjectId}`, 30000);
        const payload = await deleted.json().catch(() => ({}));
        evidence.delete_audit = { status: deleted.status(), payload, cleanup_mode: 'journey_delete_step' };
        if (!deleted.ok()) throw new Error(`delete project failed: HTTP ${deleted.status()}`);
        if (Number(payload?.orphan_rows || 0) !== 0 || Number(payload?.ambiguous_rows || 0) !== 0) throw new Error(`delete cleanup audit failed: ${JSON.stringify(payload)}`);
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
  const runIndexes = String(process.env.E2E_RUNS || '1,2').split(',').map((item) => Number(item.trim())).filter((item) => Number.isFinite(item) && item > 0);
  for (const index of runIndexes) runs.push(await runOnce(browser, index));
  await browser.close();
  let ledger = {};
  try { ledger = await (await fetch(`${process.env.E2E_API_URL || 'http://127.0.0.1:18768'}/api/e2e/mock-ledger`)).json(); } catch (error) { ledger = { error: String(error) }; }
  const failures = [];
  for (const run of runs) {
    if ((run.blockers || []).length) failures.push({ run: run.run, code: 'BLOCKERS_PRESENT', blockers: run.blockers });
    if ((run.steps || []).some((item) => item.status !== 'passed')) failures.push({ run: run.run, code: 'STEP_NOT_PASSED' });
    if (!REAL_IMAGE_STAGING && (!run.delivery_readiness?.can_export || !run.delivery_export?.record || run.delivery_export.record.status !== 'completed')) failures.push({ run: run.run, code: 'FORMAL_DELIVERY_NOT_READY', readiness: run.delivery_readiness });
    if (REAL_IMAGE_STAGING && REAL_IMAGE_SINGLE_CALL && (!run.real_image_staging?.final?.official_v1_version_id || run.real_image_staging?.final?.official_v1_current !== true || run.real_image_staging?.regenerate !== null)) failures.push({ run: run.run, code: 'REAL_IMAGE_INITIAL_OFFICIAL_NOT_PROVEN', real_image_staging: run.real_image_staging });
    if (REAL_IMAGE_STAGING && !REAL_IMAGE_SINGLE_CALL && (!run.real_image_staging?.final?.official_v2_version_id || !run.real_image_staging?.regenerate?.official_v1_current_during_review)) failures.push({ run: run.run, code: 'REAL_IMAGE_VERSION_LINEAGE_NOT_PROVEN', real_image_staging: run.real_image_staging });
    if (!run.delete_audit || Number(run.delete_audit.payload?.orphan_rows || 0) !== 0 || Number(run.delete_audit.payload?.ambiguous_rows || 0) !== 0) failures.push({ run: run.run, code: 'DELETE_AUDIT_FAILED', delete_audit: run.delete_audit });
    if (!REAL_IMAGE_STAGING && ((run.video_running_before_reload || []).some((item) => !item.execution_id || !item.provider_task_id) || (run.video_running_after_reload || []).some((item) => !item.same_execution || !item.same_provider_task))) failures.push({ run: run.run, code: 'VIDEO_RELOAD_NOT_PROVEN' });
  }
  if (!REAL_IMAGE_STAGING) {
    const videoSubmissionCounts = runs.flatMap((run) => (run.video_running_before_reload || []).map((item) => ({ run: run.run, shot_id: item.shot_id, count: (run.mutations || []).filter((mutation) => mutation.method === 'POST' && new RegExp(`/storyboard/1/${String(item.shot_id).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}/generate-video$`).test(mutation.path)).length })));
    for (const item of videoSubmissionCounts) if (item.count !== 1) failures.push({ ...item, code: 'VIDEO_DUPLICATE_OR_MISSING_SUBMISSION' });
  }
  const summary = { schema_version: REAL_IMAGE_STAGING ? (REAL_IMAGE_SINGLE_CALL ? 'production-ui-v3-real-provider-staging-image-single-call-v1' : 'production-ui-v3-real-provider-staging-image-first-v1') : 'production-ui-v3-browser-user-journey-delivery-readiness-reconcile-v1', generated_at: new Date().toISOString(), runs, ledger, failures, all_steps_passed: failures.length === 0, policy: { mutations_via_visible_ui_only: true, real_external_hosts_allowed: [], mock_runtime_only: !REAL_IMAGE_STAGING, real_provider: REAL_IMAGE_STAGING ? 'shapi-openai-images' : null, formal_delivery_gate: REAL_IMAGE_STAGING ? (REAL_IMAGE_SINGLE_CALL ? 'IMAGE v1 official; no regenerate; VIDEO frozen' : 'IMAGE v2 official with v1 current during regeneration; VIDEO blocked') : 'canExport=true and completed delivery record' } };
  await fs.promises.writeFile(path.join(OUT, 'summary.json'), JSON.stringify(summary, null, 2));
  console.log(JSON.stringify({ output: path.join(OUT, 'summary.json'), runs: runs.length, failures: failures.length, external_hosts: [...new Set(runs.flatMap(item => item.external_hosts))] }, null, 2));
  if (failures.length) process.exitCode = 1;
})().catch(error => { console.error(error); process.exitCode = 1; });
