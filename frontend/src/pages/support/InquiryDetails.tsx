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
import { Category, EvidenceFile, TechnicalSubcategory, useSupport } from "@/context/SupportContext";
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

const technicalSubcategories: TechnicalSubcategory[] = ["Aptem", "LMS", "Teams"];
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
  const [category, setCategory] = useState<Category>(ticket.category);
  const [technicalSubcategory, setTechnicalSubcategory] = useState<TechnicalSubcategory>(ticket.technicalSubcategory);
  const [inquiry, setInquiry] = useState(ticket.inquiry);
  const [evidence, setEvidence] = useState(ticket.evidence);
  const [attachmentError, setAttachmentError] = useState("");
  const [previewFile, setPreviewFile] = useState<EvidenceFile | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const canSubmit = Boolean(
    category &&
    inquiry.trim().length > 0 &&
    (category !== "Technical" || technicalSubcategory)
  );

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
          category,
          technicalSubcategory: category === "Technical" ? technicalSubcategory : "",
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
              category: Category;
              technicalSubcategory: TechnicalSubcategory;
              inquiry: string;
              status: "Open" | "Pending" | "Closed";
              statusReason?: string;
              assignedTeam: string;
              slaStatus: string;
              createdAt: string;
              liveChatRequested?: boolean;
            };
          }
        | null;

      if (!response.ok || !payload?.ticket) {
        toast.error(payload?.message || `We could not ${hasExistingTicket ? "update" : "create"} the ticket right now.`);
        return;
      }

        updateTicket({
          id: payload.ticket.id,
          learnerName: payload.ticket.learnerName || ticket.learnerName,
          email: payload.ticket.email,
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
          chatHistory: hasExistingTicket ? ticket.chatHistory : [],
        });
      navigate("/support/chat");
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
      <div className="grid max-w-5xl gap-6 mx-auto lg:grid-cols-3">
        <div className="p-6 border lg:col-span-2 bg-card rounded-2xl shadow-card md:p-8">
          <h1 className="mb-1 text-2xl font-bold">Create Support Inquiry</h1>
          <p className="mb-6 text-sm text-muted-foreground">
            Choose the category and describe your issue.
          </p>

          <div className="space-y-5">
            <div className="space-y-2">
              <Label>Inquiry Category</Label>
              <Select
                value={category}
                onValueChange={(value) => {
                  const nextCategory = value as Category;
                  setCategory(nextCategory);
                  if (nextCategory !== "Technical") {
                    setTechnicalSubcategory("");
                  }
                }}
              >
                <SelectTrigger className="h-11">
                  <SelectValue placeholder="Select a category" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Learning">Learning</SelectItem>
                  <SelectItem value="Technical">Technical</SelectItem>
                  <SelectItem value="Others">Others</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {category === "Technical" && (
              <div className="space-y-2">
                <Label>Technical Sub Category</Label>
                <Select
                  value={technicalSubcategory}
                  onValueChange={(value) => setTechnicalSubcategory(value as TechnicalSubcategory)}
                >
                  <SelectTrigger className="h-11">
                    <SelectValue placeholder="Select a technical sub category" />
                  </SelectTrigger>
                  <SelectContent>
                    {technicalSubcategories.map((item) => (
                      <SelectItem key={item} value={item}>{item}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            <div className="space-y-2">
              <Label>Inquiry</Label>
              <Textarea
                rows={6}
                placeholder="Please describe your issue in detail..."
                value={inquiry}
                onChange={(event) => setInquiry(event.target.value)}
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

            <div className="flex justify-between pt-2">
              <Button variant="ghost" onClick={() => navigate("/support")}>
                <ArrowLeft className="w-4 h-4 mr-2" /> Back
              </Button>
              <Button
                disabled={!canSubmit || isSubmitting}
                onClick={() => void handleNext()}
                className="border-0 gradient-primary"
              >
                {isSubmitting ? (ticket.id ? "Saving..." : "Creating...") : "Next"}
                {!isSubmitting && <ArrowRight className="w-4 h-4 ml-2" />}
              </Button>
            </div>
          </div>
        </div>

        <aside className="p-6 border h-fit bg-card rounded-2xl shadow-card lg:sticky lg:top-24">
          <div className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Summary
          </div>
          <dl className="space-y-3 text-sm">
            <div>
              <dt className="text-muted-foreground">Email</dt>
              <dd className="font-medium truncate">{ticket.email || "-"}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Category</dt>
              <dd className="font-medium">{category || "-"}</dd>
            </div>
            {category === "Technical" && technicalSubcategory && (
              <div>
                <dt className="text-muted-foreground">Sub Category</dt>
                <dd className="font-medium">{technicalSubcategory}</dd>
              </div>
            )}
            <div>
              <dt className="text-muted-foreground">Evidence</dt>
              <dd className="font-medium">{evidence.length} file(s)</dd>
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
