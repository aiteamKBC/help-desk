# Deploy on Hostinger VPS + OpenLiteSpeed

This project is best deployed on a Hostinger **VPS**. Hostinger states that Python and Django are supported on VPS plans, and OpenLiteSpeed can proxy requests to a backend application server.

## 1. Push the project to GitHub from your local machine

From the repository root:

```powershell
git status
git add backend frontend Knowledge_Base_Builder DEPLOY_HOSTINGER_OPENLITESPEED.md
git commit -m "Deploy support portal and knowledge base updates"
git push origin main
```

If you want to keep local notes or screenshots out of Git, do not stage files like `Tests` or `image.png`.

## 2. Connect to the Hostinger VPS

Replace `YOUR_VPS_IP` with your actual server IP:

```bash
ssh root@YOUR_VPS_IP
```

## 3. Install system packages on the VPS

```bash
apt update
apt install -y git python3 python3-venv python3-pip nodejs npm
```

If your Hostinger template already includes Python or Node.js, these commands will simply ensure they are present.

## 4. Clone the GitHub repository on the VPS

```bash
mkdir -p /var/www/help-desk
cd /var/www/help-desk
git clone https://github.com/aiteamKBC/help-desk.git .
```

If the project already exists on the server:

```bash
cd /var/www/help-desk
git pull origin main
```

## 5. Build the backend environment

```bash
cd /var/www/help-desk/backend
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 6. Add production environment variables

Create or edit `backend/.env`:

```bash
cp /var/www/help-desk/backend/.env.example /var/www/help-desk/backend/.env
nano /var/www/help-desk/backend/.env
```

Minimum production values to change:

- `DATABASE_URL`
- `LEGACY_DATABASE_URL` if you still use legacy import features
- `SUPPORT_PORTAL_PASSWORD`
- `N8N_BOOKING_WEBHOOK_URL`
- `N8N_CHATBOT_WEBHOOK_URL`
- `N8N_ADMIN_AI_WEBHOOK_URL` if needed
- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG=false`
- `DJANGO_ALLOWED_HOSTS=your-domain.com,www.your-domain.com`
- `DJANGO_CSRF_TRUSTED_ORIGINS=https://your-domain.com,https://www.your-domain.com`

## 7. Build the frontend

```bash
cd /var/www/help-desk/frontend
npm ci
npm run build
```

The built frontend will be written to `frontend/dist`, and Django is already configured to serve that build.

## 8. Run Django setup commands

```bash
cd /var/www/help-desk/backend
source .venv/bin/activate
python manage.py migrate
python manage.py apply_support_schema
python manage.py collectstatic --noinput
python manage.py check
```

## 9. Test Gunicorn manually

```bash
cd /var/www/help-desk/backend
source .venv/bin/activate
gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 3
```

Open another SSH session and test:

```bash
curl http://127.0.0.1:8000/api/health
```

Stop Gunicorn with `Ctrl+C` after the health check succeeds.

## 10. Create a systemd service for Django

Create `/etc/systemd/system/helpdesk.service`:

```ini
[Unit]
Description=Help Desk Django Gunicorn
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=/var/www/help-desk/backend
Environment="PYTHONUNBUFFERED=1"
ExecStart=/var/www/help-desk/backend/.venv/bin/gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 3
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Then enable it:

```bash
systemctl daemon-reload
systemctl enable helpdesk
systemctl restart helpdesk
systemctl status helpdesk --no-pager
```

## 11. Configure OpenLiteSpeed as a reverse proxy

In the OpenLiteSpeed WebAdmin panel:

1. Create an **External App** of type **Web Server** pointing to `127.0.0.1:8000`
2. Add a **Proxy Context** for `/` pointing to that external app
3. Map the virtual host to your domain listener

Recommended static mapping:

- URI: `/static/`
- Location: `/var/www/help-desk/backend/staticfiles/`

This lets OpenLiteSpeed serve collected Django static files directly.

## 12. Deployment update commands for later releases

Whenever you push a new release to GitHub, run these commands on the VPS:

```bash
cd /var/www/help-desk
git pull origin main

cd /var/www/help-desk/backend
source .venv/bin/activate
pip install -r requirements.txt

cd /var/www/help-desk/frontend
npm ci
npm run build

cd /var/www/help-desk/backend
python manage.py migrate
python manage.py apply_support_schema
python manage.py collectstatic --noinput
python manage.py check

systemctl restart helpdesk
systemctl status helpdesk --no-pager
```

## 13. Quick rollback

If a new deploy fails:

```bash
cd /var/www/help-desk
git log --oneline -n 5
git checkout PREVIOUS_COMMIT_HASH

cd /var/www/help-desk/frontend
npm ci
npm run build

cd /var/www/help-desk/backend
source .venv/bin/activate
python manage.py collectstatic --noinput
systemctl restart helpdesk
```
