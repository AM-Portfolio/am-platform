#!/usr/bin/env node
/**
 * @asrax/mcp — Cursor stdio entrypoint.
 * Env: ASRAX_MCP_URL, ASRAX_KEY_ID, ASRAX_KEY_SECRET (or AM_MCP_CLIENT_*), ASRAX_IDENTITY_URL
 */
import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { obtainAccessToken, loadDotEnvFiles } from "../lib/auth.js";

loadDotEnvFiles();

const mcpUrl = (process.env.ASRAX_MCP_URL || "").trim();
if (!mcpUrl) {
  console.error("ASRAX_MCP_URL is required (e.g. https://am-dev.asrax.in/mcp)");
  process.exit(1);
}

let token;
try {
  token = await obtainAccessToken();
} catch (err) {
  console.error(String(err?.message || err));
  process.exit(1);
}

const require = createRequire(import.meta.url);
let mcpRemoteBin;
try {
  const pkg = require.resolve("mcp-remote/package.json");
  mcpRemoteBin = path.join(path.dirname(pkg), "dist", "proxy.js");
} catch {
  mcpRemoteBin = null;
}

const env = {
  ...process.env,
  ASRAX_MCP_AUTH_HEADER: `Bearer ${token}`,
};

const args = mcpRemoteBin
  ? [mcpRemoteBin, mcpUrl, "--header", `Authorization: Bearer ${token}`]
  : ["--yes", "mcp-remote", mcpUrl, "--header", `Authorization: Bearer ${token}`];

const cmd = mcpRemoteBin ? process.execPath : "npx";
const child = spawn(cmd, args, { stdio: "inherit", env, shell: process.platform === "win32" });
child.on("exit", (code) => process.exit(code ?? 1));
