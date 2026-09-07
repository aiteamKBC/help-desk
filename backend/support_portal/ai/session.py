from __future__ import annotations

from typing import Any

from django.db import connection

STICKY_ROUTES = {"teams", "aptem", "moodle", "general"}


def get_session_key(payload: dict[str, Any]) -> str:
    ticket = payload.get("ticket") if isinstance(payload.get("ticket"), dict) else {}
    learner = payload.get("learner") if isinstance(payload.get("learner"), dict) else {}
    learner_email = str(learner.get("email") or "").strip().lower()

    return (
        str(ticket.get("id") or "").strip()
        or str(payload.get("ticketId") or "").strip()
        or str(payload.get("sessionId") or "").strip()
        or (f"{learner_email}:web" if learner_email else "guest:web")
    )


def get_last_route(session_key: str) -> str:
    if not session_key:
        return ""

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT last_route
            FROM charly_session_routes
            WHERE session_key = %s
            LIMIT 1
            """,
            [session_key],
        )
        row = cursor.fetchone()
    return str(row[0] or "").strip().lower() if row else ""


def save_last_route(session_key: str, route: str) -> None:
    normalized_route = str(route or "").strip().lower()
    if not session_key or normalized_route not in STICKY_ROUTES:
        return

    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO charly_session_routes (session_key, last_route, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (session_key)
            DO UPDATE SET last_route = EXCLUDED.last_route, updated_at = NOW()
            """,
            [session_key, normalized_route],
        )
