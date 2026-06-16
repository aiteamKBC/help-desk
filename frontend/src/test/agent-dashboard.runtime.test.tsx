import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import AgentDashboard from "@/pages/support/AgentDashboard";

const adminSession = {
  id: 27,
  username: "ayman.badewi",
  fullName: "Ayman Badewi",
  email: "ayman.badewi@kentbusinesscollege.com",
  role: "superadmin",
  instanceId: "runtime-test-session",
  sessionActive: true,
  consoleStatus: "Off",
  selectedConsoleStatus: "Off",
  legacySupportAccess: false,
  legacyOperationsAccess: false,
  legacyAdminAccess: true,
  entraDirectoryAdmin: true,
};

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
        teamsCallRequested: false,
        latestEscalationClosure: null,
        latestTransferDecision: null,
        latestCoverageTutorResponse: null,
        documentation: {
          inquiry: [
            "Coverage session request",
            "Tutor: Sara Ahmed",
            "Module: Digital Marketing",
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
        role: "superadmin",
        isActive: true,
        sessionActive: true,
        legacySupportAccess: false,
        legacyOperationsAccess: false,
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
        role: "superadmin",
        isActive: true,
        sessionActive: true,
        legacySupportAccess: false,
        legacyOperationsAccess: false,
        legacyAdminAccess: true,
        entraDirectoryAdmin: true,
        consoleStatus: "Off",
        selectedConsoleStatus: "Off",
      },
    ],
  },
};

describe("AgentDashboard runtime", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    window.localStorage.clear();
    window.sessionStorage.setItem("support_admin_session", JSON.stringify(adminSession));

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
        return new Response(JSON.stringify({ ok: true, sessionActive: true, admin: adminSession }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      if (url.includes("/api/admin/session")) {
        return new Response(JSON.stringify({ admin: adminSession }), {
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
        return new Response(JSON.stringify(dashboardPayload.accounts), {
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

  it("shows coverage and routed tickets in the Learning Plan Team tab", async () => {
    render(
      <MemoryRouter initialEntries={["/admin?view=coverage"]}>
        <AgentDashboard />
      </MemoryRouter>,
    );

    const learningPlanPanel = await screen.findByRole("tabpanel");
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

    fireEvent.pointerDown(within(learningPlanPanel).getByRole("button", { name: /Transfer ticket KBC-000003 to another team/i }), {
      button: 0,
      ctrlKey: false,
    });

    expect(await screen.findByRole("menuitem", { name: /Support Desk/i })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /Learning Plan Team/i })).not.toBeInTheDocument();
  });
});
