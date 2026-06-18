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
    ],
  },
};

function buildDashboardAccountsPayload() {
  return {
    accounts: {
      accounts: dashboardPayload.accounts.accounts.map((account) => ({
        ...account,
        role: runtimeAdminSession.role,
        legacySupportAccess: runtimeAdminSession.legacySupportAccess,
        legacyOperationsAccess: runtimeAdminSession.legacyOperationsAccess,
        legacyAdminAccess: runtimeAdminSession.legacyAdminAccess,
        entraDirectoryAdmin: runtimeAdminSession.entraDirectoryAdmin,
      })),
      agents: dashboardPayload.accounts.agents.map((agent) => ({
        ...agent,
        role: runtimeAdminSession.role,
        legacySupportAccess: runtimeAdminSession.legacySupportAccess,
        legacyOperationsAccess: runtimeAdminSession.legacyOperationsAccess,
        legacyAdminAccess: runtimeAdminSession.legacyAdminAccess,
        entraDirectoryAdmin: runtimeAdminSession.entraDirectoryAdmin,
      })),
    },
  };
}

describe("AgentDashboard runtime", () => {
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

    global.fetch = vi.fn(async (input: RequestInfo | URL) => {
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
  });

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
      "Manage Agents",
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
      "Manage Agents",
    ]);
    expect(screen.getByRole("tab", { name: /Admin Dashboard/i })).toHaveAttribute("data-state", "active");
    expect(screen.getByRole("tab", { name: /Support Dashboard/i })).toHaveAttribute("data-state", "inactive");
    expect(screen.getByRole("tab", { name: /Learning Plan Team/i })).toHaveAttribute("data-state", "inactive");
    expect(screen.getByRole("tab", { name: /Chat Console/i })).toHaveAttribute("data-state", "inactive");
    expect(within(adminPanel).getByRole("heading", { name: "All Tickets" })).toBeInTheDocument();
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

    const notificationButton = screen.getAllByRole("button", { name: /transfer requests/i }).at(-1);
    expect(notificationButton).toBeTruthy();
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
});
