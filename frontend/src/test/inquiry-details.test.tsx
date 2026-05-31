import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { SupportProvider } from "@/context/SupportContext";
import InquiryDetails from "@/pages/support/InquiryDetails";

const supportStorageKey = "kbc-support-state-v2";

describe("InquiryDetails", () => {
  beforeEach(() => {
    window.localStorage.clear();
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
    window.localStorage.clear();
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
});
