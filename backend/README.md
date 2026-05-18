# Django Backend

The backend now runs on Django and keeps the support desk API under `/api/...`.

## Layout

- `manage.py`: Django management entrypoint
- `config/`: Django project settings, URL routing, ASGI, and WSGI files
- `support_portal/`: Main Django app for API views and service modules
- `migrations/`: SQL schema used by the support database

## Current Status

- Django serves the support API
- Django can serve the built frontend from `frontend/dist`
- Webhook configuration still uses `backend/.env.local`
- Support schema and learner import commands are available as Django management commands

## Django Setup

For day-to-day development, starting the frontend dev server is now enough because Vite will auto-start Django on `127.0.0.1:3001` when `backend/.venv` is available.

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python manage.py runserver 127.0.0.1:3001
```

If you want to run Django by itself, the command above still works.

## Environment Files

Django reads its environment from:

- `backend/.env.local`
- `backend/.env`

The existing `DATABASE_URL`, `SUPPORT_PORTAL_PASSWORD`, `N8N_BOOKING_WEBHOOK_URL`, and `N8N_CHATBOT_WEBHOOK_URL` values can be reused during migration.

For the admin console AI panel, you can optionally set `N8N_ADMIN_AI_WEBHOOK_URL` to route the AI Agent `Send` button to a dedicated workflow without changing the learner chatbot webhook.

## Management Commands

```powershell
python manage.py apply_support_schema
python manage.py create_support_account username password --email name@example.com --role user
python manage.py import_legacy_learners
```

`support_accounts` is now the single source of truth for support portal and admin sign-in, while `learners` remains the ticket owner/profile store.
