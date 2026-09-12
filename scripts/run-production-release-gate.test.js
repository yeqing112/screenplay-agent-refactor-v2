const assert = require("assert");
const fs = require("fs");
const {
  enforceReleaseEnvironment,
  enrichStepResult,
  parseJsonLine,
  steps,
} = require("./run-production-release-gate");

const configStep = steps.find((step) => step.id === "production_config");
assert(configStep, "production configuration step must exist");

const originalEnv = process.env.DEPLOYMENT_ENV;
try {
  delete process.env.DEPLOYMENT_ENV;
  const development = enforceReleaseEnvironment(
    { passed: true, exit_code: 0 },
    configStep,
  );
  assert.strictEqual(development.passed, false);
  assert.match(development.release_blocker, /production or staging/);

  process.env.DEPLOYMENT_ENV = "staging";
  const staging = enforceReleaseEnvironment(
    { passed: true, exit_code: 0 },
    configStep,
  );
  assert.strictEqual(staging.passed, true);

  const ordinary = enforceReleaseEnvironment(
    { passed: true, exit_code: 0 },
    { id: "sample_registry" },
  );
  assert.strictEqual(ordinary.passed, true);

  const parsed = parseJsonLine('noise\n{"summary":{"release_blockers":["need samples"],"next_actions":["add real shots"]}}');
  assert.deepStrictEqual(parsed.summary.release_blockers, ["need samples"]);
  const enriched = enrichStepResult({
    id: "shot_planning_gate",
    name: "shot planning",
    exit_code: 2,
    passed: false,
    output: '{"summary":{"release_blockers":["need samples"],"next_actions":["add real shots"]}}',
  });
  assert.deepStrictEqual(enriched.details.release_blockers, ["need samples"]);
  assert.deepStrictEqual(enriched.details.next_actions, ["add real shots"]);

  const reportPath = enrichStepResult({
    id: "shot_planning_gate",
    name: "shot planning",
    exit_code: 2,
    passed: false,
    output: '{"report":"D:/evidence/shot-planning.json","summary":{"release_blockers":["need samples"]}}',
  });
  assert.strictEqual(reportPath.details.artifact, "D:/evidence/shot-planning.json");

  // The markdown writer consumes the same normalized artifact field, so the
  // report remains directly actionable without requiring log archaeology.
  const report = require("./run-production-release-gate").writeReports([reportPath]);
  const markdown = fs.readFileSync(report.mdPath, "utf8");
  assert.match(markdown, /evidence artifact/);
  assert.match(markdown, /D:\/evidence\/shot-planning\.json/);
  fs.rmSync(report.jsonPath, { force: true });
  fs.rmSync(report.mdPath, { force: true });

  console.log("run-production-release-gate.test.js: passed");
} finally {
  if (originalEnv === undefined) {
    delete process.env.DEPLOYMENT_ENV;
  } else {
    process.env.DEPLOYMENT_ENV = originalEnv;
  }
}
