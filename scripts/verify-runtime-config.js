const fs = require("fs");
const path = require("path");

// The formal workspace has one canonical local runtime.  Isolated browser
// suites may override these through E2E_API_URL/E2E_WEB_URL, but executable
// defaults must never silently fall back to the retired 8765/5173 pair.
const root = process.cwd();
const checks = [
  { file: "scripts/e2e-smoke.js", forbidden: "http://127.0.0.1:8765" },
  { file: "scripts/e2e-qa-workbench.js", forbidden: "http://127.0.0.1:8765" },
  { file: "scripts/e2e-formal-workspace-real-samples.js", forbidden: "http://127.0.0.1:8765" },
  { file: "scripts/audit-storyboard-prompt-real-samples.js", forbidden: "http://127.0.0.1:8765" },
  { file: "dev.sh", forbidden: ":8765" },
];

const failures = [];
for (const check of checks) {
  const absolute = path.join(root, check.file);
  const content = fs.readFileSync(absolute, "utf8");
  if (content.includes(check.forbidden)) failures.push(`${check.file}: contains retired ${check.forbidden}`);
}

if (failures.length) {
  console.error("[config-verify] FAILED");
  failures.forEach(item => console.error(`- ${item}`));
  process.exit(1);
}

console.log("[config-verify] OK: executable defaults use formal workspace ports (API 18765, Web 5175) or explicit env overrides.");
