const { spawnSync } = require("child_process");

// npm's argument forwarding differs between Windows npm versions.  Keep the
// public `npm run backup:database -- --output <path>` contract stable by
// forwarding the arguments from a Node entry point instead of relying on npm
// to invoke Python directly.
const python = process.env.SCREENPLAY_PYTHON || "python";
const forwarded = process.argv.slice(2);
// Some npm versions consume unknown option names such as `--output` while
// forwarding the value as a positional argument.  Recover that documented
// form without weakening the Python tool's explicit flag validation.
const pythonArgs = forwarded.length === 1 && !forwarded[0].startsWith("-")
  ? ["--output", forwarded[0]]
  : forwarded;
const result = spawnSync(python, ["scripts/backup-database.py", ...pythonArgs], {
  stdio: "inherit",
  env: {
    ...process.env,
    PYTHONIOENCODING: process.env.PYTHONIOENCODING || "utf-8",
  },
});

if (result.error) {
  console.error(`[backup-database] failed to start ${python}: ${result.error.message}`);
  process.exit(1);
}

process.exit(result.status === null ? 1 : result.status);
