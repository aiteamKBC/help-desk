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

  it("renders the quick call / quick ticket options for coach requests", async () => {
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

    expect(screen.getByText("Choose quick call or quick ticket")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("Call on Microsoft Teams")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /submit quick ticket/i })).toBeInTheDocument();
  });
});
