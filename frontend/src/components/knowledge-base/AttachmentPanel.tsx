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
        "mt-4 rounded-[22px] border border-dashed bg-slate-50/50 p-4 transition-colors",
        isDragging ? "border-primary bg-primary/5" : "border-slate-300",
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
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="text-base font-semibold text-slate-950">Attachments for this section</div>
          <p className="mt-1 text-sm text-slate-500">Drag files here, paste screenshots, or add a link.</p>
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
            className="h-8 rounded-xl border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-700 hover:bg-slate-50"
            onClick={() => inputRef.current?.click()}
          >
            Add files
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-8 rounded-xl border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-700 hover:bg-slate-50"
            onClick={onAddLink}
          >
            Add link
          </Button>
        </div>
      </div>

      <div className="mt-4 grid gap-3">
        {!attachments.length ? <div className="text-sm text-slate-500">No attachments added yet.</div> : null}

        {attachments.map((attachment) => {
          const source = resolveAttachmentUrl(attachment);
          const isImage =
            attachment.type.startsWith("image/") ||
            /\.(png|jpe?g|gif|webp|svg)$/i.test(source) ||
            source.startsWith("data:image/");

          return (
            <div
              key={attachment.id}
              className="grid gap-3 rounded-2xl border border-slate-200/90 bg-white p-3 shadow-soft md:grid-cols-[72px_minmax(0,1fr)_auto]"
            >
              <div className="flex h-[72px] items-center justify-center overflow-hidden rounded-2xl border border-slate-200 bg-slate-100">
                {isImage && source ? (
                  <img src={source} alt={attachment.name} className="h-full w-full object-cover" />
                ) : (
                  <Paperclip className="h-5 w-5 text-slate-400" />
                )}
              </div>

              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-slate-950">{attachment.name || "Attachment"}</div>
                <div className="mt-1 text-xs text-slate-500">
                  {attachment.type || "link"}
                  {attachment.size ? ` • ${formatBytes(attachment.size)}` : ""}
                </div>
                {attachment.url ? (
                  <div className="mt-2 truncate text-xs text-primary">{attachment.url}</div>
                ) : attachment.evidencePath ? (
                  <div className="mt-2 truncate text-xs text-slate-500">{attachment.evidencePath}</div>
                ) : null}
              </div>

              <div className="flex flex-wrap gap-2 md:justify-end">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-8 rounded-xl border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-700 hover:bg-slate-50"
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
                    className="h-8 rounded-xl border border-slate-200 bg-slate-100 px-3 text-xs font-semibold text-slate-700 hover:bg-slate-200"
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
                  className="h-8 rounded-xl bg-rose-50 px-3 text-xs font-semibold text-rose-600 hover:bg-rose-100 hover:text-rose-700"
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
