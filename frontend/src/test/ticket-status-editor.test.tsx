import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { TicketStatusEditor } from "@/components/support/TicketStatusEditor";

function setup(onConfirm = vi.fn(async () => {}), disabled = false) {
  const onRowClick = vi.fn();
  const onRowKeyDown = vi.fn();
  render(<div onClick={onRowClick} onKeyDown={onRowKeyDown}>
    <TicketStatusEditor ticketId="KBC-TEST" status="Pending" label="Pending" disabled={disabled} onConfirm={onConfirm} />
  </div>);
  return { onConfirm, onRowClick, onRowKeyDown };
}

it("requires an explicit change, note and confirmation without opening the ticket row", async () => {
  const { onConfirm, onRowClick, onRowKeyDown } = setup();
  fireEvent.click(screen.getByRole("button", { name: "Change status for KBC-TEST" }));
  const confirm = screen.getByRole("button", { name: "Confirm change" });
  expect(confirm).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Closed", exact: true }));
  expect(confirm).toBeDisabled();
  const note = screen.getByRole("textbox", { name: "Reason for status change" });
  fireEvent.change(note, { target: { value: "  Resolved with the requester  " } });
  fireEvent.keyDown(note, { key: " " });
  expect(onConfirm).not.toHaveBeenCalled();
  fireEvent.click(confirm);
  await waitFor(() => expect(onConfirm).toHaveBeenCalledWith("Closed", "Resolved with the requester"));
  await waitFor(() => expect(screen.queryByRole("button", { name: "Confirm change" })).not.toBeInTheDocument());
  expect(onRowClick).not.toHaveBeenCalled();
  expect(onRowKeyDown).not.toHaveBeenCalled();
});

it("cancels without sending an update", () => {
  const { onConfirm } = setup();
  fireEvent.click(screen.getByRole("button", { name: "Change status for KBC-TEST" }));
  fireEvent.click(screen.getByRole("button", { name: "Open", exact: true }));
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(onConfirm).not.toHaveBeenCalled();
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
});

it("keeps the note and shows the server error so an admin can retry", async () => {
  setup(vi.fn(async () => { throw new Error("This ticket has been archived."); }));
  fireEvent.click(screen.getByRole("button", { name: "Change status for KBC-TEST" }));
  fireEvent.click(screen.getByRole("button", { name: "Open", exact: true }));
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "Reopen for review" } });
  fireEvent.click(screen.getByRole("button", { name: "Confirm change" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("This ticket has been archived.");
  expect(screen.getByRole("textbox")).toHaveValue("Reopen for review");
});

it("blocks repeated submissions while an update is pending", async () => {
  let finish!: () => void;
  const onConfirm = vi.fn(() => new Promise<void>((resolve) => { finish = resolve; }));
  setup(onConfirm);
  fireEvent.click(screen.getByRole("button", { name: "Change status for KBC-TEST" }));
  fireEvent.click(screen.getByRole("button", { name: "Open", exact: true }));
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "Review" } });
  const confirm = screen.getByRole("button", { name: "Confirm change" });
  fireEvent.click(confirm);
  fireEvent.click(confirm);
  expect(onConfirm).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("button", { name: "Saving..." })).toBeDisabled();
  finish();
  await waitFor(() => expect(screen.queryByRole("textbox")).not.toBeInTheDocument());
});

it("does not allow editing an archived or unauthorized ticket", () => {
  const { onConfirm } = setup(undefined, true);
  const trigger = screen.getByRole("button", { name: "Change status for KBC-TEST" });
  expect(trigger).toBeDisabled();
  fireEvent.click(trigger);
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  expect(onConfirm).not.toHaveBeenCalled();
});
