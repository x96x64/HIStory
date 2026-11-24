#!/usr/bin/env node
// Start the Python implementation of hist: `python3 -m hist ARGS...`.
"use strict";

const { spawn, spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const MIN = [3, 12];

function fail(message) {
  process.stderr.write(`hist: ${message}\n`);
  process.exit(2);
}

function pythonVersion(command) {
  const result = spawnSync(command, ["-c", "import sys; print('%d.%d' % sys.version_info[:2])"], {
    encoding: "utf8",
  });
  if (result.error || result.status !== 0) return null;
  const [major, minor] = result.stdout.trim().split(".").map(Number);
  return { major, minor, text: `${major}.${minor}` };
}

function atLeast(v) {
  return v.major > MIN[0] || (v.major === MIN[0] && v.minor >= MIN[1]);
}

function findPython() {
  const wanted = process.env.HIST_PYTHON;
  const candidates = wanted ? [wanted] : ["python3", "python"];
  const old = [];
  for (const command of candidates) {
    const v = pythonVersion(command);
    if (!v) continue;
    if (atLeast(v)) return command;
    old.push(`${command} is ${v.text}`);
  }
  if (old.length > 0) {
    fail(`Python ${MIN.join(".")} or newer is required (${old.join(", ")}). Set HIST_PYTHON to a newer interpreter.`);
  }
  fail(
    wanted
      ? `cannot run HIST_PYTHON=${wanted}. Set it to a Python ${MIN.join(".")} or newer interpreter.`
      : `Python ${MIN.join(".")} or newer was not found. Install it, or set HIST_PYTHON to its path.`,
  );
}

// The package folder holds hist/ after `npm pack`; in a source checkout it is the repository root.
const here = path.resolve(__dirname, "..");
const packageDir = [here, path.resolve(here, "..")].find((dir) =>
  fs.existsSync(path.join(dir, "hist", "__init__.py")),
);
if (!packageDir) fail("the Python package 'hist' is missing; run `npm run prepack` in the npm folder.");

const python = findPython();
const pythonPath = [packageDir, process.env.PYTHONPATH].filter(Boolean).join(path.delimiter);
const child = spawn(python, ["-m", "hist", ...process.argv.slice(2)], {
  stdio: "inherit",
  env: { ...process.env, PYTHONPATH: pythonPath },
});

for (const signal of ["SIGINT", "SIGTERM", "SIGHUP"]) {
  process.on(signal, () => child.kill(signal));
}
child.on("error", (error) => fail(`cannot start ${python}: ${error.message}`));
child.on("exit", (code, signal) => {
  if (signal) {
    process.removeAllListeners(signal);
    process.kill(process.pid, signal);
  } else {
    process.exit(code ?? 1);
  }
});
