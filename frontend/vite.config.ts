import { execFileSync, spawn, type ChildProcess } from "node:child_process";
import { existsSync } from "node:fs";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { defineConfig } from "vite";
import { componentTagger } from "lovable-tagger";

const DEV_HOST = "127.0.0.1";
const FRONTEND_PORT = 3000;
const requestedBackendPort = Number(process.env.SUPPORT_BACKEND_PORT || 8000);
const configuredBackendPort = Number.isInteger(requestedBackendPort)
  && requestedBackendPort > 0
  && requestedBackendPort < 65536
  ? requestedBackendPort
  : 8000;
const BACKEND_PORT_CANDIDATES = [configuredBackendPort];
let backendUrl = `http://${DEV_HOST}:${configuredBackendPort}`;
const BACKEND_ROOT = path.resolve(__dirname, "../backend");

let managedBackendProcess: ChildProcess | null = null;
let cleanupRegistered = false;

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function isBackendHealthy(url = backendUrl) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 1500);

  try {
    const response = await fetch(`${url}/api/health`, { signal: controller.signal });
    return response.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timeoutId);
  }
}

function resolveBackendPythonExecutable() {
  const windowsPython = path.join(BACKEND_ROOT, ".venv", "Scripts", "python.exe");
  if (existsSync(windowsPython)) {
    return windowsPython;
  }

  const unixPython = path.join(BACKEND_ROOT, ".venv", "bin", "python");
  if (existsSync(unixPython)) {
    return unixPython;
  }

  // Keep local development usable when the project virtualenv has not been
  // created yet. The machine Python is still a valid fallback as long as the
  // backend requirements are installed there.
  return process.platform === "win32" ? "python.exe" : "python";
}

function stopManagedBackend() {
  const pid = managedBackendProcess?.pid;
  if (!pid) {
    managedBackendProcess = null;
    return;
  }

  try {
    if (process.platform === "win32") {
      execFileSync("taskkill", ["/PID", String(pid), "/T", "/F"], { stdio: "ignore" });
    } else {
      managedBackendProcess.kill("SIGTERM");
    }
  } catch {
    // Ignore shutdown errors because the process may have already exited.
  } finally {
    managedBackendProcess = null;
  }
}

function registerBackendCleanup() {
  if (cleanupRegistered) {
    return;
  }

  cleanupRegistered = true;

  const shutdown = () => {
    stopManagedBackend();
    process.exit(0);
  };

  process.once("SIGINT", shutdown);
  process.once("SIGTERM", shutdown);
  process.once("exit", stopManagedBackend);
}

async function waitForBackendReady(timeoutMs: number) {
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    if (await isBackendHealthy()) {
      return true;
    }

    if (managedBackendProcess?.exitCode !== null && managedBackendProcess?.exitCode !== undefined) {
      return false;
    }

    await sleep(1000);
  }

  return false;
}

async function ensureBackendReady() {
  if (process.env.SUPPORT_AUTO_START_BACKEND === "0") {
    return;
  }

  const pythonExecutable = resolveBackendPythonExecutable();
  for (const port of BACKEND_PORT_CANDIDATES) {
    backendUrl = `http://${DEV_HOST}:${port}`;

    if (await isBackendHealthy()) {
      console.log(`[support-dev] Using the existing Django backend at ${backendUrl}.`);
      return;
    }

    console.log(`[support-dev] Starting Django backend on ${backendUrl}...`);
    managedBackendProcess = spawn(
      pythonExecutable,
      ["manage.py", "runserver", `${DEV_HOST}:${port}`],
      {
        cwd: BACKEND_ROOT,
        stdio: "inherit",
        windowsHide: true,
      },
    );

    registerBackendCleanup();

    if (await waitForBackendReady(5000)) {
      return;
    }

    stopManagedBackend();
  }

  console.warn(
    `[support-dev] Django backend is unavailable on ${BACKEND_PORT_CANDIDATES.join(" or ")}. Start it manually or set SUPPORT_BACKEND_PORT to an available port.`,
  );
}

// https://vitejs.dev/config/
export default defineConfig(async ({ mode, command }) => {
  if (command === "serve") {
    await ensureBackendReady();
  }

  return {
    server: {
      host: DEV_HOST,
      port: FRONTEND_PORT,
      hmr: {
        overlay: false,
      },
      proxy: {
        "/api": {
          target: backendUrl,
          changeOrigin: true,
        },
      },
    },
    plugins: [react(), mode === "development" && componentTagger()].filter(Boolean),
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
      dedupe: ["react", "react-dom", "react/jsx-runtime", "react/jsx-dev-runtime", "@tanstack/react-query", "@tanstack/query-core"],
    },
  };
});
