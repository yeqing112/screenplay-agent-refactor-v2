const assert = require("assert");
const { auditShot, summarize } = require("./audit-storyboard-prompt-real-samples");

const book = { id: 9001, title: "审计夹具" };
const baseShot = {
  episode: 1,
  shot_id: "1",
  scene_name: "测试场景",
  visual_prompt_static: "测试场景，近景构图，冷色环境光，画面层次清晰，人物与环境关系明确。",
  visual_prompt_motion: "固定镜头缓慢推进，人物抬眼后停留在关键反应，保持动作连续。",
  structured_shot: { scene_asset_id: 1, character_asset_ids: [2], action_beats: [{ description: "人物抬眼" }] },
  prompt_compile_context: { asset_bindings: { scene: { asset_id: 1, asset_name: "测试场景" } } },
  used_assets: [],
  reference_images: [],
};

const result = auditShot(book, {
  ...baseShot,
  compiler_diagnostics: {
    warnings: ["权威视觉事实覆盖不足"],
    checks: [
      { key: "known_character_gender", passed: false, message: "已知人物性别未继承", details: ["角色 #2"] },
      { key: "passed_check", passed: true, message: "不应进入审计" },
    ],
  },
});

assert(result.warnings.some(item => item.code === "compiler_warning_present"));
assert(result.warnings.some(item => item.code === "compiler_check_failed:known_character_gender"));
assert(!result.warnings.some(item => item.code === "compiler_check_failed:passed_check"));

const summary = summarize([result]);
assert(summary.total_warnings >= 2, "共享编译器告警必须使严格门禁失败");

console.log("audit-storyboard-prompt-real-samples.test.js: passed");
