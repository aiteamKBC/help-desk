import {
  type Category,
  type RequesterSource,
  type TechnicalSubcategory,
  type Ticket,
} from "@/context/SupportContext";
import { quickTicketReason } from "@/lib/supportFlow";

interface PublicTicketPayload {
  id: string;
  learnerName?: string;
  email: string;
  requesterRole?: Ticket["requesterRole"];
  requesterSource?: RequesterSource;
  category: Category;
  technicalSubcategory: TechnicalSubcategory;
  subject?: string;
  inquiry: string;
  submittedForLearner?: Ticket["submittedForLearner"];
  notifySubmittedForLearner?: boolean;
  status: Ticket["status"];
  statusReason?: string;
  assignedAgentId?: number | null;
  assignedTeam: string;
  slaStatus: string;
  createdAt: string;
  chatState?: Ticket["chatState"];
  liveChatRequested?: boolean;
}

interface TicketStatusPayload {
  status?: Ticket["status"];
  statusReason?: string;
  assignedAgentId?: number | null;
  assignedTeam?: string;
  slaStatus?: string;
  createdAt?: string;
  chatState?: Ticket["chatState"];
  liveChatRequested?: boolean;
}

function getPayloadMessage(payload: unknown, fallback: string) {
  if (payload && typeof payload === "object" && "message" in payload && typeof payload.message === "string") {
    return payload.message;
  }

  return fallback;
}

export function buildTicketStateFromPayload(payloadTicket: PublicTicketPayload, currentTicket: Ticket): Ticket {
  const hasSubmittedForLearner = Object.prototype.hasOwnProperty.call(payloadTicket, "submittedForLearner");
  const hasNotifySubmittedForLearner = Object.prototype.hasOwnProperty.call(payloadTicket, "notifySubmittedForLearner");

  return {
    ...currentTicket,
    id: payloadTicket.id,
    learnerName: payloadTicket.learnerName || currentTicket.learnerName,
    email: payloadTicket.email || currentTicket.email,
    requesterRole: payloadTicket.requesterRole || currentTicket.requesterRole,
    requesterSource: payloadTicket.requesterSource || currentTicket.requesterSource,
    category: payloadTicket.category || currentTicket.category,
    technicalSubcategory: payloadTicket.technicalSubcategory || currentTicket.technicalSubcategory,
    subject: payloadTicket.subject || currentTicket.subject,
    inquiry: payloadTicket.inquiry || currentTicket.inquiry,
    submittedForLearner: hasSubmittedForLearner ? payloadTicket.submittedForLearner ?? null : currentTicket.submittedForLearner,
    notifySubmittedForLearner: hasNotifySubmittedForLearner ? Boolean(payloadTicket.notifySubmittedForLearner) : currentTicket.notifySubmittedForLearner,
    status: payloadTicket.status || currentTicket.status,
    statusReason: payloadTicket.statusReason || currentTicket.statusReason,
    assignedAgentId: payloadTicket.assignedAgentId ?? currentTicket.assignedAgentId,
    assignedTeam: payloadTicket.assignedTeam || currentTicket.assignedTeam,
    slaStatus: payloadTicket.slaStatus || currentTicket.slaStatus,
    createdAt: payloadTicket.createdAt || currentTicket.createdAt,
    chatState: payloadTicket.chatState ?? currentTicket.chatState,
    liveChatRequested: payloadTicket.liveChatRequested ?? currentTicket.liveChatRequested,
  };
}

export function buildTicketDraftFormData(currentTicket: Ticket) {
  const formData = new FormData();
  formData.set("email", currentTicket.email);
  formData.set("requesterRole", currentTicket.requesterRole);
  formData.set("category", currentTicket.category);
  formData.set("technicalSubcategory", currentTicket.technicalSubcategory);
  formData.set("subject", currentTicket.subject);
  formData.set("inquiry", currentTicket.inquiry);
  formData.set("submittedForLearnerId", currentTicket.submittedForLearner ? String(currentTicket.submittedForLearner.id) : "");
  formData.set("notifySubmittedForLearner", String(Boolean(currentTicket.submittedForLearner && currentTicket.notifySubmittedForLearner)));
  formData.set(
    "submittedForNotificationEmail",
    currentTicket.submittedForLearner
      ? currentTicket.submittedForLearner.notificationEmail || currentTicket.submittedForLearner.email
      : "",
  );
  currentTicket.evidence.forEach((file) => {
    if (file.file) {
      formData.append("evidenceFiles", file.file, file.name);
    }
  });
  return formData;
}

export async function persistTicketDraft(currentTicket: Ticket) {
  const response = await fetch(currentTicket.id ? `/api/tickets/${encodeURIComponent(currentTicket.id)}` : "/api/tickets", {
    method: currentTicket.id ? "PATCH" : "POST",
    body: buildTicketDraftFormData(currentTicket),
  });
  const payload = (await response.json().catch(() => null)) as
    | {
        message?: string;
        ticket?: PublicTicketPayload;
      }
    | null;

  if (!response.ok || !payload?.ticket) {
    throw new Error(getPayloadMessage(payload, currentTicket.id ? "We could not update the ticket details right now." : "We could not create the ticket right now."));
  }

  return buildTicketStateFromPayload(payload.ticket, currentTicket);
}

export async function submitTicketDirectlyForReview(currentTicket: Ticket) {
  if (!currentTicket.id) {
    throw new Error("We could not submit the ticket before creating it.");
  }

  const response = await fetch(`/api/tickets/${encodeURIComponent(currentTicket.id)}/chat-history`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      status: "Pending",
      statusReason: quickTicketReason,
      messages: currentTicket.chatHistory.map((message) => ({
        sender: message.sender,
        text: message.text,
        timestamp: message.timestamp,
      })),
    }),
  });
  const payload = (await response.json().catch(() => null)) as
    | {
        message?: string;
        ticket?: TicketStatusPayload;
      }
    | null;

  if (!response.ok || !payload?.ticket) {
    throw new Error(getPayloadMessage(payload, "We could not submit the ticket right now."));
  }

  return {
    ...currentTicket,
    status: (payload.ticket.status || "Pending") as Ticket["status"],
    statusReason: payload.ticket.statusReason || quickTicketReason,
    assignedAgentId: payload.ticket.assignedAgentId ?? currentTicket.assignedAgentId,
    assignedTeam: payload.ticket.assignedTeam || currentTicket.assignedTeam,
    slaStatus: payload.ticket.slaStatus || currentTicket.slaStatus,
    createdAt: payload.ticket.createdAt || currentTicket.createdAt,
    chatState: payload.ticket.chatState ?? currentTicket.chatState,
    liveChatRequested: payload.ticket.liveChatRequested ?? currentTicket.liveChatRequested,
  };
}
