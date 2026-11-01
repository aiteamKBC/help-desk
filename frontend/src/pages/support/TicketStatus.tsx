import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { CalendarCheck, CheckCircle2, ExternalLink, MessageSquare, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { SupportLayout } from "@/components/support/SupportLayout";
import { StepIndicator } from "@/components/support/StepIndicator";
import { type ChatMessage } from "@/context/SupportContext";
import { useSupport } from "@/context/useSupport";
import { canReturnToChat, getSupportResumePath, isAwaitingMeetingTicket, isAwaitingSupportReviewTicket, quickTicketReason, shouldShowStatusStep } from "@/lib/supportFlow";
import { toBookingSummary, type ApiBookingSummary } from "@/lib/supportBooking";
import { toast } from "sonner";

const ticketConversationPollIntervalMs = 2500;

const formatConversationTime = (value: string) => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
};

const getDisplayedTicketStatus = (status: unknown, statusReason: unknown) => {
  if (status === "Open" || status === "Pending" || status === "Closed") {
    return status;
  }

  if (statusReason === quickTicketReason || status === quickTicketReason) {
    return "Pending";
  }

  return "-";
};

const TicketStatus = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { ticket, bookingSummary, updateTicket, setBookingSummary, clearBookingSummary } = useSupport();

  useEffect(() => {
    const urlTicket = searchParams.get("ticket");
    const urlEmail = searchParams.get("email");
    if (urlTicket && urlTicket !== ticket.id) {
      updateTicket({ id: urlTicket, email: urlEmail || ticket.email, status: ticket.status || "Open" });
    }
    if (urlTicket) {
      const next = new URLSearchParams(searchParams);
      next.delete("ticket");
      next.delete("email");
      setSearchParams(next, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const isAwaitingMeeting = isAwaitingMeetingTicket(ticket);
  const isAwaitingSupportReview = isAwaitingSupportReviewTicket(ticket);
  const hasBookingSummary = Boolean(bookingSummary);
  const isReservationConfirmed = Boolean(bookingSummary?.reservationConfirmed);
  const hasStatusStep = shouldShowStatusStep(ticket, bookingSummary);
  const canCancelMeeting = hasBookingSummary || isAwaitingMeeting;
  const hasLocalChatTranscript = ticket.chatHistory.some((message) => message.source !== "intro");
  const [serverChatHistoryCount, setServerChatHistoryCount] = useState<number | null>(null);
  const hasServerChatTranscript = typeof serverChatHistoryCount === "number" && serverChatHistoryCount > 1;
  const shouldShowTicketConversation = Boolean(
    ticket.id
    && !ticket.liveChatRequested
    && ticket.status !== "Closed"
    && !hasBookingSummary
    && !isAwaitingMeeting,
  );
  const showChatAction = !shouldShowTicketConversation && (canReturnToChat(ticket) || hasLocalChatTranscript || hasServerChatTranscript);
  const chatActionLabel = canReturnToChat(ticket) && ticket.status !== "Closed" ? "View Chat" : "View Chat Transcript";
  const displayedTicketStatus = getDisplayedTicketStatus(ticket.status, ticket.statusReason);
  const [cancelMeetingOpen, setCancelMeetingOpen] = useState(false);
  const [isCancellingMeeting, setIsCancellingMeeting] = useState(false);
  const [conversationMessages, setConversationMessages] = useState<ChatMessage[]>(ticket.chatHistory);
  const conversationMessagesRef = useRef<ChatMessage[]>(ticket.chatHistory);
  const [conversationInput, setConversationInput] = useState("");
  const [isSendingConversationMessage, setIsSendingConversationMessage] = useState(false);

  useEffect(() => {
    if (!ticket.email || !ticket.id || hasStatusStep) {
      return;
    }

    // An Open ticket arriving here (e.g. the learner tapped "Open" on the LMS
    // widget) is a live-chat venue, not a redirect target. Only kick them away
    // when there is nothing on this page for them.
    if (ticket.id && ticket.status === "Open") {
      return;
    }

    navigate(getSupportResumePath(ticket, bookingSummary));
  }, [bookingSummary, hasStatusStep, navigate, ticket]);

  useEffect(() => {
    if (!ticket.id) {
      return;
    }

    let cancelled = false;

    const loadTicketConversation = async () => {
      try {
        const response = await fetch(`/api/tickets/${encodeURIComponent(ticket.id)}/chat-history`);
        const payload = (await response.json().catch(() => null)) as
          | {
              ticket?: {
                status?: "Open" | "Pending" | "Closed";
                statusReason?: string;
                assignedAgentId?: number | null;
                assignedTeam?: string;
                slaStatus?: string;
                createdAt?: string;
                chatState?: "open" | "closed";
                liveChatRequested?: boolean;
                isQuickTicket?: boolean;
              };
              bookingSummary?: ApiBookingSummary | null;
              historyCount?: number;
              chatHistory?: ChatMessage[];
            }
          | null;

        if (!response.ok || cancelled) {
          return;
        }

        if (payload?.ticket) {
          updateTicket({
            status: payload.ticket.status || ticket.status,
            statusReason: payload.ticket.statusReason || ticket.statusReason,
            assignedAgentId: payload.ticket.assignedAgentId ?? ticket.assignedAgentId,
            assignedTeam: payload.ticket.assignedTeam || ticket.assignedTeam,
            slaStatus: payload.ticket.slaStatus || ticket.slaStatus,
            createdAt: payload.ticket.createdAt || ticket.createdAt,
            chatState: payload.ticket.chatState ?? ticket.chatState,
            liveChatRequested: payload.ticket.liveChatRequested ?? ticket.liveChatRequested,
            isQuickTicket: payload.ticket.isQuickTicket ?? ticket.isQuickTicket,
          });
        }

        if ("bookingSummary" in (payload || {})) {
          setBookingSummary(toBookingSummary(payload?.bookingSummary));
        }
        if (typeof payload?.historyCount === "number") {
          setServerChatHistoryCount(payload.historyCount);
        }
        if (payload?.chatHistory) {
          conversationMessagesRef.current = payload.chatHistory;
          setConversationMessages(payload.chatHistory);
          updateTicket({ chatHistory: payload.chatHistory });
        }
      } catch {
        // The status page can still show the saved ticket state even if the refresh fetch fails.
      }
    };

    void loadTicketConversation();
    const intervalId = window.setInterval(() => void loadTicketConversation(), ticketConversationPollIntervalMs);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticket.id]);

  const handleConversationSend = async () => {
    const text = conversationInput.trim();
    if (!ticket.id || !text || isSendingConversationMessage) {
      return;
    }

    const previousMessages = conversationMessagesRef.current;
    const nextMessage: ChatMessage = {
      id: crypto.randomUUID(),
      clientMessageId: crypto.randomUUID(),
      sender: "user",
      text,
      timestamp: new Date().toISOString(),
      attachments: [],
    };
    const nextMessages = [...previousMessages, nextMessage];
    conversationMessagesRef.current = nextMessages;
    setConversationMessages(nextMessages);
    setConversationInput("");
    setIsSendingConversationMessage(true);

    try {
      const response = await fetch(`/api/tickets/${encodeURIComponent(ticket.id)}/chat-history`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          status: ticket.status,
          statusReason: ticket.statusReason,
          appendMessage: {
            sender: nextMessage.sender,
            text: nextMessage.text,
            timestamp: nextMessage.timestamp,
            clientMessageId: nextMessage.clientMessageId,
          },
        }),
      });
      const payload = (await response.json().catch(() => null)) as { message?: string } | null;
      if (!response.ok) {
        conversationMessagesRef.current = previousMessages;
        setConversationMessages(previousMessages);
        setConversationInput(text);
        toast.error(payload?.message || "We could not send your message right now.");
        return;
      }
      updateTicket({ chatHistory: nextMessages });
    } catch {
      conversationMessagesRef.current = previousMessages;
      setConversationMessages(previousMessages);
      setConversationInput(text);
      toast.error("We could not connect to the server. Please try again.");
    } finally {
      setIsSendingConversationMessage(false);
    }
  };

  const title = hasBookingSummary
    ? (isReservationConfirmed ? "Teams Session Reserved" : "Support Session Request Submitted")
    : isAwaitingMeeting
      ? "Support Session In Progress"
      : isAwaitingSupportReview
        ? "Direct Ticket Submitted"
        : ticket.status === "Closed"
          ? "Chat Closed"
          : ticket.id
            ? "Support Ticket Open"
            : ticket.status === "Pending"
              ? "Support Request Updated"
              : "Chat Closed";

  const description = hasBookingSummary
    ? (isReservationConfirmed
      ? "Your selected time has been reserved successfully in Microsoft Teams. You can open the meeting details below at any time."
      : "Your support session request has been received successfully. Our team will review it and contact you using your registered details.")
    : isAwaitingMeeting
      ? "Your support request is currently waiting for the scheduled support session. Chat is available in read-only mode while this meeting remains active."
    : isAwaitingSupportReview
        ? "Your ticket has been submitted directly to the support team. We will review the saved details and follow up using your registered contact information."
        : ticket.status === "Closed"
          ? "Thank you for contacting Kent College Support. It was a pleasure assisting you today. We appreciate your time and look forward to supporting you again in the future."
          : ticket.id
            ? "Your ticket is open. Keep the conversation going with the support team below — they will reply here as soon as they can."
            : ticket.status === "Pending"
              ? "Your support request is currently awaiting resolution. Our team will continue working on it and follow up with you."
              : "Thank you for contacting Kent College Support. It was a pleasure assisting you today. We appreciate your time and look forward to supporting you again in the future.";

  const handleCancelMeeting = async () => {
    if (!ticket.id || isCancellingMeeting) {
      return;
    }

    setIsCancellingMeeting(true);

    try {
      const response = await fetch(`/api/tickets/${encodeURIComponent(ticket.id)}/session-requests/cancel`, {
        method: "POST",
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
        toast.error(payload?.message || "We could not cancel the support meeting right now.");
        return;
      }

      const cancelledTicket = {
        ...ticket,
        status: (payload.ticket.status || "Open") as typeof ticket.status,
        statusReason: payload.ticket.statusReason || "",
      };
      const cancellationReturnPath = bookingSummary?.returnPath || getSupportResumePath(cancelledTicket, null);

      clearBookingSummary();
      updateTicket({
        status: payload.ticket.status || "Open",
        statusReason: payload.ticket.statusReason || "",
        assignedTeam: payload.ticket.assignedTeam || ticket.assignedTeam,
        slaStatus: payload.ticket.slaStatus || ticket.slaStatus,
        createdAt: payload.ticket.createdAt || ticket.createdAt,
      });
      setCancelMeetingOpen(false);
      toast.success(payload?.message || "Your support meeting has been cancelled.");
      navigate(cancellationReturnPath);
    } catch {
      toast.error("We could not connect to the server. Please try again.");
    } finally {
      setIsCancellingMeeting(false);
    }
  };

  return (
    <SupportLayout>
      <StepIndicator current={4} />
      <div className="max-w-3xl mx-auto">
        <div className="bg-card rounded-2xl border shadow-card p-8 text-center">
          <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-full bg-success/10">
            {hasBookingSummary ? (
              <CalendarCheck className="h-7 w-7 text-success" />
            ) : (
              <CheckCircle2 className="h-7 w-7 text-success" />
            )}
          </div>
          <h1 className="mb-2 text-2xl font-bold">{title}</h1>
          <p className="mx-auto max-w-xl text-sm leading-6 text-muted-foreground">
            {description}
          </p>

          {bookingSummary ? (
            <div className="mt-8 flex justify-center">
              <div className="w-full max-w-sm rounded-3xl border border-primary/15 bg-gradient-to-br from-card via-card to-primary/5 px-6 py-5 text-center shadow-soft">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-primary/80">
                  Requested Session
                </div>
                <div className="mt-3 text-base font-semibold text-foreground">
                  {bookingSummary.dateLabel}
                </div>
                <div className="mt-1 text-sm font-medium text-muted-foreground">
                  {bookingSummary.timeLabel}
                </div>
              </div>
            </div>
          ) : null}

          {ticket.id || ticket.category || ticket.status ? (
            <div className="mt-8 grid gap-3 text-left sm:grid-cols-2 lg:grid-cols-3">
              <div className="rounded-2xl border border-primary/10 bg-muted/20 px-4 py-4">
                <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-primary/80">Category</div>
                <div className="mt-2 text-sm font-semibold text-foreground">
                  {ticket.category || "-"}
                  {ticket.technicalSubcategory ? ` - ${ticket.technicalSubcategory}` : ""}
                </div>
              </div>
              <div className="rounded-2xl border border-primary/10 bg-muted/20 px-4 py-4">
                <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-primary/80">Status</div>
                <div className="mt-2 text-sm font-semibold text-foreground">
                  {displayedTicketStatus}
                </div>
              </div>
              <div className="rounded-2xl border border-primary/10 bg-muted/20 px-4 py-4">
                <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-primary/80">Ticket ID</div>
                <div className="mt-2 text-sm font-semibold text-foreground">
                  <span className="font-mono">{ticket.id || "-"}</span>
                </div>
              </div>
            </div>
          ) : null}
          {ticket.id ? (
            <p className="mt-5 text-sm text-muted-foreground">
              Need to review what you submitted? Click{" "}
              <button
                type="button"
                onClick={() => navigate("/support/inquiry")}
                className="font-semibold text-primary underline-offset-4 transition hover:underline"
              >
                Step 2 (Inquiry)
              </button>{" "}
              above.
            </p>
          ) : null}
        </div>

        {shouldShowTicketConversation ? (
          <section className="mt-6 overflow-hidden rounded-[28px] border border-primary/15 bg-card text-left shadow-[0_22px_60px_rgba(37,29,80,0.12)]">
            <div className="flex items-center gap-3 border-b border-primary/10 bg-gradient-to-r from-primary/[0.09] via-primary/[0.04] to-transparent px-5 py-4">
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-primary text-sm font-bold text-primary-foreground shadow-lg shadow-primary/20">
                {ticket.learnerName.trim().slice(0, 1).toUpperCase() || "Y"}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="font-semibold">Ticket conversation</h2>
                  <span className="rounded-full border border-primary/15 bg-background/80 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-primary">Open</span>
                </div>
                <p className="mt-0.5 truncate text-xs text-muted-foreground">{ticket.id} · Kent Support team</p>
              </div>
              <MessageSquare className="h-5 w-5 text-primary" />
            </div>

            <div className="max-h-[25rem] min-h-[16rem] space-y-4 overflow-y-auto bg-gradient-to-b from-muted/[0.35] to-background px-4 py-5 sm:px-5">
              {conversationMessages.filter((message) => message.source !== "intro" && message.source !== "history_event").length === 0 ? (
                <div className="mx-auto flex max-w-sm flex-col items-center rounded-2xl border border-dashed border-primary/20 bg-background/70 px-5 py-7 text-center">
                  <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-2xl bg-primary/10 text-primary"><MessageSquare className="h-5 w-5" /></div>
                  <p className="text-sm font-semibold">Start the conversation</p>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">Send an update and the support team will reply here.</p>
                </div>
              ) : (
                conversationMessages
                  .filter((message) => message.source !== "intro" && message.source !== "history_event")
                  .map((message) => {
                    const isRequester = message.sender === "user";
                    const senderLabel = isRequester ? "You" : message.sender === "agent" ? "Kent Support" : "Support assistant";
                    return (
                      <div key={message.id} className={isRequester ? "ml-auto flex max-w-[88%] flex-col items-end sm:max-w-[76%]" : "mr-auto flex max-w-[88%] flex-col items-start sm:max-w-[76%]"}>
                        <div className="mb-1 flex items-center gap-2 px-1 text-[11px] text-muted-foreground">
                          {!isRequester ? <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary/10 text-[9px] font-bold text-primary">K</span> : null}
                          <span className="font-medium text-foreground/80">{senderLabel}</span>
                          <span>{formatConversationTime(message.timestamp)}</span>
                        </div>
                        <div className={isRequester ? "rounded-2xl rounded-tr-md bg-gradient-to-br from-primary to-primary/85 px-4 py-3 text-sm leading-6 text-primary-foreground shadow-[0_10px_25px_rgba(98,73,238,0.22)]" : "rounded-2xl rounded-tl-md border border-border/80 bg-background px-4 py-3 text-sm leading-6 text-foreground shadow-sm"}>
                          {message.text}
                        </div>
                      </div>
                    );
                  })
              )}
            </div>

            <div className="border-t border-primary/10 bg-background px-4 py-4 sm:px-5">
              <div className="flex items-end gap-3 rounded-2xl border border-primary/15 bg-muted/[0.3] p-2 shadow-inner transition focus-within:border-primary/40 focus-within:ring-4 focus-within:ring-primary/10">
                <textarea
                  value={conversationInput}
                  onChange={(event) => setConversationInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      void handleConversationSend();
                    }
                  }}
                  placeholder="Write a message to the support team..."
                  className="min-h-12 max-h-28 flex-1 resize-y bg-transparent px-2 py-2 text-sm outline-none placeholder:text-muted-foreground"
                  disabled={isSendingConversationMessage}
                />
                <Button onClick={() => void handleConversationSend()} disabled={!conversationInput.trim() || isSendingConversationMessage} className="h-11 rounded-xl gradient-primary border-0 px-4 shadow-lg shadow-primary/20">
                  <Send className="mr-1.5 h-4 w-4" /> {isSendingConversationMessage ? "Sending" : "Send"}
                </Button>
              </div>
              <p className="mt-2 px-1 text-[11px] text-muted-foreground">Press Enter to send · Shift + Enter for a new line</p>
            </div>
          </section>
        ) : null}

        <div className="mt-6 flex flex-wrap justify-center gap-3">
          {bookingSummary?.meetingJoinUrl ? (
            <Button variant="outline" onClick={() => window.open(bookingSummary.meetingJoinUrl || "", "_blank", "noopener,noreferrer")}>
              Open Teams Meeting
              <ExternalLink className="ml-2 h-4 w-4" />
            </Button>
          ) : null}
          {canCancelMeeting ? (
            <Button
              variant="outline"
              onClick={() => setCancelMeetingOpen(true)}
              className="border-destructive/25 text-destructive hover:bg-destructive/5 hover:text-destructive"
            >
              Cancel Meeting
            </Button>
          ) : null}
          {showChatAction ? (
            <Button onClick={() => navigate("/support/chat")} className="gradient-primary border-0">
              <MessageSquare className="h-4 w-4 mr-2" /> {chatActionLabel}
            </Button>
          ) : null}
        </div>
      </div>

      <Dialog open={cancelMeetingOpen} onOpenChange={setCancelMeetingOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Cancel Support Meeting</DialogTitle>
            <DialogDescription>
              This will cancel the current support session and reopen your support request so you can choose another support route or book a different slot later.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="flex-col gap-2 sm:flex-row">
            <Button variant="outline" onClick={() => setCancelMeetingOpen(false)} disabled={isCancellingMeeting}>
              Keep Meeting
            </Button>
            <Button
              onClick={() => void handleCancelMeeting()}
              disabled={isCancellingMeeting}
              className="border-0 bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isCancellingMeeting ? "Cancelling..." : "Confirm Cancellation"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </SupportLayout>
  );
};

export default TicketStatus;
