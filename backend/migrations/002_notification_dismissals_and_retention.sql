-- Additive only: no existing table, column or row is changed or removed.

-- Per-recipient notification state.
-- The notification event itself stays on the ticket (tickets.metadata, e.g.
-- pending_support_queue_notification) and is shared by every admin who can
-- access the ticket. Each admin's Dismiss / Open Ticket / Dismiss All is stored
-- here, so one admin's action never hides the notification from anyone else.
-- notification_key identifies one event (ticket + reason + timestamp), so a new
-- event on the same ticket appears again even after an earlier one was dismissed.
CREATE TABLE IF NOT EXISTS support_notification_dismissals (
  account_id BIGINT NOT NULL REFERENCES support_accounts(id) ON DELETE CASCADE,
  ticket_id BIGINT NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
  notification_key TEXT NOT NULL,
  dismissed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (account_id, notification_key)
);

CREATE INDEX IF NOT EXISTS idx_support_notification_dismissals_ticket_id
  ON support_notification_dismissals(ticket_id);

-- Archived-ticket retention: candidates are looked up by archive time.
CREATE INDEX IF NOT EXISTS idx_tickets_archived_at
  ON tickets(archived_at, id)
  WHERE is_archived = TRUE;

-- Operational audit of the archived-ticket retention cleanup. Holds only the
-- public ticket id, the dates and the outcome: no learner names, e-mails or
-- message content. It has no foreign key so it outlives the deleted ticket.
CREATE TABLE IF NOT EXISTS ticket_retention_audit (
  id BIGSERIAL PRIMARY KEY,
  ticket_public_id TEXT NOT NULL,
  archived_at TIMESTAMPTZ,
  scheduled_deletion_at TIMESTAMPTZ,
  processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  outcome TEXT NOT NULL CHECK (outcome IN ('deleted', 'skipped', 'failed')),
  detail TEXT NOT NULL DEFAULT '',
  attachment_files_deleted INTEGER NOT NULL DEFAULT 0,
  attachment_files_retained INTEGER NOT NULL DEFAULT 0,
  attachment_files_failed INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_ticket_retention_audit_processed_at
  ON ticket_retention_audit(processed_at DESC);
