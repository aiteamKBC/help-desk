export interface ChatAttachment {
  id: string;
  name: string;
  mimeType?: string | null;
  size: number;
  storageUrl?: string | null;
  previewUrl?: string | null;
  file?: File;
}

export interface ChatMessageLike {
  id?: string;
  clientMessageId?: string;
  sender: "bot" | "user" | "agent";
  source?: "message" | "history_event" | "intro";
  text: string;
  timestamp: string;
  attachments?: ChatAttachment[];
}

interface SerializedChatAttachment {
  clientAttachmentId: string;
  name: string;
  mimeType?: string | null;
  size: number;
  storageUrl?: string | null;
}

export const supportChatAttachmentAccept = ".jpg,.jpeg,.png,.gif,.webp,.bmp,.svg,.pdf,.mp4,.mov,.avi,.mkv,.webm,image/*,video/*,application/pdf";

export function createPendingChatAttachment(file: File): ChatAttachment {
  return {
    id: crypto.randomUUID(),
    name: file.name || "attachment",
    mimeType: file.type || null,
    size: file.size,
    previewUrl: typeof URL !== "undefined" ? URL.createObjectURL(file) : null,
    file,
  };
}

export function normalizeChatAttachments(attachments: ChatAttachment[] | undefined | null): ChatAttachment[] {
  if (!Array.isArray(attachments)) {
    return [];
  }

  const seenIds = new Set<string>();
  const normalizedAttachments: ChatAttachment[] = [];
  for (const attachment of attachments) {
    const nextId = attachment?.id?.trim();
    if (!nextId || seenIds.has(nextId)) {
      continue;
    }

    seenIds.add(nextId);
    normalizedAttachments.push({
      id: nextId,
      name: attachment.name || "attachment",
      mimeType: attachment.mimeType || null,
      size: Number.isFinite(attachment.size) ? Math.max(0, attachment.size) : 0,
      storageUrl: attachment.storageUrl || null,
      previewUrl: attachment.previewUrl || null,
      ...(attachment.file ? { file: attachment.file } : {}),
    });
  }

  return normalizedAttachments;
}

function serializeChatAttachment(attachment: ChatAttachment): SerializedChatAttachment {
  return {
    clientAttachmentId: attachment.id,
    name: attachment.name || "attachment",
    mimeType: attachment.mimeType || null,
    size: Number.isFinite(attachment.size) ? Math.max(0, attachment.size) : 0,
    storageUrl: attachment.storageUrl || null,
  };
}

function getSerializableMessages(messages: ChatMessageLike[]) {
  const serializedMessages: Array<{
    sender: "bot" | "user" | "agent";
    text: string;
    timestamp: string;
    clientMessageId: string;
    attachments: SerializedChatAttachment[];
  }> = [];
  const pendingFiles: File[] = [];

  for (const message of messages) {
    if (message.source === "history_event" || message.source === "intro") {
      continue;
    }

    const attachments = normalizeChatAttachments(message.attachments);
    serializedMessages.push({
      sender: message.sender,
      text: message.text,
      timestamp: message.timestamp,
      clientMessageId: message.clientMessageId || message.id || crypto.randomUUID(),
      attachments: attachments.map((attachment) => {
        if (!attachment.storageUrl && attachment.file) {
          pendingFiles.push(attachment.file);
        }
        return serializeChatAttachment(attachment);
      }),
    });
  }

  return { serializedMessages, pendingFiles };
}

export function serializeChatHistory(messages: ChatMessageLike[]) {
  return getSerializableMessages(messages).serializedMessages;
}

export function buildChatRequestBody(
  fields: Record<string, string | number | boolean | null | undefined>,
  messages: ChatMessageLike[],
  attachmentFieldName = "attachmentFiles",
) {
  const { serializedMessages, pendingFiles } = getSerializableMessages(messages);
  const payload = {
    ...Object.fromEntries(
      Object.entries(fields).filter(([, value]) => value !== undefined && value !== null),
    ),
    messages: serializedMessages,
  };

  if (pendingFiles.length === 0) {
    return {
      body: JSON.stringify(payload),
      headers: {
        "Content-Type": "application/json",
      },
    };
  }

  const formData = new FormData();
  for (const [key, value] of Object.entries(fields)) {
    if (value === undefined || value === null) {
      continue;
    }
    formData.append(key, String(value));
  }
  formData.append("messages", JSON.stringify(serializedMessages));
  for (const file of pendingFiles) {
    formData.append(attachmentFieldName, file);
  }

  return {
    body: formData,
  };
}

export function areChatAttachmentListsEquivalent(left: ChatAttachment[] | undefined, right: ChatAttachment[] | undefined) {
  const normalizedLeft = normalizeChatAttachments(left);
  const normalizedRight = normalizeChatAttachments(right);
  return normalizedLeft.length === normalizedRight.length
    && normalizedLeft.every((attachment, index) => {
      const other = normalizedRight[index];
      return attachment.id === other.id
        && attachment.name === other.name
        && attachment.size === other.size
        && (attachment.mimeType || "") === (other.mimeType || "")
        && (attachment.storageUrl || "") === (other.storageUrl || "");
    });
}

export function summarizeChatAttachments(attachments: ChatAttachment[]) {
  const normalizedAttachments = normalizeChatAttachments(attachments);
  if (normalizedAttachments.length === 0) {
    return "";
  }
  if (normalizedAttachments.length === 1) {
    return `Shared attachment: ${normalizedAttachments[0].name}`;
  }
  return `Shared ${normalizedAttachments.length} attachments`;
}

export function getChatAttachmentOpenUrl(attachment: ChatAttachment) {
  return attachment.storageUrl || attachment.previewUrl || "";
}

export function getChatAttachmentPreviewKind(attachment: Pick<ChatAttachment, "mimeType" | "name"> | null | undefined) {
  const normalizedMimeType = (attachment?.mimeType || "").toLowerCase();
  if (normalizedMimeType.startsWith("image/")) {
    return "image";
  }
  if (normalizedMimeType.startsWith("video/")) {
    return "video";
  }
  if (normalizedMimeType === "application/pdf") {
    return "pdf";
  }

  const normalizedName = (attachment?.name || "").toLowerCase();
  if (/\.(png|jpe?g|gif|webp|bmp|svg)$/.test(normalizedName)) {
    return "image";
  }
  if (/\.(mp4|mov|avi|mkv|webm)$/.test(normalizedName)) {
    return "video";
  }
  if (normalizedName.endsWith(".pdf")) {
    return "pdf";
  }

  return "file";
}

export function openChatAttachment(attachment: ChatAttachment) {
  const targetUrl = getChatAttachmentOpenUrl(attachment);
  if (!targetUrl || typeof window === "undefined") {
    return;
  }

  window.open(targetUrl, "_blank", "noopener,noreferrer");
}

export function revokeChatAttachmentPreviewUrl(attachment: ChatAttachment) {
  const previewUrl = attachment.previewUrl || "";
  if (!previewUrl.startsWith("blob:") || typeof URL === "undefined") {
    return;
  }

  URL.revokeObjectURL(previewUrl);
}

export function revokeChatAttachmentPreviewUrls(attachments: ChatAttachment[] | undefined | null) {
  for (const attachment of normalizeChatAttachments(attachments)) {
    revokeChatAttachmentPreviewUrl(attachment);
  }
}
