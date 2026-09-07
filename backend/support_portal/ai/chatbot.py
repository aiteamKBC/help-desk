from __future__ import annotations

import logging
import time
from typing import Any

from .classifier import classify
from .formatting import CONTROLLED_FAILURE_REPLY, response_payload
from .knowledge_base import format_context, search_knowledge_base
from .prompts import build_instructions
from .openai_service import generate_reply
from .session import get_last_route, get_session_key, save_last_route

logger = logging.getLogger(__name__)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def normalize_chat_payload(payload: dict[str, Any]) -> dict[str, Any]:
    ticket = payload.get("ticket") if isinstance(payload.get("ticket"), dict) else {}
    learner = payload.get("learner") if isinstance(payload.get("learner"), dict) else {}
    normalized = dict(payload)
    normalized["message"] = _clean(payload.get("message"))
    normalized["category"] = _clean(ticket.get("category") or payload.get("category"))
    normalized["technicalSubcategory"] = _clean(
        ticket.get("subcategory")
        or ticket.get("technicalSubcategory")
        or payload.get("subcategory")
        or payload.get("technicalSubcategory")
    )
    normalized["inquiry"] = _clean(ticket.get("summary") or ticket.get("inquiry") or payload.get("issueSummary") or payload.get("inquiry"))
    normalized["ticket"] = {
        **ticket,
        "category": _clean(ticket.get("category") or payload.get("category")),
        "technicalSubcategory": _clean(ticket.get("subcategory") or ticket.get("technicalSubcategory") or payload.get("subcategory") or payload.get("technicalSubcategory")),
        "inquiry": _clean(ticket.get("summary") or ticket.get("inquiry") or payload.get("issueSummary") or payload.get("inquiry")),
    }
    normalized["learner"] = {
        **learner,
        "fullName": _clean(learner.get("fullName")),
        "email": _clean(learner.get("email")).lower(),
    }
    normalized["messages"] = payload.get("messages") if isinstance(payload.get("messages"), list) else []
    return normalized


def _recent_context_messages(messages: list[Any]) -> list[dict[str, str]]:
    normalized = []
    for item in messages[-6:]:
        if not isinstance(item, dict):
            continue
        sender = _clean(item.get("sender")).lower()
        text = _clean(item.get("text"))
        if not text:
            continue
        role = "assistant" if sender in {"bot", "agent"} else "user"
        normalized.append({"role": role, "content": text})
    return normalized


def build_retrieval_query(payload: dict[str, Any]) -> str:
    ticket = payload.get("ticket") if isinstance(payload.get("ticket"), dict) else {}
    parts = [
        _clean(ticket.get("category") or payload.get("category")),
        _clean(ticket.get("technicalSubcategory") or payload.get("technicalSubcategory")),
        _clean(ticket.get("inquiry") or payload.get("inquiry")),
    ]

    for item in payload.get("messages") if isinstance(payload.get("messages"), list) else []:
        if not isinstance(item, dict):
            continue
        text = _clean(item.get("text"))
        if text:
            parts.append(text)

    parts.append(_clean(payload.get("message")))

    query = " ".join(part for part in parts if part)
    lower_query = query.lower()
    if any(value in lower_query for value in ("main page", "home page", "overview", "workspace", "dashboard")):
        query = (
            f"{query} Learner Workspace Overview Continue Learning activity cards "
            "assignment upload submit confirm"
        )

    return query.strip()


def build_model_input(payload: dict[str, Any], kb_context: str) -> list[dict[str, Any]]:
    ticket = payload.get("ticket") if isinstance(payload.get("ticket"), dict) else {}
    learner = payload.get("learner") if isinstance(payload.get("learner"), dict) else {}
    context = (
        f"Learner: {learner.get('fullName') or ''} <{learner.get('email') or ''}>\n"
        f"Ticket category: {ticket.get('category') or payload.get('category') or ''}\n"
        f"Ticket subcategory: {ticket.get('technicalSubcategory') or payload.get('technicalSubcategory') or ''}\n"
        f"Ticket inquiry: {ticket.get('inquiry') or payload.get('inquiry') or ''}\n"
        f"Knowledge-base context:\n{kb_context or 'No retrieved context.'}"
    )
    messages = [{"role": "developer", "content": context}]
    messages.extend(_recent_context_messages(payload.get("messages") if isinstance(payload.get("messages"), list) else []))
    messages.append({"role": "user", "content": payload.get("message") or payload.get("inquiry") or "Please help with this support request."})
    return messages


def handle_chat(payload: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    timings: dict[str, int] = {}

    try:
        normalized_payload = normalize_chat_payload(payload)
        session_key = get_session_key(normalized_payload)

        checkpoint = time.perf_counter()
        previous_route = get_last_route(session_key)
        timings["lastRouteLookupMs"] = round((time.perf_counter() - checkpoint) * 1000)

        checkpoint = time.perf_counter()
        classification = classify(normalized_payload, previous_route)
        timings["classificationMs"] = round((time.perf_counter() - checkpoint) * 1000)

        if classification.direct_reply:
            processing_ms = round((time.perf_counter() - started) * 1000)
            logger.info("charly_direct_response", extra={"route": classification.route, "processingMs": processing_ms, **timings})
            return response_payload(success=True, route=classification.route, reply=classification.direct_reply, processing_ms=processing_ms)

        checkpoint = time.perf_counter()
        kb_results = search_knowledge_base(classification.route, build_retrieval_query(normalized_payload))
        kb_context = format_context(kb_results)
        timings["ragMs"] = round((time.perf_counter() - checkpoint) * 1000)

        checkpoint = time.perf_counter()
        reply = generate_reply(
            instructions=build_instructions(classification.route, kb_context),
            input_messages=build_model_input(normalized_payload, kb_context),
        )
        timings["generationMs"] = round((time.perf_counter() - checkpoint) * 1000)

        if not reply:
            raise RuntimeError("OpenAI returned an empty chatbot reply.")

        save_last_route(session_key, classification.route)
        processing_ms = round((time.perf_counter() - started) * 1000)
        logger.info("charly_chatbot_response", extra={"route": classification.route, "processingMs": processing_ms, **timings})
        return response_payload(success=True, route=classification.route, reply=reply, processing_ms=processing_ms)
    except Exception:
        processing_ms = round((time.perf_counter() - started) * 1000)
        logger.exception("Charly Django chatbot failed.")
        return response_payload(success=False, route="error", reply=CONTROLLED_FAILURE_REPLY, processing_ms=processing_ms)
