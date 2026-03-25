/**
 * Runs `prisma generate` without relying on `prisma` on PATH (fixes Vercel / npm --prefix).
 * Resolves the CLI from node_modules next to this package (works with hoisting).
 */
const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const appRoot = path.join(__dirname, "..");

function findPrismaCli() {
  const candidates = [
    path.join(appRoot, "node_modules", "prisma", "build", "index.js"),
    path.join(appRoot, "..", "node_modules", "prisma", "build", "index.js"),
  ];
  for (const p of candidates) {
    if (fs.existsSync(p)) return p;
  }
  throw new Error(
    "Could not find prisma CLI. Run npm install in the repo root (workspaces) or in care-app."
  );
}

const cli = findPrismaCli();
const result = spawnSync(process.execPath, [cli, "generate"], {
  stdio: "inherit",
  cwd: appRoot,
  env: process.env,
});

process.exit(result.status ?? 1);
