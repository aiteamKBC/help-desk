import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  Bot,
  CalendarClock,
  Clock3,
  FileText,
  Headphones,
  PhoneCall,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { StepIndicator } from "@/components/support/StepIndicator";
import { SupportLayout } from "@/components/support/SupportLayout";
import { useSupport } from "@/context/SupportContext";
import { getSupportResumePath, isQuickTicketOnlyRequesterRole, quickTicketReason, shouldShowStatusStep } from "@/lib/supportFlow";
import { toast } from "sonner";

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
    if (!ticket.email) {
      navigate("/support");
      return;
    }

    if (!ticket.id) {
      navigate("/support/inquiry");
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

  const handleContinueToChat = () => {
    clearBookingSummary();
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

  const handleQuickCallPathClick = (event: React.MouseEvent<HTMLElement>) => {
    if (!quickTicketOnlyFlow) {
      return;
    }

    const clickTarget = event.target;
    if (clickTarget instanceof HTMLElement && clickTarget.closest("button, a, input, textarea, select")) {
      return;
    }

    void prepareQuickCall();
  };

  const handleQuickCallPathKeyDown = (event: React.KeyboardEvent<HTMLElement>) => {
    if (!quickTicketOnlyFlow) {
      return;
    }

    if (event.key !== "Enter" && event.key !== " ") {
      return;
    }

    event.preventDefault();
    void prepareQuickCall();
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
      toast.success("Your quick ticket has been submitted for team review.");
      navigate("/support/status");
    } catch {
      toast.error("We could not connect to the server. Please try again.");
    } finally {
      setIsQuickSubmitting(false);
    }
  };

  return (
    <SupportLayout>
      <StepIndicator current={quickTicketOnlyFlow ? 3 : 2.5} />
      <div className="max-w-5xl mx-auto">
        <div className="p-6 border border-primary/10 bg-gradient-to-br from-white via-white to-primary/[0.04] rounded-[28px] shadow-card md:p-8">
          <div className="flex items-start justify-between gap-4">
            <div className="inline-flex items-center gap-2 rounded-full border border-primary/15 bg-primary/[0.06] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-primary/80">
              <span className="h-1.5 w-1.5 rounded-full bg-primary/75" />
              Support Options
            </div>
            <Button variant="ghost" onClick={() => navigate("/support/inquiry")} className="shrink-0">
              <ArrowLeft className="w-4 h-4 mr-2" /> Back
            </Button>
          </div>
          <h1 className="mt-4 text-2xl font-bold text-primary">
            {quickTicketOnlyFlow ? "Choose quick call or quick ticket" : "Choose how you want to continue"}
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
            {quickTicketOnlyFlow
              ? "Your inquiry details are saved. You can either request a quick support call directly or send the inquiry as a quick ticket for team review."
              : "Your inquiry details are saved. You can continue with the chatbot and escalate to a live agent or a booked session when needed, or submit the ticket directly for faster team review."}
          </p>

          <div className="grid gap-4 mt-6 md:grid-cols-2">
            <section
              className={quickTicketOnlyFlow
                ? "flex h-full cursor-pointer flex-col rounded-[26px] border border-primary/12 bg-card/90 p-5 shadow-soft transition hover:border-primary/35"
                : "flex h-full flex-col rounded-[26px] border border-primary/12 bg-card/90 p-5 shadow-soft"}
              onClick={handleQuickCallPathClick}
              onKeyDown={handleQuickCallPathKeyDown}
              role={quickTicketOnlyFlow ? "button" : undefined}
              tabIndex={quickTicketOnlyFlow ? 0 : undefined}
              aria-pressed={quickTicketOnlyFlow ? hasPreparedTeamsCall : undefined}
            >
              <div className="flex items-start gap-3">
                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-soft">
                  {quickTicketOnlyFlow ? <PhoneCall className="h-5 w-5" /> : <Bot className="h-5 w-5" />}
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-foreground">
                    {quickTicketOnlyFlow ? "Call on Microsoft Teams" : "Chatbot and Live Chat"}
                  </h2>
                  <p className="mt-1 text-sm leading-6 text-muted-foreground">
                    {quickTicketOnlyFlow
                      ? "Skip chat and place a direct Teams call to the support team from the inquiry you already saved."
                      : "Start with the chatbot, then request live chat or book a support session if you still need more help."}
                  </p>
                </div>
              </div>

              <div className="grid gap-3 mt-5">
                {quickTicketOnlyFlow ? (
                  <>
                    <div className="rounded-2xl border border-primary/10 bg-primary/[0.04] px-4 py-3">
                      <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                        <PhoneCall className="h-4 w-4 text-primary" />
                        Direct Teams ring
                      </div>
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">
                        Open Microsoft Teams and place the call without entering the chatbot or live chat flow.
                      </p>
                    </div>
                    <div className="rounded-2xl border border-primary/10 bg-primary/[0.04] px-4 py-3">
                      <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                        <Clock3 className="h-4 w-4 text-primary" />
                        Inquiry stays saved
                      </div>
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">
                        Your registered email and saved inquiry stay available in case you need to fall back to a quick ticket after the call.
                      </p>
                    </div>
                    <div className="rounded-2xl border border-primary/10 bg-primary/[0.04] px-4 py-3">
                      <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                        <Headphones className="h-4 w-4 text-primary" />
                        {hasPreparedTeamsCall ? "Ticket assigned" : (teamsCallTargetLabel ? "Teams target ready" : "Teams hand-off")}
                      </div>
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">
                        {hasPreparedTeamsCall
                          ? `This ticket is already assigned to ${teamsCallTargetLabel || "the support admin"} and ready for the Teams call.`
                          : teamsCallTargetLabel
                          ? `This button will call ${teamsCallTargetLabel} directly in Microsoft Teams.`
                          : (teamsCallMessage || "Microsoft Teams will ask you to confirm the call before it starts.")}
                      </p>
                    </div>
                  </>
                ) : (
                  <>
                    <div className="rounded-2xl border border-primary/10 bg-primary/[0.04] px-4 py-3">
                      <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                        <Bot className="h-4 w-4 text-primary" />
                        Instant chatbot support
                      </div>
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">
                        Get immediate guidance based on the inquiry you just entered.
                      </p>
                    </div>
                    <div className="rounded-2xl border border-primary/10 bg-primary/[0.04] px-4 py-3">
                      <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                        <Headphones className="h-4 w-4 text-primary" />
                        Live agent escalation
                      </div>
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">
                        Ask for human support directly from chat whenever the bot is not enough.
                      </p>
                    </div>
                    <div className="rounded-2xl border border-primary/10 bg-primary/[0.04] px-4 py-3">
                      <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                        <CalendarClock className="h-4 w-4 text-primary" />
                        Book a support session
                      </div>
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">
                        Reserve a guided session directly from the chat flow.
                      </p>
                    </div>
                  </>
                )}
              </div>

              <div className="mt-5 flex flex-1 items-end">
                <Button
                  onClick={quickTicketOnlyFlow ? () => void handleOpenQuickCall() : handleContinueToChat}
                  disabled={quickTicketOnlyFlow ? (isLoadingTeamsCall || isPreparingTeamsCall || isOpeningTeamsCall || !teamsCallUrl) : false}
                  className="w-full border-0 gradient-primary"
                >
                  {quickTicketOnlyFlow
                    ? (isLoadingTeamsCall
                      ? "Preparing Teams Call..."
                      : isPreparingTeamsCall
                        ? "Assigning to Admin..."
                      : isOpeningTeamsCall
                        ? "Opening Teams..."
                        : "Call on Teams")
                    : "Continue to Chat"}
                  <ArrowRight className="w-4 h-4 ml-2" />
                </Button>
              </div>
            </section>

            <section className="flex h-full flex-col rounded-[26px] border border-primary/12 bg-card/90 p-5 shadow-soft">
              <div className="flex items-start gap-3">
                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-secondary text-foreground shadow-soft">
                  <FileText className="h-5 w-5" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-foreground">
                    {quickTicketOnlyFlow ? "Submit Quick Ticket" : "Create Ticket Quickly"}
                  </h2>
                  <p className="mt-1 text-sm leading-6 text-muted-foreground">
                    Skip the chat and send your saved inquiry straight to the support team for review.
                  </p>
                </div>
              </div>

              <div className="mt-5 rounded-[24px] border border-dashed border-primary/20 bg-primary/[0.03] px-4 py-4">
                <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                  <Clock3 className="h-4 w-4 text-primary" />
                  Faster hand-off
                </div>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">
                  We will mark this request as a quick ticket so the team can pick it up without opening
                  the chat step first.
                </p>
              </div>

              <div className="mt-5 flex flex-1 items-end">
                <Button
                  variant="outline"
                  onClick={() => void handleQuickSubmit()}
                  disabled={isQuickSubmitting}
                  className="w-full"
                >
                  {isQuickSubmitting
                    ? "Submitting..."
                    : quickTicketOnlyFlow
                      ? "Submit Quick Ticket"
                      : "Create Ticket Quickly"}
                  {!isQuickSubmitting && <ArrowRight className="w-4 h-4 ml-2" />}
                </Button>
              </div>
            </section>
          </div>
        </div>
      </div>
    </SupportLayout>
  );
};

export default SupportOptions;
