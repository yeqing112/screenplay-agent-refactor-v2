const { spawn, spawnSync } = require("child_process");
const path = require("path");
const { chromium } = require("playwright");

const ROOT_DIR = process.cwd();
const WEB_DIR = path.join(ROOT_DIR, "web");
const API_URL = process.env.E2E_API_URL || "http://127.0.0.1:18765";
const WEB_URL = process.env.E2E_WEB_URL || "http://127.0.0.1:5175";
const START_SERVERS = process.env.E2E_START_SERVERS !== "0";
const FIXTURE_BOOK_ID = Number(process.env.E2E_QA_BOOK_ID || 999901);
const FIXTURE_EPISODE = 1;

const processes = [];

function log(message) {
  console.log(`[e2e-qa] ${message}`);
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

function runPython(code, env = {}) {
  const result = spawnSync("python", ["-c", code], {
    cwd: ROOT_DIR,
    env: { ...process.env, ...env },
    encoding: "utf-8",
  });
  if (result.status !== 0) {
    throw new Error(`Python command failed:\n${result.stdout}\n${result.stderr}`);
  }
  return result.stdout.trim();
}

function seedFixture() {
  const code = String.raw`
import json
import os
from models import Book, EpisodeOutline, QAResult, QAIssue, Script, ScriptVersion, Session, init_db

book_id = int(os.environ["E2E_QA_BOOK_ID"])
episode = int(os.environ["E2E_QA_EPISODE"])
original_script = "\n".join([
    "场1：夜，便利店内。",
    "林夏盯着监控屏，便利店门口的雨越下越大。",
    "她发现账册缺了一页，却没有任何证据能说服店长。",
    "店长沉默片刻，突然选择相信她。",
    "两人冲向后巷，门铃再次响起。",
])

init_db()
with Session() as session:
    session.query(ScriptVersion).filter(ScriptVersion.book_id == book_id).delete()
    session.query(QAIssue).filter(QAIssue.book_id == book_id).delete()
    session.query(QAResult).filter(QAResult.book_id == book_id).delete()
    session.query(EpisodeOutline).filter(EpisodeOutline.book_id == book_id).delete()
    session.query(Script).filter(Script.book_id == book_id).delete()
    session.query(Book).filter(Book.id == book_id).delete()
    session.add(Book(
        id=book_id,
        title="E2E QA Workbench Fixture",
        filename="e2e-qa-workbench.txt",
        chapter_count=1,
        total_words=len(original_script),
        status="scripted",
    ))
    session.add(EpisodeOutline(
        book_id=book_id,
        episode=episode,
        title="便利店雨夜",
        core_event="林夏发现账册缺页并争取店长信任。",
        opening_hook="雨夜监控出现异常。",
        core_conflict="证据不足导致信任跳跃。",
        climax="补充账册证据后信任成立。",
        ending_hook="门铃再次响起。",
        characters="林夏, 店长",
        scenes="便利店, 后巷",
    ))
    session.add(Script(
        book_id=book_id,
        episode=episode,
        content=original_script,
        word_count=len(original_script),
        status="draft",
    ))
    session.add(QAResult(
        book_id=book_id,
        episode=episode,
        result=json.dumps({
            "errors": [{
                "type": "logic_gap",
                "severity": "high",
                "title": "人物动机跳跃",
                "description": "店长突然选择相信林夏，缺少证据铺垫。",
                "location": {"script_section": "便利店信任转折", "line_range": [3, 4]},
                "suggestion": "增加林夏拿出账册残页或监控截图的动作，让信任转变成立。",
            }],
            "overall_score": 6,
            "suggestions": ["补强关键证据和情绪递进。"],
        }, ensure_ascii=False),
        error_count=1,
    ))
    session.commit()
print(book_id)
`;
  runPython(code, {
    E2E_QA_BOOK_ID: String(FIXTURE_BOOK_ID),
    E2E_QA_EPISODE: String(FIXTURE_EPISODE),
  });
}

function cleanupFixture() {
  const code = String.raw`
import os
from models import Book, EpisodeOutline, QAResult, QAIssue, Script, ScriptVersion, Session

book_id = int(os.environ["E2E_QA_BOOK_ID"])
with Session() as session:
    session.query(ScriptVersion).filter(ScriptVersion.book_id == book_id).delete()
    session.query(QAIssue).filter(QAIssue.book_id == book_id).delete()
    session.query(QAResult).filter(QAResult.book_id == book_id).delete()
    session.query(EpisodeOutline).filter(EpisodeOutline.book_id == book_id).delete()
    session.query(Script).filter(Script.book_id == book_id).delete()
    session.query(Book).filter(Book.id == book_id).delete()
    session.commit()
`;
  runPython(code, { E2E_QA_BOOK_ID: String(FIXTURE_BOOK_ID) });
}

async function clickProjectById(page, bookId) {
  const clicked = await page.evaluate(id => {
    const needle = `ID ${id}`;
    const nodes = Array.from(document.querySelectorAll("span, button, [role='button'], a, div"));
    const node = nodes.find(element => (element.textContent || "").trim() === needle)
      || nodes.find(element => (element.textContent || "").includes(needle));
    if (!node) return false;
    let clickable = node;
    while (clickable && clickable !== document.body) {
      const className = String(clickable.className || "");
      if (
        clickable.tagName === "BUTTON"
        || clickable.tagName === "A"
        || clickable.getAttribute("role") === "button"
        || clickable.onclick
        || className.includes("cursor-pointer")
      ) {
        break;
      }
      clickable = clickable.parentElement;
    }
    if (!clickable || clickable === document.body) return false;
    clickable.click();
    return true;
  }, bookId);
  if (!clicked) {
    throw new Error(`Could not find clickable project card for ID ${bookId}.`);
  }
}

async function runQaWorkbenchFlow() {
  const browser = await chromium.launch({ headless: process.env.E2E_HEADLESS !== "0" });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const failures = [];

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
      failures.push(`${response.status()} ${url} ${body}`);
    }
  });
  page.on("console", message => {
    if (["error", "warning"].includes(message.type())) {
      failures.push(`${message.type()}: ${message.text()}`);
    }
  });
  page.on("pageerror", error => {
    failures.push(`pageerror: ${error.message}`);
  });

  try {
    await page.goto(WEB_URL, { waitUntil: "networkidle" });
    await clickProjectById(page, FIXTURE_BOOK_ID);
    await page.waitForTimeout(1200);

    const qaTab = page.getByText("QA 修复", { exact: true }).first();
    if ((await qaTab.count()) === 0) {
      throw new Error("QA tab not found.");
    }
    await qaTab.click();
    await page.waitForTimeout(1200);

    const pageText = await page.locator("body").innerText();
    if (!pageText.includes("人物动机跳跃")) {
      throw new Error("QA issue did not render in the workbench.");
    }

    const flowResult = await page.evaluate(async ({ bookId, episode }) => {
      const readJson = async (url, options) => {
        const response = await fetch(url, options);
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(`${response.status} ${url}: ${JSON.stringify(payload)}`);
        }
        return payload;
      };

      await readJson(`/api/books/${bookId}/qa/episodes/${episode}/sync`, { method: "POST" });
      const workbench = await readJson(`/api/books/${bookId}/qa/workbench`);
      const issue = workbench.episodes?.[0]?.issues?.[0];
      if (!issue?.issue_id) {
        throw new Error("No QA issue found after sync.");
      }

      const patchedText = [
        "她发现账册缺了一页，立刻把夹在账册里的染血收据拍在柜台上。",
        "店长看见收据上的签名，沉默片刻，终于选择相信她。",
      ].join("\n");

      const preview = await readJson(`/api/books/${bookId}/qa/issues/${issue.issue_id}/preview-fix`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: "manual", option_id: "E2E", patched_text: patchedText }),
      });
      if (!preview.diff_text || !preview.diff_text.includes("染血收据")) {
        throw new Error("Preview diff did not include patched evidence.");
      }

      const apply = await readJson(`/api/books/${bookId}/qa/issues/${issue.issue_id}/apply-fix`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode: "manual",
          option_id: "E2E",
          patched_text: patchedText,
          change_reason: "E2E QA workbench repair",
          operator_name: "e2e",
          rerun_qa: false,
        }),
      });
      if (!apply.version?.id || !apply.diff_text.includes("染血收据")) {
        throw new Error("Apply fix did not create a usable script version.");
      }

      const rollback = await readJson(`/api/books/${bookId}/scripts/${episode}/versions/${apply.version.id}/rollback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ operator_name: "e2e", rerun_qa: false }),
      });
      if (rollback.version?.change_type !== "rollback") {
        throw new Error("Rollback did not create a rollback version.");
      }

      const finalWorkbench = await readJson(`/api/books/${bookId}/qa/workbench`);
      const versions = finalWorkbench.episodes?.[0]?.versions || [];
      return {
        issueId: issue.issue_id,
        appliedVersionId: apply.version.id,
        rollbackVersionId: rollback.version.id,
        versionCount: versions.length,
      };
    }, { bookId: FIXTURE_BOOK_ID, episode: FIXTURE_EPISODE });

    if (failures.length) {
      throw new Error(`Browser QA E2E found failures:\n${failures.join("\n")}`);
    }

    log(`QA issue ${flowResult.issueId} preview/apply/rollback passed.`);
    log(`Observed ${flowResult.versionCount} script version(s) after flow.`);
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
    log("Using already-running servers (E2E_START_SERVERS=0).");
  }

  try {
    await waitForOk(`${API_URL}/health`);
    await waitForOk(WEB_URL);
    seedFixture();
    log(`Seeded QA fixture project #${FIXTURE_BOOK_ID}.`);
    await runQaWorkbenchFlow();
    log("QA workbench E2E passed.");
  } finally {
    try {
      cleanupFixture();
      log(`Cleaned QA fixture project #${FIXTURE_BOOK_ID}.`);
    } finally {
      if (START_SERVERS) {
        await stopManagedProcesses();
      }
    }
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
