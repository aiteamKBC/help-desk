import { mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { spawn } from "node:child_process";

const [url, outputPath, widthText, heightText, portText] = process.argv.slice(2);
const width = Number(widthText);
const height = Number(heightText);
const debuggerPort = Number(portText);
const chromePath = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const profilePath = resolve(tmpdir(), `kbc-support-wave-${debuggerPort}`);
const keepAlive = setInterval(() => {}, 1000);
const chrome = spawn(chromePath, [
  "--headless=new",
  "--disable-gpu",
  "--hide-scrollbars",
  "--no-first-run",
  "--no-default-browser-check",
  `--remote-debugging-port=${debuggerPort}`,
  `--user-data-dir=${profilePath}`,
  `--window-size=${width},${height}`,
  "about:blank",
], { stdio: "ignore" });

const delay = (milliseconds) => new Promise((resolveDelay) => setTimeout(resolveDelay, milliseconds));

async function findPage() {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    try {
      const pages = await fetch(`http://127.0.0.1:${debuggerPort}/json`).then((response) => response.json());
      const page = pages.find((candidate) => candidate.type === "page");
      if (page) return page;
    } catch {
      // Chrome is still starting.
    }
    await delay(100);
  }
  throw new Error("Chrome debugging endpoint did not become available");
}

try {
  const page = await findPage();
  const socket = new WebSocket(page.webSocketDebuggerUrl);
  const pending = new Map();
  let id = 0;

  await new Promise((resolveOpen, rejectOpen) => {
    socket.addEventListener("open", resolveOpen, { once: true });
    socket.addEventListener("error", rejectOpen, { once: true });
  });

  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    const request = pending.get(message.id);
    if (!request) return;
    pending.delete(message.id);
    if (message.error) request.reject(new Error(message.error.message));
    else request.resolve(message.result);
  });

  const send = (method, params = {}) => new Promise((resolveCommand, rejectCommand) => {
    id += 1;
    pending.set(id, { resolve: resolveCommand, reject: rejectCommand });
    socket.send(JSON.stringify({ id, method, params }));
  });

  await send("Page.enable");
  await send("Runtime.enable");
  await send("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile: width <= 430,
  });
  await send("Page.navigate", { url });
  await delay(1600);

  const inspection = await send("Runtime.evaluate", {
    expression: `(() => {
      const selectors = [
        ".support-landing-main",
        ".support-hero",
        ".support-hero-wave",
        ".support-wave-ribbons",
        ".support-wave-photo",
        ".support-wave-layer-purple",
        ".support-wave-layer-lavender",
        ".support-wave-layer-soft",
        ".support-entry"
      ];
      const properties = [
        "position", "display", "width", "height", "minHeight", "maxHeight",
        "overflow", "overflowX", "overflowY", "transform", "clipPath", "opacity",
        "zIndex", "background", "objectFit", "objectPosition", "aspectRatio", "filter"
      ];
      const results = Object.fromEntries(selectors.map((selector) => {
        const element = document.querySelector(selector);
        if (!element) return [selector, null];
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return [selector, {
          rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
          style: Object.fromEntries(properties.map((property) => [property, style[property]])),
          viewBox: element.getAttribute("viewBox"),
          preserveAspectRatio: element.getAttribute("preserveAspectRatio")
        }];
      }));
      return JSON.stringify({
        viewport: [innerWidth, innerHeight],
        document: [document.documentElement.scrollWidth, document.documentElement.scrollHeight],
        results
      });
    })()`,
    returnByValue: true,
  });

  const screenshot = await send("Page.captureScreenshot", {
    format: "png",
    captureBeyondViewport: false,
    fromSurface: true,
  });
  mkdirSync(dirname(resolve(outputPath)), { recursive: true });
  writeFileSync(resolve(outputPath), Buffer.from(screenshot.data, "base64"));
  process.stdout.write(`${inspection.result.value}\n`);
  socket.close();
} finally {
  clearInterval(keepAlive);
  chrome.kill();
}
