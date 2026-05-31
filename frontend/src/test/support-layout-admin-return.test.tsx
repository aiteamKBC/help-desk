import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { SupportLayout } from "@/components/support/SupportLayout";

describe("SupportLayout admin return link", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  afterEach(() => {
    cleanup();
    window.sessionStorage.clear();
  });

  it("shows the Admin link after entering the support portal from the admin portal link", async () => {
    render(
      <MemoryRouter initialEntries={["/?adminPortalReturn=1"]}>
        <SupportLayout>
          <div>Support Request</div>
        </SupportLayout>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByRole("link", { name: /Admin/i })).toHaveAttribute("href", "/admin");
    });
  });

  it("does not show the Admin link for normal support portal visits", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <SupportLayout>
          <div>Support Request</div>
        </SupportLayout>
      </MemoryRouter>,
    );

    expect(screen.queryByRole("link", { name: /Admin/i })).not.toBeInTheDocument();
  });
});
