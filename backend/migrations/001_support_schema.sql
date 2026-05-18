CREATE TABLE IF NOT EXISTS learners (
  id BIGSERIAL PRIMARY KEY,
  external_learner_id TEXT,
  full_name TEXT,
  email TEXT NOT NULL UNIQUE,
  phone TEXT,
  source TEXT NOT NULL DEFAULT 'manual',
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS conversations (
  id BIGSERIAL PRIMARY KEY,
  channel TEXT NOT NULL DEFAULT 'support',
  customer_id TEXT,
  customer_name TEXT,
  customer_email TEXT,
  customer_phone TEXT,
  status TEXT NOT NULL DEFAULT 'open',
  intent TEXT,
  language TEXT NOT NULL DEFAULT 'en',
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_message_at TIMESTAMPTZ,
  chat_duration_minutes BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS messages (
  id BIGSERIAL PRIMARY KEY,
  conversation_id BIGINT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  channel TEXT NOT NULL DEFAULT 'support',
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = current_schema()
      AND table_name = 'agents'
  ) AND NOT EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = current_schema()
      AND table_name = 'support_accounts'
  ) THEN
    EXECUTE 'ALTER TABLE agents RENAME TO support_accounts';
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS support_accounts (
  id BIGSERIAL PRIMARY KEY,
  username TEXT NOT NULL UNIQUE,
  full_name TEXT,
  email TEXT UNIQUE,
  account_scope TEXT NOT NULL DEFAULT 'staff',
  role TEXT NOT NULL DEFAULT 'agent',
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT support_accounts_role_check CHECK (role IN ('agent', 'user', 'coach', 'employer', 'admin', 'superadmin')),
  CONSTRAINT support_accounts_account_scope_check CHECK (account_scope IN ('staff', 'requester'))
);

ALTER TABLE support_accounts
ADD COLUMN IF NOT EXISTS account_scope TEXT NOT NULL DEFAULT 'staff';

UPDATE support_accounts
SET account_scope = CASE
  WHEN role IN ('user', 'coach', 'employer') THEN 'requester'
  ELSE 'staff'
END;

ALTER TABLE support_accounts
DROP CONSTRAINT IF EXISTS agents_role_check;

ALTER TABLE support_accounts
DROP CONSTRAINT IF EXISTS support_accounts_role_check;

ALTER TABLE support_accounts
ADD CONSTRAINT support_accounts_role_check
CHECK (role IN ('agent', 'user', 'coach', 'employer', 'admin', 'superadmin'));

ALTER TABLE support_accounts
DROP CONSTRAINT IF EXISTS agents_account_scope_check;

ALTER TABLE support_accounts
DROP CONSTRAINT IF EXISTS support_accounts_account_scope_check;

ALTER TABLE support_accounts
ADD CONSTRAINT support_accounts_account_scope_check
CHECK (account_scope IN ('staff', 'requester'));

ALTER TABLE learners
ADD COLUMN IF NOT EXISTS support_account_id BIGINT REFERENCES support_accounts(id) ON DELETE SET NULL;

ALTER TABLE learners
DROP CONSTRAINT IF EXISTS learners_support_account_id_key;

ALTER TABLE learners
ADD CONSTRAINT learners_support_account_id_key UNIQUE (support_account_id);

UPDATE learners AS l
SET support_account_id = sa.id,
    updated_at = NOW()
FROM support_accounts AS sa
WHERE LOWER(TRIM(l.email)) = LOWER(TRIM(sa.email))
  AND sa.account_scope = 'requester'
  AND (l.support_account_id IS NULL OR l.support_account_id <> sa.id);

CREATE TABLE IF NOT EXISTS tickets (
  id BIGSERIAL PRIMARY KEY,
  public_id TEXT NOT NULL UNIQUE,
  learner_id BIGINT NOT NULL REFERENCES learners(id) ON DELETE RESTRICT,
  conversation_id BIGINT REFERENCES conversations(id) ON DELETE SET NULL,
  category TEXT NOT NULL,
  technical_subcategory TEXT,
  inquiry TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'Open',
  status_reason TEXT NOT NULL DEFAULT '',
  assigned_agent_id BIGINT REFERENCES support_accounts(id) ON DELETE SET NULL,
  assigned_team TEXT NOT NULL DEFAULT 'Unassigned',
  sla_status TEXT NOT NULL DEFAULT 'Pending Review',
  priority TEXT NOT NULL DEFAULT 'Normal',
  evidence_count INTEGER NOT NULL DEFAULT 0,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  closed_at TIMESTAMPTZ,
  CONSTRAINT tickets_status_check CHECK (status IN ('Open', 'Pending', 'Closed')),
  CONSTRAINT tickets_priority_check CHECK (priority IN ('Low', 'Normal', 'High', 'Urgent'))
);

ALTER TABLE tickets
ADD COLUMN IF NOT EXISTS technical_subcategory TEXT;

ALTER TABLE tickets
ADD COLUMN IF NOT EXISTS status_reason TEXT NOT NULL DEFAULT '';

ALTER TABLE tickets
DROP CONSTRAINT IF EXISTS tickets_conversation_id_key;

UPDATE tickets
SET status = 'Closed',
    closed_at = COALESCE(closed_at, NOW()),
    updated_at = NOW()
WHERE status = 'Resolved';

UPDATE tickets
SET status = 'Open',
    closed_at = NULL,
    updated_at = NOW()
WHERE status = 'In Progress';

UPDATE conversations
SET status = 'open'
WHERE status = 'in_progress';

ALTER TABLE conversations
ADD COLUMN IF NOT EXISTS chat_duration_minutes BIGINT NOT NULL DEFAULT 0;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = current_schema()
      AND table_name = 'conversations'
      AND column_name = 'chat_duration_seconds'
  ) THEN
    EXECUTE '
      UPDATE conversations
      SET chat_duration_minutes = CASE
        WHEN chat_duration_minutes = 0 AND chat_duration_seconds > 0
          THEN FLOOR(chat_duration_seconds / 60.0)::bigint
        ELSE chat_duration_minutes
      END
    ';
  END IF;
END $$;

ALTER TABLE tickets
DROP CONSTRAINT IF EXISTS tickets_status_check;

ALTER TABLE tickets
ADD CONSTRAINT tickets_status_check CHECK (status IN ('Open', 'Pending', 'Closed'));

CREATE TABLE IF NOT EXISTS ticket_attachments (
  id BIGSERIAL PRIMARY KEY,
  ticket_id BIGINT NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
  file_name TEXT NOT NULL,
  mime_type TEXT,
  file_size BIGINT,
  storage_url TEXT,
  preview_kind TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ticket_history (
  id BIGSERIAL PRIMARY KEY,
  ticket_id BIGINT NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  actor_type TEXT NOT NULL DEFAULT 'system',
  actor_id BIGINT,
  actor_label TEXT,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS support_session_requests (
  id BIGSERIAL PRIMARY KEY,
  ticket_id BIGINT NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
  requested_date DATE NOT NULL,
  requested_time TIME NOT NULL,
  status TEXT NOT NULL DEFAULT 'requested',
  created_by TEXT NOT NULL DEFAULT 'learner',
  notes TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT support_session_requests_status_check CHECK (status IN ('requested', 'scheduled', 'cancelled', 'completed'))
);

CREATE INDEX IF NOT EXISTS idx_learners_source ON learners(source);
CREATE INDEX IF NOT EXISTS idx_learners_support_account_id ON learners(support_account_id);
CREATE INDEX IF NOT EXISTS idx_tickets_learner_id ON tickets(learner_id);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_tickets_assigned_agent_id ON tickets(assigned_agent_id);
CREATE INDEX IF NOT EXISTS idx_tickets_created_at ON tickets(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ticket_attachments_ticket_id ON ticket_attachments(ticket_id);
CREATE INDEX IF NOT EXISTS idx_ticket_history_ticket_id ON ticket_history(ticket_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_support_session_requests_ticket_id ON support_session_requests(ticket_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_id_created_at ON messages(conversation_id, created_at);

INSERT INTO support_accounts (username, full_name, email, role)
VALUES
  ('ahmedhamamo', 'Ahmed Hamamo', NULL, 'admin')
ON CONFLICT (username) DO NOTHING;
