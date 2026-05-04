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

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python manage.py runserver 127.0.0.1:3001
```

## Environment Files

Django reads its environment from:

- `backend/.env.local`
- `backend/.env`

The existing `DATABASE_URL`, `SUPPORT_PORTAL_PASSWORD`, `N8N_BOOKING_WEBHOOK_URL`, and `N8N_CHATBOT_WEBHOOK_URL` values can be reused during migration.

## Management Commands

```powershell
python manage.py apply_support_schema
python manage.py import_legacy_learners
```
