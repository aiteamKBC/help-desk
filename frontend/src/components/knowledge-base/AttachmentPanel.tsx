import { useRef, useState } from "react";
import { Download, ExternalLink, ImageIcon, Paperclip, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { formatBytes, resolveAttachmentUrl, type KnowledgeBaseAttachment } from "@/lib/knowledgeBase";

type AttachmentPanelProps = {
  attachments: KnowledgeBaseAttachment[];
  onAddFiles: (files: File[]) => Promise<void> | void;
  onAddLink: () => void;
  onOpenAttachment: (attachment: KnowledgeBaseAttachment) => void;
  onRemoveAttachment: (attachmentId: string) => void;
};

export function AttachmentPanel({
  attachments,
  onAddFiles,
  onAddLink,
  onOpenAttachment,
  onRemoveAttachment,
}: AttachmentPanelProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const handleFiles = async (files: File[]) => {
    if (!files.length) {
      return;
    }
    await onAddFiles(files);
  };

  return (
    <div
      className={cn(
        "mt-4 rounded-xl border border-dashed p-4 transition-colors",
        isDragging ? "border-primary bg-primary/5" : "border-input bg-secondary/60",
      )}
      onDragEnter={(event) => {
        event.preventDefault();
        setIsDragging(true);
      }}
      onDragOver={(event) => {
        event.preventDefault();
        setIsDragging(true);
      }}
      onDragLeave={(event) => {
        event.preventDefault();
        setIsDragging(false);
      }}
      onDrop={async (event) => {
        event.preventDefault();
        setIsDragging(false);
        await handleFiles(Array.from(event.dataTransfer.files || []));
      }}
      onPaste={async (event) => {
        const files = Array.from(event.clipboardData.files || []);
        if (!files.length) {
          return;
        }
        event.preventDefault();
        await handleFiles(files);
      }}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="text-[13px] font-medium text-foreground">Attachments for this section</div>
          <p className="mt-0.5 text-xs text-muted-foreground">Drag files here, paste screenshots, or add a link.</p>
        </div>

        <div className="flex flex-wrap gap-2">
          <input
            ref={inputRef}
            type="file"
            multiple
            className="hidden"
            onChange={async (event) => {
              await handleFiles(Array.from(event.target.files || []));
              event.target.value = "";
            }}
          />
          <Button
            type="button"
            variant="secondary"
            size="sm"
            className="h-8 rounded-lg border border-input bg-card px-3 text-xs font-medium text-foreground hover:bg-secondary hover:text-primary"
            onClick={() => inputRef.current?.click()}
          >
            Add files
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-8 rounded-lg border border-input bg-card px-3 text-xs font-medium text-foreground hover:bg-secondary hover:text-primary"
            onClick={onAddLink}
          >
            Add link
          </Button>
        </div>
      </div>

      <div className="mt-3 grid gap-2">
        {!attachments.length ? <div className="text-xs text-muted-foreground">No attachments added yet.</div> : null}

        {attachments.map((attachment) => {
          const source = resolveAttachmentUrl(attachment);
          const isImage =
            attachment.type.startsWith("image/") ||
            /\.(png|jpe?g|gif|webp|svg)$/i.test(source) ||
            source.startsWith("data:image/");

          return (
            <div
              key={attachment.id}
              className="grid gap-3 rounded-lg border bg-card p-3 sm:grid-cols-[64px_minmax(0,1fr)] md:grid-cols-[64px_minmax(0,1fr)_auto]"
            >
              <div className="flex h-16 items-center justify-center overflow-hidden rounded-lg border bg-secondary">
                {isImage && source ? (
                  <img src={source} alt={attachment.name} className="h-full w-full object-cover" />
                ) : (
                  <Paperclip className="h-5 w-5 text-muted-foreground" />
                )}
              </div>

              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-foreground">{attachment.name || "Attachment"}</div>
                <div className="mt-0.5 text-xs text-muted-foreground">
                  {attachment.type || "link"}
                  {attachment.size ? ` • ${formatBytes(attachment.size)}` : ""}
                </div>
                {attachment.url ? (
                  <div className="mt-1 truncate text-xs text-primary">{attachment.url}</div>
                ) : attachment.evidencePath ? (
                  <div className="mt-1 truncate text-xs text-muted-foreground">{attachment.evidencePath}</div>
                ) : null}
              </div>

              <div className="flex flex-wrap gap-2 sm:col-span-2 md:col-span-1 md:justify-end">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-8 rounded-lg border border-input bg-card px-3 text-xs font-medium text-foreground hover:bg-secondary hover:text-primary"
                  onClick={() => onOpenAttachment(attachment)}
                >
                  {isImage ? <ImageIcon className="h-4 w-4" /> : <ExternalLink className="h-4 w-4" />}
                  Open
                </Button>
                {attachment.dataUrl ? (
                  <Button
                    asChild
                    type="button"
                    variant="secondary"
                    size="sm"
                    className="h-8 rounded-lg border border-input bg-card px-3 text-xs font-medium text-foreground hover:bg-secondary hover:text-primary"
                  >
                    <a href={attachment.dataUrl} download={attachment.name || "attachment"}>
                      <Download className="h-4 w-4" />
                      Download
                    </a>
                  </Button>
                ) : null}
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-8 rounded-lg border border-rose-200 bg-card px-3 text-xs font-medium text-rose-600 hover:bg-rose-50 hover:text-rose-700"
                  onClick={() => onRemoveAttachment(attachment.id)}
                >
                  <Trash2 className="h-4 w-4" />
                  Remove
                </Button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
