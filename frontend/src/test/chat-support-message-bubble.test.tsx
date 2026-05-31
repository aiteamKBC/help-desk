import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MessageBubble, liveAgentQueueWaitingMessage } from "@/pages/support/ChatSupport";

describe("MessageBubble live agent queue actions", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders booking session and submit ticket directly actions while the learner is waiting for an admin", () => {
    const handleBookingClick = vi.fn();
    const handleQuickTicketClick = vi.fn();

    render(
      <MessageBubble
        m={{
          id: "queue-message",
          sender: "bot",
          text: liveAgentQueueWaitingMessage,
          timestamp: "10:51 AM",
        }}
        allowLiveAgentQueueActions
        onBookingClick={handleBookingClick}
        onQuickTicketClick={handleQuickTicketClick}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /booking session/i }));
    fireEvent.click(screen.getByRole("button", { name: /submit ticket directly/i }));

    expect(handleBookingClick).toHaveBeenCalledTimes(1);
    expect(handleQuickTicketClick).toHaveBeenCalledTimes(1);
  });

  it("falls back to plain text when the queue actions should not be shown", () => {
    render(
      <MessageBubble
        m={{
          id: "queue-message",
          sender: "bot",
          text: liveAgentQueueWaitingMessage,
          timestamp: "10:51 AM",
        }}
      />,
    );

    expect(screen.queryByRole("button", { name: /booking session/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /submit ticket directly/i })).not.toBeInTheDocument();
    expect(screen.getByText(liveAgentQueueWaitingMessage)).toBeInTheDocument();
  });
});
