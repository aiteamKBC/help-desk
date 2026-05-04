from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from .contracts import LEGACY_ENDPOINTS
from .services import (
    ApiError,
    create_support_session_request,
    create_ticket,
    get_admin_login_response,
    get_admin_ticket_detail_response,
    get_verify_email_response,
    list_admin_tickets,
    list_agents,
    save_chat_history,
    send_chatbot_message,
    serve_frontend_asset,
    update_admin_ticket,
    update_ticket,
)


def parse_json_body(request) -> dict:
    if not request.body:
        return {}

    try:
        return json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError as error:
        raise ApiError(400, "Invalid JSON request body.") from error


def handle_api_error(error: Exception) -> JsonResponse:
    if isinstance(error, ApiError):
        extra_payload = {"exists": False} if error.message in {
            "Please enter a valid email address.",
            "This email is not registered in our records.",
        } else {}
        return JsonResponse({"message": error.message, **extra_payload}, status=error.status_code)

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


@require_http_methods(["GET"])
def admin_agents(request):
    try:
        return JsonResponse(list_agents())
    except Exception as error:
        return handle_api_error(error)


@require_http_methods(["GET"])
def admin_tickets(request):
    try:
        return JsonResponse(list_admin_tickets())
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
@require_http_methods(["POST"])
def ticket_chat_history(request, public_id: str):
    try:
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
def ticket_session_request(request, public_id: str):
    try:
        return JsonResponse(create_support_session_request(public_id, parse_json_body(request)), status=201)
    except Exception as error:
        return handle_api_error(error)


@require_http_methods(["GET", "HEAD"])
def frontend_entry(request, path: str = ""):
    asset_path = serve_frontend_asset(path or request.path)
    if not asset_path.exists():
        raise Http404("Frontend build output not found.")

    return FileResponse(asset_path.open("rb"))
