const { spawnSync } = require("child_process");

// Local development intentionally adapts to whatever samples exist.  Release
// verification must be strict so a single fixture cannot masquerade as
// multi-project production evidence.
const node = process.execPath;
const forwarded = process.argv.slice(2);
const env = {
  ...process.env,
  E2E_REAL_SAMPLE_REQUIRE_MINIMUM: "1",
  E2E_REAL_SAMPLE_MIN_COUNT: process.env.E2E_REAL_SAMPLE_MIN_COUNT || "3",
};
const result = spawnSync(node, ["scripts/e2e-formal-workspace-real-samples.js", ...forwarded], {
  stdio: "inherit",
  env,
});

if (result.error) {
  console.error(`[e2e-real-samples-release] failed to start ${node}: ${result.error.message}`);
  process.exit(1);
}

process.exit(result.status === null ? 1 : result.status);
