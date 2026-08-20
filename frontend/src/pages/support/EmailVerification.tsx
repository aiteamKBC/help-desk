import { useState, useEffect, useRef } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Mail, AlertTriangle, ArrowRight, ListChecks, MessageSquarePlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { SupportLayout } from "@/components/support/SupportLayout";
import { KentCrestMark } from "@/components/support/KentCrestMark";
import { StepIndicator } from "@/components/support/StepIndicator";
import {
  type RequesterRole,
  type RequesterSource,
  type Ticket,
} from "@/context/SupportContext";
import { useSupport } from "@/context/useSupport";
import { type ApiBookingSummary } from "@/lib/supportBooking";
import { adminPortalReturnQueryParam, clearAdminPortalReturnFlag } from "@/lib/adminSession";

const isValidEmailFormat = (email: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());

const getVerificationErrorState = (
  status: number,
  payload: { exists?: boolean; message?: string } | null,
) => {
  if (status === 400) {
    return {
      title: "Invalid Email",
      message: payload?.message || "Please enter a valid email address.",
    };
  }

  if (status === 404) {
    return {
      title: "Email Not Found",
      message: payload?.message || "This email is not registered in our records.",
    };
  }

  if (payload?.message?.toLowerCase().includes("microsoft entra")) {
    return {
      title: "Microsoft Entra Setup Required",
      message: payload.message,
    };
  }

  if (status === 502 && import.meta.env.DEV) {
    return {
      title: "Support API Offline",
      message:
        payload?.message ||
        "The frontend is running, but the Django backend on 127.0.0.1:3001 is unavailable. Start or restart the backend and try again.",
    };
  }

  if (status === 503) {
    return {
      title: "Verification Unavailable",
      message:
        payload?.message ||
        (import.meta.env.DEV
          ? "The support API is running, but it cannot reach the support data service right now. Check the database connection and try again."
          : "The verification service is unavailable right now. Please try again in a moment."),
    };
  }

  return {
    title: "Verification Unavailable",
    message: payload?.message || "The verification service is unavailable right now. Please try again in a moment.",
  };
};

const getVerificationRequestFailureMessage = () =>
  import.meta.env.DEV
    ? "We could not reach the support API. Make sure the Django backend is running on 127.0.0.1:3001, then try again."
    : "We could not verify your email right now. Please try again.";

interface RestoredTicketPayload {
  id: string;
  learnerName?: string;
  email: string;
  requesterRole?: RequesterRole;
  requesterSource?: RequesterSource;
  category: "" | "Learning" | "Technical" | "Others";
  technicalSubcategory: "" | "AI Team" | "Aptem" | "Coverage" | "LMS" | "Teams" | "Others";
  subject?: string;
  inquiry: string;
  aiTeamPersonName?: string;
  aiTeamPersonEmail?: string;
  submittedForLearner?: Ticket["submittedForLearner"];
  notifySubmittedForLearner?: boolean;
  status: "Open" | "Pending" | "Closed";
  statusReason?: string;
  assignedAgentId?: number | null;
  assignedTeam: string;
  slaStatus: string;
  createdAt: string;
  chatState?: "open" | "closed";
  liveChatRequested?: boolean;
}

const EmailVerification = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { ticket, setTicket, setBookingSummary, clearBookingSummary } = useSupport();
  const prefillEmail = searchParams.get("email")?.trim().toLowerCase() || "";
  const [email, setEmail] = useState(ticket.email || prefillEmail);
  const autoSubmittedRef = useRef(false);
  const [errorTitle, setErrorTitle] = useState("Invalid Email");
  const [errorMessage, setErrorMessage] = useState("Please enter a valid email address.");
  const [errorOpen, setErrorOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [existingRequestOpen, setExistingRequestOpen] = useState(false);
  const [requesterProfile, setRequesterProfile] = useState<{
    learnerName: string;
    requesterRole: RequesterRole;
    requesterSource: RequesterSource;
  } | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get(adminPortalReturnQueryParam) !== "1") {
      clearAdminPortalReturnFlag();
    }
  }, []);

  useEffect(() => {
    if (!prefillEmail || autoSubmittedRef.current) return;
    if (!isValidEmailFormat(prefillEmail)) return;
    autoSubmittedRef.current = true;
    submitEmail(prefillEmail);
  }, [prefillEmail]); // eslint-disable-line react-hooks/exhaustive-deps

  const startNewTicket = (
    trimmedEmail: string,
    learnerName: string,
    requesterRole: RequesterRole,
    requesterSource: RequesterSource,
  ) => {
    setTicket({
      id: "",
      learnerName,
      email: trimmedEmail,
      requesterRole,
      requesterSource,
      category: "",
      technicalSubcategory: "",
      subject: "",
      inquiry: "",
      aiTeamPersonName: "",
      aiTeamPersonEmail: "",
      submittedForLearner: null,
      notifySubmittedForLearner: false,
      evidence: [],
      status: "Open",
      statusReason: "",
      assignedAgentId: null,
      assignedTeam: "Unassigned",
      slaStatus: "Pending Review",
      createdAt: "",
      chatState: "open",
      liveChatRequested: false,
      chatHistory: [],
    });
    clearBookingSummary();
    setExistingRequestOpen(false);
    navigate("/support/inquiry");
  };

  const showRequesterDashboard = async (
    trimmedEmail: string,
    learnerName: string,
    requesterRole: RequesterRole,
    requesterSource: RequesterSource,
  ) => {
    setRequesterProfile({ learnerName, requesterRole, requesterSource });
    setTicket({
      id: "",
      learnerName,
      email: trimmedEmail,
      requesterRole,
      requesterSource,
      category: "",
      technicalSubcategory: "",
      subject: "",
      inquiry: "",
      aiTeamPersonName: "",
      aiTeamPersonEmail: "",
      submittedForLearner: null,
      notifySubmittedForLearner: false,
      evidence: [],
      status: "Open",
      statusReason: "",
      assignedAgentId: null,
      assignedTeam: "Unassigned",
      slaStatus: "Pending Review",
      createdAt: "",
      chatState: "open",
      liveChatRequested: false,
      chatHistory: [],
    });
    clearBookingSummary();
    setExistingRequestOpen(true);
  };

  const submitEmail = async (trimmedEmail: string) => {
    setIsSubmitting(true);

    try {
      const response = await fetch("/api/verify-email", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: trimmedEmail }),
      });

      const payload = (await response.json().catch(() => null)) as
        | {
            exists?: boolean;
            message?: string;
            requesterRole?: RequesterRole;
            requesterSource?: RequesterSource;
            learner?: { fullName?: string; email?: string };
            ticket?: {
              id: string;
              learnerName?: string;
              email: string;
              requesterRole?: RequesterRole;
              requesterSource?: RequesterSource;
              category: "" | "Learning" | "Technical" | "Others";
              technicalSubcategory: "" | "AI Team" | "Aptem" | "Coverage" | "LMS" | "Teams" | "Others";
              subject?: string;
              inquiry: string;
              aiTeamPersonName?: string;
              aiTeamPersonEmail?: string;
              submittedForLearner?: Ticket["submittedForLearner"];
              notifySubmittedForLearner?: boolean;
              status: "Open" | "Pending" | "Closed";
              statusReason?: string;
              assignedAgentId?: number | null;
              assignedTeam: string;
              slaStatus: string;
              createdAt: string;
              chatState?: "open" | "closed";
              liveChatRequested?: boolean;
            };
            bookingSummary?: ApiBookingSummary | null;
          }
        | null;

      if (response.ok && payload?.exists) {
        const restoredTicket = payload.ticket;
        const learnerName = payload?.learner?.fullName || "";
        const requesterRole = payload?.requesterRole || restoredTicket?.requesterRole || "user";
        const requesterSource = payload?.requesterSource || restoredTicket?.requesterSource || "";

        await showRequesterDashboard(
          trimmedEmail,
          learnerName,
          requesterRole,
          requesterSource,
        );
        return;
      }

      const errorState = getVerificationErrorState(response.status, payload);
      setErrorTitle(errorState.title);
      setErrorMessage(errorState.message);
      setErrorOpen(true);
    } catch (error) {
      console.error("Email verification request failed.", error);
      setErrorTitle("Verification Unavailable");
      setErrorMessage(getVerificationRequestFailureMessage());
      setErrorOpen(true);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleNext = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedEmail = email.trim().toLowerCase();

    if (!isValidEmailFormat(trimmedEmail)) {
      setErrorTitle("Invalid Email");
      setErrorMessage("Please enter a valid email address.");
      setErrorOpen(true);
      return;
    }

    await submitEmail(trimmedEmail);
  };

  return (
    <SupportLayout>
      <StepIndicator current={1} />
      <div className="mx-auto max-w-[22rem] sm:max-w-md">
        <div className="rounded-2xl border bg-card p-6 shadow-card sm:p-8">
          <div className="mb-6 flex flex-col items-center sm:mb-7">
            <KentCrestMark
              variant="full"
              frame="plain"
              className="h-[56px] w-full max-w-[220px] sm:h-[60px] sm:max-w-[248px]"
              imageClassName="object-contain"
            />
            <div className="mt-3 inline-flex items-center gap-2 rounded-full border border-primary/10 bg-primary/[0.04] px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-primary/80 sm:text-[11px] sm:tracking-[0.18em]">
              <span className="h-1.5 w-1.5 rounded-full bg-primary/75" />
              Support Portal
            </div>
          </div>
          <div className="mb-5 text-center sm:mb-6">
            <h1 className="text-[1.8rem] font-semibold leading-tight tracking-[-0.03em] text-foreground sm:text-[2rem]">
              Support Request
            </h1>
          </div>
          <p className="mx-auto mb-6 max-w-[320px] text-center text-sm leading-6 text-muted-foreground sm:mb-7 sm:text-[15px] sm:leading-7">
            {isSubmitting && prefillEmail
              ? "Verifying your account, please wait..."
              : "Enter your registered email address to continue. For learners, this is usually your Aptem email."}
          </p>
          <form onSubmit={handleNext} className="space-y-4 sm:space-y-5">
            <div>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  id="email"
                  type="email"
                  placeholder="Enter your registered email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="h-12 pl-9 text-[15px]"
                  autoFocus
                  required
                />
              </div>
            </div>
            <Button
              type="submit"
              className="h-11 w-full border-0 text-sm font-semibold gradient-primary"
              disabled={isSubmitting}
            >
              {isSubmitting ? "Checking..." : "Next"}
              {!isSubmitting && <ArrowRight className="ml-2 h-4 w-4" />}
            </Button>
          </form>
          <p className="mt-5 text-center text-[11px] leading-5 text-muted-foreground sm:mt-6 sm:text-xs">
            Your role will be identified automatically from your registered account.
          </p>
        </div>
      </div>

      <Dialog open={errorOpen} onOpenChange={setErrorOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <div className="mx-auto h-12 w-12 rounded-full bg-destructive/10 flex items-center justify-center mb-2">
              <AlertTriangle className="h-6 w-6 text-destructive" />
            </div>
            <DialogTitle className="text-center">{errorTitle}</DialogTitle>
            <DialogDescription className="text-center">
              {errorMessage}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button className="w-full" onClick={() => setErrorOpen(false)}>
              Try Again
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={existingRequestOpen} onOpenChange={setExistingRequestOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="text-center">Support Dashboard</DialogTitle>
            <DialogDescription className="text-center">
              Choose what you want to do for this email.
            </DialogDescription>
          </DialogHeader>

          <DialogFooter className="flex-col gap-2 sm:flex-col">
            <Button
              className="w-full border-0 gradient-primary"
              onClick={() => startNewTicket(
                email.trim().toLowerCase(),
                requesterProfile?.learnerName || "",
                requesterProfile?.requesterRole || "user",
                requesterProfile?.requesterSource || "",
              )}
            >
              <MessageSquarePlus className="mr-2 h-4 w-4" />
              Start New Ticket
            </Button>
            <Button
              variant="outline"
              className="w-full"
              onClick={() => {
                setExistingRequestOpen(false);
                navigate("/support/my-tickets");
              }}
            >
              <ListChecks className="mr-2 h-4 w-4" />
              My Tickets
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </SupportLayout>
  );
};

export default EmailVerification;
