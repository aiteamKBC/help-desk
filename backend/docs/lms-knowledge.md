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
