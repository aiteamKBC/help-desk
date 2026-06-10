import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { RequireAdmin } from "@/components/support/RequireAdmin";

const agentSession = {
  id: 7,
  username: "test.test@kentbusinesscollege.com",
  fullName: "Test Agent",
  email: "test.test@kentbusinesscollege.com",
  role: "agent",
  instanceId: "session-one",
};

function mockAdminSession(role = "agent") {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(
      new Response(JSON.stringify({ admin: { ...agentSession, role } }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    )),
  );
}

describe("RequireAdmin", () => {
  afterEach(() => {
    cleanup();
    sessionStorage.clear();
    vi.unstubAllGlobals();
  });

  it("allows support dashboard routes to admit agent sessions", async () => {
    mockAdminSession("agent");

    render(
      <MemoryRouter initialEntries={["/admin"]}>
        <Routes>
          <Route
            path="/admin"
            element={(
              <RequireAdmin allowedRoles={["agent", "admin", "superadmin"]}>
                <div>Agent dashboard</div>
              </RequireAdmin>
            )}
          />
          <Route path="/support" element={<div>Support portal</div>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Agent dashboard")).toBeInTheDocument();
  });

  it("keeps the default guard restricted to admin roles", async () => {
    mockAdminSession("agent");

    render(
      <MemoryRouter initialEntries={["/knowledge-base"]}>
        <Routes>
          <Route
            path="/knowledge-base"
            element={(
              <RequireAdmin>
                <div>Knowledge base</div>
              </RequireAdmin>
            )}
          />
          <Route path="/support" element={<div>Support portal</div>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Support portal")).toBeInTheDocument();
  });
});
