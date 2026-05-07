import { type ComponentType, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowRight,
  Bot,
  CalendarClock,
  Check,
  CheckCircle2,
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
import { StatusBadge } from "@/components/support/StatusBadge";
import { StepIndicator } from "@/components/support/StepIndicator";
import { SupportLayout } from "@/components/support/SupportLayout";
import { type Category, type ChatMessage, type TechnicalSubcategory, type TicketStatus, useSupport } from "@/context/SupportContext";
import { downloadChatPdf } from "@/lib/chatPdf";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

const ukSupportTimeZone = "Europe/London";
const ukSupportSessionStartMinutes = 8 * 60;
const ukSupportSessionEndMinutes = 16 * 60;
const supportSessionLeadTimeMs = 24 * 60 * 60 * 1000;
const inactivityReminderDelayMs = 2 * 60 * 1000;
const inactivityAutoCloseDelayMs = 3 * 60 * 1000;
const learnerChatPollIntervalMs = 2500;
const chatbotClosingReason = "Closed via Chatbot";
const awaitingMeetingReason = "Awaiting support meeting";
const inactivityClosingReason = "Closed due to inactivity";
const inactivityClosedText = "This chat has been closed due to inactivity.";
const closedChatDescription = "If you still need help, you can start a new chat and continue with a fresh support request.";
const liveAgentRequestedMessage = "A live support agent has been requested. Please stay connected while we connect you.";

function getIssueLabel(category: string, technicalSubcategory: string) {
  return technicalSubcategory.trim() || category.trim() || "your request";
}

function buildSupportIntroMessage(learnerName: string, category: string, technicalSubcategory: string) {
  const greetingName = learnerName.trim() || "there";
  const issueLabel = getIssueLabel(category, technicalSubcategory);
  return `Hello ${greetingName}, Thank you for reaching Kent College Support, I understand you are reaching us for an issue related to ${issueLabel}, am I correct?`;
}

function buildInactivityReminderText(learnerName: string) {
  const greetingName = learnerName.trim() || "there";
  return `Hi ${greetingName}, are you still connected? Please note that this chat will be automatically closed if we do not receive a reply within 3 minutes.`;
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

  return [buildBotMessage(introText), ...messagesWithoutIntro];
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

  if (!isWithinSupportSessionWindow(requestedDateTime)) {
    return "Support sessions must be between 8:00 AM and 4:00 PM UK time.";
  }

  return "";
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
  const { ticket, setTicket, updateTicket } = useSupport();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [bookingOpen, setBookingOpen] = useState(false);
  const [bookingDate, setBookingDate] = useState("");
  const [bookingTime, setBookingTime] = useState("");
  const [bookingSuccess, setBookingSuccess] = useState<{
    dateLabel: string;
    timeLabel: string;
    reservationConfirmed: boolean;
    meetingJoinUrl: string | null;
  } | null>(null);
  const [isClosing, setIsClosing] = useState(false);
  const [isBooking, setIsBooking] = useState(false);
  const [isSendingMessage, setIsSendingMessage] = useState(false);
  const [isRequestingLiveAgent, setIsRequestingLiveAgent] = useState(false);
  const [isDownloadingTranscript, setIsDownloadingTranscript] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const reminderTimerRef = useRef<number | null>(null);
  const autoCloseTimerRef = useRef<number | null>(null);
  const reminderSentRef = useRef(false);
  const isAutoClosingRef = useRef(false);
  const messagesRef = useRef<ChatMessage[]>([]);
  const ticketRef = useRef(ticket);

  const clearInactivityTimers = () => {
    if (reminderTimerRef.current !== null) {
      window.clearTimeout(reminderTimerRef.current);
      reminderTimerRef.current = null;
    }

    if (autoCloseTimerRef.current !== null) {
      window.clearTimeout(autoCloseTimerRef.current);
      autoCloseTimerRef.current = null;
    }
  };

  const replaceMessages = (nextMessages: ChatMessage[], persistToTicket = false) => {
    messagesRef.current = nextMessages;
    setMessages(nextMessages);

    if (persistToTicket) {
      updateTicket({ chatHistory: nextMessages });
    }
  };

  const appendBotMessage = (text: string, persistToTicket = false) => {
    const nextMessages = [...messagesRef.current, buildBotMessage(text)];
    replaceMessages(nextMessages, persistToTicket);
    return nextMessages;
  };

  const syncChatHistoryToServer = async (
    nextMessages: ChatMessage[],
    options?: {
      status?: TicketStatus;
      statusReason?: string;
    },
  ) => {
    const latestTicket = ticketRef.current;
    if (!latestTicket.id) {
      return null;
    }

    const response = await fetch(`/api/tickets/${encodeURIComponent(latestTicket.id)}/chat-history`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        status: options?.status || latestTicket.status,
        statusReason: options?.statusReason ?? latestTicket.statusReason,
        messages: nextMessages.map((message) => ({
          sender: message.sender,
          text: message.text,
          timestamp: message.timestamp,
        })),
      }),
    });

    const payload = (await response.json().catch(() => null)) as {
      message?: string;
      ticket?: {
        status?: TicketStatus;
        statusReason?: string;
        assignedTeam?: string;
        slaStatus?: string;
        createdAt?: string;
      };
    } | null;

    if (!response.ok) {
      throw new Error(payload?.message || "We could not sync the chat history right now.");
    }

    return payload;
  };

  useEffect(() => {
    ticketRef.current = ticket;
  }, [ticket]);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

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
          liveChatRequested?: boolean;
        },
      ) => {
      const nextMessages = ensureIntroMessage(ticket.chatHistory, introMessage);
      if (cancelled) {
        return;
      }

      replaceMessages(nextMessages);
      updateTicket({
        ...patch,
        chatHistory: nextMessages,
      });
    };

    const initializeChat = async () => {
      if (!ticket.id) {
        applyIntroMessage(fallbackIntroMessage);
        return;
      }

      try {
        const response = await fetch(`/api/tickets/${encodeURIComponent(ticket.id)}/chat-context`);
        const payload = (await response.json().catch(() => null)) as
          | {
              introMessage?: string;
              learner?: { fullName?: string };
              ticket?: {
                category?: Category;
                technicalSubcategory?: TechnicalSubcategory;
                liveChatRequested?: boolean;
              };
            }
          | null;

        if (!response.ok || !payload?.introMessage) {
          applyIntroMessage(fallbackIntroMessage);
          return;
        }

        applyIntroMessage(payload.introMessage, {
          learnerName: payload.learner?.fullName || "",
          category: payload.ticket?.category || ticket.category,
          technicalSubcategory: payload.ticket?.technicalSubcategory || "",
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
    if (!ticket.id || ticket.status === "Closed") {
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
                  assignedTeam?: string;
                  slaStatus?: string;
                  createdAt?: string;
                  liveChatRequested?: boolean;
                };
                chatHistory?: Array<{
                  id: string;
                  sender: "bot" | "user" | "agent";
                  text: string;
                  timestamp: string;
                }>;
              }
            | null;

          if (!response.ok || !payload?.ticket) {
            return;
          }

          const nextMessages = payload.chatHistory || [];
          const currentMessagesJson = JSON.stringify(messagesRef.current);
          const nextMessagesJson = JSON.stringify(nextMessages);

          if (currentMessagesJson !== nextMessagesJson) {
            replaceMessages(nextMessages);
          }

          updateTicket({
            chatHistory: nextMessages,
            status: payload.ticket.status || ticketRef.current.status,
            statusReason: payload.ticket.statusReason || ticketRef.current.statusReason,
            assignedTeam: payload.ticket.assignedTeam || ticketRef.current.assignedTeam,
            slaStatus: payload.ticket.slaStatus || ticketRef.current.slaStatus,
            createdAt: payload.ticket.createdAt || ticketRef.current.createdAt,
            liveChatRequested: Boolean(payload.ticket.liveChatRequested),
          });
        } catch {
          // Keep the learner chat stable; the next successful poll will sync new messages.
        }
      })();
    }, learnerChatPollIntervalMs);

    return () => window.clearInterval(intervalId);
  }, [ticket.id, ticket.status, isSendingMessage, isRequestingLiveAgent]);

  const pushMsg = (message: Omit<ChatMessage, "id" | "timestamp">) => {
    const nextMessages = [
      ...messagesRef.current,
      { ...message, id: crypto.randomUUID(), timestamp: buildTimestamp() },
    ];
    replaceMessages(nextMessages);
  };

  useEffect(() => {
    clearInactivityTimers();

    if (ticket.status !== "Open" || isAutoClosingRef.current) {
      return () => clearInactivityTimers();
    }

    const lastMessage = messages[messages.length - 1];
    if (!lastMessage || lastMessage.sender === "user") {
      return () => clearInactivityTimers();
    }

    if (reminderSentRef.current) {
      autoCloseTimerRef.current = window.setTimeout(() => {
        const latestTicket = ticketRef.current;
        const latestMessages = messagesRef.current;
        const latestLastMessage = latestMessages[latestMessages.length - 1];

        if (
          latestTicket.status !== "Open"
          || !latestLastMessage
          || latestLastMessage.sender === "user"
          || isAutoClosingRef.current
        ) {
          reminderSentRef.current = false;
          return;
        }

        isAutoClosingRef.current = true;
        clearInactivityTimers();

        const nextMessages = appendBotMessage(inactivityClosedText, true);
        updateTicket({
          chatHistory: nextMessages,
          status: "Closed",
          statusReason: inactivityClosingReason,
        });
        setInput("");
        setBookingOpen(false);
        toast.error("This chat was closed due to inactivity.");

        if (!latestTicket.id) {
          return;
        }

        void (async () => {
          try {
            const payload = await syncChatHistoryToServer(nextMessages, {
              status: "Closed",
              statusReason: inactivityClosingReason,
            });

            updateTicket({
              chatHistory: nextMessages,
              status: "Closed",
              statusReason: payload?.ticket?.statusReason || inactivityClosingReason,
              assignedTeam: payload?.ticket?.assignedTeam || latestTicket.assignedTeam,
              slaStatus: payload?.ticket?.slaStatus || latestTicket.slaStatus,
              createdAt: payload?.ticket?.createdAt || latestTicket.createdAt,
            });
          } catch {
            toast.error("We could not connect to the server to sync the automatic chat closure.");
          }
        })();
      }, inactivityAutoCloseDelayMs);

      return () => clearInactivityTimers();
    }

    reminderTimerRef.current = window.setTimeout(() => {
      const latestTicket = ticketRef.current;
      const latestMessages = messagesRef.current;
      const latestLastMessage = latestMessages[latestMessages.length - 1];

      if (
        latestTicket.status !== "Open"
        || !latestLastMessage
        || latestLastMessage.sender === "user"
        || reminderSentRef.current
      ) {
        return;
      }

      reminderSentRef.current = true;
      const nextMessages = appendBotMessage(buildInactivityReminderText(latestTicket.learnerName), true);

      // Persist timed system messages immediately so polling cannot wipe them out.
      void syncChatHistoryToServer(nextMessages, {
        status: latestTicket.status,
        statusReason: latestTicket.statusReason,
      }).then((payload) => {
        updateTicket({
          chatHistory: nextMessages,
          status: payload?.ticket?.status || latestTicket.status,
          statusReason: payload?.ticket?.statusReason || latestTicket.statusReason,
          assignedTeam: payload?.ticket?.assignedTeam || latestTicket.assignedTeam,
          slaStatus: payload?.ticket?.slaStatus || latestTicket.slaStatus,
          createdAt: payload?.ticket?.createdAt || latestTicket.createdAt,
        });
      }).catch(() => {
        // Keep the reminder visible locally; the auto-close fallback still runs on the learner side.
      });
    }, inactivityReminderDelayMs);

    return () => clearInactivityTimers();
  }, [messages, ticket.status]);

  const handleSend = async () => {
    const trimmedInput = input.trim();
    if (!trimmedInput || isSendingMessage) {
      inputRef.current?.focus();
      return;
    }

    if (ticket.status === "Closed") {
      toast.error("This chat is already closed.");
      return;
    }

    if (!ticket.id) {
      toast.error("This ticket is not ready for chatbot messaging yet.");
      return;
    }

    clearInactivityTimers();
    reminderSentRef.current = false;

    const userMessage: Omit<ChatMessage, "id" | "timestamp"> = {
      sender: "user",
      text: trimmedInput,
    };
    const nextMessages = [...messages, {
      ...userMessage,
      id: crypto.randomUUID(),
      timestamp: buildTimestamp(),
    }];

    replaceMessages(nextMessages);
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
            messages: nextMessages.map((message) => ({
              sender: message.sender,
              text: message.text,
              timestamp: message.timestamp,
            })),
          }),
        });

        const payload = (await response.json().catch(() => null)) as {
          message?: string;
          ticket?: {
            status?: "Open" | "Pending" | "Closed";
            statusReason?: string;
            assignedTeam?: string;
            slaStatus?: string;
            createdAt?: string;
          };
        } | null;

        if (!response.ok) {
          toast.error(payload?.message || "We could not send your message to the live support queue right now.");
          return;
        }

        updateTicket({
          chatHistory: nextMessages,
          status: payload?.ticket?.status || ticket.status,
          statusReason: payload?.ticket?.statusReason || ticket.statusReason,
          assignedTeam: payload?.ticket?.assignedTeam || ticket.assignedTeam,
          slaStatus: payload?.ticket?.slaStatus || ticket.slaStatus,
          createdAt: payload?.ticket?.createdAt || ticket.createdAt,
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
          messages: nextMessages.map((message) => ({
            sender: message.sender,
            text: message.text,
            timestamp: message.timestamp,
          })),
        }),
      });

      const payload = (await response.json().catch(() => null)) as {
        message?: string;
        reply?: string | null;
        webhookConfigured?: boolean;
        webhookDelivered?: boolean;
      } | null;

      if (!response.ok) {
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
      toast.error("We could not connect to the server. Please try again.");
    } finally {
      setIsSendingMessage(false);
      window.setTimeout(() => inputRef.current?.focus(), 0);
    }
  };

  const handleRequestLiveAgent = async () => {
    if (!ticket.id || ticket.status === "Closed" || ticket.liveChatRequested || isRequestingLiveAgent) {
      return;
    }

    clearInactivityTimers();
    reminderSentRef.current = false;
    setIsRequestingLiveAgent(true);

    try {
      const response = await fetch(`/api/tickets/${encodeURIComponent(ticket.id)}/live-chat-request`, {
        method: "POST",
      });

      const payload = (await response.json().catch(() => null)) as {
        message?: string;
        ticket?: {
          liveChatRequested?: boolean;
        };
      } | null;

      if (!response.ok) {
        toast.error(payload?.message || "We could not request a live support agent right now.");
        return;
      }

      const announcement = buildBotMessage(liveAgentRequestedMessage);
      const nextMessages = [...messagesRef.current, announcement];
      replaceMessages(nextMessages);

      await fetch(`/api/tickets/${encodeURIComponent(ticket.id)}/chat-history`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          status: ticket.status,
          statusReason: ticket.statusReason,
          messages: nextMessages.map((message) => ({
            sender: message.sender,
            text: message.text,
            timestamp: message.timestamp,
          })),
        }),
      }).catch(() => null);

      updateTicket({
        chatHistory: nextMessages,
        liveChatRequested: payload?.ticket?.liveChatRequested ?? true,
      });
      toast.success("Live support has been requested. Please stay connected.");
    } catch {
      toast.error("We could not connect to the server. Please try again.");
    } finally {
      setIsRequestingLiveAgent(false);
    }
  };

  const openOutlookBookings = async () => {
    if (ticket.status === "Closed") {
      toast.error("This chat is already closed.");
      return;
    }

    clearInactivityTimers();
    reminderSentRef.current = false;

    const bookingLink = "/api/booking-link";
    const bookingMessage = buildBotMessage("Opening the Kent Business College booking page for you now.");
    const nextMessages = [...messages, bookingMessage];

    if (!ticket.id) {
      replaceMessages(nextMessages);
      updateTicket({
        chatHistory: nextMessages,
        status: "Pending",
        statusReason: awaitingMeetingReason,
      });
      window.open(bookingLink, "_blank", "noopener,noreferrer");
      return;
    }

    try {
      const response = await fetch(`/api/tickets/${encodeURIComponent(ticket.id)}/chat-history`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          status: "Pending",
          statusReason: awaitingMeetingReason,
          messages: nextMessages,
        }),
      });

      const payload = (await response.json().catch(() => null)) as {
        message?: string;
        ticket?: {
          status?: string;
          statusReason?: string;
          assignedTeam?: string;
          slaStatus?: string;
          createdAt?: string;
        };
      } | null;

      if (!response.ok) {
        toast.error(payload?.message || "We could not update the ticket status for booking right now.");
        return;
      }

      replaceMessages(nextMessages);
      updateTicket({
        chatHistory: nextMessages,
        status: "Pending",
        statusReason: payload?.ticket?.statusReason || awaitingMeetingReason,
        assignedTeam: payload?.ticket?.assignedTeam || ticket.assignedTeam,
        slaStatus: payload?.ticket?.slaStatus || ticket.slaStatus,
        createdAt: payload?.ticket?.createdAt || ticket.createdAt,
      });
      window.open(bookingLink, "_blank", "noopener,noreferrer");
    } catch {
      toast.error("We could not connect to the server. Please try again.");
    }
  };

  const minBookingDate = formatDateInputValue(new Date());
  const bookingValidationMessage = getSupportSessionValidationMessage(bookingDate, bookingTime);

  const handleClose = async () => {
    clearInactivityTimers();
    reminderSentRef.current = false;
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
          messages: nextMessages,
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

    clearInactivityTimers();
    reminderSentRef.current = false;
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
      setBookingSuccess({
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
      updateTicket({
        status: (payload?.ticket?.status as typeof ticket.status | undefined) || "Pending",
        statusReason: payload?.ticket?.statusReason || awaitingMeetingReason,
        assignedTeam: payload?.ticket?.assignedTeam || ticket.assignedTeam,
      });
      setBookingDate("");
      setBookingTime("");
    } catch {
      toast.error("We could not connect to the server. Please try again.");
    } finally {
      setIsBooking(false);
    }
  };

  const handleStartNewChat = () => {
    clearInactivityTimers();
    reminderSentRef.current = false;
    isAutoClosingRef.current = false;

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
      assignedTeam: "Unassigned",
      slaStatus: "Pending Review",
      createdAt: "",
      liveChatRequested: false,
      chatHistory: [],
    });
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

  const isChatClosed = ticket.status === "Closed";
  const isInactivityClosed = ticket.statusReason === inactivityClosingReason;
  const closedPanelTitle = isInactivityClosed ? "Chat closed due to inactivity" : "Chat closed";

  return (
    <SupportLayout>
      <StepIndicator current={3} />
      <div className="max-w-5xl mx-auto">
        <div className="relative flex flex-col overflow-hidden border bg-card rounded-2xl shadow-card h-[calc(100vh-220px)] min-h-[560px]">
          <div className="flex items-center justify-between px-4 py-3.5 border-b md:px-6 bg-card">
            <div className="flex items-center gap-2">
              <div className="flex items-center justify-center w-8 h-8 rounded-lg gradient-primary">
                <Headphones className="w-4 h-4 text-primary-foreground" />
              </div>
              <div className="text-left">
                <div className="text-sm font-semibold">Kent Live Chat</div>
                {ticket.liveChatRequested ? (
                  <div className="text-xs font-medium text-success">Live agent requested</div>
                ) : null}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <StatusBadge status={ticket.status} />
              <Button variant="outline" size="sm" onClick={() => void handleClose()} disabled={isClosing || isChatClosed}>
                <X className="w-4 h-4 mr-1.5" /> Close
              </Button>
            </div>
          </div>

          <div className="relative flex-1 min-h-0">
            <div
              ref={scrollRef}
              className="h-full px-4 py-5 pr-20 space-y-4 overflow-y-auto sm:pr-24 md:px-6 md:pr-28 bg-gradient-to-b from-background to-card"
            >
              {messages.map((message) => (
                <MessageBubble key={message.id} m={message} />
              ))}

              {isSendingMessage && <TypingBubble />}
            </div>

            <SupportActionRail
              onBookingClick={openOutlookBookings}
              onLiveAgentClick={handleRequestLiveAgent}
              bookingDisabled={isChatClosed}
              liveAgentDisabled={isChatClosed || isRequestingLiveAgent || ticket.liveChatRequested}
              liveAgentRequested={ticket.liveChatRequested}
            />
          </div>

          <div className="p-3 border-t md:p-4 bg-card">
            {isChatClosed ? (
              <div className="rounded-2xl border bg-muted/30 px-4 py-4">
                <div className="text-sm font-semibold text-foreground">{closedPanelTitle}</div>
                <p className="mt-1 text-sm text-muted-foreground">
                  {closedChatDescription}
                </p>
                <div className="mt-4 flex flex-wrap justify-end gap-3">
                  <Button variant="outline" onClick={() => void handleDownloadTranscript()} disabled={isDownloadingTranscript}>
                    <Download className="h-4 w-4 mr-2" />
                    {isDownloadingTranscript ? "Preparing Transcript..." : "Download Transcript"}
                  </Button>
                  <Button onClick={handleStartNewChat} className="border-0 gradient-primary">
                    Start New Chat
                  </Button>
                </div>
              </div>
            ) : (
              <div className="flex items-end gap-2">
                <Button variant="ghost" size="icon" className="shrink-0" aria-label="Attach">
                  <Paperclip className="w-5 h-5" />
                </Button>
                <Input
                  ref={inputRef}
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={(event) => event.key === "Enter" && void handleSend()}
                  placeholder="Type your message..."
                  className="h-11"
                />
                <Button
                  onClick={() => void handleSend()}
                  className="h-11 border-0 shrink-0 gradient-primary"
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
              Choose a date and time that works for you. Sessions are available from 8:00 AM to 4:00 PM UK time, and they must be more than 24 hours away.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <label className="block mb-1.5 text-sm font-medium">Date</label>
              <Input
                type="date"
                min={minBookingDate}
                value={bookingDate}
                onChange={(event) => setBookingDate(event.target.value)}
              />
            </div>
            <div>
              <label className="block mb-1.5 text-sm font-medium">Time</label>
              <Input
                type="time"
                step="60"
                value={bookingTime}
                onChange={(event) => setBookingTime(event.target.value)}
              />
            </div>
            <p className={cn("text-xs", bookingValidationMessage ? "text-destructive" : "text-muted-foreground")}>
              {bookingValidationMessage || "Allowed meeting hours are 8:00 AM to 4:00 PM UK time, with more than 24 hours notice required."}
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

      <Dialog open={Boolean(bookingSuccess)} onOpenChange={(open) => !open && setBookingSuccess(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <div className="mx-auto mb-2 flex h-14 w-14 items-center justify-center rounded-full bg-success/10">
              <CheckCircle2 className="h-7 w-7 text-success" />
            </div>
            <DialogTitle className="text-center">
              {bookingSuccess?.reservationConfirmed ? "Teams Session Reserved" : "Support Session Request Submitted"}
            </DialogTitle>
            <DialogDescription className="text-center">
              {bookingSuccess?.reservationConfirmed
                ? "Your selected time has been reserved successfully in Microsoft Teams. Please keep this slot available, and use the link below if you would like to open the meeting details now."
                : "Thank you for booking a support session. Your request has been received successfully, and our team will review it and contact you using your registered details to confirm the session."}
            </DialogDescription>
          </DialogHeader>
          {bookingSuccess && (
            <div className="rounded-2xl border bg-muted/30 px-4 py-3">
              <div className="text-sm font-semibold text-foreground">Requested session</div>
              <div className="mt-1 text-sm text-muted-foreground">{bookingSuccess.dateLabel}</div>
              <div className="text-sm text-muted-foreground">{bookingSuccess.timeLabel}</div>
            </div>
          )}
          <DialogFooter>
            {bookingSuccess?.meetingJoinUrl && (
              <Button
                variant="outline"
                className="w-full"
                onClick={() => window.open(bookingSuccess.meetingJoinUrl || "", "_blank", "noopener,noreferrer")}
              >
                Open Teams Meeting
              </Button>
            )}
            <Button className="w-full border-0 gradient-primary" onClick={() => setBookingSuccess(null)}>
              Return to Chat
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
          {isUser ? "You" : isAgent ? "Live Agent" : "Help Bot"} - {m.timestamp}
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
  <div className="pointer-events-none absolute right-3 top-1/2 z-10 flex -translate-y-1/2 flex-col gap-2.5 sm:right-4">
    <SupportActionButton
      icon={CalendarClock}
      title="Book Session"
      desc="Open booking page"
      onClick={onBookingClick}
      disabled={bookingDisabled}
    />
    <SupportActionButton
      icon={Headphones}
      title={liveAgentRequested ? "Live Agent Requested" : "Live Agent"}
      desc={liveAgentRequested ? "Please stay connected" : "Request human support"}
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
      "group pointer-events-auto flex h-12 w-12 items-center gap-3 overflow-hidden rounded-full border border-border/80 bg-card/95 px-3 text-left shadow-lg backdrop-blur-sm transition-all duration-200 focus:w-60 focus:outline-none focus:ring-2 focus:ring-primary/20",
      active
        ? "w-60 border-success/30 bg-success/10 shadow-card"
        : disabled
          ? "cursor-default border-border/60 bg-muted/80"
          : "hover:w-60 hover:border-primary hover:bg-background hover:shadow-card focus:border-primary focus:bg-background",
    )}
  >
    <span
      className={cn(
        "flex h-6 w-6 shrink-0 items-center justify-center rounded-full",
        active
          ? "bg-success text-success-foreground"
          : disabled
            ? "bg-muted-foreground/20 text-muted-foreground"
            : "bg-primary text-primary-foreground",
      )}
    >
      <Icon className="h-3.5 w-3.5" />
    </span>
    <span className={cn(
      "min-w-0 max-w-0 overflow-hidden opacity-0 transition-all duration-200 group-hover:max-w-[11rem] group-hover:opacity-100 group-focus:max-w-[11rem] group-focus:opacity-100",
      active && "max-w-[11rem] opacity-100",
    )}>
      <span
        className={cn(
          "block text-sm font-semibold leading-tight whitespace-nowrap",
          active ? "text-success" : disabled ? "text-muted-foreground" : "text-foreground",
        )}
      >
        {title}
      </span>
      <span className={cn("mt-0.5 inline-flex items-center gap-1 text-xs whitespace-nowrap", active ? "text-success/80" : "text-muted-foreground")}>
        {desc}
        {!disabled && !active && <ArrowRight className="h-3 w-3 shrink-0 text-primary" />}
      </span>
    </span>
  </button>
);

export default ChatSupport;
