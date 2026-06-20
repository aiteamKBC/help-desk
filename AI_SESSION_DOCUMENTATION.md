# AI Session Documentation

## Session Prompt
Use this prompt at the start of any future session:

```text
Before making any changes, read AI_SESSION_DOCUMENTATION.md from the repo root.
Treat it as durable session memory.
Summarize the latest relevant entries, note any open risks or follow-ups, then continue with the new request.
After every meaningful code or product change, append a new entry to the end of this file without deleting older history.
```

## How To Use This Document
1. Read this file first in every new session before changing code.
2. Use the newest entries as the current source of truth for recent AI-made changes.
3. Append new work to the end of `Change Log`; do not rewrite old entries except to fix factual mistakes.
4. For each new entry, include:
   - Date
   - Request
   - What changed
   - Why it changed
   - Files touched
   - Verification
   - Follow-up notes or risks
5. If a new request overrides an older behavior, mention the older entry it supersedes.
6. If a requested change is only partial, clearly say what is still unchanged.

## Notes
- This file was created on `2026-06-11`.
- Changes made before this file existed may not be fully backfilled here unless they are still important to current work.
- Keep entries practical and implementation-focused so they remain useful when prior session memory is unavailable.

## Change Log

### 2026-06-11 - Coverage Dashboard Requester Column Shows Tutor And Module
- Request:
  Replace the coverage dashboard `Requester` column content for coverage tickets so operations can visually distinguish tickets by tutor/module and search for them more easily.
- What changed:
  - In the coverage dashboard view, coverage-ticket rows now display `Tutor` on the first line and `Module` on the second line, using parsed values from `ticket.documentation.inquiry`.
  - Coverage dashboard search now includes tutor and module terms, so the existing search bar can find coverage tickets by those values.
  - The search placeholder was updated in the coverage dashboard to reflect tutor/module search usage.
  - Standard requester rendering for non-coverage dashboard contexts was preserved.
- Why it changed:
  Operations needs to quickly identify and search coverage tickets by tutor and module rather than requester name/e-mail.
- Files touched:
  - `frontend/src/pages/support/AgentDashboard.tsx`
  - `AI_SESSION_DOCUMENTATION.md`
- Verification:
  - `npm run build` passed in `frontend/` on `2026-06-11`.
- Follow-up notes:
  - This is a coverage-dashboard-focused display/search change, not a system-wide rename of requester data.
  - If needed later, the same tutor/module presentation can be extended to other coverage-specific surfaces intentionally.

### 2026-06-13 - Coverage Tutor Requests Can Start Without Files And Accept File Follow-Ups
- Request:
  Allow coverage tutor requests to be submitted even when the presentation is not ready yet, then allow support staff to send presentation files later to the same tutor request without reopening or changing the ticket workflow.
- What changed:
  - Kept the original coverage tutor request flow for the first submission, but removed the UI-only requirement that at least one presentation file must exist before `Submit to Tutor`.
  - Added a new backend endpoint and service flow for coverage tutor file follow-ups so admins can send new presentation files later for tutor requests in `requested` or `accepted` state.
  - Follow-up file sends now keep the ticket status, status reason, and SLA unchanged while persisting the newly shared files on the existing tutor-choice card.
  - The coverage dashboard UI now shows a dedicated follow-up files block on submitted tutor request cards, including the special case where the tutor already accepted and the ticket is closed.
  - Added activity log labels for tutor file follow-ups and fixed an older coverage workflow test fixture so the full `CoverageTutorWorkflowTests` suite can pass again.
- Why it changed:
  - Operations needs to contact tutors before the presentation is ready, then send the deck later without losing SLA handling or creating a second tutor request.
  - Accepted tutor requests were previously effectively locked because the ticket closed and the original tutor-choice card was hidden.
- Files touched:
  - `backend/support_portal/services.py`
  - `backend/support_portal/views.py`
  - `backend/support_portal/urls.py`
  - `backend/support_portal/tests.py`
  - `frontend/src/pages/support/AgentDashboard.tsx`
  - `AI_SESSION_DOCUMENTATION.md`
- Verification:
  - `.\.venv\Scripts\python.exe manage.py test support_portal.tests.CoverageTutorWorkflowTests` passed in `backend/` on `2026-06-13`.
  - `npm run build` passed in `frontend/` on `2026-06-13`.
- Follow-up notes:
  - The follow-up mail reuses the existing coverage tutor request webhook transport and distinguishes the payload with `event = "coverage_tutor_follow_up"`.
  - Follow-up files are intentionally blocked for `refused` tutor requests; staff should create a fresh tutor request instead.
  - The follow-up UI stages new files locally until send time, so unsent staged files are discarded if the ticket panel is closed or refreshed before sending.

### 2026-06-13 - Ready-To-Import n8n Workflow For Coverage Tutor Request And Follow-Up
- Request:
  Prepare the existing n8n tutor-request workflow so it can handle both the original `coverage_tutor_requested` mails and the new `coverage_tutor_follow_up` attachment mails.
- What changed:
  - Added a ready-to-import workflow export at `coverage-tutor-workflow-ready.json`.
  - Updated the webhook response message to a generic tutor-event acknowledgement.
  - Updated the code node so it branches by `body.event`, keeps accept/refuse links for the first tutor request, and generates a separate follow-up email template with follow-up attachments only.
  - Preserved the existing attachment/no-attachment Gmail branching so the workflow still accepts first requests without files.
- Why it changed:
  - The backend now sends two different tutor webhook events, and the original n8n workflow only understood the first-request payload shape.
- Files touched:
  - `coverage-tutor-workflow-ready.json`
  - `AI_SESSION_DOCUMENTATION.md`
- Verification:
  - `coverage-tutor-workflow-ready.json` passed JSON parsing on `2026-06-13`.
  - The embedded `Prepare Email Data` JavaScript passed syntax validation with `new Function(...)` on `2026-06-13`.
- Follow-up notes:
  - This workflow keeps the same webhook path `Coverege/Requesting/Tutor`; if a different production webhook path is already configured, either update the path here before import or point the backend webhook URL to the imported workflow path.

### 2026-06-13 - Move Accepted Coverage Follow-Up UI Into Tutor Response Card
- Request:
  Remove the visual duplication between `Tutor Response` and `Tutor Request` after tutor acceptance by showing the follow-up attachments section inside the response card instead of rendering a second accepted request card.
- What changed:
  - Refactored the coverage follow-up attachments UI into a reusable renderer inside the coverage workspace.
  - The accepted tutor response card now hosts the `Follow-Up Files` section directly under the original-request summary.
  - The linked compact `Tutor Request` card is now hidden whenever a tutor reply card already exists, so accepted flows no longer show two separate accepted cards.
- Why it changed:
  - The previous implementation was functionally correct but visually confusing because it showed both `Tutor Response` and `Tutor Request` with accepted badges for the same flow.
- Files touched:
  - `frontend/src/pages/support/AgentDashboard.tsx`
  - `AI_SESSION_DOCUMENTATION.md`
- Verification:
  - `npm run build` passed in `frontend/` on `2026-06-13`.
- Follow-up notes:
  - Requested tutor flows still show the follow-up section on the request card itself because there is no tutor response card yet.

### 2026-06-13 - Coverage Coach Fields And Stable Manual E-mail Editing
- Request:
  Fix the coverage tutor e-mail input so manual typing does not lock after the first character, then add optional `Coach` and `Coach E-mail` fields that behave like the tutor lookup flow while reading coach data from `coach_profiles`.
- What changed:
  - Fixed the coverage workspace e-mail editing logic so manual typing keeps the field editable instead of switching back to read-only after the first typed character.
  - Protected both tutor and coach e-mail lookups from overwriting manual input if the user starts typing before the async database lookup finishes.
  - Added optional `Coach` and `Coach E-mail` fields to coverage tutor-choice cards, including persisted storage, reconstruction from coverage history, and display in compact request/response summaries.
  - Added backend coverage option endpoints for `coaches` and `coach-email`, sourcing active records from `public.coach_profiles`.
  - Coverage tutor-request submission now accepts an optional coach, auto-fills the coach e-mail from the database when possible, validates it when a coach is selected, and includes coach data in tutor-request/follow-up webhook payloads.
  - Added a `No coach` option in the dashboard select so the optional coach assignment can be cleared intentionally.
- Why it changed:
  - Staff needs to type missing e-mails manually without the field fighting them.
  - Coverage operations also needs to record coach ownership alongside tutor outreach, but without making coach assignment mandatory before `coach_profiles` is fully populated.
- Files touched:
  - `frontend/src/lib/coverageSupport.ts`
  - `frontend/src/pages/support/AgentDashboard.tsx`
  - `backend/support_portal/services.py`
  - `backend/support_portal/tests.py`
  - `AI_SESSION_DOCUMENTATION.md`
- Verification:
  - `.\.venv\Scripts\python.exe manage.py test support_portal.tests.CoverageOptionsTests support_portal.tests.CoverageTutorWorkflowTests` passed in `backend/` on `2026-06-13`.
  - `npm run build` passed in `frontend/` on `2026-06-13`.
- Follow-up notes:
  - Coach assignment remains optional; if no coach is selected, no coach e-mail is required or persisted.
  - The n8n tutor workflow does not need an immediate structural change for this update because the added coach payload is backward-compatible and can be ignored until the mail template is ready to use it.

### 2026-06-13 - Permanent Delete Action For Archived Tickets
- Request:
  Add a professional `Delete Permanently` action next to `Restore` for archived tickets so support can clean old records intentionally without exposing destructive deletion on active tickets.
- What changed:
  - Added a new admin endpoint `POST /api/admin/tickets/:publicId/delete-permanently`.
  - Permanent deletion is restricted to `superadmin` users, requires the ticket to already be archived, and validates a typed ticket-id confirmation before continuing.
  - The backend permanently deletes the ticket row, lets database cascades remove ticket attachments/history/session-request rows, deletes attachment files from local storage, and deletes the conversation only when no sibling tickets still reference it.
  - When sibling tickets still share the same conversation, the conversation is preserved and its metadata is rewritten so `latest_ticket_public_id`, `parent_ticket_public_id`, and `chat_public_id` no longer point at the deleted ticket.
  - Added destructive UI actions in the archived dashboard table and ticket side panel, both routed through a confirmation modal that requires typing the ticket ID.
- Why it changed:
  - Archived tickets sometimes need full cleanup, but that action should stay deliberate, backup-only reversible, and invisible to non-superadmins.
  - Coverage and follow-up tickets can share conversations, so deletion needed smart conversation cleanup instead of blindly deleting every linked chat thread.
- Files touched:
  - `backend/support_portal/services.py`
  - `backend/support_portal/views.py`
  - `backend/support_portal/urls.py`
  - `backend/support_portal/contracts.py`
  - `backend/support_portal/tests.py`
  - `frontend/src/pages/support/AgentDashboard.tsx`
  - `AI_SESSION_DOCUMENTATION.md`
- Verification:
  - `.\.venv\Scripts\python.exe manage.py test support_portal.tests.AdminTicketPermanentDeleteTests support_portal.tests.CoverageOptionsTests support_portal.tests.CoverageTutorWorkflowTests` passed in `backend/` on `2026-06-13`.
  - `npm run build` passed in `frontend/` on `2026-06-13`.
- Follow-up notes:
  - The destructive action currently uses a typed ticket ID as the final safeguard; if later compliance needs a stronger trail, the next step would be writing these deletions into a dedicated global audit log before the ticket row is removed.
  - A same-day UI fix moved the permanent-delete confirmation dialog to the top-level `AgentDashboard` render tree so archive-table delete buttons can actually open the confirmation modal even when the coverage workspace panel is closed.
  - The archive table was also compacted the same day by merging `Chat ID + Ticket ID` into one column, merging `Status + Status Reason` into one column, and shrinking permanent delete to an icon button so archived rows fit more cleanly without horizontal scroll on common desktop widths.
  - The archive view header was then polished with an explicit `Archive Mode` badge, warm archive-specific styling, an `Archived` scope label, and a more professional reset action label (`Return to Active View` / `Clear Filters`) so users can immediately tell they are outside the live queue.

### 2026-06-20 - Post-2026-06-13 Repo Catch-Up Summary
- Request:
  Refresh durable session memory so newer repo changes made after `2026-06-13` are represented briefly.
- What changed:
  - Reviewed live repo history from `2026-06-15` through `2026-06-18` and recorded the main post-`2026-06-13` behavior changes here.
  - Support portal flows were expanded with learning plan team transfer handling, related dashboard/e-mail/webhook notifications, and local n8n workflow guidance assets.
  - Coverage flow now includes Aptem coach recipient sourcing and a backend SLA alert sync command; support session booking also blocks overlapping session requests.
  - Admin/support UI was refined with restored support header + created-time display, clearer transfer-return vs archive actions, and improved documentation attachment preview behavior.
- Why it changed:
  The session document had stopped at `2026-06-13`, while the live repo contains several newer changes that future sessions should not miss.
- Files touched:
  - `AI_SESSION_DOCUMENTATION.md`
  - Reference review covered `backend/support_portal/services.py`, `backend/support_portal/tests.py`, `backend/support_portal/views.py`, `backend/support_portal/management/commands/sync_coverage_sla_alerts.py`, `frontend/src/pages/support/AgentDashboard.tsx`, `frontend/src/pages/support/ChatSupport.tsx`, `frontend/src/pages/support/EmbeddedBooking.tsx`, `frontend/src/pages/support/InquiryDetails.tsx`, `frontend/src/components/support/SupportLayout.tsx`, and local `docs/` learning-plan workflow notes.
- Verification:
  - Reviewed `git log` entries dated `2026-06-15` through `2026-06-18` on `2026-06-20`.
  - Checked current local context in `Tests_Notes` and `docs/` for newer workflow notes not already captured in this file.
- Follow-up notes:
  - This is a concise catch-up summary, not a full one-entry-per-commit backfill.
  - Local `docs/` learning-plan workflow files and `Tests_Notes` currently appear as working-tree context, so future sessions should treat them as local notes unless they are committed.
  - This partially supersedes the `2026-06-13 - Coverage Coach Fields And Stable Manual E-mail Editing` entry by widening coach recipient sourcing beyond `coach_profiles` to include Aptem owner data.

### 2026-06-20 - Fix Webhook Secret Loading For Open-Ticket n8n Calls
- Request:
  Fix missing `x-support-webhook-secret` on `open/ticket` webhook deliveries even though the secret was already present in `.env.local`.
- What changed:
  - Updated `backend/config/env.py` so `.env.local` and `.env` values now fill env vars that are missing or blank, instead of skipping them whenever the host process already defines the key as an empty string.
  - Added regression tests covering blank-env fallback and non-empty-env preservation for `N8N_COVERAGE_TICKET_WEBHOOK_SECRET`.
- Why it changed:
  The webhook sender already attached the header when Django had a non-empty secret, but the env loader used `setdefault`, so an empty host env var could silently block the file-based secret from loading.
- Files touched:
  - `backend/config/env.py`
  - `backend/support_portal/tests.py`
  - `AI_SESSION_DOCUMENTATION.md`
- Verification:
  - `.\.venv\Scripts\python.exe manage.py test --keepdb support_portal.tests.EnvLoadingTests support_portal.tests.SupportSessionValidationTests.test_send_coverage_ticket_operations_webhook_includes_secret_header_when_configured support_portal.tests.SupportSessionValidationTests.test_send_learning_plan_ticket_transfer_webhook_includes_secret_header_when_configured` passed in `backend/` on `2026-06-20`.
- Follow-up notes:
  - The running backend still needs a restart after deployment so Django reloads env values and starts sending the header on new webhook calls.

### 2026-06-20 - Manual Close Button For Coverage Tickets
- Request:
  Add a close action to coverage tickets like normal/quick tickets, but require a note entry through a popup before the close can be applied.
- What changed:
  - Added a reusable `Close` action for coverage tickets in both the documentation footer and the coverage details footer.
  - The action now opens a dialog that requires an internal note before `Closed via Agent` can be submitted.
  - Coverage close requests now persist the current coverage documentation draft alongside any pending assignee/SLA detail edits so the manual close behaves more like the standard ticket close flow.
  - Coverage save requests now serialize coverage-card attachments more safely before sending them to the backend.
- Why it changed:
  Coverage tickets previously exposed save/tutor-workflow actions only, which made manual closure inconsistent with normal and quick tickets and too easy to attempt without a documented closing note.
- Files touched:
  - `frontend/src/pages/support/AgentDashboard.tsx`
  - `AI_SESSION_DOCUMENTATION.md`
- Verification:
  - `npm run build` passed in `frontend/` on `2026-06-20`.
- Follow-up notes:
  - The close dialog shares the existing coverage note state, so any note already typed in the workspace is prefilled automatically when the close popup opens.
  - A same-day runtime fix removed an accidental `coverageCard.attachments` read from the coverage serializer after the close popup appeared clickable but failed on click before the PATCH request was sent; a dashboard runtime regression test now covers the close-dialog submit path.
