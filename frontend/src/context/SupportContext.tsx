import { createContext, useContext, useEffect, useState, ReactNode } from "react";

export type TicketStatus = "Open" | "Pending" | "Closed";
export type TicketChatState = "open" | "closed";
export type Category = "Learning" | "Technical" | "Others" | "";
export type TechnicalSubcategory = "Aptem" | "LMS" | "Teams" | "";
export type RequesterRole = "user" | "coach" | "employer";

export interface ChatMessage {
  id: string;
  sender: "bot" | "user" | "agent";
  source?: "message" | "history_event" | "intro";
  text: string;
  timestamp: string;
}

export interface EvidenceFile {
  name: string;
  size: number;
  mimeType?: string;
  previewUrl?: string;
  textContent?: string;
}

export interface Ticket {
  id: string;
  learnerName: string;
  email: string;
  requesterRole: RequesterRole;
  category: Category;
  technicalSubcategory: TechnicalSubcategory;
  inquiry: string;
  evidence: EvidenceFile[];
  status: TicketStatus;
  statusReason: string;
  assignedAgentId: number | null;
  assignedTeam: string;
  slaStatus: string;
  createdAt: string;
  chatState: TicketChatState;
  liveChatRequested: boolean;
  chatHistory: ChatMessage[];
}

export interface BookingSummary {
  dateLabel: string;
  timeLabel: string;
  reservationConfirmed: boolean;
  meetingJoinUrl: string | null;
}

const defaultTicket: Ticket = {
  id: "",
  learnerName: "",
  email: "",
  requesterRole: "user",
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
};

const supportStorageKey = "kbc-support-state-v1";

function normalizeRequesterRole(value: unknown, fallback: RequesterRole = defaultTicket.requesterRole): RequesterRole {
  if (typeof value !== "string") {
    return fallback;
  }

  const normalizedValue = value.trim().toLowerCase();
  if (normalizedValue === "user" || normalizedValue === "coach" || normalizedValue === "employer") {
    return normalizedValue;
  }

  return fallback;
}

function normalizeTicketState(ticket?: Partial<Ticket> | null): Ticket {
  const nextTicket = { ...defaultTicket, ...(ticket || {}) };

  return {
    ...nextTicket,
    requesterRole: normalizeRequesterRole(nextTicket.requesterRole),
  };
}

function readPersistedSupportState() {
  if (typeof window === "undefined") {
    return {
      ticket: defaultTicket,
      bookingSummary: null as BookingSummary | null,
    };
  }

  try {
    const rawValue = window.localStorage.getItem(supportStorageKey);
    if (!rawValue) {
      return {
        ticket: defaultTicket,
        bookingSummary: null as BookingSummary | null,
      };
    }

    const parsedValue = JSON.parse(rawValue) as {
      ticket?: Partial<Ticket>;
      bookingSummary?: BookingSummary | null;
    };

    return {
      ticket: normalizeTicketState(parsedValue.ticket),
      bookingSummary: parsedValue.bookingSummary || null,
    };
  } catch {
    return {
      ticket: defaultTicket,
      bookingSummary: null as BookingSummary | null,
    };
  }
}

interface SupportCtx {
  ticket: Ticket;
  bookingSummary: BookingSummary | null;
  setTicket: (t: Ticket) => void;
  updateTicket: (patch: Partial<Ticket>) => void;
  setBookingSummary: (booking: BookingSummary | null) => void;
  clearBookingSummary: () => void;
  resetTicket: () => void;
}

const Ctx = createContext<SupportCtx | null>(null);

export const SupportProvider = ({ children }: { children: ReactNode }) => {
  const persistedState = readPersistedSupportState();
  const [ticket, setTicketState] = useState<Ticket>(persistedState.ticket);
  const [bookingSummary, setBookingSummary] = useState<BookingSummary | null>(persistedState.bookingSummary);
  const setTicket = (nextTicket: Ticket) => setTicketState(normalizeTicketState(nextTicket));
  const updateTicket = (patch: Partial<Ticket>) =>
    setTicketState((currentTicket) => normalizeTicketState({ ...currentTicket, ...patch }));
  const clearBookingSummary = () => setBookingSummary(null);
  const resetTicket = () => {
    setTicketState(defaultTicket);
    clearBookingSummary();
  };

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    window.localStorage.setItem(
      supportStorageKey,
      JSON.stringify({
        ticket,
        bookingSummary,
      }),
    );
  }, [ticket, bookingSummary]);

  return (
    <Ctx.Provider
      value={{ ticket, bookingSummary, setTicket, updateTicket, setBookingSummary, clearBookingSummary, resetTicket }}
    >
      {children}
    </Ctx.Provider>
  );
};

export const useSupport = () => {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useSupport must be inside SupportProvider");
  return ctx;
};
