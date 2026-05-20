export const KNOWLEDGE_BASE_APP_VERSION = "support-knowledge-base-v1";
export const KNOWLEDGE_BASE_DRAFT_STORAGE_KEY = "support_knowledge_base_draft_v1";
export const KNOWLEDGE_BASE_SECTION_KEYS = ["inquiry", "summary", "steps", "resources"] as const;

export type KnowledgeBaseSectionKey = (typeof KNOWLEDGE_BASE_SECTION_KEYS)[number];

export type KnowledgeBaseAttachment = {
  id: string;
  name: string;
  type: string;
  size?: number;
  evidencePath?: string;
  dataUrl?: string;
  url?: string;
};

export type KnowledgeBaseArticleData = {
  schema: string;
  version: string;
  title: string;
  keywords: string;
  createdAt: string;
  updatedAt: string;
  exportedAt?: string;
  sections: Record<KnowledgeBaseSectionKey, string>;
  attachments: Record<KnowledgeBaseSectionKey, KnowledgeBaseAttachment[]>;
};

export type KnowledgeBaseArticleIndexItem = {
  id: string;
  title: string;
  keywords: string;
  fileName: string;
  path: string;
  source: string;
  json?: string;
  html?: string;
  sections: Partial<Record<KnowledgeBaseSectionKey, string>>;
  attachments: Partial<Record<KnowledgeBaseSectionKey, KnowledgeBaseAttachment[]>>;
  createdAt: string;
  updatedAt: string;
  exportedAt?: string;
};

export const KNOWLEDGE_BASE_SECTIONS: Array<{
  key: KnowledgeBaseSectionKey;
  heading: string;
  label: string;
  badge: string;
  placeholder: string;
}> = [
  {
    key: "inquiry",
    heading: "1. Inquiry",
    label: "Inquiry",
    badge: "Question",
    placeholder: "State the user question or problem this article answers.",
  },
  {
    key: "summary",
    heading: "2. Summary",
    label: "Summary",
    badge: "Short answer",
    placeholder: "Give the short answer first.",
  },
  {
    key: "steps",
    heading: "3. Steps",
    label: "Steps",
    badge: "Instructions",
    placeholder: "1. Open ...\n2. Select ...\n3. Confirm ...\nExpected result: ...\nIf it fails: ...",
  },
  {
    key: "resources",
    heading: "4. Resources",
    label: "Resources",
    badge: "Links and sources",
    placeholder: "Source link 1: ...\nSource link 2: ...\nRelated article: ...",
  },
];

const STATIC_ARTICLE_STYLES = `
  :root {
    --bg: #f6f7fb;
    --panel: #ffffff;
    --text: #172033;
    --muted: #667085;
    --border: #d9e0ec;
    --accent: #5b3f8c;
    --soft: #f4f0fa;
    --radius: 18px;
    --shadow: 0 10px 28px rgba(16, 24, 40, 0.08);
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: Arial, Helvetica, sans-serif;
    background: linear-gradient(180deg, #fbfcff, var(--bg));
    color: var(--text);
  }
  .static-body {
    max-width: 980px;
    margin: 28px auto 60px;
    padding: 0 18px;
  }
  .static-top,
  .static-section {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
  }
  .static-top {
    padding: 26px;
    margin-bottom: 18px;
  }
  .static-section {
    padding: 24px;
    margin-bottom: 16px;
  }
  .static-section h2 {
    margin-top: 0;
  }
  .static-section h3 {
    margin-bottom: 8px;
    font-size: 15px;
  }
  .static-content {
    white-space: pre-wrap;
    line-height: 1.6;
    border-left: 4px solid var(--accent);
    padding: 10px 14px;
    background: #fbfcff;
    border-radius: 10px;
  }
  .static-content a {
    color: var(--accent);
    font-weight: 700;
    overflow-wrap: anywhere;
  }
  .static-att-grid {
    display: grid;
    gap: 10px;
  }
  .badge {
    display: inline-block;
    border-radius: 999px;
    background: var(--soft);
    border: 1px solid #e7ddf5;
    color: var(--accent);
    padding: 5px 10px;
    font-size: 12px;
    font-weight: 700;
  }
  .subtitle,
  .hint {
    color: var(--muted);
    line-height: 1.45;
  }
  .attachment-item {
    display: grid;
    grid-template-columns: 58px minmax(0, 1fr) auto;
    gap: 10px;
    align-items: center;
    padding: 10px;
    border: 1px solid var(--border);
    border-radius: 14px;
    background: #ffffff;
  }
  .thumb {
    width: 58px;
    height: 46px;
    border: 1px solid var(--border);
    border-radius: 10px;
    object-fit: cover;
    background: #f2f4f7;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    color: var(--muted);
  }
  .att-name {
    font-weight: 700;
    word-break: break-word;
  }
  .att-meta {
    font-size: 12px;
    color: var(--muted);
    margin-top: 3px;
  }
  .att-actions {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }
  .file-btn {
    border: 0;
    border-radius: 12px;
    background: #eef1f6;
    color: var(--text);
    font-weight: 700;
    padding: 10px 12px;
    text-decoration: none;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
  .image-attachment {
    border: 1px solid var(--border);
    border-radius: 14px;
    background: #ffffff;
    padding: 10px;
  }
  .image-attachment summary {
    cursor: pointer;
    font-weight: 700;
    color: var(--text);
    padding: 4px;
  }
  .image-frame {
    width: 100%;
    height: min(70vh, 720px);
    min-height: 420px;
    border: 1px solid var(--border);
    border-radius: 12px;
    background: #f8fafc;
    margin-top: 10px;
  }
`;

function createEmptyAttachmentMap(): Record<KnowledgeBaseSectionKey, KnowledgeBaseAttachment[]> {
  return {
    inquiry: [],
    summary: [],
    steps: [],
    resources: [],
  };
}

function createEmptySectionMap(): Record<KnowledgeBaseSectionKey, string> {
  return {
    inquiry: "",
    summary: "",
    steps: "",
    resources: "",
  };
}

function deepClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value));
}

function escapeHtml(value: unknown): string {
  return String(value ?? "").replace(/[&<>"']/g, (char) => {
    switch (char) {
      case "&":
        return "&amp;";
      case "<":
        return "&lt;";
      case ">":
        return "&gt;";
      case '"':
        return "&quot;";
      case "'":
        return "&#039;";
      default:
        return char;
    }
  });
}

export function linkifyText(value: unknown): string {
  const text = String(value ?? "");
  const urlRegex = /\bhttps?:\/\/[^\s<>"']+/gi;
  let html = "";
  let lastIndex = 0;
  let match: RegExpExecArray | null = null;

  while ((match = urlRegex.exec(text))) {
    let url = match[0];
    let end = urlRegex.lastIndex;
    while (/[.,;:!?)]$/.test(url)) {
      url = url.slice(0, -1);
      end -= 1;
    }

    html += escapeHtml(text.slice(lastIndex, match.index));
    html += `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(url)}</a>`;
    lastIndex = end;
    urlRegex.lastIndex = end;
  }

  return html + escapeHtml(text.slice(lastIndex));
}

export function createEmptyArticle(): KnowledgeBaseArticleData {
  return {
    schema: "kb-article-builder",
    version: KNOWLEDGE_BASE_APP_VERSION,
    title: "",
    keywords: "",
    createdAt: "",
    updatedAt: "",
    exportedAt: "",
    sections: createEmptySectionMap(),
    attachments: createEmptyAttachmentMap(),
  };
}

export function createAttachmentId(): string {
  return `att_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`;
}

export function safeFileName(name: string | undefined | null, fallback = "attachment"): string {
  const normalized = String(name ?? fallback)
    .split(/[\\/]/)
    .pop()
    ?.replace(/[^a-z0-9._-]+/gi, "-")
    .replace(/^-+|-+$/g, "");
  return normalized || fallback;
}

export function safeArticleSlug(name: string | undefined | null): string {
  const normalized = String(name ?? "knowledge-base-article")
    .trim()
    .replace(/[^a-z0-9]+/gi, "-")
    .replace(/^-+|-+$/g, "")
    .toLowerCase();
  return normalized || "knowledge-base-article";
}

function getCreatedAt(data: Record<string, unknown>): string {
  return String(data.createdAt || data.exportedAt || "");
}

function getUpdatedAt(data: Record<string, unknown>): string {
  return String(data.updatedAt || data.editedAt || "");
}

export function normalizeArticleData(data: Record<string, unknown> | null | undefined): KnowledgeBaseArticleData {
  const source = data && typeof data === "object" ? data : {};
  const sections = createEmptySectionMap();
  const attachments = createEmptyAttachmentMap();

  for (const key of KNOWLEDGE_BASE_SECTION_KEYS) {
    sections[key] = String((source.sections as Record<string, unknown> | undefined)?.[key] ?? source[key] ?? "");
    const nextAttachments = (source.attachments as Record<string, KnowledgeBaseAttachment[] | undefined> | undefined)?.[key];
    attachments[key] = Array.isArray(nextAttachments) ? deepClone(nextAttachments) : [];
  }

  return {
    schema: String(source.schema || "kb-article-builder"),
    version: String(source.version || KNOWLEDGE_BASE_APP_VERSION),
    title: String(source.title || source.articleTitle || ""),
    keywords: String(source.keywords || ""),
    createdAt: getCreatedAt(source),
    updatedAt: getUpdatedAt(source),
    exportedAt: String(source.exportedAt || ""),
    sections,
    attachments,
  };
}

function parseJsonText(raw: string): Record<string, unknown> {
  try {
    return JSON.parse(String(raw || "").replace(/^\uFEFF/, "").trim());
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown JSON parsing error.";
    throw new Error(`The file could not be parsed as article JSON. ${message}`);
  }
}

export function parseArticleFromHtml(html: string): KnowledgeBaseArticleData {
  const documentFragment = new DOMParser().parseFromString(String(html || ""), "text/html");
  const template = documentFragment.getElementById("kb-article-json");
  if (template?.textContent) {
    return normalizeArticleData(parseJsonText(template.textContent));
  }

  const script = documentFragment.querySelector(
    'script[type="application/json"][data-kb-article], script#kb-article-data',
  );
  if (script?.textContent) {
    return normalizeArticleData(parseJsonText(script.textContent));
  }

  throw new Error("This HTML file is not a valid exported article from this builder.");
}

export function parseArticleContent(text: string, fileName: string): KnowledgeBaseArticleData {
  const cleaned = String(text || "").replace(/^\uFEFF/, "").trim();
  const lowerName = String(fileName || "").toLowerCase();
  const looksLikeHtml =
    lowerName.endsWith(".html") ||
    lowerName.endsWith(".htm") ||
    /^<!doctype html|^<html[\s>]/i.test(cleaned) ||
    cleaned.includes("kb-article-json");

  return looksLikeHtml ? parseArticleFromHtml(cleaned) : normalizeArticleData(parseJsonText(cleaned));
}

export function prepareArticleForSave(article: KnowledgeBaseArticleData): KnowledgeBaseArticleData {
  const clean = deepClone(article);
  for (const section of KNOWLEDGE_BASE_SECTION_KEYS) {
    clean.attachments[section] = (clean.attachments[section] || []).map((attachment) => {
      if (attachment.dataUrl && !attachment.evidencePath && !attachment.url) {
        return {
          ...attachment,
          evidencePath: `Evidence/${safeFileName(attachment.name || "attachment")}`,
        };
      }
      return attachment;
    });
  }
  return clean;
}

export function stripEmbeddedAttachmentData(article: KnowledgeBaseArticleData): KnowledgeBaseArticleData {
  const clean = deepClone(article);
  for (const section of KNOWLEDGE_BASE_SECTION_KEYS) {
    clean.attachments[section] = (clean.attachments[section] || []).map((attachment) => {
      if (attachment.evidencePath) {
        const { dataUrl, ...rest } = attachment;
        void dataUrl;
        return rest;
      }
      return attachment;
    });
  }
  return clean;
}

export function buildEvidencePayload(article: KnowledgeBaseArticleData) {
  const evidence: Array<{ name: string; dataUrl: string }> = [];
  for (const section of KNOWLEDGE_BASE_SECTION_KEYS) {
    for (const attachment of article.attachments[section] || []) {
      if (attachment.dataUrl && attachment.evidencePath) {
        evidence.push({
          name: attachment.evidencePath.replace(/^Evidence\//, ""),
          dataUrl: attachment.dataUrl,
        });
      }
    }
  }
  return evidence;
}

export function chooseArticleFilename(
  article: KnowledgeBaseArticleData,
  existingArticles: KnowledgeBaseArticleIndexItem[],
  currentFileName?: string,
): string {
  if (currentFileName) {
    return currentFileName;
  }

  const baseName = safeArticleSlug(article.title || "knowledge-base-article");
  let candidate = `${baseName}.html`;
  let counter = 2;
  while (existingArticles.some((item) => item.fileName.toLowerCase() === candidate.toLowerCase())) {
    candidate = `${baseName}-${counter}.html`;
    counter += 1;
  }
  return candidate;
}

export function formatBytes(bytes: number | undefined): string {
  const value = Number(bytes || 0);
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1048576) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / 1048576).toFixed(1)} MB`;
}

export function formatKnowledgeBaseDate(value: string | undefined): string {
  const date = value ? new Date(value) : null;
  return date && !Number.isNaN(date.getTime()) ? date.toLocaleString() : "";
}

function resolveStaticAttachmentSource(attachment: KnowledgeBaseAttachment): string {
  if (attachment.url) {
    return attachment.url;
  }
  if (attachment.evidencePath) {
    return `../${attachment.evidencePath}`;
  }
  return attachment.dataUrl || "";
}

function buildStaticAttachmentHtml(attachment: KnowledgeBaseAttachment): string {
  const source = resolveStaticAttachmentSource(attachment);
  const isImage =
    attachment.type.startsWith("image/") ||
    /\.(png|jpe?g|gif|webp|svg)$/i.test(source) ||
    source.startsWith("data:image/");

  if (isImage && source) {
    const frameDocument = [
      "<!doctype html><html><head><meta charset=\"utf-8\">",
      "<style>html,body{width:100%;height:100%;margin:0;background:#f8fafc}body{display:grid;place-items:center;overflow:hidden}",
      "img{display:block;max-width:100%;max-height:100%;width:auto;height:auto;object-fit:contain}</style></head>",
      `<body><img src="${escapeHtml(source)}" alt="${escapeHtml(attachment.name || "Image attachment")}"></body></html>`,
    ].join("");
    return [
      "<details class=\"image-attachment\" open>",
      `<summary>${escapeHtml(attachment.name || "Image attachment")}</summary>`,
      `<iframe class="image-frame" srcdoc="${escapeHtml(frameDocument)}" title="${escapeHtml(attachment.name || "Image attachment")}"></iframe>`,
      '<div class="att-actions">',
      `<a class="file-btn" href="${escapeHtml(source)}" target="_blank" rel="noopener noreferrer">Open</a>`,
      attachment.dataUrl
        ? `<a class="file-btn" href="${attachment.dataUrl}" download="${escapeHtml(attachment.name || "attachment")}">Download</a>`
        : "",
      "</div>",
      "</details>",
    ].join("");
  }

  return [
    '<div class="attachment-item">',
    `<div class="thumb">${isImage ? `<img class="thumb" src="${escapeHtml(source)}" alt="${escapeHtml(attachment.name || "Attachment")}">` : "File"}</div>`,
    "<div>",
    `<div class="att-name">${escapeHtml(attachment.name || attachment.url || "Attachment")}</div>`,
    `<div class="att-meta">${escapeHtml(attachment.type || "link")}${attachment.size ? ` - ${escapeHtml(formatBytes(attachment.size))}` : ""}</div>`,
    "</div>",
    '<div class="att-actions">',
    `<a class="file-btn" href="${escapeHtml(source || "#")}" target="_blank" rel="noopener noreferrer">Open</a>`,
    attachment.dataUrl
      ? `<a class="file-btn" href="${attachment.dataUrl}" download="${escapeHtml(attachment.name || "attachment")}">Download</a>`
      : "",
    "</div>",
    "</div>",
  ].join("");
}

export function createStaticHtml(article: KnowledgeBaseArticleData): string {
  const created = formatKnowledgeBaseDate(article.createdAt || article.exportedAt || new Date().toISOString());
  const updated = formatKnowledgeBaseDate(article.updatedAt);
  const dateMarkup = [
    created ? `<p class="hint">Created: ${escapeHtml(created)}</p>` : "",
    updated ? `<p class="hint">Edited: ${escapeHtml(updated)}</p>` : "",
  ].join("");

  const sectionsMarkup = KNOWLEDGE_BASE_SECTIONS.map((section) => {
    const sectionAttachments = article.attachments[section.key] || [];
    const attachmentMarkup = sectionAttachments.length
      ? sectionAttachments.map((attachment) => buildStaticAttachmentHtml(attachment)).join("")
      : '<p class="hint">No attachments added.</p>';
    return [
      '<section class="static-section">',
      `<h2>${escapeHtml(section.heading)}</h2>`,
      `<div class="static-content">${linkifyText(article.sections[section.key] || "")}</div>`,
      "<h3>Attachments</h3>",
      `<div class="static-att-grid">${attachmentMarkup}</div>`,
      "</section>",
    ].join("");
  }).join("");

  return [
    "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">",
    '<meta name="viewport" content="width=device-width, initial-scale=1">',
    `<title>${escapeHtml(article.title || "Knowledge Base Article")}</title>`,
    `<style>${STATIC_ARTICLE_STYLES}</style>`,
    "</head><body>",
    '<div class="static-body">',
    '<div class="static-top">',
    '<span class="badge">Knowledge Base Article</span>',
    `<h1>${escapeHtml(article.title || "Untitled article")}</h1>`,
    `<p class="subtitle"><strong>Keywords:</strong> ${escapeHtml(article.keywords || "")}</p>`,
    dateMarkup,
    "</div>",
    sectionsMarkup,
    "</div>",
    `<template id="kb-article-json">${escapeHtml(JSON.stringify(article))}</template>`,
    "</body></html>",
  ].join("");
}

export function readTextFile(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error || new Error("Failed to read file."));
    reader.readAsText(file);
  });
}

export function readDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error || new Error("Failed to read file."));
    reader.readAsDataURL(file);
  });
}

function encodePath(value: string): string {
  return value
    .split("/")
    .filter(Boolean)
    .map((segment) => encodeURIComponent(segment))
    .join("/");
}

export function buildKnowledgeBaseAssetUrl(assetPath: string | undefined): string {
  const source = String(assetPath || "");
  if (!source) {
    return "";
  }
  if (/^(https?:|data:|blob:)/i.test(source)) {
    return source;
  }
  return `/api/knowledge-base/assets/${encodePath(source.replace(/^\/+/, ""))}`;
}

export function resolveAttachmentUrl(attachment: KnowledgeBaseAttachment): string {
  if (attachment.url) {
    return attachment.url;
  }
  if (attachment.evidencePath) {
    return buildKnowledgeBaseAssetUrl(attachment.evidencePath);
  }
  return attachment.dataUrl || "";
}

export function buildKnowledgeBaseArticleUrl(fileName: string): string {
  return `/knowledge-base/articles/${encodeURIComponent(fileName)}`;
}

export function buildArticleSearchText(article: KnowledgeBaseArticleIndexItem): string {
  const parts = [article.title, article.keywords, article.fileName];
  for (const section of KNOWLEDGE_BASE_SECTION_KEYS) {
    parts.push(article.sections?.[section] || "");
  }
  return parts.join(" ").toLowerCase();
}

async function requestJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  const payload = await response.json();
  if (!response.ok || !payload.ok) {
    throw new Error(payload.error || payload.message || "Request failed.");
  }
  return payload as T;
}

export async function fetchKnowledgeBaseArticles(): Promise<KnowledgeBaseArticleIndexItem[]> {
  const payload = await requestJson<{ ok: true; articles: KnowledgeBaseArticleIndexItem[] }>(
    "/api/knowledge-base/articles",
    { cache: "no-store" },
  );
  return payload.articles || [];
}

export async function fetchKnowledgeBaseArticle(fileName: string): Promise<KnowledgeBaseArticleIndexItem> {
  const payload = await requestJson<{ ok: true; article: KnowledgeBaseArticleIndexItem }>(
    `/api/knowledge-base/articles/${encodeURIComponent(fileName)}`,
    { cache: "no-store" },
  );
  return payload.article;
}

export async function saveKnowledgeBaseArticle(payload: {
  filename: string;
  html: string;
  evidence: Array<{ name: string; dataUrl: string }>;
}) {
  return requestJson<{
    ok: true;
    path: string;
    article: KnowledgeBaseArticleIndexItem;
  }>("/api/knowledge-base/articles", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export async function archiveKnowledgeBaseArticle(filename: string) {
  return requestJson<{ ok: true; path: string }>("/api/knowledge-base/articles", {
    method: "DELETE",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ filename }),
  });
}
