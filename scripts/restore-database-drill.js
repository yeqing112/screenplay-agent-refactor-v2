const { spawnSync } = require("child_process");

// Keep `npm run verify:database-restore -- --backup <path>` usable on npm
// versions that consume unknown option names while forwarding the value.
const python = process.env.SCREENPLAY_PYTHON || "python";
const forwarded = process.argv.slice(2);
const pythonArgs = forwarded.length === 1 && !forwarded[0].startsWith("-")
  ? ["--backup", forwarded[0]]
  : forwarded;
const result = spawnSync(python, ["scripts/restore-database-drill.py", ...pythonArgs], {
  stdio: "inherit",
  env: {
    ...process.env,
    PYTHONIOENCODING: process.env.PYTHONIOENCODING || "utf-8",
  },
});

if (result.error) {
  console.error(`[restore-database-drill] failed to start ${python}: ${result.error.message}`);
  process.exit(1);
}

process.exit(result.status === null ? 1 : result.status);
