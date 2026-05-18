from __future__ import annotations

import json
import logging
from pathlib import Path

from psycopg import OperationalError as PsycopgOperationalError
from django.conf import settings
from django.db.utils import OperationalError as DjangoOperationalError
from django.http import FileResponse, Http404, HttpResponseRedirect, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from .contracts import LEGACY_ENDPOINTS
from .services import (
    acknowledge_ticket_escalation_closure,
    acknowledge_ticket_escalation_notification,
    acknowledge_ticket_teams_call_notification,
    acknowledge_ticket_transfer_decision,
    accept_ticket_transfer_request,
    ApiError,
    reject_ticket_transfer_request,
    request_support_teams_call,
    request_ticket_transfer,
    cancel_support_session_request,
    close_agent_session,
    create_support_account,
    create_follow_up_ticket,
    create_support_session_request,
    create_ticket,
    get_admin_login_response,
    list_admin_notifications,
    get_admin_ticket_detail_response,
    heartbeat_agent_session,
    get_support_booking_url,
    get_support_teams_call_context_response,
    get_ticket_booking_context_response,
    get_ticket_chat_history_response,
    get_ticket_chat_context_response,
    get_verify_email_response,
    list_admin_tickets,
    list_agents,
    require_agent_session_actor,
    request_live_chat,
    save_chat_history,
    send_admin_ai_agent_message,
    send_chatbot_message,
    serve_frontend_asset,
    update_support_account,
    update_admin_ticket,
    update_ticket,
)

logger = logging.getLogger(__name__)
DATABASE_UNAVAILABLE_MESSAGE = "The support data service is unavailable right now. Please try again in a moment."


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


@csrf_exempt
@require_http_methods(["POST"])
def admin_login(request):
    try:
        return JsonResponse(get_admin_login_response(parse_json_body(request)))
    except Exception as error:
        return handle_api_error(error)


@csrf_exempt
@require_http_methods(["POST"])
def admin_session_heartbeat(request):
    try:
        return JsonResponse(heartbeat_agent_session(parse_json_body(request)))
    except Exception as error:
        return handle_api_error(error)


@csrf_exempt
@require_http_methods(["POST"])
def admin_logout(request):
    try:
        return JsonResponse(close_agent_session(parse_json_body(request)))
    except Exception as error:
        return handle_api_error(error)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def admin_accounts(request):
    try:
        if request.method == "GET":
            payload = parse_query_params(request)
            require_agent_session_actor(payload.get("actorUsername"), payload.get("instanceId"))
            return JsonResponse(list_agents(include_inactive=True))

        return JsonResponse(create_support_account(parse_json_body(request)), status=201)
    except Exception as error:
        return handle_api_error(error)


@csrf_exempt
@require_http_methods(["PATCH"])
def admin_account_detail(request, agent_id: int):
    try:
        return JsonResponse(update_support_account(agent_id, parse_json_body(request)))
    except Exception as error:
        return handle_api_error(error)


admin_agents = admin_accounts
admin_agent_detail = admin_account_detail


@require_http_methods(["GET"])
def admin_tickets(request):
    try:
        return JsonResponse(list_admin_tickets())
    except Exception as error:
        return handle_api_error(error)


@require_http_methods(["GET"])
def admin_notifications(request):
    try:
        payload = parse_query_params(request)
        return JsonResponse(
            list_admin_notifications(
                payload.get("actorUsername"),
                payload.get("instanceId"),
                limit=payload.get("limit"),
            )
        )
    except Exception as error:
        return handle_api_error(error)


@csrf_exempt
@require_http_methods(["GET", "PATCH"])
def admin_ticket_detail(request, public_id: str):
    try:
        if request.method == "GET":
            return JsonResponse(get_admin_ticket_detail_response(public_id))

        return JsonResponse(update_admin_ticket(public_id, parse_json_body(request)))
    except Exception as error:
        return handle_api_error(error)


@csrf_exempt
@require_http_methods(["POST"])
def admin_ticket_ai_message(request, public_id: str):
    try:
        return JsonResponse(send_admin_ai_agent_message(public_id, parse_json_body(request)))
    except Exception as error:
        return handle_api_error(error)


@csrf_exempt
@require_http_methods(["POST"])
def admin_ticket_follow_up(request, public_id: str):
    try:
        return JsonResponse(create_follow_up_ticket(public_id, parse_json_body(request)), status=201)
    except Exception as error:
        return handle_api_error(error)


@csrf_exempt
@require_http_methods(["POST"])
def admin_ticket_transfer_request(request, public_id: str):
    try:
        return JsonResponse(request_ticket_transfer(public_id, parse_json_body(request)))
    except Exception as error:
        return handle_api_error(error)


@csrf_exempt
@require_http_methods(["POST"])
def admin_ticket_transfer_request_accept(request, public_id: str):
    try:
        return JsonResponse(accept_ticket_transfer_request(public_id, parse_json_body(request)))
    except Exception as error:
        return handle_api_error(error)


@csrf_exempt
@require_http_methods(["POST"])
def admin_ticket_transfer_request_reject(request, public_id: str):
    try:
        return JsonResponse(reject_ticket_transfer_request(public_id, parse_json_body(request)))
    except Exception as error:
        return handle_api_error(error)


@csrf_exempt
@require_http_methods(["POST"])
def admin_ticket_transfer_decision_acknowledge(request, public_id: str):
    try:
        return JsonResponse(acknowledge_ticket_transfer_decision(public_id, parse_json_body(request)))
    except Exception as error:
        return handle_api_error(error)


@csrf_exempt
@require_http_methods(["POST"])
def admin_ticket_teams_call_notification_acknowledge(request, public_id: str):
    try:
        return JsonResponse(acknowledge_ticket_teams_call_notification(public_id, parse_json_body(request)))
    except Exception as error:
        return handle_api_error(error)


@csrf_exempt
@require_http_methods(["POST"])
def admin_ticket_escalation_notification_acknowledge(request, public_id: str):
    try:
        return JsonResponse(acknowledge_ticket_escalation_notification(public_id, parse_json_body(request)))
    except Exception as error:
        return handle_api_error(error)


@csrf_exempt
@require_http_methods(["POST"])
def admin_ticket_escalation_closure_acknowledge(request, public_id: str):
    try:
        return JsonResponse(acknowledge_ticket_escalation_closure(public_id, parse_json_body(request)))
    except Exception as error:
        return handle_api_error(error)


@csrf_exempt
@require_http_methods(["POST"])
def tickets_create(request):
    try:
        return JsonResponse(create_ticket(parse_json_body(request)), status=201)
    except Exception as error:
        return handle_api_error(error)


@csrf_exempt
@require_http_methods(["PATCH"])
def tickets_update(request, public_id: str):
    try:
        return JsonResponse(update_ticket(public_id, parse_json_body(request)))
    except Exception as error:
        return handle_api_error(error)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def ticket_chat_history(request, public_id: str):
    try:
        if request.method == "GET":
            return JsonResponse(get_ticket_chat_history_response(public_id))
        return JsonResponse(save_chat_history(public_id, parse_json_body(request)))
    except Exception as error:
        return handle_api_error(error)


@csrf_exempt
@require_http_methods(["POST"])
def ticket_chatbot_message(request, public_id: str):
    try:
        return JsonResponse(send_chatbot_message(public_id, parse_json_body(request)))
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


@require_http_methods(["GET", "HEAD"])
def frontend_entry(request, path: str = ""):
    asset_path = serve_frontend_asset(path or request.path)
    if not asset_path.exists():
        raise Http404("Frontend build output not found.")

    return FileResponse(asset_path.open("rb"))
