import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import AdminLogin from "@/pages/support/AdminLogin";

describe("AdminLogin", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("offline"))));
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders a Microsoft Teams sign-in button with the current origin", () => {
    render(
      <MemoryRouter initialEntries={["/admin/login"]}>
        <AdminLogin />
      </MemoryRouter>,
    );

    const teamsLink = screen.getByRole("link", { name: /sign in with microsoft teams/i });
    expect(teamsLink).toHaveAttribute(
      "href",
      "http://localhost:3000/api/admin/microsoft/login?origin=http%3A%2F%2Flocalhost%3A3000",
    );
  });

  it("shows the Microsoft callback error on the login screen", () => {
    render(
      <MemoryRouter initialEntries={["/admin/login?microsoftError=Access%20denied"]}>
        <AdminLogin />
      </MemoryRouter>,
    );

    expect(screen.getByText("Access denied")).toBeInTheDocument();
  });
});
