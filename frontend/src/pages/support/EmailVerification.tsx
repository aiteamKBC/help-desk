import { useState, useEffect, useRef } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Mail, Info, AlertTriangle, ArrowRight, ListChecks, MessageSquarePlus } from "lucide-react";
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
import "./EmailVerification.css";
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
        "The frontend is running, but the Django backend is unavailable. Restart the development server and try again.",
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
    ? "We could not reach the support API. Make sure the Django backend is running, then try again."
    : "We could not verify your email right now. Please try again.";

const EmailVerification = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { ticket, setTicket, clearBookingSummary } = useSupport();
  const prefillEmail = searchParams.get("email")?.trim().toLowerCase() || "";
  const ssoToken = searchParams.get("token")?.trim() || "";
  const [email, setEmail] = useState(ticket.email || prefillEmail || "ayman.badewi@kentbusinesscollege.com");
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

  // A signed token from the LMS is the only thing that auto-enters the flow (the
  // learner is already authenticated there). A raw ?email= is treated as a
  // prefill only, never auto-submitted, so it cannot be used to impersonate.
  useEffect(() => {
    if (!ssoToken || autoSubmittedRef.current) return;
    autoSubmittedRef.current = true;
    submitSsoToken(ssoToken);
  }, [ssoToken]); // eslint-disable-line react-hooks/exhaustive-deps

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
      coverageSessions: [],
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
    setEmail(trimmedEmail);
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
      coverageSessions: [],
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

  const runVerification = async (request: () => Promise<Response>, emailFallback: string) => {
    setIsSubmitting(true);

    try {
      const response = await request();

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
              technicalSubcategory: "" | "AI Team" | "Aptem" | "Coverage" | "LMS" | "Teams" | "Enrolment" | "Quality" | "Operation" | "Curriculum" | "Others";
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
        const resolvedEmail = (payload?.learner?.email || emailFallback).trim().toLowerCase();

        await showRequesterDashboard(
          resolvedEmail,
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

  const submitEmail = (trimmedEmail: string) =>
    runVerification(
      () =>
        fetch("/api/verify-email", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: trimmedEmail }),
        }),
      trimmedEmail,
    );

  const submitSsoToken = (token: string) =>
    runVerification(
      () =>
        fetch("/api/support/sso", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token }),
        }),
      "",
    );

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
    <SupportLayout landing mainClassName="support-landing-main">
      <aside className="support-hero" aria-label="Kent Business College">
        <div className="support-hero-photo" />
        <div className="support-hero-copy">
          <h2>Support,<br />made simple.</h2>
          <p>Get the help you need, when you need it.</p>
        </div>
      </aside>

      <section className="support-entry" aria-labelledby="support-request-title">
        <div className="support-entry-content">
          <div className="support-entry-steps">
            <StepIndicator current={1} finalLabel="Open" />
          </div>
          <div className="support-entry-heading">
            <h1 id="support-request-title">Support Request</h1>
            <p id="email-description">
              {isSubmitting && ssoToken
                ? "Verifying your account, please wait..."
                : <>Enter your registered email address to continue.<br className="support-description-break" /> For learners, this is usually your Aptem email.</>}
            </p>
          </div>
          <form onSubmit={handleNext} className="support-entry-form">
            <div className="support-email-field">
              <label htmlFor="email" className="sr-only">Registered email address</label>
              <Mail aria-hidden="true" />
              <Input
                id="email"
                type="email"
                autoComplete="email"
                aria-describedby="email-description"
                placeholder="Enter your registered email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoFocus
                required
              />
            </div>
            <Button type="submit" className="support-next-button" disabled={isSubmitting}>
              {isSubmitting ? "Checking..." : "Next"}
              {!isSubmitting && <ArrowRight aria-hidden="true" />}
            </Button>
          </form>
          <div className="support-role-note">
            <Info aria-hidden="true" />
            <p>Your role will be identified automatically from your registered account.</p>
          </div>
        </div>
      </section>
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
