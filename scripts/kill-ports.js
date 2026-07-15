#!/usr/bin/env node
/**
 * Pre-dev port cleanup for Windows.
 *
 * Background: when `pnpm dev` is interrupted, the dev servers (uvicorn reloader,
 * Next.js) sometimes leave child processes holding ports 3000/8000. The next
 * `pnpm dev` fails with EADDRINUSE.
 *
 * This script finds whatever is listening on the target ports and terminates
 * the process (and any child process tree) before starting fresh.
 *
 * Usage: node scripts/kill-ports.js [port ...]
 * Defaults to the project's dev ports (3000, 8000).
 */

const { execSync } = require("node:child_process");
const os = require("node:os");

if (os.platform() !== "win32") {
  // No-op on POSIX — process groups work correctly there.
  process.exit(0);
}

const ports = process.argv.slice(2).map(Number).filter((n) => Number.isFinite(n) && n > 0);
if (ports.length === 0) ports.push(3000, 8000);

function findPids(port) {
  try {
    const out = execSync(`netstat -ano | findstr :${port}`, { encoding: "utf8" });
    const pids = new Set();
    for (const line of out.split(/\r?\n/)) {
      const m = line.match(/\s(\d+)\s*$/);
      if (m) pids.add(Number(m[1]));
    }
    return [...pids];
  } catch {
    return [];
  }
}

let killedAny = false;
for (const port of ports) {
  const pids = findPids(port);
  for (const pid of pids) {
    try {
      execSync(`taskkill /F /T /PID ${pid}`, { stdio: "ignore" });
      console.log(`[kill-ports] terminated PID ${pid} (was on port ${port})`);
      killedAny = true;
    } catch {
      // PID may have exited between findstr and taskkill; that's fine.
    }
  }
  if (pids.length === 0) {
    console.log(`[kill-ports] port ${port} is free`);
  }
}

// Give the OS a brief moment to release the sockets.
if (killedAny) {
  setTimeout(() => process.exit(0), 250);
} else {
  process.exit(0);
}
