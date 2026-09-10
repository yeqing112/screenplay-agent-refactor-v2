const { spawnSync } = require("child_process");

const steps = [
  {
    name: "python prompt/compiler regression tests",
    command: "python",
    args: [
      "-m",
      "unittest",
      "tests.test_model_adapter",
      "tests.test_llm_json_parsing",
      "tests.test_reader_fallback",
      "tests.test_storyboard_prompt_compile",
      "tests.test_storyboard_prompt_compile_repair",
      "tests.test_machine_prompt_export",
      "tests.test_production_export_records",
      "tests.test_api_security",
      "tests.test_public_asset_storage",
      "tests.test_production_readiness",
      "tests.test_production_repair_plan",
      "tests.test_qa_workbench_flow",
    ],
  },
  {
    name: "frontend production build",
    command: "npm",
    args: ["--prefix", "web", "run", "build"],
  },
  {
    name: "five-project storyboard zero-error gate",
    command: "npm",
    args: ["run", "audit:storyboard:zero-error-gate"],
  },
];

function runStep(step) {
  console.log(`[production-regression] Running: ${step.name}`);
  const result = spawnSync(step.command, step.args, {
    stdio: "inherit",
    shell: process.platform === "win32",
    env: {
      ...process.env,
      PYTHONIOENCODING: process.env.PYTHONIOENCODING || "utf-8",
    },
  });
  if (result.status !== 0) {
    const code = result.status ?? result.signal ?? "unknown";
    throw new Error(`${step.name} failed with exit code ${code}`);
  }
}

function main() {
  for (const step of steps) {
    runStep(step);
  }
  console.log("[production-regression] All production regression checks passed.");
}

main();
