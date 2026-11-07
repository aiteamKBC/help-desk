import { useEffect, useState } from "react";
import { LoaderCircle, Mail, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";

export interface ClosureNotificationInput {
  send: boolean;
  subject: string;
  message: string;
}

interface ClosureEmailDraft {
  available: boolean;
  recipients: Array<{ type: string; name: string; email: string }>;
  subject: string;
  message: string;
  previewHtml: string;
}

export function CloseTicketDialog({
  open,
  onOpenChange,
  ticketId,
  note,
  onNoteChange,
  isSaving,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  ticketId: string;
  note: string;
  onNoteChange: (value: string) => void;
  isSaving: boolean;
  onConfirm: (notification: ClosureNotificationInput) => Promise<boolean>;
}) {
  const [sendEmail, setSendEmail] = useState(false);
  const [draft, setDraft] = useState<ClosureEmailDraft | null>(null);
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [isLoadingDraft, setIsLoadingDraft] = useState(false);
  const [draftError, setDraftError] = useState("");
  const trimmedNote = note.trim();

  useEffect(() => {
    if (!open) return;
    setSendEmail(false);
    setDraft(null);
    setSubject("");
    setMessage("");
    setDraftError("");
  }, [open, ticketId]);

  useEffect(() => {
    if (!open || !sendEmail) return;
    let cancelled = false;
    setIsLoadingDraft(true);
    setDraftError("");
    fetch(`/api/admin/tickets/${encodeURIComponent(ticketId)}/closure-email-draft`, { credentials: "same-origin" })
      .then(async (response) => {
        const payload = await response.json().catch(() => null) as (ClosureEmailDraft & { message?: string }) | null;
        if (!response.ok || !payload) throw new Error(payload?.message || "Could not prepare the closure email.");
        if (cancelled) return;
        setDraft(payload);
        setSubject(payload.subject || "");
        setMessage(payload.message || "");
        if (!payload.available) setDraftError("This ticket has no valid notification recipient.");
      })
      .catch((error) => !cancelled && setDraftError(error instanceof Error ? error.message : "Could not prepare the closure email."))
      .finally(() => !cancelled && setIsLoadingDraft(false));
    return () => { cancelled = true; };
  }, [open, sendEmail, ticketId]);

  const emailReady = !sendEmail || Boolean(draft?.available && subject.trim() && message.trim());

  async function confirm() {
    if (!trimmedNote || !emailReady) return;
    const didClose = await onConfirm({ send: sendEmail, subject: subject.trim(), message: message.trim() });
    if (didClose) onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => !isSaving && onOpenChange(nextOpen)}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Close Ticket {ticketId}</DialogTitle>
          <DialogDescription>Record the internal reason, then choose whether the requester should receive an email.</DialogDescription>
        </DialogHeader>

        <div className="space-y-5">
          <div className="space-y-2">
            <Label htmlFor={`close-note-${ticketId}`}>Internal note *</Label>
            <Textarea id={`close-note-${ticketId}`} rows={3} value={note} onChange={(event) => onNoteChange(event.target.value)}
              placeholder="Add the internal reason for closing this ticket..." disabled={isSaving} />
            <p className="text-xs text-muted-foreground">Visible to support staff only. It is never copied into the email.</p>
          </div>

          <div className="rounded-2xl border p-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-2 font-semibold"><Mail className="h-4 w-4" /> Send closure email</div>
                <p className="mt-1 text-xs text-muted-foreground">Off by default. No email is sent unless you turn this on.</p>
              </div>
              <Switch checked={sendEmail} onCheckedChange={setSendEmail} disabled={isSaving} aria-label="Send closure email" />
            </div>

            {sendEmail ? (
              <div className="mt-4 space-y-4 border-t pt-4">
                {isLoadingDraft ? <div className="flex items-center gap-2 text-sm text-muted-foreground"><LoaderCircle className="h-4 w-4 animate-spin" /> Preparing email...</div> : null}
                {draft?.recipients?.length ? (
                  <div>
                    <Label>To</Label>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {draft.recipients.map((recipient) => <span key={`${recipient.type}-${recipient.email}`} className="rounded-full border bg-secondary/30 px-3 py-1 text-xs">{recipient.name} &lt;{recipient.email}&gt;</span>)}
                    </div>
                  </div>
                ) : null}
                {draftError ? <p className="text-sm text-destructive">{draftError}</p> : null}
                {draft?.available ? (
                  <Tabs defaultValue="edit">
                    <TabsList><TabsTrigger value="edit">Edit</TabsTrigger><TabsTrigger value="preview">Preview</TabsTrigger></TabsList>
                    <TabsContent value="edit" className="space-y-3 pt-2">
                      <div><Label htmlFor={`close-subject-${ticketId}`}>Subject</Label><Input id={`close-subject-${ticketId}`} className="mt-1" value={subject} maxLength={200} onChange={(event) => setSubject(event.target.value)} disabled={isSaving} /></div>
                      <div><Label htmlFor={`close-message-${ticketId}`}>Message to requester</Label><Textarea id={`close-message-${ticketId}`} className="mt-1 min-h-36" value={message} maxLength={5000} onChange={(event) => setMessage(event.target.value)} disabled={isSaving} /></div>
                    </TabsContent>
                    <TabsContent value="preview" className="pt-2">
                      <div className="overflow-hidden rounded-2xl border bg-slate-50">
                        <div className="border-b bg-emerald-50 px-5 py-4"><div className="text-xs font-bold uppercase tracking-wide text-emerald-700">Resolved</div><div className="mt-1 text-xl font-bold">Ticket closed</div></div>
                        <div className="space-y-3 bg-white p-5"><div className="text-sm"><span className="font-semibold">Subject:</span> {subject}</div><div className="whitespace-pre-wrap text-sm leading-6 text-slate-700">{message}</div><div className="rounded-xl border bg-slate-50 p-3 text-xs text-muted-foreground">Ticket details and the Kent Business College footer are added automatically.</div></div>
                      </div>
                    </TabsContent>
                  </Tabs>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>

        <DialogFooter className="gap-2">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={isSaving}>Cancel</Button>
          <Button type="button" variant="destructive" onClick={() => void confirm()} disabled={isSaving || !trimmedNote || !emailReady}>
            {isSaving ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : <X className="mr-2 h-4 w-4" />}
            {sendEmail ? "Close ticket & queue email" : "Close ticket without email"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
