import { type ComponentType, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ArrowRight, Bot, CalendarClock, Check, Headphones, Send, Ticket, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { KentCrestMark } from "@/components/support/KentCrestMark";
import { useSupport } from "@/context/useSupport";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

// ─── Types ────────────────────────────────────────────────────────────────────

interface LmsChatMessage {
  id: string;
  sender: "bot" | "user";
  text: string;
  timestamp: string;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function buildTimestamp() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function buildBotMsg(text: string): LmsChatMessage {
  return { id: crypto.randomUUID(), sender: "bot", text, timestamp: buildTimestamp() };
}

function buildUserMsg(text: string): LmsChatMessage {
  return { id: crypto.randomUUID(), sender: "user", text, timestamp: buildTimestamp() };
}

/** Decode the email from the unsigned half of the SSO token (payload.sig format). */
function decodeTokenEmail(token: string): string {
  try {
    const payloadB64 = token.split(".")[0];
    const json = atob(payloadB64.replace(/-/g, "+").replace(/_/g, "/"));
    const parsed = JSON.parse(json) as { email?: string };
    return parsed.email || "";
  } catch {
    return "";
  }
}

/** Convert LmsChatMessage[] to the `messages` format the backend expects. */
function serializeHistory(messages: LmsChatMessage[]) {
  return messages.map((m) => ({ sender: m.sender, text: m.text }));
}

// ─── Sub-components ───────────────────────────────────────────────────────────

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

const ChatBubble = ({ m }: { m: LmsChatMessage }) => {
  const isUser = m.sender === "user";
  return (
    <div className={cn("flex gap-2.5", isUser && "flex-row-reverse")}>
      <div
        className={cn(
          "h-8 w-8 rounded-full flex items-center justify-center shrink-0",
          isUser ? "bg-primary text-primary-foreground" : "bg-secondary text-foreground",
        )}
      >
        {isUser ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
      </div>
      <div className={cn("max-w-[80%]", isUser && "text-right")}>
        <div className="mb-1 text-xs text-muted-foreground">
          {isUser ? "You" : "Help Bot"} — {m.timestamp}
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

const ActionButton = ({
  icon: Icon,
  label,
  desc,
  onClick,
  disabled = false,
  active = false,
}: {
  icon: ComponentType<{ className?: string }>;
  label: string;
  desc: string;
  onClick: () => void;
  disabled?: boolean;
  active?: boolean;
}) => (
  <button
    type="button"
    onClick={disabled ? undefined : onClick}
    aria-label={`${label}. ${desc}`}
    aria-disabled={disabled}
    className={cn(
      "group/btn pointer-events-auto flex h-11 min-w-[152px] items-center gap-2.5 rounded-2xl border border-border/80 bg-card/95 px-3.5 text-left shadow-lg backdrop-blur-sm transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-primary/20 sm:h-12 sm:w-12 sm:min-w-0 sm:overflow-hidden sm:rounded-full sm:px-3 sm:transition-[width,box-shadow,border-color,background-color] sm:duration-1000 sm:hover:w-60 sm:focus:w-60",
      active
        ? "border-success/30 bg-success/10 sm:w-60"
        : disabled
          ? "cursor-default border-border/60 bg-muted/80"
          : "hover:-translate-y-0.5 hover:border-primary/70 hover:bg-background hover:shadow-card sm:focus:border-primary sm:focus:bg-background",
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
    <span className="min-w-0 flex-1 sm:max-w-0 sm:flex-none sm:overflow-hidden sm:opacity-0 sm:transition-[max-width,opacity] sm:duration-1000 sm:ease-out sm:group-hover/btn:max-w-[11rem] sm:group-hover/btn:opacity-100 sm:focus:max-w-[11rem] sm:focus:opacity-100">
      <span
        className={cn(
          "block text-[13px] font-semibold leading-tight whitespace-nowrap sm:text-sm",
          active ? "text-success" : disabled ? "text-muted-foreground" : "text-foreground",
        )}
      >
        {label}
      </span>
      <span className="mt-0.5 inline-flex items-center gap-1 text-[11px] whitespace-nowrap sm:text-xs text-muted-foreground">
        {desc}
        {!disabled && !active && <ArrowRight className="hidden h-3 w-3 shrink-0 text-primary sm:block" />}
      </span>
    </span>
  </button>
);

// ─── Main Page ─────────────────────────────────────────────────────────────────

const LmsChat = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { setTicket, updateTicket } = useSupport();

  const token = searchParams.get("token") || "";
  const emailFromToken = token ? decodeTokenEmail(token) : "";

  const [messages, setMessages] = useState<LmsChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isStarting, setIsStarting] = useState(true);
  const [canCreateTicket, setCanCreateTicket] = useState(false);
  const [ticketId, setTicketId] = useState<string | null>(null);
  const [isEscalating, setIsEscalating] = useState<"live" | "booking" | "ticket" | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const messagesRef = useRef<LmsChatMessage[]>([]);

  // Keep ref in sync for use inside callbacks
  useEffect(() => { messagesRef.current = messages; }, [messages]);

  // Auto-scroll on new messages
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, isLoading]);

  // ── Start: fetch greeting on mount ──
  useEffect(() => {
    let cancelled = false;

    const start = async () => {
      setIsStarting(true);
      try {
        const res = await fetch("/api/support/assistant", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "start", ...(token ? { token } : {}) }),
        });
        const data = (await res.json().catch(() => null)) as {
          ok?: boolean;
          reply?: string;
          canCreateTicket?: boolean;
        } | null;

        if (cancelled) return;

        if (!res.ok || !data?.reply) {
          setMessages([buildBotMsg("Hello! Welcome to Kent Business College Support. How can I help you today?")]);
          return;
        }

        setMessages([buildBotMsg(data.reply)]);
        setCanCreateTicket(Boolean(data.canCreateTicket));
      } catch {
        if (!cancelled) {
          setMessages([buildBotMsg("Hello! Welcome to Kent Business College Support. How can I help you today?")]);
        }
      } finally {
        if (!cancelled) setIsStarting(false);
      }
    };

    void start();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Call assistant and handle response ──
  const callAssistant = async (
    userMessage: string,
    opts: { silent?: boolean; escalateAction?: "live" | "booking" | "ticket" } = {},
  ): Promise<{ ticketCreated: boolean; ticketIdResult: string | null }> => {
    const history = serializeHistory(messagesRef.current);

    const body: Record<string, unknown> = {
      message: userMessage,
      messages: history,
      createTicket: "true",
    };
    if (token) body.token = token;

    const res = await fetch("/api/support/assistant", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = (await res.json().catch(() => null)) as {
      ok?: boolean;
      reply?: string;
      escalate?: boolean;
      assistantAction?: string;
      canCreateTicket?: boolean;
      ticket?: { id: string; status?: string };
      suggestedAction?: string;
      message?: string;
    } | null;

    if (!res.ok || !data) {
      throw new Error(data?.message || "Could not reach the support assistant.");
    }

    setCanCreateTicket(Boolean(data.canCreateTicket));

    // Store ticket in context if created/linked
    const newTicketId = data.ticket?.id || null;
    if (newTicketId && newTicketId !== ticketId) {
      setTicketId(newTicketId);
      // Sync into SupportContext so booking/options pages work
      setTicket({
        id: newTicketId,
        learnerName: "",
        email: emailFromToken,
        requesterRole: "user",
        requesterSource: "lms_learners",
        category: "Technical",
        technicalSubcategory: "LMS",
        subject: "",
        aiTeamPersonName: "",
        aiTeamPersonEmail: "",
        coverageSessions: [],
        submittedForLearner: null,
        notifySubmittedForLearner: false,
        inquiry: userMessage,
        evidence: [],
        status: (data.ticket?.status as "Open" | "Pending" | "Closed" | undefined) || "Open",
        statusReason: "",
        assignedAgentId: null,
        assignedTeam: "Unassigned",
        slaStatus: "Pending Review",
        createdAt: new Date().toISOString(),
        chatState: "open",
        liveChatRequested: false,
        chatHistory: [],
      });
    } else if (ticketId) {
      // Update status if ticket already existed
      if (data.ticket?.status) {
        updateTicket({ status: data.ticket.status as "Open" | "Pending" | "Closed" });
      }
    }

    if (!opts.silent && data.reply) {
      setMessages((prev) => [...prev, buildBotMsg(data.reply!)]);
    }

    return { ticketCreated: Boolean(newTicketId), ticketIdResult: newTicketId || ticketId };
  };

  // ── Send user message ──
  const handleSend = async () => {
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;

    const userMsg = buildUserMsg(trimmed);
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsLoading(true);

    try {
      await callAssistant(trimmed);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "We could not connect. Please try again.");
    } finally {
      setIsLoading(false);
      window.setTimeout(() => inputRef.current?.focus(), 0);
    }
  };

  // ── Action: Live Agent ──
  const handleLiveAgent = async () => {
    if (isEscalating) return;
    setIsEscalating("live");

    const currentTicketId = ticketId;

    try {
      if (currentTicketId) {
        // Ticket already exists — go straight to options
        navigate("/support/options");
        return;
      }

      // No ticket yet — send escalation message to create one
      const userMsg = buildUserMsg("I need to speak with a live support agent.");
      setMessages((prev) => [...prev, userMsg]);
      setIsLoading(true);

      const { ticketIdResult } = await callAssistant("I need to speak with a live support agent.");
      setIsLoading(false);

      if (ticketIdResult) {
        navigate("/support/options");
      } else {
        toast.error("Could not open a support ticket. Please try again.");
      }
    } catch (err) {
      setIsLoading(false);
      toast.error(err instanceof Error ? err.message : "Could not reach the support team right now.");
    } finally {
      setIsEscalating(null);
    }
  };

  // ── Action: Book Session ──
  const handleBookSession = async () => {
    if (isEscalating) return;
    setIsEscalating("booking");

    const currentTicketId = ticketId;

    try {
      if (currentTicketId) {
        navigate("/support/booking", { state: { returnPath: "/lms" } });
        return;
      }

      const userMsg = buildUserMsg("I'd like to book a support session.");
      setMessages((prev) => [...prev, userMsg]);
      setIsLoading(true);

      const { ticketIdResult } = await callAssistant("I'd like to book a support session.");
      setIsLoading(false);

      if (ticketIdResult) {
        navigate("/support/booking", { state: { returnPath: "/lms" } });
      } else {
        toast.error("Could not open a support ticket for booking. Please try again.");
      }
    } catch (err) {
      setIsLoading(false);
      toast.error(err instanceof Error ? err.message : "Could not reach the support team right now.");
    } finally {
      setIsEscalating(null);
    }
  };

  // ── Action: Submit Ticket ──
  const handleSubmitTicket = async () => {
    if (isEscalating) return;
    setIsEscalating("ticket");

    const currentTicketId = ticketId;

    try {
      if (currentTicketId) {
        navigate("/support/status");
        return;
      }

      const userMsg = buildUserMsg("Please submit a support ticket for my inquiry.");
      setMessages((prev) => [...prev, userMsg]);
      setIsLoading(true);

      const { ticketIdResult } = await callAssistant("Please submit a support ticket for my inquiry.");
      setIsLoading(false);

      if (ticketIdResult) {
        toast.success("Your support ticket has been submitted. Our team will follow up shortly.");
        navigate("/support/status");
      } else if (!canCreateTicket) {
        toast.error("A ticket cannot be created without a verified learner account. Please open support from your KBC learner portal.");
      } else {
        toast.error("Could not submit the ticket right now. Please try again.");
      }
    } catch (err) {
      setIsLoading(false);
      toast.error(err instanceof Error ? err.message : "Could not reach the support team right now.");
    } finally {
      setIsEscalating(null);
    }
  };

  const anyEscalating = isEscalating !== null;

  return (
    <div className="min-h-screen gradient-soft flex flex-col">
      {/* Header */}
      <header className="sticky top-0 z-30 border-b border-black/5 bg-white">
        <div className="mx-auto flex min-h-[78px] w-full max-w-7xl items-center gap-3 px-4 sm:min-h-[84px] sm:px-6 lg:px-8">
          <div className="shrink-0 rounded-xl">
            <KentCrestMark
              variant="full"
              frame="plain"
              className="h-11 w-[176px] sm:h-12 sm:w-[210px]"
              imageClassName="object-left"
            />
          </div>

          {/* Learner identity badge */}
          {emailFromToken ? (
            <div className="ml-auto flex items-center gap-2 rounded-full border border-primary/12 bg-primary/5 px-3 py-1.5">
              <div className="h-2 w-2 rounded-full bg-success" />
              <span className="max-w-[160px] truncate text-xs font-medium text-foreground sm:max-w-none">
                {emailFromToken}
              </span>
            </div>
          ) : null}
        </div>
      </header>

      {/* Main */}
      <main className="flex flex-1 flex-col container py-6 md:py-8">
        <div className="mx-auto w-full max-w-4xl flex flex-1 flex-col min-h-0">

          {/* Intro label */}
          <div className="mb-4 text-center">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-primary/15 bg-primary/5 px-3 py-1 text-xs font-medium text-primary">
              <Bot className="h-3 w-3" />
              KBC Support Assistant — LMS
            </span>
          </div>

          {/* Chat window */}
          <div className="relative flex flex-col overflow-hidden rounded-2xl border border-primary/10 bg-card shadow-[0_12px_30px_-18px_hsl(var(--primary)/0.35),0_6px_16px_-10px_hsl(var(--primary)/0.18)] flex-1 min-h-[420px] max-h-[640px] sm:max-h-[700px]">

            {/* Chat header */}
            <div className="relative z-10 shrink-0 flex items-center gap-2 border-b border-primary/10 bg-gradient-to-r from-primary/[0.05] via-card to-card px-4 py-3.5 shadow-[0_10px_22px_-18px_hsl(var(--primary)/0.4)] md:px-6">
              <div className="flex items-center justify-center w-8 h-8 rounded-lg gradient-primary">
                <Headphones className="w-4 h-4 text-primary-foreground" />
              </div>
              <div>
                <div className="text-sm font-semibold">Kent Support Bot</div>
                <div className="text-xs text-muted-foreground">
                  {isStarting ? "Connecting…" : "Ready to help"}
                </div>
              </div>
              {ticketId ? (
                <div className="ml-auto flex items-center gap-1.5 rounded-full border border-primary/15 bg-primary/5 px-2.5 py-1 text-[11px] font-medium text-primary">
                  <Check className="h-3 w-3" />
                  Ticket {ticketId}
                </div>
              ) : null}
            </div>

            {/* Messages area */}
            <div className="relative flex min-h-0 flex-1 flex-col">
              <div
                ref={scrollRef}
                className="min-h-0 flex-1 space-y-4 overflow-y-auto bg-gradient-to-b from-background to-card px-3 py-4 pr-16 sm:px-4 sm:py-5 sm:pr-20 md:px-6 md:pr-24"
              >
                {isStarting ? (
                  <TypingBubble />
                ) : (
                  messages.map((m) => <ChatBubble key={m.id} m={m} />)
                )}
                {!isStarting && isLoading ? <TypingBubble /> : null}
              </div>

              {/* Action rail (right side) */}
              <div className="group/rail pointer-events-none absolute bottom-4 right-3 z-10 flex flex-col items-end gap-2.5 sm:bottom-auto sm:right-4 sm:top-1/2 sm:-translate-y-1/2">
                <ActionButton
                  icon={Headphones}
                  label="Live Agent"
                  desc="Connect with support"
                  onClick={() => void handleLiveAgent()}
                  disabled={anyEscalating}
                  active={isEscalating === "live"}
                />
                <ActionButton
                  icon={CalendarClock}
                  label="Book Session"
                  desc="Schedule a meeting"
                  onClick={() => void handleBookSession()}
                  disabled={anyEscalating}
                  active={isEscalating === "booking"}
                />
                <ActionButton
                  icon={Ticket}
                  label="Submit Ticket"
                  desc="Create a support ticket"
                  onClick={() => void handleSubmitTicket()}
                  disabled={anyEscalating}
                  active={isEscalating === "ticket"}
                />
              </div>
            </div>

            {/* Input bar */}
            <div className="shrink-0 border-t bg-card p-3 md:p-4">
              <div className="flex items-end gap-2">
                <Input
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && void handleSend()}
                  placeholder="Type your message…"
                  className="h-11 flex-1"
                  disabled={isLoading || isStarting}
                />
                <Button
                  onClick={() => void handleSend()}
                  className="h-11 w-11 shrink-0 border-0 gradient-primary"
                  disabled={isLoading || isStarting || !input.trim()}
                  aria-label="Send message"
                >
                  <Send className="w-4 h-4" />
                </Button>
              </div>
              <p className="mt-2 text-center text-[11px] text-muted-foreground">
                Use the buttons on the right to connect with a live agent, book a session, or submit a ticket directly.
              </p>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};

export default LmsChat;
