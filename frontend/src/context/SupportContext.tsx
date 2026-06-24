import { useEffect, useState, type ReactNode } from "react";
import { type ChatAttachment } from "@/lib/supportChat";
import { SupportContext } from "@/context/support-context-value";

export type TicketStatus = "Open" | "Pending" | "Closed";
export type TicketChatState = "open" | "closed";
export type Category = "Learning" | "Technical" | "Others" | "";
export type TechnicalSubcategory = "Aptem" | "Coverage" | "LMS" | "Teams" | "Others" | "";
export type RequesterRole = "user" | "coach" | "employer";
export type RequesterSource = "kbc_users_data" | "microsoft_entra" | "support_portal_requester" | "";

export interface ChatMessage {
  id: string;
  clientMessageId?: string;
  sender: "bot" | "user" | "agent";
  source?: "message" | "history_event" | "intro";
  text: string;
  timestamp: string;
  attachments?: ChatAttachment[];
}

export interface EvidenceFile {
  name: string;
  size: number;
  mimeType?: string;
  previewUrl?: string;
  textContent?: string;
  file?: File;
}

export interface SubmittedForLearner {
  id: number;
  externalLearnerId?: string;
  fullName: string;
  email: string;
  notificationEmail?: string;
}

export interface Ticket {
  id: string;
  learnerName: string;
  email: string;
  requesterRole: RequesterRole;
  requesterSource: RequesterSource;
  category: Category;
  technicalSubcategory: TechnicalSubcategory;
  subject: string;
  inquiry: string;
  submittedForLearner: SubmittedForLearner | null;
  notifySubmittedForLearner: boolean;
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
  returnPath?: "/support/chat" | "/support/options";
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
  subject: "",
  inquiry: "",
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

function normalizeSubmittedForLearner(value: unknown): SubmittedForLearner | null {
  if (!value || typeof value !== "object") {
    return null;
  }

  const learner = value as Partial<SubmittedForLearner>;
  const id = typeof learner.id === "number" && Number.isFinite(learner.id) ? learner.id : 0;
  const email = normalizeString(learner.email);
  const fullName = normalizeString(learner.fullName, email);

  if (!id || !email) {
    return null;
  }

  return {
    id,
    externalLearnerId: normalizeString(learner.externalLearnerId),
    fullName,
    email,
    notificationEmail: normalizeString(learner.notificationEmail),
  };
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
    subject: normalizeString(nextTicket.subject),
    inquiry: normalizeString(nextTicket.inquiry),
    submittedForLearner: normalizeSubmittedForLearner(nextTicket.submittedForLearner),
    notifySubmittedForLearner: Boolean(nextTicket.notifySubmittedForLearner),
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
  const hasDraftDetails = Boolean(
    ticket.email
    || ticket.learnerName
    || ticket.category
    || ticket.technicalSubcategory
    || ticket.subject
    || ticket.inquiry
    || ticket.submittedForLearner,
  );

  if (!ticket.id && !hasDraftDetails) {
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
    subject: ticket.subject,
    inquiry: ticket.inquiry,
    submittedForLearner: ticket.submittedForLearner,
    notifySubmittedForLearner: ticket.notifySubmittedForLearner,
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
    <SupportContext.Provider
      value={{ ticket, bookingSummary, setTicket, updateTicket, setBookingSummary, clearBookingSummary, resetTicket }}
    >
      {children}
    </SupportContext.Provider>
  );
};
