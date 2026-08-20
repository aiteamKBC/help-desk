import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, CalendarClock, ListChecks, MessageSquarePlus, Ticket as TicketIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SupportLayout } from "@/components/support/SupportLayout";
import { StepIndicator } from "@/components/support/StepIndicator";
import {
  type BookingSummary,
  type RequesterRole,
  type RequesterSource,
  type Ticket,
} from "@/context/SupportContext";
import { useSupport } from "@/context/useSupport";
import { getSupportResumePath, isAwaitingSupportReviewTicket } from "@/lib/supportFlow";
import { toBookingSummary, type ApiBookingSummary } from "@/lib/supportBooking";

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
  bookingSummary?: ApiBookingSummary | null;
}

function buildRestoredTicket(restoredTicket: RestoredTicketPayload, learnerNameFallback: string): Ticket {
  return {
    id: restoredTicket.id,
    learnerName: restoredTicket.learnerName || learnerNameFallback,
    email: restoredTicket.email,
    requesterRole: restoredTicket.requesterRole || "user",
    requesterSource: restoredTicket.requesterSource || "",
    category: restoredTicket.category,
    technicalSubcategory: restoredTicket.technicalSubcategory,
    subject: restoredTicket.subject || "",
    inquiry: restoredTicket.inquiry,
    aiTeamPersonName: restoredTicket.aiTeamPersonName || "",
    aiTeamPersonEmail: restoredTicket.aiTeamPersonEmail || "",
    submittedForLearner: restoredTicket.submittedForLearner || null,
    notifySubmittedForLearner: restoredTicket.notifySubmittedForLearner || false,
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

const MyTickets = () => {
  const navigate = useNavigate();
  const { ticket, setTicket, setBookingSummary, clearBookingSummary } = useSupport();

  useEffect(() => {
    if (!ticket.email) {
      navigate("/", { replace: true });
    }
  }, [navigate, ticket.email]);

  const ticketsQuery = useQuery({
    queryKey: ["my-tickets", ticket.email],
    enabled: Boolean(ticket.email),
    staleTime: 60_000,
    gcTime: 10 * 60_000,
    refetchOnWindowFocus: false,
    queryFn: async () => {
      const response = await fetch("/api/my-tickets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: ticket.email }),
      });
      const payload = (await response.json().catch(() => null)) as
        | {
            message?: string;
            learner?: { fullName?: string };
            tickets?: RestoredTicketPayload[];
          }
        | null;

      if (!response.ok) {
        throw new Error(payload?.message || "We could not load your tickets right now.");
      }

      const learnerName = payload?.learner?.fullName || ticket.learnerName;
      return (payload?.tickets || []).map((restoredTicket) => ({
        ticket: buildRestoredTicket(restoredTicket, learnerName),
        bookingSummary: toBookingSummary(restoredTicket.bookingSummary),
      }));
    },
  });

  const tickets = ticketsQuery.data || [];
  const isInitialLoading = ticketsQuery.isLoading && !ticketsQuery.data;
  const errorMessage = ticketsQuery.error instanceof Error ? ticketsQuery.error.message : "";

  const openTicket = (selectedTicket: Ticket, bookingSummary: BookingSummary | null) => {
    setTicket(selectedTicket);
    setBookingSummary(bookingSummary);
    navigate(getSupportResumePath(selectedTicket, bookingSummary));
  };

  const startNewTicket = () => {
    setTicket({
      ...ticket,
      id: "",
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
    navigate("/support/inquiry");
  };

  return (
    <SupportLayout>
      <StepIndicator current={1} />
      <div className="mx-auto max-w-4xl">
        <div className="mb-5 flex items-center justify-between gap-3">
          <Button variant="ghost" onClick={() => navigate("/")}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back
          </Button>
          <Button className="border-0 gradient-primary" onClick={startNewTicket}>
            <MessageSquarePlus className="mr-2 h-4 w-4" />
            Create New Ticket
          </Button>
        </div>

        <div className="rounded-2xl border bg-card p-6 shadow-card sm:p-8">
          <div className="mb-6 flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-full bg-primary/10">
              <ListChecks className="h-5 w-5 text-primary" />
            </div>
            <div>
              <h1 className="text-2xl font-semibold text-foreground">My Tickets</h1>
              <p className="mt-1 text-sm text-muted-foreground">{ticket.email}</p>
            </div>
          </div>

          {ticketsQuery.isFetching && tickets.length ? (
            <div className="mb-3 rounded-2xl border border-primary/15 bg-primary/5 px-4 py-3 text-center text-sm text-muted-foreground">
              Refreshing tickets...
            </div>
          ) : null}

          {isInitialLoading ? (
            <div className="rounded-2xl border border-primary/15 bg-primary/5 px-4 py-8 text-center text-sm text-muted-foreground">
              Loading your tickets...
            </div>
          ) : errorMessage ? (
            <div className="rounded-2xl border border-destructive/20 bg-destructive/5 px-4 py-8 text-center">
              <div className="text-sm font-semibold text-foreground">Tickets unavailable</div>
              <div className="mt-1 text-sm text-muted-foreground">{errorMessage}</div>
            </div>
          ) : tickets.length ? (
            <div className="space-y-3">
              {tickets.map(({ ticket: oldTicket, bookingSummary }) => (
                <button
                  key={oldTicket.id}
                  type="button"
                  className="w-full rounded-2xl border border-primary/15 bg-card px-4 py-4 text-left transition hover:border-primary/40 hover:bg-primary/5"
                  onClick={() => openTicket(oldTicket, bookingSummary)}
                >
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/10">
                      <TicketIcon className="h-4 w-4 text-primary" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-semibold text-foreground">{oldTicket.id}</span>
                        <span className="rounded-full border px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                          {oldTicket.status}
                        </span>
                      </div>
                      <div className="mt-1 truncate text-sm font-medium text-foreground">
                        {oldTicket.subject || oldTicket.category || "Support request"}
                      </div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        {oldTicket.category}
                        {oldTicket.technicalSubcategory ? ` - ${oldTicket.technicalSubcategory}` : ""}
                        {bookingSummary?.reservationConfirmed
                          ? " - Meeting reserved"
                          : isAwaitingSupportReviewTicket(oldTicket)
                            ? " - Waiting for team review"
                            : oldTicket.status === "Pending"
                              ? " - Waiting for update"
                              : ""}
                      </div>
                    </div>
                    <CalendarClock className="mt-1 h-4 w-4 shrink-0 text-muted-foreground" />
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed px-4 py-10 text-center">
              <div className="text-sm font-semibold text-foreground">No previous tickets found</div>
              <div className="mt-1 text-sm text-muted-foreground">You can create a new support inquiry for this email.</div>
            </div>
          )}
        </div>
      </div>
    </SupportLayout>
  );
};

export default MyTickets;
