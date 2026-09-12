const { spawnSync } = require("child_process");

// Keep `npm run backup:database:scheduled -- ...` stable across Windows npm
// versions.  Some npm releases consume unknown long options and leave only
// their positional values; recover the documented directory form below while
// leaving explicit Python flags untouched.
const python = process.env.SCREENPLAY_PYTHON || "python";
const forwarded = process.argv.slice(2);
const pythonArgs = forwarded.length === 1 && !forwarded[0].startsWith("-")
  ? ["--directory", forwarded[0]]
  : forwarded;

const result = spawnSync(python, ["scripts/scheduled-database-backup.py", ...pythonArgs], {
  stdio: "inherit",
  env: {
    ...process.env,
    PYTHONIOENCODING: process.env.PYTHONIOENCODING || "utf-8",
  },
});

if (result.error) {
  console.error(`[scheduled-database-backup] failed to start ${python}: ${result.error.message}`);
  process.exit(1);
}

process.exit(result.status === null ? 1 : result.status);
