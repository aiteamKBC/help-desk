import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { SupportProvider } from "@/context/SupportContext";
import MyTickets from "@/pages/support/MyTickets";

const supportStorageKey = "kbc-support-state-v1";

describe("MyTickets", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.localStorage.setItem(supportStorageKey, JSON.stringify({
      ticket: {
        learnerName: "Ayman Badewi",
        email: "ayman.badewi@kentbusinesscollege.com",
        requesterRole: "user",
      },
      bookingSummary: null,
    }));

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      learner: { fullName: "Ayman Badewi" },
      tickets: [
        {
          id: "KBC-000877",
          email: "ayman.badewi@kentbusinesscollege.com",
          category: "Technical",
          technicalSubcategory: "AI Team",
          subject: "AI Team session access issue",
          inquiry: "Cannot access the session",
          status: "Closed",
          assignedAgentId: 3,
          assignedAgentName: "Omar Helmy",
          assignedTeam: "Support Desk",
          slaStatus: "On Track",
          createdAt: "2026-10-13T09:00:00Z",
          updatedAt: "2026-10-14T09:00:00Z",
        },
        {
          id: "KBC-000851",
          email: "ayman.badewi@kentbusinesscollege.com",
          category: "Technical",
          technicalSubcategory: "Enrolment",
          subject: "Statement of enrolment not received",
          inquiry: "The statement has not arrived",
          status: "Pending",
          assignedAgentId: 4,
          assignedAgentName: "Sara Whitfield",
          assignedTeam: "Support Desk",
          slaStatus: "On Track",
          createdAt: "2026-10-10T09:00:00Z",
          updatedAt: "2026-10-11T09:00:00Z",
        },
      ],
    }), { status: 200 })));
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    window.localStorage.clear();
  });

  it("renders ticket metrics, agent details and filters the table", async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/support/my-tickets"]}>
          <SupportProvider>
            <MyTickets />
          </SupportProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => expect(screen.getByText("KBC-000877")).toBeInTheDocument());
    expect(screen.getByText("Omar Helmy")).toBeInTheDocument();
    expect(screen.getByText("14 Oct 2026")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /All Tickets\s*2/ })).toHaveAttribute("aria-selected", "true");

    fireEvent.click(screen.getByRole("tab", { name: /Pending\s*1/ }));

    expect(screen.getByText("KBC-000851")).toBeInTheDocument();
    expect(screen.queryByText("KBC-000877")).not.toBeInTheDocument();
  });
});
