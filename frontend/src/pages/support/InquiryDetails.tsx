import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, ArrowRight, ChevronDown, FileText, Paperclip, Search, UserRound, X } from "lucide-react";
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
import { Checkbox } from "@/components/ui/checkbox";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
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
import {
  type EvidenceFile,
  type SubmittedForLearner,
  type TechnicalSubcategory,
} from "@/context/SupportContext";
import { useSupport } from "@/context/useSupport";
import {
  buildCoverageInquiry,
  fetchCoverageOptions,
  fetchCoverageTimeOptions,
  isCoverageSubcategory,
  parseCoverageInquiry,
  type CoverageTimeOption,
} from "@/lib/coverageSupport";
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

const getExtension = (name: string) => {
  const dotIndex = name.lastIndexOf(".");
  return dotIndex === -1 ? "" : name.slice(dotIndex).toLowerCase();
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

type RequestForMode = "self" | "learner";
const SUBJECT_MAX_LENGTH = 120;
const isValidEmailFormat = (email: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());

const InquiryDetails = () => {
  const navigate = useNavigate();
  const { ticket, updateTicket, clearBookingSummary } = useSupport();
  const initialCoverageDetails = parseCoverageInquiry(ticket.inquiry);
  const [technicalSubcategory, setTechnicalSubcategory] = useState<TechnicalSubcategory>(ticket.technicalSubcategory);
  const [subject, setSubject] = useState(ticket.subject);
  const [inquiry, setInquiry] = useState(
    isCoverageSubcategory(ticket.technicalSubcategory) && initialCoverageDetails ? "" : ticket.inquiry,
  );
  const [requestFor, setRequestFor] = useState<RequestForMode>(ticket.submittedForLearner ? "learner" : "self");
  const [learnerSearch, setLearnerSearch] = useState("");
  const [learnerResults, setLearnerResults] = useState<SubmittedForLearner[]>([]);
  const [selectedSubmittedForLearner, setSelectedSubmittedForLearner] = useState<SubmittedForLearner | null>(ticket.submittedForLearner);
  const [submittedForNotificationEmail, setSubmittedForNotificationEmail] = useState(
    ticket.submittedForLearner?.notificationEmail || ticket.submittedForLearner?.email || "",
  );
  const [notifySubmittedForLearner, setNotifySubmittedForLearner] = useState(ticket.notifySubmittedForLearner);
  const [isSearchingLearners, setIsSearchingLearners] = useState(false);
  const [learnerSearchError, setLearnerSearchError] = useState("");
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
  const [previewFile, setPreviewFile] = useState<EvidenceFile | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const coverageSessionDateRequestRef = useRef(0);
  const canUseCoverage = ticket.requesterSource !== "kbc_users_data";
  const canSubmitForLearner = ticket.requesterSource !== "kbc_users_data" || ticket.requesterRole === "coach" || ticket.requesterRole === "employer";
  const availableInquiryPlatforms = canUseCoverage
    ? inquiryPlatforms
    : inquiryPlatforms.filter((item) => item !== "Coverage");
  const selectedCoverageSessionNumbers = coverageSessionDates.map(
    (sessionDate) => (coverageSessionNumberByDate[sessionDate] || getDefaultCoverageSessionNumber(sessionDate, coverageSessionDateOptions)).trim(),
  );
  const selectedCoverageSessionSubjects = coverageSessionDates.map(
    (sessionDate) => (coverageSessionSubjectByDate[sessionDate] || "").trim(),
  );
  const availableCoverageTimeOptions = coverageTimeOptions.filter((item) => !item.completed);

  const isCoverageFlow = canUseCoverage && isCoverageSubcategory(technicalSubcategory);
  const hasSubmittedForLearner = requestFor !== "learner" || Boolean(selectedSubmittedForLearner);
  const trimmedSubmittedForNotificationEmail = submittedForNotificationEmail.trim();
  const hasValidSubmittedForNotificationEmail = !notifySubmittedForLearner
    || (Boolean(selectedSubmittedForLearner) && isValidEmailFormat(trimmedSubmittedForNotificationEmail));
  const hasSubject = subject.trim().length > 0;
  const canSubmit = isCoverageFlow
    ? Boolean(
      hasSubject
      && hasSubmittedForLearner
      && hasValidSubmittedForNotificationEmail
      && technicalSubcategory
      && coverageTutor
      && coverageModule
      && coverageTime
      && coverageSessionDates.length > 0
      && selectedCoverageSessionSubjects.every((value) => value.length > 0),
    )
    : Boolean(hasSubject && hasSubmittedForLearner && hasValidSubmittedForNotificationEmail && technicalSubcategory && inquiry.trim().length > 0);

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
    if (!canUseCoverage && technicalSubcategory === "Coverage") {
      setTechnicalSubcategory("");
    }
  }, [canUseCoverage, technicalSubcategory]);

  useEffect(() => {
    if (!canSubmitForLearner) {
      setRequestFor("self");
      setSelectedSubmittedForLearner(null);
      setSubmittedForNotificationEmail("");
      setNotifySubmittedForLearner(false);
      setLearnerSearch("");
      setLearnerResults([]);
      setLearnerSearchError("");
    }
  }, [canSubmitForLearner]);

  useEffect(() => {
    if (!canSubmitForLearner || requestFor !== "learner") {
      setLearnerResults([]);
      setLearnerSearchError("");
      setIsSearchingLearners(false);
      return;
    }

    const normalizedQuery = learnerSearch.trim();
    if (normalizedQuery.length < 2) {
      setLearnerResults([]);
      setLearnerSearchError("");
      setIsSearchingLearners(false);
      return;
    }

    let cancelled = false;
    const timer = window.setTimeout(() => {
      setIsSearchingLearners(true);
      setLearnerSearchError("");

      const searchParams = new URLSearchParams({
        q: normalizedQuery,
        limit: "12",
        requesterEmail: ticket.email,
      });

      void fetch(`/api/learners/search?${searchParams.toString()}`)
        .then(async (response) => {
          const payload = (await response.json().catch(() => null)) as
            | {
                message?: string;
                learners?: SubmittedForLearner[];
              }
            | null;

          if (cancelled) {
            return;
          }

          if (!response.ok) {
            setLearnerResults([]);
            setLearnerSearchError(payload?.message || "We could not search learners right now.");
            return;
          }

          setLearnerResults(Array.isArray(payload?.learners) ? payload.learners : []);
        })
        .catch(() => {
          if (!cancelled) {
            setLearnerResults([]);
            setLearnerSearchError("We could not connect to the learner search service.");
          }
        })
        .finally(() => {
          if (!cancelled) {
            setIsSearchingLearners(false);
          }
        });
    }, 300);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [canSubmitForLearner, learnerSearch, requestFor]);

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

        const nextAvailableTimeOptions = options.filter((option) => !option.completed);

        setCoverageTimeOptions(options);
        setCoverageTime((currentTime) => (
          currentTime && !nextAvailableTimeOptions.some((option) => option.label === currentTime) ? "" : currentTime
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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- Keep session-date loading tied to the selected coverage inputs only.
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
    if (selectedFiles.length > 0) {
      const nextFiles = await Promise.all(selectedFiles.map(toEvidenceFile));
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
      const submittedForLearner = canSubmitForLearner && requestFor === "learner"
        ? selectedSubmittedForLearner
          ? {
              ...selectedSubmittedForLearner,
              notificationEmail: trimmedSubmittedForNotificationEmail || selectedSubmittedForLearner.email,
            }
          : null
        : null;

      clearBookingSummary();
      updateTicket({
        id: ticket.id || "",
        learnerName: ticket.learnerName,
        email: ticket.email,
        requesterRole: ticket.requesterRole,
        requesterSource: ticket.requesterSource,
        category: "Technical",
        technicalSubcategory,
        subject: subject.trim(),
        inquiry: submittedInquiry,
        submittedForLearner,
        notifySubmittedForLearner: Boolean(submittedForLearner && notifySubmittedForLearner && isValidEmailFormat(submittedForLearner.notificationEmail || "")),
        evidence,
        status: ticket.id ? ticket.status : "Open",
        statusReason: ticket.id ? ticket.statusReason : "",
        assignedAgentId: ticket.id ? ticket.assignedAgentId : null,
        assignedTeam: ticket.id ? ticket.assignedTeam : "Unassigned",
        slaStatus: ticket.id ? ticket.slaStatus : "Pending Review",
        createdAt: ticket.id ? ticket.createdAt : "",
        chatState: ticket.id ? ticket.chatState : "open",
        liveChatRequested: ticket.id ? ticket.liveChatRequested : false,
        chatHistory: ticket.id ? ticket.chatHistory : [],
      });
      navigate("/support/options");
    } catch {
      toast.error("We could not save these inquiry details. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const previewKind = previewFile ? getPreviewKind(previewFile) : null;
  const pageDescription = isCoverageFlow
    ? "Add a subject, then select the tutor, module, time, session date, and session details."
    : "Choose the inquiry category, add a subject, and describe the issue.";

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
      <div className="mx-auto max-w-4xl">
        <div className="rounded-[28px] border border-primary/10 bg-gradient-to-br from-white via-white to-primary/[0.03] p-5 shadow-card sm:p-6 md:p-8">
          <h1 className="mb-1 text-2xl font-bold text-primary">Create Support Inquiry</h1>
          <p className="mb-6 text-sm text-muted-foreground">
            {pageDescription}
          </p>

          <div className="space-y-5">
            {canSubmitForLearner && (
              <div className="space-y-3 rounded-2xl border border-primary/10 bg-white/70 p-4 shadow-sm">
                <div>
                  <Label>Who is this request for?</Label>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">
                    Keep yourself as the requester, or attach the ticket to a learner who asked you for help.
                  </p>
                </div>

                <RadioGroup
                  value={requestFor}
                  onValueChange={(value) => {
                    const nextRequestFor = value as RequestForMode;
                    setRequestFor(nextRequestFor);
                    if (nextRequestFor === "self") {
                      setSelectedSubmittedForLearner(null);
                      setSubmittedForNotificationEmail("");
                      setNotifySubmittedForLearner(false);
                      setLearnerSearch("");
                      setLearnerResults([]);
                    }
                  }}
                  className="grid gap-3 sm:grid-cols-2"
                >
                  <Label
                    htmlFor="request-for-self"
                    className={`flex cursor-pointer items-start gap-3 rounded-2xl border px-4 py-3 text-left transition-all ${
                      requestFor === "self"
                        ? "border-primary bg-primary/[0.06] text-primary shadow-soft"
                        : "border-primary/10 bg-white hover:border-primary/25"
                    }`}
                  >
                    <RadioGroupItem id="request-for-self" value="self" className="mt-1" />
                    <span>
                      <span className="block font-semibold">For myself</span>
                      <span className="mt-1 block text-xs leading-5 text-muted-foreground">
                        The ticket is about the signed-in requester.
                      </span>
                    </span>
                  </Label>

                  <Label
                    htmlFor="request-for-learner"
                    className={`flex cursor-pointer items-start gap-3 rounded-2xl border px-4 py-3 text-left transition-all ${
                      requestFor === "learner"
                        ? "border-primary bg-primary/[0.06] text-primary shadow-soft"
                        : "border-primary/10 bg-white hover:border-primary/25"
                    }`}
                  >
                    <RadioGroupItem id="request-for-learner" value="learner" className="mt-1" />
                    <span>
                      <span className="block font-semibold">For a learner</span>
                      <span className="mt-1 block text-xs leading-5 text-muted-foreground">
                        Search KBC learners and keep the requester linked as the submitter.
                      </span>
                    </span>
                  </Label>
                </RadioGroup>

                {requestFor === "learner" && (
                  <div className="space-y-3 rounded-2xl border border-primary/10 bg-background/80 p-4">
                    {selectedSubmittedForLearner ? (
                      <div className="rounded-2xl border border-primary/15 bg-white p-4">
                        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                          <div className="flex min-w-0 items-start gap-3">
                            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-primary/[0.08] text-primary">
                              <UserRound className="h-5 w-5" />
                            </div>
                            <div className="min-w-0">
                              <div className="font-semibold text-foreground">
                                {selectedSubmittedForLearner.fullName}
                              </div>
                              <div className="mt-1 break-all text-sm text-muted-foreground">
                                Official email: {selectedSubmittedForLearner.email}
                              </div>
                              {selectedSubmittedForLearner.externalLearnerId && (
                                <div className="mt-1 text-xs text-muted-foreground">
                                  Learner ID: {selectedSubmittedForLearner.externalLearnerId}
                                </div>
                              )}
                            </div>
                          </div>
                          <Button
                            type="button"
                            variant="outline"
                            className="rounded-full"
                            onClick={() => {
                              setSelectedSubmittedForLearner(null);
                              setSubmittedForNotificationEmail("");
                              setNotifySubmittedForLearner(false);
                              setLearnerSearch("");
                            }}
                          >
                            Change
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <div className="space-y-2">
                        <Label htmlFor="learner-search">Search learner</Label>
                        <div className="relative">
                          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                          <Input
                            id="learner-search"
                            value={learnerSearch}
                            onChange={(event) => setLearnerSearch(event.target.value)}
                            placeholder="Type learner name, email, or learner ID..."
                            className="h-11 rounded-xl pl-10"
                          />
                        </div>

                        {learnerSearch.trim().length > 0 && learnerSearch.trim().length < 2 && (
                          <p className="text-xs text-muted-foreground">Type at least 2 characters to search.</p>
                        )}
                        {isSearchingLearners && (
                          <p className="text-xs text-muted-foreground">Searching learners...</p>
                        )}
                        {learnerSearchError && (
                          <p className="text-xs text-destructive">{learnerSearchError}</p>
                        )}
                        {!isSearchingLearners && learnerSearch.trim().length >= 2 && !learnerSearchError && learnerResults.length === 0 && (
                          <p className="text-xs text-muted-foreground">No matching learners found.</p>
                        )}

                        {learnerResults.length > 0 && (
                          <div className="overflow-hidden rounded-2xl border border-primary/10 bg-white shadow-soft">
                            {learnerResults.map((learner) => (
                              <button
                                key={learner.id}
                                type="button"
                                onClick={() => {
                                  setSelectedSubmittedForLearner(learner);
                                  setSubmittedForNotificationEmail(learner.notificationEmail || learner.email);
                                  setLearnerResults([]);
                                  setLearnerSearch("");
                                }}
                                className="flex w-full flex-col gap-1 border-b border-primary/8 px-4 py-3 text-left transition-colors last:border-b-0 hover:bg-primary/[0.05]"
                              >
                                <span className="font-semibold text-foreground">{learner.fullName}</span>
                                <span className="break-all text-xs text-muted-foreground">
                                  {learner.email}
                                  {learner.externalLearnerId ? ` • ID: ${learner.externalLearnerId}` : ""}
                                </span>
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    )}

                    {selectedSubmittedForLearner ? (
                      <div className="space-y-2 rounded-2xl border border-primary/10 bg-white px-4 py-3">
                        <div className="flex items-center justify-between gap-3">
                          <Label htmlFor="submitted-for-notification-email">Notification email</Label>
                          <span className="rounded-full border border-primary/10 bg-primary/[0.05] px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.16em] text-primary">
                            Ticket only
                          </span>
                        </div>
                        <Input
                          id="submitted-for-notification-email"
                          type="email"
                          value={submittedForNotificationEmail}
                          onChange={(event) => setSubmittedForNotificationEmail(event.target.value)}
                          placeholder={selectedSubmittedForLearner.email}
                          className="h-11 rounded-xl"
                        />
                        <p className="text-xs leading-5 text-muted-foreground">
                          This does not update the learner official record. It is used only if learner notification is enabled for this ticket.
                        </p>
                        {notifySubmittedForLearner && !hasValidSubmittedForNotificationEmail ? (
                          <p className="text-xs font-medium text-destructive">
                            Please enter a valid notification email before continuing.
                          </p>
                        ) : null}
                      </div>
                    ) : null}

                    <label className={`flex items-start gap-3 rounded-2xl border border-primary/10 bg-white px-4 py-3 text-sm ${
                      selectedSubmittedForLearner ? "cursor-pointer" : "cursor-not-allowed opacity-70"
                    }`}
                    >
                      <Checkbox
                        checked={notifySubmittedForLearner}
                        disabled={!selectedSubmittedForLearner}
                        onCheckedChange={(checked) => setNotifySubmittedForLearner(Boolean(checked))}
                        className="mt-1"
                      />
                      <span>
                        <span className="block font-semibold text-foreground">Notify learner by email</span>
                        <span className="mt-1 block text-xs leading-5 text-muted-foreground">
                          Off by default. If selected, the learner receives an email after the ticket is submitted.
                        </span>
                      </span>
                    </label>
                  </div>
                )}
              </div>
            )}

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
                  {availableInquiryPlatforms.map((item) => (
                    <SelectItem key={item} value={item}>{item}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <div className="flex items-end justify-between gap-3">
                <Label htmlFor="ticket-subject">Subject</Label>
                <span className="text-xs text-muted-foreground">
                  {subject.length}/{SUBJECT_MAX_LENGTH}
                </span>
              </div>
              <Input
                id="ticket-subject"
                required
                maxLength={SUBJECT_MAX_LENGTH}
                value={subject}
                onChange={(event) => setSubject(event.target.value)}
                placeholder="Write a short title for this issue..."
                className="h-11 rounded-xl"
              />
              <p className="text-xs leading-5 text-muted-foreground">
                Keep this as a short title. Add the full explanation in Issue Details below.
              </p>
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
                                : "No upcoming modules available."}
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
                        {availableCoverageTimeOptions.length > 0 ? (
                          availableCoverageTimeOptions.map((item) => (
                            <SelectItem key={item.label} value={item.label}>
                              {item.label}
                            </SelectItem>
                          ))
                        ) : (
                          <div className="px-3 py-2 text-sm text-muted-foreground">
                            {!coverageModule
                              ? "Choose module first."
                              : isLoadingCoverageTimes
                                ? "Loading times..."
                                : coverageTimeOptions.length > 0
                                  ? "No upcoming times available."
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
                <Label>Issue Details</Label>
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
                  You can upload any file type. Multiple files are supported.
                </p>
                <input
                  ref={fileRef}
                  type="file"
                  multiple
                  className="hidden"
                  onChange={(event) => void onFiles(event.target.files)}
                />
              </div>
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
                {isSubmitting ? "Saving..." : "Next"}
                {!isSubmitting && <ArrowRight className="w-4 h-4 ml-2" />}
              </Button>
            </div>
          </div>
        </div>

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
