const { spawn, spawnSync } = require("child_process");
const path = require("path");
const { chromium } = require("playwright");

const ROOT_DIR = process.cwd();
const WEB_DIR = path.join(ROOT_DIR, "web");
const API_URL = process.env.E2E_API_URL || "http://127.0.0.1:8765";
const WEB_URL = process.env.E2E_WEB_URL || "http://127.0.0.1:5173";
const START_SERVERS = process.env.E2E_START_SERVERS !== "0";

const processes = [];

function log(message) {
  console.log(`[e2e-smoke] ${message}`);
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

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`GET ${url} failed: ${response.status}`);
  }
  return response.json();
}

function chooseProject(books) {
  const candidates = [...books].sort((a, b) => {
    const score = book => (
      (Number(book.scripts || 0) > 0 ? 100 : 0) +
      (Number(book.storyboard_shots || 0) > 0 ? 100 : 0) +
      Number(book.id || 0) / 1000
    );
    return score(b) - score(a);
  });
  const selected = candidates[0];
  if (!selected) {
    throw new Error("No project exists in the local database for smoke testing.");
  }
  return selected;
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

async function clickWorkspaceTab(page, tabName) {
  const tab = page.getByText(tabName, { exact: true }).first();
  if ((await tab.count()) === 0) {
    throw new Error(`Workspace tab not found: ${tabName}`);
  }
  await tab.click();
  await page.waitForTimeout(700);
  const body = await page.locator("body").innerText();
  if (!body.includes(tabName)) {
    throw new Error(`Workspace tab did not render expected text: ${tabName}`);
  }
  return body;
}

async function runBrowserSmoke() {
  const books = await fetchJson(`${API_URL}/api/books`);
  const project = chooseProject(books);
  log(`Using project #${project.id}: ${project.title}`);

  const browser = await chromium.launch({ headless: process.env.E2E_HEADLESS !== "0" });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const failures = [];
  const chapterDetailCalls = [];

  page.on("response", async response => {
    const url = response.url();
    if (url.includes("/favicon")) return;
    if (url.includes(`/api/books/${project.id}/chapters/`)) {
      chapterDetailCalls.push(url);
    }
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
    const homeText = await page.locator("body").innerText();
    if (!homeText.includes("全部项目") && !homeText.includes("项目列表")) {
      throw new Error("Home page did not render the project list.");
    }

    await clickProjectById(page, project.id);
    await page.waitForTimeout(1200);
    const workspaceText = await page.locator("body").innerText();
    if (!workspaceText.includes("正式产品工作区")) {
      throw new Error("Project workspace did not render.");
    }

    const tabs = [
      "内容准备",
      "人物质检",
      "剧本工作台",
      "镜头工作台",
      "资产中心",
      "QA 修复",
      "任务中心",
      "导出中心",
    ];
    for (const tab of tabs) {
      await clickWorkspaceTab(page, tab);
    }

    await clickWorkspaceTab(page, "内容准备");
    const chapters = await fetchJson(`${API_URL}/api/books/${project.id}/chapters`);
    const chapterToOpen = chapters[1] || chapters[0];
    if (chapterToOpen?.title) {
      const chapterButton = page.getByText(chapterToOpen.title, { exact: true }).first();
      if ((await chapterButton.count()) > 0) {
        await chapterButton.click();
        await page.waitForTimeout(700);
      }
    }

    await clickWorkspaceTab(page, "QA 修复");
    await page.waitForTimeout(700);

    if (failures.length) {
      throw new Error(`Browser smoke found failures:\n${failures.join("\n")}`);
    }

    log(`Visited workspace tabs for project #${project.id}.`);
    log(`Observed ${chapterDetailCalls.length} chapter detail request(s).`);
  } finally {
    await browser.close();
  }
}

async function main() {
  if (START_SERVERS) {
    log("Starting backend and frontend servers...");
    spawnManaged("python", ["-m", "api.server"], { name: "api" });
    spawnManaged("npx", ["vite", "--host", "127.0.0.1", "--port", "5173"], {
      cwd: WEB_DIR,
      name: "vite",
      env: { VITE_API_PROXY_TARGET: API_URL },
    });
  } else {
    log("Using already-running servers (E2E_START_SERVERS=0).");
  }

  try {
    await waitForOk(`${API_URL}/api/books`);
    await waitForOk(WEB_URL);
    await runBrowserSmoke();
    log("Smoke test passed.");
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
