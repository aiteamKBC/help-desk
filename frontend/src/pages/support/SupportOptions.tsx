import { type ComponentType, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  Bot,
  CalendarClock,
  FileText,
  Headphones,
  MessageSquareMore,
  PhoneCall,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { StepIndicator } from "@/components/support/StepIndicator";
import { SupportLayout } from "@/components/support/SupportLayout";
import { SupportMasterHeader } from "@/components/support/SupportMasterHeader";
import {
  type Ticket,
} from "@/context/SupportContext";
import { useSupport } from "@/context/useSupport";
import {
  getSupportResumePath,
  shouldShowStatusStep,
  type SupportChatEntryAction,
} from "@/lib/supportFlow";
import { persistTicketDraft, submitTicketDirectlyForReview } from "@/lib/supportTicketDraft";
import { setTicketBookingProgress } from "@/lib/supportTicketProgress";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import "./SupportOptions.css";

interface SupportOptionAction {
  id: string;
  title: string;
  description: string;
  icon: ComponentType<{ className?: string }>;
  onClick: () => void | Promise<void>;
  disabled?: boolean;
  statusText?: string;
}

const SupportOptions = () => {
  const navigate = useNavigate();
  const { ticket, bookingSummary, clearBookingSummary, updateTicket } = useSupport();
  const [isQuickSubmitting, setIsQuickSubmitting] = useState(false);
  const [teamsCallUrl, setTeamsCallUrl] = useState("");
  const [teamsCallTargetLabel, setTeamsCallTargetLabel] = useState("");
  const [teamsCallMessage, setTeamsCallMessage] = useState("");
  const [isLoadingTeamsCall, setIsLoadingTeamsCall] = useState(false);
  const [isPreparingTeamsCall, setIsPreparingTeamsCall] = useState(false);
  const [isOpeningTeamsCall, setIsOpeningTeamsCall] = useState(false);
  const [hasPreparedTeamsCall, setHasPreparedTeamsCall] = useState(false);
  const isTechTeamFlow = ticket.technicalSubcategory === "AI Team";
  const showTeamsCall = isTechTeamFlow;
  const [isCreatingTicket, setIsCreatingTicket] = useState(false);
  const ticketRef = useRef(ticket);
  const pendingTicketCreationRef = useRef<Promise<Ticket | null> | null>(null);
  const clearedBookingProgressTicketRef = useRef("");

  useEffect(() => {
    ticketRef.current = ticket;
  }, [ticket]);

  useEffect(() => {
    if (!ticket.email) {
      navigate("/support");
      return;
    }

    if (!ticket.id && (!ticket.category || !ticket.inquiry.trim())) {
      navigate("/support/inquiry");
      return;
    }

    if (ticket.id && shouldShowStatusStep(ticket, bookingSummary)) {
      navigate(getSupportResumePath(ticket, bookingSummary));
    }
  }, [bookingSummary, navigate, ticket]);

  useEffect(() => {
    if (!ticket.id || clearedBookingProgressTicketRef.current === ticket.id) {
      return;
    }

    if (shouldShowStatusStep(ticket, bookingSummary)) {
      return;
    }

    clearedBookingProgressTicketRef.current = ticket.id;
    void setTicketBookingProgress(ticket.id, false);
  }, [bookingSummary, ticket]);

  useEffect(() => {
    if (!showTeamsCall) {
      setTeamsCallUrl("");
      setTeamsCallTargetLabel("");
      setTeamsCallMessage("");
      setIsLoadingTeamsCall(false);
      setIsPreparingTeamsCall(false);
      setHasPreparedTeamsCall(false);
      return;
    }

    let cancelled = false;

    const loadTeamsCallContext = async () => {
      setIsLoadingTeamsCall(true);

      try {
        const response = await fetch("/api/teams-call-context");
        const payload = (await response.json().catch(() => null)) as
          | {
              callUrl?: string;
              targetLabel?: string;
              message?: string;
              targets?: string[];
            }
          | null;

        if (cancelled) {
          return;
        }

        if (!response.ok || !payload?.callUrl) {
          setTeamsCallUrl("");
          setTeamsCallTargetLabel("");
          setTeamsCallMessage(payload?.message || "Microsoft Teams calling is not available right now.");
          return;
        }

        setTeamsCallUrl(payload.callUrl);
        setTeamsCallTargetLabel(payload.targetLabel || "");
        setTeamsCallMessage(payload.message || "");
      } catch {
        if (cancelled) {
          return;
        }

        setTeamsCallUrl("");
        setTeamsCallTargetLabel("");
        setTeamsCallMessage("We could not load the Teams call link right now.");
      } finally {
        if (!cancelled) {
          setIsLoadingTeamsCall(false);
        }
      }
    };

    void loadTeamsCallContext();

    return () => {
      cancelled = true;
    };
  }, [showTeamsCall, ticket.id]);

  const ensureTicketCreated = async () => {
    const currentTicket = ticketRef.current;
    if (currentTicket.id) {
      try {
        const nextTicket = await persistTicketDraft(currentTicket);
        ticketRef.current = nextTicket;
        updateTicket(nextTicket);
        return nextTicket;
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "We could not connect to the server. Please try again.");
        return null;
      }
    }

    if (pendingTicketCreationRef.current) {
      return pendingTicketCreationRef.current;
    }

    if (!currentTicket.email || !currentTicket.category || !currentTicket.subject.trim() || !currentTicket.inquiry.trim()) {
      toast.error("Please complete the inquiry details before choosing a support path.");
      navigate(currentTicket.email ? "/support/inquiry" : "/support");
      return null;
    }

    const creationPromise = (async () => {
      setIsCreatingTicket(true);

      try {
        const nextTicket = await persistTicketDraft(currentTicket);
        ticketRef.current = nextTicket;
        updateTicket(nextTicket);
        return nextTicket;
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "We could not connect to the server. Please try again.");
        return null;
      } finally {
        pendingTicketCreationRef.current = null;
        setIsCreatingTicket(false);
      }
    })();

    pendingTicketCreationRef.current = creationPromise;
    return creationPromise;
  };

  const handleContinueToChat = async (entryAction?: SupportChatEntryAction) => {
    const createdTicket = await ensureTicketCreated();
    if (!createdTicket) {
      return;
    }

    clearBookingSummary();
    if (entryAction) {
      navigate("/support/chat", {
        state: {
          entryAction,
        },
      });
      return;
    }

    navigate("/support/chat");
  };

  const prepareQuickCall = async (showSuccessToast = true) => {
    if (isPreparingTeamsCall || hasPreparedTeamsCall) {
      return hasPreparedTeamsCall;
    }

    const targetTicket = await ensureTicketCreated();
    if (!targetTicket) {
      return false;
    }

    setIsPreparingTeamsCall(true);

    try {
      const response = await fetch(`/api/tickets/${encodeURIComponent(targetTicket.id)}/teams-call-request`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
      });
      const payload = (await response.json().catch(() => null)) as
        | {
            message?: string;
          }
        | null;

      if (!response.ok) {
        toast.error(payload?.message || "We could not route this Teams call to the support admin right now.");
        return false;
      }

      setHasPreparedTeamsCall(true);
      updateTicket({
        assignedTeam: "Support Desk",
      });
      ticketRef.current = {
        ...targetTicket,
        assignedTeam: "Support Desk",
      };
      if (showSuccessToast) {
        toast.success(payload?.message || "This Teams call has been assigned to the support admin.");
      }
      return true;
    } catch {
      toast.error("We could not connect to the server. Please try again.");
      return false;
    } finally {
      setIsPreparingTeamsCall(false);
    }
  };

  const handleOpenQuickCall = async () => {
    if (isOpeningTeamsCall) {
      return;
    }

    if (!teamsCallUrl) {
      toast.error(teamsCallMessage || "Microsoft Teams calling is not available right now.");
      return;
    }

    setIsOpeningTeamsCall(true);

    try {
      const prepared = await prepareQuickCall(false);
      if (!prepared) {
        return;
      }

      const openedWindow = window.open(teamsCallUrl, "_blank", "noopener,noreferrer");
      if (!openedWindow) {
        window.location.assign(teamsCallUrl);
      }

      toast.success("Microsoft Teams is opening and the ticket is now assigned to the support admin.");
    } finally {
      setIsOpeningTeamsCall(false);
    }
  };

  const handleQuickSubmit = async () => {
    if (isQuickSubmitting) {
      return;
    }

    setIsQuickSubmitting(true);

    try {
      const targetTicket = await ensureTicketCreated();
      if (!targetTicket) {
        return;
      }

      const submittedTicket = await submitTicketDirectlyForReview(targetTicket);
      clearBookingSummary();
      ticketRef.current = submittedTicket;
      updateTicket(submittedTicket);
      toast.success("Your ticket has been submitted directly for team review.");
      navigate("/support/status");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "We could not connect to the server. Please try again.");
    } finally {
      setIsQuickSubmitting(false);
    }
  };

  const supportActions: SupportOptionAction[] = [
    {
      id: "chatbot",
      title: "Chatbot",
      description: "Open the chatbot immediately and continue the conversation from your saved inquiry.",
      icon: Bot,
      onClick: () => handleContinueToChat(),
      disabled: isCreatingTicket,
      statusText: isCreatingTicket ? "Creating ticket..." : "Open chat",
    },
    {
      id: "live-chat",
      title: ticket.liveChatRequested ? "Live Chat Requested" : "Live Chat",
      description: ticket.liveChatRequested
        ? "Continue to the chat and stay connected while the support team picks up your request."
        : "Open chat and request a live support admin directly from the conversation.",
      icon: MessageSquareMore,
      onClick: () => handleContinueToChat("live-chat"),
      disabled: isCreatingTicket,
      statusText: isCreatingTicket ? "Creating ticket..." : ticket.liveChatRequested ? "Resume" : "Request now",
    },
    {
      id: "booking-session",
      title: "Booking Session",
      description: "Open the dedicated booking page and reserve your support session without the chat popup.",
      icon: CalendarClock,
      onClick: async () => {
        const createdTicket = await ensureTicketCreated();
        if (!createdTicket) {
          return;
        }

        await setTicketBookingProgress(createdTicket.id, true);
        clearBookingSummary();
        navigate("/support/booking", {
          state: {
            returnPath: "/support/options",
          },
        });
      },
      disabled: isCreatingTicket,
      statusText: isCreatingTicket ? "Creating ticket..." : "Book now",
    },
    {
      id: "quick-ticket",
      title: "Submit Ticket Directly",
      description: "Submit the saved inquiry directly to the support team without entering the chat flow.",
      icon: FileText,
      onClick: handleQuickSubmit,
      disabled: isCreatingTicket || isQuickSubmitting,
      statusText: isCreatingTicket ? "Creating ticket..." : isQuickSubmitting ? "Submitting..." : "Send now",
    },
    ...(showTeamsCall
      ? [{
          id: "teams-call",
          title: "Call on Microsoft Teams",
          description: hasPreparedTeamsCall
            ? `Your ticket is already assigned to ${teamsCallTargetLabel || "the support admin"} and ready for the Teams call.`
            : teamsCallTargetLabel
              ? `Open Teams and call ${teamsCallTargetLabel} directly from your saved inquiry.`
              : (teamsCallMessage || "Open Microsoft Teams and place the call directly from this saved inquiry."),
          icon: PhoneCall,
          onClick: handleOpenQuickCall,
          disabled: isCreatingTicket || isLoadingTeamsCall || isPreparingTeamsCall || isOpeningTeamsCall,
          statusText: isCreatingTicket
            ? "Creating ticket..."
            : isLoadingTeamsCall
            ? "Preparing..."
            : isPreparingTeamsCall
              ? "Assigning..."
              : isOpeningTeamsCall
                ? "Opening..."
                : hasPreparedTeamsCall
                  ? "Assigned"
                  : "Start call",
        }]
      : []),
  ];
  const pageTitle = "Choose how you want to continue";
  const pageDescription = showTeamsCall
    ? "Your inquiry details are saved. Pick the route that fits your issue, or open a direct Microsoft Teams call when you want the fastest hand-off."
    : "Your inquiry details are saved. Pick the route that fits your issue and we will take you straight there.";
  const actionTitle = "Support Actions";
  const actionDescription = showTeamsCall
    ? "Everything is in one focused panel. Choose chatbot, live chat, booking, direct ticket submission, or a Microsoft Teams call."
    : "Everything is in one focused panel. Choose chatbot, live chat, booking, or direct ticket submission.";
  const ticketSummaryItems = [
    {
      label: "Requester",
      value: ticket.learnerName || ticket.email || "Requester",
    },
    ...(ticket.submittedForLearner
      ? [{
          label: "Submitted for",
          value: ticket.submittedForLearner.fullName || ticket.submittedForLearner.email,
        }]
      : []),
    {
      label: "Issue Type",
      value: ticket.category
        ? [ticket.category, ticket.technicalSubcategory].filter(Boolean).join(" - ")
        : "Not selected",
    },
    {
      label: "Subject",
      value: ticket.subject || "Not added",
    },
    {
      label: "Current Status",
      value: ticket.id ? (ticket.status || "Open") : "Not submitted yet",
    },
  ];
  return (
    <SupportLayout showHeader={false} fullWidth mainClassName="support-options-main">
      <SupportMasterHeader />

      <div className="support-options-body">
        <div className="support-options-steps">
          <StepIndicator current={3} finalLabel="Open" />
        </div>

        <div className="support-options-shell">
          <div className="support-options-heading">
            <div className="support-options-heading__text">
              <span className="support-options-eyebrow">Support Options</span>
              <h1>{pageTitle}</h1>
              <p>{pageDescription}</p>
            </div>
            <Button variant="ghost" onClick={() => navigate("/support/inquiry")} className="support-options-back">
              <ArrowLeft aria-hidden="true" /> Back
            </Button>
          </div>

          <div
            className={cn(
              "support-options-summary",
              ticketSummaryItems.length >= 5 && "support-options-summary--five",
            )}
          >
            {ticketSummaryItems.map((item) => (
              <div key={item.label} className="support-options-summary__item">
                <div className="support-options-summary__label">{item.label}</div>
                <div className="support-options-summary__value" title={item.value}>
                  {item.value}
                </div>
              </div>
            ))}
          </div>

          <section className="support-options-panel">
            <div className="support-options-panel__header">
              <div className="support-options-panel__intro">
                <div className="support-options-panel__icon" aria-hidden="true">
                  <Headphones />
                </div>
                <div>
                  <h2>{actionTitle}</h2>
                  <p>{actionDescription}</p>
                </div>
              </div>
              <div className="support-options-panel__count">
                {showTeamsCall ? "5 support paths" : "4 support paths"}
              </div>
            </div>

            {showTeamsCall && (
              <div className="support-options-notice">
                <div className="support-options-notice__title">
                  {hasPreparedTeamsCall
                    ? "Teams hand-off is already assigned"
                    : teamsCallTargetLabel
                      ? "Teams target is ready"
                      : "Direct Teams support is available"}
                </div>
                <p>
                  {hasPreparedTeamsCall
                    ? `This ticket is already assigned to ${teamsCallTargetLabel || "the support admin"} and ready for your Teams call.`
                    : teamsCallTargetLabel
                      ? `You can call ${teamsCallTargetLabel} directly in Microsoft Teams from the Teams option below.`
                      : "Your saved inquiry stays attached so you can still submit the ticket directly later if you need written follow-up."}
                </p>
              </div>
            )}

            <div
              className={cn(
                "support-options-grid",
                showTeamsCall ? "support-options-grid--five" : "support-options-grid--four",
              )}
            >
              {supportActions.map((action, index) => {
                const Icon = action.icon;

                return (
                  <button
                    key={action.id}
                    type="button"
                    onClick={() => void action.onClick()}
                    disabled={action.disabled}
                    className="support-options-card"
                    data-action={action.id}
                  >
                    <span className="support-options-card__top">
                      <span className="support-options-card__icon" aria-hidden="true">
                        <Icon />
                      </span>
                      <span className="support-options-card__title">{action.title}</span>
                      <span className="support-options-card__badge" aria-hidden="true">
                        {String(index + 1).padStart(2, "0")}
                      </span>
                    </span>

                    <span className="support-options-card__desc">{action.description}</span>

                    {action.statusText && (
                      <span className="support-options-card__action">
                        {action.statusText}
                        <ArrowRight aria-hidden="true" />
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </section>
        </div>
      </div>
    </SupportLayout>
  );
};

export default SupportOptions;
