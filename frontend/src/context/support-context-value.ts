import { createContext } from "react";
import type { BookingSummary, Ticket } from "@/context/SupportContext";

export interface SupportContextValue {
  ticket: Ticket;
  bookingSummary: BookingSummary | null;
  setTicket: (ticket: Ticket) => void;
  updateTicket: (patch: Partial<Ticket>) => void;
  setBookingSummary: (booking: BookingSummary | null) => void;
  clearBookingSummary: () => void;
  resetTicket: () => void;
}

export const SupportContext = createContext<SupportContextValue | null>(null);
