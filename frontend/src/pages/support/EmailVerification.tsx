import { useState, useEffect, useRef } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Mail, AlertTriangle, ArrowRight, Headphones } from "lucide-react";
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
        <div className="support-hero-wave" aria-hidden="true">
          <svg
            className="support-wave-ribbons"
            viewBox="0 0 1712 913"
            preserveAspectRatio="none"
            focusable="false"
          >
            <defs>
              <clipPath id="support-campus-clip" clipPathUnits="userSpaceOnUse">
                <path d="M0 0H665C718 68 751 151 749 233C746 361 705 482 644 596C578 719 475 820 342 873C253 909 167 913 82 913H0Z" />
              </clipPath>
              <linearGradient id="support-purple-ribbon" gradientUnits="userSpaceOnUse" x1="490" y1="120" x2="415" y2="913">
                <stop offset="0" stopColor="#5310ff" />
                <stop offset="0.52" stopColor="#4810f2" />
                <stop offset="1" stopColor="#5a00f5" />
              </linearGradient>
              <linearGradient id="support-lavender-ribbon" gradientUnits="userSpaceOnUse" x1="470" y1="913" x2="810" y2="65">
                <stop offset="0" stopColor="#5c18f4" />
                <stop offset="0.52" stopColor="#9a74f7" />
                <stop offset="1" stopColor="#c8b5fb" />
              </linearGradient>
              <linearGradient id="support-lavender-soft" gradientUnits="userSpaceOnUse" x1="560" y1="850" x2="860" y2="90">
                <stop offset="0" stopColor="#cbb2fa" stopOpacity="0.9" />
                <stop offset="1" stopColor="#e9e1fd" stopOpacity="0.72" />
              </linearGradient>
              <linearGradient id="support-photo-shade" gradientUnits="userSpaceOnUse" x1="0" y1="330" x2="0" y2="913">
                <stop offset="0.12" stopColor="#2410a8" stopOpacity="0" />
                <stop offset="0.58" stopColor="#2710b6" stopOpacity="0.23" />
                <stop offset="1" stopColor="#25108f" stopOpacity="0.48" />
              </linearGradient>
            </defs>
            <path
              className="support-wave-corner-band"
              d="M1270 0C1325 85 1425 140 1550 172C1635 194 1690 245 1712 310V0Z"
              fill="#e8dfff"
              fillOpacity="0.55"
            />
            <path
              className="support-wave-corner"
              d="M1300 0C1350 70 1440 120 1560 150C1640 170 1690 215 1712 270V0Z"
              fill="#fbfaff"
              fillOpacity="0.85"
            />
            <path
              className="support-wave-layer support-wave-layer-soft"
              d="M0 0H850C816 75 804 159 801 248C796 386 767 506 719 621C674 727 634 817 647 866C653 887 664 902 680 913H0Z"
              fill="url(#support-lavender-soft)"
            />
            <path
              className="support-wave-layer support-wave-layer-lavender"
              d="M0 0H793C777 74 775 155 771 240C765 370 733 490 679 607C628 718 574 811 559 863C553 883 554 900 562 913H0Z"
              fill="url(#support-lavender-ribbon)"
            />
            <path
              className="support-wave-layer support-wave-layer-purple"
              d="M0 0H690C741 70 770 153 766 239C760 369 716 492 651 607C579 733 487 831 390 874C370 884 353 897 343 913H0Z"
              fill="url(#support-purple-ribbon)"
            />
            <g className="support-wave-photo" clipPath="url(#support-campus-clip)">
              <image
                href="/support-campus.png"
                x="-32"
                y="-12"
                width="790"
                height="925"
                preserveAspectRatio="xMidYMin slice"
              />
              <rect width="790" height="913" fill="url(#support-photo-shade)" />
            </g>
          </svg>
        </div>
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
        <DialogContent
          className="support-dashboard-modal"
          overlayClassName="bg-[#0b1026]/40 backdrop-blur-[1px]"
        >
          <DialogHeader className="support-dashboard-header">
            <Headphones className="support-dashboard-icon" aria-hidden="true" strokeWidth={1.8} />
            <DialogTitle>Support Dashboard</DialogTitle>
            <DialogDescription>
              Choose what you want to do for this email.
            </DialogDescription>
          </DialogHeader>

          <DialogFooter className="support-dashboard-actions">
            <Button
              className="support-dashboard-primary"
              onClick={() => startNewTicket(
                email.trim().toLowerCase(),
                requesterProfile?.learnerName || "",
                requesterProfile?.requesterRole || "user",
                requesterProfile?.requesterSource || "",
              )}
            >
              Start New Ticket
            </Button>
            <Button
              variant="outline"
              className="support-dashboard-secondary"
              onClick={() => {
                setExistingRequestOpen(false);
                navigate("/support/my-tickets");
              }}
            >
              My Tickets
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </SupportLayout>
  );
};

export default EmailVerification;
