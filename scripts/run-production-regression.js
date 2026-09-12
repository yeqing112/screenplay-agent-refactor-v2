const { spawnSync } = require("child_process");

const steps = [
  {
    name: "python deterministic regression tests",
    command: "python",
    args: [
      "-m", "pytest", "-q",
    ],
  },
  {
    name: "deterministic Golden Project regression",
    command: "npm",
    args: ["run", "test:golden"],
  },
  {
    name: "runtime configuration verification",
    command: "npm",
    args: ["run", "config:verify"],
  },
  {
    name: "production release gate invariants",
    command: "npm",
    args: ["run", "test:release-gate"],
  },
  {
    name: "frontend production build",
    command: "npm",
    args: ["--prefix", "web", "run", "build"],
  },
];

function runStep(step) {
  console.log(`[production-regression] Running: ${step.name}`);
  const result = spawnSync(step.command, step.args, {
    stdio: "inherit",
    // Python must run without cmd.exe on Windows: cmd's inherited stdio can
    // close pytest's temporary capture stream during teardown. npm.cmd still
    // needs the shell resolution used by the existing Windows scripts.
    shell: process.platform === "win32" && step.command === "npm",
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
