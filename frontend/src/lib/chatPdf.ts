import type { ChatMessage } from "@/context/SupportContext";

interface DownloadChatPdfOptions {
  ticketId: string;
  messages: ChatMessage[];
}

interface PdfLine {
  text: string;
  color: string;
  font: string;
  spacing: number;
}

const PAGE_WIDTH = 1240;
const PAGE_HEIGHT = 1754;
const PDF_PAGE_WIDTH = 595;
const PDF_PAGE_HEIGHT = 842;
const MARGIN_X = 88;
const MARGIN_TOP = 110;
const MARGIN_BOTTOM = 96;

export async function downloadChatPdf({ ticketId, messages }: DownloadChatPdfOptions) {
  const pages = renderChatPages(ticketId, messages);
  const jpegPages = pages.map((canvas) => ({
    width: canvas.width,
    height: canvas.height,
    data: dataUrlToBytes(canvas.toDataURL("image/jpeg", 0.92)),
  }));

  const pdfBytes = buildPdfFromImages(jpegPages);
  const blob = new Blob([pdfBytes], { type: "application/pdf" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");

  link.href = url;
  link.download = `${ticketId || "support-chat"}.pdf`;
  link.click();

  setTimeout(() => {
    URL.revokeObjectURL(url);
  }, 1000);
}

function renderChatPages(ticketId: string, messages: ChatMessage[]) {
  const canvases: HTMLCanvasElement[] = [];
  const lines = buildLines(ticketId, messages);
  let canvas = createPageCanvas();
  let context = getCanvasContext(canvas);
  let y = MARGIN_TOP;

  for (const line of lines) {
    const isBlankLine = line.text.length === 0;
    const lineHeight = line.spacing;

    if (y + lineHeight > PAGE_HEIGHT - MARGIN_BOTTOM) {
      canvases.push(canvas);
      canvas = createPageCanvas();
      context = getCanvasContext(canvas);
      y = MARGIN_TOP;
    }

    if (!isBlankLine) {
      context.font = line.font;
      context.fillStyle = line.color;
      context.fillText(line.text, MARGIN_X, y);
    }

    y += lineHeight;
  }

  canvases.push(canvas);
  return canvases;
}

function buildLines(ticketId: string, messages: ChatMessage[]) {
  const measureCanvas = document.createElement("canvas");
  const context = getCanvasContext(measureCanvas);
  const lines: PdfLine[] = [];
  const contentWidth = PAGE_WIDTH - MARGIN_X * 2;
  const exportedAt = new Date().toLocaleString();

  lines.push({ text: "Support Chat Transcript", color: "#0f172a", font: "700 40px Arial", spacing: 58 });
  if (ticketId) {
    lines.push({ text: `Ticket: ${ticketId}`, color: "#334155", font: "600 24px Arial", spacing: 36 });
  }
  lines.push({ text: `Exported: ${exportedAt}`, color: "#64748b", font: "400 22px Arial", spacing: 34 });
  lines.push({ text: "", color: "#ffffff", font: "400 12px Arial", spacing: 24 });

  for (const message of messages) {
    const senderLabel = getSenderLabel(message.sender);
    const header = `${senderLabel}  ${message.timestamp}`;

    lines.push({ text: header, color: "#1e293b", font: "700 24px Arial", spacing: 34 });

    context.font = "400 24px Arial";
    for (const wrappedLine of wrapText(context, message.text, contentWidth)) {
      lines.push({
        text: wrappedLine,
        color: "#334155",
        font: "400 24px Arial",
        spacing: 34,
      });
    }

    lines.push({ text: "", color: "#ffffff", font: "400 12px Arial", spacing: 18 });
  }

  return lines;
}

function wrapText(context: CanvasRenderingContext2D, text: string, maxWidth: number) {
  if (!text.trim()) {
    return [""];
  }

  const words = text.split(/\s+/);
  const lines: string[] = [];
  let currentLine = "";

  for (const word of words) {
    const testLine = currentLine ? `${currentLine} ${word}` : word;

    if (context.measureText(testLine).width <= maxWidth) {
      currentLine = testLine;
      continue;
    }

    if (currentLine) {
      lines.push(currentLine);
      currentLine = "";
    }

    if (context.measureText(word).width <= maxWidth) {
      currentLine = word;
      continue;
    }

    for (const segment of splitLongWord(context, word, maxWidth)) {
      if (context.measureText(segment).width <= maxWidth) {
        if (!currentLine) {
          currentLine = segment;
        } else {
          lines.push(currentLine);
          currentLine = segment;
        }
      }
    }
  }

  if (currentLine) {
    lines.push(currentLine);
  }

  return lines;
}

function splitLongWord(context: CanvasRenderingContext2D, word: string, maxWidth: number) {
  const segments: string[] = [];
  let currentSegment = "";

  for (const char of [...word]) {
    const testSegment = `${currentSegment}${char}`;

    if (context.measureText(testSegment).width <= maxWidth || currentSegment.length === 0) {
      currentSegment = testSegment;
      continue;
    }

    segments.push(currentSegment);
    currentSegment = char;
  }

  if (currentSegment) {
    segments.push(currentSegment);
  }

  return segments;
}

function createPageCanvas() {
  const canvas = document.createElement("canvas");
  canvas.width = PAGE_WIDTH;
  canvas.height = PAGE_HEIGHT;
  const context = getCanvasContext(canvas);

  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, canvas.width, canvas.height);

  return canvas;
}

function getCanvasContext(canvas: HTMLCanvasElement) {
  const context = canvas.getContext("2d");

  if (!context) {
    throw new Error("Canvas is not available in this browser.");
  }

  context.textBaseline = "top";
  return context;
}

function getSenderLabel(sender: ChatMessage["sender"]) {
  if (sender === "user") return "You";
  if (sender === "agent") return "Live Agent";
  return "Help Bot";
}

function dataUrlToBytes(dataUrl: string) {
  const base64Value = dataUrl.split(",")[1] || "";
  const binary = atob(base64Value);
  const bytes = new Uint8Array(binary.length);

  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }

  return bytes;
}

function buildPdfFromImages(images: Array<{ width: number; height: number; data: Uint8Array }>) {
  const encoder = new TextEncoder();
  const chunks: Uint8Array[] = [];
  const offsets: number[] = [];
  let totalLength = 0;

  const pushString = (value: string) => {
    const bytes = encoder.encode(value);
    chunks.push(bytes);
    totalLength += bytes.length;
  };

  const pushBytes = (value: Uint8Array) => {
    chunks.push(value);
    totalLength += value.length;
  };

  const pushObjectStart = (objectNumber: number) => {
    offsets[objectNumber] = totalLength;
    pushString(`${objectNumber} 0 obj\n`);
  };

  const pageObjects = images.map((_, index) => ({
    page: 3 + index * 3,
    content: 4 + index * 3,
    image: 5 + index * 3,
  }));
  const lastObjectNumber = pageObjects.length === 0 ? 2 : pageObjects[pageObjects.length - 1].image;

  pushString("%PDF-1.4\n");
  pushBytes(new Uint8Array([37, 255, 255, 255, 255, 10]));

  pushObjectStart(1);
  pushString("<< /Type /Catalog /Pages 2 0 R >>\nendobj\n");

  pushObjectStart(2);
  pushString(`<< /Type /Pages /Count ${images.length} /Kids [${pageObjects.map((entry) => `${entry.page} 0 R`).join(" ")}] >>\nendobj\n`);

  images.forEach((image, index) => {
    const refs = pageObjects[index];
    const contentStream = `q\n${PDF_PAGE_WIDTH} 0 0 ${PDF_PAGE_HEIGHT} 0 0 cm\n/Im0 Do\nQ\n`;

    pushObjectStart(refs.page);
    pushString(
      `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${PDF_PAGE_WIDTH} ${PDF_PAGE_HEIGHT}] /Resources << /XObject << /Im0 ${refs.image} 0 R >> >> /Contents ${refs.content} 0 R >>\nendobj\n`,
    );

    pushObjectStart(refs.content);
    pushString(`<< /Length ${contentStream.length} >>\nstream\n${contentStream}endstream\nendobj\n`);

    pushObjectStart(refs.image);
    pushString(
      `<< /Type /XObject /Subtype /Image /Width ${image.width} /Height ${image.height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${image.data.length} >>\nstream\n`,
    );
    pushBytes(image.data);
    pushString("\nendstream\nendobj\n");
  });

  const xrefOffset = totalLength;
  pushString(`xref\n0 ${lastObjectNumber + 1}\n`);
  pushString("0000000000 65535 f \n");

  for (let objectNumber = 1; objectNumber <= lastObjectNumber; objectNumber += 1) {
    const offset = offsets[objectNumber] ?? 0;
    pushString(`${String(offset).padStart(10, "0")} 00000 n \n`);
  }

  pushString(`trailer\n<< /Size ${lastObjectNumber + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF`);

  return joinChunks(chunks, totalLength);
}

function joinChunks(chunks: Uint8Array[], totalLength: number) {
  const result = new Uint8Array(totalLength);
  let offset = 0;

  for (const chunk of chunks) {
    result.set(chunk, offset);
    offset += chunk.length;
  }

  return result;
}
