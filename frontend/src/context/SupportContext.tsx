import { createContext, useContext, useState, ReactNode } from "react";

export type TicketStatus = "Open" | "Pending" | "Closed";
export type Category = "Learning" | "Technical" | "Others" | "";
export type TechnicalSubcategory = "Aptem" | "LMS" | "Teams" | "";

export interface ChatMessage {
  id: string;
  sender: "bot" | "user" | "agent";
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
  category: Category;
  technicalSubcategory: TechnicalSubcategory;
  inquiry: string;
  evidence: EvidenceFile[];
  status: TicketStatus;
  statusReason: string;
  assignedTeam: string;
  slaStatus: string;
  createdAt: string;
  liveChatRequested: boolean;
  chatHistory: ChatMessage[];
}

const defaultTicket: Ticket = {
  id: "",
  learnerName: "",
  email: "",
  category: "",
  technicalSubcategory: "",
  inquiry: "",
  evidence: [],
  status: "Open",
  statusReason: "",
  assignedTeam: "Unassigned",
  slaStatus: "Pending Review",
  createdAt: "",
  liveChatRequested: false,
  chatHistory: [],
};

interface SupportCtx {
  ticket: Ticket;
  setTicket: (t: Ticket) => void;
  updateTicket: (patch: Partial<Ticket>) => void;
  resetTicket: () => void;
}

const Ctx = createContext<SupportCtx | null>(null);

export const SupportProvider = ({ children }: { children: ReactNode }) => {
  const [ticket, setTicket] = useState<Ticket>(defaultTicket);
  const updateTicket = (patch: Partial<Ticket>) =>
    setTicket((t) => ({ ...t, ...patch }));
  const resetTicket = () => setTicket(defaultTicket);
  return (
    <Ctx.Provider value={{ ticket, setTicket, updateTicket, resetTicket }}>
      {children}
    </Ctx.Provider>
  );
};

export const useSupport = () => {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useSupport must be inside SupportProvider");
  return ctx;
};
