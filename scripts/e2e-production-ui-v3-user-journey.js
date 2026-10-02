const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE = process.env.E2E_BASE_URL || 'http://127.0.0.1:5176';
const ALLOWED_HOSTS = new Set([new URL(BASE).host, new URL(process.env.E2E_API_URL || 'http://127.0.0.1:18768').host]);
const OUT = path.resolve(process.env.E2E_ARTIFACT_DIR || 'output/playwright/user-journey');
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

async function runOnce(browser, index) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  page.on('dialog', dialog => dialog.accept());
  const mutations = [];
  const externalHosts = [];
  const consoleErrors = [];
  let disposableProjectId = null;
  const disposableTitle = `V3 UI Journey Mock Run ${index} ${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
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
    const materializedShot = page.locator('[data-testid^="shot-studio-shot-"]').first();
    await materializedShot.waitFor({ state: 'visible', timeout: 120000 });
    await shot('storyboard-materialized');
  });
  await step('production-asset-bridge-through-ui', async () => {
    const v3Url = new URL(page.url());
    v3Url.searchParams.set('section', 'storyboard');
    v3Url.searchParams.set('ui_v3', 'shot-studio');
    await page.goto(v3Url.toString());
    await page.waitForFunction(() => !document.body.innerText.includes('正在加载工作区...') && !document.body.innerText.includes('正在同步项目数据'), null, { timeout: 30000 }).catch(() => {});
    const bridge = page.locator('[data-testid="production-asset-bridge"]');
    await bridge.waitFor({ state: 'visible', timeout: 60000 });
    const assetPath = path.join(OUT, `${String(index).padStart(2, '0')}-production-asset.png`);
    fs.writeFileSync(assetPath, Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64'));
    const uploadInput = bridge.locator('input[type="file"]').first();
    await uploadInput.waitFor({ state: 'visible', timeout: 30000 });
    await uploadInput.setInputFiles(assetPath);
    const approve = bridge.getByRole('button', { name: '批准并激活', exact: true }).first();
    await approve.waitFor({ state: 'visible', timeout: 30000 });
    await approve.click();
    const bind = bridge.getByRole('button', { name: /显式绑定到当前镜头|重新绑定当前版本/, exact: false });
    await bind.waitFor({ state: 'visible', timeout: 30000 });
    await bind.click();
    await bridge.waitFor({ state: 'detached', timeout: 60000 }).catch(() => {});
    await shot('production-assets-bound');
  });
  await step('prompt-ir-preparation-through-v3-ui', async () => {
    const imageModel = page.getByLabel('IMAGE 生成模型', { exact: true });
    const videoModel = page.getByLabel('VIDEO 生成模型', { exact: true });
    await imageModel.waitFor({ state: 'visible', timeout: 30000 });
    await videoModel.waitFor({ state: 'visible', timeout: 30000 });
    await imageModel.selectOption('builtin-mock-image');
    await videoModel.selectOption('builtin-mock-video');
    const prepareImage = page.getByRole('button', { name: '准备 IMAGE PromptIR', exact: true });
    await prepareImage.waitFor({ state: 'visible', timeout: 30000 });
    const prompt = await clickAndWaitForResponse(page, prepareImage, (response) => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/prompt-ir/compile'), 30000);
    if (!prompt.ok()) {
      let detail = '';
      try { detail = JSON.stringify(await prompt.json()); } catch { detail = await prompt.text().catch(() => ''); }
      throw new Error(`PromptIR compilation failed: HTTP ${prompt.status()} ${detail}`);
    }
    await page.getByRole('button', { name: '准备 IMAGE PromptIR', exact: true }).waitFor({ state: 'visible', timeout: 30000 });
    await shot('prompt-ir-prepared');
  });
  await step('image-generation-review-official', async () => {
    await page.getByRole('button', { name: '图片', exact: true }).click();
    const generate = page.getByRole('button', { name: '生成 IMAGE', exact: true });
    await generate.waitFor({ state: 'visible', timeout: 30000 });
    await generate.waitFor({ state: 'visible', timeout: 30000 });
    const generation = await clickAndWaitForResponse(page, generate, (response) => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/generate-frame'), 120000);
    if (!generation.ok()) throw new Error(`IMAGE generation failed: HTTP ${generation.status()} ${await generation.text()}`);
    await page.getByText('候选媒体审核', { exact: true }).waitFor({ timeout: 120000 }).catch(async (error) => {
      await shot('image-review-timeout');
      throw error;
    });
    await shot('image-review');
    const approve = page.getByRole('button', { name: '批准并继续', exact: true });
    await approve.waitFor({ state: 'visible', timeout: 30000 });
    await approve.click();
    await page.getByText('已建立正式版本', { exact: true }).waitFor({ timeout: 120000 });
    await shot('image-official');
  });
  await step('video-generation-review-official', async () => {
    const prepareVideo = page.getByRole('button', { name: '准备 VIDEO PromptIR', exact: true });
    const prompt = await clickAndWaitForResponse(page, prepareVideo, (response) => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/prompt-ir/compile'), 30000);
    if (!prompt.ok()) throw new Error(`VIDEO PromptIR compilation failed: HTTP ${prompt.status()} ${await prompt.text()}`);
    await page.getByRole('button', { name: '准备 VIDEO PromptIR', exact: true }).waitFor({ state: 'visible', timeout: 30000 });
    await page.getByRole('button', { name: '视频', exact: true }).click();
    const generate = page.getByRole('button', { name: '生成 VIDEO', exact: true });
    await generate.waitFor({ state: 'visible', timeout: 30000 });
    // VIDEO execution is intentionally asynchronous. Observe the submission
    // briefly, then let the durable projection and reload prove the running /
    // completed state instead of blocking the journey on a long response.
    const generationResponse = await clickAndObserveResponse(page, generate, (response) => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/generate-video'));
    // The canonical mock video adapter is asynchronous. Reload after the
    // submission has been accepted so the next state is recovered from the
    // durable Production Workspace projection.
    await page.waitForTimeout(250);
    await page.reload();
    await page.waitForFunction(() => !document.body.innerText.includes('正在加载工作区...') && !document.body.innerText.includes('正在同步项目数据'), null, { timeout: 60000 }).catch(() => {});
    await shot('video-reload-running');
    if (generationResponse && !generationResponse.ok()) throw new Error(`VIDEO generation failed: HTTP ${generationResponse.status()} ${await generationResponse.text()}`);
    await page.getByText('候选媒体审核', { exact: true }).waitFor({ timeout: 120000 });
    await shot('video-review');
    const approve = page.getByRole('button', { name: '批准并继续', exact: true });
    await approve.waitFor({ state: 'visible', timeout: 30000 });
    await approve.click();
    await page.getByText('已建立正式版本', { exact: true }).waitFor({ timeout: 120000 });
    await shot('video-official');
  });
  await step('qa-and-delivery-export', async () => {
    await clickIfVisible('button', 'QA 修复');
    await page.waitForFunction(() => !document.body.innerText.includes('正在加载工作区...') && !document.body.innerText.includes('正在同步项目数据'), null, { timeout: 60000 }).catch(() => {});
    const qaBody = await page.locator('body').innerText();
    if (/阻塞|待处理/.test(qaBody) && !/没有|已放行|通过/.test(qaBody)) throw new Error('QA still reports a delivery blocker.');
    await clickIfVisible('button', '导出中心');
    await page.getByText('交付 readiness', { exact: true }).waitFor({ timeout: 60000 });
    await page.getByText('更多交付格式、复制与历史刷新', { exact: true }).click().catch(() => {});
    const download = page.waitForEvent('download', { timeout: 60000 });
    await page.getByRole('button', { name: '导出 JSON 并登记', exact: true }).click();
    const file = await download;
    const suggested = file.suggestedFilename();
    const savePath = path.join(OUT, `${String(index).padStart(2, '0')}-${safeName(suggested || 'delivery.json')}`);
    await file.saveAs(savePath);
    if (!fs.statSync(savePath).size) throw new Error('Delivery export download was empty.');
    await page.getByText(/JSON 已导出，并登记交付记录。/, { exact: true }).waitFor({ timeout: 30000 }).catch(() => {});
    await shot('delivery-ready');
  });
  await step('asset-blocker-evidence', async () => {
    await clickIfVisible('button', '资产中心');
    await page.waitForFunction(() => !document.body.innerText.includes('正在加载工作区...') && !document.body.innerText.includes('正在同步项目数据'), null, { timeout: 30000 }).catch(() => {});
    await shot('asset-blocker');
    const body = await page.locator('body').innerText();
    if (!body.includes('缺少真实视觉资产') && !body.includes('当前没有 Production Asset')) throw new Error('asset blocker was not visible');
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
  const summary = { schema_version: 'production-ui-v3-browser-user-journey-mock-v1', generated_at: new Date().toISOString(), runs, ledger, policy: { mutations_via_visible_ui_only: true, real_external_hosts_allowed: [], mock_runtime_only: true } };
  await fs.promises.writeFile(path.join(OUT, 'summary.json'), JSON.stringify(summary, null, 2));
  console.log(JSON.stringify({ output: path.join(OUT, 'summary.json'), runs: runs.length, external_hosts: [...new Set(runs.flatMap(item => item.external_hosts))] }, null, 2));
})().catch(error => { console.error(error); process.exitCode = 1; });
