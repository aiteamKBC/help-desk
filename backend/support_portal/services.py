from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request
from uuid import uuid4
from zoneinfo import ZoneInfo

import psycopg
from django.conf import settings
from django.db import connection, transaction

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
ALLOWED_STATUSES = {"Open", "Pending", "In Progress", "Resolved", "Closed"}
ALLOWED_CATEGORIES = {"Learning", "Technical", "Others"}
ALLOWED_TECHNICAL_SUBCATEGORIES = {"Aptem", "LMS", "Teams"}
ALLOWED_SLA_STATUSES = {"Pending Review", "On Track", "Breached"}
UK_SUPPORT_TIMEZONE = "Europe/London"
UK_SUPPORT_SESSION_START_MINUTES = 8 * 60
UK_SUPPORT_SESSION_END_MINUTES = 16 * 60
SUPPORT_SESSION_LEAD_TIME_SECONDS = 24 * 60 * 60
WEBHOOK_RESPONSE_WRAPPER_KEYS = ("data", "body", "result", "payload", "json", "content", "booking", "meeting", "event")


@dataclass
class ApiError(Exception):
    status_code: int
    message: str


def sanitize_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def normalize_email(value: Any) -> str:
    return sanitize_text(value).lower()


def is_valid_email(email: str) -> bool:
    return bool(EMAIL_PATTERN.match(email))


def normalize_technical_subcategory(value: Any) -> str:
    normalized_value = sanitize_text(value)
    if not normalized_value:
        return ""

    for item in ALLOWED_TECHNICAL_SUBCATEGORIES:
        if item.lower() == normalized_value.lower():
            return item

    return ""


def build_public_ticket_id(ticket_id: int) -> str:
    return f"KBC-{ticket_id:06d}"


def dictfetchall(cursor) -> list[dict[str, Any]]:
    columns = [column[0] for column in cursor.description or []]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def dictfetchone(cursor) -> dict[str, Any] | None:
    rows = dictfetchall(cursor)
    return rows[0] if rows else None


def run_query(sql: str, params: list[Any] | tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        return dictfetchall(cursor)


def run_query_one(sql: str, params: list[Any] | tuple[Any, ...] | None = None) -> dict[str, Any] | None:
    rows = run_query(sql, params)
    return rows[0] if rows else None


def fetch_local_learner_by_email(email: str) -> dict[str, Any] | None:
    return run_query_one(
        """
        SELECT id, external_learner_id, full_name, email, phone
        FROM learners
        WHERE LOWER(TRIM(email)) = %s
        LIMIT 1
        """,
        [email],
    )


def fetch_legacy_learner_by_email(email: str) -> dict[str, Any] | None:
    if not settings.LEGACY_DATABASE_URL:
        return None

    with psycopg.connect(settings.LEGACY_DATABASE_URL) as source_connection:
        with source_connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT
                  NULLIF(TRIM("ID"::text), '') AS external_learner_id,
                  NULLIF(TRIM(COALESCE("FullName", CONCAT_WS(' ', "FirstName", "LastName"))), '') AS full_name,
                  LOWER(TRIM("Email")) AS email,
                  NULLIF(TRIM(COALESCE("Learner_Phone", "learner-phone")), '') AS phone
                FROM kbc_users_data
                WHERE LOWER(TRIM("Email")) = %s
                LIMIT 1
                """,
                [email],
            )
            row = cursor.fetchone()

    if not row:
        return None

    external_learner_id, full_name, normalized_email, phone = row
    return {
        "external_learner_id": external_learner_id,
        "full_name": full_name,
        "email": normalized_email,
        "phone": phone,
    }


def upsert_learner_record(learner: dict[str, Any], source: str, metadata: dict[str, Any]) -> dict[str, Any] | None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO learners (
              external_learner_id,
              full_name,
              email,
              phone,
              source,
              metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (email) DO UPDATE
            SET
              external_learner_id = COALESCE(EXCLUDED.external_learner_id, learners.external_learner_id),
              full_name = COALESCE(EXCLUDED.full_name, learners.full_name),
              phone = COALESCE(EXCLUDED.phone, learners.phone),
              source = EXCLUDED.source,
              metadata = learners.metadata || EXCLUDED.metadata,
              updated_at = NOW()
            RETURNING id, external_learner_id, full_name, email, phone
            """,
            [
                learner.get("external_learner_id"),
                learner.get("full_name"),
                learner["email"],
                learner.get("phone"),
                source,
                json.dumps(metadata),
            ],
        )
        return dictfetchone(cursor)


def find_learner_by_email(email: str) -> dict[str, Any] | None:
    learner = fetch_local_learner_by_email(email)
    if learner:
        return learner

    legacy_learner = fetch_legacy_learner_by_email(email)
    if not legacy_learner:
        return None

    return upsert_learner_record(
        legacy_learner,
        source="legacy_kbc_users_data",
        metadata={
            "legacy_source": "kbc_users_data",
            "synced_on_demand": True,
        },
    )


def serialize_agent(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "username": row["username"],
        "fullName": row.get("full_name") or row["username"],
        "email": row.get("email") or None,
        "role": row["role"],
    }


def serialize_ticket_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["public_id"],
        "learnerName": row.get("learner_name") or "",
        "email": row.get("learner_email") or "",
        "category": row["category"],
        "technicalSubcategory": row.get("technical_subcategory") or "",
        "status": row["status"],
        "assignedAgentId": int(row["assigned_agent_id"]) if row.get("assigned_agent_id") else None,
        "assignedAgentName": row.get("assigned_agent_name") or "Unassigned",
        "assignedAgentUsername": row.get("assigned_agent_username") or "",
        "assignedTeam": row.get("assigned_team") or "Unassigned",
        "slaStatus": row["sla_status"],
        "evidenceCount": int(row.get("evidence_count") or 0),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def serialize_ticket_detail(row: dict[str, Any]) -> dict[str, Any]:
    detail = serialize_ticket_summary(row)
    detail.update(
        {
            "inquiry": row["inquiry"],
            "priority": row["priority"],
            "closedAt": row.get("closed_at"),
        }
    )
    return detail


def to_sender_label(role: str, metadata: dict[str, Any] | None) -> str:
    original_sender = sanitize_text((metadata or {}).get("original_sender"))

    if role == "user":
        return "Learner"
    if role == "agent":
        return "Agent"
    if original_sender == "bot":
        return "Bot"
    return "Support"


def map_sender_to_role(sender: str) -> str:
    if sender == "user":
        return "user"
    if sender == "agent":
        return "agent"
    return "assistant"


def parse_assigned_agent_id(value: Any) -> int | None:
    if value in (None, "", "unassigned"):
        return None

    try:
        return int(str(value))
    except (TypeError, ValueError) as error:
        raise ApiError(400, "Invalid assigned agent.") from error


def derive_assigned_team(agent: dict[str, Any] | None) -> str:
    return "Support Desk" if agent else "Unassigned"


def map_conversation_status(status: str) -> str:
    if status == "In Progress":
        return "in_progress"
    return status.lower()


def parse_local_datetime(date_value: str, time_value: str) -> datetime | None:
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_value) or not re.match(r"^\d{2}:\d{2}$", time_value):
        return None

    try:
        return datetime.strptime(f"{date_value} {time_value}", "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def parse_scheduled_at(value: str) -> datetime | None:
    value = sanitize_text(value)
    if not value:
        return None

    try:
        normalized_value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized_value)
    except ValueError:
        return None


def get_time_in_timezone_minutes(value: datetime, timezone_name: str) -> int:
    if value.tzinfo is None:
        aware_value = value.replace(tzinfo=ZoneInfo(settings.TIME_ZONE))
    else:
        aware_value = value

    localized = aware_value.astimezone(ZoneInfo(timezone_name))
    return (localized.hour * 60) + localized.minute


def is_minutes_within_range(minutes: int, start_minutes: int, end_minutes: int) -> bool:
    return start_minutes <= minutes <= end_minutes


def is_within_support_session_window(requested_datetime: datetime) -> bool:
    uk_minutes = get_time_in_timezone_minutes(requested_datetime, UK_SUPPORT_TIMEZONE)

    return is_minutes_within_range(
        uk_minutes,
        UK_SUPPORT_SESSION_START_MINUTES,
        UK_SUPPORT_SESSION_END_MINUTES,
    )


def validate_support_session_request(
    date_value: str,
    time_value: str,
    scheduled_at_value: str = "",
    now: datetime | None = None,
) -> str:
    current_time = now or datetime.now(tz=ZoneInfo(settings.TIME_ZONE))
    requested_datetime = resolve_support_session_datetime(date_value, time_value, scheduled_at_value)

    if not requested_datetime:
        return "Please choose a valid session date and time."

    if (requested_datetime - current_time).total_seconds() <= SUPPORT_SESSION_LEAD_TIME_SECONDS:
        return "Support sessions must be booked more than 24 hours in advance."

    if not is_within_support_session_window(requested_datetime):
        return "Support sessions must be between 8:00 AM and 4:00 PM UK time."

    return ""


def resolve_support_session_datetime(date_value: str, time_value: str, scheduled_at_value: str = "") -> datetime | None:
    requested_datetime = parse_scheduled_at(scheduled_at_value) if scheduled_at_value else parse_local_datetime(date_value, time_value)

    if not requested_datetime:
        return None

    if requested_datetime.tzinfo is None:
        return requested_datetime.replace(tzinfo=ZoneInfo(settings.TIME_ZONE))

    return requested_datetime


def extract_webhook_value(response_payload: Any, keys: tuple[str, ...]) -> Any | None:
    if isinstance(response_payload, list):
        for item in response_payload:
            value = extract_webhook_value(item, keys)
            if value is not None and (not isinstance(value, str) or value.strip()):
                return value
        return None

    if isinstance(response_payload, dict):
        for key in keys:
            if key in response_payload:
                value = response_payload[key]
                if value is not None and (not isinstance(value, str) or value.strip()):
                    return value

        for wrapper_key in WEBHOOK_RESPONSE_WRAPPER_KEYS:
            if wrapper_key in response_payload:
                nested_value = extract_webhook_value(response_payload[wrapper_key], keys)
                if nested_value is not None and (not isinstance(nested_value, str) or nested_value.strip()):
                    return nested_value

    return None


def extract_webhook_string(response_payload: Any, keys: tuple[str, ...]) -> str:
    value = extract_webhook_value(response_payload, keys)
    return sanitize_text(value) if isinstance(value, str) else ""


def extract_webhook_bool(response_payload: Any, keys: tuple[str, ...]) -> bool | None:
    value = extract_webhook_value(response_payload, keys)

    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized_value = value.strip().lower()
        if normalized_value in {"true", "1", "yes", "ok", "success"}:
            return True
        if normalized_value in {"false", "0", "no", "failed"}:
            return False

    return None


def build_support_session_webhook_payload(
    ticket: dict[str, Any],
    session_request_id: int,
    requested_date: str,
    requested_time: str,
    requested_datetime: datetime,
    client_time_zone: str,
    created_at: Any,
) -> dict[str, Any]:
    request_end = requested_datetime + timedelta(minutes=settings.SUPPORT_SESSION_DURATION_MINUTES)
    request_start_utc = requested_datetime.astimezone(ZoneInfo("UTC"))
    request_end_utc = request_end.astimezone(ZoneInfo("UTC"))

    return {
        "event": "support_session_requested",
        "source": "support_portal",
        "bookingProvider": "microsoft_teams",
        "reserveSlot": True,
        "durationMinutes": settings.SUPPORT_SESSION_DURATION_MINUTES,
        "ticketId": ticket["public_id"],
        "learnerId": int(ticket["learner_id"]),
        "learnerName": ticket.get("learner_full_name"),
        "learnerEmail": ticket["learner_email"],
        "learnerPhone": ticket.get("learner_phone"),
        "category": ticket["category"],
        "technicalSubcategory": ticket.get("technical_subcategory"),
        "inquiry": ticket["inquiry"],
        "ticketStatus": ticket["status"],
        "ticketPriority": ticket["priority"],
        "assignedTeam": ticket["assigned_team"],
        "requestedDate": requested_date,
        "requestedTime": requested_time,
        "requestedStartAt": requested_datetime.isoformat(),
        "requestedEndAt": request_end.isoformat(),
        "requestedStartAtUtc": request_start_utc.isoformat().replace("+00:00", "Z"),
        "requestedEndAtUtc": request_end_utc.isoformat().replace("+00:00", "Z"),
        "requestedTimeZone": client_time_zone or settings.TIME_ZONE,
        "sessionRequestId": session_request_id,
        "createdAt": created_at,
        "learner": {
            "id": int(ticket["learner_id"]),
            "fullName": ticket.get("learner_full_name"),
            "email": ticket["learner_email"],
            "phone": ticket.get("learner_phone"),
        },
        "ticket": {
            "id": ticket["public_id"],
            "category": ticket["category"],
            "technicalSubcategory": ticket.get("technical_subcategory"),
            "inquiry": ticket["inquiry"],
            "status": ticket["status"],
            "priority": ticket["priority"],
            "assignedTeam": ticket["assigned_team"],
        },
    }


def extract_booking_webhook_result(response_payload: Any, delivered: bool, status: int | None) -> dict[str, Any]:
    meeting_join_url = extract_webhook_string(
        response_payload,
        ("joinUrl", "meetingJoinUrl", "teamsJoinUrl", "meeting_url", "teams_meeting_url", "webUrl"),
    )
    event_id = extract_webhook_string(
        response_payload,
        ("eventId", "calendarEventId", "bookingId", "reservationId", "id"),
    )
    calendar_event_url = extract_webhook_string(
        response_payload,
        ("calendarEventUrl", "eventUrl", "calendarUrl", "outlookEventUrl"),
    )
    organizer_email = extract_webhook_string(
        response_payload,
        ("organizerEmail", "hostEmail", "ownerEmail", "calendarOwnerEmail"),
    )
    booking_reference = extract_webhook_string(
        response_payload,
        ("bookingReference", "reference", "bookingCode", "reservationCode"),
    )

    reserved_flag = extract_webhook_bool(
        response_payload,
        ("reservationConfirmed", "bookingConfirmed", "reserved", "booked", "scheduled", "created"),
    )
    conflict_flag = extract_webhook_bool(
        response_payload,
        ("slotUnavailable", "conflict", "alreadyBooked", "busy", "unavailable"),
    )
    available_flag = extract_webhook_bool(response_payload, ("available", "slotAvailable"))
    message = extract_webhook_string(
        response_payload,
        ("message", "detail", "error", "reason"),
    ) or extract_chatbot_reply(response_payload)

    slot_unavailable = conflict_flag is True or available_flag is False or status == 409
    reservation_confirmed = False

    if not slot_unavailable:
        if reserved_flag is not None:
            reservation_confirmed = reserved_flag
        elif delivered and status is not None and 200 <= status < 300 and (event_id or meeting_join_url or calendar_event_url):
            reservation_confirmed = True

    return {
        "reservationConfirmed": reservation_confirmed,
        "slotUnavailable": slot_unavailable,
        "meetingJoinUrl": meeting_join_url or None,
        "calendarEventId": event_id or None,
        "calendarEventUrl": calendar_event_url or None,
        "organizerEmail": organizer_email or None,
        "bookingReference": booking_reference or None,
        "message": message or "",
    }


def update_support_session_request_record(
    session_request_id: int,
    *,
    status: str,
    notes: str | None = None,
    metadata_patch: dict[str, Any] | None = None,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE support_session_requests
            SET status = %s,
                notes = COALESCE(%s, notes),
                metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb
            WHERE id = %s
            """,
            [
                status,
                sanitize_text(notes) or None,
                json.dumps(metadata_patch or {}),
                session_request_id,
            ],
        )


def normalize_chat_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []

    for message in messages or []:
        content = sanitize_text(message.get("text"))
        if not content:
            continue

        normalized.append(
            {
                "role": map_sender_to_role(sanitize_text(message.get("sender"))),
                "content": content,
                "metadata": {
                    "original_sender": sanitize_text(message.get("sender")),
                    "client_timestamp": sanitize_text(message.get("timestamp")),
                },
            }
        )

    return normalized


def sync_conversation_messages(conversation_id: int, status: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    filtered_messages = normalize_chat_messages(messages)

    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM messages WHERE conversation_id = %s", [conversation_id])

        for message in filtered_messages:
            cursor.execute(
                """
                INSERT INTO messages (
                  conversation_id,
                  role,
                  content,
                  channel,
                  metadata
                )
                VALUES (%s, %s, %s, %s, %s::jsonb)
                """,
                [
                    conversation_id,
                    message["role"],
                    message["content"],
                    "support",
                    json.dumps(message["metadata"]),
                ],
            )

        cursor.execute(
            """
            UPDATE conversations
            SET status = %s,
                last_message_at = NOW(),
                metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb
            WHERE id = %s
            """,
            [map_conversation_status(status), json.dumps({"synced_messages": len(filtered_messages)}), conversation_id],
        )

    return filtered_messages


def fetch_actor_by_username(username: str) -> dict[str, Any] | None:
    if not username:
        return None

    return run_query_one(
        """
        SELECT id, username, full_name, role
        FROM agents
        WHERE LOWER(username) = %s
        LIMIT 1
        """,
        [username.lower()],
    )


def insert_history_event(ticket_id: int, event_type: str, actor: dict[str, Any] | None, payload: dict[str, Any]) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO ticket_history (
              ticket_id,
              event_type,
              actor_type,
              actor_id,
              actor_label,
              payload
            )
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            """,
            [
                ticket_id,
                event_type,
                actor.get("role") if actor else "system",
                actor.get("id") if actor else None,
                actor.get("label") if actor else None,
                json.dumps(payload or {}),
            ],
        )


def fetch_admin_ticket_detail(public_id: str) -> dict[str, Any] | None:
    ticket = run_query_one(
        """
        SELECT
          t.id,
          t.public_id,
          t.category,
          t.technical_subcategory,
          t.inquiry,
          t.status,
          t.assigned_team,
          t.sla_status,
          t.priority,
          t.evidence_count,
          t.created_at,
          t.updated_at,
          t.closed_at,
          t.conversation_id,
          l.full_name AS learner_name,
          l.email AS learner_email,
          a.id AS assigned_agent_id,
          a.username AS assigned_agent_username,
          a.full_name AS assigned_agent_name
        FROM tickets t
        JOIN learners l
          ON l.id = t.learner_id
        LEFT JOIN agents a
          ON a.id = t.assigned_agent_id
        WHERE t.public_id = %s
        LIMIT 1
        """,
        [public_id],
    )

    if not ticket:
        return None

    if ticket.get("conversation_id"):
        messages = run_query(
            """
            SELECT id, role, content, metadata, created_at
            FROM messages
            WHERE conversation_id = %s
            ORDER BY created_at ASC, id ASC
            """,
            [ticket["conversation_id"]],
        )
    else:
        messages = []

    attachments = run_query(
        """
        SELECT id, file_name, mime_type, file_size, storage_url, metadata, created_at
        FROM ticket_attachments
        WHERE ticket_id = %s
        ORDER BY created_at ASC, id ASC
        """,
        [ticket["id"]],
    )
    history = run_query(
        """
        SELECT id, event_type, actor_type, actor_label, payload, created_at
        FROM ticket_history
        WHERE ticket_id = %s
        ORDER BY created_at DESC, id DESC
        """,
        [ticket["id"]],
    )
    session_requests = run_query(
        """
        SELECT id, requested_date, requested_time, status, created_by, notes, metadata, created_at
        FROM support_session_requests
        WHERE ticket_id = %s
        ORDER BY created_at DESC, id DESC
        """,
        [ticket["id"]],
    )

    return {
        "ticket": serialize_ticket_detail(ticket),
        "chatHistory": [
            {
                "id": int(row["id"]),
                "role": row["role"],
                "senderLabel": to_sender_label(row["role"], row.get("metadata")),
                "text": row["content"],
                "createdAt": row["created_at"],
            }
            for row in messages
        ],
        "attachments": [
            {
                "id": int(row["id"]),
                "name": row["file_name"],
                "mimeType": row.get("mime_type"),
                "size": int(row["file_size"]) if row.get("file_size") else 0,
                "storageUrl": row.get("storage_url"),
                "metadata": row.get("metadata") or {},
                "createdAt": row["created_at"],
            }
            for row in attachments
        ],
        "history": [
            {
                "id": int(row["id"]),
                "eventType": row["event_type"],
                "actorType": row["actor_type"],
                "actorLabel": row.get("actor_label"),
                "payload": row.get("payload") or {},
                "createdAt": row["created_at"],
            }
            for row in history
        ],
        "sessionRequests": [
            {
                "id": int(row["id"]),
                "requestedDate": row["requested_date"],
                "requestedTime": row["requested_time"],
                "status": row["status"],
                "createdBy": row["created_by"],
                "notes": row.get("notes"),
                "metadata": row.get("metadata") or {},
                "createdAt": row["created_at"],
            }
            for row in session_requests
        ],
    }


def get_verify_email_response(payload: dict[str, Any]) -> dict[str, Any]:
    email = normalize_email(payload.get("email"))

    if not is_valid_email(email):
        raise ApiError(400, "Please enter a valid email address.")

    learner = find_learner_by_email(email)

    if not learner:
        raise ApiError(404, "This email is not registered in our records.")

    return {
        "exists": True,
        "learner": {
            "id": learner["id"],
            "fullName": learner.get("full_name"),
            "email": learner["email"],
        },
        "message": "Email verified.",
    }


def get_admin_login_response(payload: dict[str, Any]) -> dict[str, Any]:
    username = sanitize_text(payload.get("username")).lower()
    password = payload.get("password") if isinstance(payload.get("password"), str) else ""

    if not username or not password:
        raise ApiError(400, "Username and password are required.")

    if not settings.SUPPORT_PORTAL_PASSWORD:
        raise ApiError(503, "Admin login is not configured. Set SUPPORT_PORTAL_PASSWORD on the server.")

    agent = run_query_one(
        """
        SELECT id, username, full_name, email, role
        FROM agents
        WHERE LOWER(username) = %s
          AND is_active = TRUE
        LIMIT 1
        """,
        [username],
    )

    if not agent or password != settings.SUPPORT_PORTAL_PASSWORD:
        raise ApiError(401, "Invalid username or password.")

    return {
        "admin": serialize_agent(agent),
        "message": "Login successful.",
    }


def list_agents() -> dict[str, Any]:
    agents = run_query(
        """
        SELECT id, username, full_name, email, role
        FROM agents
        WHERE is_active = TRUE
        ORDER BY role DESC, full_name ASC NULLS LAST, username ASC
        """
    )

    return {"agents": [serialize_agent(agent) for agent in agents]}


def list_admin_tickets() -> dict[str, Any]:
    tickets = run_query(
        """
        SELECT
          t.id,
          t.public_id,
          t.category,
          t.technical_subcategory,
          t.status,
          t.assigned_team,
          t.sla_status,
          t.evidence_count,
          t.created_at,
          t.updated_at,
          l.full_name AS learner_name,
          l.email AS learner_email,
          a.id AS assigned_agent_id,
          a.username AS assigned_agent_username,
          a.full_name AS assigned_agent_name
        FROM tickets t
        JOIN learners l
          ON l.id = t.learner_id
        LEFT JOIN agents a
          ON a.id = t.assigned_agent_id
        ORDER BY t.created_at DESC, t.id DESC
        """
    )

    return {"tickets": [serialize_ticket_summary(ticket) for ticket in tickets]}


def get_admin_ticket_detail_response(public_id: str) -> dict[str, Any]:
    if not public_id:
        raise ApiError(400, "Ticket id is required.")

    detail = fetch_admin_ticket_detail(public_id)
    if not detail:
        raise ApiError(404, "Ticket not found.")

    return detail


def update_admin_ticket(public_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    requested_status = sanitize_text(payload.get("status")) if "status" in payload else None
    requested_sla_status = sanitize_text(payload.get("slaStatus")) if "slaStatus" in payload else None
    requested_assigned_team = sanitize_text(payload.get("assignedTeam")) if "assignedTeam" in payload else None
    actor_username = sanitize_text(payload.get("actorUsername")).lower()
    note = sanitize_text(payload.get("note"))
    has_assigned_agent_input = "assignedAgentId" in payload

    if not public_id:
        raise ApiError(400, "Ticket id is required.")

    if requested_status is not None and requested_status not in ALLOWED_STATUSES:
        raise ApiError(400, "Invalid ticket status.")

    if requested_sla_status is not None and requested_sla_status not in ALLOWED_SLA_STATUSES:
        raise ApiError(400, "Invalid SLA status.")

    parsed_assigned_agent_id = parse_assigned_agent_id(payload.get("assignedAgentId")) if has_assigned_agent_input else None

    with transaction.atomic():
        ticket = run_query_one(
            """
            SELECT
              t.id,
              t.public_id,
              t.status,
              t.assigned_agent_id,
              t.assigned_team,
              t.sla_status,
              t.closed_at,
              t.conversation_id,
              a.username AS assigned_agent_username,
              a.full_name AS assigned_agent_name
            FROM tickets t
            LEFT JOIN agents a
              ON a.id = t.assigned_agent_id
            WHERE t.public_id = %s
            LIMIT 1
            """,
            [public_id],
        )

        if not ticket:
            raise ApiError(404, "Ticket not found.")

        actor_row = fetch_actor_by_username(actor_username) if actor_username else None
        actor = (
            {
                "id": actor_row["id"],
                "role": actor_row["role"],
                "label": actor_row.get("full_name") or actor_row["username"],
            }
            if actor_row
            else None
        )

        assigned_agent = None
        if has_assigned_agent_input and parsed_assigned_agent_id is not None:
            assigned_agent = run_query_one(
                """
                SELECT id, username, full_name, email, role
                FROM agents
                WHERE id = %s
                  AND is_active = TRUE
                LIMIT 1
                """,
                [parsed_assigned_agent_id],
            )
            if not assigned_agent:
                raise ApiError(400, "The selected agent does not exist.")
        elif not has_assigned_agent_input and ticket.get("assigned_agent_id"):
            assigned_agent = {
                "id": ticket["assigned_agent_id"],
                "username": ticket.get("assigned_agent_username"),
                "full_name": ticket.get("assigned_agent_name"),
                "role": "agent",
            }

        next_status = requested_status or ticket["status"]
        next_sla_status = requested_sla_status or ticket["sla_status"]
        next_assigned_agent_id = parsed_assigned_agent_id if has_assigned_agent_input else ticket.get("assigned_agent_id")
        if requested_assigned_team is not None:
            next_assigned_team = requested_assigned_team or derive_assigned_team(assigned_agent)
        elif has_assigned_agent_input:
            next_assigned_team = derive_assigned_team(assigned_agent)
        else:
            next_assigned_team = ticket["assigned_team"]

        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE tickets
                SET
                  status = %s,
                  assigned_agent_id = %s,
                  assigned_team = %s,
                  sla_status = %s,
                  updated_at = NOW(),
                  closed_at = CASE
                    WHEN %s = 'Closed' THEN NOW()
                    WHEN status = 'Closed' AND %s <> 'Closed' THEN NULL
                    ELSE closed_at
                  END
                WHERE id = %s
                """,
                [
                    next_status,
                    next_assigned_agent_id,
                    next_assigned_team,
                    next_sla_status,
                    next_status,
                    next_status,
                    ticket["id"],
                ],
            )

            if ticket.get("conversation_id"):
                cursor.execute(
                    """
                    UPDATE conversations
                    SET
                      status = %s,
                      last_message_at = NOW(),
                      metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb
                    WHERE id = %s
                    """,
                    [
                        map_conversation_status(next_status),
                        json.dumps(
                            {
                                "ticket_status": next_status,
                                "assigned_agent_id": next_assigned_agent_id,
                                "assigned_team": next_assigned_team,
                            }
                        ),
                        ticket["conversation_id"],
                    ],
                )

        if ticket["status"] != next_status:
            insert_history_event(ticket["id"], "status_changed", actor, {"from": ticket["status"], "to": next_status})

        if (ticket.get("assigned_agent_id") or None) != (next_assigned_agent_id or None):
            insert_history_event(
                ticket["id"],
                "assignment_changed",
                actor,
                {
                    "fromAgentId": ticket.get("assigned_agent_id"),
                    "toAgentId": next_assigned_agent_id,
                    "toAgentName": assigned_agent.get("full_name") if assigned_agent else None,
                },
            )

        if ticket["sla_status"] != next_sla_status:
            insert_history_event(ticket["id"], "sla_changed", actor, {"from": ticket["sla_status"], "to": next_sla_status})

        if note:
            insert_history_event(ticket["id"], "internal_note", actor, {"note": note})

    detail = fetch_admin_ticket_detail(public_id)
    if not detail:
        raise ApiError(404, "Ticket not found.")

    return detail


def create_ticket(payload: dict[str, Any]) -> dict[str, Any]:
    email = normalize_email(payload.get("email"))
    category = sanitize_text(payload.get("category"))
    technical_subcategory = normalize_technical_subcategory(payload.get("technicalSubcategory"))
    inquiry = sanitize_text(payload.get("inquiry"))
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), list) else []

    if not is_valid_email(email):
        raise ApiError(400, "Please enter a valid email address.")
    if category not in ALLOWED_CATEGORIES:
        raise ApiError(400, "Please choose a valid inquiry category.")
    if category == "Technical" and not technical_subcategory:
        raise ApiError(400, "Please choose a technical sub category.")
    if category != "Technical" and technical_subcategory:
        raise ApiError(400, "Technical sub category can only be used with Technical inquiries.")
    if not inquiry:
        raise ApiError(400, "Inquiry details are required.")

    with transaction.atomic():
        learner = find_learner_by_email(email)

        if not learner:
            raise ApiError(404, "This email is not registered in our records.")

        draft_public_id = f"TMP-{int(datetime.now().timestamp() * 1000)}-{uuid4().hex[:8]}"
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO tickets (
                  public_id,
                  learner_id,
                  category,
                  technical_subcategory,
                  inquiry,
                  evidence_count,
                  metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                RETURNING id, status, assigned_team, sla_status, created_at
                """,
                [
                    draft_public_id,
                    learner["id"],
                    category,
                    technical_subcategory or None,
                    inquiry,
                    len(evidence),
                    json.dumps(
                        {
                            "source": "support_portal",
                            "technical_subcategory": technical_subcategory or None,
                        }
                    ),
                ],
            )
            ticket_row = dictfetchone(cursor)
            if not ticket_row:
                raise ApiError(500, "We could not create the ticket right now.")

            public_id = build_public_ticket_id(int(ticket_row["id"]))

            cursor.execute(
                """
                INSERT INTO conversations (
                  channel,
                  customer_id,
                  customer_name,
                  customer_email,
                  customer_phone,
                  status,
                  intent,
                  language,
                  created_at,
                  last_message_at,
                  metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW(), %s::jsonb)
                RETURNING id
                """,
                [
                    "support",
                    public_id,
                    learner.get("full_name"),
                    learner["email"],
                    learner.get("phone"),
                    "open",
                    category,
                    "en",
                    json.dumps(
                        {
                            "ticket_public_id": public_id,
                            "learner_id": learner["id"],
                            "technical_subcategory": technical_subcategory or None,
                        }
                    ),
                ],
            )
            conversation_row = dictfetchone(cursor)
            conversation_id = conversation_row["id"] if conversation_row else None

            cursor.execute(
                """
                UPDATE tickets
                SET public_id = %s, conversation_id = %s, updated_at = NOW()
                WHERE id = %s
                """,
                [public_id, conversation_id, ticket_row["id"]],
            )

            for file in evidence:
                cursor.execute(
                    """
                    INSERT INTO ticket_attachments (
                      ticket_id,
                      file_name,
                      mime_type,
                      file_size,
                      storage_url,
                      metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    [
                        ticket_row["id"],
                        sanitize_text(file.get("name")),
                        sanitize_text(file.get("mimeType")) or None,
                        int(file["size"]) if isinstance(file.get("size"), (int, float)) else None,
                        None,
                        json.dumps(file),
                    ],
                )

        insert_history_event(
            int(ticket_row["id"]),
            "ticket_created",
            {"role": "learner", "label": learner["email"]},
            {
                "category": category,
                "technical_subcategory": technical_subcategory or None,
                "evidence_count": len(evidence),
            },
        )

    return {
        "ticket": {
            "id": public_id,
            "email": learner["email"],
            "category": category,
            "technicalSubcategory": technical_subcategory,
            "inquiry": inquiry,
            "status": ticket_row["status"],
            "assignedTeam": ticket_row["assigned_team"],
            "slaStatus": ticket_row["sla_status"],
            "createdAt": ticket_row["created_at"],
        }
    }


def update_ticket(public_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    category = sanitize_text(payload.get("category"))
    technical_subcategory = normalize_technical_subcategory(payload.get("technicalSubcategory"))
    inquiry = sanitize_text(payload.get("inquiry"))
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), list) else []

    if not public_id:
        raise ApiError(400, "Ticket id is required.")
    if category not in ALLOWED_CATEGORIES:
        raise ApiError(400, "Please choose a valid inquiry category.")
    if category == "Technical" and not technical_subcategory:
        raise ApiError(400, "Please choose a technical sub category.")
    if category != "Technical" and technical_subcategory:
        raise ApiError(400, "Technical sub category can only be used with Technical inquiries.")
    if not inquiry:
        raise ApiError(400, "Inquiry details are required.")

    with transaction.atomic():
        existing_ticket = run_query_one(
            """
            SELECT
              t.id,
              t.public_id,
              t.status,
              t.assigned_team,
              t.sla_status,
              t.created_at,
              t.conversation_id,
              t.technical_subcategory,
              l.email
            FROM tickets t
            JOIN learners l
              ON l.id = t.learner_id
            WHERE t.public_id = %s
            LIMIT 1
            """,
            [public_id],
        )

        if not existing_ticket:
            raise ApiError(404, "Ticket not found.")

        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE tickets
                SET
                  category = %s,
                  technical_subcategory = %s,
                  inquiry = %s,
                  evidence_count = %s,
                  updated_at = NOW()
                WHERE id = %s
                """,
                [category, technical_subcategory or None, inquiry, len(evidence), existing_ticket["id"]],
            )

            if existing_ticket.get("conversation_id"):
                cursor.execute(
                    """
                    UPDATE conversations
                    SET
                      intent = %s,
                      metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb,
                      last_message_at = NOW()
                    WHERE id = %s
                    """,
                    [
                        category,
                        json.dumps(
                            {
                                "ticket_category": category,
                                "technical_subcategory": technical_subcategory or None,
                                "latest_inquiry": inquiry,
                                "evidence_count": len(evidence),
                            }
                        ),
                        existing_ticket["conversation_id"],
                    ],
                )

            cursor.execute("DELETE FROM ticket_attachments WHERE ticket_id = %s", [existing_ticket["id"]])

            for file in evidence:
                cursor.execute(
                    """
                    INSERT INTO ticket_attachments (
                      ticket_id,
                      file_name,
                      mime_type,
                      file_size,
                      storage_url,
                      metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    [
                        existing_ticket["id"],
                        sanitize_text(file.get("name")),
                        sanitize_text(file.get("mimeType")) or None,
                        int(file["size"]) if isinstance(file.get("size"), (int, float)) else None,
                        None,
                        json.dumps(file),
                    ],
                )

        insert_history_event(
            int(existing_ticket["id"]),
            "ticket_updated",
            {"role": "learner", "label": existing_ticket["email"]},
            {
                "category": category,
                "technical_subcategory": technical_subcategory or None,
                "evidence_count": len(evidence),
            },
        )

    return {
        "ticket": {
            "id": existing_ticket["public_id"],
            "email": existing_ticket["email"],
            "category": category,
            "technicalSubcategory": technical_subcategory,
            "inquiry": inquiry,
            "status": existing_ticket["status"],
            "assignedTeam": existing_ticket["assigned_team"],
            "slaStatus": existing_ticket["sla_status"],
            "createdAt": existing_ticket["created_at"],
        }
    }


def save_chat_history(public_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    status = sanitize_text(payload.get("status")) or "Open"
    messages = payload.get("messages") if isinstance(payload.get("messages"), list) else []

    if not public_id:
        raise ApiError(400, "Ticket id is required.")
    if status not in ALLOWED_STATUSES:
        raise ApiError(400, "Invalid ticket status.")

    with transaction.atomic():
        ticket = run_query_one(
            """
            SELECT id, conversation_id
            FROM tickets
            WHERE public_id = %s
            LIMIT 1
            """,
            [public_id],
        )

        if not ticket:
            raise ApiError(404, "Ticket not found.")
        if not ticket.get("conversation_id"):
            raise ApiError(400, "This ticket is not linked to a conversation.")

        filtered_messages = sync_conversation_messages(int(ticket["conversation_id"]), status, messages)

        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE tickets
                SET status = %s,
                    updated_at = NOW(),
                    closed_at = CASE WHEN %s = 'Closed' THEN NOW() ELSE closed_at END
                WHERE id = %s
                """,
                [status, status, ticket["id"]],
            )

        insert_history_event(
            int(ticket["id"]),
            "chat_history_synced",
            {"role": "system", "label": "support_portal"},
            {"message_count": len(filtered_messages), "status": status},
        )

    return {"ok": True}


def extract_chatbot_reply(response_payload: Any) -> str:
    if not response_payload:
        return ""
    if isinstance(response_payload, str):
        return response_payload.strip()
    if isinstance(response_payload, list):
        for item in response_payload:
            reply = extract_chatbot_reply(item)
            if reply:
                return reply
        return ""
    if isinstance(response_payload, dict):
        for key in ("reply", "message", "text", "response", "answer", "output", "output_text"):
            value = response_payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        for key in ("data", "body", "result", "payload", "json", "content", "choices", "output"):
            if key in response_payload:
                nested_reply = extract_chatbot_reply(response_payload[key])
                if nested_reply:
                    return nested_reply
    return ""


def post_json_webhook(url: str, payload: dict[str, Any]) -> tuple[bool, bool, int | None, Any]:
    if not url:
        return False, False, None, None

    request = urllib_request.Request(
        url,
        data=json.dumps(payload, default=str).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib_request.urlopen(request, timeout=20) as response:
            status = response.getcode()
            body = response.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(body) if body else None
            except json.JSONDecodeError:
                parsed = body

            return True, 200 <= status < 300, status, parsed
    except urllib_error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body) if body else None
        except json.JSONDecodeError:
            parsed = body
        return True, False, error.code, parsed or sanitize_text(body)
    except Exception:
        return True, False, None, None


def send_booking_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    configured, delivered, status, response_payload = post_json_webhook(settings.BOOKING_WEBHOOK_URL, payload)
    booking_result = extract_booking_webhook_result(response_payload, delivered, status)
    return {
        "configured": configured,
        "delivered": delivered,
        "status": status,
        **booking_result,
    }


def send_chatbot_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    configured, delivered, status, response_payload = post_json_webhook(settings.CHATBOT_WEBHOOK_URL, payload)
    return {
        "configured": configured,
        "delivered": delivered,
        "status": status,
        "reply": extract_chatbot_reply(response_payload),
    }


def send_chatbot_message(public_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    message = sanitize_text(payload.get("message"))
    client_time_zone = sanitize_text(payload.get("clientTimeZone"))
    messages = payload.get("messages") if isinstance(payload.get("messages"), list) else []

    if not public_id:
        raise ApiError(400, "Ticket id is required.")
    if not message:
        raise ApiError(400, "Message text is required.")

    ticket = run_query_one(
        """
        SELECT
          t.id,
          t.public_id,
          t.conversation_id,
          t.category,
          t.technical_subcategory,
          t.inquiry,
          t.status,
          t.priority,
          t.assigned_team,
          l.id AS learner_id,
          l.full_name AS learner_full_name,
          l.email AS learner_email,
          l.phone AS learner_phone
        FROM tickets t
        JOIN learners l
          ON l.id = t.learner_id
        WHERE t.public_id = %s
        LIMIT 1
        """,
        [public_id],
    )

    if not ticket:
        raise ApiError(404, "Ticket not found.")

    recent_messages = [
        {
            "sender": sanitize_text(entry.get("sender")),
            "text": sanitize_text(entry.get("text")),
            "timestamp": sanitize_text(entry.get("timestamp")),
        }
        for entry in messages[-12:]
        if sanitize_text(entry.get("text"))
    ]

    webhook_result = send_chatbot_webhook(
        {
            "event": "support_chat_message",
            "source": "support_portal",
            "message": message,
            "clientTimeZone": client_time_zone or None,
            "category": ticket["category"],
            "technicalSubcategory": ticket.get("technical_subcategory"),
            "inquiry": ticket["inquiry"],
            "learner": {
                "id": int(ticket["learner_id"]),
                "fullName": ticket.get("learner_full_name"),
                "email": ticket["learner_email"],
                "phone": ticket.get("learner_phone"),
            },
            "ticket": {
                "id": ticket["public_id"],
                "category": ticket["category"],
                "technicalSubcategory": ticket.get("technical_subcategory"),
                "inquiry": ticket["inquiry"],
                "status": ticket["status"],
                "priority": ticket["priority"],
                "assignedTeam": ticket["assigned_team"],
            },
            "messages": recent_messages,
        }
    )

    if ticket.get("conversation_id"):
        synced_messages = (
            messages
            + [{"sender": "bot", "text": webhook_result["reply"], "timestamp": datetime.now().isoformat()}]
            if webhook_result.get("reply")
            else messages
        )

        try:
            with transaction.atomic():
                sync_conversation_messages(int(ticket["conversation_id"]), ticket["status"], synced_messages)
        except Exception:
            pass

    return {
        "ok": True,
        "reply": webhook_result["reply"],
        "webhookConfigured": webhook_result["configured"],
        "webhookDelivered": webhook_result["delivered"],
        "webhookStatus": webhook_result["status"],
    }


def create_support_session_request(public_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    requested_date = sanitize_text(payload.get("date"))
    requested_time = sanitize_text(payload.get("time"))
    scheduled_at = sanitize_text(payload.get("scheduledAt"))
    client_time_zone = sanitize_text(payload.get("clientTimeZone"))

    if not public_id or not requested_date or not requested_time:
        raise ApiError(400, "Ticket id, date and time are required.")

    support_session_validation_message = validate_support_session_request(requested_date, requested_time, scheduled_at)
    if support_session_validation_message:
        raise ApiError(400, support_session_validation_message)

    requested_datetime = resolve_support_session_datetime(requested_date, requested_time, scheduled_at)
    if not requested_datetime:
        raise ApiError(400, "Please choose a valid session date and time.")

    with transaction.atomic():
        ticket = run_query_one(
            """
            SELECT
              t.id,
              t.public_id,
              t.category,
              t.technical_subcategory,
              t.inquiry,
              t.status,
              t.priority,
              t.assigned_team,
              l.id AS learner_id,
              l.full_name AS learner_full_name,
              l.email AS learner_email,
              l.phone AS learner_phone
            FROM tickets t
            JOIN learners l
              ON l.id = t.learner_id
            WHERE t.public_id = %s
            LIMIT 1
            """,
            [public_id],
        )

        if not ticket:
            raise ApiError(404, "Ticket not found.")

        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO support_session_requests (
                  ticket_id,
                  requested_date,
                  requested_time,
                  metadata
                )
                VALUES (%s, %s, %s, %s::jsonb)
                RETURNING id, created_at
                """,
                [
                    ticket["id"],
                    requested_date,
                    requested_time,
                    json.dumps(
                        {
                            "source": "support_portal",
                            "scheduled_at": scheduled_at or None,
                            "client_time_zone": client_time_zone or None,
                        }
                    ),
                ],
            )
            created_session_request = dictfetchone(cursor)

        insert_history_event(
            int(ticket["id"]),
            "support_session_requested",
            {"role": "learner", "label": public_id},
            {"requestedDate": requested_date, "requestedTime": requested_time},
        )

    webhook_result = send_booking_webhook(
        build_support_session_webhook_payload(
            ticket,
            int(created_session_request["id"]),
            requested_date,
            requested_time,
            requested_datetime,
            client_time_zone,
            created_session_request["created_at"],
        )
    )

    session_request_metadata = {
        "booking_provider": "microsoft_teams",
        "webhook_configured": webhook_result["configured"],
        "webhook_delivered": webhook_result["delivered"],
        "webhook_status": webhook_result["status"],
        "requested_start_at": requested_datetime.isoformat(),
        "requested_end_at": (requested_datetime + timedelta(minutes=settings.SUPPORT_SESSION_DURATION_MINUTES)).isoformat(),
        "duration_minutes": settings.SUPPORT_SESSION_DURATION_MINUTES,
        "reservation_confirmed": webhook_result["reservationConfirmed"],
        "slot_unavailable": webhook_result["slotUnavailable"],
        "calendar_event_id": webhook_result["calendarEventId"],
        "calendar_event_url": webhook_result["calendarEventUrl"],
        "meeting_join_url": webhook_result["meetingJoinUrl"],
        "organizer_email": webhook_result["organizerEmail"],
        "booking_reference": webhook_result["bookingReference"],
    }

    if webhook_result["reservationConfirmed"]:
        update_support_session_request_record(
            int(created_session_request["id"]),
            status="scheduled",
            notes="Microsoft Teams booking confirmed.",
            metadata_patch=session_request_metadata,
        )
        insert_history_event(
            int(ticket["id"]),
            "support_session_scheduled",
            {"role": "system", "label": "booking_webhook"},
            {
                "sessionRequestId": int(created_session_request["id"]),
                "meetingJoinUrl": webhook_result["meetingJoinUrl"],
                "calendarEventId": webhook_result["calendarEventId"],
            },
        )
    elif webhook_result["slotUnavailable"]:
        update_support_session_request_record(
            int(created_session_request["id"]),
            status="cancelled",
            notes=webhook_result["message"] or "The selected Teams slot is no longer available.",
            metadata_patch=session_request_metadata,
        )
        insert_history_event(
            int(ticket["id"]),
            "support_session_unavailable",
            {"role": "system", "label": "booking_webhook"},
            {
                "sessionRequestId": int(created_session_request["id"]),
                "message": webhook_result["message"] or "The selected Teams slot is no longer available.",
            },
        )
        raise ApiError(409, webhook_result["message"] or "This Teams slot is no longer available. Please choose a different time.")
    else:
        update_support_session_request_record(
            int(created_session_request["id"]),
            status="requested",
            notes=webhook_result["message"] or None,
            metadata_patch=session_request_metadata,
        )

    return {
        "ok": True,
        "webhookConfigured": webhook_result["configured"],
        "webhookDelivered": webhook_result["delivered"],
        "webhookStatus": webhook_result["status"],
        "reservationConfirmed": webhook_result["reservationConfirmed"],
        "meetingJoinUrl": webhook_result["meetingJoinUrl"],
        "calendarEventId": webhook_result["calendarEventId"],
        "calendarEventUrl": webhook_result["calendarEventUrl"],
        "organizerEmail": webhook_result["organizerEmail"],
        "bookingReference": webhook_result["bookingReference"],
        "message": webhook_result["message"] or "",
    }


def serve_frontend_asset(request_path: str) -> Path:
    dist_dir = settings.BASE_DIR.parent / "frontend" / "dist"
    index_file = dist_dir / "index.html"

    if request_path:
        candidate = (dist_dir / request_path.lstrip("/")).resolve()
        if candidate.exists() and candidate.is_file() and str(candidate).startswith(str(dist_dir.resolve())):
            return candidate

    return index_file
