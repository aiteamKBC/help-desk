# LearningOS knowledge import

The support assistant uses the current `LMS_KNOWLEDGE_BASE.md` guide for LMS
questions. Moodle is retained in its existing table as an archive, never queried
by the native assistant. Aptem and Teams remain available for their own questions.
Support-portal documentation remains separate from LMS sign-in instructions.

## Source and import

Initial source: `C:\Users\DELL\Desktop\LMS_V2\LMS_KNOWLEDGE_BASE.md`.
Run from `backend` using the project's virtual environment:

```powershell
.\venv\Scripts\python.exe manage.py import_lms_knowledge 'C:\Users\DELL\Desktop\LMS_V2\LMS_KNOWLEDGE_BASE.md' --archive-moodle
```

This is a read-only dry run. Check its database/host, source hash and role counts.
To apply, append `--apply --expected-host <inspected-DATABASE_URL-host>` and
optionally `--report ..\logs\lms-knowledge-import.json`. The command uses the
existing support DATABASE_URL; it neither provisions a database nor edits env files.

The existing `new_lms_knowledge_base` table stores one complete source snapshot
(no embedding) plus heading-aware embedded chunks, all marked with
`source_key=kbc-learningos-help`. Metadata records source hash, role, section and
embedding model. A repeated identical import does not duplicate or re-embed data.
Changed versions archive the previous version in place. Existing unrelated rows
are preserved. Embeddings are generated before the single write transaction;
failed verification rolls that transaction back.

`--archive-moodle` adds archival metadata to Moodle records without deleting their
text, IDs or embeddings. The command verifies content fingerprints before commit
and independently reads back the current version after commit. No schema migration,
ticket, conversation, attachment, user or authentication changes are performed.

## Answer boundaries

Learner, coach and tutor guidance is labelled separately. The signed-in role,
explicit coach/tutor mode, or self-described role guides wording, not permissions.
Role labels are never access-control grants. Global limitations and "Not live yet"
are included with every LearningOS search, independently of vector relevance.
The model must acknowledge undocumented issues instead of inventing product steps.
Tutor documentation is currently brief; ingesting it cannot cover every tutor issue.

The application must run the updated backend code for the new retrieval filters to
take effect. Database archival metadata alone does not disable external/legacy
workflows that ignore that metadata. Importing knowledge is not a deployment.

## Tests

`support_portal.test_lms_knowledge` contains offline regression tests for section
coverage, role inheritance, embedding validation, version matching, route isolation,
archival filters, role-aware responses and mandatory limitations. Run with isolated
test settings; never point an integration test runner at production to create tables.

## Validation on 2026-10-14

- Applied to the existing support Neon database: one full source snapshot and 48
  chunks; source SHA-256 `b494b2148569653fd170a65b7979c1499a3a5dcc16098eb708f5a79b7acde60e`.
- Archived 163 Moodle rows in place; all IDs, text and embeddings verified unchanged.
  All 64 unrelated records in the new-LMS table were also verified unchanged.
- A second applied run reported the same version, no new Moodle archival and no
  duplicated records. Reports: `logs/lms-knowledge-import-20261014.json` and
  `logs/lms-knowledge-idempotence-20261014.json` (local, gitignored).
- 16 focused offline tests passed, including existing assistant escalation tests.
  The wider suite initially had three failures: two were inherited webhook-secret
  settings and passed when isolated; the remaining admin-update assertion expects
  no `uploaded_files=[]` argument and also fails with the original HEAD chatbot.
  Ticket implementation and existing tests were deliberately left untouched.
- Read-only live reply checks covered learner evidence uploads, coach attendance,
  tutor My Teaching, disabled Messages, and Arabic coach attendance. Answers matched
  the guide. Arabic retrieval distance was about 0.559, above the existing 0.55
  escalation threshold, so it recommended escalation despite correct steps.
  The threshold was not changed; no endpoint that creates tickets/logs was invoked.
- No commit, push or deployment was performed. Live use requires deployment of
  the updated backend; the Neon import itself is already applied.

## Rebuild on 2026-10-15 — code-verified learner sections

The source has no repository of its own (`C:\Users\DELL\Desktop\LMS_V2\LMS_KNOWLEDGE_BASE.md`
is a loose file, not under version control). A snapshot as of this rebuild is kept at
`backend/docs/LMS_KNOWLEDGE_BASE.snapshot.md` in this repo so the content survives even
if that file is lost; it is a copy for reference, not the live import source.

This rebuild was triggered by two observed failures: the assistant gave a different
menu location for Progress Review on consecutive turns, and separately named "KBC
LearningOS" in nearly every reply. Both traced back to the same cause — every chunk's
embedding included the document banner and full heading path, which pulled all 51
vectors within 0.02 of each other, so no LMS question ever cleared the 0.55 confidence
threshold and the model filled the gap by guessing. Fixed in `lms_knowledge.py` by
embedding the heading trail and body only, keeping the banner for display
(`embed_text` vs `text`; see `embed_hash` in chunk metadata so a changed embedding
forces a re-embed even when the stored text is unchanged).

Every new learner-facing claim below was checked against the current frontend source
at `E:\Projects\lms_updates\LMS_v2\frontend\src`, not against `mocks/user-guide-data.ts`
— that file backs the in-app `/user-guide` page and reads as confident, detailed
documentation, but it describes screens already flagged live as sample-data-only
(Support, Gateway, Knowledge Base) with the same confidence as working ones, and at
least one quoted label ("Flag for Review" on the quiz page) does not exist in the
component it is attributed to. Treat it as an index of topics to verify, never as a
source of fact for this document.

Findings from that verification:

- The real learner menu (`mocks/navigation.ts`) groups Monthly Submission, Monthly
  Logs, Monthly Coaching Meeting, Progress Review and Reviews under one "My Progress"
  entry — confirmed correct already; the chatbot's inconsistency was a retrieval gap
  before the embedding fix, not a wrong document (3.2, 3.10a).
- The Catch-Up Learning Hub (`/learner/catchup`) is demo-only in a way the existing
  "Not live yet" list had not caught: its evidence form sets local state and calls no
  endpoint, so "Submit" shows a fake success screen and saves nothing. The real,
  backend-connected catch-up booking and absence report both live inside the
  Attendance page itself (`fetch('/learner_api/session-catchup/...')` in
  `pages/learner/attendance/page.tsx`, and `AbsenceReportForm` posting to
  `api/absenceReports`). Added to "Not live yet" and to 3.12.
- Messages is confirmed still off (`CHAT_ENABLED = false` in `lib/featureFlags.ts`);
  opening `/learner/messages` redirects to `/`. Unchanged from the existing entry.
- `/learner/otjh` and `/learner/ksbs` are not separate pages — both routes render
  `ProgressPage` (`router/config.tsx`), the same component as `/learner/progress`.
- Clubs, Events, Rewards and Flash cards are reached from the Dashboard
  (`learnerDashboardLinks` in `mocks/navigation.ts`), not from the main sidebar;
  Profile is not in either list. Both were previously undocumented (3.15a, 3.15b).
- Monthly Cycle (`/learner/monthly-cycle`) and Learning Plan (`/learner/learning-plan`)
  are real, API-backed views reached as alternate addresses for Monthly Logs and My
  Learning respectively (`matchPaths` in `mocks/navigation.ts`), not separate menu
  items. Previously undocumented; added as 3.9a and a note under 3.3.
- Monthly Coaching Meeting and Progress Review were already accurately documented.
  Added 3.10a to state plainly how they differ from the third, previously-undocumented
  "Reviews" page (`/learner/reviews`, booked/held review history including anything
  imported from the college's previous system).

Prompt changes in `chatbot.py` alongside this: told the assistant LearningOS and the
support service are separate (so a feature switched off in one says nothing about the
other), to stop repeating the product name every reply, to try at least one real
suggestion before saying the support team is needed, and gated escalation so a vague
opening message or a clarifying question from the assistant itself no longer counts as
a failed attempt. Also: the per-model token-cap parameter is chosen per attempt now
(`max_completion_tokens` vs `max_tokens`) rather than silently dropping the cap on the
first rejection, which had been quietly undoing the brevity instructions for gpt-5-era
models.

Re-imported chunk count: 48 → 52 (new: 3.9a, 3.10a, 3.15a, 3.15b, plus expansions to
3.2, 3.3, 3.12, 3.13). `unrelated_knowledge_records_preserved: 64` confirmed unchanged
on apply. 24 offline tests passed (`test_lms_knowledge`, `test_support_hardening`).
No commit, push or deployment was performed for the frontend findings above — they are
documentation only; nothing in the LMS frontend itself was changed.

## Full-site verification pass, same day

Extended the same code-first method across every remaining section of the document —
Calendar, Evidence, Quizzes, My Learning, Video, the onboarding flow, working-hours
rule, Coach, Curriculum, Tutor, Enrolment, Employer, Admin and Engagement — checking
each specific claim (button labels, routes, thresholds, file-format lists) against the
current frontend source rather than rewriting from scratch. Most of the existing
document held up: exact matches confirmed include the quiz question-type list, the
`07:00–19:00` Monday–Friday working-hours window, the four onboarding review names,
"Book my first session" and its tomorrow-earliest rule, the evidence file-size/type
limits, "Signing opens after the month ends" for Monthly Logs (literal string in
`features/monthly-logs/page.tsx`), and the engagement risk thresholds "critical <55,
high <70" (literal string in `pages/engagement/attendance-risk/page.tsx`).

Two factual errors found and corrected:

- **"Unlock monthly log" is admin-only**, not a coach action as the document stated —
  the button is gated `auth.account?.role === 'admin'` in `features/monthly-logs/page.tsx`.
  A coach now gets told to escalate to an admin rather than look for a button they do
  not have.
- **"My Teaching" is the sidebar label for the tutor dashboard, not text on the page
  itself** — the page's actual heading is "Good morning, {name}". Previously stated as
  if it were the page title.

Also expanded Calendar (3.11), previously four lines for a 2,192-line page: added the
Month/Week/Day view switcher, the per-event Join Meeting and Export .ics buttons
(confirming there is no single whole-calendar export), and the real event-type colours
(Live Session, Coaching, Review).

Chunk count unchanged at 52 (the Calendar edit lands inside an existing chunk; the two
corrections are line-level fixes, not new sections). Re-imported and re-tested after
each edit; `unrelated_knowledge_records_preserved: 64` held at every apply. Retrieval
confidence checked directly against both corrections post-import (`0.370` and `0.395`
respectively, well inside the `0.55` threshold).

Sections not touched this pass: the Super Admin and Audit subsections' own claims
(Access Logs, Audit Trail, Platform Report, Monthly Learning Sign-Off Report PDF) were
not independently re-verified against source — spot-checked adjacent code in the same
files but did not trace every listed feature. If a reported issue ever traces to one of
those, verify it the same way before trusting the existing text.
