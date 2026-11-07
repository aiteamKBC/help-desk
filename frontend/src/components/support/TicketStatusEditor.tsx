import { useRef, useState } from "react";
import { ChevronDown, LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { StatusBadge } from "@/components/support/StatusBadge";
import { CloseTicketDialog, type ClosureNotificationInput } from "@/components/support/CloseTicketDialog";

type TicketStatus = "Open" | "Pending" | "Closed";

export function TicketStatusEditor({ ticketId, status, label, disabled, onConfirm }: {
  ticketId: string;
  status: TicketStatus;
  label: string;
  disabled: boolean;
  onConfirm: (status: TicketStatus, note: string, closureNotification?: ClosureNotificationInput) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [nextStatus, setNextStatus] = useState(status);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [closeDialogOpen, setCloseDialogOpen] = useState(false);
  const inFlight = useRef(false);

  async function confirm() {
    if (inFlight.current || disabled || nextStatus === status || !note.trim()) return;
    if (nextStatus === "Closed") {
      setOpen(false);
      setCloseDialogOpen(true);
      return;
    }
    inFlight.current = true;
    setSaving(true);
    setError("");
    try {
      await onConfirm(nextStatus, note.trim());
      setOpen(false);
    } catch (error) {
      setError(error instanceof Error ? error.message : "Could not update the ticket. Please try again.");
    } finally {
      inFlight.current = false;
      setSaving(false);
    }
  }

  async function confirmClose(closureNotification: ClosureNotificationInput) {
    if (inFlight.current || disabled || !note.trim()) return false;
    inFlight.current = true;
    setSaving(true);
    setError("");
    try {
      await onConfirm("Closed", note.trim(), closureNotification);
      return true;
    } catch (closeError) {
      setError(closeError instanceof Error ? closeError.message : "Could not close the ticket. Please try again.");
      return false;
    } finally {
      inFlight.current = false;
      setSaving(false);
    }
  }

  return (
    <span onClick={(event) => event.stopPropagation()} onKeyDown={(event) => event.stopPropagation()}>
      <Popover open={open} onOpenChange={(value) => {
        if (inFlight.current) return;
        if (value) {
          setNextStatus(status);
          setNote("");
          setError("");
        }
        setOpen(value);
      }}>
        <PopoverTrigger asChild>
          <button type="button" disabled={disabled} aria-label={`Change status for ${ticketId}`}
            className="inline-flex items-center gap-1 rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:cursor-default">
            <StatusBadge status={status} label={label} />
            {!disabled && <ChevronDown className="h-3 w-3 text-muted-foreground" />}
          </button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-80 space-y-3" aria-label={`Update status for ${ticketId}`}>
          <div className="text-sm font-semibold">Update status · {ticketId}</div>
          <div className="flex gap-2" role="group" aria-label="New ticket status">
            {(["Open", "Pending", "Closed"] as const).map((value) => (
              <Button key={value} type="button" size="sm" variant={nextStatus === value ? "default" : "outline"}
                aria-pressed={nextStatus === value} disabled={saving} onClick={() => setNextStatus(value)}>
                {value}
              </Button>
            ))}
          </div>
          <Textarea aria-label="Reason for status change" placeholder="Add a short internal note (required)"
            value={note} onChange={(event) => setNote(event.target.value)} disabled={saving} />
          {nextStatus === "Closed" && <p className="text-xs text-muted-foreground">Closing follows the ticket's usual notification workflow.</p>}
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" disabled={saving} onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="button" size="sm" disabled={saving || disabled || nextStatus === status || !note.trim()} onClick={() => void confirm()}>
              {saving && <LoaderCircle className="mr-2 h-3 w-3 animate-spin" />}
              {saving ? "Saving..." : "Confirm change"}
            </Button>
          </div>
        </PopoverContent>
      </Popover>
      <CloseTicketDialog open={closeDialogOpen} onOpenChange={setCloseDialogOpen} ticketId={ticketId}
        note={note} onNoteChange={setNote} isSaving={saving} onConfirm={confirmClose} />
    </span>
  );
}
