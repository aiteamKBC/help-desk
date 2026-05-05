# Help Desk Documentation

## Overview

This repository contains a Kent Business College help desk application with:

- A `React + Vite + TypeScript` frontend in `frontend/`
- A `Django` backend in `backend/`
- A PostgreSQL-backed support workflow for learner verification, ticket creation, chat history, admin ticket management, and support session requests

The frontend runs on `127.0.0.1:3000` in development and proxies `/api` requests to the Django backend on `127.0.0.1:3001`.

## Current Functional Summary

- Learners verify their email before opening a ticket
- Learners create support tickets with category, inquiry details, and evidence attachments
- Evidence uploads are limited to `images`, `PDFs`, and `videos`
- Learners can continue chatting after sending messages
- The support chat exposes quick actions after enough user interaction
- The booking shortcut currently opens the official Outlook Bookings page in a new tab
- Admin users can log in, review tickets, update ticket state, and inspect support session requests

## Repository Structure

```text
support/
├─ backend/
│  ├─ config/
│  ├─ migrations/
│  ├─ support_portal/
│  ├─ manage.py
│  ├─ requirements.txt
│  └─ .env.example
├─ frontend/
│  ├─ public/
│  ├─ src/
│  ├─ package.json
│  └─ vite.config.ts
├─ README.md
└─ Help_Desk _Documentation.md
```

## Frontend Workflow

### Learner Journey

1. The learner lands on `/` and enters a registered email address.
2. The frontend calls `POST /api/verify-email`.
3. If the email is valid, the learner moves to `/support/inquiry`.
4. The learner selects a category:
   - `Learning`
   - `Technical`
   - `Others`
5. If the category is `Technical`, the learner must also choose a technical subcategory:
   - `Aptem`
   - `LMS`
   - `Teams`
6. The learner writes the inquiry and optionally uploads evidence.
7. Accepted evidence types are:
   - `image/*`
   - `application/pdf`
   - `video/*`
8. The frontend creates the ticket through `POST /api/tickets`.
9. The learner moves to `/support/chat`.
10. Chat messages are sent to `POST /api/tickets/:publicId/chatbot-message`.
11. After enough learner interaction, quick actions appear:
   - `Book a Support Session`
   - `Speak to Live Agent`
12. The booking quick action currently opens the external Outlook Bookings URL:
   - `https://outlook.office.com/book/StudentSupport1@kentbusinesscollege.com/s/Z4Zc9rZxw0mEOB417C5bVQ2`
13. When the learner closes the chat, the frontend stores chat history through `POST /api/tickets/:publicId/chat-history` and navigates to `/support/status`.
14. From the status page, the learner can export the saved conversation as a PDF.

### Support Session Booking Notes

- The in-app booking dialog and backend validation support a booking window of `8:00 AM to 4:00 PM UK time`
- The current quick action in chat opens the external Outlook Bookings page instead of completing the booking form inside the app
- A separate `BookingConfirmed` page exists in the frontend, but the active quick-action flow now points to Outlook Bookings

### Admin Journey

1. Admin users log in at `/admin/login`.
2. Successful login stores an admin session in the frontend.
3. Protected routes:
   - `/admin`
   - `/agent`
4. The admin dashboard can:
   - list tickets
   - view ticket details
   - inspect chat history
   - inspect attachments
   - inspect support session requests
   - update ticket fields such as status, assignment, and SLA state

## Backend Workflow

### Runtime Responsibilities

The Django backend is responsible for:

- verifying learner identity by email
- reading and writing support tickets
- storing session requests
- storing chat history
- serving admin ticket data
- calling external webhooks for chatbot and booking integrations
- optionally serving the built frontend from `frontend/dist`

### Key API Endpoints

The active backend contract includes:

- `POST /api/verify-email`
- `POST /api/admin/login`
- `GET /api/admin/agents`
- `GET /api/admin/tickets`
- `GET /api/admin/tickets/:publicId`
- `PATCH /api/admin/tickets/:publicId`
- `POST /api/tickets`
- `PATCH /api/tickets/:publicId`
- `POST /api/tickets/:publicId/chat-history`
- `POST /api/tickets/:publicId/chatbot-message`
- `POST /api/tickets/:publicId/session-requests`

### Learner Lookup Behavior

Email verification uses a two-step strategy:

1. Check the local `learners` table
2. If not found, try syncing the learner from the legacy KBC source through `LEGACY_DATABASE_URL`

This makes the verification flow more tolerant when a learner exists in the legacy source but has not yet been imported locally.

### Booking Integration Behavior

The backend contains support-session webhook logic that:

- validates session times
- builds booking payloads
- posts booking requests to `N8N_BOOKING_WEBHOOK_URL`
- reads booking webhook responses
- records whether a reservation was confirmed or unavailable

This logic is present even though the active learner chat shortcut currently opens Outlook Bookings externally.

## Tech Stack

### Frontend

- React 18
- TypeScript
- Vite
- React Router
- TanStack Query
- Tailwind CSS
- Radix UI
- Sonner for notifications
- Vitest for frontend tests

### Backend

- Django 5.2
- psycopg 3
- PostgreSQL via `DATABASE_URL`

## Configuration and Environment

The backend reads environment variables from:

- `backend/.env.local`
- `backend/.env`

Important environment values:

- `DATABASE_URL`
- `LEGACY_DATABASE_URL`
- `SUPPORT_PORTAL_PASSWORD`
- `N8N_BOOKING_WEBHOOK_URL`
- `N8N_CHATBOT_WEBHOOK_URL`
- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `SUPPORT_SESSION_DURATION_MINUTES`

## Local Development

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python manage.py runserver 127.0.0.1:3001
```

### Frontend

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 3000
```

### Useful Backend Commands

```powershell
cd backend
.\.venv\Scripts\python manage.py check
.\.venv\Scripts\python manage.py test support_portal
.\.venv\Scripts\python manage.py apply_support_schema
.\.venv\Scripts\python manage.py import_legacy_learners
```

### Useful Frontend Commands

```powershell
cd frontend
npm run build
npm run test
npm run lint
```

## Data and Persistence

The SQL schema in `backend/migrations/001_support_schema.sql` covers:

- `learners`
- `agents`
- `tickets`
- `ticket_attachments`
- `ticket_history`
- `support_session_requests`

The backend relies heavily on direct SQL through Django database cursors instead of Django ORM models for the main support workflow.

## Git Workflow

### Branching

Observed project flow:

- `main` is the default branch
- feature work can be developed on separate branches
- one recent example branch was `support-workflow-updates`

### Pull Requests

A `PR` means `Pull Request` in GitHub. It is the request to merge one branch into another, typically after review.

Recommended workflow:

1. Create a feature branch from `main`
2. Make and test changes locally
3. Push the branch to GitHub
4. Open a pull request into `main`
5. Review and resolve conflicts if `main` has moved
6. Merge the pull request
7. Pull the updated `main` locally

## GitHub Actions

### Current Status

At the time this document was created, the repository does **not** contain a `.github/workflows/` directory.

That means:

- no GitHub Actions workflow files are currently configured in the repository
- no repository-defined CI/CD pipeline is available from source control
- no workflow-run history can be documented from checked-in workflow definitions

### Current Result

Because no GitHub Actions workflows are configured in the repository, the GitHub Actions result is:

- `No workflow files found`
- `No repository CI results available from GitHub Actions configuration`

## Latest Verification Results

Since no GitHub Actions workflows are configured, the following local verification results are the current project health reference captured during documentation work:

- `backend\\.venv\\Scripts\\python manage.py test support_portal`  
  Result: `7 tests passed`

- `backend\\.venv\\Scripts\\python manage.py check`  
  Result: `System check identified no issues`

- `frontend\\npm run build`  
  Result: `Build completed successfully`

- Runtime verification:
  - frontend confirmed on `http://127.0.0.1:3000`
  - backend confirmed on `http://127.0.0.1:3001`
  - proxied email verification endpoint returned `200 OK`

### Non-Blocking Warning Observed

During frontend build and dev startup, Vite emitted a non-blocking recommendation:

- the project currently uses `@vitejs/plugin-react-swc`
- Vite recommends `@vitejs/plugin-react` when no SWC-specific plugins are used

This is a tooling recommendation only and does not currently block builds or runtime behavior.

## Known Gaps / Follow-Up Items

- The root `README.md` is currently only a short change note and not a full onboarding document
- No GitHub Actions workflow files are present
- The `BookingConfirmed` page still contains a dummy meeting link placeholder
- Outlook Bookings is opened externally rather than being completed entirely within the app
- If a full Microsoft Bookings or Teams automation is required, the Graph API or webhook flow should be finalized and documented separately

## Suggested Next Improvements

- Add a real project-level `README.md` with setup and architecture summary
- Add `.github/workflows/` CI for backend tests and frontend build
- Replace the placeholder meeting link with real booking confirmation data
- Add explicit API tests for ticket creation, chat history, and admin ticket updates
- Add lint and test automation to GitHub Actions once workflow files are created
