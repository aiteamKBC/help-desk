import { type BookingSummary, type RequesterRole, type Ticket } from "@/context/SupportContext";

export const awaitingMeetingReason = "Awaiting support meeting";
export const quickTicketReason = "Quick Ticket";
export const awaitingSupportReviewReason = quickTicketReason;
export type SupportChatEntryAction = "live-chat" | "booking";
export interface SupportChatLocationState {
  entryAction?: SupportChatEntryAction;
}
export interface SupportBookingLocationState {
  returnPath?: "/support/chat" | "/support/options";
}
const legacyQuickTicketReasons = ["Awaiting resolution", "Awaiting Resolution", "Awaiting support review"] as const;

type TicketFlowState = Pick<Ticket, "id" | "status" | "statusReason" | "requesterRole">;

export const isQuickTicketOnlyRequesterRole = (role: RequesterRole | string | null | undefined) =>
  (role || "").trim().toLowerCase() === "coach";

export const isAwaitingMeetingTicket = (ticket: TicketFlowState) =>
  ticket.status === "Pending" && ticket.statusReason === awaitingMeetingReason;

export const isAwaitingSupportReviewTicket = (ticket: TicketFlowState) =>
  ticket.status === "Pending"
  && [quickTicketReason, ...legacyQuickTicketReasons].includes(ticket.statusReason);

export const canReturnToChat = (ticket: TicketFlowState) =>
  !isQuickTicketOnlyRequesterRole(ticket.requesterRole)
  && !isAwaitingSupportReviewTicket(ticket);

export const shouldShowStatusStep = (
  ticket: Pick<Ticket, "id" | "status">,
  bookingSummary: BookingSummary | null,
) => Boolean(bookingSummary || (ticket.id && ticket.status !== "Open"));

export const getSupportResumePath = (
  ticket: Pick<Ticket, "id" | "status" | "requesterRole">,
  bookingSummary: BookingSummary | null,
) => {
  if (shouldShowStatusStep(ticket, bookingSummary)) {
    return "/support/status";
  }

  if (isQuickTicketOnlyRequesterRole(ticket.requesterRole)) {
    return ticket.id ? "/support/options" : "/";
  }

  return "/support/chat";
};
