import { type ComponentType, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  Bot,
  CalendarClock,
  FileText,
  Headphones,
  PhoneCall,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { StepIndicator } from "@/components/support/StepIndicator";
import { SupportLayout } from "@/components/support/SupportLayout";
import { useSupport } from "@/context/SupportContext";
import {
  getSupportResumePath,
  isQuickTicketOnlyRequesterRole,
  quickTicketReason,
  shouldShowStatusStep,
  type SupportChatEntryAction,
} from "@/lib/supportFlow";
import { toast } from "sonner";

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
  const quickTicketOnlyFlow = isQuickTicketOnlyRequesterRole(ticket.requesterRole);

  useEffect(() => {
    if (!ticket.id) {
      navigate(ticket.email ? "/support/inquiry" : "/support");
      return;
    }

    if (shouldShowStatusStep(ticket, bookingSummary)) {
      navigate(getSupportResumePath(ticket, bookingSummary));
    }
  }, [bookingSummary, navigate, ticket]);

  useEffect(() => {
    if (!quickTicketOnlyFlow) {
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
  }, [quickTicketOnlyFlow, ticket.id]);

  const handleContinueToChat = (entryAction?: SupportChatEntryAction) => {
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
    if (!ticket.id || isPreparingTeamsCall || hasPreparedTeamsCall) {
      return hasPreparedTeamsCall;
    }

    setIsPreparingTeamsCall(true);

    try {
      const response = await fetch(`/api/tickets/${encodeURIComponent(ticket.id)}/teams-call-request`, {
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
    if (!ticket.id || isOpeningTeamsCall) {
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
    if (!ticket.id || isQuickSubmitting) {
      return;
    }

    setIsQuickSubmitting(true);

    try {
      const response = await fetch(`/api/tickets/${encodeURIComponent(ticket.id)}/chat-history`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          status: "Pending",
          statusReason: quickTicketReason,
          messages: ticket.chatHistory.map((message) => ({
            sender: message.sender,
            text: message.text,
            timestamp: message.timestamp,
          })),
        }),
      });

      const payload = (await response.json().catch(() => null)) as
        | {
            message?: string;
            ticket?: {
              status?: "Open" | "Pending" | "Closed";
              statusReason?: string;
              assignedTeam?: string;
              slaStatus?: string;
              createdAt?: string;
            };
          }
        | null;

      if (!response.ok || !payload?.ticket) {
        toast.error(payload?.message || "We could not submit the ticket right now.");
        return;
      }

      clearBookingSummary();
      updateTicket({
        status: payload.ticket.status || "Pending",
        statusReason: payload.ticket.statusReason || quickTicketReason,
        assignedTeam: payload.ticket.assignedTeam || ticket.assignedTeam,
        slaStatus: payload.ticket.slaStatus || ticket.slaStatus,
        createdAt: payload.ticket.createdAt || ticket.createdAt,
      });
      toast.success("Your ticket has been submitted directly for team review.");
      navigate("/support/status");
    } catch {
      toast.error("We could not connect to the server. Please try again.");
    } finally {
      setIsQuickSubmitting(false);
    }
  };

  const supportActions: SupportOptionAction[] = quickTicketOnlyFlow
    ? [
        {
          id: "teams-call",
          title: "Call on Microsoft Teams",
          description: hasPreparedTeamsCall
            ? `Your ticket is already assigned to ${teamsCallTargetLabel || "the support admin"} and ready for the Teams call.`
            : teamsCallTargetLabel
              ? `Open Teams and call ${teamsCallTargetLabel} directly from your saved inquiry.`
              : (teamsCallMessage || "Open Microsoft Teams and place the call directly from this saved inquiry."),
          icon: PhoneCall,
          onClick: handleOpenQuickCall,
          disabled: isLoadingTeamsCall || isPreparingTeamsCall || isOpeningTeamsCall,
          statusText: isLoadingTeamsCall
            ? "Preparing..."
            : isPreparingTeamsCall
              ? "Assigning..."
              : isOpeningTeamsCall
                ? "Opening..."
                : hasPreparedTeamsCall
                  ? "Assigned"
                  : "Start call",
        },
        {
          id: "quick-ticket",
          title: "Submit Ticket Directly",
          description: "Send the saved inquiry straight to the support team for review without opening chat first.",
          icon: FileText,
          onClick: handleQuickSubmit,
          disabled: isQuickSubmitting,
          statusText: isQuickSubmitting ? "Submitting..." : "Send now",
        },
      ]
    : [
        {
          id: "chatbot",
          title: "Chatbot",
          description: "Open the chatbot immediately and continue the conversation from your saved inquiry.",
          icon: Bot,
          onClick: () => handleContinueToChat(),
          statusText: "Open chat",
        },
        {
          id: "live-chat",
          title: ticket.liveChatRequested ? "Live Chat Requested" : "Live Chat",
          description: ticket.liveChatRequested
            ? "Continue to the chat and stay connected while the support team picks up your request."
            : "Open chat and request a live support admin directly from the conversation.",
          icon: Headphones,
          onClick: () => handleContinueToChat("live-chat"),
          statusText: ticket.liveChatRequested ? "Resume" : "Request now",
        },
        {
          id: "booking-session",
          title: "Booking Session",
          description: "Open the dedicated booking page and reserve your support session without the chat popup.",
          icon: CalendarClock,
          onClick: () => {
            clearBookingSummary();
            navigate("/support/booking", {
              state: {
                returnPath: "/support/options",
              },
            });
          },
          statusText: "Book now",
        },
        {
          id: "quick-ticket",
          title: "Submit Ticket Directly",
          description: "Submit the saved inquiry directly to the support team without entering the chat flow.",
          icon: FileText,
          onClick: handleQuickSubmit,
          disabled: isQuickSubmitting,
          statusText: isQuickSubmitting ? "Submitting..." : "Send now",
        },
      ];
  const pageTitle = quickTicketOnlyFlow
    ? "Choose quick call or submit ticket directly"
    : "Choose how you want to continue";
  const pageDescription = quickTicketOnlyFlow
    ? "Your inquiry details are saved. Pick the fastest support route below: start a Teams call or submit the ticket directly for review."
    : "Your inquiry details are saved. Pick the route that fits your issue and we will take you straight there.";
  const actionTitle = quickTicketOnlyFlow ? "Quick Support Actions" : "Support Actions";
  const actionDescription = quickTicketOnlyFlow
    ? "Everything is in one focused panel. Choose to open a Teams call or send the ticket directly from here."
    : "Everything is in one focused panel. Choose chatbot, live chat, booking, or direct ticket submission.";
  const ticketSummaryItems = [
    {
      label: "Requester",
      value: ticket.learnerName || ticket.email || "Requester",
    },
    {
      label: "Issue Type",
      value: ticket.category
        ? [ticket.category, ticket.technicalSubcategory].filter(Boolean).join(" - ")
        : "Not selected",
    },
    {
      label: "Current Status",
      value: ticket.status || "Open",
    },
  ];

  return (
    <SupportLayout>
      <StepIndicator current={quickTicketOnlyFlow ? 3 : 2.5} />
      <div className="mx-auto max-w-6xl">
        <div className="relative overflow-hidden rounded-[32px] border border-primary/10 bg-[radial-gradient(circle_at_top_right,rgba(98,73,238,0.14),transparent_32%),linear-gradient(135deg,#ffffff_0%,#ffffff_58%,rgba(98,73,238,0.055)_100%)] p-6 shadow-card md:p-8 lg:p-10">
          <div className="pointer-events-none absolute -right-24 top-20 h-64 w-64 rounded-full bg-primary/10 blur-3xl" />
          <div className="pointer-events-none absolute bottom-0 right-10 h-28 w-72 rounded-full bg-sky-200/25 blur-3xl" />

          <div className="relative flex items-start justify-between gap-4">
            <div className="inline-flex items-center gap-2 rounded-full border border-primary/15 bg-white/75 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-primary/80 shadow-soft backdrop-blur">
              <span className="h-1.5 w-1.5 rounded-full bg-primary/75" />
              Support Options
            </div>
            <Button variant="ghost" onClick={() => navigate("/support/inquiry")} className="shrink-0 rounded-full bg-white/60 hover:bg-white">
              <ArrowLeft className="w-4 h-4 mr-2" /> Back
            </Button>
          </div>

          <div className="relative mt-6 grid gap-6 lg:grid-cols-[minmax(0,0.95fr)_minmax(360px,1.15fr)] lg:items-end">
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-primary md:text-3xl">
                {pageTitle}
              </h1>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground md:text-base">
                {pageDescription}
              </p>
            </div>

            <div className="grid gap-3 rounded-[26px] border border-primary/10 bg-white/70 p-4 shadow-soft backdrop-blur sm:grid-cols-3">
              {ticketSummaryItems.map((item) => (
                <div key={item.label} className="rounded-2xl border border-primary/10 bg-white/80 px-4 py-3">
                  <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                    {item.label}
                  </div>
                  <div className="mt-1 truncate text-sm font-semibold text-foreground" title={item.value}>
                    {item.value}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <section className="relative mt-7 rounded-[28px] border border-primary/12 bg-card/90 p-5 shadow-soft backdrop-blur md:p-6">
            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
              <div className="flex items-start gap-4">
                <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-soft">
                  {quickTicketOnlyFlow ? <PhoneCall className="h-6 w-6" /> : <Bot className="h-6 w-6" />}
                </div>
                <div>
                  <h2 className="text-xl font-semibold text-foreground">
                    {actionTitle}
                  </h2>
                  <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
                    {actionDescription}
                  </p>
                </div>
              </div>
              <div className="rounded-full border border-primary/10 bg-primary/[0.05] px-4 py-2 text-xs font-semibold text-primary">
                {quickTicketOnlyFlow ? "2 fast options" : "4 support paths"}
              </div>
            </div>

            {quickTicketOnlyFlow && (
              <div className="mt-5 rounded-[24px] border border-primary/15 bg-primary/[0.04] px-4 py-4">
                <div className="text-sm font-semibold text-foreground">
                  {hasPreparedTeamsCall
                    ? "Teams hand-off is already assigned"
                    : teamsCallTargetLabel
                      ? "Teams target is ready"
                      : "Direct Teams support is available"}
                </div>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">
                  {hasPreparedTeamsCall
                    ? `This ticket is already assigned to ${teamsCallTargetLabel || "the support admin"} and ready for your Teams call.`
                    : teamsCallTargetLabel
                      ? `You can call ${teamsCallTargetLabel} directly in Microsoft Teams from the first option below.`
                      : "Your saved inquiry stays attached so you can still submit the ticket directly later if you need written follow-up."}
                </p>
              </div>
            )}

            <div className={`mt-6 grid gap-4 ${quickTicketOnlyFlow ? "lg:grid-cols-2" : "lg:grid-cols-2"}`}>
              {supportActions.map((action, index) => {
                const Icon = action.icon;

                return (
                  <button
                    key={action.id}
                    type="button"
                    onClick={() => void action.onClick()}
                    disabled={action.disabled}
                    className="group relative flex min-h-[148px] w-full flex-col justify-between overflow-hidden rounded-[24px] border border-primary/12 bg-gradient-to-br from-white via-white to-primary/[0.045] p-5 text-left shadow-soft outline-none transition-all duration-500 ease-out hover:-translate-y-1 hover:scale-[1.015] hover:border-primary/35 hover:bg-primary/[0.035] hover:shadow-[0_24px_70px_rgba(98,73,238,0.18)] focus-visible:-translate-y-1 focus-visible:scale-[1.015] focus-visible:border-primary/45 focus-visible:ring-4 focus-visible:ring-primary/15 active:translate-y-0 active:scale-[0.995] disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:translate-y-0 disabled:hover:scale-100"
                  >
                    <span className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_18%_18%,rgba(98,73,238,0.14),transparent_28%),linear-gradient(120deg,transparent_0%,rgba(255,255,255,0.75)_48%,transparent_62%)] opacity-0 transition-opacity duration-500 group-hover:opacity-100 group-focus-visible:opacity-100" />
                    <span className="pointer-events-none absolute -right-16 -top-16 h-32 w-32 rounded-full bg-primary/15 blur-2xl opacity-0 transition-all duration-700 group-hover:right-0 group-hover:top-0 group-hover:opacity-100 group-focus-visible:right-0 group-focus-visible:top-0 group-focus-visible:opacity-100" />
                    <span className="flex items-start justify-between gap-4">
                      <span className="relative flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-primary/[0.08] text-primary ring-1 ring-primary/10 transition-all duration-500 group-hover:rotate-3 group-hover:scale-110 group-hover:bg-primary group-hover:text-primary-foreground group-hover:shadow-[0_14px_32px_rgba(98,73,238,0.28)] group-focus-visible:rotate-3 group-focus-visible:scale-110 group-focus-visible:bg-primary group-focus-visible:text-primary-foreground">
                        <Icon className="h-5 w-5" />
                      </span>
                      <span className="relative rounded-full border border-primary/10 bg-white/80 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground transition-colors duration-500 group-hover:border-primary/25 group-hover:text-primary">
                        {String(index + 1).padStart(2, "0")}
                      </span>
                    </span>

                    <span className="relative mt-5 block">
                      <span className="block text-base font-semibold text-foreground">
                        {action.title}
                      </span>
                      <span className="mt-2 block text-sm leading-6 text-muted-foreground">
                        {action.description}
                      </span>
                    </span>

                    <span className="relative mt-5 flex items-center justify-between gap-3 text-primary">
                      {action.statusText && (
                        <span className="text-sm font-semibold">
                          {action.statusText}
                        </span>
                      )}
                      <span className="ml-auto flex h-9 w-9 items-center justify-center rounded-full bg-primary/[0.08] transition-all duration-500 group-hover:translate-x-1 group-hover:bg-primary group-hover:text-primary-foreground group-hover:shadow-[0_10px_24px_rgba(98,73,238,0.24)] group-focus-visible:translate-x-1 group-focus-visible:bg-primary group-focus-visible:text-primary-foreground">
                        <ArrowRight className="h-4 w-4 transition-transform duration-500 group-hover:translate-x-0.5 group-focus-visible:translate-x-0.5" />
                      </span>
                    </span>
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
