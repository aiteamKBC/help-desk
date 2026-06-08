import { createContext, useContext, useEffect, useState, ReactNode } from "react";

export type TicketStatus = "Open" | "Pending" | "Closed";
export type TicketChatState = "open" | "closed";
export type Category = "Learning" | "Technical" | "Others" | "";
export type TechnicalSubcategory = "Aptem" | "Coverage" | "LMS" | "Teams" | "Others" | "";
export type RequesterRole = "user" | "coach" | "employer";
export type RequesterSource = "kbc_users_data" | "microsoft_entra" | "support_portal_requester" | "";

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
  file?: File;
}

export interface Ticket {
  id: string;
  learnerName: string;
  email: string;
  requesterRole: RequesterRole;
  requesterSource: RequesterSource;
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

interface PersistedSupportState {
  ticket?: Partial<Ticket>;
}

const defaultTicket: Ticket = {
  id: "",
  learnerName: "",
  email: "",
  requesterRole: "user",
  requesterSource: "",
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

const legacySupportStorageKey = "kbc-support-state-v1";
const supportStorageKey = "kbc-support-state-v2";

function normalizeCategory(value: unknown, fallback: Category = defaultTicket.category): Category {
  if (value === "Learning" || value === "Technical" || value === "Others" || value === "") {
    return value;
  }

  return fallback;
}

function normalizeTechnicalSubcategory(
  value: unknown,
  fallback: TechnicalSubcategory = defaultTicket.technicalSubcategory,
): TechnicalSubcategory {
  if (
    value === "Aptem"
    || value === "Coverage"
    || value === "LMS"
    || value === "Teams"
    || value === "Others"
    || value === ""
  ) {
    return value;
  }

  return fallback;
}

function normalizeTicketStatus(value: unknown, fallback: TicketStatus = defaultTicket.status): TicketStatus {
  if (value === "Open" || value === "Pending" || value === "Closed") {
    return value;
  }

  return fallback;
}

function normalizeTicketChatState(value: unknown, fallback: TicketChatState = defaultTicket.chatState): TicketChatState {
  if (value === "open" || value === "closed") {
    return value;
  }

  return fallback;
}

function normalizeString(value: unknown, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

function normalizeNullableNumber(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

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

function normalizeRequesterSource(
  value: unknown,
  fallback: RequesterSource = defaultTicket.requesterSource,
): RequesterSource {
  if (typeof value !== "string") {
    return fallback;
  }

  const normalizedValue = value.trim().toLowerCase();
  if (
    normalizedValue === "kbc_users_data"
    || normalizedValue === "legacy_kbc_users_data"
  ) {
    return "kbc_users_data";
  }
  if (normalizedValue === "microsoft_entra") {
    return "microsoft_entra";
  }
  if (normalizedValue === "support_portal_requester") {
    return "support_portal_requester";
  }

  return fallback;
}

function normalizeTicketState(ticket?: Partial<Ticket> | null): Ticket {
  const nextTicket = { ...defaultTicket, ...(ticket || {}) };

  return {
    ...nextTicket,
    requesterRole: normalizeRequesterRole(nextTicket.requesterRole),
    requesterSource: normalizeRequesterSource(nextTicket.requesterSource),
    learnerName: normalizeString(nextTicket.learnerName),
    email: normalizeString(nextTicket.email),
    category: normalizeCategory(nextTicket.category),
    technicalSubcategory: normalizeTechnicalSubcategory(nextTicket.technicalSubcategory),
    inquiry: normalizeString(nextTicket.inquiry),
    evidence: Array.isArray(nextTicket.evidence) ? nextTicket.evidence : [],
    status: normalizeTicketStatus(nextTicket.status),
    statusReason: normalizeString(nextTicket.statusReason),
    assignedAgentId: normalizeNullableNumber(nextTicket.assignedAgentId),
    assignedTeam: normalizeString(nextTicket.assignedTeam, defaultTicket.assignedTeam),
    slaStatus: normalizeString(nextTicket.slaStatus, defaultTicket.slaStatus),
    createdAt: normalizeString(nextTicket.createdAt),
    chatState: normalizeTicketChatState(nextTicket.chatState),
    liveChatRequested: Boolean(nextTicket.liveChatRequested),
    chatHistory: Array.isArray(nextTicket.chatHistory) ? nextTicket.chatHistory : [],
  };
}

function buildPersistedTicket(ticket: Ticket): Partial<Ticket> | null {
  if (!ticket.id) {
    return null;
  }

  return {
    id: ticket.id,
    learnerName: ticket.learnerName,
    email: ticket.email,
    requesterRole: ticket.requesterRole,
    requesterSource: ticket.requesterSource,
    category: ticket.category,
    technicalSubcategory: ticket.technicalSubcategory,
    inquiry: ticket.inquiry,
    status: ticket.status,
    statusReason: ticket.statusReason,
    assignedAgentId: ticket.assignedAgentId,
    assignedTeam: ticket.assignedTeam,
    slaStatus: ticket.slaStatus,
    createdAt: ticket.createdAt,
    chatState: ticket.chatState,
    liveChatRequested: ticket.liveChatRequested,
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
    const rawValue = window.localStorage.getItem(supportStorageKey)
      || window.localStorage.getItem(legacySupportStorageKey);
    if (!rawValue) {
      return {
        ticket: defaultTicket,
        bookingSummary: null as BookingSummary | null,
      };
    }

    const parsedValue = JSON.parse(rawValue) as PersistedSupportState;

    return {
      ticket: normalizeTicketState(parsedValue.ticket),
      bookingSummary: null as BookingSummary | null,
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

    const persistedTicket = buildPersistedTicket(ticket);

    window.localStorage.removeItem(legacySupportStorageKey);

    if (!persistedTicket) {
      window.localStorage.removeItem(supportStorageKey);
      return;
    }

    window.localStorage.setItem(
      supportStorageKey,
      JSON.stringify({
        ticket: persistedTicket,
      } satisfies PersistedSupportState),
    );
  }, [ticket]);

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
