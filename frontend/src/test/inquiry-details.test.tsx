import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { SupportProvider } from "@/context/SupportContext";
import { buildCoverageInquiry, parseCoverageInquiry } from "@/lib/coverageSupport";
import InquiryDetails from "@/pages/support/InquiryDetails";

const supportStorageKey = "kbc-support-state-v2";

describe("InquiryDetails", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);

        if (url.includes("/api/coverage-options?type=tutors")) {
          return Promise.resolve({
            ok: true,
            json: async () => ({ options: ["Ray", "Nathan"] }),
          });
        }

        if (url.includes("/api/coverage-options?type=modules") && url.includes("tutor=Ray")) {
          return Promise.resolve({
            ok: true,
            json: async () => ({ options: ["APM"] }),
          });
        }

        if (url.includes("/api/coverage-options?type=times") && url.includes("module=APM") && url.includes("tutor=Ray")) {
          return Promise.resolve({
            ok: true,
            json: async () => ({ options: ["Friday 12:00 - 14:00 | Fri-12 | Feb 2026"] }),
          });
        }

        if (
          url.includes("/api/coverage-options?type=session-dates") &&
          url.includes("module=APM") &&
          url.includes("tutor=Ray") &&
          url.includes("time=Friday+12%3A00+-+14%3A00+%7C+Fri-12+%7C+Feb+2026")
        ) {
          return Promise.resolve({
            ok: true,
            json: async () => ({ options: ["Friday 06 Jun 2026", "Friday 13 Jun 2026"] }),
          });
        }

        if (url === "/api/tickets") {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              ticket: {
                id: "KBC-000321",
                learnerName: "Omar Two",
                email: "omar2@gmail.com",
                requesterRole: "user",
                requesterSource: "microsoft_entra",
                category: "Technical",
                technicalSubcategory: "Coverage",
                inquiry: buildCoverageInquiry({
                  tutor: "Ray",
                  module: "APM",
                  time: "Friday 12:00 - 14:00 | Fri-12 | Feb 2026",
                  sessionDates: ["Friday 06 Jun 2026"],
                  sessionSubject: "Assessment review",
                }),
                status: "Open",
                assignedTeam: "Unassigned",
                slaStatus: "Pending Review",
                createdAt: "2026-06-03T12:00:00+00:00",
                chatState: "open",
                liveChatRequested: false,
              },
            }),
          });
        }

        if (url === "/api/tickets/KBC-000321/chat-history") {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              ticket: {
                status: "Pending",
                statusReason: "Quick Ticket",
                assignedTeam: "Unassigned",
                slaStatus: "Pending Review",
                createdAt: "2026-06-03T12:00:00+00:00",
                chatState: "closed",
              },
            }),
          });
        }

        return Promise.resolve({
          ok: true,
          json: async () => ({ options: [] }),
        });
      }),
    );
    window.localStorage.setItem(
      supportStorageKey,
      JSON.stringify({
        ticket: {
          email: "omar2@gmail.com",
          requesterRole: "user",
          technicalSubcategory: "Others",
        },
      }),
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    window.localStorage.clear();
  });

  it("builds and parses session numbers in the coverage inquiry", () => {
    const inquiry = buildCoverageInquiry({
      tutor: "Ray",
      module: "APM",
      time: "Friday 12:00 - 14:00 | Fri-12 | Feb 2026",
      sessionDates: ["Friday 06 Jun 2026", "Friday 13 Jun 2026"],
      sessionNumbers: ["1", "2"],
      sessionSubjects: ["Assessment review", "Mock exam"],
      sessionSubject: "",
    });

    expect(inquiry).toContain("Session Number: 1; 2");
    expect(inquiry).toContain("Session Subject: Assessment review; Mock exam");
    expect(parseCoverageInquiry(inquiry)).toEqual({
      tutor: "Ray",
      module: "APM",
      time: "Friday 12:00 - 14:00 | Fri-12 | Feb 2026",
      sessionDates: ["Friday 06 Jun 2026", "Friday 13 Jun 2026"],
      sessionNumbers: ["1", "2"],
      sessionSubjects: ["Assessment review", "Mock exam"],
      sessionSubject: "Assessment review; Mock exam",
    });
  });

  it("renders Others as a supported inquiry category", () => {
    render(
      <MemoryRouter initialEntries={["/support/inquiry"]}>
        <SupportProvider>
          <InquiryDetails />
        </SupportProvider>
      </MemoryRouter>,
    );

    expect(screen.getByRole("combobox")).toHaveTextContent("Others");
    expect(screen.getAllByText("Others").length).toBeGreaterThan(0);
  });

  it("accepts PowerPoint files as supporting evidence", async () => {
    const { container } = render(
      <MemoryRouter initialEntries={["/support/inquiry"]}>
        <SupportProvider>
          <InquiryDetails />
        </SupportProvider>
      </MemoryRouter>,
    );
    const fileInput = container.querySelector<HTMLInputElement>('input[type="file"]');
    expect(fileInput).toBeInTheDocument();

    const presentationFile = new File(["slides"], "coverage-plan.pptx", {
      type: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    });

    fireEvent.change(fileInput!, { target: { files: [presentationFile] } });

    expect(await screen.findByText("coverage-plan.pptx")).toBeInTheDocument();
  });

  it("renders the coverage-specific fields when Coverage is selected", async () => {
    window.localStorage.setItem(
      supportStorageKey,
      JSON.stringify({
        ticket: {
          email: "omar2@gmail.com",
          requesterRole: "user",
          requesterSource: "microsoft_entra",
          subject: "Coverage session request",
          technicalSubcategory: "Coverage",
          inquiry: buildCoverageInquiry({
            tutor: "Ray",
            module: "APM",
            time: "Friday 12:00 - 14:00 | Fri-12 | Feb 2026",
            sessionDates: ["Friday 06 Jun 2026"],
            sessionNumbers: ["1"],
            sessionSubject: "Assessment review",
          }),
        },
      }),
    );

    render(
      <MemoryRouter initialEntries={["/support/inquiry"]}>
        <SupportProvider>
          <InquiryDetails />
        </SupportProvider>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalled();
    });

    expect(screen.getAllByText("Tutor").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Module").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Time").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Session Date").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Session No.").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Friday 06 Jun 2026").length).toBeGreaterThan(0);
    expect(screen.getByDisplayValue("1")).toBeInTheDocument();
    expect(screen.getByLabelText("Session Subject")).toHaveValue("Assessment review");
    expect(screen.queryByText("Generated Inquiry Preview")).not.toBeInTheDocument();
  });

  it("hides Coverage for standard KBC learner accounts", () => {
    window.localStorage.setItem(
      supportStorageKey,
      JSON.stringify({
        ticket: {
          email: "learner@example.com",
          requesterRole: "user",
          requesterSource: "kbc_users_data",
          technicalSubcategory: "Others",
        },
      }),
    );

    render(
      <MemoryRouter initialEntries={["/support/inquiry"]}>
        <SupportProvider>
          <InquiryDetails />
        </SupportProvider>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("combobox"));
    expect(screen.queryByText("Coverage")).not.toBeInTheDocument();
  });

  it("submits coverage directly to status after creating the ticket", async () => {
    window.localStorage.setItem(
      supportStorageKey,
      JSON.stringify({
        ticket: {
          email: "omar2@gmail.com",
          requesterRole: "user",
          requesterSource: "microsoft_entra",
          subject: "Coverage session request",
          technicalSubcategory: "Coverage",
          inquiry: buildCoverageInquiry({
            tutor: "Ray",
            module: "APM",
            time: "Friday 12:00 - 14:00 | Fri-12 | Feb 2026",
            sessionDates: ["Friday 06 Jun 2026"],
            sessionNumbers: ["1"],
            sessionSubject: "Assessment review",
          }),
        },
      }),
    );

    render(
      <MemoryRouter initialEntries={["/support/inquiry"]}>
        <SupportProvider>
          <InquiryDetails />
        </SupportProvider>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /next/i })).toBeEnabled();
    });

    fireEvent.click(screen.getByRole("button", { name: /next/i }));

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/tickets",
        expect.objectContaining({
          method: "POST",
        }),
      );
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/tickets/KBC-000321/chat-history",
        expect.objectContaining({
          method: "POST",
        }),
      );
    });
  });
});
