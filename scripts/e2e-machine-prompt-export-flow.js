const { spawn, spawnSync } = require("child_process");
const path = require("path");
const { chromium } = require("playwright");

const ROOT_DIR = process.cwd();
const WEB_DIR = path.join(ROOT_DIR, "web");
const API_URL = process.env.E2E_API_URL || "http://127.0.0.1:8765";
const WEB_URL = process.env.E2E_WEB_URL || "http://127.0.0.1:5173";
const START_SERVERS = process.env.E2E_START_SERVERS !== "0";
const BOOK_ID = Number(process.env.E2E_MACHINE_PROMPT_BOOK_ID || 75);
const BOOK_TITLE = process.env.E2E_MACHINE_PROMPT_BOOK_TITLE || "深夜便利店";
const EPISODE = Number(process.env.E2E_MACHINE_PROMPT_EPISODE || 1);
const SHOT_ID = Number(process.env.E2E_MACHINE_PROMPT_SHOT_ID || 1);

const processes = [];

function log(message) {
  console.log(`[e2e-machine-prompt] ${message}`);
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

async function waitForOk(url, timeoutMs = 45000) {
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

function runPython(code, env = {}) {
  const result = spawnSync("python", ["-c", code], {
    cwd: ROOT_DIR,
    env: { ...process.env, PYTHONIOENCODING: "utf-8", ...env },
    encoding: "utf-8",
  });
  if (result.status !== 0) {
    throw new Error(`Python command failed:\n${result.stdout}\n${result.stderr}`);
  }
  return result.stdout.trim();
}

function captureBaseline() {
  const code = String.raw`
import json
import os
from core import safe_json_loads
from models import ProductionExportRecord, Session, StoryboardShot, TaskRun, init_db

book_id = int(os.environ["BOOK_ID"])
episode = int(os.environ["EPISODE"])
shot_id = int(os.environ["SHOT_ID"])

init_db()
with Session() as session:
    shot = session.query(StoryboardShot).filter(
        StoryboardShot.book_id == book_id,
        StoryboardShot.episode == episode,
        StoryboardShot.shot_id == shot_id,
    ).first()
    if not shot:
        raise SystemExit(f"Storyboard shot not found: book={book_id} episode={episode} shot={shot_id}")
    meta = safe_json_loads(shot.meta_info) if shot.meta_info else {}
    if not isinstance(meta, dict):
        meta = {}
    record_ids = [
        row.id
        for row in session.query(ProductionExportRecord).filter(
            ProductionExportRecord.book_id == book_id,
        ).all()
        if isinstance((safe_json_loads(row.meta_info) if row.meta_info else {}), dict)
        and (safe_json_loads(row.meta_info) if row.meta_info else {}).get("record_type") == "storyboard_machine_prompt_export"
        and int((safe_json_loads(row.meta_info) if row.meta_info else {}).get("episode") or 0) == episode
        and str((safe_json_loads(row.meta_info) if row.meta_info else {}).get("shot_id") or "") == str(shot_id)
    ]
    task_ids = [
        row.task_id
        for row in session.query(TaskRun).filter(
            TaskRun.book_id == book_id,
            TaskRun.episode == episode,
            TaskRun.task_kind == "creative-machine_prompt_api_submission",
        ).all()
        if isinstance((safe_json_loads(row.payload) if row.payload else {}), dict)
        and str((safe_json_loads(row.payload) if row.payload else {}).get("shot_id") or "") == str(shot_id)
    ]
    print(json.dumps({
        "meta_info": meta,
        "record_ids": record_ids,
        "task_ids": task_ids,
        "scene_name": shot.scene_name,
    }, ensure_ascii=False))
`;
  return JSON.parse(runPython(code, {
    BOOK_ID: String(BOOK_ID),
    EPISODE: String(EPISODE),
    SHOT_ID: String(SHOT_ID),
  }));
}

function restoreBaseline(baseline) {
  const code = String.raw`
import json
import os
from core import safe_json_loads
from models import ProductionExportRecord, Session, StoryboardShot, TaskRun, init_db

book_id = int(os.environ["BOOK_ID"])
episode = int(os.environ["EPISODE"])
shot_id = int(os.environ["SHOT_ID"])
baseline_meta = json.loads(os.environ["BASELINE_META"])
baseline_record_ids = set(json.loads(os.environ["BASELINE_RECORD_IDS"]))
baseline_task_ids = set(json.loads(os.environ["BASELINE_TASK_IDS"]))

init_db()
removed = []
removed_task_ids = []
with Session() as session:
    shot = session.query(StoryboardShot).filter(
        StoryboardShot.book_id == book_id,
        StoryboardShot.episode == episode,
        StoryboardShot.shot_id == shot_id,
    ).first()
    if shot:
        shot.meta_info = json.dumps(baseline_meta, ensure_ascii=False)

    rows = session.query(ProductionExportRecord).filter(
        ProductionExportRecord.book_id == book_id,
    ).all()
    for row in rows:
        meta = safe_json_loads(row.meta_info) if row.meta_info else {}
        if not isinstance(meta, dict):
            continue
        if (
            meta.get("record_type") == "storyboard_machine_prompt_export"
            and int(meta.get("episode") or 0) == episode
            and str(meta.get("shot_id") or "") == str(shot_id)
            and row.id not in baseline_record_ids
        ):
            removed.append(row.id)
            session.delete(row)
    task_rows = session.query(TaskRun).filter(
        TaskRun.book_id == book_id,
        TaskRun.episode == episode,
        TaskRun.task_kind == "creative-machine_prompt_api_submission",
    ).all()
    for row in task_rows:
        payload = safe_json_loads(row.payload) if row.payload else {}
        if not isinstance(payload, dict):
            payload = {}
        if str(payload.get("shot_id") or "") == str(shot_id) and row.task_id not in baseline_task_ids:
            removed_task_ids.append(row.task_id)
            session.delete(row)
    session.commit()
print(json.dumps({"removed_record_ids": removed, "removed_task_ids": removed_task_ids}, ensure_ascii=False))
`;
  return JSON.parse(runPython(code, {
    BOOK_ID: String(BOOK_ID),
    EPISODE: String(EPISODE),
    SHOT_ID: String(SHOT_ID),
    BASELINE_META: JSON.stringify(baseline.meta_info),
    BASELINE_RECORD_IDS: JSON.stringify(baseline.record_ids),
    BASELINE_TASK_IDS: JSON.stringify(baseline.task_ids || []),
  }));
}

async function readJsonFromPage(page, pathname) {
  return await page.evaluate(async (path) => {
    const response = await fetch(path, { cache: "no-store" });
    if (!response.ok) throw new Error(`${path} -> HTTP ${response.status}`);
    return await response.json();
  }, pathname);
}

async function runFlow() {
  const browser = await chromium.launch({ headless: process.env.E2E_HEADLESS !== "0" });
  const context = await browser.newContext({ acceptDownloads: true });
  await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: WEB_URL });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", error => errors.push(`pageerror: ${error.message}`));
  page.on("console", msg => {
    if (msg.type() === "error") errors.push(`console.error: ${msg.text()}`);
  });

  try {
    await page.goto(WEB_URL, { waitUntil: "domcontentloaded" });
    await page.evaluate(({ bookId, title }) => {
      localStorage.setItem("screenplay-app-view-v1", JSON.stringify({
        page: "canvas",
        book: { id: bookId, title },
      }));
    }, { bookId: BOOK_ID, title: BOOK_TITLE });
    await page.reload({ waitUntil: "domcontentloaded" });

    await page.getByRole("button", { name: /^镜头工作台/ }).click();
    await page.getByText("机器提示词导出预览").waitFor({ state: "visible", timeout: 20000 });

    const shotButton = page.locator(`[data-episode="${EPISODE}"][data-shot-id="${SHOT_ID}"]`);
    if (await shotButton.count()) {
      await shotButton.first().click();
    }

    await page.getByRole("button", { name: "加载导出预览" }).click();
    await page.getByText("已生成机器提示词导出预览").waitFor({ state: "visible", timeout: 20000 });
    await page.getByText("真实提交 H3 前摘要").waitFor({ state: "visible", timeout: 10000 });
    await page.getByText("Base URL：https://metaso.cn/api/minimax").waitFor({ state: "visible", timeout: 10000 });
    await page.getByText("规格：768P / 5s / 16:9").waitFor({ state: "visible", timeout: 10000 });
    await page.getByText("更多机器语言与单字段复制").click();
    await page.getByText("MiniMax H3 / WebUI 导出").waitFor({ state: "visible", timeout: 10000 });

    const customDirectorText = [
      "场景：便利店收银台",
      `镜头：E2E-${Date.now()} 用户编辑导演分镜语言；林小夏听到门铃后先停顿，再把视线投向门口。`,
      "过程：保持收银台、冷白灯、人物服装和首帧连续，只改变可观察动作节奏。",
      "落点：她意识到异常来客已经进入。"
    ].join("\n");
    await page.locator("textarea[placeholder*='导演分镜']").fill(customDirectorText);
    await page.getByRole("button", { name: "保存并重编译导出" }).click();
    await page.getByText("已保存导演分镜语言，并重新编译机器提示词导出").waitFor({ state: "visible", timeout: 20000 });
    await page.getByText("用户编辑版").waitFor({ state: "visible", timeout: 10000 });

    const previewAfterEdit = await readJsonFromPage(page, `/api/books/${BOOK_ID}/storyboard/${EPISODE}/${SHOT_ID}/machine-prompt-export?target_model=minimax-h3`);
    if (previewAfterEdit.director_shot_text !== customDirectorText) {
      throw new Error("Director shot text override was not used by export preview.");
    }
    if (previewAfterEdit.api_submission !== false || previewAfterEdit.machine_prompt?.api_submission !== false) {
      throw new Error("Machine prompt preview unexpectedly allows API submission.");
    }

    await page.getByRole("button", { name: "复制 H3 全字段" }).click();
    await page.getByText("H3 全字段 已复制").waitFor({ state: "visible", timeout: 10000 });
    const clipboardText = await page.evaluate(async () => await navigator.clipboard.readText());
    if (!clipboardText.includes("API 提交：否，仅复制/导出") || !clipboardText.includes("integrated_multimodal_description")) {
      throw new Error("Clipboard text does not contain expected H3 WebUI export fields.");
    }

    const manualDraftText = `E2E-${Date.now()} 人工临时 H3 画面描述：林小夏在冷白灯下短暂停顿，视线越过收银台投向门口。`;
    await page.getByText("临时编辑最终 WebUI 草稿").click();
    await page.locator("textarea[placeholder*='最终 H3']").fill(manualDraftText);
    await page.getByRole("button", { name: "应用到临时草稿" }).click();
    await page.getByText("已应用临时导出草稿").waitFor({ state: "visible", timeout: 10000 });
    await page.getByText("人工临时修改").waitFor({ state: "visible", timeout: 10000 });
    await page.getByRole("button", { name: "复制 H3 全字段" }).first().click();
    const manualDraftClipboardText = await page.evaluate(async () => await navigator.clipboard.readText());
    if (!manualDraftClipboardText.includes(manualDraftText) || !manualDraftClipboardText.includes("API 提交：否，仅复制/导出")) {
      throw new Error("Manual temporary WebUI draft was not used by H3 copy.");
    }

    await page.getByText("更多导出").click();
    for (const [label, suffix] of [
      ["导出 Markdown", ".md"],
      ["导出 CSV", ".csv"],
      ["导出 API JSON", ".api-preview.json"],
    ]) {
      const [download] = await Promise.all([
        page.waitForEvent("download", { timeout: 10000 }),
        page.getByRole("button", { name: label }).click(),
      ]);
      const filename = download.suggestedFilename();
      if (!filename.endsWith(suffix)) {
        throw new Error(`${label} produced unexpected filename: ${filename}`);
      }
    }

    await page.getByRole("button", { name: "保存导出记录" }).click();
    await page.getByText("已登记导出记录").waitFor({ state: "visible", timeout: 20000 });
    await page.getByRole("button", { name: "刷新导出历史" }).click();
    await page.getByText(/已读取 \d+ 条当前镜头机器提示词导出记录/).waitFor({ state: "visible", timeout: 20000 });
    await page.getByText("当前镜头导出历史").click();
    await page.getByText("API 提交：否").waitFor({ state: "visible", timeout: 10000 });
    await page.getByRole("button", { name: "恢复为 WebUI 草稿" }).first().click();
    await page.getByText("已恢复历史快照").waitFor({ state: "visible", timeout: 10000 });
    await page.getByText("历史草稿 #").waitFor({ state: "visible", timeout: 10000 });
    await page.getByRole("button", { name: "复制 H3 全字段" }).click();
    const restoredClipboardText = await page.evaluate(async () => await navigator.clipboard.readText());
    if (!restoredClipboardText.includes("API 提交：否，仅复制/导出") || !restoredClipboardText.includes("integrated_multimodal_description")) {
      throw new Error("Restored WebUI draft did not provide a copy-ready H3 export.");
    }

    await page.getByText("高级").first().click();
    await page.getByRole("button", { name: "恢复系统版" }).click();
    await page.getByText("已恢复系统生成导演分镜语言").waitFor({ state: "visible", timeout: 20000 });
    await page.getByText("系统生成版").waitFor({ state: "visible", timeout: 10000 });

    const apiSubmitButton = page.getByRole("button", { name: "登记 API 提交任务" });
    if (!(await apiSubmitButton.isVisible().catch(() => false))) {
      await page.getByText("更多导出").click();
    }
    await apiSubmitButton.click();
    await page.getByText("已登记 API 提交任务").waitFor({ state: "visible", timeout: 20000 });
    const creativeTasks = await readJsonFromPage(page, `/api/books/${BOOK_ID}/creative-tasks?limit=30`);
    const machinePromptApiTask = (creativeTasks.tasks || []).find(task =>
      task.kind === "machine_prompt_api_submission" &&
      String(task.shot_id || "") === String(SHOT_ID)
    );
    if (!machinePromptApiTask) {
      throw new Error("Machine prompt API submission task was not listed in task center payload.");
    }
    if (machinePromptApiTask.actual_provider_submission !== false || machinePromptApiTask.external_status !== "waiting_for_generation_adapter") {
      throw new Error("Machine prompt API submission task crossed the provider-call safety boundary.");
    }

    if (errors.length) {
      throw new Error(`Browser collected errors:\n${errors.join("\n")}`);
    }

    log(`Machine prompt export browser flow passed for book #${BOOK_ID}, episode ${EPISODE}, shot ${SHOT_ID}.`);
  } finally {
    await browser.close();
  }
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
    log("Using already-running servers.");
  }

  const baseline = captureBaseline();
  log(`Captured baseline for book #${BOOK_ID}, scene "${baseline.scene_name}".`);
  try {
    await waitForOk(`${API_URL}/health`);
    await waitForOk(WEB_URL);
    await runFlow();
  } finally {
    const cleanup = restoreBaseline(baseline);
    log(`Restored baseline; removed records: ${cleanup.removed_record_ids.join(", ") || "none"}; removed API tasks: ${cleanup.removed_task_ids.join(", ") || "none"}.`);
    if (START_SERVERS) {
      await stopManagedProcesses();
    }
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
