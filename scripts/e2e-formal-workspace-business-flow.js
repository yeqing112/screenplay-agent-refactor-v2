const { spawn, spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const ROOT_DIR = process.cwd();
const WEB_DIR = path.join(ROOT_DIR, "web");
const API_URL = process.env.E2E_API_URL || "http://127.0.0.1:8765";
const WEB_URL = process.env.E2E_WEB_URL || "http://127.0.0.1:5173";
const START_SERVERS = process.env.E2E_START_SERVERS !== "0";
const FIXTURE_BOOK_ID = Number(process.env.E2E_BUSINESS_BOOK_ID || 999902);
const FIXTURE_EPISODE = 1;
const FIXTURE_SHOT_ID = 1;
const FIXTURE_REPAIR_SHOT_ID = 2;

const processes = [];

function log(message) {
  console.log(`[e2e-business] ${message}`);
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

function cleanupFixture() {
  const code = String.raw`
import os
from pathlib import Path
from models import (
    Book, BookBible, Chapter, CharacterProfile, CharacterStage, EpisodeOutline, KV,
    ProductionExportRecord, QAResult, QAIssue, SceneCharacter, SceneProp, Script,
    ScriptVersion, Session, StoryboardAcceptanceRecord, StoryboardPromptVersion,
    StoryboardShot, TaskRun, VisualEraSpec, VisualLocation, VisualMakeup, VisualProp,
    VisualReferenceAsset, init_db,
)

book_id = int(os.environ["E2E_BUSINESS_BOOK_ID"])
init_db()
with Session() as session:
    for model in [
        ScriptVersion, QAIssue, QAResult, Script, EpisodeOutline, StoryboardAcceptanceRecord,
        StoryboardPromptVersion, StoryboardShot, VisualReferenceAsset, VisualMakeup,
        VisualProp, VisualLocation, VisualEraSpec, SceneCharacter, SceneProp,
        CharacterStage, CharacterProfile, ProductionExportRecord, TaskRun, Chapter,
        BookBible,
    ]:
        session.query(model).filter(model.book_id == book_id).delete()
    session.query(KV).filter(KV.key.in_([
        f"product_workspace:adaptation:{book_id}",
        f"production_skill_state:{book_id}",
    ])).delete(synchronize_session=False)
    session.query(Book).filter(Book.id == book_id).delete()
    session.commit()

decision_dir = Path("runs").parent / "script_decisions"
decision_path = decision_dir / f"book_{book_id}.json"
if decision_path.exists():
    decision_path.unlink()
`;
  runPython(code, { E2E_BUSINESS_BOOK_ID: String(FIXTURE_BOOK_ID) });
}

function seedFixture() {
  cleanupFixture();
  const code = String.raw`
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from models import (
    Book, BookBible, Chapter, CharacterProfile, EpisodeOutline, ProductionExportRecord,
    QAResult, Script, Session, StoryboardPromptVersion, StoryboardShot, TaskRun,
    VisualEraSpec, VisualLocation, VisualMakeup, VisualProp, VisualReferenceAsset,
    init_db, set_kv,
)

book_id = int(os.environ["E2E_BUSINESS_BOOK_ID"])
episode = int(os.environ["E2E_BUSINESS_EPISODE"])
shot_id = int(os.environ["E2E_BUSINESS_SHOT_ID"])
now = datetime.now(timezone.utc).isoformat()

original_script = "\n".join([
    "场1：夜，老茶馆内。",
    "林夏推门进来，雨水顺着外套滴在地板上。",
    "她发现账册缺了一页，却没有任何证据能说服店长。",
    "店长沉默片刻，突然选择相信她。",
    "两人冲向后巷，门铃再次响起。",
])

init_db()
with Session() as session:
    session.add(Book(
        id=book_id,
        title="E2E 正式工作台业务流项目",
        filename="e2e-formal-workspace-business-flow.txt",
        chapter_count=2,
        total_words=1680,
        status="storyboarded",
    ))
    session.add(BookBible(
        book_id=book_id,
        content="主角林夏在雨夜追查账册缺页，用关键证据赢得店长信任，并推进到后巷追踪。",
    ))
    session.add(Chapter(
        book_id=book_id,
        seq=1,
        title="雨夜账册",
        content="林夏在老茶馆发现账册缺页，意识到有人提前转移证据。",
        word_count=320,
        status="read",
        summary="林夏发现账册异常，关键证据缺失。",
        character_table=json.dumps([{"name": "林夏", "role": "调查者"}, {"name": "店长", "role": "协助者"}], ensure_ascii=False),
        events=json.dumps(["账册缺页", "店长信任动摇"], ensure_ascii=False),
        scenes=json.dumps(["老茶馆", "后巷"], ensure_ascii=False),
    ))
    session.add(Chapter(
        book_id=book_id,
        seq=2,
        title="后巷门铃",
        content="门铃在空巷里响起，林夏和店长确认有人正在引他们离开。",
        word_count=300,
        status="read",
        summary="林夏和店长进入后巷，新的线索出现。",
        character_table=json.dumps([{"name": "林夏", "role": "调查者"}], ensure_ascii=False),
        events=json.dumps(["后巷追踪", "门铃响起"], ensure_ascii=False),
        scenes=json.dumps(["后巷"], ensure_ascii=False),
    ))
    session.add(CharacterProfile(
        book_id=book_id,
        name="林夏",
        gender="女",
        age_range="26-30",
        role="主角",
        identity="调查记者",
        signature_outfit="深色雨衣，随身斜挎包",
        temperament="冷静、敏锐、行动果断",
        speech_style="短句、直接，压迫感强",
        visual_prompt_zh="年轻女性调查记者，深色雨衣，警觉眼神，现实主义短剧风格",
    ))
    session.add(EpisodeOutline(
        book_id=book_id,
        genre="short_drama",
        episode=episode,
        title="雨夜账册",
        core_event="林夏发现账册缺页并争取店长信任。",
        opening_hook="雨夜监控出现异常。",
        core_conflict="证据不足导致店长信任跳跃。",
        climax="林夏拿出被雨水打湿的收据，店长确认签名。",
        ending_hook="后巷门铃再次响起。",
        characters=json.dumps(["林夏", "店长"], ensure_ascii=False),
        scenes=json.dumps(["老茶馆", "后巷"], ensure_ascii=False),
        raw_content="雨夜账册：林夏必须用证据说服店长，否则后巷线索会消失。",
    ))
    session.add(Script(
        book_id=book_id,
        genre="short_drama",
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
                "title": "信任转折缺少证据",
                "description": "店长突然选择相信林夏，缺少可见证据支撑。",
                "location": {"script_section": "老茶馆信任转折", "line_range": [3, 4]},
                "suggestion": "补充林夏拿出收据或监控截图的动作，再让店长转变态度。",
            }],
            "overall_score": 6,
            "suggestions": ["补强关键证据。"],
        }, ensure_ascii=False),
        error_count=1,
    ))
    session.add(VisualEraSpec(
        book_id=book_id,
        timeline_start="现代都市",
        timeline_end="现代都市",
        clothing_spec="现实主义雨夜短剧服装",
        color_palette="冷蓝雨夜与暖黄茶馆灯光对比",
        architecture_spec="旧式街边茶馆，窄后巷",
        environment_spec="雨夜、湿地面、霓虹反光",
        prop_spec="旧账册、收据、门铃",
    ))
    location = VisualLocation(
        book_id=book_id,
        book_title="E2E 正式工作台业务流项目",
        name="老茶馆",
        category="interior",
        style="现实主义旧街茶馆",
        description="木质柜台、旧账册、暖黄吊灯，窗外暴雨。",
        visual_prompt_zh="老茶馆内景，木质柜台，旧账册，窗外暴雨，暖黄灯光",
        asset_status="ref_ready",
    )
    prop = VisualProp(
        book_id=book_id,
        book_title="E2E 正式工作台业务流项目",
        name="染水收据",
        category="evidence",
        description="被雨水打湿但仍能看清签名的关键收据。",
        visual_prompt_zh="一张被雨水打湿的收据，签名清晰可见",
        asset_status="ref_ready",
    )
    makeup = VisualMakeup(
        book_id=book_id,
        book_title="E2E 正式工作台业务流项目",
        episode=episode,
        character_name="林夏",
        stage_name="雨夜调查",
        refined_outfit="深色雨衣，内搭白衬衫，斜挎包",
        makeup_spec="轻微雨水痕迹，神情紧绷",
        hair_style="短发被雨水打湿",
        visual_prompt_zh="林夏，深色雨衣，短发湿润，警觉眼神",
        asset_status="ref_ready",
    )
    session.add(location)
    session.add(prop)
    session.add(makeup)
    session.flush()

    image_data_uri = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='320' height='180'%3E%3Crect width='320' height='180' fill='%230f172a'/%3E%3Ctext x='28' y='95' fill='%23bae6fd' font-size='22'%3EE2E Frame%3C/text%3E%3C/svg%3E"
    for asset_type, asset_id, asset_name, token in [
        ("scene", str(location.id), "老茶馆", "scene-ref-e2e"),
        ("prop", str(prop.id), "染水收据", "prop-ref-e2e"),
        ("character", str(makeup.id), "林夏", "char-ref-e2e"),
    ]:
        session.add(VisualReferenceAsset(
            book_id=book_id,
            episode=episode,
            asset_type=asset_type,
            asset_id=asset_id,
            asset_name=asset_name,
            image_url=image_data_uri,
            reference_token=token,
            status="selected",
            prompt=f"{asset_name} reference for E2E business flow",
        ))

    prompt_context = {
        "asset_bindings": {
            "scene": {
                "asset_id": str(location.id),
                "asset_name": "老茶馆",
                "reference_status": "selected",
                "reference_source": "selected",
                "scope_label": "主场景",
            },
            "characters": [{
                "asset_id": str(makeup.id),
                "asset_name": "林夏",
                "reference_status": "selected",
                "reference_source": "selected",
                "scope_label": "雨夜调查",
            }],
            "props": [{
                "asset_id": str(prop.id),
                "asset_name": "染水收据",
                "reference_status": "selected",
                "reference_source": "selected",
                "scope_label": "关键证据",
            }],
        },
        "acceptance_feedback": {},
    }
    shot_meta = {
        "structured_shot": {
            "scene_asset_id": str(location.id),
            "character_asset_ids": [str(makeup.id)],
            "prop_asset_ids": [str(prop.id)],
            "style_key": "cinematic-default",
            "character_blocking": [{
                "character_id": str(makeup.id),
                "screen_position": "left",
                "pose": "standing",
                "status": "active",
                "emotion": "tense",
                "visual_alias": "林夏",
            }],
            "action_beats": [{
                "sequence": 1,
                "subject_type": "character",
                "subject_id": str(makeup.id),
                "time_slice": "0-3s",
                "description": "林夏把收据压在账册上，逼店长确认签名。",
                "emotion": "urgent",
                "intensity": "high",
            }],
        },
        "prompt_compiler": {
            "latest_version": 1,
            "locked": False,
            "locked_version": None,
            "negative_prompt": "字幕, 水印, 变形手指",
            "prompt_compile_context": prompt_context,
            "used_assets": [
                {"asset_type": "scene", "asset_id": str(location.id), "asset_name": "老茶馆", "reference_status": "selected"},
                {"asset_type": "character", "asset_id": str(makeup.id), "asset_name": "林夏", "reference_status": "selected"},
                {"asset_type": "prop", "asset_id": str(prop.id), "asset_name": "染水收据", "reference_status": "selected"},
            ],
            "reference_images": [
                {"asset_type": "scene", "asset_id": str(location.id), "asset_name": "老茶馆", "reference_token": "scene-ref-e2e", "reference_status": "selected", "image_url": image_data_uri},
                {"asset_type": "character", "asset_id": str(makeup.id), "asset_name": "林夏", "reference_token": "char-ref-e2e", "reference_status": "selected", "image_url": image_data_uri},
                {"asset_type": "prop", "asset_id": str(prop.id), "asset_name": "染水收据", "reference_token": "prop-ref-e2e", "reference_status": "selected", "image_url": image_data_uri},
            ],
            "reference_asset_ids": [str(location.id), str(makeup.id), str(prop.id)],
            "locked_reference_summary": {"summary_text": "老茶馆、林夏、染水收据均已有参考图。"},
            "compiler_warnings": [],
            "compiler_diagnostics": {"score": 92},
        },
    }
    session.add(StoryboardShot(
        book_id=book_id,
        episode=episode,
        scene_name="老茶馆",
        shot_id=shot_id,
        dialogue="林夏：这张收据上的签名，和账册缺页处完全一致。",
        duration=5,
        camera_angle="CU",
        camera_movement="push-in",
        transition="cut",
        lighting="窗外冷蓝雨光与室内暖黄灯光交错",
        start_state="店长怀疑林夏，账册摊在柜台上。",
        action_process="林夏把染水收据压在账册缺页位置，店长看见签名后动摇。",
        end_state="店长点头，跟林夏冲向后巷。",
        visual_prompt_static="老茶馆柜台前，林夏把染水收据压在旧账册上，店长震惊看向签名。",
        visual_prompt_motion="镜头缓慢推进到收据签名，随后切到店长表情变化，最后林夏转身冲向后巷。",
        visual_prompt_final="字幕, 水印, 变形手指",
        asset_links=json.dumps({
            "images": [{"id": "frame-e2e-1", "url": image_data_uri, "title": "老茶馆证据首帧", "status": "adopted"}],
            "videos": [{"id": "video-e2e-1", "url": image_data_uri, "title": "老茶馆证据视频", "status": "adopted"}],
        }, ensure_ascii=False),
        asset_status="done",
        meta_info=json.dumps(shot_meta, ensure_ascii=False),
    ))
    session.add(StoryboardPromptVersion(
        book_id=book_id,
        episode=episode,
        shot_id=shot_id,
        version=1,
        compile_reason="fixture-baseline",
        prompt_static="老茶馆柜台前，林夏把染水收据压在旧账册上，店长震惊看向签名。",
        prompt_motion="镜头缓慢推进到收据签名，随后切到店长表情变化，最后林夏转身冲向后巷。",
        negative_prompt="字幕, 水印, 变形手指",
        meta_info=json.dumps({"prompt_compile_context": prompt_context, "compiler_diagnostics": {"score": 92}}, ensure_ascii=False),
    ))

    degraded_structured = {
        "scene_asset_id": "",
        "character_asset_ids": [str(makeup.id)],
        "prop_asset_ids": [str(prop.id)],
        "style_key": "cinematic-default",
        "character_blocking": [],
        "action_beats": [],
    }
    degraded_meta = {
        "structured_shot": degraded_structured,
        "prompt_compiler": {
            "latest_version": 1,
            "locked": False,
            "locked_version": None,
            "negative_prompt": "字幕, 水印, 变形手指",
            "prompt_compile_context": {},
            "used_assets": [],
            "reference_images": [],
            "reference_asset_ids": [],
            "compiler_warnings": ["E2E fixture starts with a degraded prompt."],
            "compiler_diagnostics": {
                "status": "warning",
                "checks": [
                    {"key": "static_prompt_quality", "passed": False, "message": "静态提示词过短"},
                    {"key": "motion_prompt_quality", "passed": False, "message": "运动提示词过短"},
                ],
            },
        },
    }
    session.add(StoryboardShot(
        book_id=book_id,
        episode=episode,
        scene_name="老茶馆",
        shot_id=2,
        dialogue="店长：你确定有人动过账册？",
        duration=4,
        camera_angle="MS",
        camera_movement="push-in",
        transition="cut",
        lighting="窗外冷蓝雨光与室内暖黄灯光交错",
        start_state="林夏站在柜台前，店长仍在犹豫。",
        action_process="林夏指向收据边角，店长低头核对账册缺页。",
        end_state="店长终于意识到账册被人动过。",
        visual_prompt_static="老茶馆里，林夏和店长对视。",
        visual_prompt_motion="镜头推进。",
        visual_prompt_final="字幕, 水印, 变形手指",
        asset_links=json.dumps({
            "images": [{"id": "frame-e2e-repair", "url": image_data_uri, "title": "降级镜头首帧", "status": "adopted"}],
            "videos": [{"id": "video-e2e-repair", "url": image_data_uri, "title": "降级镜头视频", "status": "adopted"}],
        }, ensure_ascii=False),
        asset_status="needs_prompt_repair",
        meta_info=json.dumps(degraded_meta, ensure_ascii=False),
    ))
    session.add(StoryboardPromptVersion(
        book_id=book_id,
        episode=episode,
        shot_id=2,
        version=1,
        compile_reason="fixture-degraded-baseline",
        prompt_static="老茶馆里，林夏和店长对视。",
        prompt_motion="镜头推进。",
        negative_prompt="字幕, 水印, 变形手指",
        meta_info=json.dumps({
            "structured_shot": degraded_structured,
            "prompt_compile_context": {},
            "compiler_diagnostics": degraded_meta["prompt_compiler"]["compiler_diagnostics"],
        }, ensure_ascii=False),
    ))
    session.add(ProductionExportRecord(
        book_id=book_id,
        export_format="json",
        status="blocked",
        total_shots=1,
        deliverable_shots=0,
        pending_review_shots=1,
        blocked_shots=1,
        summary="E2E fixture: QA issue still needs repair before final delivery.",
        meta_info=json.dumps({"episode": episode, "blocked_reasons": ["QA issue open"]}, ensure_ascii=False),
    ))
    session.add(TaskRun(
        task_id=f"e2e-business-{book_id}",
        task_kind="creative-image",
        status="done",
        progress=100,
        book_id=book_id,
        episode=episode,
        payload=json.dumps({"shot_id": str(shot_id), "kind": "image", "result_url": image_data_uri}, ensure_ascii=False),
    ))
    session.commit()

set_kv(f"product_workspace:adaptation:{book_id}", json.dumps({
    "book_id": book_id,
    "selected_id": "e2e-main-direction",
    "selected_name": "雨夜悬疑短剧",
    "custom_note": "E2E fixture adaptation direction.",
    "locked_at": None,
    "created_at": now,
    "updated_at": now,
}, ensure_ascii=False))

decision_dir = Path("script_decisions")
decision_dir.mkdir(parents=True, exist_ok=True)
(decision_dir / f"book_{book_id}.json").write_text(json.dumps({
    "book_id": book_id,
    "episodes": {
        str(episode): {
            "locked_at": now,
            "released_at": now,
            "note": "E2E fixture releases episode to storyboard before browser load.",
            "created_at": now,
            "updated_at": now,
        }
    }
}, ensure_ascii=False, indent=2), encoding="utf-8")
print(book_id)
`;
  runPython(code, {
    E2E_BUSINESS_BOOK_ID: String(FIXTURE_BOOK_ID),
    E2E_BUSINESS_EPISODE: String(FIXTURE_EPISODE),
    E2E_BUSINESS_SHOT_ID: String(FIXTURE_SHOT_ID),
  });
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
      throw new Error(`${response.status} ${url}: ${JSON.stringify(payload).slice(0, 600)}`);
    }
    return payload;
  }, { url, options });
}

async function clickProjectById(page, bookId) {
  const card = page.locator(`[data-book-id="${bookId}"]`).first();
  if ((await card.count()) === 0) {
    throw new Error(`Could not find project card for ID ${bookId}.`);
  }
  await card.click();
}

async function clickWorkspaceTab(page, tabName) {
  const tab = page.getByText(tabName, { exact: true }).first();
  if ((await tab.count()) === 0) {
    throw new Error(`Workspace tab not found: ${tabName}`);
  }
  await tab.click();
  await page.waitForTimeout(500);
  const body = await page.locator("body").innerText();
  if (!body.includes(tabName)) {
    throw new Error(`Workspace tab did not render expected text: ${tabName}`);
  }
  return body;
}

async function assertBodyIncludes(page, expected, context) {
  const body = await page.locator("body").innerText();
  if (!body.includes(expected)) {
    throw new Error(`${context} did not include expected text: ${expected}`);
  }
  return body;
}

async function waitForPromptCompileTask(page, taskId, timeoutMs = 60000) {
  const started = Date.now();
  let lastPayload = null;
  while (Date.now() - started < timeoutMs) {
    const payload = await readJsonFromPage(page, `/api/storyboard-prompt-compile-tasks/${taskId}`);
    lastPayload = payload;
    if (payload.status === "done") return payload;
    if (payload.status === "error") {
      throw new Error(`Prompt compile task failed: ${JSON.stringify(payload)}`);
    }
    await page.waitForTimeout(1000);
  }
  throw new Error(`Timed out waiting for prompt compile task ${taskId}: ${JSON.stringify(lastPayload)}`);
}

async function runBusinessFlow() {
  const browser = await chromium.launch({ headless: process.env.E2E_HEADLESS !== "0" });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } });
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
    await assertBodyIncludes(page, "全部项目", "Project home");
    await clickProjectById(page, FIXTURE_BOOK_ID);
    await page.waitForTimeout(1200);

    const workspaceText = await assertBodyIncludes(page, "正式产品工作区", "Project workspace");
    for (const legacyLabel of ["旧版生产", "创作沙盘", "高级编排", "产品原型 Demo"]) {
      if (workspaceText.includes(legacyLabel)) {
        throw new Error(`Legacy workspace entry is still visible: ${legacyLabel}`);
      }
    }

    let body = await clickWorkspaceTab(page, "内容准备");
    if (!body.includes("雨夜账册") || !body.includes("林夏发现账册异常")) {
      throw new Error("Content preparation did not expose seeded chapter business content.");
    }
    const chapters = await readJsonFromPage(page, `/api/books/${FIXTURE_BOOK_ID}/chapters`);
    if (chapters.length !== 2) {
      throw new Error(`Expected 2 seeded chapters, got ${chapters.length}.`);
    }

    body = await clickWorkspaceTab(page, "改编方向");
    if (!body.includes("改编方向候选") || !body.includes("Production Skill")) {
      throw new Error("Adaptation workspace did not expose candidate and production skill controls.");
    }
    const firstAdaptationCandidate = page.getByRole("button", { name: /竖屏情绪悬疑短剧/ }).first();
    if ((await firstAdaptationCandidate.count()) === 0) {
      throw new Error("Adaptation candidate card was not available for UI locking flow.");
    }
    await firstAdaptationCandidate.click();
    await page.waitForTimeout(500);

    const lockSkillButton = page.getByRole("button", { name: "锁定 Production Skill" }).first();
    if ((await lockSkillButton.count()) > 0 && await lockSkillButton.isEnabled()) {
      await lockSkillButton.click();
      await page.waitForTimeout(800);
    }

    const lockAdaptationButton = page.getByRole("button", { name: "锁定为主方向" }).first();
    if ((await lockAdaptationButton.count()) > 0 && await lockAdaptationButton.isEnabled()) {
      await lockAdaptationButton.click();
      await page.waitForTimeout(1000);
    }
    body = await page.locator("body").innerText();
    if (!body.includes("当前主方向") || !body.includes("项目级方向状态") || !body.includes("已锁定")) {
      throw new Error("Adaptation direction did not lock through the real UI flow.");
    }
    const adaptationState = await readJsonFromPage(page, `/api/books/${FIXTURE_BOOK_ID}/adaptation-state`);
    if (!adaptationState.locked_at || !String(adaptationState.selected_name || "").includes("竖屏情绪悬疑短剧")) {
      throw new Error(`Adaptation lock did not persist expected state: ${JSON.stringify(adaptationState)}`);
    }
    const productionSkillState = await readJsonFromPage(page, `/api/books/${FIXTURE_BOOK_ID}/production-skill-state`);
    if (!productionSkillState.locked_at || !productionSkillState.skill_id) {
      throw new Error(`Production skill lock did not persist expected state: ${JSON.stringify(productionSkillState)}`);
    }

    body = await clickWorkspaceTab(page, "剧本工作台");
    if (!body.includes("林夏推门进来") && !body.includes("雨夜账册")) {
      throw new Error("Script workbench did not expose seeded episode/script context.");
    }

    body = await clickWorkspaceTab(page, "镜头工作台");
    if (!body.includes("老茶馆") || !body.includes("染水收据")) {
      throw new Error("Storyboard workbench did not expose seeded shot and asset bindings.");
    }

    const promptVersionsBeforeLock = await readJsonFromPage(
      page,
      `/api/books/${FIXTURE_BOOK_ID}/storyboard/${FIXTURE_EPISODE}/${FIXTURE_SHOT_ID}/prompt-versions`,
    );
    if (promptVersionsBeforeLock.locked) {
      throw new Error("Fixture prompt should start unlocked.");
    }

    await page.getByText("提示词历史版本").click();
    const lockButton = page.getByRole("button", { name: /锁定当前版本|已锁定提示词/ }).first();
    if ((await lockButton.count()) === 0) {
      throw new Error("Prompt lock button was not available in storyboard workbench.");
    }
    await lockButton.click();
    await page.waitForTimeout(700);
    const promptVersionsAfterLock = await readJsonFromPage(
      page,
      `/api/books/${FIXTURE_BOOK_ID}/storyboard/${FIXTURE_EPISODE}/${FIXTURE_SHOT_ID}/prompt-versions`,
    );
    if (!promptVersionsAfterLock.locked || promptVersionsAfterLock.locked_version !== 1) {
      throw new Error(`Prompt lock did not persist expected state: ${JSON.stringify(promptVersionsAfterLock)}`);
    }

    const degradedShotCard = page.locator(`[data-shot-id="${FIXTURE_REPAIR_SHOT_ID}"]`).first();
    if ((await degradedShotCard.count()) === 0) {
      throw new Error("Degraded prompt repair shot was not visible in storyboard list.");
    }
    await degradedShotCard.click();
    await page.waitForTimeout(700);
    body = await page.locator("body").innerText();
    if (!body.includes("当前修复入口") || !body.includes("重编提示词") || !body.includes("静态提示词过短") || !body.includes("运动提示词过短")) {
      throw new Error("Degraded prompt repair entry did not expose a clear short-prompt recompile action.");
    }

    const promptCompileResponsePromise = page.waitForResponse(
      response =>
        response.url().includes(`/api/books/${FIXTURE_BOOK_ID}/storyboard/${FIXTURE_EPISODE}/${FIXTURE_REPAIR_SHOT_ID}/compile-prompts/async`)
        && response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "重新编译提示词" }).click();
    const promptCompileResponse = await promptCompileResponsePromise;
    if (!promptCompileResponse.ok()) {
      throw new Error(`Prompt repair compile submit failed with HTTP ${promptCompileResponse.status()}: ${await promptCompileResponse.text()}`);
    }
    const promptCompilePayload = await promptCompileResponse.json();
    const promptTaskId = String(promptCompilePayload.task_id || "").trim();
    if (!promptTaskId) {
      throw new Error(`Prompt repair compile did not return task id: ${JSON.stringify(promptCompilePayload)}`);
    }
    const promptTask = await waitForPromptCompileTask(page, promptTaskId);
    if (Number(promptTask.version || promptTask.prompt_version || 0) !== 2) {
      throw new Error(`Prompt repair compile did not create v2: ${JSON.stringify(promptTask)}`);
    }

    const degradedPromptVersions = await readJsonFromPage(
      page,
      `/api/books/${FIXTURE_BOOK_ID}/storyboard/${FIXTURE_EPISODE}/${FIXTURE_REPAIR_SHOT_ID}/prompt-versions`,
    );
    if (Number(degradedPromptVersions.current_version || 0) !== 2 || (degradedPromptVersions.versions || []).length < 2) {
      throw new Error(`Prompt repair did not persist v2 version history: ${JSON.stringify(degradedPromptVersions)}`);
    }
    const repairedVersion = (degradedPromptVersions.versions || []).find(version => Number(version.version || 0) === 2);
    const repairedStatic = String(repairedVersion?.prompt_static || "");
    const repairedMotion = String(repairedVersion?.prompt_motion || "");
    const repairedSceneAssetId = String(repairedVersion?.meta_info?.structured_shot?.scene_asset_id || "");
    if (repairedStatic.length < 80 || repairedMotion.length < 50 || !repairedSceneAssetId) {
      throw new Error(`Prompt repair v2 did not repair prompt length and scene binding: ${JSON.stringify(repairedVersion)}`);
    }

    const originalShotCard = page.locator(`[data-shot-id="${FIXTURE_SHOT_ID}"]`).first();
    await originalShotCard.click();
    await page.waitForTimeout(500);

    await page.getByText("提交验收记录").click();
    await page.locator('input[placeholder="资产 ID"]').first().fill("frame-e2e-1");
    await page.locator("select").filter({ hasText: "通过采纳" }).first().selectOption("failed");
    await page.getByRole("button", { name: "道具不一致" }).click();
    await page.locator('textarea[placeholder="记录通过理由、打回原因或下一轮约束。"]').fill(
      "E2E 验收打回：收据必须完整露出，店长视线要落在签名上。",
    );
    const acceptanceResponsePromise = page.waitForResponse(
      response =>
        response.url().includes(`/api/books/${FIXTURE_BOOK_ID}/storyboard/${FIXTURE_EPISODE}/${FIXTURE_SHOT_ID}/acceptance-records`)
        && response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "保存验收" }).click();
    const acceptanceResponse = await acceptanceResponsePromise;
    if (!acceptanceResponse.ok()) {
      throw new Error(`Acceptance save failed with HTTP ${acceptanceResponse.status()}: ${await acceptanceResponse.text()}`);
    }
    await page.waitForTimeout(400);
    const acceptanceRecords = await readJsonFromPage(
      page,
      `/api/books/${FIXTURE_BOOK_ID}/storyboard/${FIXTURE_EPISODE}/${FIXTURE_SHOT_ID}/acceptance-records`,
    );
    const latestAcceptance = acceptanceRecords.records?.[0];
    if (latestAcceptance?.status !== "failed" || !latestAcceptance.failure_tags?.includes("prop_mismatch")) {
      throw new Error(`Acceptance record did not persist expected failure: ${JSON.stringify(acceptanceRecords)}`);
    }

    body = await clickWorkspaceTab(page, "资产中心");
    if (!body.includes("老茶馆") || !body.includes("林夏") || !body.includes("染水收据")) {
      throw new Error("Asset center did not expose scene, character, and prop assets.");
    }

    body = await clickWorkspaceTab(page, "任务中心");
    if (!body.includes("任务中心概览") || !body.includes("QA 修复")) {
      throw new Error("Task center did not expose project execution and QA state.");
    }

    body = await clickWorkspaceTab(page, "导出中心");
    if (!body.includes("导出中心") || !body.includes("QA")) {
      throw new Error("Delivery center did not expose delivery readiness and QA blocking state.");
    }

    body = await clickWorkspaceTab(page, "创作画布");
    if (!body.includes("React Flow") || !body.includes("老茶馆") || !body.includes("第 1 集质检") || !body.includes("第 1 集交付")) {
      throw new Error("Creative canvas did not expose the linked script, shot, QA, and delivery graph.");
    }

    body = await clickWorkspaceTab(page, "模型管理");
    if (!body.includes("文本 / LLM") || !body.includes("向量 / Embedding") || !body.includes("图像 / Image") || !body.includes("视频 / Video")) {
      throw new Error("Model management did not expose the full default model chain.");
    }

    await clickWorkspaceTab(page, "QA 修复");
    await readJsonFromPage(page, `/api/books/${FIXTURE_BOOK_ID}/qa/episodes/${FIXTURE_EPISODE}/sync`, { method: "POST" });
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.waitForTimeout(800);
    await clickWorkspaceTab(page, "QA 修复");
    body = await assertBodyIncludes(page, "信任转折缺少证据", "QA workbench");

    const workbenchBeforeFix = await readJsonFromPage(page, `/api/books/${FIXTURE_BOOK_ID}/qa/workbench`);
    const issue = workbenchBeforeFix.episodes?.[0]?.issues?.[0];
    if (!issue?.issue_id) {
      throw new Error(`Expected synced QA issue, got: ${JSON.stringify(workbenchBeforeFix)}`);
    }
    const outputsBeforeFix = await readJsonFromPage(page, `/api/pipeline/book/${FIXTURE_BOOK_ID}/outputs`);
    const originalScript = outputsBeforeFix.scripts?.find(item => Number(item.episode) === FIXTURE_EPISODE)?.content || "";
    if (!originalScript.includes("突然选择相信她")) {
      throw new Error("Original script assertion failed before QA repair.");
    }

    const patchedText = [
      "她发现账册缺了一页，立刻把夹在封底的染水收据摊开。",
      "店长看见收据上的签名与缺页边角吻合，沉默片刻，终于选择相信她。",
    ].join("\n");

    const repairBox = page.getByPlaceholder("选择修复方案后会填入这里，也可以直接人工编辑。").first();
    if ((await repairBox.count()) === 0) {
      throw new Error("QA repair textarea was not available for manual browser repair.");
    }
    await repairBox.fill(patchedText);

    await page.getByRole("button", { name: "预览 diff" }).click();
    await page.waitForTimeout(1000);
    body = await page.locator("body").innerText();
    if (!body.includes("修复 Diff") || !body.includes("染水收据摊开")) {
      throw new Error("QA diff preview did not render the manual evidence patch in the UI.");
    }

    await page.getByRole("button", { name: "应用修复并复检" }).click();
    await page.waitForTimeout(1800);

    const outputsAfterApply = await readJsonFromPage(page, `/api/pipeline/book/${FIXTURE_BOOK_ID}/outputs`);
    const scriptAfterApply = outputsAfterApply.scripts?.find(item => Number(item.episode) === FIXTURE_EPISODE)?.content || "";
    if (!scriptAfterApply.includes("染水收据") || scriptAfterApply.includes("突然选择相信她")) {
      throw new Error("Applied QA repair did not update script content as expected.");
    }

    await page.reload({ waitUntil: "domcontentloaded" });
    await page.waitForTimeout(800);
    await clickWorkspaceTab(page, "QA 修复");
    body = await page.locator("body").innerText();
    if (!body.includes("v2") || !body.includes("semi_auto修复")) {
      throw new Error("QA workbench did not render the repair version after apply.");
    }
    const workbenchAfterApply = await readJsonFromPage(page, `/api/books/${FIXTURE_BOOK_ID}/qa/workbench`);
    const fixVersion = (workbenchAfterApply.episodes?.[0]?.versions || []).find(
      version => String(version.change_type || "").toLowerCase() !== "baseline",
    );
    if (!fixVersion?.id || String(fixVersion.change_type || "").toLowerCase() !== "semi_auto_fix") {
      throw new Error(`UI apply did not create expected script fix version: ${JSON.stringify(workbenchAfterApply.episodes?.[0]?.versions || [])}`);
    }

    const rollbackButton = page.getByRole("button", { name: "回滚到修复前" }).first();
    if ((await rollbackButton.count()) === 0) {
      throw new Error("QA rollback button was not available after applying a script repair.");
    }
    await rollbackButton.click();
    await page.waitForTimeout(500);
    const confirmRollbackButton = page.getByRole("button", { name: "确认回滚并复检" }).first();
    if ((await confirmRollbackButton.count()) === 0) {
      throw new Error("QA rollback confirmation was not available after clicking rollback.");
    }
    await confirmRollbackButton.click();
    await page.waitForTimeout(1800);

    const outputsAfterRollback = await readJsonFromPage(page, `/api/pipeline/book/${FIXTURE_BOOK_ID}/outputs`);
    const scriptAfterRollback = outputsAfterRollback.scripts?.find(item => Number(item.episode) === FIXTURE_EPISODE)?.content || "";
    if (!scriptAfterRollback.includes("突然选择相信她") || scriptAfterRollback.includes("染水收据摊开")) {
      throw new Error("Rollback did not restore original script content.");
    }

    const finalWorkbench = await readJsonFromPage(page, `/api/books/${FIXTURE_BOOK_ID}/qa/workbench`);
    const versions = finalWorkbench.episodes?.[0]?.versions || [];
    if (versions.length < 3) {
      throw new Error(`Expected baseline, fix, and rollback versions; got ${versions.length}.`);
    }
    const rollbackVersion = versions.find(version => String(version.change_type || "").toLowerCase() === "rollback");
    if (!rollbackVersion?.label?.includes("回滚到") || rollbackVersion.label.includes("鍥炴粴")) {
      throw new Error(`Rollback version label is not production-safe Chinese: ${JSON.stringify(rollbackVersion)}`);
    }

    if (failures.length) {
      throw new Error(`Browser business E2E found failures:\n${failures.join("\n")}`);
    }

    log(`Formal workspace business flow passed for project #${FIXTURE_BOOK_ID}.`);
    log(`QA issue ${issue.issue_id} generated version ${fixVersion.id} and rollback ${rollbackVersion.id}.`);
    log(`Acceptance record ${latestAcceptance.id} persisted with tags: ${latestAcceptance.failure_tags.join(", ")}.`);
  } finally {
    await browser.close();
  }
}

async function main() {
  if (START_SERVERS) {
    log("Starting backend and frontend servers...");
    spawnManaged("python", ["-m", "api.server"], {
      name: "api",
      env: { E2E_STORYBOARD_PROMPT_MOCK: "1" },
    });
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
    log(`Seeded formal workspace business fixture project #${FIXTURE_BOOK_ID}.`);
    await runBusinessFlow();
    log("Business flow E2E passed.");
  } finally {
    try {
      cleanupFixture();
      log(`Cleaned business fixture project #${FIXTURE_BOOK_ID}.`);
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
