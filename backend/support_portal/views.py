from __future__ import annotations

import json
import logging
from pathlib import Path
from urllib import parse as urllib_parse
from uuid import uuid4

from psycopg import OperationalError as PsycopgOperationalError
from django.conf import settings
from django.db.utils import OperationalError as DjangoOperationalError
from django.http import FileResponse, Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.utils.html import escape
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from .contracts import LEGACY_ENDPOINTS
from .roles import ADMIN_ACCESS_ROLES, SUPPORT_PORTAL_ACCESS_ROLES
from .services import (
    acknowledge_ticket_escalation_closure,
    acknowledge_ticket_escalation_notification,
    acknowledge_ticket_teams_call_notification,
    acknowledge_ticket_transfer_decision,
    acknowledge_coverage_ticket_notification,
    acknowledge_coverage_tutor_response,
    accept_ticket_transfer_request,
    ApiError,
    confirm_coverage_tutor_session,
    reject_ticket_transfer_request,
    process_coverage_tutor_response,
    request_support_teams_call,
    request_ticket_transfer,
    cancel_support_session_request,
    close_agent_session,
    create_follow_up_ticket,
    create_support_session_request,
    create_ticket,
    delete_admin_ticket_permanently,
    get_admin_login_response,
    get_admin_microsoft_login_response,
    get_admin_ticket_attachment_file,
    get_ticket_chat_attachment_file,
    list_admin_notifications,
    get_admin_ticket_detail_response,
    get_coverage_options_response,
    get_open_assigned_live_chat_agent_ids,
    heartbeat_agent_session,
    build_microsoft_admin_authorize_url,
    get_support_booking_url,
    get_support_session_availability_response,
    get_support_teams_call_context_response,
    get_ticket_booking_context_response,
    get_ticket_chat_history_response,
    get_ticket_chat_context_response,
    get_verify_email_response,
    add_entra_agent,
    list_admin_tickets,
    list_agents,
    remove_agent,
    require_agent_session_actor,
    search_entra_agents,
    request_live_chat,
    save_chat_history,
    sanitize_text,
    send_admin_ai_agent_message,
    send_chatbot_message,
    serialize_agent,
    serve_frontend_asset,
    set_ticket_booking_progress,
    send_coverage_tutor_follow_up_files,
    submit_coverage_tutor_request,
    update_admin_ticket,
    update_admin_ticket_archive_state,
    update_agent_support_access,
    update_ticket,
)

logger = logging.getLogger(__name__)
DATABASE_UNAVAILABLE_MESSAGE = "The support data service is unavailable right now. Please try again in a moment."
ADMIN_SESSION_KEY = "support_admin_session"
ADMIN_MICROSOFT_AUTH_SESSION_KEY = "support_admin_microsoft_auth"
ADMIN_MICROSOFT_ERROR_QUERY_PARAM = "microsoftError"


def log_unexpected_api_error(message: str, error: Exception) -> None:
    logger.error(message, exc_info=(type(error), error, error.__traceback__))


def parse_json_body(request) -> dict:
    if not request.body:
        return {}

    try:
        return json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError as error:
        raise ApiError(400, "Invalid JSON request body.") from error


def parse_query_params(request) -> dict:
    return {key: value for key, value in request.GET.items()}


def build_coverage_tutor_response_page(title: str, message: str, *, accent: str = "#6d28d9") -> HttpResponse:
    safe_title = escape(title)
    safe_message = escape(message)
    html = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{safe_title}</title>
    <link rel="icon" type="image/svg+xml" href="/kent-crest.svg" />
    <link rel="shortcut icon" href="/favicon.ico" />
    <link rel="apple-touch-icon" href="/kent-crest.svg" />
    <style>
      :root {{
        color-scheme: light;
        --accent: {accent};
        --accent-soft: rgba(109, 40, 217, 0.08);
        --accent-border: rgba(109, 40, 217, 0.18);
        --surface: #ffffff;
        --text: #1f1648;
        --muted: #6b7280;
        --bg: linear-gradient(180deg, #f7f5ff 0%, #ffffff 100%);
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        padding: 24px;
        background: var(--bg);
        color: var(--text);
        font-family: "Segoe UI", Arial, sans-serif;
      }}
      .card {{
        width: min(100%, 560px);
        border-radius: 28px;
        border: 1px solid var(--accent-border);
        background: var(--surface);
        box-shadow: 0 24px 60px rgba(82, 54, 188, 0.14);
        padding: 32px 28px;
      }}
      .badge {{
        display: inline-flex;
        align-items: center;
        gap: 8px;
        border-radius: 999px;
        border: 1px solid var(--accent-border);
        background: var(--accent-soft);
        color: var(--accent);
        padding: 8px 14px;
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.16em;
        text-transform: uppercase;
      }}
      h1 {{
        margin: 18px 0 10px;
        font-size: 30px;
        line-height: 1.15;
      }}
      p {{
        margin: 0;
        font-size: 16px;
        line-height: 1.7;
        color: var(--muted);
      }}
    </style>
  </head>
  <body>
    <main class="card">
      <div class="badge">Kent Support Portal</div>
      <h1>{safe_title}</h1>
      <p>{safe_message}</p>
    </main>
  </body>
</html>
"""
    return HttpResponse(html)


def build_coverage_tutor_response_result_page_from_payload(payload: dict[str, str]) -> HttpResponse:
    status = sanitize_text(payload.get("status")).lower()
    outcome = sanitize_text(payload.get("outcome") or payload.get("action")).lower()
    message = sanitize_text(payload.get("message"))

    if status == "error":
        return build_coverage_tutor_response_page(
            "Response Could Not Be Recorded",
            message or "We could not process this tutor response right now.",
            accent="#dc2626",
        )

    if outcome in {"accept", "accepted", "approved", "confirmed"}:
        return build_coverage_tutor_response_page(
            "Response Recorded",
            "Thank you. The coverage request was accepted and the support team has been updated.",
            accent="#16a34a",
        )

    if outcome in {"refuse", "refused", "reject", "rejected", "declined"}:
        return build_coverage_tutor_response_page(
            "Response Recorded",
            "Thank you. The coverage request was declined and the support team has been updated.",
            accent="#dc2626",
        )

    return build_coverage_tutor_response_page(
        "Tutor Response",
        "This page is ready to show the final tutor response result after the workflow completes.",
        accent="#6d28d9",
    )


def normalize_frontend_origin(value: object) -> str:
    normalized_value = sanitize_text(value).rstrip("/")
    if not normalized_value:
        return ""

    parsed = urllib_parse.urlparse(normalized_value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path not in {"", "/"}:
        return ""

    return f"{parsed.scheme}://{parsed.netloc}"


def normalize_login_redirect_uri(value: object) -> str:
    normalized_value = sanitize_text(value)
    if not normalized_value:
        return ""

    parsed = urllib_parse.urlparse(normalized_value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.path:
        return ""

    return urllib_parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def is_allowed_frontend_origin(origin: str) -> bool:
    normalized_origin = normalize_frontend_origin(origin)
    if not normalized_origin:
        return False

    allowed_origins = {
        normalize_frontend_origin(value)
        for value in getattr(settings, "CSRF_TRUSTED_ORIGINS", [])
    }
    return normalized_origin in allowed_origins


def build_admin_login_error_redirect(message: str) -> str:
    query_string = urllib_parse.urlencode({ADMIN_MICROSOFT_ERROR_QUERY_PARAM: message})
    return f"/admin/login?{query_string}"


def parse_public_ticket_submission_request(request) -> tuple[dict, list]:
    content_type = (request.content_type or "").strip().lower()
    if content_type.startswith("multipart/form-data") or content_type.startswith("application/x-www-form-urlencoded"):
        return ({key: value for key, value in request.POST.items()}, list(request.FILES.getlist("evidenceFiles")))

    return parse_json_body(request), []


def parse_chat_submission_request(request, *, file_field_name: str = "attachmentFiles") -> tuple[dict, list]:
    content_type = (request.content_type or "").strip().lower()
    if content_type.startswith("multipart/form-data") or content_type.startswith("application/x-www-form-urlencoded"):
        payload: dict[str, object] = {}
        for key, value in request.POST.items():
            if key == "messages":
                try:
                    payload[key] = json.loads(value) if value else []
                except json.JSONDecodeError as error:
                    raise ApiError(400, "Invalid chat message payload.") from error
                continue
            payload[key] = value

        return payload, list(request.FILES.getlist(file_field_name))

    return parse_json_body(request), []


def normalize_request_session_instance_id(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def store_request_admin_session(request, admin_payload: dict, instance_id: str) -> None:
    request.session.cycle_key()
    request.session[ADMIN_SESSION_KEY] = {
        "id": int(admin_payload["id"]),
        "username": admin_payload["username"],
        "fullName": admin_payload.get("fullName") or admin_payload["username"],
        "email": admin_payload.get("email"),
        "role": admin_payload["role"],
        "instanceId": instance_id,
    }
    request.session.set_expiry(settings.SUPPORT_ADMIN_SESSION_COOKIE_AGE)


def clear_request_admin_session(request) -> None:
    request.session.flush()


def require_request_admin_session(request, *, allowed_roles: set[str] | None = SUPPORT_PORTAL_ACCESS_ROLES) -> tuple[dict, dict]:
    session_payload = request.session.get(ADMIN_SESSION_KEY)
    if not isinstance(session_payload, dict):
        raise ApiError(401, "Admin session is required.")

    instance_id = normalize_request_session_instance_id(session_payload.get("instanceId"))
    username = session_payload.get("username")

    try:
        actor = require_agent_session_actor(username, instance_id, allowed_roles=allowed_roles)
    except ApiError as error:
        if error.status_code in {401, 403}:
            clear_request_admin_session(request)
        raise

    request.session[ADMIN_SESSION_KEY] = {
        **session_payload,
        "id": int(actor["id"]),
        "username": actor["username"],
        "fullName": actor.get("full_name") or actor["username"],
        "email": actor.get("email"),
        "role": actor["role"],
        "instanceId": instance_id,
    }
    request.session.set_expiry(settings.SUPPORT_ADMIN_SESSION_COOKIE_AGE)
    return actor, request.session[ADMIN_SESSION_KEY]


def build_session_bound_admin_payload(
    request,
    *,
    allowed_roles: set[str] | None = SUPPORT_PORTAL_ACCESS_ROLES,
    payload: dict | None = None,
) -> dict:
    actor, session_payload = require_request_admin_session(request, allowed_roles=allowed_roles)
    session_bound_payload = dict(payload or parse_json_body(request))
    session_bound_payload["actorUsername"] = actor["username"]
    session_bound_payload["instanceId"] = session_payload["instanceId"]
    return session_bound_payload


def build_admin_session_response(actor: dict, session_payload: dict) -> dict:
    serialized_actor = serialize_agent(
        actor,
        open_assigned_chat_agent_ids=get_open_assigned_live_chat_agent_ids(),
    )
    return {
        "id": int(serialized_actor["id"]),
        "username": serialized_actor["username"],
        "fullName": serialized_actor["fullName"],
        "email": serialized_actor.get("email") or None,
        "role": serialized_actor["role"],
        "instanceId": session_payload["instanceId"],
        "sessionActive": serialized_actor.get("sessionActive"),
        "consoleStatus": serialized_actor.get("consoleStatus"),
        "selectedConsoleStatus": serialized_actor.get("selectedConsoleStatus"),
        "legacySupportAccess": bool(serialized_actor.get("legacySupportAccess")),
        "legacyOperationsAccess": bool(serialized_actor.get("legacyOperationsAccess")),
        "legacyAdminAccess": bool(serialized_actor.get("legacyAdminAccess")),
        "entraDirectoryAdmin": bool(serialized_actor.get("entraDirectoryAdmin")),
    }


def handle_api_error(error: Exception) -> JsonResponse:
    if isinstance(error, ApiError):
        extra_payload = {"exists": False} if error.message in {
            "Please enter a valid email address.",
            "This email is not registered in our records.",
        } else {}
        return JsonResponse({"message": error.message, **extra_payload}, status=error.status_code)

    if isinstance(error, (DjangoOperationalError, PsycopgOperationalError)):
        log_unexpected_api_error("Database connectivity error while handling support portal API request.", error)
        return JsonResponse({"message": DATABASE_UNAVAILABLE_MESSAGE}, status=503)

    log_unexpected_api_error("Unexpected support portal API error.", error)
    return JsonResponse({"message": "We could not process this request right now."}, status=500)


@require_GET
def health(_request):
    database_name = settings.DATABASES.get("default", {}).get("NAME", "")
    return JsonResponse({"ok": True, "databaseConfigured": bool(database_name)})


@require_GET
def migration_status(_request):
    return JsonResponse(
        {
            "framework": "django",
            "legacyExpressEntryPoint": str(settings.LEGACY_EXPRESS_ENTRYPOINT),
            "legacyExpressPresent": settings.LEGACY_EXPRESS_ENTRYPOINT.exists(),
            "bookingWebhookConfigured": bool(settings.BOOKING_WEBHOOK_URL),
            "adminAiWebhookConfigured": bool(settings.ADMIN_AI_WEBHOOK_URL or settings.CHATBOT_WEBHOOK_URL),
            "chatbotWebhookConfigured": bool(settings.CHATBOT_WEBHOOK_URL),
            "supportPortalPasswordConfigured": bool(settings.SUPPORT_PORTAL_PASSWORD),
            "nextRoutesToPort": LEGACY_ENDPOINTS,
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def verify_email(request):
    try:
        return JsonResponse(get_verify_email_response(parse_json_body(request)))
    except Exception as error:
        return handle_api_error(error)


@require_http_methods(["POST"])
def admin_login(request):
    try:
        payload = parse_json_body(request)
        instance_id = normalize_request_session_instance_id(payload.get("instanceId")) or uuid4().hex
        payload["instanceId"] = instance_id
        response_payload = get_admin_login_response(payload)
        admin_payload = response_payload.get("admin")
        if not isinstance(admin_payload, dict):
            raise ApiError(500, "We could not start the admin session right now.")

        store_request_admin_session(request, admin_payload, instance_id)
        response_payload["admin"] = {
            **admin_payload,
            "instanceId": instance_id,
        }
        return JsonResponse(response_payload)
    except Exception as error:
        return handle_api_error(error)


@require_GET
def admin_microsoft_login(request):
    origin = normalize_frontend_origin(request.GET.get("origin"))
    configured_redirect_uri = normalize_login_redirect_uri(settings.AZURE_LOGIN_REDIRECT_URI)

    try:
        if settings.AZURE_LOGIN_REDIRECT_URI and not configured_redirect_uri:
            raise ApiError(500, "The configured Microsoft sign-in redirect URI is invalid.")

        if not configured_redirect_uri and not is_allowed_frontend_origin(origin):
            raise ApiError(400, "Microsoft sign-in must start from an allowed portal origin.")

        state = uuid4().hex
        nonce = uuid4().hex
        redirect_uri = configured_redirect_uri or f"{origin}/api/admin/microsoft/callback"

        request.session[ADMIN_MICROSOFT_AUTH_SESSION_KEY] = {
            "state": state,
            "nonce": nonce,
            "redirectUri": redirect_uri,
        }
        request.session.set_expiry(settings.SUPPORT_ADMIN_SESSION_COOKIE_AGE)

        return HttpResponseRedirect(
            build_microsoft_admin_authorize_url(
                redirect_uri=redirect_uri,
                state=state,
                nonce=nonce,
            )
        )
    except Exception as error:
        if origin:
            if isinstance(error, ApiError):
                return HttpResponseRedirect(build_admin_login_error_redirect(error.message))
            log_unexpected_api_error("Unexpected Microsoft admin sign-in start error.", error)
            return HttpResponseRedirect(build_admin_login_error_redirect("We could not start Microsoft sign-in right now."))

        return handle_api_error(error)


@require_GET
def admin_microsoft_callback(request):
    auth_session = request.session.get(ADMIN_MICROSOFT_AUTH_SESSION_KEY)
    if not isinstance(auth_session, dict):
        return HttpResponseRedirect(build_admin_login_error_redirect("The Microsoft sign-in session expired. Please try again."))

    request.session.pop(ADMIN_MICROSOFT_AUTH_SESSION_KEY, None)

    try:
        returned_state = sanitize_text(request.GET.get("state"))
        expected_state = sanitize_text(auth_session.get("state"))
        if not returned_state or not expected_state or returned_state != expected_state:
            raise ApiError(401, "Microsoft sign-in validation failed. Please try again.")

        oauth_error = sanitize_text(request.GET.get("error"))
        if oauth_error:
            oauth_error_description = sanitize_text(request.GET.get("error_description"))
            raise ApiError(401, oauth_error_description or oauth_error.replace("_", " ").capitalize())

        code = sanitize_text(request.GET.get("code"))
        if not code:
            raise ApiError(400, "Microsoft sign-in did not return an authorization code.")

        instance_id = uuid4().hex
        response_payload = get_admin_microsoft_login_response(
            {
                "code": code,
                "redirectUri": auth_session.get("redirectUri"),
                "expectedNonce": auth_session.get("nonce"),
                "instanceId": instance_id,
                "consoleStatus": "Off",
            }
        )
        admin_payload = response_payload.get("admin")
        if not isinstance(admin_payload, dict):
            raise ApiError(500, "We could not start the admin session right now.")

        store_request_admin_session(request, admin_payload, instance_id)
        return HttpResponseRedirect("/admin")
    except Exception as error:
        if isinstance(error, ApiError):
            return HttpResponseRedirect(build_admin_login_error_redirect(error.message))

        log_unexpected_api_error("Unexpected Microsoft admin sign-in callback error.", error)
        return HttpResponseRedirect(build_admin_login_error_redirect("We could not complete Microsoft sign-in right now."))


@ensure_csrf_cookie
@require_http_methods(["GET"])
def admin_session(request):
    try:
        actor, session_payload = require_request_admin_session(request)
        return JsonResponse({"admin": build_admin_session_response(actor, session_payload)})
    except Exception as error:
        return handle_api_error(error)


@require_http_methods(["POST"])
def admin_session_heartbeat(request):
    try:
        try:
            actor, session_payload = require_request_admin_session(request)
        except ApiError as error:
            if error.status_code == 401:
                return JsonResponse({"ok": True, "sessionActive": False, "sessionReplaced": False})
            raise

        payload = parse_json_body(request)
        response_payload = heartbeat_agent_session(
            {
                "actorUsername": request.session[ADMIN_SESSION_KEY]["username"],
                "instanceId": session_payload["instanceId"],
                "consoleStatus": payload.get("consoleStatus"),
            }
        )
        if response_payload.get("sessionActive") is False:
            clear_request_admin_session(request)
            return JsonResponse(response_payload)

        refreshed_actor, refreshed_session_payload = require_request_admin_session(request)
        return JsonResponse(
            {
                **response_payload,
                "admin": build_admin_session_response(refreshed_actor, refreshed_session_payload),
            }
        )
    except Exception as error:
        return handle_api_error(error)


@require_http_methods(["POST"])
def admin_logout(request):
    try:
        session_payload = request.session.get(ADMIN_SESSION_KEY)
        if not isinstance(session_payload, dict):
            return JsonResponse({"ok": True, "sessionClosed": False, "sessionReplaced": False})

        response_payload = close_agent_session(
            {
                "actorUsername": session_payload.get("username"),
                "instanceId": session_payload.get("instanceId"),
            }
        )
        clear_request_admin_session(request)
        return JsonResponse(response_payload)
    except Exception as error:
        return handle_api_error(error)


@require_http_methods(["GET", "POST"])
def admin_accounts(request):
    try:
        if request.method == "POST":
            require_request_admin_session(request, allowed_roles=ADMIN_ACCESS_ROLES)
            agent = add_entra_agent(parse_json_body(request))
            return JsonResponse(agent, status=201)
        require_request_admin_session(request)
        return JsonResponse(list_agents(include_inactive=True))
    except Exception as error:
        return handle_api_error(error)


@require_GET
def admin_agents_search(request):
    try:
        require_request_admin_session(request, allowed_roles=ADMIN_ACCESS_ROLES)
        q = sanitize_text(request.GET.get("q", ""))
        return JsonResponse(search_entra_agents(q))
    except Exception as error:
        return handle_api_error(error)


admin_agents = admin_accounts


@require_http_methods(["PATCH", "DELETE"])
def admin_account_detail(request, account_id: int):
    try:
        require_request_admin_session(request, allowed_roles=ADMIN_ACCESS_ROLES)
        if request.method == "DELETE":
            remove_agent(account_id)
            return JsonResponse({"ok": True})
        payload = parse_json_body(request)
        if "supportAccess" not in payload:
            raise ApiError(400, "supportAccess field is required.")
        support_access = bool(payload["supportAccess"])
        agent = update_agent_support_access(account_id, support_access=support_access)
        return JsonResponse({"agent": agent})
    except Exception as error:
        return handle_api_error(error)


@require_http_methods(["GET"])
def admin_tickets(request):
    try:
        require_request_admin_session(request)
        return JsonResponse(list_admin_tickets())
    except Exception as error:
        return handle_api_error(error)


@require_http_methods(["GET"])
def admin_notifications(request):
    try:
        _actor, session_payload = require_request_admin_session(request)
        payload = parse_query_params(request)
        return JsonResponse(
            list_admin_notifications(
                request.session[ADMIN_SESSION_KEY]["username"],
                session_payload["instanceId"],
                limit=payload.get("limit"),
            )
        )
    except Exception as error:
        return handle_api_error(error)


@require_http_methods(["GET", "PATCH"])
def admin_ticket_detail(request, public_id: str):
    try:
        require_request_admin_session(request)
        if request.method == "GET":
            return JsonResponse(get_admin_ticket_detail_response(public_id))

        return JsonResponse(update_admin_ticket(public_id, build_session_bound_admin_payload(request)))
    except Exception as error:
        return handle_api_error(error)


@require_http_methods(["POST"])
def admin_ticket_archive(request, public_id: str):
    try:
        require_request_admin_session(request)
        return JsonResponse(update_admin_ticket_archive_state(public_id, build_session_bound_admin_payload(request)))
    except Exception as error:
        return handle_api_error(error)


@require_http_methods(["POST"])
def admin_ticket_permanent_delete(request, public_id: str):
    try:
        require_request_admin_session(request)
        return JsonResponse(delete_admin_ticket_permanently(public_id, build_session_bound_admin_payload(request)))
    except Exception as error:
        return handle_api_error(error)


@require_http_methods(["GET"])
def admin_ticket_attachment_download(request, public_id: str, attachment_id: int):
    try:
        require_request_admin_session(request)
        attachment = get_admin_ticket_attachment_file(public_id, attachment_id)
        response = FileResponse(
            attachment["path"].open("rb"),
            as_attachment=False,
            filename=attachment["fileName"],
            content_type=attachment.get("mimeType") or "application/octet-stream",
        )
        response["X-Content-Type-Options"] = "nosniff"
        return response
    except Exception as error:
        return handle_api_error(error)


@require_http_methods(["GET"])
def admin_ticket_chat_attachment_download(request, public_id: str, client_attachment_id: str):
    try:
        require_request_admin_session(request)
        attachment = get_ticket_chat_attachment_file(public_id, client_attachment_id)
        response = FileResponse(
            attachment["path"].open("rb"),
            as_attachment=False,
            filename=attachment["fileName"],
            content_type=attachment.get("mimeType") or "application/octet-stream",
        )
        response["X-Content-Type-Options"] = "nosniff"
        return response
    except Exception as error:
        return handle_api_error(error)


@require_http_methods(["POST"])
def admin_ticket_chat_history(request, public_id: str):
    try:
        payload, uploaded_files = parse_chat_submission_request(request)
        return JsonResponse(
            save_chat_history(
                public_id,
                build_session_bound_admin_payload(request, payload=payload),
                uploaded_files=uploaded_files,
            )
        )
    except Exception as error:
        return handle_api_error(error)


@require_http_methods(["POST"])
def admin_ticket_ai_message(request, public_id: str):
    try:
        return JsonResponse(send_admin_ai_agent_message(public_id, build_session_bound_admin_payload(request)))
    except Exception as error:
        return handle_api_error(error)


@require_http_methods(["POST"])
def admin_ticket_follow_up(request, public_id: str):
    try:
        return JsonResponse(create_follow_up_ticket(public_id, build_session_bound_admin_payload(request)), status=201)
    except Exception as error:
        return handle_api_error(error)


@require_http_methods(["POST"])
def admin_ticket_transfer_request(request, public_id: str):
    try:
        return JsonResponse(request_ticket_transfer(public_id, build_session_bound_admin_payload(request)))
    except Exception as error:
        return handle_api_error(error)


@require_http_methods(["POST"])
def admin_ticket_transfer_request_accept(request, public_id: str):
    try:
        return JsonResponse(accept_ticket_transfer_request(public_id, build_session_bound_admin_payload(request)))
    except Exception as error:
        return handle_api_error(error)


@require_http_methods(["POST"])
def admin_ticket_transfer_request_reject(request, public_id: str):
    try:
        return JsonResponse(reject_ticket_transfer_request(public_id, build_session_bound_admin_payload(request)))
    except Exception as error:
        return handle_api_error(error)


@require_http_methods(["POST"])
def admin_ticket_transfer_decision_acknowledge(request, public_id: str):
    try:
        return JsonResponse(acknowledge_ticket_transfer_decision(public_id, build_session_bound_admin_payload(request)))
    except Exception as error:
        return handle_api_error(error)


@require_http_methods(["POST"])
def admin_ticket_teams_call_notification_acknowledge(request, public_id: str):
    try:
        return JsonResponse(acknowledge_ticket_teams_call_notification(public_id, build_session_bound_admin_payload(request)))
    except Exception as error:
        return handle_api_error(error)


@require_http_methods(["POST"])
def admin_ticket_escalation_notification_acknowledge(request, public_id: str):
    try:
        return JsonResponse(acknowledge_ticket_escalation_notification(public_id, build_session_bound_admin_payload(request)))
    except Exception as error:
        return handle_api_error(error)


@require_http_methods(["POST"])
def admin_ticket_escalation_closure_acknowledge(request, public_id: str):
    try:
        return JsonResponse(acknowledge_ticket_escalation_closure(public_id, build_session_bound_admin_payload(request)))
    except Exception as error:
        return handle_api_error(error)


@require_http_methods(["POST"])
def admin_ticket_coverage_tutor_request(request, public_id: str):
    try:
        return JsonResponse(submit_coverage_tutor_request(public_id, build_session_bound_admin_payload(request)))
    except Exception as error:
        return handle_api_error(error)


@require_http_methods(["POST"])
def admin_ticket_coverage_tutor_follow_up(request, public_id: str):
    try:
        return JsonResponse(send_coverage_tutor_follow_up_files(public_id, build_session_bound_admin_payload(request)))
    except Exception as error:
        return handle_api_error(error)


@require_http_methods(["POST"])
def admin_ticket_coverage_tutor_response_acknowledge(request, public_id: str):
    try:
        return JsonResponse(acknowledge_coverage_tutor_response(public_id, build_session_bound_admin_payload(request)))
    except Exception as error:
        return handle_api_error(error)


@require_http_methods(["POST"])
def admin_ticket_coverage_ticket_notification_acknowledge(request, public_id: str):
    try:
        return JsonResponse(acknowledge_coverage_ticket_notification(public_id, build_session_bound_admin_payload(request)))
    except Exception as error:
        return handle_api_error(error)


@require_http_methods(["POST"])
def admin_ticket_coverage_confirm_session(request, public_id: str):
    try:
        return JsonResponse(confirm_coverage_tutor_session(public_id, build_session_bound_admin_payload(request)))
    except Exception as error:
        return handle_api_error(error)


@csrf_exempt
@require_http_methods(["POST"])
def tickets_create(request):
    try:
        payload, uploaded_files = parse_public_ticket_submission_request(request)
        return JsonResponse(create_ticket(payload, uploaded_files=uploaded_files), status=201)
    except Exception as error:
        return handle_api_error(error)


@csrf_exempt
@require_http_methods(["PATCH", "POST"])
def tickets_update(request, public_id: str):
    try:
        payload, uploaded_files = parse_public_ticket_submission_request(request)
        return JsonResponse(update_ticket(public_id, payload, uploaded_files=uploaded_files))
    except Exception as error:
        return handle_api_error(error)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def ticket_chat_history(request, public_id: str):
    try:
        if request.method == "GET":
            return JsonResponse(get_ticket_chat_history_response(public_id))
        payload, uploaded_files = parse_chat_submission_request(request)
        return JsonResponse(save_chat_history(public_id, payload, uploaded_files=uploaded_files))
    except Exception as error:
        return handle_api_error(error)


@csrf_exempt
@require_http_methods(["POST"])
def ticket_chatbot_message(request, public_id: str):
    try:
        payload, uploaded_files = parse_chat_submission_request(request)
        return JsonResponse(send_chatbot_message(public_id, payload, uploaded_files=uploaded_files))
    except Exception as error:
        return handle_api_error(error)


@csrf_exempt
@require_http_methods(["GET"])
def ticket_chat_attachment_download(request, public_id: str, client_attachment_id: str):
    try:
        attachment = get_ticket_chat_attachment_file(public_id, client_attachment_id)
        response = FileResponse(
            attachment["path"].open("rb"),
            as_attachment=False,
            filename=attachment["fileName"],
            content_type=attachment.get("mimeType") or "application/octet-stream",
        )
        response["X-Content-Type-Options"] = "nosniff"
        return response
    except Exception as error:
        return handle_api_error(error)


@csrf_exempt
@require_http_methods(["POST"])
def ticket_live_chat_request(request, public_id: str):
    try:
        return JsonResponse(request_live_chat(public_id))
    except Exception as error:
        return handle_api_error(error)


@require_http_methods(["GET"])
def ticket_booking_context(request, public_id: str):
    try:
        return JsonResponse(get_ticket_booking_context_response(public_id))
    except Exception as error:
        return handle_api_error(error)


@csrf_exempt
@require_http_methods(["POST"])
def ticket_booking_progress(request, public_id: str):
    try:
        payload = parse_json_body(request)
        return JsonResponse(set_ticket_booking_progress(public_id, active=bool(payload.get("active"))))
    except Exception as error:
        return handle_api_error(error)


@require_http_methods(["GET"])
def ticket_session_availability(request, public_id: str):
    try:
        return JsonResponse(
            get_support_session_availability_response(
                public_id,
                request.GET.get("date", ""),
                request.GET.get("clientTimeZone", ""),
            )
        )
    except Exception as error:
        return handle_api_error(error)


@require_http_methods(["GET"])
def ticket_chat_context(request, public_id: str):
    try:
        return JsonResponse(get_ticket_chat_context_response(public_id))
    except Exception as error:
        return handle_api_error(error)


@csrf_exempt
@require_http_methods(["POST"])
def ticket_teams_call_request(request, public_id: str):
    try:
        return JsonResponse(request_support_teams_call(public_id))
    except Exception as error:
        return handle_api_error(error)


@require_http_methods(["GET"])
def booking_link(_request):
    try:
        return HttpResponseRedirect(get_support_booking_url())
    except Exception as error:
        return handle_api_error(error)


@require_http_methods(["GET"])
def teams_call_context(_request):
    try:
        return JsonResponse(get_support_teams_call_context_response())
    except Exception as error:
        return handle_api_error(error)


@require_http_methods(["GET"])
def coverage_options(request):
    try:
        return JsonResponse(get_coverage_options_response(parse_query_params(request)))
    except Exception as error:
        return handle_api_error(error)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def coverage_tutor_response(request):
    try:
        if request.method == "GET":
            payload = parse_query_params(request)
            if not payload.get("outcome") and payload.get("action"):
                payload["outcome"] = sanitize_text(payload.get("action"))
            detail = process_coverage_tutor_response(payload)
            if detail.get("coverageTutorResponseAlreadyRecorded"):
                recorded_outcome = sanitize_text(detail.get("recordedCoverageTutorResponseOutcome")).lower()
                if recorded_outcome == "accepted":
                    message = "Your original response was ACCEPTED. This link is now locked, so no new decision was recorded."
                    accent = "#16a34a"
                elif recorded_outcome == "rejected":
                    message = "Your original response was DECLINED. This link is now locked, so no new decision was recorded."
                    accent = "#dc2626"
                else:
                    message = "This request already has a recorded decision. To protect the ticket history, this new click was ignored."
                    accent = "#6d28d9"
                return build_coverage_tutor_response_page(
                    "Decision Locked",
                    message,
                    accent=accent,
                )
            outcome = sanitize_text(payload.get("outcome")).lower()
            was_accepted = outcome in {"accept", "accepted", "approved", "confirmed"}
            return build_coverage_tutor_response_page(
                "Response Recorded",
                "Thank you. The coverage request was accepted and the support team has been updated."
                if was_accepted
                else "Thank you. The coverage request was declined and the support team has been updated.",
                accent="#16a34a" if was_accepted else "#dc2626",
            )

        return JsonResponse(process_coverage_tutor_response(parse_json_body(request)))
    except Exception as error:
        if request.method == "GET":
            message = error.message if isinstance(error, ApiError) else "We could not process this tutor response right now."
            return build_coverage_tutor_response_page("Response Could Not Be Recorded", message, accent="#dc2626")
        return handle_api_error(error)


@require_GET
def coverage_tutor_response_result(request):
    return build_coverage_tutor_response_result_page_from_payload(parse_query_params(request))


@csrf_exempt
@require_http_methods(["POST"])
def ticket_session_request(request, public_id: str):
    try:
        return JsonResponse(create_support_session_request(public_id, parse_json_body(request)), status=201)
    except Exception as error:
        return handle_api_error(error)


@csrf_exempt
@require_http_methods(["POST"])
def ticket_session_request_cancel(request, public_id: str):
    try:
        return JsonResponse(cancel_support_session_request(public_id))
    except Exception as error:
        return handle_api_error(error)


@ensure_csrf_cookie
@require_http_methods(["GET", "HEAD"])
def frontend_entry(request, path: str = ""):
    asset_path = serve_frontend_asset(path or request.path)
    if not asset_path.exists():
        raise Http404("Frontend build output not found.")

    return FileResponse(asset_path.open("rb"))
