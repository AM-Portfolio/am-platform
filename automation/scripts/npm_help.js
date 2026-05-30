#!/usr/bin/env node
/**
 * Print root + workspace npm scripts for am-platform.
 */
const { readFileSync } = require("fs");
const { join } = require("path");

const root = join(__dirname, "..", "..");
const rootPkg = JSON.parse(readFileSync(join(root, "package.json"), "utf8"));

console.log("\n=== am-platform (root) ===\n");
for (const [name, cmd] of Object.entries(rootPkg.scripts || {}).sort()) {
  if (name === "help") continue;
  console.log(name.padEnd(30), cmd);
}

const workspaces = rootPkg.workspaces || [];
for (const ws of workspaces) {
  const pkgPath = join(root, ws, "package.json");
  try {
    const pkg = JSON.parse(readFileSync(pkgPath, "utf8"));
    console.log(`\n=== ${pkg.name || ws} (${ws}) ===\n`);
    for (const [name, cmd] of Object.entries(pkg.scripts || {}).sort()) {
      console.log(name.padEnd(30), cmd);
    }
  } catch {
    // skip missing
  }
}

console.log("\nTip: npm run platform:dev  |  npm run identity:dev  |  npm run infra:tf:apply\n");
