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
