import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, ArrowRight, ChevronDown, FileText, Paperclip, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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
import {
  buildCoverageInquiry,
  fetchCoverageOptions,
  fetchCoverageTimeOptions,
  isCoverageSubcategory,
  parseCoverageInquiry,
  type CoverageTimeOption,
} from "@/lib/coverageSupport";
import { quickTicketReason } from "@/lib/supportFlow";
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

const inquiryPlatforms: TechnicalSubcategory[] = ["LMS", "Aptem", "Teams", "Coverage", "Others"];
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
    file,
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

const buildCoverageSessionNumberMap = (sessionDates: string[] = [], sessionNumbers: string[] = []) => {
  return sessionDates.reduce<Record<string, string>>((accumulator, sessionDate, index) => {
    const sessionNumber = sessionNumbers[index]?.trim() || "";
    if (sessionNumber) {
      accumulator[sessionDate] = sessionNumber;
    }
    return accumulator;
  }, {});
};

const buildCoverageSessionSubjectMap = (sessionDates: string[] = [], sessionSubjects: string[] = [], fallbackSubject = "") => {
  const normalizedFallbackSubject = fallbackSubject.trim();

  return sessionDates.reduce<Record<string, string>>((accumulator, sessionDate, index) => {
    const sessionSubject = sessionSubjects[index]?.trim() || (sessionSubjects.length === 0 ? normalizedFallbackSubject : "");
    if (sessionSubject) {
      accumulator[sessionDate] = sessionSubject;
    }
    return accumulator;
  }, {});
};

const getDefaultCoverageSessionNumber = (sessionDate: string, sessionDateOptions: string[]) => {
  const sessionIndex = sessionDateOptions.indexOf(sessionDate);
  return sessionIndex >= 0 ? String(sessionIndex + 1) : "";
};

const InquiryDetails = () => {
  const navigate = useNavigate();
  const { ticket, updateTicket, clearBookingSummary } = useSupport();
  const initialCoverageDetails = parseCoverageInquiry(ticket.inquiry);
  const [technicalSubcategory, setTechnicalSubcategory] = useState<TechnicalSubcategory>(ticket.technicalSubcategory);
  const [inquiry, setInquiry] = useState(
    isCoverageSubcategory(ticket.technicalSubcategory) && initialCoverageDetails ? "" : ticket.inquiry,
  );
  const [coverageTutor, setCoverageTutor] = useState(initialCoverageDetails?.tutor || "");
  const [coverageModule, setCoverageModule] = useState(initialCoverageDetails?.module || "");
  const [coverageTime, setCoverageTime] = useState(initialCoverageDetails?.time || "");
  const [coverageSessionDates, setCoverageSessionDates] = useState(initialCoverageDetails?.sessionDates || []);
  const [coverageSessionNumberByDate, setCoverageSessionNumberByDate] = useState<Record<string, string>>(
    buildCoverageSessionNumberMap(initialCoverageDetails?.sessionDates || [], initialCoverageDetails?.sessionNumbers || []),
  );
  const [coverageSessionSubjectByDate, setCoverageSessionSubjectByDate] = useState<Record<string, string>>(
    buildCoverageSessionSubjectMap(
      initialCoverageDetails?.sessionDates || [],
      initialCoverageDetails?.sessionSubjects || [],
      initialCoverageDetails?.sessionSubject || "",
    ),
  );
  const [coverageTutorOptions, setCoverageTutorOptions] = useState<string[]>([]);
  const [coverageModuleOptions, setCoverageModuleOptions] = useState<string[]>([]);
  const [coverageTimeOptions, setCoverageTimeOptions] = useState<CoverageTimeOption[]>([]);
  const [coverageSessionDateOptions, setCoverageSessionDateOptions] = useState<string[]>([]);
  const [coverageOptionsError, setCoverageOptionsError] = useState("");
  const [isLoadingCoverageTutors, setIsLoadingCoverageTutors] = useState(false);
  const [isLoadingCoverageModules, setIsLoadingCoverageModules] = useState(false);
  const [isLoadingCoverageTimes, setIsLoadingCoverageTimes] = useState(false);
  const [isLoadingCoverageSessionDates, setIsLoadingCoverageSessionDates] = useState(false);
  const [evidence, setEvidence] = useState(ticket.evidence);
  const [attachmentError, setAttachmentError] = useState("");
  const [previewFile, setPreviewFile] = useState<EvidenceFile | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const coverageSessionDateRequestRef = useRef(0);
  const selectedCoverageSessionNumbers = coverageSessionDates.map(
    (sessionDate) => (coverageSessionNumberByDate[sessionDate] || getDefaultCoverageSessionNumber(sessionDate, coverageSessionDateOptions)).trim(),
  );
  const selectedCoverageSessionSubjects = coverageSessionDates.map(
    (sessionDate) => (coverageSessionSubjectByDate[sessionDate] || "").trim(),
  );

  const isCoverageFlow = isCoverageSubcategory(technicalSubcategory);
  const canSubmit = isCoverageFlow
    ? Boolean(
      coverageTutor
      && coverageModule
      && coverageTime
      && coverageSessionDates.length > 0
      && selectedCoverageSessionSubjects.every((value) => value.length > 0),
    )
    : Boolean(technicalSubcategory && inquiry.trim().length > 0);

  const loadCoverageSessionDateOptions = (tutorValue: string, moduleValue: string, timeValue: string) => {
    if (!isCoverageFlow || !tutorValue || !moduleValue || !timeValue) {
      coverageSessionDateRequestRef.current += 1;
      setCoverageSessionDateOptions([]);
      setCoverageSessionDates([]);
      setCoverageSessionNumberByDate({});
      setCoverageSessionSubjectByDate({});
      setIsLoadingCoverageSessionDates(false);
      return;
    }

    const requestId = coverageSessionDateRequestRef.current + 1;
    coverageSessionDateRequestRef.current = requestId;
    setIsLoadingCoverageSessionDates(true);
    setCoverageOptionsError("");

    void fetchCoverageOptions("session-dates", {
      tutor: tutorValue,
      module: moduleValue,
      time: timeValue,
    })
      .then((options) => {
        if (coverageSessionDateRequestRef.current !== requestId) {
          return;
        }

        setCoverageSessionDateOptions(options);
        setCoverageSessionDates((currentDates) => currentDates.filter((currentDate) => options.includes(currentDate)));
      })
      .catch((error: unknown) => {
        if (coverageSessionDateRequestRef.current !== requestId) {
          return;
        }

        setCoverageSessionDateOptions([]);
        setCoverageSessionDates([]);
        setCoverageSessionNumberByDate({});
        setCoverageSessionSubjectByDate({});
        setCoverageOptionsError(error instanceof Error ? error.message : "We could not load the session dates right now.");
      })
      .finally(() => {
        if (coverageSessionDateRequestRef.current === requestId) {
          setIsLoadingCoverageSessionDates(false);
        }
      });
  };

  useEffect(() => {
    if (!ticket.id && !ticket.email) {
      navigate("/support");
    }
  }, [navigate, ticket.email, ticket.id]);

  useEffect(() => {
    if (!isCoverageFlow) {
      setCoverageOptionsError("");
      setCoverageTutorOptions([]);
      setCoverageModuleOptions([]);
      setCoverageTimeOptions([]);
      setCoverageSessionDateOptions([]);
      setCoverageSessionDates([]);
      setCoverageSessionNumberByDate({});
      setCoverageSessionSubjectByDate({});
      setIsLoadingCoverageTutors(false);
      setIsLoadingCoverageModules(false);
      setIsLoadingCoverageTimes(false);
      setIsLoadingCoverageSessionDates(false);
      return;
    }

    let cancelled = false;
    setIsLoadingCoverageTutors(true);
    setCoverageOptionsError("");

    void fetchCoverageOptions("tutors")
      .then((options) => {
        if (cancelled) {
          return;
        }

        setCoverageTutorOptions(options);
        setCoverageTutor((currentTutor) => (currentTutor && !options.includes(currentTutor) ? "" : currentTutor));
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }

        setCoverageTutorOptions([]);
        setCoverageOptionsError(error instanceof Error ? error.message : "We could not load the tutors right now.");
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoadingCoverageTutors(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [isCoverageFlow]);

  useEffect(() => {
    if (!isCoverageFlow || !coverageTutor) {
      setCoverageModule("");
      setCoverageTime("");
      setCoverageModuleOptions([]);
      setCoverageTimeOptions([]);
      setCoverageSessionDateOptions([]);
      setCoverageSessionDates([]);
      setCoverageSessionNumberByDate({});
      setCoverageSessionSubjectByDate({});
      setIsLoadingCoverageModules(false);
      setIsLoadingCoverageTimes(false);
      setIsLoadingCoverageSessionDates(false);
      return;
    }

    let cancelled = false;
    setIsLoadingCoverageModules(true);
    setCoverageOptionsError("");

    void fetchCoverageOptions("modules", { tutor: coverageTutor })
      .then((options) => {
        if (cancelled) {
          return;
        }

        setCoverageModuleOptions(options);
        setCoverageModule((currentModule) => (currentModule && !options.includes(currentModule) ? "" : currentModule));
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }

        setCoverageModuleOptions([]);
        setCoverageOptionsError(error instanceof Error ? error.message : "We could not load the modules right now.");
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoadingCoverageModules(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [coverageTutor, isCoverageFlow]);

  useEffect(() => {
    if (!isCoverageFlow || !coverageTutor || !coverageModule) {
      setCoverageTime("");
      setCoverageTimeOptions([]);
      setCoverageSessionDateOptions([]);
      setCoverageSessionDates([]);
      setCoverageSessionNumberByDate({});
      setCoverageSessionSubjectByDate({});
      setIsLoadingCoverageTimes(false);
      setIsLoadingCoverageSessionDates(false);
      return;
    }

    let cancelled = false;
    setIsLoadingCoverageTimes(true);
    setCoverageOptionsError("");

    void fetchCoverageTimeOptions({ tutor: coverageTutor, module: coverageModule })
      .then((options) => {
        if (cancelled) {
          return;
        }

        setCoverageTimeOptions(options);
        setCoverageTime((currentTime) => (
          currentTime && !options.some((option) => option.label === currentTime) ? "" : currentTime
        ));
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }

        setCoverageTimeOptions([]);
        setCoverageOptionsError(error instanceof Error ? error.message : "We could not load the times right now.");
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoadingCoverageTimes(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [coverageModule, coverageTutor, isCoverageFlow]);

  useEffect(() => {
    if (!isCoverageFlow || !coverageTutor || !coverageModule || !coverageTime) {
      coverageSessionDateRequestRef.current += 1;
      setCoverageSessionDateOptions([]);
      setCoverageSessionDates([]);
      setCoverageSessionNumberByDate({});
      setCoverageSessionSubjectByDate({});
      setIsLoadingCoverageSessionDates(false);
      return;
    }

    loadCoverageSessionDateOptions(coverageTutor, coverageModule, coverageTime);
  }, [coverageModule, coverageTime, coverageTutor, isCoverageFlow]);

  useEffect(() => {
    if (!isCoverageFlow) {
      setCoverageSessionNumberByDate({});
      setCoverageSessionSubjectByDate({});
      return;
    }

    setCoverageSessionNumberByDate((currentSessionNumberByDate) => {
      const nextSessionNumberByDate = coverageSessionDates.reduce<Record<string, string>>((accumulator, sessionDate) => {
        accumulator[sessionDate] = currentSessionNumberByDate[sessionDate] || getDefaultCoverageSessionNumber(sessionDate, coverageSessionDateOptions);
        return accumulator;
      }, {});

      const currentKeys = Object.keys(currentSessionNumberByDate);
      const nextKeys = Object.keys(nextSessionNumberByDate);
      const hasChanged = currentKeys.length !== nextKeys.length || nextKeys.some((key) => currentSessionNumberByDate[key] !== nextSessionNumberByDate[key]);
      return hasChanged ? nextSessionNumberByDate : currentSessionNumberByDate;
    });
  }, [coverageSessionDateOptions, coverageSessionDates, isCoverageFlow]);

  useEffect(() => {
    if (!isCoverageFlow) {
      setCoverageSessionSubjectByDate({});
      return;
    }

    setCoverageSessionSubjectByDate((currentSessionSubjectByDate) => {
      const nextSessionSubjectByDate = coverageSessionDates.reduce<Record<string, string>>((accumulator, sessionDate) => {
        const sessionSubject = currentSessionSubjectByDate[sessionDate]?.trim() || "";
        if (sessionSubject) {
          accumulator[sessionDate] = sessionSubject;
        }
        return accumulator;
      }, {});

      const currentKeys = Object.keys(currentSessionSubjectByDate);
      const nextKeys = Object.keys(nextSessionSubjectByDate);
      const hasChanged = currentKeys.length !== nextKeys.length || nextKeys.some((key) => currentSessionSubjectByDate[key] !== nextSessionSubjectByDate[key]);
      return hasChanged ? nextSessionSubjectByDate : currentSessionSubjectByDate;
    });
  }, [coverageSessionDates, isCoverageFlow]);

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
      const submittedInquiry = isCoverageFlow
        ? buildCoverageInquiry({
            tutor: coverageTutor,
            module: coverageModule,
            time: coverageTime,
            sessionDates: coverageSessionDates,
            sessionNumbers: selectedCoverageSessionNumbers,
            sessionSubjects: selectedCoverageSessionSubjects,
            sessionSubject: selectedCoverageSessionSubjects.join("; "),
          })
        : inquiry.trim();
      const formData = new FormData();
      if (!hasExistingTicket) {
        formData.set("email", ticket.email);
      }
      formData.set("requesterRole", ticket.requesterRole);
      formData.set("category", "Technical");
      formData.set("technicalSubcategory", technicalSubcategory);
      formData.set("inquiry", submittedInquiry);
      evidence.forEach((file) => {
        if (file.file) {
          formData.append("evidenceFiles", file.file, file.name);
        }
      });

      const response = await fetch(hasExistingTicket ? `/api/tickets/${encodeURIComponent(ticket.id)}` : "/api/tickets", {
        method: "POST",
        body: formData,
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
              assignedAgentId?: number | null;
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
        inquiry: payload.ticket.inquiry || submittedInquiry,
        evidence,
        statusReason: payload.ticket.statusReason || ticket.statusReason,
        assignedAgentId: payload.ticket.assignedAgentId ?? (hasExistingTicket ? ticket.assignedAgentId : null),
        createdAt: payload.ticket.createdAt,
        status: payload.ticket.status,
        assignedTeam: payload.ticket.assignedTeam,
        slaStatus: payload.ticket.slaStatus,
        liveChatRequested: payload.ticket.liveChatRequested ?? (hasExistingTicket ? ticket.liveChatRequested : false),
        chatState: payload.ticket.chatState ?? (hasExistingTicket ? ticket.chatState : "open"),
        chatHistory: hasExistingTicket ? ticket.chatHistory : [],
      } as const;

      updateTicket(nextTicketState);

      if (isCoverageFlow) {
        const directSubmitResponse = await fetch(`/api/tickets/${encodeURIComponent(payload.ticket.id)}/chat-history`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            status: "Pending",
            statusReason: quickTicketReason,
            messages: nextTicketState.chatHistory.map((message) => ({
              sender: message.sender,
              text: message.text,
              timestamp: message.timestamp,
            })),
          }),
        });

        const directSubmitPayload = (await directSubmitResponse.json().catch(() => null)) as
          | {
              message?: string;
              ticket?: {
                status?: "Open" | "Pending" | "Closed";
                statusReason?: string;
                assignedTeam?: string;
                slaStatus?: string;
                createdAt?: string;
                chatState?: "open" | "closed";
              };
            }
          | null;

        if (!directSubmitResponse.ok || !directSubmitPayload?.ticket) {
          toast.error(directSubmitPayload?.message || "We could not submit the ticket right now.");
          return;
        }

        clearBookingSummary();
        updateTicket({
          ...nextTicketState,
          status: directSubmitPayload.ticket.status || "Pending",
          statusReason: directSubmitPayload.ticket.statusReason || quickTicketReason,
          assignedTeam: directSubmitPayload.ticket.assignedTeam || nextTicketState.assignedTeam,
          slaStatus: directSubmitPayload.ticket.slaStatus || nextTicketState.slaStatus,
          createdAt: directSubmitPayload.ticket.createdAt || nextTicketState.createdAt,
          chatState: directSubmitPayload.ticket.chatState || nextTicketState.chatState,
        });
        toast.success("Your ticket has been submitted directly for team review.");
        navigate("/support/status");
        return;
      }

      navigate("/support/options");
    } catch {
      toast.error("We could not connect to the server. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const previewKind = previewFile ? getPreviewKind(previewFile) : null;
  const pageDescription = isCoverageFlow
    ? "Choose the inquiry category, then select the tutor, module, time, session date, and session details."
    : "Choose the inquiry category and describe your issue.";

  const handleCoverageTutorChange = (value: string) => {
    setCoverageTutor(value);
    setCoverageModule("");
    setCoverageTime("");
    setCoverageSessionDates([]);
    setCoverageSessionDateOptions([]);
    setCoverageSessionNumberByDate({});
    setCoverageSessionSubjectByDate({});
  };

  const handleCoverageModuleChange = (value: string) => {
    setCoverageModule(value);
    setCoverageTime("");
    setCoverageSessionDates([]);
    setCoverageSessionDateOptions([]);
    setCoverageSessionNumberByDate({});
    setCoverageSessionSubjectByDate({});
  };

  const handleCoverageTimeChange = (value: string) => {
    setCoverageTime(value);
    setCoverageSessionDates([]);
    setCoverageSessionNumberByDate({});
    setCoverageSessionSubjectByDate({});
  };

  const toggleCoverageSessionDate = (value: string) => {
    setCoverageSessionDates((currentDates) => {
      if (currentDates.includes(value)) {
        return currentDates.filter((currentDate) => currentDate !== value);
      }

      return coverageSessionDateOptions.filter((option) => option === value || currentDates.includes(option));
    });
  };

  const handleCoverageSessionNumberChange = (sessionDate: string, value: string) => {
    setCoverageSessionNumberByDate((currentSessionNumberByDate) => ({
      ...currentSessionNumberByDate,
      [sessionDate]: value.replace(/[^\d]/g, ""),
    }));
  };

  const handleCoverageSessionSubjectChange = (sessionDate: string, value: string) => {
    setCoverageSessionSubjectByDate((currentSessionSubjectByDate) => ({
      ...currentSessionSubjectByDate,
      [sessionDate]: value,
    }));
  };

  const coverageSessionDateTriggerLabel = !coverageTime
    ? "Choose time first"
    : isLoadingCoverageSessionDates
      ? "Loading session dates..."
      : coverageSessionDates.length === 0
        ? "Choose session date(s)"
        : coverageSessionDates.length === 1
          ? coverageSessionDates[0]
          : `${coverageSessionDates.length} session dates selected`;

  return (
    <SupportLayout>
      <StepIndicator current={2} />
      <div className="mx-auto grid max-w-5xl gap-4 sm:gap-6 lg:grid-cols-3 lg:items-stretch">
        <div className="rounded-[28px] border border-primary/10 bg-gradient-to-br from-white via-white to-primary/[0.03] p-5 shadow-card sm:p-6 md:p-8 lg:col-span-2">
          <h1 className="mb-1 text-2xl font-bold text-primary">Create Support Inquiry</h1>
          <p className="mb-6 text-sm text-muted-foreground">
            {pageDescription}
          </p>

          <div className="space-y-5">
            <div className="space-y-2">
              <Label>Inquiry Category</Label>
              <Select
                value={technicalSubcategory}
                onValueChange={(value) => setTechnicalSubcategory(value as TechnicalSubcategory)}
              >
                <SelectTrigger className="h-11">
                  <SelectValue placeholder="Select a category" />
                </SelectTrigger>
                <SelectContent>
                  {inquiryPlatforms.map((item) => (
                    <SelectItem key={item} value={item}>{item}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {isCoverageFlow ? (
              <div className="space-y-5 rounded-2xl border border-primary/10 bg-primary/[0.03] p-4">
                <div className="grid gap-5 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label>Tutor</Label>
                    <Select value={coverageTutor} onValueChange={handleCoverageTutorChange} disabled={isLoadingCoverageTutors}>
                      <SelectTrigger className="h-11">
                        <SelectValue placeholder={isLoadingCoverageTutors ? "Loading tutors..." : "Choose tutor"} />
                      </SelectTrigger>
                      <SelectContent>
                        {coverageTutorOptions.length > 0 ? (
                          coverageTutorOptions.map((item) => (
                            <SelectItem key={item} value={item}>{item}</SelectItem>
                          ))
                        ) : (
                          <div className="px-3 py-2 text-sm text-muted-foreground">
                            {isLoadingCoverageTutors ? "Loading tutors..." : "No tutors available."}
                          </div>
                        )}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label>Module</Label>
                    <Select
                      value={coverageModule}
                      onValueChange={handleCoverageModuleChange}
                      disabled={!coverageTutor || isLoadingCoverageModules}
                    >
                      <SelectTrigger className="h-11">
                        <SelectValue
                          placeholder={
                            !coverageTutor
                              ? "Choose tutor first"
                              : isLoadingCoverageModules
                                ? "Loading modules..."
                                : "Choose module"
                          }
                        />
                      </SelectTrigger>
                      <SelectContent>
                        {coverageModuleOptions.length > 0 ? (
                          coverageModuleOptions.map((item) => (
                            <SelectItem key={item} value={item}>{item}</SelectItem>
                          ))
                        ) : (
                          <div className="px-3 py-2 text-sm text-muted-foreground">
                            {!coverageTutor
                              ? "Choose tutor first."
                              : isLoadingCoverageModules
                                ? "Loading modules..."
                                : "No modules available."}
                          </div>
                        )}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="grid gap-5 md:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
                  <div className="space-y-2">
                    <Label>Time</Label>
                    <Select
                      value={coverageTime}
                      onValueChange={handleCoverageTimeChange}
                      disabled={!coverageModule || isLoadingCoverageTimes}
                    >
                      <SelectTrigger className="h-11">
                        <SelectValue
                          placeholder={
                            !coverageModule
                              ? "Choose module first"
                              : isLoadingCoverageTimes
                                ? "Loading times..."
                                : "Choose time"
                          }
                        />
                      </SelectTrigger>
                      <SelectContent>
                        {coverageTimeOptions.length > 0 ? (
                          coverageTimeOptions.map((item) => (
                            <SelectItem key={item.label} value={item.label}>
                              <span className="flex w-full items-center justify-between gap-3">
                                <span className="truncate">{item.label}</span>
                                {item.completed ? (
                                  <span className="shrink-0 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-amber-700">
                                    Completed
                                  </span>
                                ) : null}
                              </span>
                            </SelectItem>
                          ))
                        ) : (
                          <div className="px-3 py-2 text-sm text-muted-foreground">
                            {!coverageModule
                              ? "Choose module first."
                              : isLoadingCoverageTimes
                                ? "Loading times..."
                                : "No times available."}
                          </div>
                        )}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label>Session Date</Label>
                    <DropdownMenu
                      onOpenChange={(open) => {
                        if (
                          open
                          && coverageTutor
                          && coverageModule
                          && coverageTime
                          && coverageSessionDateOptions.length === 0
                          && !isLoadingCoverageSessionDates
                        ) {
                          loadCoverageSessionDateOptions(coverageTutor, coverageModule, coverageTime);
                        }
                      }}
                    >
                      <DropdownMenuTrigger asChild>
                        <Button
                          type="button"
                          variant="outline"
                          disabled={!coverageTime || isLoadingCoverageSessionDates}
                          className="h-11 w-full justify-between rounded-xl border-primary/12 bg-white px-3 font-normal text-foreground shadow-sm hover:bg-white"
                        >
                          <span className="truncate text-left">
                            {coverageSessionDateTriggerLabel}
                          </span>
                          <ChevronDown className="ml-2 h-4 w-4 shrink-0 text-muted-foreground" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent
                        align="start"
                        className="w-[min(92vw,32rem)] overflow-hidden rounded-2xl border border-primary/12 bg-white/95 p-0 text-foreground shadow-[0_24px_60px_rgba(35,27,103,0.16)] backdrop-blur"
                      >
                        <div className="border-b border-primary/8 px-4 py-3">
                          <div className="text-sm font-semibold text-foreground">
                            Select one or more upcoming sessions
                          </div>
                          <p className="mt-1 text-xs text-muted-foreground">
                            {coverageSessionDates.length > 0
                              ? `${coverageSessionDates.length} ${coverageSessionDates.length === 1 ? "date" : "dates"} selected`
                              : "Choose all matching session dates for this request."}
                          </p>
                        </div>
                        <div className="max-h-[min(22rem,60vh)] overflow-y-auto p-2">
                          {coverageSessionDateOptions.length > 0 ? (
                            coverageSessionDateOptions.map((item) => (
                              <DropdownMenuCheckboxItem
                                key={item}
                                checked={coverageSessionDates.includes(item)}
                                onSelect={(event) => event.preventDefault()}
                                onCheckedChange={() => toggleCoverageSessionDate(item)}
                                className="min-h-11 rounded-xl py-2.5 pl-10 pr-3 text-sm font-medium text-foreground outline-none transition-all focus:bg-primary/[0.06] focus:text-foreground data-[state=checked]:bg-primary/[0.08] data-[state=checked]:text-primary"
                              >
                                <span className="whitespace-normal break-words leading-5">{item}</span>
                              </DropdownMenuCheckboxItem>
                            ))
                          ) : (
                            <div className="rounded-xl border border-dashed border-primary/10 px-3 py-3 text-sm text-muted-foreground">
                              {!coverageTime
                                ? "Choose time first."
                                : isLoadingCoverageSessionDates
                                  ? "Loading session dates..."
                                  : "No upcoming session dates available."}
                            </div>
                          )}
                        </div>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </div>

                <div className="space-y-4 rounded-2xl border border-primary/10 bg-white/70 p-4 shadow-sm">
                  <div>
                    <Label>Session Details</Label>
                    <p className="mt-1 max-w-2xl text-xs leading-5 text-muted-foreground">
                      Session numbers are auto-calculated from the training plan. You can still adjust them, and each selected session can have its own subject.
                    </p>
                  </div>

                  {coverageSessionDates.length > 0 ? (
                    <div className="space-y-3">
                      {coverageSessionDates.map((sessionDate, index) => (
                        <div
                          key={sessionDate}
                          className="rounded-2xl border border-primary/10 bg-background/90 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]"
                        >
                          <div className="mb-3 text-sm font-semibold text-foreground">
                            Session {index + 1}
                          </div>
                          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_148px] lg:items-end">
                            <div className="space-y-2">
                              <Label htmlFor={`session-subject-${sessionDate}`}>Session Subject</Label>
                              <Input
                                id={`session-subject-${sessionDate}`}
                                placeholder="Write the session subject"
                                value={coverageSessionSubjectByDate[sessionDate] || ""}
                                onChange={(event) => handleCoverageSessionSubjectChange(sessionDate, event.target.value)}
                                className="h-11 rounded-xl border-primary/12 bg-white shadow-none"
                              />
                            </div>

                            <div className="space-y-2">
                              <Label
                                htmlFor={`session-number-${sessionDate}`}
                                className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground"
                              >
                                Session No.
                              </Label>
                              <Input
                                id={`session-number-${sessionDate}`}
                                inputMode="numeric"
                                pattern="[0-9]*"
                                placeholder="No."
                                value={coverageSessionNumberByDate[sessionDate] || ""}
                                onChange={(event) => handleCoverageSessionNumberChange(sessionDate, event.target.value)}
                                className="h-11 rounded-xl border-primary/12 bg-white text-center font-semibold shadow-none"
                              />
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="rounded-2xl border border-dashed border-primary/12 bg-background/80 px-4 py-3 text-sm text-muted-foreground">
                      Choose session date(s) first to unlock the session details.
                    </div>
                  )}
                </div>

                {coverageOptionsError && (
                  <p className="text-sm text-destructive">
                    {coverageOptionsError}
                  </p>
                )}

              </div>
            ) : (
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
            )}

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
            {isCoverageFlow && (
              <>
                <div className="border-b border-primary/10 py-4">
                  <dt className="text-[15px] font-bold text-foreground">Tutor</dt>
                  <dd className="mt-1 text-[15px] font-medium">{coverageTutor || "-"}</dd>
                </div>
                <div className="border-b border-primary/10 py-4">
                  <dt className="text-[15px] font-bold text-foreground">Module</dt>
                  <dd className="mt-1 text-[15px] font-medium">{coverageModule || "-"}</dd>
                </div>
                <div className="border-b border-primary/10 py-4">
                  <dt className="text-[15px] font-bold text-foreground">Time</dt>
                  <dd className="mt-1 text-[15px] font-medium">{coverageTime || "-"}</dd>
                </div>
                <div className="border-b border-primary/10 py-4">
                  <dt className="text-[15px] font-bold text-foreground">Session Details</dt>
                  <dd className="mt-2">
                    {coverageSessionDates.length > 0 ? (
                      <div className="space-y-2">
                        {coverageSessionDates.map((sessionDate, index) => {
                          const sessionNumber = (
                            coverageSessionNumberByDate[sessionDate]
                            || getDefaultCoverageSessionNumber(sessionDate, coverageSessionDateOptions)
                          ).trim();
                          const sessionSubject = (coverageSessionSubjectByDate[sessionDate] || "").trim();

                          return (
                            <div
                              key={sessionDate}
                              className="rounded-2xl border border-primary/10 bg-white/80 px-3 py-2.5 shadow-sm"
                            >
                              <div className="text-sm font-semibold text-foreground">
                                Session {index + 1}
                              </div>
                              <div className="mt-1 text-xs font-medium text-muted-foreground">
                                {sessionDate}
                              </div>
                              <div className="mt-2 text-sm font-medium text-foreground">
                                Number: {sessionNumber || "-"}
                              </div>
                              <div className="mt-1 text-sm font-medium text-foreground">
                                Subject: {sessionSubject || "-"}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <span className="text-[15px] font-medium">-</span>
                    )}
                  </dd>
                </div>
              </>
            )}
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
