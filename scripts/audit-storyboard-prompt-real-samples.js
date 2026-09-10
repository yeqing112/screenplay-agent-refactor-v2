const { spawn, spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const ROOT_DIR = process.cwd();
const ARGS = new Set(process.argv.slice(2));
const ZERO_ERROR_GATE = ARGS.has("--zero-error-gate");
const FULL_FIVE_PROJECTS = ZERO_ERROR_GATE || ARGS.has("--full-five-projects");
const API_URL = process.env.AUDIT_API_URL || process.env.E2E_API_URL || "http://127.0.0.1:8765";
const START_SERVER = process.env.AUDIT_START_SERVER !== "0";
const SAMPLE_BOOK_IDS = (process.env.AUDIT_STORYBOARD_BOOK_IDS || "14,5,75,3,1")
  .split(",")
  .map(value => Number(value.trim()))
  .filter(value => Number.isFinite(value) && value > 0);
const TARGET_SHOT_COUNT = Number(process.env.AUDIT_STORYBOARD_SHOT_COUNT || (FULL_FIVE_PROJECTS ? 200 : 50));
const STRICT_MODE = ZERO_ERROR_GATE || process.env.AUDIT_STORYBOARD_STRICT === "1";
const MIN_AUDITED_SHOTS = Number(process.env.AUDIT_STORYBOARD_MIN_AUDITED_SHOTS || (ZERO_ERROR_GATE ? 100 : 0));
const MIN_STATIC_LENGTH = Number(process.env.AUDIT_STORYBOARD_MIN_STATIC_LENGTH || 80);
const MIN_MOTION_LENGTH = Number(process.env.AUDIT_STORYBOARD_MIN_MOTION_LENGTH || 50);
const INTERNAL_REPAIR_MARKERS = [
  "真实项目灰度修复",
  "真实项目克隆",
  "deterministic",
  "E2E storyboard prompt mock",
];
const GENERIC_MOTION_MARKERS = [
  "按原分镜过程自然推进",
  "最后停在关键反应瞬间",
  "情绪逐步增强",
];

const processes = [];

function log(message) {
  console.log(`[storyboard-audit] ${message}`);
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

async function readJson(pathname) {
  const response = await fetch(`${API_URL}${pathname}`, { method: "GET" });
  const text = await response.text();
  let payload = {};
  try {
    payload = text ? JSON.parse(text) : {};
  } catch {
    payload = { raw: text };
  }
  if (!response.ok) {
    throw new Error(`${response.status} ${pathname}: ${JSON.stringify(payload).slice(0, 800)}`);
  }
  return payload;
}

function hasText(value) {
  return String(value || "").trim().length > 0;
}

function normalizeText(value) {
  return String(value || "").trim();
}

function sceneMatchText(value) {
  return normalizeText(value)
    .replace(/[·・•\s\t\n\r\-_\/\\—，。、；：:（）()]/g, "");
}

function sceneNameParts(value) {
  return normalizeText(value)
    .split(/[·・•\s\t\n\r\-_\/\\—，。、；：:（）()]+/g)
    .map(item => item.trim())
    .filter(item => item.length >= 2);
}

function staticPromptContainsSceneName(staticPrompt, sceneName) {
  const sceneText = normalizeText(sceneName);
  if (!sceneText) return true;
  if (staticPrompt.includes(sceneText)) return true;
  const normalizedScene = sceneMatchText(sceneText);
  const normalizedStatic = sceneMatchText(staticPrompt);
  if (normalizedScene.length > 0 && normalizedStatic.includes(normalizedScene)) return true;
  const parts = sceneNameParts(sceneText);
  return parts.length >= 2 && parts.every(part => normalizedStatic.includes(sceneMatchText(part)));
}

function hasMojibake(value) {
  const text = normalizeText(value);
  if (!text) return false;
  if (text.includes("�")) return true;
  const suspicious = [
    "鍥", "鐨", "瀵", "绋", "绔", "涓", "鏃", "姝", "宸", "寮", "犺",
    "����", "???", "Ã", "Â",
  ];
  return suspicious.some(token => text.includes(token));
}

function containsAny(text, terms) {
  return terms.some(term => text.includes(term));
}

function collectStructuredActionText(structured) {
  const beats = Array.isArray(structured?.action_beats) ? structured.action_beats : [];
  return beats
    .map(item => String(item?.description || ""))
    .filter(Boolean)
    .join(" ");
}

function isExpectedCharacterlessShot(shot, structured) {
  const text = [
    shot.scene_name,
    shot.camera_angle,
    shot.start_state,
    shot.action_process,
    shot.end_state,
    shot.dialogue,
    collectStructuredActionText(structured),
  ].map(value => String(value || "")).join(" ");
  const objectOrScreenFocusTerms = [
    "监控画面",
    "监控屏",
    "屏幕",
    "画面静止",
    "照片",
    "杯子印记",
    "水渍",
    "台面",
    "物件",
    "道具",
    "空镜",
    "空无一人",
    "无人物",
    "无人物形象",
    "只见手",
    "手从画面",
    "第一人称",
    "高空",
    "树冠",
    "泥地",
    "乱葬岗",
    "坟茔",
    "墓碑",
    "铜钟",
    "钟楼",
    "鳞片",
    "鱼鳞",
    "蛇鳞",
    "布条缝隙",
  ];
  const humanActionTerms = [
    "说",
    "低声",
    "看",
    "盯",
    "走",
    "坐",
    "站",
    "转身",
    "表情",
    "眼神",
    "身体",
  ];
  const hasObjectOrScreenFocus = containsAny(text, objectOrScreenFocusTerms);
  const dialogueText = String(shot.dialogue || "").trim();
  const hasDialogue = dialogueText
    && !containsAny(dialogueText, ["无台词", "无对白", "内心独白", "旁白", "风声", "环境声"]);
  const hasHumanAction = containsAny(String(shot.action_process || ""), humanActionTerms);
  return hasObjectOrScreenFocus && !hasDialogue && !hasHumanAction;
}

function collectRequiredAssets(shot) {
  const context = shot.prompt_compile_context || {};
  const contract = context.compile_prompt_contract || {};
  const required = [
    ...(Array.isArray(context.required_used_assets) ? context.required_used_assets : []),
    ...(Array.isArray(contract.required_used_assets) ? contract.required_used_assets : []),
  ];
  const seen = new Set();
  return required.filter(item => {
    if (!item || typeof item !== "object") return false;
    const key = `${item.asset_type || ""}:${item.asset_id || ""}:${item.asset_name || ""}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function collectBindings(shot) {
  const bindings = shot.prompt_compile_context?.asset_bindings || {};
  return [
    bindings.scene ? { ...bindings.scene, asset_type: "scene" } : null,
    ...((bindings.characters || []).map(item => ({ ...item, asset_type: "character" }))),
    ...((bindings.props || []).map(item => ({ ...item, asset_type: "prop" }))),
  ].filter(Boolean);
}

function assetKey(item) {
  return `${String(item?.asset_type || "").trim()}:${String(item?.asset_id || "").trim()}`;
}

function auditShot(book, shot) {
  const staticPrompt = normalizeText(shot.visual_prompt_static);
  const motionPrompt = normalizeText(shot.visual_prompt_motion);
  const combinedPrompt = `${staticPrompt}\n${motionPrompt}`;
  const requiredAssets = collectRequiredAssets(shot);
  const usedAssets = Array.isArray(shot.used_assets) ? shot.used_assets : [];
  const bindings = collectBindings(shot);
  const structured = shot.structured_shot || {};
  const referenceImages = Array.isArray(shot.reference_images) ? shot.reference_images : [];
  const issues = [];
  const warnings = [];

  function issue(code, message, severity = "error", details = {}) {
    (severity === "error" ? issues : warnings).push({ code, message, severity, details });
  }

  if (!staticPrompt) issue("missing_static_prompt", "缺少静态提示词。");
  if (!motionPrompt) issue("missing_motion_prompt", "缺少运动提示词。");
  if (staticPrompt && staticPrompt.length < MIN_STATIC_LENGTH) {
    issue("short_static_prompt", `静态提示词过短：${staticPrompt.length} 字符，低于 ${MIN_STATIC_LENGTH}。`);
  }
  if (motionPrompt && motionPrompt.length < MIN_MOTION_LENGTH) {
    issue("short_motion_prompt", `运动提示词过短：${motionPrompt.length} 字符，低于 ${MIN_MOTION_LENGTH}。`);
  }
  if (hasMojibake(staticPrompt) || hasMojibake(motionPrompt) || hasMojibake(shot.scene_name)) {
    issue("mojibake_text", "镜头场景名或提示词存在疑似乱码/坏编码。");
  }
  if (containsAny(staticPrompt, INTERNAL_REPAIR_MARKERS) || containsAny(motionPrompt, INTERNAL_REPAIR_MARKERS)) {
    issue("internal_repair_marker_in_prompt", "提示词含有内部修复/测试痕迹，不能作为生产交付提示词。");
  }
  if (containsAny(motionPrompt, GENERIC_MOTION_MARKERS)) {
    issue("generic_motion_prompt", "运动提示词仍是占位式泛化描述，未把导演分镜动作编译为具体机器语言。");
  }

  const motionTerms = ["镜头", "推进", "推近", "拉远", "横移", "跟拍", "摇镜", "切到", "环绕", "聚焦", "固定", "运动", "缓慢", "快速"];
  if (motionPrompt && !containsAny(motionPrompt, motionTerms)) {
    issue("weak_motion_language", "运动提示词缺少明确镜头运动或调度词。", "warning");
  }

  const visualTerms = ["光", "色", "景", "场", "构图", "质感", "近景", "远景", "特写", "环境", "背景", "镜头", "氛围"];
  if (staticPrompt && !containsAny(staticPrompt, visualTerms)) {
    issue("weak_static_visual_language", "静态提示词缺少视觉构图/光线/环境类描述。", "warning");
  }

  if (hasText(shot.scene_name) && !hasMojibake(shot.scene_name) && staticPrompt && !staticPromptContainsSceneName(staticPrompt, shot.scene_name)) {
    issue("scene_name_not_in_static_prompt", "静态提示词未显式包含镜头场景名。", "warning", { scene_name: shot.scene_name });
  }

  if (!structured.scene_asset_id) {
    issue("missing_structured_scene_asset", "structured_shot 缺少 scene_asset_id。");
  }
  if (
    (!Array.isArray(structured.character_asset_ids) || structured.character_asset_ids.length === 0)
    && !isExpectedCharacterlessShot(shot, structured)
  ) {
    issue("missing_structured_character_assets", "structured_shot 缺少 character_asset_ids。", "warning");
  }
  if (!Array.isArray(structured.action_beats) || structured.action_beats.length === 0) {
    issue("missing_action_beats", "structured_shot 缺少 action_beats，动作过程难以结构化追踪。", "warning");
  }

  const usedKeys = new Set(usedAssets.map(assetKey).filter(key => !key.endsWith(":")));
  const missingUsedAssets = requiredAssets.filter(item => !usedKeys.has(assetKey(item)));
  if (missingUsedAssets.length > 0) {
    issue("required_assets_missing_from_used_assets", "必须保留的关键资产未进入 used_assets。", "error", {
      missing: missingUsedAssets.map(item => ({
        asset_type: item.asset_type,
        asset_id: item.asset_id,
        asset_name: item.asset_name,
      })),
    });
  }

  const bindingKeys = new Set(bindings.map(assetKey).filter(key => !key.endsWith(":")));
  if (structured.scene_asset_id) {
    const sceneKey = `scene:${String(structured.scene_asset_id)}`;
    if (bindingKeys.size > 0 && !bindingKeys.has(sceneKey)) {
      issue("structured_scene_binding_mismatch", "structured_shot 的场景资产与 prompt_compile_context.asset_bindings 不一致。", "error", {
        structured_scene_asset_id: structured.scene_asset_id,
      });
    }
  }

  const criticalBindingsWithReference = bindings.filter(item => item.has_reference || item.locked_reference || item.reference_status === "selected" || item.reference_status === "locked");
  const referenceKeys = new Set(referenceImages.map(assetKey).filter(key => !key.endsWith(":")));
  const missingReferenceImages = criticalBindingsWithReference.filter(item => !referenceKeys.has(assetKey(item)));
  if (missingReferenceImages.length > 0) {
    issue("binding_reference_not_in_reference_images", "已绑定且有参考图的资产未进入 reference_images。", "warning", {
      missing: missingReferenceImages.map(item => ({
        asset_type: item.asset_type,
        asset_id: item.asset_id,
        asset_name: item.asset_name,
        reference_status: item.reference_status,
      })),
    });
  }

  const namedAssets = bindings
    .map(item => normalizeText(item.asset_name))
    .filter(name => name && !hasMojibake(name));
  const mentionedAssets = namedAssets.filter(name => combinedPrompt.includes(name));
  if (namedAssets.length > 0 && mentionedAssets.length === 0) {
    issue("bound_asset_names_not_mentioned", "提示词未显式提到任何已绑定资产名称。", "warning", {
      bound_assets: namedAssets.slice(0, 8),
    });
  }

  const compilerDiagnostics = shot.compiler_diagnostics || {};
  const blockingDiagnostics = Array.isArray(compilerDiagnostics.blocking_issues)
    ? compilerDiagnostics.blocking_issues
    : [];
  if (blockingDiagnostics.length > 0) {
    issue("compiler_blocking_issues_present", "后端编译诊断仍存在 blocking issues。", "error", {
      blocking_issues: blockingDiagnostics,
    });
  }
  // The audit must consume the exact diagnostics produced by the shared
  // compiler.  Otherwise this external sample gate can report a false green
  // while the product itself is warning about omitted authority facts,
  // continuity, or variant inheritance.  Keep the diagnostic key and details
  // intact so the report points back to the same corrective path as the UI.
  const compilerWarnings = Array.isArray(compilerDiagnostics.warnings)
    ? compilerDiagnostics.warnings.map(normalizeText).filter(Boolean)
    : [];
  for (const message of [...new Set(compilerWarnings)]) {
    issue("compiler_warning_present", message, "warning");
  }
  const failedCompilerChecks = Array.isArray(compilerDiagnostics.checks)
    ? compilerDiagnostics.checks.filter(item => item && item.passed === false)
    : [];
  for (const check of failedCompilerChecks) {
    const key = normalizeText(check.key) || "unknown";
    const message = normalizeText(check.message) || "编译诊断检查未通过。";
    issue(`compiler_check_failed:${key}`, message, "warning", {
      check_key: key,
      details: Array.isArray(check.details) ? check.details : [],
    });
  }

  return {
    book_id: book.id,
    book_title: book.title,
    episode: shot.episode,
    shot_id: shot.shot_id,
    scene_name: shot.scene_name,
    prompt_lengths: {
      static: staticPrompt.length,
      motion: motionPrompt.length,
    },
    counts: {
      required_assets: requiredAssets.length,
      used_assets: usedAssets.length,
      bindings: bindings.length,
      reference_images: referenceImages.length,
    },
    issues,
    warnings,
    snippets: {
      static: staticPrompt.slice(0, 160),
      motion: motionPrompt.slice(0, 160),
    },
  };
}

function pickEvenly(items, count) {
  if (items.length <= count) return items;
  const result = [];
  const used = new Set();
  for (let index = 0; index < count; index += 1) {
    const candidate = Math.round((index * (items.length - 1)) / Math.max(1, count - 1));
    if (!used.has(candidate)) {
      used.add(candidate);
      result.push(items[candidate]);
    }
  }
  for (let index = 0; result.length < count && index < items.length; index += 1) {
    if (!used.has(index)) result.push(items[index]);
  }
  return result;
}

async function collectAuditSamples() {
  const books = await readJson("/api/books");
  const byId = new Map(books.map(book => [Number(book.id), book]));
  const samples = SAMPLE_BOOK_IDS.map(id => byId.get(id)).filter(Boolean);
  if (samples.length === 0) {
    throw new Error(`No audit sample books found for: ${SAMPLE_BOOK_IDS.join(",")}`);
  }

  const outputs = [];
  for (const book of samples) {
    const payload = await readJson(`/api/pipeline/book/${book.id}/outputs`);
    const storyboard = Array.isArray(payload.storyboard) ? payload.storyboard : [];
    outputs.push({ book, storyboard });
    log(`#${book.id} ${book.title}: storyboard shots=${storyboard.length}`);
  }

  const perBookTarget = Math.max(1, Math.floor(TARGET_SHOT_COUNT / outputs.length));
  let selected = [];
  for (const item of outputs) {
    selected.push(...pickEvenly(item.storyboard, perBookTarget).map(shot => ({ book: item.book, shot })));
  }

  const remaining = outputs
    .flatMap(item => item.storyboard.map(shot => ({ book: item.book, shot })))
    .filter(candidate => !selected.some(item =>
      Number(item.book.id) === Number(candidate.book.id)
      && Number(item.shot.episode || 0) === Number(candidate.shot.episode || 0)
      && String(item.shot.shot_id) === String(candidate.shot.shot_id)
    ));

  for (const candidate of remaining) {
    if (selected.length >= TARGET_SHOT_COUNT) break;
    selected.push(candidate);
  }

  selected = selected.slice(0, TARGET_SHOT_COUNT);
  if (selected.length < TARGET_SHOT_COUNT) {
    log(`Only selected ${selected.length}/${TARGET_SHOT_COUNT} shots because sample projects do not contain enough storyboard rows.`);
  }
  return selected;
}

function summarize(results) {
  const issueCounts = new Map();
  const warningCounts = new Map();
  for (const result of results) {
    for (const issue of result.issues) {
      issueCounts.set(issue.code, (issueCounts.get(issue.code) || 0) + 1);
    }
    for (const warning of result.warnings) {
      warningCounts.set(warning.code, (warningCounts.get(warning.code) || 0) + 1);
    }
  }
  const byBook = {};
  for (const result of results) {
    const key = `${result.book_id}`;
    byBook[key] ||= { book_title: result.book_title, shots: 0, issues: 0, warnings: 0 };
    byBook[key].shots += 1;
    byBook[key].issues += result.issues.length;
    byBook[key].warnings += result.warnings.length;
  }
  return {
    audited_shots: results.length,
    shots_with_errors: results.filter(result => result.issues.length > 0).length,
    shots_with_warnings: results.filter(result => result.warnings.length > 0).length,
    total_errors: results.reduce((total, result) => total + result.issues.length, 0),
    total_warnings: results.reduce((total, result) => total + result.warnings.length, 0),
    issue_counts: Object.fromEntries([...issueCounts.entries()].sort((a, b) => b[1] - a[1])),
    warning_counts: Object.fromEntries([...warningCounts.entries()].sort((a, b) => b[1] - a[1])),
    by_book: byBook,
  };
}

function writeReport(report) {
  const artifactsDir = path.join(ROOT_DIR, "artifacts");
  fs.mkdirSync(artifactsDir, { recursive: true });
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const reportPath = path.join(artifactsDir, `storyboard-prompt-real-sample-audit-${stamp}.json`);
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2), "utf-8");
  return reportPath;
}

async function runAudit() {
  const selected = await collectAuditSamples();
  const results = selected.map(({ book, shot }) => auditShot(book, shot));
  const summary = summarize(results);
  const report = {
    generatedAt: new Date().toISOString(),
    apiUrl: API_URL,
    strict: STRICT_MODE,
    config: {
      sampleBookIds: SAMPLE_BOOK_IDS,
      targetShotCount: TARGET_SHOT_COUNT,
      minAuditedShots: MIN_AUDITED_SHOTS,
      minStaticLength: MIN_STATIC_LENGTH,
      minMotionLength: MIN_MOTION_LENGTH,
      zeroErrorGate: ZERO_ERROR_GATE,
    },
    summary,
    top_findings: results
      .filter(result => result.issues.length > 0 || result.warnings.length > 0)
      .slice(0, 12)
      .map(result => ({
        book_id: result.book_id,
        book_title: result.book_title,
        episode: result.episode,
        shot_id: result.shot_id,
        scene_name: result.scene_name,
        issues: result.issues.map(item => item.code),
        warnings: result.warnings.map(item => item.code),
      })),
    results,
  };
  const reportPath = writeReport(report);
  log(`Audited ${summary.audited_shots} shots. errors=${summary.total_errors}, warnings=${summary.total_warnings}`);
  log(`Report written: ${reportPath}`);
  log(`Issue counts: ${JSON.stringify(summary.issue_counts)}`);
  log(`Warning counts: ${JSON.stringify(summary.warning_counts)}`);

  if (MIN_AUDITED_SHOTS > 0 && summary.audited_shots < MIN_AUDITED_SHOTS) {
    throw new Error(
      `Storyboard prompt audit only covered ${summary.audited_shots} shots; expected at least ${MIN_AUDITED_SHOTS}.`
    );
  }
  // `--zero-error-gate` is the production safety gate: warnings are
  // reviewable quality debt, while errors are blockers.  The opt-in strict
  // environment mode intentionally remains warning-free for teams that want
  // that stronger policy.  Previously the zero-error gate also failed on
  // advisory warnings, making its name and operational meaning inconsistent.
  const gateFailed = ZERO_ERROR_GATE
    ? summary.total_errors > 0
    : STRICT_MODE && (summary.total_errors > 0 || summary.total_warnings > 0);
  if (gateFailed) {
    throw new Error(
      `Storyboard prompt audit failed with ${summary.total_errors} errors and ${summary.total_warnings} warnings.`
    );
  }
}

async function main() {
  if (START_SERVER) {
    log("Starting backend server...");
    spawnManaged("python", ["-m", "api.server"], { name: "api" });
  } else {
    log("Using already-running API server (AUDIT_START_SERVER=0).");
  }

  try {
    await waitForOk(`${API_URL}/health`);
    await runAudit();
  } finally {
    if (START_SERVER) {
      await stopManagedProcesses();
    }
  }
}

if (require.main === module) {
  main().catch(error => {
    console.error(error);
    process.exitCode = 1;
  });
}

module.exports = {
  auditShot,
  summarize,
};
