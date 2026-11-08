import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import AgentDashboard from "@/pages/support/AgentDashboard";

const adminSession = {
  id: 27,
  username: "ayman.badewi",
  fullName: "Ayman Badewi",
  email: "ayman.badewi@kentbusinesscollege.com",
  role: "admin",
  instanceId: "runtime-test-session",
  sessionActive: true,
  consoleStatus: "Off",
  selectedConsoleStatus: "Off",
  legacySupportAccess: true,
  legacyOperationsAccess: true,
  legacyAdminAccess: true,
  entraDirectoryAdmin: true,
};

let runtimeAdminSession = adminSession;

function setRuntimeAdminSession(overrides: Partial<typeof adminSession>) {
  runtimeAdminSession = { ...adminSession, ...overrides };
  window.sessionStorage.setItem("support_admin_session", JSON.stringify(runtimeAdminSession));
}

const dashboardPayload = {
  tickets: {
    tickets: [
      {
        id: "KBC-000001",
        learnerName: "Engagement",
        requesterName: "Engagement",
        email: "engagement@kentbusinesscollege.com",
        learnerPhone: "",
        requesterRole: "user",
        requesterSource: "microsoft_entra",
        priority: "Normal",
        category: "Technical",
        technicalSubcategory: "Teams",
        inquiryPreview: "Test issue",
        status: "Open",
        statusReason: "",
        assignedAgentId: 27,
        assignedAgentName: "Ayman Badewi",
        assignedAgentUsername: "ayman.badewi",
        assignedTeam: "Support Desk",
        chatId: "CHAT-000001",
        chatIsActive: true,
        liveChatRequested: false,
        liveChatRequestedAt: null,
        queueAssignedAt: null,
        chatDurationMinutes: 0,
        chatState: "open",
        lastMessageAt: null,
        pendingTransferRequest: null,
        pendingEscalationNotification: null,
        pendingTeamsCallNotification: null,
        pendingCoverageTicketNotification: null,
        pendingLearningPlanTransferNotification: null,
        teamsCallRequested: false,
        latestEscalationClosure: null,
        latestTransferDecision: null,
        latestCoverageTutorResponse: null,
        documentation: {
          inquiry: "Test issue",
          symptoms: "",
          errors: "",
          steps: "",
          resources: "",
          chatId: "CHAT-000001",
          ticketId: "KBC-000001",
          ticketStatus: "",
          statusReason: "",
          issuesAddressed: "",
          escalationAgentId: null,
          escalationAgentName: "",
          escalationNote: "",
          coverageNotes: "",
          coverageCards: [],
          documentationCards: [],
          errorImages: [],
        },
        slaStatus: "On Track",
        slaAttentionRequired: false,
        evidenceCount: 0,
        isArchived: false,
        archivedAt: null,
        archivedById: null,
        archivedByName: "",
        archivedByUsername: "",
        createdAt: "2026-06-14T10:00:00.000Z",
        updatedAt: "2026-06-14T10:00:00.000Z",
      },
      {
        id: "KBC-000002",
        learnerName: "Coverage Requester",
        requesterName: "Coverage Requester",
        email: "coverage@kentbusinesscollege.com",
        learnerPhone: "",
        requesterRole: "coach",
        requesterSource: "microsoft_entra",
        priority: "High",
        category: "Technical",
        technicalSubcategory: "Coverage",
        inquiryPreview: "Coverage session request",
        status: "Pending",
        statusReason: "Coverage Ticket",
        assignedAgentId: 27,
        assignedAgentName: "Ayman Badewi",
        assignedAgentUsername: "ayman.badewi",
        assignedTeam: "Support Desk",
        chatId: "CHAT-000002",
        chatIsActive: false,
        liveChatRequested: false,
        liveChatRequestedAt: null,
        queueAssignedAt: null,
        chatDurationMinutes: 0,
        chatState: "closed",
        lastMessageAt: null,
        pendingTransferRequest: null,
        pendingEscalationNotification: null,
        pendingTeamsCallNotification: null,
        pendingCoverageTicketNotification: null,
        pendingLearningPlanTransferNotification: null,
        teamsCallRequested: false,
        latestEscalationClosure: null,
        latestTransferDecision: null,
        latestCoverageTutorResponse: null,
        documentation: {
          inquiry: [
            "Coverage session request",
            "Tutor: Sara Ahmed",
            "Module: Digital Marketing",
            "Session Date: Saturday 19 Jun 2099",
          ].join("\n"),
          symptoms: "",
          errors: "",
          steps: "",
          resources: "",
          chatId: "CHAT-000002",
          ticketId: "KBC-000002",
          ticketStatus: "",
          statusReason: "",
          issuesAddressed: "",
          escalationAgentId: null,
          escalationAgentName: "",
          escalationNote: "",
          coverageNotes: "",
          coverageCards: [],
          documentationCards: [],
          errorImages: [],
        },
        slaStatus: "On Track",
        slaAttentionRequired: false,
        evidenceCount: 0,
        isArchived: false,
        archivedAt: null,
        archivedById: null,
        archivedByName: "",
        archivedByUsername: "",
        createdAt: "2026-06-14T11:00:00.000Z",
        updatedAt: "2026-06-14T11:00:00.000Z",
      },
      {
        id: "KBC-000003",
        learnerName: "Transferred Requester",
        requesterName: "Transferred Requester",
        email: "learning.plan@kentbusinesscollege.com",
        learnerPhone: "",
        requesterRole: "user",
        requesterSource: "microsoft_entra",
        priority: "Normal",
        category: "Learning",
        technicalSubcategory: "",
        inquiryPreview: "Please help with the training plan update.",
        status: "Open",
        statusReason: "",
        assignedAgentId: 27,
        assignedAgentName: "Ayman Badewi",
        assignedAgentUsername: "ayman.badewi",
        assignedTeam: "Learning Plan Team",
        chatId: "CHAT-000003",
        chatIsActive: true,
        liveChatRequested: false,
        liveChatRequestedAt: null,
        queueAssignedAt: null,
        chatDurationMinutes: 0,
        chatState: "open",
        lastMessageAt: null,
        pendingTransferRequest: null,
        pendingEscalationNotification: null,
        pendingTeamsCallNotification: null,
        pendingCoverageTicketNotification: null,
        pendingLearningPlanTransferNotification: {
          ticketId: "KBC-000003",
          requesterName: "Transferred Requester",
          requesterEmail: "learning.plan@kentbusinesscollege.com",
          requesterRole: "user",
          fromTeam: "Support Desk",
          toTeam: "Learning Plan Team",
          transferredAt: "2026-06-14T12:30:00.000Z",
          transferredById: 91,
          transferredByName: "Support Manager",
          transferredByUsername: "support.manager",
          assignedAgentId: 27,
          assignedAgentName: "Ayman Badewi",
          assignedAgentUsername: "ayman.badewi",
          note: "Please continue with the learning plan workflow.",
        },
        teamsCallRequested: false,
        latestEscalationClosure: null,
        latestTransferDecision: null,
        latestCoverageTutorResponse: null,
        documentation: {
          inquiry: "Please help with the training plan update.",
          symptoms: "",
          errors: "",
          steps: "",
          resources: "",
          chatId: "CHAT-000003",
          ticketId: "KBC-000003",
          ticketStatus: "",
          statusReason: "",
          issuesAddressed: "",
          escalationAgentId: null,
          escalationAgentName: "",
          escalationNote: "",
          coverageNotes: "",
          coverageCards: [],
          documentationCards: [],
          errorImages: [],
        },
        slaStatus: "On Track",
        slaAttentionRequired: false,
        evidenceCount: 0,
        isArchived: false,
        archivedAt: null,
        archivedById: null,
        archivedByName: "",
        archivedByUsername: "",
        createdAt: "2026-06-14T12:00:00.000Z",
        updatedAt: "2026-06-14T12:00:00.000Z",
      },
      {
        id: "KBC-000004",
        learnerName: "Sooner Coverage",
        requesterName: "Sooner Coverage",
        email: "sooner.coverage@kentbusinesscollege.com",
        learnerPhone: "",
        requesterRole: "coach",
        requesterSource: "microsoft_entra",
        priority: "Normal",
        category: "Technical",
        technicalSubcategory: "Coverage",
        inquiryPreview: "Upcoming coverage session request",
        status: "Pending",
        statusReason: "Coverage Ticket",
        assignedAgentId: 27,
        assignedAgentName: "Ayman Badewi",
        assignedAgentUsername: "ayman.badewi",
        assignedTeam: "Support Desk",
        chatId: "CHAT-000004",
        chatIsActive: false,
        liveChatRequested: false,
        liveChatRequestedAt: null,
        queueAssignedAt: null,
        chatDurationMinutes: 0,
        chatState: "closed",
        lastMessageAt: null,
        pendingTransferRequest: null,
        pendingEscalationNotification: null,
        pendingTeamsCallNotification: null,
        pendingCoverageTicketNotification: null,
        pendingLearningPlanTransferNotification: null,
        teamsCallRequested: false,
        latestEscalationClosure: null,
        latestTransferDecision: null,
        latestCoverageTutorResponse: null,
        documentation: {
          inquiry: [
            "Coverage session request",
            "Tutor: Mona Adel",
            "Module: Project Planning",
            "Session Date: Friday 18 Jun 2099",
          ].join("\n"),
          symptoms: "",
          errors: "",
          steps: "",
          resources: "",
          chatId: "CHAT-000004",
          ticketId: "KBC-000004",
          ticketStatus: "",
          statusReason: "",
          issuesAddressed: "",
          escalationAgentId: null,
          escalationAgentName: "",
          escalationNote: "",
          coverageNotes: "",
          coverageCards: [],
          documentationCards: [],
          errorImages: [],
        },
        slaStatus: "On Track",
        slaAttentionRequired: false,
        evidenceCount: 0,
        isArchived: false,
        archivedAt: null,
        archivedById: null,
        archivedByName: "",
        archivedByUsername: "",
        createdAt: "2026-06-14T09:00:00.000Z",
        updatedAt: "2026-06-14T09:00:00.000Z",
      },
    ],
  },
  accounts: {
    accounts: [
      {
        id: 27,
        username: "ayman.badewi",
        fullName: "Ayman Badewi",
        email: "ayman.badewi@kentbusinesscollege.com",
        accountScope: "staff",
        role: "admin",
        isActive: true,
        sessionActive: true,
        legacySupportAccess: true,
        legacyOperationsAccess: true,
        legacyAdminAccess: true,
        entraDirectoryAdmin: true,
        consoleStatus: "Off",
        selectedConsoleStatus: "Off",
      },
      {
        id: 41,
        username: "test.test",
        fullName: "Test Test",
        email: "test.test@kentbusinesscollege.com",
        accountScope: "staff",
        role: "agent",
        isActive: true,
        sessionActive: false,
        legacySupportAccess: false,
        legacyOperationsAccess: false,
        legacyAdminAccess: false,
        entraDirectoryAdmin: false,
        consoleStatus: "Off",
        selectedConsoleStatus: "Off",
      },
    ],
    agents: [
      {
        id: 27,
        username: "ayman.badewi",
        fullName: "Ayman Badewi",
        email: "ayman.badewi@kentbusinesscollege.com",
        accountScope: "staff",
        role: "admin",
        isActive: true,
        sessionActive: true,
        legacySupportAccess: true,
        legacyOperationsAccess: true,
        legacyAdminAccess: true,
        entraDirectoryAdmin: true,
        consoleStatus: "Off",
        selectedConsoleStatus: "Off",
      },
      {
        id: 41,
        username: "test.test",
        fullName: "Test Test",
        email: "test.test@kentbusinesscollege.com",
        accountScope: "staff",
        role: "agent",
        isActive: true,
        sessionActive: false,
        legacySupportAccess: false,
        legacyOperationsAccess: false,
        legacyAdminAccess: false,
        entraDirectoryAdmin: false,
        consoleStatus: "Off",
        selectedConsoleStatus: "Off",
      },
    ],
  },
};

type RuntimeDashboardTicket = (typeof dashboardPayload.tickets.tickets)[number] & {
  ticketState?: {
    dashboardBucket?: string;
    ticketType?: string;
  };
};

function isRuntimeCoverageTicket(ticket: RuntimeDashboardTicket) {
  return ticket.ticketState?.ticketType === "coverage" || ticket.technicalSubcategory === "Coverage";
}

function isRuntimeQuickTicket(ticket: RuntimeDashboardTicket) {
  return (
    ticket.ticketState?.ticketType === "quick"
    || ticket.statusReason === "Quick Ticket"
    || ticket.statusReason === "Quick Resolution"
  ) && !isRuntimeCoverageTicket(ticket);
}

function buildDashboardMetricsPayload(tickets: RuntimeDashboardTicket[] = dashboardPayload.tickets.tickets) {
  const activeTickets = tickets.filter((ticket) => !ticket.isArchived);
  return {
    metrics: {
      total: activeTickets.length,
      open: activeTickets.filter((ticket) => ticket.status === "Open" && ticket.chatState !== "closed").length,
      pending: activeTickets.filter((ticket) => ticket.status === "Pending" || ticket.ticketState?.dashboardBucket === "pending").length,
      escalation: activeTickets.filter((ticket) => ticket.status === "Pending" && ticket.statusReason === "Escalation").length,
      closed: activeTickets.filter((ticket) => ticket.status === "Closed" || ticket.ticketState?.dashboardBucket === "closed").length,
      slaBreached: activeTickets.filter((ticket) => ticket.slaStatus === "Breached").length,
      coverage: activeTickets.filter(isRuntimeCoverageTicket).length,
      quickResolution: activeTickets.filter(isRuntimeQuickTicket).length,
      sections: {
        coverage: activeTickets.filter(isRuntimeCoverageTicket).length,
        learningPlanOther: activeTickets.filter((ticket) => ticket.assignedTeam === "Learning Plan Team" && !isRuntimeCoverageTicket(ticket)).length,
      },
    },
  };
}

function buildDashboardAccountsPayload() {
  const applyRuntimeSessionToSignedInAccount = (account: (typeof dashboardPayload.accounts.accounts)[number]) => {
    if (account.id !== runtimeAdminSession.id && account.username !== runtimeAdminSession.username) {
      return account;
    }

    return {
      ...account,
      role: runtimeAdminSession.role,
      legacySupportAccess: runtimeAdminSession.legacySupportAccess,
      legacyOperationsAccess: runtimeAdminSession.legacyOperationsAccess,
      legacyAdminAccess: runtimeAdminSession.legacyAdminAccess,
      entraDirectoryAdmin: runtimeAdminSession.entraDirectoryAdmin,
    };
  };

  return {
    accounts: {
      accounts: dashboardPayload.accounts.accounts.map(applyRuntimeSessionToSignedInAccount),
      agents: dashboardPayload.accounts.agents.map(applyRuntimeSessionToSignedInAccount),
    },
  };
}

function buildRuntimeTicketDetail(ticketId: string) {
  const summary = dashboardPayload.tickets.tickets.find((ticket) => ticket.id === ticketId);
  if (!summary) {
    throw new Error(`Ticket ${ticketId} was not found in runtime payload.`);
  }

  return {
    ticket: {
      ...summary,
      inquiry: summary.documentation?.inquiry || summary.inquiryPreview,
      closedAt: summary.status === "Closed" ? summary.updatedAt : null,
      documentation: summary.documentation || {
        inquiry: summary.inquiryPreview,
        symptoms: "",
        errors: "",
        steps: "",
        resources: "",
        chatId: summary.chatId,
        ticketId: summary.id,
        ticketStatus: "",
        statusReason: "",
        issuesAddressed: "",
        escalationAgentId: null,
        escalationAgentName: "",
        escalationNote: "",
        coverageNotes: "",
        coverageCards: [],
        documentationCards: [],
        errorImages: [],
      },
    },
    chatHistory: [],
    attachments: [],
    history: [],
    sessionRequests: [],
  };
}

describe("AgentDashboard runtime", () => {
  it("claims an unassigned ticket only after the explicit claim action", async () => {
    let detail = buildRuntimeTicketDetail("KBC-000001");
    detail = { ...detail, ticket: { ...detail.ticket, assignedAgentId: null, assignedAgentName: "Unassigned", assignedAgentUsername: "" } };
    const patches: Record<string, unknown>[] = [];
    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/admin/tickets/KBC-000001" && init?.method === "PATCH") {
        patches.push(JSON.parse(String(init.body)));
        detail = { ...detail, ticket: { ...detail.ticket, assignedAgentId: 27, assignedAgentName: "Ayman Badewi", assignedAgentUsername: "ayman.badewi" } };
        return new Response(JSON.stringify(detail), { status: 200 });
      }
      if (url.startsWith("/api/admin/tickets") && !url.includes("/metrics")) {
        return new Response(JSON.stringify({ tickets: [detail.ticket] }), { status: 200 });
      }
      return originalFetch(input, init);
    }) as typeof fetch;
    render(<MemoryRouter initialEntries={["/admin"]}><AgentDashboard /></MemoryRouter>);
    const claim = await screen.findByRole("button", { name: "Claim ticket KBC-000001" });
    expect(patches).toHaveLength(0);
    fireEvent.click(claim);
    await waitFor(() => expect(patches).toEqual([{ claim: true }]));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Claim ticket KBC-000001" })).not.toBeInTheDocument());
    expect(screen.getByText("Assigned to Ayman Badewi")).toBeInTheDocument();
  });

  it("confirms a status change directly from the table and updates the row without opening ticket details", async () => {
    let detail = buildRuntimeTicketDetail("KBC-000001");
    const patches: Record<string, unknown>[] = [];
    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/admin/tickets/KBC-000001" && init?.method === "PATCH") {
        const body = JSON.parse(String(init.body));
        patches.push(body);
        detail = { ...detail, ticket: { ...detail.ticket, status: body.status, statusReason: body.statusReason } };
        return new Response(JSON.stringify(detail), { status: 200 });
      }
      if (url.startsWith("/api/admin/tickets") && !url.includes("/metrics")) {
        return new Response(JSON.stringify({ tickets: [detail.ticket] }), { status: 200 });
      }
      return originalFetch(input, init);
    }) as typeof fetch;
    render(<MemoryRouter initialEntries={["/admin"]}><AgentDashboard /></MemoryRouter>);
    const trigger = await screen.findByRole("button", { name: "Change status for KBC-000001" });
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("button", { name: "Closed", exact: true }));
    fireEvent.change(screen.getByRole("textbox", { name: "Reason for status change" }), { target: { value: "Issue resolved" } });
    expect(patches).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Confirm change" }));
    fireEvent.click(await screen.findByRole("button", { name: "Close ticket without email" }));
    await waitFor(() => expect(patches).toEqual([{
      status: "Closed",
      statusReason: "Closed via Agent",
      note: "Issue resolved",
      closureNotification: { send: false, subject: "", message: "" },
    }]));
    await waitFor(() => expect(screen.getByRole("button", { name: "Change status for KBC-000001" })).toHaveTextContent("Closed"));
    expect(screen.queryByRole("heading", { name: "Ticket KBC-000001" })).not.toBeInTheDocument();
  });

  it.each([
    ["user", "kbc_users_data", "Learner"],
    ["user", "lms_learners", "Learner"],
    ["user", "legacy_kbc_users_data", "Learner"],
    ["coach", "microsoft_entra", "Coach"],
    ["tutor", "microsoft_entra", "Tutor"],
    ["employer", "microsoft_entra", "Employer"],
    ["user", "microsoft_entra", "User"],
    ["", "", "User"],
  ])("keeps the %s/%s requester badge (%s) and searched row after opening a ticket", async (role, source, label) => {
    const detail = buildRuntimeTicketDetail("KBC-000001");
    const ticket = { ...detail.ticket, requesterRole: role, requesterSource: source, subject: "Unique searchable subject" };
    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/admin/tickets/KBC-000001") {
        return new Response(JSON.stringify({ ...detail, ticket }), { status: 200 });
      }
      if (url.startsWith("/api/admin/tickets") && !url.includes("/metrics")) {
        return new Response(JSON.stringify({ tickets: [ticket] }), { status: 200 });
      }
      return originalFetch(input, init);
    }) as typeof fetch;

    render(<MemoryRouter initialEntries={["/admin"]}><AgentDashboard /></MemoryRouter>);
    const row = (await screen.findByText(ticket.id)).closest("tr")!;
    expect(within(row).getByText(label, { exact: true })).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: /Search by requester name/ }), {
      target: { value: ticket.subject },
    });
    const searchedRow = (await screen.findByText(ticket.id)).closest("tr")!;
    fireEvent.click(searchedRow);
    const dialog = await screen.findByRole("dialog");
    await within(dialog).findByRole("heading", { name: `Ticket ${ticket.id}` });
    fireEvent.keyDown(dialog, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    const remainingRow = screen.getByText(ticket.id).closest("tr")!;
    expect(within(remainingRow).getByText(label, { exact: true })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /Search by requester name/ })).toHaveValue(ticket.subject);
  });

  beforeEach(() => {
    window.sessionStorage.clear();
    window.localStorage.clear();
    runtimeAdminSession = adminSession;
    window.sessionStorage.setItem("support_admin_session", JSON.stringify(runtimeAdminSession));

    Object.defineProperty(window, "Notification", {
      configurable: true,
      writable: true,
      value: class NotificationMock {
        static permission = "denied";
        static requestPermission = vi.fn(async () => "denied");
        close() {}
      },
    });

    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;

      if (url.includes("/api/admin/session-heartbeat")) {
        return new Response(JSON.stringify({ ok: true, sessionActive: true, admin: runtimeAdminSession }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      if (url.includes("/api/admin/session")) {
        return new Response(JSON.stringify({ admin: runtimeAdminSession }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      if (url.includes("/api/admin/tickets/metrics")) {
        return new Response(JSON.stringify(buildDashboardMetricsPayload()), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      if (url.includes("/api/admin/tickets")) {
        return new Response(JSON.stringify(dashboardPayload.tickets), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      if (url.includes("/api/admin/accounts")) {
        return new Response(JSON.stringify(buildDashboardAccountsPayload().accounts), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      if (url.includes("/api/admin/migration-status")) {
        return new Response(JSON.stringify({ adminAiWebhookConfigured: true, chatbotWebhookConfigured: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      if (url.includes("/api/admin/notifications")) {
        return new Response(JSON.stringify({ notifications: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      throw new Error(`Unhandled fetch in runtime test: ${url}`);
    }) as typeof fetch;
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("filters tickets and counts by creation date while preserving search and archive filters", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    // Cairo's daylight saving change skips midnight on this date.
    vi.setSystemTime(new Date(2026, 3, 24, 12));
    const tickets = [
      { ...dashboardPayload.tickets.tickets[0], id: "KBC-000101", createdAt: new Date(2026, 3, 24).toISOString() },
      { ...dashboardPayload.tickets.tickets[0], id: "KBC-000102", createdAt: new Date(2026, 3, 18).toISOString() },
      { ...dashboardPayload.tickets.tickets[0], id: "KBC-000103", createdAt: new Date(2026, 3, 17, 23, 59, 59).toISOString() },
      { ...dashboardPayload.tickets.tickets[0], id: "KBC-000104", createdAt: new Date(2026, 3, 25).toISOString() },
      { ...dashboardPayload.tickets.tickets[0], id: "KBC-000105", isArchived: true, createdAt: new Date(2026, 3, 24).toISOString() },
      { ...dashboardPayload.tickets.tickets[0], id: "KBC-000106", isArchived: true, createdAt: new Date(2026, 3, 17).toISOString() },
    ];
    const defaultFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).startsWith("/api/admin/tickets/metrics")) {
        // Exercise local counts alongside the unpaginated cached-list fallback.
        return new Response(JSON.stringify({ metrics: null }), { status: 200 });
      }
      if (String(input).startsWith("/api/admin/tickets") && !String(input).includes("/metrics")) {
        // No pagination metadata: exercise the cached-list fallback.
        return new Response(JSON.stringify({ tickets }), { status: 200 });
      }
      return defaultFetch(input, init);
    }) as typeof fetch;

    render(<MemoryRouter initialEntries={["/admin"]}><AgentDashboard /></MemoryRouter>);
    await screen.findByText("KBC-000101");
    const selectPeriod = async (name: string) => {
      fireEvent.click(screen.getByRole("button", { name: "Filter tickets by creation date" }));
      fireEvent.click(await screen.findByRole("button", { name, exact: true }));
      fireEvent.keyDown(screen.getByRole("button", { name, exact: true }), { key: "Escape" });
    };
    const expectOpenCount = (count: string) => {
      expect(within(screen.getByRole("button", { name: /Open Tickets/ })).getByText(count, { exact: true })).toBeInTheDocument();
    };
    await waitFor(() => expectOpenCount("4"));

    await selectPeriod("Today");
    expect(await screen.findByText("KBC-000101")).toBeInTheDocument();
    for (const id of ["KBC-000102", "KBC-000103", "KBC-000104", "KBC-000105"]) {
      expect(screen.queryByText(id)).not.toBeInTheDocument();
    }
    expectOpenCount("1");

    fireEvent.click(screen.getByRole("button", { name: /Pending Tickets/ }));
    expect(await screen.findByText("No tickets match the current filters for today.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Pending Tickets/ }));

    await selectPeriod("Last 7 Days");
    expect(await screen.findByText("KBC-000101")).toBeInTheDocument();
    expect(await screen.findByText("KBC-000102")).toBeInTheDocument();
    expect(screen.queryByText("KBC-000103")).not.toBeInTheDocument();
    expect(screen.queryByText("KBC-000104")).not.toBeInTheDocument();
    expectOpenCount("2");

    fireEvent.change(screen.getByRole("textbox", { name: /Search by requester name/ }), { target: { value: "KBC-000102" } });
    expect(await screen.findByText("KBC-000102")).toBeInTheDocument();
    expect(screen.queryByText("KBC-000101")).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: /Search by requester name/ }), { target: { value: "KBC-000103" } });
    expect(await screen.findByText("No matching tickets found for this search.")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: /Search by requester name/ }), { target: { value: "" } });

    fireEvent.click(screen.getByRole("button", { name: "Reset Filters" }));
    expect(screen.getByRole("button", { name: "Filter tickets by creation date" })).toHaveTextContent("All Time");
    expect(await screen.findByText("KBC-000103")).toBeInTheDocument();
    expect(screen.getByText("KBC-000104")).toBeInTheDocument();
    await waitFor(() => expectOpenCount("4"));

    await selectPeriod("Today");
    fireEvent.click(screen.getByRole("button", { name: "Archived" }));
    expect(await screen.findByText("KBC-000105")).toBeInTheDocument();
    expect(screen.queryByText("KBC-000101")).not.toBeInTheDocument();
    expect(screen.queryByText("KBC-000106")).not.toBeInTheDocument();
    expectOpenCount("1");
    fireEvent.click(screen.getByRole("button", { name: "Back to Active" }));
    expect(screen.getByRole("button", { name: "Filter tickets by creation date" })).toHaveTextContent("All Time");
    await waitFor(() => expectOpenCount("4"));
  }, 15000);

  it("requests the same date range for pages and metrics and returns to the first page", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 5, 14, 12));
    const defaultFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://localhost");
      if (url.pathname === "/api/admin/tickets" && url.searchParams.has("page")) {
        const page = Number(url.searchParams.get("page"));
        const filtered = url.searchParams.has("createdFrom");
        return new Response(JSON.stringify({
          tickets: filtered ? [] : [dashboardPayload.tickets.tickets[0]],
          pagination: {
            page, pageSize: 25, total: filtered ? 0 : 26, totalPages: filtered ? 0 : 2,
            hasNext: !filtered && page === 1, hasPrevious: page > 1, isPaginated: true,
          },
        }), { status: 200 });
      }
      if (url.pathname === "/api/admin/tickets/metrics" && url.searchParams.has("createdFrom")) {
        return new Response(JSON.stringify(buildDashboardMetricsPayload([])), { status: 200 });
      }
      return defaultFetch(input, init);
    }) as typeof fetch;

    render(<MemoryRouter initialEntries={["/admin"]}><AgentDashboard /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: "Next" }));
    await screen.findByText("Page 2 of 2");

    fireEvent.click(screen.getByRole("button", { name: "Filter tickets by creation date" }));
    fireEvent.click(await screen.findByRole("button", { name: "Today", exact: true }));
    fireEvent.keyDown(screen.getByRole("button", { name: "Today", exact: true }), { key: "Escape" });
    await screen.findByText("No tickets match the current filters for today.");
    const expectedFrom = new Date(2026, 5, 14).toISOString();
    const expectedBefore = new Date(2026, 5, 15).toISOString();
    await waitFor(() => {
      const requests = vi.mocked(globalThis.fetch).mock.calls.map(([input]) => new URL(String(input), "http://localhost"));
      for (const path of ["/api/admin/tickets", "/api/admin/tickets/metrics"]) {
        expect(requests.some((url) => url.pathname === path
          && url.searchParams.get("createdFrom") === expectedFrom
          && url.searchParams.get("createdBefore") === expectedBefore
          && (path.endsWith("metrics") || url.searchParams.get("page") === "1"))).toBe(true);
      }
      expect(screen.getByRole("button", { name: /Open Tickets/ })).toHaveTextContent("0");
    });

    fireEvent.click(screen.getByRole("button", { name: "Reset Filters" }));
    await screen.findByText("Page 1 of 2");
    expect(screen.getByRole("button", { name: "Filter tickets by creation date" })).toHaveTextContent("All Time");
  }, 15000);

  it("renders the admin dashboard with live payload data", async () => {
    render(
      <MemoryRouter initialEntries={["/admin"]}>
        <AgentDashboard />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("Overview")).toBeInTheDocument();
    });
  });

  it("keeps Support Dashboard focused and separates Admin Dashboard overview", async () => {
    render(
      <MemoryRouter initialEntries={["/admin"]}>
        <AgentDashboard />
      </MemoryRouter>,
    );

    const supportPanel = await screen.findByRole("tabpanel");
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual([
      "Admin Dashboard",
      "Support Dashboard",
      "Learning Plan Team",
      "Chat Console",
      "Team Management",
    ]);
    expect(screen.getByRole("tab", { name: /Admin Dashboard/i })).toHaveAttribute("data-state", "inactive");
    expect(screen.getByRole("tab", { name: /Support Dashboard/i })).toHaveAttribute("data-state", "active");
    const supportOverview = screen.getByText("Overview").closest(".rounded-2xl");
    expect(supportOverview).not.toBeNull();
    expect(within(supportOverview as HTMLElement).getByText("1")).toBeInTheDocument();
    expect(within(supportOverview as HTMLElement).getByText("Support Tickets")).toBeInTheDocument();
    expect(within(supportPanel).getByText("Support Tickets")).toBeInTheDocument();
    expect(within(supportPanel).getByText("KBC-000001")).toBeInTheDocument();
    expect(within(supportPanel).queryByText("KBC-000002")).not.toBeInTheDocument();
    expect(within(supportPanel).queryByText("KBC-000003")).not.toBeInTheDocument();
  });

  it("defaults admin-only sessions to Admin Dashboard while keeping workspace shortcuts visible", async () => {
    setRuntimeAdminSession({
      legacySupportAccess: false,
      legacyOperationsAccess: false,
    });

    render(
      <MemoryRouter initialEntries={["/admin"]}>
        <AgentDashboard />
      </MemoryRouter>,
    );

    const adminPanel = await screen.findByRole("tabpanel");
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual([
      "Admin Dashboard",
      "Support Dashboard",
      "Learning Plan Team",
      "Chat Console",
      "Team Management",
    ]);
    expect(screen.getByRole("tab", { name: /Admin Dashboard/i })).toHaveAttribute("data-state", "active");
    expect(screen.getByRole("tab", { name: /Support Dashboard/i })).toHaveAttribute("data-state", "inactive");
    expect(screen.getByRole("tab", { name: /Learning Plan Team/i })).toHaveAttribute("data-state", "inactive");
    expect(screen.getByRole("tab", { name: /Chat Console/i })).toHaveAttribute("data-state", "inactive");
    expect(within(adminPanel).getByRole("heading", { name: "All Tickets" })).toBeInTheDocument();
  });

  it("keeps no-access staff visible in Team Management so access can be restored", async () => {
    render(
      <MemoryRouter initialEntries={["/admin?view=management"]}>
        <AgentDashboard />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Team Management" })).toBeInTheDocument();
    expect(screen.getByText("Test Test")).toBeInTheDocument();
    expect(screen.getByText(/No support access/i)).toBeInTheDocument();
  });

  it("loads dynamic teams into the transfer menu", async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;

      if (url.includes("/api/admin/teams")) {
        return new Response(JSON.stringify({
          teams: [
            {
              id: 7,
              key: "curriculum",
              name: "Curriculum Team",
              assignedTeam: "Curriculum Team",
              label: "Curriculum Team",
              description: "Route this ticket to the curriculum queue.",
              receiverAccessMetadataKey: "team_access:curriculum",
              isActive: true,
            },
          ],
        }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      return originalFetch(input, init);
    }) as typeof fetch;

    render(
      <MemoryRouter initialEntries={["/admin"]}>
        <AgentDashboard />
      </MemoryRouter>,
    );

    await screen.findByText("Overview");
    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith("/api/admin/teams", { cache: "no-store" });
    });

    fireEvent.pointerDown(screen.getByRole("button", { name: /Transfer ticket KBC-000001 to another team/i }), {
      button: 0,
      ctrlKey: false,
    });

    expect(await screen.findByRole("menuitem", { name: /Curriculum Team/i })).toBeInTheDocument();
  });

  it("shows dynamic teams as isolated dashboard tabs", async () => {
    const originalFetch = globalThis.fetch;
    const dynamicTeams = [
      { id: 7, key: "curriculum", label: "Curriculum Team", ticketId: "KBC-000006", subcategory: "Curriculum" },
      { id: 8, key: "ai_team", label: "Ai Team", ticketId: "KBC-000007", subcategory: "AI Team" },
      { id: 9, key: "enrolment_team", label: "Enrolment Team", ticketId: "KBC-000008", subcategory: "Enrolment" },
      { id: 10, key: "operation_team", label: "Operation Team", ticketId: "KBC-000009", subcategory: "Operation" },
      { id: 11, key: "quality_team", label: "Quality team", ticketId: "KBC-000010", subcategory: "Quality" },
    ];
    const dynamicTeamTickets = dynamicTeams.map((team, index) => ({
      ...dashboardPayload.tickets.tickets[0],
      id: team.ticketId,
      learnerName: `${team.label} Learner`,
      requesterName: `${team.label} Learner`,
      email: `${team.key}@kentbusinesscollege.com`,
      inquiryPreview: `${team.label} request`,
      technicalSubcategory: team.subcategory,
      assignedTeam: team.label,
      chatId: `CHAT-${team.ticketId.slice(4)}`,
      createdAt: `2026-06-14T${13 + index}:00:00.000Z`,
      updatedAt: `2026-06-14T${13 + index}:00:00.000Z`,
    }));
    const allDashboardTickets = [...dashboardPayload.tickets.tickets, ...dynamicTeamTickets];

    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;

      if (url.includes("/api/admin/teams")) {
        return new Response(JSON.stringify({
          teams: dynamicTeams.map((team) => ({
            id: team.id,
            key: team.key,
            name: team.label,
            assignedTeam: team.label,
            label: team.label,
            description: `Route this ticket to the ${team.label} queue.`,
            receiverAccessMetadataKey: `team_access:${team.key}`,
            isActive: true,
          })),
        }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      if (url.includes("/api/admin/tickets/metrics")) {
        return new Response(JSON.stringify(buildDashboardMetricsPayload(allDashboardTickets)), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      if (url.includes("/api/admin/tickets")) {
        const requestedTeamKey = new URL(url, "http://localhost").searchParams.get("team");
        const requestedDynamicTeamIndex = dynamicTeams.findIndex((team) => team.key === requestedTeamKey);
        const responseTickets = requestedDynamicTeamIndex >= 0
          ? [dynamicTeamTickets[requestedDynamicTeamIndex]]
          : allDashboardTickets;
        return new Response(JSON.stringify({
          tickets: responseTickets,
          pagination: {
            page: 1,
            pageSize: 50,
            total: responseTickets.length,
            totalPages: 1,
            hasNext: false,
            hasPrevious: false,
            isPaginated: true,
          },
        }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      return originalFetch(input, init);
    }) as typeof fetch;

    render(
      <MemoryRouter initialEntries={["/admin?view=admin"]}>
        <AgentDashboard />
      </MemoryRouter>,
    );

    const curriculumTab = await screen.findByRole("tab", { name: /^Curriculum Team$/i });
    await screen.findByRole("tabpanel", { name: /Admin Dashboard/i });

    fireEvent.pointerDown(screen.getByTitle("Sort by Category"), {
      button: 0,
      ctrlKey: false,
    });
    expect(await screen.findByRole("menuitem", { name: "Support Dashboard" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Learning Plan Team" })).toBeInTheDocument();
    for (const team of dynamicTeams) {
      expect(screen.getByRole("menuitem", { name: team.label })).toBeInTheDocument();
    }
    expect(screen.queryByRole("menuitem", { name: "Technical first" })).not.toBeInTheDocument();

    for (const [index, team] of dynamicTeams.entries()) {
      if (index > 0) {
        fireEvent.pointerDown(screen.getByTitle("Sort by Category"), {
          button: 0,
          ctrlKey: false,
        });
      }
      fireEvent.click(await screen.findByRole("menuitem", { name: team.label }));
      await waitFor(() => {
        const adminPanel = screen.getByRole("tabpanel", { name: /Admin Dashboard/i });
        const ticketRows = Array.from(adminPanel.querySelectorAll("tbody tr"));
        expect(ticketRows[0]).toHaveTextContent(team.ticketId);
      });
    }

    fireEvent.pointerDown(screen.getByTitle("Sort by Category"), {
      button: 0,
      ctrlKey: false,
    });
    fireEvent.click(await screen.findByRole("menuitem", { name: "Support Dashboard" }));
    await waitFor(() => {
      const adminPanel = screen.getByRole("tabpanel", { name: /Admin Dashboard/i });
      const ticketRows = Array.from(adminPanel.querySelectorAll("tbody tr"));
      expect(ticketRows[0]).toHaveTextContent("KBC-000001");
    });

    fireEvent.pointerDown(screen.getByTitle("Sort by Category"), {
      button: 0,
      ctrlKey: false,
    });
    fireEvent.click(await screen.findByRole("menuitem", { name: "Learning Plan Team" }));
    await waitFor(() => {
      const adminPanel = screen.getByRole("tabpanel", { name: /Admin Dashboard/i });
      const ticketRows = Array.from(adminPanel.querySelectorAll("tbody tr"));
      expect(ticketRows[0]).toHaveTextContent("KBC-000002");
    });

    fireEvent.mouseDown(curriculumTab, {
      button: 0,
      ctrlKey: false,
    });
    fireEvent.mouseUp(curriculumTab);
    fireEvent.click(curriculumTab);

    expect(await screen.findByRole("heading", { name: "Curriculum Team Tickets" })).toBeInTheDocument();
    const curriculumPanel = screen.getByRole("tabpanel", { name: /^Curriculum Team$/i });
    expect(within(curriculumPanel).getByText("KBC-000006")).toBeInTheDocument();
    expect(within(curriculumPanel).queryByText("KBC-000001")).not.toBeInTheDocument();
  });

  it("toggles dynamic team receiver access through the team-access endpoint", async () => {
    const originalFetch = globalThis.fetch;
    const teamAccessRequests: Array<Record<string, unknown>> = [];
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;

      if (url.includes("/api/admin/teams")) {
        return new Response(JSON.stringify({
          teams: [
            {
              id: 7,
              key: "curriculum",
              name: "Curriculum Team",
              assignedTeam: "Curriculum Team",
              label: "Curriculum Team",
              description: "Route this ticket to the curriculum queue.",
              receiverAccessMetadataKey: "team_access:curriculum",
              isActive: true,
            },
          ],
        }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      if (url.endsWith("/api/admin/accounts/41/team-access") && init?.method === "PATCH") {
        const parsedBody = JSON.parse(String(init.body || "{}")) as Record<string, unknown>;
        teamAccessRequests.push(parsedBody);
        return new Response(JSON.stringify({
          agent: {
            ...dashboardPayload.accounts.accounts[1],
            teamAccess: [
              {
                key: "curriculum",
                name: "Curriculum Team",
                assignedTeam: "Curriculum Team",
                label: "Curriculum Team",
                canReceiveTickets: true,
              },
            ],
            teamAccessKeys: ["curriculum"],
          },
        }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      return originalFetch(input, init);
    }) as typeof fetch;

    render(
      <MemoryRouter initialEntries={["/admin?view=management"]}>
        <AgentDashboard />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("tab", { name: /Curriculum Team0/i })).toBeInTheDocument();
    const curriculumTab = screen.getByRole("tab", { name: /Curriculum Team0/i });
    fireEvent.mouseDown(curriculumTab, {
      button: 0,
      ctrlKey: false,
    });
    fireEvent.mouseUp(curriculumTab);
    fireEvent.click(curriculumTab);
    await waitFor(() => {
      expect(curriculumTab).toHaveAttribute("data-state", "active");
    });
    fireEvent.click(screen.getByRole("switch", { name: /Toggle Curriculum Team access for Test Test/i }));

    await waitFor(() => {
      expect(teamAccessRequests).toEqual([{ teamKey: "curriculum", receiveTickets: true }]);
    });
  });

  it("surfaces live handoffs from ticketState even before chatIsActive is set", async () => {
    const originalFetch = globalThis.fetch;
    const waitingLiveTicket = {
      ...dashboardPayload.tickets.tickets[0],
      id: "KBC-000005",
      learnerName: "Waiting Learner",
      requesterName: "Waiting Learner",
      email: "waiting.learner@kentbusinesscollege.com",
      inquiryPreview: "Waiting for an available support agent",
      chatId: "CHAT-000005",
      chatIsActive: false,
      liveChatRequested: true,
      liveChatRequestedAt: "2026-06-14T10:05:00.000Z",
      chatState: "open",
      ticketState: {
        ticketType: "live_chat",
        workflowStage: "awaiting_agent",
        queueScope: "support",
        dashboardBucket: "live_chat",
        canShowConversation: true,
        canReceiveChat: true,
        resolutionReason: "",
      },
    };

    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;

      if (url.includes("/api/admin/tickets/metrics")) {
        return new Response(JSON.stringify(buildDashboardMetricsPayload([...dashboardPayload.tickets.tickets, waitingLiveTicket])), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      if (url.includes("/api/admin/tickets")) {
        return new Response(JSON.stringify({
          tickets: [...dashboardPayload.tickets.tickets, waitingLiveTicket],
        }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      return originalFetch(input, init);
    }) as typeof fetch;

    render(
      <MemoryRouter initialEntries={["/admin?view=console"]}>
        <AgentDashboard />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Waiting Learner")).toBeInTheDocument();
    expect(screen.getByText("CHAT-000005")).toBeInTheDocument();
  });

  it("opens the Admin Dashboard overview from the admin view deep link", async () => {
    render(
      <MemoryRouter initialEntries={["/admin?view=adminDashboard"]}>
        <AgentDashboard />
      </MemoryRouter>,
    );

    const adminPanel = await screen.findByRole("tabpanel");
    const adminOverview = screen.getByText("Overview").closest(".rounded-2xl");
    expect(adminOverview).not.toBeNull();
    expect(within(adminOverview as HTMLElement).getByText("4")).toBeInTheDocument();
    expect(within(adminOverview as HTMLElement).getByText("All Tickets")).toBeInTheDocument();
    expect(within(adminPanel).getByRole("heading", { name: "All Tickets" })).toBeInTheDocument();
    expect(within(adminPanel).getByText("KBC-000001")).toBeInTheDocument();
    expect(within(adminPanel).getByText("KBC-000002")).toBeInTheDocument();
    expect(within(adminPanel).getByText("KBC-000003")).toBeInTheDocument();
  });

  it("shows learning plan transfer alerts in the admin notifications panel", async () => {
    render(
      <MemoryRouter initialEntries={["/admin?view=adminDashboard"]}>
        <AgentDashboard />
      </MemoryRouter>,
    );

    await screen.findByRole("tabpanel");

    const notificationButton = screen.getAllByRole("button", { name: /transfer requests/i }).slice(-1)[0];
    expect(notificationButton).toBeTruthy();
    // The bell shows this admin's outstanding (undismissed) notifications.
    expect(within(notificationButton as HTMLElement).getByText("1")).toBeInTheDocument();

    fireEvent.pointerDown(notificationButton as HTMLElement, {
      button: 0,
      ctrlKey: false,
    });

    expect(await screen.findByText("Admin Notifications")).toBeInTheDocument();
    expect(await screen.findByText("Learning Plan Transfers")).toBeInTheDocument();
    expect(screen.getByText("Ticket KBC-000003")).toBeInTheDocument();
    expect(screen.getByText(/Support Desk to Learning Plan Team/i)).toBeInTheDocument();
  });

  const learningPlanTransferKey = "learning-plan-transfer:KBC-000003:2026-06-14T12:30:00.000Z:Support Desk:Learning Plan Team";

  function mockTicketListWithDismissals(dismissedNotificationKeys: string[], onRequest?: (url: string, init?: RequestInit) => Response | null) {
    const defaultFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const custom = onRequest?.(url, init);
      if (custom) {
        return custom;
      }
      if (url === "/api/admin/tickets") {
        return new Response(JSON.stringify({ ...dashboardPayload.tickets, dismissedNotificationKeys }), { status: 200 });
      }
      return defaultFetch(input, init);
    }) as typeof fetch;
  }

  function openNotificationBell() {
    const notificationButton = screen.getAllByRole("button", { name: /transfer requests/i }).slice(-1)[0] as HTMLElement;
    fireEvent.pointerDown(notificationButton, { button: 0, ctrlKey: false });
    return notificationButton;
  }

  it("hides notifications this admin already dismissed, including after a reload", async () => {
    mockTicketListWithDismissals([learningPlanTransferKey]);

    render(
      <MemoryRouter initialEntries={["/admin?view=adminDashboard"]}>
        <AgentDashboard />
      </MemoryRouter>,
    );
    await screen.findByRole("tabpanel");

    const notificationButton = screen.getAllByRole("button", { name: /transfer requests/i }).slice(-1)[0] as HTMLElement;
    await waitFor(() => expect(within(notificationButton).queryByText("1")).not.toBeInTheDocument());
    openNotificationBell();
    expect(await screen.findByText(/No admin notifications right now/i)).toBeInTheDocument();
    expect(screen.queryByText("Ticket KBC-000003")).not.toBeInTheDocument();
  });

  it("dismisses all notifications for the signed-in admin only", async () => {
    let dismissRequestBody: unknown = null;
    let dismissed = false;
    mockTicketListWithDismissals([], (url, init) => {
      if (url === "/api/admin/notifications/dismiss") {
        dismissRequestBody = JSON.parse(String(init?.body || "{}"));
        dismissed = true;
        return new Response(JSON.stringify({ dismissedNotificationKeys: [learningPlanTransferKey], skipped: 0 }), { status: 200 });
      }
      if (url === "/api/admin/tickets" && dismissed) {
        // The ticket and its notification event are unchanged on the server.
        return new Response(JSON.stringify({ ...dashboardPayload.tickets, dismissedNotificationKeys: [learningPlanTransferKey] }), { status: 200 });
      }
      return null;
    });

    render(
      <MemoryRouter initialEntries={["/admin?view=adminDashboard"]}>
        <AgentDashboard />
      </MemoryRouter>,
    );
    await screen.findByRole("tabpanel");

    const notificationButton = openNotificationBell();
    expect(await screen.findByText("Ticket KBC-000003")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Dismiss all" }));

    await waitFor(() => expect(dismissRequestBody).toEqual({
      notifications: [{ ticketId: "KBC-000003", kind: "learning-plan-transfer" }],
      clearAll: true,
    }));
    await waitFor(() => expect(within(notificationButton).queryByText("1")).not.toBeInTheDocument());
    // Only the notification goes; the ticket itself stays on the dashboard.
    expect(screen.getAllByText("KBC-000003").length).toBeGreaterThan(0);
  });

  it("shows the retention notice and deletion date for archived tickets", async () => {
    const archivedTicket = {
      ...dashboardPayload.tickets.tickets[0],
      id: "KBC-000201",
      isArchived: true,
      archivedAt: "2026-08-31T12:00:00.000Z",
      scheduledDeletionAt: "2026-11-30T12:00:00.000Z",
    };
    const defaultFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.startsWith("/api/admin/tickets/metrics")) {
        return new Response(JSON.stringify({ metrics: null }), { status: 200 });
      }
      if (url.startsWith("/api/admin/tickets") && !url.includes("/metrics")) {
        return new Response(JSON.stringify({ tickets: [...dashboardPayload.tickets.tickets, archivedTicket] }), { status: 200 });
      }
      return defaultFetch(input, init);
    }) as typeof fetch;

    render(<MemoryRouter initialEntries={["/admin"]}><AgentDashboard /></MemoryRouter>);
    await screen.findByRole("tabpanel");
    fireEvent.click(await screen.findByRole("button", { name: "Archived" }));

    expect(await screen.findByText("KBC-000201")).toBeInTheDocument();
    expect(screen.getByText(
      "Archived tickets are retained for 3 months from their archive date and are automatically deleted afterwards.",
    )).toBeInTheDocument();
    expect(screen.getByText(/^Archived .*2026/)).toBeInTheDocument();
    expect(screen.getByText(/^Deletes .*2026/)).toBeInTheDocument();
  });

  it("shows coverage and routed tickets in the Learning Plan Team tab", async () => {
    render(
      <MemoryRouter initialEntries={["/admin?view=coverage"]}>
        <AgentDashboard />
      </MemoryRouter>,
    );

    const learningPlanPanel = await screen.findByRole("tabpanel");
    const learningPlanOverview = screen.getByText("Overview").closest(".rounded-2xl");
    expect(learningPlanOverview).not.toBeNull();
    expect(within(learningPlanOverview as HTMLElement).getByText("3")).toBeInTheDocument();
    expect(within(learningPlanOverview as HTMLElement).getByText("Learning Plan Tickets")).toBeInTheDocument();
    expect(within(learningPlanOverview as HTMLElement).getByText("2")).toBeInTheDocument();
    expect(within(learningPlanOverview as HTMLElement).getByText("Cov")).toBeInTheDocument();
    expect(within(learningPlanOverview as HTMLElement).getByText("1")).toBeInTheDocument();
    expect(within(learningPlanOverview as HTMLElement).getByText("Oth")).toBeInTheDocument();
    expect(within(learningPlanPanel).getByText("Coverage Tickets")).toBeInTheDocument();
    expect(within(learningPlanPanel).getByText("KBC-000002")).toBeInTheDocument();
    expect(within(learningPlanPanel).queryByText("KBC-000003")).not.toBeInTheDocument();
    expect(within(learningPlanPanel).queryByText("KBC-000001")).not.toBeInTheDocument();

    fireEvent.click(within(learningPlanPanel).getByRole("button", { name: /others/i }));

    await waitFor(() => {
      expect(within(learningPlanPanel).getByText("Other Learning Plan Tickets")).toBeInTheDocument();
    });

    expect(within(learningPlanPanel).getByText("KBC-000003")).toBeInTheDocument();
    expect(within(learningPlanPanel).queryByText("KBC-000002")).not.toBeInTheDocument();
  });

  it("defaults Learning Plan Team coverage tickets to Highest Priority session-date sorting", async () => {
    render(
      <MemoryRouter initialEntries={["/admin?view=coverage"]}>
        <AgentDashboard />
      </MemoryRouter>,
    );

    const learningPlanPanel = await screen.findByRole("tabpanel");
    const getCoverageRows = () => (
      within(learningPlanPanel)
        .getAllByRole("button")
        .filter((row) => /KBC-\d+/.test(row.textContent || ""))
    );
    const getCoverageRow = (ticketId: string) => {
      const row = getCoverageRows().find((candidate) => within(candidate).queryByText(ticketId));
      if (!row) {
        throw new Error(`Coverage row ${ticketId} was not found.`);
      }

      return row;
    };
    const getCoverageRowIndex = (ticketId: string) => getCoverageRows().indexOf(getCoverageRow(ticketId));

    expect(within(learningPlanPanel).getByLabelText("Sort tickets")).toHaveTextContent("Highest Priority");
    expect(getCoverageRowIndex("KBC-000004")).toBeLessThan(getCoverageRowIndex("KBC-000002"));
    expect(within(getCoverageRow("KBC-000004")).getByLabelText("Date Friday 18 Jun 2099")).toBeInTheDocument();
  });

  it("shows only Learning Plan Team when a support desk ticket is transferred", async () => {
    render(
      <MemoryRouter initialEntries={["/admin"]}>
        <AgentDashboard />
      </MemoryRouter>,
    );

    await screen.findByText("Overview");

    fireEvent.pointerDown(screen.getByRole("button", { name: /Transfer ticket KBC-000001 to another team/i }), {
      button: 0,
      ctrlKey: false,
    });

    expect(await screen.findByRole("menuitem", { name: /Learning Plan Team/i })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /Support Desk/i })).not.toBeInTheDocument();
  });

  it("shows Support Desk as a return option for Learning Plan Team tickets in admin dashboard", async () => {
    render(
      <MemoryRouter initialEntries={["/admin?view=coverage"]}>
        <AgentDashboard />
      </MemoryRouter>,
    );

    const learningPlanPanel = await screen.findByRole("tabpanel");
    fireEvent.click(within(learningPlanPanel).getByRole("button", { name: /others/i }));

    await waitFor(() => {
      expect(within(learningPlanPanel).getByText("KBC-000003")).toBeInTheDocument();
    });

    fireEvent.pointerDown(within(learningPlanPanel).getByRole("button", { name: /Return ticket KBC-000003 to another team/i }), {
      button: 0,
      ctrlKey: false,
    });

    expect(await screen.findByRole("menuitem", { name: /Support Desk/i })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /Learning Plan Team/i })).not.toBeInTheDocument();
  });

  it("closes a coverage ticket from the close dialog when a note is provided", async () => {
    const originalFetch = globalThis.fetch;
    const patchRequests: Array<{ url: string; body: Record<string, unknown> }> = [];

    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;

      if (url.endsWith("/api/admin/tickets/KBC-000002") && (!init?.method || init.method === "GET")) {
        return new Response(JSON.stringify(buildRuntimeTicketDetail("KBC-000002")), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      if (url.endsWith("/api/admin/tickets/KBC-000002") && init?.method === "PATCH") {
        const parsedBody = JSON.parse(String(init.body || "{}")) as Record<string, unknown>;
        patchRequests.push({ url, body: parsedBody });
        const detail = buildRuntimeTicketDetail("KBC-000002");

        return new Response(JSON.stringify({
          ...detail,
          ticket: {
            ...detail.ticket,
            status: "Closed",
            statusReason: "Closed via Agent",
            closedAt: "2026-06-20T16:00:00.000Z",
            updatedAt: "2026-06-20T16:00:00.000Z",
          },
        }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      return originalFetch(input, init);
    }) as typeof fetch;

    render(
      <MemoryRouter initialEntries={["/admin?view=coverage"]}>
        <AgentDashboard />
      </MemoryRouter>,
    );

    const learningPlanPanel = await screen.findByRole("tabpanel");
    const coverageRow = within(learningPlanPanel)
      .getAllByRole("button")
      .find((candidate) => /KBC-000002/.test(candidate.textContent || ""));
    expect(coverageRow).toBeTruthy();
    fireEvent.click(coverageRow as HTMLElement);

    expect(await screen.findByText("Coverage Cards")).toBeInTheDocument();

    const saveTicketButton = screen.getByRole("button", { name: /Save Ticket/i });
    const workspaceFooter = saveTicketButton.parentElement;
    expect(workspaceFooter).not.toBeNull();
    fireEvent.click(within(workspaceFooter as HTMLElement).getByRole("button", { name: /^Close$/i }));
    expect(await screen.findByText("Close Ticket KBC-000002")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Internal note *"), {
      target: { value: "Closing this coverage ticket after manual review." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Close ticket without email" }));

    await waitFor(() => {
      expect(patchRequests).toHaveLength(1);
    });

    expect(patchRequests[0].body.status).toBe("Closed");
    expect(patchRequests[0].body.statusReason).toBe("Closed via Agent");
    expect(patchRequests[0].body.note).toBe("Closing this coverage ticket after manual review.");
  });

  it("keeps the internal note after Save Changes so Close reuses it without retyping", async () => {
    const originalFetch = globalThis.fetch;
    const patchRequests: Array<{ body: Record<string, unknown> }> = [];

    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;

      if (url.endsWith("/api/admin/tickets/KBC-000001") && (!init?.method || init.method === "GET")) {
        return new Response(JSON.stringify(buildRuntimeTicketDetail("KBC-000001")), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      if (url.endsWith("/api/admin/tickets/KBC-000001") && init?.method === "PATCH") {
        const body = JSON.parse(String(init.body || "{}")) as Record<string, unknown>;
        patchRequests.push({ body });
        const detail = buildRuntimeTicketDetail("KBC-000001");
        return new Response(JSON.stringify({
          ...detail,
          ticket: {
            ...detail.ticket,
            status: (body.status as string) || detail.ticket.status,
            updatedAt: "2026-06-20T16:00:00.000Z",
          },
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }

      return originalFetch(input, init);
    }) as typeof fetch;

    render(
      <MemoryRouter initialEntries={["/admin"]}>
        <AgentDashboard />
      </MemoryRouter>,
    );

    // Open the ticket from the dashboard table.
    await screen.findByText("KBC-000001");
    const ticketRow = screen.getAllByRole("button")
      .find((candidate) => candidate.tagName === "TR" && /KBC-000001/.test(candidate.textContent || ""));
    expect(ticketRow).toBeTruthy();
    fireEvent.click(ticketRow as HTMLElement);

    const noteField = await screen.findByPlaceholderText(/Add an internal note before closing/i);

    // Type the note once and Save.
    fireEvent.change(noteField, { target: { value: "Resolved and verified with the learner." } });
    fireEvent.click(screen.getByRole("button", { name: /Save Changes/i }));

    await waitFor(() => {
      expect(patchRequests).toHaveLength(1);
    });
    expect(patchRequests[0].body.note).toBe("Resolved and verified with the learner.");

    // The note must still be in the field (not cleared) so Close can reuse it.
    await waitFor(() => {
      expect((noteField as HTMLTextAreaElement).value).toBe("Resolved and verified with the learner.");
    });

    // Close WITHOUT retyping the note (the footer button, not the sheet's X).
    const closeButton = screen.getAllByRole("button", { name: /Close/i })
      .find((candidate) => !candidate.className.includes("absolute"));
    expect(closeButton).toBeTruthy();
    fireEvent.click(closeButton as HTMLElement);
    fireEvent.click(await screen.findByRole("button", { name: "Close ticket without email" }));

    await waitFor(() => {
      expect(patchRequests).toHaveLength(2);
    });
    expect(patchRequests[1].body.status).toBe("Closed");
    expect(patchRequests[1].body.note).toBe("Resolved and verified with the learner.");

    globalThis.fetch = originalFetch;
  });

  it("opens the Attachment column popup with the requester's note and images", async () => {
    const originalFetch = globalThis.fetch;

    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;

      if (url.endsWith("/api/admin/tickets/KBC-000001") && (!init?.method || init.method === "GET")) {
        const detail = buildRuntimeTicketDetail("KBC-000001");
        return new Response(JSON.stringify({
          ...detail,
          ticket: { ...detail.ticket, inquiry: "A learner can't submit her assignment" },
          attachments: [
            {
              id: 501,
              name: "screenshot.png",
              mimeType: "image/png",
              size: 2048,
              storageUrl: "/media/support_attachments/screenshot.png",
              metadata: {},
              createdAt: "2026-06-14T10:00:00.000Z",
            },
          ],
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }

      return originalFetch(input, init);
    }) as typeof fetch;

    render(
      <MemoryRouter initialEntries={["/admin"]}>
        <AgentDashboard />
      </MemoryRouter>,
    );

    await screen.findByText("KBC-000001");

    // Click the Attachment column button for the ticket (not the row itself).
    const attachmentButton = await screen.findByRole("button", {
      name: /View note and images for ticket KBC-000001/i,
    });
    fireEvent.click(attachmentButton);

    const dialog = await screen.findByRole("dialog");
    // The requester's note shows in the popup.
    await waitFor(() => {
      expect(within(dialog).getByText("A learner can't submit her assignment")).toBeInTheDocument();
    });
    // The attached image is listed by name and rendered as a thumbnail.
    expect(within(dialog).getByText("screenshot.png")).toBeInTheDocument();
    expect(within(dialog).getByAltText("screenshot.png")).toBeInTheDocument();

    globalThis.fetch = originalFetch;
  });
});
