import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { CloseTicketDialog } from "@/components/support/CloseTicketDialog";

it("keeps email off by default and only loads the editable draft after opt-in", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
    available: true,
    recipients: [{ type: "requester", name: "Ayman", email: "ayman@example.com" }],
    subject: "Your support ticket KBC-1 has been closed",
    message: "Default closure message",
    previewHtml: "<html></html>",
  }), { status: 200, headers: { "Content-Type": "application/json" } }));
  const onConfirm = vi.fn(async () => true);

  render(<CloseTicketDialog open onOpenChange={() => {}} ticketId="KBC-1" note="Resolved"
    onNoteChange={() => {}} isSaving={false} onConfirm={onConfirm} />);

  const toggle = screen.getByRole("switch", { name: "Send closure email" });
  expect(toggle).not.toBeChecked();
  expect(fetchMock).not.toHaveBeenCalled();

  fireEvent.click(toggle);
  expect(await screen.findByDisplayValue("Default closure message")).toBeInTheDocument();
  fireEvent.change(screen.getByDisplayValue("Default closure message"), { target: { value: "Custom resolution" } });
  fireEvent.click(screen.getByRole("button", { name: "Close ticket & queue email" }));

  await waitFor(() => expect(onConfirm).toHaveBeenCalledWith({
    send: true,
    subject: "Your support ticket KBC-1 has been closed",
    message: "Custom resolution",
  }));
  fetchMock.mockRestore();
});
