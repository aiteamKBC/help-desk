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

  it("shows the Admin link for normal support portal visits", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <SupportLayout>
          <div>Support Request</div>
        </SupportLayout>
      </MemoryRouter>,
    );

    expect(screen.getByRole("link", { name: /Admin/i })).toHaveAttribute("href", "/admin");
    expect(screen.queryByRole("link", { name: /Support Portal/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /campus building/i })).not.toBeInTheDocument();
  });

  it("uses the admin dashboard banner on internal support pages", () => {
    render(
      <MemoryRouter initialEntries={["/support/status"]}>
        <SupportLayout>
          <div>Ticket Status</div>
        </SupportLayout>
      </MemoryRouter>,
    );

    expect(screen.getByRole("img", { name: /campus building/i })).toHaveAttribute(
      "src",
      "/kbc-dashboard-header.jpg",
    );
    expect(screen.getByRole("link", { name: /Admin/i })).toHaveAttribute("href", "/admin");
    expect(screen.getByRole("link", { name: /Knowledge Base/i })).toHaveAttribute("href", "/knowledge-base");
    expect(screen.queryByRole("button", { name: /Back/i })).not.toBeInTheDocument();
  });

  it("keeps the admin login header hidden", () => {
    render(
      <MemoryRouter initialEntries={["/admin/login"]}>
        <SupportLayout showHeader={false}>
          <div>Admin Login</div>
        </SupportLayout>
      </MemoryRouter>,
    );

    expect(screen.queryByRole("banner")).not.toBeInTheDocument();
  });

  it("shows the Support Portal link for admin area visits", () => {
    render(
      <MemoryRouter initialEntries={["/admin/login"]}>
        <SupportLayout>
          <div>Admin Login</div>
        </SupportLayout>
      </MemoryRouter>,
    );

    expect(screen.getByRole("link", { name: /Support Portal/i })).toHaveAttribute("href", "/?adminPortalReturn=1");
  });
});
