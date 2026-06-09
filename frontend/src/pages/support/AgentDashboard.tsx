import { useEffect, useRef, useState, type ChangeEvent, type MouseEvent as ReactMouseEvent, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  Bot,
  AlertOctagon,
  ArrowLeft,
  Bell,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clock,
  FileText,
  Hash,
  Headphones,
  GripHorizontal,
  ImagePlus,
  LayoutDashboard,
  LoaderCircle,
  LogOut,
  Mail,
  MessageSquareText,
  Paperclip,
  Phone,
  RefreshCw,
  Search,
  Save,
  SendHorizontal,
  Settings2,
  Ticket as TicketIcon,
  UserRound,
  UserPlus,
  Users,
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
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Switch } from "@/components/ui/switch";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { SupportLayout } from "@/components/support/SupportLayout";
import { StatusBadge } from "@/components/support/StatusBadge";
import {
  clearAdminSession,
  fetchVerifiedAdminSession,
  getAdminSession,
  isSameAdminIdentity,
  isSameAdminSession,
  setAdminSession,
  setAdminSessionOnWindow,
  type AdminSession,
} from "@/lib/adminSession";
import { fetchCoverageOptions, fetchCoverageTutorEmail, parseCoverageInquiry } from "@/lib/coverageSupport";
import { buildCsrfHeaders } from "@/lib/csrf";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

interface AdminAgent {
  id: number;
  username: string;
  fullName: string;
  email: string | null;
  accountScope?: string;
  role: string;
  isActive?: boolean;
  sessionActive?: boolean;
  consoleStatus?: string;
  selectedConsoleStatus?: string;
  legacySupportAccess?: boolean;
  legacyAdminAccess?: boolean;
  manuallyAddedAgent?: boolean;
  canRemoveFromAgentManagement?: boolean;
}

interface PendingTransferRequest {
  fromAgentId: number;
  fromAgentName: string;
  fromAgentUsername: string;
  toAgentId: number;
  toAgentName: string;
  toAgentUsername: string;
  reason: string;
  requestedAt: string;
}

interface PendingEscalationNotification {
  fromAgentId: number;
  fromAgentName: string;
  fromAgentUsername: string;
  toAgentId: number;
  toAgentName: string;
  toAgentUsername: string;
  note: string;
  ticketId: string;
  requestedAt: string;
}

interface PendingTeamsCallNotification {
  toAgentId: number;
  toAgentName: string;
  toAgentUsername: string;
  requesterName: string;
  requesterEmail: string;
  requesterRole: string;
  note: string;
  targetLabel: string;
  ticketId: string;
  requestedAt: string;
}

interface PendingCoverageTicketNotification {
  ticketId: string;
  requesterName: string;
  requesterEmail: string;
  requesterRole: string;
  createdAt: string;
}

interface LatestEscalationClosure {
  fromAgentId: number;
  fromAgentName: string;
  fromAgentUsername: string;
  toAgentId: number;
  toAgentName: string;
  toAgentUsername: string;
  closedById: number;
  closedByName: string;
  closedByUsername: string;
  note: string;
  ticketId: string;
  requestedAt: string;
  closedAt: string;
  closedStatusReason: string;
  requesterAcknowledged: boolean;
}

interface LatestTransferDecision {
  status: "accepted" | "rejected";
  fromAgentId: number;
  fromAgentName: string;
  fromAgentUsername: string;
  toAgentId: number;
  toAgentName: string;
  toAgentUsername: string;
  reason: string;
  requestedAt: string;
  decidedAt: string;
  decidedById: number;
  decidedByName: string;
  decidedByUsername: string;
  requesterAcknowledged: boolean;
}

interface LatestCoverageTutorResponse {
  outcome: "accepted" | "rejected";
  toAgentId: number;
  toAgentName: string;
  toAgentUsername: string;
  ticketId: string;
  tutor: string;
  tutorEmail: string;
  cardId: string;
  relatedTutorChoiceCardId: string;
  requestedAt: string | null;
  respondedAt: string;
  sessionDetails: string;
  replyText: string;
  sessionStartAt: string | null;
  sessionEndAt: string | null;
  requesterAcknowledged: boolean;
}

interface TicketSummary {
  id: string;
  learnerName: string;
  email: string;
  learnerPhone: string;
  requesterRole: string;
  priority: string;
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
  liveChatRequestedAt: string | null;
  queueAssignedAt: string | null;
  chatDurationMinutes: number;
  chatState: string;
  lastMessageAt: string | null;
  pendingTransferRequest?: PendingTransferRequest | null;
  pendingEscalationNotification?: PendingEscalationNotification | null;
  pendingTeamsCallNotification?: PendingTeamsCallNotification | null;
  pendingCoverageTicketNotification?: PendingCoverageTicketNotification | null;
  teamsCallRequested?: boolean;
  latestEscalationClosure?: LatestEscalationClosure | null;
  latestTransferDecision?: LatestTransferDecision | null;
  latestCoverageTutorResponse?: LatestCoverageTutorResponse | null;
  documentation?: AdminDocumentation | null;
  slaStatus: "Pending Review" | "On Track" | "Breached";
  slaAttentionRequired?: boolean;
  evidenceCount: number;
  createdAt: string;
  updatedAt: string;
}

interface TicketDetail extends TicketSummary {
  inquiry: string;
  closedAt: string | null;
  documentation: AdminDocumentation;
}

interface ChatHistoryItem {
  id: string | number;
  role: string;
  source?: "message" | "history_event" | "intro";
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

interface AdminNotificationLogItem extends HistoryItem {
  ticketId: string;
  chatId: string;
  learnerName: string;
  email: string;
  requesterRole: string;
  status: "Open" | "Pending" | "Closed";
  statusReason: string;
  isCurrent: boolean;
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

interface CoverageCardAttachment {
  id: string;
  name: string;
  mimeType: string;
  size: number;
  dataUrl: string;
}

type CoverageWorkflowCardType = "tutor_choice" | "tutor_reply" | "note";
type CoverageTutorRequestStatus = "draft" | "requested" | "accepted" | "refused";
type CoverageTutorReplyOutcome = "" | "accepted" | "refused";

interface CoverageWorkflowCard {
  id: string;
  type: CoverageWorkflowCardType;
  title: string;
  note: string;
  tutor: string;
  tutorEmail: string;
  sessionDetails: string;
  replyText: string;
  requestStatus: CoverageTutorRequestStatus;
  replyOutcome: CoverageTutorReplyOutcome;
  locked: boolean;
  createdAt: string;
  updatedAt: string;
  submittedAt: string;
  respondedAt: string;
  relatedTutorChoiceCardId: string;
  requestSubmittedByAgentId?: number | null;
  requestSubmittedByAgentName?: string;
  requestSubmittedByAgentUsername?: string;
  responseToken?: string;
  sessionStartAt?: string;
  sessionEndAt?: string;
  confirmedAt?: string;
  confirmedByAgentId?: number | null;
  confirmedByAgentName?: string;
  confirmedByAgentUsername?: string;
  presentationFiles: CoverageCardAttachment[];
}

interface DocumentationWorkflowCard {
  id: string;
  inquiry: string;
  symptoms: string;
  errors: string;
  steps: string;
  resources: string;
  locked: boolean;
  createdAt: string;
  updatedAt: string;
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
  escalationAgentId?: number | null;
  escalationAgentName?: string;
  escalationNote?: string;
  coverageNotes: string;
  coverageCards: CoverageWorkflowCard[];
  documentationCards: DocumentationWorkflowCard[];
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
  accounts?: AdminAgent[];
  agents?: AdminAgent[];
  account?: AdminAgent;
  agent?: AdminAgent;
}

interface EntraSearchResult {
  entraId: string;
  displayName: string;
  email: string;
  username: string;
  alreadyAdded: boolean;
}

interface DetailResponse extends TicketDetailResponse {
  message?: string;
}

interface MigrationStatusResponse {
  adminAiWebhookConfigured?: boolean;
  chatbotWebhookConfigured?: boolean;
}

interface NotificationLogResponse {
  message?: string;
  notifications?: AdminNotificationLogItem[];
}

interface AdminSessionHeartbeatResponse {
  admin?: AdminSession;
  ok?: boolean;
  sessionActive?: boolean;
  sessionReplaced?: boolean;
  message?: string;
}

interface AdminAiMessageResponse {
  message?: string;
  ok?: boolean;
  reply?: string;
  webhookConfigured?: boolean;
  webhookDelivered?: boolean;
}

type AssignedAgentAccent = {
  badgeClassName: string;
  dotClassName: string;
  stripeClassName: string;
};

const statuses: TicketSummary["status"][] = ["Open", "Pending", "Closed"];
const slaStatuses: TicketSummary["slaStatus"][] = ["Pending Review", "On Track", "Breached"];
const autoManagedSlaStatuses = new Set<TicketSummary["status"]>(["Open", "Pending", "Closed"]);
const adminConsoleStatuses = ["Available", "Busy", "Off"] as const;
const adminSelectableConsoleStatuses = ["Available", "Off"] as const;
const consolePollIntervalMs = 2500;
const dashboardTicketPollIntervalMs = 5000;
const dashboardAgentPollIntervalMs = 15000;
const documentationWorkflowStatuses = ["Closed", "Pending"] as const;
const defaultPendingDocumentationStatusReason = "Awaiting resolution";
const documentationStatusReasons = {
  Closed: ["Closed due to inactivity", "Closed via Chatbot", "Closed via Agent"],
  Pending: [defaultPendingDocumentationStatusReason, "Awaiting support meeting", "Escalation", "Quick Ticket"],
} as const;
const userManagementRoles = new Set<string>(["admin", "superadmin"]);
type AdminConsoleStatus = (typeof adminConsoleStatuses)[number];
type AdminSelectableConsoleStatus = (typeof adminSelectableConsoleStatuses)[number];
type DocumentationWorkflowStatus = (typeof documentationWorkflowStatuses)[number];
type DocumentationIssuesAddressed = "yes" | "no" | "";
type DashboardTicketFilter = "all" | "open" | "pending" | "closed" | "slaBreached" | "quickResolution" | "escalation" | "coverage";
type DashboardSortOrder = "newest" | "oldest" | "priorityDesc" | "priorityAsc";
type DashboardAssignedFilter = "all" | "me" | "unassigned" | `agent:${number}`;
type AdminView = "dashboard" | "coverage" | "console" | "management";
type TicketDetailTab = "conversation" | "documentation" | "details";
type CoverageWorkspaceTab = "documentation" | "details";

function buildAdminJsonHeaders() {
  return buildCsrfHeaders({
    "Content-Type": "application/json",
  });
}

const AgentDashboard = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [session, setSessionState] = useState<AdminSession | null>(() => getAdminSession());
  const initialConsoleDeepLink = parseAdminDeepLink(location.search);
  const isMountedRef = useRef(true);
  const sessionRef = useRef<AdminSession | null>(session);
  const previousConsoleChatStateRef = useRef<{ ticketId: string; chatState: string } | null>(null);
  const processedConsoleDeepLinkRef = useRef<string>("");
  const pendingConsoleStatusRef = useRef<AdminSelectableConsoleStatus | null>(null);
  const [tickets, setTickets] = useState<TicketSummary[]>([]);
  const [agents, setAgents] = useState<AdminAgent[]>([]);
  const [adminView, setAdminView] = useState<AdminView>(initialConsoleDeepLink.view);
  const [isAdminSidebarCollapsed, setIsAdminSidebarCollapsed] = useState(false);
  const [isStackedAdminLayout, setIsStackedAdminLayout] = useState(() => (
    typeof window !== "undefined" ? window.innerWidth < 1024 : false
  ));
  const [activeTicketId, setActiveTicketId] = useState("");
  const [activeTicketTab, setActiveTicketTab] = useState<TicketDetailTab>("conversation");
  const [activeDetail, setActiveDetail] = useState<TicketDetailResponse | null>(null);
  const [consoleCaseScope, setConsoleCaseScope] = useState<"my" | "all">(initialConsoleDeepLink.scope);
  const [consoleQueueTab, setConsoleQueueTab] = useState<"open" | "closed">(initialConsoleDeepLink.queueTab);
  const [consoleSearch, setConsoleSearch] = useState("");
  const [isConsoleSearchOptionsVisible, setIsConsoleSearchOptionsVisible] = useState(false);
  const [consoleSearchStatusFilter, setConsoleSearchStatusFilter] = useState<"all" | "open" | "closed">("all");
  const [consoleStatus, setConsoleStatus] = useState<AdminSelectableConsoleStatus | null>(
    session?.consoleStatus ? normalizeAdminSelectableConsoleStatus(session.consoleStatus) : null,
  );
  const [consoleTicketId, setConsoleTicketId] = useState(initialConsoleDeepLink.ticketId);
  const [consoleDetail, setConsoleDetail] = useState<TicketDetailResponse | null>(null);
  const [consoleChatInput, setConsoleChatInput] = useState("");
  const [consoleAiInput, setConsoleAiInput] = useState("");
  const [dashboardTicketFilter, setDashboardTicketFilter] = useState<DashboardTicketFilter>("all");
  const [dashboardSortOrder, setDashboardSortOrder] = useState<DashboardSortOrder>("newest");
  const [dashboardAssignedFilter, setDashboardAssignedFilter] = useState<DashboardAssignedFilter>("all");
  const [dashboardSearch, setDashboardSearch] = useState("");
  const [documentationDraft, setDocumentationDraft] = useState<AdminDocumentation | null>(null);
  const [activeDocumentationDraft, setActiveDocumentationDraft] = useState<AdminDocumentation | null>(null);
  const [documentationStep, setDocumentationStep] = useState(1);
  const [documentationTicketStatus, setDocumentationTicketStatus] = useState<DocumentationWorkflowStatus | "">("");
  const [documentationStatusReason, setDocumentationStatusReason] = useState("");
  const [documentationEscalationAgentId, setDocumentationEscalationAgentId] = useState("");
  const [documentationEscalationNote, setDocumentationEscalationNote] = useState("");
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
  const [isForceClosingConsoleChat, setIsForceClosingConsoleChat] = useState(false);
  const [isTransferMenuOpen, setIsTransferMenuOpen] = useState(false);
  const [isTransferringConsoleTicket, setIsTransferringConsoleTicket] = useState(false);
  const [isTransferNotificationsOpen, setIsTransferNotificationsOpen] = useState(false);
  const [activeTransferRequestTicketId, setActiveTransferRequestTicketId] = useState("");
  const [transferReason, setTransferReason] = useState("");
  const [isSendingAiMessage, setIsSendingAiMessage] = useState(false);
  const [isSavingDocumentation, setIsSavingDocumentation] = useState(false);
  const [isSavingActiveDocumentation, setIsSavingActiveDocumentation] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isUpdatingConsoleStatus, setIsUpdatingConsoleStatus] = useState(false);
  const [managementSearch, setManagementSearch] = useState("");
  const [togglingAccessIds, setTogglingAccessIds] = useState<Set<number>>(new Set());
  const [showAddAgentSheet, setShowAddAgentSheet] = useState(false);
  const [agentSearchQuery, setAgentSearchQuery] = useState("");
  const [agentSearchResults, setAgentSearchResults] = useState<EntraSearchResult[]>([]);
  const [isSearchingAgents, setIsSearchingAgents] = useState(false);
  const [isAddingAgentId, setIsAddingAgentId] = useState<string | null>(null);
  const [removingAgentIds, setRemovingAgentIds] = useState<Set<number>>(new Set());
  const [confirmRemoveAgent, setConfirmRemoveAgent] = useState<AdminAgent | null>(null);
  const [error, setError] = useState("");
  const [chatbotWorkflowConfigured, setChatbotWorkflowConfigured] = useState(false);
  const [consoleTimerNow, setConsoleTimerNow] = useState(() => Date.now());
  const [notificationLog, setNotificationLog] = useState<AdminNotificationLogItem[]>([]);
  const seenTransferNotificationKeysRef = useRef<Set<string>>(new Set());
  const hasHydratedTransferNotificationsRef = useRef(false);
  const pendingRemovedAgentIdsRef = useRef<Set<number>>(new Set());
  const canManageUsers = userManagementRoles.has((session?.role || "").toLowerCase())
    && !!(session?.legacyAdminAccess || session?.entraDirectoryAdmin);
  const isSuperadminSession = (session?.role || "").toLowerCase() === "superadmin";
  const isConsoleView = adminView === "console";
  const isCoverageDashboardView = adminView === "coverage";
  const isDashboardLikeView = adminView === "dashboard" || adminView === "coverage";
  const useCompactAdminSidebar = !isStackedAdminLayout && isAdminSidebarCollapsed;
  const trimmedNotes = notes.trim();
  const dashboardSessionAgentName = session?.fullName || session?.username || "Me";
  const isSlaAutoManaged = Boolean(activeDetail) && autoManagedSlaStatuses.has(draftStatus);
  const effectiveDraftSlaStatus = activeDetail
    ? deriveDashboardSlaStatus(draftStatus, activeDetail.ticket.createdAt, draftSlaStatus)
    : draftSlaStatus;
  const isStatusChanging = Boolean(activeDetail) && draftStatus !== activeDetail.ticket.status;
  const canSubmitStatusChange = !isStatusChanging || Boolean(trimmedNotes);
  const normalizedConsoleSearch = normalizeConsoleSearchValue(consoleSearch);
  const compactConsoleSearch = compactConsoleSearchValue(normalizedConsoleSearch);
  const normalizedDashboardSearch = normalizeConsoleSearchValue(dashboardSearch);
  const compactDashboardSearch = compactConsoleSearchValue(normalizedDashboardSearch);
  const isActiveCoverageTicket = isCoverageTicket(activeDetail?.ticket);
  const isActiveQuickTicket = Boolean(activeDetail) && isDashboardQuickResolutionTicket(activeDetail.ticket);
  const effectiveActiveTicketTab = isActiveQuickTicket && activeTicketTab === "conversation"
    ? "documentation"
    : activeTicketTab;
  const activeCoverageDocumentationBaseline = activeDetail && isActiveCoverageTicket
    ? buildCoverageDocumentationDraft(activeDetail.ticket)
    : null;
  const activeCoverageDocumentationDraft = activeDocumentationDraft
    && activeDetail
    && activeDocumentationDraft.ticketId === activeDetail.ticket.id
    ? activeDocumentationDraft
    : activeCoverageDocumentationBaseline;
  const activeCoverageDocumentationReadOnly = Boolean(activeDetail) && activeDetail.ticket.status === "Closed";
  const activeCoverageDocumentationDirty = Boolean(activeCoverageDocumentationBaseline && activeCoverageDocumentationDraft)
    && JSON.stringify(activeCoverageDocumentationDraft) !== JSON.stringify(activeCoverageDocumentationBaseline);
  const isActiveStandardDocumentationTicket = Boolean(activeDetail)
    && activeDetail.ticket.status === "Pending"
    && !isActiveCoverageTicket;
  const activeStandardDocumentationBaseline = activeDetail && isActiveStandardDocumentationTicket
    ? buildStandardDocumentationDraft(activeDetail.ticket)
    : null;
  const activeStandardDocumentationDraft = activeDocumentationDraft
    && activeDetail
    && activeDocumentationDraft.ticketId === activeDetail.ticket.id
    ? activeDocumentationDraft
    : activeStandardDocumentationBaseline;
  const activeStandardDocumentationDirty = Boolean(activeStandardDocumentationBaseline && activeStandardDocumentationDraft)
    && JSON.stringify(activeStandardDocumentationDraft) !== JSON.stringify(activeStandardDocumentationBaseline);
  const activeAgents = agents.filter((agent) => agent.isActive !== false && isStaffSupportAccount(agent) && agent.legacySupportAccess === true);
  const signedInAgent = agents.find((agent) => (
    (session?.id && agent.id === session.id)
    || (session?.username && agent.username === session.username)
  ));
  const resolvedSessionAgentId = signedInAgent?.id ?? session?.id ?? null;
  const dashboardSessionAgentId = resolvedSessionAgentId;
  const scopedConsoleTickets = tickets.filter((ticket) => {
    if (isQuickResolutionTicket(ticket)) {
      return false;
    }

    // The live chat console should only surface cases that explicitly requested
    // a handoff from the chatbot into an admin chat.
    if (!ticket.chatIsActive || !ticket.liveChatRequested) {
      return false;
    }

    if (consoleCaseScope === "my") {
      return ticket.assignedAgentId === resolvedSessionAgentId;
    }

    return true;
  });
  const openConsoleQueueTickets = sortConsoleTickets(
    scopedConsoleTickets.filter((ticket) => ticket.chatState !== "closed"),
    "open",
  );
  const closedConsoleQueueTickets = sortConsoleTickets(
    scopedConsoleTickets.filter((ticket) => ticket.chatState === "closed"),
    "closed",
  );

  function persistAdminSessionState(nextSession: AdminSession | null) {
    sessionRef.current = nextSession;
    setSessionState(nextSession);
    if (nextSession) {
      setAdminSession(nextSession);
      return;
    }

    clearAdminSession();
  }

  function redirectForEndedAdminSession(message: string, redirectTarget: "/admin/login" | "/support" = "/admin/login") {
    persistAdminSessionState(null);
    toast.error(message);
    navigate(redirectTarget);
  }

  async function revalidateAdminSession(options?: {
    silent?: boolean;
    mismatchMessage?: string;
    expiredMessage?: string;
  }) {
    try {
      const { response, admin } = await fetchVerifiedAdminSession();
      if (response.status === 401) {
        redirectForEndedAdminSession(options?.expiredMessage || "Your admin session ended. Please sign in again.");
        return null;
      }

      if (response.status === 403) {
        redirectForEndedAdminSession(options?.expiredMessage || "This account no longer has admin access.", "/support");
        return null;
      }

      if (!response.ok) {
        if (!options?.silent) {
          toast.error("We could not verify your admin session right now.");
        }
        return sessionRef.current;
      }

      if (!admin) {
        redirectForEndedAdminSession(options?.expiredMessage || "Your admin session ended. Please sign in again.");
        return null;
      }

      const normalizedRole = (admin.role || "").trim().toLowerCase();
      if (normalizedRole !== "admin" && normalizedRole !== "superadmin") {
        redirectForEndedAdminSession(options?.expiredMessage || "This account no longer has admin access.", "/support");
        return null;
      }

      const currentSession = sessionRef.current;
      if (currentSession && !isSameAdminSession(currentSession, admin)) {
        if (isSameAdminIdentity(currentSession, admin)) {
          persistAdminSessionState(admin);
          return admin;
        }

        redirectForEndedAdminSession(
          options?.mismatchMessage || "Your admin session changed. Please sign in again.",
        );
        return null;
      }

      persistAdminSessionState(admin);
      return admin;
    } catch {
      if (!options?.silent) {
        toast.error("We could not verify your admin session right now.");
      }

      return null;
    }
  }

  async function reconcileAdminAuthorizationFailure(options?: {
    mismatchMessage?: string;
    expiredMessage?: string;
  }) {
    const nextSession = await revalidateAdminSession({
      silent: true,
      mismatchMessage: options?.mismatchMessage,
      expiredMessage: options?.expiredMessage,
    });
    return !nextSession;
  }

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const mediaQuery = window.matchMedia("(max-width: 1023.98px)");
    const updateLayoutMode = (matches: boolean) => {
      setIsStackedAdminLayout(matches);
    };

    updateLayoutMode(mediaQuery.matches);

    const handleChange = (event: MediaQueryListEvent) => {
      updateLayoutMode(event.matches);
    };

    if (typeof mediaQuery.addEventListener === "function") {
      mediaQuery.addEventListener("change", handleChange);
      return () => mediaQuery.removeEventListener("change", handleChange);
    }

    mediaQuery.addListener(handleChange);
    return () => mediaQuery.removeListener(handleChange);
  }, []);

  useEffect(() => {
    sessionRef.current = session;
  }, [session]);

  useEffect(() => {
    if (!session?.username || !browserDesktopNotificationsSupported()) {
      return;
    }

    if (window.Notification.permission !== "default") {
      return;
    }

    const promptStorageKey = getAdminDesktopNotificationPromptStorageKey(session.username);
    if (window.localStorage.getItem(promptStorageKey) === "1") {
      return;
    }

    window.localStorage.setItem(promptStorageKey, "1");
    void window.Notification.requestPermission().catch(() => undefined);
  }, [session?.username]);

  const searchMatchedConsoleTickets = scopedConsoleTickets.filter((ticket) => {
    if (!normalizedConsoleSearch) {
      return true;
    }

    const searchableFields = [
      ticket.id,
      getDisplayedChatReference(ticket),
      ticket.learnerName,
      ticket.email,
      formatRequesterRoleLabel(ticket.requesterRole),
      ticket.category,
      ticket.technicalSubcategory,
      ticket.inquiryPreview,
    ];

    return searchableFields.some((fieldValue) => {
      const normalizedFieldValue = normalizeConsoleSearchValue(fieldValue);
      if (normalizedFieldValue.includes(normalizedConsoleSearch)) {
        return true;
      }

      return compactConsoleSearchValue(normalizedFieldValue).includes(compactConsoleSearch);
    });
  });
  const searchFilteredConsoleTickets = searchMatchedConsoleTickets.filter((ticket) => (
    consoleSearchStatusFilter === "all"
      ? true
      : consoleSearchStatusFilter === "open"
        ? ticket.chatState !== "closed"
        : ticket.chatState === "closed"
  ));
  const searchResultConsoleTickets = !normalizedConsoleSearch
    ? []
    : consoleSearchStatusFilter === "all"
      ? sortConsoleSearchResults(searchFilteredConsoleTickets)
      : sortConsoleTickets(searchFilteredConsoleTickets, consoleSearchStatusFilter);
  const visibleOpenConsoleTickets = openConsoleQueueTickets;
  const visibleClosedConsoleTickets = closedConsoleQueueTickets;
  const hasVisibleOpenConsoleQueue = visibleOpenConsoleTickets.length > 0;
  const activeConsoleQueueTickets = consoleQueueTab === "open"
    ? visibleOpenConsoleTickets
    : visibleClosedConsoleTickets;
  const myOpenConsoleQueueTickets = tickets.filter((ticket) => {
    if (isQuickResolutionTicket(ticket)) {
      return false;
    }

    if (!ticket.chatIsActive || !ticket.liveChatRequested || ticket.chatState === "closed") {
      return false;
    }

    return ticket.assignedAgentId === resolvedSessionAgentId;
  });
  const myOpenChatCount = myOpenConsoleQueueTickets.length;
  // Keep admin availability tied to the signed-in admin's own live queue.
  // The All Cases tab may still surface other admins' chats for review.
  const hasCurrentAdminOpenConsoleQueue = myOpenConsoleQueueTickets.length > 0;
  const myOpenChatCardToneClassName = myOpenChatCount === 0
    ? "border-emerald-200 bg-emerald-50/90"
    : "border-red-200 bg-red-50/90";

  function openAdminNotificationsFromDesktopAlert() {
    if (typeof window !== "undefined") {
      window.focus();
    }

    setAdminView("dashboard");
    setIsTransferNotificationsOpen(true);
  }

  function showAdminDesktopNotification(key: string, title: string, body: string) {
    if (!shouldDispatchAdminDesktopNotification()) {
      return;
    }

    try {
      const notification = new window.Notification(title, {
        body,
        tag: `support-admin:${key}`,
        icon: "/kent-crest.svg",
        requireInteraction: true,
      });

      notification.onclick = () => {
        notification.close();
        openAdminNotificationsFromDesktopAlert();
      };
    } catch {
      // Ignore browser notification failures so in-app alerts still work.
    }
  }

  const myActualConsoleStatus = signedInAgent
    ? normalizeAdminConsoleStatus(signedInAgent.consoleStatus)
    : normalizeAdminConsoleStatus(hasCurrentAdminOpenConsoleQueue ? "Busy" : (consoleStatus || "Off"));
  const consoleAvailabilityEmptyMessage = !hasCurrentAdminOpenConsoleQueue && consoleCaseScope === "all" && hasVisibleOpenConsoleQueue
    ? "Your queue is clear right now. All Cases can still show chats assigned to other admins."
    : "Your queue is clear right now. New chats will appear here as soon as they become available.";
  const sortedAgents = [...activeAgents].sort((leftAgent, rightAgent) => {
    const leftStatusRank = getAgentConsoleStatusRank(normalizeAdminConsoleStatus(leftAgent.consoleStatus));
    const rightStatusRank = getAgentConsoleStatusRank(normalizeAdminConsoleStatus(rightAgent.consoleStatus));

    if (leftStatusRank !== rightStatusRank) {
      return leftStatusRank - rightStatusRank;
    }

    return getAgentDisplayName(leftAgent).localeCompare(getAgentDisplayName(rightAgent), undefined, { sensitivity: "base" });
  });
  const selectedDraftAgent = sortedAgents.find((agent) => String(agent.id) === draftAgentId) || null;
  const availableAgentCount = sortedAgents.filter((agent) => normalizeAdminConsoleStatus(agent.consoleStatus) === "Available").length;
  const busyAgentCount = sortedAgents.filter((agent) => normalizeAdminConsoleStatus(agent.consoleStatus) === "Busy").length;
  const offAgentCount = sortedAgents.filter((agent) => normalizeAdminConsoleStatus(agent.consoleStatus) === "Off").length;
  const dashboardAgentFilterOptions = [
    { value: "all" as DashboardAssignedFilter, label: isCoverageDashboardView ? "All Coverage Tickets" : "All Tickets" },
    ...(dashboardSessionAgentId ? [{ value: "me" as DashboardAssignedFilter, label: "Me" }] : []),
    { value: "unassigned" as DashboardAssignedFilter, label: "Unassigned" },
    ...sortedAgents
      .filter((agent) => agent.id !== dashboardSessionAgentId)
      .map((agent) => ({
        value: buildDashboardAssignedAgentFilterValue(agent.id),
        label: getAgentDisplayName(agent),
      })),
  ];
  const assignableAdminAgents = sortedAgents.filter((agent) => (agent.role || "").toLowerCase() === "admin");
  const dashboardBaseTickets = isCoverageDashboardView
    ? tickets.filter((ticket) => isCoverageTicket(ticket))
    : tickets;
  const dashboardAssignmentScopedTickets = filterDashboardTicketsByAssignee(
    dashboardBaseTickets,
    dashboardAssignedFilter,
    dashboardSessionAgentId,
  );
  const quickResolutionTickets = dashboardAssignmentScopedTickets.filter(isDashboardQuickResolutionTicket);
  const scopedDashboardTickets = filterDashboardTickets(dashboardAssignmentScopedTickets, dashboardTicketFilter);
  const visibleDashboardTickets = [...scopedDashboardTickets]
    .filter((ticket) => {
      if (!normalizedDashboardSearch) {
        return true;
      }

      const searchableFields = [
        getDisplayedChatReference(ticket),
        ticket.id,
        ticket.learnerName,
        ticket.email,
        formatRequesterRoleLabel(ticket.requesterRole),
      ];

      return searchableFields.some((fieldValue) => {
        const normalizedFieldValue = normalizeConsoleSearchValue(fieldValue);
        if (normalizedFieldValue.includes(normalizedDashboardSearch)) {
          return true;
        }

        return compactConsoleSearchValue(normalizedFieldValue).includes(compactDashboardSearch);
      });
    })
    .sort((leftTicket, rightTicket) => {
      if (dashboardSortOrder === "priorityDesc") {
        const lifecycleDifference = compareTicketLifecycleRank(leftTicket, rightTicket);
        if (lifecycleDifference !== 0) {
          return lifecycleDifference;
        }

        const priorityDifference = compareTicketPriority(leftTicket, rightTicket);
        if (priorityDifference !== 0) {
          return priorityDifference;
        }
      }

      if (dashboardSortOrder === "priorityAsc") {
        const lifecycleDifference = compareTicketLifecycleRank(leftTicket, rightTicket);
        if (lifecycleDifference !== 0) {
          return -lifecycleDifference;
        }

        const priorityDifference = compareTicketPriority(leftTicket, rightTicket);
        if (priorityDifference !== 0) {
          return -priorityDifference;
        }
      }

      const leftTimestamp = getDashboardTicketSortTimestamp(leftTicket);
      const rightTimestamp = getDashboardTicketSortTimestamp(rightTicket);
      return dashboardSortOrder === "oldest"
        ? leftTimestamp - rightTimestamp
        : rightTimestamp - leftTimestamp;
    });
  const dashboardTableTitle = dashboardTicketFilter === "all" && isCoverageDashboardView
    ? "Coverage Tickets"
    : getDashboardTableTitle(dashboardTicketFilter);
  const dashboardAssignedFilterLabel = getDashboardAssignedFilterLabel(
    dashboardAssignedFilter,
    dashboardSessionAgentName,
    sortedAgents,
  );
  const dashboardAssignedFilterEmptyTarget = getDashboardAssignedFilterEmptyTargetLabel(
    dashboardAssignedFilter,
    dashboardSessionAgentName,
    sortedAgents,
  );
  const dashboardTableCountLabel = getDashboardTableCountLabel(
    dashboardTicketFilter,
    visibleDashboardTickets.length,
    scopedDashboardTickets.length,
    dashboardAssignmentScopedTickets.length,
    dashboardBaseTickets.length,
    Boolean(normalizedDashboardSearch),
    dashboardAssignedFilter !== "all",
    dashboardAssignedFilterLabel,
  );
  const dashboardEmptyMessage = normalizedDashboardSearch
    ? "No matching tickets found for this search."
    : dashboardAssignedFilter !== "all"
      ? getDashboardAssignedFilterEmptyMessage(dashboardTicketFilter, dashboardAssignedFilterEmptyTarget)
      : isCoverageDashboardView && dashboardTicketFilter === "all"
        ? "No coverage tickets have been created yet."
        : getDashboardEmptyMessage(dashboardTicketFilter);
  const isConsoleOwnedBySignedInAgent = Boolean(
    consoleDetail
    && resolvedSessionAgentId
    && consoleDetail.ticket.assignedAgentId === resolvedSessionAgentId
  );
  const canAssignActiveTicket = Boolean(
    isSuperadminSession
    && activeDetail,
  );
  const isActiveTicketAlreadyAssigned = Boolean(activeDetail?.ticket.assignedAgentId);
  const canForceCloseConsoleChat = Boolean(consoleDetail)
    && consoleDetail.ticket.status === "Closed"
    && consoleDetail.ticket.chatState !== "closed";
  const transferTargetAgents = sortedAgents.filter((agent) => agent.id !== consoleDetail?.ticket.assignedAgentId);
  const pendingTransferRequests = tickets
    .filter((ticket) => {
      const pendingTransferRequest = ticket.pendingTransferRequest;
      if (!pendingTransferRequest) {
        return false;
      }

      if (resolvedSessionAgentId) {
        return pendingTransferRequest.toAgentId === resolvedSessionAgentId;
      }

      return sanitizeAssignedAgentName(pendingTransferRequest.toAgentUsername) === sanitizeAssignedAgentName(session?.username || "");
    })
    .sort((leftTicket, rightTicket) => {
      const leftRequestedAt = Date.parse(leftTicket.pendingTransferRequest?.requestedAt || "");
      const rightRequestedAt = Date.parse(rightTicket.pendingTransferRequest?.requestedAt || "");
      return (Number.isNaN(rightRequestedAt) ? 0 : rightRequestedAt) - (Number.isNaN(leftRequestedAt) ? 0 : leftRequestedAt);
    });
  const pendingEscalationNotifications = tickets
    .filter((ticket) => {
      const pendingEscalationNotification = ticket.pendingEscalationNotification;
      if (!pendingEscalationNotification) {
        return false;
      }

      if (resolvedSessionAgentId) {
        return pendingEscalationNotification.toAgentId === resolvedSessionAgentId;
      }

      return sanitizeAssignedAgentName(pendingEscalationNotification.toAgentUsername) === sanitizeAssignedAgentName(session?.username || "");
    })
    .sort((leftTicket, rightTicket) => {
      const leftRequestedAt = Date.parse(leftTicket.pendingEscalationNotification?.requestedAt || "");
      const rightRequestedAt = Date.parse(rightTicket.pendingEscalationNotification?.requestedAt || "");
      return (Number.isNaN(rightRequestedAt) ? 0 : rightRequestedAt) - (Number.isNaN(leftRequestedAt) ? 0 : leftRequestedAt);
    });
  const pendingTeamsCallNotifications = tickets
    .filter((ticket) => {
      const pendingTeamsCallNotification = ticket.pendingTeamsCallNotification;
      if (!pendingTeamsCallNotification) {
        return false;
      }

      if (resolvedSessionAgentId) {
        return pendingTeamsCallNotification.toAgentId === resolvedSessionAgentId;
      }

      return sanitizeAssignedAgentName(pendingTeamsCallNotification.toAgentUsername) === sanitizeAssignedAgentName(session?.username || "");
    })
    .sort((leftTicket, rightTicket) => {
      const leftRequestedAt = Date.parse(leftTicket.pendingTeamsCallNotification?.requestedAt || "");
      const rightRequestedAt = Date.parse(rightTicket.pendingTeamsCallNotification?.requestedAt || "");
      return (Number.isNaN(rightRequestedAt) ? 0 : rightRequestedAt) - (Number.isNaN(leftRequestedAt) ? 0 : leftRequestedAt);
    });
  const waitingLiveChatNotifications = myActualConsoleStatus === "Off"
    ? tickets
      .filter((ticket) => (
        ticket.liveChatRequested
        && ticket.chatState !== "closed"
        && ticket.status !== "Closed"
        && !ticket.assignedAgentId
      ))
      .sort((leftTicket, rightTicket) => {
        const leftRequestedAt = Date.parse(leftTicket.liveChatRequestedAt || "");
        const rightRequestedAt = Date.parse(rightTicket.liveChatRequestedAt || "");
        return (Number.isNaN(rightRequestedAt) ? 0 : rightRequestedAt) - (Number.isNaN(leftRequestedAt) ? 0 : leftRequestedAt);
      })
    : [];
  const transferDecisionNotifications = tickets
    .filter((ticket) => {
      const latestTransferDecision = ticket.latestTransferDecision;
      if (!latestTransferDecision || latestTransferDecision.requesterAcknowledged) {
        return false;
      }

      if (resolvedSessionAgentId) {
        return latestTransferDecision.fromAgentId === resolvedSessionAgentId;
      }

      return sanitizeAssignedAgentName(latestTransferDecision.fromAgentUsername) === sanitizeAssignedAgentName(session?.username || "");
    })
    .sort((leftTicket, rightTicket) => {
      const leftDecidedAt = Date.parse(leftTicket.latestTransferDecision?.decidedAt || "");
      const rightDecidedAt = Date.parse(rightTicket.latestTransferDecision?.decidedAt || "");
      return (Number.isNaN(rightDecidedAt) ? 0 : rightDecidedAt) - (Number.isNaN(leftDecidedAt) ? 0 : leftDecidedAt);
    });
  const escalationClosureNotifications = tickets
    .filter((ticket) => {
      const latestEscalationClosure = ticket.latestEscalationClosure;
      if (!latestEscalationClosure || latestEscalationClosure.requesterAcknowledged) {
        return false;
      }

      if (resolvedSessionAgentId) {
        return latestEscalationClosure.fromAgentId === resolvedSessionAgentId;
      }

      return sanitizeAssignedAgentName(latestEscalationClosure.fromAgentUsername) === sanitizeAssignedAgentName(session?.username || "");
    })
    .sort((leftTicket, rightTicket) => {
      const leftClosedAt = Date.parse(leftTicket.latestEscalationClosure?.closedAt || "");
      const rightClosedAt = Date.parse(rightTicket.latestEscalationClosure?.closedAt || "");
      return (Number.isNaN(rightClosedAt) ? 0 : rightClosedAt) - (Number.isNaN(leftClosedAt) ? 0 : leftClosedAt);
    });
  const coverageTutorResponseNotifications = tickets
    .filter((ticket) => {
      const latestCoverageTutorResponse = ticket.latestCoverageTutorResponse;
      if (!latestCoverageTutorResponse || latestCoverageTutorResponse.requesterAcknowledged) {
        return false;
      }

      if (resolvedSessionAgentId) {
        return latestCoverageTutorResponse.toAgentId === resolvedSessionAgentId;
      }

      return sanitizeAssignedAgentName(latestCoverageTutorResponse.toAgentUsername) === sanitizeAssignedAgentName(session?.username || "");
    })
    .sort((leftTicket, rightTicket) => {
      const leftRespondedAt = Date.parse(leftTicket.latestCoverageTutorResponse?.respondedAt || "");
      const rightRespondedAt = Date.parse(rightTicket.latestCoverageTutorResponse?.respondedAt || "");
      return (Number.isNaN(rightRespondedAt) ? 0 : rightRespondedAt) - (Number.isNaN(leftRespondedAt) ? 0 : leftRespondedAt);
    });
  const coverageTicketNotifications = tickets
    .filter((ticket) => Boolean(ticket.pendingCoverageTicketNotification))
    .sort((leftTicket, rightTicket) => {
      const leftCreatedAt = Date.parse(leftTicket.pendingCoverageTicketNotification?.createdAt || leftTicket.createdAt || "");
      const rightCreatedAt = Date.parse(rightTicket.pendingCoverageTicketNotification?.createdAt || rightTicket.createdAt || "");
      return (Number.isNaN(rightCreatedAt) ? 0 : rightCreatedAt) - (Number.isNaN(leftCreatedAt) ? 0 : leftCreatedAt);
    });
  const totalAdminNotificationCount = pendingTransferRequests.length
    + pendingEscalationNotifications.length
    + pendingTeamsCallNotifications.length
    + waitingLiveChatNotifications.length
    + transferDecisionNotifications.length
    + escalationClosureNotifications.length
    + coverageTicketNotifications.length
    + coverageTutorResponseNotifications.length;
  const archivedNotificationLog = notificationLog
    .filter((item) => !item.isCurrent)
    .slice(0, 12);
  const liveChatLocked = Boolean(consoleDetail) && (
    consoleDetail.ticket.status === "Closed" || consoleDetail.ticket.chatState === "closed"
  );
  const consoleWorkspaceReadOnly = Boolean(consoleDetail) && (
    consoleCaseScope === "all"
    || !isConsoleOwnedBySignedInAgent
    || liveChatLocked
  );
  const consoleWorkspaceReadOnlyMessage = !consoleDetail
    ? ""
    : canForceCloseConsoleChat
      ? "This ticket is already closed, but the live chat is still open. Use Force Close Chat to finalize it."
      : consoleCaseScope === "all"
      ? "All Cases is view-only. Switch to My Cases to reply, document, or use the AI assistant."
      : !isConsoleOwnedBySignedInAgent
        ? `This case is assigned to ${consoleDetail.ticket.assignedAgentName || "another agent"}.`
        : liveChatLocked
          ? "This case is closed, so the workspace is now view-only."
          : "";
  const consoleTransferHandoffNotice = consoleDetail
    && resolvedSessionAgentId
    && consoleDetail.ticket.assignedAgentId === resolvedSessionAgentId
    ? getLatestTransferHandoffNotice(consoleDetail.history, consoleDetail.ticket.assignedAgentName)
    : null;
  const hasConsoleWorkspaceBanner = Boolean(consoleWorkspaceReadOnlyMessage || consoleTransferHandoffNotice);
  const canTransferConsoleTicket = Boolean(consoleDetail)
    && !consoleWorkspaceReadOnly
    && !consoleDetail.ticket.pendingTransferRequest
    && transferTargetAgents.length > 0;
  const isDocumentationReadOnly = Boolean(consoleDetail) && (
    consoleWorkspaceReadOnly
    || consoleDetail.ticket.status === "Closed"
  );
  const adminCanReplyToLiveChat = Boolean(consoleDetail?.ticket.liveChatRequested) && !consoleWorkspaceReadOnly;
  const activeAiThread = consoleDetail ? (aiThreads[consoleDetail.ticket.id] || []) : [];
  const documentationAutoStatusReason = !isDocumentationReadOnly
    ? getAutomaticDocumentationStatusReason(documentationTicketStatus)
    : "";
  const documentationResolvedStatusReason = documentationAutoStatusReason || documentationStatusReason;
  const documentationRequiresEscalationAssignee = documentationResolvedStatusReason === "Escalation";
  const documentationEscalationTargetAgents = sortedAgents.filter((agent) => agent.id !== consoleDetail?.ticket.assignedAgentId);
  const selectedDocumentationEscalationAgent = documentationEscalationTargetAgents.find(
    (agent) => String(agent.id) === documentationEscalationAgentId,
  ) || sortedAgents.find((agent) => String(agent.id) === documentationEscalationAgentId) || null;
  const documentationEscalationAssigneeLabel = documentationRequiresEscalationAssignee
    ? (selectedDocumentationEscalationAgent
      ? getAgentDisplayName(selectedDocumentationEscalationAgent)
      : (documentationDraft?.escalationAgentName || ""))
    : "";
  const documentationStatusReasonsForSelection = documentationTicketStatus && !documentationAutoStatusReason
    ? [...documentationStatusReasons[documentationTicketStatus]]
    : [];
  const documentationPageOneDirty = Boolean(consoleDetail && documentationDraft)
    && JSON.stringify(documentationDraft) !== JSON.stringify(normalizeDocumentationDraft(consoleDetail.ticket.documentation));
  const documentationPageTwoDirty = Boolean(consoleDetail) && (
    documentationTicketStatus !== deriveDocumentationTicketStatus(consoleDetail.ticket.status)
    || normalizeQuickTicketStatusReason(documentationResolvedStatusReason) !== normalizeQuickTicketStatusReason(consoleDetail.ticket.statusReason || "")
    || documentationEscalationAgentId !== deriveDocumentationEscalationAgentId(consoleDetail.ticket)
    || documentationEscalationNote !== deriveDocumentationEscalationNote(consoleDetail.ticket.documentation)
  );
  const documentationPageThreeDirty = Boolean(consoleDetail) && (
    documentationIssuesAddressed !== deriveDocumentationIssuesAddressed(
      consoleDetail.ticket.chatState,
      consoleDetail.ticket.documentation,
    )
  );
  const documentationWorkflowDirty = documentationPageOneDirty || documentationPageTwoDirty || documentationPageThreeDirty;
  const canMoveDocumentationForward = (
    documentationStep === 1
      ? true
      : documentationStep === 2
        ? Boolean(
          documentationTicketStatus
          && documentationResolvedStatusReason
          && (!documentationRequiresEscalationAssignee || (documentationEscalationAgentId && documentationEscalationNote.trim())),
        )
        : Boolean(documentationIssuesAddressed)
  );
  const consoleDurationStart = consoleDetail ? getConsoleDurationStartInfo(consoleDetail.ticket) : null;
  const persistedConsoleDurationMinutes = consoleDetail?.ticket.chatDurationMinutes ?? 0;
  const consoleDurationLabel = !consoleDetail
    ? ""
    : consoleDetail.ticket.chatState === "closed"
      ? formatConsoleDurationFromMinutes(persistedConsoleDurationMinutes)
      : consoleDurationStart
        ? formatConsoleDuration(
            consoleDurationStart.startedAt,
            getConsoleDurationEndTimestamp(consoleDetail.ticket, consoleTimerNow),
          )
        : "";

  useEffect(() => {
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  function isCurrentDashboardSession(expectedSession: AdminSession | null = sessionRef.current) {
    if (!isMountedRef.current) {
      return false;
    }

    if (!expectedSession?.username || !expectedSession.instanceId) {
      return true;
    }

    const currentSession = sessionRef.current;
    return Boolean(currentSession && isSameAdminSession(currentSession, expectedSession));
  }

  useEffect(() => {
    void loadDashboard();
  }, []);

  useEffect(() => {
    if (!session?.username || !session.instanceId) {
      return;
    }

    if (!consoleStatus) {
      return;
    }

    void syncAgentSessionHeartbeat(true);

    const intervalId = window.setInterval(() => {
      void syncAgentSessionHeartbeat(true);
    }, 30000);

    return () => window.clearInterval(intervalId);
  }, [consoleStatus, session?.instanceId, session?.username]);

  useEffect(() => {
    if (adminView !== "console") {
      return;
    }

    if (consoleTicketId && !activeConsoleQueueTickets.some((ticket) => ticket.id === consoleTicketId)) {
      setConsoleTicketId("");
      setConsoleDetail(null);
    }
  }, [activeConsoleQueueTickets, adminView, consoleTicketId]);

  useEffect(() => {
    if (!consoleDetail) {
      setDocumentationDraft(null);
      setDocumentationStep(1);
      setDocumentationTicketStatus("");
      setDocumentationStatusReason("");
      setDocumentationEscalationAgentId("");
      setDocumentationEscalationNote("");
      setDocumentationIssuesAddressed("");
      setConsoleChatInput("");
      setConsoleAiInput("");
      return;
    }

    const nextDocumentationStatusReason = consoleDetail.ticket.statusReason || "";
    setDocumentationDraft(normalizeDocumentationDraft(consoleDetail.ticket.documentation));
    setDocumentationStep(1);
    setDocumentationTicketStatus(deriveDocumentationTicketStatus(consoleDetail.ticket.status));
    setDocumentationStatusReason(nextDocumentationStatusReason);
    setDocumentationEscalationAgentId(deriveDocumentationEscalationAgentId(consoleDetail.ticket));
    setDocumentationEscalationNote(deriveDocumentationEscalationNote(consoleDetail.ticket.documentation));
    setDocumentationIssuesAddressed(
      deriveDocumentationIssuesAddressed(consoleDetail.ticket.chatState, consoleDetail.ticket.documentation),
    );
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
    if (!activeDetail) {
      setActiveDocumentationDraft(null);
      return;
    }

    if (isCoverageTicket(activeDetail.ticket)) {
      setActiveDocumentationDraft(buildCoverageDocumentationDraft(activeDetail.ticket));
      return;
    }

    setActiveDocumentationDraft(buildStandardDocumentationDraft(activeDetail.ticket));
  }, [activeDetail?.ticket.id, activeDetail?.ticket.updatedAt, activeDetail?.ticket.technicalSubcategory]);

  useEffect(() => {
    if (adminView !== "console" || !consoleDetail) {
      previousConsoleChatStateRef.current = null;
      return;
    }

    const currentConsoleChatState = {
      ticketId: consoleDetail.ticket.id,
      chatState: consoleDetail.ticket.chatState,
    };
    const previousConsoleChatState = previousConsoleChatStateRef.current;

    if (
      previousConsoleChatState
      && previousConsoleChatState.ticketId === currentConsoleChatState.ticketId
      && previousConsoleChatState.chatState !== "closed"
      && currentConsoleChatState.chatState === "closed"
    ) {
      previousConsoleChatStateRef.current = null;
      collapseConsoleWorkspace();
      return;
    }

    previousConsoleChatStateRef.current = currentConsoleChatState;
  }, [adminView, consoleDetail]);

  useEffect(() => {
    setIsTransferMenuOpen(false);
    setTransferReason("");
  }, [consoleDetail?.ticket.id]);

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
    if (!isDashboardLikeView) {
      return;
    }

    const ticketsIntervalId = window.setInterval(() => {
      void refreshTicketsOnly(true);
    }, dashboardTicketPollIntervalMs);

    const agentsIntervalId = window.setInterval(() => {
      void refreshAgentsOnly(true);
    }, dashboardAgentPollIntervalMs);

    return () => {
      window.clearInterval(ticketsIntervalId);
      window.clearInterval(agentsIntervalId);
    };
  }, [isDashboardLikeView]);

  useEffect(() => {
    if (!canManageUsers && adminView === "management") {
      setAdminView("dashboard");
    }
  }, [adminView, canManageUsers]);

  useEffect(() => {
    const nextNotificationKeys = new Set<string>();
    const newCoverageTickets: TicketSummary[] = [];
    const newTransferRequests: TicketSummary[] = [];
    const newEscalationNotifications: TicketSummary[] = [];
    const newTeamsCallNotifications: TicketSummary[] = [];
    const newWaitingLiveChatNotifications: TicketSummary[] = [];
    const newTransferDecisions: TicketSummary[] = [];
    const newEscalationClosures: TicketSummary[] = [];
    const newCoverageTutorResponses: TicketSummary[] = [];

    for (const ticket of coverageTicketNotifications) {
      const pendingCoverageTicketNotification = ticket.pendingCoverageTicketNotification;
      if (!pendingCoverageTicketNotification) {
        continue;
      }

      const notificationKey = `coverage-ticket:${ticket.id}:${pendingCoverageTicketNotification.createdAt}`;
      nextNotificationKeys.add(notificationKey);
      if (!seenTransferNotificationKeysRef.current.has(notificationKey)) {
        newCoverageTickets.push(ticket);
      }
    }

    for (const ticket of pendingTransferRequests) {
      const pendingTransferRequest = ticket.pendingTransferRequest;
      if (!pendingTransferRequest) {
        continue;
      }

      const notificationKey = `request:${ticket.id}:${pendingTransferRequest.requestedAt}:${pendingTransferRequest.toAgentId}`;
      nextNotificationKeys.add(notificationKey);
      if (!seenTransferNotificationKeysRef.current.has(notificationKey)) {
        newTransferRequests.push(ticket);
      }
    }

    for (const ticket of pendingEscalationNotifications) {
      const pendingEscalationNotification = ticket.pendingEscalationNotification;
      if (!pendingEscalationNotification) {
        continue;
      }

      const notificationKey = `escalation:${ticket.id}:${pendingEscalationNotification.requestedAt}:${pendingEscalationNotification.toAgentId}`;
      nextNotificationKeys.add(notificationKey);
      if (!seenTransferNotificationKeysRef.current.has(notificationKey)) {
        newEscalationNotifications.push(ticket);
      }
    }

    for (const ticket of pendingTeamsCallNotifications) {
      const pendingTeamsCallNotification = ticket.pendingTeamsCallNotification;
      if (!pendingTeamsCallNotification) {
        continue;
      }

      const notificationKey = `teams-call:${ticket.id}:${pendingTeamsCallNotification.requestedAt}:${pendingTeamsCallNotification.toAgentId}`;
      nextNotificationKeys.add(notificationKey);
      if (!seenTransferNotificationKeysRef.current.has(notificationKey)) {
        newTeamsCallNotifications.push(ticket);
      }
    }

    for (const ticket of waitingLiveChatNotifications) {
      const notificationKey = `waiting-live-chat:${ticket.id}:${ticket.liveChatRequestedAt || ticket.createdAt}`;
      nextNotificationKeys.add(notificationKey);
      if (!seenTransferNotificationKeysRef.current.has(notificationKey)) {
        newWaitingLiveChatNotifications.push(ticket);
      }
    }

    for (const ticket of transferDecisionNotifications) {
      const latestTransferDecision = ticket.latestTransferDecision;
      if (!latestTransferDecision) {
        continue;
      }

      const notificationKey = `decision:${ticket.id}:${latestTransferDecision.status}:${latestTransferDecision.decidedAt}`;
      nextNotificationKeys.add(notificationKey);
      if (!seenTransferNotificationKeysRef.current.has(notificationKey)) {
        newTransferDecisions.push(ticket);
      }
    }

    for (const ticket of escalationClosureNotifications) {
      const latestEscalationClosure = ticket.latestEscalationClosure;
      if (!latestEscalationClosure) {
        continue;
      }

      const notificationKey = `escalation-closed:${ticket.id}:${latestEscalationClosure.closedAt}:${latestEscalationClosure.fromAgentId}`;
      nextNotificationKeys.add(notificationKey);
      if (!seenTransferNotificationKeysRef.current.has(notificationKey)) {
        newEscalationClosures.push(ticket);
      }
    }

    for (const ticket of coverageTutorResponseNotifications) {
      const latestCoverageTutorResponse = ticket.latestCoverageTutorResponse;
      if (!latestCoverageTutorResponse) {
        continue;
      }

      const notificationKey = `coverage-response:${ticket.id}:${latestCoverageTutorResponse.cardId}:${latestCoverageTutorResponse.respondedAt}`;
      nextNotificationKeys.add(notificationKey);
      if (!seenTransferNotificationKeysRef.current.has(notificationKey)) {
        newCoverageTutorResponses.push(ticket);
      }
    }

    if (!hasHydratedTransferNotificationsRef.current) {
      seenTransferNotificationKeysRef.current = nextNotificationKeys;
      hasHydratedTransferNotificationsRef.current = true;
      return;
    }

    for (const ticket of newCoverageTickets) {
      const pendingCoverageTicketNotification = ticket.pendingCoverageTicketNotification;
      if (!pendingCoverageTicketNotification) {
        continue;
      }

      toast.info(
        `New coverage ticket ${ticket.id} created for ${pendingCoverageTicketNotification.requesterName || ticket.learnerName || ticket.email || "requester"}.`,
      );
      showAdminDesktopNotification(
        `coverage-ticket:${ticket.id}:${pendingCoverageTicketNotification.createdAt}`,
        "New Coverage Ticket",
        `${ticket.id} • ${pendingCoverageTicketNotification.requesterName || ticket.learnerName || ticket.email || "Requester"}`,
      );
    }

    for (const ticket of newTransferRequests) {
      const pendingTransferRequest = ticket.pendingTransferRequest;
      if (!pendingTransferRequest) {
        continue;
      }

      toast.info(`New transfer request for ${ticket.id} from ${pendingTransferRequest.fromAgentName}.`);
      showAdminDesktopNotification(
        `request:${ticket.id}:${pendingTransferRequest.requestedAt}:${pendingTransferRequest.toAgentId}`,
        "New Transfer Request",
        `${ticket.id} from ${pendingTransferRequest.fromAgentName}.`,
      );
    }

    for (const ticket of newEscalationNotifications) {
      const pendingEscalationNotification = ticket.pendingEscalationNotification;
      if (!pendingEscalationNotification) {
        continue;
      }

      toast.info(`Escalation notice received for ${pendingEscalationNotification.ticketId} from ${pendingEscalationNotification.fromAgentName}.`);
      showAdminDesktopNotification(
        `escalation:${ticket.id}:${pendingEscalationNotification.requestedAt}:${pendingEscalationNotification.toAgentId}`,
        "Escalation Notice",
        `${pendingEscalationNotification.ticketId} from ${pendingEscalationNotification.fromAgentName}.`,
      );
    }

    for (const ticket of newTeamsCallNotifications) {
      const pendingTeamsCallNotification = ticket.pendingTeamsCallNotification;
      if (!pendingTeamsCallNotification) {
        continue;
      }

      toast.info(
        `Teams call request received for ${pendingTeamsCallNotification.ticketId} from ${pendingTeamsCallNotification.requesterName}.`,
      );
      showAdminDesktopNotification(
        `teams-call:${ticket.id}:${pendingTeamsCallNotification.requestedAt}:${pendingTeamsCallNotification.toAgentId}`,
        "Teams Call Request",
        `${pendingTeamsCallNotification.ticketId} from ${pendingTeamsCallNotification.requesterName}.`,
      );
    }

    for (const ticket of newWaitingLiveChatNotifications) {
      toast.info(
        `Live chat is waiting for an available admin for ${ticket.id} (${ticket.learnerName || ticket.email || "Learner"}).`,
      );
      showAdminDesktopNotification(
        `waiting-live-chat:${ticket.id}:${ticket.liveChatRequestedAt || ticket.createdAt}`,
        "Waiting Live Chat",
        `${ticket.id} is waiting for an available admin.`,
      );
    }

    for (const ticket of newTransferDecisions) {
      const latestTransferDecision = ticket.latestTransferDecision;
      if (!latestTransferDecision) {
        continue;
      }

      toast.info(
        latestTransferDecision.status === "accepted"
          ? `Transfer accepted for ${ticket.id} by ${latestTransferDecision.decidedByName}.`
          : `Transfer declined for ${ticket.id} by ${latestTransferDecision.decidedByName}.`,
      );
      showAdminDesktopNotification(
        `decision:${ticket.id}:${latestTransferDecision.status}:${latestTransferDecision.decidedAt}`,
        latestTransferDecision.status === "accepted" ? "Transfer Accepted" : "Transfer Declined",
        `${ticket.id} by ${latestTransferDecision.decidedByName}.`,
      );
    }

    for (const ticket of newEscalationClosures) {
      const latestEscalationClosure = ticket.latestEscalationClosure;
      if (!latestEscalationClosure) {
        continue;
      }

      toast.info(`Escalated ticket ${latestEscalationClosure.ticketId} was closed by ${latestEscalationClosure.closedByName}.`);
      showAdminDesktopNotification(
        `escalation-closed:${ticket.id}:${latestEscalationClosure.closedAt}:${latestEscalationClosure.fromAgentId}`,
        "Escalated Ticket Closed",
        `${latestEscalationClosure.ticketId} was closed by ${latestEscalationClosure.closedByName}.`,
      );
    }

    for (const ticket of newCoverageTutorResponses) {
      const latestCoverageTutorResponse = ticket.latestCoverageTutorResponse;
      if (!latestCoverageTutorResponse) {
        continue;
      }

      const wasAccepted = latestCoverageTutorResponse.outcome === "accepted";
      toast.info(
        wasAccepted
          ? `Tutor accepted coverage session for ${ticket.id}. The ticket was closed automatically.`
          : `Tutor refused coverage session for ${ticket.id}.`,
      );
      showAdminDesktopNotification(
        `coverage-response:${ticket.id}:${latestCoverageTutorResponse.cardId}:${latestCoverageTutorResponse.respondedAt}`,
        wasAccepted ? "Tutor Accepted • Ticket Closed" : "Tutor Refused",
        `${ticket.id} • ${latestCoverageTutorResponse.tutor}`,
      );
    }

    if (
      newCoverageTickets.length > 0
      || newTransferRequests.length > 0
      || newEscalationNotifications.length > 0
      || newTeamsCallNotifications.length > 0
      || newWaitingLiveChatNotifications.length > 0
      || newTransferDecisions.length > 0
      || newEscalationClosures.length > 0
      || newCoverageTutorResponses.length > 0
    ) {
      playTransferNotificationSound();
    }

    seenTransferNotificationKeysRef.current = nextNotificationKeys;
  }, [coverageTicketNotifications, coverageTutorResponseNotifications, escalationClosureNotifications, pendingEscalationNotifications, pendingTeamsCallNotifications, pendingTransferRequests, transferDecisionNotifications, waitingLiveChatNotifications]);

  useEffect(() => {
    if (!documentationTicketStatus) {
      if (documentationStatusReason) {
        setDocumentationStatusReason("");
      }
      return;
    }

    if (documentationAutoStatusReason) {
      if (documentationStatusReason !== documentationAutoStatusReason) {
        setDocumentationStatusReason(documentationAutoStatusReason);
      }
      return;
    }

    const allowedReasons = documentationStatusReasons[documentationTicketStatus] as readonly string[];
    if (!allowedReasons.includes(documentationStatusReason)) {
      setDocumentationStatusReason(getDefaultDocumentationStatusReason(documentationTicketStatus));
    }
  }, [documentationAutoStatusReason, documentationStatusReason, documentationTicketStatus]);

  useEffect(() => {
    if (!documentationRequiresEscalationAssignee) {
      if (documentationEscalationAgentId) {
        setDocumentationEscalationAgentId("");
      }
      if (documentationEscalationNote) {
        setDocumentationEscalationNote("");
      }
      return;
    }
  }, [
    documentationEscalationAgentId,
    documentationEscalationNote,
    documentationRequiresEscalationAssignee,
  ]);

  useEffect(() => {
    if (!isConsoleView || !consoleDetail || !consoleDurationStart) {
      return;
    }

    setConsoleTimerNow(Date.now());

    if (consoleDetail.ticket.chatState === "closed") {
      return;
    }

    const intervalId = window.setInterval(() => {
      setConsoleTimerNow(Date.now());
    }, 1000);

    return () => window.clearInterval(intervalId);
  }, [
    isConsoleView,
    consoleDetail?.ticket.id,
    consoleDetail?.ticket.chatState,
    consoleDetail?.ticket.queueAssignedAt,
    consoleDetail?.ticket.liveChatRequestedAt,
    consoleDurationStart?.startedAt,
  ]);

  const kpis = [
    {
      label: "Open Tickets",
      value: dashboardAssignmentScopedTickets.filter(isDashboardOpenTicket).length,
      icon: TicketIcon,
      color: "text-info bg-info/10",
      filter: "open" as const,
    },
    {
      label: "Pending Tickets",
      value: dashboardAssignmentScopedTickets.filter((ticket) => ticket.status === "Pending").length,
      icon: Clock,
      color: "text-warning bg-warning/10",
      filter: "pending" as const,
    },
    {
      label: "Escalation Tickets",
      value: dashboardAssignmentScopedTickets.filter((ticket) => ticket.status === "Pending" && ticket.statusReason === "Escalation").length,
      icon: AlertOctagon,
      color: "text-amber-700 bg-amber-100",
      filter: "escalation" as const,
    },
    {
      label: "Closed Tickets",
      value: dashboardAssignmentScopedTickets.filter((ticket) => ticket.status === "Closed").length,
      icon: CheckCircle2,
      color: "text-success bg-success/10",
      filter: "closed" as const,
    },
    {
      label: "SLA Breaches",
      value: dashboardAssignmentScopedTickets.filter((ticket) => ticket.slaStatus === "Breached").length,
      icon: AlertOctagon,
      color: "bg-rose-100 text-rose-700",
      filter: "slaBreached" as const,
    },
    {
      label: "Coverage Tickets",
      value: dashboardAssignmentScopedTickets.filter((ticket) => isCoverageTicket(ticket)).length,
      icon: FileText,
      color: "bg-primary/10 text-primary",
      filter: "coverage" as const,
    },
  ];

  async function fetchTicketsList() {
    const response = await fetch("/api/admin/tickets", { cache: "no-store" });
    const payload = (await response.json().catch(() => null)) as ListResponse | null;

    if (!response.ok) {
      if ((response.status === 401 || response.status === 403) && await reconcileAdminAuthorizationFailure()) {
        throw new Error("Admin session is required.");
      }
      throw new Error(payload?.message || "We could not load tickets right now.");
    }

    return payload?.tickets || [];
  }

  async function fetchAgentsList() {
    const response = await fetch("/api/admin/accounts");
    const payload = (await response.json().catch(() => null)) as ListResponse | null;

    if (!response.ok) {
      if ((response.status === 401 || response.status === 403) && await reconcileAdminAuthorizationFailure()) {
        throw new Error("Admin session is required.");
      }
      throw new Error(payload?.message || "We could not load support accounts right now.");
    }

    return payload?.accounts || payload?.agents || [];
  }

  async function fetchNotificationLog() {
    if (!sessionRef.current?.username || !sessionRef.current.instanceId) {
      return [];
    }

    const response = await fetch("/api/admin/notifications?limit=20", { cache: "no-store" });
    const payload = (await response.json().catch(() => null)) as NotificationLogResponse | null;

    if (!response.ok) {
      if ((response.status === 401 || response.status === 403) && await reconcileAdminAuthorizationFailure()) {
        throw new Error("Admin session is required.");
      }
      throw new Error(payload?.message || "We could not load the notification log right now.");
    }

    return payload?.notifications || [];
  }

  function syncConsoleStatusFromAgents(nextAgents: AdminAgent[]) {
    if (!isCurrentDashboardSession()) {
      return;
    }

    const signedInAgent = nextAgents.find((agent) => (
      (session?.id && agent.id === session.id)
      || (session?.username && agent.username === session.username)
    ));

    if (!signedInAgent) {
      return;
    }

    const nextStatus = signedInAgent.sessionActive
      ? normalizeAdminSelectableConsoleStatus(signedInAgent.selectedConsoleStatus || signedInAgent.consoleStatus)
      : "Off";

    if (pendingConsoleStatusRef.current && nextStatus !== pendingConsoleStatusRef.current) {
      return;
    }

    if (pendingConsoleStatusRef.current === nextStatus) {
      pendingConsoleStatusRef.current = null;
      setIsUpdatingConsoleStatus(false);
    }

    setConsoleStatus((currentStatus) => currentStatus === nextStatus ? currentStatus : nextStatus);
    if (sessionRef.current) {
      persistAdminSessionState({
        ...sessionRef.current,
        id: sessionRef.current.id || signedInAgent.id,
        username: sessionRef.current.username || signedInAgent.username,
        fullName: sessionRef.current.fullName || signedInAgent.fullName,
        email: sessionRef.current.email ?? signedInAgent.email,
        role: sessionRef.current.role || signedInAgent.role,
        instanceId: sessionRef.current.instanceId || "",
        sessionActive: signedInAgent.sessionActive,
        consoleStatus: normalizeAdminConsoleStatus(signedInAgent.consoleStatus),
        selectedConsoleStatus: nextStatus,
      });
    }
  }

  function filterPendingRemovedAgents(nextAgents: AdminAgent[]) {
    const pendingRemovedAgentIds = pendingRemovedAgentIdsRef.current;
    if (pendingRemovedAgentIds.size === 0) {
      return nextAgents;
    }

    return nextAgents.filter((agent) => !pendingRemovedAgentIds.has(agent.id));
  }

  async function loadDashboard() {
    setIsLoading(true);
    setError("");

    try {
      const requestSession = sessionRef.current;
      const verifiedSession = await revalidateAdminSession({ silent: true });
      if (!verifiedSession || !isCurrentDashboardSession(requestSession)) {
        return;
      }

      const [tickets, nextAgents, migrationStatusResponse, nextNotificationLog] = await Promise.all([
        fetchTicketsList(),
        fetchAgentsList(),
        fetch("/api/migration-status"),
        fetchNotificationLog().catch(() => []),
      ]);
      const migrationStatusPayload = (await migrationStatusResponse.json().catch(() => null)) as MigrationStatusResponse | null;
      if (!isCurrentDashboardSession()) {
        return;
      }
      setTickets(tickets);
      const visibleAgents = filterPendingRemovedAgents(nextAgents);
      setAgents(visibleAgents);
      setNotificationLog(nextNotificationLog);
      syncConsoleStatusFromAgents(visibleAgents);
      setChatbotWorkflowConfigured(
        Boolean(migrationStatusPayload?.adminAiWebhookConfigured ?? migrationStatusPayload?.chatbotWebhookConfigured),
      );
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : "We could not load the dashboard right now.");
    } finally {
      setIsLoading(false);
    }
  }

  async function refreshTicketsOnly(silent = false) {
    try {
      const [nextTickets, nextNotificationLog] = await Promise.all([
        fetchTicketsList(),
        fetchNotificationLog().catch(() => null),
      ]);
      setTickets(nextTickets);
      if (nextNotificationLog !== null) {
        setNotificationLog(nextNotificationLog);
      }

      const currentActiveTicketId = activeDetail?.ticket.id || "";
      if (currentActiveTicketId) {
        const previousActiveTicket = activeDetail?.ticket;
        const nextActiveTicket = nextTickets.find((ticket) => ticket.id === currentActiveTicketId);
        const shouldForceCoverageDetailRefresh = Boolean(previousActiveTicket && isCoverageTicket(previousActiveTicket));
        const coverageResponseChanged = (
          (previousActiveTicket?.latestCoverageTutorResponse?.cardId || "") !== (nextActiveTicket?.latestCoverageTutorResponse?.cardId || "")
          || (previousActiveTicket?.latestCoverageTutorResponse?.respondedAt || "") !== (nextActiveTicket?.latestCoverageTutorResponse?.respondedAt || "")
          || (previousActiveTicket?.latestCoverageTutorResponse?.outcome || "") !== (nextActiveTicket?.latestCoverageTutorResponse?.outcome || "")
        );
        const activeTicketChanged = Boolean(
          nextActiveTicket
          && previousActiveTicket
          && (
            shouldForceCoverageDetailRefresh
            || (
            nextActiveTicket.updatedAt !== previousActiveTicket.updatedAt
            || nextActiveTicket.status !== previousActiveTicket.status
            || nextActiveTicket.statusReason !== previousActiveTicket.statusReason
            || coverageResponseChanged
            )
          )
        );

        if (activeTicketChanged) {
          try {
            const refreshedDetail = await fetchTicketDetail(currentActiveTicketId);
            syncDetailAcrossViews(refreshedDetail);
          } catch {
            // Keep the visible detail stable; the next successful poll will recover.
          }
        }
      }
    } catch (fetchError) {
      if (!silent) {
        setError(fetchError instanceof Error ? fetchError.message : "We could not load tickets right now.");
      }
    }
  }

  async function refreshAgentsOnly(silent = false) {
    try {
      const requestSession = sessionRef.current;
      const nextAgents = await fetchAgentsList();
      if (!isCurrentDashboardSession(requestSession)) {
        return;
      }
      const visibleAgents = filterPendingRemovedAgents(nextAgents);
      setAgents(visibleAgents);
      syncConsoleStatusFromAgents(visibleAgents);
    } catch (fetchError) {
      if (!silent) {
        setError(fetchError instanceof Error ? fetchError.message : "We could not load support accounts right now.");
      }
    }
  }

  async function syncAgentSessionHeartbeat(silent = false, statusOverride?: AdminSelectableConsoleStatus) {
    if (!session?.username || !session.instanceId) {
      return true;
    }

    try {
      const response = await fetch("/api/admin/session-heartbeat", {
        method: "POST",
        headers: buildAdminJsonHeaders(),
        body: JSON.stringify({
          consoleStatus: statusOverride || consoleStatus,
        }),
      });

      const payload = (await response.json().catch(() => null)) as AdminSessionHeartbeatResponse | null;
      const responseAdmin = payload?.admin || null;
      if (responseAdmin && !isSameAdminSession(sessionRef.current, responseAdmin)) {
        if (isSameAdminIdentity(sessionRef.current, responseAdmin)) {
          persistAdminSessionState(responseAdmin);
        } else {
          redirectForEndedAdminSession("Your admin session changed. Please sign in again.");
          return false;
        }
      }

      if (payload?.sessionReplaced) {
        redirectForEndedAdminSession("This support session was replaced by another sign-in. Please sign in again.");
        return false;
      }

      if (payload?.sessionActive === false) {
        redirectForEndedAdminSession("Your admin session ended. Please sign in again.");
        return false;
      }

      if (!response.ok && !silent) {
        if ((response.status === 401 || response.status === 403) && await reconcileAdminAuthorizationFailure()) {
          return false;
        }
        toast.error(payload?.message || "We could not refresh the agent session right now.");
      }

      if (response.ok) {
        if (responseAdmin) {
          persistAdminSessionState(responseAdmin);
        }
        void refreshAgentsOnly(true);
      }

      return response.ok;
    } catch {
      if (!silent) {
        toast.error("We could not refresh the agent session right now.");
      }

      return false;
    }
  }

  async function toggleSupportAccess(agent: AdminAgent, nextValue: boolean) {
    setTogglingAccessIds((prev) => new Set(prev).add(agent.id));
    try {
      const response = await fetch(`/api/admin/accounts/${agent.id}`, {
        method: "PATCH",
        headers: buildAdminJsonHeaders(),
        body: JSON.stringify({ supportAccess: nextValue }),
      });
      const payload = (await response.json().catch(() => null)) as { agent?: AdminAgent; message?: string } | null;
      if (!response.ok) {
        toast.error(payload?.message || "Could not update support access.");
        return;
      }
      const updatedAgent = payload?.agent;
      if (updatedAgent) {
        setAgents((prev) => prev.map((a) => (a.id === updatedAgent.id ? { ...a, ...updatedAgent } : a)));
      }
      void refreshAgentsOnly(true);
      toast.success(`Support access ${nextValue ? "enabled" : "disabled"} for ${agent.fullName || agent.username}.`);
    } catch {
      toast.error("Could not update support access.");
    } finally {
      setTogglingAccessIds((prev) => {
        const next = new Set(prev);
        next.delete(agent.id);
        return next;
      });
    }
  }

  async function searchEntraAgents(q: string) {
    if (q.trim().length < 2) {
      setAgentSearchResults([]);
      return;
    }
    setIsSearchingAgents(true);
    try {
      const response = await fetch(`/api/admin/agents/search?q=${encodeURIComponent(q.trim())}`, {
        headers: buildAdminJsonHeaders(),
      });
      const payload = (await response.json().catch(() => null)) as { results?: EntraSearchResult[]; message?: string } | null;
      if (!response.ok) {
        toast.error(payload?.message || "Could not search agents.");
        return;
      }
      setAgentSearchResults(payload?.results || []);
    } catch {
      toast.error("Could not search agents.");
    } finally {
      setIsSearchingAgents(false);
    }
  }

  async function addEntraAgent(result: EntraSearchResult) {
    setIsAddingAgentId(result.entraId);
    try {
      const response = await fetch("/api/admin/accounts", {
        method: "POST",
        headers: buildAdminJsonHeaders(),
        body: JSON.stringify(result),
      });
      const payload = (await response.json().catch(() => null)) as { agent?: AdminAgent; message?: string } | null;
      if (!response.ok) {
        toast.error(payload?.message || "Could not add agent.");
        return;
      }
      const newAgent = payload?.agent;
      if (newAgent) {
        pendingRemovedAgentIdsRef.current.delete(newAgent.id);
        setAgents((prev) => [...prev, newAgent]);
      }
      setAgentSearchResults((prev) => prev.map((r) => r.entraId === result.entraId ? { ...r, alreadyAdded: true } : r));
      toast.success(`${result.displayName || result.email} added as an agent.`);
    } catch {
      toast.error("Could not add agent.");
    } finally {
      setIsAddingAgentId(null);
    }
  }

  async function removeAgentById(agent: AdminAgent) {
    if (agent.canRemoveFromAgentManagement !== true) {
      toast.info("This agent is managed from KBC permissions. Turn ticket access off or update KBC auth.");
      return;
    }

    const previousAgents = agents;
    pendingRemovedAgentIdsRef.current.add(agent.id);
    setAgents((prev) => prev.filter((a) => a.id !== agent.id));
    setRemovingAgentIds((prev) => new Set(prev).add(agent.id));
    try {
      const response = await fetch(`/api/admin/accounts/${agent.id}`, {
        method: "DELETE",
        headers: buildAdminJsonHeaders(),
      });
      const payload = (await response.json().catch(() => null)) as { ok?: boolean; message?: string } | null;
      if (!response.ok) {
        pendingRemovedAgentIdsRef.current.delete(agent.id);
        setAgents(previousAgents);
        toast.error(payload?.message || "Could not remove agent.");
        return;
      }
      toast.success(`${agent.fullName || agent.username} removed.`);
    } catch {
      pendingRemovedAgentIdsRef.current.delete(agent.id);
      setAgents(previousAgents);
      toast.error("Could not remove agent.");
    } finally {
      setRemovingAgentIds((prev) => {
        const next = new Set(prev);
        next.delete(agent.id);
        return next;
      });
    }
  }

  async function fetchTicketDetail(ticketId: string) {
    const response = await fetch(`/api/admin/tickets/${encodeURIComponent(ticketId)}`, { cache: "no-store" });
    const payload = (await response.json().catch(() => null)) as DetailResponse | null;

    if (!response.ok || !payload?.ticket) {
      if ((response.status === 401 || response.status === 403) && await reconcileAdminAuthorizationFailure()) {
        throw new Error("Admin session is required.");
      }
      throw new Error(payload?.message || "We could not load this ticket right now.");
    }

    return payload;
  }

  function shouldAutoAcknowledgeCoverageTutorResponse(ticket: TicketSummary) {
    const latestCoverageTutorResponse = ticket.latestCoverageTutorResponse;
    if (!latestCoverageTutorResponse || latestCoverageTutorResponse.requesterAcknowledged || !session?.username) {
      return false;
    }

    if (resolvedSessionAgentId) {
      return latestCoverageTutorResponse.toAgentId === resolvedSessionAgentId;
    }

    return sanitizeAssignedAgentName(latestCoverageTutorResponse.toAgentUsername) === sanitizeAssignedAgentName(session.username);
  }

  function shouldAutoAcknowledgeCoverageTicketNotification(ticket: TicketSummary) {
    return Boolean(ticket.pendingCoverageTicketNotification && session?.username);
  }

  async function acknowledgeCoverageTutorResponseSilently(ticket: TicketSummary) {
    if (!shouldAutoAcknowledgeCoverageTutorResponse(ticket)) {
      return null;
    }

    const response = await fetch(
      `/api/admin/tickets/${encodeURIComponent(ticket.id)}/coverage-tutor-response/acknowledge`,
      {
        method: "POST",
        headers: buildAdminJsonHeaders(),
        body: JSON.stringify({}),
      },
    );

    const payload = (await response.json().catch(() => null)) as DetailResponse | null;
    if (!response.ok || !payload?.ticket) {
      if ((response.status === 401 || response.status === 403) && await reconcileAdminAuthorizationFailure()) {
        return null;
      }
      return null;
    }

    return payload;
  }

  async function acknowledgeCoverageTicketNotificationSilently(ticket: TicketSummary) {
    if (!shouldAutoAcknowledgeCoverageTicketNotification(ticket)) {
      return null;
    }

    const response = await fetch(
      `/api/admin/tickets/${encodeURIComponent(ticket.id)}/coverage-ticket-notification/acknowledge`,
      {
        method: "POST",
        headers: buildAdminJsonHeaders(),
        body: JSON.stringify({}),
      },
    );

    const payload = (await response.json().catch(() => null)) as DetailResponse | null;
    if (!response.ok || !payload?.ticket) {
      if ((response.status === 401 || response.status === 403) && await reconcileAdminAuthorizationFailure()) {
        return null;
      }
      return null;
    }

    return payload;
  }

  async function openTicket(ticketId: string, initialTab: TicketDetailTab = "conversation") {
    setActiveTicketId(ticketId);
    setActiveTicketTab(initialTab);
    setActiveDetail(null);
    setNotes("");
    setIsOpening(true);

    try {
      let payload = await fetchTicketDetail(ticketId);
      const acknowledgedCoverageTicketPayload = await acknowledgeCoverageTicketNotificationSilently(payload.ticket);
      if (acknowledgedCoverageTicketPayload?.ticket) {
        payload = acknowledgedCoverageTicketPayload;
      }
      const acknowledgedPayload = await acknowledgeCoverageTutorResponseSilently(payload.ticket);
      if (acknowledgedPayload?.ticket) {
        payload = acknowledgedPayload;
      }

      if (isDashboardQuickResolutionTicket(payload.ticket) && initialTab === "conversation") {
        setActiveTicketTab("documentation");
      }

      setActiveDetail(payload);
      setTickets((currentTickets) => currentTickets.map((ticket) => (
        ticket.id === payload.ticket.id ? payload.ticket : ticket
      )));
      setConsoleDetail((currentDetail) => (
        currentDetail?.ticket.id === payload.ticket.id ? payload : currentDetail
      ));
      syncDrafts(payload);
    } catch (fetchError) {
      closePanel();
      toast.error(fetchError instanceof Error ? fetchError.message : "We could not connect to the server. Please try again.");
    } finally {
      setIsOpening(false);
    }
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
      const acknowledgedCoverageTicketPayload = await acknowledgeCoverageTicketNotificationSilently(payload.ticket);
      if (acknowledgedCoverageTicketPayload?.ticket) {
        payload = acknowledgedCoverageTicketPayload;
      }
      const acknowledgedPayload = await acknowledgeCoverageTutorResponseSilently(payload.ticket);
      if (acknowledgedPayload?.ticket) {
        payload = acknowledgedPayload;
      }

      if (shouldRouteConsoleChatToMyOpenQueue({
        currentScope: consoleCaseScope,
        currentQueueTab: consoleQueueTab,
        ticket: payload.ticket,
        sessionAgentId: resolvedSessionAgentId,
      })) {
        setConsoleCaseScope("my");
        setConsoleQueueTab("open");
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

  async function openConsoleSearchResult(ticket: TicketSummary) {
    if (!session || typeof window === "undefined") {
      toast.error("Admin session is required before opening this chat in a new tab.");
      return;
    }

    const nextQueueTab = ticket.chatState === "closed" ? "closed" : "open";
    const nextUrl = buildConsoleSearchResultUrl({
      pathname: location.pathname,
      ticketId: ticket.id,
      scope: consoleCaseScope,
      queueTab: nextQueueTab,
    });
    const nextWindow = window.open("", "_blank");

    if (!nextWindow) {
      toast.error("Please allow pop-ups for this site so the chat can open in a new tab.");
      return;
    }

    setAdminSessionOnWindow(nextWindow, session);
    nextWindow.location.href = nextUrl;
  }

  async function openNotificationLogTicket(ticketId: string) {
    setIsTransferNotificationsOpen(false);
    await openTicket(ticketId, "documentation");
  }

  useEffect(() => {
    if (isLoading) {
      return;
    }

    // Only sync the dashboard view from the URL when the URL changes.
    // Otherwise a local tab switch to the console view gets forced back to
    // dashboard whenever the current route has no query string.
    if (!location.search) {
      processedConsoleDeepLinkRef.current = "";
      setAdminView((currentView) => (currentView === "dashboard" ? currentView : "dashboard"));
      return;
    }

    if (processedConsoleDeepLinkRef.current === location.search) {
      return;
    }

    const nextConsoleDeepLink = parseAdminDeepLink(location.search);

    if (nextConsoleDeepLink.view !== "console" && !nextConsoleDeepLink.ticketId) {
      return;
    }

    processedConsoleDeepLinkRef.current = location.search;

    if (nextConsoleDeepLink.view === "console") {
      setAdminView("console");
    }

    setConsoleCaseScope(nextConsoleDeepLink.scope);
    setConsoleQueueTab(nextConsoleDeepLink.queueTab);

    if (nextConsoleDeepLink.ticketId) {
      void openConsoleChat(nextConsoleDeepLink.ticketId);
    }
  }, [isLoading, location.search]);

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

  function updateActiveDocumentationField(field: keyof AdminDocumentation, value: string) {
    setActiveDocumentationDraft((currentDraft) => {
      if (!currentDraft) {
        return currentDraft;
      }

      return {
        ...currentDraft,
        [field]: value,
      };
    });
  }

  function updateActiveCoverageDocumentation(updater: (draft: AdminDocumentation) => AdminDocumentation) {
    setActiveDocumentationDraft((currentDraft) => {
      const baseDraft = currentDraft || activeCoverageDocumentationBaseline;
      if (!baseDraft) {
        return currentDraft;
      }

      return updater(baseDraft);
    });
  }

  function updateActiveStandardDocumentation(updater: (draft: AdminDocumentation) => AdminDocumentation) {
    setActiveDocumentationDraft((currentDraft) => {
      const baseDraft = currentDraft || activeStandardDocumentationBaseline;
      if (!baseDraft) {
        return currentDraft;
      }

      return updater(baseDraft);
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

  async function persistActiveCoverageDocumentation(options?: {
    documentation?: AdminDocumentation;
    status?: TicketSummary["status"];
    statusReason?: string;
    note?: string;
    successMessage?: string;
    errorMessage?: string;
    showSuccessToast?: boolean;
  }) {
    if (!activeDetail || !isCoverageTicket(activeDetail.ticket)) {
      return null;
    }

    const documentationToSave = options?.documentation || activeDocumentationDraft || buildCoverageDocumentationDraft(activeDetail.ticket);

    setIsSavingActiveDocumentation(true);

    try {
      const response = await fetch(`/api/admin/tickets/${encodeURIComponent(activeDetail.ticket.id)}`, {
        method: "PATCH",
        headers: buildAdminJsonHeaders(),
        body: JSON.stringify({
          documentation: documentationToSave,
          ...(options?.status ? { status: options.status } : {}),
          ...(options?.statusReason ? { statusReason: options.statusReason } : {}),
          ...(options?.note ? { note: options.note } : {}),
        }),
      });

      const payload = (await response.json().catch(() => null)) as DetailResponse | null;

      if (!response.ok || !payload?.ticket) {
        if ((response.status === 401 || response.status === 403) && await reconcileAdminAuthorizationFailure()) {
          return null;
        }
        toast.error(payload?.message || options?.errorMessage || "We could not save the coverage ticket right now.");
        return null;
      }

      syncDetailAcrossViews(payload);
      syncDrafts(payload);
      setActiveDocumentationDraft(buildCoverageDocumentationDraft(payload.ticket));
      if (options?.showSuccessToast !== false) {
        toast.success(options?.successMessage || "Coverage ticket saved.");
      }
      return payload;
    } catch {
      toast.error(options?.errorMessage || "We could not connect to the server. Please try again.");
      return null;
    } finally {
      setIsSavingActiveDocumentation(false);
    }
  }

  async function saveActiveCoverageDocumentation() {
    await persistActiveCoverageDocumentation({
      successMessage: "Coverage ticket saved.",
      errorMessage: "We could not save the coverage ticket right now.",
    });
  }

  async function submitActiveCoverageTutorChoiceCard(cardId: string) {
    if (!activeDetail || !isCoverageTicket(activeDetail.ticket)) {
      return;
    }

    const currentDraft = activeDocumentationDraft || buildCoverageDocumentationDraft(activeDetail.ticket);
    const targetCard = currentDraft.coverageCards.find((card) => card.id === cardId && card.type === "tutor_choice");
    const lightweightDocumentation: AdminDocumentation = {
      ...currentDraft,
      coverageCards: currentDraft.coverageCards.map((card) => ({
        ...card,
        presentationFiles: [],
      })),
    };

    if (!targetCard) {
      return;
    }

    if (!targetCard.tutor.trim()) {
      toast.error("Choose a tutor before submitting the request.");
      return;
    }

    if (!targetCard.sessionDetails.trim()) {
      toast.error("Add the session details before submitting the request.");
      return;
    }

    if (!targetCard.tutorEmail.trim()) {
      toast.error("Add the tutor e-mail before submitting the request.");
      return;
    }

    if (!isValidCoverageTutorEmail(targetCard.tutorEmail)) {
      toast.error("Please enter a valid tutor e-mail before submitting the request.");
      return;
    }

    setIsSavingActiveDocumentation(true);
    try {
      const response = await fetch(
        `/api/admin/tickets/${encodeURIComponent(activeDetail.ticket.id)}/coverage-tutor-request`,
        {
          method: "POST",
          headers: buildAdminJsonHeaders(),
          body: JSON.stringify({
            cardId,
            origin: window.location.origin,
            card: targetCard,
            documentation: lightweightDocumentation,
          }),
        },
      );

      const payload = (await response.json().catch(() => null)) as DetailResponse | null;

      if (!response.ok || !payload?.ticket) {
        if ((response.status === 401 || response.status === 403) && await reconcileAdminAuthorizationFailure()) {
          return;
        }
        toast.error(payload?.message || "We could not submit this tutor request right now.");
        return;
      }

      syncDetailAcrossViews(payload);
      syncDrafts(payload);
      setActiveDocumentationDraft(buildCoverageDocumentationDraft(payload.ticket));
      toast.success("Tutor request sent.");
    } catch {
      toast.error("We could not connect to the server. Please try again.");
    } finally {
      setIsSavingActiveDocumentation(false);
    }
  }

  async function confirmActiveCoverageTutorSession(cardId: string) {
    if (!activeDetail || !isCoverageTicket(activeDetail.ticket)) {
      return;
    }

    setIsSavingActiveDocumentation(true);

    try {
      const response = await fetch(
        `/api/admin/tickets/${encodeURIComponent(activeDetail.ticket.id)}/coverage-confirm-session`,
        {
          method: "POST",
          headers: buildAdminJsonHeaders(),
          body: JSON.stringify({ cardId }),
        },
      );

      const payload = (await response.json().catch(() => null)) as DetailResponse | null;

      if (!response.ok || !payload?.ticket) {
        if ((response.status === 401 || response.status === 403) && await reconcileAdminAuthorizationFailure()) {
          return;
        }
        toast.error(payload?.message || "We could not confirm this tutor session right now.");
        return;
      }

      syncDetailAcrossViews(payload);
      syncDrafts(payload);
      setActiveDocumentationDraft(buildCoverageDocumentationDraft(payload.ticket));
      toast.success("Session confirmed and ticket closed.");
    } catch {
      toast.error("We could not connect to the server. Please try again.");
    } finally {
      setIsSavingActiveDocumentation(false);
    }
  }

  async function saveDocumentation() {
    if (!consoleDetail || !documentationDraft || consoleWorkspaceReadOnly) {
      return;
    }

    setIsSavingDocumentation(true);

    try {
      const response = await fetch(`/api/admin/tickets/${encodeURIComponent(consoleDetail.ticket.id)}`, {
        method: "PATCH",
        headers: buildAdminJsonHeaders(),
        body: JSON.stringify({
          documentation: documentationDraft,
        }),
      });

      const payload = (await response.json().catch(() => null)) as DetailResponse | null;

      if (!response.ok || !payload?.ticket) {
        if ((response.status === 401 || response.status === 403) && await reconcileAdminAuthorizationFailure()) {
          return;
        }
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

  async function runDocumentationWorkflow() {
    if (
      !consoleDetail
      || !documentationDraft
      || consoleWorkspaceReadOnly
      || !documentationTicketStatus
      || !documentationResolvedStatusReason
      || (documentationRequiresEscalationAssignee && !documentationEscalationAgentId)
      || (documentationRequiresEscalationAssignee && !documentationEscalationNote.trim())
      || (!documentationRequiresEscalationAssignee && !documentationIssuesAddressed)
    ) {
      return;
    }

    if (documentationRequiresEscalationAssignee && !selectedDocumentationEscalationAgent) {
      toast.error("Select an admin to receive this escalation.");
      return;
    }

    if (documentationRequiresEscalationAssignee && !documentationEscalationNote.trim()) {
      toast.error("Add an escalation note before notifying another admin.");
      return;
    }

    setIsSavingDocumentation(true);

    try {
      const shouldCreateFollowUpTicket = documentationIssuesAddressed === "no";
      const escalationAssigneeName = selectedDocumentationEscalationAgent
        ? getAgentDisplayName(selectedDocumentationEscalationAgent)
        : "";
      const workflowDocumentation: AdminDocumentation = {
        ...documentationDraft,
        ticketStatus: documentationTicketStatus,
        statusReason: documentationResolvedStatusReason,
        issuesAddressed: documentationIssuesAddressed,
        escalationAgentId: documentationRequiresEscalationAssignee
          ? Number(documentationEscalationAgentId)
          : null,
        escalationAgentName: documentationRequiresEscalationAssignee
          ? escalationAssigneeName
          : "",
        escalationNote: documentationRequiresEscalationAssignee
          ? documentationEscalationNote.trim()
          : "",
      };
      const workflowNote = buildDocumentationWorkflowNote(
        consoleDetail.ticket,
        documentationTicketStatus,
        documentationResolvedStatusReason,
        documentationIssuesAddressed,
        escalationAssigneeName,
        documentationEscalationNote.trim(),
      );

      const response = await fetch(`/api/admin/tickets/${encodeURIComponent(consoleDetail.ticket.id)}`, {
        method: "PATCH",
        headers: buildAdminJsonHeaders(),
        body: JSON.stringify({
          status: documentationTicketStatus,
          statusReason: documentationResolvedStatusReason,
          ...(documentationRequiresEscalationAssignee ? {
            escalationAgentId: Number(documentationEscalationAgentId),
            escalationNote: documentationEscalationNote.trim(),
          } : {}),
          chatState: documentationIssuesAddressed === "yes" ? "closed" : "open",
          ...(shouldCreateFollowUpTicket ? {
            createFollowUpTicket: true,
            followUpInquiry: workflowDocumentation.inquiry || consoleDetail.ticket.inquiry,
          } : {}),
          documentation: workflowDocumentation,
          note: workflowNote,
        }),
      });

      const payload = (await response.json().catch(() => null)) as DetailResponse | null;

      if (!response.ok || !payload?.ticket) {
        if ((response.status === 401 || response.status === 403) && await reconcileAdminAuthorizationFailure()) {
          return;
        }
        toast.error(payload?.message || "We could not save the documentation workflow right now.");
        return;
      }

      if (shouldCreateFollowUpTicket) {
        await refreshTicketsOnly(true);
        setConsoleTicketId(payload.ticket.id);
        setConsoleDetail(payload);
        toast.success(
          documentationRequiresEscalationAssignee
            ? `Escalation notification sent. Follow-up ticket ${payload.ticket.id} is now continuing this chat.`
            : `Workflow saved. Follow-up ticket ${payload.ticket.id} is now continuing this chat.`,
        );
        return;
      }

      syncDetailAcrossViews(payload);
      setDocumentationDraft(normalizeDocumentationDraft(payload.ticket.documentation));
      setDocumentationTicketStatus(deriveDocumentationTicketStatus(payload.ticket.status));
      setDocumentationStatusReason(payload.ticket.statusReason || "");
      setDocumentationEscalationAgentId(deriveDocumentationEscalationAgentId(payload.ticket));
      setDocumentationEscalationNote(deriveDocumentationEscalationNote(payload.ticket.documentation));
      setDocumentationIssuesAddressed(
        deriveDocumentationIssuesAddressed(payload.ticket.chatState, payload.ticket.documentation),
      );
      setDocumentationStep(1);

      if (documentationRequiresEscalationAssignee && documentationIssuesAddressed === "yes") {
        await refreshTicketsOnly(true);
        toast.success(`Escalation notification sent to ${escalationAssigneeName || "the selected admin"} and the chat was closed.`);
        return;
      }

      await refreshTicketsOnly(true);
      toast.success("Workflow saved and chat closed.");
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
      const response = await fetch(`/api/admin/tickets/${encodeURIComponent(consoleDetail.ticket.id)}/chat-history`, {
        method: "POST",
        headers: buildAdminJsonHeaders(),
        body: JSON.stringify({
          status: consoleDetail.ticket.status,
          statusReason: consoleDetail.ticket.statusReason,
          messages: serializeConsoleChatHistory(optimisticDetail.chatHistory),
        }),
      });

      const payload = (await response.json().catch(() => null)) as { message?: string } | null;

      if (!response.ok) {
        if ((response.status === 401 || response.status === 403) && await reconcileAdminAuthorizationFailure()) {
          return;
        }
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

  async function handleForceCloseConsoleChat() {
    if (!consoleDetail || !canForceCloseConsoleChat || isForceClosingConsoleChat) {
      return;
    }

    setIsForceClosingConsoleChat(true);

    try {
      const response = await fetch(`/api/admin/tickets/${encodeURIComponent(consoleDetail.ticket.id)}`, {
        method: "PATCH",
        headers: buildAdminJsonHeaders(),
        body: JSON.stringify({
          chatState: "closed",
        }),
      });

      const payload = (await response.json().catch(() => null)) as DetailResponse | null;

      if (!response.ok || !payload?.ticket) {
        if ((response.status === 401 || response.status === 403) && await reconcileAdminAuthorizationFailure()) {
          return;
        }
        toast.error(payload?.message || "We could not force-close the chat right now.");
        return;
      }

      syncDetailAcrossViews(payload);
      toast.success("Chat force-closed.");
    } catch {
      toast.error("We could not connect to the server. Please try again.");
    } finally {
      setIsForceClosingConsoleChat(false);
    }
  }

  async function handleTransferConsoleTicket(agent: AdminAgent) {
    if (!consoleDetail || consoleWorkspaceReadOnly || isTransferringConsoleTicket) {
      return;
    }

    const trimmedTransferReason = transferReason.trim();
    if (agent.id === consoleDetail.ticket.assignedAgentId) {
      setIsTransferMenuOpen(false);
      return;
    }
    if (!trimmedTransferReason) {
      toast.error("Add a transfer reason before reassigning this ticket.");
      return;
    }

    setIsTransferMenuOpen(false);
    setIsTransferringConsoleTicket(true);

    try {
      const response = await fetch(`/api/admin/tickets/${encodeURIComponent(consoleDetail.ticket.id)}/transfer-request`, {
        method: "POST",
        headers: buildAdminJsonHeaders(),
        body: JSON.stringify({
          targetAgentId: agent.id,
          reason: trimmedTransferReason,
        }),
      });

      const payload = (await response.json().catch(() => null)) as DetailResponse | null;

      if (!response.ok || !payload?.ticket) {
        if ((response.status === 401 || response.status === 403) && await reconcileAdminAuthorizationFailure()) {
          return;
        }
        toast.error(payload?.message || "We could not transfer the ticket right now.");
        return;
      }

      syncDetailAcrossViews(payload);
      setTransferReason("");
      toast.success(`Transfer request sent to ${getAgentDisplayName(agent)}.`);
      await refreshTicketsOnly(true);
    } catch {
      toast.error("We could not connect to the server. Please try again.");
    } finally {
      setIsTransferringConsoleTicket(false);
    }
  }

  async function handleTransferRequestDecision(ticket: TicketSummary, action: "accept" | "reject") {
    if (!ticket.pendingTransferRequest || !session?.username || activeTransferRequestTicketId) {
      return;
    }

    if (action === "accept" && myActualConsoleStatus === "Off") {
      void updateConsoleStatus("Available");
    }

    setActiveTransferRequestTicketId(ticket.id);

    try {
      const response = await fetch(
        `/api/admin/tickets/${encodeURIComponent(ticket.id)}/transfer-request/${action}`,
        {
          method: "POST",
          headers: buildAdminJsonHeaders(),
          body: JSON.stringify({}),
        },
      );

      const payload = (await response.json().catch(() => null)) as DetailResponse | null;

      if (!response.ok || !payload?.ticket) {
        if ((response.status === 401 || response.status === 403) && await reconcileAdminAuthorizationFailure({
          mismatchMessage: "Your admin session changed before this transfer decision could be completed. Please sign in again.",
        })) {
          return;
        }
        toast.error(payload?.message || `We could not ${action} this transfer request right now.`);
        return;
      }

      syncDetailAcrossViews(payload);
      if (activeDetail?.ticket.id === ticket.id) {
        syncDrafts(payload);
      }
      await refreshTicketsOnly(true);
      if (action === "accept") {
        await refreshAgentsOnly(true);
        setConsoleCaseScope("my");
        setConsoleQueueTab("open");
        setIsTransferNotificationsOpen(false);
      }

      if (action === "accept") {
        toast.success(`Transfer accepted for ${ticket.id}.`);
      } else {
        toast.success(`Transfer declined for ${ticket.id}.`);
      }
    } catch {
      toast.error("We could not connect to the server. Please try again.");
    } finally {
      setActiveTransferRequestTicketId("");
    }
  }

  async function handleTransferDecisionAcknowledge(ticket: TicketSummary) {
    if (!ticket.latestTransferDecision || !session?.username || activeTransferRequestTicketId) {
      return;
    }

    setActiveTransferRequestTicketId(ticket.id);

    try {
      const response = await fetch(
        `/api/admin/tickets/${encodeURIComponent(ticket.id)}/transfer-decision/acknowledge`,
        {
          method: "POST",
          headers: buildAdminJsonHeaders(),
          body: JSON.stringify({}),
        },
      );

      const payload = (await response.json().catch(() => null)) as DetailResponse | null;

      if (!response.ok || !payload?.ticket) {
        if ((response.status === 401 || response.status === 403) && await reconcileAdminAuthorizationFailure()) {
          return;
        }
        toast.error(payload?.message || "We could not clear this transfer update right now.");
        return;
      }

      syncDetailAcrossViews(payload);
      if (activeDetail?.ticket.id === ticket.id) {
        syncDrafts(payload);
      }
      await refreshTicketsOnly(true);
    } catch {
      toast.error("We could not connect to the server. Please try again.");
    } finally {
      setActiveTransferRequestTicketId("");
    }
  }

  async function handleEscalationClosureAcknowledge(ticket: TicketSummary) {
    if (!ticket.latestEscalationClosure || !session?.username || activeTransferRequestTicketId) {
      return;
    }

    setActiveTransferRequestTicketId(ticket.id);

    try {
      const response = await fetch(
        `/api/admin/tickets/${encodeURIComponent(ticket.id)}/escalation-closure/acknowledge`,
        {
          method: "POST",
          headers: buildAdminJsonHeaders(),
          body: JSON.stringify({}),
        },
      );

      const payload = (await response.json().catch(() => null)) as DetailResponse | null;

      if (!response.ok || !payload?.ticket) {
        if ((response.status === 401 || response.status === 403) && await reconcileAdminAuthorizationFailure()) {
          return;
        }
        toast.error(payload?.message || "We could not clear this escalation update right now.");
        return;
      }

      syncDetailAcrossViews(payload);
      if (activeDetail?.ticket.id === ticket.id) {
        syncDrafts(payload);
      }
      await refreshTicketsOnly(true);
    } catch {
      toast.error("We could not connect to the server. Please try again.");
    } finally {
      setActiveTransferRequestTicketId("");
    }
  }

  async function handleCoverageTutorResponseAcknowledge(ticket: TicketSummary) {
    if (!ticket.latestCoverageTutorResponse || !session?.username || activeTransferRequestTicketId) {
      return;
    }

    setActiveTransferRequestTicketId(ticket.id);

    try {
      const response = await fetch(
        `/api/admin/tickets/${encodeURIComponent(ticket.id)}/coverage-tutor-response/acknowledge`,
        {
          method: "POST",
          headers: buildAdminJsonHeaders(),
          body: JSON.stringify({}),
        },
      );

      const payload = (await response.json().catch(() => null)) as DetailResponse | null;

      if (!response.ok || !payload?.ticket) {
        if ((response.status === 401 || response.status === 403) && await reconcileAdminAuthorizationFailure()) {
          return;
        }
        toast.error(payload?.message || "We could not clear this tutor update right now.");
        return;
      }

      syncDetailAcrossViews(payload);
      if (activeDetail?.ticket.id === ticket.id) {
        syncDrafts(payload);
      }
      await refreshTicketsOnly(true);
    } catch {
      toast.error("We could not connect to the server. Please try again.");
    } finally {
      setActiveTransferRequestTicketId("");
    }
  }

  async function handleCoverageTicketNotificationAcknowledge(ticket: TicketSummary) {
    if (!ticket.pendingCoverageTicketNotification || !session?.username || activeTransferRequestTicketId) {
      return;
    }

    setActiveTransferRequestTicketId(ticket.id);

    try {
      const response = await fetch(
        `/api/admin/tickets/${encodeURIComponent(ticket.id)}/coverage-ticket-notification/acknowledge`,
        {
          method: "POST",
          headers: buildAdminJsonHeaders(),
          body: JSON.stringify({}),
        },
      );

      const payload = (await response.json().catch(() => null)) as DetailResponse | null;

      if (!response.ok || !payload?.ticket) {
        if ((response.status === 401 || response.status === 403) && await reconcileAdminAuthorizationFailure()) {
          return;
        }
        toast.error(payload?.message || "We could not clear this coverage ticket alert right now.");
        return;
      }

      syncDetailAcrossViews(payload);
      if (activeDetail?.ticket.id === ticket.id) {
        syncDrafts(payload);
      }
      await refreshTicketsOnly(true);
    } catch {
      toast.error("We could not connect to the server. Please try again.");
    } finally {
      setActiveTransferRequestTicketId("");
    }
  }

  async function handleTeamsCallNotificationOpen(ticket: TicketSummary) {
    if (!ticket.pendingTeamsCallNotification || !session?.username || activeTransferRequestTicketId) {
      return;
    }

    setActiveTransferRequestTicketId(ticket.id);

    try {
      const response = await fetch(
        `/api/admin/tickets/${encodeURIComponent(ticket.id)}/teams-call-notification/acknowledge`,
        {
          method: "POST",
          headers: buildAdminJsonHeaders(),
          body: JSON.stringify({}),
        },
      );

      const payload = (await response.json().catch(() => null)) as DetailResponse | null;

      if (!response.ok || !payload?.ticket) {
        if (response.status === 409) {
          setIsTransferNotificationsOpen(false);
          await openTicket(ticket.id, "documentation");
          return;
        }
        if ((response.status === 401 || response.status === 403) && await reconcileAdminAuthorizationFailure()) {
          return;
        }

        toast.error(payload?.message || "We could not open this Teams call request right now.");
        return;
      }

      syncDetailAcrossViews(payload);
      if (activeDetail?.ticket.id === ticket.id) {
        syncDrafts(payload);
      }
      await refreshTicketsOnly(true);
      setIsTransferNotificationsOpen(false);
      await openTicket(ticket.id, "documentation");
    } catch {
      toast.error("We could not connect to the server. Please try again.");
    } finally {
      setActiveTransferRequestTicketId("");
    }
  }

  async function handleEscalationNotificationAcknowledge(ticket: TicketSummary, openChat = false) {
    if (!ticket.pendingEscalationNotification || !session?.username || activeTransferRequestTicketId) {
      return;
    }

    setActiveTransferRequestTicketId(ticket.id);

    try {
      const response = await fetch(
        `/api/admin/tickets/${encodeURIComponent(ticket.id)}/escalation-notification/acknowledge`,
        {
          method: "POST",
          headers: buildAdminJsonHeaders(),
          body: JSON.stringify({}),
        },
      );

      const payload = (await response.json().catch(() => null)) as DetailResponse | null;

      if (!response.ok || !payload?.ticket) {
        if ((response.status === 401 || response.status === 403) && await reconcileAdminAuthorizationFailure()) {
          return;
        }
        toast.error(payload?.message || "We could not clear this escalation notification right now.");
        return;
      }

      syncDetailAcrossViews(payload);
      if (activeDetail?.ticket.id === ticket.id) {
        syncDrafts(payload);
      }
      await refreshTicketsOnly(true);

      if (openChat) {
        await openConsoleChat(ticket.id);
      }
    } catch {
      toast.error("We could not connect to the server. Please try again.");
    } finally {
      setActiveTransferRequestTicketId("");
    }
  }

  async function handleAiMessageSend() {
    if (!consoleDetail || !consoleAiInput.trim() || consoleWorkspaceReadOnly || isSendingAiMessage) {
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
        headers: buildAdminJsonHeaders(),
        body: JSON.stringify({
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
        if ((response.status === 401 || response.status === 403) && await reconcileAdminAuthorizationFailure()) {
          return;
        }
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
    setActiveTicketTab("conversation");
    setActiveDetail(null);
    setActiveDocumentationDraft(null);
    setNotes("");
  }

  function collapseConsoleWorkspace() {
    setIsTransferMenuOpen(false);
    setTransferReason("");
    setConsoleTicketId("");
    setConsoleDetail(null);
    setDocumentationDraft(null);
    setDocumentationStep(1);
    setDocumentationTicketStatus("");
    setDocumentationStatusReason("");
    setDocumentationEscalationAgentId("");
    setDocumentationEscalationNote("");
    setDocumentationIssuesAddressed("");
    setConsoleChatInput("");
    setConsoleAiInput("");
  }

  async function updateConsoleStatus(nextStatus: AdminSelectableConsoleStatus) {
    const previousStatus = consoleStatus || "Off";
    if (nextStatus === previousStatus && !pendingConsoleStatusRef.current) {
      return;
    }

    pendingConsoleStatusRef.current = nextStatus;
    setIsUpdatingConsoleStatus(true);
    setConsoleStatus(nextStatus);
    setAgents((currentAgents) => currentAgents.map((agent) => {
      const isSignedInAgent = (
        (session?.id && agent.id === session.id)
        || (session?.username && agent.username === session.username)
      );

      if (!isSignedInAgent) {
        return agent;
      }

      return {
        ...agent,
        consoleStatus: hasCurrentAdminOpenConsoleQueue ? "Busy" : nextStatus,
        selectedConsoleStatus: nextStatus,
        sessionActive: true,
      };
    }));

    if (!session?.username || !session.instanceId) {
      return;
    }

    persistAdminSessionState({
      ...session,
      consoleStatus: nextStatus,
    });

    const synced = await syncAgentSessionHeartbeat(false, nextStatus);
    if (synced) {
      void refreshTicketsOnly(true);
      setIsUpdatingConsoleStatus(false);
      return;
    }

    pendingConsoleStatusRef.current = null;
    setIsUpdatingConsoleStatus(false);
    setConsoleStatus(previousStatus);
    void refreshAgentsOnly(true);
    persistAdminSessionState({
      ...session,
      consoleStatus: previousStatus,
    });
  }

  async function saveTicket(overrides?: {
    status?: TicketSummary["status"];
    statusReason?: string;
    slaStatus?: TicketSummary["slaStatus"];
    note?: string;
    successMessage?: string;
  }) {
    if (!activeDetail) {
      return;
    }

    const nextStatus = overrides?.status ?? draftStatus;
    const nextNote = (overrides?.note ?? notes).trim();
    const standardDocumentationToSave = isActiveStandardDocumentationTicket
      && activeStandardDocumentationDraft
      && activeStandardDocumentationDirty
      ? freezeDocumentationCardsForSave(activeStandardDocumentationDraft)
      : null;

    if (nextStatus !== activeDetail.ticket.status && !nextNote) {
      toast.error("Add an internal note before changing the ticket status.");
      return;
    }

    setIsSaving(true);

    try {
      const requestBody: Record<string, unknown> = {
        status: nextStatus,
        ...(overrides?.statusReason ? { statusReason: overrides.statusReason } : {}),
        slaStatus: overrides?.slaStatus ?? effectiveDraftSlaStatus,
        note: nextNote,
        ...(standardDocumentationToSave ? { documentation: standardDocumentationToSave } : {}),
      };

      if (canAssignActiveTicket) {
        const currentAssignedAgentId = activeDetail.ticket.assignedAgentId ? String(activeDetail.ticket.assignedAgentId) : "unassigned";
        if (draftAgentId !== currentAssignedAgentId) {
          requestBody.assignedAgentId = draftAgentId === "unassigned" ? null : Number(draftAgentId);
        }
      }

      const response = await fetch(`/api/admin/tickets/${encodeURIComponent(activeDetail.ticket.id)}`, {
        method: "PATCH",
        headers: buildAdminJsonHeaders(),
        body: JSON.stringify(requestBody),
      });

      const payload = (await response.json().catch(() => null)) as DetailResponse | null;

      if (!response.ok || !payload?.ticket) {
        if ((response.status === 401 || response.status === 403) && await reconcileAdminAuthorizationFailure()) {
          return;
        }
        toast.error(payload?.message || "We could not update the ticket right now.");
        return;
      }

      setActiveDetail(payload);
      syncDrafts(payload);
      if (standardDocumentationToSave) {
        setActiveDocumentationDraft(buildStandardDocumentationDraft(payload.ticket));
      }
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

  function renderDashboardWorkspace() {
    const coverageDashboardKpiFilters: DashboardTicketFilter[] = ["coverage", "pending", "closed", "slaBreached"];
    const visibleKpis = isCoverageDashboardView
      ? kpis.filter((kpi) => coverageDashboardKpiFilters.includes(kpi.filter))
      : kpis;

    return (
      <div className="space-y-5">
        <div className={cn(
          "grid grid-cols-1 gap-4",
          isCoverageDashboardView ? "sm:grid-cols-2 xl:grid-cols-4" : "sm:grid-cols-2 xl:grid-cols-7",
        )}>
          {visibleKpis.map((kpi) => (
            <button
              key={kpi.label}
              type="button"
              onClick={() => setDashboardTicketFilter((currentFilter) => (
                currentFilter === kpi.filter ? "all" : kpi.filter
              ))}
              className={cn(
                "bg-card rounded-2xl border shadow-soft p-5 text-left transition-colors",
                dashboardTicketFilter === kpi.filter
                  ? "border-primary bg-primary/5 ring-1 ring-primary/20"
                  : "hover:border-primary/40 hover:bg-secondary/20",
              )}
            >
              <div className={cn("h-9 w-9 rounded-lg flex items-center justify-center mb-3", kpi.color)}>
                <kpi.icon className="h-5 w-5" />
              </div>
              <div className="text-2xl font-bold">{kpi.value}</div>
              <div className="text-xs text-muted-foreground">{kpi.label}</div>
              <div className="mt-2 text-[11px] font-medium text-primary">
                {dashboardTicketFilter === kpi.filter ? `Showing ${kpi.label.toLowerCase()}` : `Click to view ${kpi.label.toLowerCase()}`}
              </div>
            </button>
          ))}
          {!isCoverageDashboardView ? (
            <button
              type="button"
              onClick={() => setDashboardTicketFilter((currentFilter) => (
                currentFilter === "quickResolution" ? "all" : "quickResolution"
              ))}
              className={cn(
                "bg-card rounded-2xl border shadow-soft p-5 text-left transition-colors",
                dashboardTicketFilter === "quickResolution"
                  ? "border-primary bg-primary/5 ring-1 ring-primary/20"
                  : "hover:border-primary/40 hover:bg-secondary/20",
              )}
            >
              <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <FileText className="h-5 w-5" />
              </div>
              <div className="text-2xl font-bold">{quickResolutionTickets.length}</div>
              <div className="text-xs text-muted-foreground">Quick Tickets</div>
              <div className="mt-2 text-[11px] font-medium text-primary">
                {dashboardTicketFilter === "quickResolution" ? "Showing only quick tickets" : "Click to view quick tickets"}
              </div>
            </button>
          ) : null}
        </div>

        <div className="bg-card overflow-hidden rounded-2xl border shadow-card">
          <div className="border-b px-4 py-4 sm:px-5">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
              <div>
                <h2 className="font-semibold">{dashboardTableTitle}</h2>
                {dashboardTicketFilter === "quickResolution" ? (
                  <p className="mt-1 text-xs text-muted-foreground">
                    These tickets skip the chat console and stay available from the dashboard only.
                  </p>
                ) : null}
              </div>
              <div className="flex flex-col gap-3 lg:items-end">
                <div className="flex items-center gap-3">
                  <span className="text-xs text-muted-foreground">{dashboardTableCountLabel}</span>
                  {dashboardTicketFilter !== "all" || dashboardSortOrder !== "newest" ? (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        setDashboardTicketFilter("all");
                        setDashboardSortOrder("newest");
                      }}
                    >
                      Reset View
                    </Button>
                  ) : null}
                </div>
                <div className="flex w-full flex-col gap-3 sm:flex-row sm:items-center sm:justify-end">
                  {!isCoverageDashboardView ? (
                    <div className="w-full sm:w-[170px]">
                      <Select
                        value={consoleStatus || "Off"}
                        onValueChange={(value) => void updateConsoleStatus(value as AdminSelectableConsoleStatus)}
                        disabled={isUpdatingConsoleStatus}
                      >
                        <SelectTrigger
                          aria-label="Set your console status"
                          className={cn(
                            (consoleStatus || "Off") === "Available"
                              ? "border-emerald-200 bg-emerald-50/80 text-emerald-700"
                              : "border-slate-200 bg-slate-50/80 text-slate-600",
                          )}
                        >
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {adminSelectableConsoleStatuses.map((status) => (
                            <SelectItem key={status} value={status}>{status}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  ) : null}
                  <div className="w-full sm:w-[200px]">
                    <Select
                      value={dashboardAssignedFilter}
                      onValueChange={(value) => setDashboardAssignedFilter(value as DashboardAssignedFilter)}
                    >
                      <SelectTrigger aria-label="Filter tickets by assigned agent">
                        <SelectValue placeholder="Assigned To" />
                      </SelectTrigger>
                      <SelectContent>
                        {dashboardAgentFilterOptions.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="w-full sm:w-[170px]">
                    <Select
                      value={dashboardSortOrder}
                      onValueChange={(value) => setDashboardSortOrder(value as DashboardSortOrder)}
                    >
                      <SelectTrigger aria-label="Sort tickets">
                        <SelectValue placeholder="Sort by" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="newest">Newest First</SelectItem>
                        <SelectItem value="oldest">Oldest First</SelectItem>
                        <SelectItem value="priorityDesc">Highest Priority</SelectItem>
                        <SelectItem value="priorityAsc">Lowest Priority</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="outline" className="w-full max-w-full justify-between gap-3 sm:w-[300px]">
                        <span className="inline-flex items-center gap-2">
                          <UserRound className="h-4 w-4 text-primary" />
                          Team Status
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {availableAgentCount} available
                        </span>
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="w-[min(92vw,340px)] p-0">
                      <div className="border-b px-4 py-3">
                        <div className="text-sm font-semibold">Agent Status</div>
                        <div className="mt-1 text-xs text-muted-foreground">
                          Live availability from the support accounts table.
                        </div>
                        <div className="mt-3 flex flex-wrap gap-2">
                          {([
                            { label: "Available", count: availableAgentCount },
                            { label: "Busy", count: busyAgentCount },
                            { label: "Off", count: offAgentCount },
                          ] as const).map((item) => (
                            <div
                              key={item.label}
                              className="inline-flex items-center gap-2 rounded-full border bg-background/80 px-2.5 py-1 text-[11px] text-muted-foreground"
                            >
                              <span className={cn("h-2 w-2 rounded-full", presenceDotClassName(item.label))} />
                              <span>{item.label}</span>
                              <span className="font-semibold text-foreground">{item.count}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                      <div className="max-h-[320px] overflow-y-auto p-2">
                        {sortedAgents.length === 0 ? (
                          <div className="rounded-xl border border-dashed px-3 py-4 text-sm text-muted-foreground">
                            No active agents found.
                          </div>
                        ) : (
                          <div className="space-y-2">
                            {sortedAgents.map((agent) => {
                              const agentStatus = normalizeAdminConsoleStatus(agent.consoleStatus);

                              return (
                                <div
                                  key={agent.id}
                                  className="rounded-xl border bg-background/80 px-3 py-3 shadow-soft"
                                >
                                  <div className="flex items-start justify-between gap-3">
                                    <div className="min-w-0">
                                      <div className="truncate font-medium text-foreground">
                                        {getAgentDisplayName(agent)}
                                      </div>
                                      <div className="mt-1 truncate text-xs text-muted-foreground">
                                        @{agent.username}
                                        {agent.role ? ` - ${formatAdminRoleLabel(agent.role)}` : ""}
                                      </div>
                                    </div>
                                    <span className="inline-flex shrink-0 items-center gap-2 rounded-full border bg-background px-2.5 py-1 text-[11px] text-muted-foreground">
                                      <span className={cn("h-2 w-2 rounded-full", presenceDotClassName(agentStatus))} />
                                      {agentStatus}
                                    </span>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    </DropdownMenuContent>
                  </DropdownMenu>
                  <div className="relative w-full lg:w-[360px]">
                    <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      value={dashboardSearch}
                      onChange={(event) => setDashboardSearch(event.target.value)}
                      placeholder="Search by learner name, chat ID, or ticket ID"
                      className="pl-10"
                      aria-label="Search tickets by learner name, chat ID, or ticket ID"
                    />
                  </div>
                </div>
              </div>
            </div>
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
          ) : visibleDashboardTickets.length === 0 ? (
            <div className="p-10 text-sm text-muted-foreground text-center">
              {dashboardEmptyMessage}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-secondary/50 text-muted-foreground">
                  <tr className="text-left">
                    {["Chat ID", "Ticket ID", "Learner", "Category", "Status", "Status Reason", "Assigned Agent", "Created", "SLA"].map((heading) => (
                      <th key={heading} className="px-4 py-3 font-medium whitespace-nowrap">{heading}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {visibleDashboardTickets.map((ticket) => (
                    <tr
                      key={ticket.id}
                      role="button"
                      tabIndex={0}
                      onClick={() => void openTicket(ticket.id)}
                      onKeyDown={(event) => {
                        if (event.key !== "Enter" && event.key !== " ") {
                          return;
                        }

                        event.preventDefault();
                        void openTicket(ticket.id);
                      }}
                      className={cn(
                        "cursor-pointer transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-inset hover:bg-secondary/20",
                        getTicketTransferRowClassName(ticket),
                      )}
                    >
                      <td className="px-4 py-3 font-mono font-medium whitespace-nowrap">{getDisplayedChatReference(ticket)}</td>
                      <td className="px-4 py-3 font-mono font-medium whitespace-nowrap">{ticket.id}</td>
                      <td className="px-4 py-3 min-w-[240px]">
                        <div className="font-medium">{ticket.learnerName || "Learner"}</div>
                        <div className="text-xs text-muted-foreground">{ticket.email}</div>
                        <div className="mt-2">
                          <RequesterRoleBadge role={ticket.requesterRole} />
                        </div>
                      </td>
                      <td className="px-4 py-3">{formatCategoryLabel(ticket.category, ticket.technicalSubcategory)}</td>
                      <td className="px-4 py-3"><StatusBadge status={ticket.status} label={getDisplayedTicketStatus(ticket)} /></td>
                      <td className="px-4 py-3 text-muted-foreground">{getDisplayedTicketStatusReason(ticket)}</td>
                      <td className="px-4 py-3">
                        <AssignedAgentBadge
                          assignedAgentId={ticket.assignedAgentId}
                          assignedAgentName={ticket.assignedAgentName}
                          statusReason={ticket.statusReason}
                          documentation={ticket.documentation}
                          pendingEscalationNotification={ticket.pendingEscalationNotification}
                          latestEscalationClosure={ticket.latestEscalationClosure}
                          latestTransferDecision={ticket.latestTransferDecision}
                        />
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">{formatDateTime(ticket.createdAt)}</td>
                      <td className="px-4 py-3">
                        <span className={cn("text-xs font-medium", slaStatusClassName(ticket.slaStatus))}>
                          {ticket.slaStatus}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <SupportLayout
      fullWidth
      showHeader={!isConsoleView}
      right={undefined}
      mainClassName={isConsoleView ? "h-[100dvh] px-0 py-0 md:px-0 md:py-0" : undefined}
    >
      <Tabs
        value={adminView}
        onValueChange={(value) => {
          const nextView = value as AdminView;
          if (nextView !== adminView) {
            closePanel();
          }
          setAdminView(nextView);
        }}
        className={cn(
          "min-h-0",
          isConsoleView
            ? "h-full min-h-[100dvh]"
            : isStackedAdminLayout
              ? "h-auto"
              : "h-[calc(100vh-112px)] min-h-[calc(100vh-112px)]",
        )}
      >
        <div className={cn("flex min-h-0 gap-4", isStackedAdminLayout ? "h-auto flex-col" : "h-full flex-row")}>
          <aside
            className={cn(
              "flex shrink-0 flex-col overflow-hidden rounded-3xl border bg-card/95 shadow-card transition-all duration-300",
              isStackedAdminLayout
                ? "w-full p-4"
                : useCompactAdminSidebar
                  ? "h-full w-[88px] p-3"
                  : "h-full w-[320px] p-4",
            )}
          >
            <div className={cn(
              "gap-3",
              useCompactAdminSidebar ? "flex flex-col items-center" : "relative",
            )}>
              {useCompactAdminSidebar ? (
                <div className="flex w-full flex-col items-center gap-2">
                  <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                    <LayoutDashboard className="h-5 w-5" />
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setIsAdminSidebarCollapsed(false)}
                    aria-label="Expand sidebar"
                    className="h-11 w-11 rounded-2xl border bg-background/90 text-muted-foreground shadow-sm hover:bg-background hover:text-foreground"
                  >
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                  <DropdownMenu open={isTransferNotificationsOpen} onOpenChange={setIsTransferNotificationsOpen}>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon" className="relative h-11 w-11 rounded-2xl border bg-background/90">
                        <Bell className="h-4 w-4" />
                        {totalAdminNotificationCount > 0 ? (
                          <span className="absolute -right-1 -top-1 inline-flex min-w-[1.2rem] items-center justify-center rounded-full bg-destructive px-1.5 py-0.5 text-[10px] font-semibold text-destructive-foreground">
                            {totalAdminNotificationCount}
                          </span>
                        ) : null}
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="start" sideOffset={8} className="w-[min(92vw,380px)] rounded-2xl p-2">
                      <AdminNotificationsPanel
                        coverageTickets={coverageTicketNotifications}
                        requests={pendingTransferRequests}
                        escalations={pendingEscalationNotifications}
                        teamsCalls={pendingTeamsCallNotifications}
                        waitingLiveChats={waitingLiveChatNotifications}
                        currentConsoleStatus={myActualConsoleStatus}
                        isUpdatingConsoleStatus={isUpdatingConsoleStatus}
                        coverageResponses={coverageTutorResponseNotifications}
                        escalationUpdates={escalationClosureNotifications}
                        decisionUpdates={transferDecisionNotifications}
                        notificationLog={archivedNotificationLog}
                        activeTicketId={activeTransferRequestTicketId}
                        onDecision={handleTransferRequestDecision}
                        onOpenTeamsCall={handleTeamsCallNotificationOpen}
                        onAcknowledgeCoverageTicket={handleCoverageTicketNotificationAcknowledge}
                        onAcknowledgeEscalation={handleEscalationNotificationAcknowledge}
                        onAcknowledgeEscalationUpdate={handleEscalationClosureAcknowledge}
                        onAcknowledgeCoverageResponse={handleCoverageTutorResponseAcknowledge}
                        onAcknowledgeDecision={handleTransferDecisionAcknowledge}
                        onOpenTicket={openNotificationLogTicket}
                        onSetAvailable={() => void updateConsoleStatus("Available")}
                      />
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              ) : (
                <div className="relative w-full min-w-0">
                  <div className="rounded-[26px] border border-primary/12 bg-gradient-to-br from-primary/[0.08] via-white to-slate-50 p-4 pr-24 shadow-soft">
                    <div className="flex items-center gap-3">
                      <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-primary/12 text-primary ring-1 ring-primary/10">
                        <UserRound className="h-4 w-4" />
                      </div>
                      <div className="min-w-0">
                        <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-primary/65">
                          {formatAdminRoleLabel(session?.role)}
                        </div>
                        <div className="truncate text-[15px] font-semibold text-foreground">
                          {session?.fullName || session?.username || "Support Admin"}
                        </div>
                      </div>
                    </div>
                  </div>
                  <DropdownMenu open={isTransferNotificationsOpen} onOpenChange={setIsTransferNotificationsOpen}>
                    <DropdownMenuTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label="Transfer requests"
                        className="absolute right-14 top-1/2 h-8 w-8 -translate-y-1/2 rounded-full border border-primary/10 bg-background/90 text-muted-foreground shadow-sm hover:bg-background hover:text-foreground"
                      >
                        <Bell className="h-4 w-4" />
                        {totalAdminNotificationCount > 0 ? (
                          <span className="absolute -right-1 -top-1 inline-flex min-w-[1.1rem] items-center justify-center rounded-full bg-destructive px-1 py-0.5 text-[10px] font-semibold leading-none text-destructive-foreground">
                            {totalAdminNotificationCount}
                          </span>
                        ) : null}
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" sideOffset={8} className="w-[min(92vw,380px)] rounded-2xl p-2">
                      <AdminNotificationsPanel
                        coverageTickets={coverageTicketNotifications}
                        requests={pendingTransferRequests}
                        escalations={pendingEscalationNotifications}
                        teamsCalls={pendingTeamsCallNotifications}
                        waitingLiveChats={waitingLiveChatNotifications}
                        currentConsoleStatus={myActualConsoleStatus}
                        isUpdatingConsoleStatus={isUpdatingConsoleStatus}
                        coverageResponses={coverageTutorResponseNotifications}
                        escalationUpdates={escalationClosureNotifications}
                        decisionUpdates={transferDecisionNotifications}
                        notificationLog={archivedNotificationLog}
                        activeTicketId={activeTransferRequestTicketId}
                        onDecision={handleTransferRequestDecision}
                        onOpenTeamsCall={handleTeamsCallNotificationOpen}
                        onAcknowledgeCoverageTicket={handleCoverageTicketNotificationAcknowledge}
                        onAcknowledgeEscalation={handleEscalationNotificationAcknowledge}
                        onAcknowledgeEscalationUpdate={handleEscalationClosureAcknowledge}
                        onAcknowledgeCoverageResponse={handleCoverageTutorResponseAcknowledge}
                        onAcknowledgeDecision={handleTransferDecisionAcknowledge}
                        onOpenTicket={openNotificationLogTicket}
                        onSetAvailable={() => void updateConsoleStatus("Available")}
                      />
                    </DropdownMenuContent>
                  </DropdownMenu>
                  {!isStackedAdminLayout ? (
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => setIsAdminSidebarCollapsed((currentState) => !currentState)}
                      aria-label={useCompactAdminSidebar ? "Expand sidebar" : "Collapse sidebar"}
                      className="absolute right-3 top-1/2 h-8 w-8 -translate-y-1/2 rounded-full border border-primary/10 bg-background/90 text-muted-foreground shadow-sm hover:bg-background hover:text-foreground"
                    >
                      <ChevronLeft className="h-4 w-4" />
                    </Button>
                  ) : null}
                </div>
              )}
            </div>

            <div className="mt-4 flex min-h-0 flex-1 flex-col gap-4">
              <div className={cn(
                "rounded-2xl border bg-secondary/40",
                useCompactAdminSidebar ? "p-2" : "p-3",
              )}>
                {useCompactAdminSidebar ? (
                    <div className="space-y-2 text-center text-[11px] font-medium text-muted-foreground">
                      <div className="rounded-xl border bg-background px-2 py-2">
                        <div className="text-base font-semibold text-foreground">{tickets.length}</div>
                        <div>Tickets</div>
                      </div>
                      <div className={cn("rounded-xl border px-2 py-2", myOpenChatCardToneClassName)}>
                        <div className="text-base font-semibold text-foreground">{myOpenChatCount}</div>
                        <div>My Chats</div>
                      </div>
                    </div>
                  ) : (
                  <>
                    <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Overview</div>
                    <div className="mt-3 grid grid-cols-2 gap-3">
                      <div className="rounded-xl border bg-background px-3 py-3">
                        <div className="text-2xl font-bold">{tickets.length}</div>
                        <div className="text-xs text-muted-foreground">Tickets</div>
                      </div>
                      <div className={cn("rounded-xl border px-3 py-3", myOpenChatCardToneClassName)}>
                        <div className="text-2xl font-bold text-foreground">{myOpenChatCount}</div>
                        <div className="text-xs text-muted-foreground">My Open Chats</div>
                      </div>
                    </div>
                  </>
                )}
              </div>

              <div className={cn(
                "rounded-2xl border bg-secondary/35",
                useCompactAdminSidebar ? "p-2" : "p-2.5",
              )}>
                {useCompactAdminSidebar ? (
                  <div className="flex flex-col items-center gap-1 text-center">
                    <span className={cn("h-2.5 w-2.5 rounded-full", presenceDotClassName(myActualConsoleStatus))} />
                    <span className="text-[11px] font-semibold text-foreground">{myActualConsoleStatus}</span>
                  </div>
                ) : (
                  <>
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                      <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        My Status:
                      </div>
                      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                        <Select
                          value={consoleStatus || "Off"}
                          onValueChange={(value) => void updateConsoleStatus(value as AdminSelectableConsoleStatus)}
                          disabled={isUpdatingConsoleStatus}
                        >
                          <SelectTrigger
                            aria-label="Set your console status"
                            className={cn(
                              "h-8 w-full text-sm sm:w-[150px]",
                              (consoleStatus || "Off") === "Available"
                                ? "border-emerald-200 bg-emerald-50/80 text-emerald-700"
                                : "border-slate-200 bg-slate-50/80 text-slate-600",
                            )}
                          >
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {adminSelectableConsoleStatuses.map((status) => (
                              <SelectItem key={status} value={status}>{status}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        {isUpdatingConsoleStatus ? (
                          <span className="text-[11px] text-muted-foreground">Saving...</span>
                        ) : null}
                      </div>
                    </div>
                  </>
                )}
              </div>

              <TabsList className={cn(
                "grid h-auto w-full grid-cols-1 gap-2 bg-transparent p-0",
                useCompactAdminSidebar && "justify-items-center",
              )}>
                <TabsTrigger
                  value="dashboard"
                  className={cn(
                    "h-12 rounded-2xl border bg-background px-3 text-sm font-medium data-[state=active]:border-primary data-[state=active]:bg-primary/8 data-[state=active]:text-primary",
                    useCompactAdminSidebar ? "w-12 justify-center px-0" : "justify-start gap-3",
                  )}
                >
                  <LayoutDashboard className="h-4 w-4 shrink-0" />
                  {!useCompactAdminSidebar ? <span>Admin Dashboard</span> : null}
                </TabsTrigger>
                <TabsTrigger
                  value="coverage"
                  className={cn(
                    "h-12 rounded-2xl border bg-background px-3 text-sm font-medium data-[state=active]:border-primary data-[state=active]:bg-primary/8 data-[state=active]:text-primary",
                    useCompactAdminSidebar ? "w-12 justify-center px-0" : "justify-start gap-3",
                  )}
                >
                  <FileText className="h-4 w-4 shrink-0" />
                  {!useCompactAdminSidebar ? <span>Coverage Dashboard</span> : null}
                </TabsTrigger>
                <TabsTrigger
                  value="console"
                  className={cn(
                    "h-12 rounded-2xl border bg-background px-3 text-sm font-medium data-[state=active]:border-primary data-[state=active]:bg-primary/8 data-[state=active]:text-primary",
                    useCompactAdminSidebar ? "w-12 justify-center px-0" : "justify-start gap-3",
                  )}
                >
                  <MessageSquareText className="h-4 w-4 shrink-0" />
                  {!useCompactAdminSidebar ? <span>Chat Console</span> : null}
                </TabsTrigger>
                {canManageUsers ? (
                  <TabsTrigger
                    value="management"
                    className={cn(
                      "h-12 rounded-2xl border bg-background px-3 text-sm font-medium data-[state=active]:border-primary data-[state=active]:bg-primary/8 data-[state=active]:text-primary",
                      useCompactAdminSidebar ? "w-12 justify-center px-0" : "justify-start gap-3",
                    )}
                  >
                    <Settings2 className="h-4 w-4 shrink-0" />
                    {!useCompactAdminSidebar ? <span>Manage Agents</span> : null}
                  </TabsTrigger>
                ) : null}
              </TabsList>

              {!useCompactAdminSidebar && adminView === "console" ? (
                <div className="rounded-2xl border bg-secondary/35 p-3">
                  <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Search Queue</div>
                  <div className="mt-3 relative">
                    <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      value={consoleSearch}
                      onChange={(event) => setConsoleSearch(event.target.value)}
                      onFocus={() => setIsConsoleSearchOptionsVisible(true)}
                      placeholder="Search by learner name or chat ID"
                      className="pl-9"
                    />
                  </div>
                  {isConsoleSearchOptionsVisible || normalizedConsoleSearch ? (
                    <>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {([
                          { value: "all", label: "All" },
                          { value: "open", label: "Open" },
                          { value: "closed", label: "Closed" },
                        ] as const).map((filterOption) => (
                          <Button
                            key={filterOption.value}
                            type="button"
                            size="sm"
                            variant={consoleSearchStatusFilter === filterOption.value ? "default" : "outline"}
                            onClick={() => setConsoleSearchStatusFilter(filterOption.value)}
                            className={cn(
                              "rounded-full",
                              consoleSearchStatusFilter === filterOption.value && "border-0 gradient-primary",
                            )}
                          >
                            {filterOption.label}
                          </Button>
                        ))}
                      </div>
                      <div className="mt-2 text-[11px] text-muted-foreground">
                        {normalizedConsoleSearch
                          ? consoleSearchStatusFilter === "all"
                            ? "Search is checking both open and closed chats in the current case scope."
                            : `Search is limited to ${consoleSearchStatusFilter} chats in the current case scope.`
                          : "Choose All, Open, or Closed before browsing matching chats."}
                      </div>
                      {normalizedConsoleSearch ? (
                        <div className="mt-3 border-t pt-3">
                          <div className="mb-2 flex items-center justify-between text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                            <span>Results</span>
                            <span>{searchResultConsoleTickets.length}</span>
                          </div>
                          <div className="max-h-72 overflow-y-auto pr-1">
                            <ConsoleQueueList
                              tickets={searchResultConsoleTickets}
                              selectedTicketId={consoleTicketId}
                              onSelectTicket={openConsoleSearchResult}
                              emptyTone="success"
                              emptyMessage="No matching chats found."
                            />
                          </div>
                        </div>
                      ) : null}
                    </>
                  ) : null}
                </div>
              ) : null}

              <div className={cn("mt-auto flex gap-2", isStackedAdminLayout ? "flex-row flex-wrap" : "flex-col")}>
                <Button asChild variant="outline" size={useCompactAdminSidebar ? "icon" : "sm"} className={cn(!useCompactAdminSidebar && "justify-start")}>
                  <Link to="/">
                    <ArrowLeft className={cn("h-4 w-4", !useCompactAdminSidebar && "mr-2")} />
                    {!useCompactAdminSidebar ? "Back" : null}
                  </Link>
                </Button>
                <Button
                  variant="outline"
                  size={useCompactAdminSidebar ? "icon" : "sm"}
                  onClick={() => void loadDashboard()}
                  disabled={isLoading}
                  className={cn(!useCompactAdminSidebar && "justify-start")}
                >
                  <RefreshCw className={cn("h-4 w-4", isLoading && "animate-spin", !useCompactAdminSidebar && "mr-2")} />
                  {!useCompactAdminSidebar ? "Refresh" : null}
                </Button>
                <LogoutButton collapsed={useCompactAdminSidebar} />
              </div>
            </div>
          </aside>

          <div className={cn("flex min-w-0 w-full flex-1 flex-col", isStackedAdminLayout ? "overflow-visible" : "overflow-hidden")}>

          <TabsContent value="dashboard" className="mt-0 min-h-0 w-full flex-1 space-y-5 overflow-y-auto pr-1 sm:space-y-6">
            {renderDashboardWorkspace()}
          </TabsContent>

          <TabsContent value="coverage" className="mt-0 min-h-0 w-full flex-1 space-y-5 overflow-y-auto pr-1 sm:space-y-6">
            {renderDashboardWorkspace()}
          </TabsContent>


          <TabsContent value="management" className="mt-0 min-h-0 w-full flex-1 overflow-y-auto pr-1">
            <div className="space-y-6">
              <div className="rounded-3xl border bg-card shadow-card">
                <div className="border-b px-4 py-4 sm:px-5">
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <h2 className="text-lg font-semibold text-foreground">Agent Management</h2>
                      <p className="mt-1 text-sm text-muted-foreground">
                        Agents added here receive ticket assignments.
                      </p>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="relative w-full sm:w-[240px]">
                        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                        <Input
                          value={managementSearch}
                          onChange={(e) => setManagementSearch(e.target.value)}
                          placeholder="Search agents..."
                          className="pl-10"
                        />
                      </div>
                      <Button
                        className="shrink-0 border-0 gradient-primary"
                        onClick={() => {
                          setShowAddAgentSheet(true);
                          setAgentSearchQuery("");
                          setAgentSearchResults([]);
                        }}
                      >
                        <UserPlus className="mr-2 h-4 w-4" />
                        Add Agent
                      </Button>
                    </div>
                  </div>
                </div>

                <div className="divide-y">
                  {isLoading ? (
                    <div className="flex items-center justify-center gap-2 p-10 text-sm text-muted-foreground">
                      <LoaderCircle className="h-4 w-4 animate-spin" />
                      Loading agents...
                    </div>
                  ) : agents.filter((agent) => {
                    if (!managementSearch.trim()) return true;
                    const q = managementSearch.toLowerCase();
                    return (
                      (agent.fullName || "").toLowerCase().includes(q) ||
                      agent.username.toLowerCase().includes(q) ||
                      (agent.email || "").toLowerCase().includes(q)
                    );
                  }).length === 0 ? (
                    <div className="p-10 text-center text-sm text-muted-foreground">
                      No agents added yet. Use "Add Agent" to add someone from Microsoft Entra.
                    </div>
                  ) : (
                    agents
                      .filter((agent) => {
                        if (!managementSearch.trim()) return true;
                        const q = managementSearch.toLowerCase();
                        return (
                          (agent.fullName || "").toLowerCase().includes(q) ||
                          agent.username.toLowerCase().includes(q) ||
                          (agent.email || "").toLowerCase().includes(q)
                        );
                      })
                      .map((agent) => {
                        const isToggling = togglingAccessIds.has(agent.id);
                        const hasAccess = agent.legacySupportAccess === true;
                        const isCurrentUser = session?.id === agent.id;
                        const canRemoveAgent = agent.canRemoveFromAgentManagement === true && !isCurrentUser;
                        return (
                          <div key={agent.id} className="flex items-center justify-between gap-4 px-4 py-3.5 sm:px-5">
                            <div className="flex min-w-0 items-center gap-3">
                              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
                                <Users className="h-4 w-4" />
                              </div>
                              <div className="min-w-0">
                                <div className="truncate text-sm font-medium text-foreground">
                                  {agent.fullName || agent.username}
                                  {isCurrentUser ? <span className="ml-1.5 text-xs text-muted-foreground">(You)</span> : null}
                                </div>
                                <div className="truncate text-xs text-muted-foreground">
                                  @{agent.username}{agent.email ? ` · ${agent.email}` : ""}
                                </div>
                              </div>
                            </div>
                            <div className="flex shrink-0 items-center gap-3">
                              <span className={cn(
                                "hidden text-xs font-medium sm:block",
                                hasAccess ? "text-emerald-600" : "text-muted-foreground",
                              )}>
                                {hasAccess ? "Receives tickets" : "No ticket access"}
                              </span>
                              <Switch
                                checked={hasAccess}
                                disabled={isToggling}
                                onCheckedChange={(checked) => void toggleSupportAccess(agent, checked)}
                                aria-label={`Toggle support access for ${agent.fullName || agent.username}`}
                              />
                              {canRemoveAgent ? (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  disabled={removingAgentIds.has(agent.id)}
                                  onClick={() => setConfirmRemoveAgent(agent)}
                                  className="h-8 w-8 p-0 text-muted-foreground hover:text-destructive"
                                  aria-label={`Remove ${agent.fullName || agent.username}`}
                                >
                                  {removingAgentIds.has(agent.id) ? (
                                    <LoaderCircle className="h-4 w-4 animate-spin" />
                                  ) : (
                                    <X className="h-4 w-4" />
                                  )}
                                </Button>
                              ) : (
                                <span className="hidden w-8 text-center text-[10px] font-medium uppercase tracking-wide text-muted-foreground sm:inline">
                                  KBC
                                </span>
                              )}
                            </div>
                          </div>
                        );
                      })
                  )}
                </div>
              </div>
            </div>

            <Sheet open={showAddAgentSheet} onOpenChange={setShowAddAgentSheet}>
              <SheetContent className="w-full sm:max-w-md">
                <SheetHeader>
                  <SheetTitle>Add Agent</SheetTitle>
                  <SheetDescription>Search for a person in Microsoft Entra and add them as an agent.</SheetDescription>
                </SheetHeader>
                <div className="mt-6 space-y-4">
                  <div className="relative">
                    <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      placeholder="Search by name or email..."
                      className="pl-10"
                      value={agentSearchQuery}
                      onChange={(e) => {
                        setAgentSearchQuery(e.target.value);
                        void searchEntraAgents(e.target.value);
                      }}
                      autoFocus
                    />
                  </div>

                  {isSearchingAgents ? (
                    <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
                      <LoaderCircle className="h-4 w-4 animate-spin" />
                      Searching...
                    </div>
                  ) : agentSearchQuery.trim().length >= 2 && agentSearchResults.length === 0 ? (
                    <div className="py-8 text-center text-sm text-muted-foreground">
                      No results found in Microsoft Entra.
                    </div>
                  ) : (
                    <div className="divide-y rounded-2xl border">
                      {agentSearchResults.map((result) => (
                        <div key={result.entraId} className="flex items-center justify-between gap-3 px-4 py-3">
                          <div className="min-w-0">
                            <div className="truncate text-sm font-medium text-foreground">{result.displayName}</div>
                            <div className="truncate text-xs text-muted-foreground">{result.email}</div>
                          </div>
                          <Button
                            size="sm"
                            disabled={result.alreadyAdded || isAddingAgentId === result.entraId}
                            onClick={() => void addEntraAgent(result)}
                            className="shrink-0 border-0 gradient-primary"
                          >
                            {isAddingAgentId === result.entraId ? (
                              <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
                            ) : result.alreadyAdded ? (
                              "Added"
                            ) : (
                              "Add"
                            )}
                          </Button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                <SheetFooter className="mt-6">
                  <Button variant="outline" className="w-full" onClick={() => setShowAddAgentSheet(false)}>
                    Close
                  </Button>
                </SheetFooter>
              </SheetContent>
            </Sheet>

            <Dialog open={!!confirmRemoveAgent} onOpenChange={(open) => { if (!open) setConfirmRemoveAgent(null); }}>
              <DialogContent className="max-w-sm">
                <DialogHeader>
                  <DialogTitle>Remove Agent</DialogTitle>
                  <DialogDescription>
                    Are you sure you want to remove <span className="font-medium text-foreground">{confirmRemoveAgent?.fullName || confirmRemoveAgent?.username}</span> as an agent? They will lose support portal access.
                  </DialogDescription>
                </DialogHeader>
                <DialogFooter className="flex-col gap-2 sm:flex-row">
                  <Button variant="outline" className="w-full" onClick={() => setConfirmRemoveAgent(null)}>
                    Cancel
                  </Button>
                  <Button
                    variant="destructive"
                    className="w-full"
                    disabled={confirmRemoveAgent ? removingAgentIds.has(confirmRemoveAgent.id) : false}
                    onClick={() => {
                      if (!confirmRemoveAgent) return;
                      void removeAgentById(confirmRemoveAgent);
                      setConfirmRemoveAgent(null);
                    }}
                  >
                    Remove
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </TabsContent>

          <TabsContent value="console" className="mt-0 min-h-0 flex-1">
            <div className="h-full min-h-0 overflow-hidden rounded-3xl border bg-card p-3 shadow-card md:p-4">
              <div className="flex h-full flex-col">
                <div className="flex flex-wrap items-center gap-3">
                  <div className={cn(
                    "rounded-xl border px-4 py-2 text-sm font-medium",
                    hasCurrentAdminOpenConsoleQueue ? "border-destructive/20 bg-destructive/10 text-destructive" : "border-emerald-200 bg-emerald-50 text-emerald-700",
                  )}>
                    {hasCurrentAdminOpenConsoleQueue ? "Cases Available" : "No case available"}
                  </div>
                  {consoleDurationStart && consoleDurationLabel ? (
                    <div className="inline-flex items-center gap-2 rounded-xl border border-primary/15 bg-primary/[0.06] px-4 py-2">
                      <Clock className="h-4 w-4 text-primary" />
                      <div className="leading-none">
                        <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                          {consoleDurationStart.sourceLabel}
                        </div>
                        <div className="mt-1 font-mono text-sm font-semibold text-foreground">
                          {consoleDurationLabel}
                        </div>
                      </div>
                    </div>
                  ) : null}
                </div>

                <div className="mt-4 grid min-h-0 flex-1 gap-4 xl:grid-cols-[240px_minmax(0,1fr)]">
                  <section className="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-sky-200/80 bg-sky-50/30 shadow-soft">
                    <div className="border-b border-sky-200/80 bg-sky-50/55 px-4 py-4">
                      <div className="text-sm font-semibold">Cases</div>
                      <div className="text-xs text-muted-foreground">
                        Review all cases, and work from your own queue in My Cases.
                      </div>
                    </div>
                    <Tabs
                      value={consoleCaseScope}
                      onValueChange={(value) => setConsoleCaseScope(value as "my" | "all")}
                      className="flex min-h-0 flex-1 flex-col"
                    >
                      <TabsList className="mx-4 mt-4 grid w-[calc(100%-2rem)] grid-cols-2">
                        <TabsTrigger value="my">My Cases</TabsTrigger>
                        <TabsTrigger value="all">All Cases</TabsTrigger>
                      </TabsList>

                      {(["my", "all"] as const).map((scopeValue) => (
                        <TabsContent key={scopeValue} value={scopeValue} className="mt-0 min-h-0 flex-1">
                          <Tabs
                            value={consoleQueueTab}
                            onValueChange={(value) => setConsoleQueueTab(value as "open" | "closed")}
                            className="flex min-h-0 h-full flex-1 flex-col"
                          >
                            <TabsList className="mx-4 mt-4 grid w-[calc(100%-2rem)] grid-cols-2">
                              <TabsTrigger value="open">Open</TabsTrigger>
                              <TabsTrigger value="closed">Closed</TabsTrigger>
                            </TabsList>
                            <TabsContent value="open" className="mt-4 min-h-0 flex-1 overflow-y-auto px-4 pb-4">
                              <ConsoleQueueList
                                tickets={visibleOpenConsoleTickets}
                                selectedTicketId={consoleTicketId}
                                onSelect={openConsoleChat}
                                emptyTone="success"
                              />
                            </TabsContent>
                            <TabsContent value="closed" className="mt-4 min-h-0 flex-1 overflow-y-auto px-4 pb-4">
                              <ConsoleQueueList
                                tickets={visibleClosedConsoleTickets}
                                selectedTicketId={consoleTicketId}
                                onSelect={openConsoleChat}
                                emptyTone="success"
                              />
                            </TabsContent>
                          </Tabs>
                        </TabsContent>
                      ))}
                    </Tabs>
                  </section>

                  {isConsoleOpening ? (
                    <div className="flex min-h-[420px] items-center justify-center rounded-2xl border border-slate-300/80 bg-slate-50/50 text-sm text-muted-foreground">
                      <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> Opening chat console...
                    </div>
                  ) : consoleDetail && documentationDraft ? (
                    <div className="relative flex min-h-0 flex-col overflow-hidden rounded-2xl border border-slate-300/80 bg-background/75 shadow-soft">
                      <div className="absolute right-3 top-3 z-10 flex items-center gap-2">
                        <DropdownMenu
                          open={isTransferMenuOpen}
                          onOpenChange={(open) => {
                            setIsTransferMenuOpen(open);
                            if (!open) {
                              setTransferReason("");
                            }
                          }}
                        >
                          <DropdownMenuTrigger asChild>
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              disabled={!canTransferConsoleTicket || isTransferringConsoleTicket}
                              title={
                                !consoleDetail
                                  ? "Open a ticket first."
                                  : consoleWorkspaceReadOnly
                                    ? "Transfer is available only while editing your assigned case."
                                    : consoleDetail.ticket.pendingTransferRequest
                                      ? "A transfer request is already pending for this ticket."
                                    : transferTargetAgents.length === 0
                                      ? "No other admins are available to receive this ticket."
                                      : "Send a transfer request to another admin."
                              }
                              className={cn(
                                "h-8 rounded-full px-3 shadow-sm",
                                "bg-background/80 backdrop-blur hover:bg-background",
                              )}
                            >
                              {isTransferringConsoleTicket ? (
                                <LoaderCircle className="h-4 w-4 animate-spin" />
                              ) : null}
                              {consoleDetail?.ticket.pendingTransferRequest ? "Transfer Pending" : "Transfer"}
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end" sideOffset={8} className="w-80 rounded-2xl p-2">
                            <div className="px-2 pb-2 pt-1">
                              <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                                Transfer Chat
                              </div>
                            </div>
                            <div className="px-2 pb-3">
                              <Label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                                Transfer Reason
                              </Label>
                              <Textarea
                                value={transferReason}
                                onChange={(event) => setTransferReason(event.target.value)}
                                rows={3}
                                placeholder="Add a short handoff note for the next admin..."
                                className="min-h-[88px] resize-none rounded-xl bg-background"
                              />
                              <div className="mt-1 text-[11px] text-muted-foreground">
                                This note will be saved in the ticket activity log with the transfer.
                              </div>
                            </div>
                            <div className="space-y-1">
                              {transferTargetAgents.length === 0 ? (
                                <div className="rounded-xl px-3 py-3 text-sm text-muted-foreground">
                                  No other admins are available to receive this ticket right now.
                                </div>
                              ) : (
                                transferTargetAgents.map((agent) => (
                                  <button
                                    key={agent.id}
                                    type="button"
                                    onClick={() => void handleTransferConsoleTicket(agent)}
                                    className="flex w-full rounded-xl px-3 py-2 text-left transition-colors hover:bg-secondary/70"
                                  >
                                    <AgentStatusLabel agent={agent} />
                                  </button>
                                ))
                              )}
                            </div>
                          </DropdownMenuContent>
                        </DropdownMenu>
                        <Button
                          type="button"
                          variant={canForceCloseConsoleChat ? "destructive" : "outline"}
                          size="sm"
                          onClick={() => void handleForceCloseConsoleChat()}
                          disabled={!canForceCloseConsoleChat || isForceClosingConsoleChat}
                          title={
                            canForceCloseConsoleChat
                              ? "Force-close this still-open chat under a closed ticket."
                              : "Available only when the ticket is closed and the chat is still open."
                          }
                          className={cn(
                            "h-8 rounded-full px-3 shadow-sm",
                            !canForceCloseConsoleChat && "bg-background/80 backdrop-blur hover:bg-background",
                          )}
                        >
                          <AlertOctagon className="h-4 w-4" />
                          {isForceClosingConsoleChat ? "Closing..." : "Force Close Chat"}
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={collapseConsoleWorkspace}
                          aria-label="Retract workspace"
                          className={cn(
                            "h-8 w-8 rounded-full",
                            consoleWorkspaceReadOnlyMessage
                              ? "text-amber-700 hover:bg-amber-100 hover:text-amber-900"
                              : "bg-background/80 text-muted-foreground shadow-sm backdrop-blur hover:bg-background",
                          )}
                        >
                          <X className="h-4 w-4" />
                        </Button>
                      </div>
                      {consoleWorkspaceReadOnlyMessage ? (
                        <div className="border-b bg-amber-50 px-4 py-3 pr-56 text-sm text-amber-800 sm:pr-72">
                          {consoleWorkspaceReadOnlyMessage}
                        </div>
                      ) : null}
                      {consoleTransferHandoffNotice ? (
                        <div className="border-b bg-sky-50/90 px-4 py-3 pr-56 text-sm text-sky-900 sm:pr-72">
                          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-sky-700">
                            Transfer Note
                          </div>
                          <div className="mt-1 font-medium">
                            Transferred from {consoleTransferHandoffNotice.transferredFrom}
                          </div>
                          <div className="mt-1 text-sky-900/85">
                            {consoleTransferHandoffNotice.reason}
                          </div>
                          <div className="mt-2 text-xs text-sky-700/80">
                            {formatDateTime(consoleTransferHandoffNotice.createdAt)}
                          </div>
                        </div>
                      ) : null}
                      <div className={cn(
                        "grid min-h-0 flex-1 gap-4 p-4 xl:grid-cols-[minmax(0,1.7fr)_minmax(320px,0.95fr)_minmax(320px,0.95fr)] xl:grid-rows-1 xl:items-stretch",
                        !hasConsoleWorkspaceBanner && "pt-14",
                      )}>
                        <div className="flex min-h-0 flex-col gap-4 overflow-y-auto pr-1 xl:h-full xl:overflow-hidden xl:pr-0">
                          <ConsoleSectionCard
                            title="Learner Information"
                            description={consoleWorkspaceReadOnly ? "This case is open for review only in the current tab." : "This case is assigned to you and ready for live handling."}
                            className="shrink-0 border-blue-200/80 bg-blue-50/30"
                            headerClassName="border-blue-200/80 bg-blue-50/55"
                            contentClassName="min-h-0 flex-1 overflow-y-auto p-4"
                            resizable
                            defaultHeight={250}
                            minHeight={180}
                            resizeHandlePosition="bottom"
                          >
                            <div className="grid gap-3 sm:grid-cols-2">
                              <ConsoleField label="Name" icon={UserRound} value={consoleDetail.ticket.learnerName || "-"} />
                              <ConsoleField label="E-mail" icon={Mail} value={consoleDetail.ticket.email || "-"} />
                              <ConsoleField label="Requester Role" icon={UserRound} value={formatRequesterRoleLabel(consoleDetail.ticket.requesterRole)} />
                              <ConsoleField label="Phone" icon={Phone} value={consoleDetail.ticket.learnerPhone || "-"} />
                              <ConsoleField label="Category / Subcategory" icon={TicketIcon} value={formatCategoryLabel(consoleDetail.ticket.category, consoleDetail.ticket.technicalSubcategory)} />
                              <ConsoleField label="Chat ID" icon={Hash} value={getDisplayedChatReference(consoleDetail.ticket)} />
                              <ConsoleField label="Ticket ID" icon={Hash} value={consoleDetail.ticket.id} />
                              <ConsoleField label="Inquiry" icon={MessageSquareText} value={consoleDetail.ticket.inquiry || "-"} className="sm:col-span-2" />
                            </div>
                          </ConsoleSectionCard>

                          <ConsoleChatPanel
                            className="min-h-0 flex-1 border-indigo-200/80 bg-white"
                            headerClassName="border-indigo-200/80 bg-indigo-50/55"
                            title="Kent Chatbot"
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
                              consoleWorkspaceReadOnly
                                ? "This case is read-only in the current tab."
                                : liveChatLocked
                                ? "This chat is closed."
                                : consoleDetail.ticket.liveChatRequested
                                  ? "Type your message..."
                                  : "The learner must choose Live Chat before admin replies are enabled."
                            }
                            emptyMessage="No live chat messages are available for this conversation yet."
                            headerMeta={consoleDetail.ticket.liveChatRequested ? `Chat ID: ${consoleDetail.ticket.chatId || "No chat ID"}` : "Waiting for learner live chat request"}
                            icon={Headphones}
                          />
                        </div>

                      <ConsoleSectionCard
                        title="Documentation"
                        description="Step through case notes, ticket outcome, and learner resolution before finalizing the chat."
                        className="min-h-0 h-full border-violet-200/80 bg-violet-50/30"
                        headerClassName="border-violet-200/80 bg-violet-50/55"
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
                          readOnly={isDocumentationReadOnly}
                          attachments={consoleDetail.attachments}
                          sessionRequests={consoleDetail.sessionRequests}
                          onFieldChange={updateDocumentationField}
                          onImagesAdded={handleDocumentationImagesAdded}
                          onRemoveImage={removeDocumentationImage}
                          onTicketStatusChange={setDocumentationTicketStatus}
                          onStatusReasonChange={setDocumentationStatusReason}
                          escalationTargetAgents={documentationEscalationTargetAgents}
                          escalationAgentId={documentationEscalationAgentId}
                          escalationNote={documentationEscalationNote}
                          escalationAssigneeLabel={documentationEscalationAssigneeLabel}
                          selectedEscalationAgent={selectedDocumentationEscalationAgent}
                          onEscalationAgentChange={setDocumentationEscalationAgentId}
                          onEscalationNoteChange={setDocumentationEscalationNote}
                          onIssuesAddressedChange={setDocumentationIssuesAddressed}
                          onBack={() => setDocumentationStep((currentStep) => Math.max(1, currentStep - 1))}
                          onNext={() => setDocumentationStep((currentStep) => Math.min(3, currentStep + 1))}
                          onSaveOnly={() => void saveDocumentation()}
                          onSubmit={() => void runDocumentationWorkflow()}
                          canMoveForward={canMoveDocumentationForward}
                        />
                      </ConsoleSectionCard>

                      <ConsoleChatPanel
                        className="min-h-0 h-full border-emerald-200/80 bg-emerald-50/25"
                        headerClassName="border-emerald-200/80 bg-emerald-50/55"
                        title="AI Agent"
                        subtitle={`Admin status: ${consoleStatus || "Off"}`}
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
                        sendDisabled={consoleWorkspaceReadOnly || isSendingAiMessage}
                        sendLabel={isSendingAiMessage ? "Sending..." : "Send"}
                        placeholder={consoleWorkspaceReadOnly ? "Switch to My Cases to use the AI assistant on your assigned case." : "Ask the AI agent for the next step..."}
                        emptyMessage="Start an AI handoff to capture workflow guidance for this ticket."
                        headerMeta={getSuggestedAiAction(consoleDetail.ticket, consoleDetail.attachments.length)}
                        icon={Bot}
                      />
                    </div>
                  </div>
                ) : (
                  <div className="flex min-h-[420px] items-center justify-center rounded-2xl border border-dashed border-slate-300/80 bg-slate-50/40 px-8 text-center">
                    <div className="max-w-xl">
                      {hasCurrentAdminOpenConsoleQueue ? (
                        <div className="mx-auto max-w-sm rounded-3xl border border-red-200 bg-red-50/80 px-8 py-8 shadow-soft">
                          <div className="text-3xl font-semibold uppercase tracking-[0.12em] text-red-600">Chats Available</div>
                          <div className="mt-3 text-sm leading-6 text-red-800/80">
                            Open a chat from the sidebar to start working on the next available learner case.
                          </div>
                        </div>
                      ) : (
                        <div className="mx-auto max-w-sm rounded-3xl border border-emerald-200 bg-emerald-50/80 px-8 py-8 shadow-soft">
                          <div className="text-3xl font-semibold uppercase tracking-[0.12em] text-emerald-600">No Chats</div>
                          <div className="mt-3 text-sm leading-6 text-emerald-800/80">
                            {consoleAvailabilityEmptyMessage}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}
                </div>
              </div>
            </div>
          </TabsContent>
          </div>
        </div>
      </Tabs>

      <Sheet open={!!activeTicketId} onOpenChange={(open) => !open && closePanel()}>
        <SheetContent className={cn(
          "w-full overflow-y-auto",
          isActiveCoverageTicket || isActiveStandardDocumentationTicket ? "sm:max-w-6xl" : "sm:max-w-3xl",
        )}>
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
                  {activeDetail.ticket.learnerName || activeDetail.ticket.email} - {formatTicketHeaderCategoryLabel(activeDetail.ticket.category, activeDetail.ticket.technicalSubcategory)}
                </SheetDescription>
              </SheetHeader>

              {isActiveCoverageTicket && activeCoverageDocumentationDraft ? (
                <CoverageTicketWorkspace
                  ticket={activeDetail.ticket}
                  history={activeDetail.history}
                  draft={activeCoverageDocumentationDraft}
                  readOnly={activeCoverageDocumentationReadOnly}
                  isSaving={isSavingActiveDocumentation}
                  isSavingDetails={isSaving}
                  isDirty={activeCoverageDocumentationDirty}
                  notes={notes}
                  onNotesChange={setNotes}
                  draftStatus={draftStatus}
                  onDraftStatusChange={setDraftStatus}
                  statusOptions={activeDetail.ticket.status === "Closed" ? statuses : statuses.filter((status) => status !== "Closed")}
                  canAssignActiveTicket={canAssignActiveTicket}
                  draftAgentId={draftAgentId}
                  onDraftAgentChange={setDraftAgentId}
                  selectedDraftAgent={selectedDraftAgent}
                  assignableAdminAgents={assignableAdminAgents}
                  isActiveTicketAlreadyAssigned={isActiveTicketAlreadyAssigned}
                  isSlaAutoManaged={isSlaAutoManaged}
                  effectiveDraftSlaStatus={effectiveDraftSlaStatus}
                  onDraftSlaStatusChange={setDraftSlaStatus}
                  slaStatuses={slaStatuses}
                  isStatusChanging={isStatusChanging}
                  canSubmitStatusChange={canSubmitStatusChange}
                  onFieldChange={updateActiveDocumentationField}
                  onDraftUpdate={updateActiveCoverageDocumentation}
                  onCancel={closePanel}
                  onSave={() => void saveActiveCoverageDocumentation()}
                  onSaveDetails={() => void saveTicket({ successMessage: "Changes saved" })}
                  onSubmitTutorChoiceCard={(cardId) => void submitActiveCoverageTutorChoiceCard(cardId)}
                  onConfirmTutorSession={(cardId) => void confirmActiveCoverageTutorSession(cardId)}
                />
              ) : (
                <>
                  <div className="space-y-5 py-5">
                    <Tabs
                      value={effectiveActiveTicketTab}
                      onValueChange={(value) => setActiveTicketTab(value as TicketDetailTab)}
                      className="space-y-4"
                    >
                  <TabsList className={cn("grid w-full", isActiveQuickTicket ? "grid-cols-2" : "grid-cols-3")}>
                    {!isActiveQuickTicket ? (
                      <TabsTrigger value="conversation">
                        <MessageSquareText className="mr-2 h-4 w-4" /> Conversation
                      </TabsTrigger>
                    ) : null}
                    <TabsTrigger value="documentation">
                      <FileText className="mr-2 h-4 w-4" /> Documentation
                    </TabsTrigger>
                    <TabsTrigger value="details">
                      <TicketIcon className="mr-2 h-4 w-4" /> Ticket Details
                    </TabsTrigger>
                  </TabsList>

                  {!isActiveQuickTicket ? (
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
                  ) : null}

                  <TabsContent value="documentation" className="space-y-5">
                    {isActiveStandardDocumentationTicket && activeStandardDocumentationDraft ? (
                      <StandardDocumentationWorkspace
                        ticket={activeDetail.ticket}
                        draft={activeStandardDocumentationDraft}
                        attachments={activeDetail.attachments}
                        readOnly={!isActiveStandardDocumentationTicket}
                        isSaving={isSaving}
                        isDirty={activeStandardDocumentationDirty}
                        onDraftUpdate={updateActiveStandardDocumentation}
                      />
                    ) : (
                      <section>
                        <Label className="mb-1.5 block">Documentation</Label>
                        <div className="rounded-xl border p-3">
                          <DocumentationAccordionReadOnly
                            draft={activeDetail.ticket.documentation}
                            attachments={activeDetail.attachments}
                            sessionRequests={activeDetail.sessionRequests}
                          />
                        </div>
                      </section>
                    )}
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
                        <Label className="mb-1.5 block">Assign Admin</Label>
                        {canAssignActiveTicket ? (
                          <>
                            <Select value={draftAgentId} onValueChange={setDraftAgentId}>
                              <SelectTrigger>
                                {selectedDraftAgent ? (
                                  <AgentStatusLabel agent={selectedDraftAgent} />
                                ) : (
                                  <span className="text-sm text-foreground">Select admin</span>
                                )}
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="unassigned">Unassigned</SelectItem>
                                {assignableAdminAgents.map((agent) => (
                                  <SelectItem key={agent.id} value={String(agent.id)} className="py-2">
                                    <AgentStatusLabel agent={agent} />
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                            <p className="mt-1 text-xs text-muted-foreground">
                              Only superadmins can assign or reassign tickets to admin accounts.
                            </p>
                          </>
                        ) : (
                          <>
                            <div className="rounded-xl border bg-secondary/20 px-3 py-2.5">
                              {selectedDraftAgent ? (
                                <AgentStatusLabel agent={selectedDraftAgent} />
                              ) : (
                                <span className="text-sm text-foreground">Unassigned</span>
                              )}
                            </div>
                            <p className="mt-1 text-xs text-muted-foreground">
                              {isActiveTicketAlreadyAssigned
                                ? "Only superadmins can reassign this ticket."
                                : "Only superadmins can assign or reassign tickets to admin accounts."}
                            </p>
                          </>
                        )}
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
                      <InfoCard label="Requester E-mail" value={activeDetail.ticket.email} />
                      <InfoCard label="Requester Role" value={formatRequesterRoleLabel(activeDetail.ticket.requesterRole)} />
                      <InfoCard label="Assigned Team" value={activeDetail.ticket.assignedTeam} />
                      <InfoCard label="Category" value={formatCategoryLabel(activeDetail.ticket.category, activeDetail.ticket.technicalSubcategory)} />
                      <InfoCard label="Status Reason" value={getDisplayedTicketStatusReason(activeDetail.ticket)} />
                      <InfoCard label="Created" value={formatDateTime(activeDetail.ticket.createdAt)} />
                      <InfoCard label="Updated" value={formatDateTime(activeDetail.ticket.updatedAt)} />
                      <InfoCard label="Priority" value={activeDetail.ticket.priority} />
                      <InfoCard label="Evidence Count" value={String(activeDetail.ticket.evidenceCount)} />
                    </div>

                    <section>
                      <Label className="mb-1.5 block">Activity log</Label>
                      <ActivityLogTimeline history={activeDetail.history} />
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

              <SheetFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
                <Button
                  variant="outline"
                  className="w-full sm:w-auto"
                  onClick={() => void saveTicket({
                    status: "Closed",
                    statusReason: "Closed via Agent",
                    successMessage: "Ticket closed",
                  })}
                  disabled={isSaving}
                >
                  <X className="h-4 w-4 mr-2" /> Close
                </Button>
                <Button
                  className="w-full gradient-primary border-0 sm:w-auto"
                  onClick={() => void saveTicket({ successMessage: "Changes saved" })}
                  disabled={isSaving || !canSubmitStatusChange}
                >
                  {isSaving ? <LoaderCircle className="h-4 w-4 mr-2 animate-spin" /> : <Save className="h-4 w-4 mr-2" />}
                  Save Changes
                </Button>
              </SheetFooter>
                </>
              )}
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

function useVerticalPanelResize({
  enabled,
  defaultHeight,
  minHeight,
  handlePosition,
}: {
  enabled: boolean;
  defaultHeight: number;
  minHeight: number;
  handlePosition: "top" | "bottom";
}) {
  const [height, setHeight] = useState(defaultHeight);
  const resizeStateRef = useRef<{ startY: number; startHeight: number } | null>(null);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    const handleMouseMove = (event: MouseEvent) => {
      if (!resizeStateRef.current) {
        return;
      }

      const deltaY = event.clientY - resizeStateRef.current.startY;
      const nextHeight = handlePosition === "top"
        ? resizeStateRef.current.startHeight - deltaY
        : resizeStateRef.current.startHeight + deltaY;

      setHeight(Math.max(minHeight, nextHeight));
    };

    const handleMouseUp = () => {
      resizeStateRef.current = null;
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
    };

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);

    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
    };
  }, [enabled, handlePosition, minHeight]);

  const startResize = (event: ReactMouseEvent<HTMLDivElement>) => {
    if (!enabled) {
      return;
    }

    event.preventDefault();
    resizeStateRef.current = {
      startY: event.clientY,
      startHeight: height,
    };
    document.body.style.userSelect = "none";
    document.body.style.cursor = "row-resize";
  };

  return { height, startResize };
}

const VerticalResizeHandle = ({
  position,
  onMouseDown,
}: {
  position: "top" | "bottom";
  onMouseDown: (event: ReactMouseEvent<HTMLDivElement>) => void;
}) => (
  <div
    className={cn(
      "group flex h-3 shrink-0 cursor-row-resize items-center justify-center bg-secondary/20 transition-colors hover:bg-secondary/40",
      position === "top" ? "border-b" : "border-t",
    )}
    onMouseDown={onMouseDown}
    role="separator"
    aria-orientation="horizontal"
  >
    <GripHorizontal className="h-3.5 w-3.5 text-muted-foreground transition-colors group-hover:text-foreground" />
  </div>
);

const ConsoleQueueList = ({
  tickets,
  selectedTicketId,
  onSelect,
  onSelectTicket,
  emptyTone,
  emptyMessage = "No case available",
}: {
  tickets: TicketSummary[];
  selectedTicketId: string;
  onSelect?: (ticketId: string) => Promise<void>;
  onSelectTicket?: (ticket: TicketSummary) => Promise<void>;
  emptyTone: "success" | "destructive";
  emptyMessage?: string;
}) => {
  if (tickets.length === 0) {
    return (
      <div className={cn(
        "rounded-2xl border px-4 py-5 text-sm font-medium",
        emptyTone === "success" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-destructive/20 bg-destructive/10 text-destructive",
      )}>
        {emptyMessage}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {tickets.map((ticket) => {
        const assignedAgentAccent = getAssignedAgentAccent(ticket.assignedAgentId, ticket.assignedAgentName);

        return (
          <button
            key={ticket.id}
            type="button"
            onClick={() => {
              if (onSelectTicket) {
                void onSelectTicket(ticket);
                return;
              }
              if (onSelect) {
                void onSelect(ticket.id);
              }
            }}
            className={cn(
              "relative w-full overflow-hidden rounded-2xl border px-3 py-3 text-left transition-all",
              selectedTicketId === ticket.id
                ? "border-primary bg-primary/6 shadow-soft"
                : "border-border bg-background hover:bg-secondary/40",
            )}
          >
            <span
              aria-hidden="true"
              className={cn("absolute inset-y-0 left-0 w-1 rounded-l-2xl", assignedAgentAccent.stripeClassName)}
            />
            <div className="flex items-center justify-between gap-3">
              <span className="font-mono text-xs font-semibold">{getDisplayedChatReference(ticket, true)}</span>
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
            <div className="mt-2">
              <RequesterRoleBadge role={ticket.requesterRole} />
            </div>
            <div className="mt-1 text-xs text-muted-foreground">{formatCategoryLabel(ticket.category, ticket.technicalSubcategory)}</div>
            <div className="mt-2">
              <AssignedAgentBadge
                assignedAgentId={ticket.assignedAgentId}
                assignedAgentName={ticket.assignedAgentName}
                statusReason={ticket.statusReason}
                documentation={ticket.documentation}
                pendingEscalationNotification={ticket.pendingEscalationNotification}
                latestEscalationClosure={ticket.latestEscalationClosure}
                latestTransferDecision={ticket.latestTransferDecision}
              />
            </div>
          </button>
        );
      })}
    </div>
  );
};

const AssignedAgentBadge = ({
  assignedAgentId,
  assignedAgentName,
  statusReason,
  documentation,
  pendingEscalationNotification,
  latestEscalationClosure,
  latestTransferDecision,
}: {
  assignedAgentId: number | null;
  assignedAgentName: string;
  statusReason: string;
  documentation?: Pick<AdminDocumentation, "escalationAgentId" | "escalationAgentName"> | null;
  pendingEscalationNotification?: PendingEscalationNotification | null;
  latestEscalationClosure?: LatestEscalationClosure | null;
  latestTransferDecision?: LatestTransferDecision | null;
}) => {
  const accent = getAssignedAgentAccent(assignedAgentId, assignedAgentName);
  const label = getAssignedAgentBadgeLabel(
    assignedAgentName,
    statusReason,
    documentation,
    pendingEscalationNotification,
    latestEscalationClosure,
    latestTransferDecision,
  );

  return (
    <span className={cn(
      "inline-flex max-w-full items-center gap-2 rounded-full border px-2.5 py-1 text-[11px] font-medium",
      accent.badgeClassName,
    )} title={label}>
      <span className={cn("h-2 w-2 shrink-0 rounded-full", accent.dotClassName)} />
      <span className="truncate">{label}</span>
    </span>
  );
};

const AgentStatusLabel = ({
  agent,
}: {
  agent: Pick<AdminAgent, "fullName" | "username" | "consoleStatus">;
}) => {
  const agentStatus = normalizeAdminConsoleStatus(agent.consoleStatus);

  return (
    <div className="flex w-full items-center justify-between gap-3">
      <span className="truncate font-medium">{getAgentDisplayName(agent)}</span>
      <span className="inline-flex shrink-0 items-center gap-2 rounded-full border bg-background/70 px-2 py-0.5 text-[11px] text-muted-foreground">
        <span className={cn("h-2 w-2 rounded-full", presenceDotClassName(agentStatus))} />
        {agentStatus}
      </span>
    </div>
  );
};

const AdminNotificationsPanel = ({
  coverageTickets,
  requests,
  escalations,
  teamsCalls,
  waitingLiveChats,
  currentConsoleStatus,
  isUpdatingConsoleStatus,
  coverageResponses,
  escalationUpdates,
  decisionUpdates,
  notificationLog,
  activeTicketId,
  onDecision,
  onOpenTeamsCall,
  onAcknowledgeCoverageTicket,
  onAcknowledgeEscalation,
  onAcknowledgeEscalationUpdate,
  onAcknowledgeCoverageResponse,
  onAcknowledgeDecision,
  onOpenTicket,
  onSetAvailable,
}: {
  coverageTickets: TicketSummary[];
  requests: TicketSummary[];
  escalations: TicketSummary[];
  teamsCalls: TicketSummary[];
  waitingLiveChats: TicketSummary[];
  currentConsoleStatus: AdminConsoleStatus;
  isUpdatingConsoleStatus: boolean;
  coverageResponses: TicketSummary[];
  escalationUpdates: TicketSummary[];
  decisionUpdates: TicketSummary[];
  notificationLog: AdminNotificationLogItem[];
  activeTicketId: string;
  onDecision: (ticket: TicketSummary, action: "accept" | "reject") => Promise<void>;
  onOpenTeamsCall: (ticket: TicketSummary) => Promise<void>;
  onAcknowledgeCoverageTicket: (ticket: TicketSummary) => Promise<void>;
  onAcknowledgeEscalation: (ticket: TicketSummary, openChat?: boolean) => Promise<void>;
  onAcknowledgeEscalationUpdate: (ticket: TicketSummary) => Promise<void>;
  onAcknowledgeCoverageResponse: (ticket: TicketSummary) => Promise<void>;
  onAcknowledgeDecision: (ticket: TicketSummary) => Promise<void>;
  onOpenTicket: (ticketId: string) => Promise<void>;
  onSetAvailable: () => void;
}) => {
  if (
    coverageTickets.length === 0
    && requests.length === 0
    && escalations.length === 0
    && teamsCalls.length === 0
    && waitingLiveChats.length === 0
    && coverageResponses.length === 0
    && escalationUpdates.length === 0
    && decisionUpdates.length === 0
    && notificationLog.length === 0
  ) {
    return (
      <div className="rounded-2xl px-3 py-4 text-sm text-muted-foreground">
        No admin notifications right now.
      </div>
    );
  }

  return (
    <div>
      <div className="border-b px-3 pb-3 pt-2">
        <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
          Admin Notifications
        </div>
        <div className="mt-1 text-xs text-muted-foreground">
          Review active alerts and the recent notification log for new coverage tickets, transfer, escalation, coverage tutor replies, Teams calls, and waiting live chat activity.
        </div>
      </div>
      <div className="max-h-[420px] space-y-2 overflow-y-auto p-2">
        {coverageTickets.length > 0 ? (
          <div className="px-1 pt-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
            New Coverage Tickets
          </div>
        ) : null}
        {coverageTickets.map((ticket) => {
          const pendingCoverageTicketNotification = ticket.pendingCoverageTicketNotification;
          if (!pendingCoverageTicketNotification) {
            return null;
          }

          const isBusy = activeTicketId === ticket.id;

          return (
            <div key={`${ticket.id}-${pendingCoverageTicketNotification.createdAt}`} className="rounded-2xl border border-primary/20 bg-primary/5 px-3 py-3 shadow-soft">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-mono text-xs font-semibold text-primary">Ticket {pendingCoverageTicketNotification.ticketId}</div>
                  <div className="mt-1 truncate text-sm font-semibold text-foreground">
                    {pendingCoverageTicketNotification.requesterName || ticket.learnerName || ticket.email || "Requester"}
                  </div>
                  <div className="mt-2">
                    <RequesterRoleBadge
                      role={pendingCoverageTicketNotification.requesterRole || ticket.requesterRole}
                      className="border-primary/20 bg-white/80 text-primary"
                    />
                  </div>
                  <div className="mt-1 text-xs text-primary/75">
                    Coverage ticket created • {formatDateTime(pendingCoverageTicketNotification.createdAt)}
                  </div>
                </div>
                <StatusBadge status={ticket.status} label={getDisplayedTicketStatus(ticket)} />
              </div>
              {ticket.inquiryPreview ? (
                <div className="mt-3 rounded-xl border border-primary/15 bg-background px-3 py-2 text-sm leading-6 text-foreground">
                  {ticket.inquiryPreview}
                </div>
              ) : null}
              <div className="mt-3 flex gap-2">
                <Button
                  size="sm"
                  className="border-0 gradient-primary"
                  disabled={Boolean(activeTicketId)}
                  onClick={() => void onOpenTicket(ticket.id)}
                >
                  {isBusy ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : null}
                  Open Ticket
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={Boolean(activeTicketId)}
                  onClick={() => void onAcknowledgeCoverageTicket(ticket)}
                >
                  Dismiss
                </Button>
              </div>
            </div>
          );
        })}
        {requests.length > 0 ? (
          <div className="px-1 pt-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
            Incoming Requests
          </div>
        ) : null}
        {requests.map((ticket) => {
          const pendingTransferRequest = ticket.pendingTransferRequest;
          if (!pendingTransferRequest) {
            return null;
          }

          const isBusy = activeTicketId === ticket.id;

          return (
            <div key={ticket.id} className="rounded-2xl border bg-background px-3 py-3 shadow-soft">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-mono text-xs font-semibold text-primary">{ticket.id}</div>
                  <div className="mt-1 truncate text-sm font-semibold text-foreground">
                    {ticket.learnerName || ticket.email || "Learner"}
                  </div>
                  <div className="mt-2">
                    <RequesterRoleBadge role={ticket.requesterRole} className="border-primary/20 bg-primary/5 text-primary" />
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    From {pendingTransferRequest.fromAgentName} • {formatDateTime(pendingTransferRequest.requestedAt)}
                  </div>
                </div>
                <StatusBadge status={ticket.status} label={getDisplayedTicketStatus(ticket)} />
              </div>
              <div className="mt-3 rounded-xl border bg-secondary/30 px-3 py-2 text-sm leading-6 text-foreground">
                {pendingTransferRequest.reason}
              </div>
              <div className="mt-3 flex gap-2">
                <Button
                  size="sm"
                  className="border-0 gradient-primary"
                  disabled={Boolean(activeTicketId)}
                  onClick={() => void onDecision(ticket, "accept")}
                >
                  {isBusy ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : null}
                  Accept
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={Boolean(activeTicketId)}
                  onClick={() => void onDecision(ticket, "reject")}
                >
                  Decline
                </Button>
              </div>
            </div>
          );
        })}
        {escalations.length > 0 ? (
          <div className="px-1 pt-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
            Escalation Notices
          </div>
        ) : null}
        {escalations.map((ticket) => {
          const pendingEscalationNotification = ticket.pendingEscalationNotification;
          if (!pendingEscalationNotification) {
            return null;
          }

          const isBusy = activeTicketId === ticket.id;

          return (
            <div key={`${ticket.id}-${pendingEscalationNotification.requestedAt}`} className="rounded-2xl border border-amber-200 bg-amber-50/60 px-3 py-3 shadow-soft">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-mono text-xs font-semibold text-amber-900">Ticket {pendingEscalationNotification.ticketId}</div>
                  <div className="mt-1 truncate text-sm font-semibold text-foreground">
                    {ticket.learnerName || ticket.email || "Learner"}
                  </div>
                  <div className="mt-2">
                    <RequesterRoleBadge role={ticket.requesterRole} className="border-amber-300 bg-white/70 text-amber-900" />
                  </div>
                  <div className="mt-1 text-xs text-amber-900/75">
                    From {pendingEscalationNotification.fromAgentName} to {pendingEscalationNotification.toAgentName}
                  </div>
                </div>
                <StatusBadge status={ticket.status} label={getDisplayedTicketStatus(ticket)} />
              </div>
              <div className="mt-3 rounded-xl border border-amber-200 bg-background px-3 py-2 text-sm leading-6 text-foreground">
                {pendingEscalationNotification.note}
              </div>
              <div className="mt-3 flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={Boolean(activeTicketId)}
                  onClick={() => void onAcknowledgeEscalation(ticket)}
                >
                  {isBusy ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : null}
                  Dismiss
                </Button>
              </div>
            </div>
          );
        })}
        {teamsCalls.length > 0 ? (
          <div className="px-1 pt-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
            Teams Call Requests
          </div>
        ) : null}
        {teamsCalls.map((ticket) => {
          const pendingTeamsCallNotification = ticket.pendingTeamsCallNotification;
          if (!pendingTeamsCallNotification) {
            return null;
          }

          const isBusy = activeTicketId === ticket.id;

          return (
            <div key={`${ticket.id}-${pendingTeamsCallNotification.requestedAt}`} className="rounded-2xl border border-primary/20 bg-primary/5 px-3 py-3 shadow-soft">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-mono text-xs font-semibold text-primary">Ticket {pendingTeamsCallNotification.ticketId}</div>
                  <div className="mt-1 truncate text-sm font-semibold text-foreground">
                    {ticket.learnerName || pendingTeamsCallNotification.requesterName || ticket.email || "Learner"}
                  </div>
                  <div className="mt-2">
                    <RequesterRoleBadge role={pendingTeamsCallNotification.requesterRole || ticket.requesterRole} className="border-primary/20 bg-white/80 text-primary" />
                  </div>
                  <div className="mt-1 text-xs text-primary/75">
                    Direct Teams call requested for {pendingTeamsCallNotification.toAgentName} • {formatDateTime(pendingTeamsCallNotification.requestedAt)}
                  </div>
                </div>
                <StatusBadge status={ticket.status} label={getDisplayedTicketStatus(ticket)} />
              </div>
              <div className="mt-3 rounded-xl border border-primary/15 bg-background px-3 py-2 text-sm leading-6 text-foreground">
                {pendingTeamsCallNotification.note}
              </div>
              {ticket.inquiryPreview ? (
                <div className="mt-2 rounded-xl border bg-secondary/30 px-3 py-2 text-sm leading-6 text-foreground">
                  {ticket.inquiryPreview}
                </div>
              ) : null}
              <div className="mt-3 flex gap-2">
                <Button
                  size="sm"
                  className="border-0 gradient-primary"
                  disabled={Boolean(activeTicketId)}
                  onClick={() => void onOpenTeamsCall(ticket)}
                >
                  {isBusy ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : null}
                  Open Documentation
                </Button>
              </div>
            </div>
          );
        })}
        {waitingLiveChats.length > 0 ? (
          <div className="px-1 pt-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
            Waiting Live Chats
          </div>
        ) : null}
        {waitingLiveChats.map((ticket) => {
          const isBusy = activeTicketId === ticket.id;
          const canSetAvailable = currentConsoleStatus === "Off";

          return (
            <div key={`${ticket.id}-${ticket.liveChatRequestedAt || ticket.createdAt}`} className="rounded-2xl border border-amber-200 bg-amber-50/60 px-3 py-3 shadow-soft">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-mono text-xs font-semibold text-amber-900">{ticket.id}</div>
                  <div className="mt-1 truncate text-sm font-semibold text-foreground">
                    {ticket.learnerName || ticket.email || "Learner"}
                  </div>
                  <div className="mt-2">
                    <RequesterRoleBadge role={ticket.requesterRole} className="border-amber-300 bg-white/70 text-amber-900" />
                  </div>
                  <div className="mt-1 text-xs text-amber-900/75">
                    Live chat requested • {formatDateTime(ticket.liveChatRequestedAt || ticket.createdAt)}
                  </div>
                </div>
                <StatusBadge status={ticket.status} label={getDisplayedTicketStatus(ticket)} />
              </div>
              <div className="mt-3 rounded-xl border border-amber-200 bg-background px-3 py-2 text-sm leading-6 text-foreground">
                A learner is waiting for a live agent, but no admin was available at the time of the request.
              </div>
              {ticket.inquiryPreview ? (
                <div className="mt-2 rounded-xl border bg-secondary/30 px-3 py-2 text-sm leading-6 text-foreground">
                  {ticket.inquiryPreview}
                </div>
              ) : null}
              <div className="mt-3 flex gap-2">
                {canSetAvailable ? (
                  <Button
                    size="sm"
                    disabled={isUpdatingConsoleStatus}
                    onClick={onSetAvailable}
                  >
                    {isUpdatingConsoleStatus ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : null}
                    Set Available
                  </Button>
                ) : null}
                <Button
                  size="sm"
                  variant={canSetAvailable ? "outline" : "default"}
                  disabled={Boolean(activeTicketId)}
                  onClick={() => void onOpenTicket(ticket.id)}
                >
                  {isBusy ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : null}
                  Open Ticket
                </Button>
              </div>
            </div>
          );
        })}
        {coverageResponses.length > 0 ? (
          <div className="px-1 pt-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
            Coverage Tutor Replies
          </div>
        ) : null}
        {coverageResponses.map((ticket) => {
          const latestCoverageTutorResponse = ticket.latestCoverageTutorResponse;
          if (!latestCoverageTutorResponse) {
            return null;
          }

          const isBusy = activeTicketId === ticket.id;
          const wasAccepted = latestCoverageTutorResponse.outcome === "accepted";

          return (
            <div
              key={`${ticket.id}-${latestCoverageTutorResponse.cardId}-${latestCoverageTutorResponse.respondedAt}`}
              className={cn(
                "rounded-2xl border px-3 py-3 shadow-soft",
                wasAccepted
                  ? "border-emerald-200 bg-emerald-50/60"
                  : "border-rose-200 bg-rose-50/60",
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className={cn(
                    "font-mono text-xs font-semibold",
                    wasAccepted ? "text-emerald-900" : "text-rose-900",
                  )}>
                    Ticket {latestCoverageTutorResponse.ticketId}
                  </div>
                  <div className="mt-1 truncate text-sm font-semibold text-foreground">
                    {ticket.learnerName || ticket.email || "Learner"}
                  </div>
                  <div className="mt-2">
                    <RequesterRoleBadge
                      role={ticket.requesterRole}
                      className={cn(
                        wasAccepted
                          ? "border-emerald-300 bg-white/70 text-emerald-900"
                          : "border-rose-300 bg-white/70 text-rose-900",
                      )}
                    />
                  </div>
                  <div className={cn(
                    "mt-1 text-xs",
                    wasAccepted ? "text-emerald-900/75" : "text-rose-900/75",
                  )}>
                    {wasAccepted ? "Accepted" : "Rejected"} by {latestCoverageTutorResponse.tutor} • {formatDateTime(latestCoverageTutorResponse.respondedAt)}
                  </div>
                </div>
                <StatusBadge status={ticket.status} label={getDisplayedTicketStatus(ticket)} />
              </div>
              {latestCoverageTutorResponse.sessionDetails ? (
                <div className="mt-3 rounded-xl border bg-background px-3 py-2 text-sm leading-6 text-foreground">
                  {latestCoverageTutorResponse.sessionDetails}
                </div>
              ) : null}
              {latestCoverageTutorResponse.replyText ? (
                <div className="mt-2 rounded-xl border bg-secondary/30 px-3 py-2 text-sm leading-6 text-foreground">
                  {latestCoverageTutorResponse.replyText}
                </div>
              ) : null}
              <div className="mt-3 flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={Boolean(activeTicketId)}
                  onClick={() => void onOpenTicket(ticket.id)}
                >
                  {isBusy ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : null}
                  Open Ticket
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={Boolean(activeTicketId)}
                  onClick={() => void onAcknowledgeCoverageResponse(ticket)}
                >
                  Dismiss
                </Button>
              </div>
            </div>
          );
        })}
        {escalationUpdates.length > 0 ? (
          <div className="px-1 pt-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
            Escalation Updates
          </div>
        ) : null}
        {escalationUpdates.map((ticket) => {
          const latestEscalationClosure = ticket.latestEscalationClosure;
          if (!latestEscalationClosure) {
            return null;
          }

          const isBusy = activeTicketId === ticket.id;

          return (
            <div key={`${ticket.id}-${latestEscalationClosure.closedAt}`} className="rounded-2xl border border-emerald-200 bg-emerald-50/60 px-3 py-3 shadow-soft">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-mono text-xs font-semibold text-emerald-900">Ticket {latestEscalationClosure.ticketId}</div>
                  <div className="mt-1 truncate text-sm font-semibold text-foreground">
                    {ticket.learnerName || ticket.email || "Learner"}
                  </div>
                  <div className="mt-2">
                    <RequesterRoleBadge role={ticket.requesterRole} className="border-emerald-300 bg-white/70 text-emerald-900" />
                  </div>
                  <div className="mt-1 text-xs text-emerald-900/75">
                    From {latestEscalationClosure.fromAgentName} to {latestEscalationClosure.toAgentName}
                  </div>
                  <div className="mt-1 text-xs text-emerald-900/75">
                    Closed by {latestEscalationClosure.closedByName} • {formatDateTime(latestEscalationClosure.closedAt)}
                  </div>
                </div>
                <StatusBadge status={ticket.status} label={getDisplayedTicketStatus(ticket)} />
              </div>
              <div className="mt-3 rounded-xl border border-emerald-200 bg-background px-3 py-2 text-sm leading-6 text-foreground">
                {latestEscalationClosure.note}
              </div>
              <div className="mt-3 flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={Boolean(activeTicketId)}
                  onClick={() => void onAcknowledgeEscalationUpdate(ticket)}
                >
                  {isBusy ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : null}
                  Dismiss
                </Button>
              </div>
            </div>
          );
        })}
        {decisionUpdates.length > 0 ? (
          <div className="px-1 pt-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
            Transfer Updates
          </div>
        ) : null}
        {decisionUpdates.map((ticket) => {
          const latestTransferDecision = ticket.latestTransferDecision;
          if (!latestTransferDecision) {
            return null;
          }

          const isBusy = activeTicketId === ticket.id;
          const wasAccepted = latestTransferDecision.status === "accepted";

          return (
            <div key={`${ticket.id}-${latestTransferDecision.decidedAt}`} className="rounded-2xl border bg-background px-3 py-3 shadow-soft">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-mono text-xs font-semibold text-primary">{ticket.id}</div>
                  <div className="mt-1 truncate text-sm font-semibold text-foreground">
                    {ticket.learnerName || ticket.email || "Learner"}
                  </div>
                  <div className="mt-2">
                    <RequesterRoleBadge role={ticket.requesterRole} className="border-primary/20 bg-primary/5 text-primary" />
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {wasAccepted ? "Accepted" : "Declined"} by {latestTransferDecision.decidedByName} • {formatDateTime(latestTransferDecision.decidedAt)}
                  </div>
                </div>
                <span className={cn(
                  "inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[11px] font-medium",
                  wasAccepted
                    ? "bg-emerald-100 text-emerald-700"
                    : "bg-slate-100 text-slate-700",
                )}>
                  {wasAccepted ? "Accepted" : "Declined"}
                </span>
              </div>
              <div className={cn(
                "mt-3 rounded-xl border px-3 py-2 text-sm leading-6",
                wasAccepted
                  ? "border-emerald-200 bg-emerald-50 text-emerald-900"
                  : "border-slate-200 bg-slate-50 text-slate-900",
              )}>
                {wasAccepted
                  ? `Transferred to ${latestTransferDecision.toAgentName}.`
                  : `${latestTransferDecision.decidedByName} declined this transfer request.`}
              </div>
              <div className="mt-2 rounded-xl border bg-secondary/30 px-3 py-2 text-sm leading-6 text-foreground">
                {latestTransferDecision.reason}
              </div>
              <div className="mt-3 flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={Boolean(activeTicketId)}
                  onClick={() => void onAcknowledgeDecision(ticket)}
                >
                  {isBusy ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : null}
                  Dismiss
                </Button>
              </div>
            </div>
          );
        })}
        {notificationLog.length > 0 ? (
          <div className="px-1 pt-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
            Recent Log
          </div>
        ) : null}
        {notificationLog.map((item) => (
          <AdminNotificationLogCard
            key={`notification-log-${item.id}`}
            item={item}
            onOpenTicket={onOpenTicket}
          />
        ))}
      </div>
    </div>
  );
};

const AdminNotificationLogCard = ({
  item,
  onOpenTicket,
}: {
  item: AdminNotificationLogItem;
  onOpenTicket: (ticketId: string) => Promise<void>;
}) => {
  const tone = getActivityEventTone(item.eventType);
  const detail = getAdminNotificationLogDetail(item);

  return (
    <div className="rounded-2xl border bg-background px-3 py-3 shadow-soft">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <span className={cn(
            "inline-flex rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.14em]",
            tone.badgeClassName,
          )}>
            {getActivityEventLabel(item.eventType)}
          </span>
          <div className="mt-2 font-mono text-xs font-semibold text-primary">
            {getDisplayedChatReference(item, true)}
          </div>
          <div className="mt-1 truncate text-sm font-semibold text-foreground">
            {item.learnerName || item.email || "Learner"}
          </div>
          <div className="mt-2">
            <RequesterRoleBadge role={item.requesterRole} className="border-primary/20 bg-primary/5 text-primary" />
          </div>
          <div className="mt-2 text-sm font-medium text-foreground">
            {getActivityEventSummary(item)}
          </div>
          {detail ? (
            <div className="mt-2 rounded-xl border bg-secondary/30 px-3 py-2 text-sm leading-6 text-foreground">
              {detail}
            </div>
          ) : null}
          <div className="mt-2 text-xs text-muted-foreground">
            {formatDateTime(item.createdAt)}
          </div>
        </div>
        <StatusBadge status={item.status} label={getDisplayedTicketStatus(item)} />
      </div>
      <div className="mt-3 flex gap-2">
        <Button
          size="sm"
          variant="outline"
          onClick={() => void onOpenTicket(item.ticketId)}
        >
          Open Ticket
        </Button>
      </div>
    </div>
  );
};

const ConsoleSectionCard = ({
  title,
  description,
  children,
  className,
  headerClassName,
  contentClassName,
  footer,
  resizable = false,
  defaultHeight = 320,
  minHeight = 180,
  resizeHandlePosition = "bottom",
}: {
  title: string;
  description: string;
  children: ReactNode;
  className?: string;
  headerClassName?: string;
  contentClassName?: string;
  footer?: ReactNode;
  resizable?: boolean;
  defaultHeight?: number;
  minHeight?: number;
  resizeHandlePosition?: "top" | "bottom";
}) => {
  const { height, startResize } = useVerticalPanelResize({
    enabled: resizable,
    defaultHeight,
    minHeight,
    handlePosition: resizeHandlePosition,
  });

  return (
    <section
      className={cn("flex min-h-0 flex-col overflow-hidden rounded-2xl border bg-background/80 shadow-soft", className)}
      style={resizable ? { height: `${height}px` } : undefined}
    >
      {resizable && resizeHandlePosition === "top" ? <VerticalResizeHandle position="top" onMouseDown={startResize} /> : null}
      <div className={cn("border-b px-4 py-4", headerClassName)}>
        <div className="font-semibold">{title}</div>
        <div className="text-xs text-muted-foreground">{description}</div>
      </div>
      <div className={cn("min-h-0 p-4", contentClassName)}>{children}</div>
      {footer}
      {resizable && resizeHandlePosition === "bottom" ? <VerticalResizeHandle position="bottom" onMouseDown={startResize} /> : null}
    </section>
  );
};

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
  className,
  headerClassName,
  resizable = false,
  defaultHeight = 420,
  minHeight = 240,
  resizeHandlePosition = "bottom",
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
  className?: string;
  headerClassName?: string;
  resizable?: boolean;
  defaultHeight?: number;
  minHeight?: number;
  resizeHandlePosition?: "top" | "bottom";
}) => {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const shouldStickToBottomRef = useRef(true);
  const { height, startResize } = useVerticalPanelResize({
    enabled: resizable,
    defaultHeight,
    minHeight,
    handlePosition: resizeHandlePosition,
  });

  useEffect(() => {
    shouldStickToBottomRef.current = true;

    if (!scrollRef.current) {
      return;
    }

    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [headerMeta]);

  useEffect(() => {
    if (!scrollRef.current) {
      return;
    }

    if (!shouldStickToBottomRef.current) {
      return;
    }

    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages]);

  const handleScroll = () => {
    if (!scrollRef.current) {
      return;
    }

    const distanceFromBottom = scrollRef.current.scrollHeight - scrollRef.current.scrollTop - scrollRef.current.clientHeight;
    shouldStickToBottomRef.current = distanceFromBottom <= 80;
  };

  return (
    <section
      className={cn("flex min-h-0 flex-col overflow-hidden rounded-2xl border bg-card shadow-soft", className)}
      style={resizable ? { height: `${height}px` } : undefined}
    >
      {resizable && resizeHandlePosition === "top" ? <VerticalResizeHandle position="top" onMouseDown={startResize} /> : null}
      <div className={cn("border-b bg-card px-4 py-3.5", headerClassName)}>
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 flex-1 items-center gap-2">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <Icon className="h-4 w-4" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-semibold">{title}</div>
              <div className="truncate text-xs text-muted-foreground">{subtitle}</div>
            </div>
          </div>
          <span className={cn(
            "shrink-0 rounded-full border px-3 py-1 text-xs font-medium",
            statusTone === "success" && "border-emerald-200 bg-emerald-50 text-emerald-700",
            statusTone === "warning" && "border-amber-200 bg-amber-50 text-amber-700",
            statusTone === "muted" && "border-border bg-secondary text-muted-foreground",
            statusTone === "info" && "border-info/20 bg-info/10 text-info",
          )}>
            {statusLabel}
          </span>
        </div>
        <div className="mt-2 flex items-center gap-2 pl-10">
          <div className="truncate text-xs text-muted-foreground">{headerMeta}</div>
        </div>
      </div>

      <div className="min-h-0 flex-1 bg-gradient-to-b from-background to-card">
        <div ref={scrollRef} onScroll={handleScroll} className="h-full space-y-4 overflow-y-auto px-4 py-5">
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
      {resizable && resizeHandlePosition === "bottom" ? <VerticalResizeHandle position="bottom" onMouseDown={startResize} /> : null}
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

const CoverageTicketDetailsPanel = ({
  ticket,
  history,
  readOnly,
  isSaving,
  notes,
  onNotesChange,
  draftStatus,
  onDraftStatusChange,
  statusOptions,
  canAssignActiveTicket,
  draftAgentId,
  onDraftAgentChange,
  selectedDraftAgent,
  assignableAdminAgents,
  isActiveTicketAlreadyAssigned,
  isSlaAutoManaged,
  effectiveDraftSlaStatus,
  onDraftSlaStatusChange,
  slaStatuses,
  isStatusChanging,
  canSubmitStatusChange,
  onCancel,
  onSaveDetails,
}: {
  ticket: TicketDetail;
  history: HistoryItem[];
  readOnly: boolean;
  isSaving: boolean;
  notes: string;
  onNotesChange: (value: string) => void;
  draftStatus: TicketSummary["status"];
  onDraftStatusChange: (value: TicketSummary["status"]) => void;
  statusOptions: TicketSummary["status"][];
  canAssignActiveTicket: boolean;
  draftAgentId: string;
  onDraftAgentChange: (value: string) => void;
  selectedDraftAgent: AdminAgent | null;
  assignableAdminAgents: AdminAgent[];
  isActiveTicketAlreadyAssigned: boolean;
  isSlaAutoManaged: boolean;
  effectiveDraftSlaStatus: TicketSummary["slaStatus"];
  onDraftSlaStatusChange: (value: TicketSummary["slaStatus"]) => void;
  slaStatuses: TicketSummary["slaStatus"][];
  isStatusChanging: boolean;
  canSubmitStatusChange: boolean;
  onCancel: () => void;
  onSaveDetails: () => void;
}) => (
  <div className="space-y-5">
    <div className="grid gap-3 md:grid-cols-3">
      <div>
        <Label className="mb-1.5 block">Status</Label>
        <div className="rounded-xl border bg-secondary/20 px-3 py-2.5 text-sm text-foreground">
          {draftStatus}
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          Coverage ticket status is managed by the workflow.
        </p>
      </div>
      <div>
        <Label className="mb-1.5 block">Assign Agent</Label>
        {canAssignActiveTicket && !readOnly ? (
          <>
            <Select value={draftAgentId} onValueChange={onDraftAgentChange}>
              <SelectTrigger>
                {selectedDraftAgent ? (
                  <AgentStatusLabel agent={selectedDraftAgent} />
                ) : (
                  <span className="text-sm text-foreground">Select agent</span>
                )}
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="unassigned">Unassigned</SelectItem>
                {assignableAdminAgents.map((agent) => (
                  <SelectItem key={agent.id} value={String(agent.id)} className="py-2">
                    <AgentStatusLabel agent={agent} />
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="mt-1 text-xs text-muted-foreground">
              Only superadmins can assign or reassign tickets to agent accounts.
            </p>
          </>
        ) : (
          <>
            <div className="rounded-xl border bg-secondary/20 px-3 py-2.5">
              {selectedDraftAgent ? (
                <AgentStatusLabel agent={selectedDraftAgent} />
              ) : (
                <span className="text-sm text-foreground">Unassigned</span>
              )}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {isActiveTicketAlreadyAssigned
                ? "Only superadmins can reassign this ticket."
                : "Only superadmins can assign or reassign tickets to agent accounts."}
            </p>
          </>
        )}
      </div>
      <div>
        <Label className="mb-1.5 block">{isSlaAutoManaged ? "SLA (Automatic)" : "SLA"}</Label>
        <Select
          value={effectiveDraftSlaStatus}
          onValueChange={(value) => onDraftSlaStatusChange(value as TicketSummary["slaStatus"])}
          disabled={readOnly || isSaving || isSlaAutoManaged}
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
      <InfoCard label="Requester E-mail" value={ticket.email} />
      <InfoCard label="Requester Role" value={formatRequesterRoleLabel(ticket.requesterRole)} />
      <InfoCard label="Assigned Team" value={ticket.assignedTeam} />
      <InfoCard label="Category" value={formatCategoryLabel(ticket.category, ticket.technicalSubcategory)} />
      <InfoCard label="Status Reason" value={getDisplayedTicketStatusReason(ticket)} />
      <InfoCard label="Created" value={formatDateTime(ticket.createdAt)} />
      <InfoCard label="Updated" value={formatDateTime(ticket.updatedAt)} />
      <InfoCard label="Priority" value={ticket.priority} />
      <InfoCard label="Evidence Count" value={String(ticket.evidenceCount)} />
    </div>

    <section>
      <Label className="mb-1.5 block">Activity log</Label>
      <ActivityLogTimeline history={history} />
    </section>

    <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4">
      <div className="text-xs text-muted-foreground">
        {readOnly ? "Closed tickets are view-only." : "Review ticket metadata, then save your changes. Coverage tickets close after a tutor accepts the request."}
      </div>
      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        {!readOnly ? (
          <Button onClick={onSaveDetails} className="border-0 gradient-primary" disabled={isSaving || !canSubmitStatusChange}>
            {isSaving ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
            Save Changes
          </Button>
        ) : null}
      </div>
    </div>
  </div>
);

const CoverageTicketWorkspace = ({
  ticket,
  history,
  draft,
  readOnly,
  isSaving,
  isSavingDetails,
  isDirty,
  notes,
  onNotesChange,
  draftStatus,
  onDraftStatusChange,
  statusOptions,
  canAssignActiveTicket,
  draftAgentId,
  onDraftAgentChange,
  selectedDraftAgent,
  assignableAdminAgents,
  isActiveTicketAlreadyAssigned,
  isSlaAutoManaged,
  effectiveDraftSlaStatus,
  onDraftSlaStatusChange,
  slaStatuses,
  isStatusChanging,
  canSubmitStatusChange,
  onFieldChange,
  onDraftUpdate,
  onCancel,
  onSave,
  onSaveDetails,
  onSubmitTutorChoiceCard,
  onConfirmTutorSession,
}: {
  ticket: TicketDetail;
  history: HistoryItem[];
  draft: AdminDocumentation;
  readOnly: boolean;
  isSaving: boolean;
  isSavingDetails: boolean;
  isDirty: boolean;
  notes: string;
  onNotesChange: (value: string) => void;
  draftStatus: TicketSummary["status"];
  onDraftStatusChange: (value: TicketSummary["status"]) => void;
  statusOptions: TicketSummary["status"][];
  canAssignActiveTicket: boolean;
  draftAgentId: string;
  onDraftAgentChange: (value: string) => void;
  selectedDraftAgent: AdminAgent | null;
  assignableAdminAgents: AdminAgent[];
  isActiveTicketAlreadyAssigned: boolean;
  isSlaAutoManaged: boolean;
  effectiveDraftSlaStatus: TicketSummary["slaStatus"];
  onDraftSlaStatusChange: (value: TicketSummary["slaStatus"]) => void;
  slaStatuses: TicketSummary["slaStatus"][];
  isStatusChanging: boolean;
  canSubmitStatusChange: boolean;
  onFieldChange: (field: keyof AdminDocumentation, value: string) => void;
  onDraftUpdate: (updater: (draft: AdminDocumentation) => AdminDocumentation) => void;
  onCancel: () => void;
  onSave: () => void;
  onSaveDetails: () => void;
  onSubmitTutorChoiceCard: (cardId: string) => void;
  onConfirmTutorSession: (cardId: string) => void;
}) => {
  const [tutorOptions, setTutorOptions] = useState<string[]>([]);
  const [coverageTutorError, setCoverageTutorError] = useState("");
  const [isLoadingTutorOptions, setIsLoadingTutorOptions] = useState(false);
  const [previewAttachment, setPreviewAttachment] = useState<CoverageCardAttachment | null>(null);
  const [editingTutorEmailCardIds, setEditingTutorEmailCardIds] = useState<Set<string>>(new Set());
  const [loadingTutorEmailCardIds, setLoadingTutorEmailCardIds] = useState<Set<string>>(new Set());
  const [collapsedCoverageCardIds, setCollapsedCoverageCardIds] = useState<Set<string>>(new Set());
  const [workspaceTab, setWorkspaceTab] = useState<CoverageWorkspaceTab>("documentation");
  const hasSavedCoverageSnapshot = Boolean(ticket.documentation?.coverageCards?.length || ticket.documentation?.coverageNotes?.trim());
  const previewAttachmentKind = getCoverageAttachmentPreviewKind(previewAttachment);
  const parsedCoverageInquiry = parseCoverageInquiry(draft.inquiry);
  const coverageInquiryModule = parsedCoverageInquiry?.module?.trim() || "";

  useEffect(() => {
    setWorkspaceTab("documentation");
  }, [ticket.id]);

  useEffect(() => {
    setCollapsedCoverageCardIds(new Set());
  }, [ticket.id]);

  useEffect(() => {
    let cancelled = false;
    setIsLoadingTutorOptions(true);
    setCoverageTutorError("");

    void fetchCoverageOptions("tutors", coverageInquiryModule ? { module: coverageInquiryModule } : undefined)
      .then((options) => {
        if (cancelled) {
          return;
        }

        setTutorOptions(options);
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }

        setTutorOptions([]);
        setCoverageTutorError(error instanceof Error ? error.message : "We could not load the tutors right now.");
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoadingTutorOptions(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [coverageInquiryModule, ticket.id]);

  const expandCoverageHistoryCards = () => {
    setCollapsedCoverageCardIds(new Set());
  };

  const updateCoverageCard = (cardId: string, updates: Partial<CoverageWorkflowCard>) => {
    const timestamp = new Date().toISOString();
    expandCoverageHistoryCards();
    onDraftUpdate((currentDraft) => ({
      ...currentDraft,
      coverageCards: currentDraft.coverageCards.map((card) => (
        card.id === cardId
          ? {
              ...card,
              ...updates,
              updatedAt: timestamp,
            }
          : card
      )),
    }));
  };

  const addTutorChoiceCard = () => {
    expandCoverageHistoryCards();
    onDraftUpdate((currentDraft) => ({
      ...currentDraft,
      coverageCards: [...currentDraft.coverageCards, createCoverageTutorChoiceCard(currentDraft.inquiry)],
    }));
  };

  const addNoteCard = () => {
    expandCoverageHistoryCards();
    onDraftUpdate((currentDraft) => ({
      ...currentDraft,
      coverageCards: [...currentDraft.coverageCards, createCoverageNoteCard()],
    }));
  };

  const removeCoverageCard = (cardId: string) => {
    onDraftUpdate((currentDraft) => ({
      ...currentDraft,
      coverageCards: currentDraft.coverageCards.filter((card) => card.id !== cardId),
    }));
    setEditingTutorEmailCardIds((currentIds) => {
      if (!currentIds.has(cardId)) {
        return currentIds;
      }

      const nextIds = new Set(currentIds);
      nextIds.delete(cardId);
      return nextIds;
    });
  };

  const setTutorEmailEditing = (cardId: string, isEditing: boolean) => {
    setEditingTutorEmailCardIds((currentIds) => {
      const nextIds = new Set(currentIds);
      if (isEditing) {
        nextIds.add(cardId);
      } else {
        nextIds.delete(cardId);
      }
      return nextIds;
    });
  };

  const setTutorEmailLoading = (cardId: string, isLoading: boolean) => {
    setLoadingTutorEmailCardIds((currentIds) => {
      const nextIds = new Set(currentIds);
      if (isLoading) {
        nextIds.add(cardId);
      } else {
        nextIds.delete(cardId);
      }
      return nextIds;
    });
  };

  const handleTutorChange = (cardId: string, tutor: string) => {
    expandCoverageHistoryCards();
    updateCoverageCard(cardId, {
      tutor,
      tutorEmail: "",
    });
    setTutorEmailEditing(cardId, false);
    setTutorEmailLoading(cardId, false);

    if (!tutor.trim()) {
      return;
    }

    setTutorEmailLoading(cardId, true);
    void fetchCoverageTutorEmail(tutor)
      .then((email) => {
        onDraftUpdate((currentDraft) => ({
          ...currentDraft,
          coverageCards: currentDraft.coverageCards.map((card) => (
            card.id === cardId && card.tutor === tutor
              ? {
                  ...card,
                  tutorEmail: email,
                  updatedAt: new Date().toISOString(),
                }
              : card
          )),
        }));
        setTutorEmailEditing(cardId, !email);
      })
      .catch((error: unknown) => {
        setTutorEmailEditing(cardId, true);
        toast.error(error instanceof Error ? error.message : "We could not load the tutor e-mail right now.");
      })
      .finally(() => {
        setTutorEmailLoading(cardId, false);
      });
  };

  const handlePresentationFilesAdded = async (cardId: string, event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || []);
    event.target.value = "";

    if (files.length === 0) {
      return;
    }

    try {
      expandCoverageHistoryCards();
      const nextFiles = await Promise.all(files.map(readFileAsCoverageCardAttachment));
      onDraftUpdate((currentDraft) => ({
        ...currentDraft,
        coverageCards: currentDraft.coverageCards.map((card) => (
          card.id === cardId
            ? {
                ...card,
                presentationFiles: [...card.presentationFiles, ...nextFiles],
                updatedAt: new Date().toISOString(),
              }
            : card
        )),
      }));
    } catch {
      toast.error("We could not read one or more presentation files right now.");
    }
  };

  const removePresentationFile = (cardId: string, fileId: string) => {
    expandCoverageHistoryCards();
    onDraftUpdate((currentDraft) => ({
      ...currentDraft,
      coverageCards: currentDraft.coverageCards.map((card) => (
        card.id === cardId
          ? {
              ...card,
              presentationFiles: card.presentationFiles.filter((file) => file.id !== fileId),
              updatedAt: new Date().toISOString(),
            }
          : card
      )),
    }));
  };

  const toggleCoverageCardCollapsed = (cardId: string) => {
    setCollapsedCoverageCardIds((currentIds) => {
      const nextIds = new Set(currentIds);
      if (nextIds.has(cardId)) {
        nextIds.delete(cardId);
      } else {
        nextIds.add(cardId);
      }
      return nextIds;
    });
  };
  const coverageCardsForDisplay = sortCoverageWorkflowCardsForDisplay(draft.coverageCards);

  return (
    <div className="space-y-4 py-4">
      <Tabs value={workspaceTab} onValueChange={(value) => setWorkspaceTab(value as CoverageWorkspaceTab)} className="space-y-4">
        <TabsList className="grid w-full grid-cols-2 rounded-2xl border border-primary/10 bg-white/80 p-1 shadow-soft">
          <TabsTrigger value="documentation" className="h-11 rounded-xl border border-transparent bg-transparent text-sm font-semibold data-[state=active]:border-primary/15 data-[state=active]:bg-primary/[0.08] data-[state=active]:text-primary">
            <FileText className="mr-2 h-4 w-4" /> Documentation
          </TabsTrigger>
          <TabsTrigger value="details" className="h-11 rounded-xl border border-transparent bg-transparent text-sm font-semibold data-[state=active]:border-primary/15 data-[state=active]:bg-primary/[0.08] data-[state=active]:text-primary">
            <TicketIcon className="mr-2 h-4 w-4" /> Ticket Details
          </TabsTrigger>
        </TabsList>

        <TabsContent value="documentation" className="space-y-5">
          <div className="grid items-stretch gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(320px,0.9fr)]">
            <div className="h-full rounded-[30px] border border-primary/12 bg-gradient-to-br from-white via-primary/[0.025] to-violet-50/70 p-5 shadow-[0_22px_45px_rgba(82,54,188,0.08)]">
              <div className="flex h-full flex-col space-y-3">
                <div className="inline-flex items-center rounded-full border border-primary/15 bg-primary/[0.08] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-primary">
                  Inquiry
                </div>
                {parseCoverageInquiry(draft.inquiry) ? (
                  <CoverageInquirySummary inquiry={draft.inquiry} />
                ) : (
                  <Textarea
                    value={draft.inquiry}
                    onChange={(event) => onFieldChange("inquiry", event.target.value)}
                    readOnly={readOnly || hasSavedCoverageSnapshot}
                    placeholder="Document the learner inquiry..."
                    className="min-h-[220px] rounded-2xl border-primary/12 bg-background"
                  />
                )}
                {!readOnly && hasSavedCoverageSnapshot ? (
                  <p className="text-xs text-muted-foreground">
                    Saved inquiry details are frozen and kept as the original submitted request.
                  </p>
                ) : null}
              </div>
            </div>

            <div className="h-full rounded-[30px] border border-primary/12 bg-gradient-to-br from-white via-violet-50/80 to-primary/[0.06] p-5 shadow-[0_22px_45px_rgba(82,54,188,0.08)]">
              <div className="flex h-full flex-col space-y-3">
                <div className="inline-flex items-center rounded-full border border-primary/15 bg-white/90 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-primary">
                  Ticket Note
                </div>
                <Textarea
                  rows={7}
                  placeholder="Add an internal note for the ticket..."
                  value={notes}
                  onChange={(event) => onNotesChange(event.target.value)}
                  readOnly={readOnly}
                  className="min-h-[230px] flex-1 rounded-2xl border-primary/12 bg-white/90 shadow-none xl:min-h-0"
                />
                {isStatusChanging ? (
                  <p className={cn("text-xs", canSubmitStatusChange ? "text-muted-foreground" : "text-destructive")}>
                    A note is required before changing this ticket status.
                  </p>
                ) : (
                  <p className="text-xs text-muted-foreground">
                    This note belongs to the ticket itself and is visible to support staff only.
                  </p>
                )}
              </div>
            </div>
          </div>

          <div className="rounded-[30px] border border-primary/12 bg-gradient-to-br from-white via-white to-primary/[0.04] p-5 shadow-[0_22px_45px_rgba(82,54,188,0.08)]">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <div className="inline-flex items-center rounded-full border border-primary/15 bg-primary/[0.08] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-primary">
                  Coverage Cards
                </div>
                <p className="mt-2 text-sm text-muted-foreground">
                  Track tutor outreach, responses, and follow-up actions in one place.
                </p>
              </div>
              {!readOnly ? (
                <div className="flex flex-wrap gap-2">
                  <Button className="border-0 gradient-primary text-white shadow-[0_16px_30px_rgba(82,54,188,0.22)]" onClick={addTutorChoiceCard} disabled={isSaving}>
                    Add Tutor Choice Card
                  </Button>
                  <Button className="border-0 bg-violet-600 text-white shadow-[0_16px_30px_rgba(109,40,217,0.18)] hover:bg-violet-700" onClick={addNoteCard} disabled={isSaving}>
                    Add Note Card
                  </Button>
                </div>
              ) : null}
            </div>

            <div className="mt-5 space-y-3">
          {coverageCardsForDisplay.map((card) => {
            const cardReadOnly = readOnly || card.locked;
            const isTutorEmailEditable = editingTutorEmailCardIds.has(card.id) || !card.tutorEmail.trim();
            const isTutorEmailLoading = loadingTutorEmailCardIds.has(card.id);
            const canRemoveCard = !readOnly && !card.locked;
            const canCollapseCard = cardReadOnly;
            const isCardCollapsed = canCollapseCard && collapsedCoverageCardIds.has(card.id);

            if (card.type === "tutor_reply") {
              const canConfirmSession = canConfirmCoverageReplyCard(card);
              const wasAccepted = card.replyOutcome === "accepted";
              const relatedTutorChoiceCard = draft.coverageCards.find((candidate) => (
                candidate.type === "tutor_choice" && candidate.id === card.relatedTutorChoiceCardId
              ));
              const relatedTutorRequestSummary = summarizeCoverageTutorRequestDetails(
                relatedTutorChoiceCard?.sessionDetails || "",
              );
              const replyAccentClassName = wasAccepted
                ? "border-emerald-200/70 bg-emerald-50/50"
                : "border-rose-200/70 bg-rose-50/50";
              const replyTextClassName = wasAccepted ? "text-emerald-900" : "text-rose-900";
              const replyMutedTextClassName = wasAccepted ? "text-emerald-900/70" : "text-rose-900/70";
              const replyBorderClassName = wasAccepted ? "border-emerald-200" : "border-rose-200";
              const replySeparatorClassName = wasAccepted ? "border-emerald-200/80" : "border-rose-200/80";
              const replyStatusLabel = getCoverageReplyOutcomeLabel(card.replyOutcome);
              const responseSummary = card.sessionDetails.trim();
              const requestSummary = relatedTutorChoiceCard?.sessionDetails.trim() || "";
              const hasUpdatedSessionDetails = Boolean(responseSummary && responseSummary !== requestSummary);
              const replyText = card.replyText.trim();
              const tutorEmail = card.tutorEmail.trim();
              const requestTutorEmail = relatedTutorChoiceCard?.tutorEmail.trim().toLowerCase() || "";
              const hasUpdatedTutorEmail = Boolean(tutorEmail && tutorEmail.toLowerCase() !== requestTutorEmail);

              return (
                <div key={card.id} className={cn("rounded-[26px] border px-4 py-3.5 shadow-soft", replyAccentClassName)}>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex min-w-0 flex-wrap items-center gap-2">
                      <div className={cn("truncate text-sm font-semibold", replyTextClassName)}>
                        Tutor Response
                      </div>
                      {card.replyOutcome ? (
                        <div className={cn("rounded-full border px-2 py-0.5 text-[11px] font-medium", replyBorderClassName, replyMutedTextClassName)}>
                          {replyStatusLabel}
                        </div>
                      ) : null}
                      {card.tutor ? (
                        <div className={cn("truncate text-sm", replyMutedTextClassName)}>
                          {card.tutor}
                        </div>
                      ) : null}
                    </div>
                    <div className={cn("rounded-full border bg-white px-3 py-1 text-xs font-medium", replyBorderClassName, replyMutedTextClassName)}>
                      {buildCoverageCardTimestampLabel(card.createdAt, card.updatedAt)}
                    </div>
                    {canCollapseCard ? (
                      <button
                        type="button"
                        onClick={() => toggleCoverageCardCollapsed(card.id)}
                        className={cn(
                          "inline-flex h-8 w-8 items-center justify-center rounded-full border bg-white transition",
                          replyBorderClassName,
                          replyMutedTextClassName,
                        )}
                        aria-label={isCardCollapsed ? "Expand tutor response" : "Collapse tutor response"}
                      >
                        <ChevronDown className={cn("h-4 w-4 transition-transform", isCardCollapsed && "-rotate-90")} />
                      </button>
                    ) : null}
                  </div>

                  {!isCardCollapsed ? (
                    <div className="mt-3 space-y-2 text-sm">
                    {hasUpdatedTutorEmail ? (
                      <div className={cn("flex flex-wrap gap-x-2 gap-y-1", replyMutedTextClassName)}>
                        <span className="font-medium">Tutor E-mail:</span>
                        <span className="text-foreground break-all">{tutorEmail}</span>
                      </div>
                    ) : null}
                    <div className={cn("rounded-xl bg-white/80 px-3 py-2", replyMutedTextClassName)}>
                      <div className="font-medium">{wasAccepted ? "Tutor accepted this request." : "Tutor refused this request."}</div>
                      {replyText ? (
                        <div className="mt-1 whitespace-pre-wrap leading-7 text-foreground">
                          {replyText}
                        </div>
                      ) : null}
                    </div>
                    {hasUpdatedSessionDetails ? (
                      <div className={cn("space-y-1", replyMutedTextClassName)}>
                        <div className="font-medium">Updated Session Details:</div>
                        <div className="whitespace-pre-wrap rounded-xl bg-white/80 px-3 py-2 leading-7 text-foreground">
                          {card.sessionDetails}
                        </div>
                        </div>
                      ) : null}
                      {relatedTutorChoiceCard ? (
                        <div className="space-y-2 pt-1">
                          <div className={cn("text-[11px] font-semibold uppercase tracking-[0.14em]", replyMutedTextClassName)}>
                            Original Request
                          </div>
                          <div className="rounded-xl border border-white/70 bg-white/85 px-3 py-3">
                            <div className="flex flex-wrap items-start justify-between gap-3">
                              <div className="min-w-0 flex-1">
                                <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-foreground">
                                  <span className="font-medium">{relatedTutorChoiceCard.tutor || "Tutor"}</span>
                                  {relatedTutorChoiceCard.tutorEmail ? (
                                    <span className="break-all text-muted-foreground">{relatedTutorChoiceCard.tutorEmail}</span>
                                  ) : null}
                                </div>
                                <div className="mt-2 flex flex-wrap gap-2">
                                  {relatedTutorRequestSummary.moduleLine ? (
                                    <div className="rounded-full border border-primary/10 bg-white px-3 py-1 text-xs font-medium text-foreground">
                                      {relatedTutorRequestSummary.moduleLine}
                                    </div>
                                  ) : null}
                                  {relatedTutorRequestSummary.sessionCount > 0 ? (
                                    <div className="rounded-full border border-primary/10 bg-white px-3 py-1 text-xs font-medium text-foreground">
                                      {relatedTutorRequestSummary.sessionCount} session{relatedTutorRequestSummary.sessionCount === 1 ? "" : "s"}
                                    </div>
                                  ) : null}
                                </div>
                              </div>
                              {relatedTutorChoiceCard.submittedAt ? (
                                <div className="text-xs text-muted-foreground">
                                  Submitted {formatDateTime(relatedTutorChoiceCard.submittedAt)}
                                </div>
                              ) : null}
                            </div>
                            {relatedTutorRequestSummary.preferredTimeLine ? (
                              <div className="mt-3 rounded-xl border border-primary/10 bg-white px-3 py-2 text-sm text-foreground">
                                {relatedTutorRequestSummary.preferredTimeLine}
                              </div>
                            ) : null}
                            {relatedTutorRequestSummary.sessionLines.length > 0 ? (
                              <div className="mt-3 space-y-2">
                                <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                                  Requested Sessions
                                </div>
                                <div className="space-y-2">
                                  {relatedTutorRequestSummary.sessionLines.map((line) => (
                                    <div
                                      key={line}
                                      className="rounded-xl border border-primary/10 bg-white px-3 py-2 text-sm text-foreground"
                                    >
                                      {line}
                                    </div>
                                  ))}
                                </div>
                              </div>
                            ) : null}
                            {relatedTutorChoiceCard.presentationFiles.length > 0 ? (
                              <div className="mt-3 flex flex-wrap gap-2">
                                {relatedTutorChoiceCard.presentationFiles.map((file) => (
                                  <button
                                    key={file.id}
                                    type="button"
                                    onClick={() => setPreviewAttachment(file)}
                                    className="inline-flex max-w-full items-center gap-2 rounded-full border bg-white px-3 py-1.5 text-xs shadow-sm"
                                  >
                                    <span className="truncate font-medium text-primary">{file.name}</span>
                                    <span className="shrink-0 text-muted-foreground">{formatBytes(file.size)}</span>
                                  </button>
                                ))}
                              </div>
                            ) : null}
                          </div>
                        </div>
                      ) : null}
                    </div>
                  ) : null}

                  {wasAccepted && !isCardCollapsed ? (
                    <div className={cn("mt-3 flex flex-wrap items-center justify-between gap-3 border-t pt-3", replySeparatorClassName)}>
                      <div className={cn("text-xs", wasAccepted ? "text-emerald-900/75" : "text-rose-900/75")}>
                        {card.confirmedAt
                          ? `Confirmed ${formatDateTime(card.confirmedAt)}`
                          : getCoverageReplyCardTimingMessage(card)}
                      </div>
                      {!readOnly ? (
                        <Button
                          onClick={() => void onConfirmTutorSession(card.id)}
                          disabled={isSaving || !canConfirmSession || Boolean(card.confirmedAt)}
                          className="border-0 bg-emerald-600 text-white hover:bg-emerald-700"
                        >
                          {isSaving ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : null}
                          Confirm Session
                        </Button>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              );
            }

            if (card.type === "note") {
              return (
                <div key={card.id} className="rounded-[26px] border border-primary/12 bg-gradient-to-br from-violet-50/70 via-white to-primary/[0.05] p-4 shadow-soft">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-foreground">Note</div>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="rounded-full border bg-background px-3 py-1 text-xs font-medium text-muted-foreground">
                        {buildCoverageCardTimestampLabel(card.createdAt, card.updatedAt)}
                      </div>
                      {canCollapseCard ? (
                        <button
                          type="button"
                          onClick={() => toggleCoverageCardCollapsed(card.id)}
                          className="inline-flex h-8 w-8 items-center justify-center rounded-full border bg-background text-muted-foreground transition hover:border-primary/30 hover:text-primary"
                          aria-label={isCardCollapsed ? "Expand note card" : "Collapse note card"}
                        >
                          <ChevronDown className={cn("h-4 w-4 transition-transform", isCardCollapsed && "-rotate-90")} />
                        </button>
                      ) : null}
                      {canRemoveCard ? (
                        <button
                          type="button"
                          onClick={() => removeCoverageCard(card.id)}
                          className="inline-flex h-8 w-8 items-center justify-center rounded-full border bg-background text-muted-foreground transition hover:border-destructive/30 hover:text-destructive"
                          aria-label="Remove note card"
                        >
                          <X className="h-4 w-4" />
                        </button>
                      ) : null}
                    </div>
                  </div>

                  {!isCardCollapsed ? (
                    <div className="mt-3 space-y-2">
                    <Label className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Note</Label>
                    <Textarea
                      value={card.note}
                      onChange={(event) => updateCoverageCard(card.id, { note: event.target.value })}
                      readOnly={cardReadOnly}
                      placeholder="Add a support note, update, or internal reminder..."
                      className="min-h-[120px] rounded-2xl border-primary/12 bg-white/90 shadow-none"
                    />
                    </div>
                  ) : null}
                </div>
              );
            }

            const displayedTutorOptions = card.tutor && !tutorOptions.includes(card.tutor)
              ? [card.tutor, ...tutorOptions]
              : tutorOptions;
            const tutorChoiceStatusLabel = card.requestStatus === "draft" ? "" : getCoverageTutorRequestLabel(card.requestStatus);
            const showCompactTutorChoice = cardReadOnly;
            const compactTutorRequestSummary = summarizeCoverageTutorRequestDetails(card.sessionDetails);
            const linkedTutorReplyCard = draft.coverageCards.find((candidate) => (
              candidate.type === "tutor_reply" && candidate.relatedTutorChoiceCardId === card.id
            ));

            if (showCompactTutorChoice && linkedTutorReplyCard) {
              return null;
            }

            return (
              <div
                key={card.id}
                className={cn(
                  "rounded-[26px] border p-4 shadow-soft",
                  showCompactTutorChoice
                    ? "border-primary/12 bg-white/95"
                    : "border-primary/15 bg-gradient-to-br from-primary/[0.09] via-white to-violet-50/80",
                )}
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="text-sm font-semibold text-foreground">
                        {showCompactTutorChoice ? "Tutor Request" : "Tutor Choice"}
                      </div>
                      {tutorChoiceStatusLabel ? (
                        <div className={cn(
                          "rounded-full border px-2.5 py-0.5 text-[11px] font-medium",
                          getCoverageTutorRequestBadgeClassName(card.requestStatus),
                        )}>
                          {tutorChoiceStatusLabel}
                        </div>
                      ) : null}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="rounded-full border bg-background px-3 py-1 text-xs font-medium text-muted-foreground">
                      {buildCoverageCardTimestampLabel(card.createdAt, card.updatedAt)}
                    </div>
                    {canCollapseCard ? (
                      <button
                        type="button"
                        onClick={() => toggleCoverageCardCollapsed(card.id)}
                        className="inline-flex h-8 w-8 items-center justify-center rounded-full border bg-background text-muted-foreground transition hover:border-primary/30 hover:text-primary"
                        aria-label={isCardCollapsed ? "Expand tutor choice card" : "Collapse tutor choice card"}
                      >
                        <ChevronDown className={cn("h-4 w-4 transition-transform", isCardCollapsed && "-rotate-90")} />
                      </button>
                    ) : null}
                    {canRemoveCard ? (
                      <button
                        type="button"
                        onClick={() => removeCoverageCard(card.id)}
                        className="inline-flex h-8 w-8 items-center justify-center rounded-full border bg-background text-muted-foreground transition hover:border-destructive/30 hover:text-destructive"
                        aria-label="Remove tutor choice card"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    ) : null}
                  </div>
                </div>

                {showCompactTutorChoice && !isCardCollapsed ? (
                  <>
                    <div className="mt-3 rounded-2xl border border-primary/10 bg-gradient-to-br from-primary/[0.035] via-white to-violet-50/40 px-4 py-3.5">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-foreground">
                            <span className="font-medium">{card.tutor || "Tutor"}</span>
                            {card.tutorEmail ? (
                              <span className="break-all text-muted-foreground">{card.tutorEmail}</span>
                            ) : null}
                          </div>
                          <div className="mt-2 flex flex-wrap gap-2">
                            {compactTutorRequestSummary.moduleLine ? (
                              <div className="rounded-full border border-primary/10 bg-white px-3 py-1 text-xs font-medium text-foreground">
                                {compactTutorRequestSummary.moduleLine}
                              </div>
                            ) : null}
                            {compactTutorRequestSummary.sessionCount > 0 ? (
                              <div className="rounded-full border border-primary/10 bg-white px-3 py-1 text-xs font-medium text-foreground">
                                {compactTutorRequestSummary.sessionCount} session{compactTutorRequestSummary.sessionCount === 1 ? "" : "s"}
                              </div>
                            ) : null}
                          </div>
                        </div>
                        {card.submittedAt ? (
                          <div className="text-xs text-muted-foreground">
                            Submitted {formatDateTime(card.submittedAt)}
                          </div>
                        ) : null}
                      </div>
                      {compactTutorRequestSummary.preferredTimeLine ? (
                        <div className="mt-3 rounded-xl border border-primary/10 bg-white/90 px-3 py-2 text-sm text-foreground">
                          {compactTutorRequestSummary.preferredTimeLine}
                        </div>
                      ) : null}
                      {compactTutorRequestSummary.sessionLines.length > 0 ? (
                        <div className="mt-3 space-y-2">
                          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                            Requested Sessions
                          </div>
                          <div className="space-y-2">
                            {compactTutorRequestSummary.sessionLines.map((line) => (
                              <div
                                key={line}
                                className="rounded-xl border border-primary/10 bg-white/85 px-3 py-2 text-sm text-foreground"
                              >
                                {line}
                              </div>
                            ))}
                          </div>
                        </div>
                      ) : card.sessionDetails ? (
                        <div className="mt-3 whitespace-pre-wrap rounded-xl border border-primary/10 bg-white/85 px-3 py-2 text-sm leading-7 text-foreground">
                          {card.sessionDetails}
                        </div>
                      ) : null}
                      {card.presentationFiles.length > 0 ? (
                        <div className="mt-3 flex flex-wrap gap-2">
                          {card.presentationFiles.map((file) => (
                            <button
                              key={file.id}
                              type="button"
                              onClick={() => setPreviewAttachment(file)}
                              className="inline-flex max-w-full items-center gap-2 rounded-full border bg-background px-3 py-1.5 text-xs shadow-sm"
                            >
                              <span className="truncate font-medium text-primary">{file.name}</span>
                              <span className="shrink-0 text-muted-foreground">{formatBytes(file.size)}</span>
                            </button>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  </>
                ) : showCompactTutorChoice ? null : (
                  <>
                    <div className="mt-3 grid gap-3">
                      <div className="grid gap-3 md:grid-cols-2 md:items-start">
                        <div className="space-y-2">
                          <Label className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Tutor</Label>
                          <Select
                            value={card.tutor}
                            onValueChange={(value) => handleTutorChange(card.id, value)}
                            disabled={isLoadingTutorOptions || isSaving}
                          >
                            <SelectTrigger>
                              <SelectValue placeholder={isLoadingTutorOptions ? "Loading tutors..." : "Choose tutor"} />
                            </SelectTrigger>
                            <SelectContent>
                              {displayedTutorOptions.length === 0 ? (
                                <div className="px-3 py-2 text-sm text-muted-foreground">
                                  {isLoadingTutorOptions ? "Loading tutors..." : "No tutors available."}
                                </div>
                              ) : (
                                displayedTutorOptions.map((option) => (
                                  <SelectItem key={option} value={option}>{option}</SelectItem>
                                ))
                              )}
                            </SelectContent>
                          </Select>
                        </div>

                        <div className="space-y-2">
                          <Label className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Tutor E-mail</Label>
                          <div className="relative">
                            <Input
                              type="email"
                              value={card.tutorEmail}
                              onChange={(event) => updateCoverageCard(card.id, { tutorEmail: event.target.value })}
                              readOnly={!isTutorEmailEditable}
                              placeholder={card.tutor ? "Enter tutor e-mail" : "Choose tutor first"}
                              className={cn(
                                "bg-background",
                                card.tutorEmail.trim() && "pr-16",
                                !card.tutorEmail.trim() && "border-amber-300",
                              )}
                            />
                            {card.tutorEmail.trim() ? (
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={() => setTutorEmailEditing(card.id, !isTutorEmailEditable)}
                                className="absolute right-2 top-1/2 h-7 -translate-y-1/2 px-2 text-[11px]"
                              >
                                {isTutorEmailEditable ? "Done" : "Edit"}
                              </Button>
                            ) : null}
                          </div>
                        </div>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {card.tutor
                          ? isTutorEmailLoading
                            ? "Loading tutor e-mail..."
                            : card.tutorEmail.trim()
                            ? isTutorEmailEditable
                              ? "Edit if the tutor e-mail needs a correction."
                              : "Loaded from Tutors_Modules."
                            : "No e-mail was found in Tutors_Modules. Please enter it manually."
                          : "Choose a tutor to load the e-mail automatically."}
                      </p>
                    </div>

                    <div className="mt-3 grid gap-3 lg:grid-cols-2">
                      <div className="space-y-2 lg:col-span-2">
                        <Label className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Presentation Upload</Label>
                        <div className="rounded-2xl border border-primary/12 bg-gradient-to-br from-white via-primary/[0.02] to-violet-50/40 p-3 shadow-sm">
                          <input
                            id={`coverage-presentation-${card.id}`}
                            type="file"
                            multiple
                            accept=".pdf,.ppt,.pptx,.odp,.key,image/*"
                            disabled={isSaving}
                            onChange={(event) => void handlePresentationFilesAdded(card.id, event)}
                            className="sr-only"
                          />
                          <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
                            <label
                              htmlFor={`coverage-presentation-${card.id}`}
                              className={cn(
                                "inline-flex cursor-pointer items-center justify-center gap-2 rounded-xl border border-primary/15 bg-white px-4 py-2.5 text-sm font-semibold text-primary shadow-sm transition hover:border-primary/30 hover:bg-primary/[0.04]",
                                isSaving && "cursor-not-allowed opacity-60",
                              )}
                            >
                              <Paperclip className="h-4 w-4" />
                              {card.presentationFiles.length > 0 ? "Add More Files" : "Attach Presentation Files"}
                            </label>
                            <div className="text-sm text-muted-foreground xl:text-right">
                              {card.presentationFiles.length > 0
                                ? `${card.presentationFiles.length} file${card.presentationFiles.length === 1 ? "" : "s"} selected`
                                : "PDF, PPT, PPTX, ODP, Keynote, or image files"}
                            </div>
                          </div>
                          {card.presentationFiles.length > 0 ? (
                            <div className="mt-3 flex min-w-0 flex-wrap gap-2">
                              {card.presentationFiles.map((file) => (
                                <div
                                  key={file.id}
                                  className="inline-flex min-w-0 max-w-full items-center gap-2 rounded-full border border-primary/10 bg-white px-3 py-1.5 text-xs shadow-sm"
                                >
                                  <button
                                    type="button"
                                    onClick={() => setPreviewAttachment(file)}
                                    className="truncate font-medium text-primary underline-offset-4 hover:underline"
                                  >
                                    {file.name}
                                  </button>
                                  <span className="shrink-0 text-muted-foreground">{formatBytes(file.size)}</span>
                                  <button
                                    type="button"
                                    onClick={() => removePresentationFile(card.id, file.id)}
                                    className="inline-flex h-4 w-4 items-center justify-center rounded-full text-muted-foreground transition hover:bg-secondary hover:text-foreground"
                                    aria-label={`Remove ${file.name}`}
                                  >
                                    <X className="h-3 w-3" />
                                  </button>
                                </div>
                              ))}
                            </div>
                          ) : null}
                          </div>
                        </div>

                      <div className="space-y-2 lg:col-span-2">
                        <Label className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Session Details</Label>
                        <Textarea
                          value={card.sessionDetails}
                          onChange={(event) => updateCoverageCard(card.id, { sessionDetails: event.target.value })}
                          readOnly={false}
                          placeholder="Add the session details the tutor should review..."
                          className="min-h-[130px] bg-background"
                        />
                      </div>
                    </div>

                    <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t pt-3">
                      <div className="text-xs text-muted-foreground">
                        {card.submittedAt
                          ? `Submitted ${formatDateTime(card.submittedAt)}`
                          : "Editable until submitted"}
                      </div>
                      <Button
                        onClick={() => void onSubmitTutorChoiceCard(card.id)}
                        disabled={isSaving || isLoadingTutorOptions || isTutorEmailLoading}
                        className="border-0 gradient-primary"
                      >
                        {isSaving ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : null}
                        Submit to Tutor
                      </Button>
                    </div>
                  </>
                )}
              </div>
            );
          })}
        </div>

        {coverageTutorError ? (
          <p className="mt-3 text-sm text-destructive">{coverageTutorError}</p>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4">
        <div className="text-xs text-muted-foreground">
          {readOnly ? "Closed tickets are view-only." : "Save your work or submit a tutor request. Coverage tickets close after a tutor accepts the request."}
        </div>
        <div className="flex flex-wrap justify-end gap-2">
          <Button variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          {!readOnly ? (
            <>
              <Button onClick={onSave} className="border-0 gradient-primary" disabled={!isDirty || isSaving}>
                {isSaving ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
                Save Ticket
              </Button>
            </>
          ) : null}
        </div>
      </div>
        </TabsContent>

        <TabsContent value="details" className="space-y-4">
          <CoverageTicketDetailsPanel
            ticket={ticket}
            history={history}
            readOnly={readOnly}
            isSaving={isSavingDetails}
            notes={notes}
            onNotesChange={onNotesChange}
            draftStatus={draftStatus}
            onDraftStatusChange={onDraftStatusChange}
            statusOptions={statusOptions}
            canAssignActiveTicket={canAssignActiveTicket}
            draftAgentId={draftAgentId}
            onDraftAgentChange={onDraftAgentChange}
            selectedDraftAgent={selectedDraftAgent}
            assignableAdminAgents={assignableAdminAgents}
            isActiveTicketAlreadyAssigned={isActiveTicketAlreadyAssigned}
            isSlaAutoManaged={isSlaAutoManaged}
            effectiveDraftSlaStatus={effectiveDraftSlaStatus}
            onDraftSlaStatusChange={onDraftSlaStatusChange}
            slaStatuses={slaStatuses}
            isStatusChanging={isStatusChanging}
            canSubmitStatusChange={canSubmitStatusChange}
            onCancel={onCancel}
            onSaveDetails={onSaveDetails}
          />
        </TabsContent>
      </Tabs>

      <Dialog open={Boolean(previewAttachment)} onOpenChange={(open) => !open && setPreviewAttachment(null)}>
        <DialogContent className="max-h-[90vh] max-w-5xl overflow-hidden">
          <DialogHeader>
            <DialogTitle className="truncate pr-8">{previewAttachment?.name || "Attachment Preview"}</DialogTitle>
            <DialogDescription>
              {previewAttachment?.mimeType || "Attachment"} {previewAttachment ? `- ${formatBytes(previewAttachment.size)}` : ""}
            </DialogDescription>
          </DialogHeader>

          {previewAttachment ? (
            previewAttachmentKind === "image" ? (
              <div className="overflow-auto rounded-2xl border bg-secondary/10 p-3">
                <img
                  src={previewAttachment.dataUrl}
                  alt={previewAttachment.name}
                  className="mx-auto max-h-[70vh] w-auto max-w-full rounded-xl object-contain"
                />
              </div>
            ) : previewAttachmentKind === "pdf" ? (
              <div className="overflow-hidden rounded-2xl border bg-secondary/10">
                <iframe
                  src={previewAttachment.dataUrl}
                  title={previewAttachment.name}
                  className="h-[70vh] w-full border-0"
                />
              </div>
            ) : (
              <div className="rounded-2xl border bg-secondary/10 p-5">
                <div className="text-sm text-foreground">
                  Preview is not available for this file type yet.
                </div>
                <div className="mt-2 text-xs text-muted-foreground">
                  You can still download the file from here if needed.
                </div>
                <div className="mt-4">
                  <a
                    href={previewAttachment.dataUrl}
                    download={previewAttachment.name}
                    className="inline-flex items-center rounded-full border px-4 py-2 text-sm font-medium text-primary transition hover:bg-secondary/40"
                  >
                    Download File
                  </a>
                </div>
              </div>
            )
          ) : null}
        </DialogContent>
      </Dialog>
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
  readOnly,
  attachments,
  sessionRequests,
  onFieldChange,
  onImagesAdded,
  onRemoveImage,
  onTicketStatusChange,
  onStatusReasonChange,
  escalationTargetAgents,
  escalationAgentId,
  escalationNote,
  escalationAssigneeLabel,
  selectedEscalationAgent,
  onEscalationAgentChange,
  onEscalationNoteChange,
  onIssuesAddressedChange,
  onBack,
  onNext,
  onSaveOnly,
  onSubmit,
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
  readOnly: boolean;
  attachments: AttachmentItem[];
  sessionRequests: SessionRequestItem[];
  onFieldChange: (field: keyof AdminDocumentation, value: string) => void;
  onImagesAdded: (event: ChangeEvent<HTMLInputElement>) => Promise<void>;
  onRemoveImage: (index: number) => void;
  onTicketStatusChange: (value: DocumentationWorkflowStatus | "") => void;
  onStatusReasonChange: (value: string) => void;
  escalationTargetAgents: AdminAgent[];
  escalationAgentId: string;
  escalationNote: string;
  escalationAssigneeLabel: string;
  selectedEscalationAgent: AdminAgent | null;
  onEscalationAgentChange: (value: string) => void;
  onEscalationNoteChange: (value: string) => void;
  onIssuesAddressedChange: (value: DocumentationIssuesAddressed) => void;
  onBack: () => void;
  onNext: () => void;
  onSaveOnly: () => void;
  onSubmit: () => void;
  canMoveForward: boolean;
}) => {
  const automaticStatusReason = !readOnly ? getAutomaticDocumentationStatusReason(ticketStatus) : "";
  const displayedStatusReason = automaticStatusReason || statusReason;
  const isEscalationWorkflow = displayedStatusReason === "Escalation";

  return (
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
        readOnly ? (
          <DocumentationAccordionReadOnly draft={draft} attachments={attachments} sessionRequests={sessionRequests} />
        ) : (
          <DocumentationAccordionEditor
            draft={draft}
            attachments={attachments}
            sessionRequests={sessionRequests}
            onFieldChange={onFieldChange}
            onImagesAdded={onImagesAdded}
            onRemoveImage={onRemoveImage}
          />
        )
      ) : step === 2 ? (
        <div className="flex h-full min-h-0 flex-col justify-between gap-6">
          <div className="space-y-5 overflow-y-auto pr-1">
            <div className="rounded-2xl border bg-secondary/20 p-4">
              <div className="text-sm font-semibold">Ticket status</div>
              <div className="mt-1 text-xs text-muted-foreground">
                Choose the final ticket status for this documentation workflow.
              </div>
              <div className="mt-3">
                {readOnly ? (
                  <ReadOnlyDocumentationValue value={ticketStatus || "-"} />
                ) : (
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
                )}
              </div>
            </div>

            <div className="rounded-2xl border bg-secondary/20 p-4">
              <div className="text-sm font-semibold">Status reason</div>
              <div className="mt-1 text-xs text-muted-foreground">
                {automaticStatusReason
                  ? "Closed tickets are saved automatically as Closed via Agent."
                  : "The available reasons change based on the selected ticket status."}
              </div>
              <div className="mt-3">
                {readOnly || automaticStatusReason ? (
                  <ReadOnlyDocumentationValue value={displayedStatusReason || "-"} />
                ) : (
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
                )}
              </div>
            </div>

            {isEscalationWorkflow ? (
              <div className="rounded-2xl border border-amber-200 bg-amber-50/60 p-4">
                <div className="text-sm font-semibold text-amber-900">Escalate to</div>
                <div className="mt-1 text-xs text-amber-800/80">
                  Choose the admin who should be notified about this chat, then add a short escalation note.
                </div>
                <div className="mt-3">
                  {readOnly ? (
                    <ReadOnlyDocumentationValue value={escalationAssigneeLabel || "-"} />
                  ) : (
                    <Select value={escalationAgentId} onValueChange={onEscalationAgentChange}>
                      <SelectTrigger>
                        {selectedEscalationAgent ? (
                          <AgentStatusLabel agent={selectedEscalationAgent} />
                        ) : (
                          <SelectValue placeholder="Select admin to escalate to" />
                        )}
                      </SelectTrigger>
                      <SelectContent>
                        {escalationTargetAgents.length === 0 ? (
                          <div className="px-3 py-2 text-sm text-muted-foreground">
                            No other admins are available for escalation right now.
                          </div>
                        ) : (
                          escalationTargetAgents.map((agent) => (
                            <SelectItem key={agent.id} value={String(agent.id)} className="py-2">
                              <AgentStatusLabel agent={agent} />
                            </SelectItem>
                          ))
                        )}
                      </SelectContent>
                    </Select>
                  )}
                </div>
                <div className="mt-4">
                  <Label className="text-xs font-semibold uppercase tracking-[0.12em] text-amber-900/80">
                    Escalation Note
                  </Label>
                  <div className="mt-2">
                    {readOnly ? (
                      <ReadOnlyDocumentationValue value={escalationNote || "-"} />
                    ) : (
                      <Textarea
                        value={escalationNote}
                        onChange={(event) => onEscalationNoteChange(event.target.value)}
                        rows={4}
                        placeholder="Tell the next admin what they need to check in this chat..."
                        className="min-h-[108px] bg-background"
                      />
                    )}
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      ) : (
        <div className="flex h-full min-h-0 flex-col justify-between gap-6">
          <div className="space-y-5 overflow-y-auto pr-1">
            {isEscalationWorkflow ? (
              <div className="rounded-2xl border border-amber-200 bg-amber-50/60 p-5">
                <div className="text-lg font-semibold text-amber-950">Escalation Notification</div>
                <div className="mt-2 text-sm text-amber-900/80">
                  Send the escalation notice, then choose whether to close this chat now or continue on a new follow-up ticket.
                </div>
                <div className="mt-5 grid gap-3">
                  <div className="rounded-2xl border bg-background px-4 py-4">
                    <div className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">Selected Admin</div>
                    <div className="mt-1 font-semibold text-foreground">{escalationAssigneeLabel || "-"}</div>
                  </div>
                  <div className="rounded-2xl border bg-background px-4 py-4">
                    <div className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">Chat ID</div>
                    <div className="mt-1 font-mono text-sm font-semibold text-foreground">{draft.chatId || draft.ticketId || "-"}</div>
                  </div>
                  <div className="rounded-2xl border bg-background px-4 py-4">
                    <div className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">Escalation Note</div>
                    <div className="mt-1 whitespace-pre-wrap text-sm leading-6 text-foreground">{escalationNote || "-"}</div>
                  </div>
                </div>
                {readOnly ? (
                  <div className="mt-5 rounded-2xl border bg-background px-4 py-4">
                    <div className="font-semibold">{issuesAddressed === "yes" ? "Close Chat" : issuesAddressed === "no" ? "Create New Ticket" : "-"}</div>
                    <div className="mt-1 text-sm text-muted-foreground">
                      {issuesAddressed === "yes"
                        ? "The escalation notice was sent and this chat was closed."
                        : issuesAddressed === "no"
                          ? "The escalation notice was sent and a follow-up ticket continued this chat."
                          : "No escalation outcome was saved for this ticket."}
                    </div>
                  </div>
                ) : (
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
                      <div className="font-semibold">Close Chat</div>
                      <div className={cn("mt-1 text-sm", issuesAddressed === "yes" ? "text-success/80" : "text-muted-foreground")}>
                        Send the escalation notice and close this live chat so it leaves My Cases and Open.
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
                      <div className="font-semibold">Create New Ticket</div>
                      <div className={cn("mt-1 text-sm", issuesAddressed === "no" ? "text-warning/80" : "text-muted-foreground")}>
                        Send the escalation notice and continue this case on a new follow-up ticket.
                      </div>
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <div className="rounded-2xl border bg-secondary/20 p-5">
                <div className="text-lg font-semibold">Were the Learner&apos;s issues addressed?</div>
                <div className="mt-2 text-sm text-muted-foreground">
                  Choose whether this ticket is fully resolved, or whether the same live chat should continue on a new follow-up ticket.
                </div>
                {readOnly ? (
                  <div className="mt-5 rounded-2xl border bg-background px-4 py-4">
                    <div className="font-semibold">{issuesAddressed === "yes" ? "Yes" : issuesAddressed === "no" ? "No" : "-"}</div>
                    <div className="mt-1 text-sm text-muted-foreground">
                      {issuesAddressed === "yes"
                        ? "The learner issues were marked as addressed and the chat was closed."
                        : issuesAddressed === "no"
                          ? "The learner issues were marked as not yet addressed and the same chat continued on a follow-up ticket."
                          : "No workflow outcome was saved for this ticket."}
                    </div>
                  </div>
                ) : (
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
                        Save this ticket and continue the same live chat on a new follow-up ticket.
                      </div>
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>

    <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t pt-4">
      <div className="text-xs text-muted-foreground">
        {readOnly
          ? "This ticket is closed, so the documentation is shown as saved output only."
          : step === 1
            ? "Page 1 remains the expandable documentation workspace."
            : step === 2
              ? automaticStatusReason
                ? "Closed tickets are tagged automatically as Closed via Agent before you continue."
                : isEscalationWorkflow
                  ? "Choose the admin and add an escalation note before you continue."
                  : "Choose a ticket status and status reason before you continue."
              : isEscalationWorkflow
                ? "Choose whether to close this chat now or continue on a new follow-up ticket after sending the escalation notice."
                : "Pick Yes to close this chat, or No to save this ticket and continue on a new follow-up ticket."}
      </div>
      <div className="flex flex-wrap justify-end gap-2">
        {readOnly ? (
          <>
            {step > 1 ? (
              <Button variant="outline" onClick={onBack}>
                Back
              </Button>
            ) : null}
            {step < 3 ? (
              <Button onClick={onNext} className="border-0 gradient-primary">
                Next
              </Button>
            ) : null}
          </>
        ) : step === 1 ? (
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
            <Button onClick={onSubmit} className="border-0 gradient-primary" disabled={!canMoveForward || isSaving}>
              {isSaving
                ? "Saving..."
                : isEscalationWorkflow
                  ? issuesAddressed === "yes"
                    ? "Send Notice and Close Chat"
                    : "Send Notice and Create New Ticket"
                  : issuesAddressed === "yes"
                    ? "Save and Close Chat"
                    : "Save and Create New Ticket"}
            </Button>
          </>
        )}
      </div>
    </div>
    </div>
  );
};

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

const ReadOnlyDocumentationValue = ({
  value,
  mono,
}: {
  value: string;
  mono?: boolean;
}) => (
  <div className={cn(
    "rounded-2xl border bg-background px-4 py-3 text-sm leading-6 text-foreground",
    mono ? "font-mono" : "",
  )}>
    {value.trim() ? value : "-"}
  </div>
);

const documentationCardFields: {
  key: keyof Pick<DocumentationWorkflowCard, "inquiry" | "symptoms" | "errors" | "steps" | "resources">;
  label: string;
  placeholder: string;
}[] = [
  { key: "inquiry", label: "Inquiry", placeholder: "Document the support inquiry..." },
  { key: "symptoms", label: "Symptoms", placeholder: "Capture the observed symptoms..." },
  { key: "errors", label: "Errors", placeholder: "Add any error details..." },
  { key: "steps", label: "Steps", placeholder: "Record troubleshooting steps..." },
  { key: "resources", label: "Resources", placeholder: "Add links, resources, or follow-up notes..." },
];

const StandardDocumentationWorkspace = ({
  ticket,
  draft,
  attachments,
  readOnly,
  isSaving,
  isDirty,
  onDraftUpdate,
}: {
  ticket: TicketDetail;
  draft: AdminDocumentation;
  attachments: AttachmentItem[];
  readOnly: boolean;
  isSaving: boolean;
  isDirty: boolean;
  onDraftUpdate: (updater: (draft: AdminDocumentation) => AdminDocumentation) => void;
}) => {
  const [collapsedCardIds, setCollapsedCardIds] = useState<Set<string>>(new Set());
  const cardsForDisplay = sortDocumentationWorkflowCardsForDisplay(draft.documentationCards);

  useEffect(() => {
    setCollapsedCardIds(new Set());
  }, [ticket.id]);

  function addDocumentationCard() {
    const nextCard = createDocumentationCard();
    onDraftUpdate((currentDraft) => ({
      ...currentDraft,
      documentationCards: [nextCard, ...currentDraft.documentationCards],
    }));
    setCollapsedCardIds((currentIds) => {
      const nextIds = new Set(currentIds);
      nextIds.delete(nextCard.id);
      return nextIds;
    });
  }

  function toggleCard(cardId: string) {
    setCollapsedCardIds((currentIds) => {
      const nextIds = new Set(currentIds);
      if (nextIds.has(cardId)) {
        nextIds.delete(cardId);
      } else {
        nextIds.add(cardId);
      }
      return nextIds;
    });
  }

  function updateCardField(
    cardId: string,
    field: keyof Pick<DocumentationWorkflowCard, "inquiry" | "symptoms" | "errors" | "steps" | "resources">,
    value: string,
  ) {
    onDraftUpdate((currentDraft) => ({
      ...currentDraft,
      documentationCards: currentDraft.documentationCards.map((card) => (
        card.id === cardId && !card.locked
          ? { ...card, [field]: value, updatedAt: new Date().toISOString() }
          : card
      )),
    }));
  }

  return (
    <section className="space-y-4">
      <div className="rounded-[28px] border border-primary/15 bg-gradient-to-br from-primary/[0.06] via-white to-fuchsia-50/60 p-4 shadow-[0_18px_45px_rgba(82,54,188,0.10)] sm:p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="inline-flex items-center rounded-full border border-primary/15 bg-white/85 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-primary shadow-sm">
              Requester Submission
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              Fixed starting point from the requester. This section cannot be edited by agents.
            </p>
          </div>
          <div className="rounded-full border border-primary/15 bg-white/80 px-3 py-1 text-xs font-medium text-muted-foreground">
            Created {formatDateTime(ticket.createdAt)}
          </div>
        </div>

        <div className="mt-4 rounded-2xl border border-primary/10 bg-white/90 p-4 text-sm leading-6 text-foreground shadow-sm">
          {ticket.inquiry?.trim() ? ticket.inquiry : "No inquiry text was submitted."}
        </div>

        <div className="mt-4">
          <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            <Paperclip className="h-3.5 w-3.5" />
            Requester Attachments
          </div>
          {attachments.length > 0 ? (
            <div className="grid gap-2">
              {attachments.map((file) => (
                <div key={file.id} className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-primary/10 bg-white/85 px-3 py-2.5 shadow-sm">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold text-foreground">{file.name}</div>
                    <div className="mt-0.5 text-xs text-muted-foreground">
                      {(file.mimeType || "Unknown type")} - {formatBytes(file.size)}
                    </div>
                  </div>
                  {file.storageUrl ? (
                    <Button
                      type="button"
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
          ) : (
            <div className="rounded-2xl border border-dashed border-primary/15 bg-white/60 px-3 py-3 text-sm text-muted-foreground">
              No requester attachments submitted.
            </div>
          )}
        </div>
      </div>

      <div className="rounded-[28px] border bg-card/95 p-4 shadow-card sm:p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-foreground">Agent Documentation Cards</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Add updates while the ticket is pending. Saved cards become frozen history.
            </p>
          </div>
          <Button
            type="button"
            className="border-0 bg-gradient-to-r from-primary to-violet-500 text-white shadow-[0_12px_26px_rgba(82,54,188,0.22)] hover:opacity-95"
            onClick={addDocumentationCard}
            disabled={readOnly || isSaving}
          >
            Add Documentation Card
          </Button>
        </div>

        {cardsForDisplay.length > 0 ? (
          <div className="mt-4 space-y-3">
            {cardsForDisplay.map((card) => {
              const isCollapsed = collapsedCardIds.has(card.id);
              const isCardReadOnly = readOnly || card.locked;

              return (
                <article
                  key={card.id}
                  className={cn(
                    "overflow-hidden rounded-[24px] border bg-gradient-to-br from-white via-white to-primary/[0.03] shadow-[0_14px_32px_rgba(15,23,42,0.06)]",
                    card.locked ? "border-slate-200" : "border-primary/25 ring-1 ring-primary/10",
                  )}
                >
                  <button
                    type="button"
                    className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
                    onClick={() => toggleCard(card.id)}
                  >
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-semibold text-foreground">Documentation Card</span>
                        <span className={cn(
                          "rounded-full border px-2.5 py-0.5 text-[11px] font-semibold",
                          card.locked
                            ? "border-slate-200 bg-slate-50 text-slate-600"
                            : "border-primary/20 bg-primary/10 text-primary",
                        )}>
                          {card.locked ? "Saved" : "Editable"}
                        </span>
                      </div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        {buildDocumentationCardTimestampLabel(card)}
                      </div>
                    </div>
                    <ChevronDown className={cn("h-4 w-4 shrink-0 text-muted-foreground transition-transform", !isCollapsed && "rotate-180")} />
                  </button>

                  {!isCollapsed ? (
                    <div className="border-t border-primary/10 px-4 py-4">
                      {isCardReadOnly ? (
                        <div className="grid gap-3">
                          {documentationCardFields.map((field) => (
                            <ReadOnlyDocumentationBlock key={field.key} label={field.label} value={card[field.key]} />
                          ))}
                        </div>
                      ) : (
                        <div className="grid gap-3">
                          {documentationCardFields.map((field) => (
                            <div key={field.key}>
                              <Label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                                {field.label}
                              </Label>
                              <Textarea
                                value={card[field.key]}
                                onChange={(event) => updateCardField(card.id, field.key, event.target.value)}
                                placeholder={field.placeholder}
                                className="min-h-[88px] resize-y rounded-2xl bg-white"
                              />
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ) : null}
                </article>
              );
            })}
          </div>
        ) : (
          <div className="mt-4 rounded-2xl border border-dashed bg-secondary/20 px-4 py-6 text-center text-sm text-muted-foreground">
            No documentation cards yet. Add the first card when you are ready to document the case.
          </div>
        )}

        {isDirty ? (
          <p className="mt-3 text-xs font-medium text-primary">Unsaved documentation changes.</p>
        ) : null}
      </div>
    </section>
  );
};

const ReadOnlyDocumentationBlock = ({
  label,
  value,
}: {
  label: string;
  value: string;
}) => (
  <div className="rounded-2xl border bg-white/85 px-4 py-3">
    <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{label}</div>
    <div className="mt-1 whitespace-pre-wrap text-sm leading-6 text-foreground">{value.trim() ? value : "-"}</div>
  </div>
);

const DocumentationAccordionReadOnly = ({
  draft,
  attachments,
  sessionRequests,
}: {
  draft: AdminDocumentation;
  attachments: AttachmentItem[];
  sessionRequests: SessionRequestItem[];
}) => (
  <div className="flex h-full min-h-0 flex-col">
    <Accordion type="multiple" defaultValue={["inquiry", "symptoms", "errors"]} className="min-h-0 flex-1 overflow-y-auto pr-1">
      <AccordionItem value="inquiry">
        <AccordionTrigger>Inquiry</AccordionTrigger>
        <AccordionContent>
          <ReadOnlyDocumentationValue value={draft.inquiry} />
        </AccordionContent>
      </AccordionItem>

      <AccordionItem value="symptoms">
        <AccordionTrigger>Symptoms</AccordionTrigger>
        <AccordionContent>
          <ReadOnlyDocumentationValue value={draft.symptoms} />
        </AccordionContent>
      </AccordionItem>

      <AccordionItem value="errors">
        <AccordionTrigger>Errors</AccordionTrigger>
        <AccordionContent className="space-y-4">
          <ReadOnlyDocumentationValue value={draft.errors} />

          {draft.errorImages.length > 0 ? (
            <div className="grid gap-3 sm:grid-cols-2">
              {draft.errorImages.map((image, index) => (
                <div key={`${image.name}-${index}`} className="overflow-hidden rounded-2xl border bg-background">
                  <img src={image.dataUrl} alt={image.name} className="h-40 w-full object-cover" />
                  <div className="p-3">
                    <div className="truncate text-sm font-medium">{image.name}</div>
                    <div className="text-xs text-muted-foreground">{formatBytes(image.size)}</div>
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
          <ReadOnlyDocumentationValue value={draft.steps} />
        </AccordionContent>
      </AccordionItem>

      <AccordionItem value="resources">
        <AccordionTrigger>Resources</AccordionTrigger>
        <AccordionContent className="space-y-4">
          <ReadOnlyDocumentationValue value={draft.resources} />

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
          <ReadOnlyDocumentationValue value={draft.chatId} mono />
        </AccordionContent>
      </AccordionItem>

      <AccordionItem value="ticketid">
        <AccordionTrigger>Ticket ID</AccordionTrigger>
        <AccordionContent>
          <ReadOnlyDocumentationValue value={draft.ticketId} mono />
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

const ActivityLogTimeline = ({
  history,
}: {
  history: HistoryItem[];
}) => {
  if (history.length === 0) {
    return (
      <div className="rounded-2xl border bg-card/60 px-4 py-5 text-sm text-muted-foreground">
        No activity has been recorded yet.
      </div>
    );
  }

  return (
    <div className="rounded-2xl border bg-card/50 p-4 shadow-soft">
      <div className="relative max-h-72 overflow-y-auto pr-1">
        <div className="absolute bottom-0 left-[11px] top-2 w-px bg-border" />
        <div className="space-y-4">
          {history.map((item) => (
            <ActivityLogItemCard key={item.id} item={item} />
          ))}
        </div>
      </div>
    </div>
  );
};

const ActivityLogItemCard = ({
  item,
}: {
  item: HistoryItem;
}) => {
  const payloadEntries = buildActivityPayloadEntries(item.payload);
  const tone = getActivityEventTone(item.eventType);

  return (
    <div className="relative pl-8">
      <span className={cn("absolute left-0 top-5 h-[22px] w-[22px] rounded-full border-[5px] border-background", tone.dotClassName)} />
      <div className="rounded-2xl border bg-background/95 p-4 shadow-soft">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <span className={cn("inline-flex rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.14em]", tone.badgeClassName)}>
              {getActivityEventLabel(item.eventType)}
            </span>
            <div className="mt-2 text-sm font-medium text-foreground">
              {getActivityEventSummary(item)}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              {formatActivityActorLabel(item)}
            </div>
          </div>
          <div className="text-right text-xs text-muted-foreground">
            {formatDateTime(item.createdAt)}
          </div>
        </div>

        {payloadEntries.length > 0 ? (
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {payloadEntries.map((entry) => (
              <ActivityPayloadField key={`${item.id}-${entry.key}`} entry={entry} />
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
};

const ActivityPayloadField = ({
  entry,
}: {
  entry: ActivityPayloadEntry;
}) => (
  <div className={cn("rounded-xl border bg-secondary/25 px-3 py-3", entry.kind === "multiline" && "sm:col-span-2")}>
    <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
      {entry.label}
    </div>
    {entry.kind === "link" ? (
      <a
        href={entry.value}
        target="_blank"
        rel="noreferrer"
        className="mt-1 block break-all text-sm font-medium leading-6 text-primary underline-offset-4 hover:underline"
      >
        {entry.value}
      </a>
    ) : (
      <div className={cn(
        "mt-1 text-sm font-medium text-foreground",
        entry.kind === "mono" && "break-all font-mono text-[13px]",
        entry.kind === "multiline" ? "whitespace-pre-wrap leading-6" : "break-words",
      )}>
        {entry.value}
      </div>
    )}
  </div>
);

function isCoverageTicket(ticket?: Pick<TicketSummary, "technicalSubcategory"> | null) {
  return ticket?.technicalSubcategory === "Coverage";
}

function createCoverageCardId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }

  return `coverage-card-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function buildCoverageTutorSessionDetails(inquiry: string) {
  const parsedInquiry = parseCoverageInquiry(inquiry);
  if (!parsedInquiry) {
    return "";
  }

  const sessionDates = parsedInquiry.sessionDates || [];
  const sessionNumbers = parsedInquiry.sessionNumbers || [];
  const sessionSubjects = parsedInquiry.sessionSubjects || [];
  const sessionDetailLines = Array.from({
    length: Math.max(sessionDates.length, sessionNumbers.length, sessionSubjects.length),
  })
    .map((_, index) => {
      const sessionParts = [
        sessionDates[index]?.trim() || "",
        sessionNumbers[index]?.trim() ? `No. ${sessionNumbers[index]?.trim()}` : "",
        sessionSubjects[index]?.trim() ? `${sessionSubjects[index]?.trim()}` : "",
      ].filter(Boolean);

      return sessionParts.length > 0 ? `${index + 1}. ${sessionParts.join(" | ")}` : "";
    })
    .filter(Boolean);

  return [
    parsedInquiry.module ? `Module: ${parsedInquiry.module}` : "",
    parsedInquiry.time ? `Preferred Time: ${parsedInquiry.time}` : "",
    sessionDetailLines.length > 0 ? "Sessions:" : "",
    ...sessionDetailLines,
  ]
    .filter(Boolean)
    .join("\n");
}

function CoverageInquirySummary({ inquiry }: { inquiry: string }) {
  const parsedInquiry = parseCoverageInquiry(inquiry);
  if (!parsedInquiry) {
    return null;
  }

  const sessionDates = parsedInquiry.sessionDates || [];
  const sessionNumbers = parsedInquiry.sessionNumbers || [];
  const sessionSubjects = parsedInquiry.sessionSubjects || [];
  const sessionCount = Math.max(sessionDates.length, sessionNumbers.length, sessionSubjects.length, 1);

  return (
    <div className="space-y-3">
      <div className="overflow-hidden rounded-[28px] border border-primary/15 bg-gradient-to-br from-primary/[0.08] via-white to-fuchsia-50/70 shadow-[0_18px_40px_rgba(82,54,188,0.10)]">
        <div className="border-b border-primary/10 px-4 py-3 sm:px-5">
          <div className="inline-flex items-center rounded-full border border-primary/15 bg-white/85 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-primary shadow-sm">
            Coverage Session Request
          </div>
        </div>
        <div className="grid gap-4 px-4 py-4 sm:grid-cols-2 sm:px-5">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Tutor</div>
            <div className="mt-1 text-[15px] font-semibold text-foreground">{parsedInquiry.tutor || "-"}</div>
          </div>
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Module</div>
            <div className="mt-1 text-[15px] font-semibold text-foreground">{parsedInquiry.module || "-"}</div>
          </div>
          <div className="sm:col-span-2">
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Preferred Time</div>
            <div className="mt-1 text-[15px] font-semibold text-foreground">{parsedInquiry.time || "-"}</div>
          </div>
        </div>
      </div>

      <div className="grid gap-3">
        {Array.from({ length: sessionCount }).map((_, index) => {
          const sessionDate = sessionDates[index]?.trim() || "";
          const sessionNumber = sessionNumbers[index]?.trim() || "";
          const sessionSubject = sessionSubjects[index]?.trim()
            || (sessionSubjects.length === 1 ? sessionSubjects[0]?.trim() || "" : "");

          if (!sessionDate && !sessionNumber && !sessionSubject && index > 0) {
            return null;
          }

          return (
            <div
              key={`${sessionDate || "session"}-${index}`}
              className="rounded-[26px] border border-primary/12 bg-white/92 px-4 py-3.5 shadow-[0_14px_30px_rgba(82,54,188,0.07)]"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="text-sm font-semibold text-foreground">Session {index + 1}</div>
                <div className="inline-flex items-center rounded-full border border-primary/12 bg-primary/[0.06] px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-primary">
                  Planned Session
                </div>
              </div>
              <div className="mt-3 grid gap-3 sm:grid-cols-3">
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Date</div>
                  <div className="mt-1 text-sm font-semibold text-foreground">{sessionDate || "-"}</div>
                </div>
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Number</div>
                  <div className="mt-1 text-sm font-semibold text-foreground">{sessionNumber || "-"}</div>
                </div>
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Subject</div>
                  <div className="mt-1 text-sm font-semibold text-foreground">{sessionSubject || "-"}</div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function createCoverageTutorChoiceCard(inquiry: string): CoverageWorkflowCard {
  const timestamp = new Date().toISOString();
  const parsedInquiry = parseCoverageInquiry(inquiry);

  return {
    id: createCoverageCardId(),
    type: "tutor_choice",
    title: "",
    note: "",
    tutor: parsedInquiry?.tutor || "",
    tutorEmail: "",
    sessionDetails: buildCoverageTutorSessionDetails(inquiry),
    replyText: "",
    requestStatus: "draft",
    replyOutcome: "",
    locked: false,
    createdAt: timestamp,
    updatedAt: timestamp,
    submittedAt: "",
    respondedAt: "",
    relatedTutorChoiceCardId: "",
    requestSubmittedByAgentId: null,
    requestSubmittedByAgentName: "",
    requestSubmittedByAgentUsername: "",
    responseToken: "",
    sessionStartAt: "",
    sessionEndAt: "",
    confirmedAt: "",
    confirmedByAgentId: null,
    confirmedByAgentName: "",
    confirmedByAgentUsername: "",
    presentationFiles: [],
  };
}

function createCoverageNoteCard(): CoverageWorkflowCard {
  const timestamp = new Date().toISOString();

  return {
    id: createCoverageCardId(),
    type: "note",
    title: "",
    note: "",
    tutor: "",
    tutorEmail: "",
    sessionDetails: "",
    replyText: "",
    requestStatus: "draft",
    replyOutcome: "",
    locked: false,
    createdAt: timestamp,
    updatedAt: timestamp,
    submittedAt: "",
    respondedAt: "",
    relatedTutorChoiceCardId: "",
    requestSubmittedByAgentId: null,
    requestSubmittedByAgentName: "",
    requestSubmittedByAgentUsername: "",
    responseToken: "",
    sessionStartAt: "",
    sessionEndAt: "",
    confirmedAt: "",
    confirmedByAgentId: null,
    confirmedByAgentName: "",
    confirmedByAgentUsername: "",
    presentationFiles: [],
  };
}

function normalizeCoverageCardAttachment(attachment: CoverageCardAttachment | null | undefined): CoverageCardAttachment | null {
  if (!attachment?.dataUrl?.startsWith("data:")) {
    return null;
  }

  return {
    id: attachment.id || createCoverageCardId(),
    name: attachment.name || "attachment",
    mimeType: attachment.mimeType || "application/octet-stream",
    size: Number(attachment.size || 0),
    dataUrl: attachment.dataUrl,
  };
}

function normalizeCoverageTutorRequestStatus(status: unknown): CoverageTutorRequestStatus {
  switch (status) {
    case "requested":
    case "pending":
      return "requested";
    case "accepted":
      return "accepted";
    case "refused":
    case "rejected":
      return "refused";
    default:
      return "draft";
  }
}

function normalizeCoverageTutorReplyOutcome(outcome: unknown): CoverageTutorReplyOutcome {
  switch (outcome) {
    case "accepted":
      return "accepted";
    case "refused":
    case "rejected":
      return "refused";
    default:
      return "";
  }
}

function normalizeCoverageWorkflowCards(cards: CoverageWorkflowCard[] | null | undefined): CoverageWorkflowCard[] {
  const allowedTypes: CoverageWorkflowCardType[] = ["tutor_choice", "tutor_reply", "note"];

  return Array.isArray(cards)
    ? cards.flatMap((card) => {
        if (!card || !allowedTypes.includes(card.type)) {
          return [];
        }

        const requestStatus = normalizeCoverageTutorRequestStatus(card.requestStatus);
        const replyOutcome = normalizeCoverageTutorReplyOutcome(card.replyOutcome);
        const presentationFiles = Array.isArray(card.presentationFiles)
          ? card.presentationFiles
            .map((file) => normalizeCoverageCardAttachment(file))
            .filter((file): file is CoverageCardAttachment => Boolean(file))
          : [];

        return [{
          id: card.id || createCoverageCardId(),
          type: card.type,
          title: card.title || "",
          note: card.note || "",
          tutor: card.tutor || "",
          tutorEmail: card.tutorEmail || "",
          sessionDetails: card.sessionDetails || "",
          replyText: card.replyText || "",
          requestStatus,
          replyOutcome,
          locked: Boolean(card.locked),
          createdAt: card.createdAt || "",
          updatedAt: card.updatedAt || "",
          submittedAt: card.submittedAt || "",
          respondedAt: card.respondedAt || "",
          relatedTutorChoiceCardId: card.relatedTutorChoiceCardId || "",
          requestSubmittedByAgentId: card.requestSubmittedByAgentId ?? null,
          requestSubmittedByAgentName: card.requestSubmittedByAgentName || "",
          requestSubmittedByAgentUsername: card.requestSubmittedByAgentUsername || "",
          responseToken: card.responseToken || "",
          sessionStartAt: card.sessionStartAt || "",
          sessionEndAt: card.sessionEndAt || "",
          confirmedAt: card.confirmedAt || "",
          confirmedByAgentId: card.confirmedByAgentId ?? null,
          confirmedByAgentName: card.confirmedByAgentName || "",
          confirmedByAgentUsername: card.confirmedByAgentUsername || "",
          presentationFiles,
        }];
      })
    : [];
}

function getCoverageWorkflowCardSortTimestamp(card: Pick<CoverageWorkflowCard, "createdAt" | "updatedAt">) {
  const createdTimestamp = Date.parse(card.createdAt || "");
  if (!Number.isNaN(createdTimestamp)) {
    return createdTimestamp;
  }

  const updatedTimestamp = Date.parse(card.updatedAt || "");
  if (!Number.isNaN(updatedTimestamp)) {
    return updatedTimestamp;
  }

  return 0;
}

function sortCoverageWorkflowCardsForDisplay(cards: CoverageWorkflowCard[]): CoverageWorkflowCard[] {
  return [...cards].sort((leftCard, rightCard) => (
    getCoverageWorkflowCardSortTimestamp(rightCard) - getCoverageWorkflowCardSortTimestamp(leftCard)
  ));
}

function createDocumentationCard(): DocumentationWorkflowCard {
  const timestamp = new Date().toISOString();

  return {
    id: createCoverageCardId(),
    inquiry: "",
    symptoms: "",
    errors: "",
    steps: "",
    resources: "",
    locked: false,
    createdAt: timestamp,
    updatedAt: timestamp,
  };
}

function normalizeDocumentationWorkflowCards(
  cards: DocumentationWorkflowCard[] | null | undefined,
): DocumentationWorkflowCard[] {
  return Array.isArray(cards)
    ? cards.flatMap((card) => {
        if (!card) {
          return [];
        }

        return [{
          id: card.id || createCoverageCardId(),
          inquiry: card.inquiry || "",
          symptoms: card.symptoms || "",
          errors: card.errors || "",
          steps: card.steps || "",
          resources: card.resources || "",
          locked: Boolean(card.locked),
          createdAt: card.createdAt || "",
          updatedAt: card.updatedAt || "",
        }];
      })
    : [];
}

function getDocumentationWorkflowCardSortTimestamp(card: Pick<DocumentationWorkflowCard, "createdAt" | "updatedAt">) {
  const createdTimestamp = Date.parse(card.createdAt || "");
  if (!Number.isNaN(createdTimestamp)) {
    return createdTimestamp;
  }

  const updatedTimestamp = Date.parse(card.updatedAt || "");
  if (!Number.isNaN(updatedTimestamp)) {
    return updatedTimestamp;
  }

  return 0;
}

function sortDocumentationWorkflowCardsForDisplay(cards: DocumentationWorkflowCard[]): DocumentationWorkflowCard[] {
  return [...cards].sort((leftCard, rightCard) => (
    getDocumentationWorkflowCardSortTimestamp(rightCard) - getDocumentationWorkflowCardSortTimestamp(leftCard)
  ));
}

function buildDocumentationCardTimestampLabel(card: DocumentationWorkflowCard) {
  if (!card.createdAt) {
    return "Created time unavailable";
  }

  if (card.updatedAt && card.updatedAt !== card.createdAt) {
    return `Created ${formatDateTime(card.createdAt)} | Edited ${formatDateTime(card.updatedAt)}`;
  }

  return `Created ${formatDateTime(card.createdAt)}`;
}

function freezeDocumentationCardsForSave(documentation: AdminDocumentation): AdminDocumentation {
  const timestamp = new Date().toISOString();
  const nextCards = documentation.documentationCards.map((card) => {
    if (card.locked) {
      return card;
    }

    return {
      ...card,
      locked: true,
      updatedAt: timestamp,
    };
  });
  const latestCard = sortDocumentationWorkflowCardsForDisplay(nextCards)[0];

  return {
    ...documentation,
    documentationCards: nextCards,
    inquiry: latestCard?.inquiry || documentation.inquiry,
    symptoms: latestCard?.symptoms || documentation.symptoms,
    errors: latestCard?.errors || documentation.errors,
    steps: latestCard?.steps || documentation.steps,
    resources: latestCard?.resources || documentation.resources,
  };
}

function getCoverageAttachmentPreviewKind(file: Pick<CoverageCardAttachment, "mimeType" | "dataUrl"> | null | undefined) {
  const mimeType = (file?.mimeType || "").toLowerCase();
  const dataUrl = (file?.dataUrl || "").toLowerCase();

  if (mimeType.startsWith("image/") || dataUrl.startsWith("data:image/")) {
    return "image";
  }

  if (mimeType === "application/pdf" || dataUrl.startsWith("data:application/pdf")) {
    return "pdf";
  }

  return "unsupported";
}

function isValidCoverageTutorEmail(value: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

function hasCoverageTimestampUpdate(createdAt: string, updatedAt: string) {
  return Boolean(createdAt && updatedAt && createdAt !== updatedAt);
}

function buildCoverageTimestampLabel(createdAt: string, updatedAt: string) {
  if (!createdAt) {
    return "Created time unavailable";
  }

  if (hasCoverageTimestampUpdate(createdAt, updatedAt)) {
    return `Created ${formatDateTime(createdAt)} • Edited ${formatDateTime(updatedAt)}`;
  }

  return `Created ${formatDateTime(createdAt)}`;
}

function buildCoverageCardTimestampLabel(createdAt: string, updatedAt: string) {
  if (!createdAt) {
    return "Created time unavailable";
  }

  if (hasCoverageTimestampUpdate(createdAt, updatedAt)) {
    return `Created ${formatDateTime(createdAt)} | Edited ${formatDateTime(updatedAt)}`;
  }

  return `Created ${formatDateTime(createdAt)}`;
}

function summarizeCoverageTutorRequestDetails(sessionDetails: string) {
  const lines = sessionDetails
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  const moduleLine = lines.find((line) => line.toLowerCase().startsWith("module:"));
  const preferredTimeLine = lines.find((line) => line.toLowerCase().startsWith("preferred time:"));
  const sessionLines = lines.filter((line) => /^\d+\.\s/.test(line));

  return {
    moduleLine: moduleLine || "",
    preferredTimeLine: preferredTimeLine || "",
    sessionLines,
    sessionCount: sessionLines.length,
  };
}

function canConfirmCoverageReplyCard(card: Pick<CoverageWorkflowCard, "replyOutcome" | "confirmedAt" | "sessionStartAt">) {
  if (card.replyOutcome !== "accepted" || Boolean(card.confirmedAt)) {
    return false;
  }

  const sessionStartMs = Date.parse(card.sessionStartAt || "");
  if (Number.isNaN(sessionStartMs)) {
    return false;
  }

  return Date.now() >= sessionStartMs;
}

function getCoverageReplyCardTimingMessage(card: Pick<CoverageWorkflowCard, "replyOutcome" | "sessionStartAt" | "sessionEndAt">) {
  if (card.replyOutcome !== "accepted") {
    return "Tutor reply saved.";
  }

  const sessionStartMs = Date.parse(card.sessionStartAt || "");
  const sessionEndMs = Date.parse(card.sessionEndAt || "");
  if (Number.isNaN(sessionStartMs)) {
    return "Confirmation becomes available once the workflow provides a structured session time.";
  }

  const startLabel = formatDateTime(card.sessionStartAt || "");
  const endLabel = Number.isNaN(sessionEndMs) ? "" : formatDateTime(card.sessionEndAt || "");
  const sessionWindowLabel = endLabel ? `${startLabel} to ${endLabel}` : startLabel;

  if (Date.now() < sessionStartMs) {
    return `Confirmation becomes available at ${sessionWindowLabel}.`;
  }

  return `Session time reached: ${sessionWindowLabel}.`;
}

function getCoverageTutorRequestLabel(status: CoverageTutorRequestStatus) {
  switch (status) {
    case "requested":
      return "Requested";
    case "accepted":
      return "Accepted";
    case "refused":
      return "Refused";
    default:
      return "";
  }
}

function getCoverageTutorRequestBadgeClassName(status: CoverageTutorRequestStatus) {
  switch (status) {
    case "requested":
      return "border-amber-200 bg-amber-50 text-amber-700";
    case "accepted":
      return "border-emerald-200 bg-emerald-50 text-emerald-700";
    case "refused":
      return "border-rose-200 bg-rose-50 text-rose-700";
    default:
      return "border-slate-200 bg-slate-50 text-slate-700";
  }
}

function getCoverageReplyOutcomeLabel(outcome: CoverageTutorReplyOutcome) {
  switch (outcome) {
    case "accepted":
      return "Accepted";
    case "refused":
      return "Refused";
    default:
      return "Reply";
  }
}

function buildStandardDocumentationDraft(
  ticket: Pick<TicketDetail, "id" | "chatId" | "documentation">,
): AdminDocumentation {
  const normalizedDocumentation = normalizeDocumentationDraft(ticket.documentation);

  return {
    ...normalizedDocumentation,
    chatId: normalizedDocumentation.chatId || ticket.chatId || "",
    ticketId: normalizedDocumentation.ticketId || ticket.id || "",
  };
}

function buildCoverageDocumentationDraft(
  ticket: Pick<TicketDetail, "id" | "inquiry" | "chatId" | "documentation">,
): AdminDocumentation {
  const normalizedDocumentation = normalizeDocumentationDraft(ticket.documentation);
  const coverageCards = normalizedDocumentation.coverageCards.length > 0
    ? normalizedDocumentation.coverageCards
    : [createCoverageTutorChoiceCard(ticket.inquiry || normalizedDocumentation.inquiry)];

  return {
    ...normalizedDocumentation,
    inquiry: normalizedDocumentation.inquiry || ticket.inquiry || "",
    chatId: normalizedDocumentation.chatId || ticket.chatId || "",
    ticketId: normalizedDocumentation.ticketId || ticket.id || "",
    coverageCards,
  };
}

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
    escalationAgentId: documentation?.escalationAgentId ?? null,
    escalationAgentName: documentation?.escalationAgentName || "",
    escalationNote: documentation?.escalationNote || "",
    coverageNotes: documentation?.coverageNotes || "",
    coverageCards: normalizeCoverageWorkflowCards(documentation?.coverageCards),
    documentationCards: normalizeDocumentationWorkflowCards(documentation?.documentationCards),
    errorImages: Array.isArray(documentation?.errorImages) ? documentation.errorImages : [],
  };
}

function normalizeConsoleSearchValue(value: string | null | undefined): string {
  return (value || "")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

function compactConsoleSearchValue(value: string | null | undefined): string {
  return normalizeConsoleSearchValue(value).replace(/[\s\-_]+/g, "");
}

function parseAdminDeepLink(search: string) {
  const searchParams = new URLSearchParams(search);
  const requestedView = searchParams.get("view");
  const requestedTicketId = searchParams.get("ticket") || "";
  const requestedScope = searchParams.get("scope");
  const requestedQueueTab = searchParams.get("tab");
  const shouldOpenManagement = requestedView === "management";
  const shouldOpenConsole = requestedView === "console" || Boolean(requestedTicketId);

  return {
    view: shouldOpenManagement
      ? "management" as const
      : shouldOpenConsole
        ? "console" as const
        : "dashboard" as const,
    ticketId: requestedTicketId,
    scope: requestedScope === "all" ? "all" as const : "my" as const,
    queueTab: requestedQueueTab === "closed" ? "closed" as const : "open" as const,
  };
}

function buildConsoleSearchResultUrl({
  pathname,
  ticketId,
  scope,
  queueTab,
}: {
  pathname: string;
  ticketId: string;
  scope: "my" | "all";
  queueTab: "open" | "closed";
}) {
  const nextUrl = new URL(pathname, window.location.origin);
  nextUrl.searchParams.set("view", "console");
  nextUrl.searchParams.set("ticket", ticketId);
  nextUrl.searchParams.set("scope", scope);
  nextUrl.searchParams.set("tab", queueTab);
  return nextUrl.toString();
}

function shouldRouteConsoleChatToMyOpenQueue({
  currentScope,
  currentQueueTab,
  ticket,
  sessionAgentId,
}: {
  currentScope: "my" | "all";
  currentQueueTab: "open" | "closed";
  ticket: Pick<TicketSummary, "assignedAgentId" | "chatState">;
  sessionAgentId: number | null | undefined;
}) {
  return (
    currentScope === "all"
    && currentQueueTab === "open"
    && ticket.chatState !== "closed"
    && Boolean(sessionAgentId)
    && ticket.assignedAgentId === sessionAgentId
  );
}

function getConsoleDurationStartInfo(ticket: Pick<TicketSummary, "queueAssignedAt" | "liveChatRequestedAt">) {
  const assignedAt = parseTimestampMs(ticket.queueAssignedAt);
  if (assignedAt !== null) {
    return {
      startedAt: assignedAt,
      sourceLabel: "Assigned",
    };
  }

  const liveChatStartedAt = parseTimestampMs(ticket.liveChatRequestedAt);
  if (liveChatStartedAt !== null) {
    return {
      startedAt: liveChatStartedAt,
      sourceLabel: "Live chat",
    };
  }

  return null;
}

function getConsoleDurationEndTimestamp(
  ticket: Pick<TicketDetail, "chatState" | "lastMessageAt" | "closedAt" | "updatedAt">,
  nowTimestamp: number,
) {
  if (ticket.chatState !== "closed") {
    return nowTimestamp;
  }

  return (
    parseTimestampMs(ticket.lastMessageAt)
    ?? parseTimestampMs(ticket.closedAt)
    ?? parseTimestampMs(ticket.updatedAt)
    ?? nowTimestamp
  );
}

function parseTimestampMs(value: string | null | undefined) {
  const parsedValue = Date.parse(value || "");
  return Number.isNaN(parsedValue) ? null : parsedValue;
}

function formatConsoleDuration(startTimestamp: number, endTimestamp: number) {
  const totalSeconds = Math.max(0, Math.floor((endTimestamp - startTimestamp) / 1000));
  return formatConsoleDurationFromSeconds(totalSeconds);
}

function formatConsoleDurationFromMinutes(totalMinutes: number) {
  return formatConsoleDurationFromSeconds(Math.max(0, totalMinutes) * 60);
}

function formatConsoleDurationFromSeconds(totalSeconds: number) {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function deriveDocumentationTicketStatus(status: TicketSummary["status"]): DocumentationWorkflowStatus | "" {
  return status === "Closed" || status === "Pending" ? status : "";
}

function deriveDocumentationEscalationAgentId(
  ticket: Pick<TicketSummary, "pendingEscalationNotification" | "statusReason"> & {
    documentation?: Pick<AdminDocumentation, "escalationAgentId"> | null;
  },
) {
  if (normalizeQuickTicketStatusReason(ticket.statusReason || "") !== "Escalation") {
    return "";
  }

  if (ticket.pendingEscalationNotification?.toAgentId) {
    return String(ticket.pendingEscalationNotification.toAgentId);
  }

  return ticket.documentation?.escalationAgentId ? String(ticket.documentation.escalationAgentId) : "";
}

function deriveDocumentationEscalationNote(
  documentation?: Pick<AdminDocumentation, "escalationNote"> | null,
) {
  return documentation?.escalationNote || "";
}

function getAutomaticDocumentationStatusReason(status: DocumentationWorkflowStatus | "") {
  return status === "Closed" ? "Closed via Agent" : "";
}

function getDefaultDocumentationStatusReason(status: DocumentationWorkflowStatus | "") {
  return status === "Pending" ? defaultPendingDocumentationStatusReason : "";
}

function deriveDocumentationIssuesAddressed(
  chatState: string,
  documentation?: Pick<AdminDocumentation, "issuesAddressed"> | null,
): DocumentationIssuesAddressed {
  if (documentation?.issuesAddressed === "yes" || documentation?.issuesAddressed === "no") {
    return documentation.issuesAddressed;
  }

  return chatState === "closed" ? "yes" : "";
}

function normalizeQuickTicketStatusReason(statusReason: string) {
  const normalizedReason = statusReason.trim().toLowerCase();

  if (
    normalizedReason === "awaiting resolution"
    || normalizedReason === "awaiting support review"
    || normalizedReason === "quick ticket"
  ) {
    return "Quick Ticket";
  }

  return statusReason;
}

function getDisplayedTicketStatusReason(source: {
  statusReason: string;
  technicalSubcategory?: string | null;
}) {
  if (!source.statusReason) {
    return "-";
  }

  if (normalizeQuickTicketStatusReason(source.statusReason) !== "Quick Ticket") {
    return source.statusReason;
  }

  return source.technicalSubcategory === "Coverage" ? "Coverage Ticket" : "Quick Ticket";
}

function getDisplayedTicketStatus(source: {
  status: string;
  technicalSubcategory?: string | null;
}) {
  return source.status || "-";
}

function isStaffSupportAccount(agent: Pick<AdminAgent, "accountScope" | "role">) {
  const normalizedScope = (agent.accountScope || "").trim().toLowerCase();
  return normalizedScope === "staff";
}

function filterDashboardTickets(tickets: TicketSummary[], filter: DashboardTicketFilter) {
  if (filter === "open") {
    return tickets.filter(isDashboardOpenTicket);
  }

  if (filter === "pending") {
    return tickets.filter((ticket) => ticket.status === "Pending");
  }

  if (filter === "escalation") {
    return tickets.filter((ticket) => ticket.status === "Pending" && ticket.statusReason === "Escalation");
  }

  if (filter === "closed") {
    return tickets.filter((ticket) => ticket.status === "Closed");
  }

  if (filter === "slaBreached") {
    return tickets.filter((ticket) => ticket.slaStatus === "Breached");
  }

  if (filter === "coverage") {
    return tickets.filter((ticket) => isCoverageTicket(ticket));
  }

  if (filter === "quickResolution") {
    return tickets.filter(isDashboardQuickResolutionTicket);
  }

  return tickets;
}

function buildDashboardAssignedAgentFilterValue(agentId: number): DashboardAssignedFilter {
  return `agent:${agentId}`;
}

function parseDashboardAssignedAgentFilterValue(filter: DashboardAssignedFilter) {
  if (!filter.startsWith("agent:")) {
    return null;
  }

  const parsedValue = Number(filter.slice("agent:".length));
  return Number.isFinite(parsedValue) ? parsedValue : null;
}

function isTicketLinkedToEscalationAgent(
  ticket: Pick<TicketSummary, "assignedAgentId" | "pendingEscalationNotification" | "latestEscalationClosure" | "statusReason" | "documentation">,
  agentId: number,
) {
  const pendingEscalationNotification = ticket.pendingEscalationNotification;
  if (pendingEscalationNotification) {
    return pendingEscalationNotification.fromAgentId === agentId || pendingEscalationNotification.toAgentId === agentId;
  }

  const latestEscalationClosure = ticket.latestEscalationClosure;
  if (!latestEscalationClosure) {
    if (ticket.statusReason !== "Escalation") {
      return false;
    }

    return ticket.assignedAgentId === agentId || ticket.documentation?.escalationAgentId === agentId;
  }

  return latestEscalationClosure.fromAgentId === agentId || latestEscalationClosure.toAgentId === agentId;
}

function filterDashboardTicketsByAssignee(
  tickets: TicketSummary[],
  filter: DashboardAssignedFilter,
  sessionAgentId: number | null,
) {
  if (filter === "all") {
    return tickets;
  }

  if (filter === "me") {
    if (!sessionAgentId) {
      return tickets;
    }

    return tickets.filter((ticket) =>
      ticket.assignedAgentId === sessionAgentId
      || isTicketLinkedToEscalationAgent(ticket, sessionAgentId),
    );
  }

  if (filter === "unassigned") {
    return tickets.filter((ticket) => !ticket.assignedAgentId);
  }

  const agentId = parseDashboardAssignedAgentFilterValue(filter);
  if (!agentId) {
    return tickets;
  }

  return tickets.filter((ticket) =>
    ticket.assignedAgentId === agentId
    || isTicketLinkedToEscalationAgent(ticket, agentId),
  );
}

function getDashboardTableTitle(filter: DashboardTicketFilter) {
  if (filter === "open") return "Open Tickets";
  if (filter === "pending") return "Pending Tickets";
  if (filter === "escalation") return "Escalation Tickets";
  if (filter === "closed") return "Closed Tickets";
  if (filter === "slaBreached") return "SLA Breaches";
  if (filter === "coverage") return "Coverage Tickets";
  if (filter === "quickResolution") return "Quick Tickets";
  return "Recent Tickets";
}

function getDashboardTableCountLabel(
  filter: DashboardTicketFilter,
  visibleCount: number,
  scopedCount: number,
  assignedScopeCount: number,
  totalCount: number,
  hasSearch: boolean,
  hasAssignedFilter: boolean,
  assignedFilterLabel: string,
) {
  if (hasSearch) {
    return filter === "all" && !hasAssignedFilter
      ? `${visibleCount} matching of ${totalCount} total`
      : `${visibleCount} matching of ${scopedCount}`;
  }

  if (filter === "all" && !hasAssignedFilter) {
    return `${totalCount} total`;
  }

  if (filter === "all" && hasAssignedFilter) {
    return `${assignedScopeCount} ticket${assignedScopeCount === 1 ? "" : "s"} for ${assignedFilterLabel}`;
  }

  if (filter === "quickResolution") {
    return hasAssignedFilter
      ? `${visibleCount} quick ticket${visibleCount === 1 ? "" : "s"} for ${assignedFilterLabel}`
      : `${visibleCount} quick ticket${visibleCount === 1 ? "" : "s"}`;
  }

  if (filter === "coverage") {
    return hasAssignedFilter
      ? `${visibleCount} coverage ticket${visibleCount === 1 ? "" : "s"} for ${assignedFilterLabel}`
      : `${visibleCount} coverage ticket${visibleCount === 1 ? "" : "s"}`;
  }

  return hasAssignedFilter
    ? `${visibleCount} matching ticket${visibleCount === 1 ? "" : "s"} for ${assignedFilterLabel}`
    : `${visibleCount} matching ticket${visibleCount === 1 ? "" : "s"}`;
}

function getDashboardEmptyMessage(filter: DashboardTicketFilter) {
  if (filter === "open") return "No open tickets are currently available.";
  if (filter === "pending") return "No pending tickets are currently available.";
  if (filter === "escalation") return "No escalation tickets are currently available.";
  if (filter === "closed") return "No closed tickets are currently available.";
  if (filter === "slaBreached") return "No SLA breaches are currently available.";
  if (filter === "coverage") return "No coverage tickets are currently available.";
  if (filter === "quickResolution") return "No quick tickets are currently available.";
  return "No tickets have been created yet.";
}

function getDashboardAssignedFilterLabel(
  filter: DashboardAssignedFilter,
  sessionAgentName: string,
  agents: AdminAgent[],
) {
  if (filter === "me") {
    return "Me";
  }

  if (filter === "unassigned") {
    return "Unassigned";
  }

  if (filter === "all") {
    return "All Tickets";
  }

  const agentId = parseDashboardAssignedAgentFilterValue(filter);
  const matchedAgent = agents.find((agent) => agent.id === agentId);
  return matchedAgent ? getAgentDisplayName(matchedAgent) : sessionAgentName;
}

function getDashboardAssignedFilterEmptyTargetLabel(
  filter: DashboardAssignedFilter,
  sessionAgentName: string,
  agents: AdminAgent[],
) {
  if (filter === "me") {
    return "you";
  }

  if (filter === "unassigned") {
    return "the unassigned queue";
  }

  if (filter === "all") {
    return "the current filter";
  }

  const agentId = parseDashboardAssignedAgentFilterValue(filter);
  const matchedAgent = agents.find((agent) => agent.id === agentId);
  return matchedAgent ? getAgentDisplayName(matchedAgent) : sessionAgentName;
}

function getDashboardAssignedFilterEmptyMessage(
  filter: DashboardTicketFilter,
  targetLabel: string,
) {
  if (filter === "open") return `No open tickets are currently assigned to ${targetLabel}.`;
  if (filter === "pending") return `No pending tickets are currently assigned to ${targetLabel}.`;
  if (filter === "escalation") return `No escalation tickets are currently linked to ${targetLabel}.`;
  if (filter === "closed") return `No closed tickets are currently assigned to ${targetLabel}.`;
  if (filter === "slaBreached") return `No SLA breaches are currently assigned to ${targetLabel}.`;
  if (filter === "coverage") return `No coverage tickets are currently assigned to ${targetLabel}.`;
  if (filter === "quickResolution") return `No quick tickets are currently assigned to ${targetLabel}.`;
  return `No tickets are currently assigned to ${targetLabel}.`;
}

function isQuickResolutionTicket(ticket: Pick<TicketSummary, "status" | "statusReason">) {
  if (ticket.status !== "Pending") {
    return false;
  }

  return normalizeQuickTicketStatusReason(ticket.statusReason) === "Quick Ticket";
}

function isDashboardQuickResolutionTicket(
  ticket: Pick<TicketSummary, "status" | "statusReason" | "technicalSubcategory">,
) {
  return isQuickResolutionTicket(ticket) && !isCoverageTicket(ticket);
}

function getDisplayedChatReference(
  source: {
    status: "Open" | "Pending" | "Closed";
    statusReason: string;
    technicalSubcategory?: string | null;
    chatId?: string | null;
    pendingTeamsCallNotification?: PendingTeamsCallNotification | null;
    teamsCallRequested?: boolean;
    ticketId?: string;
    id?: string | number;
  },
  fallbackToTicketId = false,
) {
  if (source.status === "Pending" && source.technicalSubcategory === "Coverage") {
    return "Coverage Ticket";
  }

  if (source.status === "Pending" && normalizeQuickTicketStatusReason(source.statusReason) === "Quick Ticket") {
    return getDisplayedTicketStatusReason(source);
  }

  if (source.pendingTeamsCallNotification) {
    return "Teams Call";
  }

  if (source.teamsCallRequested) {
    return "Teams Call";
  }

  if (source.chatId) {
    return source.chatId;
  }

  if (fallbackToTicketId) {
    return source.ticketId || (source.id === undefined || source.id === null ? "-" : String(source.id));
  }

  return "-";
}

function isDashboardOpenTicket(ticket: Pick<TicketSummary, "status" | "chatState" | "chatIsActive" | "liveChatRequested">) {
  return (
    ticket.status === "Open"
    && ticket.chatState !== "closed"
    && (!ticket.liveChatRequested || ticket.chatIsActive)
  );
}

function buildDocumentationWorkflowNote(
  ticket: TicketDetail,
  status: DocumentationWorkflowStatus,
  statusReason: string,
  issuesAddressed: DocumentationIssuesAddressed,
  escalationAssigneeName = "",
  escalationNote = "",
) {
  if (statusReason === "Escalation") {
    return [
      `Documentation workflow updated ticket ${ticket.id}.`,
      `Status set to ${status}.`,
      `Reason set to ${statusReason}.`,
      ...(escalationAssigneeName ? [`Escalation notice sent to ${escalationAssigneeName}.`] : []),
      `Ticket ID: ${ticket.id}.`,
      ...(escalationNote ? [`Escalation note: ${escalationNote}`] : []),
      issuesAddressed === "yes"
        ? "The live chat was closed after the escalation notice was sent."
        : "A follow-up ticket was created after the escalation notice was sent.",
      "Ticket assignment remained unchanged.",
    ].join(" ");
  }

  const changeSummary = [
    `Documentation workflow updated ticket ${ticket.id}.`,
    `Status set to ${status}.`,
    `Reason set to ${statusReason}.`,
    ...(statusReason === "Escalation" && escalationAssigneeName
      ? [`Escalated to ${escalationAssigneeName}.`]
      : []),
    issuesAddressed === "yes"
      ? "Learner issues were marked as addressed and the chat was closed."
      : "Learner issues were marked as not yet addressed and the chat continued on a follow-up ticket.",
  ];

  return changeSummary.join(" ");
}

function getLatestTransferHandoffNotice(history: HistoryItem[], assignedAgentName: string) {
  const normalizedAssignedAgentName = sanitizeAssignedAgentName(assignedAgentName);
  if (!normalizedAssignedAgentName) {
    return null;
  }

  for (const item of history) {
    if (item.eventType !== "transfer_request_accepted") {
      continue;
    }

    const transferredTo = getActivityPayloadTextValue(item.payload.toAgentName);
    const reason = getActivityPayloadTextValue(item.payload.reason);
    if (!transferredTo || !reason) {
      continue;
    }

    if (sanitizeAssignedAgentName(transferredTo) !== normalizedAssignedAgentName) {
      continue;
    }

    return {
      transferredFrom: getActivityPayloadTextValue(item.payload.fromAgentName) || "Support Portal",
      transferredTo,
      reason,
      createdAt: item.createdAt,
    };
  }

  return null;
}

function sortConsoleTickets(tickets: TicketSummary[], queueTab: "open" | "closed") {
  return [...tickets].sort((leftTicket, rightTicket) => {
    if (queueTab === "open") {
      const priorityDifference = compareTicketPriority(leftTicket, rightTicket);
      if (priorityDifference !== 0) {
        return priorityDifference;
      }
    }

    const leftTime = getConsoleTicketSortTime(leftTicket, queueTab);
    const rightTime = getConsoleTicketSortTime(rightTicket, queueTab);

    if (queueTab === "open") {
      return leftTime - rightTime;
    }

    return rightTime - leftTime;
  });
}

function sortConsoleSearchResults(tickets: TicketSummary[]) {
  return [...tickets].sort((leftTicket, rightTicket) => {
    const leftQueueTab = leftTicket.chatState === "closed" ? "closed" : "open";
    const rightQueueTab = rightTicket.chatState === "closed" ? "closed" : "open";

    if (leftQueueTab !== rightQueueTab) {
      return leftQueueTab === "open" ? -1 : 1;
    }

    if (leftQueueTab === "open") {
      const priorityDifference = compareTicketPriority(leftTicket, rightTicket);
      if (priorityDifference !== 0) {
        return priorityDifference;
      }
    }

    const leftTime = getConsoleTicketSortTime(leftTicket, leftQueueTab);
    const rightTime = getConsoleTicketSortTime(rightTicket, rightQueueTab);

    if (leftQueueTab === "open") {
      return leftTime - rightTime;
    }

    return rightTime - leftTime;
  });
}

const ticketPriorityRank: Record<string, number> = {
  urgent: 0,
  high: 1,
  normal: 2,
  low: 3,
};

function getTicketPriorityRank(priority: string | null | undefined) {
  return ticketPriorityRank[(priority || "").trim().toLowerCase()] ?? 99;
}

function compareTicketPriority(
  leftTicket: Pick<TicketSummary, "priority">,
  rightTicket: Pick<TicketSummary, "priority">,
) {
  const leftPriorityRank = getTicketPriorityRank(leftTicket.priority);
  const rightPriorityRank = getTicketPriorityRank(rightTicket.priority);
  return leftPriorityRank - rightPriorityRank;
}

function shouldPrioritizeTicketByStatus(ticket: Pick<TicketSummary, "status" | "chatState" | "chatIsActive" | "liveChatRequested">) {
  return isDashboardOpenTicket(ticket) || ticket.status === "Pending";
}

function compareTicketLifecycleRank(
  leftTicket: Pick<TicketSummary, "status" | "chatState" | "chatIsActive" | "liveChatRequested">,
  rightTicket: Pick<TicketSummary, "status" | "chatState" | "chatIsActive" | "liveChatRequested">,
) {
  const leftRank = shouldPrioritizeTicketByStatus(leftTicket) ? 0 : 1;
  const rightRank = shouldPrioritizeTicketByStatus(rightTicket) ? 0 : 1;
  return leftRank - rightRank;
}

function getDashboardTicketSortTimestamp(
  ticket: Pick<TicketSummary, "createdAt" | "updatedAt">,
) {
  const timestampSource = ticket.createdAt || ticket.updatedAt;
  const timestampValue = Date.parse(timestampSource || "");
  return Number.isNaN(timestampValue) ? 0 : timestampValue;
}

function getConsoleTicketSortTime(ticket: TicketSummary, queueTab: "open" | "closed") {
  const timestampSource = queueTab === "open"
    ? ticket.liveChatRequestedAt || ticket.queueAssignedAt || ticket.lastMessageAt || ticket.createdAt
    : ticket.lastMessageAt || ticket.updatedAt || ticket.queueAssignedAt || ticket.createdAt;
  const timestampValue = Date.parse(timestampSource || "");

  return Number.isNaN(timestampValue) ? 0 : timestampValue;
}

function serializeConsoleChatHistory(messages: ChatHistoryItem[]) {
  return messages
    .filter((message) => message.source !== "history_event" && message.source !== "intro")
    .map((message) => ({
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

function readFileAsCoverageCardAttachment(file: File): Promise<CoverageCardAttachment> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();

    reader.onload = () => {
      const result = typeof reader.result === "string" ? reader.result : "";
      if (!result.startsWith("data:")) {
        reject(new Error("Invalid file format."));
        return;
      }

      resolve({
        id: createCoverageCardId(),
        name: file.name,
        mimeType: file.type || "application/octet-stream",
        size: file.size,
        dataUrl: result,
      });
    };

    reader.onerror = () => reject(new Error("Could not read file."));
    reader.readAsDataURL(file);
  });
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

const LogoutButton = ({ collapsed = false }: { collapsed?: boolean }) => {
  const navigate = useNavigate();

  async function handleLogout() {
    const session = getAdminSession();

    try {
      if (session?.username && session.instanceId) {
        await fetch("/api/admin/logout", {
          method: "POST",
          headers: buildAdminJsonHeaders(),
          body: JSON.stringify({}),
        });
      }
    } catch {
      // Keep the local logout responsive even if the network call fails.
    } finally {
      clearAdminSession();
      navigate("/admin/login");
    }
  }

  return (
    <Button
      variant="outline"
      size={collapsed ? "icon" : "sm"}
      className={cn(!collapsed && "justify-start")}
      onClick={() => void handleLogout()}
    >
      <LogOut className={cn("h-4 w-4", !collapsed && "mr-2")} />
      {!collapsed ? "Logout" : null}
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

function playTransferNotificationSound() {
  if (typeof window === "undefined") {
    return;
  }

  const audioWindow = window as Window & {
    webkitAudioContext?: typeof AudioContext;
  };
  const AudioContextConstructor = window.AudioContext || audioWindow.webkitAudioContext;

  if (!AudioContextConstructor) {
    return;
  }

  try {
    const audioContext = new AudioContextConstructor();
    const now = audioContext.currentTime;
    const masterGain = audioContext.createGain();
    const compressor = audioContext.createDynamicsCompressor();
    const scheduleRingPulse = (
      startOffset: number,
      duration: number,
      primaryFrequency: number,
      secondaryFrequency: number,
    ) => {
      const pulseStart = now + startOffset;
      const pulseEnd = pulseStart + duration;
      const pulseGain = audioContext.createGain();
      const primaryTone = audioContext.createOscillator();
      const secondaryTone = audioContext.createOscillator();

      pulseGain.gain.setValueAtTime(0.0001, pulseStart);
      pulseGain.gain.exponentialRampToValueAtTime(0.14, pulseStart + 0.025);
      pulseGain.gain.exponentialRampToValueAtTime(0.07, pulseStart + duration * 0.55);
      pulseGain.gain.exponentialRampToValueAtTime(0.0001, pulseEnd);
      pulseGain.connect(masterGain);

      primaryTone.type = "triangle";
      primaryTone.frequency.setValueAtTime(primaryFrequency, pulseStart);
      primaryTone.frequency.linearRampToValueAtTime(primaryFrequency * 0.985, pulseEnd);
      primaryTone.connect(pulseGain);
      primaryTone.start(pulseStart);
      primaryTone.stop(pulseEnd);

      secondaryTone.type = "sine";
      secondaryTone.frequency.setValueAtTime(secondaryFrequency, pulseStart);
      secondaryTone.frequency.linearRampToValueAtTime(secondaryFrequency * 1.015, pulseEnd);
      secondaryTone.connect(pulseGain);
      secondaryTone.start(pulseStart);
      secondaryTone.stop(pulseEnd);
    };

    void audioContext.resume().catch(() => undefined);

    compressor.threshold.setValueAtTime(-18, now);
    compressor.knee.setValueAtTime(18, now);
    compressor.ratio.setValueAtTime(8, now);
    compressor.attack.setValueAtTime(0.003, now);
    compressor.release.setValueAtTime(0.2, now);
    masterGain.gain.setValueAtTime(0.9, now);
    masterGain.connect(compressor);
    compressor.connect(audioContext.destination);

    // Layered pulses make the alert feel closer to a ringtone than a single beep.
    scheduleRingPulse(0.0, 0.18, 1046.5, 1318.5);
    scheduleRingPulse(0.24, 0.18, 1046.5, 1568);
    scheduleRingPulse(0.5, 0.18, 1318.5, 1760);
    scheduleRingPulse(0.92, 0.18, 1046.5, 1318.5);
    scheduleRingPulse(1.16, 0.18, 1046.5, 1568);
    scheduleRingPulse(1.42, 0.22, 1318.5, 1760);

    window.setTimeout(() => {
      void audioContext.close().catch(() => undefined);
    }, 2200);
  } catch {
    // Ignore sound playback failures so notifications still render.
  }
}

const adminDesktopNotificationPromptStorageKeyPrefix = "support-admin-desktop-notification-prompted";

function getAdminDesktopNotificationPromptStorageKey(username: string) {
  return `${adminDesktopNotificationPromptStorageKeyPrefix}:${username.toLowerCase()}`;
}

function browserDesktopNotificationsSupported() {
  return typeof window !== "undefined" && "Notification" in window;
}

function shouldDispatchAdminDesktopNotification() {
  if (!browserDesktopNotificationsSupported() || typeof document === "undefined") {
    return false;
  }

  if (window.Notification.permission !== "granted") {
    return false;
  }

  return document.visibilityState !== "visible" || !document.hasFocus();
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

function formatTicketHeaderCategoryLabel(category: string, technicalSubcategory: string) {
  if (category === "Technical" && technicalSubcategory) {
    return technicalSubcategory;
  }

  return formatCategoryLabel(category, technicalSubcategory);
}

function getTicketTransferRowClassName(
  ticket: Pick<TicketSummary, "pendingTransferRequest" | "latestTransferDecision" | "status" | "statusReason" | "slaStatus">,
) {
  if (ticket.slaStatus === "Breached") {
    return "bg-red-50/70 hover:bg-red-50";
  }

  if (normalizeQuickTicketStatusReason(ticket.statusReason) === "Quick Ticket") {
    return "bg-violet-50/70 hover:bg-violet-50";
  }

  if (ticket.status === "Pending" && ticket.statusReason === "Escalation") {
    return "bg-amber-50/70 hover:bg-amber-50";
  }

  if (ticket.pendingTransferRequest) {
    return "bg-amber-50/70 hover:bg-amber-50";
  }

  if (ticket.latestTransferDecision?.status === "accepted") {
    return "bg-sky-50/70 hover:bg-sky-50";
  }

  if (ticket.status === "Closed") {
    return "bg-emerald-50/70 hover:bg-emerald-50";
  }

  if (ticket.status === "Pending") {
    return "bg-warning/10 hover:bg-warning/15";
  }

  if (ticket.status === "Open") {
    return "bg-info/10 hover:bg-info/15";
  }

  return "hover:bg-secondary/30";
}

function getAssignedAgentBadgeLabel(
  assignedAgentName: string,
  statusReason: string,
  documentation?: Pick<AdminDocumentation, "escalationAgentId" | "escalationAgentName"> | null,
  pendingEscalationNotification?: PendingEscalationNotification | null,
  latestEscalationClosure?: LatestEscalationClosure | null,
  latestTransferDecision?: LatestTransferDecision | null,
) {
  const currentAssignedAgentName = assignedAgentName || "Unassigned";

  if (
    pendingEscalationNotification?.fromAgentName
    && pendingEscalationNotification.toAgentName
  ) {
    return `From ${pendingEscalationNotification.fromAgentName} -- To ${pendingEscalationNotification.toAgentName}`;
  }

  if (
    latestEscalationClosure?.fromAgentName
    && latestEscalationClosure.toAgentName
  ) {
    return `From ${latestEscalationClosure.fromAgentName} -- To ${latestEscalationClosure.toAgentName}`;
  }

  if (
    statusReason === "Escalation"
    && currentAssignedAgentName
    && currentAssignedAgentName !== "Unassigned"
    && documentation?.escalationAgentName
  ) {
    return `From ${currentAssignedAgentName} -- To ${documentation.escalationAgentName}`;
  }

  if (
    latestTransferDecision?.status === "accepted"
    && sanitizeAssignedAgentName(latestTransferDecision.toAgentName) === sanitizeAssignedAgentName(currentAssignedAgentName)
    && sanitizeAssignedAgentName(latestTransferDecision.fromAgentName)
    && sanitizeAssignedAgentName(latestTransferDecision.fromAgentName) !== sanitizeAssignedAgentName(currentAssignedAgentName)
  ) {
    return `Assigned from ${latestTransferDecision.fromAgentName} to ${currentAssignedAgentName}`;
  }

  return `Assigned to ${currentAssignedAgentName}`;
}

function humanizeEvent(value: string) {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

type ActivityPayloadEntryKind = "text" | "mono" | "link" | "multiline";

interface ActivityPayloadEntry {
  key: string;
  label: string;
  value: string;
  kind: ActivityPayloadEntryKind;
}

const activityEventLabels: Record<string, string> = {
  assignment_changed: "Assignment Updated",
  chat_history_synced: "Chat History Synced",
  follow_up_ticket_created: "Follow-up Ticket Created",
  internal_note: "Internal Note",
  live_chat_requested: "Live Chat Requested",
  sla_changed: "SLA Updated",
  status_changed: "Status Updated",
  status_reason_changed: "Status Reason Updated",
  support_session_booking_failed: "Session Booking Failed",
  support_session_cancelled: "Session Cancelled",
  support_session_requested: "Session Requested",
  support_session_scheduled: "Session Scheduled",
  support_session_unavailable: "Session Unavailable",
  ticket_created: "Ticket Created",
  ticket_updated: "Ticket Updated",
  coverage_ticket_operations_notified: "Operations Notified",
  coverage_ticket_operations_notification_failed: "Operations Notification Failed",
  coverage_tutor_requested: "Tutor Requested",
  coverage_tutor_response: "Tutor Reply",
  coverage_session_confirmed: "Session Confirmed",
  escalation_closed: "Escalation Closed",
  escalation_notified: "Escalation Notified",
  teams_call_requested: "Teams Call Requested",
  transfer_requested: "Transfer Requested",
  transfer_request_accepted: "Transfer Accepted",
  transfer_request_rejected: "Transfer Declined",
};

const activityPayloadLabels: Record<string, string> = {
  calendarEventId: "Calendar Event ID",
  category: "Category",
  chatId: "Chat ID",
  cardId: "Card ID",
  closedAt: "Closed At",
  closedById: "Closed By ID",
  closedByName: "Closed By",
  closedByUsername: "Closed By Username",
  closedStatusReason: "Closed Status Reason",
  evidence_count: "Evidence Files",
  followUpFrom: "Follow-up From",
  from: "From",
  fromAgentId: "Previous Agent ID",
  liveChatRequestedAt: "Live Chat Requested",
  message: "Message",
  module: "Module",
  message_count: "Message Count",
  meetingJoinUrl: "Teams Join Link",
  note: "Internal Note",
  queuedAt: "Queued At",
  requested: "Requested",
  requestedDate: "Requested Date",
  requestedTime: "Requested Time",
  requesterEmail: "Requester Email",
  requesterName: "Requester",
  requesterRole: "Requester Role",
  sessionRequestId: "Session Request ID",
  slaAttentionRequired: "SLA Attention Required",
  slaStatus: "SLA Status",
  status: "Status",
  statusReason: "Status Reason",
  technical_subcategory: "Technical Subcategory",
  to: "To",
  toAgentId: "Assigned Agent ID",
  toAgentName: "Assigned Agent",
  fromAgentName: "From Admin",
  fromAgentUsername: "From Username",
  reason: "Transfer Reason",
  replyText: "Reply",
  requestedAt: "Requested At",
  respondedAt: "Responded At",
  sessionDetails: "Session Details",
  sessionCount: "Session Count",
  tutor: "Tutor",
  tutorEmail: "Tutor E-mail",
  targetLabel: "Teams Target",
  toAgentUsername: "To Username",
  webhookDelivered: "Webhook Delivered",
  webhookStatus: "Webhook Status",
};

function getActivityEventLabel(eventType: string) {
  return activityEventLabels[eventType] || humanizeEvent(eventType);
}

function getActivityEventTone(eventType: string) {
  if (eventType === "escalation_closed") {
    return {
      dotClassName: "bg-emerald-500",
      badgeClassName: "border-emerald-200 bg-emerald-50 text-emerald-700",
    };
  }

  if (eventType.includes("failed") || eventType.includes("unavailable")) {
    return {
      dotClassName: "bg-destructive",
      badgeClassName: "border-destructive/20 bg-destructive/10 text-destructive",
    };
  }

  if (eventType.includes("cancelled")) {
    return {
      dotClassName: "bg-slate-400",
      badgeClassName: "border-border bg-secondary text-muted-foreground",
    };
  }

  if (eventType.includes("scheduled") || eventType.includes("created") || eventType.includes("requested")) {
    return {
      dotClassName: "bg-emerald-500",
      badgeClassName: "border-emerald-200 bg-emerald-50 text-emerald-700",
    };
  }

  return {
    dotClassName: "bg-primary",
    badgeClassName: "border-primary/15 bg-primary/8 text-primary",
  };
}

function getActivityEventSummary(item: HistoryItem) {
  const fromValue = getActivityPayloadTextValue(item.payload.from);
  const toValue = getActivityPayloadTextValue(item.payload.to);
  const fromAgentName = getActivityPayloadTextValue(item.payload.fromAgentName);
  const assignedAgentName = getActivityPayloadTextValue(item.payload.toAgentName);
  const closedByName = getActivityPayloadTextValue(item.payload.closedByName);
  const requestedDate = getActivityPayloadTextValue(item.payload.requestedDate);
  const requestedTime = getActivityPayloadTextValue(item.payload.requestedTime);
  const requesterName = getActivityPayloadTextValue(item.payload.requesterName);
  const tutor = getActivityPayloadTextValue(item.payload.tutor);
  const sessionDetails = getActivityPayloadTextValue(item.payload.sessionDetails);

  switch (item.eventType) {
    case "status_changed":
      if (fromValue || toValue) {
        return `Status moved from ${fromValue || "Empty"} to ${toValue || "Empty"}`;
      }
      break;
    case "status_reason_changed":
      if (fromValue || toValue) {
        return `Reason updated from ${fromValue || "Empty"} to ${toValue || "Empty"}`;
      }
      break;
    case "sla_changed":
      if (fromValue || toValue) {
        return `SLA changed from ${fromValue || "Empty"} to ${toValue || "Empty"}`;
      }
      break;
    case "assignment_changed":
      if (assignedAgentName) {
        return `Assigned to ${assignedAgentName}`;
      }
      break;
    case "transfer_requested":
      if (assignedAgentName) {
        return `Transfer requested for ${assignedAgentName}`;
      }
      return "Transfer requested";
    case "escalation_notified":
      if (fromAgentName && assignedAgentName) {
        return `Escalation notice sent from ${fromAgentName} to ${assignedAgentName}`;
      }
      if (assignedAgentName) {
        return `Escalation notice sent to ${assignedAgentName}`;
      }
      return "Escalation notice sent";
    case "teams_call_requested":
      if (requesterName) {
        return `Teams call requested by ${requesterName}`;
      }
      return "Teams call requested";
    case "escalation_closed":
      if (closedByName) {
        return `Escalated ticket closed by ${closedByName}`;
      }
      return "Escalated ticket closed";
    case "transfer_request_accepted":
      if (assignedAgentName) {
        return `Transfer accepted by ${assignedAgentName}`;
      }
      return "Transfer accepted";
    case "transfer_request_rejected":
      if (assignedAgentName) {
        return `Transfer declined by ${assignedAgentName}`;
      }
      return "Transfer declined";
    case "support_session_requested":
      return requestedDate || requestedTime
        ? `Support session requested for ${[requestedDate, requestedTime].filter(Boolean).join(" at ")}`
        : "Support session requested";
    case "coverage_ticket_operations_notified":
      return "Operations team notified about this coverage ticket";
    case "coverage_ticket_operations_notification_failed":
      return "Operations team notification could not be delivered";
    case "coverage_tutor_requested":
      return tutor ? `Tutor request sent to ${tutor}` : "Tutor request sent";
    case "coverage_tutor_response":
      return tutor
        ? `${getActivityPayloadTextValue(item.payload.outcome) === "accepted" ? "Tutor accepted" : "Tutor rejected"}: ${tutor}`
        : "Tutor reply received";
    case "coverage_session_confirmed":
      return tutor ? `Coverage session confirmed with ${tutor}` : "Coverage session confirmed";
    case "internal_note":
      return "Internal note recorded";
    default:
      break;
  }

  return getActivityEventLabel(item.eventType);
}

function getAdminNotificationLogDetail(item: AdminNotificationLogItem) {
  const reason = getActivityPayloadTextValue(item.payload.reason);
  const note = getActivityPayloadTextValue(item.payload.note);
  const closedByName = getActivityPayloadTextValue(item.payload.closedByName);
  const decidedByName = getActivityPayloadTextValue(item.payload.decidedByName);
  const targetAgentName = getActivityPayloadTextValue(item.payload.toAgentName);
  const sessionDetails = getActivityPayloadTextValue(item.payload.sessionDetails);
  const replyText = getActivityPayloadTextValue(item.payload.replyText);

  switch (item.eventType) {
    case "transfer_requested":
      return reason;
    case "escalation_notified":
      return note;
    case "teams_call_requested":
      return note;
    case "escalation_closed":
      if (closedByName && note) {
        return `${closedByName} closed this escalated ticket. Note: ${note}`;
      }
      if (closedByName) {
        return `${closedByName} closed this escalated ticket.`;
      }
      return note;
    case "transfer_request_accepted":
      return targetAgentName ? `Transferred to ${targetAgentName}.` : "Transfer request accepted.";
    case "transfer_request_rejected":
      return decidedByName ? `${decidedByName} declined this transfer request.` : "Transfer request declined.";
    case "coverage_tutor_requested":
      return sessionDetails;
    case "coverage_tutor_response":
      return [sessionDetails, replyText].filter(Boolean).join(" ");
    case "coverage_session_confirmed":
      return getActivityPayloadTextValue(item.payload.confirmedByName)
        ? `Confirmed by ${getActivityPayloadTextValue(item.payload.confirmedByName)}.`
        : "Coverage session confirmed.";
    default:
      return "";
  }
}

function formatActivityActorLabel(item: HistoryItem) {
  const actorLabel = (item.actorLabel || "").trim();
  if (actorLabel) {
    return `Source: ${actorLabel}`;
  }

  return `Source: ${humanizeEvent((item.actorType || "system").replace(/\s+/g, "_"))}`;
}

function buildActivityPayloadEntries(payload: Record<string, unknown>) {
  return Object.entries(payload)
    .filter(([, value]) => hasMeaningfulActivityValue(value))
    .sort(([leftKey], [rightKey]) => getActivityPayloadSortRank(leftKey) - getActivityPayloadSortRank(rightKey))
    .map(([key, value]) => {
      const formattedValue = formatActivityPayloadValue(key, value);
      return formattedValue
        ? {
            key,
            label: activityPayloadLabels[key] || humanizeActivityFieldLabel(key),
            value: formattedValue,
            kind: getActivityPayloadKind(key, formattedValue),
          }
        : null;
    })
    .filter((entry): entry is ActivityPayloadEntry => Boolean(entry));
}

function hasMeaningfulActivityValue(value: unknown) {
  if (value === null || value === undefined) {
    return false;
  }

  if (typeof value === "string") {
    return value.trim().length > 0;
  }

  if (Array.isArray(value)) {
    return value.length > 0;
  }

  if (typeof value === "object") {
    return Object.keys(value as Record<string, unknown>).length > 0;
  }

  return true;
}

function getActivityPayloadSortRank(key: string) {
  const activityPayloadOrder = [
    "from",
    "to",
    "status",
    "statusReason",
    "toAgentName",
    "toAgentId",
    "fromAgentId",
    "category",
    "technical_subcategory",
    "requestedDate",
    "requestedTime",
    "queuedAt",
    "liveChatRequestedAt",
    "sessionRequestId",
    "chatId",
    "meetingJoinUrl",
    "calendarEventId",
    "message",
    "note",
  ];
  const rank = activityPayloadOrder.indexOf(key);
  return rank === -1 ? activityPayloadOrder.length + 1 : rank;
}

function getActivityPayloadTextValue(value: unknown) {
  return typeof value === "string" ? value.trim() : typeof value === "number" ? String(value) : "";
}

function humanizeActivityFieldLabel(value: string) {
  return value
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/_/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatActivityPayloadValue(key: string, value: unknown): string {
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }

  if (typeof value === "number") {
    return String(value);
  }

  if (typeof value === "string") {
    const trimmedValue = value.trim();
    if (!trimmedValue) {
      return "";
    }

    if (looksLikeActivityDateTime(key, trimmedValue)) {
      return formatDateTime(trimmedValue);
    }

    if (looksLikeActivityDateOnly(key, trimmedValue)) {
      return formatDateShort(trimmedValue);
    }

    return trimmedValue;
  }

  if (Array.isArray(value)) {
    return value
      .map((item) => formatActivityPayloadValue(key, item))
      .filter(Boolean)
      .join(", ");
  }

  return JSON.stringify(value, null, 2);
}

function getActivityPayloadKind(key: string, value: string): ActivityPayloadEntryKind {
  if (/^https?:\/\//i.test(value)) {
    return "link";
  }

  if (key === "message" || key === "note" || value.length > 120) {
    return "multiline";
  }

  if (key.toLowerCase().endsWith("id") || value.startsWith("KBC-")) {
    return "mono";
  }

  return "text";
}

function looksLikeActivityDateTime(key: string, value: string) {
  return (
    /^\d{4}-\d{2}-\d{2}t\d{2}:\d{2}/i.test(value)
    || key.toLowerCase().endsWith("at")
  ) && !Number.isNaN(Date.parse(value));
}

function looksLikeActivityDateOnly(key: string, value: string) {
  return key.toLowerCase().endsWith("date")
    && /^\d{4}-\d{2}-\d{2}$/.test(value)
    && !Number.isNaN(Date.parse(value));
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

function getAgentDisplayName(agent: Pick<AdminAgent, "fullName" | "username">) {
  return agent.fullName || agent.username || "Support Agent";
}

function formatKnownRoleLabel(value: string | null | undefined, fallback: string) {
  const normalizedValue = (value || fallback).trim().toLowerCase();
  if (!normalizedValue) {
    return fallback;
  }

  const knownLabels: Record<string, string> = {
    superadmin: "Super Admin",
    admin: "Admin",
    coach: "Coach",
    employer: "Employer",
    user: "User",
    agent: "Agent",
  };

  return knownLabels[normalizedValue] || (normalizedValue.charAt(0).toUpperCase() + normalizedValue.slice(1));
}

function formatAdminRoleLabel(value: string | null | undefined) {
  return formatKnownRoleLabel(value, "Admin");
}

function deriveAccountScopeFromRole(value: string | null | undefined) {
  const normalizedValue = (value || "").trim().toLowerCase();
  if (normalizedValue === "requester" || normalizedValue === "staff") {
    return normalizedValue;
  }
  if (normalizedValue === "user" || normalizedValue === "coach" || normalizedValue === "employer") {
    return "requester";
  }
  return "staff";
}

function formatAccountScopeLabel(value: string | null | undefined) {
  return deriveAccountScopeFromRole(value) === "requester" ? "Support Requester" : "Support Staff";
}

function formatRequesterRoleLabel(value: string | null | undefined) {
  return formatKnownRoleLabel(value, "User");
}

function RequesterRoleBadge({
  role,
  className,
}: {
  role: string | null | undefined;
  className?: string;
}) {
  return (
    <span className={cn(
      "inline-flex items-center rounded-full border border-primary/15 bg-primary/5 px-2.5 py-1 text-[11px] font-medium text-primary",
      className,
    )}>
      {formatRequesterRoleLabel(role)}
    </span>
  );
}

function sortAgentsForDirectory(agents: AdminAgent[]) {
  const rolePriority: Record<string, number> = {
    superadmin: 0,
    admin: 1,
    coach: 2,
    employer: 3,
    agent: 4,
    user: 5,
  };

  return [...agents].sort((leftAgent, rightAgent) => {
    const leftActiveRank = leftAgent.isActive === false ? 1 : 0;
    const rightActiveRank = rightAgent.isActive === false ? 1 : 0;
    if (leftActiveRank !== rightActiveRank) {
      return leftActiveRank - rightActiveRank;
    }

    const leftRoleRank = rolePriority[(leftAgent.role || "").toLowerCase()] ?? 99;
    const rightRoleRank = rolePriority[(rightAgent.role || "").toLowerCase()] ?? 99;
    if (leftRoleRank !== rightRoleRank) {
      return leftRoleRank - rightRoleRank;
    }

    const leftName = (leftAgent.fullName || leftAgent.username || "").toLowerCase();
    const rightName = (rightAgent.fullName || rightAgent.username || "").toLowerCase();
    return leftName.localeCompare(rightName) || (leftAgent.username || "").localeCompare(rightAgent.username || "");
  });
}

function getAssignedAgentAccent(assignedAgentId: number | null, assignedAgentName: string): AssignedAgentAccent {
  if (!assignedAgentId && !sanitizeAssignedAgentName(assignedAgentName)) {
    return {
      badgeClassName: "border-slate-200 bg-slate-50 text-slate-700",
      dotClassName: "bg-slate-400",
      stripeClassName: "bg-slate-300",
    };
  }

  const palettes: AssignedAgentAccent[] = [
    {
      badgeClassName: "border-sky-200 bg-sky-50 text-sky-700",
      dotClassName: "bg-sky-500",
      stripeClassName: "bg-sky-400",
    },
    {
      badgeClassName: "border-emerald-200 bg-emerald-50 text-emerald-700",
      dotClassName: "bg-emerald-500",
      stripeClassName: "bg-emerald-400",
    },
    {
      badgeClassName: "border-amber-200 bg-amber-50 text-amber-700",
      dotClassName: "bg-amber-500",
      stripeClassName: "bg-amber-400",
    },
    {
      badgeClassName: "border-violet-200 bg-violet-50 text-violet-700",
      dotClassName: "bg-violet-500",
      stripeClassName: "bg-violet-400",
    },
    {
      badgeClassName: "border-rose-200 bg-rose-50 text-rose-700",
      dotClassName: "bg-rose-500",
      stripeClassName: "bg-rose-400",
    },
    {
      badgeClassName: "border-cyan-200 bg-cyan-50 text-cyan-700",
      dotClassName: "bg-cyan-500",
      stripeClassName: "bg-cyan-400",
    },
    {
      badgeClassName: "border-orange-200 bg-orange-50 text-orange-700",
      dotClassName: "bg-orange-500",
      stripeClassName: "bg-orange-400",
    },
    {
      badgeClassName: "border-lime-200 bg-lime-50 text-lime-700",
      dotClassName: "bg-lime-500",
      stripeClassName: "bg-lime-400",
    },
  ];

  const normalizedName = sanitizeAssignedAgentName(assignedAgentName);
  const seed = typeof assignedAgentId === "number" && Number.isFinite(assignedAgentId)
    ? assignedAgentId
    : normalizedName.split("").reduce((total, char) => total + char.charCodeAt(0), 0);

  return palettes[Math.abs(seed) % palettes.length];
}

function sanitizeAssignedAgentName(value: string | null | undefined) {
  const normalizedValue = (value || "").trim();
  return normalizedValue && normalizedValue.toLowerCase() !== "unassigned" ? normalizedValue : "";
}

function normalizeAdminSelectableConsoleStatus(value: string | null | undefined): AdminSelectableConsoleStatus {
  return normalizeAdminConsoleStatus(value) === "Off" ? "Off" : "Available";
}

function normalizeAdminConsoleStatus(value: string | null | undefined): AdminConsoleStatus {
  return adminConsoleStatuses.includes(value as AdminConsoleStatus)
    ? (value as AdminConsoleStatus)
    : "Off";
}

function getAgentConsoleStatusRank(status: AdminConsoleStatus) {
  if (status === "Available") return 0;
  if (status === "Busy") return 1;
  return 2;
}

function presenceDotClassName(status: AdminConsoleStatus) {
  if (status === "Busy") return "bg-amber-500";
  if (status === "Off") return "bg-slate-400";
  return "bg-emerald-500";
}

function consoleStatusBadgeClassName(status: AdminConsoleStatus) {
  if (status === "Busy") return "border-amber-200 bg-amber-50 text-amber-700";
  if (status === "Off") return "border-slate-200 bg-slate-100 text-slate-600";
  return "border-emerald-200 bg-emerald-50 text-emerald-700";
}

function consoleStatusTextClassName(status: AdminConsoleStatus) {
  if (status === "Busy") return "text-amber-700";
  if (status === "Off") return "text-slate-600";
  return "text-emerald-700";
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
  if (value === "Breached") return "inline-flex items-center rounded-full bg-rose-600 px-2.5 py-1 text-white";
  if (value === "On Track") return "text-success";
  return "text-warning";
}

export default AgentDashboard;
