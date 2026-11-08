import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, BadgeCheck, ChevronDown, ChevronRight, ChevronUp, ListFilter, Mail, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SupportLayout } from "@/components/support/SupportLayout";
import { type BookingSummary, type RequesterRole, type RequesterSource, type Ticket } from "@/context/SupportContext";
import { useSupport } from "@/context/useSupport";
import { getSupportResumePath } from "@/lib/supportFlow";
import { toBookingSummary, type ApiBookingSummary } from "@/lib/supportBooking";
import { cn } from "@/lib/utils";
import "./MyTickets.css";

interface RestoredTicketPayload {
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
  coverageSessions?: Ticket["coverageSessions"];
  submittedForLearner?: Ticket["submittedForLearner"];
  notifySubmittedForLearner?: boolean;
  status: "Open" | "Pending" | "Closed";
  statusReason?: string;
  assignedAgentId?: number | null;
  assignedAgentName?: string;
  assignedTeam: string;
  slaStatus: string;
  createdAt: string;
  updatedAt?: string;
  chatState?: "open" | "closed";
  liveChatRequested?: boolean;
  bookingSummary?: ApiBookingSummary | null;
}

type TicketFilter = "All" | RestoredTicketPayload["status"];

interface TicketListItem {
  ticket: Ticket;
  bookingSummary: BookingSummary | null;
  assignedAgentName: string;
  updatedAt: string;
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
    coverageSessions: restoredTicket.coverageSessions || [],
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
    isQuickTicket: false,
    chatHistory: [],
  };
}

function formatUpdatedDate(value: string) {
  if (!value || Number.isNaN(Date.parse(value))) return "-";
  return new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(value));
}

function ticketCategoryLabel(ticket: Ticket) {
  return [ticket.category, ticket.technicalSubcategory].filter(Boolean).join(" - ") || "General Support";
}

const MyTickets = () => {
  const navigate = useNavigate();
  const { ticket, setTicket, setBookingSummary, clearBookingSummary } = useSupport();
  const [activeFilter, setActiveFilter] = useState<TicketFilter>("All");
  const tableBodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ticket.email) navigate("/", { replace: true });
  }, [navigate, ticket.email]);

  const ticketsQuery = useQuery({
    queryKey: ["my-tickets", ticket.email],
    enabled: Boolean(ticket.email),
    staleTime: 60_000,
    gcTime: 10 * 60_000,
    refetchOnWindowFocus: false,
    queryFn: async (): Promise<TicketListItem[]> => {
      const response = await fetch("/api/my-tickets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: ticket.email }),
      });
      const payload = (await response.json().catch(() => null)) as
        | { message?: string; learner?: { fullName?: string }; tickets?: RestoredTicketPayload[] }
        | null;

      if (!response.ok) throw new Error(payload?.message || "We could not load your tickets right now.");

      const learnerName = payload?.learner?.fullName || ticket.learnerName;
      return (payload?.tickets || []).map((restoredTicket) => ({
        ticket: buildRestoredTicket(restoredTicket, learnerName),
        bookingSummary: toBookingSummary(restoredTicket.bookingSummary),
        assignedAgentName: restoredTicket.assignedAgentName || "Unassigned",
        updatedAt: restoredTicket.updatedAt || restoredTicket.createdAt,
      }));
    },
  });

  const tickets = ticketsQuery.data || [];
  const ticketCounts = useMemo(() => ({
    All: tickets.length,
    Open: tickets.filter(({ ticket: item }) => item.status === "Open").length,
    Pending: tickets.filter(({ ticket: item }) => item.status === "Pending").length,
    Closed: tickets.filter(({ ticket: item }) => item.status === "Closed").length,
  }), [tickets]);
  const filteredTickets = useMemo(
    () => activeFilter === "All" ? tickets : tickets.filter(({ ticket: item }) => item.status === activeFilter),
    [activeFilter, tickets],
  );
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
      isQuickTicket: false,
      chatHistory: [],
    });
    clearBookingSummary();
    navigate("/support/inquiry");
  };

  const scrollTicketList = (direction: "up" | "down") => {
    tableBodyRef.current?.scrollBy({ top: direction === "up" ? -220 : 220, behavior: "smooth" });
  };

  return (
    <SupportLayout fullWidth mainClassName="my-tickets-main">
      <section className="my-tickets-page" aria-labelledby="my-tickets-title">
        <div className="my-tickets-heading">
          <div>
            <h1 id="my-tickets-title">My Tickets</h1>
            <p>Every support request linked to your registered email address.</p>
            <div className="my-tickets-email">
              <Mail aria-hidden="true" />
              <span>{ticket.email}</span>
            </div>
          </div>

          <div className="my-tickets-actions">
            <Button
              variant="outline"
              onClick={() => navigate("/")}
              className="h-[38px] rounded-full border-primary/30 bg-white px-4 hover:bg-primary/5 hover:text-primary"
            >
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back
            </Button>
            <Button variant="outline" onClick={() => navigate("/")} className="my-tickets-change-email">
              <BadgeCheck aria-hidden="true" />
              Change email
            </Button>
            <Button onClick={startNewTicket} className="my-tickets-new-ticket">
              <Plus aria-hidden="true" />
              Start new ticket
            </Button>
          </div>
        </div>

        <div className="my-tickets-filters" role="tablist" aria-label="Filter tickets by status">
          {(["All", "Open", "Pending", "Closed"] as const).map((filter) => (
            <button
              key={filter}
              type="button"
              role="tab"
              aria-selected={activeFilter === filter}
              className={cn("my-tickets-filter", activeFilter === filter && "is-active")}
              onClick={() => setActiveFilter(filter)}
            >
              <span>{filter === "All" ? "All Tickets" : filter}</span>
              <span className="my-tickets-filter__count">{ticketCounts[filter]}</span>
            </button>
          ))}
        </div>

        <div className="my-tickets-divider" />

        <div className="my-tickets-table" aria-busy={isInitialLoading || ticketsQuery.isFetching}>
          <div className="my-tickets-table__header" role="row">
            <span>Ticket</span><span>Subject</span><span>Category</span><span>Agent</span><span>Status</span><span>Updated</span><span>View</span>
          </div>

          <div ref={tableBodyRef} className="my-tickets-table__body">
            {ticketsQuery.isFetching && tickets.length ? <div className="my-tickets-table__notice">Refreshing tickets...</div> : null}
            {isInitialLoading ? (
              <div className="my-tickets-table__state">Loading your tickets...</div>
            ) : errorMessage ? (
              <div className="my-tickets-table__state my-tickets-table__state--error">
                <strong>Tickets unavailable</strong><span>{errorMessage}</span>
              </div>
            ) : filteredTickets.length ? (
              filteredTickets.map(({ ticket: oldTicket, bookingSummary, assignedAgentName, updatedAt }) => (
                <button
                  key={oldTicket.id}
                  type="button"
                  className="my-tickets-row"
                  onClick={() => openTicket(oldTicket, bookingSummary)}
                  aria-label={`View ticket ${oldTicket.id}`}
                >
                  <span className="my-tickets-cell my-tickets-cell--ticket" data-label="Ticket">{oldTicket.id}</span>
                  <span className="my-tickets-cell my-tickets-cell--subject" data-label="Subject">{oldTicket.subject || oldTicket.inquiry || "Support request"}</span>
                  <span className="my-tickets-cell" data-label="Category">{ticketCategoryLabel(oldTicket)}</span>
                  <span className="my-tickets-cell" data-label="Agent">{assignedAgentName}</span>
                  <span className="my-tickets-cell" data-label="Status">
                    <span className={`my-tickets-status my-tickets-status--${oldTicket.status.toLowerCase()}`}>{oldTicket.status}</span>
                  </span>
                  <span className="my-tickets-cell" data-label="Updated">{formatUpdatedDate(updatedAt)}</span>
                  <span className="my-tickets-cell my-tickets-cell--view" aria-hidden="true"><ChevronRight /></span>
                </button>
              ))
            ) : (
              <div className="my-tickets-table__state">
                <strong>{tickets.length ? `No ${activeFilter.toLowerCase()} tickets` : "No previous tickets found"}</strong>
                <span>{tickets.length ? "Choose another status filter." : "Start a new ticket whenever you need support."}</span>
              </div>
            )}
          </div>

          <div className="my-tickets-table__footer">
            <div><ListFilter aria-hidden="true" /><span>Scroll the list to see all {filteredTickets.length} tickets</span></div>
            <div className="my-tickets-scroll-controls">
              <button type="button" onClick={() => scrollTicketList("up")} aria-label="Scroll tickets up"><ChevronUp /></button>
              <button type="button" onClick={() => scrollTicketList("down")} aria-label="Scroll tickets down"><ChevronDown /></button>
            </div>
          </div>
        </div>

        <p className="my-tickets-summary">Showing {filteredTickets.length} of {tickets.length} tickets. Ticket data is linked to {ticket.email}.</p>
      </section>
    </SupportLayout>
  );
};

export default MyTickets;
