import { render, screen, waitFor } from "@testing-library/react";
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
});
