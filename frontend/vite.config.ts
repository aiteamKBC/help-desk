import { execFileSync, spawn, type ChildProcess } from "node:child_process";
import { existsSync } from "node:fs";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { defineConfig } from "vite";
import { componentTagger } from "lovable-tagger";

const DEV_HOST = "127.0.0.1";
const FRONTEND_PORT = 3000;
const BACKEND_PORT = 3001;
const BACKEND_URL = `http://${DEV_HOST}:${BACKEND_PORT}`;
const BACKEND_HEALTH_URL = `${BACKEND_URL}/api/health`;
const BACKEND_ROOT = path.resolve(__dirname, "../backend");

let managedBackendProcess: ChildProcess | null = null;
let cleanupRegistered = false;

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function isBackendHealthy() {
  try {
    const response = await fetch(BACKEND_HEALTH_URL);
    return response.ok;
  } catch {
    return false;
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

  return null;
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

  if (await isBackendHealthy()) {
    return;
  }

  const pythonExecutable = resolveBackendPythonExecutable();
  if (!pythonExecutable) {
    console.warn(
      `[support-dev] Django backend is offline and no virtualenv Python was found under ${BACKEND_ROOT}. Start the backend manually or create backend/.venv first.`,
    );
    return;
  }

  console.log(`[support-dev] Starting Django backend on ${BACKEND_URL}...`);

  managedBackendProcess = spawn(
    pythonExecutable,
    ["manage.py", "runserver", `${DEV_HOST}:${BACKEND_PORT}`],
    {
      cwd: BACKEND_ROOT,
      stdio: "inherit",
      windowsHide: true,
    },
  );

  registerBackendCleanup();

  const ready = await waitForBackendReady(30000);
  if (!ready) {
    console.warn(
      "[support-dev] Django backend did not become ready within 30 seconds. Check the backend logs above if the API still appears offline.",
    );
  }
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
          target: BACKEND_URL,
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
