# Deployment handoff — support assistant + LMS chat widget

**For:** whoever deploys the support portal.
**Branch:** `feat/native-assistant-lms-integration`

Everything below is already working locally and verified end to end. This is what
has to happen on the server for it to keep working there.

No secret values appear in this file. Where one is needed it says so — take it
from the existing production `.env`, or ask Khaled for it directly.

---

## 1. Settings to add to the server `.env`

### Required — new in this release

```env
# Who the support team's own notifications go to: a ticket being opened, and a
# live-agent request with nobody available. Comma-separated.
SUPPORT_OPERATIONS_NOTIFICATION_EMAILS=Meeka@kentbusinesscollege.com

# The assistant's chat model.
OPENAI_MODEL=gpt-5.4-mini
```

**If `SUPPORT_OPERATIONS_NOTIFICATION_EMAILS` is left out**, notifications still
go out — the code falls back to `SUPPORT_TEAMS_CALL_TARGETS`, which currently
holds the same address. That is a coincidence, not a design: the two settings
answer different questions, and the day someone repoints Teams calls at a
different person, the ticket emails silently follow them. Set it explicitly.

**If `OPENAI_MODEL` is left out**, the assistant falls back to `gpt-4o-mini`.
It still works, but replies are slower and noticeably less precise — in testing
it gave vaguer answers and named pages less accurately.

### Required — check these are right for production

```env
# Must list the LMS origin. Do NOT carry over any localhost entries from a
# developer's file — those are only there for local testing.
CORS_ALLOWED_ORIGINS=https://lms.kentbusinesscollege.org

# Must point at the deployed admin callback, not localhost.
AZURE_LOGIN_REDIRECT_URI=https://technicalsupport.kentbusinesscollege.net/api/admin/microsoft/callback
```

### Already set, unchanged — just confirm they are present

`DATABASE_URL`, `LEGACY_DATABASE_URL`, `LMS_DATABASE_URL`, `OPENAI_API_KEY`,
`OPENAI_EMBEDDING_MODEL`, `SUPPORT_SSO_SECRET`, `SUPPORT_PORTAL_PUBLIC_BASE_URL`,
`N8N_SUPPORT_NOTIFICATION_WEBHOOK_URL`, `SUPPORT_TEAMS_CALL_TARGETS`,
`DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`,
and the Azure/booking group.

---

## 2. One value looks wrong in the current config

`AZURE_BOOKING_TENANT_ID` is two characters shorter than the other two tenant
IDs in the same file, which are identical to each other:

```
AZURE_TENANT_ID=        ddf2d4be-155f-4f5b-bbc4-63e97ba2fa45
AZURE_LOGIN_TENANT_ID=  ddf2d4be-155f-4f5b-bbc4-63e97ba2fa45
AZURE_BOOKING_TENANT_ID=ddf2d4be-155f-4f5b-bbc4-63e97ba2fa      <- missing "45"
```

A tenant ID is a UUID, so this one is truncated rather than legitimately
different. Booking calls authenticating against it would fail. Worth checking
the production value before deploying — if it has the same truncation, fix it to
match the other two.

---

## 3. n8n — already done, for the record

The `supportNotifications` workflow needed a branch for a new event,
`ticket_created`, which the backend now sends whenever a ticket is opened. That
branch was added and tested; this note is only so the next person knows the
dependency exists.

Events the backend sends to that webhook:

| Event | Goes to | When |
| --- | --- | --- |
| `ticket_created` | operations | Any new ticket, from any route |
| `live_agent_unavailable` | operations | Live agent asked for, nobody available |
| `quick_ticket_submitted` | the learner | Their ticket was received |
| `quick_ticket_closed` | the learner | Their ticket was closed |

The payload names the recipients explicitly in a `recipients` array, taken from
`SUPPORT_OPERATIONS_NOTIFICATION_EMAILS`. n8n should address the mail from that
field rather than from its own copy of the rota, so a change of recipient stays
a settings change.

---

## 4. The LMS side is a separate repo and is not covered here

The chat widget lives inside KBC LearningOS, not in this repository. Its
integration — the SSO endpoint, the button, and three LMS-side settings — is
documented separately in `LMS_SSO_HANDOFF.md`, and the work belongs to whoever
owns the LMS repo. The support portal needs no further changes for it.

Note that the widget currently has the support portal's addresses hard-coded for
local testing:

```ts
const SUPPORT_API_BASE = 'http://127.0.0.1:8010';
const SUPPORT_PORTAL_BASE = 'http://127.0.0.1:3001';
```

These must become the deployed addresses before the widget ships.

---

## 5. After deploying — worth checking

1. **A ticket reaches the team.** Open one through the portal and confirm the
   address in `SUPPORT_OPERATIONS_NOTIFICATION_EMAILS` receives the mail. The
   ticket's history row will say `ticket_created_operations_notified` with
   `webhookDelivered: true` if the handoff to n8n succeeded — if the mail still
   does not arrive after that, the gap is inside n8n, not here.
2. **The assistant answers.** Ask it something an LMS learner would ask
   ("where do I find Progress Review?") and check the reply names a real page.
3. **The knowledge base is current.** It lives in the database, not in the
   deployment — see `backend/docs/lms-knowledge.md`. It was last imported on
   2026-10-15 and does not need re-importing as part of this deploy, but it does
   need re-importing whenever the LMS itself changes, or the assistant will
   confidently describe screens that have moved.
