const { spawn, spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const ROOT_DIR = process.cwd();
const WEB_DIR = path.join(ROOT_DIR, "web");
const SAMPLE_REGISTRY_PATH = path.join(ROOT_DIR, "production-sample-registry.json");
let retiredSampleBookIds = new Set();
let activeSampleBookIds = new Set();
let hasActiveSampleRegistry = false;
try {
  const registry = JSON.parse(fs.readFileSync(SAMPLE_REGISTRY_PATH, "utf-8"));
  retiredSampleBookIds = new Set((registry.retired_book_ids || []).map(Number).filter(Number.isFinite));
  activeSampleBookIds = new Set((registry.active_book_ids || []).map(Number).filter(Number.isFinite));
  hasActiveSampleRegistry = activeSampleBookIds.size > 0;
} catch {
  // The registry is optional for cloned/embedded runners; absence must not
  // prevent the generic sample fallback from operating.
}
const API_URL = process.env.E2E_API_URL || "http://127.0.0.1:18765";
const WEB_URL = process.env.E2E_WEB_URL || "http://127.0.0.1:5175";
const START_SERVERS = process.env.E2E_START_SERVERS !== "0";
const DEFAULT_SAMPLE_BOOK_IDS = hasActiveSampleRegistry ? [...activeSampleBookIds] : [14, 5, 75, 3, 1];
const SAMPLE_BOOK_IDS = (process.env.E2E_REAL_SAMPLE_BOOK_IDS || DEFAULT_SAMPLE_BOOK_IDS.join(","))
  .split(",")
  .map(value => Number(value.trim()))
  .filter(value => Number.isFinite(value) && value > 0);
const MIN_SAMPLE_COUNT = Number(process.env.E2E_REAL_SAMPLE_MIN_COUNT || 5);
// Real-project databases are intentionally disposable in local development.
// Adapt to the samples that actually exist by default; CI/release jobs can
// opt back into the hard five-sample gate with E2E_REAL_SAMPLE_REQUIRE_MINIMUM=1.
const REQUIRE_SAMPLE_MINIMUM = process.env.E2E_REAL_SAMPLE_REQUIRE_MINIMUM === "1";
const STRICT_MODE = process.env.E2E_REAL_SAMPLE_STRICT !== "0";
const REQUIRED_FLOW = [
  "内容准备",
  "改编方向",
  "剧本工作台",
  "镜头工作台",
  "资产中心",
  "QA 修复",
  "导出中心",
];
const SUPPLEMENTAL_FLOW = ["创作画布", "任务中心", "模型管理"];
const SAFE_HTTP_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);
// The formal workspace refreshes proactive Agent updates on entry.  Reconcile
// is idempotent but persists notification rows, so a read-only browser
// regression must short-circuit it instead of counting it as a production
// mutation or leaking a blocked-request console error.
const READONLY_MOCK_POSTS = new Map([
  ["/api/agent/updates/reconcile", {
    updates: [],
    created_count: 0,
    reused_count: 0,
    summary: { status: "read_only_regression" },
    evidence_fingerprint: "read-only-regression",
    mutated: false,
  }],
]);

const processes = [];

function log(message) {
  console.log(`[e2e-real-samples] ${message}`);
}

function spawnManaged(command, args, options = {}) {
  const child = spawn(command, args, {
    cwd: options.cwd || ROOT_DIR,
    env: { ...process.env, ...(options.env || {}) },
    shell: process.platform === "win32",
    stdio: ["ignore", "pipe", "pipe"],
  });
  processes.push(child);
  child.stdout.on("data", data => {
    const text = data.toString().trim();
    if (text) log(`${options.name || command}: ${text}`);
  });
  child.stderr.on("data", data => {
    const text = data.toString().trim();
    if (text) log(`${options.name || command} stderr: ${text}`);
  });
  return child;
}

async function stopManagedProcesses() {
  for (const child of processes.reverse()) {
    if (child.killed) continue;
    if (process.platform === "win32") {
      spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
    } else {
      child.kill("SIGINT");
    }
  }
}

async function waitForOk(url, timeoutMs = 30000) {
  const started = Date.now();
  let lastError = "";
  while (Date.now() - started < timeoutMs) {
    try {
      const response = await fetch(url);
      if (response.ok) return response;
      lastError = `${response.status} ${response.statusText}`;
    } catch (error) {
      lastError = error.message;
    }
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  throw new Error(`Timed out waiting for ${url}: ${lastError}`);
}

async function readJson(url, options) {
  const target = url.startsWith("http") ? url : `${API_URL}${url}`;
  const response = await fetch(target, options);
  const text = await response.text();
  let payload = {};
  try {
    payload = text ? JSON.parse(text) : {};
  } catch {
    payload = { raw: text };
  }
  if (!response.ok) {
    throw new Error(`${response.status} ${target}: ${JSON.stringify(payload).slice(0, 800)}`);
  }
  return payload;
}

async function readJsonFromPage(page, url, options) {
  return page.evaluate(async ({ url, options }) => {
    const response = await fetch(url, options);
    const text = await response.text();
    let payload = {};
    try {
      payload = text ? JSON.parse(text) : {};
    } catch {
      payload = { raw: text };
    }
    if (!response.ok) {
      throw new Error(`${response.status} ${url}: ${JSON.stringify(payload).slice(0, 800)}`);
    }
    return payload;
  }, { url, options });
}

function summarizeOutputs(outputs) {
  const visual = outputs.visual || {};
  const assets = [
    ...(visual.makeups || []),
    ...(visual.locations || []),
    ...(visual.props || []),
  ];
  const firstShot = (outputs.storyboard || [])[0] || {};
  const firstScript = (outputs.scripts || [])[0] || {};
  return {
    bibleReady: Boolean(String(outputs.bible || "").trim()),
    productionSkillLocked: Boolean(outputs.production_skill?.locked_at),
    genres: outputs.genres || [],
    outlines: (outputs.outlines || []).length,
    scripts: (outputs.scripts || []).length,
    storyboardShots: (outputs.storyboard || []).length,
    qaResults: (outputs.qa || []).length,
    assets: assets.length,
    referenceAssets: assets.reduce((total, asset) => total + ((asset.reference_assets || []).length), 0),
    firstScriptEpisode: firstScript.episode || null,
    firstScriptSnippet: String(firstScript.content || "").slice(0, 80),
    firstShotEpisode: firstShot.episode || null,
    firstShotId: firstShot.shot_id || null,
    firstShotScene: firstShot.scene_name || "",
  };
}

async function collectSample(book) {
  const [chapters, outputs, qaWorkbench, exportRecords, adaptationState] = await Promise.all([
    readJson(`/api/books/${book.id}/chapters`).catch(error => ({ error: error.message })),
    readJson(`/api/pipeline/book/${book.id}/outputs`).catch(error => ({ error: error.message })),
    readJson(`/api/books/${book.id}/qa/workbench`).catch(error => ({ error: error.message })),
    readJson(`/api/books/${book.id}/export-records`).catch(error => ({ error: error.message })),
    readJson(`/api/books/${book.id}/adaptation-state`).catch(error => ({ error: error.message })),
  ]);
  const outputSummary = outputs.error ? { error: outputs.error } : summarizeOutputs(outputs);
  const qaEpisodes = Array.isArray(qaWorkbench.episodes) ? qaWorkbench.episodes : [];
  return {
    id: book.id,
    title: book.title,
    status: book.status,
    projectCard: {
      chapters: book.chapters,
      words: book.words,
      scripts: book.scripts,
      storyboardShots: book.storyboard_shots,
    },
    chapters: Array.isArray(chapters) ? chapters.length : 0,
    outputs: outputSummary,
    qaWorkbench: {
      episodes: qaEpisodes.length,
      issues: qaEpisodes.reduce((total, episode) => total + ((episode.issues || []).length), 0),
      versions: qaEpisodes.reduce((total, episode) => total + ((episode.versions || []).length), 0),
      error: qaWorkbench.error || null,
    },
    exportRecords: Array.isArray(exportRecords) ? exportRecords.length : 0,
    adaptation: {
      locked: Boolean(adaptationState.locked_at),
      selectedName: adaptationState.selected_name || "",
      error: adaptationState.error || null,
    },
    apiErrors: [chapters, outputs, qaWorkbench, exportRecords, adaptationState]
      .filter(payload => payload && payload.error)
      .map(payload => payload.error),
    browser: {
      modules: [],
      blockers: [],
      mutations: [],
      observations: [],
    },
  };
}

function sampleHasMainChainData(sample) {
  const hasContentSource =
    sample.chapters > 0
    || Number(sample.projectCard?.chapters || 0) > 0
    || Boolean(sample.outputs?.bibleReady);
  return (
    hasContentSource
    && Number(sample.outputs?.scripts || 0) > 0
    && Number(sample.outputs?.storyboardShots || 0) > 0
  );
}

async function chooseSamples() {
  const books = await readJson("/api/books");
  const byId = new Map(books.map(book => [Number(book.id), book]));
  const requested = SAMPLE_BOOK_IDS
    .filter(id => !retiredSampleBookIds.has(Number(id)))
    .map(id => byId.get(id))
    .filter(Boolean);
  const fallback = books
    .filter(book => !SAMPLE_BOOK_IDS.includes(Number(book.id)))
    .filter(book => !retiredSampleBookIds.has(Number(book.id)))
    .filter(book => !hasActiveSampleRegistry || activeSampleBookIds.has(Number(book.id)))
    .filter(book => Number(book.scripts || 0) > 0 && Number(book.storyboard_shots || 0) > 0)
    .sort((a, b) => Number(b.storyboard_shots || 0) - Number(a.storyboard_shots || 0));
  const picked = [...requested];
  for (const book of fallback) {
    if (picked.length >= MIN_SAMPLE_COUNT) break;
    picked.push(book);
  }
  if (picked.length === 0) {
    throw new Error("No eligible real samples found after applying the production sample registry.");
  }
  if (picked.length < MIN_SAMPLE_COUNT && REQUIRE_SAMPLE_MINIMUM) {
    throw new Error(`Only found ${picked.length} real samples, expected at least ${MIN_SAMPLE_COUNT}.`);
  }
  if (picked.length < MIN_SAMPLE_COUNT) {
    log(`Only found ${picked.length} real samples; continuing with available samples (hard minimum disabled).`);
  }
  return picked.slice(0, Math.max(Math.min(MIN_SAMPLE_COUNT, picked.length), requested.length));
}

async function assertBodyIncludes(page, expected, context) {
  const body = await page.locator("body").innerText();
  if (!body.includes(expected)) {
    throw new Error(`${context} did not include expected text: ${expected}`);
  }
  return body;
}

async function clickProjectById(page, bookId) {
  const card = page.locator(`[data-book-id="${bookId}"]`).first();
  if ((await card.count()) === 0) {
    throw new Error(`Could not find project card for ID ${bookId}.`);
  }
  await card.click();
}

async function clickWorkspaceTab(page, tabName) {
  const tab = page.locator("aside nav button").filter({ hasText: tabName }).first();
  if ((await tab.count()) === 0) {
    throw new Error(`Workspace tab not found: ${tabName}`);
  }
  const disabled = await tab.getAttribute("aria-disabled");
  if (disabled === "true") {
    const title = await tab.getAttribute("title");
    return {
      blocked: true,
      reason: title || "业务门禁阻止进入该模块",
      body: await page.locator("body").innerText(),
    };
  }
  await tab.click();
  await page.waitForTimeout(700);
  const body = await page.locator("body").innerText();
  if (!body.includes(tabName)) {
    throw new Error(`Workspace tab did not render expected text: ${tabName}`);
  }
  return { blocked: false, reason: null, body };
}

function collectModuleObservation(sample, tabName, body) {
  const observations = [];
  if (tabName === "内容准备") {
    if (sample.chapters > 0 && !body.includes("章节") && !body.includes("内容")) {
      observations.push("内容准备模块未明显展示章节/内容语义。");
    }
  }
  if (tabName === "剧本工作台" && Number(sample.outputs.scripts || 0) > 0) {
    if (!body.includes("剧本") && !body.includes("分集")) observations.push("剧本模块未明显展示剧本/分集语义。");
  }
  if (tabName === "镜头工作台" && Number(sample.outputs.storyboardShots || 0) > 0) {
    if (!body.includes("镜头")) observations.push("镜头模块未明显展示镜头语义。");
  }
  if (tabName === "资产中心" && Number(sample.outputs.assets || 0) > 0) {
    if (!body.includes("资产")) observations.push("资产中心未明显展示资产语义。");
  }
  if (tabName === "QA 修复" && (sample.qaWorkbench.issues > 0 || Number(sample.outputs.qaResults || 0) > 0)) {
    if (!body.includes("QA") && !body.includes("质检")) observations.push("QA 模块未明显展示 QA/质检语义。");
  }
  if (tabName === "导出中心") {
    if (!body.includes("导出") && !body.includes("交付")) observations.push("导出中心未明显展示导出/交付语义。");
  }
  return observations;
}

async function runBrowserSample(page, sample) {
  await page.goto(WEB_URL, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForLoadState("domcontentloaded");
  await page.waitForTimeout(800);
  await assertBodyIncludes(page, "全部项目", "Project home");
  await page.evaluate(bookId => {
    window.localStorage.removeItem(`product-workspace.navigation-state.${bookId}`);
  }, sample.id);
  await clickProjectById(page, sample.id);
  await page.waitForTimeout(1400);

  const workspaceText = await assertBodyIncludes(page, "正式产品工作台", `Project workspace #${sample.id}`);
  if (!workspaceText.includes("已接入真实项目数据") && !workspaceText.includes("正在同步项目数据")) {
    throw new Error(`Workspace #${sample.id} did not expose real project data state.`);
  }
  for (const legacyLabel of ["旧版生产", "创作沙盘", "高级编排", "产品原型 Demo"]) {
    if (workspaceText.includes(legacyLabel)) {
      throw new Error(`Legacy workspace entry is still visible in #${sample.id}: ${legacyLabel}`);
    }
  }

  const allTabs = [...REQUIRED_FLOW, ...SUPPLEMENTAL_FLOW];
  for (const tabName of allTabs) {
    const result = await clickWorkspaceTab(page, tabName);
    const moduleResult = {
      name: tabName,
      blocked: result.blocked,
      reason: result.reason,
      observations: result.blocked ? [] : collectModuleObservation(sample, tabName, result.body),
    };
    sample.browser.modules.push(moduleResult);
    if (result.blocked) {
      sample.browser.blockers.push({ module: tabName, reason: result.reason });
      continue;
    }
    sample.browser.observations.push(...moduleResult.observations.map(text => `${tabName}: ${text}`));
  }

  const outputsInBrowser = await readJsonFromPage(page, `/api/pipeline/book/${sample.id}/outputs`);
  const browserOutputSummary = summarizeOutputs(outputsInBrowser);
  if (browserOutputSummary.scripts !== sample.outputs.scripts) {
    throw new Error(`Browser/API script count mismatch for #${sample.id}: ${browserOutputSummary.scripts} vs ${sample.outputs.scripts}`);
  }
  if (browserOutputSummary.storyboardShots !== sample.outputs.storyboardShots) {
    throw new Error(`Browser/API storyboard count mismatch for #${sample.id}: ${browserOutputSummary.storyboardShots} vs ${sample.outputs.storyboardShots}`);
  }
}

function buildVerdict(samples, browserFailures) {
  const failures = [];
  const samplesWithMainChainData = samples.filter(sampleHasMainChainData);
  const expectedSampleCount = REQUIRE_SAMPLE_MINIMUM ? MIN_SAMPLE_COUNT : Math.min(MIN_SAMPLE_COUNT, samples.length);
  if (samplesWithMainChainData.length < expectedSampleCount) {
    failures.push(`Only ${samplesWithMainChainData.length}/${expectedSampleCount} samples have chapter + script + storyboard data.`);
  }
  for (const sample of samples) {
    if (sample.apiErrors.length) {
      failures.push(`#${sample.id} API errors: ${sample.apiErrors.join(" | ")}`);
    }
    if (sample.browser.mutations.length) {
      failures.push(`#${sample.id} attempted real-data mutations: ${sample.browser.mutations.join(" | ")}`);
    }
    const requiredBlockers = sample.browser.blockers.filter(item => REQUIRED_FLOW.includes(item.module));
    if (requiredBlockers.length) {
      failures.push(`#${sample.id} required modules blocked: ${requiredBlockers.map(item => `${item.module}(${item.reason})`).join(", ")}`);
    }
    if (!sampleHasMainChainData(sample)) {
      failures.push(`#${sample.id} lacks main-chain real data: chapters=${sample.chapters}, projectCardChapters=${sample.projectCard?.chapters || 0}, bibleReady=${sample.outputs?.bibleReady ? "yes" : "no"}, scripts=${sample.outputs?.scripts || 0}, shots=${sample.outputs?.storyboardShots || 0}`);
    }
  }
  failures.push(...browserFailures);
  return {
    passed: failures.length === 0,
    strict: STRICT_MODE,
    failures,
    summary: {
      sampleCount: samples.length,
      samplesWithMainChainData: samplesWithMainChainData.length,
      expectedSampleCount,
      hardMinimumEnforced: REQUIRE_SAMPLE_MINIMUM,
      requiredFlow: REQUIRED_FLOW,
      supplementalFlow: SUPPLEMENTAL_FLOW,
    },
  };
}

function writeReport(report) {
  const artifactsDir = path.join(ROOT_DIR, "artifacts");
  fs.mkdirSync(artifactsDir, { recursive: true });
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const reportPath = path.join(artifactsDir, `e2e-real-sample-regression-${stamp}.json`);
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2), "utf-8");
  return reportPath;
}

async function runRealSamples() {
  const pickedBooks = await chooseSamples();
  log(`Selected real samples: ${pickedBooks.map(book => `#${book.id}`).join(", ")}`);
  const samples = [];
  for (const book of pickedBooks) {
    const sample = await collectSample(book);
    samples.push(sample);
    log(
      `#${sample.id} ${sample.title}: chapters=${sample.chapters}/${sample.projectCard.chapters || 0}, scripts=${sample.outputs.scripts || 0}, shots=${sample.outputs.storyboardShots || 0}, qaIssues=${sample.qaWorkbench.issues}, assets=${sample.outputs.assets || 0}`,
    );
  }

  const browser = await chromium.launch({ headless: process.env.E2E_HEADLESS !== "0" });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } });
  const browserFailures = [];
  let activeSample = null;

  await page.addInitScript(() => {
    window.localStorage.removeItem("screenplay-app-view-v1");
    for (const key of Object.keys(window.localStorage)) {
      if (key.startsWith("product-workspace.navigation-state.")) {
        window.localStorage.removeItem(key);
      }
    }
  });

  await page.route("**/api/**", async route => {
    const request = route.request();
    const method = request.method().toUpperCase();
    if (method === "POST") {
      const pathname = new URL(request.url()).pathname;
      const mockPayload = READONLY_MOCK_POSTS.get(pathname);
      if (mockPayload) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(mockPayload),
        });
        return;
      }
    }
    if (!SAFE_HTTP_METHODS.has(method)) {
      const mutation = `${method} ${request.url()}`;
      if (activeSample) {
        activeSample.browser.mutations.push(mutation);
      }
      await route.abort("blockedbyclient");
      return;
    }
    await route.continue();
  });

  page.on("response", async response => {
    const url = response.url();
    if (url.includes("/favicon")) return;
    if (response.status() >= 400) {
      let body = "";
      try {
        body = (await response.text()).slice(0, 300);
      } catch {
        body = "";
      }
      browserFailures.push(`${response.status()} ${url} ${body}`);
    }
  });
  page.on("console", message => {
    if (message.type() === "error") {
      browserFailures.push(`console error: ${message.text()}`);
    }
  });
  page.on("pageerror", error => {
    browserFailures.push(`pageerror: ${error.message}`);
  });

  try {
    for (const sample of samples) {
      activeSample = sample;
      log(`Running browser regression for #${sample.id}...`);
      await runBrowserSample(page, sample);
      activeSample = null;
    }
  } finally {
    activeSample = null;
    await browser.close();
  }

  const verdict = buildVerdict(samples, browserFailures);
  const report = {
    generatedAt: new Date().toISOString(),
    apiUrl: API_URL,
    webUrl: WEB_URL,
    verdict,
    samples,
  };
  const reportPath = writeReport(report);
  log(`Report written: ${reportPath}`);

  for (const sample of samples) {
    const blocked = sample.browser.blockers.length
      ? ` blocked=${sample.browser.blockers.map(item => item.module).join("/")}`
      : " blocked=none";
    log(`#${sample.id} browser modules=${sample.browser.modules.length}${blocked}`);
  }

  if (!verdict.passed) {
    const message = `Real sample regression found issues:\n${verdict.failures.join("\n")}`;
    if (STRICT_MODE) throw new Error(message);
    log(message);
  }
  log("Formal workspace real sample regression passed.");
}

async function main() {
  if (START_SERVERS) {
    log("Starting backend and frontend servers...");
    spawnManaged("python", ["-m", "api.server"], { name: "api" });
    spawnManaged("npx", ["vite", "--host", "127.0.0.1", "--port", "5173", "--strictPort"], {
      cwd: WEB_DIR,
      name: "vite",
      env: { VITE_API_PROXY_TARGET: API_URL },
    });
  } else {
    log("Using already-running servers (E2E_START_SERVERS=0).");
  }

  try {
    await waitForOk(`${API_URL}/health`);
    await waitForOk(WEB_URL);
    await runRealSamples();
  } finally {
    if (START_SERVERS) {
      await stopManagedProcesses();
    }
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
