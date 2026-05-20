from __future__ import annotations

import json

from django.http import FileResponse, HttpResponseNotAllowed, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from .services import archive_article_file, get_article_detail, get_public_asset, list_article_index, save_article_file


def _parse_json_body(request) -> dict:
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("Invalid JSON request body.") from error


@csrf_exempt
def articles_collection(request):
    if request.method == "GET":
        try:
            return JsonResponse({"ok": True, "articles": list_article_index()})
        except Exception as error:
            return JsonResponse({"ok": False, "error": str(error)}, status=500)

    if request.method == "POST":
        try:
            payload = _parse_json_body(request)
            result = save_article_file(
                payload.get("filename") or "",
                str(payload.get("html") or ""),
                payload.get("evidence") if isinstance(payload.get("evidence"), list) else [],
            )
            return JsonResponse({"ok": True, **result})
        except ValueError as error:
            return JsonResponse({"ok": False, "error": str(error)}, status=400)
        except Exception as error:
            return JsonResponse({"ok": False, "error": str(error)}, status=500)

    if request.method == "DELETE":
        try:
            payload = _parse_json_body(request)
            result = archive_article_file(str(payload.get("filename") or ""))
            return JsonResponse({"ok": True, **result})
        except ValueError as error:
            return JsonResponse({"ok": False, "error": str(error)}, status=400)
        except Exception as error:
            message = str(error)
            status_code = 404 if "not found" in message.lower() else 400
            return JsonResponse({"ok": False, "error": message}, status=status_code)

    return HttpResponseNotAllowed(["GET", "POST", "DELETE"])


@require_GET
def article_detail(_request, filename: str):
    try:
        return JsonResponse({"ok": True, "article": get_article_detail(filename)})
    except Exception as error:
        message = str(error)
        status_code = 404 if "not found" in message.lower() else 400
        return JsonResponse({"ok": False, "error": message}, status=status_code)


@require_GET
def article_asset(_request, asset_path: str):
    file_path, content_type = get_public_asset(asset_path)
    return FileResponse(file_path.open("rb"), content_type=content_type)
