# Help-Desk — PM Handoff & Branch Plan

**Prepared for:** PM (to split the work into parallel branches and ship today)
**Date:** 2026-10-08
**Repo:** `help-desk` · base branch: `main` (clean)
**Source of truth for backlog:** [`Tests_Notes`](Tests_Notes)

---

## 1. Goal for today

Finish the open backlog by **splitting it into independent branches that can be worked in parallel**, each with a clear scope, acceptance criteria, and a test to prove it. Merge order is defined at the bottom to avoid conflicts.

> There are many edits. The point of this doc is that two or more people/agents can work at the same time without stepping on each other.

---

## 2. Current architecture (quick context)

- **Backend:** Django (`backend/`), main logic in [`support_portal/services.py`](backend/support_portal/services.py), API in [`support_portal/views.py`](backend/support_portal/views.py).
- **Frontend:** React + Vite (`frontend/`), support pages under [`frontend/src/pages/support/`](frontend/src/pages/support/).
- **Integrations:** n8n via webhooks. Config in `backend/.env.local` / [`backend/.env.example`](backend/.env.example).

### Chatbot ("Charlie") — status
- The chatbot is **still powered by n8n via webhook**, proxied through the backend — it is **not** fully migrated into backend logic.
- Entry points: `send_chatbot_webhook()` → [`services.py:16114`](backend/support_portal/services.py#L16114), `send_chatbot_message()` → [`services.py:16139`](backend/support_portal/services.py#L16139), reply parsing `extract_chatbot_reply()` → [`services.py:15620`](backend/support_portal/services.py#L15620). URL = `CHATBOT_WEBHOOK_URL` (also `ADMIN_AI_WEBHOOK_URL`).
- The name "Charlie" is **not** present anywhere in the code — treat it as the product name only.
- **Decision needed:** keep n8n proxy, or move the model + chat-history handling into the backend. Several chatbot bugs below (model/history) are blocked on this decision — owner noted as **Diaa**.

---

## 3. Workstreams → branches (parallelizable)

Each workstream = one branch off `main`. Branch names suggested. "Owner" from Tests_Notes where known.

### Branch A — `fix/live-chat-reliability`  🔴 High
Agent/requester live-chat stability. Mostly frontend + some backend sync.
- [ ] Agent send is slow / text field frozen while sending — free the agent to reply immediately after message arrives on requester side. *(Tests_Notes #live-chat.2)*
- [ ] Message appears/disappears repeatedly while sending (agent side). *(#live-chat.3)*
- [ ] On requester close: agent chat keeps flickering → agent should get a "Requester closed chat" message, chatbox frozen, but still able to document & change status. *(#live-chat.4)*
- [ ] Fix message duplication + forced scroll-to-bottom when scrolling up. *(Needs-Solution #6, #7)*
- [ ] Chatbot intro messages are messed up in live chat. *(#live-chat.1)*
**Files:** `frontend/src/pages/support/ChatSupport.tsx`, `AgentDashboard.tsx`, backend conversation/status in `services.py`.
**Done when:** two-tab test (agent + requester) shows no flicker/duplication, agent replies back-to-back, close event handled.

### Branch B — `fix/chat-status-reasons`  🔴 High
- [ ] When requester closes chat, status must **not** show "Closed via Chatbot" — use a proper reason. *(#live-chat.5)* — see `STATUS_REASON_CLOSING_BY_CHATBOT` [`services.py:80`](backend/support_portal/services.py#L80).
- [ ] Submit ticket: change status to **"Pending"**. *(Submit ticket note)*
- [ ] Closed ticket should leave **one** card in history (fix duplication). *(Ticket section)*
**Done when:** status/status_reason verified in DB for each close path.

### Branch C — `feat/chatbot-improvements`  🟠 Medium (⚠️ partly blocked on Diaa)
- [ ] Preserve chat bubbles — they disappear while bot prepares an answer (repro: navigate back/forth after a question). *(#chatbot.1)*
- [ ] Give chatbot access to `inquiry`. *(#chatbot.2)*
- [ ] Request timeout handling. *(#chatbot.3 — with Hammamo)*
- [ ] "Facing technical issue" → change model + pass chat history. *(#chatbot.4 — Diaa, backend)*
- [ ] Guide to meeting options directly (more data/visuals). *(#chatbot.5)*
- [ ] Fix non-working links + add hyperlinks. *(#chatbot.6 — Diaa + Hammamo)*
- [ ] Chatbot history log to revisit & relearn. *(To Diyaa)*
**Decision gate:** resolve the n8n-vs-backend question in §2 first.

### Branch D — `feat/booking-sessions`  🟠 Medium (Owner: Lutfi)
- [ ] Booking window **08:00 → 15:00 (8→3)**. *(To Lutfi / #booking.1)*
- [ ] Meeting duration 30 min, extendable to 1 hr. *(#booking.1)*
**Files:** [`EmbeddedBooking.tsx`](frontend/src/pages/support/EmbeddedBooking.tsx), `supportBooking` lib, backend availability.

### Branch E — `feat/coverage-tutor-flow`  🟠 Medium
- [ ] Coverage cards: add "x" to remove, remove the "?" in front. *(Needs-Solution bottom)*
- [ ] "Submit to tutor" → n8n workflow (`N8N_MAIL_WEBHOOK_URL` in `.env.local`): send tutor name, email, presentation; response sets status reason **Tutor accepted / rejected**.
- [ ] Notify agent via dashboard on accept/reject.
- [ ] On accept: add acceptance card w/ session details + "Confirm session" button (active only at session time; closing ticket on click).
- [ ] Coverage automatic send to all replacements; first accept → Tutor accepted, others informed.
- [ ] Change tutor email sender in n8n (currently `student@Kent...org`).
- [ ] Ensure SLA deactivated in archive.
- [ ] Add Delete in Archive (superadmin only, by Eng. Ayman) + deletion log.
**Note:** many coverage items already **[Done]** in Tests_Notes — only the unchecked ones above remain.

### Branch F — `feat/ticket-and-kb-polish`  🟢 Low
- [ ] Ticket: attachments in documentation; unify assignment & transfer ordering/logic. *(Ticket section)*
- [ ] Knowledge base: revise "open" format, attachments for links view, resource blocks. *(KB section)*
- [ ] Admin button in knowledge base. *(Needs-Solution #3)*
- [ ] Change Coverage category → **Operations** (not Technical).
- [ ] New "Follow up" ticket category linked to old ticket (transaction flow).
- [ ] Category: Portal: Bugs / Portal: Suggestions and Requests.

### Branch G — `feat/call-availability`  🟠 Medium
- [ ] "Call agent, no agent available": return clear path (currently 503 "Teams calling not linked"). Notify user to wait + notify agents via email & dashboard + browser notification like Teams call. *(Needs-Solution #1)*
- [ ] In call case, create a **call-id** instead of chat. *(Needs-Solution #2)*
- [ ] Agent-available path: assignment + bot message "Live chat requested…" + success toast + notify all agents. *(Needs-Solution #4)*
- [ ] Add transfer message "You are currently speaking to …". *(Needs-Solution #5)*

---

## 4. Suggested owners / split

| Branch | Theme | Suggested owner | Priority |
|---|---|---|---|
| A | Live chat reliability | Hammamo / FE | 🔴 |
| B | Chat status reasons | BE | 🔴 |
| C | Chatbot improvements | Diaa (BE/model) | 🟠 blocked |
| D | Booking 8→3 | Lutfi | 🟠 |
| E | Coverage tutor flow | BE + n8n | 🟠 |
| F | Ticket/KB polish | FE | 🟢 |
| G | Call availability | FE + BE | 🟠 |

---

## 5. Merge order (avoid conflicts)

1. **B** (status reasons) — touches shared `services.py` status constants; merge first.
2. **A** then **G** — both touch `ChatSupport.tsx` / `AgentDashboard.tsx`; A first, G rebases on it.
3. **D**, **E**, **F**, **C** — mostly independent, merge as ready.
4. Rebase each branch on `main` before PR; run frontend + backend tests.

---

## 6. Definition of done (every branch)

- Scope above complete + each item verified with the test noted.
- Fill the relevant rows in the **QA Matrix** at the top of [`Tests_Notes`](Tests_Notes) (Backend Status / Chat State / Learner UI / Admin UI / Proof Source).
- Backend tests pass (`support_portal/tests.py`), frontend tests pass (`frontend/src/test/`).
- PR description lists what changed + proof source.

---

## 7. Open decisions for PM to confirm

1. **Chatbot:** keep n8n proxy, or migrate model + history into backend? (Blocks Branch C.)
2. **Call feature:** is Teams calling integration in scope today, or defer Branch G?
3. **Archive delete:** confirm superadmin-only + logging requirement with Eng. Ayman.
