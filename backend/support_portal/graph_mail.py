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
_BRAND_DARK = "#4338ca"
_INK = "#0f172a"
_MUTED = "#64748b"
_BORDER = "#e2e8f0"
_SOFT = "#f8fafc"


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


def _ticket_link_html(public_id: str, url: str) -> str:
    pid = escape(public_id or "-")
    if not url:
        return f'<span style="color:{_INK};font-weight:700">{pid}</span>'
    return f'<a href="{escape(url)}" style="color:{_BRAND};font-weight:700;text-decoration:none">{pid}</a>'


def _button(text: str, url: str) -> str:
    if not url:
        return ""
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:22px 0 4px">'
        f'<tr><td style="border-radius:8px;background:{_BRAND}">'
        f'<a href="{escape(url)}" style="display:inline-block;padding:11px 22px;color:#ffffff;'
        f'font-size:14px;font-weight:600;text-decoration:none;border-radius:8px">{escape(text)}</a>'
        f'</td></tr></table>'
    )


def _base_email(*, title: str, intro_html: str, rows: list[tuple[str, str]], cta: tuple[str, str] | None, note_html: str) -> str:
    detail = "".join(
        f'<tr>'
        f'<td style="padding:7px 0;color:{_MUTED};font-size:13px;width:130px;vertical-align:top">{escape(label)}</td>'
        f'<td style="padding:7px 0;color:{_INK};font-size:14px;font-weight:600">{value_html}</td>'
        f'</tr>'
        for label, value_html in rows
        if value_html
    )
    cta_html = _button(*cta) if cta else ""
    return f"""\
<!doctype html>
<html><body style="margin:0;background:#eef2f7;padding:28px 12px;font-family:Segoe UI,Roboto,Arial,sans-serif">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">
    <table role="presentation" width="560" cellpadding="0" cellspacing="0"
           style="max-width:560px;width:100%;background:#ffffff;border:1px solid {_BORDER};border-radius:16px;overflow:hidden">
      <tr><td style="background:{_BRAND};background-image:linear-gradient(135deg,{_BRAND},{_BRAND_DARK});padding:22px 30px">
        <div style="color:#ffffff;font-size:19px;font-weight:700;letter-spacing:.2px">Kent Business College</div>
        <div style="color:#c7d2fe;font-size:12px;margin-top:3px;text-transform:uppercase;letter-spacing:1px">Student Support</div>
      </td></tr>
      <tr><td style="padding:30px">
        <div style="color:{_INK};font-size:19px;font-weight:700;margin-bottom:12px">{escape(title)}</div>
        <div style="color:{_INK};font-size:14px;line-height:1.65;margin-bottom:20px">{intro_html}</div>
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
               style="border-top:1px solid {_BORDER};border-bottom:1px solid {_BORDER};margin-bottom:4px">{detail}</table>
        {cta_html}
        <div style="color:{_MUTED};font-size:13px;line-height:1.65;margin-top:18px">{note_html}</div>
      </td></tr>
      <tr><td style="padding:16px 30px;background:{_SOFT};border-top:1px solid {_BORDER}">
        <div style="color:{_MUTED};font-size:12px">Kent Business College &middot; Student Support Team</div>
        <div style="color:#94a3b8;font-size:11px;margin-top:4px">This is an automated message &mdash; please do not reply to this address.</div>
      </td></tr>
    </table>
  </td></tr></table>
</body></html>"""


def _row_text(label: str, value: str) -> tuple[str, str]:
    return label, escape((value or "").strip())


def _common_rows(ticket: dict[str, Any], payload: dict[str, Any], *, include_status: bool = True) -> list[tuple[str, str]]:
    public_id = ticket.get("id") or "-"
    cat = ticket.get("category") or ""
    sub = ticket.get("technicalSubcategory") or ""
    category_label = f"{cat} / {sub}".strip(" /") if (cat or sub) else ""
    rows = [
        ("Ticket", _ticket_link_html(public_id, _ticket_url(payload))),
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
