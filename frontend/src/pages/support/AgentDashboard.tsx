import { useEffect, useRef, useState, type ChangeEvent, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Bot,
  AlertOctagon,
  ArrowLeft,
  CheckCircle2,
  Clock,
  Eye,
  FileText,
  Hash,
  Headphones,
  ImagePlus,
  LoaderCircle,
  LogOut,
  Mail,
  MessageSquareText,
  Phone,
  RefreshCw,
  Search,
  Save,
  SendHorizontal,
  Ticket as TicketIcon,
  UserRound,
  X,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { SupportLayout } from "@/components/support/SupportLayout";
import { StatusBadge } from "@/components/support/StatusBadge";
import { clearAdminSession, getAdminSession } from "@/lib/adminSession";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

interface AdminAgent {
  id: number;
  username: string;
  fullName: string;
  email: string | null;
  role: string;
}

interface TicketSummary {
  id: string;
  learnerName: string;
  email: string;
  learnerPhone: string;
  category: string;
  technicalSubcategory: string;
  inquiryPreview: string;
  status: "Open" | "Pending" | "Closed";
  statusReason: string;
  assignedAgentId: number | null;
  assignedAgentName: string;
  assignedAgentUsername: string;
  assignedTeam: string;
  chatId: string;
  chatIsActive: boolean;
  liveChatRequested: boolean;
  chatState: string;
  lastMessageAt: string | null;
  slaStatus: "Pending Review" | "On Track" | "Breached";
  slaAttentionRequired?: boolean;
  evidenceCount: number;
  createdAt: string;
  updatedAt: string;
}

interface TicketDetail extends TicketSummary {
  inquiry: string;
  priority: string;
  closedAt: string | null;
  documentation: AdminDocumentation;
}

interface ChatHistoryItem {
  id: string | number;
  role: string;
  senderLabel: string;
  text: string;
  createdAt: string;
}

interface AttachmentItem {
  id: number;
  name: string;
  mimeType: string | null;
  size: number;
  storageUrl: string | null;
  metadata: Record<string, unknown>;
  createdAt: string;
}

interface HistoryItem {
  id: number;
  eventType: string;
  actorType: string;
  actorLabel: string | null;
  payload: Record<string, unknown>;
  createdAt: string;
}

interface SessionRequestItem {
  id: number;
  requestedDate: string;
  requestedTime: string;
  status: string;
  createdBy: string;
  notes: string | null;
  metadata: Record<string, unknown>;
  createdAt: string;
}

interface DocumentationImage {
  name: string;
  mimeType: string;
  size: number;
  dataUrl: string;
}

interface AdminDocumentation {
  inquiry: string;
  symptoms: string;
  errors: string;
  steps: string;
  resources: string;
  chatId: string;
  ticketId: string;
  ticketStatus?: string;
  statusReason?: string;
  issuesAddressed?: string;
  errorImages: DocumentationImage[];
}

interface AiConsoleMessage {
  id: string;
  role: "assistant" | "user" | "system";
  text: string;
  createdAt: string;
}

interface TicketDetailResponse {
  ticket: TicketDetail;
  chatHistory: ChatHistoryItem[];
  attachments: AttachmentItem[];
  history: HistoryItem[];
  sessionRequests: SessionRequestItem[];
}

interface ListResponse {
  message?: string;
  tickets?: TicketSummary[];
  agents?: AdminAgent[];
}

interface DetailResponse extends TicketDetailResponse {
  message?: string;
}

interface MigrationStatusResponse {
  chatbotWebhookConfigured?: boolean;
}

interface AdminAiMessageResponse {
  message?: string;
  ok?: boolean;
  reply?: string;
  webhookConfigured?: boolean;
  webhookDelivered?: boolean;
}

const statuses: TicketSummary["status"][] = ["Open", "Pending", "Closed"];
const slaStatuses: TicketSummary["slaStatus"][] = ["Pending Review", "On Track", "Breached"];
const autoManagedSlaStatuses = new Set<TicketSummary["status"]>(["Open", "Pending", "Closed"]);
const adminConsoleStatuses = ["Available", "Busy", "Off"] as const;
const consolePollIntervalMs = 2500;
const documentationWorkflowStatuses = ["Closed", "Pending"] as const;
const documentationStatusReasons = {
  Closed: ["Closed due to inactivity", "Closed via Chatbot", "Closed via Agent"],
  Pending: ["Awaiting support meeting", "Escalation", "Awaiting Resolution"],
} as const;
type AdminConsoleStatus = (typeof adminConsoleStatuses)[number];
type DocumentationWorkflowStatus = (typeof documentationWorkflowStatuses)[number];
type DocumentationIssuesAddressed = "yes" | "no" | "";

const AgentDashboard = () => {
  const navigate = useNavigate();
  const session = getAdminSession();
  const [tickets, setTickets] = useState<TicketSummary[]>([]);
  const [agents, setAgents] = useState<AdminAgent[]>([]);
  const [adminView, setAdminView] = useState<"dashboard" | "console">("dashboard");
  const [activeTicketId, setActiveTicketId] = useState("");
  const [activeDetail, setActiveDetail] = useState<TicketDetailResponse | null>(null);
  const [consoleQueueTab, setConsoleQueueTab] = useState<"open" | "closed">("open");
  const [consoleSearch, setConsoleSearch] = useState("");
  const [consoleStatus, setConsoleStatus] = useState<AdminConsoleStatus>("Available");
  const [consoleTicketId, setConsoleTicketId] = useState("");
  const [consoleDetail, setConsoleDetail] = useState<TicketDetailResponse | null>(null);
  const [consoleChatInput, setConsoleChatInput] = useState("");
  const [consoleAiInput, setConsoleAiInput] = useState("");
  const [documentationDraft, setDocumentationDraft] = useState<AdminDocumentation | null>(null);
  const [documentationStep, setDocumentationStep] = useState(1);
  const [documentationTicketStatus, setDocumentationTicketStatus] = useState<DocumentationWorkflowStatus | "">("");
  const [documentationStatusReason, setDocumentationStatusReason] = useState("");
  const [documentationIssuesAddressed, setDocumentationIssuesAddressed] = useState<DocumentationIssuesAddressed>("");
  const [aiThreads, setAiThreads] = useState<Record<string, AiConsoleMessage[]>>({});
  const [draftStatus, setDraftStatus] = useState<TicketSummary["status"]>("Open");
  const [draftAgentId, setDraftAgentId] = useState("unassigned");
  const [draftSlaStatus, setDraftSlaStatus] = useState<TicketSummary["slaStatus"]>("Pending Review");
  const [notes, setNotes] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isOpening, setIsOpening] = useState(false);
  const [isConsoleOpening, setIsConsoleOpening] = useState(false);
  const [isSendingConsoleChat, setIsSendingConsoleChat] = useState(false);
  const [isSendingAiMessage, setIsSendingAiMessage] = useState(false);
  const [isSavingDocumentation, setIsSavingDocumentation] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState("");
  const [chatbotWorkflowConfigured, setChatbotWorkflowConfigured] = useState(false);
  const trimmedNotes = notes.trim();
  const isSlaAutoManaged = Boolean(activeDetail) && autoManagedSlaStatuses.has(draftStatus);
  const effectiveDraftSlaStatus = activeDetail
    ? deriveDashboardSlaStatus(draftStatus, activeDetail.ticket.createdAt, draftSlaStatus)
    : draftSlaStatus;
  const isStatusChanging = Boolean(activeDetail) && draftStatus !== activeDetail.ticket.status;
  const canSubmitStatusChange = !isStatusChanging || Boolean(trimmedNotes);
  const normalizedConsoleSearch = consoleSearch.trim().toLowerCase();
  const consoleQueueTickets = dedupeConsoleQueueTickets(tickets.filter((ticket) => ticket.chatIsActive)).filter((ticket) => (
    consoleQueueTab === "open"
      ? ticket.chatState !== "closed"
      : ticket.chatState === "closed"
  ));
  const filteredConsoleTickets = consoleQueueTickets.filter((ticket) => {
    if (!normalizedConsoleSearch) {
      return true;
    }

    const searchTarget = [
      ticket.id,
      ticket.chatId,
      ticket.learnerName,
      ticket.email,
      ticket.category,
      ticket.technicalSubcategory,
      ticket.inquiryPreview,
    ]
      .join(" ")
      .toLowerCase();

    return searchTarget.includes(normalizedConsoleSearch);
  });
  const hasConsoleQueue = filteredConsoleTickets.length > 0;
  const liveChatLocked = Boolean(consoleDetail) && (
    consoleDetail.ticket.status === "Closed" || consoleDetail.ticket.chatState === "closed"
  );
  const adminCanReplyToLiveChat = Boolean(consoleDetail?.ticket.liveChatRequested) && !liveChatLocked;
  const activeAiThread = consoleDetail ? (aiThreads[consoleDetail.ticket.id] || []) : [];
  const documentationStatusReasonsForSelection = documentationTicketStatus ? [...documentationStatusReasons[documentationTicketStatus]] : [];
  const documentationPageOneDirty = Boolean(consoleDetail && documentationDraft)
    && JSON.stringify(documentationDraft) !== JSON.stringify(normalizeDocumentationDraft(consoleDetail.ticket.documentation));
  const documentationPageTwoDirty = Boolean(consoleDetail) && (
    documentationTicketStatus !== deriveDocumentationTicketStatus(consoleDetail.ticket.status)
    || documentationStatusReason !== (consoleDetail.ticket.statusReason || "")
  );
  const documentationPageThreeDirty = Boolean(consoleDetail) && (
    documentationIssuesAddressed !== deriveDocumentationIssuesAddressed(consoleDetail.ticket.chatState)
  );
  const documentationWorkflowDirty = documentationPageOneDirty || documentationPageTwoDirty || documentationPageThreeDirty;
  const canMoveDocumentationForward = (
    documentationStep === 1
      ? true
      : documentationStep === 2
        ? Boolean(documentationTicketStatus && documentationStatusReason)
        : Boolean(documentationIssuesAddressed)
  );

  useEffect(() => {
    void loadDashboard();
  }, []);

  useEffect(() => {
    if (adminView !== "console") {
      return;
    }

    if (filteredConsoleTickets.length === 0) {
      if (consoleTicketId) {
        setConsoleTicketId("");
        setConsoleDetail(null);
      }
      return;
    }

    if (!filteredConsoleTickets.some((ticket) => ticket.id === consoleTicketId)) {
      setConsoleTicketId("");
      setConsoleDetail(null);
    }
  }, [adminView, consoleQueueTab, consoleSearch, tickets]);

  useEffect(() => {
    if (!consoleDetail) {
      setDocumentationDraft(null);
      setDocumentationStep(1);
      setDocumentationTicketStatus("");
      setDocumentationStatusReason("");
      setDocumentationIssuesAddressed("");
      setConsoleChatInput("");
      setConsoleAiInput("");
      return;
    }

    setDocumentationDraft(normalizeDocumentationDraft(consoleDetail.ticket.documentation));
    setDocumentationStep(1);
    setDocumentationTicketStatus(deriveDocumentationTicketStatus(consoleDetail.ticket.status));
    setDocumentationStatusReason(consoleDetail.ticket.statusReason || "");
    setDocumentationIssuesAddressed(deriveDocumentationIssuesAddressed(consoleDetail.ticket.chatState));
    setConsoleChatInput("");
    setConsoleAiInput("");
    setAiThreads((currentThreads) => {
      if (currentThreads[consoleDetail.ticket.id]) {
        return currentThreads;
      }

      return {
        ...currentThreads,
        [consoleDetail.ticket.id]: [buildInitialAiMessage(consoleDetail.ticket, chatbotWorkflowConfigured)],
      };
    });
  }, [consoleDetail?.ticket.id, chatbotWorkflowConfigured]);

  useEffect(() => {
    if (adminView !== "console") {
      return;
    }

    const intervalId = window.setInterval(() => {
      void refreshTicketsOnly(true);

      if (consoleTicketId && !isConsoleOpening && !isSendingConsoleChat) {
        void refreshConsoleTicketDetail(consoleTicketId);
      }
    }, consolePollIntervalMs);

    return () => window.clearInterval(intervalId);
  }, [adminView, consoleTicketId, isConsoleOpening, isSendingConsoleChat]);

  useEffect(() => {
    if (!documentationTicketStatus) {
      if (documentationStatusReason) {
        setDocumentationStatusReason("");
      }
      return;
    }

    const allowedReasons = documentationStatusReasons[documentationTicketStatus] as readonly string[];
    if (!allowedReasons.includes(documentationStatusReason)) {
      setDocumentationStatusReason("");
    }
  }, [documentationTicketStatus]);

  const kpis = [
    {
      label: "Open Tickets",
      value: tickets.filter((ticket) => ticket.status === "Open").length,
      icon: TicketIcon,
      color: "text-info bg-info/10",
    },
    {
      label: "Pending Tickets",
      value: tickets.filter((ticket) => ticket.status === "Pending").length,
      icon: Clock,
      color: "text-warning bg-warning/10",
    },
    {
      label: "Closed Tickets",
      value: tickets.filter((ticket) => ticket.status === "Closed").length,
      icon: CheckCircle2,
      color: "text-success bg-success/10",
    },
    {
      label: "SLA Breaches",
      value: tickets.filter((ticket) => ticket.slaStatus === "Breached").length,
      icon: AlertOctagon,
      color: "text-destructive bg-destructive/10",
    },
  ];

  async function fetchTicketsList() {
    const response = await fetch("/api/admin/tickets");
    const payload = (await response.json().catch(() => null)) as ListResponse | null;

    if (!response.ok) {
      throw new Error(payload?.message || "We could not load tickets right now.");
    }

    return payload?.tickets || [];
  }

  async function loadDashboard() {
    setIsLoading(true);
    setError("");

    try {
      const [tickets, agentsResponse, migrationStatusResponse] = await Promise.all([
        fetchTicketsList(),
        fetch("/api/admin/agents"),
        fetch("/api/migration-status"),
      ]);

      const agentsPayload = (await agentsResponse.json().catch(() => null)) as ListResponse | null;
      const migrationStatusPayload = (await migrationStatusResponse.json().catch(() => null)) as MigrationStatusResponse | null;

      if (!agentsResponse.ok) {
        throw new Error(agentsPayload?.message || "We could not load agents right now.");
      }

      setTickets(tickets);
      setAgents(agentsPayload?.agents || []);
      setChatbotWorkflowConfigured(Boolean(migrationStatusPayload?.chatbotWebhookConfigured));
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : "We could not load the dashboard right now.");
    } finally {
      setIsLoading(false);
    }
  }

  async function refreshTicketsOnly(silent = false) {
    try {
      const nextTickets = await fetchTicketsList();
      setTickets(nextTickets);
    } catch (fetchError) {
      if (!silent) {
        setError(fetchError instanceof Error ? fetchError.message : "We could not load tickets right now.");
      }
    }
  }

  async function fetchTicketDetail(ticketId: string) {
    const response = await fetch(`/api/admin/tickets/${encodeURIComponent(ticketId)}`);
    const payload = (await response.json().catch(() => null)) as DetailResponse | null;

    if (!response.ok || !payload?.ticket) {
      throw new Error(payload?.message || "We could not load this ticket right now.");
    }

    return payload;
  }

  async function openTicket(ticketId: string) {
    setActiveTicketId(ticketId);
    setActiveDetail(null);
    setNotes("");
    setIsOpening(true);

    try {
      const payload = await fetchTicketDetail(ticketId);
      setActiveDetail(payload);
      syncDrafts(payload);
    } catch (fetchError) {
      closePanel();
      toast.error(fetchError instanceof Error ? fetchError.message : "We could not connect to the server. Please try again.");
    } finally {
      setIsOpening(false);
    }
  }

  async function assignTicketToSignedInAdmin(ticketId: string) {
    if (!session?.id || !session.username) {
      return null;
    }

    const response = await fetch(`/api/admin/tickets/${encodeURIComponent(ticketId)}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        assignedAgentId: session.id,
        actorUsername: session.username,
      }),
    });

    const payload = (await response.json().catch(() => null)) as DetailResponse | null;

    if (!response.ok || !payload?.ticket) {
      throw new Error(payload?.message || "We could not assign this chat right now.");
    }

    setTickets((currentTickets) => currentTickets.map((ticket) => (
      ticket.id === payload.ticket.id ? payload.ticket : ticket
    )));

    return payload;
  }

  async function openConsoleChat(ticketId: string) {
    if (consoleTicketId === ticketId && consoleDetail?.ticket.id === ticketId) {
      setConsoleTicketId("");
      setConsoleDetail(null);
      return;
    }

    setConsoleTicketId(ticketId);
    setConsoleDetail(null);
    setIsConsoleOpening(true);

    try {
      let payload = await fetchTicketDetail(ticketId);

      if (session?.id && payload.ticket.assignedAgentId !== session.id) {
        payload = await assignTicketToSignedInAdmin(ticketId) || payload;
      }

      setConsoleDetail(payload);
      setTickets((currentTickets) => currentTickets.map((ticket) => (
        ticket.id === payload.ticket.id ? payload.ticket : ticket
      )));
    } catch (fetchError) {
      setConsoleTicketId("");
      setConsoleDetail(null);
      toast.error(fetchError instanceof Error ? fetchError.message : "We could not open this chat right now.");
    } finally {
      setIsConsoleOpening(false);
    }
  }

  async function refreshConsoleTicketDetail(ticketId: string) {
    try {
      const payload = await fetchTicketDetail(ticketId);
      syncDetailAcrossViews(payload);
    } catch {
      // Keep the current view stable; the next successful poll will recover automatically.
    }
  }

  function syncDetailAcrossViews(detail: TicketDetailResponse) {
    setTickets((currentTickets) => currentTickets.map((ticket) => (
      ticket.id === detail.ticket.id ? detail.ticket : ticket
    )));
    setConsoleDetail((currentDetail) => (
      currentDetail?.ticket.id === detail.ticket.id ? detail : currentDetail
    ));
    setActiveDetail((currentDetail) => (
      currentDetail?.ticket.id === detail.ticket.id ? detail : currentDetail
    ));
  }

  function updateDocumentationField(field: keyof AdminDocumentation, value: string) {
    setDocumentationDraft((currentDraft) => {
      if (!currentDraft) {
        return currentDraft;
      }

      return {
        ...currentDraft,
        [field]: value,
      };
    });
  }

  async function handleDocumentationImagesAdded(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files || []);
    event.target.value = "";

    if (files.length === 0) {
      return;
    }

    const nonImageCount = files.filter((file) => !file.type.startsWith("image/")).length;
    if (nonImageCount > 0) {
      toast.error("Only image attachments are allowed in the Errors section.");
    }

    const imageFiles = files.filter((file) => file.type.startsWith("image/"));
    if (imageFiles.length === 0) {
      return;
    }

    try {
      const nextImages = await Promise.all(imageFiles.map(readImageFileAsDocumentationImage));
      setDocumentationDraft((currentDraft) => {
        if (!currentDraft) {
          return currentDraft;
        }

        return {
          ...currentDraft,
          errorImages: [...currentDraft.errorImages, ...nextImages],
        };
      });
    } catch {
      toast.error("We could not read one or more images right now.");
    }
  }

  function removeDocumentationImage(index: number) {
    setDocumentationDraft((currentDraft) => {
      if (!currentDraft) {
        return currentDraft;
      }

      return {
        ...currentDraft,
        errorImages: currentDraft.errorImages.filter((_, imageIndex) => imageIndex !== index),
      };
    });
  }

  async function saveDocumentation() {
    if (!consoleDetail || !documentationDraft) {
      return;
    }

    setIsSavingDocumentation(true);

    try {
      const response = await fetch(`/api/admin/tickets/${encodeURIComponent(consoleDetail.ticket.id)}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          documentation: documentationDraft,
          actorUsername: session?.username || "admin",
        }),
      });

      const payload = (await response.json().catch(() => null)) as DetailResponse | null;

      if (!response.ok || !payload?.ticket) {
        toast.error(payload?.message || "We could not save the documentation right now.");
        return;
      }

      syncDetailAcrossViews(payload);
      setDocumentationDraft(normalizeDocumentationDraft(payload.ticket.documentation));
      toast.success("Documentation saved.");
    } catch {
      toast.error("We could not connect to the server. Please try again.");
    } finally {
      setIsSavingDocumentation(false);
    }
  }

  async function runDocumentationWorkflow(options?: { createFollowUpTicket?: boolean }) {
    if (
      !consoleDetail
      || !documentationDraft
      || !documentationTicketStatus
      || !documentationStatusReason
      || !documentationIssuesAddressed
    ) {
      return;
    }

    setIsSavingDocumentation(true);

    try {
      const workflowDocumentation: AdminDocumentation = {
        ...documentationDraft,
        ticketStatus: documentationTicketStatus,
        statusReason: documentationStatusReason,
        issuesAddressed: documentationIssuesAddressed,
      };
      const workflowNote = buildDocumentationWorkflowNote(
        consoleDetail.ticket,
        documentationTicketStatus,
        documentationStatusReason,
        documentationIssuesAddressed,
      );

      const response = await fetch(`/api/admin/tickets/${encodeURIComponent(consoleDetail.ticket.id)}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          status: documentationTicketStatus,
          statusReason: documentationStatusReason,
          chatState: documentationIssuesAddressed === "yes" ? "closed" : "open",
          documentation: workflowDocumentation,
          note: workflowNote,
          actorUsername: session?.username || "admin",
        }),
      });

      const payload = (await response.json().catch(() => null)) as DetailResponse | null;

      if (!response.ok || !payload?.ticket) {
        toast.error(payload?.message || "We could not save the documentation workflow right now.");
        return;
      }

      syncDetailAcrossViews(payload);
      setDocumentationDraft(normalizeDocumentationDraft(payload.ticket.documentation));
      setDocumentationTicketStatus(deriveDocumentationTicketStatus(payload.ticket.status));
      setDocumentationStatusReason(payload.ticket.statusReason || "");
      setDocumentationIssuesAddressed(deriveDocumentationIssuesAddressed(payload.ticket.chatState));
      setDocumentationStep(1);

      if (options?.createFollowUpTicket) {
        const followUpResponse = await fetch(`/api/admin/tickets/${encodeURIComponent(payload.ticket.id)}/follow-up-ticket`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            actorUsername: session?.username || "admin",
            inquiry: workflowDocumentation.inquiry || payload.ticket.inquiry,
          }),
        });

        const followUpPayload = (await followUpResponse.json().catch(() => null)) as DetailResponse | null;

        if (!followUpResponse.ok || !followUpPayload?.ticket) {
          toast.error(followUpPayload?.message || "The workflow was saved, but we could not create the follow-up ticket.");
          await refreshTicketsOnly(true);
          return;
        }

        await refreshTicketsOnly(true);
        setConsoleTicketId(followUpPayload.ticket.id);
        setConsoleDetail(followUpPayload);
        toast.success(`A new follow-up ticket ${followUpPayload.ticket.id} has been created for this chat.`);
        return;
      }

      await refreshTicketsOnly(true);
      toast.success(
        documentationIssuesAddressed === "yes"
          ? "Workflow saved and chat closed."
          : "Workflow saved and chat kept open.",
      );
    } catch {
      toast.error("We could not connect to the server. Please try again.");
    } finally {
      setIsSavingDocumentation(false);
    }
  }

  async function handleConsoleChatSend() {
    if (!consoleDetail || !consoleChatInput.trim() || !adminCanReplyToLiveChat || isSendingConsoleChat) {
      return;
    }

    const messageText = consoleChatInput.trim();
    const outgoingMessage: ChatHistoryItem = {
      id: Date.now(),
      role: "agent",
      senderLabel: session?.fullName || session?.username || "Support Agent",
      text: messageText,
      createdAt: new Date().toISOString(),
    };
    const optimisticDetail: TicketDetailResponse = {
      ...consoleDetail,
      chatHistory: [...consoleDetail.chatHistory, outgoingMessage],
    };

    setConsoleChatInput("");
    setIsSendingConsoleChat(true);
    setConsoleDetail(optimisticDetail);

    try {
      const response = await fetch(`/api/tickets/${encodeURIComponent(consoleDetail.ticket.id)}/chat-history`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          status: consoleDetail.ticket.status,
          statusReason: consoleDetail.ticket.statusReason,
          messages: serializeConsoleChatHistory(optimisticDetail.chatHistory),
        }),
      });

      const payload = (await response.json().catch(() => null)) as { message?: string } | null;

      if (!response.ok) {
        setConsoleDetail(consoleDetail);
        setConsoleChatInput(messageText);
        toast.error(payload?.message || "We could not send the chat message right now.");
        return;
      }

      const refreshedDetail = await fetchTicketDetail(consoleDetail.ticket.id);
      syncDetailAcrossViews(refreshedDetail);
    } catch {
      setConsoleDetail(consoleDetail);
      setConsoleChatInput(messageText);
      toast.error("We could not connect to the server. Please try again.");
    } finally {
      setIsSendingConsoleChat(false);
    }
  }

  async function handleAiMessageSend() {
    if (!consoleDetail || !consoleAiInput.trim() || isSendingAiMessage) {
      return;
    }

    const ticketId = consoleDetail.ticket.id;
    const messageText = consoleAiInput.trim();
    const outgoingMessage = createAiThreadMessage("user", messageText);
    const nextThread = [...activeAiThread, outgoingMessage];

    setConsoleAiInput("");
    setIsSendingAiMessage(true);
    setAiThreads((currentThreads) => ({
      ...currentThreads,
      [ticketId]: nextThread,
    }));

    try {
      const response = await fetch(`/api/admin/tickets/${encodeURIComponent(ticketId)}/ai-agent-message`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          actorUsername: session?.username || "admin",
          message: messageText,
          messages: nextThread.map((message) => ({
            role: message.role,
            text: message.text,
            timestamp: message.createdAt,
          })),
        }),
      });

      const payload = (await response.json().catch(() => null)) as AdminAiMessageResponse | null;

      if (!response.ok || !payload?.ok) {
        setAiThreads((currentThreads) => ({
          ...currentThreads,
          [ticketId]: activeAiThread,
        }));
        setConsoleAiInput(messageText);
        toast.error(payload?.message || "We could not reach the AI agent right now.");
        return;
      }

      const fallbackReply = payload?.webhookConfigured === false
        ? "The AI workflow is not configured yet. You can still continue documenting the case and reply manually."
        : "The AI workflow did not return a text reply for this message.";

      setAiThreads((currentThreads) => ({
        ...currentThreads,
        [ticketId]: [...nextThread, createAiThreadMessage("assistant", payload?.reply || fallbackReply)],
      }));
    } catch {
      setAiThreads((currentThreads) => ({
        ...currentThreads,
        [ticketId]: activeAiThread,
      }));
      setConsoleAiInput(messageText);
      toast.error("We could not connect to the AI workflow right now.");
    } finally {
      setIsSendingAiMessage(false);
    }
  }

  function syncDrafts(detail: TicketDetailResponse) {
    setDraftStatus(detail.ticket.status);
    setDraftAgentId(detail.ticket.assignedAgentId ? String(detail.ticket.assignedAgentId) : "unassigned");
    setDraftSlaStatus(detail.ticket.slaStatus);
    setNotes("");
  }

  function closePanel() {
    setActiveTicketId("");
    setActiveDetail(null);
    setNotes("");
  }

  async function saveTicket(overrides?: {
    status?: TicketSummary["status"];
    slaStatus?: TicketSummary["slaStatus"];
    note?: string;
    successMessage?: string;
  }) {
    if (!activeDetail) {
      return;
    }

    const nextStatus = overrides?.status ?? draftStatus;
    const nextNote = (overrides?.note ?? notes).trim();

    if (nextStatus !== activeDetail.ticket.status && !nextNote) {
      toast.error("Add an internal note before changing the ticket status.");
      return;
    }

    setIsSaving(true);

    try {
      const response = await fetch(`/api/admin/tickets/${encodeURIComponent(activeDetail.ticket.id)}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          status: nextStatus,
          assignedAgentId: draftAgentId === "unassigned" ? null : Number(draftAgentId),
          slaStatus: overrides?.slaStatus ?? effectiveDraftSlaStatus,
          note: nextNote,
          actorUsername: session?.username || "admin",
        }),
      });

      const payload = (await response.json().catch(() => null)) as DetailResponse | null;

      if (!response.ok || !payload?.ticket) {
        toast.error(payload?.message || "We could not update the ticket right now.");
        return;
      }

      setActiveDetail(payload);
      syncDrafts(payload);
      setTickets((currentTickets) => currentTickets.map((ticket) => (
        ticket.id === payload.ticket.id ? payload.ticket : ticket
      )));
      toast.success(overrides?.successMessage || "Changes saved");
    } catch {
      toast.error("We could not connect to the server. Please try again.");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <SupportLayout fullWidth>
      <div className="w-full space-y-6">
        <div className="flex items-center justify-between flex-wrap gap-3 mb-6">
          <div>
            <h1 className="text-3xl font-bold">Admin Dashboard</h1>
            <p className="text-muted-foreground text-sm">
              Manage learner tickets, assignments, chat history and SLA actions.
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              Signed in as {session?.fullName || session?.username || "Support Admin"} ({session?.role || "admin"})
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button asChild variant="outline" size="sm">
              <Link to="/"><ArrowLeft className="h-4 w-4 mr-2" /> Back</Link>
            </Button>
            <Button variant="outline" size="sm" onClick={() => void loadDashboard()} disabled={isLoading}>
              <RefreshCw className={cn("h-4 w-4 mr-2", isLoading && "animate-spin")} /> Refresh
            </Button>
            <LogoutButton />
          </div>
        </div>

        <Tabs
          value={adminView}
          onValueChange={(value) => {
            const nextView = value as "dashboard" | "console";
            setAdminView(nextView);
            if (nextView !== "dashboard") {
              closePanel();
            }
          }}
          className="space-y-6"
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <TabsList className="grid w-full max-w-md grid-cols-2">
              <TabsTrigger value="dashboard">Admin Dashboard</TabsTrigger>
              <TabsTrigger value="console">Chat Console</TabsTrigger>
            </TabsList>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span>{tickets.length} ticket(s)</span>
              <span className="h-1 w-1 rounded-full bg-border" />
              <span>{tickets.filter((ticket) => ticket.chatIsActive && ticket.chatState !== "closed").length} active chat(s)</span>
            </div>
          </div>

          <TabsContent value="dashboard" className="mt-0 space-y-6">
            <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
              {kpis.map((kpi) => (
                <div key={kpi.label} className="bg-card rounded-2xl border shadow-soft p-5">
                  <div className={cn("h-9 w-9 rounded-lg flex items-center justify-center mb-3", kpi.color)}>
                    <kpi.icon className="h-5 w-5" />
                  </div>
                  <div className="text-2xl font-bold">{kpi.value}</div>
                  <div className="text-xs text-muted-foreground">{kpi.label}</div>
                </div>
              ))}
            </div>

            <div className="bg-card rounded-2xl border shadow-card overflow-hidden">
              <div className="px-5 py-4 border-b flex items-center justify-between">
                <h2 className="font-semibold">Recent Tickets</h2>
                <span className="text-xs text-muted-foreground">{tickets.length} total</span>
              </div>

              {error ? (
                <div className="p-5 text-sm text-destructive bg-destructive/5 border-b border-destructive/10">
                  {error}
                </div>
              ) : null}

              {isLoading ? (
                <div className="p-10 text-sm text-muted-foreground flex items-center justify-center gap-2">
                  <LoaderCircle className="h-4 w-4 animate-spin" /> Loading dashboard...
                </div>
              ) : tickets.length === 0 ? (
                <div className="p-10 text-sm text-muted-foreground text-center">
                  No tickets have been created yet.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-secondary/50 text-muted-foreground">
                      <tr className="text-left">
                        {["Ticket ID", "Learner", "Category", "Status", "Assigned Agent", "Created", "SLA", "Action"].map((heading) => (
                          <th key={heading} className="px-4 py-3 font-medium whitespace-nowrap">{heading}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {tickets.map((ticket) => (
                        <tr key={ticket.id} className="hover:bg-secondary/30 transition-colors">
                          <td className="px-4 py-3 font-mono font-medium whitespace-nowrap">{ticket.id}</td>
                          <td className="px-4 py-3 min-w-[240px]">
                            <div className="font-medium">{ticket.learnerName || "Learner"}</div>
                            <div className="text-xs text-muted-foreground">{ticket.email}</div>
                          </td>
                          <td className="px-4 py-3">{formatCategoryLabel(ticket.category, ticket.technicalSubcategory)}</td>
                          <td className="px-4 py-3"><StatusBadge status={ticket.status} /></td>
                          <td className="px-4 py-3">{ticket.assignedAgentName}</td>
                          <td className="px-4 py-3 whitespace-nowrap">{formatDateShort(ticket.createdAt)}</td>
                          <td className="px-4 py-3">
                            <span className={cn("text-xs font-medium", slaStatusClassName(ticket.slaStatus))}>
                              {ticket.slaStatus}
                            </span>
                          </td>
                          <td className="px-4 py-3">
                            <Button size="sm" variant="outline" onClick={() => void openTicket(ticket.id)}>
                              <Eye className="h-3.5 w-3.5 mr-1.5" /> View
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </TabsContent>

          <TabsContent value="console" className="mt-0">
            <div className="h-[calc(100vh-180px)] min-h-[820px] overflow-hidden rounded-3xl border bg-card p-4 shadow-card md:p-5">
              <div className="flex h-full flex-col">
                <div className="flex flex-wrap items-center gap-3">
                  <div className={cn(
                    "rounded-xl border px-4 py-2 text-sm font-medium",
                    hasConsoleQueue ? "border-destructive/20 bg-destructive/10 text-destructive" : "border-emerald-200 bg-emerald-50 text-emerald-700",
                  )}>
                    {hasConsoleQueue ? "Chats Available" : "No chat available"}
                  </div>
                  <div className="min-w-[200px] max-w-sm flex-1">
                    <div className="relative">
                      <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                      <Input
                        value={consoleSearch}
                        onChange={(event) => setConsoleSearch(event.target.value)}
                        placeholder="Search chats, learner, ticket, or category"
                        className="pl-9"
                      />
                    </div>
                  </div>
                  <div className="min-w-[180px]">
                    <Select value={consoleStatus} onValueChange={(value) => setConsoleStatus(value as AdminConsoleStatus)}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {adminConsoleStatuses.map((status) => (
                          <SelectItem key={status} value={status}>{status}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="mt-5 grid min-h-0 flex-1 gap-4 xl:grid-cols-[240px_minmax(0,1.9fr)_minmax(360px,1fr)]">
                  <section className="flex min-h-0 flex-col overflow-hidden rounded-2xl border bg-background/80 shadow-soft">
                    <div className="border-b px-4 py-4">
                      <div className="text-sm font-semibold">Chats</div>
                      <div className="text-xs text-muted-foreground">
                        Queue, search, and open live or ended chat threads.
                      </div>
                    </div>
                    <Tabs
                      value={consoleQueueTab}
                      onValueChange={(value) => setConsoleQueueTab(value as "open" | "closed")}
                      className="flex min-h-0 flex-1 flex-col"
                    >
                      <TabsList className="mx-4 mt-4 grid w-[calc(100%-2rem)] grid-cols-2">
                        <TabsTrigger value="open">Open</TabsTrigger>
                        <TabsTrigger value="closed">Closed</TabsTrigger>
                      </TabsList>
                      <TabsContent value="open" className="mt-4 min-h-0 flex-1 overflow-y-auto px-4 pb-4">
                        <ConsoleQueueList
                          tickets={filteredConsoleTickets}
                          selectedTicketId={consoleTicketId}
                          onSelect={openConsoleChat}
                          emptyTone="success"
                        />
                      </TabsContent>
                      <TabsContent value="closed" className="mt-4 min-h-0 flex-1 overflow-y-auto px-4 pb-4">
                        <ConsoleQueueList
                          tickets={filteredConsoleTickets}
                          selectedTicketId={consoleTicketId}
                          onSelect={openConsoleChat}
                          emptyTone="success"
                        />
                      </TabsContent>
                    </Tabs>
                  </section>

                  {isConsoleOpening ? (
                    <div className="col-span-2 flex min-h-[420px] items-center justify-center rounded-2xl border bg-background/80 text-sm text-muted-foreground">
                      <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> Opening chat console...
                    </div>
                  ) : consoleDetail && documentationDraft ? (
                    <>
                    <div className="grid min-h-0 gap-4 xl:grid-rows-[220px_minmax(0,1fr)]">
                        <ConsoleSectionCard
                          title="Learner Information"
                          description="Learner details and ticket context are unlocked as soon as the chat is assigned to the signed-in admin."
                          className="min-h-0"
                          contentClassName="min-h-0 flex-1 overflow-y-auto p-4"
                        >
                          <div className="grid gap-3 sm:grid-cols-2">
                            <ConsoleField label="Name" icon={UserRound} value={consoleDetail.ticket.learnerName || "-"} />
                            <ConsoleField label="E-mail" icon={Mail} value={consoleDetail.ticket.email || "-"} />
                            <ConsoleField label="Phone" icon={Phone} value={consoleDetail.ticket.learnerPhone || "-"} />
                            <ConsoleField label="Category / Subcategory" icon={TicketIcon} value={formatCategoryLabel(consoleDetail.ticket.category, consoleDetail.ticket.technicalSubcategory)} />
                            <ConsoleField label="Inquiry" icon={MessageSquareText} value={consoleDetail.ticket.inquiry || "-"} className="sm:col-span-2" />
                            <ConsoleField label="Ticket ID" icon={Hash} value={consoleDetail.ticket.id} />
                          </div>
                        </ConsoleSectionCard>

                        <ConsoleChatPanel
                          title="Kent Live Chat"
                          subtitle={`Assigned to ${consoleDetail.ticket.assignedAgentName || "Unassigned"}`}
                          statusLabel={
                            consoleDetail.ticket.chatState === "closed"
                              ? "Closed"
                              : consoleDetail.ticket.liveChatRequested
                                ? "Live chat requested"
                                : "Chatbot only"
                          }
                          statusTone={
                            consoleDetail.ticket.chatState === "closed"
                              ? "muted"
                              : consoleDetail.ticket.liveChatRequested
                                ? "success"
                                : "warning"
                          }
                          messages={consoleDetail.chatHistory.map((message) => ({
                            id: String(message.id),
                            role: message.role === "user" ? "user" : "assistant",
                            title: message.senderLabel,
                            text: message.text,
                            createdAt: message.createdAt,
                          }))}
                          composerValue={consoleChatInput}
                          onComposerChange={setConsoleChatInput}
                          onSend={handleConsoleChatSend}
                          sendDisabled={!adminCanReplyToLiveChat || isSendingConsoleChat}
                          sendLabel={isSendingConsoleChat ? "Sending..." : "Send"}
                          placeholder={
                            liveChatLocked
                              ? "This chat is closed."
                              : consoleDetail.ticket.liveChatRequested
                                ? "Type your message..."
                                : "The learner must choose Live Agent before admin replies are enabled."
                          }
                          emptyMessage="No live chat messages are available for this conversation yet."
                          headerMeta={consoleDetail.ticket.liveChatRequested ? (consoleDetail.ticket.chatId || "No chat ID") : "Waiting for learner live chat request"}
                          icon={Headphones}
                        />
                      </div>

                    <div className="grid min-h-0 gap-4 xl:grid-rows-[minmax(0,1.15fr)_minmax(0,1fr)]">
                      <ConsoleSectionCard
                        title="Documentation"
                        description="Step through case notes, ticket outcome, and learner resolution before finalizing the chat."
                        className="min-h-0"
                        contentClassName="min-h-0 flex-1 overflow-hidden"
                      >
                        <DocumentationWorkflowPanel
                          draft={documentationDraft}
                          step={documentationStep}
                          ticketStatus={documentationTicketStatus}
                          statusReason={documentationStatusReason}
                          issuesAddressed={documentationIssuesAddressed}
                          statusReasonOptions={documentationStatusReasonsForSelection}
                          isSaving={isSavingDocumentation}
                          isDirty={documentationWorkflowDirty}
                          attachments={consoleDetail.attachments}
                          sessionRequests={consoleDetail.sessionRequests}
                          onFieldChange={updateDocumentationField}
                          onImagesAdded={handleDocumentationImagesAdded}
                          onRemoveImage={removeDocumentationImage}
                          onTicketStatusChange={setDocumentationTicketStatus}
                          onStatusReasonChange={setDocumentationStatusReason}
                          onIssuesAddressedChange={setDocumentationIssuesAddressed}
                          onBack={() => setDocumentationStep((currentStep) => Math.max(1, currentStep - 1))}
                          onNext={() => setDocumentationStep((currentStep) => Math.min(3, currentStep + 1))}
                          onSaveOnly={() => void saveDocumentation()}
                          onSubmit={() => void runDocumentationWorkflow()}
                          onCreateFollowUpTicket={() => void runDocumentationWorkflow({ createFollowUpTicket: true })}
                          canMoveForward={canMoveDocumentationForward}
                        />
                      </ConsoleSectionCard>

                      <ConsoleChatPanel
                        title="AI Agent"
                        subtitle={`Admin status: ${consoleStatus}`}
                        statusLabel={chatbotWorkflowConfigured ? "Connected" : "Offline"}
                        statusTone={chatbotWorkflowConfigured ? "success" : "warning"}
                        messages={activeAiThread.map((message) => ({
                          id: message.id,
                          role: message.role,
                          title: message.role === "assistant" ? "AI Agent" : (session?.fullName || session?.username || "Admin"),
                          text: message.text,
                          createdAt: message.createdAt,
                        }))}
                        composerValue={consoleAiInput}
                        onComposerChange={setConsoleAiInput}
                        onSend={handleAiMessageSend}
                        sendDisabled={isSendingAiMessage}
                        sendLabel={isSendingAiMessage ? "Sending..." : "Send"}
                        placeholder="Ask the AI agent for the next step..."
                        emptyMessage="Start an AI handoff to capture workflow guidance for this ticket."
                        headerMeta={getSuggestedAiAction(consoleDetail.ticket, consoleDetail.attachments.length)}
                        icon={Bot}
                      />
                    </div>
                  </>
                ) : (
                  <div className="col-span-2 flex min-h-[420px] items-center justify-center rounded-2xl border border-dashed bg-background/60 px-8 text-center">
                    <div className="max-w-xl">
                      <div className="text-lg font-semibold">Open a chat from the queue</div>
                      <div className="mt-2 text-sm leading-6 text-muted-foreground">
                        The learner information, Kent live chat, documentation workspace, and AI agent panel stay closed until an admin opens a chat from the sidebar.
                      </div>
                    </div>
                  </div>
                )}
                </div>
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </div>

      <Sheet open={!!activeTicketId} onOpenChange={(open) => !open && closePanel()}>
        <SheetContent className="w-full sm:max-w-3xl overflow-y-auto">
          {isOpening ? (
            <div className="h-full min-h-[300px] flex items-center justify-center gap-2 text-sm text-muted-foreground">
              <LoaderCircle className="h-4 w-4 animate-spin" /> Loading ticket...
            </div>
          ) : activeDetail ? (
            <>
              <SheetHeader>
                <SheetTitle className="flex items-center gap-2">
                  Ticket <span className="font-mono">{activeDetail.ticket.id}</span>
                </SheetTitle>
                <SheetDescription>
                  {activeDetail.ticket.learnerName || activeDetail.ticket.email} - {formatCategoryLabel(activeDetail.ticket.category, activeDetail.ticket.technicalSubcategory)}
                </SheetDescription>
              </SheetHeader>

              <div className="space-y-5 py-5">
                <Tabs defaultValue="conversation" className="space-y-4">
                  <TabsList className="grid w-full grid-cols-3">
                    <TabsTrigger value="conversation">
                      <MessageSquareText className="mr-2 h-4 w-4" /> Conversation
                    </TabsTrigger>
                    <TabsTrigger value="documentation">
                      <FileText className="mr-2 h-4 w-4" /> Documentation
                    </TabsTrigger>
                    <TabsTrigger value="details">
                      <TicketIcon className="mr-2 h-4 w-4" /> Ticket Details
                    </TabsTrigger>
                  </TabsList>

                  <TabsContent value="conversation" className="space-y-5">
                    <section>
                      <Label className="mb-1.5 block">Inquiry details</Label>
                      <div className="rounded-xl border bg-secondary/40 p-3 text-sm leading-6">
                        {activeDetail.ticket.inquiry}
                      </div>
                    </section>

                    <section>
                      <Label className="mb-1.5 block">Support session requests</Label>
                      <div className="rounded-xl border p-3 space-y-3">
                        {activeDetail.sessionRequests.length === 0 ? (
                          <div className="text-sm text-muted-foreground">No session requests for this ticket yet.</div>
                        ) : (
                          activeDetail.sessionRequests.map((request) => (
                            <div key={request.id} className="rounded-lg bg-secondary/40 p-3 text-sm">
                              <div className="font-medium">
                                {request.requestedDate} at {request.requestedTime}
                              </div>
                              <div className="text-muted-foreground text-xs mt-1">
                                Status: {request.status} - Requested by: {request.createdBy} - {formatDateTime(request.createdAt)}
                              </div>
                              {typeof request.metadata?.meeting_join_url === "string" && request.metadata.meeting_join_url ? (
                                <a
                                  href={request.metadata.meeting_join_url}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="mt-2 inline-block text-xs font-medium text-primary hover:underline"
                                >
                                  Open Teams meeting
                                </a>
                              ) : null}
                            </div>
                          ))
                        )}
                      </div>
                    </section>

                    <section>
                      <Label className="mb-1.5 block">Chat history</Label>
                      <div className="space-y-2 max-h-[28rem] overflow-y-auto rounded-xl border p-3">
                        {activeDetail.chatHistory.length === 0 ? (
                          <div className="text-sm text-muted-foreground">No chat messages stored for this ticket yet.</div>
                        ) : (
                          activeDetail.chatHistory.map((message) => (
                            <div key={message.id} className="rounded-lg bg-secondary/40 p-3">
                              <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
                                <span className="font-medium text-foreground">{message.senderLabel}</span>
                                <span>{formatDateTime(message.createdAt)}</span>
                              </div>
                              <div className="mt-1 text-sm leading-6">{message.text}</div>
                            </div>
                          ))
                        )}
                      </div>
                    </section>
                  </TabsContent>

                  <TabsContent value="documentation" className="space-y-5">
                    <section>
                      <Label className="mb-1.5 block">Documentation</Label>
                      <div className="rounded-xl border p-3 space-y-3">
                        {activeDetail.attachments.length === 0 ? (
                          <div className="text-sm text-muted-foreground">No documentation or supporting files were uploaded for this ticket.</div>
                        ) : (
                          activeDetail.attachments.map((file) => (
                            <div key={file.id} className="flex items-start justify-between gap-3 rounded-lg bg-secondary/40 p-3">
                              <div className="min-w-0">
                                <div className="font-medium flex items-center gap-2">
                                  <FileText className="h-4 w-4 shrink-0" />
                                  <span className="truncate">{file.name}</span>
                                </div>
                                <div className="text-xs text-muted-foreground mt-1">
                                  {(file.mimeType || "Unknown type")} - {formatBytes(file.size)} - {formatDateTime(file.createdAt)}
                                </div>
                                {!file.storageUrl && (
                                  <div className="text-xs text-muted-foreground mt-1">
                                    This file is registered in the ticket, but no downloadable storage URL is available yet.
                                  </div>
                                )}
                              </div>
                              {file.storageUrl ? (
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => window.open(file.storageUrl || "", "_blank", "noopener,noreferrer")}
                                >
                                  Open
                                </Button>
                              ) : null}
                            </div>
                          ))
                        )}
                      </div>
                    </section>
                  </TabsContent>

                  <TabsContent value="details" className="space-y-5">
                    <div className="grid gap-3 md:grid-cols-3">
                      <div>
                        <Label className="mb-1.5 block">Status</Label>
                        <Select value={draftStatus} onValueChange={(value) => setDraftStatus(value as TicketSummary["status"])}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {statuses.map((status) => (
                              <SelectItem key={status} value={status}>{status}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div>
                        <Label className="mb-1.5 block">Assign Agent</Label>
                        <Select value={draftAgentId} onValueChange={setDraftAgentId}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="unassigned">Unassigned</SelectItem>
                            {agents.map((agent) => (
                              <SelectItem key={agent.id} value={String(agent.id)}>
                                {agent.fullName}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div>
                        <Label className="mb-1.5 block">{isSlaAutoManaged ? "SLA (Automatic)" : "SLA"}</Label>
                        <Select
                          value={effectiveDraftSlaStatus}
                          onValueChange={(value) => setDraftSlaStatus(value as TicketSummary["slaStatus"])}
                          disabled={isSlaAutoManaged}
                        >
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {slaStatuses.map((status) => (
                              <SelectItem key={status} value={status}>{status}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        {isSlaAutoManaged ? (
                          <p className="mt-1 text-xs text-muted-foreground">
                            Managed automatically from the current ticket status and age.
                          </p>
                        ) : null}
                      </div>
                    </div>

                    <div className="grid gap-4 text-sm sm:grid-cols-2">
                      <InfoCard label="Learner Email" value={activeDetail.ticket.email} />
                      <InfoCard label="Assigned Team" value={activeDetail.ticket.assignedTeam} />
                      <InfoCard label="Category" value={formatCategoryLabel(activeDetail.ticket.category, activeDetail.ticket.technicalSubcategory)} />
                      <InfoCard label="Status Reason" value={activeDetail.ticket.statusReason || "-"} />
                      <InfoCard label="Created" value={formatDateTime(activeDetail.ticket.createdAt)} />
                      <InfoCard label="Updated" value={formatDateTime(activeDetail.ticket.updatedAt)} />
                      <InfoCard label="Priority" value={activeDetail.ticket.priority} />
                      <InfoCard label="Evidence Count" value={String(activeDetail.ticket.evidenceCount)} />
                    </div>

                    <section>
                      <Label className="mb-1.5 block">Activity log</Label>
                      <div className="rounded-xl border p-3 space-y-3 max-h-64 overflow-y-auto">
                        {activeDetail.history.length === 0 ? (
                          <div className="text-sm text-muted-foreground">No activity has been recorded yet.</div>
                        ) : (
                          activeDetail.history.map((item) => (
                            <div key={item.id} className="rounded-lg bg-secondary/40 p-3">
                              <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
                                <span className="font-medium text-foreground">{humanizeEvent(item.eventType)}</span>
                                <span>{formatDateTime(item.createdAt)}</span>
                              </div>
                              <div className="text-xs text-muted-foreground mt-1">
                                {item.actorLabel || item.actorType}
                              </div>
                              <pre className="mt-2 text-xs whitespace-pre-wrap break-words text-muted-foreground">
                                {JSON.stringify(item.payload, null, 2)}
                              </pre>
                            </div>
                          ))
                        )}
                      </div>
                    </section>

                    <section>
                      <Label className="mb-1.5 block">Internal notes</Label>
                      <Textarea
                        rows={4}
                        placeholder="Add an internal note visible to support staff only..."
                        value={notes}
                        onChange={(event) => setNotes(event.target.value)}
                      />
                      {isStatusChanging ? (
                        <p className={cn("mt-2 text-xs", canSubmitStatusChange ? "text-muted-foreground" : "text-destructive")}>
                          A note is required before changing this ticket status.
                        </p>
                      ) : (
                        <p className="mt-2 text-xs text-muted-foreground">
                          Add a note here to explain any admin action or handoff.
                        </p>
                      )}
                    </section>
                  </TabsContent>
                </Tabs>
              </div>

              <SheetFooter className="flex-col gap-2">
                <Button
                  className="w-full gradient-primary border-0"
                  onClick={() => void saveTicket({ successMessage: "Changes saved" })}
                  disabled={isSaving || !canSubmitStatusChange}
                >
                  {isSaving ? <LoaderCircle className="h-4 w-4 mr-2 animate-spin" /> : <Save className="h-4 w-4 mr-2" />}
                  Save Changes
                </Button>
                <div className="grid gap-2 sm:grid-cols-1">
                  <Button
                    variant="outline"
                    className="w-full"
                    onClick={() => void saveTicket({
                      status: "Closed",
                      successMessage: "Ticket closed",
                    })}
                    disabled={isSaving}
                  >
                    <X className="h-4 w-4 mr-2" /> Close
                  </Button>
                </div>
              </SheetFooter>
            </>
          ) : (
            <div className="h-full min-h-[300px] flex items-center justify-center text-sm text-muted-foreground">
              Select a ticket to view its details.
            </div>
          )}
        </SheetContent>
      </Sheet>
    </SupportLayout>
  );
};

const ConsoleQueueList = ({
  tickets,
  selectedTicketId,
  onSelect,
  emptyTone,
}: {
  tickets: TicketSummary[];
  selectedTicketId: string;
  onSelect: (ticketId: string) => Promise<void>;
  emptyTone: "success" | "destructive";
}) => {
  if (tickets.length === 0) {
    return (
      <div className={cn(
        "rounded-2xl border px-4 py-5 text-sm font-medium",
        emptyTone === "success" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-destructive/20 bg-destructive/10 text-destructive",
      )}>
        No chat available
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {tickets.map((ticket) => (
        <button
          key={ticket.id}
          type="button"
          onClick={() => void onSelect(ticket.id)}
          className={cn(
            "w-full rounded-2xl border px-3 py-3 text-left transition-all",
            selectedTicketId === ticket.id
              ? "border-primary bg-primary/6 shadow-soft"
              : "border-border bg-background hover:bg-secondary/40",
          )}
        >
          <div className="flex items-center justify-between gap-3">
            <span className="font-mono text-xs font-semibold">{ticket.chatId || ticket.id}</span>
            <span className={cn(
              "rounded-full px-2 py-0.5 text-[11px] font-medium",
              ticket.chatState === "closed"
                ? "bg-muted text-muted-foreground"
                : "bg-info/10 text-info",
            )}>
              {humanizeChatState(ticket.chatState)}
            </span>
          </div>
          <div className="mt-2 font-medium">{ticket.learnerName || "Learner"}</div>
          <div className="mt-1 text-xs text-muted-foreground">{ticket.id} - {formatCategoryLabel(ticket.category, ticket.technicalSubcategory)}</div>
        </button>
      ))}
    </div>
  );
};

const ConsoleSectionCard = ({
  title,
  description,
  children,
  className,
  contentClassName,
  footer,
}: {
  title: string;
  description: string;
  children: ReactNode;
  className?: string;
  contentClassName?: string;
  footer?: ReactNode;
}) => (
  <section className={cn("flex min-h-0 flex-col overflow-hidden rounded-2xl border bg-background/80 shadow-soft", className)}>
    <div className="border-b px-4 py-4">
      <div className="font-semibold">{title}</div>
      <div className="text-xs text-muted-foreground">{description}</div>
    </div>
    <div className={cn("min-h-0 p-4", contentClassName)}>{children}</div>
    {footer}
  </section>
);

const ConsoleChatPanel = ({
  title,
  subtitle,
  statusLabel,
  statusTone,
  messages,
  composerValue,
  onComposerChange,
  onSend,
  sendDisabled,
  sendLabel,
  placeholder,
  emptyMessage,
  headerMeta,
  icon: Icon,
}: {
  title: string;
  subtitle: string;
  statusLabel: string;
  statusTone: "info" | "success" | "warning" | "muted";
  messages: Array<{
    id: string;
    role: "assistant" | "user" | "system";
    title: string;
    text: string;
    createdAt: string;
  }>;
  composerValue: string;
  onComposerChange: (value: string) => void;
  onSend: () => Promise<void>;
  sendDisabled: boolean;
  sendLabel: string;
  placeholder: string;
  emptyMessage: string;
  headerMeta: string;
  icon: typeof Bot;
}) => {
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!scrollRef.current) {
      return;
    }

    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages]);

  return (
    <section className="flex min-h-0 flex-col overflow-hidden rounded-2xl border bg-card shadow-soft">
      <div className="flex items-center justify-between border-b bg-card px-4 py-3.5">
        <div className="flex min-w-0 items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Icon className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold">{title}</div>
            <div className="truncate text-xs text-muted-foreground">{subtitle}</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="hidden max-w-[220px] truncate text-right text-xs text-muted-foreground md:block">{headerMeta}</div>
          <span className={cn(
            "rounded-full border px-3 py-1 text-xs font-medium",
            statusTone === "success" && "border-emerald-200 bg-emerald-50 text-emerald-700",
            statusTone === "warning" && "border-amber-200 bg-amber-50 text-amber-700",
            statusTone === "muted" && "border-border bg-secondary text-muted-foreground",
            statusTone === "info" && "border-info/20 bg-info/10 text-info",
          )}>
            {statusLabel}
          </span>
        </div>
      </div>

      <div className="min-h-0 flex-1 bg-gradient-to-b from-background to-card">
        <div ref={scrollRef} className="h-full space-y-4 overflow-y-auto px-4 py-5">
          {messages.length === 0 ? (
            <div className="rounded-2xl border border-dashed bg-background/70 px-4 py-6 text-sm text-muted-foreground">
              {emptyMessage}
            </div>
          ) : (
            messages.map((message) => (
              <ConsoleChatBubble key={message.id} message={message} />
            ))
          )}
        </div>
      </div>

      <div className="border-t bg-card p-3 md:p-4">
        <div className="flex items-end gap-2">
          <Input
            value={composerValue}
            onChange={(event) => onComposerChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                void onSend();
              }
            }}
            placeholder={placeholder}
            className="h-11"
            disabled={sendDisabled}
          />
          <Button onClick={() => void onSend()} className="h-11 shrink-0" disabled={sendDisabled}>
            <SendHorizontal className="mr-2 h-4 w-4" />
            {sendLabel}
          </Button>
        </div>
      </div>
    </section>
  );
};

const ConsoleChatBubble = ({
  message,
}: {
  message: {
    role: "assistant" | "user" | "system";
    title: string;
    text: string;
    createdAt: string;
  };
}) => {
  const isUser = message.role === "user";

  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div className={cn("max-w-[88%]", isUser ? "items-end" : "items-start")}>
        <div className={cn("mb-1 flex items-center gap-2 text-xs text-muted-foreground", isUser ? "justify-end" : "justify-start")}>
          <span>{message.title}</span>
          <span>{formatDateTime(message.createdAt)}</span>
        </div>
        <div className={cn(
          "rounded-2xl border px-4 py-3 text-sm leading-6 shadow-soft",
          isUser
            ? "border-primary/10 bg-primary text-primary-foreground"
            : "border-border bg-background text-foreground",
        )}>
          {message.text}
        </div>
      </div>
    </div>
  );
};

const DocumentationWorkflowPanel = ({
  draft,
  step,
  ticketStatus,
  statusReason,
  issuesAddressed,
  statusReasonOptions,
  isSaving,
  isDirty,
  attachments,
  sessionRequests,
  onFieldChange,
  onImagesAdded,
  onRemoveImage,
  onTicketStatusChange,
  onStatusReasonChange,
  onIssuesAddressedChange,
  onBack,
  onNext,
  onSaveOnly,
  onSubmit,
  onCreateFollowUpTicket,
  canMoveForward,
}: {
  draft: AdminDocumentation;
  step: number;
  ticketStatus: DocumentationWorkflowStatus | "";
  statusReason: string;
  issuesAddressed: DocumentationIssuesAddressed;
  statusReasonOptions: string[];
  isSaving: boolean;
  isDirty: boolean;
  attachments: AttachmentItem[];
  sessionRequests: SessionRequestItem[];
  onFieldChange: (field: keyof AdminDocumentation, value: string) => void;
  onImagesAdded: (event: ChangeEvent<HTMLInputElement>) => Promise<void>;
  onRemoveImage: (index: number) => void;
  onTicketStatusChange: (value: DocumentationWorkflowStatus | "") => void;
  onStatusReasonChange: (value: string) => void;
  onIssuesAddressedChange: (value: DocumentationIssuesAddressed) => void;
  onBack: () => void;
  onNext: () => void;
  onSaveOnly: () => void;
  onSubmit: () => void;
  onCreateFollowUpTicket: () => void;
  canMoveForward: boolean;
}) => (
  <div className="flex h-full min-h-0 flex-col">
    <div className="mb-4 flex items-center gap-2 border-b pb-3">
      {[1, 2, 3].map((pageNumber) => (
        <div key={pageNumber} className="flex items-center gap-2">
          <div className={cn(
            "flex h-7 w-7 items-center justify-center rounded-full border text-xs font-semibold",
            pageNumber === step
              ? "border-primary bg-primary text-primary-foreground"
              : pageNumber < step
                ? "border-success bg-success/10 text-success"
                : "border-border text-muted-foreground",
          )}>
            {pageNumber}
          </div>
          {pageNumber < 3 ? <div className="h-px w-8 bg-border" /> : null}
        </div>
      ))}
      <div className="ml-auto text-xs text-muted-foreground">
        Page {step} of 3
      </div>
    </div>

    <div className="min-h-0 flex-1">
      {step === 1 ? (
        <DocumentationAccordionEditor
          draft={draft}
          attachments={attachments}
          sessionRequests={sessionRequests}
          onFieldChange={onFieldChange}
          onImagesAdded={onImagesAdded}
          onRemoveImage={onRemoveImage}
        />
      ) : step === 2 ? (
        <div className="flex h-full min-h-0 flex-col justify-between gap-6">
          <div className="space-y-5 overflow-y-auto pr-1">
            <div className="rounded-2xl border bg-secondary/20 p-4">
              <div className="text-sm font-semibold">Ticket status</div>
              <div className="mt-1 text-xs text-muted-foreground">
                Choose the final ticket status for this documentation workflow.
              </div>
              <div className="mt-3">
                <Select value={ticketStatus} onValueChange={(value) => onTicketStatusChange(value as DocumentationWorkflowStatus)}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select ticket status" />
                  </SelectTrigger>
                  <SelectContent>
                    {documentationWorkflowStatuses.map((statusOption) => (
                      <SelectItem key={statusOption} value={statusOption}>{statusOption}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="rounded-2xl border bg-secondary/20 p-4">
              <div className="text-sm font-semibold">Status reason</div>
              <div className="mt-1 text-xs text-muted-foreground">
                The available reasons change based on the selected ticket status.
              </div>
              <div className="mt-3">
                <Select value={statusReason} onValueChange={onStatusReasonChange} disabled={!ticketStatus}>
                  <SelectTrigger>
                    <SelectValue placeholder={ticketStatus ? "Select status reason" : "Choose ticket status first"} />
                  </SelectTrigger>
                  <SelectContent>
                    {statusReasonOptions.map((reasonOption) => (
                      <SelectItem key={reasonOption} value={reasonOption}>{reasonOption}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="flex h-full min-h-0 flex-col justify-between gap-6">
          <div className="space-y-5 overflow-y-auto pr-1">
            <div className="rounded-2xl border bg-secondary/20 p-5">
              <div className="text-lg font-semibold">Were the Learner&apos;s issues addressed?</div>
              <div className="mt-2 text-sm text-muted-foreground">
                Choose how the chat itself should end after the documentation workflow is saved.
              </div>
              <div className="mt-5 grid gap-3 sm:grid-cols-2">
                <button
                  type="button"
                  onClick={() => onIssuesAddressedChange("yes")}
                  className={cn(
                    "rounded-2xl border px-4 py-4 text-left transition-colors",
                    issuesAddressed === "yes"
                      ? "border-success bg-success/10 text-success"
                      : "border-border bg-background hover:bg-secondary/40",
                  )}
                >
                  <div className="font-semibold">Yes</div>
                  <div className={cn("mt-1 text-sm", issuesAddressed === "yes" ? "text-success/80" : "text-muted-foreground")}>
                    Save the workflow and close this chat conversation.
                  </div>
                </button>
                <button
                  type="button"
                  onClick={() => onIssuesAddressedChange("no")}
                  className={cn(
                    "rounded-2xl border px-4 py-4 text-left transition-colors",
                    issuesAddressed === "no"
                      ? "border-warning bg-warning/10 text-warning"
                      : "border-border bg-background hover:bg-secondary/40",
                  )}
                >
                  <div className="font-semibold">No</div>
                  <div className={cn("mt-1 text-sm", issuesAddressed === "no" ? "text-warning/80" : "text-muted-foreground")}>
                    Keep the chat open and optionally create a new ticket on the same chat.
                  </div>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>

    <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t pt-4">
      <div className="text-xs text-muted-foreground">
        {step === 1
          ? "Page 1 remains the expandable documentation workspace."
          : step === 2
            ? "Both dropdowns must be selected before you can continue."
            : "Pick Yes or No, then save the workflow or create a follow-up ticket."}
      </div>
      <div className="flex flex-wrap justify-end gap-2">
        {step === 1 ? (
          <>
            <Button variant="outline" onClick={onSaveOnly} disabled={!isDirty || isSaving}>
              <Save className="mr-2 h-4 w-4" />
              {isSaving ? "Saving..." : "Save Page 1"}
            </Button>
            <Button onClick={onNext} className="border-0 gradient-primary">
              Next
            </Button>
          </>
        ) : step === 2 ? (
          <>
            <Button variant="outline" onClick={onBack}>
              Back
            </Button>
            <Button onClick={onNext} className="border-0 gradient-primary" disabled={!canMoveForward}>
              Next
            </Button>
          </>
        ) : (
          <>
            <Button variant="outline" onClick={onBack} disabled={isSaving}>
              Back
            </Button>
            {issuesAddressed === "no" ? (
              <Button variant="outline" onClick={onCreateFollowUpTicket} disabled={!canMoveForward || isSaving}>
                {isSaving ? "Working..." : "Create New Ticket for Same Chat"}
              </Button>
            ) : null}
            <Button onClick={onSubmit} className="border-0 gradient-primary" disabled={!canMoveForward || isSaving}>
              {isSaving ? "Saving..." : issuesAddressed === "yes" ? "Save and Close Chat" : "Save and Keep Chat Open"}
            </Button>
          </>
        )}
      </div>
    </div>
  </div>
);

const DocumentationAccordionEditor = ({
  draft,
  attachments,
  sessionRequests,
  onFieldChange,
  onImagesAdded,
  onRemoveImage,
}: {
  draft: AdminDocumentation;
  attachments: AttachmentItem[];
  sessionRequests: SessionRequestItem[];
  onFieldChange: (field: keyof AdminDocumentation, value: string) => void;
  onImagesAdded: (event: ChangeEvent<HTMLInputElement>) => Promise<void>;
  onRemoveImage: (index: number) => void;
}) => (
  <div className="flex h-full min-h-0 flex-col">
    <Accordion type="multiple" defaultValue={["inquiry", "symptoms", "errors"]} className="min-h-0 flex-1 overflow-y-auto pr-1">
      <AccordionItem value="inquiry">
        <AccordionTrigger>Inquiry</AccordionTrigger>
        <AccordionContent>
          <Textarea
            value={draft.inquiry}
            onChange={(event) => onFieldChange("inquiry", event.target.value)}
            placeholder="Document the learner inquiry..."
            className="min-h-[120px]"
          />
        </AccordionContent>
      </AccordionItem>

      <AccordionItem value="symptoms">
        <AccordionTrigger>Symptoms</AccordionTrigger>
        <AccordionContent>
          <Textarea
            value={draft.symptoms}
            onChange={(event) => onFieldChange("symptoms", event.target.value)}
            placeholder="Capture the observed symptoms..."
            className="min-h-[120px]"
          />
        </AccordionContent>
      </AccordionItem>

      <AccordionItem value="errors">
        <AccordionTrigger>Errors</AccordionTrigger>
        <AccordionContent className="space-y-4">
          <Textarea
            value={draft.errors}
            onChange={(event) => onFieldChange("errors", event.target.value)}
            placeholder="Describe the error details and attach supporting screenshots..."
            className="min-h-[120px]"
          />

          <div className="flex flex-wrap items-center gap-3">
            <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium hover:bg-secondary/50">
              <ImagePlus className="h-4 w-4" />
              Add images
              <input type="file" accept="image/*" multiple className="sr-only" onChange={(event) => void onImagesAdded(event)} />
            </label>
            <span className="text-xs text-muted-foreground">Images only. Use this area for screenshots and error captures.</span>
          </div>

          {draft.errorImages.length > 0 ? (
            <div className="grid gap-3 sm:grid-cols-2">
              {draft.errorImages.map((image, index) => (
                <div key={`${image.name}-${index}`} className="overflow-hidden rounded-2xl border bg-background">
                  <img src={image.dataUrl} alt={image.name} className="h-40 w-full object-cover" />
                  <div className="flex items-center justify-between gap-3 p-3">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium">{image.name}</div>
                      <div className="text-xs text-muted-foreground">{formatBytes(image.size)}</div>
                    </div>
                    <Button variant="outline" size="sm" onClick={() => onRemoveImage(index)}>
                      Remove
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          ) : null}

          {attachments.length > 0 ? (
            <div className="space-y-2">
              <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Existing ticket evidence</div>
              {attachments.map((file) => (
                <div key={file.id} className="flex items-start justify-between gap-3 rounded-xl border bg-secondary/20 p-3">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">{file.name}</div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {(file.mimeType || "Unknown type")} - {formatBytes(file.size)}
                    </div>
                  </div>
                  {file.storageUrl ? (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => window.open(file.storageUrl || "", "_blank", "noopener,noreferrer")}
                    >
                      Open
                    </Button>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}
        </AccordionContent>
      </AccordionItem>

      <AccordionItem value="steps">
        <AccordionTrigger>Steps</AccordionTrigger>
        <AccordionContent>
          <Textarea
            value={draft.steps}
            onChange={(event) => onFieldChange("steps", event.target.value)}
            placeholder="Record the troubleshooting steps already taken..."
            className="min-h-[120px]"
          />
        </AccordionContent>
      </AccordionItem>

      <AccordionItem value="resources">
        <AccordionTrigger>Resources</AccordionTrigger>
        <AccordionContent className="space-y-4">
          <Textarea
            value={draft.resources}
            onChange={(event) => onFieldChange("resources", event.target.value)}
            placeholder="Add resources, links, or follow-up notes..."
            className="min-h-[120px]"
          />

          {sessionRequests.length > 0 ? (
            <div className="space-y-2">
              <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Support session history</div>
              {sessionRequests.map((request) => (
                <div key={request.id} className="rounded-xl border bg-secondary/20 p-3">
                  <div className="font-medium">{request.requestedDate} at {request.requestedTime}</div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {request.status} - {formatDateTime(request.createdAt)}
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </AccordionContent>
      </AccordionItem>

      <AccordionItem value="chatid">
        <AccordionTrigger>Chat ID</AccordionTrigger>
        <AccordionContent>
          <Textarea value={draft.chatId} readOnly className="min-h-[92px] font-mono" />
        </AccordionContent>
      </AccordionItem>

      <AccordionItem value="ticketid">
        <AccordionTrigger>Ticket ID</AccordionTrigger>
        <AccordionContent>
          <Textarea value={draft.ticketId} readOnly className="min-h-[92px] font-mono" />
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  </div>
);

const ConsoleField = ({
  label,
  value,
  icon: Icon,
  className,
}: {
  label: string;
  value: string;
  icon: typeof UserRound;
  className?: string;
}) => (
  <div className={cn("rounded-xl border bg-secondary/20 p-3", className)}>
    <div className="flex items-center gap-2 text-xs text-muted-foreground">
      <Icon className="h-3.5 w-3.5" />
      {label}
    </div>
    <div className="mt-2 break-words text-sm font-medium leading-6">{value}</div>
  </div>
);

function normalizeDocumentationDraft(documentation?: AdminDocumentation | null): AdminDocumentation {
  return {
    inquiry: documentation?.inquiry || "",
    symptoms: documentation?.symptoms || "",
    errors: documentation?.errors || "",
    steps: documentation?.steps || "",
    resources: documentation?.resources || "",
    chatId: documentation?.chatId || "",
    ticketId: documentation?.ticketId || "",
    ticketStatus: documentation?.ticketStatus || "",
    statusReason: documentation?.statusReason || "",
    issuesAddressed: documentation?.issuesAddressed || "",
    errorImages: Array.isArray(documentation?.errorImages) ? documentation.errorImages : [],
  };
}

function deriveDocumentationTicketStatus(status: TicketSummary["status"]): DocumentationWorkflowStatus | "" {
  return status === "Closed" || status === "Pending" ? status : "";
}

function deriveDocumentationIssuesAddressed(chatState: string): DocumentationIssuesAddressed {
  return chatState === "closed" ? "yes" : "";
}

function buildDocumentationWorkflowNote(
  ticket: TicketDetail,
  status: DocumentationWorkflowStatus,
  statusReason: string,
  issuesAddressed: DocumentationIssuesAddressed,
) {
  const changeSummary = [
    `Documentation workflow updated ticket ${ticket.id}.`,
    `Status set to ${status}.`,
    `Reason set to ${statusReason}.`,
    issuesAddressed === "yes"
      ? "Learner issues were marked as addressed and the chat was closed."
      : "Learner issues were marked as not yet addressed and the chat remained open.",
  ];

  return changeSummary.join(" ");
}

function dedupeConsoleQueueTickets(tickets: TicketSummary[]) {
  const orderedTickets = [...tickets].sort((leftTicket, rightTicket) => {
    const leftDate = Date.parse(leftTicket.updatedAt || leftTicket.lastMessageAt || leftTicket.createdAt || "");
    const rightDate = Date.parse(rightTicket.updatedAt || rightTicket.lastMessageAt || rightTicket.createdAt || "");
    return rightDate - leftDate;
  });
  const ticketsByChatId = new Map<string, TicketSummary>();

  for (const ticket of orderedTickets) {
    const queueKey = ticket.chatId || ticket.id;
    if (!ticketsByChatId.has(queueKey)) {
      ticketsByChatId.set(queueKey, ticket);
    }
  }

  return Array.from(ticketsByChatId.values());
}

function serializeConsoleChatHistory(messages: ChatHistoryItem[]) {
  return messages.map((message) => ({
    sender: message.role === "user" ? "user" : message.role === "agent" ? "agent" : "bot",
    text: message.text,
    timestamp: message.createdAt,
  }));
}

function createAiThreadMessage(role: AiConsoleMessage["role"], text: string): AiConsoleMessage {
  return {
    id: `${role}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    role,
    text,
    createdAt: new Date().toISOString(),
  };
}

function buildInitialAiMessage(ticket: TicketDetail, workflowConfigured: boolean): AiConsoleMessage {
  const workflowText = workflowConfigured
    ? "The chatbot workflow is connected and ready for admin prompts."
    : "The chatbot workflow is not configured yet, so guidance will be limited to local ticket context.";

  return createAiThreadMessage(
    "assistant",
    `${workflowText} Ticket ${ticket.id} is ${ticket.status.toLowerCase()} with SLA ${ticket.slaStatus}. ${getSuggestedAiAction(ticket, ticket.evidenceCount)}`,
  );
}

function readImageFileAsDocumentationImage(file: File): Promise<DocumentationImage> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error);
    reader.onload = () => {
      const result = typeof reader.result === "string" ? reader.result : "";
      resolve({
        name: file.name,
        mimeType: file.type || "image/png",
        size: file.size,
        dataUrl: result,
      });
    };
    reader.readAsDataURL(file);
  });
}

const InfoCard = ({ label, value }: { label: string; value: string }) => (
  <div className="rounded-xl border p-3">
    <div className="text-xs text-muted-foreground">{label}</div>
    <div className="font-medium mt-1 break-words">{value}</div>
  </div>
);

const LogoutButton = () => {
  const navigate = useNavigate();

  return (
    <Button
      variant="outline"
      size="sm"
      onClick={() => {
        clearAdminSession();
        navigate("/admin/login");
      }}
    >
      <LogOut className="h-4 w-4 mr-2" /> Logout
    </Button>
  );
};

function formatDateShort(value: string) {
  return new Date(value).toLocaleDateString([], {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function formatDateTime(value: string) {
  return new Date(value).toLocaleString([], {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatBytes(value: number) {
  if (!value) {
    return "0 B";
  }

  const units = ["B", "KB", "MB", "GB"];
  let size = value;
  let unitIndex = 0;

  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }

  return `${size.toFixed(size >= 10 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

function formatCategoryLabel(category: string, technicalSubcategory: string) {
  if (category === "Technical" && technicalSubcategory) {
    return `${category} - ${technicalSubcategory}`;
  }

  return category;
}

function humanizeEvent(value: string) {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function humanizeChatState(value: string) {
  const normalizedValue = value.trim().toLowerCase();
  if (normalizedValue === "closed") return "Closed";
  if (!normalizedValue) return "Open";
  return normalizedValue.charAt(0).toUpperCase() + normalizedValue.slice(1);
}

function getLatestAssistantMessage(messages: ChatHistoryItem[]) {
  const reversedMessages = [...messages].reverse();
  const lastAssistantMessage = reversedMessages.find((message) => message.role === "assistant" || message.role === "agent");
  return lastAssistantMessage?.text || "";
}

function getSuggestedAiAction(ticket: TicketDetail, attachmentCount: number) {
  if (ticket.slaStatus === "Breached") {
    return "This case is outside SLA. Review the transcript, contact the learner, and escalate through the admin workflow as needed.";
  }

  if (ticket.status === "Pending") {
    return "The learner is waiting on a support meeting or follow-up. Confirm the next action and keep documentation up to date.";
  }

  if (attachmentCount === 0) {
    return "Ask the learner for supporting screenshots, documents, or error captures before closing the case.";
  }

  return "Review the learner details, transcript, and attachments, then decide whether the ticket should stay open or move to closed.";
}

function presenceDotClassName(status: AdminConsoleStatus) {
  if (status === "Busy") return "bg-amber-500";
  if (status === "Off") return "bg-slate-400";
  return "bg-emerald-500";
}

function deriveDashboardSlaStatus(
  status: TicketSummary["status"],
  createdAt: string,
  fallback: TicketSummary["slaStatus"],
): TicketSummary["slaStatus"] {
  if (status === "Open") {
    return "Pending Review";
  }

  if (status === "Closed") {
    return "On Track";
  }

  if (status === "Pending") {
    const createdAtTime = new Date(createdAt).getTime();
    if (!Number.isNaN(createdAtTime) && (Date.now() - createdAtTime) > (3 * 24 * 60 * 60 * 1000)) {
      return "Breached";
    }

    return "On Track";
  }

  return fallback;
}

function slaStatusClassName(value: TicketSummary["slaStatus"]) {
  if (value === "Breached") return "text-destructive";
  if (value === "On Track") return "text-success";
  return "text-warning";
}

export default AgentDashboard;
