import { useEffect, useRef, useState, type ChangeEvent, type MouseEvent as ReactMouseEvent, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  Bot,
  AlertOctagon,
  ArrowLeft,
  Bell,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  Eye,
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
  Phone,
  RefreshCw,
  Search,
  Save,
  SendHorizontal,
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
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { SupportLayout } from "@/components/support/SupportLayout";
import { StatusBadge } from "@/components/support/StatusBadge";
import { clearAdminSession, getAdminSession, setAdminSession, setAdminSessionOnWindow } from "@/lib/adminSession";
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
  latestEscalationClosure?: LatestEscalationClosure | null;
  latestTransferDecision?: LatestTransferDecision | null;
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
const accountDirectoryPollIntervalMs = 15000;
const documentationWorkflowStatuses = ["Closed", "Pending"] as const;
const defaultPendingDocumentationStatusReason = "Awaiting resolution";
const documentationStatusReasons = {
  Closed: ["Closed due to inactivity", "Closed via Chatbot", "Closed via Agent"],
  Pending: [defaultPendingDocumentationStatusReason, "Awaiting support meeting", "Escalation", "Quick Ticket"],
} as const;
const adminAccountRoleOptions = [
  { value: "superadmin", label: "Super Admin" },
  { value: "admin", label: "Admin" },
] as const;
const requesterAccountRoleOptions = [
  { value: "coach", label: "Coach" },
  { value: "employer", label: "Employer" },
  { value: "user", label: "User" },
] as const;
const adminDirectoryRoles = new Set<string>(["admin", "superadmin"]);
const requesterDirectoryRoles = new Set<string>(["user", "coach", "employer"]);
const userManagementRoles = new Set<string>(["admin", "superadmin"]);
type AdminConsoleStatus = (typeof adminConsoleStatuses)[number];
type AdminSelectableConsoleStatus = (typeof adminSelectableConsoleStatuses)[number];
type DocumentationWorkflowStatus = (typeof documentationWorkflowStatuses)[number];
type DocumentationIssuesAddressed = "yes" | "no" | "";
type DashboardTicketFilter = "all" | "open" | "pending" | "closed" | "slaBreached" | "quickResolution" | "escalation";
type DashboardSortOrder = "newest" | "oldest" | "priorityDesc" | "priorityAsc";
type DashboardAssignedFilter = "all" | "me" | "unassigned" | `agent:${number}`;
type AdminView = "dashboard" | "console" | "users" | "requesters";
type TicketDetailTab = "conversation" | "documentation" | "details";
type UserStatusFilter = "all" | "active" | "inactive";
type ManagedAccountScope = "staff" | "requester";

interface UserEditorState {
  id: number | null;
  username: string;
  fullName: string;
  email: string;
  role: string;
  password: string;
  isActive: boolean;
}

function createEmptyUserEditorState(scope: ManagedAccountScope = "staff"): UserEditorState {
  return {
    id: null,
    username: "",
    fullName: "",
    email: "",
    role: scope === "requester" ? "user" : "admin",
    password: "",
    isActive: true,
  };
}

const AgentDashboard = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const session = getAdminSession();
  const initialConsoleDeepLink = parseAdminDeepLink(location.search);
  const isMountedRef = useRef(true);
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
  const [dashboardAssignedFilter, setDashboardAssignedFilter] = useState<DashboardAssignedFilter>(() => (
    (session?.role || "").toLowerCase() === "superadmin"
      ? "all"
      : session?.id
        ? "me"
        : "all"
  ));
  const [dashboardSearch, setDashboardSearch] = useState("");
  const [documentationDraft, setDocumentationDraft] = useState<AdminDocumentation | null>(null);
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
  const [isSaving, setIsSaving] = useState(false);
  const [isSavingUser, setIsSavingUser] = useState(false);
  const [isUpdatingConsoleStatus, setIsUpdatingConsoleStatus] = useState(false);
  const [isUserEditorOpen, setIsUserEditorOpen] = useState(false);
  const [userStatusFilter, setUserStatusFilter] = useState<UserStatusFilter>("all");
  const [userRoleFilter, setUserRoleFilter] = useState<string>("all");
  const [userSearch, setUserSearch] = useState("");
  const [requesterStatusFilter, setRequesterStatusFilter] = useState<UserStatusFilter>("all");
  const [requesterRoleFilter, setRequesterRoleFilter] = useState<string>("all");
  const [requesterSearch, setRequesterSearch] = useState("");
  const [userEditorScope, setUserEditorScope] = useState<ManagedAccountScope>("staff");
  const [userEditor, setUserEditor] = useState<UserEditorState>(() => createEmptyUserEditorState());
  const [error, setError] = useState("");
  const [chatbotWorkflowConfigured, setChatbotWorkflowConfigured] = useState(false);
  const [consoleTimerNow, setConsoleTimerNow] = useState(() => Date.now());
  const [notificationLog, setNotificationLog] = useState<AdminNotificationLogItem[]>([]);
  const seenTransferNotificationKeysRef = useRef<Set<string>>(new Set());
  const hasHydratedTransferNotificationsRef = useRef(false);
  const canManageUsers = userManagementRoles.has((session?.role || "").toLowerCase());
  const isSuperadminSession = (session?.role || "").toLowerCase() === "superadmin";
  const isConsoleView = adminView === "console";
  const useCompactAdminSidebar = !isStackedAdminLayout && isAdminSidebarCollapsed;
  const userEditorRoleOptions = userEditorScope === "requester" ? requesterAccountRoleOptions : adminAccountRoleOptions;
  const userEditorEntityLabel = userEditorScope === "requester" ? "Requester" : "Admin";
  const trimmedNotes = notes.trim();
  const dashboardSessionAgentId = session?.id ?? null;
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
  const activeAgents = agents.filter((agent) => agent.isActive !== false && isStaffSupportAccount(agent));
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
      return ticket.assignedAgentId === session?.id;
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
  const searchMatchedConsoleTickets = scopedConsoleTickets.filter((ticket) => {
    if (!normalizedConsoleSearch) {
      return true;
    }

    const searchableFields = [
      ticket.id,
      ticket.chatId,
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

    return ticket.assignedAgentId === session?.id;
  });
  const myOpenChatCount = myOpenConsoleQueueTickets.length;
  // Keep admin availability tied to the signed-in admin's own live queue.
  // The All Cases tab may still surface other admins' chats for review.
  const hasCurrentAdminOpenConsoleQueue = myOpenConsoleQueueTickets.length > 0;
  const myOpenChatCardToneClassName = myOpenChatCount === 0
    ? "border-emerald-200 bg-emerald-50/90"
    : "border-red-200 bg-red-50/90";
  const signedInAgent = agents.find((agent) => (
    (session?.id && agent.id === session.id)
    || (session?.username && agent.username === session.username)
  ));
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
    ...(dashboardSessionAgentId ? [{ value: "me" as DashboardAssignedFilter, label: "Me" }] : []),
    { value: "all" as DashboardAssignedFilter, label: "All Tickets" },
    { value: "unassigned" as DashboardAssignedFilter, label: "Unassigned" },
    ...sortedAgents
      .filter((agent) => agent.id !== dashboardSessionAgentId)
      .map((agent) => ({
        value: buildDashboardAssignedAgentFilterValue(agent.id),
        label: getAgentDisplayName(agent),
      })),
  ];
  const normalizedUserSearch = normalizeConsoleSearchValue(userSearch);
  const normalizedRequesterSearch = normalizeConsoleSearchValue(requesterSearch);
  const managedAdminUsers = agents.filter((agent) => adminDirectoryRoles.has((agent.role || "").toLowerCase()));
  const managedRequesterUsers = agents.filter((agent) => requesterDirectoryRoles.has((agent.role || "").toLowerCase()));
  const activeManagedAdminUsers = managedAdminUsers.filter((agent) => agent.isActive !== false);
  const activeManagedRequesterUsers = managedRequesterUsers.filter((agent) => agent.isActive !== false);
  const assignableAdminAgents = sortedAgents.filter((agent) => (agent.role || "").toLowerCase() === "admin");
  const filteredUsers = managedAdminUsers.filter((agent) => {
    const matchesStatus = userStatusFilter === "all"
      ? true
      : userStatusFilter === "active"
        ? agent.isActive !== false
        : agent.isActive === false;
    const matchesRole = userRoleFilter === "all" ? true : agent.role === userRoleFilter;
    const searchableFields = [
      agent.fullName,
      agent.username,
      agent.email || "",
      formatAccountScopeLabel(agent.accountScope || agent.role),
      formatAdminRoleLabel(agent.role),
    ];
    const matchesSearch = !normalizedUserSearch || searchableFields.some((fieldValue) => (
      normalizeConsoleSearchValue(fieldValue).includes(normalizedUserSearch)
    ));

    return matchesStatus && matchesRole && matchesSearch;
  });
  const filteredRequesters = managedRequesterUsers.filter((agent) => {
    const matchesStatus = requesterStatusFilter === "all"
      ? true
      : requesterStatusFilter === "active"
        ? agent.isActive !== false
        : agent.isActive === false;
    const matchesRole = requesterRoleFilter === "all" ? true : agent.role === requesterRoleFilter;
    const searchableFields = [
      agent.fullName,
      agent.username,
      agent.email || "",
      formatAccountScopeLabel(agent.accountScope || agent.role),
      formatRequesterRoleLabel(agent.role),
    ];
    const matchesSearch = !normalizedRequesterSearch || searchableFields.some((fieldValue) => (
      normalizeConsoleSearchValue(fieldValue).includes(normalizedRequesterSearch)
    ));

    return matchesStatus && matchesRole && matchesSearch;
  });
  const dashboardAssignmentScopedTickets = filterDashboardTicketsByAssignee(
    tickets,
    dashboardAssignedFilter,
    dashboardSessionAgentId,
  );
  const quickResolutionTickets = dashboardAssignmentScopedTickets.filter(isQuickResolutionTicket);
  const scopedDashboardTickets = filterDashboardTickets(dashboardAssignmentScopedTickets, dashboardTicketFilter);
  const visibleDashboardTickets = [...scopedDashboardTickets]
    .filter((ticket) => {
      if (!normalizedDashboardSearch) {
        return true;
      }

      const searchableFields = [
        ticket.chatId,
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
  const dashboardTableTitle = getDashboardTableTitle(dashboardTicketFilter);
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
    tickets.length,
    Boolean(normalizedDashboardSearch),
    dashboardAssignedFilter !== "all",
    dashboardAssignedFilterLabel,
  );
  const dashboardEmptyMessage = normalizedDashboardSearch
    ? "No matching tickets found for this search."
    : dashboardAssignedFilter !== "all"
      ? getDashboardAssignedFilterEmptyMessage(dashboardTicketFilter, dashboardAssignedFilterEmptyTarget)
      : getDashboardEmptyMessage(dashboardTicketFilter);
  const isConsoleOwnedBySignedInAgent = Boolean(consoleDetail && session?.id && consoleDetail.ticket.assignedAgentId === session.id);
  const canAssignActiveTicket = Boolean(
    isSuperadminSession
    && activeDetail
    && !activeDetail.ticket.assignedAgentId,
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

      if (session?.id) {
        return pendingTransferRequest.toAgentId === session.id;
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

      if (session?.id) {
        return pendingEscalationNotification.toAgentId === session.id;
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

      if (session?.id) {
        return pendingTeamsCallNotification.toAgentId === session.id;
      }

      return sanitizeAssignedAgentName(pendingTeamsCallNotification.toAgentUsername) === sanitizeAssignedAgentName(session?.username || "");
    })
    .sort((leftTicket, rightTicket) => {
      const leftRequestedAt = Date.parse(leftTicket.pendingTeamsCallNotification?.requestedAt || "");
      const rightRequestedAt = Date.parse(rightTicket.pendingTeamsCallNotification?.requestedAt || "");
      return (Number.isNaN(rightRequestedAt) ? 0 : rightRequestedAt) - (Number.isNaN(leftRequestedAt) ? 0 : leftRequestedAt);
    });
  const transferDecisionNotifications = tickets
    .filter((ticket) => {
      const latestTransferDecision = ticket.latestTransferDecision;
      if (!latestTransferDecision || latestTransferDecision.requesterAcknowledged) {
        return false;
      }

      if (session?.id) {
        return latestTransferDecision.fromAgentId === session.id;
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

      if (session?.id) {
        return latestEscalationClosure.fromAgentId === session.id;
      }

      return sanitizeAssignedAgentName(latestEscalationClosure.fromAgentUsername) === sanitizeAssignedAgentName(session?.username || "");
    })
    .sort((leftTicket, rightTicket) => {
      const leftClosedAt = Date.parse(leftTicket.latestEscalationClosure?.closedAt || "");
      const rightClosedAt = Date.parse(rightTicket.latestEscalationClosure?.closedAt || "");
      return (Number.isNaN(rightClosedAt) ? 0 : rightClosedAt) - (Number.isNaN(leftClosedAt) ? 0 : leftClosedAt);
    });
  const totalAdminNotificationCount = pendingTransferRequests.length
    + pendingEscalationNotifications.length
    + pendingTeamsCallNotifications.length
    + transferDecisionNotifications.length
    + escalationClosureNotifications.length;
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
    && session?.id
    && consoleDetail.ticket.assignedAgentId === session.id
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

  function isCurrentDashboardSession() {
    if (!isMountedRef.current) {
      return false;
    }

    if (!session?.username || !session.instanceId) {
      return true;
    }

    const currentSession = getAdminSession();
    return Boolean(
      currentSession
      && currentSession.username === session.username
      && currentSession.instanceId === session.instanceId
    );
  }

  useEffect(() => {
    void loadDashboard();
  }, []);

  useEffect(() => {
    if (!session?.username || !session.instanceId || !consoleStatus) {
      return;
    }

    setAdminSession({
      ...session,
      consoleStatus,
    });
  }, [consoleStatus, session?.email, session?.fullName, session?.id, session?.instanceId, session?.role, session?.username]);

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
    if (adminView !== "dashboard") {
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
  }, [adminView]);

  useEffect(() => {
    if (adminView !== "users" && adminView !== "requesters") {
      return;
    }

    const intervalId = window.setInterval(() => {
      void refreshAgentsOnly(true);
    }, accountDirectoryPollIntervalMs);

    return () => window.clearInterval(intervalId);
  }, [adminView]);

  useEffect(() => {
    if (!canManageUsers && (adminView === "users" || adminView === "requesters")) {
      setAdminView("dashboard");
    }
  }, [adminView, canManageUsers]);

  useEffect(() => {
    const nextNotificationKeys = new Set<string>();
    const newTransferRequests: TicketSummary[] = [];
    const newEscalationNotifications: TicketSummary[] = [];
    const newTeamsCallNotifications: TicketSummary[] = [];
    const newTransferDecisions: TicketSummary[] = [];
    const newEscalationClosures: TicketSummary[] = [];

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

    if (!hasHydratedTransferNotificationsRef.current) {
      seenTransferNotificationKeysRef.current = nextNotificationKeys;
      hasHydratedTransferNotificationsRef.current = true;
      return;
    }

    for (const ticket of newTransferRequests) {
      const pendingTransferRequest = ticket.pendingTransferRequest;
      if (!pendingTransferRequest) {
        continue;
      }

      toast.info(`New transfer request for ${ticket.id} from ${pendingTransferRequest.fromAgentName}.`);
    }

    for (const ticket of newEscalationNotifications) {
      const pendingEscalationNotification = ticket.pendingEscalationNotification;
      if (!pendingEscalationNotification) {
        continue;
      }

      toast.info(`Escalation notice received for ${pendingEscalationNotification.ticketId} from ${pendingEscalationNotification.fromAgentName}.`);
    }

    for (const ticket of newTeamsCallNotifications) {
      const pendingTeamsCallNotification = ticket.pendingTeamsCallNotification;
      if (!pendingTeamsCallNotification) {
        continue;
      }

      toast.info(
        `Teams call request received for ${pendingTeamsCallNotification.ticketId} from ${pendingTeamsCallNotification.requesterName}.`,
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
    }

    for (const ticket of newEscalationClosures) {
      const latestEscalationClosure = ticket.latestEscalationClosure;
      if (!latestEscalationClosure) {
        continue;
      }

      toast.info(`Escalated ticket ${latestEscalationClosure.ticketId} was closed by ${latestEscalationClosure.closedByName}.`);
    }

    if (
      newTransferRequests.length > 0
      || newEscalationNotifications.length > 0
      || newTeamsCallNotifications.length > 0
      || newTransferDecisions.length > 0
      || newEscalationClosures.length > 0
    ) {
      playTransferNotificationSound();
    }

    seenTransferNotificationKeysRef.current = nextNotificationKeys;
  }, [escalationClosureNotifications, pendingEscalationNotifications, pendingTeamsCallNotifications, pendingTransferRequests, transferDecisionNotifications]);

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
  ];

  async function fetchTicketsList() {
    const response = await fetch("/api/admin/tickets");
    const payload = (await response.json().catch(() => null)) as ListResponse | null;

    if (!response.ok) {
      throw new Error(payload?.message || "We could not load tickets right now.");
    }

    return payload?.tickets || [];
  }

  function buildAdminSessionQuery() {
    if (!session?.username || !session.instanceId) {
      throw new Error("Admin session is required.");
    }

    const searchParams = new URLSearchParams();
    searchParams.set("actorUsername", session.username);
    searchParams.set("instanceId", session.instanceId);
    return searchParams.toString();
  }

  async function fetchAgentsList() {
    const response = await fetch(`/api/admin/accounts?${buildAdminSessionQuery()}`);
    const payload = (await response.json().catch(() => null)) as ListResponse | null;

    if (!response.ok) {
      throw new Error(payload?.message || "We could not load support accounts right now.");
    }

    return payload?.accounts || payload?.agents || [];
  }

  async function fetchNotificationLog() {
    if (!session?.username || !session.instanceId) {
      return [];
    }

    const response = await fetch(`/api/admin/notifications?${buildAdminSessionQuery()}&limit=20`);
    const payload = (await response.json().catch(() => null)) as NotificationLogResponse | null;

    if (!response.ok) {
      throw new Error(payload?.message || "We could not load the notification log right now.");
    }

    return payload?.notifications || [];
  }

  function openCreateUserEditor(scope: ManagedAccountScope) {
    setUserEditorScope(scope);
    setUserEditor(createEmptyUserEditorState(scope));
    setIsUserEditorOpen(true);
  }

  function openEditUserEditor(agent: AdminAgent) {
    const nextScope = deriveAccountScopeFromRole(agent.accountScope || agent.role);
    setUserEditorScope(nextScope);
    setUserEditor({
      id: agent.id,
      username: agent.username,
      fullName: agent.fullName,
      email: agent.email || "",
      role: agent.role || "user",
      password: "",
      isActive: agent.isActive !== false,
    });
    setIsUserEditorOpen(true);
  }

  function syncSessionFromManagedUser(agent: AdminAgent) {
    if (!session || session.id !== agent.id) {
      return;
    }

    setAdminSession({
      ...session,
      username: agent.username,
      fullName: agent.fullName,
      email: agent.email,
      role: agent.role,
    });
  }

  async function saveManagedUser() {
    if (!session?.username || !session.instanceId) {
      toast.error("Admin session is required.");
      return;
    }

    setIsSavingUser(true);

    try {
      const payload = {
        actorUsername: session.username,
        instanceId: session.instanceId,
        username: userEditor.username,
        fullName: userEditor.fullName,
        email: userEditor.email,
        role: userEditor.role,
        password: userEditor.password,
        isActive: userEditor.isActive,
      };
      const isEditingUser = Boolean(userEditor.id);
      const response = await fetch(
        isEditingUser
          ? `/api/admin/accounts/${encodeURIComponent(String(userEditor.id))}`
          : "/api/admin/accounts",
        {
          method: isEditingUser ? "PATCH" : "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(payload),
        },
      );
      const responsePayload = (await response.json().catch(() => null)) as ListResponse | null;
      const savedAccount = responsePayload?.account || responsePayload?.agent;

      if (!response.ok || !savedAccount) {
        throw new Error(responsePayload?.message || "We could not save this account right now.");
      }

      setAgents((currentAgents) => sortAgentsForDirectory([
        ...currentAgents.filter((agent) => agent.id !== savedAccount.id),
        savedAccount,
      ]));
      syncSessionFromManagedUser(savedAccount);
      setIsUserEditorOpen(false);
      setUserEditor(createEmptyUserEditorState(userEditorScope));
      toast.success(responsePayload.message || (isEditingUser ? "Account updated." : "Account created."));
      if (!userManagementRoles.has((savedAccount.role || "").toLowerCase()) && session.id === savedAccount.id) {
        setAdminView("dashboard");
      }
    } catch (saveError) {
      toast.error(saveError instanceof Error ? saveError.message : "We could not save this account right now.");
    } finally {
      setIsSavingUser(false);
    }
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
    setAdminSession({
      ...(session || {}),
      id: session?.id || signedInAgent.id,
      username: session?.username || signedInAgent.username,
      fullName: session?.fullName || signedInAgent.fullName,
      email: session?.email ?? signedInAgent.email,
      role: session?.role || signedInAgent.role,
      instanceId: session?.instanceId || "",
      consoleStatus: nextStatus,
    });
  }

  async function loadDashboard() {
    setIsLoading(true);
    setError("");

    try {
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
      setAgents(nextAgents);
      setNotificationLog(nextNotificationLog);
      syncConsoleStatusFromAgents(nextAgents);
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
    } catch (fetchError) {
      if (!silent) {
        setError(fetchError instanceof Error ? fetchError.message : "We could not load tickets right now.");
      }
    }
  }

  async function refreshAgentsOnly(silent = false) {
    try {
      const nextAgents = await fetchAgentsList();
      if (!isCurrentDashboardSession()) {
        return;
      }
      setAgents(nextAgents);
      syncConsoleStatusFromAgents(nextAgents);
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
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          actorUsername: session.username,
          instanceId: session.instanceId,
          consoleStatus: statusOverride || consoleStatus,
        }),
      });

      const payload = (await response.json().catch(() => null)) as AdminSessionHeartbeatResponse | null;
      const currentSession = getAdminSession();

      if (
        !currentSession
        || currentSession.instanceId !== session.instanceId
        || currentSession.username !== session.username
      ) {
        return false;
      }

      if (payload?.sessionReplaced) {
        clearAdminSession();
        toast.error("This support session was replaced by another sign-in. Please sign in again.");
        navigate("/admin/login");
        return false;
      }

      if (payload?.sessionActive === false) {
        clearAdminSession();
        toast.error("Your admin session ended. Please sign in again.");
        navigate("/admin/login");
        return false;
      }

      if (!response.ok && !silent) {
        toast.error(payload?.message || "We could not refresh the agent session right now.");
      }

      if (response.ok) {
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

  async function fetchTicketDetail(ticketId: string) {
    const response = await fetch(`/api/admin/tickets/${encodeURIComponent(ticketId)}`);
    const payload = (await response.json().catch(() => null)) as DetailResponse | null;

    if (!response.ok || !payload?.ticket) {
      throw new Error(payload?.message || "We could not load this ticket right now.");
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
      const payload = await fetchTicketDetail(ticketId);
      if (shouldRouteConsoleChatToMyOpenQueue({
        currentScope: consoleCaseScope,
        currentQueueTab: consoleQueueTab,
        ticket: payload.ticket,
        sessionAgentId: session?.id,
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

    if (nextConsoleDeepLink.view === "users") {
      if (canManageUsers) {
        processedConsoleDeepLinkRef.current = location.search;
        setAdminView("users");
      }
      return;
    }

    if (nextConsoleDeepLink.view === "requesters") {
      if (canManageUsers) {
        processedConsoleDeepLinkRef.current = location.search;
        setAdminView("requesters");
      }
      return;
    }

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
  }, [canManageUsers, isLoading, location.search]);

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
    if (!consoleDetail || !documentationDraft || consoleWorkspaceReadOnly) {
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
        headers: {
          "Content-Type": "application/json",
        },
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
          actorUsername: session?.username || "admin",
        }),
      });

      const payload = (await response.json().catch(() => null)) as DetailResponse | null;

      if (!response.ok || !payload?.ticket) {
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
      const response = await fetch(`/api/tickets/${encodeURIComponent(consoleDetail.ticket.id)}/chat-history`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          status: consoleDetail.ticket.status,
          statusReason: consoleDetail.ticket.statusReason,
          actorUsername: session?.username || "",
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

  async function handleForceCloseConsoleChat() {
    if (!consoleDetail || !canForceCloseConsoleChat || isForceClosingConsoleChat) {
      return;
    }

    setIsForceClosingConsoleChat(true);

    try {
      const response = await fetch(`/api/admin/tickets/${encodeURIComponent(consoleDetail.ticket.id)}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          chatState: "closed",
          actorUsername: session?.username || "admin",
        }),
      });

      const payload = (await response.json().catch(() => null)) as DetailResponse | null;

      if (!response.ok || !payload?.ticket) {
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
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          targetAgentId: agent.id,
          reason: trimmedTransferReason,
          actorUsername: session?.username || "admin",
        }),
      });

      const payload = (await response.json().catch(() => null)) as DetailResponse | null;

      if (!response.ok || !payload?.ticket) {
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

    setActiveTransferRequestTicketId(ticket.id);

    try {
      const response = await fetch(
        `/api/admin/tickets/${encodeURIComponent(ticket.id)}/transfer-request/${action}`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            actorUsername: session.username,
          }),
        },
      );

      const payload = (await response.json().catch(() => null)) as DetailResponse | null;

      if (!response.ok || !payload?.ticket) {
        toast.error(payload?.message || `We could not ${action} this transfer request right now.`);
        return;
      }

      syncDetailAcrossViews(payload);
      if (activeDetail?.ticket.id === ticket.id) {
        syncDrafts(payload);
      }
      await refreshTicketsOnly(true);

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
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            actorUsername: session.username,
          }),
        },
      );

      const payload = (await response.json().catch(() => null)) as DetailResponse | null;

      if (!response.ok || !payload?.ticket) {
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
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            actorUsername: session.username,
          }),
        },
      );

      const payload = (await response.json().catch(() => null)) as DetailResponse | null;

      if (!response.ok || !payload?.ticket) {
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
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            actorUsername: session.username,
          }),
        },
      );

      const payload = (await response.json().catch(() => null)) as DetailResponse | null;

      if (!response.ok || !payload?.ticket) {
        if (response.status === 409) {
          setIsTransferNotificationsOpen(false);
          await openTicket(ticket.id, "documentation");
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
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            actorUsername: session.username,
          }),
        },
      );

      const payload = (await response.json().catch(() => null)) as DetailResponse | null;

      if (!response.ok || !payload?.ticket) {
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
    setActiveTicketTab("conversation");
    setActiveDetail(null);
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

    setAdminSession({
      ...session,
      consoleStatus: nextStatus,
    });

    const synced = await syncAgentSessionHeartbeat(false, nextStatus);
    if (synced) {
      setIsUpdatingConsoleStatus(false);
      return;
    }

    pendingConsoleStatusRef.current = null;
    setIsUpdatingConsoleStatus(false);
    setConsoleStatus(previousStatus);
    void refreshAgentsOnly(true);
    setAdminSession({
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
        actorUsername: session?.username || "admin",
      };

      if (canAssignActiveTicket) {
        requestBody.assignedAgentId = draftAgentId === "unassigned" ? null : Number(draftAgentId);
      }

      const response = await fetch(`/api/admin/tickets/${encodeURIComponent(activeDetail.ticket.id)}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(requestBody),
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
    <SupportLayout
      fullWidth
      showHeader={!isConsoleView}
      right={!isConsoleView && canManageUsers ? (
        <>
          <Link
            to="/admin?view=requesters"
            className={cn(
              "inline-flex items-center gap-2 whitespace-nowrap rounded-full border px-3.5 py-2 text-[13px] font-medium shadow-soft transition-all sm:text-sm",
              adminView === "requesters"
                ? "border-primary/18 bg-primary/6 text-primary hover:border-primary/30 hover:bg-primary/10"
                : "border-primary/12 bg-white text-foreground hover:border-primary/25 hover:bg-primary/5 hover:text-primary",
            )}
          >
            <UserRound className="h-4 w-4 text-primary" />
            Requesters
          </Link>
          <Link
            to="/admin?view=users"
            className={cn(
              "inline-flex items-center gap-2 whitespace-nowrap rounded-full border px-3.5 py-2 text-[13px] font-medium shadow-soft transition-all sm:text-sm",
              adminView === "users"
                ? "border-primary/18 bg-primary/6 text-primary hover:border-primary/30 hover:bg-primary/10"
                : "border-primary/12 bg-white text-foreground hover:border-primary/25 hover:bg-primary/5 hover:text-primary",
            )}
          >
            <Users className="h-4 w-4 text-primary" />
            <span className="sm:hidden">Admins</span>
            <span className="hidden sm:inline">Admin Management</span>
          </Link>
        </>
      ) : undefined}
      mainClassName={isConsoleView ? "h-[100dvh] px-0 py-0 md:px-0 md:py-0" : undefined}
    >
      <Tabs
        value={adminView}
        onValueChange={(value) => {
          const nextView = value as AdminView;
          setAdminView(nextView);
          if (nextView !== "dashboard") {
            closePanel();
          }
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
                        requests={pendingTransferRequests}
                        escalations={pendingEscalationNotifications}
                        teamsCalls={pendingTeamsCallNotifications}
                        escalationUpdates={escalationClosureNotifications}
                        decisionUpdates={transferDecisionNotifications}
                        notificationLog={archivedNotificationLog}
                        activeTicketId={activeTransferRequestTicketId}
                        onDecision={handleTransferRequestDecision}
                        onOpenTeamsCall={handleTeamsCallNotificationOpen}
                        onAcknowledgeEscalation={handleEscalationNotificationAcknowledge}
                        onAcknowledgeEscalationUpdate={handleEscalationClosureAcknowledge}
                        onAcknowledgeDecision={handleTransferDecisionAcknowledge}
                        onOpenTicket={openNotificationLogTicket}
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
                        requests={pendingTransferRequests}
                        escalations={pendingEscalationNotifications}
                        teamsCalls={pendingTeamsCallNotifications}
                        escalationUpdates={escalationClosureNotifications}
                        decisionUpdates={transferDecisionNotifications}
                        notificationLog={archivedNotificationLog}
                        activeTicketId={activeTransferRequestTicketId}
                        onDecision={handleTransferRequestDecision}
                        onOpenTeamsCall={handleTeamsCallNotificationOpen}
                        onAcknowledgeEscalation={handleEscalationNotificationAcknowledge}
                        onAcknowledgeEscalationUpdate={handleEscalationClosureAcknowledge}
                        onAcknowledgeDecision={handleTransferDecisionAcknowledge}
                        onOpenTicket={openNotificationLogTicket}
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
                  value="console"
                  className={cn(
                    "h-12 rounded-2xl border bg-background px-3 text-sm font-medium data-[state=active]:border-primary data-[state=active]:bg-primary/8 data-[state=active]:text-primary",
                    useCompactAdminSidebar ? "w-12 justify-center px-0" : "justify-start gap-3",
                  )}
                >
                  <MessageSquareText className="h-4 w-4 shrink-0" />
                  {!useCompactAdminSidebar ? <span>Chat Console</span> : null}
                </TabsTrigger>
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
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-6">
              {kpis.map((kpi) => (
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
                        {["Chat ID", "Ticket ID", "Learner", "Category", "Status", "Status Reason", "Assigned Agent", "Created", "SLA", "Action"].map((heading) => (
                          <th key={heading} className="px-4 py-3 font-medium whitespace-nowrap">{heading}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {visibleDashboardTickets.map((ticket) => (
                        <tr
                          key={ticket.id}
                          className={cn(
                            "transition-colors",
                            getTicketTransferRowClassName(ticket),
                          )}
                        >
                          <td className="px-4 py-3 font-mono font-medium whitespace-nowrap">{ticket.chatId || "-"}</td>
                          <td className="px-4 py-3 font-mono font-medium whitespace-nowrap">{ticket.id}</td>
                          <td className="px-4 py-3 min-w-[240px]">
                            <div className="font-medium">{ticket.learnerName || "Learner"}</div>
                            <div className="text-xs text-muted-foreground">{ticket.email}</div>
                            <div className="mt-2">
                              <RequesterRoleBadge role={ticket.requesterRole} />
                            </div>
                          </td>
                          <td className="px-4 py-3">{formatCategoryLabel(ticket.category, ticket.technicalSubcategory)}</td>
                          <td className="px-4 py-3"><StatusBadge status={ticket.status} /></td>
                          <td className="px-4 py-3 text-muted-foreground">{ticket.statusReason || "-"}</td>
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

          <TabsContent value="users" className="mt-0 min-h-0 w-full flex-1 overflow-y-auto pr-1">
            <div className="space-y-6">
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                <div className="rounded-2xl border bg-card p-5 shadow-soft">
                  <div className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Total Admins</div>
                  <div className="mt-3 text-3xl font-bold text-foreground">{managedAdminUsers.length}</div>
                  <div className="mt-2 text-sm text-muted-foreground">Admin and superadmin accounts visible in this directory.</div>
                </div>
                <div className="rounded-2xl border bg-card p-5 shadow-soft">
                  <div className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Active</div>
                  <div className="mt-3 text-3xl font-bold text-emerald-700">{activeManagedAdminUsers.length}</div>
                  <div className="mt-2 text-sm text-muted-foreground">Admin accounts that can still sign in.</div>
                </div>
                <div className="rounded-2xl border bg-card p-5 shadow-soft">
                  <div className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Inactive</div>
                  <div className="mt-3 text-3xl font-bold text-slate-600">{managedAdminUsers.length - activeManagedAdminUsers.length}</div>
                  <div className="mt-2 text-sm text-muted-foreground">Admin accounts disabled from the admin login.</div>
                </div>
              </div>

              <div className="rounded-3xl border bg-card shadow-card">
                <div className="border-b px-4 py-4 sm:px-5">
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
                    <div>
                      <h2 className="text-lg font-semibold text-foreground">Admin Management</h2>
                      <p className="mt-1 text-sm text-muted-foreground">
                        Review admin and superadmin accounts, reset passwords, and control dashboard access from one place.
                      </p>
                    </div>
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                      <div className="relative w-full sm:w-[280px]">
                        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                        <Input
                          value={userSearch}
                          onChange={(event) => setUserSearch(event.target.value)}
                          placeholder="Search by name, username, or email"
                          className="pl-10"
                        />
                      </div>
                      <div className="w-full sm:w-[170px]">
                        <Select value={userRoleFilter} onValueChange={setUserRoleFilter}>
                          <SelectTrigger>
                            <SelectValue placeholder="Role" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="all">All Roles</SelectItem>
                            {adminAccountRoleOptions.map((roleOption) => (
                              <SelectItem key={roleOption.value} value={roleOption.value}>{roleOption.label}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="w-full sm:w-[170px]">
                        <Select value={userStatusFilter} onValueChange={(value) => setUserStatusFilter(value as UserStatusFilter)}>
                          <SelectTrigger>
                            <SelectValue placeholder="Status" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="all">All Statuses</SelectItem>
                            <SelectItem value="active">Active</SelectItem>
                            <SelectItem value="inactive">Inactive</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <Button onClick={() => openCreateUserEditor("staff")} className="w-full gap-2 gradient-primary sm:w-auto">
                        <UserPlus className="h-4 w-4" />
                        Add Admin
                      </Button>
                    </div>
                  </div>
                </div>

                {error && adminView === "users" ? (
                  <div className="border-b border-destructive/10 bg-destructive/5 px-5 py-3 text-sm text-destructive">
                    {error}
                  </div>
                ) : null}

                <div className="p-4 sm:p-5">
                  {isLoading ? (
                    <div className="flex items-center justify-center gap-2 rounded-2xl border border-dashed p-10 text-sm text-muted-foreground">
                      <LoaderCircle className="h-4 w-4 animate-spin" />
                      Loading admin accounts...
                    </div>
                  ) : filteredUsers.length === 0 ? (
                    <div className="rounded-2xl border border-dashed p-10 text-center text-sm text-muted-foreground">
                      No admin accounts matched the current search and filters.
                    </div>
                  ) : (
                    <div className="grid gap-4 xl:grid-cols-2">
                      {filteredUsers.map((agent) => {
                        const isCurrentSessionUser = session?.id === agent.id;

                        return (
                          <div key={agent.id} className="overflow-hidden rounded-2xl border bg-background/70 p-4 shadow-soft">
                            <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                              <div className="min-w-0">
                                <div className="flex items-start gap-2 sm:items-center">
                                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                                    <Users className="h-4 w-4" />
                                  </div>
                                  <div className="min-w-0">
                                    <div className="truncate font-semibold text-foreground">
                                      {agent.fullName || agent.username}
                                      {isCurrentSessionUser ? " (You)" : ""}
                                    </div>
                                    <div className="truncate text-xs text-muted-foreground">
                                      @{agent.username}
                                    </div>
                                  </div>
                                </div>
                                <div className="mt-4 flex flex-wrap gap-2">
                                  <span className="inline-flex items-center rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[11px] font-medium text-emerald-700">
                                    {formatAccountScopeLabel(agent.accountScope || agent.role)}
                                  </span>
                                  <span className="inline-flex items-center rounded-full border border-primary/15 bg-primary/5 px-2.5 py-1 text-[11px] font-medium text-primary">
                                    {formatAdminRoleLabel(agent.role)}
                                  </span>
                                  <span className={cn(
                                    "inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-medium",
                                    agent.isActive !== false
                                      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                                      : "border-slate-200 bg-slate-100 text-slate-600",
                                  )}>
                                    {agent.isActive !== false ? "Active" : "Inactive"}
                                  </span>
                                  <span className={cn(
                                    "inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-medium",
                                    consoleStatusBadgeClassName(normalizeAdminConsoleStatus(agent.consoleStatus)),
                                  )}>
                                    Console: {normalizeAdminConsoleStatus(agent.consoleStatus)}
                                  </span>
                                </div>
                              </div>
                              <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:shrink-0">
                                <Button variant="outline" size="sm" className="w-full sm:w-auto" onClick={() => openEditUserEditor(agent)}>
                                  Edit
                                </Button>
                                <Button
                                  variant="outline"
                                  size="sm"
                                  className="w-full sm:w-auto"
                                  onClick={() => {
                                    openEditUserEditor(agent);
                                    setUserEditor((currentState) => ({
                                      ...currentState,
                                      isActive: !(agent.isActive !== false),
                                    }));
                                  }}
                                >
                                  {agent.isActive !== false ? "Deactivate" : "Activate"}
                                </Button>
                              </div>
                            </div>
                            <div className="mt-4 grid gap-3 rounded-2xl border bg-card/60 p-3 text-sm sm:grid-cols-2">
                              <div>
                                <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">Email</div>
                                <div className="mt-1 break-all text-foreground">{agent.email || "No email saved"}</div>
                              </div>
                              <div>
                                <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">Availability</div>
                                <div className={cn(
                                  "mt-1",
                                  agent.isActive !== false
                                    ? consoleStatusTextClassName(normalizeAdminConsoleStatus(agent.consoleStatus))
                                    : "text-foreground",
                                )}>
                                  {agent.isActive !== false
                                    ? `${normalizeAdminConsoleStatus(agent.consoleStatus)}${agent.sessionActive ? " session" : ""}`
                                    : "Disabled"}
                                </div>
                              </div>
                              <div>
                                <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">Access Scope</div>
                                <div className="mt-1 text-foreground">{formatAccountScopeLabel(agent.accountScope || agent.role)}</div>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="requesters" className="mt-0 min-h-0 w-full flex-1 overflow-y-auto pr-1">
            <div className="space-y-6">
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                <div className="rounded-2xl border bg-card p-5 shadow-soft">
                  <div className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Total Requesters</div>
                  <div className="mt-3 text-3xl font-bold text-foreground">{managedRequesterUsers.length}</div>
                  <div className="mt-2 text-sm text-muted-foreground">Portal accounts for users, coaches, and employers.</div>
                </div>
                <div className="rounded-2xl border bg-card p-5 shadow-soft">
                  <div className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Active</div>
                  <div className="mt-3 text-3xl font-bold text-emerald-700">{activeManagedRequesterUsers.length}</div>
                  <div className="mt-2 text-sm text-muted-foreground">Requester accounts that can submit support tickets.</div>
                </div>
                <div className="rounded-2xl border bg-card p-5 shadow-soft">
                  <div className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Inactive</div>
                  <div className="mt-3 text-3xl font-bold text-slate-600">{managedRequesterUsers.length - activeManagedRequesterUsers.length}</div>
                  <div className="mt-2 text-sm text-muted-foreground">Requester accounts currently blocked from the public portal.</div>
                </div>
              </div>

              <div className="rounded-3xl border bg-card shadow-card">
                <div className="border-b px-4 py-4 sm:px-5">
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
                    <div>
                      <h2 className="text-lg font-semibold text-foreground">Requester Accounts</h2>
                      <p className="mt-1 text-sm text-muted-foreground">
                        Manage the people who can enter the public portal and create tickets as users, coaches, or employers.
                      </p>
                    </div>
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                      <div className="relative w-full sm:w-[280px]">
                        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                        <Input
                          value={requesterSearch}
                          onChange={(event) => setRequesterSearch(event.target.value)}
                          placeholder="Search by name, username, or email"
                          className="pl-10"
                        />
                      </div>
                      <div className="w-full sm:w-[170px]">
                        <Select value={requesterRoleFilter} onValueChange={setRequesterRoleFilter}>
                          <SelectTrigger>
                            <SelectValue placeholder="Role" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="all">All Roles</SelectItem>
                            {requesterAccountRoleOptions.map((roleOption) => (
                              <SelectItem key={roleOption.value} value={roleOption.value}>{roleOption.label}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="w-full sm:w-[170px]">
                        <Select value={requesterStatusFilter} onValueChange={(value) => setRequesterStatusFilter(value as UserStatusFilter)}>
                          <SelectTrigger>
                            <SelectValue placeholder="Status" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="all">All Statuses</SelectItem>
                            <SelectItem value="active">Active</SelectItem>
                            <SelectItem value="inactive">Inactive</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <Button onClick={() => openCreateUserEditor("requester")} className="w-full gap-2 gradient-primary sm:w-auto">
                        <UserPlus className="h-4 w-4" />
                        Add Requester
                      </Button>
                    </div>
                  </div>
                </div>

                {error && adminView === "requesters" ? (
                  <div className="border-b border-destructive/10 bg-destructive/5 px-5 py-3 text-sm text-destructive">
                    {error}
                  </div>
                ) : null}

                <div className="p-4 sm:p-5">
                  {isLoading ? (
                    <div className="flex items-center justify-center gap-2 rounded-2xl border border-dashed p-10 text-sm text-muted-foreground">
                      <LoaderCircle className="h-4 w-4 animate-spin" />
                      Loading requester accounts...
                    </div>
                  ) : filteredRequesters.length === 0 ? (
                    <div className="rounded-2xl border border-dashed p-10 text-center text-sm text-muted-foreground">
                      No requester accounts matched the current search and filters.
                    </div>
                  ) : (
                    <div className="grid gap-4 xl:grid-cols-2">
                      {filteredRequesters.map((agent) => (
                        <div key={agent.id} className="overflow-hidden rounded-2xl border bg-background/70 p-4 shadow-soft">
                          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                            <div className="min-w-0">
                              <div className="flex items-start gap-2 sm:items-center">
                                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                                  <UserRound className="h-4 w-4" />
                                </div>
                                <div className="min-w-0">
                                  <div className="truncate font-semibold text-foreground">
                                    {agent.fullName || agent.username}
                                  </div>
                                  <div className="truncate text-xs text-muted-foreground">
                                    @{agent.username}
                                  </div>
                                </div>
                              </div>
                              <div className="mt-4 flex flex-wrap gap-2">
                                <span className="inline-flex items-center rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[11px] font-medium text-emerald-700">
                                  {formatAccountScopeLabel(agent.accountScope || agent.role)}
                                </span>
                                <RequesterRoleBadge role={agent.role} />
                                <span className={cn(
                                  "inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-medium",
                                  agent.isActive !== false
                                    ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                                    : "border-slate-200 bg-slate-100 text-slate-600",
                                )}>
                                  {agent.isActive !== false ? "Active" : "Inactive"}
                                </span>
                              </div>
                            </div>
                            <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:shrink-0">
                              <Button variant="outline" size="sm" className="w-full sm:w-auto" onClick={() => openEditUserEditor(agent)}>
                                Edit
                              </Button>
                              <Button
                                variant="outline"
                                size="sm"
                                className="w-full sm:w-auto"
                                onClick={() => {
                                  openEditUserEditor(agent);
                                  setUserEditor((currentState) => ({
                                    ...currentState,
                                    isActive: !(agent.isActive !== false),
                                  }));
                                }}
                              >
                                {agent.isActive !== false ? "Deactivate" : "Activate"}
                              </Button>
                            </div>
                          </div>
                          <div className="mt-4 grid gap-3 rounded-2xl border bg-card/60 p-3 text-sm sm:grid-cols-2">
                            <div>
                              <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">Email</div>
                              <div className="mt-1 break-all text-foreground">{agent.email || "No email saved"}</div>
                            </div>
                            <div>
                              <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">Portal Access</div>
                              <div className="mt-1 text-foreground">{agent.isActive !== false ? "Enabled" : "Disabled"}</div>
                            </div>
                            <div>
                              <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">Role</div>
                              <div className="mt-1 text-foreground">{formatRequesterRoleLabel(agent.role)}</div>
                            </div>
                            <div>
                              <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">Access Scope</div>
                              <div className="mt-1 text-foreground">{formatAccountScopeLabel(agent.accountScope || agent.role)}</div>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
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
                              <ConsoleField label="Chat ID" icon={Hash} value={consoleDetail.ticket.chatId || "-"} />
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
                <Tabs
                  value={activeTicketTab}
                  onValueChange={(value) => setActiveTicketTab(value as TicketDetailTab)}
                  className="space-y-4"
                >
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
                      <div className="rounded-xl border p-3">
                        <DocumentationAccordionReadOnly
                          draft={activeDetail.ticket.documentation}
                          attachments={activeDetail.attachments}
                          sessionRequests={activeDetail.sessionRequests}
                        />
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
                              Only superadmins can assign unassigned tickets to admin accounts.
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
                                ? "This ticket is already assigned. Only unassigned tickets can be assigned by a superadmin."
                                : "Only superadmins can assign unassigned tickets to admin accounts."}
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
                      <InfoCard label="Learner Email" value={activeDetail.ticket.email} />
                      <InfoCard label="Requester Role" value={formatRequesterRoleLabel(activeDetail.ticket.requesterRole)} />
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
                      statusReason: "Closed via Agent",
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

      <Sheet
        open={isUserEditorOpen}
        onOpenChange={(open) => {
          setIsUserEditorOpen(open);
          if (!open) {
            setUserEditor(createEmptyUserEditorState(userEditorScope));
          }
        }}
      >
        <SheetContent className="w-full sm:max-w-xl overflow-y-auto">
          <SheetHeader>
            <SheetTitle className="flex items-center gap-2">
              <Users className="h-5 w-5 text-primary" />
              {userEditor.id ? `Edit ${userEditorEntityLabel}` : `Add ${userEditorEntityLabel}`}
            </SheetTitle>
            <SheetDescription>
              {userEditor.id
                ? userEditorScope === "requester"
                  ? "Update requester account details, reset the password if needed, or change who can access the portal."
                  : "Update admin account details, reset the password if needed, or change access."
                : userEditorScope === "requester"
                  ? "Create a portal requester account and choose whether this person is a user, coach, or employer."
                  : "Create a new admin account and choose the access level that fits this user."}
            </SheetDescription>
          </SheetHeader>

          <div className="space-y-5 py-5">
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <Label htmlFor="managed-user-full-name" className="mb-1.5 block">Full Name</Label>
                <Input
                  id="managed-user-full-name"
                  value={userEditor.fullName}
                  onChange={(event) => setUserEditor((currentState) => ({ ...currentState, fullName: event.target.value }))}
                  placeholder="Full name"
                />
              </div>
              <div>
                <Label htmlFor="managed-user-username" className="mb-1.5 block">Username</Label>
                <Input
                  id="managed-user-username"
                  value={userEditor.username}
                  onChange={(event) => setUserEditor((currentState) => ({ ...currentState, username: event.target.value }))}
                  placeholder="username"
                  autoComplete="username"
                />
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <Label htmlFor="managed-user-email" className="mb-1.5 block">Email</Label>
                <Input
                  id="managed-user-email"
                  value={userEditor.email}
                  onChange={(event) => setUserEditor((currentState) => ({ ...currentState, email: event.target.value }))}
                  placeholder="name@example.com"
                  autoComplete="email"
                />
              </div>
              <div>
                <Label htmlFor="managed-user-role" className="mb-1.5 block">Role</Label>
                <Select
                  value={userEditor.role}
                  onValueChange={(value) => setUserEditor((currentState) => ({ ...currentState, role: value }))}
                >
                  <SelectTrigger id="managed-user-role">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {userEditorRoleOptions.map((roleOption) => (
                      <SelectItem key={roleOption.value} value={roleOption.value}>{roleOption.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="mt-2 text-xs text-muted-foreground">
                  Access scope: {formatAccountScopeLabel(deriveAccountScopeFromRole(userEditor.role))}
                </p>
              </div>
            </div>

            <div>
              <Label htmlFor="managed-user-password" className="mb-1.5 block">
                {userEditor.id ? "New Password" : "Password"}
              </Label>
              <Input
                id="managed-user-password"
                type="password"
                value={userEditor.password}
                onChange={(event) => setUserEditor((currentState) => ({ ...currentState, password: event.target.value }))}
                placeholder={userEditor.id ? "Leave blank to keep the current password" : "Set a password"}
                autoComplete={userEditor.id ? "new-password" : "current-password"}
              />
              <p className="mt-1 text-xs text-muted-foreground">
                {userEditor.id
                  ? "Only fill this field when you want to reset the password."
                  : userEditorScope === "requester"
                    ? "This password is stored with the requester account for future portal access flows."
                    : "The user will use this password to sign in to the admin area."}
              </p>
            </div>

            <div className="rounded-2xl border bg-secondary/35 p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-medium text-foreground">Account Status</div>
                  <div className="mt-1 text-sm text-muted-foreground">
                    {userEditorScope === "requester"
                      ? "Inactive requester accounts stay in the directory but cannot use the public portal until reactivated."
                      : "Inactive admin accounts stay in the system but cannot log in until reactivated."}
                  </div>
                </div>
                <Button
                  type="button"
                  variant={userEditor.isActive ? "outline" : "default"}
                  onClick={() => setUserEditor((currentState) => ({ ...currentState, isActive: !currentState.isActive }))}
                >
                  {userEditor.isActive ? "Active" : "Inactive"}
                </Button>
              </div>
            </div>
          </div>

          <SheetFooter className="flex-col gap-2 sm:flex-col">
            <Button className="w-full gradient-primary border-0" onClick={() => void saveManagedUser()} disabled={isSavingUser}>
              {isSavingUser ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
              {userEditor.id ? `Save ${userEditorEntityLabel} Changes` : `Create ${userEditorEntityLabel}`}
            </Button>
            <Button variant="outline" className="w-full" onClick={() => setIsUserEditorOpen(false)} disabled={isSavingUser}>
              Cancel
            </Button>
          </SheetFooter>
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
  requests,
  escalations,
  teamsCalls,
  escalationUpdates,
  decisionUpdates,
  notificationLog,
  activeTicketId,
  onDecision,
  onOpenTeamsCall,
  onAcknowledgeEscalation,
  onAcknowledgeEscalationUpdate,
  onAcknowledgeDecision,
  onOpenTicket,
}: {
  requests: TicketSummary[];
  escalations: TicketSummary[];
  teamsCalls: TicketSummary[];
  escalationUpdates: TicketSummary[];
  decisionUpdates: TicketSummary[];
  notificationLog: AdminNotificationLogItem[];
  activeTicketId: string;
  onDecision: (ticket: TicketSummary, action: "accept" | "reject") => Promise<void>;
  onOpenTeamsCall: (ticket: TicketSummary) => Promise<void>;
  onAcknowledgeEscalation: (ticket: TicketSummary, openChat?: boolean) => Promise<void>;
  onAcknowledgeEscalationUpdate: (ticket: TicketSummary) => Promise<void>;
  onAcknowledgeDecision: (ticket: TicketSummary) => Promise<void>;
  onOpenTicket: (ticketId: string) => Promise<void>;
}) => {
  if (
    requests.length === 0
    && escalations.length === 0
    && teamsCalls.length === 0
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
          Review active alerts and the recent notification log for transfer, escalation, and Teams call activity.
        </div>
      </div>
      <div className="max-h-[420px] space-y-2 overflow-y-auto p-2">
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
                <StatusBadge status={ticket.status} />
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
                <StatusBadge status={ticket.status} />
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
                <StatusBadge status={ticket.status} />
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
                <StatusBadge status={ticket.status} />
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
            {item.chatId || item.ticketId}
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
        <StatusBadge status={item.status} />
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
  const { height, startResize } = useVerticalPanelResize({
    enabled: resizable,
    defaultHeight,
    minHeight,
    handlePosition: resizeHandlePosition,
  });

  useEffect(() => {
    if (!scrollRef.current) {
      return;
    }

    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages]);

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
  const shouldOpenUsers = requestedView === "users";
  const shouldOpenRequesters = requestedView === "requesters";
  const shouldOpenConsole = requestedView === "console" || Boolean(requestedTicketId);

  return {
    view: shouldOpenUsers
      ? "users" as const
      : shouldOpenRequesters
        ? "requesters" as const
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

function isStaffSupportAccount(agent: Pick<AdminAgent, "accountScope" | "role">) {
  const normalizedScope = (agent.accountScope || "").trim().toLowerCase();
  const normalizedRole = (agent.role || "").trim().toLowerCase();

  if (normalizedScope) {
    return normalizedScope === "staff";
  }

  return adminDirectoryRoles.has(normalizedRole);
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

  if (filter === "quickResolution") {
    return tickets.filter(isQuickResolutionTicket);
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
  if (filter === "quickResolution") return `No quick tickets are currently assigned to ${targetLabel}.`;
  return `No tickets are currently assigned to ${targetLabel}.`;
}

function isQuickResolutionTicket(ticket: Pick<TicketSummary, "status" | "statusReason">) {
  if (ticket.status !== "Pending") {
    return false;
  }

  return normalizeQuickTicketStatusReason(ticket.statusReason) === "Quick Ticket";
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

const LogoutButton = ({ collapsed = false }: { collapsed?: boolean }) => {
  const navigate = useNavigate();

  async function handleLogout() {
    const session = getAdminSession();

    try {
      if (session?.username && session.instanceId) {
        await fetch("/api/admin/logout", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            actorUsername: session.username,
            instanceId: session.instanceId,
          }),
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
  requestedAt: "Requested At",
  targetLabel: "Teams Target",
  toAgentUsername: "To Username",
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
