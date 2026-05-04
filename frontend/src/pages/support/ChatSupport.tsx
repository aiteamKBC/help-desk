import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowRight,
  Bot,
  CalendarClock,
  Check,
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
import { ChatMessage, useSupport } from "@/context/SupportContext";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

const egyptSupportTimeZone = "Africa/Cairo";
const ukSupportTimeZone = "Europe/London";
const egyptSupportSessionStartMinutes = 10 * 60;
const egyptSupportSessionEndMinutes = 18 * 60;
const ukSupportSessionStartMinutes = 8 * 60;
const ukSupportSessionEndMinutes = 18 * 60;
const supportSessionLeadTimeMs = 24 * 60 * 60 * 1000;

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
  const egyptMinutes = getTimeInTimeZoneMinutes(requestedDateTime, egyptSupportTimeZone);
  const ukMinutes = getTimeInTimeZoneMinutes(requestedDateTime, ukSupportTimeZone);

  return (
    isMinutesWithinRange(egyptMinutes, egyptSupportSessionStartMinutes, egyptSupportSessionEndMinutes)
    || isMinutesWithinRange(ukMinutes, ukSupportSessionStartMinutes, ukSupportSessionEndMinutes)
  );
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
    return "Support sessions must be between 10:00 AM and 6:00 PM Egypt time or between 8:00 AM and 6:00 PM UK time.";
  }

  return "";
}

const ChatSupport = () => {
  const navigate = useNavigate();
  const { ticket, updateTicket } = useSupport();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [bookingOpen, setBookingOpen] = useState(false);
  const [bookingDate, setBookingDate] = useState("");
  const [bookingTime, setBookingTime] = useState("");
  const [isClosing, setIsClosing] = useState(false);
  const [isBooking, setIsBooking] = useState(false);
  const [isSendingMessage, setIsSendingMessage] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ticket.email) {
      navigate("/support");
      return;
    }

    if (messages.length === 0) {
      const now = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      setMessages([
        {
          id: "m1",
          sender: "bot",
          text: ticket.category === "Technical" && ticket.technicalSubcategory
            ? `Hi! I'm your Help Desk assistant. I see you've raised a technical inquiry related to ${ticket.technicalSubcategory}.`
            : `Hi! I'm your Help Desk assistant. I see you've raised a ${ticket.category.toLowerCase()} inquiry.`,
          timestamp: now,
        },
        { id: "m2", sender: "user", text: ticket.inquiry, timestamp: now },
        {
          id: "m3",
          sender: "bot",
          text: "Thank you. Your support request has been created. A support agent will review your inquiry shortly.",
          timestamp: now,
        },
        {
          id: "m4",
          sender: "bot",
          text: "In the meantime, here are a few ways I can help you right now:",
          timestamp: now,
        },
      ]);
    }
    // eslint-disable-next-line
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const pushMsg = (message: Omit<ChatMessage, "id" | "timestamp">) => {
    const now = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    setMessages((prev) => [...prev, { ...message, id: crypto.randomUUID(), timestamp: now }]);
  };

  const handleSend = async () => {
    const trimmedInput = input.trim();
    if (!trimmedInput || isSendingMessage) return;

    if (!ticket.id) {
      toast.error("This ticket is not ready for chatbot messaging yet.");
      return;
    }

    const userMessage: Omit<ChatMessage, "id" | "timestamp"> = {
      sender: "user",
      text: trimmedInput,
    };
    const nextMessages = [...messages, {
      ...userMessage,
      id: crypto.randomUUID(),
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    }];

    setMessages(nextMessages);
    setInput("");
    setIsSendingMessage(true);

    try {
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
    }
  };

  const onLiveAgent = () => {
    pushMsg({ sender: "bot", text: "You are being connected to a live support agent." });
    setTimeout(() => {
      pushMsg({ sender: "agent", text: "Hello, I'm here to help. Could you please provide more details?" });
    }, 1200);
  };

  const userMessageCount = messages.filter((message) => message.sender === "user").length;
  const canShowSupportActions = userMessageCount >= 5;
  const minBookingDate = formatDateInputValue(new Date());
  const bookingValidationMessage = getSupportSessionValidationMessage(bookingDate, bookingTime);

  const handleClose = async () => {
    if (!ticket.id) {
      updateTicket({ chatHistory: messages, status: "Open" });
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
          status: "Open",
          messages,
        }),
      });

      const payload = (await response.json().catch(() => null)) as {
        message?: string;
        webhookConfigured?: boolean;
        webhookDelivered?: boolean;
      } | null;

      if (!response.ok) {
        toast.error(payload?.message || "We could not save the chat history right now.");
        return;
      }

      updateTicket({ chatHistory: messages, status: "Open" });
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
      } | null;

      if (!response.ok) {
        toast.error(payload?.message || "We could not save the support session request.");
        return;
      }

      setBookingOpen(false);
      pushMsg({
        sender: "bot",
        text: `Your support session request has been sent for ${bookingDate} at ${bookingTime}.`,
      });
      if (payload?.webhookConfigured === false) {
        toast.error("Booking saved, but the booking webhook is not configured on the server.");
      } else if (payload?.webhookDelivered === false) {
        toast.error("Booking saved, but the webhook notification could not be delivered.");
      } else {
        toast.success("Support session request saved and sent to the booking webhook.");
      }
      setBookingDate("");
      setBookingTime("");
    } catch {
      toast.error("We could not connect to the server. Please try again.");
    } finally {
      setIsBooking(false);
    }
  };

  return (
    <SupportLayout>
      <StepIndicator current={3} />
      <div className="max-w-5xl mx-auto">
        <div className="flex flex-col overflow-hidden border bg-card rounded-2xl shadow-card h-[calc(100vh-220px)] min-h-[560px]">
          <div className="flex items-center justify-between px-4 py-3.5 border-b md:px-6 bg-card">
            <div className="flex items-center gap-2">
              <div className="flex items-center justify-center w-8 h-8 rounded-lg gradient-primary">
                <Headphones className="w-4 h-4 text-primary-foreground" />
              </div>
              <div className="text-left">
                <div className="text-sm font-semibold">Help Desk Support</div>
                <div className="text-xs text-muted-foreground">Live assistance for your inquiry</div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <StatusBadge status="Open" />
              <Button variant="outline" size="sm" onClick={() => void handleClose()} disabled={isClosing}>
                <X className="w-4 h-4 mr-1.5" /> Close
              </Button>
            </div>
          </div>

          <div
            ref={scrollRef}
            className="flex-1 px-4 py-5 space-y-4 overflow-y-auto md:px-6 bg-gradient-to-b from-background to-card"
          >
            {messages.map((message) => (
              <MessageBubble key={message.id} m={message} />
            ))}

            {canShowSupportActions && (
              <div className="grid gap-3 pt-2 sm:grid-cols-2">
                <QuickCard icon={CalendarClock} title="Book a Support Session" desc="Schedule a call" onClick={() => setBookingOpen(true)} />
                <QuickCard icon={Headphones} title="Speak to Live Agent" desc="Talk to a human" onClick={onLiveAgent} />
              </div>
            )}
          </div>

          <div className="p-3 border-t md:p-4 bg-card">
            <div className="flex items-end gap-2">
              <Button variant="ghost" size="icon" className="shrink-0" aria-label="Attach">
                <Paperclip className="w-5 h-5" />
              </Button>
              <Input
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => event.key === "Enter" && void handleSend()}
                placeholder="Type your message..."
                className="h-11"
                disabled={isSendingMessage}
              />
              <Button onClick={() => void handleSend()} className="h-11 border-0 shrink-0 gradient-primary" disabled={isSendingMessage}>
                <Send className="w-4 h-4" />
              </Button>
            </div>
          </div>
        </div>
      </div>

      <Dialog open={bookingOpen} onOpenChange={setBookingOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Book a Support Session</DialogTitle>
            <DialogDescription>
              Choose a date and time that works for you. Sessions are available from 10:00 AM to 6:00 PM Egypt time or from 8:00 AM to 6:00 PM UK time, and they must be more than 24 hours away.
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
              {bookingValidationMessage || "Allowed meeting hours are 10:00 AM to 6:00 PM Egypt time or 8:00 AM to 6:00 PM UK time, with more than 24 hours notice required."}
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

const QuickCard = ({ icon: Icon, title, desc, onClick }: any) => (
  <button
    onClick={onClick}
    className="p-3.5 text-left transition-all border rounded-xl bg-card group hover:border-primary hover:shadow-card hover:-translate-y-0.5"
  >
    <div className="flex items-center justify-center w-8 h-8 mb-2 rounded-lg bg-primary/10 text-primary">
      <Icon className="w-4 h-4" />
    </div>
    <div className="text-sm font-medium">{title}</div>
    <div className="mt-0.5 text-xs text-muted-foreground">{desc}</div>
    <div className="inline-flex items-center gap-1 mt-2 text-xs text-primary transition-all group-hover:gap-2">
      Open <ArrowRight className="w-3 h-3" />
    </div>
  </button>
);

export default ChatSupport;
