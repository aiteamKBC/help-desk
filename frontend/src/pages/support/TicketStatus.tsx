import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CalendarCheck, CheckCircle2, ExternalLink, MessageSquare } from "lucide-react";
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
import { useSupport } from "@/context/useSupport";
import { canReturnToChat, getSupportResumePath, isAwaitingMeetingTicket, isAwaitingSupportReviewTicket, quickTicketReason, shouldShowStatusStep } from "@/lib/supportFlow";
import { toBookingSummary, type ApiBookingSummary } from "@/lib/supportBooking";
import { toast } from "sonner";

const TicketStatus = () => {
  const navigate = useNavigate();
  const { ticket, bookingSummary, updateTicket, setBookingSummary, clearBookingSummary } = useSupport();
  const isAwaitingMeeting = isAwaitingMeetingTicket(ticket);
  const isAwaitingSupportReview = isAwaitingSupportReviewTicket(ticket);
  const hasBookingSummary = Boolean(bookingSummary);
  const isReservationConfirmed = Boolean(bookingSummary?.reservationConfirmed);
  const hasStatusStep = shouldShowStatusStep(ticket, bookingSummary);
  const showChatAction = canReturnToChat(ticket);
  const canCancelMeeting = hasBookingSummary || isAwaitingMeeting;
  const displayedStatusReason = ticket.technicalSubcategory === "Coverage" && ticket.statusReason === quickTicketReason
    ? "Coverage Ticket"
    : (ticket.statusReason || ticket.status);
  const [cancelMeetingOpen, setCancelMeetingOpen] = useState(false);
  const [isCancellingMeeting, setIsCancellingMeeting] = useState(false);

  useEffect(() => {
    if (!ticket.email || !ticket.id || hasStatusStep) {
      return;
    }

    navigate(getSupportResumePath(ticket, bookingSummary));
  }, [bookingSummary, hasStatusStep, navigate, ticket]);

  useEffect(() => {
    if (bookingSummary || !ticket.id) {
      return;
    }

    let cancelled = false;

    const loadBookingSummary = async () => {
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
              };
              bookingSummary?: ApiBookingSummary | null;
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
          });
        }

        if ("bookingSummary" in (payload || {})) {
          setBookingSummary(toBookingSummary(payload?.bookingSummary));
        }
      } catch {
        // The status page can still show the saved ticket state even if the refresh fetch fails.
      }
    };

    void loadBookingSummary();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bookingSummary, ticket.id]);

  const title = hasBookingSummary
    ? (isReservationConfirmed ? "Teams Session Reserved" : "Support Session Request Submitted")
    : isAwaitingMeeting
      ? "Support Session In Progress"
      : isAwaitingSupportReview
        ? "Direct Ticket Submitted"
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
                  {displayedStatusReason}
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
        </div>

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
              <MessageSquare className="h-4 w-4 mr-2" /> View Chat
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
