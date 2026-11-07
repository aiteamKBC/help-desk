"""Direct Microsoft Graph e-mail sender for support notifications.

In-backend replacement for the n8n webhook delivery. Uses the app-only (client
credentials) flow with the Mail.Send application permission and sends as
``settings.AZURE_MAIL_SENDER``. Dependency-free (standard-library ``urllib``).

``send_notification_via_graph`` takes the same payload the webhook layer builds
(``build_support_notification_webhook_payload``) and renders a Kent-branded
e-mail per event, so the notification call sites don't change. All helpers return
``{configured, delivered, status, response}`` like the webhook sender.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from django.conf import settings
from django.utils.html import escape

logger = logging.getLogger(__name__)

_GRAPH_SEND_URL = "https://graph.microsoft.com/v1.0/users/{sender}/sendMail"
_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
_SCOPE = "https://graph.microsoft.com/.default"
_TIMEOUT = 25

_token_cache: dict[str, Any] = {"value": None, "expires_at": 0.0}
_token_lock = threading.Lock()


# --------------------------------------------------------------------------- #
# Transport                                                                   #
# --------------------------------------------------------------------------- #
def is_graph_mail_configured() -> bool:
    return bool(
        settings.AZURE_MAIL_TENANT_ID
        and settings.AZURE_MAIL_CLIENT_ID
        and settings.AZURE_MAIL_CLIENT_SECRET
        and settings.AZURE_MAIL_SENDER
    )


def _post(url: str, *, data: bytes, headers: dict[str, str]) -> tuple[int, str]:
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001 - transport failure is reported, not raised
        return 0, str(exc)[:200]


def _get_token() -> str | None:
    now = time.time()
    with _token_lock:
        if _token_cache["value"] and _token_cache["expires_at"] - 60 > now:
            return _token_cache["value"]
        body = urllib.parse.urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": settings.AZURE_MAIL_CLIENT_ID,
                "client_secret": settings.AZURE_MAIL_CLIENT_SECRET,
                "scope": _SCOPE,
            }
        ).encode()
        status, raw = _post(
            _TOKEN_URL.format(tenant=settings.AZURE_MAIL_TENANT_ID),
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = {}
        token = payload.get("access_token")
        if not token:
            logger.warning("Graph mail token request failed (%s): %s", status, raw[:300])
            return None
        _token_cache["value"] = token
        _token_cache["expires_at"] = now + int(payload.get("expires_in", 3600))
        return token


def send_graph_mail(
    *,
    to: list[str],
    subject: str,
    html: str,
    cc: list[str] | None = None,
    sender: str | None = None,
) -> dict[str, Any]:
    recipients = [a for a in (to or []) if a]
    if not is_graph_mail_configured() or not recipients:
        return {"configured": False, "delivered": False, "status": None, "response": None}
    token = _get_token()
    if not token:
        return {"configured": True, "delivered": False, "status": None, "response": "token_error"}
    message: dict[str, Any] = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html},
            "toRecipients": [{"emailAddress": {"address": a}} for a in recipients],
        },
        "saveToSentItems": True,
    }
    if cc:
        message["message"]["ccRecipients"] = [{"emailAddress": {"address": a}} for a in cc if a]
    status, raw = _post(
        _GRAPH_SEND_URL.format(sender=urllib.parse.quote(sender or settings.AZURE_MAIL_SENDER)),
        data=json.dumps(message).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    delivered = status == 202
    if not delivered:
        logger.warning("Graph sendMail failed (%s) to %s: %s", status, recipients, raw[:300])
    return {"configured": True, "delivered": delivered, "status": status, "response": raw[:500] or None}


# --------------------------------------------------------------------------- #
# Kent-branded templates                                                      #
# --------------------------------------------------------------------------- #
_BRAND = "#4f46e5"
_INK = "#0f172a"
_MUTED = "#64748b"
_BORDER = "#e2e8f0"
_SOFT = "#f8fafc"
_CANVAS = "#f3f5f9"


def _email_visual_theme(title: str) -> tuple[str, str, str, str]:
    """Return badge label, foreground, background and border for the hero."""
    normalized_title = (title or "").strip().lower()
    if "closed" in normalized_title:
        return "Resolved", "#047857", "#ecfdf5", "#a7f3d0"
    if "unavailable" in normalized_title:
        return "Action required", "#b45309", "#fffbeb", "#fde68a"
    if "new" in normalized_title or "ai team" in normalized_title:
        return "New request", "#6d28d9", "#f5f3ff", "#ddd6fe"
    if "received" in normalized_title:
        return "Request received", "#4338ca", "#eef2ff", "#c7d2fe"
    return "Ticket update", "#0369a1", "#f0f9ff", "#bae6fd"


def _portal_base() -> str:
    return (settings.SUPPORT_PORTAL_PUBLIC_BASE_URL or "").rstrip("/")


def _ticket_url(payload: dict[str, Any]) -> str:
    """Student e-mails deep-link to the learner's tickets; staff to the dashboard."""
    if payload.get("recipientType") == "requester":
        base = _portal_base()
        return f"{base}/support/my-tickets" if base else ""
    if payload.get("recipientType") == "submitted_for_learner":
        return ""
    return (payload.get("ticket") or {}).get("dashboardUrl") or f"{_portal_base()}/admin"


def _button(text: str, url: str) -> str:
    if not url:
        return ""
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:24px 0 0">'
        f'<tr><td style="border-radius:10px;background:{_BRAND};box-shadow:0 7px 16px rgba(79,70,229,.22)">'
        f'<a href="{escape(url)}" style="display:inline-block;padding:13px 22px;color:#ffffff;'
        f'font-size:14px;line-height:18px;font-weight:700;text-decoration:none;border-radius:10px">'
        f'{escape(text)} &nbsp;&rarr;</a>'
        f'</td></tr></table>'
    )


def _base_email(*, title: str, intro_html: str, rows: list[tuple[str, str]], cta: tuple[str, str] | None, note_html: str) -> str:
    visible_rows = [(label, value_html) for label, value_html in rows if value_html]
    detail = "".join(
        f'<tr>'
        f'<td class="detail-label" style="padding:13px 18px;color:{_MUTED};font-size:12px;line-height:18px;'
        f'font-weight:700;letter-spacing:.35px;text-transform:uppercase;width:32%;vertical-align:top;'
        f'{"border-bottom:1px solid " + _BORDER if index < len(visible_rows) - 1 else ""}">{escape(label)}</td>'
        f'<td class="detail-value" style="padding:13px 18px;color:{_INK};font-size:14px;line-height:20px;'
        f'font-weight:600;word-break:break-word;vertical-align:top;'
        f'{"border-bottom:1px solid " + _BORDER if index < len(visible_rows) - 1 else ""}">{value_html}</td>'
        f'</tr>'
        for index, (label, value_html) in enumerate(visible_rows)
    )
    badge_label, accent, accent_soft, accent_border = _email_visual_theme(title)
    cta_html = _button(*cta) if cta else ""
    note_block = (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="margin-top:22px;background:{_SOFT};border:1px solid {_BORDER};border-radius:12px">'
        f'<tr><td style="padding:14px 16px;color:{_MUTED};font-size:13px;line-height:20px">'
        f'<span style="color:{_INK};font-weight:700">Need anything else?</span><br>{note_html}'
        f'</td></tr></table>'
        if note_html else ""
    )
    return f"""\
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="x-apple-disable-message-reformatting">
  <title>{escape(title)}</title>
  <style>
    @media only screen and (max-width:620px) {{
      .email-shell {{ padding:16px 8px !important; }}
      .email-card {{ border-radius:16px !important; }}
      .brand-cell {{ padding:18px 20px !important; }}
      .hero-cell {{ padding:25px 20px 22px !important; }}
      .content-cell {{ padding:22px 20px 26px !important; }}
      .footer-cell {{ padding:17px 20px !important; }}
      .detail-label, .detail-value {{ display:block !important;width:auto !important; }}
      .detail-label {{ padding:12px 14px 2px !important;border-bottom:0 !important; }}
      .detail-value {{ padding:0 14px 12px !important; }}
    }}
  </style>
</head>
<body style="margin:0;padding:0;background:{_CANVAS};font-family:'Segoe UI',Roboto,Arial,sans-serif;-webkit-font-smoothing:antialiased">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent">{escape(title)} from Kent Business College Support.</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="{_CANVAS}" style="background:{_CANVAS}">
    <tr><td class="email-shell" align="center" style="padding:36px 12px">
      <table class="email-card" role="presentation" width="620" cellpadding="0" cellspacing="0"
             style="max-width:620px;width:100%;background:#ffffff;border:1px solid {_BORDER};border-radius:20px;overflow:hidden;box-shadow:0 14px 40px rgba(15,23,42,.08)">
        <tr>
          <td class="brand-cell" style="padding:20px 28px;background:#ffffff;border-bottom:1px solid {_BORDER}">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
              <td width="46" style="vertical-align:middle">
                <div style="width:42px;height:42px;line-height:42px;text-align:center;border-radius:12px;background:{_BRAND};color:#ffffff;font-size:13px;font-weight:800;letter-spacing:.5px">KBC</div>
              </td>
              <td style="padding-left:11px;vertical-align:middle">
                <div style="color:{_INK};font-size:15px;line-height:20px;font-weight:800">Kent Business College</div>
                <div style="color:{_MUTED};font-size:12px;line-height:18px">Student Support Centre</div>
              </td>
              <td align="right" style="vertical-align:middle">
                <span style="display:inline-block;padding:6px 10px;border-radius:999px;background:#f8fafc;border:1px solid {_BORDER};color:{_MUTED};font-size:10px;line-height:12px;font-weight:800;letter-spacing:.7px;text-transform:uppercase">Support</span>
              </td>
            </tr></table>
          </td>
        </tr>
        <tr>
          <td class="hero-cell" style="padding:31px 30px 27px;background:{accent_soft};border-bottom:1px solid {accent_border}">
            <span style="display:inline-block;padding:6px 10px;border-radius:999px;background:#ffffff;border:1px solid {accent_border};color:{accent};font-size:11px;line-height:14px;font-weight:800;letter-spacing:.5px;text-transform:uppercase">{escape(badge_label)}</span>
            <div style="margin-top:14px;color:{_INK};font-size:26px;line-height:33px;font-weight:800;letter-spacing:-.4px">{escape(title)}</div>
          </td>
        </tr>
        <tr>
          <td class="content-cell" style="padding:28px 30px 32px">
            <div style="color:#334155;font-size:15px;line-height:24px;margin-bottom:24px">{intro_html}</div>
            <div style="margin-bottom:9px;color:{_MUTED};font-size:11px;line-height:15px;font-weight:800;letter-spacing:.9px;text-transform:uppercase">Ticket details</div>
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                   style="background:#ffffff;border:1px solid {_BORDER};border-radius:12px;overflow:hidden">{detail}</table>
            {cta_html}
            {note_block}
          </td>
        </tr>
        <tr>
          <td class="footer-cell" style="padding:18px 30px;background:{_INK}">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
              <td style="color:#cbd5e1;font-size:11px;line-height:17px">&copy; Kent Business College<br><span style="color:#94a3b8">Student Support Team</span></td>
              <td align="right" style="color:#94a3b8;font-size:10px;line-height:16px">Automated notification<br>Please do not reply</td>
            </tr></table>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _row_text(label: str, value: str) -> tuple[str, str]:
    return label, escape((value or "").strip())


def _common_rows(ticket: dict[str, Any], payload: dict[str, Any], *, include_status: bool = True) -> list[tuple[str, str]]:
    cat = ticket.get("category") or ""
    sub = ticket.get("technicalSubcategory") or ""
    category_label = f"{cat} / {sub}".strip(" /") if (cat or sub) else ""
    rows = [
        _row_text("Subject", ticket.get("subject") or "-"),
        _row_text("Category", category_label),
    ]
    if include_status:
        rows.append(_row_text("Status", ticket.get("status") or ""))
    return rows


def _render_closed(payload: dict[str, Any]) -> tuple[str, str]:
    t = payload.get("ticket") or {}
    name = (payload.get("requester") or {}).get("name") or "there"
    subject = f"Your support ticket {t.get('id')} has been closed"
    intro = (
        f"Hi {escape(name.strip() or 'there')},<br><br>"
        "Your support ticket has been <b>resolved and closed</b> by our team. "
        "We hope everything is now sorted out for you."
    )
    rows = _common_rows(t, payload)
    note = (
        "If your issue is still not resolved, please open a new ticket from the "
        "Support Portal and our team will be happy to help you again."
    )
    return subject, _base_email(title="Ticket closed", intro_html=intro, rows=rows,
                                cta=("Open a new ticket", _portal_base() + "/support" if _portal_base() else ""),
                                note_html=note)


def _render_submitted_for_learner(payload: dict[str, Any]) -> tuple[str, str]:
    ticket = payload.get("ticket") or {}
    learner = payload.get("submittedFor") or {}
    requester = payload.get("requester") or {}
    name = escape((learner.get("fullName") or "there").strip())
    submitted_by = escape((requester.get("name") or "a member of staff").strip())
    closed = payload.get("event") == "submitted_for_learner_closed"
    state = "has been resolved and closed" if closed else "has been received"
    subject = f"Support ticket {ticket.get('id')} {state}"
    intro = f"Hi {name},<br><br>A support ticket submitted for you by {submitted_by} {state}."
    rows = _common_rows(ticket, payload)
    note = "If you have questions about this ticket, please contact the person who submitted it or the support team."
    return subject, _base_email(title="Ticket closed" if closed else "Ticket received", intro_html=intro, rows=rows, cta=None, note_html=note)


def _render_submitted(payload: dict[str, Any]) -> tuple[str, str]:
    t = payload.get("ticket") or {}
    name = (payload.get("requester") or {}).get("name") or "there"
    subject = f"We've received your support ticket {t.get('id')}"
    intro = (
        f"Hi {escape(name.strip() or 'there')},<br><br>"
        "Thanks for reaching out. We've <b>received your support ticket</b> and our "
        "team will get back to you as soon as possible."
    )
    rows = _common_rows(t, payload)
    note = "You can track the progress of your ticket any time from the Support Portal."
    return subject, _base_email(title="Ticket received", intro_html=intro, rows=rows,
                                cta=("Track my tickets", _ticket_url(payload)),
                                note_html=note)


def _render_ticket_created(payload: dict[str, Any]) -> tuple[str, str]:
    t = payload.get("ticket") or {}
    r = payload.get("requester") or {}
    subject = f"New support ticket {t.get('id')} — {t.get('assignedTeam') or 'Support'}"
    intro = (
        f"A new support ticket has been opened and routed to "
        f"<b>{escape(t.get('assignedTeam') or 'Support')}</b>."
    )
    requester = " ".join(x for x in [r.get("name"), f"({r.get('email')})" if r.get("email") else ""] if x)
    rows = _common_rows(t, payload, include_status=True)
    rows.insert(1, _row_text("Requester", requester or "-"))
    if t.get("priority"):
        rows.append(_row_text("Priority", t.get("priority")))
    note = "Open the ticket in the Admin Dashboard to review and action it."
    return subject, _base_email(title="New support ticket", intro_html=intro, rows=rows,
                                cta=("Open in dashboard", _ticket_url(payload)), note_html=note)


def _render_ai_team(payload: dict[str, Any]) -> tuple[str, str]:
    t = payload.get("ticket") or {}
    person = payload.get("aiTeamPerson") or {}
    r = payload.get("requester") or {}
    name = person.get("personName") or "there"
    subject = f"You've been asked to help with ticket {t.get('id')}"
    intro = (
        f"Hi {escape(str(name).strip() or 'there')},<br><br>"
        "A support ticket has been routed to you by the AI Team workflow. Please "
        "take a look when you can."
    )
    rows = _common_rows(t, payload, include_status=False)
    requester = " ".join(x for x in [r.get("name"), f"({r.get('email')})" if r.get("email") else ""] if x)
    rows.insert(1, _row_text("Requester", requester or "-"))
    if t.get("inquiry"):
        rows.append(_row_text("Details", t.get("inquiry")))
    note = "Open the ticket in the Admin Dashboard for the full conversation."
    return subject, _base_email(title="AI Team request", intro_html=intro, rows=rows,
                                cta=("Open in dashboard", _ticket_url(payload)), note_html=note)


def _render_live_agent(payload: dict[str, Any]) -> tuple[str, str]:
    t = payload.get("ticket") or {}
    r = payload.get("requester") or {}
    subject = f"Live chat needs attention — ticket {t.get('id')}"
    intro = (
        "A learner requested a live chat but no agent was available to pick it up. "
        "Please follow up as soon as possible."
    )
    rows = _common_rows(t, payload, include_status=True)
    requester = " ".join(x for x in [r.get("name"), f"({r.get('email')})" if r.get("email") else ""] if x)
    rows.insert(1, _row_text("Requester", requester or "-"))
    note = "Open the ticket in the Admin Dashboard to assist the learner."
    return subject, _base_email(title="Live agent unavailable", intro_html=intro, rows=rows,
                                cta=("Open in dashboard", _ticket_url(payload)), note_html=note)


def _render_generic(payload: dict[str, Any]) -> tuple[str, str]:
    t = payload.get("ticket") or {}
    subject = f"Support ticket update — {t.get('id')}"
    intro = "There is an update on a support ticket."
    rows = _common_rows(t, payload)
    return subject, _base_email(title="Support ticket update", intro_html=intro, rows=rows,
                                cta=("Open ticket", _ticket_url(payload)), note_html="")


_RENDERERS = {
    "submitted_for_learner_created": _render_submitted_for_learner,
    "submitted_for_learner_closed": _render_submitted_for_learner,
    "ticket_created": _render_ticket_created,
    "quick_ticket_submitted": _render_submitted,
    "quick_ticket_closed": _render_closed,
    "ai_team_ticket_submitted": _render_ai_team,
    "live_agent_unavailable": _render_live_agent,
}


def render_notification_email(payload: dict[str, Any]) -> tuple[str, str]:
    renderer = _RENDERERS.get(payload.get("event"), _render_generic)
    return renderer(payload)


def send_notification_via_graph(payload: dict[str, Any], attachments: list[Any] | None = None) -> dict[str, Any]:
    """Render ``payload`` into a Kent e-mail and send it via Graph.

    (Attachments are not yet forwarded through Graph; the e-mail links back to the
    ticket instead. Evidence files stay available in the portal.)
    """
    recipients = [a for a in (payload.get("recipients") or []) if a]
    if not recipients:
        return {"configured": True, "delivered": False, "status": None, "response": "no_recipients"}
    subject, html = render_notification_email(payload)
    return send_graph_mail(to=recipients, subject=subject, html=html)
