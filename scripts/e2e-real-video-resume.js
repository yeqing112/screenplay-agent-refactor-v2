const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { reviewableRawCandidate, findWorkspaceShot } = require('./e2e-production-ui-v3-user-journey');

const BASE = process.env.E2E_BASE_URL || 'http://127.0.0.1:5176';
const API = process.env.E2E_API_URL || 'http://127.0.0.1:18768';
const BOOK_ID = Number(process.env.E2E_EXISTING_CANARY_BOOK_ID || 990454);
const SHOT_ID = String(process.env.E2E_CANARY_SHOT_ID || '1');
const PROFILE_ID = process.env.E2E_REAL_VIDEO_PROFILE_ID || 'local-video-7deneh';
const OUT = path.resolve(process.env.E2E_ARTIFACT_DIR || 'output/playwright/real-provider-final-slice-real-resume');
fs.mkdirSync(OUT, { recursive: true });

async function readShot(page) {
  const response = await page.request.get(`${API}/api/books/${BOOK_ID}/production-workspace-v2`, { headers: { 'Cache-Control': 'no-cache' } });
  const payload = await response.json();
  if (!response.ok()) throw new Error(`workspace read failed ${response.status()}`);
  const shot = findWorkspaceShot(payload, SHOT_ID);
  if (!shot) throw new Error(`shot ${SHOT_ID} missing`);
  return { payload, shot };
}

async function waitForShot(page, predicate, timeout = 240000) {
  const deadline = Date.now() + timeout;
  let latest = null;
  while (Date.now() < deadline) {
    latest = await readShot(page);
    if (predicate(latest.shot, latest.payload)) return latest;
    await page.waitForTimeout(500);
  }
  throw new Error(`timed out waiting for shot: ${JSON.stringify(latest?.shot)}`);
}

function identity(shot) {
  const e = shot?.VIDEO?.latest_execution || {};
  return { execution_id: e.id || null, provider_task_id: e.provider_task_id || null, provider_request_id: e.provider_request_id || null, state: String(e.state || '').toUpperCase() };
}

async function main() {
  const browser = await chromium.launch({ headless: process.env.E2E_HEADED !== '1' });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  page.on('dialog', (dialog) => dialog.accept());
  const evidence = { schema_version: 'production-ui-v3-real-provider-video-resume-v1', book_id: BOOK_ID, shot_id: SHOT_ID, profile_id: PROFILE_ID, mutations: [], external_hosts: [], screenshots: [], video_poll_states: [], browser_direct_provider_calls: 0 };
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method())) evidence.mutations.push({ method: request.method(), path: url.pathname, host: url.host });
    if (!['127.0.0.1:5176', '127.0.0.1:18768'].includes(url.host)) evidence.external_hosts.push(url.host);
  });
  const shot = async (name) => { const file = path.join(OUT, `01-${name}.png`); await page.screenshot({ path: file, fullPage: true }); evidence.screenshots.push(file); };
  await page.goto(`${BASE}/?book_id=${BOOK_ID}`);
  const formalWorkspace = page.getByRole('button', { name: '正式工作台', exact: true });
  if (await formalWorkspace.count()) { await formalWorkspace.click(); await page.waitForTimeout(800); }
  await page.getByRole('button', { name: '镜头工坊', exact: true }).waitFor({ state: 'visible', timeout: 60000 }).catch(() => {});
  await page.getByTestId(`shot-studio-shot-${SHOT_ID}`).click();
  const videoModel = page.getByLabel('VIDEO 生成模型', { exact: true });
  await videoModel.waitFor({ state: 'visible', timeout: 30000 });
  await page.waitForFunction((id) => Array.from(document.querySelectorAll('select[aria-label="VIDEO 生成模型"] option')).some((option) => option.value === id), PROFILE_ID, { timeout: 30000 });
  await videoModel.selectOption(PROFILE_ID);
  await page.waitForFunction((id) => document.querySelector('select[aria-label="VIDEO 生成模型"]')?.value === id, PROFILE_ID, { timeout: 30000 });
  await page.getByRole('button', { name: '视频', exact: true }).click();
  await shot('video-ready');
  const generate = page.getByTestId('shot-studio-generate-video');
  await generate.waitFor({ state: 'visible', timeout: 30000 });
  if (await generate.isDisabled()) throw new Error(`VIDEO generate disabled; selector=${await videoModel.inputValue()} body=${(await page.locator('body').innerText()).slice(0, 3000)}`);
  const initialResponse = page.waitForResponse((response) => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/generate-video'), { timeout: 180000 });
  await generate.click();
  const runningBefore = await waitForShot(page, (current) => {
    const item = identity(current);
    if (evidence.video_poll_states.length < 120) evidence.video_poll_states.push(item);
    return Boolean(item.execution_id && item.provider_task_id && ['RUNNING', 'IN_PROGRESS', 'PROVIDER_PENDING', 'PROVIDER_CALLED'].includes(item.state));
  });
  evidence.running_before_reload = { ...identity(runningBefore.shot), observed: true };
  await shot('video-running-before-reload');
  await page.reload();
  await page.waitForFunction(() => !document.body.innerText.includes('正在加载工作区') && !document.body.innerText.includes('正在同步项目数据'), null, { timeout: 60000 }).catch(() => {});
  const runningAfter = await waitForShot(page, (current) => {
    const item = identity(current);
    return item.execution_id === evidence.running_before_reload.execution_id && item.provider_task_id === evidence.running_before_reload.provider_task_id && ['RUNNING', 'IN_PROGRESS', 'PROVIDER_PENDING', 'PROVIDER_CALLED', 'SUCCEEDED'].includes(item.state);
  });
  evidence.running_after_reload = { ...identity(runningAfter.shot), same_execution: true, same_provider_task: true, same_provider_request: identity(runningAfter.shot).provider_request_id === evidence.running_before_reload.provider_request_id };
  await shot('video-running-after-reload');
  const initial = await initialResponse;
  if (!initial.ok()) throw new Error(`VIDEO initial failed HTTP ${initial.status()}: ${await initial.text()}`);
  const v1 = await waitForShot(page, (current) => reviewableRawCandidate(current.VIDEO).reviewable, 240000);
  const v1Review = reviewableRawCandidate(v1.shot.VIDEO);
  evidence.initial_execution = identity(v1.shot);
  evidence.candidate_v1 = { id: v1Review.candidateId, validation_status: v1Review.validationStatus, execution_id: v1Review.executionId };
  await page.getByRole('button', { name: '视频', exact: true }).click();
  const sync = page.getByRole('button', { name: '重新同步 Shot Studio', exact: true });
  if (await sync.count()) { await sync.click(); await page.waitForTimeout(500); await page.getByRole('button', { name: '视频', exact: true }).click(); }
  const approveV1 = page.getByTestId('shot-studio-review-desk').getByRole('button', { name: '批准并继续', exact: true });
  await approveV1.waitFor({ state: 'visible', timeout: 30000 });
  if (await approveV1.isDisabled()) throw new Error('VIDEO v1 approve disabled');
  await shot('video-review-v1');
  const promoteV1 = page.waitForResponse((response) => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/promote'), { timeout: 60000 });
  await approveV1.click();
  const promotedV1 = await promoteV1;
  if (!promotedV1.ok()) throw new Error(`VIDEO v1 promotion failed HTTP ${promotedV1.status()}`);
  const officialV1State = await waitForShot(page, (current) => current.VIDEO?.official?.current === true && current.VIDEO?.official?.version?.candidate_id === v1Review.candidateId);
  evidence.official_v1 = { id: officialV1State.shot.VIDEO.official.version.id, candidate_id: v1Review.candidateId, current: true };
  await shot('video-official-v1');
  await page.getByRole('button', { name: '视频', exact: true }).click();
  const regenerate = page.getByTestId('shot-studio-regenerate-video');
  await regenerate.waitFor({ state: 'visible', timeout: 30000 });
  if (await regenerate.isDisabled()) throw new Error('VIDEO regenerate disabled');
  const attempt = page.waitForResponse((response) => response.request().method() === 'POST' && new URL(response.url()).pathname.includes('/generation-attempts'), { timeout: 60000 });
  await regenerate.click();
  const attemptResponse = await attempt;
  if (!attemptResponse.ok()) throw new Error(`VIDEO regenerate attempt failed HTTP ${attemptResponse.status()}`);
  const regenerating = await waitForShot(page, (current) => current.VIDEO?.official?.current === true && current.VIDEO?.official?.version?.id === evidence.official_v1.id && identity(current).execution_id !== evidence.initial_execution.execution_id && ['RUNNING', 'IN_PROGRESS', 'PROVIDER_PENDING', 'PROVIDER_CALLED', 'SUCCEEDED'].includes(identity(current).state));
  evidence.regenerate_running = { ...identity(regenerating.shot), old_official_preserved: true };
  await shot('video-regenerate-running');
  const v2 = await waitForShot(page, (current) => current.VIDEO?.official?.current === true && current.VIDEO?.official?.version?.id === evidence.official_v1.id && reviewableRawCandidate(current.VIDEO).reviewable && identity(current).execution_id !== evidence.initial_execution.execution_id, 240000);
  const v2Review = reviewableRawCandidate(v2.shot.VIDEO);
  evidence.candidate_v2 = { id: v2Review.candidateId, validation_status: v2Review.validationStatus, execution_id: v2Review.executionId };
  await page.getByRole('button', { name: '视频', exact: true }).click();
  const syncV2 = page.getByRole('button', { name: '重新同步 Shot Studio', exact: true });
  if (await syncV2.count()) { await syncV2.click(); await page.waitForTimeout(500); await page.getByRole('button', { name: '视频', exact: true }).click(); }
  const approveV2 = page.getByTestId('shot-studio-review-desk').getByRole('button', { name: '批准并继续', exact: true });
  await approveV2.waitFor({ state: 'visible', timeout: 30000 });
  if (await approveV2.isDisabled()) throw new Error('VIDEO v2 approve disabled');
  await shot('video-review-v2');
  const promoteV2 = page.waitForResponse((response) => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/promote'), { timeout: 60000 });
  await approveV2.click();
  const promotedV2 = await promoteV2;
  if (!promotedV2.ok()) throw new Error(`VIDEO v2 promotion failed HTTP ${promotedV2.status()}`);
  const officialV2State = await waitForShot(page, (current) => current.VIDEO?.official?.current === true && current.VIDEO?.official?.version?.candidate_id === v2Review.candidateId && current.VIDEO?.official?.version?.id !== evidence.official_v1.id);
  evidence.official_v2 = { id: officialV2State.shot.VIDEO.official.version.id, candidate_id: v2Review.candidateId, current: true, v1_superseded: true };
  await shot('video-official-v2');
  evidence.real_provider_calls = (evidence.mutations || []).filter((item) => item.method === 'POST' && (item.path.endsWith('/generate-video') || item.path.includes('/generation-attempts'))).length;
  fs.writeFileSync(path.join(OUT, 'evidence.json'), JSON.stringify(evidence, null, 2));
  await context.close(); await browser.close();
  console.log(JSON.stringify({ output: path.join(OUT, 'evidence.json'), real_provider_calls: evidence.real_provider_calls, external_hosts: evidence.external_hosts }, null, 2));
}

main().catch(async (error) => { console.error(error); process.exitCode = 1; });
