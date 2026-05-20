import { type ComponentType, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowRight,
  Bot,
  CalendarClock,
  Check,
  Download,
  Headphones,
  Paperclip,
  Send,
  User,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { StatusBadge } from "@/components/support/StatusBadge";
import { StepIndicator } from "@/components/support/StepIndicator";
import { SupportLayout } from "@/components/support/SupportLayout";
import { type Category, type ChatMessage, type TechnicalSubcategory, type Ticket, useSupport } from "@/context/SupportContext";
import { downloadChatPdf } from "@/lib/chatPdf";
import { toBookingSummary, type ApiBookingSummary } from "@/lib/supportBooking";
import { getSupportResumePath, isAwaitingMeetingTicket, isAwaitingSupportReviewTicket, isQuickTicketOnlyRequesterRole } from "@/lib/supportFlow";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

const ukSupportTimeZone = "Europe/London";
const ukSupportSessionStartMinutes = 8 * 60;
const ukSupportSessionEndMinutes = 16 * 60;
const supportSessionSlotIntervalMinutes = 30;
const supportSessionLeadTimeMs = 24 * 60 * 60 * 1000;
const learnerChatPollIntervalMs = 2500;
const chatbotClosingReason = "Closed via Chatbot";
const awaitingMeetingReason = "Awaiting support meeting";
const inactivityClosingReason = "Closed due to inactivity";
const closedChatDescription = "If you still need help, you can start a new chat and continue with a fresh support request.";
const liveAgentQueueWaitingMessage = "No support admins are available right now. You're in queue and we'll connect you as soon as one becomes available.";

function getIssueLabel(category: string, technicalSubcategory: string) {
  return technicalSubcategory.trim() || category.trim() || "your request";
}

function buildSupportIntroMessage(learnerName: string, category: string, technicalSubcategory: string) {
  const greetingName = learnerName.trim() || "there";
  const issueLabel = getIssueLabel(category, technicalSubcategory);
  return `Hello ${greetingName}, Thank you for reaching Kent College Support, I understand you are reaching us for an issue related to ${issueLabel}, am I correct?`;
}

function buildTimestamp() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function buildBotMessage(text: string): ChatMessage {
  return {
    id: crypto.randomUUID(),
    sender: "bot",
    text,
    timestamp: buildTimestamp(),
  };
}

function ensureIntroMessage(messages: ChatMessage[], introText: string) {
  if (!introText.trim()) {
    return messages;
  }

  if (messages[0]?.sender === "bot" && messages[0]?.text === introText) {
    return messages;
  }

  const messagesWithoutIntro = messages.filter(
    (message) => !(message.sender === "bot" && message.text === introText),
  );

  return [{
    ...buildBotMessage(introText),
    source: "intro",
  }, ...messagesWithoutIntro];
}

function serializeLearnerChatHistory(messages: ChatMessage[]) {
  return messages
    .filter((message) => message.source !== "history_event" && message.source !== "intro")
    .map((message) => ({
      sender: message.sender,
      text: message.text,
      timestamp: message.timestamp,
    }));
}

function isSameChatMessage(left: Pick<ChatMessage, "sender" | "text">, right: Pick<ChatMessage, "sender" | "text">) {
  return left.sender === right.sender && left.text === right.text;
}

function areMessageListsEquivalent(left: ChatMessage[], right: ChatMessage[]) {
  return left.length === right.length && left.every((message, index) => isSameChatMessage(message, right[index]));
}

function isMessageListPrefix(prefix: ChatMessage[], full: ChatMessage[]) {
  return prefix.length <= full.length && prefix.every((message, index) => isSameChatMessage(message, full[index]));
}

function reconcileChatHistory(
  localMessages: ChatMessage[],
  incomingMessages: ChatMessage[],
  preferLocalMessages = false,
) {
  if (areMessageListsEquivalent(localMessages, incomingMessages)) {
    return { messages: localMessages, backendCaughtUp: true };
  }

  // Keep optimistic learner messages visible until the backend history catches up.
  if (preferLocalMessages && localMessages.length > incomingMessages.length && isMessageListPrefix(incomingMessages, localMessages)) {
    return { messages: localMessages, backendCaughtUp: false };
  }

  return { messages: incomingMessages, backendCaughtUp: true };
}

function isLearnerChatClosed(ticket: Pick<Ticket, "status" | "chatState">) {
  return ticket.status === "Closed" || ticket.chatState === "closed";
}

function isWaitingForLiveAgentAssignment(ticket: Pick<Ticket, "liveChatRequested" | "assignedAgentId" | "status" | "chatState">) {
  return ticket.liveChatRequested && !ticket.assignedAgentId && !isLearnerChatClosed(ticket);
}

function ensureBotStatusMessage(messages: ChatMessage[], text: string) {
  if (!text.trim() || messages.some((message) => message.sender === "bot" && message.text === text)) {
    return messages;
  }

  return [...messages, buildBotMessage(text)];
}

function formatDateInputValue(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function parseLocalDateTime(dateValue: string, timeValue: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(dateValue) || !/^\d{2}:\d{2}$/.test(timeValue)) {
    return null;
  }

  const [year, month, day] = dateValue.split("-").map(Number);
  const [hours, minutes] = timeValue.split(":").map(Number);
  const parsed = new Date(year, month - 1, day, hours, minutes, 0, 0);

  if (
    Number.isNaN(parsed.getTime())
    || parsed.getFullYear() !== year
    || parsed.getMonth() !== month - 1
    || parsed.getDate() !== day
    || parsed.getHours() !== hours
    || parsed.getMinutes() !== minutes
  ) {
    return null;
  }

  return parsed;
}

function getTimeInTimeZoneMinutes(date: Date, timeZone: string) {
  const formatter = new Intl.DateTimeFormat("en-GB", {
    timeZone,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  const parts = formatter.formatToParts(date);
  const hours = Number(parts.find((part) => part.type === "hour")?.value ?? Number.NaN);
  const minutes = Number(parts.find((part) => part.type === "minute")?.value ?? Number.NaN);

  if (Number.isNaN(hours) || Number.isNaN(minutes)) {
    return Number.NaN;
  }

  return (hours * 60) + minutes;
}

function isMinutesWithinRange(minutes: number, startMinutes: number, endMinutes: number) {
  return minutes >= startMinutes && minutes <= endMinutes;
}

function isWithinSupportSessionWindow(requestedDateTime: Date) {
  const ukMinutes = getTimeInTimeZoneMinutes(requestedDateTime, ukSupportTimeZone);

  return isMinutesWithinRange(ukMinutes, ukSupportSessionStartMinutes, ukSupportSessionEndMinutes);
}

function isSupportSessionTimeAligned(requestedDateTime: Date) {
  const localMinutes = (requestedDateTime.getHours() * 60) + requestedDateTime.getMinutes();
  return localMinutes % supportSessionSlotIntervalMinutes === 0;
}

function getSupportSessionValidationMessage(dateValue: string, timeValue: string, now = new Date()) {
  if (!dateValue || !timeValue) {
    return "";
  }

  const requestedDateTime = parseLocalDateTime(dateValue, timeValue);
  if (!requestedDateTime) {
    return "Please choose a valid session date and time.";
  }

  if ((requestedDateTime.getTime() - now.getTime()) <= supportSessionLeadTimeMs) {
    return "Support sessions must be booked more than 24 hours in advance.";
  }

  if (!isSupportSessionTimeAligned(requestedDateTime)) {
    return "Support sessions must start on 30-minute intervals.";
  }

  if (!isWithinSupportSessionWindow(requestedDateTime)) {
    return "Support sessions must be between 8:00 AM and 4:00 PM UK time.";
  }

  return "";
}

function buildSupportSessionTimeOptions(dateValue: string, now = new Date()) {
  if (!dateValue) {
    return [];
  }

  const options: Array<{ value: string; label: string }> = [];

  for (let minutes = 0; minutes < 24 * 60; minutes += supportSessionSlotIntervalMinutes) {
    const hours = String(Math.floor(minutes / 60)).padStart(2, "0");
    const mins = String(minutes % 60).padStart(2, "0");
    const value = `${hours}:${mins}`;
    const requestedDateTime = parseLocalDateTime(dateValue, value);

    if (!requestedDateTime) {
      continue;
    }

    if ((requestedDateTime.getTime() - now.getTime()) <= supportSessionLeadTimeMs) {
      continue;
    }

    if (!isWithinSupportSessionWindow(requestedDateTime)) {
      continue;
    }

    options.push({
      value,
      label: new Intl.DateTimeFormat("en-US", {
        hour: "numeric",
        minute: "2-digit",
        hour12: true,
      }).format(requestedDateTime),
    });
  }

  return options;
}

function formatSupportSessionDetails(dateValue: string, timeValue: string) {
  const requestedDateTime = parseLocalDateTime(dateValue, timeValue);

  if (!requestedDateTime) {
    return {
      dateLabel: dateValue,
      timeLabel: timeValue,
    };
  }

  return {
    dateLabel: new Intl.DateTimeFormat("en-US", {
      weekday: "long",
      month: "long",
      day: "numeric",
      year: "numeric",
    }).format(requestedDateTime),
    timeLabel: new Intl.DateTimeFormat("en-US", {
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    }).format(requestedDateTime),
  };
}

const ChatSupport = () => {
  const navigate = useNavigate();
  const { ticket, bookingSummary, setTicket, updateTicket, setBookingSummary, clearBookingSummary } = useSupport();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [bookingOpen, setBookingOpen] = useState(false);
  const [bookingDate, setBookingDate] = useState("");
  const [bookingTime, setBookingTime] = useState("");
  const [isClosing, setIsClosing] = useState(false);
  const [isBooking, setIsBooking] = useState(false);
  const [isSendingMessage, setIsSendingMessage] = useState(false);
  const [isRequestingLiveAgent, setIsRequestingLiveAgent] = useState(false);
  const [isDownloadingTranscript, setIsDownloadingTranscript] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const messagesRef = useRef<ChatMessage[]>([]);
  const hasPendingOptimisticHistoryRef = useRef(false);
  const ticketRef = useRef(ticket);
  const isSupportReviewChatLocked = isAwaitingSupportReviewTicket(ticket);
  const isQuickTicketOnlyFlow = isQuickTicketOnlyRequesterRole(ticket.requesterRole);
  const isMeetingChatReadOnly = Boolean(bookingSummary) || isAwaitingMeetingTicket(ticket);

  const replaceMessages = (nextMessages: ChatMessage[], persistToTicket = false) => {
    messagesRef.current = nextMessages;
    setMessages(nextMessages);

    if (persistToTicket) {
      updateTicket({ chatHistory: nextMessages });
    }
  };

  useEffect(() => {
    ticketRef.current = ticket;
  }, [ticket]);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  useEffect(() => {
    if (isQuickTicketOnlyFlow) {
      navigate(getSupportResumePath(ticket, bookingSummary));
      return;
    }
  }, [bookingSummary, isQuickTicketOnlyFlow, navigate, ticket]);

  useEffect(() => {
    if (isSupportReviewChatLocked) {
      navigate("/support/status");
      return;
    }
  }, [navigate, isSupportReviewChatLocked]);

  useEffect(() => {
    if (!ticket.email) {
      navigate("/support");
      return;
    }

    let cancelled = false;

    const fallbackIntroMessage = buildSupportIntroMessage(
      ticket.learnerName,
      ticket.category,
      ticket.technicalSubcategory,
    );

      const applyIntroMessage = (
        introMessage: string,
        patch?: {
          learnerName?: string;
          category?: Category;
          technicalSubcategory?: TechnicalSubcategory;
          status?: "Open" | "Pending" | "Closed";
          statusReason?: string;
          assignedAgentId?: number | null;
          chatState?: "open" | "closed";
          liveChatRequested?: boolean;
        },
      ) => {
      const nextMessages = ensureIntroMessage(ticket.chatHistory, introMessage);
      const decoratedMessages = isWaitingForLiveAgentAssignment({
        liveChatRequested: patch?.liveChatRequested ?? ticket.liveChatRequested,
        assignedAgentId: patch?.assignedAgentId ?? ticket.assignedAgentId,
        status: patch?.status ?? ticket.status,
        chatState: patch?.chatState ?? ticket.chatState,
      })
        ? ensureBotStatusMessage(nextMessages, liveAgentQueueWaitingMessage)
        : nextMessages;

      if (cancelled) {
        return;
      }

      replaceMessages(decoratedMessages);
      updateTicket({
        ...patch,
        chatHistory: decoratedMessages,
      });
    };

    const initializeChat = async () => {
      if (!ticket.id) {
        applyIntroMessage(fallbackIntroMessage);
        return;
      }

      try {
        const [contextResponse, historyResponse] = await Promise.all([
          fetch(`/api/tickets/${encodeURIComponent(ticket.id)}/chat-context`),
          fetch(`/api/tickets/${encodeURIComponent(ticket.id)}/chat-history`),
        ]);
        const payload = (await contextResponse.json().catch(() => null)) as
          | {
              introMessage?: string;
              learner?: { fullName?: string };
              ticket?: {
                category?: Category;
                technicalSubcategory?: TechnicalSubcategory;
                status?: "Open" | "Pending" | "Closed";
                statusReason?: string;
                assignedAgentId?: number | null;
                chatState?: "open" | "closed";
                liveChatRequested?: boolean;
              };
            }
          | null;
        const historyPayload = (await historyResponse.json().catch(() => null)) as
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
              chatHistory?: Array<{
                  id: string;
                  sender: "bot" | "user" | "agent";
                  source?: "message" | "history_event" | "intro";
                  text: string;
                  timestamp: string;
                }>;
            }
          | null;

        const resolvedIntroMessage = contextResponse.ok && payload?.introMessage
          ? payload.introMessage
          : fallbackIntroMessage;

        if (historyResponse.ok && historyPayload?.ticket) {
          const nextMessages = ensureIntroMessage(historyPayload.chatHistory || [], resolvedIntroMessage);
          const decoratedMessages = isWaitingForLiveAgentAssignment({
            liveChatRequested: Boolean(historyPayload.ticket.liveChatRequested),
            assignedAgentId: historyPayload.ticket.assignedAgentId ?? ticket.assignedAgentId,
            status: historyPayload.ticket.status || ticket.status,
            chatState: historyPayload.ticket.chatState ?? ticket.chatState,
          })
            ? ensureBotStatusMessage(nextMessages, liveAgentQueueWaitingMessage)
            : nextMessages;

          if (cancelled) {
            return;
          }

          hasPendingOptimisticHistoryRef.current = false;
          replaceMessages(decoratedMessages);
          updateTicket({
            learnerName: payload?.learner?.fullName || ticket.learnerName,
            category: payload?.ticket?.category || ticket.category,
            technicalSubcategory: payload?.ticket?.technicalSubcategory || ticket.technicalSubcategory,
            status: historyPayload.ticket.status || ticket.status,
            statusReason: historyPayload.ticket.statusReason || ticket.statusReason,
            assignedAgentId: historyPayload.ticket.assignedAgentId ?? ticket.assignedAgentId,
            assignedTeam: historyPayload.ticket.assignedTeam || ticket.assignedTeam,
            slaStatus: historyPayload.ticket.slaStatus || ticket.slaStatus,
            createdAt: historyPayload.ticket.createdAt || ticket.createdAt,
            chatState: historyPayload.ticket.chatState ?? ticket.chatState,
            liveChatRequested: Boolean(historyPayload.ticket.liveChatRequested),
            chatHistory: decoratedMessages,
          });
          return;
        }

        if (!contextResponse.ok || !payload?.introMessage) {
          applyIntroMessage(fallbackIntroMessage);
          return;
        }

        applyIntroMessage(payload.introMessage, {
          learnerName: payload.learner?.fullName || "",
          category: payload.ticket?.category || ticket.category,
          technicalSubcategory: payload.ticket?.technicalSubcategory || "",
          status: payload.ticket?.status || ticket.status,
          statusReason: payload.ticket?.statusReason || ticket.statusReason,
          assignedAgentId: payload.ticket?.assignedAgentId ?? ticket.assignedAgentId,
          chatState: payload.ticket?.chatState ?? ticket.chatState,
          ...(typeof payload.ticket?.liveChatRequested === "boolean" ? { liveChatRequested: payload.ticket.liveChatRequested } : {}),
        });
      } catch {
        applyIntroMessage(fallbackIntroMessage);
      }
    };

    void initializeChat();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [isSendingMessage, messages]);

  useEffect(() => {
    if (!ticket.id || isLearnerChatClosed(ticket)) {
      return;
    }

    const intervalId = window.setInterval(() => {
      if (isSendingMessage || isRequestingLiveAgent) {
        return;
      }

      void (async () => {
        try {
          const response = await fetch(`/api/tickets/${encodeURIComponent(ticket.id)}/chat-history`);
          const payload = (await response.json().catch(() => null)) as
            | {
                message?: string;
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
                chatHistory?: Array<{
                  id: string;
                  sender: "bot" | "user" | "agent";
                  source?: "message" | "history_event" | "intro";
                  text: string;
                  timestamp: string;
                }>;
              }
            | null;

          if (!response.ok || !payload?.ticket) {
            return;
          }

          const currentMessages = messagesRef.current;
          const { messages: nextMessages, backendCaughtUp } = reconcileChatHistory(
            currentMessages,
            payload.chatHistory || [],
            hasPendingOptimisticHistoryRef.current,
          );
          const decoratedMessages = isWaitingForLiveAgentAssignment({
            liveChatRequested: Boolean(payload.ticket.liveChatRequested),
            assignedAgentId: payload.ticket.assignedAgentId ?? ticketRef.current.assignedAgentId,
            status: payload.ticket.status || ticketRef.current.status,
            chatState: payload.ticket.chatState ?? ticketRef.current.chatState,
          })
            ? ensureBotStatusMessage(nextMessages, liveAgentQueueWaitingMessage)
            : nextMessages;
          hasPendingOptimisticHistoryRef.current = !backendCaughtUp;

          if (!areMessageListsEquivalent(currentMessages, decoratedMessages)) {
            replaceMessages(decoratedMessages);
          }

          updateTicket({
            chatHistory: decoratedMessages,
            status: payload.ticket.status || ticketRef.current.status,
            statusReason: payload.ticket.statusReason || ticketRef.current.statusReason,
            assignedAgentId: payload.ticket.assignedAgentId ?? ticketRef.current.assignedAgentId,
            assignedTeam: payload.ticket.assignedTeam || ticketRef.current.assignedTeam,
            slaStatus: payload.ticket.slaStatus || ticketRef.current.slaStatus,
            createdAt: payload.ticket.createdAt || ticketRef.current.createdAt,
            chatState: payload.ticket.chatState ?? ticketRef.current.chatState,
            liveChatRequested: Boolean(payload.ticket.liveChatRequested),
          });
          if ("bookingSummary" in payload) {
            setBookingSummary(toBookingSummary(payload.bookingSummary));
          }
        } catch {
          // Keep the learner chat stable; the next successful poll will sync new messages.
        }
      })();
    }, learnerChatPollIntervalMs);

    return () => window.clearInterval(intervalId);
  }, [ticket.id, ticket.status, ticket.chatState, isSendingMessage, isRequestingLiveAgent]);

  const pushMsg = (message: Omit<ChatMessage, "id" | "timestamp">) => {
    const nextMessages = [
      ...messagesRef.current,
      { ...message, id: crypto.randomUUID(), timestamp: buildTimestamp() },
    ];
    replaceMessages(nextMessages, true);
  };

  const handleSend = async () => {
    const trimmedInput = input.trim();
    if (!trimmedInput || isSendingMessage) {
      inputRef.current?.focus();
      return;
    }

    if (isLearnerChatClosed(ticket)) {
      toast.error("This chat is already closed.");
      return;
    }

    if (isMeetingChatReadOnly) {
      toast.error("Chat replies are disabled while your support meeting is active.");
      return;
    }

    if (!ticket.id) {
      toast.error("This ticket is not ready for chatbot messaging yet.");
      return;
    }

    const userMessage: Omit<ChatMessage, "id" | "timestamp"> = {
      sender: "user",
      text: trimmedInput,
    };
    const previousMessages = messagesRef.current;
    const nextMessages = [...previousMessages, {
      ...userMessage,
      id: crypto.randomUUID(),
      timestamp: buildTimestamp(),
    }];

    hasPendingOptimisticHistoryRef.current = true;
    replaceMessages(nextMessages, true);
    setInput("");
    setIsSendingMessage(true);

    try {
      if (ticket.liveChatRequested) {
        const response = await fetch(`/api/tickets/${encodeURIComponent(ticket.id)}/chat-history`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            status: ticket.status,
            statusReason: ticket.statusReason,
            messages: serializeLearnerChatHistory(nextMessages),
          }),
        });

        const payload = (await response.json().catch(() => null)) as {
          message?: string;
          ticket?: {
            status?: "Open" | "Pending" | "Closed";
            statusReason?: string;
            assignedAgentId?: number | null;
            assignedTeam?: string;
            slaStatus?: string;
            createdAt?: string;
            chatState?: "open" | "closed";
          };
        } | null;

        if (!response.ok) {
          hasPendingOptimisticHistoryRef.current = false;
          replaceMessages(previousMessages, true);
          setInput(trimmedInput);
          toast.error(payload?.message || "We could not send your message to the live support queue right now.");
          return;
        }

        updateTicket({
          chatHistory: nextMessages,
          status: payload?.ticket?.status || ticket.status,
          statusReason: payload?.ticket?.statusReason || ticket.statusReason,
          assignedAgentId: payload?.ticket?.assignedAgentId ?? ticket.assignedAgentId,
          assignedTeam: payload?.ticket?.assignedTeam || ticket.assignedTeam,
          slaStatus: payload?.ticket?.slaStatus || ticket.slaStatus,
          createdAt: payload?.ticket?.createdAt || ticket.createdAt,
          chatState: payload?.ticket?.chatState ?? ticket.chatState,
          liveChatRequested: true,
        });
        return;
      }

      const response = await fetch(`/api/tickets/${encodeURIComponent(ticket.id)}/chatbot-message`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message: trimmedInput,
          clientTimeZone: Intl.DateTimeFormat().resolvedOptions().timeZone || null,
          messages: serializeLearnerChatHistory(nextMessages),
        }),
      });

      const payload = (await response.json().catch(() => null)) as {
        message?: string;
        reply?: string | null;
        webhookConfigured?: boolean;
        webhookDelivered?: boolean;
      } | null;

      if (!response.ok) {
        hasPendingOptimisticHistoryRef.current = false;
        replaceMessages(previousMessages, true);
        setInput(trimmedInput);
        toast.error(payload?.message || "We could not send your message to the chatbot right now.");
        return;
      }

      if (payload?.reply) {
        pushMsg({ sender: "bot", text: payload.reply });
      } else if (payload?.webhookConfigured === false) {
        pushMsg({ sender: "bot", text: "I received your message, but the chatbot is not connected yet." });
        toast.error("Chatbot webhook is not configured on the server.");
      } else if (payload?.webhookDelivered === false) {
        pushMsg({ sender: "bot", text: "I received your message, but I could not reach the chatbot right now." });
        toast.error("Your message was saved, but the chatbot webhook could not be reached.");
      } else {
        pushMsg({ sender: "bot", text: "Your message was sent, but the chatbot did not return a reply." });
      }
    } catch {
      hasPendingOptimisticHistoryRef.current = false;
      replaceMessages(previousMessages, true);
      setInput(trimmedInput);
      toast.error("We could not connect to the server. Please try again.");
    } finally {
      setIsSendingMessage(false);
      window.setTimeout(() => inputRef.current?.focus(), 0);
    }
  };

  const handleRequestLiveAgent = async () => {
    if (!ticket.id || isLearnerChatClosed(ticket) || ticket.liveChatRequested || isRequestingLiveAgent) {
      return;
    }

    if (isMeetingChatReadOnly) {
      toast.error("Live chat requests are unavailable while your support meeting is active.");
      return;
    }

    setIsRequestingLiveAgent(true);

    try {
      const response = await fetch(`/api/tickets/${encodeURIComponent(ticket.id)}/live-chat-request`, {
        method: "POST",
      });

      const payload = (await response.json().catch(() => null)) as {
        message?: string;
        ticket?: {
          chatState?: "open" | "closed";
          liveChatRequested?: boolean;
          assignedAgentId?: number | null;
          assignedAgentName?: string | null;
        };
      } | null;

      if (!response.ok) {
        toast.error(payload?.message || "We could not request a live support agent right now.");
        return;
      }

      if (payload?.ticket?.assignedAgentId) {
        try {
          const historyResponse = await fetch(`/api/tickets/${encodeURIComponent(ticket.id)}/chat-history`);
          const historyPayload = (await historyResponse.json().catch(() => null)) as
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
                chatHistory?: Array<{
                  id: string;
                  sender: "bot" | "user" | "agent";
                  source?: "message" | "history_event" | "intro";
                  text: string;
                  timestamp: string;
                }>;
              }
            | null;

          if (historyResponse.ok && historyPayload?.ticket) {
            const nextMessages = historyPayload.chatHistory || [];
            replaceMessages(nextMessages);
            updateTicket({
              chatHistory: nextMessages,
              status: historyPayload.ticket.status || ticket.status,
              statusReason: historyPayload.ticket.statusReason || ticket.statusReason,
              assignedAgentId: historyPayload.ticket.assignedAgentId ?? payload.ticket.assignedAgentId ?? null,
              assignedTeam: historyPayload.ticket.assignedTeam || ticket.assignedTeam,
              slaStatus: historyPayload.ticket.slaStatus || ticket.slaStatus,
              createdAt: historyPayload.ticket.createdAt || ticket.createdAt,
              chatState: historyPayload.ticket.chatState ?? payload.ticket.chatState ?? ticket.chatState,
              liveChatRequested: Boolean(historyPayload.ticket.liveChatRequested ?? payload.ticket.liveChatRequested ?? true),
            });
          } else {
            updateTicket({
              assignedAgentId: payload.ticket.assignedAgentId ?? null,
              chatState: payload.ticket.chatState ?? ticket.chatState,
              liveChatRequested: payload.ticket.liveChatRequested ?? true,
            });
          }
        } catch {
          updateTicket({
            assignedAgentId: payload.ticket.assignedAgentId ?? null,
            chatState: payload.ticket.chatState ?? ticket.chatState,
            liveChatRequested: payload.ticket.liveChatRequested ?? true,
          });
        }

        toast.success(`You are now talking to ${payload.ticket.assignedAgentName || "the assigned support admin"}.`);
      } else {
        const nextMessages = ensureBotStatusMessage(messagesRef.current, liveAgentQueueWaitingMessage);
        replaceMessages(nextMessages);

        await fetch(`/api/tickets/${encodeURIComponent(ticket.id)}/chat-history`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            status: ticket.status,
            statusReason: ticket.statusReason,
            messages: serializeLearnerChatHistory(nextMessages),
          }),
        }).catch(() => null);

        updateTicket({
          chatHistory: nextMessages,
          assignedAgentId: payload?.ticket?.assignedAgentId ?? null,
          chatState: payload?.ticket?.chatState ?? ticket.chatState,
          liveChatRequested: payload?.ticket?.liveChatRequested ?? true,
        });
        toast.info(liveAgentQueueWaitingMessage);
      }
    } catch {
      toast.error("We could not connect to the server. Please try again.");
    } finally {
      setIsRequestingLiveAgent(false);
    }
  };

  const openBookingDialog = () => {
    if (isLearnerChatClosed(ticket)) {
      toast.error("This chat is already closed.");
      return;
    }

    if (isMeetingChatReadOnly) {
      toast.error("This chat is in read-only mode while your support meeting is active.");
      return;
    }

    if (!ticket.id || !ticket.email) {
      toast.error("We could not prepare your booking details right now.");
      return;
    }

    setBookingOpen(true);
  };

  const minBookingDate = formatDateInputValue(new Date());
  const bookingValidationMessage = getSupportSessionValidationMessage(bookingDate, bookingTime);
  const bookingTimeOptions = buildSupportSessionTimeOptions(bookingDate);

  const handleClose = async () => {
    const nextMessages = messagesRef.current;

    if (!ticket.id) {
      updateTicket({
        chatHistory: nextMessages,
        status: "Closed",
        statusReason: chatbotClosingReason,
      });
      navigate("/support/status");
      return;
    }

    setIsClosing(true);

    try {
      const response = await fetch(`/api/tickets/${encodeURIComponent(ticket.id)}/chat-history`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          status: "Closed",
          statusReason: chatbotClosingReason,
          messages: serializeLearnerChatHistory(nextMessages),
        }),
      });

      const payload = (await response.json().catch(() => null)) as {
        message?: string;
        webhookConfigured?: boolean;
        webhookDelivered?: boolean;
        ticket?: {
          status?: string;
          statusReason?: string;
          assignedTeam?: string;
          slaStatus?: string;
          createdAt?: string;
          chatState?: "open" | "closed";
        };
      } | null;

      if (!response.ok) {
        toast.error(payload?.message || "We could not save the chat history right now.");
        return;
      }

      replaceMessages(nextMessages, true);
      updateTicket({
        chatHistory: nextMessages,
        status: "Closed",
        statusReason: payload?.ticket?.statusReason || chatbotClosingReason,
        assignedTeam: payload?.ticket?.assignedTeam || ticket.assignedTeam,
        slaStatus: payload?.ticket?.slaStatus || ticket.slaStatus,
        createdAt: payload?.ticket?.createdAt || ticket.createdAt,
        chatState: payload?.ticket?.chatState || "closed",
      });
      navigate("/support/status");
    } catch {
      toast.error("We could not connect to the server. Please try again.");
    } finally {
      setIsClosing(false);
    }
  };

  const handleBooking = async () => {
    if (!ticket.id || !bookingDate || !bookingTime) return;
    const requestedDateTime = parseLocalDateTime(bookingDate, bookingTime);

    if (bookingValidationMessage) {
      toast.error(bookingValidationMessage);
      return;
    }

    if (!requestedDateTime) {
      toast.error("Please choose a valid session date and time.");
      return;
    }

    setIsBooking(true);

    try {
      const response = await fetch(`/api/tickets/${encodeURIComponent(ticket.id)}/session-requests`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          date: bookingDate,
          time: bookingTime,
          scheduledAt: requestedDateTime.toISOString(),
          clientTimeZone: Intl.DateTimeFormat().resolvedOptions().timeZone || null,
        }),
      });

      const payload = (await response.json().catch(() => null)) as {
        message?: string;
        webhookConfigured?: boolean;
        webhookDelivered?: boolean;
        reservationConfirmed?: boolean;
        meetingJoinUrl?: string | null;
        ticket?: {
          status?: string;
          statusReason?: string;
          assignedTeam?: string;
        };
      } | null;

      if (!response.ok) {
        toast.error(payload?.message || "We could not save the support session request.");
        return;
      }

      const bookingDetails = formatSupportSessionDetails(bookingDate, bookingTime);
      setBookingOpen(false);
      updateTicket({
        status: (payload?.ticket?.status as typeof ticket.status | undefined) || "Pending",
        statusReason: payload?.ticket?.statusReason || awaitingMeetingReason,
        assignedTeam: payload?.ticket?.assignedTeam || ticket.assignedTeam,
      });
      setBookingDate("");
      setBookingTime("");

      setBookingSummary({
        ...bookingDetails,
        reservationConfirmed: Boolean(payload?.reservationConfirmed),
        meetingJoinUrl: payload?.meetingJoinUrl || null,
      });
      pushMsg({
        sender: "bot",
        text: payload?.reservationConfirmed
          ? `Your support session has been booked for ${bookingDetails.dateLabel} at ${bookingDetails.timeLabel}. The Teams slot is now reserved for you.`
          : `Thank you. Your support session request has been submitted for ${bookingDetails.dateLabel} at ${bookingDetails.timeLabel}. Our team will review it and confirm the next steps with you shortly.`,
      });
      if (payload?.reservationConfirmed) {
        toast.success("Your Teams support session has been reserved successfully.");
      } else if (payload?.webhookConfigured === false) {
        toast.success("Your request has been submitted successfully. Our team will review it shortly.");
      } else if (payload?.webhookDelivered === false) {
        toast.success("Your request has been submitted successfully. Confirmation may take a little longer than usual.");
      } else {
        toast.success("Your support session request has been submitted successfully.");
      }
      navigate("/support/status");
    } catch {
      toast.error("We could not connect to the server. Please try again.");
    } finally {
      setIsBooking(false);
    }
  };

  const handleStartNewChat = () => {
    setTicket({
      id: "",
      learnerName: ticket.learnerName,
      email: ticket.email,
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
    });
    clearBookingSummary();
    navigate("/support/inquiry");
  };

  const handleDownloadTranscript = async () => {
    const transcriptMessages = messagesRef.current;

    if (transcriptMessages.length === 0) {
      toast.error("No chat history is available to export yet.");
      return;
    }

    setIsDownloadingTranscript(true);

    try {
      await downloadChatPdf({
        ticketId: ticket.id || "support-chat",
        messages: transcriptMessages,
      });
    } catch {
      toast.error("We could not generate the PDF right now.");
    } finally {
      setIsDownloadingTranscript(false);
    }
  };

  const isChatClosed = isLearnerChatClosed(ticket);
  const isInactivityClosed = ticket.statusReason === inactivityClosingReason;
  const closedPanelTitle = isInactivityClosed ? "Chat closed due to inactivity" : "Chat closed";
  const showReadOnlyPanel = !isChatClosed && isMeetingChatReadOnly;
  const isWaitingForAssignment = isWaitingForLiveAgentAssignment(ticket);

  return (
    <SupportLayout>
      <StepIndicator current={3} />
      <div className="mx-auto max-w-5xl min-h-0">
        <div className="relative flex h-[calc(100dvh-245px)] min-h-[420px] max-h-[760px] flex-col overflow-hidden rounded-2xl border border-primary/10 bg-card shadow-[0_12px_30px_-18px_hsl(var(--primary)/0.35),0_6px_16px_-10px_hsl(var(--primary)/0.18)] sm:h-[calc(100dvh-260px)] sm:min-h-[520px]">
          <div className="relative z-10 shrink-0 flex flex-col gap-3 border-b border-primary/10 bg-gradient-to-r from-primary/[0.05] via-card to-card px-4 py-3.5 shadow-[0_10px_22px_-18px_hsl(var(--primary)/0.4)] sm:flex-row sm:items-center sm:justify-between md:px-6">
            <div className="flex items-center gap-2">
              <div className="flex items-center justify-center w-8 h-8 rounded-lg gradient-primary">
                <Headphones className="w-4 h-4 text-primary-foreground" />
              </div>
              <div className="text-left">
                <div className="text-sm font-semibold">Kent Chatbot</div>
                {isWaitingForAssignment ? (
                  <div className="text-xs font-medium text-amber-600">Waiting for an available support admin</div>
                ) : ticket.liveChatRequested ? (
                  <div className="text-xs font-medium text-success">Live chat requested</div>
                ) : null}
              </div>
            </div>
            <div className="flex w-full items-center justify-between gap-2 sm:w-auto sm:justify-end">
              <StatusBadge status={isChatClosed ? "Closed" : ticket.status} />
              <Button
                variant="outline"
                size="sm"
                onClick={() => void handleClose()}
                disabled={isClosing || isChatClosed || isMeetingChatReadOnly}
              >
                <X className="w-4 h-4 mr-1.5" /> Close
              </Button>
            </div>
          </div>

          <div className="relative flex min-h-0 flex-1 flex-col">
            <div
              ref={scrollRef}
              className="min-h-0 flex-1 space-y-4 overflow-y-auto bg-gradient-to-b from-background to-card px-3 py-4 pr-16 sm:px-4 sm:py-5 sm:pr-24 md:px-6 md:pr-28"
            >
              {messages.map((message) => (
                <MessageBubble key={message.id} m={message} />
              ))}

              {isSendingMessage && <TypingBubble />}
            </div>

            <SupportActionRail
              onBookingClick={openBookingDialog}
              onLiveAgentClick={handleRequestLiveAgent}
              bookingDisabled={isChatClosed || isMeetingChatReadOnly || !ticket.id || !ticket.email}
              liveAgentDisabled={isChatClosed || isMeetingChatReadOnly || isRequestingLiveAgent || ticket.liveChatRequested}
              liveAgentRequested={ticket.liveChatRequested}
            />
          </div>

          <div className="shrink-0 border-t bg-card p-3 md:p-4">
            {isChatClosed ? (
              <div className="rounded-2xl border border-primary/10 bg-muted/30 px-4 py-4 shadow-[0_10px_24px_-18px_hsl(var(--primary)/0.35)]">
                <div className="text-sm font-semibold text-foreground">{closedPanelTitle}</div>
                <p className="mt-1 text-sm text-muted-foreground">
                  {closedChatDescription}
                </p>
                <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:justify-end">
                  <Button variant="outline" className="w-full sm:w-auto" onClick={() => void handleDownloadTranscript()} disabled={isDownloadingTranscript}>
                    <Download className="h-4 w-4 mr-2" />
                    {isDownloadingTranscript ? "Preparing Transcript..." : "Download Transcript"}
                  </Button>
                  <Button onClick={handleStartNewChat} className="w-full border-0 gradient-primary sm:w-auto">
                    Start New Chat
                  </Button>
                </div>
              </div>
            ) : showReadOnlyPanel ? (
              <div className="rounded-2xl border border-primary/15 bg-primary/5 px-4 py-4 shadow-[0_10px_24px_-18px_hsl(var(--primary)/0.35)]">
                <div className="text-sm font-semibold text-foreground">Chat is read-only during your booked session</div>
                <p className="mt-1 text-sm text-muted-foreground">
                  You can still review the conversation here, but new messages are disabled until the support meeting is cancelled or completed.
                </p>
                <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:justify-end">
                  <Button variant="outline" className="w-full sm:w-auto" onClick={() => navigate("/support/status")}>
                    View Meeting Status
                  </Button>
                </div>
              </div>
            ) : (
              <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
                <div className="flex flex-1 items-end gap-2">
                  <Button variant="ghost" size="icon" className="shrink-0" aria-label="Attach">
                    <Paperclip className="w-5 h-5" />
                  </Button>
                  <Input
                    ref={inputRef}
                    value={input}
                    onChange={(event) => setInput(event.target.value)}
                    onKeyDown={(event) => event.key === "Enter" && void handleSend()}
                    placeholder="Type your message..."
                    className="h-11 flex-1"
                  />
                </div>
                <Button
                  onClick={() => void handleSend()}
                  className="h-11 w-full border-0 shrink-0 gradient-primary sm:w-auto"
                  disabled={isSendingMessage}
                >
                  <Send className="w-4 h-4" />
                </Button>
              </div>
            )}
          </div>
        </div>
      </div>

      <Dialog open={bookingOpen} onOpenChange={setBookingOpen}>
        <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>Book a Support Session</DialogTitle>
              <DialogDescription>
                Choose a date and time that works for you. We will use your verified Aptem email for the booking, and sessions must be more than 24 hours away between 8:00 AM and 4:00 PM UK time using 30-minute start times.
              </DialogDescription>
            </DialogHeader>
          <div className="space-y-3">
            <div className="rounded-2xl border border-primary/20 bg-primary/5 px-4 py-3">
              <div className="text-xs font-semibold uppercase tracking-wide text-primary">Aptem Email</div>
              <div className="mt-1 text-sm font-medium text-foreground break-all">{ticket.email || "-"}</div>
              <p className="mt-1 text-xs text-muted-foreground">
                This is the email address that will be used for your booking and follow-up.
              </p>
            </div>
            <div>
              <label className="block mb-1.5 text-sm font-medium">Date</label>
              <Input
                type="date"
                min={minBookingDate}
                value={bookingDate}
                onChange={(event) => {
                  setBookingDate(event.target.value);
                  setBookingTime("");
                }}
              />
            </div>
            <div>
              <label className="block mb-1.5 text-sm font-medium">Time</label>
              <Select value={bookingTime} onValueChange={setBookingTime} disabled={!bookingDate || bookingTimeOptions.length === 0}>
                <SelectTrigger className="h-11">
                  <SelectValue placeholder={bookingDate ? "Select a time slot" : "Choose a date first"} />
                </SelectTrigger>
                <SelectContent>
                  {bookingTimeOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {bookingDate && bookingTimeOptions.length === 0 ? (
                <p className="mt-1.5 text-xs text-muted-foreground">
                  No valid support session slots are available for the selected date.
                </p>
              ) : null}
            </div>
            <p className={cn("text-xs", bookingValidationMessage ? "text-destructive" : "text-muted-foreground")}>
              {bookingValidationMessage || "Allowed meeting hours are 8:00 AM to 4:00 PM UK time, with more than 24 hours notice required, and sessions start on 30-minute intervals."}
            </p>
          </div>
          <DialogFooter>
            <Button
              className="w-full border-0 gradient-primary"
              disabled={!bookingDate || !bookingTime || Boolean(bookingValidationMessage) || isBooking}
              onClick={() => void handleBooking()}
            >
              <Check className="w-4 h-4 mr-2" /> {isBooking ? "Saving..." : "Confirm Booking"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

    </SupportLayout>
  );
};

const MessageBubble = ({ m }: { m: ChatMessage }) => {
  const isUser = m.sender === "user";
  const isAgent = m.sender === "agent";

  return (
    <div className={cn("flex gap-2.5", isUser && "flex-row-reverse")}>
      <div
        className={cn(
          "h-8 w-8 rounded-full flex items-center justify-center shrink-0",
          isUser
            ? "bg-primary text-primary-foreground"
            : isAgent
              ? "bg-success text-success-foreground"
              : "bg-secondary text-foreground",
        )}
      >
        {isUser ? (
          <User className="w-4 h-4" />
        ) : isAgent ? (
          <Headphones className="w-4 h-4" />
        ) : (
          <Bot className="w-4 h-4" />
        )}
      </div>
      <div className={cn("max-w-[80%]", isUser && "text-right")}>
        <div className="mb-1 text-xs text-muted-foreground">
          {isUser ? "You" : isAgent ? "Live Chat" : "Help Bot"} - {m.timestamp}
        </div>
        <div
          className={cn(
            "rounded-2xl px-4 py-2.5 text-sm shadow-soft inline-block text-left",
            isUser
              ? "gradient-primary text-primary-foreground rounded-tr-sm"
              : "bg-card border rounded-tl-sm",
          )}
        >
          {m.text}
        </div>
      </div>
    </div>
  );
};

const TypingBubble = () => (
  <div className="flex gap-2.5" aria-live="polite" aria-label="Chatbot is thinking">
    <div className="h-8 w-8 rounded-full flex items-center justify-center shrink-0 bg-secondary text-foreground">
      <Bot className="w-4 h-4" />
    </div>
    <div className="max-w-[80%]">
      <div className="mb-1 text-xs text-muted-foreground">Help Bot</div>
      <div className="inline-flex items-center gap-3 rounded-2xl rounded-tl-sm border bg-card px-4 py-3 text-sm shadow-soft">
        <div className="flex items-center gap-1.5">
          <span className="h-2 w-2 animate-pulse rounded-full bg-primary [animation-delay:-0.2s]" />
          <span className="h-2 w-2 animate-pulse rounded-full bg-primary [animation-delay:-0.1s]" />
          <span className="h-2 w-2 animate-pulse rounded-full bg-primary" />
        </div>
      </div>
    </div>
  </div>
);

const SupportActionRail = ({
  onBookingClick,
  onLiveAgentClick,
  bookingDisabled = false,
  liveAgentDisabled = false,
  liveAgentRequested = false,
}: {
  onBookingClick: () => void | Promise<void>;
  onLiveAgentClick: () => void | Promise<void>;
  bookingDisabled?: boolean;
  liveAgentDisabled?: boolean;
  liveAgentRequested?: boolean;
}) => (
  <div className="group/rail pointer-events-none absolute bottom-20 right-3 z-10 flex flex-col items-end gap-2.5 sm:bottom-auto sm:right-4 sm:top-1/2 sm:-translate-y-1/2">
    <SupportActionButton
      icon={CalendarClock}
      title="Book Session"
      desc="Use your Aptem email"
      onClick={onBookingClick}
      disabled={bookingDisabled}
    />
    <SupportActionButton
      icon={Headphones}
      title={liveAgentRequested ? "Live Chat Requested" : "Live Chat"}
      desc={liveAgentRequested ? "Please stay connected" : "Request live support"}
      onClick={onLiveAgentClick}
      disabled={liveAgentDisabled}
      active={liveAgentRequested}
    />
  </div>
);

const SupportActionButton = ({
  icon: Icon,
  title,
  desc,
  onClick,
  disabled = false,
  active = false,
}: {
  icon: ComponentType<{ className?: string }>;
  title: string;
  desc: string;
  onClick?: () => void | Promise<void>;
  disabled?: boolean;
  active?: boolean;
}) => (
  <button
    type="button"
    onClick={disabled ? undefined : () => void onClick?.()}
    aria-label={`${title}. ${desc}`}
    aria-disabled={disabled}
    className={cn(
      "group/button pointer-events-auto flex h-11 min-w-[152px] items-center gap-2.5 rounded-2xl border border-border/80 bg-card/95 px-3.5 text-left shadow-lg backdrop-blur-sm transition-all duration-300 ease-out focus:outline-none focus:ring-2 focus:ring-primary/20 sm:h-12 sm:w-12 sm:min-w-0 sm:gap-3 sm:overflow-hidden sm:rounded-full sm:px-3 sm:transition-[width,transform,box-shadow,border-color,background-color] sm:duration-[1000ms]",
      active
        ? "border-success/30 bg-success/10 shadow-card sm:w-60"
        : disabled
          ? "cursor-default border-border/60 bg-muted/80"
          : "hover:-translate-y-0.5 hover:border-primary/70 hover:bg-background hover:shadow-card sm:group-hover/rail:w-60 sm:group-focus-within/rail:w-60 sm:focus:w-60 sm:focus:border-primary sm:focus:bg-background",
    )}
  >
    <span
      className={cn(
        "flex h-7 w-7 shrink-0 items-center justify-center rounded-full sm:h-6 sm:w-6",
        active
          ? "bg-success text-success-foreground"
          : disabled
            ? "bg-muted-foreground/20 text-muted-foreground"
            : "bg-primary text-primary-foreground",
      )}
    >
      <Icon className="h-3.5 w-3.5" />
    </span>
    <span
      className={cn(
        "min-w-0 flex-1 sm:max-w-0 sm:flex-none sm:overflow-hidden sm:opacity-0 sm:transition-[max-width,opacity] sm:duration-[1000ms] sm:ease-out sm:group-hover/rail:max-w-[11rem] sm:group-hover/rail:opacity-100 sm:group-focus-within/rail:max-w-[11rem] sm:group-focus-within/rail:opacity-100",
        active && "sm:max-w-[11rem] sm:opacity-100",
      )}
    >
      <span
        className={cn(
          "block text-[13px] font-semibold leading-tight whitespace-nowrap sm:text-sm",
          active ? "text-success" : disabled ? "text-muted-foreground" : "text-foreground",
        )}
      >
        {title}
      </span>
      <span className={cn("mt-0.5 inline-flex items-center gap-1 text-[11px] whitespace-nowrap sm:text-xs", active ? "text-success/80" : "text-muted-foreground")}>
        {desc}
        {!disabled && !active && <ArrowRight className="hidden h-3 w-3 shrink-0 text-primary sm:block" />}
      </span>
    </span>
  </button>
);

export default ChatSupport;
