import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Mail, AlertTriangle, ArrowRight, CalendarClock, MessageSquarePlus } from "lucide-react";
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
import { type BookingSummary, type RequesterRole, type Ticket, useSupport } from "@/context/SupportContext";
import { getSupportResumePath, isAwaitingSupportReviewTicket } from "@/lib/supportFlow";
import { toBookingSummary, type ApiBookingSummary } from "@/lib/supportBooking";

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
  category: "" | "Learning" | "Technical" | "Others";
  technicalSubcategory: "" | "Aptem" | "LMS" | "Teams";
  inquiry: string;
  status: "Open" | "Pending" | "Closed";
  statusReason?: string;
  assignedAgentId?: number | null;
  assignedTeam: string;
  slaStatus: string;
  createdAt: string;
  chatState?: "open" | "closed";
  liveChatRequested?: boolean;
}

function buildRestoredTicket(
  restoredTicket: RestoredTicketPayload,
  learnerNameFallback: string,
): Ticket {
  return {
    id: restoredTicket.id,
    learnerName: restoredTicket.learnerName || learnerNameFallback,
    email: restoredTicket.email,
    requesterRole: restoredTicket.requesterRole || "user",
    category: restoredTicket.category,
    technicalSubcategory: restoredTicket.technicalSubcategory,
    inquiry: restoredTicket.inquiry,
    evidence: [],
    status: restoredTicket.status,
    statusReason: restoredTicket.statusReason || "",
    assignedAgentId: restoredTicket.assignedAgentId ?? null,
    assignedTeam: restoredTicket.assignedTeam,
    slaStatus: restoredTicket.slaStatus,
    createdAt: restoredTicket.createdAt,
    chatState: restoredTicket.chatState || "open",
    liveChatRequested: restoredTicket.liveChatRequested ?? false,
    chatHistory: [],
  };
}

const EmailVerification = () => {
  const navigate = useNavigate();
  const { ticket, setTicket, setBookingSummary, clearBookingSummary } = useSupport();
  const [email, setEmail] = useState(ticket.email);
  const [errorTitle, setErrorTitle] = useState("Invalid Email");
  const [errorMessage, setErrorMessage] = useState("Please enter a valid email address.");
  const [errorOpen, setErrorOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [existingRequestOpen, setExistingRequestOpen] = useState(false);
  const [existingRequestTicket, setExistingRequestTicket] = useState<Ticket | null>(null);
  const [existingRequestBookingSummary, setExistingRequestBookingSummary] = useState<BookingSummary | null>(null);

  const restoreExistingRequest = (restoredTicket: Ticket, restoredBookingSummary: BookingSummary | null) => {
    setTicket(restoredTicket);
    setBookingSummary(restoredBookingSummary);
    setExistingRequestOpen(false);
    navigate(getSupportResumePath(restoredTicket, restoredBookingSummary));
  };

  const startNewTicket = (trimmedEmail: string, learnerName: string, requesterRole: RequesterRole) => {
    setTicket({
      id: "",
      learnerName,
      email: trimmedEmail,
      requesterRole,
      category: "",
      technicalSubcategory: "",
      inquiry: "",
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

  const handleNext = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedEmail = email.trim().toLowerCase();

    if (!isValidEmailFormat(trimmedEmail)) {
      setErrorTitle("Invalid Email");
      setErrorMessage("Please enter a valid email address.");
      setErrorOpen(true);
      return;
    }

    setIsSubmitting(true);

    try {
      const response = await fetch("/api/verify-email", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ email: trimmedEmail }),
      });

      const payload = (await response.json().catch(() => null)) as
        | {
            exists?: boolean;
            message?: string;
            requesterRole?: RequesterRole;
            learner?: { fullName?: string; email?: string };
            ticket?: {
              id: string;
              learnerName?: string;
              email: string;
              requesterRole?: RequesterRole;
              category: "" | "Learning" | "Technical" | "Others";
              technicalSubcategory: "" | "Aptem" | "LMS" | "Teams";
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
          bookingSummary?: ApiBookingSummary | null;
          }
        | null;

      if (response.ok && payload?.exists) {
        const restoredBookingSummary = toBookingSummary(payload.bookingSummary);
        const restoredTicket = payload.ticket;
        const learnerName = payload?.learner?.fullName || "";
        const requesterRole = payload?.requesterRole || restoredTicket?.requesterRole || "user";

        if (restoredTicket?.id) {
          setExistingRequestTicket(buildRestoredTicket(restoredTicket, learnerName));
          setExistingRequestBookingSummary(restoredBookingSummary);
          setExistingRequestOpen(true);
          return;
        }

        startNewTicket(trimmedEmail, learnerName, requesterRole);
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
            Enter the email address your KBC admin registered for you to continue.
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
            <DialogTitle className="text-center">Existing Support Request Found</DialogTitle>
            <DialogDescription className="text-center">
              We found an active support request for this email. You can continue to the existing request to access your meeting or updates, or start a new ticket.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3">
            {existingRequestTicket ? (
              <div className="rounded-2xl border border-primary/15 bg-primary/5 px-4 py-4 text-center">
                <div className="text-xs font-semibold uppercase tracking-[0.16em] text-primary/80">Current Request</div>
                <div className="mt-2 text-sm text-muted-foreground">
                  {existingRequestTicket.category}
                  {existingRequestTicket.technicalSubcategory ? ` - ${existingRequestTicket.technicalSubcategory}` : ""}
                </div>
                <div className="mt-1 text-sm text-muted-foreground">
                  {existingRequestBookingSummary?.reservationConfirmed
                    ? "Meeting reserved and ready to open."
                    : isAwaitingSupportReviewTicket(existingRequestTicket)
                      ? "Quick ticket submitted and waiting for team review."
                      : existingRequestTicket.status === "Pending"
                        ? "Request is saved and waiting for the next support update."
                        : "Progress saved and available to continue."}
                </div>
              </div>
            ) : null}
          </div>

          <DialogFooter className="flex-col gap-2 sm:flex-col">
            <Button
              className="w-full border-0 gradient-primary"
              onClick={() => {
                if (!existingRequestTicket) {
                  return;
                }
                restoreExistingRequest(existingRequestTicket, existingRequestBookingSummary);
              }}
            >
              <CalendarClock className="mr-2 h-4 w-4" />
              Review Existing Request
            </Button>
            <Button
              variant="outline"
              className="w-full"
              onClick={() => startNewTicket(
                email.trim().toLowerCase(),
                existingRequestTicket?.learnerName || "",
                existingRequestTicket?.requesterRole || "user",
              )}
            >
              <MessageSquarePlus className="mr-2 h-4 w-4" />
              Start New Ticket
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </SupportLayout>
  );
};

export default EmailVerification;
