import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { SupportProvider } from "@/context/SupportContext";
import SupportOptions from "@/pages/support/SupportOptions";

const supportStorageKey = "kbc-support-state-v1";

describe("SupportOptions", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          callUrl: "https://teams.microsoft.com/l/call/0/0",
          targetLabel: "Support Admin",
          message: "",
        }),
      }),
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    window.localStorage.clear();
  });

  it("renders all support paths plus Teams call for coach requests", async () => {
    window.localStorage.setItem(
      supportStorageKey,
      JSON.stringify({
        ticket: {
          id: "KBC-000246",
          learnerName: "hamamo",
          email: "hamamo@gmail.com",
          requesterRole: "coach",
          category: "Technical",
          technicalSubcategory: "Teams",
          inquiry: "Need a Teams support call",
          evidence: [],
          status: "Open",
          statusReason: "",
          assignedAgentId: null,
          assignedTeam: "Unassigned",
          slaStatus: "Pending Review",
          createdAt: "2026-05-19T11:52:00+00:00",
          chatState: "open",
          liveChatRequested: false,
          chatHistory: [],
        },
        bookingSummary: null,
      }),
    );

    render(
      <MemoryRouter initialEntries={["/support/options"]}>
        <SupportProvider>
          <SupportOptions />
        </SupportProvider>
      </MemoryRouter>,
    );

    expect(screen.getByText("Choose how you want to continue")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("Call on Microsoft Teams")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /chatbot/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /live chat/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /booking session/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /submit ticket directly/i })).toBeInTheDocument();
  });

  it("renders direct support actions inside one card for learner requests", () => {
    window.localStorage.setItem(
      supportStorageKey,
      JSON.stringify({
        ticket: {
          id: "KBC-000247",
          learnerName: "omar2",
          email: "omar2@gmail.com",
          requesterRole: "user",
          category: "Technical",
          technicalSubcategory: "Others",
          inquiry: "Need help with another system",
          evidence: [],
          status: "Open",
          statusReason: "",
          assignedAgentId: null,
          assignedTeam: "Unassigned",
          slaStatus: "Pending Review",
          createdAt: "2026-05-23T11:52:00+00:00",
          chatState: "open",
          liveChatRequested: false,
          chatHistory: [],
        },
        bookingSummary: null,
      }),
    );

    render(
      <MemoryRouter initialEntries={["/support/options"]}>
        <SupportProvider>
          <SupportOptions />
        </SupportProvider>
      </MemoryRouter>,
    );

    expect(screen.getByText("Choose how you want to continue")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /chatbot/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /live chat/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /booking session/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /submit ticket directly/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /call on microsoft teams/i })).not.toBeInTheDocument();
  });
});
