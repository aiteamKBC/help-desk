import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, ArrowRight, FileText, Paperclip, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { SupportLayout } from "@/components/support/SupportLayout";
import { StepIndicator } from "@/components/support/StepIndicator";
import { type Category, type EvidenceFile, type TechnicalSubcategory, useSupport } from "@/context/SupportContext";
import { isQuickTicketOnlyRequesterRole } from "@/lib/supportFlow";
import { toast } from "sonner";

const textExtensions = new Set([
  ".txt",
  ".csv",
  ".json",
  ".md",
  ".log",
  ".xml",
  ".html",
  ".css",
  ".js",
  ".ts",
]);

const textMimeTypes = new Set([
  "application/json",
  "application/xml",
  "application/javascript",
  "application/x-javascript",
]);

const inquiryPlatforms: TechnicalSubcategory[] = ["LMS", "Aptem", "Teams"];
const acceptedEvidenceExtensions = new Set([".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".pdf", ".mp4", ".mov", ".avi", ".mkv", ".webm"]);

const getExtension = (name: string) => {
  const dotIndex = name.lastIndexOf(".");
  return dotIndex === -1 ? "" : name.slice(dotIndex).toLowerCase();
};

const isAcceptedEvidenceFile = (file: File) => {
  return file.type.startsWith("image/") || file.type.startsWith("video/") || file.type === "application/pdf" || acceptedEvidenceExtensions.has(getExtension(file.name));
};

const isTextPreviewable = (file: { name: string; mimeType?: string; type?: string }) => {
  const mimeType = file.mimeType || file.type || "";
  return mimeType.startsWith("text/") || textMimeTypes.has(mimeType) || textExtensions.has(getExtension(file.name));
};

const getPreviewKind = (file: EvidenceFile) => {
  const mimeType = file.mimeType || "";

  if (mimeType.startsWith("image/")) return "image";
  if (mimeType.startsWith("video/")) return "video";
  if (mimeType.startsWith("audio/")) return "audio";
  if (mimeType === "application/pdf") return "pdf";
  if (isTextPreviewable(file)) return "text";
  return "generic";
};

const toEvidenceFile = async (file: File): Promise<EvidenceFile> => {
  const evidenceFile: EvidenceFile = {
    name: file.name,
    size: file.size,
    mimeType: file.type,
    previewUrl: URL.createObjectURL(file),
  };

  if (!isTextPreviewable(file)) {
    return evidenceFile;
  }

  try {
    return {
      ...evidenceFile,
      textContent: await file.text(),
    };
  } catch {
    return evidenceFile;
  }
};

const formatFileTypeLabel = (file: EvidenceFile) => {
  const kind = getPreviewKind(file);

  if (kind === "pdf") return "PDF preview";
  if (kind === "generic") return file.mimeType || "File preview";

  return `${kind.charAt(0).toUpperCase()}${kind.slice(1)} preview`;
};

const InquiryDetails = () => {
  const navigate = useNavigate();
  const { ticket, updateTicket } = useSupport();
  const [technicalSubcategory, setTechnicalSubcategory] = useState<TechnicalSubcategory>(ticket.technicalSubcategory);
  const [inquiry, setInquiry] = useState(ticket.inquiry);
  const [evidence, setEvidence] = useState(ticket.evidence);
  const [attachmentError, setAttachmentError] = useState("");
  const [previewFile, setPreviewFile] = useState<EvidenceFile | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const canSubmit = Boolean(technicalSubcategory && inquiry.trim().length > 0);

  const onFiles = async (files: FileList | null) => {
    if (!files) return;

    const selectedFiles = Array.from(files);
    const acceptedFiles = selectedFiles.filter(isAcceptedEvidenceFile);
    const rejectedFiles = selectedFiles.filter((file) => !isAcceptedEvidenceFile(file));

    if (rejectedFiles.length > 0) {
      setAttachmentError("Unsupported file type. Please upload an image, PDF, or video file.");
    } else {
      setAttachmentError("");
    }

    if (acceptedFiles.length > 0) {
      const nextFiles = await Promise.all(acceptedFiles.map(toEvidenceFile));
      setEvidence((prev) => [...prev, ...nextFiles]);
    }

    if (fileRef.current) {
      fileRef.current.value = "";
    }
  };

  const removeFile = (index: number) => {
    setEvidence((prev) => {
      const fileToRemove = prev[index];

      if (previewFile?.previewUrl === fileToRemove?.previewUrl) {
        setPreviewFile(null);
      }

      if (fileToRemove?.previewUrl?.startsWith("blob:")) {
        URL.revokeObjectURL(fileToRemove.previewUrl);
      }

      return prev.filter((_, currentIndex) => currentIndex !== index);
    });
  };

  const handleNext = async () => {
    if (!canSubmit) return;

    setIsSubmitting(true);

    try {
      const hasExistingTicket = Boolean(ticket.id);
      const response = await fetch(hasExistingTicket ? `/api/tickets/${encodeURIComponent(ticket.id)}` : "/api/tickets", {
        method: hasExistingTicket ? "PATCH" : "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email: ticket.email,
          requesterRole: ticket.requesterRole,
          category: "Technical",
          technicalSubcategory,
          inquiry,
          evidence: evidence.map((file) => ({
            name: file.name,
            size: file.size,
            mimeType: file.mimeType,
          })),
        }),
      });

      const payload = (await response.json().catch(() => null)) as
        | {
            message?: string;
            ticket?: {
              id: string;
              learnerName?: string;
              email: string;
              requesterRole?: "user" | "coach" | "employer";
              category: Category;
              technicalSubcategory: TechnicalSubcategory;
              inquiry: string;
              status: "Open" | "Pending" | "Closed";
              statusReason?: string;
              assignedTeam: string;
              slaStatus: string;
              createdAt: string;
              chatState?: "open" | "closed";
              liveChatRequested?: boolean;
            };
          }
        | null;

      if (!response.ok || !payload?.ticket) {
        toast.error(payload?.message || `We could not ${hasExistingTicket ? "update" : "create"} the ticket right now.`);
        return;
      }

      const nextRequesterRole = payload.ticket.requesterRole || ticket.requesterRole;
      const nextTicketState = {
        id: payload.ticket.id,
        learnerName: payload.ticket.learnerName || ticket.learnerName,
        email: payload.ticket.email,
        requesterRole: nextRequesterRole,
        category: payload.ticket.category,
        technicalSubcategory: payload.ticket.technicalSubcategory,
        inquiry: payload.ticket.inquiry,
        evidence,
        statusReason: payload.ticket.statusReason || ticket.statusReason,
        createdAt: payload.ticket.createdAt,
        status: payload.ticket.status,
        assignedTeam: payload.ticket.assignedTeam,
        slaStatus: payload.ticket.slaStatus,
        liveChatRequested: payload.ticket.liveChatRequested ?? (hasExistingTicket ? ticket.liveChatRequested : false),
        chatState: payload.ticket.chatState ?? (hasExistingTicket ? ticket.chatState : "open"),
        chatHistory: hasExistingTicket ? ticket.chatHistory : [],
      } as const;

      updateTicket(nextTicketState);

      navigate("/support/options");
    } catch {
      toast.error("We could not connect to the server. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const previewKind = previewFile ? getPreviewKind(previewFile) : null;

  return (
    <SupportLayout>
      <StepIndicator current={2} />
      <div className="mx-auto grid max-w-5xl gap-4 sm:gap-6 lg:grid-cols-3 lg:items-stretch">
        <div className="rounded-[28px] border border-primary/10 bg-gradient-to-br from-white via-white to-primary/[0.03] p-5 shadow-card sm:p-6 md:p-8 lg:col-span-2">
          <h1 className="mb-1 text-2xl font-bold text-primary">Create Support Inquiry</h1>
          <p className="mb-6 text-sm text-muted-foreground">
            Choose the platform and describe your issue.
          </p>

          <div className="space-y-5">
            <div className="space-y-2">
              <Label>Inquiry Category</Label>
              <Select
                value={technicalSubcategory}
                onValueChange={(value) => setTechnicalSubcategory(value as TechnicalSubcategory)}
              >
                <SelectTrigger className="h-11">
                  <SelectValue placeholder="Select a platform" />
                </SelectTrigger>
                <SelectContent>
                  {inquiryPlatforms.map((item) => (
                    <SelectItem key={item} value={item}>{item}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Inquiry</Label>
              <Textarea
                rows={6}
                placeholder="Please describe your issue in detail..."
                value={inquiry}
                onChange={(event) => setInquiry(event.target.value)}
                className="resize-none"
              />
            </div>

            <div className="space-y-2">
              <Label className="flex items-center gap-2">
                <Paperclip className="w-4 h-4" /> Upload supporting evidence
              </Label>
              <div
                onClick={() => fileRef.current?.click()}
                className="p-6 text-center transition-colors border-2 border-dashed rounded-xl cursor-pointer border-border hover:border-primary hover:bg-primary/5"
              >
                <Paperclip className="w-6 h-6 mx-auto mb-2 text-muted-foreground" />
                <p className="text-sm font-medium">Click to upload files</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Accepted file types: images, PDFs, and videos. You can upload multiple files.
                </p>
                <input
                  ref={fileRef}
                  type="file"
                  accept="image/*,application/pdf,video/*"
                  multiple
                  className="hidden"
                  onChange={(event) => void onFiles(event.target.files)}
                />
              </div>
              {attachmentError && (
                <p className="text-xs text-destructive">
                  {attachmentError}
                </p>
              )}
              {evidence.length > 0 && (
                <ul className="mt-3 space-y-2">
                  {evidence.map((file, index) => (
                    <li
                      key={`${file.name}-${index}`}
                      className="flex items-center justify-between px-3 py-2 text-sm rounded-lg bg-secondary"
                    >
                      <button
                        type="button"
                        onClick={() => setPreviewFile(file)}
                        className="flex flex-1 min-w-0 items-center gap-2 text-left transition-colors hover:text-primary"
                      >
                        <FileText className="w-4 h-4 shrink-0 text-muted-foreground" />
                        <span className="truncate">{file.name}</span>
                        <span className="shrink-0 text-xs text-primary">View</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => removeFile(index)}
                        className="ml-3 shrink-0 text-muted-foreground hover:text-destructive"
                        aria-label="Remove"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="flex flex-col-reverse gap-3 pt-2 sm:flex-row sm:items-center sm:justify-between">
              <Button variant="ghost" className="w-full sm:w-auto" onClick={() => navigate("/support")}>
                <ArrowLeft className="w-4 h-4 mr-2" /> Back
              </Button>
              <Button
                disabled={!canSubmit || isSubmitting}
                onClick={() => void handleNext()}
                className="w-full border-0 gradient-primary sm:w-auto"
              >
                {isSubmitting ? (ticket.id ? "Saving..." : "Creating...") : "Next"}
                {!isSubmitting && <ArrowRight className="w-4 h-4 ml-2" />}
              </Button>
            </div>
          </div>
        </div>

        <aside className="rounded-[28px] border border-primary/12 bg-gradient-to-br from-white via-white to-primary/[0.04] p-5 shadow-elevated sm:p-6 lg:sticky lg:top-24 lg:self-stretch lg:min-h-full">
          <div className="mb-3 text-xs font-semibold uppercase tracking-wide text-primary/75">
            Summary
          </div>
          <dl className="text-sm">
            <div className="border-b border-primary/10 pb-4">
              <dt className="text-[15px] font-bold text-foreground">Requester Type</dt>
              <dd className="mt-1 text-[15px] font-medium capitalize">{ticket.requesterRole || "-"}</dd>
            </div>
            <div className="border-b border-primary/10 py-4">
              <dt className="text-[15px] font-bold text-foreground">Email</dt>
              <dd className="mt-1 text-[15px] font-medium truncate">{ticket.email || "-"}</dd>
            </div>
            <div className="border-b border-primary/10 py-4">
              <dt className="text-[15px] font-bold text-foreground">Category</dt>
              <dd className="mt-1 text-[15px] font-medium">{technicalSubcategory || "-"}</dd>
            </div>
            <div className="py-4">
              <dt className="text-[15px] font-bold text-foreground">Evidence</dt>
              <dd className="mt-1 text-[15px] font-medium">{evidence.length} file(s)</dd>
            </div>
          </dl>
        </aside>
      </div>

      <Dialog open={!!previewFile} onOpenChange={(open) => !open && setPreviewFile(null)}>
        <DialogContent className="max-w-4xl p-3 sm:p-4">
          <DialogHeader className="px-1 pt-1">
            <DialogTitle className="text-base">{previewFile?.name}</DialogTitle>
            <DialogDescription>
              {previewFile ? formatFileTypeLabel(previewFile) : "File preview"}
            </DialogDescription>
          </DialogHeader>

          {previewFile?.previewUrl && previewKind === "image" && (
            <img
              src={previewFile.previewUrl}
              alt={previewFile.name}
              className="w-full max-h-[75vh] rounded-lg object-contain bg-secondary/30"
            />
          )}

          {previewFile?.previewUrl && previewKind === "video" && (
            <video
              src={previewFile.previewUrl}
              controls
              className="w-full max-h-[75vh] rounded-lg bg-black"
            />
          )}

          {previewFile?.previewUrl && previewKind === "audio" && (
            <div className="p-4 border rounded-lg bg-secondary/20">
              <audio src={previewFile.previewUrl} controls className="w-full" />
            </div>
          )}

          {previewFile?.previewUrl && previewKind === "pdf" && (
            <iframe
              src={previewFile.previewUrl}
              title={previewFile.name}
              className="h-[75vh] w-full rounded-lg border bg-white"
            />
          )}

          {previewKind === "text" && (
            <pre className="max-h-[75vh] overflow-auto rounded-lg border bg-secondary/20 p-4 text-sm whitespace-pre-wrap break-words">
              {previewFile?.textContent || "Unable to load text preview."}
            </pre>
          )}

          {previewFile?.previewUrl && previewKind === "generic" && (
            <div className="space-y-3">
              <object
                data={previewFile.previewUrl}
                type={previewFile.mimeType}
                className="h-[65vh] w-full rounded-lg border bg-white"
              >
                <div className="flex h-full min-h-48 items-center justify-center rounded-lg border bg-secondary/20 p-4 text-center text-sm text-muted-foreground">
                  This file type cannot be previewed directly here. Use Open File to view or download it.
                </div>
              </object>
              <div className="flex justify-end">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => window.open(previewFile.previewUrl, "_blank", "noopener,noreferrer")}
                >
                  Open File
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </SupportLayout>
  );
};

export default InquiryDetails;
