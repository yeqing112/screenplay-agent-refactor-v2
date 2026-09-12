const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

// This is the single release-gate entry point. It deliberately runs every
// gate even when an earlier gate fails, so operators receive the complete
// blocker set in one report. It never creates production data or calls an
// external model/provider by itself; those boundaries remain enforced by the
// commands it invokes.
const steps = [
  {
    id: "production_config",
    name: "production configuration verification",
    command: "npm",
    args: ["run", "config:verify:production"],
  },
  {
    id: "sample_registry",
    name: "production sample registry validation",
    command: "npm",
    args: ["run", "validate:sample-registry"],
  },
  {
    id: "shot_planning_gate",
    name: "shot planning quality gate",
    command: "npm",
    args: ["run", "audit:shot-planning:gate"],
  },
  {
    id: "storyboard_prompt_gate",
    name: "storyboard prompt zero-error gate",
    command: "npm",
    args: ["run", "audit:storyboard:zero-error-gate"],
  },
  {
    id: "production_regression",
    name: "deterministic production regression",
    command: "npm",
    args: ["run", "check:production"],
  },
  {
    id: "real_browser_release_e2e",
    name: "production real-browser regression",
    command: "npm",
    args: ["run", "e2e:real-samples:release"],
  },
];

function runStep(step) {
  const processResult = spawnSync(step.command, step.args, {
    shell: process.platform === "win32" && step.command === "npm",
    encoding: "utf8",
    env: {
      ...process.env,
      PYTHONIOENCODING: process.env.PYTHONIOENCODING || "utf-8",
    },
  });
  const stdout = processResult.stdout || "";
  const stderr = processResult.stderr || "";
  const status = processResult.status == null ? 1 : processResult.status;
  const result = {
    id: step.id,
    name: step.name,
    command: [step.command, ...step.args].join(" "),
    exit_code: status,
    passed: status === 0,
    output: `${stdout}${stderr}`.trim(),
  };
  return enrichStepResult(result);
}

function parseJsonLine(output) {
  const lines = String(output || "").split(/\r?\n/).reverse();
  for (const line of lines) {
    const candidate = line.trim();
    if (!candidate.startsWith("{") || !candidate.endsWith("}")) {
      continue;
    }
    try {
      return JSON.parse(candidate);
    } catch {
      // A command may print non-JSON diagnostic lines; keep scanning.
    }
  }
  return null;
}

function enrichStepResult(result) {
  const details = {};
  const parsed = parseJsonLine(result.output);
  if (parsed && typeof parsed === "object") {
    if (parsed.summary && typeof parsed.summary === "object") {
      const summary = parsed.summary;
      if (Array.isArray(summary.release_blockers) && summary.release_blockers.length) {
        details.release_blockers = summary.release_blockers;
      }
      if (Array.isArray(summary.next_actions) && summary.next_actions.length) {
        details.next_actions = summary.next_actions;
      }
      details.summary = summary;
    }
    if (parsed.warnings && Array.isArray(parsed.warnings) && parsed.warnings.length) {
      details.warnings = parsed.warnings;
    }
    // Several read-only gates return their evidence path as `report`, while
    // others print a `Report written:` line.  Preserve either form in the
    // unified release report so operators can open the exact artifact that
    // explains a blocker.  This is intentionally schema-agnostic and does not
    // infer paths by scanning the artifacts directory (which could select a
    // stale report).
    if (typeof parsed.report === "string" && parsed.report.trim()) {
      details.artifact = parsed.report.trim();
    } else if (typeof parsed.artifact === "string" && parsed.artifact.trim()) {
      details.artifact = parsed.artifact.trim();
    }
  }
  const reportMatch = String(result.output || "").match(/Report written:\s*(.+)/);
  if (reportMatch) {
    details.artifact = reportMatch[1].trim();
  }
  const auditedMatch = String(result.output || "").match(/Audited\s+(\d+)\s+shots\.\s*errors=(\d+),\s*warnings=(\d+)/);
  if (auditedMatch) {
    details.audited_shots = Number(auditedMatch[1]);
    details.errors = Number(auditedMatch[2]);
    details.warnings_count = Number(auditedMatch[3]);
  }
  return Object.keys(details).length ? { ...result, details } : result;
}

function enforceReleaseEnvironment(result, step) {
  // `config:verify:production` intentionally skips in local development.
  // That is safe for development, but a release gate must never interpret a
  // skipped production check as a green result.
  if (step.id !== "production_config") {
    return result;
  }
  const deploymentEnv = String(process.env.DEPLOYMENT_ENV || "").toLowerCase();
  if (deploymentEnv === "production" || deploymentEnv === "staging") {
    return result;
  }
  return {
    ...result,
    passed: false,
    release_blocker: "DEPLOYMENT_ENV must be production or staging for a release gate",
  };
}

function isoFileStamp() {
  return new Date().toISOString().replace(/[:.]/g, "-");
}

function writeReports(results) {
  const stamp = isoFileStamp();
  const artifactsDir = path.resolve(process.cwd(), "artifacts");
  fs.mkdirSync(artifactsDir, { recursive: true });
  const jsonPath = path.join(artifactsDir, `production-release-gate-${stamp}.json`);
  const mdPath = path.join(artifactsDir, `production-release-gate-${stamp}.md`);
  const passed = results.every((item) => item.passed);
  const report = {
    mode: "production_release_gate",
    generated_at: new Date().toISOString(),
    release_green: passed,
    steps: results.map(({ output, ...item }) => item),
  };
  fs.writeFileSync(jsonPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");

  const lines = [
    "# Production release gate",
    "",
    `- Generated: ${report.generated_at}`,
    `- Result: **${passed ? "PASS" : "BLOCKED"}**`,
    "",
    "## Steps",
    "",
    "| Step | Status | Exit code | Release blocker |",
    "| --- | --- | ---: | --- |",
  ];
  for (const item of report.steps) {
    const blockers = [
      item.release_blocker,
      ...(item.details?.release_blockers || []),
    ].filter(Boolean);
    const blocker = blockers.join("；").replaceAll("|", "\\|");
    lines.push(`| ${item.name} | ${item.passed ? "PASS" : "BLOCKED"} | ${item.exit_code} | ${blocker} |`);
    if (item.details?.next_actions?.length) {
      lines.push(`| ↳ next actions | — | — | ${item.details.next_actions.join("；").replaceAll("|", "\\|")} |`);
    }
    if (item.details?.artifact) {
      lines.push(`| ↳ evidence artifact | — | — | ${String(item.details.artifact).replaceAll("|", "\\|")} |`);
    }
  }
  lines.push(
    "",
    "The gate is fail-closed: every step must pass. See the JSON report and the command-specific artifacts for blockers.",
    "",
  );
  fs.writeFileSync(mdPath, `${lines.join("\n")}\n`, "utf8");
  return { jsonPath, mdPath, passed };
}

function main() {
  const results = [];
  for (const step of steps) {
    console.log(`[production-release-gate] Running: ${step.name}`);
    const result = enforceReleaseEnvironment(runStep(step), step);
    results.push(result);
    if (result.output) {
      process.stdout.write(`${result.output}\n`);
    }
    console.log(`[production-release-gate] ${result.passed ? "PASS" : "BLOCKED"}: ${step.id}`);
  }
  const report = writeReports(results);
  console.log(`[production-release-gate] JSON report: ${report.jsonPath}`);
  console.log(`[production-release-gate] Markdown report: ${report.mdPath}`);
  if (!report.passed) {
    process.exitCode = 2;
    console.log("[production-release-gate] Release remains blocked; review every failed step.");
    return;
  }
  console.log("[production-release-gate] All release gates passed.");
}

if (require.main === module) {
  main();
}

module.exports = {
  steps,
  runStep,
  parseJsonLine,
  enrichStepResult,
  enforceReleaseEnvironment,
  writeReports,
};
