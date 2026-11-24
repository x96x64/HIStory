#!/usr/bin/env node
// Copy the Python package, the README and the LICENSE from the repository root into this folder
// so that `npm pack` and `npm publish` include them.
"use strict";

const fs = require("node:fs");
const path = require("node:path");

const here = path.resolve(__dirname, "..");
const root = path.resolve(here, "..");

function skip(source) {
  const name = path.basename(source);
  return name === "__pycache__" || name.endsWith(".pyc");
}

fs.rmSync(path.join(here, "hist"), { recursive: true, force: true });
fs.cpSync(path.join(root, "hist"), path.join(here, "hist"), {
  recursive: true,
  filter: (source) => !skip(source),
});
for (const file of ["README.md", "LICENSE"]) {
  fs.copyFileSync(path.join(root, file), path.join(here, file));
}
