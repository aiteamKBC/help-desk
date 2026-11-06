import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { SupportProvider } from "@/context/SupportContext";
import TicketStatus from "@/pages/support/TicketStatus";
import InquiryDetails from "@/pages/support/InquiryDetails";

const supportStorageKey = "kbc-support-state-v2";

/**
 * Reproduces the reported flow: a Pending ticket on the Status step, the user
 * clicks back to step 2 (Inquiry) and returns to step 4 (Status) using ONLY the
 * step navigation (no close/end button). The final step must NOT flip to
 * "Completed" — it should stay on the live "Pending" status.
 */

type ChatHistoryTicket = {
  status: "Open" | "Pending" | "Closed";
  statusReason: string;
  assignedTeam?: string;
  slaStatus?: string;
  createdAt?: string;
  chatState?: "open" | "closed";
  liveChatRequested?: boolean;
  isQuickTicket?: boolean;
};

const renderFlow = () =>
  render(
    <MemoryRouter initialEntries={["/support/status"]}>
      <SupportProvider>
        <Routes>
          <Route path="/" element={<div>home</div>} />
          <Route path="/support/inquiry" element={<InquiryDetails />} />
          <Route path="/support/options" element={<div>options</div>} />
          <Route path="/support/status" element={<TicketStatus />} />
        </Routes>
      </SupportProvider>
    </MemoryRouter>,
  );

const stubFetch = (chatHistoryTicket: ChatHistoryTicket, bookingSummary: unknown = null) => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/chat-history")) {
        return {
          ok: true,
          json: async () => ({
            ticket: chatHistoryTicket,
            bookingSummary,
            historyCount: 1,
            chatHistory: [],
          }),
        } as Response;
      }
      // Any other endpoint the flow may poll (learner search, availability, ...).
      return { ok: true, json: async () => ({}) } as Response;
    }),
  );
};

const seedTicket = (overrides: Record<string, unknown> = {}) => {
  window.localStorage.setItem(
    supportStorageKey,
    JSON.stringify({
      ticket: {
        id: "KBC-REPRO-1",
        learnerName: "Repro Learner",
        email: "repro@example.com",
        requesterRole: "user",
        requesterSource: "microsoft_entra",
        category: "Technical",
        technicalSubcategory: "LMS",
        subject: "Repro",
        inquiry: "Reproduction of the status-step bug.",
        status: "Pending",
        statusReason: "Quick Ticket",
        assignedAgentId: null,
        assignedTeam: "Support Desk",
        slaStatus: "Pending Review",
        createdAt: "2026-07-06T12:00:00+00:00",
        chatState: "closed",
        liveChatRequested: false,
        isQuickTicket: true,
        ...overrides,
      },
    }),
  );
};

const stepButtonByLabel = (label: string) => {
  const labelNode = screen.getByText(label);
  const container = labelNode.parentElement as HTMLElement;
  const button = container.querySelector("button");
  if (!button) {
    throw new Error(`No step button found for label "${label}"`);
  }
  return button;
};

describe("Support flow — status step after back-navigation", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    window.localStorage.clear();
  });

  it("keeps a Pending ticket on 'Pending' after going back to Inquiry and returning (no close action)", async () => {
    stubFetch({
      status: "Pending",
      statusReason: "Quick Ticket",
      assignedTeam: "Support Desk",
      slaStatus: "Pending Review",
      createdAt: "2026-07-06T12:00:00+00:00",
      chatState: "closed",
      liveChatRequested: false,
      isQuickTicket: true,
    });
    seedTicket();

    renderFlow();

    // On the Status step the final step must read "Pending", never "Completed".
    await waitFor(() => {
      expect(screen.getAllByText("Pending").length).toBeGreaterThan(0);
    });
    expect(screen.queryByText("Completed")).not.toBeInTheDocument();

    // Pure navigation: click step 2 (Inquiry).
    fireEvent.click(stepButtonByLabel("Inquiry"));
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /support inquiry/i })).toBeInTheDocument();
    });

    // Return to step 4 (Status) via the step indicator (button shows "4").
    fireEvent.click(screen.getByRole("button", { name: "4" }));

    await waitFor(() => {
      expect(screen.getAllByText("Pending").length).toBeGreaterThan(0);
    });
    // The bug: this used to flip to "Completed". It must not.
    expect(screen.queryByText("Completed")).not.toBeInTheDocument();
  });

  it("does NOT mark the final step Completed when a Pending ticket carries a stale booking summary", async () => {
    // Guards the subtler path where a lingering booking summary makes the step
    // read "Completed" for a ticket that is still Pending.
    stubFetch(
      {
        status: "Pending",
        statusReason: "Quick Ticket",
        assignedTeam: "Support Desk",
        slaStatus: "Pending Review",
        createdAt: "2026-07-06T12:00:00+00:00",
        chatState: "closed",
        liveChatRequested: false,
        isQuickTicket: true,
      },
      {
        meetingId: "mtg-1",
        reservationConfirmed: false,
        startDateTime: "2026-07-07T12:00:00+00:00",
        endDateTime: "2026-07-07T12:30:00+00:00",
      },
    );
    seedTicket();

    renderFlow();

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalled();
    });
    expect(screen.queryByText("Completed")).not.toBeInTheDocument();
  });
});
