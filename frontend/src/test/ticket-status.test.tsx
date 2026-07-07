import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { SupportProvider } from "@/context/SupportContext";
import TicketStatus from "@/pages/support/TicketStatus";

const supportStorageKey = "kbc-support-state-v2";

describe("TicketStatus", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    window.localStorage.clear();
  });

  it("shows chat transcript actions for closed chatbot tickets with history", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          ticket: {
            status: "Closed",
            statusReason: "Closed via Chatbot",
            assignedTeam: "Support Desk",
            slaStatus: "Resolved",
            createdAt: "2026-07-06T12:00:00+00:00",
            chatState: "closed",
            liveChatRequested: false,
          },
          bookingSummary: null,
          historyCount: 4,
        }),
      }),
    );
    window.localStorage.setItem(
      supportStorageKey,
      JSON.stringify({
        ticket: {
          id: "KBC-000610",
          learnerName: "Omar Badr",
          email: "omar@example.com",
          requesterRole: "user",
          requesterSource: "microsoft_entra",
          category: "Technical",
          technicalSubcategory: "LMS",
          subject: "test",
          inquiry: "testtesttest",
          status: "Closed",
          statusReason: "Closed via Chatbot",
          assignedAgentId: null,
          assignedTeam: "Support Desk",
          slaStatus: "Resolved",
          createdAt: "2026-07-06T12:00:00+00:00",
          chatState: "closed",
          liveChatRequested: false,
        },
      }),
    );

    render(
      <MemoryRouter initialEntries={["/support/status"]}>
        <SupportProvider>
          <TicketStatus />
        </SupportProvider>
      </MemoryRouter>,
    );

    expect(screen.queryByRole("button", { name: /view ticket details/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /step 2 \(inquiry\)/i })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /view chat transcript/i })).toBeInTheDocument();
    });
  });

  it("does not show a chat transcript action for direct tickets without chat history", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          ticket: {
            status: "Pending",
            statusReason: "Quick Ticket",
            assignedTeam: "Ai Team",
            slaStatus: "Pending Review",
            createdAt: "2026-07-06T12:00:00+00:00",
            chatState: "closed",
            liveChatRequested: false,
          },
          bookingSummary: null,
          historyCount: 1,
        }),
      }),
    );
    window.localStorage.setItem(
      supportStorageKey,
      JSON.stringify({
        ticket: {
          id: "KBC-000611",
          learnerName: "Omar Badr",
          email: "omar@example.com",
          requesterRole: "user",
          requesterSource: "microsoft_entra",
          category: "Technical",
          technicalSubcategory: "AI Team",
          subject: "AI Team access",
          inquiry: "Cannot access AI Team.",
          aiTeamPersonName: "Ahmed Hamamo",
          aiTeamPersonEmail: "ahmed@example.com",
          status: "Pending",
          statusReason: "Quick Ticket",
          assignedAgentId: null,
          assignedTeam: "Ai Team",
          slaStatus: "Pending Review",
          createdAt: "2026-07-06T12:00:00+00:00",
          chatState: "closed",
          liveChatRequested: false,
        },
      }),
    );

    render(
      <MemoryRouter initialEntries={["/support/status"]}>
        <SupportProvider>
          <TicketStatus />
        </SupportProvider>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith("/api/tickets/KBC-000611/chat-history");
    });
    expect(screen.queryByRole("button", { name: /view chat transcript/i })).not.toBeInTheDocument();
  });
});
