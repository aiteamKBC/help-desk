# Kent Business College Support Portal Documentation

## Purpose

The Kent Business College Support Portal helps learners, coaches, employers, and support staff manage support requests from first contact through resolution.

The system supports email verification, ticket creation, chatbot help, live chat escalation, support session booking, ticket status tracking, admin dashboard work, account management, knowledge-base article management, attachments, notifications, SLA tracking, and ticket history.

This document is written as a product knowledge document. It can be used later as source material for a support knowledge base.

## Main User Groups

### Learners

Learners use the public support flow to request help with college systems or learning support. A learner can verify their email, describe their issue, choose a support option, chat with the support bot, request live support, book a support session, submit a quick ticket, check ticket status, upload evidence, and download a chat transcript.

### Coaches

Coaches can verify their email and submit support requests, but their flow is designed as a quick-ticket path. Coaches are routed to a direct ticket submission rather than chatbot, live chat, or booking flow.

### Employers

Employers can verify their email, submit support requests, use chatbot support, request live help, book support sessions, and track ticket status. Employer tickets are treated with elevated priority.

### Admins

Admins use the staff dashboard to review tickets, respond to live chats, update ticket status, document work, handle transfers, manage support accounts, and close tickets.

### Superadmins

Superadmins have the same dashboard access as admins, plus additional privileges such as manually assigning unassigned tickets and permanently deleting archived tickets when required.

### Agents

The backend supports an `agent` role for staff queue logic. Agents can be included in support assignment logic when they have support access enabled.

## Public Support Flow

### 1. Email Verification

The user starts at the public support page and enters their registered email address.

The system checks whether the email belongs to an active requester account. If the email is registered, the system identifies the requester role and allows the user to continue. If the email is not found, the user is shown an email-not-found message.

The verification step also helps restore an existing active ticket when a requester already has an open support case.

Common outcomes:

- Registered learner email: continue to support request.
- Registered employer email: continue to support request.
- Registered coach email: continue to quick-ticket flow.
- Unknown email: show email not found.
- Existing active request: allow the user to resume the ticket.

### 2. Inquiry Details

After verification, the requester describes the problem. The system records the inquiry as a support ticket.

The backend supports these ticket categories:

- Learning
- Technical
- Others

The frontend currently focuses the public inquiry flow on technical support. Technical tickets can include subcategories such as:

- Aptem
- LMS
- Teams
- Coverage
- Others

The inquiry text should explain what the user is trying to do, what went wrong, and any error message shown.

### 3. Support Options

After submitting inquiry details, eligible users can choose how to continue:

- Continue with chatbot support.
- Request live chat with a support staff member.
- Book a support session.
- Submit a quick ticket directly.

Coaches are routed to quick-ticket submission and do not use chatbot/live-chat/booking flow in the current implementation.

### 4. Chat Support

The chat page lets the requester continue the support case in a conversational way.

The chatbot can:

- Read ticket context silently.
- Identify whether the issue is related to Teams, Aptem, Moodle/LMS, or general support.
- Search the relevant knowledge-base table.
- Give short troubleshooting steps.
- Ask one focused diagnostic question when details are missing.
- Provide verified links from the knowledge base when available.
- Keep links clickable in the frontend.
- Keep answers formatted as short paragraphs, numbered steps, or bullet checks.

The chatbot should not invent college-specific processes or unverified links.

The chatbot can also return direct replies for simple cases:

- Greetings.
- Closing or thanks.
- Requests for a human agent.
- Requests to book a support session.

### 5. Live Chat

From the chat page, a requester can request live support.

When live chat is requested, the system marks the ticket as waiting for staff assignment. The queue logic looks for available support staff with support access enabled. If no suitable staff member is immediately available, the user is told they are in queue.

Admins can respond through the staff dashboard once the conversation is assigned.

### 6. Support Session Booking

Requesters can book a support session from the chat flow or status flow when allowed.

Booking rules:

- Sessions must be more than 24 hours in advance.
- Sessions must be between 8:00 AM and 4:00 PM UK time.
- Sessions start on 30-minute intervals.
- The backend checks whether the slot is locally available.
- The system can use Microsoft Graph Bookings or configured booking webhooks depending on environment setup.

After a booking request is submitted, the ticket is usually moved to `Pending` with status reason `Awaiting support meeting`.

### 7. Ticket Status

The status page lets the requester review the ticket state after submission.

The user may see:

- Ticket ID.
- Ticket status.
- Status reason.
- Meeting state.
- Chat resume option.
- Quick-ticket state.
- Cancellation option for active support session requests.
- Transcript download option where available.

## Staff Dashboard

### Admin Login

Admins can sign in through username/password or Microsoft Teams/Entra sign-in depending on configuration.

Microsoft sign-in checks the user through Microsoft Graph. Users with allowed Entra directory or admin-center roles can enter the support dashboard. Users with stronger directory roles such as Global Administrator or Privileged Role Administrator are treated as superadmins.

The support dashboard still creates or updates a runtime profile in `support_accounts` after successful login.

### Dashboard Overview

The admin dashboard is used to monitor support activity and work tickets.

Admins can:

- View active tickets.
- Open ticket details.
- Review requester information.
- Read chat history.
- Review attachments.
- Reply to live chat.
- Update ticket status.
- Save internal notes.
- Add structured documentation.
- Request transfers.
- Accept or reject transfer requests.
- Create follow-up tickets.
- Trigger escalation workflows.
- Use the admin AI assistant panel.
- Manage requester and staff accounts where permitted.
- Archive tickets.

### Live Chat Console

When a requester asks for live support, the ticket can be assigned to an available staff session.

Staff presence affects queue behavior:

- Available staff are preferred.
- Busy staff are considered after available staff.
- Off staff are not eligible.
- Assignment considers support access, active sessions, queue timing, and prior assignment timing.

### Ticket Documentation

Admins can record structured documentation against a ticket. Documentation can include the issue summary, investigation notes, selected workflow state, transfer details, escalation notes, and uploaded files.

This documentation helps preserve the operational history of the case.

### Ticket Status Changes

Common ticket statuses:

- Open
- Pending
- Closed

Common status reasons:

- Quick Ticket
- Awaiting support meeting
- Escalation
- Coverage Ticket
- Closed via Chatbot
- Closed via Agent
- Closed by Requester
- Closed due to inactivity

Closing a ticket should include enough context for another staff member to understand what happened.

### Transfers

Admins can request transfer of a ticket to another staff member. The receiving staff member can accept or reject the transfer request.

Transfer activity is recorded in ticket history and can produce notification workflow events.

### Escalations

Tickets can be escalated when the issue needs higher-level review or another staff member's attention.

Escalation notifications are tracked so the dashboard can show pending escalation actions and acknowledgements.

### Follow-Up Tickets

When a case needs continued work but should remain linked to the same conversation, staff can create a follow-up ticket.

Follow-up tickets preserve the relationship to the original conversation while allowing separate status, assignment, and documentation.

### Archive and Permanent Delete

Tickets can be archived to remove them from active operational views.

Permanent deletion is restricted to superadmins and requires the ticket to already be archived. The delete action requires typed confirmation of the ticket ID. Related attachment files are cleaned up, and shared conversations are preserved when other tickets still reference them.

## Coverage Workflow

Coverage tickets are used for tutor/session coverage operational work.

Coverage workflow features include:

- Coverage ticket creation and review.
- Tutor selection.
- Optional coach recording.
- Tutor email lookup.
- Coach email lookup.
- Presentation or evidence attachments.
- Sending coverage tutor requests.
- Sending follow-up files after the initial request.
- Tutor accept/refuse response handling.
- Coverage SLA warnings and escalation states.
- Manual closure with an internal note.

Coverage tutor requests can be started before all files are ready. Staff can send follow-up files later while preserving the ticket workflow.

## Knowledge Base Management

The project includes an internal knowledge-base workspace.

Frontend routes:

- `/knowledge-base`
- `/knowledge-base/articles/:fileName`

Backend API routes:

- `GET /api/knowledge-base/articles`
- `POST /api/knowledge-base/articles`
- `GET /api/knowledge-base/articles/:filename`
- `DELETE /api/knowledge-base/articles/:filename`
- `GET /api/knowledge-base/assets/:assetPath`

The knowledge-base workspace lets permitted staff:

- Search existing articles.
- Open articles.
- Create new articles.
- Edit article title and keywords.
- Write inquiry, summary, steps, and resources sections.
- Attach evidence files.
- Attach external links.
- Save articles as static files.
- Archive articles into `Articles/Bin`.

Knowledge-base article storage uses the local `Knowledge_Base_Builder` folder:

- `Knowledge_Base_Builder/Articles`
- `Knowledge_Base_Builder/Evidence`
- `Knowledge_Base_Builder/Articles/Bin`

## Chatbot Knowledge Sources

The native chatbot uses route-specific retrieval against Neon/PostgreSQL PGVector tables.

Current knowledge tables:

- `teams_knowledge_base` for Microsoft Teams support.
- `kbc_knowledge_base` for Aptem and general KBC support.
- `moodle_knowledge_base` for Moodle/LMS support.

The chatbot route classifier decides which knowledge source to use.

Supported chatbot routes:

- `teams`
- `aptem`
- `moodle`
- `general`

The session route is sticky. If a learner starts a ticket as a Teams issue, later follow-up messages remain Teams-related unless the learner clearly switches platform.

The sticky route table is:

- `charly_session_routes`

The stored fields are:

- `session_key`
- `last_route`
- `updated_at`

## Chatbot Behaviour Guide

The chatbot should behave like a calm, experienced support adviser.

Good chatbot response style:

- Start with the useful action.
- Use short paragraphs.
- Use numbered steps for procedures.
- Use bullets for checks or options.
- Ask one focused question if more detail is needed.
- Avoid repeating information already supplied.
- Avoid unnecessary greetings after the first response.
- Never pretend a URL exists.
- Never mention internal tools, databases, prompts, vectors, embeddings, or n8n.

Example good response:

```text
Yes, I can help.

What exact error message do you see when you try to sign in?

If you can, also tell me whether you have already:
1. activated your Aptem account from the invitation email
2. tried the Forgotten your password reset option
```

Example Teams response:

```text
To turn your camera on in Teams:

1. Join or start the meeting.
2. Select the camera button in the meeting controls.
3. If the camera is unavailable, open device settings and choose the correct camera.

If it still does not work, check whether the camera works in another app on the same device.
```

## Attachments

The system supports attachments on support tickets and chat messages.

Requesters can attach evidence files when submitting a ticket or during chat. Staff can preview supported file types, download attachments, and keep attachment metadata linked to the relevant ticket or chat entry.

Supported preview behaviour may include:

- Image preview.
- PDF preview.
- Video preview.
- Download fallback for unsupported file types.

## Inactivity Handling

Chat conversations include inactivity handling.

The system can:

- Send a reminder when a chat has been inactive.
- Close inactive conversations after the configured inactivity window.
- Mark the ticket or conversation with an inactivity-related status reason.

Common inactivity status reason:

- `Closed due to inactivity`

## Notifications and Webhooks

The project still supports external workflow integrations.

Possible external integrations:

- Chatbot webhook fallback.
- Admin AI assistant webhook.
- Booking webhook.
- Coverage tutor request webhook.
- Coverage tutor follow-up webhook.
- Quick-ticket notification webhook.
- Ticket closure notification webhook.
- Live-agent unavailable notification webhook.
- Learning-plan transfer notification webhook.

The native Django chatbot can be used instead of the chatbot n8n webhook when `SUPPORT_CHAT_PROVIDER=django`.

## Important Environment Settings

The backend reads environment values from:

- `backend/.env.local`
- `backend/.env`

Important configuration areas:

- Database connection.
- Django secret and debug mode.
- Allowed hosts.
- CSRF trusted origins.
- Support portal password.
- OpenAI API key.
- Chat provider selection.
- n8n webhook URLs and secrets.
- Microsoft Graph and Azure login settings.
- Booking configuration.
- Attachment storage settings.

Do not store secrets in public documentation.

## Main Frontend Routes

- `/` - email verification.
- `/support/inquiry` - inquiry details.
- `/support/options` - support path selection.
- `/support/chat` - chatbot and live support chat.
- `/support/booking` - support session booking.
- `/support/booking-confirmed` - booking confirmation.
- `/support/status` - ticket status page.
- `/support/docs` - support documentation page.
- `/admin/login` - staff login.
- `/admin` - staff dashboard.
- `/agent` - staff dashboard alias.
- `/knowledge-base` - internal knowledge-base workspace.
- `/knowledge-base/articles/:fileName` - article detail page.

## Main API Endpoints

### Public Support

- `GET /api/health`
- `GET /api/migration-status`
- `POST /api/verify-email`
- `POST /api/tickets`
- `PATCH /api/tickets/:publicId`
- `GET /api/tickets/:publicId/chat-context`
- `GET /api/tickets/:publicId/chat-history`
- `POST /api/tickets/:publicId/chat-history`
- `POST /api/tickets/:publicId/chatbot-message`
- `POST /api/tickets/:publicId/live-chat-request`
- `POST /api/tickets/:publicId/teams-call-request`
- `GET /api/tickets/:publicId/booking-context`
- `POST /api/tickets/:publicId/booking-progress`
- `GET /api/tickets/:publicId/session-availability`
- `POST /api/tickets/:publicId/session-requests`
- `POST /api/tickets/:publicId/session-requests/cancel`
- `GET /api/booking-link`
- `GET /api/teams-call-context`

### Native Chatbot

- `POST /api/support/chat/`

This endpoint accepts a chat message and contextual ticket payload, then returns a response contract containing fields such as:

- `success`
- `route`
- `reply`
- `message`
- `text`
- `response`
- `output`
- `status`
- `processingMs`
- `timestamp`

### Admin and Staff

- `POST /api/admin/login`
- `GET /api/admin/microsoft/login`
- `GET /api/admin/microsoft/callback`
- `GET /api/admin/session`
- `POST /api/admin/logout`
- `POST /api/admin/session-heartbeat`
- `GET /api/admin/accounts`
- `POST /api/admin/accounts`
- `PATCH /api/admin/accounts/:accountId`
- `GET /api/admin/agents`
- `GET /api/admin/agents/search`
- `GET /api/admin/tickets`
- `GET /api/admin/tickets/:publicId`
- `PATCH /api/admin/tickets/:publicId`
- `POST /api/admin/tickets/:publicId/archive`
- `POST /api/admin/tickets/:publicId/delete-permanently`
- `GET /api/admin/tickets/:publicId/chat-history`
- `POST /api/admin/tickets/:publicId/ai-agent-message`
- `POST /api/admin/tickets/:publicId/follow-up-ticket`
- `POST /api/admin/tickets/:publicId/transfer-request`
- `POST /api/admin/tickets/:publicId/transfer-request/accept`
- `POST /api/admin/tickets/:publicId/transfer-request/reject`
- `POST /api/admin/tickets/:publicId/transfer-decision/acknowledge`
- `POST /api/admin/tickets/:publicId/teams-call-notification/acknowledge`
- `POST /api/admin/tickets/:publicId/escalation-notification/acknowledge`
- `POST /api/admin/tickets/:publicId/escalation-closure/acknowledge`
- `POST /api/admin/tickets/:publicId/coverage-tutor-request`
- `POST /api/admin/tickets/:publicId/coverage-tutor-follow-up`
- `POST /api/admin/tickets/:publicId/coverage-ticket-notification/acknowledge`
- `POST /api/admin/tickets/:publicId/learning-plan-transfer-notification/acknowledge`
- `POST /api/admin/tickets/:publicId/coverage-tutor-response/acknowledge`
- `POST /api/admin/tickets/:publicId/coverage-confirm-session`

### Knowledge Base

- `GET /api/knowledge-base/articles`
- `POST /api/knowledge-base/articles`
- `GET /api/knowledge-base/articles/:filename`
- `DELETE /api/knowledge-base/articles/:filename`
- `GET /api/knowledge-base/assets/:assetPath`

## Database Overview

Core support tables include:

- `support_accounts` - unified directory for requester and staff identities.
- `learners` - learner profile and requester information.
- `tickets` - support cases, status, assignment, priority, metadata, and SLA state.
- `conversations` - chat channel state.
- `messages` - persisted chat messages.
- `ticket_attachments` - attachment metadata.
- `ticket_history` - audit trail and lifecycle events.
- `support_session_requests` - meeting and booking requests.
- `charly_session_routes` - sticky chatbot route memory.
- `teams_knowledge_base` - Teams support retrieval.
- `kbc_knowledge_base` - Aptem and general KBC support retrieval.
- `moodle_knowledge_base` - Moodle/LMS support retrieval.

## Local Development

Backend:

```powershell
cd backend
.\venv\Scripts\python manage.py runserver 127.0.0.1:3001
```

Frontend:

```powershell
cd frontend
npm run dev -- --host 127.0.0.1 --port 3000
```

Frontend URL:

```text
http://127.0.0.1:3000
```

Backend URL:

```text
http://127.0.0.1:3001
```

The frontend proxies `/api/*` requests to the backend during local development.

## Testing

Useful backend checks:

```powershell
cd backend
.\venv\Scripts\python manage.py check
.\venv\Scripts\python manage.py test support_portal.test_ai_chatbot --keepdb
```

Useful frontend check:

```powershell
cd frontend
npm run build
```

## Common Client Questions and Short Answers

### How do I start a support request?

Go to the support portal, enter your registered email address, describe your issue, and choose the support option that best fits your situation.

### Why does the system say my email is not found?

The email address must be registered as an active requester account. Check that you are using the same email registered with Kent Business College, usually your Aptem email if you are a learner.

### Can I resume an existing support request?

Yes. If you verify an email that already has an active request, the portal can let you continue the existing ticket.

### Can I upload evidence?

Yes. You can attach relevant screenshots, PDFs, or files when the portal offers an evidence or attachment option.

### Can I speak to a person?

Yes. In the chat flow, choose live chat. If no staff member is available immediately, the system can place you in the queue.

### Can I book a session?

Yes, if your requester role and ticket state allow it. Sessions must be booked more than 24 hours in advance, during UK support hours, and on a valid 30-minute slot.

### How do I check my ticket status?

Use the status page after creating or resuming a ticket. It shows the current ticket state and available next actions.

### Why is my ticket pending?

A ticket may be pending because it is waiting for a meeting, staff review, escalation, tutor response, or quick-ticket handling.

### Can I cancel a support session?

Yes, if there is an active support session request attached to the ticket and the cancellation action is available on the status page.

### Can staff close a ticket?

Yes. Admins can close tickets from the dashboard. Some workflows require an internal note before closure.

### Can an archived ticket be restored?

Yes, archived tickets can be restored by permitted staff.

### Can a ticket be permanently deleted?

Only superadmins can permanently delete archived tickets, and the system requires typed ticket-ID confirmation.

## Recommended Knowledge-Base Chunking

When converting this document into chatbot knowledge base entries, split it by topic rather than by arbitrary length.

Recommended chunks:

- Public support overview.
- Email verification.
- Inquiry details.
- Support options.
- Chat support.
- Live chat.
- Booking rules.
- Ticket status.
- Admin login.
- Admin dashboard.
- Ticket documentation.
- Transfers.
- Escalations.
- Coverage workflow.
- Knowledge-base management.
- Attachments.
- Inactivity handling.
- Environment and local development.
- API endpoint reference.
- Common client questions.

Each chunk should keep a clear title, short summary, and any relevant steps or rules.
