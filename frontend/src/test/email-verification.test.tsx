import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { SupportProvider } from "@/context/SupportContext";
import { useSupport } from "@/context/useSupport";
import EmailVerification from "@/pages/support/EmailVerification";

function RequesterDestination() {
  const { ticket } = useSupport();
  const location = useLocation();
  return <output data-testid="destination">{JSON.stringify({ path: location.pathname, ticket })}</output>;
}

function renderVerification(entry: string) {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <SupportProvider>
        <Routes>
          <Route path="/" element={<EmailVerification />} />
          <Route path="/support/inquiry" element={<RequesterDestination />} />
          <Route path="/support/my-tickets" element={<RequesterDestination />} />
        </Routes>
      </SupportProvider>
    </MemoryRouter>,
  );
}

describe("LMS sign-in with the requester dashboard", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    window.localStorage.clear();
  });

  it.each([
    ["Start New Ticket", "/support/inquiry"],
    ["My Tickets", "/support/my-tickets"],
  ])("keeps the verified LMS identity when choosing %s", async (button, path) => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      exists: true,
      learner: { fullName: "LMS Tutor", email: "tutor@example.com" },
      requesterRole: "tutor",
      requesterSource: "lms_learners",
    }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    renderVerification("/?token=signed-token&email=unverified@example.com");

    fireEvent.click(await screen.findByRole("button", { name: button }));
    const destination = JSON.parse((await screen.findByTestId("destination")).textContent || "{}");
    expect(destination.path).toBe(path);
    expect(destination.ticket).toMatchObject({
      id: "", email: "tutor@example.com", learnerName: "LMS Tutor",
      requesterRole: "tutor", requesterSource: "lms_learners", coverageSessions: [],
    });
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith("/api/support/sso", expect.objectContaining({
      method: "POST", body: JSON.stringify({ token: "signed-token" }),
    }));
  });

  it("prefills a raw email without automatically verifying it", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderVerification("/?email=learner@example.com");
    expect(screen.getByPlaceholderText("Enter your registered email")).toHaveValue("learner@example.com");
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.queryByText("Support Dashboard")).not.toBeInTheDocument();
  });

  it("uses one coordinated SVG wave system for the campus image and ribbon layers", () => {
    renderVerification("/");

    const wave = document.querySelector(".support-hero-wave");
    expect(wave).toBeInTheDocument();
    expect(wave?.querySelector("clipPath path")).toBeInTheDocument();
    expect(wave?.querySelector(".support-wave-layer-purple")).toBeInTheDocument();
    expect(wave?.querySelector(".support-wave-layer-lavender")).toBeInTheDocument();
    expect(wave?.querySelector('image[href="/support-campus.png"]')).toBeInTheDocument();
  });

  it("opens the Support Dashboard after clicking Next with a verified email", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      exists: true,
      learner: { fullName: "Ayman Badewi", email: "ayman.badewi@kentbusinesscollege.com" },
      requesterRole: "user",
      requesterSource: "support_portal_requester",
    }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    renderVerification("/");

    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    expect(await screen.findByRole("dialog", { name: "Support Dashboard" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/verify-email", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ email: "ayman.badewi@kentbusinesscollege.com" }),
    }));
  });

  it("does not open the requester dashboard when the SSO token is rejected", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      message: "This sign-in link has expired.",
    }), { status: 401 })));
    renderVerification("/?token=expired-token");
    expect(await screen.findByText("This sign-in link has expired.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "My Tickets" })).not.toBeInTheDocument();
  });

  it("shows a text-only support dashboard and closes back to the homepage", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      exists: true,
      learner: { fullName: "LMS Tutor", email: "tutor@example.com" },
      requesterRole: "tutor",
      requesterSource: "lms_learners",
    }), { status: 200 })));
    renderVerification("/?token=signed-token");

    const dialog = await screen.findByRole("dialog", { name: "Support Dashboard" });
    expect(within(dialog).getByText("Choose what you want to do for this email.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start New Ticket" }).querySelector("svg")).toBeNull();
    expect(screen.getByRole("button", { name: "My Tickets" }).querySelector("svg")).toBeNull();
    expect(screen.queryByText(/Your role will be identified automatically/i)).not.toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog", { name: "Support Dashboard" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Support Request" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Enter your registered email")).toHaveValue("tutor@example.com");
    expect(screen.getByRole("link", { name: /Admin/i })).toBeInTheDocument();
  });
});
