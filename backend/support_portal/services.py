from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request
from uuid import uuid4
from zoneinfo import ZoneInfo

import psycopg
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import connection, transaction

from .roles import (
    ACCOUNT_ROLES,
    ACCOUNT_SCOPE_REQUESTER,
    ACCOUNT_SCOPE_STAFF,
    ACCOUNT_SCOPES,
    ADMIN_ACCESS_ROLES,
    DEFAULT_ACCOUNT_ROLE,
    PUBLIC_SUPPORT_ACCOUNT_ROLE_SET,
    PUBLIC_SUPPORT_ACCOUNT_ROLES,
    ROLE_ADMIN,
    ROLE_COACH,
    derive_account_scope_from_role,
    ROLE_EMPLOYER,
    ROLE_SUPERADMIN,
    ROLE_USER,
)

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
TICKET_PUBLIC_ID_PATTERN = re.compile(r"^KBC-\d{6}$", re.IGNORECASE)
ALLOWED_STATUSES = {"Open", "Pending", "Closed"}
ALLOWED_CATEGORIES = {"Learning", "Technical", "Others"}
ALLOWED_TECHNICAL_SUBCATEGORIES = {"Aptem", "LMS", "Teams"}
ALLOWED_SLA_STATUSES = {"Pending Review", "On Track", "Breached"}
ALLOWED_TICKET_PRIORITIES = {"Low", "Normal", "High", "Urgent"}
DEFAULT_TICKET_PRIORITY = "Normal"
EMPLOYER_TICKET_PRIORITY = "High"
COACH_TICKET_PRIORITY = "High"
TICKET_PRIORITY_RANKS = {
    "Urgent": 0,
    "High": 1,
    "Normal": 2,
    "Low": 3,
}
ACTIVE_PRIORITY_TICKET_STATUSES = {"Open", "Pending"}
STATUS_REASON_CLOSED_DUE_TO_INACTIVITY = "Closed due to inactivity"
STATUS_REASON_CLOSING_BY_CHATBOT = "Closed via Chatbot"
STATUS_REASON_CLOSED_BY_AGENT = "Closed via Agent"
STATUS_REASON_AWAITING_MEETING = "Awaiting support meeting"
STATUS_REASON_ESCALATION = "Escalation"
STATUS_REASON_QUICK_TICKET = "Quick Ticket"
LEGACY_STATUS_REASON_AWAITING_RESOLUTION = "Awaiting Resolution"
LEGACY_STATUS_REASON_AWAITING_RESOLUTION_FRONTEND = "Awaiting resolution"
STATUS_REASON_AWAITING_RESOLUTION = LEGACY_STATUS_REASON_AWAITING_RESOLUTION_FRONTEND
LEGACY_STATUS_REASON_AWAITING_SUPPORT_REVIEW = "Awaiting support review"
QUICK_TICKET_STATUS_REASONS = {
    STATUS_REASON_QUICK_TICKET,
    LEGACY_STATUS_REASON_AWAITING_RESOLUTION,
    LEGACY_STATUS_REASON_AWAITING_RESOLUTION_FRONTEND,
    LEGACY_STATUS_REASON_AWAITING_SUPPORT_REVIEW,
}
ALLOWED_CHAT_STATES = {"open", "closed"}
ALLOWED_STATUS_REASONS_BY_STATUS = {
    "Closed": {
        STATUS_REASON_CLOSED_DUE_TO_INACTIVITY,
        STATUS_REASON_CLOSING_BY_CHATBOT,
        STATUS_REASON_CLOSED_BY_AGENT,
    },
    "Pending": {
        STATUS_REASON_AWAITING_MEETING,
        STATUS_REASON_ESCALATION,
        *QUICK_TICKET_STATUS_REASONS,
    },
}
AUTO_MANAGED_SLA_STATUSES = {"Open", "Pending", "Closed"}
PENDING_SLA_BREACH_AFTER = timedelta(days=3)
SLA_ATTENTION_REASON_PENDING_OVERDUE = "pending_over_3_days"
CHAT_INACTIVITY_REMINDER_AFTER = timedelta(minutes=2)
CHAT_INACTIVITY_AUTO_CLOSE_AFTER = timedelta(minutes=3)
INACTIVITY_WAITING_SINCE_METADATA_KEY = "inactivity_waiting_since"
INACTIVITY_REMINDER_SENT_AT_METADATA_KEY = "inactivity_reminder_sent_at"
UK_SUPPORT_TIMEZONE = "Europe/London"
UK_SUPPORT_SESSION_START_MINUTES = 8 * 60
UK_SUPPORT_SESSION_END_MINUTES = 16 * 60
SUPPORT_SESSION_LEAD_TIME_SECONDS = 24 * 60 * 60
WEBHOOK_RESPONSE_WRAPPER_KEYS = ("data", "body", "result", "payload", "json", "content", "booking", "meeting", "event", "error")
AGENT_SESSION_TIMEOUT = timedelta(minutes=5)
DEFAULT_AGENT_CONSOLE_STATUS = "Off"
AGENT_CONSOLE_STATUSES = {"Available", "Busy", "Off"}
SELECTABLE_AGENT_CONSOLE_STATUSES = {"Available", "Off"}
NON_ASSIGNABLE_AGENT_CONSOLE_STATUSES = {"Off"}
PENDING_TRANSFER_REQUEST_METADATA_KEY = "pending_transfer_request"
LATEST_TRANSFER_DECISION_METADATA_KEY = "latest_transfer_decision"
PENDING_ESCALATION_NOTIFICATION_METADATA_KEY = "pending_escalation_notification"
LATEST_ESCALATION_CLOSURE_METADATA_KEY = "latest_escalation_closure"
PENDING_TEAMS_CALL_NOTIFICATION_METADATA_KEY = "pending_teams_call_notification"
TEAMS_CALL_REQUESTED_METADATA_KEY = "teams_call_requested"
LAST_QUICK_TICKET_ASSIGNED_AT_METADATA_KEY = "last_quick_ticket_assigned_at"
MICROSOFT_GRAPH_V1_BASE_URL = "https://graph.microsoft.com/v1.0"
MICROSOFT_GRAPH_BETA_BASE_URL = "https://graph.microsoft.com/beta"
MICROSOFT_GRAPH_SCOPE = "https://graph.microsoft.com/.default"
MICROSOFT_TEAMS_CALL_DEEP_LINK_URL = "https://teams.microsoft.com/l/call/0/0"
MICROSOFT_GRAPH_BOOKINGS_TIMEZONE = "GMT Standard Time"
MICROSOFT_GRAPH_TIMEZONE_ALIASES = {
    "UTC": "UTC",
    "Etc/UTC": "UTC",
    "Europe/London": "GMT Standard Time",
    "Africa/Cairo": "Egypt Standard Time",
}
MICROSOFT_GRAPH_TIMEZONE_TO_IANA = {
    "UTC": "UTC",
    "GMT Standard Time": "Europe/London",
    "Egypt Standard Time": "Africa/Cairo",
}
MICROSOFT_GRAPH_STAFF_ROLE_PRIORITY = {
    "administrator": 0,
    "guest": 1,
    "viewer": 2,
    "externalguest": 3,
}
MANAGE_ACCOUNT_ROLES = ADMIN_ACCESS_ROLES
MANAGED_PUBLIC_REQUESTER_SOURCE = "support_portal_requester"


@dataclass
class ApiError(Exception):
    status_code: int
    message: str


def sanitize_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def get_default_status_reason_for_status(status: str) -> str:
    normalized_status = sanitize_text(status)

    if normalized_status == "Closed":
        return STATUS_REASON_CLOSED_BY_AGENT
    if normalized_status == "Pending":
        return STATUS_REASON_AWAITING_RESOLUTION
    return ""


def parse_iso_datetime(value: Any) -> datetime | None:
    normalized_value = sanitize_text(value)
    if not normalized_value:
        return None

    try:
        parsed_value = datetime.fromisoformat(normalized_value.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed_value.tzinfo is None:
        return parsed_value.replace(tzinfo=timezone.utc)
    return parsed_value


def serialize_datetime_value(value: datetime | None) -> str | None:
    if not isinstance(value, datetime):
        return None

    normalized_value = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return normalized_value.astimezone(timezone.utc).isoformat()


def coerce_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return parse_iso_datetime(value)


def normalize_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)

    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    return {}


def normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


def normalize_pending_transfer_request(value: Any) -> dict[str, Any] | None:
    payload = normalize_json_object(value)
    if not payload:
        return None

    from_agent_id = parse_assigned_agent_id(payload.get("fromAgentId"))
    to_agent_id = parse_assigned_agent_id(payload.get("toAgentId"))
    from_agent_name = sanitize_text(payload.get("fromAgentName"))
    from_agent_username = sanitize_text(payload.get("fromAgentUsername"))
    to_agent_name = sanitize_text(payload.get("toAgentName"))
    to_agent_username = sanitize_text(payload.get("toAgentUsername"))
    reason = sanitize_text(payload.get("reason"))
    requested_at = serialize_datetime_value(coerce_datetime(payload.get("requestedAt")))

    if (
        not from_agent_id
        or not to_agent_id
        or not from_agent_name
        or not from_agent_username
        or not to_agent_name
        or not to_agent_username
        or not reason
        or not requested_at
    ):
        return None

    return {
        "fromAgentId": from_agent_id,
        "fromAgentName": from_agent_name,
        "fromAgentUsername": from_agent_username,
        "toAgentId": to_agent_id,
        "toAgentName": to_agent_name,
        "toAgentUsername": to_agent_username,
        "reason": reason,
        "requestedAt": requested_at,
    }


def get_pending_transfer_request(metadata: Any) -> dict[str, Any] | None:
    return normalize_pending_transfer_request(normalize_json_object(metadata).get(PENDING_TRANSFER_REQUEST_METADATA_KEY))


def normalize_pending_escalation_notification(value: Any) -> dict[str, Any] | None:
    payload = normalize_json_object(value)
    if not payload:
        return None

    from_agent_id = parse_assigned_agent_id(payload.get("fromAgentId"))
    to_agent_id = parse_assigned_agent_id(payload.get("toAgentId"))
    from_agent_name = sanitize_text(payload.get("fromAgentName"))
    from_agent_username = sanitize_text(payload.get("fromAgentUsername"))
    to_agent_name = sanitize_text(payload.get("toAgentName"))
    to_agent_username = sanitize_text(payload.get("toAgentUsername"))
    note = sanitize_text(payload.get("note"))
    ticket_id = sanitize_text(payload.get("ticketId")) or sanitize_text(payload.get("chatId"))
    requested_at = serialize_datetime_value(coerce_datetime(payload.get("requestedAt")))

    if (
        not from_agent_id
        or not to_agent_id
        or not from_agent_name
        or not from_agent_username
        or not to_agent_name
        or not to_agent_username
        or not note
        or not ticket_id
        or not requested_at
    ):
        return None

    return {
        "fromAgentId": from_agent_id,
        "fromAgentName": from_agent_name,
        "fromAgentUsername": from_agent_username,
        "toAgentId": to_agent_id,
        "toAgentName": to_agent_name,
        "toAgentUsername": to_agent_username,
        "note": note,
        "ticketId": ticket_id,
        "requestedAt": requested_at,
    }


def get_pending_escalation_notification(metadata: Any) -> dict[str, Any] | None:
    return normalize_pending_escalation_notification(normalize_json_object(metadata).get(PENDING_ESCALATION_NOTIFICATION_METADATA_KEY))


def normalize_pending_teams_call_notification(value: Any) -> dict[str, Any] | None:
    payload = normalize_json_object(value)
    if not payload:
        return None

    to_agent_id = parse_assigned_agent_id(payload.get("toAgentId"))
    to_agent_name = sanitize_text(payload.get("toAgentName"))
    to_agent_username = sanitize_text(payload.get("toAgentUsername"))
    requester_name = sanitize_text(payload.get("requesterName"))
    requester_email = sanitize_text(payload.get("requesterEmail"))
    requester_role = normalize_public_requester_role(payload.get("requesterRole"))
    note = sanitize_text(payload.get("note"))
    target_label = sanitize_text(payload.get("targetLabel"))
    ticket_id = sanitize_text(payload.get("ticketId")) or sanitize_text(payload.get("chatId"))
    requested_at = serialize_datetime_value(coerce_datetime(payload.get("requestedAt")))

    if (
        not to_agent_id
        or not to_agent_name
        or not to_agent_username
        or not requester_name
        or not requester_email
        or not note
        or not ticket_id
        or not requested_at
    ):
        return None

    return {
        "toAgentId": to_agent_id,
        "toAgentName": to_agent_name,
        "toAgentUsername": to_agent_username,
        "requesterName": requester_name,
        "requesterEmail": requester_email,
        "requesterRole": requester_role,
        "note": note,
        "targetLabel": target_label,
        "ticketId": ticket_id,
        "requestedAt": requested_at,
    }


def get_pending_teams_call_notification(metadata: Any) -> dict[str, Any] | None:
    return normalize_pending_teams_call_notification(normalize_json_object(metadata).get(PENDING_TEAMS_CALL_NOTIFICATION_METADATA_KEY))


def is_teams_call_requested(metadata: Any) -> bool:
    return normalize_bool(normalize_json_object(metadata).get(TEAMS_CALL_REQUESTED_METADATA_KEY))


def normalize_latest_escalation_closure(value: Any) -> dict[str, Any] | None:
    payload = normalize_json_object(value)
    if not payload:
        return None

    from_agent_id = parse_assigned_agent_id(payload.get("fromAgentId"))
    to_agent_id = parse_assigned_agent_id(payload.get("toAgentId"))
    closed_by_id = parse_assigned_agent_id(payload.get("closedById"))
    from_agent_name = sanitize_text(payload.get("fromAgentName"))
    from_agent_username = sanitize_text(payload.get("fromAgentUsername"))
    to_agent_name = sanitize_text(payload.get("toAgentName"))
    to_agent_username = sanitize_text(payload.get("toAgentUsername"))
    closed_by_name = sanitize_text(payload.get("closedByName"))
    closed_by_username = sanitize_text(payload.get("closedByUsername"))
    note = sanitize_text(payload.get("note"))
    ticket_id = sanitize_text(payload.get("ticketId")) or sanitize_text(payload.get("chatId"))
    requested_at = serialize_datetime_value(coerce_datetime(payload.get("requestedAt")))
    closed_at = serialize_datetime_value(coerce_datetime(payload.get("closedAt")))
    closed_status_reason = sanitize_text(payload.get("closedStatusReason"))
    requester_acknowledged = normalize_bool(payload.get("requesterAcknowledged"))

    if (
        not from_agent_id
        or not to_agent_id
        or not closed_by_id
        or not from_agent_name
        or not from_agent_username
        or not to_agent_name
        or not to_agent_username
        or not closed_by_name
        or not closed_by_username
        or not note
        or not ticket_id
        or not requested_at
        or not closed_at
    ):
        return None

    return {
        "fromAgentId": from_agent_id,
        "fromAgentName": from_agent_name,
        "fromAgentUsername": from_agent_username,
        "toAgentId": to_agent_id,
        "toAgentName": to_agent_name,
        "toAgentUsername": to_agent_username,
        "closedById": closed_by_id,
        "closedByName": closed_by_name,
        "closedByUsername": closed_by_username,
        "note": note,
        "ticketId": ticket_id,
        "requestedAt": requested_at,
        "closedAt": closed_at,
        "closedStatusReason": closed_status_reason,
        "requesterAcknowledged": requester_acknowledged,
    }


def get_latest_escalation_closure(metadata: Any) -> dict[str, Any] | None:
    return normalize_latest_escalation_closure(normalize_json_object(metadata).get(LATEST_ESCALATION_CLOSURE_METADATA_KEY))


def normalize_latest_transfer_decision(value: Any) -> dict[str, Any] | None:
    payload = normalize_json_object(value)
    if not payload:
        return None

    status = sanitize_text(payload.get("status")).lower()
    from_agent_id = parse_assigned_agent_id(payload.get("fromAgentId"))
    to_agent_id = parse_assigned_agent_id(payload.get("toAgentId"))
    decided_by_id = parse_assigned_agent_id(payload.get("decidedById"))
    from_agent_name = sanitize_text(payload.get("fromAgentName"))
    from_agent_username = sanitize_text(payload.get("fromAgentUsername"))
    to_agent_name = sanitize_text(payload.get("toAgentName"))
    to_agent_username = sanitize_text(payload.get("toAgentUsername"))
    reason = sanitize_text(payload.get("reason"))
    requested_at = serialize_datetime_value(coerce_datetime(payload.get("requestedAt")))
    decided_at = serialize_datetime_value(coerce_datetime(payload.get("decidedAt")))
    decided_by_name = sanitize_text(payload.get("decidedByName"))
    decided_by_username = sanitize_text(payload.get("decidedByUsername"))
    requester_acknowledged = normalize_bool(payload.get("requesterAcknowledged"))

    if (
        status not in {"accepted", "rejected"}
        or not from_agent_id
        or not to_agent_id
        or not decided_by_id
        or not from_agent_name
        or not from_agent_username
        or not to_agent_name
        or not to_agent_username
        or not reason
        or not requested_at
        or not decided_at
        or not decided_by_name
        or not decided_by_username
    ):
        return None

    return {
        "status": status,
        "fromAgentId": from_agent_id,
        "fromAgentName": from_agent_name,
        "fromAgentUsername": from_agent_username,
        "toAgentId": to_agent_id,
        "toAgentName": to_agent_name,
        "toAgentUsername": to_agent_username,
        "reason": reason,
        "requestedAt": requested_at,
        "decidedAt": decided_at,
        "decidedById": decided_by_id,
        "decidedByName": decided_by_name,
        "decidedByUsername": decided_by_username,
        "requesterAcknowledged": requester_acknowledged,
    }


def get_latest_transfer_decision(metadata: Any) -> dict[str, Any] | None:
    return normalize_latest_transfer_decision(normalize_json_object(metadata).get(LATEST_TRANSFER_DECISION_METADATA_KEY))


def normalize_console_status(value: Any) -> str:
    normalized_value = sanitize_text(value).title()
    if normalized_value in AGENT_CONSOLE_STATUSES:
        return normalized_value
    return DEFAULT_AGENT_CONSOLE_STATUS


def normalize_selectable_console_status(value: Any) -> str:
    normalized_value = normalize_console_status(value)
    if normalized_value in SELECTABLE_AGENT_CONSOLE_STATUSES:
        return normalized_value
    if normalized_value == "Busy":
        return "Available"
    return DEFAULT_AGENT_CONSOLE_STATUS


def resolve_agent_console_status(
    metadata: Any,
    *,
    session_active: bool | None = None,
    has_open_assigned_chat: bool = False,
) -> str:
    normalized_metadata = normalize_json_object(metadata)
    is_session_active = is_agent_session_active(normalized_metadata) if session_active is None else session_active
    if not is_session_active:
        return "Off"
    if has_open_assigned_chat:
        return "Busy"
    return normalize_selectable_console_status(normalized_metadata.get("console_status"))


def get_agent_password_hash(metadata: Any) -> str:
    normalized_metadata = normalize_json_object(metadata)
    return sanitize_text(normalized_metadata.get("password_hash"))


def verify_agent_password(agent: dict[str, Any] | None, password: str) -> bool:
    if not agent or not password:
        return False

    password_hash = get_agent_password_hash(agent.get("metadata"))
    if password_hash:
        return check_password(password, password_hash)

    shared_password = settings.SUPPORT_PORTAL_PASSWORD or ""
    return bool(shared_password) and password == shared_password


def normalize_account_role(value: Any, *, default: str = DEFAULT_ACCOUNT_ROLE) -> str:
    normalized_value = sanitize_text(value).lower()
    if not normalized_value:
        return default
    if normalized_value not in ACCOUNT_ROLES:
        raise ApiError(400, "Select a valid role.")
    return normalized_value


def normalize_account_scope(value: Any, *, fallback_role: Any = None, default: str = ACCOUNT_SCOPE_STAFF) -> str:
    normalized_value = sanitize_text(value).lower()
    if normalized_value in ACCOUNT_SCOPES:
        return normalized_value

    derived_scope = derive_account_scope_from_role(sanitize_text(fallback_role).lower())
    if derived_scope in ACCOUNT_SCOPES:
        return derived_scope
    return default


def normalize_public_requester_role(value: Any, *, default: str = ROLE_USER) -> str:
    normalized_value = sanitize_text(value).lower()
    if normalized_value in PUBLIC_SUPPORT_ACCOUNT_ROLE_SET:
        return normalized_value
    return default


def normalize_ticket_priority(value: Any, *, default: str = DEFAULT_TICKET_PRIORITY) -> str:
    normalized_value = sanitize_text(value).title()
    if normalized_value in ALLOWED_TICKET_PRIORITIES:
        return normalized_value
    return default


def get_ticket_priority_rank(value: Any) -> int:
    return TICKET_PRIORITY_RANKS.get(normalize_ticket_priority(value), TICKET_PRIORITY_RANKS[DEFAULT_TICKET_PRIORITY])


def derive_requester_ticket_priority(requester_role: Any, current_priority: Any = None) -> str:
    normalized_priority = normalize_ticket_priority(current_priority)
    normalized_role = normalize_public_requester_role(requester_role)

    if normalized_role == ROLE_EMPLOYER and get_ticket_priority_rank(normalized_priority) > get_ticket_priority_rank(EMPLOYER_TICKET_PRIORITY):
        return EMPLOYER_TICKET_PRIORITY
    if normalized_role == ROLE_COACH and get_ticket_priority_rank(normalized_priority) > get_ticket_priority_rank(COACH_TICKET_PRIORITY):
        return COACH_TICKET_PRIORITY

    return normalized_priority


def get_ticket_sort_timestamp(value: Any) -> float:
    normalized_value = coerce_datetime(value)
    if not normalized_value:
        return 0.0
    return normalized_value.timestamp()


def is_priority_sorted_ticket_status(value: Any) -> bool:
    return sanitize_text(value) in ACTIVE_PRIORITY_TICKET_STATUSES


def sort_tickets_by_priority_and_recency(tickets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        tickets,
        key=lambda ticket: (
            0 if is_priority_sorted_ticket_status(ticket.get("status")) else 1,
            get_ticket_priority_rank(ticket.get("priority")) if is_priority_sorted_ticket_status(ticket.get("status")) else TICKET_PRIORITY_RANKS[DEFAULT_TICKET_PRIORITY],
            -get_ticket_sort_timestamp(
                ticket.get("created_at")
                if is_priority_sorted_ticket_status(ticket.get("status"))
                else (ticket.get("closed_at") or ticket.get("updated_at") or ticket.get("created_at"))
            ),
            -(int(ticket.get("id") or 0)),
        ),
    )


def normalize_account_email(value: Any) -> str | None:
    normalized_value = sanitize_text(value).lower()
    if not normalized_value:
        return None
    if not EMAIL_PATTERN.match(normalized_value):
        raise ApiError(400, "Please enter a valid email address.")
    return normalized_value


def is_active_conversation(value: Any) -> bool:
    metadata = normalize_json_object(value)
    return normalize_bool(metadata.get("is_active_conversation"))


def is_latest_ticket_for_conversation(ticket_public_id: Any, conversation_metadata: Any) -> bool:
    normalized_ticket_public_id = sanitize_text(ticket_public_id)
    metadata = normalize_json_object(conversation_metadata)
    latest_ticket_public_id = sanitize_text(metadata.get("latest_ticket_public_id"))
    return not latest_ticket_public_id or latest_ticket_public_id == normalized_ticket_public_id


def is_live_chat_requested(ticket_metadata: Any, conversation_metadata: Any = None) -> bool:
    normalized_ticket_metadata = normalize_json_object(ticket_metadata)
    normalized_conversation_metadata = normalize_json_object(conversation_metadata)
    return (
        normalize_bool(normalized_conversation_metadata.get("live_chat_requested"))
        or normalize_bool(normalized_ticket_metadata.get("live_chat_requested"))
    )


def normalize_admin_documentation(
    value: Any,
    *,
    fallback_inquiry: str = "",
    fallback_chat_id: str = "",
    fallback_ticket_id: str = "",
) -> dict[str, Any]:
    source = normalize_json_object(value)
    raw_images = source.get("errorImages") if isinstance(source.get("errorImages"), list) else []
    error_images = []

    for item in raw_images:
        if not isinstance(item, dict):
            continue

        data_url = sanitize_text(item.get("dataUrl"))
        mime_type = sanitize_text(item.get("mimeType")) or "image/png"
        if not data_url.startswith("data:image/"):
            continue

        error_images.append(
            {
                "name": sanitize_text(item.get("name")) or "image",
                "mimeType": mime_type,
                "size": int(item.get("size") or 0),
                "dataUrl": data_url,
            }
        )

    normalized_chat_id = sanitize_text(source.get("chatId"))
    if fallback_chat_id and TICKET_PUBLIC_ID_PATTERN.fullmatch(normalized_chat_id):
        normalized_chat_id = fallback_chat_id

    return {
        "inquiry": sanitize_text(source.get("inquiry")) or fallback_inquiry,
        "symptoms": sanitize_text(source.get("symptoms")),
        "errors": sanitize_text(source.get("errors")),
        "steps": sanitize_text(source.get("steps")),
        "resources": sanitize_text(source.get("resources")),
        "chatId": normalized_chat_id or fallback_chat_id,
        "ticketId": sanitize_text(source.get("ticketId")) or fallback_ticket_id,
        "ticketStatus": sanitize_text(source.get("ticketStatus")),
        "statusReason": sanitize_text(source.get("statusReason")),
        "issuesAddressed": sanitize_text(source.get("issuesAddressed")),
        "escalationAgentId": parse_assigned_agent_id(source.get("escalationAgentId")),
        "escalationAgentName": sanitize_text(source.get("escalationAgentName")),
        "escalationNote": sanitize_text(source.get("escalationNote")),
        "errorImages": error_images,
    }


def derive_sla_state(status: Any, created_at: Any, current_sla_status: Any) -> tuple[str, bool, str | None]:
    normalized_status = sanitize_text(status)
    fallback_sla_status = sanitize_text(current_sla_status)

    if fallback_sla_status not in ALLOWED_SLA_STATUSES:
        fallback_sla_status = "Pending Review"

    if normalized_status == "Open":
        return "Pending Review", False, None

    if normalized_status == "Closed":
        return "On Track", False, None

    if normalized_status == "Pending":
        created_datetime = created_at if isinstance(created_at, datetime) else None
        if created_datetime:
            comparison_now = datetime.now(created_datetime.tzinfo or timezone.utc)
            if (comparison_now - created_datetime) > PENDING_SLA_BREACH_AFTER:
                return "Breached", True, SLA_ATTENTION_REASON_PENDING_OVERDUE

        return "On Track", False, None

    return fallback_sla_status, False, None


def resolve_next_sla_state(
    status: Any,
    created_at: Any,
    current_sla_status: Any,
    requested_sla_status: Any = None,
) -> tuple[str, bool, str | None]:
    normalized_status = sanitize_text(status)
    normalized_requested_sla_status = sanitize_text(requested_sla_status)

    if normalized_status in AUTO_MANAGED_SLA_STATUSES:
        return derive_sla_state(normalized_status, created_at, current_sla_status)

    if normalized_requested_sla_status in ALLOWED_SLA_STATUSES:
        return normalized_requested_sla_status, False, None

    return derive_sla_state(normalized_status, created_at, current_sla_status)


def build_sla_metadata_patch(attention_required: bool, attention_reason: str | None) -> dict[str, Any]:
    return {
        "sla_attention_required": attention_required,
        "sla_attention_reason": attention_reason,
        "sla_attention_updated_at": datetime.now(timezone.utc).isoformat(),
    }


def validate_status_reason_for_status(status: str, status_reason: str) -> None:
    normalized_status = sanitize_text(status)
    normalized_status_reason = sanitize_text(status_reason)

    if not normalized_status_reason:
        return

    allowed_reasons = ALLOWED_STATUS_REASONS_BY_STATUS.get(normalized_status)
    if allowed_reasons is None:
        return

    if normalized_status_reason not in allowed_reasons:
        raise ApiError(400, f"Invalid status reason for {normalized_status.lower()} tickets.")


def is_status_reason_allowed_for_status(status: str, status_reason: str) -> bool:
    try:
        validate_status_reason_for_status(status, status_reason)
    except ApiError:
        return False

    return True


def apply_ticket_sla_policy(row: dict[str, Any], persist: bool = False) -> dict[str, Any]:
    metadata = normalize_json_object(row.get("metadata"))
    current_sla_status = sanitize_text(row.get("sla_status")) or "Pending Review"
    current_attention_required = normalize_bool(metadata.get("sla_attention_required"))
    current_attention_reason = sanitize_text(metadata.get("sla_attention_reason")) or None

    next_sla_status, attention_required, attention_reason = derive_sla_state(
        row.get("status"),
        row.get("created_at"),
        current_sla_status,
    )
    metadata_patch = build_sla_metadata_patch(attention_required, attention_reason)

    row["sla_status"] = next_sla_status
    row["sla_attention_required"] = attention_required
    row["metadata"] = {**metadata, **metadata_patch}

    if (
        persist
        and row.get("id")
        and (
            next_sla_status != current_sla_status
            or attention_required != current_attention_required
            or attention_reason != current_attention_reason
        )
    ):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE tickets
                SET sla_status = %s,
                    metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb,
                    updated_at = NOW()
                WHERE id = %s
                """,
                [next_sla_status, json.dumps(metadata_patch), row["id"]],
            )

    return row


def sync_auto_managed_ticket_sla_statuses() -> dict[str, int]:
    tickets = run_query(
        """
        SELECT id, status, sla_status, metadata, created_at
        FROM tickets
        WHERE status = ANY(%s)
        ORDER BY id ASC
        """,
        [list(AUTO_MANAGED_SLA_STATUSES)],
    )

    scanned_count = 0
    updated_count = 0
    breached_count = 0
    attention_required_count = 0

    for ticket in tickets:
        scanned_count += 1
        previous_sla_status = sanitize_text(ticket.get("sla_status")) or "Pending Review"
        previous_metadata = normalize_json_object(ticket.get("metadata"))
        previous_attention_required = normalize_bool(previous_metadata.get("sla_attention_required"))
        previous_attention_reason = sanitize_text(previous_metadata.get("sla_attention_reason")) or None

        synced_ticket = apply_ticket_sla_policy(ticket, persist=True)
        current_sla_status = sanitize_text(synced_ticket.get("sla_status")) or "Pending Review"
        current_metadata = normalize_json_object(synced_ticket.get("metadata"))
        current_attention_required = normalize_bool(current_metadata.get("sla_attention_required"))
        current_attention_reason = sanitize_text(current_metadata.get("sla_attention_reason")) or None

        if (
            current_sla_status != previous_sla_status
            or current_attention_required != previous_attention_required
            or current_attention_reason != previous_attention_reason
        ):
            updated_count += 1

        if current_sla_status == "Breached":
            breached_count += 1

        if current_attention_required:
            attention_required_count += 1

    return {
        "scanned": scanned_count,
        "updated": updated_count,
        "breached": breached_count,
        "attentionRequired": attention_required_count,
    }


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


def build_conversation_chat_id(conversation_id: Any) -> str:
    try:
        normalized_conversation_id = int(conversation_id)
    except (TypeError, ValueError):
        return ""

    return f"CHAT-{normalized_conversation_id:06d}"


def build_public_chat_id(ticket_public_id: Any = "", conversation_id: Any = None, conversation_metadata: Any = None) -> str:
    normalized_conversation_metadata = normalize_json_object(conversation_metadata)
    configured_chat_public_id = sanitize_text(normalized_conversation_metadata.get("chat_public_id"))
    if configured_chat_public_id and not TICKET_PUBLIC_ID_PATTERN.fullmatch(configured_chat_public_id):
        return configured_chat_public_id

    normalized_conversation_chat_id = build_conversation_chat_id(conversation_id)
    if normalized_conversation_chat_id:
        return normalized_conversation_chat_id

    normalized_ticket_public_id = sanitize_text(ticket_public_id)
    return configured_chat_public_id or normalized_ticket_public_id


def normalize_history_payload(payload: Any, *, ticket_public_id: Any = "", conversation_id: Any = None, conversation_metadata: Any = None) -> dict[str, Any]:
    normalized_payload = normalize_json_object(payload)
    normalized_chat_id = build_public_chat_id(ticket_public_id, conversation_id, conversation_metadata)
    raw_chat_id = sanitize_text(normalized_payload.get("chatId"))

    if normalized_chat_id and raw_chat_id and TICKET_PUBLIC_ID_PATTERN.fullmatch(raw_chat_id):
        return {
            **normalized_payload,
            "chatId": normalized_chat_id,
        }

    return normalized_payload


def parse_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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
        SELECT id, external_learner_id, support_account_id, full_name, email, phone, source, metadata
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
              support_account_id,
              full_name,
              email,
              phone,
              source,
              metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (email) DO UPDATE
            SET
              external_learner_id = COALESCE(EXCLUDED.external_learner_id, learners.external_learner_id),
              support_account_id = COALESCE(EXCLUDED.support_account_id, learners.support_account_id),
              full_name = COALESCE(EXCLUDED.full_name, learners.full_name),
              phone = COALESCE(EXCLUDED.phone, learners.phone),
              source = EXCLUDED.source,
              metadata = learners.metadata || EXCLUDED.metadata,
              updated_at = NOW()
            RETURNING id, external_learner_id, support_account_id, full_name, email, phone
            """,
            [
                learner.get("external_learner_id"),
                learner.get("support_account_id"),
                learner.get("full_name"),
                learner["email"],
                learner.get("phone"),
                source,
                json.dumps(metadata),
            ],
        )
        return dictfetchone(cursor)


def link_support_account_to_learner(*, support_account_id: int, email: str | None) -> None:
    normalized_email = normalize_account_email(email)
    if not normalized_email:
        return

    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE learners
            SET support_account_id = %s,
                updated_at = NOW()
            WHERE LOWER(TRIM(email)) = %s
            """,
            [support_account_id, normalized_email],
        )


def unlink_support_account_from_learners(*, support_account_id: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE learners
            SET support_account_id = NULL,
                updated_at = NOW()
            WHERE support_account_id = %s
            """,
            [support_account_id],
        )


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


def get_ticket_requester_role(ticket_metadata: Any, *, default: str = ROLE_USER) -> str:
    normalized_metadata = normalize_json_object(ticket_metadata)
    return normalize_public_requester_role(normalized_metadata.get("requester_role"), default=default)


def is_quick_ticket_only_requester_role(value: Any) -> bool:
    return sanitize_text(value).lower() == ROLE_COACH


def ensure_ticket_allows_chat_features(ticket_metadata: Any) -> None:
    if is_quick_ticket_only_requester_role(get_ticket_requester_role(ticket_metadata)):
        raise ApiError(403, "Coach accounts can only submit quick tickets or quick calls from the support portal.")


def serialize_requested_date(value: Any) -> str:
    if hasattr(value, "isoformat"):
        serialized_value = value.isoformat()
        return serialized_value.split("T", 1)[0]
    return sanitize_text(value)


def serialize_requested_time(value: Any) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%H:%M")
    normalized_value = sanitize_text(value)
    return normalized_value[:5] if normalized_value else ""


def get_latest_ticket_booking_summary(ticket_id: int) -> dict[str, Any] | None:
    booking_row = run_query_one(
        """
        SELECT requested_date, requested_time, status, metadata, created_at
        FROM support_session_requests
        WHERE ticket_id = %s
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        [ticket_id],
    )

    if not booking_row:
        return None

    if sanitize_text(booking_row.get("status")).lower() == "cancelled":
        return None

    metadata = normalize_json_object(booking_row.get("metadata"))
    requested_date = serialize_requested_date(booking_row.get("requested_date"))
    requested_time = serialize_requested_time(booking_row.get("requested_time"))
    reservation_confirmed = normalize_bool(metadata.get("reservation_confirmed")) or sanitize_text(booking_row.get("status")).lower() == "scheduled"
    meeting_join_url = sanitize_text(metadata.get("meeting_join_url")) or None

    if not requested_date or not requested_time:
        return None

    return {
        "requestedDate": requested_date,
        "requestedTime": requested_time,
        "reservationConfirmed": reservation_confirmed,
        "meetingJoinUrl": meeting_join_url,
    }


def find_latest_active_ticket_for_learner(learner_id: int) -> dict[str, Any] | None:
    return run_query_one(
        """
        SELECT
          t.id,
          t.public_id,
          t.category,
          t.technical_subcategory,
          t.inquiry,
          t.status,
          t.status_reason,
          t.assigned_agent_id,
          t.assigned_team,
          t.sla_status,
          t.created_at,
          t.metadata,
          c.status AS conversation_status,
          c.metadata AS conversation_metadata
        FROM tickets t
        LEFT JOIN conversations c
          ON c.id = t.conversation_id
        WHERE t.learner_id = %s
          AND t.status <> 'Closed'
          AND (
            t.status <> 'Open'
            OR LOWER(COALESCE(c.status, 'open')) <> 'closed'
          )
        ORDER BY
          CASE
            WHEN t.status = 'Pending' AND t.status_reason = %s THEN 0
            WHEN t.status = 'Open' THEN 1
            ELSE 2
          END,
          t.updated_at DESC,
          t.id DESC
        LIMIT 1
        """,
        [learner_id, STATUS_REASON_AWAITING_MEETING],
    )


def is_chat_locked_for_learner(ticket_status: Any, ticket_status_reason: Any) -> bool:
    return sanitize_text(ticket_status) == "Pending" and sanitize_text(ticket_status_reason) in {
        STATUS_REASON_AWAITING_MEETING,
        *QUICK_TICKET_STATUS_REASONS,
    }


def derive_ticket_chat_state(ticket_status: Any, conversation_status: Any) -> str:
    normalized_conversation_status = sanitize_text(conversation_status).lower()
    if normalized_conversation_status in ALLOWED_CHAT_STATES:
        return normalized_conversation_status
    return "closed" if sanitize_text(ticket_status) == "Closed" else "open"


def is_ticket_chat_closed(ticket_status: Any, conversation_status: Any) -> bool:
    return derive_ticket_chat_state(ticket_status, conversation_status) == "closed"


def ensure_open_ticket_uses_open_chat(ticket_status: Any, chat_state: Any) -> None:
    if sanitize_text(ticket_status) == "Open" and sanitize_text(chat_state).lower() == "closed":
        raise ApiError(
            409,
            "An open ticket must stay attached to an open chat. Change the ticket status before closing this chat.",
        )


def is_quick_ticket_status_reason(status_reason: Any) -> bool:
    return sanitize_text(status_reason).lower() in {
        sanitize_text(reason).lower() for reason in QUICK_TICKET_STATUS_REASONS
    }


def serialize_agent(row: dict[str, Any], *, open_assigned_chat_agent_ids: set[int] | None = None) -> dict[str, Any]:
    metadata = normalize_json_object(row.get("metadata"))
    is_active = normalize_bool(row.get("is_active")) if "is_active" in row else True
    account_scope = normalize_account_scope(row.get("account_scope"), fallback_role=row.get("role"))
    is_staff_account = account_scope == ACCOUNT_SCOPE_STAFF
    session_active = is_active and is_staff_account and is_agent_session_active(metadata)
    agent_id = int(row["id"])
    has_open_assigned_chat = agent_id in (open_assigned_chat_agent_ids or set())
    selected_console_status = normalize_selectable_console_status(metadata.get("console_status")) if session_active else "Off"
    return {
        "id": agent_id,
        "username": row["username"],
        "fullName": row.get("full_name") or row["username"],
        "email": row.get("email") or None,
        "accountScope": account_scope,
        "role": row["role"],
        "isActive": is_active,
        "sessionActive": session_active,
        "consoleStatus": resolve_agent_console_status(
            metadata,
            session_active=session_active,
            has_open_assigned_chat=has_open_assigned_chat,
        ) if is_active and is_staff_account else "Off",
        "selectedConsoleStatus": selected_console_status,
    }


def serialize_ticket_summary(row: dict[str, Any]) -> dict[str, Any]:
    ticket_metadata = normalize_json_object(row.get("metadata"))
    conversation_metadata = normalize_json_object(row.get("conversation_metadata"))
    chat_state = sanitize_text(row.get("conversation_status")).lower()
    if not chat_state:
        chat_state = "closed" if sanitize_text(row.get("status")) == "Closed" else "open"
    chat_duration_minutes = int(row.get("chat_duration_minutes") or 0)

    return {
        "id": row["public_id"],
        "learnerName": row.get("learner_name") or "",
        "email": row.get("learner_email") or "",
        "learnerPhone": row.get("learner_phone") or "",
        "requesterRole": get_ticket_requester_role(ticket_metadata),
        "priority": normalize_ticket_priority(row.get("priority")),
        "category": row["category"],
        "technicalSubcategory": row.get("technical_subcategory") or "",
        "inquiryPreview": sanitize_text(row.get("inquiry")),
        "status": row["status"],
        "statusReason": row.get("status_reason") or "",
        "assignedAgentId": int(row["assigned_agent_id"]) if row.get("assigned_agent_id") else None,
        "assignedAgentName": row.get("assigned_agent_name") or "Unassigned",
        "assignedAgentUsername": row.get("assigned_agent_username") or "",
        "assignedTeam": row.get("assigned_team") or "Unassigned",
        "chatId": build_public_chat_id(row.get("public_id"), row.get("conversation_id"), conversation_metadata),
        "chatIsActive": is_active_conversation(conversation_metadata)
        and is_latest_ticket_for_conversation(row.get("public_id"), conversation_metadata),
        "liveChatRequested": is_live_chat_requested(ticket_metadata, conversation_metadata),
        "liveChatRequestedAt": serialize_datetime_value(get_live_chat_requested_at(ticket_metadata, conversation_metadata)),
        "queueAssignedAt": serialize_datetime_value(get_queue_assigned_at(ticket_metadata, conversation_metadata)),
        "chatDurationMinutes": chat_duration_minutes,
        "chatState": chat_state,
        "lastMessageAt": row.get("last_message_at"),
        "pendingTransferRequest": get_pending_transfer_request(ticket_metadata),
        "pendingEscalationNotification": get_pending_escalation_notification(ticket_metadata),
        "pendingTeamsCallNotification": get_pending_teams_call_notification(ticket_metadata),
        "teamsCallRequested": is_teams_call_requested(ticket_metadata),
        "latestEscalationClosure": get_latest_escalation_closure(ticket_metadata),
        "latestTransferDecision": get_latest_transfer_decision(ticket_metadata),
        "documentation": normalize_admin_documentation(
            ticket_metadata.get("admin_documentation"),
            fallback_inquiry=sanitize_text(row.get("inquiry")),
            fallback_chat_id=build_public_chat_id(row.get("public_id"), row.get("conversation_id"), conversation_metadata),
            fallback_ticket_id=row.get("public_id") or "",
        ),
        "slaStatus": row["sla_status"],
        "slaAttentionRequired": bool(row.get("sla_attention_required")),
        "evidenceCount": int(row.get("evidence_count") or 0),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def serialize_ticket_detail(row: dict[str, Any]) -> dict[str, Any]:
    detail = serialize_ticket_summary(row)
    metadata = normalize_json_object(row.get("metadata"))
    detail.update(
        {
            "inquiry": row["inquiry"],
            "priority": normalize_ticket_priority(row.get("priority")),
            "closedAt": row.get("closed_at"),
            "documentation": normalize_admin_documentation(
                metadata.get("admin_documentation"),
                fallback_inquiry=sanitize_text(row.get("inquiry")),
                fallback_chat_id=build_public_chat_id(row.get("public_id"), row.get("conversation_id"), row.get("conversation_metadata")),
                fallback_ticket_id=row.get("public_id") or "",
            ),
        }
    )
    return detail


def get_ticket_issue_label(category: str, technical_subcategory: str) -> str:
    normalized_subcategory = sanitize_text(technical_subcategory)
    normalized_category = sanitize_text(category)

    if normalized_subcategory:
        return normalized_subcategory
    if normalized_category:
        return normalized_category
    return "your request"


def build_chat_intro_message(learner_name: Any, category: Any, technical_subcategory: Any) -> str:
    greeting_name = sanitize_text(learner_name) or "there"
    issue_label = get_ticket_issue_label(
        sanitize_text(category),
        sanitize_text(technical_subcategory),
    )
    return (
        f"Hello {greeting_name}, Thank you for reaching Kent College Support, "
        f"I understand you are reaching us for an issue related to {issue_label}, am I correct?"
    )


def build_chat_inactivity_reminder_message(learner_name: Any) -> str:
    greeting_name = sanitize_text(learner_name) or "there"
    return (
        f"Hi {greeting_name}, are you still connected? Please note that this chat will be "
        "automatically closed if we do not receive a reply within 3 minutes."
    )


def build_chat_inactivity_closed_message() -> str:
    return "This chat has been closed due to inactivity."


def format_chat_message_timestamp(value: Any) -> str:
    if isinstance(value, datetime):
        parsed_value = value
    else:
        try:
            parsed_value = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return ""

    if parsed_value.tzinfo is None:
        localized_value = parsed_value.replace(tzinfo=ZoneInfo(settings.TIME_ZONE))
    else:
        localized_value = parsed_value.astimezone(ZoneInfo(settings.TIME_ZONE))

    return localized_value.strftime("%I:%M %p").lstrip("0")


def ensure_intro_message_row(
    rows: list[dict[str, Any]],
    *,
    intro_message: str,
    created_at: Any,
    intro_id: str,
) -> list[dict[str, Any]]:
    normalized_intro_message = sanitize_text(intro_message)
    if not normalized_intro_message:
        return rows

    rows_without_intro = [
        row
        for row in rows
        if sanitize_text(row.get("content")) != normalized_intro_message
    ]

    return [
        {
            "id": intro_id,
            "role": "assistant",
            "content": normalized_intro_message,
            "metadata": {"original_sender": "bot"},
            "created_at": created_at,
        },
        *rows_without_intro,
    ]


def to_sender_label(role: str, metadata: Any) -> str:
    metadata_object = normalize_json_object(metadata)
    original_sender = sanitize_text(metadata_object.get("original_sender"))

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


def serialize_chat_history_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": str(row["id"]),
            "sender": map_role_to_sender(row["role"], row.get("metadata")),
            "text": row["content"],
            "timestamp": sanitize_text(normalize_json_object(row.get("metadata")).get("client_timestamp"))
            or format_chat_message_timestamp(row.get("created_at")),
        }
        for row in rows
    ]


def build_assignment_changed_chat_notice(payload: Any) -> str:
    to_agent_name = sanitize_text(normalize_json_object(payload).get("toAgentName"))
    if not to_agent_name:
        return ""

    return f"You are now talking to {to_agent_name}."


def build_chat_history_event_notice(event_type: Any, payload: Any) -> str:
    normalized_event_type = sanitize_text(event_type).lower()

    if normalized_event_type == "assignment_changed":
        return build_assignment_changed_chat_notice(payload)

    return ""


def build_chat_timeline_entries(
    message_rows: list[dict[str, Any]],
    history_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    timeline_entries: list[dict[str, Any]] = []
    assignment_notice_texts = {
        build_chat_history_event_notice(row.get("event_type"), row.get("payload"))
        for row in history_rows
        if sanitize_text(row.get("event_type")).lower() == "assignment_changed"
    }
    assignment_notice_texts.discard("")

    for row in message_rows:
        message_metadata = normalize_json_object(row.get("metadata"))
        is_bot_message = (
            sanitize_text(row.get("role")).lower() == "assistant"
            and sanitize_text(message_metadata.get("original_sender")).lower() == "bot"
        )
        if is_bot_message and sanitize_text(row.get("content")) in assignment_notice_texts:
            continue

        timeline_entries.append(
            {
                "id": str(row["id"]),
                "role": row["role"],
                "metadata": message_metadata,
                "source": "intro" if str(row.get("id", "")).startswith("intro-") else "message",
                "text": row["content"],
                "timestamp": sanitize_text(message_metadata.get("client_timestamp"))
                or format_chat_message_timestamp(row.get("created_at")),
                "created_at": row.get("created_at"),
                "sort_priority": 0,
            }
        )

    for row in history_rows:
        notice_text = build_chat_history_event_notice(row.get("event_type"), row.get("payload"))
        if not notice_text:
            continue

        timeline_entries.append(
            {
                "id": f"history-{row['id']}",
                "role": "assistant",
                "metadata": {"original_sender": "bot", "source_event": sanitize_text(row.get("event_type")).lower()},
                "source": "history_event",
                "text": notice_text,
                "timestamp": format_chat_message_timestamp(row.get("created_at")),
                "created_at": row.get("created_at"),
                "sort_priority": 1,
            }
        )

    timeline_entries.sort(
        key=lambda entry: (
            entry.get("created_at") or datetime.min.replace(tzinfo=timezone.utc),
            entry.get("sort_priority", 0),
            entry["id"],
        )
    )

    deduped_entries: list[dict[str, Any]] = []
    for entry in timeline_entries:
        if deduped_entries:
            previous_entry = deduped_entries[-1]
            previous_is_bot_notice = (
                sanitize_text(previous_entry.get("role")).lower() == "assistant"
                and sanitize_text(normalize_json_object(previous_entry.get("metadata")).get("original_sender")).lower() == "bot"
            )
            current_is_bot_notice = (
                sanitize_text(entry.get("role")).lower() == "assistant"
                and sanitize_text(normalize_json_object(entry.get("metadata")).get("original_sender")).lower() == "bot"
            )
            if previous_is_bot_notice and current_is_bot_notice and sanitize_text(previous_entry.get("text")) == sanitize_text(entry.get("text")):
                continue

        deduped_entries.append(entry)

    return deduped_entries


def serialize_chat_timeline_rows(
    message_rows: list[dict[str, Any]],
    history_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    timeline_entries = build_chat_timeline_entries(message_rows, history_rows)

    return [
        {
            "id": entry["id"],
            "sender": map_role_to_sender(entry["role"], entry.get("metadata")),
            "source": entry.get("source") or "message",
            "text": entry["text"],
            "timestamp": entry["timestamp"],
        }
        for entry in timeline_entries
    ]


def serialize_admin_chat_timeline_rows(
    message_rows: list[dict[str, Any]],
    history_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    timeline_entries = build_chat_timeline_entries(message_rows, history_rows)

    return [
        {
            "id": int(entry["id"]) if isinstance(entry.get("id"), int) else str(entry.get("id")),
            "role": entry["role"],
            "source": entry.get("source") or "message",
            "senderLabel": to_sender_label(entry["role"], entry.get("metadata")),
            "text": entry["text"],
            "createdAt": entry["created_at"],
        }
        for entry in timeline_entries
    ]


def get_inactivity_waiting_since(metadata: Any) -> datetime | None:
    return parse_iso_datetime(normalize_json_object(metadata).get(INACTIVITY_WAITING_SINCE_METADATA_KEY))


def get_inactivity_reminder_sent_at(metadata: Any) -> datetime | None:
    return parse_iso_datetime(normalize_json_object(metadata).get(INACTIVITY_REMINDER_SENT_AT_METADATA_KEY))


def build_inactivity_metadata_patch_for_messages(
    status: str,
    filtered_messages: list[dict[str, Any]],
    *,
    reference_time: datetime,
) -> dict[str, Any]:
    if sanitize_text(status) != "Open":
        return {
            INACTIVITY_WAITING_SINCE_METADATA_KEY: None,
            INACTIVITY_REMINDER_SENT_AT_METADATA_KEY: None,
        }

    if not filtered_messages:
        return {
            INACTIVITY_WAITING_SINCE_METADATA_KEY: None,
            INACTIVITY_REMINDER_SENT_AT_METADATA_KEY: None,
        }

    last_message = filtered_messages[-1]
    last_sender = map_role_to_sender(last_message.get("role"), last_message.get("metadata"))
    if last_sender == "user":
        return {
            INACTIVITY_WAITING_SINCE_METADATA_KEY: None,
            INACTIVITY_REMINDER_SENT_AT_METADATA_KEY: None,
        }

    return {
        INACTIVITY_WAITING_SINCE_METADATA_KEY: serialize_datetime_value(reference_time),
        INACTIVITY_REMINDER_SENT_AT_METADATA_KEY: None,
    }


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


def is_support_session_time_aligned(requested_datetime: datetime) -> bool:
    slot_interval = max(int(settings.SUPPORT_SESSION_SLOT_INTERVAL_MINUTES or 30), 1)
    localized_datetime = requested_datetime.astimezone(ZoneInfo(settings.TIME_ZONE))
    total_minutes = (localized_datetime.hour * 60) + localized_datetime.minute
    return total_minutes % slot_interval == 0


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

    if not is_support_session_time_aligned(requested_datetime):
        return f"Support sessions must start on {settings.SUPPORT_SESSION_SLOT_INTERVAL_MINUTES}-minute intervals."

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
        "ticketStatusReason": ticket.get("status_reason"),
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
            "statusReason": ticket.get("status_reason"),
            "priority": ticket["priority"],
            "assignedTeam": ticket["assigned_team"],
        },
    }


def is_direct_microsoft_booking_configured() -> bool:
    return all(
        sanitize_text(value)
        for value in (
            settings.AZURE_TENANT_ID,
            settings.AZURE_CLIENT_ID,
            settings.AZURE_CLIENT_SECRET,
            settings.BOOKING_BUSINESS_ID,
            settings.BOOKING_SERVICE_ID,
        )
    )


def parse_iso8601_duration_minutes(value: Any) -> int | None:
    normalized_value = sanitize_text(value).upper()
    if not normalized_value.startswith("P"):
        return None

    pattern = re.compile(
        r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
    )
    match = pattern.match(normalized_value)
    if not match:
        return None

    days = int(match.group("days") or 0)
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)
    total_minutes = (days * 24 * 60) + (hours * 60) + minutes + (1 if seconds else 0)
    return total_minutes if total_minutes > 0 else None


def get_direct_booking_duration_minutes(service_payload: Any = None) -> int:
    if isinstance(service_payload, dict):
        service_duration = parse_iso8601_duration_minutes(service_payload.get("defaultDuration"))
        if service_duration:
            return service_duration

    return settings.SUPPORT_SESSION_DURATION_MINUTES


def to_microsoft_graph_timezone(value: str, default: str = MICROSOFT_GRAPH_BOOKINGS_TIMEZONE) -> str:
    normalized_value = sanitize_text(value)
    if not normalized_value:
        return default
    if normalized_value in MICROSOFT_GRAPH_TIMEZONE_TO_IANA:
        return normalized_value
    return MICROSOFT_GRAPH_TIMEZONE_ALIASES.get(normalized_value, default)


def resolve_microsoft_graph_zoneinfo(timezone_name: str) -> ZoneInfo:
    iana_timezone_name = MICROSOFT_GRAPH_TIMEZONE_TO_IANA.get(timezone_name, UK_SUPPORT_TIMEZONE)
    return ZoneInfo(iana_timezone_name)


def build_microsoft_graph_date_time_time_zone(value: datetime, timezone_name: str) -> dict[str, str]:
    localized_value = value.astimezone(resolve_microsoft_graph_zoneinfo(timezone_name))
    return {
        "@odata.type": "#microsoft.graph.dateTimeTimeZone",
        "dateTime": localized_value.strftime("%Y-%m-%dT%H:%M:%S"),
        "timeZone": timezone_name,
    }


def get_microsoft_booking_staff_member_details(access_token: str, staff_id: str) -> tuple[bool, bool, int | None, Any]:
    business_id = urllib_parse.quote(sanitize_text(settings.BOOKING_BUSINESS_ID), safe="")
    encoded_staff_id = urllib_parse.quote(sanitize_text(staff_id), safe="")
    staff_url = f"{MICROSOFT_GRAPH_V1_BASE_URL}/solutions/bookingBusinesses/{business_id}/staffMembers/{encoded_staff_id}"
    request = urllib_request.Request(
        staff_url,
        headers={"Authorization": f"Bearer {access_token}"},
        method="GET",
    )
    return execute_http_request(request)


def get_microsoft_booking_staff_availability(
    access_token: str,
    staff_ids: list[str],
    requested_datetime: datetime,
    duration_minutes: int,
) -> tuple[bool, bool, int | None, Any]:
    business_id = urllib_parse.quote(sanitize_text(settings.BOOKING_BUSINESS_ID), safe="")
    availability_url = f"{MICROSOFT_GRAPH_V1_BASE_URL}/solutions/bookingBusinesses/{business_id}/getStaffAvailability"
    booking_end = requested_datetime + timedelta(minutes=duration_minutes)
    payload = {
        "staffIds": staff_ids,
        "startDateTime": build_microsoft_graph_date_time_time_zone(requested_datetime, MICROSOFT_GRAPH_BOOKINGS_TIMEZONE),
        "endDateTime": build_microsoft_graph_date_time_time_zone(booking_end, MICROSOFT_GRAPH_BOOKINGS_TIMEZONE),
    }
    return post_json_request(
        availability_url,
        payload,
        headers={"Authorization": f"Bearer {access_token}"},
    )


def parse_microsoft_graph_local_datetime(value: Any) -> datetime | None:
    normalized_value = sanitize_text(value)
    if not normalized_value:
        return None

    try:
        return datetime.fromisoformat(normalized_value.replace("Z", ""))
    except ValueError:
        return None


def availability_window_covers_slot(availability_item: Any, slot_start: datetime, slot_end: datetime) -> bool:
    if not isinstance(availability_item, dict):
        return False
    if sanitize_text(availability_item.get("status")).lower() != "available":
        return False

    start_object = availability_item.get("startDateTime") if isinstance(availability_item.get("startDateTime"), dict) else {}
    end_object = availability_item.get("endDateTime") if isinstance(availability_item.get("endDateTime"), dict) else {}
    availability_start = parse_microsoft_graph_local_datetime(start_object.get("dateTime"))
    availability_end = parse_microsoft_graph_local_datetime(end_object.get("dateTime"))

    return bool(availability_start and availability_end and availability_start <= slot_start and availability_end >= slot_end)


def select_microsoft_booking_staff_member_ids(
    access_token: str,
    service_payload: Any,
    requested_datetime: datetime,
    duration_minutes: int,
) -> list[str]:
    staff_ids = [sanitize_text(staff_id) for staff_id in (service_payload.get("staffMemberIds") or []) if sanitize_text(staff_id)]
    if not staff_ids:
        return []

    candidate_staff_ids = list(staff_ids)
    _, availability_delivered, _, availability_payload = get_microsoft_booking_staff_availability(
        access_token,
        staff_ids,
        requested_datetime,
        duration_minutes,
    )
    if availability_delivered and isinstance(availability_payload, dict):
        slot_start = build_microsoft_graph_date_time_time_zone(requested_datetime, MICROSOFT_GRAPH_BOOKINGS_TIMEZONE)["dateTime"]
        slot_end = build_microsoft_graph_date_time_time_zone(
            requested_datetime + timedelta(minutes=duration_minutes),
            MICROSOFT_GRAPH_BOOKINGS_TIMEZONE,
        )["dateTime"]
        requested_slot_start = parse_microsoft_graph_local_datetime(slot_start)
        requested_slot_end = parse_microsoft_graph_local_datetime(slot_end)
        available_staff_ids = [
            sanitize_text(staff_item.get("staffId"))
            for staff_item in (availability_payload.get("value") or [])
            if isinstance(staff_item, dict)
            and requested_slot_start
            and requested_slot_end
            and any(
                availability_window_covers_slot(availability_item, requested_slot_start, requested_slot_end)
                for availability_item in (staff_item.get("availabilityItems") or [])
            )
        ]
        if available_staff_ids:
            candidate_staff_ids = available_staff_ids

    ranked_candidates: list[tuple[tuple[int, int, int], str]] = []
    for index, staff_id in enumerate(candidate_staff_ids):
        _, delivered, _, staff_payload = get_microsoft_booking_staff_member_details(access_token, staff_id)
        staff_role = sanitize_text(staff_payload.get("role")).lower() if delivered and isinstance(staff_payload, dict) else ""
        membership_status = sanitize_text(staff_payload.get("membershipStatus")).lower() if delivered and isinstance(staff_payload, dict) else ""
        role_priority = MICROSOFT_GRAPH_STAFF_ROLE_PRIORITY.get(staff_role, 10)
        membership_priority = 0 if membership_status == "active" else 1
        ranked_candidates.append(((membership_priority, role_priority, index), staff_id))

    ranked_candidates.sort(key=lambda item: item[0])
    return [ranked_candidates[0][1]] if ranked_candidates else candidate_staff_ids[:1]


def build_microsoft_booking_appointment_payload(
    ticket: dict[str, Any],
    requested_datetime: datetime,
    client_time_zone: str,
    *,
    duration_minutes: int,
    service_payload: Any,
    staff_member_ids: list[str],
) -> dict[str, Any]:
    request_end = requested_datetime + timedelta(minutes=duration_minutes)
    customer_name = sanitize_text(ticket.get("learner_full_name")) or ticket["learner_email"]
    customer_phone = sanitize_text(ticket.get("learner_phone"))
    customer_time_zone = to_microsoft_graph_timezone(client_time_zone)
    service_name = sanitize_text(service_payload.get("displayName")) or sanitize_text(settings.BOOKING_SERVICE_ID)
    maximum_attendees_count = max(int(service_payload.get("maximumAttendeesCount") or 1), 1)

    payload = {
        "@odata.type": "#microsoft.graph.bookingAppointment",
        "customerTimeZone": customer_time_zone,
        "customerName": customer_name,
        "customerEmailAddress": ticket["learner_email"],
        "isCustomerAllowedToManageBooking": normalize_bool(service_payload.get("isCustomerAllowedToManageBooking")),
        "isLocationOnline": normalize_bool(service_payload.get("isLocationOnline")),
        "optOutOfCustomerEmail": False,
        "smsNotificationsEnabled": normalize_bool(service_payload.get("smsNotificationsEnabled")),
        "serviceId": settings.BOOKING_SERVICE_ID,
        "serviceName": service_name,
        "staffMemberIds": staff_member_ids,
        "maximumAttendeesCount": maximum_attendees_count,
        "filledAttendeesCount": 1,
        "start": build_microsoft_graph_date_time_time_zone(requested_datetime, MICROSOFT_GRAPH_BOOKINGS_TIMEZONE),
        "end": build_microsoft_graph_date_time_time_zone(request_end, MICROSOFT_GRAPH_BOOKINGS_TIMEZONE),
    }

    if customer_phone:
        payload["customerPhone"] = customer_phone

    return payload


def extract_external_service_message(response_payload: Any) -> str:
    return extract_webhook_string(
        response_payload,
        ("message", "error_description", "detail", "reason"),
    ) or extract_chatbot_reply(response_payload)


def get_microsoft_booking_service_details(access_token: str) -> tuple[bool, bool, int | None, Any]:
    business_id = urllib_parse.quote(sanitize_text(settings.BOOKING_BUSINESS_ID), safe="")
    service_id = urllib_parse.quote(sanitize_text(settings.BOOKING_SERVICE_ID), safe="")
    service_url = f"{MICROSOFT_GRAPH_V1_BASE_URL}/solutions/bookingBusinesses/{business_id}/services/{service_id}"
    request = urllib_request.Request(
        service_url,
        headers={"Authorization": f"Bearer {access_token}"},
        method="GET",
    )
    return execute_http_request(request)


def should_retry_with_microsoft_graph_beta(status: int | None, response_payload: Any) -> bool:
    if status != 500 or not isinstance(response_payload, dict):
        return False

    error_payload = response_payload.get("error") if isinstance(response_payload.get("error"), dict) else {}
    error_code = sanitize_text(error_payload.get("code"))
    error_message = sanitize_text(error_payload.get("message"))
    return error_code == "UnknownError" and not error_message


def extract_booking_webhook_result(response_payload: Any, delivered: bool, status: int | None) -> dict[str, Any]:
    meeting_join_url = extract_webhook_string(
        response_payload,
        ("joinUrl", "joinWebUrl", "meetingJoinUrl", "teamsJoinUrl", "meeting_url", "teams_meeting_url", "webUrl"),
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

    normalized_message = message.lower()
    slot_unavailable = (
        conflict_flag is True
        or available_flag is False
        or status == 409
        or any(
            phrase in normalized_message
            for phrase in (
                "already booked",
                "no longer available",
                "not available",
                "slot unavailable",
                "busy",
                "conflict",
            )
        )
    )
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


def sync_conversation_messages(
    conversation_id: int,
    status: str,
    messages: list[dict[str, Any]],
    *,
    conversation_metadata_patch: dict[str, Any] | None = None,
    reference_time: datetime | None = None,
) -> list[dict[str, Any]]:
    filtered_messages = normalize_chat_messages(messages)
    persisted_at = reference_time or datetime.now(timezone.utc)
    conversation_metadata = {"synced_messages": len(filtered_messages), **(conversation_metadata_patch or {})}

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
                last_message_at = %s,
                metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb
            WHERE id = %s
            """,
            [
                map_conversation_status(status),
                persisted_at,
                json.dumps(conversation_metadata),
                conversation_id,
            ],
        )

    return filtered_messages


def apply_ticket_chat_history_sync(
    ticket: dict[str, Any],
    *,
    status: str,
    status_reason: str | None,
    messages: list[dict[str, Any]],
    conversation_metadata_patch: dict[str, Any] | None = None,
    reference_time: datetime | None = None,
) -> tuple[list[dict[str, Any]], str, str, bool]:
    persisted_at = reference_time or datetime.now(timezone.utc)
    apply_ticket_sla_policy(ticket)
    filtered_messages = sync_conversation_messages(
        int(ticket["conversation_id"]),
        status,
        messages,
        conversation_metadata_patch=conversation_metadata_patch,
        reference_time=persisted_at,
    )
    next_status_reason = status_reason if status_reason is not None else (ticket.get("status_reason") or "")
    if status == "Pending" and not next_status_reason:
        next_status_reason = get_default_status_reason_for_status(status)
    elif status == "Pending" and status_reason is None and not is_status_reason_allowed_for_status(status, next_status_reason):
        next_status_reason = get_default_status_reason_for_status(status)
    next_sla_status, next_sla_attention_required, next_sla_attention_reason = resolve_next_sla_state(
        status,
        ticket.get("created_at"),
        ticket["sla_status"],
    )
    sla_metadata_patch = build_sla_metadata_patch(next_sla_attention_required, next_sla_attention_reason)

    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE tickets
            SET status = %s,
                status_reason = %s,
                sla_status = %s,
                metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb,
                updated_at = NOW(),
                closed_at = CASE
                  WHEN %s = 'Closed' THEN NOW()
                  WHEN status = 'Closed' AND %s <> 'Closed' THEN NULL
                  ELSE closed_at
                END
            WHERE id = %s
            """,
            [status, next_status_reason, next_sla_status, json.dumps(sla_metadata_patch), status, status, ticket["id"]],
        )

    if status == "Pending" and is_quick_ticket_status_reason(next_status_reason):
        try_auto_assign_quick_ticket(ticket, now=persisted_at)

    if map_conversation_status(status) == "closed":
        persist_conversation_chat_duration(ticket["id"], ticket["conversation_id"], reference_time=persisted_at)

    insert_history_event(
        int(ticket["id"]),
        "chat_history_synced",
        {"role": "system", "label": "support_portal"},
        {
            "message_count": len(filtered_messages),
            "status": status,
            "statusReason": next_status_reason,
            "slaStatus": next_sla_status,
            "slaAttentionRequired": next_sla_attention_required,
        },
    )

    ticket["status"] = status
    ticket["status_reason"] = next_status_reason
    ticket["sla_status"] = next_sla_status
    if status == "Closed":
        ticket["closed_at"] = persisted_at
    elif ticket.get("closed_at") and status != "Closed":
        ticket["closed_at"] = None

    return filtered_messages, next_status_reason, next_sla_status, next_sla_attention_required


def persist_conversation_metadata_patch(conversation_id: Any, metadata_patch: dict[str, Any]) -> None:
    try:
        normalized_conversation_id = int(conversation_id)
    except (TypeError, ValueError):
        return

    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE conversations
            SET metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb
            WHERE id = %s
            """,
            [json.dumps(metadata_patch), normalized_conversation_id],
        )


def process_ticket_chat_inactivity(
    ticket: dict[str, Any],
    *,
    reference_time: datetime | None = None,
    allow_reminder: bool = True,
) -> str | None:
    if sanitize_text(ticket.get("status")) != "Open":
        return None

    if is_ticket_chat_closed(ticket.get("status"), ticket.get("conversation_status")):
        return None

    conversation_metadata = normalize_json_object(ticket.get("conversation_metadata"))
    latest_message_sender = map_role_to_sender(ticket.get("last_message_role"), ticket.get("last_message_metadata"))
    latest_message_content = sanitize_text(ticket.get("last_message_content"))
    latest_message_created_at = coerce_datetime(ticket.get("last_message_created_at"))
    reference_now = reference_time or datetime.now(timezone.utc)
    chat_is_active = (
        normalize_bool(conversation_metadata.get("is_active_conversation"))
        or bool(latest_message_created_at)
        or is_live_chat_requested(ticket.get("metadata"), conversation_metadata)
    )

    if not chat_is_active:
        return None

    waiting_since = get_inactivity_waiting_since(conversation_metadata)
    reminder_sent_at = get_inactivity_reminder_sent_at(conversation_metadata)
    reminder_text = build_chat_inactivity_reminder_message(ticket.get("learner_name"))

    if latest_message_sender == "user":
        if waiting_since or reminder_sent_at:
            persist_conversation_metadata_patch(
                ticket.get("conversation_id"),
                {
                    INACTIVITY_WAITING_SINCE_METADATA_KEY: None,
                    INACTIVITY_REMINDER_SENT_AT_METADATA_KEY: None,
                },
            )
        return None

    if waiting_since is None:
        waiting_since = (
            latest_message_created_at
            or get_live_chat_requested_at(ticket.get("metadata"), conversation_metadata, ticket.get("created_at"))
            or coerce_datetime(ticket.get("last_message_at"))
            or coerce_datetime(ticket.get("created_at"))
        )

    if reminder_sent_at is None and latest_message_content == reminder_text:
        reminder_sent_at = latest_message_created_at or reference_now

    if reminder_sent_at and latest_message_content and latest_message_content != reminder_text:
        if latest_message_created_at and latest_message_created_at > reminder_sent_at:
            waiting_since = latest_message_created_at
            reminder_sent_at = None
    elif reminder_sent_at is None and latest_message_created_at and waiting_since and latest_message_created_at > waiting_since:
        waiting_since = latest_message_created_at

    if not waiting_since:
        return None

    reminder_due = reminder_sent_at is None and (reference_now - waiting_since) >= CHAT_INACTIVITY_REMINDER_AFTER
    close_due = False
    if reminder_sent_at is not None:
        close_due = (reference_now - reminder_sent_at) >= CHAT_INACTIVITY_AUTO_CLOSE_AFTER
    elif not allow_reminder:
        close_due = (reference_now - waiting_since) >= (CHAT_INACTIVITY_REMINDER_AFTER + CHAT_INACTIVITY_AUTO_CLOSE_AFTER)

    if not reminder_due and not close_due:
        normalized_waiting_since = serialize_datetime_value(waiting_since)
        normalized_reminder_sent_at = serialize_datetime_value(reminder_sent_at)
        current_waiting_since = serialize_datetime_value(get_inactivity_waiting_since(conversation_metadata))
        current_reminder_sent_at = serialize_datetime_value(get_inactivity_reminder_sent_at(conversation_metadata))
        if (
            normalized_waiting_since != current_waiting_since
            or normalized_reminder_sent_at != current_reminder_sent_at
        ):
            persist_conversation_metadata_patch(
                ticket.get("conversation_id"),
                {
                    INACTIVITY_WAITING_SINCE_METADATA_KEY: normalized_waiting_since,
                    INACTIVITY_REMINDER_SENT_AT_METADATA_KEY: normalized_reminder_sent_at,
                },
            )
        return None

    raw_message_rows = run_query(
        """
        SELECT id, role, content, metadata, created_at
        FROM messages
        WHERE conversation_id = %s
        ORDER BY created_at ASC, id ASC
        """,
        [ticket["conversation_id"]],
    )
    chat_history = serialize_chat_history_rows(raw_message_rows)
    message_timestamp = format_chat_message_timestamp(reference_now)

    if close_due:
        next_messages = [
            *chat_history,
            {
                "sender": "bot",
                "text": build_chat_inactivity_closed_message(),
                "timestamp": message_timestamp,
            },
        ]
        apply_ticket_chat_history_sync(
            ticket,
            status="Closed",
            status_reason=STATUS_REASON_CLOSED_DUE_TO_INACTIVITY,
            messages=next_messages,
            conversation_metadata_patch={
                INACTIVITY_WAITING_SINCE_METADATA_KEY: None,
                INACTIVITY_REMINDER_SENT_AT_METADATA_KEY: None,
            },
            reference_time=reference_now,
        )
        return "closed"

    if allow_reminder and reminder_due:
        next_messages = [
            *chat_history,
            {
                "sender": "bot",
                "text": reminder_text,
                "timestamp": message_timestamp,
            },
        ]
        apply_ticket_chat_history_sync(
            ticket,
            status="Open",
            status_reason=ticket.get("status_reason") or "",
            messages=next_messages,
            conversation_metadata_patch={
                INACTIVITY_WAITING_SINCE_METADATA_KEY: serialize_datetime_value(waiting_since),
                INACTIVITY_REMINDER_SENT_AT_METADATA_KEY: serialize_datetime_value(reference_now),
            },
            reference_time=reference_now,
        )
        return "reminded"

    return None


def sync_open_ticket_inactivity(
    *,
    public_id: str | None = None,
    reference_time: datetime | None = None,
    allow_reminder: bool = True,
) -> dict[str, int]:
    params: list[Any] = []
    public_id_filter = ""
    if public_id:
        public_id_filter = "AND t.public_id = %s"
        params.append(public_id)

    tickets = run_query(
        f"""
        SELECT
          t.id,
          t.public_id,
          t.status,
          t.status_reason,
          t.sla_status,
          t.metadata,
          t.created_at,
          t.closed_at,
          t.conversation_id,
          c.status AS conversation_status,
          c.metadata AS conversation_metadata,
          c.last_message_at,
          l.full_name AS learner_name,
          lm.role AS last_message_role,
          lm.content AS last_message_content,
          lm.metadata AS last_message_metadata,
          lm.created_at AS last_message_created_at
        FROM tickets t
        JOIN learners l
          ON l.id = t.learner_id
        LEFT JOIN conversations c
          ON c.id = t.conversation_id
        LEFT JOIN LATERAL (
          SELECT role, content, metadata, created_at
          FROM messages
          WHERE conversation_id = t.conversation_id
          ORDER BY created_at DESC, id DESC
          LIMIT 1
        ) lm
          ON TRUE
        WHERE t.status = 'Open'
          AND t.conversation_id IS NOT NULL
          {public_id_filter}
        ORDER BY t.id ASC
        """,
        params,
    )

    result = {"scanned": len(tickets), "reminded": 0, "closed": 0}
    for ticket in tickets:
        action = process_ticket_chat_inactivity(
            ticket,
            reference_time=reference_time,
            allow_reminder=allow_reminder,
        )
        if action == "reminded":
            result["reminded"] += 1
        elif action == "closed":
            result["closed"] += 1

    return result


def fetch_actor_by_username(username: str) -> dict[str, Any] | None:
    if not username:
        return None

    return run_query_one(
        """
        SELECT id, username, full_name, role
        FROM support_accounts
        WHERE LOWER(username) = %s
        LIMIT 1
        """,
        [username.lower()],
    )


def fetch_agent_account_by_id(agent_id: int) -> dict[str, Any] | None:
    return run_query_one(
        """
        SELECT id, username, full_name, email, account_scope, role, is_active, metadata
        FROM support_accounts
        WHERE id = %s
        LIMIT 1
        """,
        [agent_id],
    )


def fetch_agent_account_by_username(username: str, *, active_only: bool = False) -> dict[str, Any] | None:
    if not username:
        return None

    active_filter = "AND is_active = TRUE" if active_only else ""
    return run_query_one(
        f"""
        SELECT id, username, full_name, email, account_scope, role, is_active, metadata
        FROM support_accounts
        WHERE LOWER(username) = %s
          {active_filter}
        LIMIT 1
        """,
        [username.lower()],
    )


def fetch_agent_with_metadata_by_username(username: str) -> dict[str, Any] | None:
    return fetch_agent_account_by_username(username, active_only=True)


def find_agent_account_by_username(username: str, *, exclude_agent_id: int | None = None) -> dict[str, Any] | None:
    if not username:
        return None

    if exclude_agent_id is None:
        return run_query_one(
            """
            SELECT id, username
            FROM support_accounts
            WHERE LOWER(username) = %s
            LIMIT 1
            """,
            [username.lower()],
        )

    return run_query_one(
        """
        SELECT id, username
        FROM support_accounts
        WHERE LOWER(username) = %s
          AND id <> %s
        LIMIT 1
        """,
        [username.lower(), exclude_agent_id],
    )


def find_agent_account_by_email(email: str | None, *, exclude_agent_id: int | None = None) -> dict[str, Any] | None:
    if not email:
        return None

    if exclude_agent_id is None:
        return run_query_one(
            """
            SELECT id, email
            FROM support_accounts
            WHERE LOWER(email) = %s
            LIMIT 1
            """,
            [email.lower()],
        )

    return run_query_one(
        """
        SELECT id, email
        FROM support_accounts
        WHERE LOWER(email) = %s
          AND id <> %s
        LIMIT 1
        """,
        [email.lower(), exclude_agent_id],
    )


def fetch_public_requester_account_by_email(email: str) -> dict[str, Any] | None:
    if not email:
        return None

    return run_query_one(
        """
        SELECT id, username, full_name, email, account_scope, role, is_active, metadata
        FROM support_accounts
        WHERE LOWER(TRIM(email)) = %s
          AND is_active = TRUE
          AND account_scope = %s
          AND role = ANY(%s)
        LIMIT 1
        """,
        [email.lower(), ACCOUNT_SCOPE_REQUESTER, list(PUBLIC_SUPPORT_ACCOUNT_ROLES)],
    )


def resolve_public_support_requester(email: str) -> dict[str, Any] | None:
    managed_account = fetch_public_requester_account_by_email(email)
    if not managed_account:
        return None

    local_learner = fetch_local_learner_by_email(email)
    return {
        "email": email,
        "role": normalize_public_requester_role(managed_account.get("role")),
        "account": managed_account,
        "learner": local_learner,
        "display_name": (
            sanitize_text(managed_account.get("full_name"))
            or sanitize_text(local_learner.get("full_name") if local_learner else "")
            or sanitize_text(managed_account.get("username"))
        ),
    }


def ensure_public_requester_learner(requester: dict[str, Any]) -> dict[str, Any]:
    existing_learner = requester.get("learner")
    managed_account = requester.get("account")

    if not managed_account:
        if not existing_learner:
            raise ApiError(404, "This email is not registered in our records.")
        return existing_learner

    learner_payload = {
        "external_learner_id": existing_learner.get("external_learner_id") if existing_learner else None,
        "support_account_id": int(managed_account["id"]),
        "full_name": (
            sanitize_text(managed_account.get("full_name"))
            or sanitize_text(existing_learner.get("full_name") if existing_learner else "")
            or sanitize_text(managed_account.get("username"))
        ),
        "email": requester["email"],
        "phone": existing_learner.get("phone") if existing_learner else None,
    }
    ensured_learner = upsert_learner_record(
        learner_payload,
        source=MANAGED_PUBLIC_REQUESTER_SOURCE,
        metadata={
            "managed_public_requester": True,
            "requester_role": normalize_public_requester_role(managed_account.get("role")),
        },
    )
    if not ensured_learner:
        raise ApiError(500, "We could not prepare this support account right now.")
    return ensured_learner


def require_agent_session_actor(
    actor_username: Any,
    instance_id: Any,
    *,
    allowed_roles: set[str] | None = None,
) -> dict[str, Any]:
    normalized_actor_username = sanitize_text(actor_username).lower()
    normalized_instance_id = sanitize_text(instance_id)
    if not normalized_actor_username or not normalized_instance_id:
        raise ApiError(401, "Admin session is required.")

    actor = fetch_agent_with_metadata_by_username(normalized_actor_username)
    if not actor:
        raise ApiError(401, "Your admin session has expired. Please sign in again.")

    metadata = normalize_json_object(actor.get("metadata"))
    if sanitize_text(metadata.get("session_instance_id")) != normalized_instance_id or not is_agent_session_active(metadata):
        raise ApiError(401, "Your admin session has expired. Please sign in again.")

    actor_role = sanitize_text(actor.get("role")).lower()
    if allowed_roles and actor_role not in allowed_roles:
        raise ApiError(403, "You do not have permission to manage support accounts.")

    return actor


def persist_agent_metadata(agent_id: int, metadata: dict[str, Any]) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE support_accounts
            SET metadata = %s::jsonb,
                updated_at = NOW()
            WHERE id = %s
            """,
            [json.dumps(metadata or {}), agent_id],
        )


def is_agent_session_active(metadata: Any, now: datetime | None = None) -> bool:
    normalized_metadata = normalize_json_object(metadata)
    if not normalize_bool(normalized_metadata.get("session_active")):
        return False

    comparison_now = now or datetime.now(timezone.utc)
    last_seen_at = parse_iso_datetime(normalized_metadata.get("session_last_seen_at"))
    if last_seen_at is None:
        last_seen_at = parse_iso_datetime(normalized_metadata.get("session_started_at"))
    if last_seen_at is None:
        return False

    return (comparison_now - last_seen_at) <= AGENT_SESSION_TIMEOUT


def is_agent_assignable_for_live_chat(metadata: Any, now: datetime | None = None) -> bool:
    normalized_metadata = normalize_json_object(metadata)
    if not is_agent_session_active(normalized_metadata, now):
        return False

    return normalize_selectable_console_status(normalized_metadata.get("console_status")) not in NON_ASSIGNABLE_AGENT_CONSOLE_STATUSES


def get_agent_queue_joined_at(metadata: Any, fallback: datetime | None = None) -> datetime | None:
    normalized_metadata = normalize_json_object(metadata)
    return (
        parse_iso_datetime(normalized_metadata.get("queue_joined_at"))
        or parse_iso_datetime(normalized_metadata.get("session_started_at"))
        or fallback
    )


def get_agent_last_live_chat_assigned_at(metadata: Any) -> datetime | None:
    normalized_metadata = normalize_json_object(metadata)
    return parse_iso_datetime(normalized_metadata.get("last_live_chat_assigned_at"))


def get_agent_last_quick_ticket_assigned_at(metadata: Any) -> datetime | None:
    normalized_metadata = normalize_json_object(metadata)
    return parse_iso_datetime(normalized_metadata.get(LAST_QUICK_TICKET_ASSIGNED_AT_METADATA_KEY))


def get_live_chat_requested_at(ticket_metadata: Any, conversation_metadata: Any = None, fallback: Any = None) -> datetime | None:
    normalized_ticket_metadata = normalize_json_object(ticket_metadata)
    normalized_conversation_metadata = normalize_json_object(conversation_metadata)
    return (
        parse_iso_datetime(normalized_conversation_metadata.get("live_chat_requested_at"))
        or parse_iso_datetime(normalized_ticket_metadata.get("live_chat_requested_at"))
        or (fallback if isinstance(fallback, datetime) else parse_iso_datetime(fallback))
    )


def get_queue_assigned_at(ticket_metadata: Any, conversation_metadata: Any = None) -> datetime | None:
    normalized_ticket_metadata = normalize_json_object(ticket_metadata)
    normalized_conversation_metadata = normalize_json_object(conversation_metadata)
    return (
        parse_iso_datetime(normalized_conversation_metadata.get("queue_assigned_at"))
        or parse_iso_datetime(normalized_ticket_metadata.get("queue_assigned_at"))
    )


def calculate_conversation_chat_duration_minutes(
    ticket_metadata: Any,
    conversation_metadata: Any = None,
    *,
    created_at: Any = None,
    updated_at: Any = None,
    closed_at: Any = None,
    last_message_at: Any = None,
    conversation_status: Any = None,
    reference_time: datetime | None = None,
) -> int:
    start_at = get_queue_assigned_at(ticket_metadata, conversation_metadata) or get_live_chat_requested_at(
        ticket_metadata,
        conversation_metadata,
    )
    if not start_at:
        return 0

    comparison_now = reference_time or datetime.now(timezone.utc)
    is_closed = sanitize_text(conversation_status).lower() == "closed" or coerce_datetime(closed_at) is not None
    end_at = (
        coerce_datetime(last_message_at)
        or coerce_datetime(closed_at)
        or coerce_datetime(updated_at)
        or comparison_now
    ) if is_closed else comparison_now

    elapsed_seconds = max(int((end_at - start_at).total_seconds()), 0)
    return elapsed_seconds // 60


def persist_conversation_chat_duration(
    ticket_id: Any,
    conversation_id: Any,
    *,
    reference_time: datetime | None = None,
) -> int | None:
    try:
        normalized_ticket_id = int(ticket_id)
        normalized_conversation_id = int(conversation_id)
    except (TypeError, ValueError):
        return None

    row = run_query_one(
        """
        SELECT
          t.metadata,
          t.created_at,
          t.updated_at,
          t.closed_at,
          c.status AS conversation_status,
          c.metadata AS conversation_metadata,
          c.last_message_at
        FROM tickets t
        JOIN conversations c
          ON c.id = t.conversation_id
        WHERE t.id = %s
          AND c.id = %s
        LIMIT 1
        """,
        [normalized_ticket_id, normalized_conversation_id],
    )

    if not row:
        return None

    if sanitize_text(row.get("conversation_status")).lower() != "closed" and coerce_datetime(row.get("closed_at")) is None:
        return None

    duration_minutes = calculate_conversation_chat_duration_minutes(
        row.get("metadata"),
        row.get("conversation_metadata"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
        closed_at=row.get("closed_at"),
        last_message_at=row.get("last_message_at"),
        conversation_status=row.get("conversation_status"),
        reference_time=reference_time,
    )

    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE conversations
            SET
              chat_duration_minutes = %s,
              metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb
            WHERE id = %s
            """,
            [
                duration_minutes,
                json.dumps(
                    {
                        "chat_duration_minutes": duration_minutes,
                        "chat_duration_updated_at": serialize_datetime_value(reference_time or datetime.now(timezone.utc)),
                    }
                ),
                normalized_conversation_id,
            ],
        )

    return duration_minutes


def is_open_assigned_live_chat_ticket(ticket: dict[str, Any]) -> bool:
    if sanitize_text(ticket.get("status")) != "Open":
        return False
    if not ticket.get("assigned_agent_id"):
        return False
    if sanitize_text(ticket.get("conversation_status")).lower() == "closed":
        return False
    if not is_live_chat_requested(ticket.get("metadata"), ticket.get("conversation_metadata")):
        return False
    if not is_active_conversation(ticket.get("conversation_metadata")):
        return False
    if not is_latest_ticket_for_conversation(ticket.get("public_id"), ticket.get("conversation_metadata")):
        return False
    return True


def get_open_assigned_live_chat_agent_ids(ticket_rows: list[dict[str, Any]] | None = None) -> set[int]:
    if ticket_rows is None:
        ticket_rows = run_query(
            """
            SELECT
              t.assigned_agent_id,
              t.public_id,
              t.status,
              t.metadata,
              c.status AS conversation_status,
              c.metadata AS conversation_metadata
            FROM tickets t
            JOIN conversations c
              ON c.id = t.conversation_id
            WHERE t.conversation_id IS NOT NULL
              AND t.assigned_agent_id IS NOT NULL
              AND t.status = 'Open'
            ORDER BY t.id ASC
            """
        )

    open_assigned_chat_agent_ids: set[int] = set()
    for ticket in ticket_rows:
        if not is_open_assigned_live_chat_ticket(ticket):
            continue

        try:
            open_assigned_chat_agent_ids.add(int(ticket["assigned_agent_id"]))
        except (TypeError, ValueError):
            continue

    return open_assigned_chat_agent_ids


def sort_agents_for_live_chat_queue(
    agents: list[dict[str, Any]],
    now: datetime | None = None,
    open_assigned_chat_agent_ids: set[int] | None = None,
) -> list[dict[str, Any]]:
    comparison_now = now or datetime.now(timezone.utc)
    busy_agent_ids = open_assigned_chat_agent_ids or set()

    def queue_sort_key(agent: dict[str, Any]) -> tuple[int, datetime, datetime, int]:
        metadata = normalize_json_object(agent.get("metadata"))
        agent_id = int(agent["id"])
        console_status = resolve_agent_console_status(
            metadata,
            session_active=True,
            has_open_assigned_chat=agent_id in busy_agent_ids,
        )
        queue_joined_at = get_agent_queue_joined_at(metadata, comparison_now) or comparison_now
        last_assigned_at = get_agent_last_live_chat_assigned_at(metadata) or queue_joined_at
        priority = 0 if console_status == "Available" else 1
        return (priority, last_assigned_at, queue_joined_at, agent_id)

    return sorted(agents, key=queue_sort_key)


def select_next_live_chat_agent(
    agents: list[dict[str, Any]],
    now: datetime | None = None,
    open_assigned_chat_agent_ids: set[int] | None = None,
) -> dict[str, Any] | None:
    comparison_now = now or datetime.now(timezone.utc)
    busy_agent_ids = open_assigned_chat_agent_ids or set()
    sorted_agents = sort_agents_for_live_chat_queue(agents, comparison_now, busy_agent_ids)

    for agent in sorted_agents:
        metadata = normalize_json_object(agent.get("metadata"))
        agent_id = int(agent["id"])
        effective_console_status = resolve_agent_console_status(
            metadata,
            session_active=True,
            has_open_assigned_chat=agent_id in busy_agent_ids,
        )
        if effective_console_status == "Available":
            return agent

    return None


def sort_admins_for_quick_ticket_queue(
    admins: list[dict[str, Any]],
    now: datetime | None = None,
    open_assigned_chat_agent_ids: set[int] | None = None,
) -> list[dict[str, Any]]:
    comparison_now = now or datetime.now(timezone.utc)
    busy_agent_ids = open_assigned_chat_agent_ids or set()
    console_status_priority = {"Available": 0, "Busy": 1, "Off": 2}

    def queue_sort_key(admin: dict[str, Any]) -> tuple[int, datetime, int]:
        metadata = normalize_json_object(admin.get("metadata"))
        admin_id = int(admin["id"])
        console_status = resolve_agent_console_status(
            metadata,
            has_open_assigned_chat=admin_id in busy_agent_ids,
        )
        last_assigned_at = (
            get_agent_last_quick_ticket_assigned_at(metadata)
            or get_agent_last_live_chat_assigned_at(metadata)
            or get_agent_queue_joined_at(metadata, comparison_now)
            or comparison_now
        )
        return (console_status_priority.get(console_status, 99), last_assigned_at, admin_id)

    return sorted(admins, key=queue_sort_key)


def select_next_quick_ticket_admin(
    admins: list[dict[str, Any]],
    now: datetime | None = None,
    open_assigned_chat_agent_ids: set[int] | None = None,
) -> dict[str, Any] | None:
    sorted_admins = sort_admins_for_quick_ticket_queue(admins, now, open_assigned_chat_agent_ids)
    return sorted_admins[0] if sorted_admins else None


def assign_ticket_to_agent(ticket: dict[str, Any], agent: dict[str, Any], assigned_at: datetime) -> bool:
    next_assigned_agent_id = int(agent["id"])
    current_assigned_agent_id = int(ticket["assigned_agent_id"]) if ticket.get("assigned_agent_id") else None

    if current_assigned_agent_id == next_assigned_agent_id:
        return False

    assigned_at_value = serialize_datetime_value(assigned_at)
    ticket_metadata = normalize_json_object(ticket.get("metadata"))
    conversation_metadata = normalize_json_object(ticket.get("conversation_metadata"))
    assigned_team = derive_assigned_team(agent)
    agent_name = agent.get("full_name") or agent["username"]

    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE tickets
            SET assigned_agent_id = %s,
                assigned_team = %s,
                metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb,
                updated_at = NOW()
            WHERE id = %s
            """,
            [
                next_assigned_agent_id,
                assigned_team,
                json.dumps(
                    {
                        "queue_assigned_at": assigned_at_value,
                        "queue_assigned_agent_username": agent["username"],
                        "queue_assigned_agent_name": agent_name,
                    }
                ),
                ticket["id"],
            ],
        )

        if ticket.get("conversation_id"):
            cursor.execute(
                """
                UPDATE conversations
                SET metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb
                WHERE id = %s
                """,
                [
                    json.dumps(
                        {
                            "assigned_agent_id": next_assigned_agent_id,
                            "assigned_agent_username": agent["username"],
                            "assigned_agent_name": agent_name,
                            "queue_assigned_at": assigned_at_value,
                            "chat_public_id": build_public_chat_id(
                                ticket.get("public_id"),
                                ticket.get("conversation_id"),
                                conversation_metadata,
                            ),
                        }
                    ),
                    ticket["conversation_id"],
                ],
            )

    insert_history_event(
        int(ticket["id"]),
        "assignment_changed",
        {"role": "system", "label": "live_chat_queue"},
        {
            "fromAgentId": current_assigned_agent_id,
            "toAgentId": next_assigned_agent_id,
            "toAgentName": agent_name,
            "queuedAt": assigned_at_value,
            "liveChatRequestedAt": serialize_datetime_value(
                get_live_chat_requested_at(ticket_metadata, conversation_metadata, ticket.get("created_at"))
            ),
        },
    )

    ticket["assigned_agent_id"] = next_assigned_agent_id
    ticket["assigned_agent_username"] = agent["username"]
    ticket["assigned_agent_name"] = agent_name
    ticket["assigned_team"] = assigned_team
    ticket["metadata"] = {
        **ticket_metadata,
        "queue_assigned_at": assigned_at_value,
        "queue_assigned_agent_username": agent["username"],
        "queue_assigned_agent_name": agent_name,
    }
    ticket["conversation_metadata"] = {
        **conversation_metadata,
        "assigned_agent_id": next_assigned_agent_id,
        "assigned_agent_username": agent["username"],
        "assigned_agent_name": agent_name,
        "queue_assigned_at": assigned_at_value,
    }
    return True


def assign_quick_ticket_to_admin(ticket: dict[str, Any], admin: dict[str, Any], assigned_at: datetime) -> bool:
    next_assigned_admin_id = int(admin["id"])
    current_assigned_admin_id = int(ticket["assigned_agent_id"]) if ticket.get("assigned_agent_id") else None

    if current_assigned_admin_id == next_assigned_admin_id:
        return False

    assigned_at_value = serialize_datetime_value(assigned_at)
    ticket_metadata = normalize_json_object(ticket.get("metadata"))
    conversation_metadata = normalize_json_object(ticket.get("conversation_metadata"))
    assigned_team = derive_assigned_team(admin)
    admin_name = admin.get("full_name") or admin["username"]

    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE tickets
            SET assigned_agent_id = %s,
                assigned_team = %s,
                metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb,
                updated_at = NOW()
            WHERE id = %s
            """,
            [
                next_assigned_admin_id,
                assigned_team,
                json.dumps(
                    {
                        "quick_ticket_assigned_at": assigned_at_value,
                        "quick_ticket_assigned_admin_username": admin["username"],
                        "quick_ticket_assigned_admin_name": admin_name,
                    }
                ),
                ticket["id"],
            ],
        )

        if ticket.get("conversation_id"):
            cursor.execute(
                """
                UPDATE conversations
                SET metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb
                WHERE id = %s
                """,
                [
                    json.dumps(
                        {
                            "assigned_agent_id": next_assigned_admin_id,
                            "assigned_agent_username": admin["username"],
                            "assigned_agent_name": admin_name,
                            "quick_ticket_assigned_at": assigned_at_value,
                        }
                    ),
                    ticket["conversation_id"],
                ],
            )

    insert_history_event(
        int(ticket["id"]),
        "assignment_changed",
        {"role": "system", "label": "quick_ticket_queue"},
        {
            "fromAgentId": current_assigned_admin_id,
            "toAgentId": next_assigned_admin_id,
            "toAgentName": admin_name,
            "assignedAt": assigned_at_value,
            "assignmentSource": "quick_ticket",
            "statusReason": STATUS_REASON_QUICK_TICKET,
        },
    )

    next_admin_metadata = normalize_json_object(admin.get("metadata"))
    next_admin_metadata[LAST_QUICK_TICKET_ASSIGNED_AT_METADATA_KEY] = assigned_at_value
    persist_agent_metadata(int(admin["id"]), next_admin_metadata)
    admin["metadata"] = next_admin_metadata

    ticket["assigned_agent_id"] = next_assigned_admin_id
    ticket["assigned_agent_username"] = admin["username"]
    ticket["assigned_agent_name"] = admin_name
    ticket["assigned_team"] = assigned_team
    ticket["metadata"] = {
        **ticket_metadata,
        "quick_ticket_assigned_at": assigned_at_value,
        "quick_ticket_assigned_admin_username": admin["username"],
        "quick_ticket_assigned_admin_name": admin_name,
    }
    ticket["conversation_metadata"] = {
        **conversation_metadata,
        "assigned_agent_id": next_assigned_admin_id,
        "assigned_agent_username": admin["username"],
        "assigned_agent_name": admin_name,
        "quick_ticket_assigned_at": assigned_at_value,
    }
    return True


def try_auto_assign_quick_ticket(ticket: dict[str, Any], now: datetime | None = None) -> dict[str, Any] | None:
    if ticket.get("assigned_agent_id"):
        return None

    admin_candidates = run_query(
        """
        SELECT id, username, full_name, email, role, metadata
        FROM support_accounts
        WHERE is_active = TRUE
          AND account_scope = %s
          AND role = %s
        ORDER BY id ASC
        """,
        [ACCOUNT_SCOPE_STAFF, ROLE_ADMIN],
    )
    if not admin_candidates:
        return None

    assignment_now = now or datetime.now(timezone.utc)
    open_assigned_chat_agent_ids = get_open_assigned_live_chat_agent_ids()
    next_admin = select_next_quick_ticket_admin(admin_candidates, assignment_now, open_assigned_chat_agent_ids)
    if not next_admin:
        return None
    if not assign_quick_ticket_to_admin(ticket, next_admin, assignment_now):
        return None
    return next_admin


def assign_waiting_live_chat_tickets(now: datetime | None = None) -> list[int]:
    assignment_now = now or datetime.now(timezone.utc)
    active_agents = [
        agent
        for agent in run_query(
            """
            SELECT id, username, full_name, email, account_scope, role, metadata
            FROM support_accounts
            WHERE is_active = TRUE
              AND account_scope = %s
            ORDER BY id ASC
            """,
            [ACCOUNT_SCOPE_STAFF],
        )
        if is_agent_assignable_for_live_chat(agent.get("metadata"), assignment_now)
    ]

    if not active_agents:
        return []

    active_agent_ids = {
        int(agent["id"])
        for agent in active_agents
        if isinstance(agent.get("id"), (int, float)) or str(agent.get("id")).isdigit()
    }

    candidate_tickets = run_query(
        """
        SELECT
          t.id,
          t.public_id,
          t.status,
          t.priority,
          t.metadata,
          t.created_at,
          t.updated_at,
          t.conversation_id,
          t.assigned_agent_id,
          t.assigned_team,
          c.status AS conversation_status,
          c.metadata AS conversation_metadata,
          a.metadata AS assigned_agent_metadata
        FROM tickets t
        JOIN conversations c
          ON c.id = t.conversation_id
        LEFT JOIN support_accounts a
          ON a.id = t.assigned_agent_id
        WHERE t.conversation_id IS NOT NULL
          AND t.status = 'Open'
        ORDER BY t.created_at ASC, t.id ASC
        """
    )
    open_assigned_chat_agent_ids = get_open_assigned_live_chat_agent_ids(candidate_tickets)
    waiting_tickets = []
    for ticket in candidate_tickets:
        if not is_live_chat_requested(ticket.get("metadata"), ticket.get("conversation_metadata")):
            continue
        if sanitize_text(ticket.get("conversation_status")).lower() == "closed":
            continue

        assigned_agent_id = int(ticket["assigned_agent_id"]) if ticket.get("assigned_agent_id") else None
        has_active_assigned_agent = bool(assigned_agent_id) and assigned_agent_id in active_agent_ids
        if has_active_assigned_agent:
            continue

        waiting_tickets.append(ticket)

    waiting_tickets.sort(
        key=lambda ticket: (
            get_ticket_priority_rank(ticket.get("priority")),
            get_live_chat_requested_at(ticket.get("metadata"), ticket.get("conversation_metadata"), ticket.get("created_at"))
            or assignment_now,
            ticket.get("created_at") or assignment_now,
            int(ticket["id"]),
        )
    )

    assigned_ticket_ids: list[int] = []
    assignment_cursor = assignment_now

    for ticket in waiting_tickets:
        next_agent = select_next_live_chat_agent(active_agents, assignment_cursor, open_assigned_chat_agent_ids)
        if not next_agent:
            break

        if not assign_ticket_to_agent(ticket, next_agent, assignment_cursor):
            continue

        next_agent_metadata = normalize_json_object(next_agent.get("metadata"))
        next_agent_metadata["console_status"] = normalize_selectable_console_status(
            next_agent_metadata.get("console_status")
        )
        next_agent_metadata["last_live_chat_assigned_at"] = serialize_datetime_value(assignment_cursor)
        persist_agent_metadata(int(next_agent["id"]), next_agent_metadata)
        next_agent["metadata"] = next_agent_metadata
        open_assigned_chat_agent_ids.add(int(next_agent["id"]))
        assigned_ticket_ids.append(int(ticket["id"]))
        assignment_cursor += timedelta(milliseconds=1)

    return assigned_ticket_ids


def register_agent_session(username: str, instance_id: str, console_status: str = DEFAULT_AGENT_CONSOLE_STATUS) -> dict[str, Any]:
    normalized_username = sanitize_text(username).lower()
    normalized_instance_id = sanitize_text(instance_id) or uuid4().hex
    normalized_console_status = normalize_selectable_console_status(console_status)
    agent = fetch_agent_with_metadata_by_username(normalized_username)

    if not agent:
        raise ApiError(401, "Invalid username or password.")

    now = datetime.now(timezone.utc)
    metadata = normalize_json_object(agent.get("metadata"))
    current_instance_id = sanitize_text(metadata.get("session_instance_id"))
    should_reset_queue_joined_at = (
        not current_instance_id
        or current_instance_id != normalized_instance_id
        or not is_agent_session_active(metadata, now)
    )

    metadata.update(
        {
            "session_active": True,
            "session_instance_id": normalized_instance_id,
            "session_started_at": metadata.get("session_started_at") if not should_reset_queue_joined_at else serialize_datetime_value(now),
            "session_last_seen_at": serialize_datetime_value(now),
            "console_status": normalized_console_status,
            "queue_joined_at": metadata.get("queue_joined_at") if not should_reset_queue_joined_at else serialize_datetime_value(now),
        }
    )
    persist_agent_metadata(int(agent["id"]), metadata)
    agent["metadata"] = metadata
    assign_waiting_live_chat_tickets(now)
    return serialize_agent(agent, open_assigned_chat_agent_ids=get_open_assigned_live_chat_agent_ids())


def heartbeat_agent_session(payload: dict[str, Any]) -> dict[str, Any]:
    actor_username = sanitize_text(payload.get("actorUsername")).lower()
    instance_id = sanitize_text(payload.get("instanceId"))
    console_status = normalize_selectable_console_status(payload.get("consoleStatus"))

    if not actor_username or not instance_id:
        raise ApiError(400, "Agent session details are required.")

    agent = fetch_agent_with_metadata_by_username(actor_username)
    if not agent:
        raise ApiError(404, "Agent not found.")

    metadata = normalize_json_object(agent.get("metadata"))
    current_instance_id = sanitize_text(metadata.get("session_instance_id"))
    if current_instance_id and current_instance_id != instance_id:
        return {
            "ok": True,
            "sessionActive": False,
            "sessionReplaced": is_agent_session_active(metadata),
        }

    if not current_instance_id or not is_agent_session_active(metadata):
        return {"ok": True, "sessionActive": False, "sessionReplaced": False}

    register_agent_session(actor_username, instance_id, console_status)
    return {"ok": True, "sessionActive": True, "sessionReplaced": False}


def close_agent_session(payload: dict[str, Any]) -> dict[str, Any]:
    actor_username = sanitize_text(payload.get("actorUsername")).lower()
    instance_id = sanitize_text(payload.get("instanceId"))

    if not actor_username:
        raise ApiError(400, "Agent username is required.")

    agent = fetch_agent_with_metadata_by_username(actor_username)
    if not agent:
        return {"ok": True, "sessionClosed": False}

    metadata = normalize_json_object(agent.get("metadata"))
    current_instance_id = sanitize_text(metadata.get("session_instance_id"))
    if instance_id and current_instance_id and current_instance_id != instance_id and is_agent_session_active(metadata):
        return {"ok": True, "sessionClosed": False, "sessionReplaced": True}

    now = datetime.now(timezone.utc)
    metadata.update(
        {
            "session_active": False,
            "session_last_seen_at": serialize_datetime_value(now),
            "session_logged_out_at": serialize_datetime_value(now),
            "console_status": "Off",
        }
    )
    persist_agent_metadata(int(agent["id"]), metadata)
    assign_waiting_live_chat_tickets(now)
    return {"ok": True, "sessionClosed": True, "sessionReplaced": False}


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
          t.status_reason,
          t.assigned_team,
          t.sla_status,
          t.priority,
          t.evidence_count,
          t.metadata,
          t.created_at,
          t.updated_at,
          t.closed_at,
          t.conversation_id,
          c.status AS conversation_status,
          c.metadata AS conversation_metadata,
          c.chat_duration_minutes,
          c.last_message_at,
          l.full_name AS learner_name,
          l.email AS learner_email,
          l.phone AS learner_phone,
          a.id AS assigned_agent_id,
          a.username AS assigned_agent_username,
          a.full_name AS assigned_agent_name
        FROM tickets t
        JOIN learners l
          ON l.id = t.learner_id
        LEFT JOIN conversations c
          ON c.id = t.conversation_id
        LEFT JOIN support_accounts a
          ON a.id = t.assigned_agent_id
        WHERE t.public_id = %s
        LIMIT 1
        """,
        [public_id],
    )

    if not ticket:
        return None

    apply_ticket_sla_policy(ticket, persist=True)

    if ticket.get("conversation_id"):
        raw_messages = run_query(
            """
            SELECT id, role, content, metadata, created_at
            FROM messages
            WHERE conversation_id = %s
            ORDER BY created_at ASC, id ASC
            """,
            [ticket["conversation_id"]],
        )
    else:
        raw_messages = []

    messages = ensure_intro_message_row(
        raw_messages,
        intro_message=build_chat_intro_message(
            ticket.get("learner_name"),
            ticket.get("category"),
            ticket.get("technical_subcategory"),
        ),
        created_at=ticket.get("created_at"),
        intro_id=f"intro-{ticket['public_id']}",
    )

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
    chat_history_events = [
        row
        for row in history
        if sanitize_text(row.get("event_type")).lower() == "assignment_changed"
    ]
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
        "chatHistory": serialize_admin_chat_timeline_rows(messages, chat_history_events),
        "attachments": [
            {
                "id": int(row["id"]),
                "name": row["file_name"],
                "mimeType": row.get("mime_type"),
                "size": int(row["file_size"]) if row.get("file_size") else 0,
                "storageUrl": row.get("storage_url"),
                "metadata": normalize_json_object(row.get("metadata")),
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
                "payload": normalize_history_payload(
                    row.get("payload"),
                    ticket_public_id=ticket.get("public_id"),
                    conversation_id=ticket.get("conversation_id"),
                    conversation_metadata=ticket.get("conversation_metadata"),
                ),
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
                "metadata": normalize_json_object(row.get("metadata")),
                "createdAt": row["created_at"],
            }
            for row in session_requests
        ],
    }


def get_verify_email_response(payload: dict[str, Any]) -> dict[str, Any]:
    email = normalize_email(payload.get("email"))

    if not is_valid_email(email):
        raise ApiError(400, "Please enter a valid email address.")

    requester = resolve_public_support_requester(email)
    if not requester:
        raise ApiError(404, "This email is not registered in our records.")

    learner = requester.get("learner")
    requester_role = requester["role"]
    response = {
        "exists": True,
        "requesterRole": requester_role,
        "learner": {
            "id": learner["id"] if learner else None,
            "fullName": requester.get("display_name") or (learner.get("full_name") if learner else ""),
            "email": email,
        },
        "message": "Email verified.",
    }

    if not learner:
        return response

    existing_ticket = find_latest_active_ticket_for_learner(int(learner["id"]))
    if not existing_ticket:
        return response

    existing_ticket_metadata = normalize_json_object(existing_ticket.get("metadata"))
    response["ticket"] = {
        "id": existing_ticket["public_id"],
        "learnerName": requester.get("display_name") or learner.get("full_name") or "",
        "email": learner["email"],
        "requesterRole": get_ticket_requester_role(existing_ticket_metadata, default=requester_role),
        "category": existing_ticket["category"],
        "technicalSubcategory": existing_ticket.get("technical_subcategory") or "",
        "inquiry": existing_ticket.get("inquiry") or "",
        "status": existing_ticket["status"],
        "statusReason": existing_ticket.get("status_reason") or "",
        "assignedAgentId": int(existing_ticket["assigned_agent_id"]) if existing_ticket.get("assigned_agent_id") else None,
        "assignedTeam": existing_ticket.get("assigned_team") or "Unassigned",
        "slaStatus": existing_ticket["sla_status"],
        "createdAt": existing_ticket["created_at"],
        "chatState": derive_ticket_chat_state(existing_ticket.get("status"), existing_ticket.get("conversation_status")),
        "liveChatRequested": is_live_chat_requested(existing_ticket.get("metadata"), existing_ticket.get("conversation_metadata")),
    }

    booking_summary = get_latest_ticket_booking_summary(int(existing_ticket["id"]))
    if booking_summary:
        response["bookingSummary"] = booking_summary

    return response


def get_admin_login_response(payload: dict[str, Any]) -> dict[str, Any]:
    username = sanitize_text(payload.get("username")).lower()
    password = payload.get("password") if isinstance(payload.get("password"), str) else ""
    instance_id = sanitize_text(payload.get("instanceId"))
    console_status = normalize_selectable_console_status(payload.get("consoleStatus"))

    if not username or not password:
        raise ApiError(400, "Username and password are required.")

    agent = fetch_agent_with_metadata_by_username(username)

    if not verify_agent_password(agent, password):
        raise ApiError(401, "Invalid username or password.")
    if normalize_account_scope(agent.get("account_scope"), fallback_role=agent.get("role")) != ACCOUNT_SCOPE_STAFF:
        raise ApiError(403, "This account does not have admin access.")
    if sanitize_text(agent.get("role")).lower() not in ADMIN_ACCESS_ROLES:
        raise ApiError(403, "This account does not have admin access.")

    return {
        "admin": register_agent_session(username, instance_id, console_status),
        "message": "Login successful.",
    }


def list_agents(*, include_inactive: bool = True) -> dict[str, Any]:
    where_clause = "" if include_inactive else "WHERE is_active = TRUE"
    accounts = run_query(
        f"""
        SELECT id, username, full_name, email, account_scope, role, is_active, metadata
        FROM support_accounts
        {where_clause}
        ORDER BY
          CASE WHEN is_active = TRUE THEN 0 ELSE 1 END,
          CASE account_scope
            WHEN 'staff' THEN 0
            WHEN 'requester' THEN 1
            ELSE 2
          END,
          CASE role
            WHEN 'superadmin' THEN 0
            WHEN 'admin' THEN 1
            WHEN 'coach' THEN 2
            WHEN 'employer' THEN 3
            WHEN 'agent' THEN 4
            WHEN 'user' THEN 5
            ELSE 6
          END,
          full_name ASC NULLS LAST,
          username ASC
        """
    )
    open_assigned_chat_agent_ids = get_open_assigned_live_chat_agent_ids()
    serialized_accounts = [
        serialize_agent(account, open_assigned_chat_agent_ids=open_assigned_chat_agent_ids)
        for account in accounts
    ]

    return {
        "accounts": serialized_accounts,
        "agents": serialized_accounts,
    }


def create_support_account(payload: dict[str, Any]) -> dict[str, Any]:
    actor = require_agent_session_actor(
        payload.get("actorUsername"),
        payload.get("instanceId"),
        allowed_roles=MANAGE_ACCOUNT_ROLES,
    )
    username = sanitize_text(payload.get("username"))
    password = payload.get("password") if isinstance(payload.get("password"), str) else ""
    full_name = sanitize_text(payload.get("fullName")) or username
    email = normalize_account_email(payload.get("email"))
    role = normalize_account_role(payload.get("role"))
    account_scope = derive_account_scope_from_role(role)
    is_active = normalize_bool(payload.get("isActive")) if "isActive" in payload else True

    if not username:
        raise ApiError(400, "Username is required.")
    if not password:
        raise ApiError(400, "Password is required.")
    if account_scope == ACCOUNT_SCOPE_REQUESTER and not email:
        raise ApiError(400, "An email address is required for support requester accounts.")
    if find_agent_account_by_username(username):
        raise ApiError(409, "That username is already in use.")
    if email and find_agent_account_by_email(email):
        raise ApiError(409, "That email address is already in use.")

    metadata = {
        "password_hash": make_password(password),
        "password_updated_at": datetime.now(timezone.utc).isoformat(),
        "created_by_username": actor["username"],
    }
    if not is_active or account_scope != ACCOUNT_SCOPE_STAFF:
        metadata["session_active"] = False
        metadata["console_status"] = DEFAULT_AGENT_CONSOLE_STATUS

    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO support_accounts (
                  username,
                  full_name,
                  email,
                  account_scope,
                  role,
                  is_active,
                  metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                RETURNING id
                """,
                [
                    username,
                    full_name,
                    email,
                    account_scope,
                    role,
                    is_active,
                    json.dumps(metadata),
                ],
            )
            created_row = cursor.fetchone()

    if not created_row:
        raise ApiError(500, "We could not create this support account right now.")

    if account_scope == ACCOUNT_SCOPE_REQUESTER and email:
        link_support_account_to_learner(support_account_id=int(created_row[0]), email=email)

    created_agent = fetch_agent_account_by_id(int(created_row[0]))
    if not created_agent:
        raise ApiError(500, "We could not load the new support account right now.")

    return {
        "account": serialize_agent(created_agent, open_assigned_chat_agent_ids=get_open_assigned_live_chat_agent_ids()),
        "agent": serialize_agent(created_agent, open_assigned_chat_agent_ids=get_open_assigned_live_chat_agent_ids()),
        "message": f"Support account {username} created successfully.",
    }


def update_support_account(agent_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    actor = require_agent_session_actor(
        payload.get("actorUsername"),
        payload.get("instanceId"),
        allowed_roles=MANAGE_ACCOUNT_ROLES,
    )
    existing_agent = fetch_agent_account_by_id(agent_id)
    if not existing_agent:
        raise ApiError(404, "Support account not found.")

    username = sanitize_text(payload.get("username"))
    password = payload.get("password") if isinstance(payload.get("password"), str) else ""
    full_name = sanitize_text(payload.get("fullName")) or username
    email = normalize_account_email(payload.get("email"))
    role = normalize_account_role(payload.get("role"), default=sanitize_text(existing_agent.get("role")).lower() or DEFAULT_ACCOUNT_ROLE)
    account_scope = derive_account_scope_from_role(role)
    is_active = normalize_bool(payload.get("isActive")) if "isActive" in payload else normalize_bool(existing_agent.get("is_active"))

    if not username:
        raise ApiError(400, "Username is required.")
    if not is_active and int(existing_agent["id"]) == int(actor["id"]):
        raise ApiError(400, "You cannot deactivate your own account.")
    if account_scope == ACCOUNT_SCOPE_REQUESTER and not email:
        raise ApiError(400, "An email address is required for support requester accounts.")
    if find_agent_account_by_username(username, exclude_agent_id=agent_id):
        raise ApiError(409, "That username is already in use.")
    if email and find_agent_account_by_email(email, exclude_agent_id=agent_id):
        raise ApiError(409, "That email address is already in use.")

    metadata = normalize_json_object(existing_agent.get("metadata"))
    if password:
        metadata.update(
            {
                "password_hash": make_password(password),
                "password_updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    if not is_active or account_scope != ACCOUNT_SCOPE_STAFF:
        metadata["session_active"] = False
        metadata["console_status"] = DEFAULT_AGENT_CONSOLE_STATUS

    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE support_accounts
                SET username = %s,
                    full_name = %s,
                    email = %s,
                    account_scope = %s,
                    role = %s,
                    is_active = %s,
                    metadata = %s::jsonb,
                    updated_at = NOW()
                WHERE id = %s
                """,
                [
                    username,
                    full_name,
                    email,
                    account_scope,
                    role,
                    is_active,
                    json.dumps(metadata),
                    agent_id,
                ],
            )
        unlink_support_account_from_learners(support_account_id=agent_id)
        if account_scope == ACCOUNT_SCOPE_REQUESTER and email:
            link_support_account_to_learner(support_account_id=agent_id, email=email)

    updated_agent = fetch_agent_account_by_id(agent_id)
    if not updated_agent:
        raise ApiError(500, "We could not load the updated support account right now.")

    return {
        "account": serialize_agent(updated_agent, open_assigned_chat_agent_ids=get_open_assigned_live_chat_agent_ids()),
        "agent": serialize_agent(updated_agent, open_assigned_chat_agent_ids=get_open_assigned_live_chat_agent_ids()),
        "message": f"Support account {username} updated successfully.",
    }


def list_admin_tickets() -> dict[str, Any]:
    sync_open_ticket_inactivity()
    tickets = run_query(
        """
        SELECT
          t.id,
          t.public_id,
          t.category,
          t.inquiry,
          t.technical_subcategory,
          t.status,
          t.status_reason,
          t.priority,
          t.assigned_team,
          t.sla_status,
          t.metadata,
          t.evidence_count,
          t.created_at,
          t.updated_at,
          t.conversation_id,
          c.status AS conversation_status,
          c.metadata AS conversation_metadata,
          c.chat_duration_minutes,
          c.last_message_at,
          l.full_name AS learner_name,
          l.email AS learner_email,
          l.phone AS learner_phone,
          a.id AS assigned_agent_id,
          a.username AS assigned_agent_username,
          a.full_name AS assigned_agent_name
        FROM tickets t
        JOIN learners l
          ON l.id = t.learner_id
        LEFT JOIN conversations c
          ON c.id = t.conversation_id
        LEFT JOIN support_accounts a
          ON a.id = t.assigned_agent_id
        ORDER BY
          CASE t.priority
            WHEN 'Urgent' THEN 0
            WHEN 'High' THEN 1
            WHEN 'Normal' THEN 2
            ELSE 3
          END,
          t.created_at DESC,
          t.id DESC
        """
    )

    tickets = [apply_ticket_sla_policy(ticket, persist=True) for ticket in tickets]
    tickets = sort_tickets_by_priority_and_recency(tickets)
    return {"tickets": [serialize_ticket_summary(ticket) for ticket in tickets]}


def do_transfer_request_payloads_match(left: Any, right: Any) -> bool:
    left_payload = normalize_pending_transfer_request(left)
    right_payload = normalize_pending_transfer_request(right)
    if not left_payload or not right_payload:
        return False

    return (
        int(left_payload["fromAgentId"]) == int(right_payload["fromAgentId"])
        and int(left_payload["toAgentId"]) == int(right_payload["toAgentId"])
        and sanitize_text(left_payload["requestedAt"]) == sanitize_text(right_payload["requestedAt"])
    )


def do_escalation_notification_payloads_match(left: Any, right: Any) -> bool:
    left_payload = normalize_pending_escalation_notification(left)
    right_payload = normalize_pending_escalation_notification(right)
    if not left_payload or not right_payload:
        return False

    return (
        int(left_payload["toAgentId"]) == int(right_payload["toAgentId"])
        and sanitize_text(left_payload["ticketId"]) == sanitize_text(right_payload["ticketId"])
        and sanitize_text(left_payload["requestedAt"]) == sanitize_text(right_payload["requestedAt"])
    )


def do_teams_call_notification_payloads_match(left: Any, right: Any) -> bool:
    left_payload = normalize_pending_teams_call_notification(left)
    right_payload = normalize_pending_teams_call_notification(right)
    if not left_payload or not right_payload:
        return False

    return (
        int(left_payload["toAgentId"]) == int(right_payload["toAgentId"])
        and sanitize_text(left_payload["ticketId"]) == sanitize_text(right_payload["ticketId"])
        and sanitize_text(left_payload["requestedAt"]) == sanitize_text(right_payload["requestedAt"])
    )


def do_escalation_closure_payloads_match(left: Any, right: Any) -> bool:
    left_payload = normalize_latest_escalation_closure(left)
    right_payload = normalize_latest_escalation_closure(right)
    if not left_payload or not right_payload:
        return False

    return (
        int(left_payload["fromAgentId"]) == int(right_payload["fromAgentId"])
        and int(left_payload["toAgentId"]) == int(right_payload["toAgentId"])
        and sanitize_text(left_payload["ticketId"]) == sanitize_text(right_payload["ticketId"])
        and sanitize_text(left_payload["requestedAt"]) == sanitize_text(right_payload["requestedAt"])
        and sanitize_text(left_payload["closedAt"]) == sanitize_text(right_payload["closedAt"])
    )


def is_current_admin_notification_history_item(event_type: Any, payload: Any, ticket_metadata: Any) -> bool:
    normalized_event_type = sanitize_text(event_type)
    normalized_ticket_metadata = normalize_json_object(ticket_metadata)

    if normalized_event_type == "transfer_requested":
        return do_transfer_request_payloads_match(
            payload,
            normalized_ticket_metadata.get(PENDING_TRANSFER_REQUEST_METADATA_KEY),
        )

    if normalized_event_type == "escalation_notified":
        return do_escalation_notification_payloads_match(
            payload,
            normalized_ticket_metadata.get(PENDING_ESCALATION_NOTIFICATION_METADATA_KEY),
        )

    if normalized_event_type == "teams_call_requested":
        return do_teams_call_notification_payloads_match(
            payload,
            normalized_ticket_metadata.get(PENDING_TEAMS_CALL_NOTIFICATION_METADATA_KEY),
        )

    if normalized_event_type == "escalation_closed":
        latest_escalation_closure = get_latest_escalation_closure(normalized_ticket_metadata)
        return bool(
            latest_escalation_closure
            and not normalize_bool(latest_escalation_closure.get("requesterAcknowledged"))
            and do_escalation_closure_payloads_match(payload, latest_escalation_closure)
        )

    if normalized_event_type in {"transfer_request_accepted", "transfer_request_rejected"}:
        latest_transfer_decision = get_latest_transfer_decision(normalized_ticket_metadata)
        return bool(
            latest_transfer_decision
            and not normalize_bool(latest_transfer_decision.get("requesterAcknowledged"))
            and sanitize_text(latest_transfer_decision.get("status")) == normalized_event_type.replace("transfer_request_", "")
            and do_transfer_request_payloads_match(payload, latest_transfer_decision)
        )

    return False


def serialize_admin_notification_log_item(row: dict[str, Any]) -> dict[str, Any]:
    ticket_metadata = normalize_json_object(row.get("metadata"))
    conversation_metadata = normalize_json_object(row.get("conversation_metadata"))
    normalized_payload = normalize_history_payload(
        row.get("payload"),
        ticket_public_id=row.get("public_id"),
        conversation_id=row.get("conversation_id"),
        conversation_metadata=conversation_metadata,
    )

    return {
        "id": int(row["id"]),
        "eventType": row["event_type"],
        "actorType": row["actor_type"],
        "actorLabel": row.get("actor_label"),
        "payload": normalized_payload,
        "createdAt": row["created_at"],
        "ticketId": row["public_id"],
        "chatId": build_public_chat_id(row.get("public_id"), row.get("conversation_id"), conversation_metadata),
        "learnerName": row.get("learner_name") or "",
        "email": row.get("learner_email") or "",
        "requesterRole": get_ticket_requester_role(ticket_metadata),
        "status": row["status"],
        "statusReason": row.get("status_reason") or "",
        "isCurrent": is_current_admin_notification_history_item(row.get("event_type"), normalized_payload, ticket_metadata),
    }


def list_admin_notifications(actor_username: Any, instance_id: Any, *, limit: Any = 25) -> dict[str, Any]:
    actor = require_agent_session_actor(actor_username, instance_id, allowed_roles=ADMIN_ACCESS_ROLES)
    actor_id = str(int(actor["id"]))
    resolved_limit = max(1, min(parse_int(limit, 25), 50))
    notifications = run_query(
        """
        SELECT
          h.id,
          h.event_type,
          h.actor_type,
          h.actor_label,
          h.payload,
          h.created_at,
          t.public_id,
          t.status,
          t.status_reason,
          t.metadata,
          t.conversation_id,
          c.metadata AS conversation_metadata,
          l.full_name AS learner_name,
          l.email AS learner_email
        FROM ticket_history h
        JOIN tickets t
          ON t.id = h.ticket_id
        JOIN learners l
          ON l.id = t.learner_id
        LEFT JOIN conversations c
          ON c.id = t.conversation_id
        WHERE
          (h.event_type = 'transfer_requested' AND COALESCE(h.payload ->> 'toAgentId', '') = %s)
          OR (h.event_type = 'escalation_notified' AND COALESCE(h.payload ->> 'toAgentId', '') = %s)
          OR (h.event_type = 'teams_call_requested' AND COALESCE(h.payload ->> 'toAgentId', '') = %s)
          OR (h.event_type = 'escalation_closed' AND COALESCE(h.payload ->> 'fromAgentId', '') = %s)
          OR (h.event_type = 'transfer_request_accepted' AND COALESCE(h.payload ->> 'fromAgentId', '') = %s)
          OR (h.event_type = 'transfer_request_rejected' AND COALESCE(h.payload ->> 'fromAgentId', '') = %s)
        ORDER BY h.created_at DESC, h.id DESC
        LIMIT %s
        """,
        [actor_id, actor_id, actor_id, actor_id, actor_id, actor_id, resolved_limit],
    )

    return {"notifications": [serialize_admin_notification_log_item(row) for row in notifications]}


def get_admin_ticket_detail_response(public_id: str) -> dict[str, Any]:
    if not public_id:
        raise ApiError(400, "Ticket id is required.")

    sync_open_ticket_inactivity(public_id=public_id)
    detail = fetch_admin_ticket_detail(public_id)
    if not detail:
        raise ApiError(404, "Ticket not found.")

    return detail


def request_support_teams_call(public_id: str) -> dict[str, Any]:
    if not public_id:
        raise ApiError(400, "Ticket id is required.")

    configured_url = sanitize_text(settings.SUPPORT_TEAMS_CALL_URL)
    targets = get_support_teams_call_targets(include_booking_fallback=not bool(configured_url))
    target_agent = resolve_support_teams_call_notification_target(targets)
    if not target_agent:
        raise ApiError(503, "Microsoft Teams calling is not linked to a support admin right now.")

    with transaction.atomic():
        ticket = run_query_one(
            """
            SELECT
              t.id,
              t.public_id,
              t.metadata,
              t.assigned_agent_id,
              t.assigned_team,
              t.conversation_id,
              l.full_name AS learner_name,
              l.email AS learner_email
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

        ticket_metadata = normalize_json_object(ticket.get("metadata"))
        requester_role = get_ticket_requester_role(ticket_metadata)
        if not is_quick_ticket_only_requester_role(requester_role):
            raise ApiError(403, "Coach accounts can only submit quick tickets or quick calls from the support portal.")

        pending_notification = get_pending_teams_call_notification(ticket_metadata)
        already_notified = bool(pending_notification)
        if not pending_notification:
            pending_notification = {
                "toAgentId": int(target_agent["id"]),
                "toAgentName": target_agent.get("full_name") or target_agent["username"],
                "toAgentUsername": target_agent["username"],
                "requesterName": sanitize_text(ticket.get("learner_name")) or sanitize_text(ticket.get("learner_email")) or "Coach",
                "requesterEmail": sanitize_text(ticket.get("learner_email")),
                "requesterRole": requester_role,
                "note": "Coach requested a direct Microsoft Teams support call from the support portal.",
                "targetLabel": get_support_teams_call_label(targets),
                "ticketId": ticket["public_id"],
                "requestedAt": serialize_datetime_value(datetime.now(timezone.utc)),
            }
            ticket_metadata[PENDING_TEAMS_CALL_NOTIFICATION_METADATA_KEY] = pending_notification
        ticket_metadata[TEAMS_CALL_REQUESTED_METADATA_KEY] = True
        next_assigned_team = derive_assigned_team(target_agent)

        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE tickets
                SET assigned_agent_id = %s,
                    assigned_team = %s,
                    metadata = %s::jsonb,
                    updated_at = NOW()
                WHERE id = %s
                """,
                [target_agent["id"], next_assigned_team, json.dumps(ticket_metadata), ticket["id"]],
            )

            if ticket.get("conversation_id"):
                cursor.execute(
                    """
                    UPDATE conversations
                    SET metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb
                    WHERE id = %s
                    """,
                    [
                        json.dumps(
                            {
                                "assigned_agent_id": int(target_agent["id"]),
                                "assigned_team": next_assigned_team,
                            }
                        ),
                        ticket["conversation_id"],
                    ],
                )

        if not already_notified:
            insert_history_event(
                int(ticket["id"]),
                "teams_call_requested",
                {"role": requester_role, "label": ticket.get("learner_email") or "learner"},
                pending_notification,
            )
        if int(ticket.get("assigned_agent_id") or 0) != int(target_agent["id"]):
            insert_history_event(
                int(ticket["id"]),
                "assignment_changed",
                {"role": requester_role, "label": ticket.get("learner_email") or "learner"},
                {
                    "fromAgentId": ticket.get("assigned_agent_id"),
                    "toAgentId": int(target_agent["id"]),
                    "toAgentName": target_agent.get("full_name") or target_agent["username"],
                },
            )

    return {
        "ok": True,
        "message": (
            "The support admin has already been notified about this Teams call request."
            if already_notified
            else "The support admin has been notified about this Teams call request."
        ),
        "ticketId": public_id,
        "notificationPending": True,
    }


def clear_prepared_support_teams_call(ticket: dict[str, Any]) -> bool:
    ticket_metadata = normalize_json_object(ticket.get("metadata"))
    pending_notification = get_pending_teams_call_notification(ticket_metadata)
    current_assigned_agent_id = parse_assigned_agent_id(ticket.get("assigned_agent_id"))
    prepared_agent_id = parse_assigned_agent_id(pending_notification.get("toAgentId")) if pending_notification else None

    if prepared_agent_id is None:
        target_agent = resolve_support_teams_call_notification_target()
        prepared_agent_id = int(target_agent["id"]) if target_agent else None

    should_clear_assignment = bool(
        current_assigned_agent_id
        and prepared_agent_id
        and current_assigned_agent_id == prepared_agent_id
    )

    if not pending_notification and not should_clear_assignment:
        return False

    ticket_metadata.pop(PENDING_TEAMS_CALL_NOTIFICATION_METADATA_KEY, None)
    next_assigned_agent_id = None if should_clear_assignment else current_assigned_agent_id
    next_assigned_team = "Unassigned" if should_clear_assignment else (sanitize_text(ticket.get("assigned_team")) or "Unassigned")

    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE tickets
            SET assigned_agent_id = %s,
                assigned_team = %s,
                metadata = %s::jsonb,
                updated_at = NOW()
            WHERE id = %s
            """,
            [
                next_assigned_agent_id,
                next_assigned_team,
                json.dumps(ticket_metadata),
                ticket["id"],
            ],
        )

        if ticket.get("conversation_id") and should_clear_assignment:
            cursor.execute(
                """
                UPDATE conversations
                SET metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb
                WHERE id = %s
                """,
                [
                    json.dumps(
                        {
                            "assigned_agent_id": None,
                            "assigned_agent_username": None,
                            "assigned_agent_name": None,
                        }
                    ),
                    ticket["conversation_id"],
                ],
            )

    ticket["metadata"] = ticket_metadata
    if should_clear_assignment:
        ticket["assigned_agent_id"] = None
        ticket["assigned_team"] = "Unassigned"
        ticket["assigned_agent_username"] = None
        ticket["assigned_agent_name"] = None

    return True


def request_ticket_transfer(public_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    actor_username = sanitize_text(payload.get("actorUsername")).lower()
    reason = sanitize_text(payload.get("reason"))
    target_agent_id = parse_assigned_agent_id(payload.get("targetAgentId"))

    if not public_id:
        raise ApiError(400, "Ticket id is required.")
    if target_agent_id is None:
        raise ApiError(400, "Select an admin to receive this transfer.")
    if not reason:
        raise ApiError(400, "Add a transfer reason before sending this request.")

    with transaction.atomic():
        ticket = run_query_one(
            """
            SELECT
              t.id,
              t.public_id,
              t.assigned_agent_id,
              t.assigned_team,
              t.metadata,
              t.conversation_id,
              a.username AS assigned_agent_username,
              a.full_name AS assigned_agent_name
            FROM tickets t
            LEFT JOIN support_accounts a
              ON a.id = t.assigned_agent_id
            WHERE t.public_id = %s
            LIMIT 1
            """,
            [public_id],
        )

        if not ticket:
            raise ApiError(404, "Ticket not found.")
        if not ticket.get("assigned_agent_id"):
            raise ApiError(409, "Only assigned tickets can be transferred.")
        if actor_username and sanitize_text(ticket.get("assigned_agent_username")).lower() != actor_username:
            raise ApiError(403, "Only the assigned admin can request this transfer.")
        if get_pending_transfer_request(ticket.get("metadata")):
            raise ApiError(409, "A transfer request is already pending for this ticket.")

        target_agent = run_query_one(
            """
            SELECT id, username, full_name, email, role
            FROM support_accounts
            WHERE id = %s
              AND is_active = TRUE
            LIMIT 1
            """,
            [target_agent_id],
        )

        if not target_agent:
            raise ApiError(400, "The selected admin does not exist.")
        if int(ticket["assigned_agent_id"]) == int(target_agent["id"]):
            raise ApiError(400, "This ticket is already assigned to the selected admin.")

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

        requested_at = datetime.now(timezone.utc)
        pending_transfer_request = {
            "fromAgentId": int(ticket["assigned_agent_id"]),
            "fromAgentName": ticket.get("assigned_agent_name") or ticket.get("assigned_agent_username") or "Support Admin",
            "fromAgentUsername": ticket.get("assigned_agent_username") or "",
            "toAgentId": int(target_agent["id"]),
            "toAgentName": target_agent.get("full_name") or target_agent["username"],
            "toAgentUsername": target_agent["username"],
            "reason": reason,
            "requestedAt": serialize_datetime_value(requested_at),
        }
        ticket_metadata = normalize_json_object(ticket.get("metadata"))
        ticket_metadata[PENDING_TRANSFER_REQUEST_METADATA_KEY] = pending_transfer_request
        ticket_metadata.pop(LATEST_TRANSFER_DECISION_METADATA_KEY, None)

        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE tickets
                SET metadata = %s::jsonb,
                    updated_at = NOW()
                WHERE id = %s
                """,
                [json.dumps(ticket_metadata), ticket["id"]],
            )

        insert_history_event(
            int(ticket["id"]),
            "transfer_requested",
            actor,
            pending_transfer_request,
        )
        insert_history_event(
            int(ticket["id"]),
            "internal_note",
            actor,
            {"note": f"Transfer to {pending_transfer_request['toAgentName']}. Reason: {reason}"},
        )

    detail = fetch_admin_ticket_detail(public_id)
    if not detail:
        raise ApiError(404, "Ticket not found.")

    return detail


def accept_ticket_transfer_request(public_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    actor_username = sanitize_text(payload.get("actorUsername")).lower()

    if not public_id:
        raise ApiError(400, "Ticket id is required.")
    if not actor_username:
        raise ApiError(403, "Admin sign-in is required.")

    with transaction.atomic():
        ticket = run_query_one(
            """
            SELECT
              t.id,
              t.public_id,
              t.assigned_agent_id,
              t.assigned_team,
              t.metadata,
              t.conversation_id,
              a.username AS assigned_agent_username,
              a.full_name AS assigned_agent_name
            FROM tickets t
            LEFT JOIN support_accounts a
              ON a.id = t.assigned_agent_id
            WHERE t.public_id = %s
            LIMIT 1
            """,
            [public_id],
        )

        if not ticket:
            raise ApiError(404, "Ticket not found.")

        pending_transfer_request = get_pending_transfer_request(ticket.get("metadata"))
        if not pending_transfer_request:
            raise ApiError(409, "There is no pending transfer request for this ticket.")

        actor_row = fetch_actor_by_username(actor_username)
        if not actor_row or int(actor_row["id"]) != int(pending_transfer_request["toAgentId"]):
            raise ApiError(403, "Only the requested admin can accept this transfer.")

        if int(ticket.get("assigned_agent_id") or 0) != int(pending_transfer_request["fromAgentId"]):
            raise ApiError(409, "This transfer request is no longer valid.")

        target_agent = run_query_one(
            """
            SELECT id, username, full_name, email, role
            FROM support_accounts
            WHERE id = %s
              AND is_active = TRUE
            LIMIT 1
            """,
            [pending_transfer_request["toAgentId"]],
        )

        if not target_agent:
            raise ApiError(409, "The requested admin is no longer available.")

        actor = {
            "id": actor_row["id"],
            "role": actor_row["role"],
            "label": actor_row.get("full_name") or actor_row["username"],
        }
        next_assigned_team = derive_assigned_team(target_agent)
        ticket_metadata = normalize_json_object(ticket.get("metadata"))
        ticket_metadata.pop(PENDING_TRANSFER_REQUEST_METADATA_KEY, None)
        ticket_metadata[LATEST_TRANSFER_DECISION_METADATA_KEY] = {
            **pending_transfer_request,
            "status": "accepted",
            "decidedAt": serialize_datetime_value(datetime.now(timezone.utc)),
            "decidedById": int(actor_row["id"]),
            "decidedByName": actor_row.get("full_name") or actor_row["username"],
            "decidedByUsername": actor_row["username"],
            "requesterAcknowledged": False,
        }

        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE tickets
                SET assigned_agent_id = %s,
                    assigned_team = %s,
                    metadata = %s::jsonb,
                    updated_at = NOW()
                WHERE id = %s
                """,
                [target_agent["id"], next_assigned_team, json.dumps(ticket_metadata), ticket["id"]],
            )

            if ticket.get("conversation_id"):
                cursor.execute(
                    """
                    UPDATE conversations
                    SET metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb
                    WHERE id = %s
                    """,
                    [
                        json.dumps(
                            {
                                "assigned_agent_id": int(target_agent["id"]),
                                "assigned_team": next_assigned_team,
                            }
                        ),
                        ticket["conversation_id"],
                    ],
                )

        insert_history_event(int(ticket["id"]), "transfer_request_accepted", actor, pending_transfer_request)
        insert_history_event(
            int(ticket["id"]),
            "assignment_changed",
            actor,
            {
                "fromAgentId": ticket.get("assigned_agent_id"),
                "toAgentId": int(target_agent["id"]),
                "toAgentName": target_agent.get("full_name") or target_agent["username"],
            },
        )

    detail = fetch_admin_ticket_detail(public_id)
    if not detail:
        raise ApiError(404, "Ticket not found.")

    return detail


def reject_ticket_transfer_request(public_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    actor_username = sanitize_text(payload.get("actorUsername")).lower()

    if not public_id:
        raise ApiError(400, "Ticket id is required.")
    if not actor_username:
        raise ApiError(403, "Admin sign-in is required.")

    with transaction.atomic():
        ticket = run_query_one(
            """
            SELECT
              t.id,
              t.public_id,
              t.metadata
            FROM tickets t
            WHERE t.public_id = %s
            LIMIT 1
            """,
            [public_id],
        )

        if not ticket:
            raise ApiError(404, "Ticket not found.")

        pending_transfer_request = get_pending_transfer_request(ticket.get("metadata"))
        if not pending_transfer_request:
            raise ApiError(409, "There is no pending transfer request for this ticket.")

        actor_row = fetch_actor_by_username(actor_username)
        if not actor_row or int(actor_row["id"]) != int(pending_transfer_request["toAgentId"]):
            raise ApiError(403, "Only the requested admin can reject this transfer.")

        actor = {
            "id": actor_row["id"],
            "role": actor_row["role"],
            "label": actor_row.get("full_name") or actor_row["username"],
        }
        ticket_metadata = normalize_json_object(ticket.get("metadata"))
        ticket_metadata.pop(PENDING_TRANSFER_REQUEST_METADATA_KEY, None)
        ticket_metadata[LATEST_TRANSFER_DECISION_METADATA_KEY] = {
            **pending_transfer_request,
            "status": "rejected",
            "decidedAt": serialize_datetime_value(datetime.now(timezone.utc)),
            "decidedById": int(actor_row["id"]),
            "decidedByName": actor_row.get("full_name") or actor_row["username"],
            "decidedByUsername": actor_row["username"],
            "requesterAcknowledged": False,
        }

        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE tickets
                SET metadata = %s::jsonb,
                    updated_at = NOW()
                WHERE id = %s
                """,
                [json.dumps(ticket_metadata), ticket["id"]],
            )

        insert_history_event(int(ticket["id"]), "transfer_request_rejected", actor, pending_transfer_request)

    detail = fetch_admin_ticket_detail(public_id)
    if not detail:
        raise ApiError(404, "Ticket not found.")

    return detail


def acknowledge_ticket_transfer_decision(public_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    actor_username = sanitize_text(payload.get("actorUsername")).lower()

    if not public_id:
        raise ApiError(400, "Ticket id is required.")
    if not actor_username:
        raise ApiError(403, "Admin sign-in is required.")

    with transaction.atomic():
        ticket = run_query_one(
            """
            SELECT
              t.id,
              t.public_id,
              t.metadata
            FROM tickets t
            WHERE t.public_id = %s
            LIMIT 1
            """,
            [public_id],
        )

        if not ticket:
            raise ApiError(404, "Ticket not found.")

        latest_transfer_decision = get_latest_transfer_decision(ticket.get("metadata"))
        if not latest_transfer_decision:
            raise ApiError(409, "There is no transfer update to acknowledge.")

        actor_row = fetch_actor_by_username(actor_username)
        if not actor_row or int(actor_row["id"]) != int(latest_transfer_decision["fromAgentId"]):
            raise ApiError(403, "Only the requesting admin can acknowledge this transfer update.")

        if latest_transfer_decision.get("requesterAcknowledged"):
            return fetch_admin_ticket_detail(public_id) or {"ticket": {"id": public_id}}

        ticket_metadata = normalize_json_object(ticket.get("metadata"))
        ticket_metadata[LATEST_TRANSFER_DECISION_METADATA_KEY] = {
            **latest_transfer_decision,
            "requesterAcknowledged": True,
        }

        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE tickets
                SET metadata = %s::jsonb,
                    updated_at = NOW()
                WHERE id = %s
                """,
                [json.dumps(ticket_metadata), ticket["id"]],
            )

    detail = fetch_admin_ticket_detail(public_id)
    if not detail:
        raise ApiError(404, "Ticket not found.")

    return detail


def acknowledge_ticket_teams_call_notification(public_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    actor_username = sanitize_text(payload.get("actorUsername")).lower()

    if not public_id:
        raise ApiError(400, "Ticket id is required.")
    if not actor_username:
        raise ApiError(403, "Admin sign-in is required.")

    with transaction.atomic():
        ticket = run_query_one(
            """
            SELECT
              t.id,
              t.public_id,
              t.metadata
            FROM tickets t
            WHERE t.public_id = %s
            LIMIT 1
            """,
            [public_id],
        )

        if not ticket:
            raise ApiError(404, "Ticket not found.")

        pending_teams_call_notification = get_pending_teams_call_notification(ticket.get("metadata"))
        if not pending_teams_call_notification:
            raise ApiError(409, "There is no Teams call notification to acknowledge.")

        actor_row = fetch_actor_by_username(actor_username)
        if not actor_row or int(actor_row["id"]) != int(pending_teams_call_notification["toAgentId"]):
            raise ApiError(403, "Only the notified admin can open this Teams call request.")

        ticket_metadata = normalize_json_object(ticket.get("metadata"))
        ticket_metadata.pop(PENDING_TEAMS_CALL_NOTIFICATION_METADATA_KEY, None)

        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE tickets
                SET metadata = %s::jsonb,
                    updated_at = NOW()
                WHERE id = %s
                """,
                [json.dumps(ticket_metadata), ticket["id"]],
            )

    detail = fetch_admin_ticket_detail(public_id)
    if not detail:
        raise ApiError(404, "Ticket not found.")

    return detail


def acknowledge_ticket_escalation_notification(public_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    actor_username = sanitize_text(payload.get("actorUsername")).lower()

    if not public_id:
        raise ApiError(400, "Ticket id is required.")
    if not actor_username:
        raise ApiError(403, "Admin sign-in is required.")

    with transaction.atomic():
        ticket = run_query_one(
            """
            SELECT
              t.id,
              t.public_id,
              t.metadata
            FROM tickets t
            WHERE t.public_id = %s
            LIMIT 1
            """,
            [public_id],
        )

        if not ticket:
            raise ApiError(404, "Ticket not found.")

        pending_escalation_notification = get_pending_escalation_notification(ticket.get("metadata"))
        if not pending_escalation_notification:
            raise ApiError(409, "There is no escalation notification to acknowledge.")

        actor_row = fetch_actor_by_username(actor_username)
        if not actor_row or int(actor_row["id"]) != int(pending_escalation_notification["toAgentId"]):
            raise ApiError(403, "Only the notified admin can dismiss this escalation.")

        ticket_metadata = normalize_json_object(ticket.get("metadata"))
        ticket_metadata.pop(PENDING_ESCALATION_NOTIFICATION_METADATA_KEY, None)

        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE tickets
                SET metadata = %s::jsonb,
                    updated_at = NOW()
                WHERE id = %s
                """,
                [json.dumps(ticket_metadata), ticket["id"]],
            )

    detail = fetch_admin_ticket_detail(public_id)
    if not detail:
        raise ApiError(404, "Ticket not found.")

    return detail


def acknowledge_ticket_escalation_closure(public_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    actor_username = sanitize_text(payload.get("actorUsername")).lower()

    if not public_id:
        raise ApiError(400, "Ticket id is required.")
    if not actor_username:
        raise ApiError(403, "Admin sign-in is required.")

    with transaction.atomic():
        ticket = run_query_one(
            """
            SELECT
              t.id,
              t.public_id,
              t.metadata
            FROM tickets t
            WHERE t.public_id = %s
            LIMIT 1
            """,
            [public_id],
        )

        if not ticket:
            raise ApiError(404, "Ticket not found.")

        latest_escalation_closure = get_latest_escalation_closure(ticket.get("metadata"))
        if not latest_escalation_closure:
            raise ApiError(409, "There is no escalation closure update to acknowledge.")

        actor_row = fetch_actor_by_username(actor_username)
        if not actor_row or int(actor_row["id"]) != int(latest_escalation_closure["fromAgentId"]):
            raise ApiError(403, "Only the original admin can acknowledge this escalation update.")

        if latest_escalation_closure.get("requesterAcknowledged"):
            return fetch_admin_ticket_detail(public_id) or {"ticket": {"id": public_id}}

        ticket_metadata = normalize_json_object(ticket.get("metadata"))
        ticket_metadata[LATEST_ESCALATION_CLOSURE_METADATA_KEY] = {
            **latest_escalation_closure,
            "requesterAcknowledged": True,
        }

        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE tickets
                SET metadata = %s::jsonb,
                    updated_at = NOW()
                WHERE id = %s
                """,
                [json.dumps(ticket_metadata), ticket["id"]],
            )

    detail = fetch_admin_ticket_detail(public_id)
    if not detail:
        raise ApiError(404, "Ticket not found.")

    return detail


def get_latest_ticket_escalation_notification(ticket_id: Any, actor_id: Any) -> dict[str, Any] | None:
    normalized_actor_id = parse_assigned_agent_id(actor_id)
    if not ticket_id or normalized_actor_id is None:
        return None

    row = run_query_one(
        """
        SELECT
          h.payload,
          h.actor_id,
          h.actor_label,
          actor.username AS actor_username,
          actor.full_name AS actor_full_name,
          target.username AS to_agent_username
        FROM ticket_history h
        LEFT JOIN support_accounts actor
          ON actor.id = h.actor_id
        LEFT JOIN support_accounts target
          ON target.id = CASE
            WHEN COALESCE(h.payload ->> 'toAgentId', '') ~ '^[0-9]+$'
              THEN CAST(h.payload ->> 'toAgentId' AS INTEGER)
            ELSE NULL
          END
        WHERE h.ticket_id = %s
          AND h.event_type = 'escalation_notified'
          AND COALESCE(h.payload ->> 'toAgentId', '') = %s
        ORDER BY h.created_at DESC, h.id DESC
        LIMIT 1
        """,
        [ticket_id, str(normalized_actor_id)],
    )
    if not row:
        return None

    payload = normalize_json_object(row.get("payload"))
    return normalize_pending_escalation_notification(
        {
            **payload,
            "fromAgentId": payload.get("fromAgentId") or row.get("actor_id"),
            "fromAgentName": payload.get("fromAgentName") or row.get("actor_full_name") or row.get("actor_label"),
            "fromAgentUsername": payload.get("fromAgentUsername") or row.get("actor_username"),
            "toAgentUsername": payload.get("toAgentUsername") or row.get("to_agent_username"),
        }
    )


def create_follow_up_ticket_from_source_ticket(
    ticket: dict[str, Any],
    *,
    actor_row: dict[str, Any] | None,
    requested_inquiry: str = "",
) -> str:
    if not ticket.get("conversation_id"):
        raise ApiError(400, "This ticket is not linked to a chat conversation.")
    if sanitize_text(ticket.get("status")) == "Open":
        raise ApiError(409, "Move the current ticket to Pending or Closed before creating a follow-up ticket for this chat.")
    if is_ticket_chat_closed(ticket.get("status"), ticket.get("conversation_status")):
        raise ApiError(409, "This chat has already been closed. Start a new chat instead of creating a follow-up ticket.")

    actor = (
        {
            "id": actor_row["id"],
            "role": actor_row["role"],
            "label": actor_row.get("full_name") or actor_row["username"],
        }
        if actor_row
        else {"role": "system", "label": "support_portal"}
    )

    next_inquiry = requested_inquiry or sanitize_text(ticket.get("inquiry"))
    if not next_inquiry:
        raise ApiError(400, "Inquiry details are required.")

    ticket_metadata = normalize_json_object(ticket.get("metadata"))
    conversation_metadata = normalize_json_object(ticket.get("conversation_metadata"))
    requester_role = get_ticket_requester_role(
        ticket_metadata,
        default=get_ticket_requester_role(conversation_metadata),
    )
    next_priority = derive_requester_ticket_priority(requester_role, ticket.get("priority"))
    requester_account_id_value = ticket_metadata.get("requester_account_id")
    if requester_account_id_value in (None, ""):
        requester_account_id_value = conversation_metadata.get("requester_account_id")
    try:
        requester_account_id = int(str(requester_account_id_value).strip()) if requester_account_id_value not in (None, "") else None
    except (TypeError, ValueError):
        requester_account_id = None
    requester_username = sanitize_text(ticket_metadata.get("requester_username"))
    if not requester_username:
        requester_username = sanitize_text(conversation_metadata.get("requester_username"))
    chat_public_id = build_public_chat_id(
        ticket.get("public_id"),
        ticket.get("conversation_id"),
        ticket.get("conversation_metadata"),
    )
    pending_escalation_notification = get_pending_escalation_notification(ticket_metadata)
    draft_public_id = f"TMP-{int(datetime.now().timestamp() * 1000)}-{uuid4().hex[:8]}"

    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO tickets (
              public_id,
              learner_id,
              conversation_id,
              category,
              technical_subcategory,
              inquiry,
              status,
              status_reason,
              assigned_agent_id,
              assigned_team,
              priority,
              evidence_count,
              metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING id
            """,
            [
                draft_public_id,
                ticket["learner_id"],
                ticket["conversation_id"],
                ticket["category"],
                ticket.get("technical_subcategory") or None,
                next_inquiry,
                "Open",
                "",
                ticket.get("assigned_agent_id"),
                ticket.get("assigned_team") or "Unassigned",
                next_priority,
                0,
                json.dumps(
                    {
                        "source": "support_portal_follow_up",
                        "parent_ticket_public_id": ticket["public_id"],
                        "chat_public_id": chat_public_id,
                        "technical_subcategory": ticket.get("technical_subcategory") or None,
                        "requester_role": requester_role,
                        "requester_account_id": requester_account_id,
                        "requester_username": requester_username,
                    }
                ),
            ],
        )
        new_ticket_row = dictfetchone(cursor)
        if not new_ticket_row:
            raise ApiError(500, "We could not create the follow-up ticket right now.")

        new_public_id = build_public_ticket_id(int(new_ticket_row["id"]))
        cursor.execute(
            """
            UPDATE tickets
            SET public_id = %s, updated_at = NOW()
            WHERE id = %s
            """,
            [new_public_id, new_ticket_row["id"]],
        )

        if pending_escalation_notification:
            next_new_ticket_metadata = {
                "source": "support_portal_follow_up",
                "parent_ticket_public_id": ticket["public_id"],
                "chat_public_id": chat_public_id,
                "technical_subcategory": ticket.get("technical_subcategory") or None,
                "requester_role": requester_role,
                "requester_account_id": requester_account_id,
                "requester_username": requester_username,
                PENDING_ESCALATION_NOTIFICATION_METADATA_KEY: {
                    **pending_escalation_notification,
                    "ticketId": new_public_id,
                },
            }
            cursor.execute(
                """
                UPDATE tickets
                SET metadata = %s::jsonb,
                    updated_at = NOW()
                WHERE id = %s
                """,
                [json.dumps(next_new_ticket_metadata), new_ticket_row["id"]],
            )

            ticket_metadata.pop(PENDING_ESCALATION_NOTIFICATION_METADATA_KEY, None)
            cursor.execute(
                """
                UPDATE tickets
                SET metadata = %s::jsonb,
                    updated_at = NOW()
                WHERE id = %s
                """,
                [json.dumps(ticket_metadata), ticket["id"]],
            )

        cursor.execute(
            """
            UPDATE conversations
            SET status = 'open',
                last_message_at = NOW(),
                metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb
            WHERE id = %s
            """,
            [
                json.dumps(
                    {
                        "chat_public_id": chat_public_id or new_public_id,
                        "latest_ticket_public_id": new_public_id,
                        "parent_ticket_public_id": ticket["public_id"],
                    }
                ),
                ticket["conversation_id"],
            ],
        )

    insert_history_event(
        int(new_ticket_row["id"]),
        "ticket_created",
        actor,
        {
            "category": ticket["category"],
            "technical_subcategory": ticket.get("technical_subcategory") or None,
            "followUpFrom": ticket["public_id"],
            "chatId": chat_public_id or new_public_id,
        },
    )
    insert_history_event(
        int(ticket["id"]),
        "follow_up_ticket_created",
        actor,
        {
            "newTicketId": new_public_id,
            "chatId": chat_public_id or new_public_id,
        },
    )

    return new_public_id


def create_follow_up_ticket(public_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    actor_username = sanitize_text(payload.get("actorUsername")).lower()
    requested_inquiry = sanitize_text(payload.get("inquiry"))

    if not public_id:
        raise ApiError(400, "Ticket id is required.")

    with transaction.atomic():
        ticket = run_query_one(
            """
            SELECT
              t.id,
              t.public_id,
              t.learner_id,
              t.conversation_id,
              t.category,
              t.technical_subcategory,
              t.inquiry,
              t.status,
              t.priority,
              t.assigned_agent_id,
              t.assigned_team,
              t.metadata,
              c.status AS conversation_status,
              c.metadata AS conversation_metadata
            FROM tickets t
            LEFT JOIN conversations c
              ON c.id = t.conversation_id
            WHERE t.public_id = %s
            LIMIT 1
            """,
            [public_id],
        )

        if not ticket:
            raise ApiError(404, "Ticket not found.")

        actor_row = fetch_actor_by_username(actor_username) if actor_username else None
        new_public_id = create_follow_up_ticket_from_source_ticket(
            ticket,
            actor_row=actor_row,
            requested_inquiry=requested_inquiry,
        )

    detail = fetch_admin_ticket_detail(new_public_id)
    if not detail:
        raise ApiError(500, "We could not load the follow-up ticket.")

    return detail


def send_admin_ai_agent_message(public_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    message = sanitize_text(payload.get("message"))
    actor_username = sanitize_text(payload.get("actorUsername")).lower()
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
          t.metadata,
          t.category,
          t.technical_subcategory,
          t.inquiry,
          t.status,
          t.status_reason,
          t.priority,
          t.assigned_team,
          t.metadata,
          c.metadata AS conversation_metadata,
          l.id AS learner_id,
          l.full_name AS learner_full_name,
          l.email AS learner_email,
          l.phone AS learner_phone
        FROM tickets t
        JOIN learners l
          ON l.id = t.learner_id
        LEFT JOIN conversations c
          ON c.id = t.conversation_id
        WHERE t.public_id = %s
        LIMIT 1
        """,
        [public_id],
    )

    if not ticket:
        raise ApiError(404, "Ticket not found.")

    admin_actor = fetch_actor_by_username(actor_username) if actor_username else None
    documentation = normalize_admin_documentation(
        normalize_json_object(ticket.get("metadata")).get("admin_documentation"),
        fallback_inquiry=sanitize_text(ticket.get("inquiry")),
        fallback_chat_id=build_public_chat_id(ticket.get("public_id"), ticket.get("conversation_id"), ticket.get("conversation_metadata")),
        fallback_ticket_id=ticket["public_id"],
    )
    conversation_history = get_ticket_conversation_history(ticket.get("conversation_id"))
    recent_messages = [
        {
            "role": sanitize_text(entry.get("role")) or "user",
            "text": sanitize_text(entry.get("text")),
            "timestamp": sanitize_text(entry.get("timestamp")),
        }
        for entry in messages[-12:]
        if sanitize_text(entry.get("text"))
    ]

    webhook_result = send_admin_ai_webhook(
        {
            "event": "admin_console_ai_message",
            "source": "support_portal_admin_console",
            "message": message,
            "admin": {
                "username": actor_username or None,
                "fullName": admin_actor.get("full_name") if admin_actor else None,
                "role": admin_actor.get("role") if admin_actor else None,
            },
            "learner": {
                "id": int(ticket["learner_id"]),
                "fullName": ticket.get("learner_full_name"),
                "email": ticket["learner_email"],
                "phone": ticket.get("learner_phone"),
            },
            "ticket": {
                "id": ticket["public_id"],
                "chatId": build_public_chat_id(ticket.get("public_id"), ticket.get("conversation_id"), ticket.get("conversation_metadata")),
                "category": ticket["category"],
                "technicalSubcategory": ticket.get("technical_subcategory"),
                "inquiry": ticket["inquiry"],
                "status": ticket["status"],
                "statusReason": ticket.get("status_reason"),
                "priority": ticket["priority"],
                "assignedTeam": ticket["assigned_team"],
                "documentation": documentation,
            },
            "conversationHistory": conversation_history[-20:],
            "messages": recent_messages,
        }
    )

    return {
        "ok": True,
        "reply": webhook_result["reply"],
        "webhookConfigured": webhook_result["configured"],
        "webhookDelivered": webhook_result["delivered"],
        "webhookStatus": webhook_result["status"],
    }


def get_support_booking_url() -> str:
    booking_url = sanitize_text(settings.SUPPORT_BOOKING_URL)
    if not booking_url:
        raise ApiError(503, "Support booking is not configured on the server.")

    return booking_url


def get_support_teams_call_targets(*, include_booking_fallback: bool = True) -> list[str]:
    raw_targets = settings.SUPPORT_TEAMS_CALL_TARGETS
    configured_targets = [raw_targets] if isinstance(raw_targets, str) else list(raw_targets or [])
    normalized_targets: list[str] = []

    for item in configured_targets:
        normalized_item = sanitize_text(item)
        if normalized_item and normalized_item not in normalized_targets:
            normalized_targets.append(normalized_item)

    fallback_target = sanitize_text(settings.BOOKING_BUSINESS_ID)
    if include_booking_fallback and not normalized_targets and fallback_target and fallback_target not in normalized_targets:
        normalized_targets.append(fallback_target)

    return normalized_targets


def get_support_teams_call_label(targets: list[str] | None = None) -> str:
    configured_label = sanitize_text(settings.SUPPORT_TEAMS_CALL_LABEL)
    if configured_label:
        return configured_label

    normalized_targets = targets if targets is not None else get_support_teams_call_targets()
    if normalized_targets:
        return ", ".join(normalized_targets)

    return "Support Team"


def build_support_teams_call_url(targets: list[str]) -> str:
    if not targets:
        raise ApiError(503, "Microsoft Teams calling is not configured on the server.")

    query_string = urllib_parse.urlencode(
        {"users": ",".join(targets)},
        quote_via=urllib_parse.quote,
    )
    return f"{MICROSOFT_TEAMS_CALL_DEEP_LINK_URL}?{query_string}"


def get_support_teams_call_url() -> str:
    configured_url = sanitize_text(settings.SUPPORT_TEAMS_CALL_URL)
    if configured_url:
        return configured_url

    return build_support_teams_call_url(get_support_teams_call_targets())


def get_support_teams_call_context_response() -> dict[str, Any]:
    configured_url = sanitize_text(settings.SUPPORT_TEAMS_CALL_URL)
    targets = get_support_teams_call_targets(include_booking_fallback=not bool(configured_url))

    return {
        "callUrl": get_support_teams_call_url(),
        "targetLabel": get_support_teams_call_label(targets),
        "targets": targets,
        "handoffMethod": "deepLink",
        "message": "Microsoft Teams will ask you to confirm the call before it starts.",
    }


def normalize_support_teams_call_target_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", sanitize_text(value).lower())


def resolve_support_teams_call_target_candidate(agent: dict[str, Any], normalized_target: str, normalized_local_part: str, leading_token: str) -> tuple[int, dict[str, Any]] | None:
    username = sanitize_text(agent.get("username")).lower()
    full_name = sanitize_text(agent.get("full_name")).lower()
    email = sanitize_text(agent.get("email")).lower()
    email_local_part = email.split("@", 1)[0] if "@" in email else email

    normalized_username = normalize_support_teams_call_target_key(username)
    normalized_full_name = normalize_support_teams_call_target_key(full_name)
    normalized_email_local_part = normalize_support_teams_call_target_key(email_local_part)

    if normalized_local_part:
        if normalized_username == normalized_local_part or normalized_full_name == normalized_local_part or normalized_email_local_part == normalized_local_part:
            return (0, agent)
        if normalized_local_part in {normalized_username, normalized_full_name, normalized_email_local_part}:
            return (1, agent)

    if leading_token and len(leading_token) >= 3:
        for candidate_value in (username, full_name, email_local_part):
            if candidate_value.startswith(leading_token):
                return (2, agent)

    if normalized_target and normalized_target in {normalized_username, normalized_full_name, normalized_email_local_part}:
        return (1, agent)

    return None


def resolve_support_teams_call_notification_target(targets: list[str] | None = None) -> dict[str, Any] | None:
    normalized_targets = targets if targets is not None else get_support_teams_call_targets()

    for target in normalized_targets:
        normalized_target = sanitize_text(target).lower()
        if not normalized_target:
            continue

        agent = run_query_one(
            """
            SELECT id, username, full_name, email, role
            FROM support_accounts
            WHERE is_active = TRUE
              AND account_scope = %s
              AND role = ANY(%s)
              AND (
                LOWER(TRIM(COALESCE(email, ''))) = %s
                OR LOWER(TRIM(username)) = %s
              )
            ORDER BY
              CASE
                WHEN LOWER(TRIM(COALESCE(email, ''))) = %s THEN 0
                ELSE 1
              END,
              id ASC
            LIMIT 1
            """,
            [
                ACCOUNT_SCOPE_STAFF,
                list(ADMIN_ACCESS_ROLES),
                normalized_target,
                normalized_target,
                normalized_target,
            ],
        )

        if agent:
            return agent

        normalized_local_part = normalize_support_teams_call_target_key(normalized_target.split("@", 1)[0])
        leading_token = sanitize_text(re.split(r"[^a-z0-9]+", normalized_target.split("@", 1)[0])[0])
        if not normalized_local_part and not leading_token:
            continue

        candidate_rows = run_query(
            """
            SELECT id, username, full_name, email, role
            FROM support_accounts
            WHERE is_active = TRUE
              AND account_scope = %s
              AND role = ANY(%s)
            ORDER BY id ASC
            """,
            [ACCOUNT_SCOPE_STAFF, list(ADMIN_ACCESS_ROLES)],
        )
        ranked_candidates = [
            ranked_candidate
            for agent_row in candidate_rows
            if (ranked_candidate := resolve_support_teams_call_target_candidate(
                agent_row,
                normalized_target,
                normalized_local_part,
                leading_token,
            )) is not None
        ]
        if not ranked_candidates:
            continue

        ranked_candidates.sort(key=lambda item: (item[0], int(item[1].get("id") or 0)))
        best_rank = ranked_candidates[0][0]
        best_candidates = [agent_row for rank, agent_row in ranked_candidates if rank == best_rank]
        if len(best_candidates) == 1:
            return best_candidates[0]

    return None


def get_ticket_booking_context_response(public_id: str) -> dict[str, Any]:
    if not public_id:
        raise ApiError(400, "Ticket id is required.")

    ticket = run_query_one(
        """
        SELECT
          t.public_id,
          t.category,
          t.technical_subcategory,
          t.inquiry,
          t.status,
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

    return {
        "bookingUrl": get_support_booking_url(),
        "externalAutofillSupported": False,
        "handoffMethod": "postMessage",
        "message": (
            "Booking details were prepared from the support portal and will be sent to the embedded page. "
            "Autofill depends on the external booking provider supporting this handoff."
        ),
        "learner": {
            "id": int(ticket["learner_id"]),
            "fullName": ticket.get("learner_full_name") or "",
            "email": ticket["learner_email"],
            "phone": ticket.get("learner_phone") or "",
        },
        "ticket": {
            "id": ticket["public_id"],
            "category": ticket["category"],
            "technicalSubcategory": ticket.get("technical_subcategory") or "",
            "inquiry": ticket["inquiry"],
            "status": ticket["status"],
        },
        "prefill": {
            "fullName": ticket.get("learner_full_name") or "",
            "email": ticket["learner_email"],
            "phone": ticket.get("learner_phone") or "",
            "specialRequests": ticket["inquiry"],
        },
    }


def get_ticket_conversation_history(conversation_id: Any) -> list[dict[str, Any]]:
    try:
        normalized_conversation_id = int(conversation_id)
    except (TypeError, ValueError):
        return []

    rows = run_query(
        """
        SELECT role, content, metadata, created_at
        FROM messages
        WHERE conversation_id = %s
        ORDER BY created_at ASC, id ASC
        """,
        [normalized_conversation_id],
    )

    return [
        {
            "role": row["role"],
            "senderLabel": to_sender_label(row["role"], row.get("metadata")),
            "text": row["content"],
            "createdAt": row["created_at"],
        }
        for row in rows
    ]


def map_role_to_sender(role: Any, metadata: Any) -> str:
    normalized_metadata = normalize_json_object(metadata)
    original_sender = sanitize_text(normalized_metadata.get("original_sender"))
    if original_sender in {"user", "bot", "agent"}:
        return original_sender

    normalized_role = sanitize_text(role).lower()
    if normalized_role == "user":
        return "user"
    if normalized_role == "agent":
        return "agent"
    return "bot"


def get_ticket_chat_history_response(public_id: str) -> dict[str, Any]:
    if not public_id:
        raise ApiError(400, "Ticket id is required.")

    sync_open_ticket_inactivity(public_id=public_id)
    ticket = run_query_one(
        """
        SELECT
          t.id,
          t.public_id,
          t.category,
          t.technical_subcategory,
          t.status,
          t.status_reason,
          t.assigned_agent_id,
          t.assigned_team,
          t.sla_status,
          t.created_at,
          t.metadata,
          t.conversation_id,
          c.status AS conversation_status,
          c.metadata AS conversation_metadata,
          l.full_name AS learner_name
        FROM tickets t
        JOIN learners l
          ON l.id = t.learner_id
        LEFT JOIN conversations c
          ON c.id = t.conversation_id
        WHERE t.public_id = %s
        LIMIT 1
        """,
        [public_id],
    )

    if not ticket:
        raise ApiError(404, "Ticket not found.")

    raw_message_rows = run_query(
        """
        SELECT id, role, content, metadata, created_at
        FROM messages
        WHERE conversation_id = %s
        ORDER BY created_at ASC, id ASC
        """,
        [ticket["conversation_id"]],
    ) if ticket.get("conversation_id") else []

    messages = ensure_intro_message_row(
        raw_message_rows,
        intro_message=build_chat_intro_message(
            ticket.get("learner_name"),
            ticket.get("category"),
            ticket.get("technical_subcategory"),
        ),
        created_at=ticket.get("created_at"),
        intro_id=f"intro-{ticket['public_id']}",
    )
    history_rows = run_query(
        """
        SELECT id, event_type, payload, created_at
        FROM ticket_history
        WHERE ticket_id = %s
          AND event_type = 'assignment_changed'
        ORDER BY created_at ASC, id ASC
        """,
        [ticket["id"]],
    )
    booking_summary = get_latest_ticket_booking_summary(int(ticket["id"]))

    return {
        "ticket": {
            "id": ticket["public_id"],
            "status": ticket["status"],
            "statusReason": ticket.get("status_reason") or "",
            "assignedAgentId": int(ticket["assigned_agent_id"]) if ticket.get("assigned_agent_id") else None,
            "assignedTeam": ticket.get("assigned_team") or "Unassigned",
            "slaStatus": ticket["sla_status"],
            "createdAt": ticket["created_at"],
            "chatState": derive_ticket_chat_state(ticket.get("status"), ticket.get("conversation_status")),
            "liveChatRequested": is_live_chat_requested(ticket.get("metadata"), ticket.get("conversation_metadata")),
        },
        "chatHistory": serialize_chat_timeline_rows(messages, history_rows),
        "bookingSummary": booking_summary,
        "historyCount": len(messages) + len(history_rows),
    }


def mark_conversation_as_active(ticket_public_id: str, conversation_id: Any) -> None:
    try:
        normalized_conversation_id = int(conversation_id)
    except (TypeError, ValueError):
        return

    normalized_chat_public_id = build_public_chat_id(ticket_public_id, normalized_conversation_id)

    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE conversations
            SET
              last_message_at = COALESCE(last_message_at, NOW()),
              metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb
            WHERE id = %s
            """,
            [
                json.dumps(
                    {
                        "is_active_conversation": True,
                        "chat_public_id": normalized_chat_public_id or None,
                    }
                ),
                normalized_conversation_id,
            ],
        )


def request_live_chat(public_id: str) -> dict[str, Any]:
    if not public_id:
        raise ApiError(400, "Ticket id is required.")

    sync_open_ticket_inactivity(public_id=public_id, allow_reminder=False)
    with transaction.atomic():
        request_time = datetime.now(timezone.utc)
        ticket = run_query_one(
            """
            SELECT
              t.id,
              t.public_id,
              t.status,
              t.status_reason,
              t.metadata,
              t.conversation_id,
              t.assigned_agent_id,
              c.status AS conversation_status,
              l.email AS learner_email
            FROM tickets t
            JOIN learners l
              ON l.id = t.learner_id
            LEFT JOIN conversations c
              ON c.id = t.conversation_id
            WHERE t.public_id = %s
            LIMIT 1
            """,
            [public_id],
        )

        if not ticket:
            raise ApiError(404, "Ticket not found.")
        if not ticket.get("conversation_id"):
            raise ApiError(400, "This ticket is not linked to a conversation.")
        ensure_ticket_allows_chat_features(ticket.get("metadata"))
        if is_chat_locked_for_learner(ticket.get("status"), ticket.get("status_reason")):
            raise ApiError(409, "Chat is unavailable while a support meeting is active. Cancel the meeting to continue in chat.")
        if is_ticket_chat_closed(ticket.get("status"), ticket.get("conversation_status")):
            raise ApiError(409, "This chat has been closed by support. Start a new chat to continue.")

        mark_conversation_as_active(ticket["public_id"], ticket.get("conversation_id"))
        chat_public_id = build_public_chat_id(ticket.get("public_id"), ticket.get("conversation_id"))

        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE tickets
                SET
                  metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb,
                  updated_at = NOW()
                WHERE id = %s
                """,
                [
                    json.dumps(
                        {
                            "live_chat_requested": True,
                            "live_chat_requested_at": request_time.isoformat(),
                        }
                    ),
                    ticket["id"],
                ],
            )
            cursor.execute(
                """
                UPDATE conversations
                SET
                  last_message_at = NOW(),
                  metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb
                WHERE id = %s
                """,
                [
                    json.dumps(
                        {
                            "chat_public_id": chat_public_id,
                            "is_active_conversation": True,
                            "live_chat_requested": True,
                            "live_chat_requested_at": request_time.isoformat(),
                            INACTIVITY_WAITING_SINCE_METADATA_KEY: request_time.isoformat(),
                            INACTIVITY_REMINDER_SENT_AT_METADATA_KEY: None,
                        }
                    ),
                    ticket["conversation_id"],
                ],
            )

        insert_history_event(
            int(ticket["id"]),
            "live_chat_requested",
            {"role": "learner", "label": ticket.get("learner_email") or "learner"},
            {"requested": True},
        )

        assign_waiting_live_chat_tickets(request_time)

        refreshed_ticket = run_query_one(
            """
            SELECT
              t.public_id,
              t.assigned_agent_id,
              a.full_name AS assigned_agent_name,
              a.username AS assigned_agent_username
            FROM tickets t
            LEFT JOIN support_accounts a
              ON a.id = t.assigned_agent_id
            WHERE t.id = %s
            LIMIT 1
            """,
            [ticket["id"]],
        )

    return {
        "ok": True,
        "ticket": {
            "id": ticket["public_id"],
            "chatState": "open",
            "liveChatRequested": True,
            "assignedAgentId": int(refreshed_ticket["assigned_agent_id"]) if refreshed_ticket and refreshed_ticket.get("assigned_agent_id") else None,
            "assignedAgentName": refreshed_ticket.get("assigned_agent_name") if refreshed_ticket else None,
            "assignedAgentUsername": refreshed_ticket.get("assigned_agent_username") if refreshed_ticket else None,
        },
    }


def get_ticket_chat_context_response(public_id: str) -> dict[str, Any]:
    if not public_id:
        raise ApiError(400, "Ticket id is required.")

    sync_open_ticket_inactivity(public_id=public_id)
    ticket = run_query_one(
        """
        SELECT
          t.public_id,
          t.metadata,
          t.conversation_id,
          t.status,
          t.status_reason,
          t.assigned_agent_id,
          t.category,
          t.technical_subcategory,
          c.status AS conversation_status,
          c.metadata AS conversation_metadata,
          l.id AS learner_id,
          l.full_name AS learner_full_name,
          l.email AS learner_email
        FROM tickets t
        JOIN learners l
          ON l.id = t.learner_id
        LEFT JOIN conversations c
          ON c.id = t.conversation_id
        WHERE t.public_id = %s
        LIMIT 1
        """,
        [public_id],
    )

    if not ticket:
        raise ApiError(404, "Ticket not found.")
    ensure_ticket_allows_chat_features(ticket.get("metadata"))
    if is_chat_locked_for_learner(ticket.get("status"), ticket.get("status_reason")):
        raise ApiError(409, "Chat is unavailable while a support meeting is active. Cancel the meeting to continue in chat.")

    chat_state = derive_ticket_chat_state(ticket.get("status"), ticket.get("conversation_status"))
    if chat_state != "closed":
        mark_conversation_as_active(ticket["public_id"], ticket.get("conversation_id"))

    return {
        "introMessage": build_chat_intro_message(
            ticket.get("learner_full_name"),
            ticket["category"],
            ticket.get("technical_subcategory"),
        ),
        "learner": {
            "id": int(ticket["learner_id"]),
            "fullName": ticket.get("learner_full_name") or "",
            "email": ticket["learner_email"],
        },
        "ticket": {
            "id": ticket["public_id"],
            "category": ticket["category"],
            "technicalSubcategory": ticket.get("technical_subcategory") or "",
            "status": ticket.get("status") or "Open",
            "statusReason": ticket.get("status_reason") or "",
            "assignedAgentId": int(ticket["assigned_agent_id"]) if ticket.get("assigned_agent_id") else None,
            "chatState": chat_state,
            "liveChatRequested": is_live_chat_requested(ticket.get("metadata"), ticket.get("conversation_metadata")),
        },
    }


def update_admin_ticket(public_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    requested_status = sanitize_text(payload.get("status")) if "status" in payload else None
    requested_status_reason = sanitize_text(payload.get("statusReason")) if "statusReason" in payload else None
    requested_chat_state = sanitize_text(payload.get("chatState")).lower() if "chatState" in payload else None
    requested_sla_status = sanitize_text(payload.get("slaStatus")) if "slaStatus" in payload else None
    requested_assigned_team = sanitize_text(payload.get("assignedTeam")) if "assignedTeam" in payload else None
    requested_documentation = payload.get("documentation") if isinstance(payload.get("documentation"), dict) else None
    should_create_follow_up_ticket = normalize_bool(payload.get("createFollowUpTicket"))
    requested_follow_up_inquiry = sanitize_text(payload.get("followUpInquiry"))
    has_escalation_agent_input = "escalationAgentId" in payload
    requested_escalation_note = sanitize_text(payload.get("escalationNote"))
    actor_username = sanitize_text(payload.get("actorUsername")).lower()
    note = sanitize_text(payload.get("note"))
    has_assigned_agent_input = "assignedAgentId" in payload

    if not public_id:
        raise ApiError(400, "Ticket id is required.")

    if requested_status is not None and requested_status not in ALLOWED_STATUSES:
        raise ApiError(400, "Invalid ticket status.")

    if requested_chat_state is not None and requested_chat_state not in ALLOWED_CHAT_STATES:
        raise ApiError(400, "Invalid chat state.")

    if requested_sla_status is not None and requested_sla_status not in ALLOWED_SLA_STATUSES:
        raise ApiError(400, "Invalid SLA status.")

    parsed_assigned_agent_id = parse_assigned_agent_id(payload.get("assignedAgentId")) if has_assigned_agent_input else None
    parsed_escalation_agent_id = parse_assigned_agent_id(payload.get("escalationAgentId")) if has_escalation_agent_input else None

    with transaction.atomic():
        ticket = run_query_one(
            """
            SELECT
              t.id,
              t.public_id,
              t.learner_id,
              t.category,
              t.technical_subcategory,
              t.inquiry,
              t.status,
              t.status_reason,
              t.priority,
              t.assigned_agent_id,
              t.assigned_team,
              t.sla_status,
              t.metadata,
              t.created_at,
              t.closed_at,
              t.conversation_id,
              c.metadata AS conversation_metadata,
              a.username AS assigned_agent_username,
              a.full_name AS assigned_agent_name
            FROM tickets t
            LEFT JOIN support_accounts a
              ON a.id = t.assigned_agent_id
            LEFT JOIN conversations c
              ON c.id = t.conversation_id
            WHERE t.public_id = %s
            LIMIT 1
            """,
            [public_id],
        )

        if not ticket:
            raise ApiError(404, "Ticket not found.")

        apply_ticket_sla_policy(ticket)

        if requested_status is not None and requested_status != ticket["status"] and not note:
            raise ApiError(400, "Add an internal note before changing the ticket status.")

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
        current_assigned_agent_id = int(ticket["assigned_agent_id"]) if ticket.get("assigned_agent_id") else None
        requested_assignment_changed = has_assigned_agent_input and current_assigned_agent_id != parsed_assigned_agent_id

        if requested_assignment_changed:
            actor_role = sanitize_text(actor_row.get("role") if actor_row else "").lower()
            if actor_role != ROLE_SUPERADMIN:
                raise ApiError(403, "Only superadmins can assign tickets.")
            if current_assigned_agent_id is not None:
                raise ApiError(409, "Only unassigned tickets can be assigned from this screen.")
            if parsed_assigned_agent_id is None:
                raise ApiError(400, "Select an admin before assigning this ticket.")

        escalation_target_agent = None
        if has_escalation_agent_input and parsed_escalation_agent_id is not None:
            escalation_target_agent = run_query_one(
                """
                SELECT id, username, full_name, email, role
                FROM support_accounts
                WHERE id = %s
                  AND is_active = TRUE
                LIMIT 1
                """,
                [parsed_escalation_agent_id],
            )
            if not escalation_target_agent:
                raise ApiError(400, "The selected admin does not exist.")

        assigned_agent = None
        if has_assigned_agent_input and parsed_assigned_agent_id is not None:
            assigned_agent = run_query_one(
                """
                SELECT id, username, full_name, email, role
                FROM support_accounts
                WHERE id = %s
                  AND is_active = TRUE
                  AND role = %s
                LIMIT 1
                """,
                [parsed_assigned_agent_id, ROLE_ADMIN],
            )
            if not assigned_agent:
                raise ApiError(400, "The selected admin does not exist.")
        elif not has_assigned_agent_input and ticket.get("assigned_agent_id"):
            assigned_agent = {
                "id": ticket["assigned_agent_id"],
                "username": ticket.get("assigned_agent_username"),
                "full_name": ticket.get("assigned_agent_name"),
                "role": "agent",
            }

        next_status = requested_status or ticket["status"]
        is_escalation_notification = next_status == "Pending" and requested_status_reason == STATUS_REASON_ESCALATION
        if is_escalation_notification and parsed_escalation_agent_id is None:
            raise ApiError(400, "Select an admin to escalate this ticket.")
        if is_escalation_notification and not requested_escalation_note:
            raise ApiError(400, "Add an escalation note before notifying another admin.")
        if requested_status == "Closed" and not requested_status_reason:
            next_status_reason = get_default_status_reason_for_status(requested_status)
        else:
            next_status_reason = requested_status_reason if requested_status_reason is not None else (ticket.get("status_reason") or "")
        if requested_status != "Closed":
            if next_status == "Pending" and not next_status_reason:
                next_status_reason = get_default_status_reason_for_status(next_status)
            elif next_status == "Pending" and requested_status_reason is None and not is_status_reason_allowed_for_status(next_status, next_status_reason):
                next_status_reason = get_default_status_reason_for_status(next_status)
            elif requested_status_reason is None and not is_status_reason_allowed_for_status(next_status, next_status_reason):
                next_status_reason = ""
        validate_status_reason_for_status(next_status, next_status_reason)
        next_sla_status, next_sla_attention_required, next_sla_attention_reason = resolve_next_sla_state(
            next_status,
            ticket.get("created_at"),
            ticket["sla_status"],
            requested_sla_status,
        )
        next_chat_state = requested_chat_state or map_conversation_status(next_status)
        ensure_open_ticket_uses_open_chat(next_status, next_chat_state)
        updated_ticket_metadata = normalize_json_object(ticket.get("metadata"))
        updated_ticket_metadata.update(build_sla_metadata_patch(next_sla_attention_required, next_sla_attention_reason))
        chat_public_id = build_public_chat_id(ticket.get("public_id"), ticket.get("conversation_id"), ticket.get("conversation_metadata"))
        if requested_documentation is not None:
            documentation_payload = normalize_admin_documentation(
                requested_documentation,
                fallback_inquiry=sanitize_text(ticket.get("inquiry")),
                fallback_chat_id=chat_public_id,
                fallback_ticket_id=ticket["public_id"],
            )
            updated_ticket_metadata["admin_documentation"] = documentation_payload

        if is_escalation_notification and escalation_target_agent:
            updated_ticket_metadata.pop(LATEST_ESCALATION_CLOSURE_METADATA_KEY, None)
            escalation_sender_id = int(actor_row["id"]) if actor_row else int(ticket.get("assigned_agent_id") or 0)
            escalation_sender_username = (
                sanitize_text(actor_row.get("username")) if actor_row else sanitize_text(ticket.get("assigned_agent_username"))
            )
            escalation_sender_name = (
                sanitize_text(actor_row.get("full_name")) if actor_row else sanitize_text(ticket.get("assigned_agent_name"))
            )
            if not escalation_sender_id or not escalation_sender_username or not escalation_sender_name:
                raise ApiError(400, "A signed-in admin is required before sending this escalation.")

            updated_ticket_metadata[PENDING_ESCALATION_NOTIFICATION_METADATA_KEY] = {
                "fromAgentId": escalation_sender_id,
                "fromAgentName": escalation_sender_name,
                "fromAgentUsername": escalation_sender_username,
                "toAgentId": int(escalation_target_agent["id"]),
                "toAgentName": escalation_target_agent.get("full_name") or escalation_target_agent["username"],
                "toAgentUsername": escalation_target_agent["username"],
                "note": requested_escalation_note,
                "ticketId": ticket["public_id"],
                "requestedAt": datetime.now(timezone.utc).isoformat(),
            }

        latest_ticket_escalation_notification = None
        latest_escalation_closure = None
        pending_escalation_notification = get_pending_escalation_notification(updated_ticket_metadata)
        is_closing_ticket = requested_status == "Closed" and ticket["status"] != "Closed"
        if is_closing_ticket and actor_row:
            actor_id = int(actor_row["id"])
            if pending_escalation_notification:
                if actor_id == int(pending_escalation_notification["toAgentId"]):
                    latest_ticket_escalation_notification = pending_escalation_notification
            else:
                latest_ticket_escalation_notification = get_latest_ticket_escalation_notification(ticket["id"], actor_id)

        if latest_ticket_escalation_notification and actor_row:
            latest_escalation_closure = {
                **latest_ticket_escalation_notification,
                "closedAt": serialize_datetime_value(datetime.now(timezone.utc)),
                "closedById": int(actor_row["id"]),
                "closedByName": actor_row.get("full_name") or actor_row["username"],
                "closedByUsername": actor_row["username"],
                "closedStatusReason": next_status_reason,
                "requesterAcknowledged": False,
            }
            updated_ticket_metadata.pop(PENDING_ESCALATION_NOTIFICATION_METADATA_KEY, None)
            updated_ticket_metadata[LATEST_ESCALATION_CLOSURE_METADATA_KEY] = latest_escalation_closure

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
                  status_reason = %s,
                  assigned_agent_id = %s,
                  assigned_team = %s,
                  sla_status = %s,
                  metadata = %s::jsonb,
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
                    next_status_reason,
                    next_assigned_agent_id,
                    next_assigned_team,
                    next_sla_status,
                    json.dumps(updated_ticket_metadata),
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
                        next_chat_state,
                        json.dumps(
                            {
                                "ticket_status": next_status,
                                "status_reason": next_status_reason,
                                "chat_state": next_chat_state,
                                "assigned_agent_id": next_assigned_agent_id,
                                "assigned_team": next_assigned_team,
                            }
                        ),
                        ticket["conversation_id"],
                    ],
                )

        if ticket.get("conversation_id") and sanitize_text(next_chat_state).lower() == "closed":
            persist_conversation_chat_duration(ticket["id"], ticket["conversation_id"])

        if ticket["status"] != next_status:
            insert_history_event(ticket["id"], "status_changed", actor, {"from": ticket["status"], "to": next_status})

        if (ticket.get("status_reason") or "") != next_status_reason:
            insert_history_event(
                ticket["id"],
                "status_reason_changed",
                actor,
                {"from": ticket.get("status_reason") or "", "to": next_status_reason},
            )

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

        if is_escalation_notification and escalation_target_agent:
            insert_history_event(
                ticket["id"],
                "escalation_notified",
                actor,
                updated_ticket_metadata[PENDING_ESCALATION_NOTIFICATION_METADATA_KEY],
            )

        if latest_escalation_closure and actor:
            insert_history_event(
                ticket["id"],
                "escalation_closed",
                actor,
                {
                    "ticketId": latest_escalation_closure["ticketId"],
                    "fromAgentId": latest_escalation_closure["fromAgentId"],
                    "fromAgentName": latest_escalation_closure["fromAgentName"],
                    "fromAgentUsername": latest_escalation_closure["fromAgentUsername"],
                    "toAgentId": latest_escalation_closure["toAgentId"],
                    "toAgentName": latest_escalation_closure["toAgentName"],
                    "toAgentUsername": latest_escalation_closure["toAgentUsername"],
                    "closedById": latest_escalation_closure["closedById"],
                    "closedByName": latest_escalation_closure["closedByName"],
                    "closedByUsername": latest_escalation_closure["closedByUsername"],
                    "note": latest_escalation_closure["note"],
                    "requestedAt": latest_escalation_closure["requestedAt"],
                    "closedAt": latest_escalation_closure["closedAt"],
                    "closedStatusReason": latest_escalation_closure["closedStatusReason"],
                },
            )

        follow_up_public_id = ""
        if should_create_follow_up_ticket:
            follow_up_public_id = create_follow_up_ticket_from_source_ticket(
                {
                    **ticket,
                    "status": next_status,
                    "assigned_agent_id": next_assigned_agent_id,
                    "assigned_team": next_assigned_team,
                    "metadata": updated_ticket_metadata,
                    "conversation_status": next_chat_state,
                },
                actor_row=actor_row,
                requested_inquiry=requested_follow_up_inquiry,
            )

    detail_public_id = follow_up_public_id or public_id
    detail = fetch_admin_ticket_detail(detail_public_id)
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
        requester = resolve_public_support_requester(email)
        if not requester:
            raise ApiError(404, "This email is not registered in our records.")

        requester_role = requester["role"]
        ticket_priority = derive_requester_ticket_priority(requester_role)
        learner = ensure_public_requester_learner(requester)
        managed_account = requester.get("account")
        ticket_metadata = {
            "source": "support_portal",
            "technical_subcategory": technical_subcategory or None,
            "requester_role": requester_role,
        }
        if managed_account:
            ticket_metadata.update(
                {
                    "requester_account_id": int(managed_account["id"]),
                    "requester_username": sanitize_text(managed_account.get("username")),
                }
            )

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
                  priority,
                  evidence_count,
                  metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                RETURNING id, status, assigned_team, sla_status, created_at
                """,
                [
                    draft_public_id,
                    learner["id"],
                    category,
                    technical_subcategory or None,
                    inquiry,
                    ticket_priority,
                    len(evidence),
                    json.dumps(ticket_metadata),
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
                    requester.get("display_name") or learner.get("full_name"),
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
                            "requester_role": requester_role,
                            "requester_account_id": int(managed_account["id"]) if managed_account else None,
                            "requester_username": sanitize_text(managed_account.get("username")) if managed_account else "",
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

            if conversation_id:
                cursor.execute(
                    """
                    UPDATE conversations
                    SET metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb
                    WHERE id = %s
                    """,
                    [
                        json.dumps(
                            {
                                "chat_public_id": build_public_chat_id(public_id, conversation_id),
                            }
                        ),
                        conversation_id,
                    ],
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
            {"role": requester_role, "label": learner["email"]},
            {
                "category": category,
                "technical_subcategory": technical_subcategory or None,
                "evidence_count": len(evidence),
            },
        )

    return {
        "ticket": {
            "id": public_id,
            "learnerName": requester.get("display_name") or learner.get("full_name") or "",
            "email": learner["email"],
            "requesterRole": requester_role,
            "category": category,
            "technicalSubcategory": technical_subcategory,
            "inquiry": inquiry,
            "status": ticket_row["status"],
        "statusReason": "",
        "assignedTeam": ticket_row["assigned_team"],
        "slaStatus": ticket_row["sla_status"],
        "createdAt": ticket_row["created_at"],
        "chatState": "open",
        "liveChatRequested": False,
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
              t.status_reason,
              t.priority,
              t.assigned_team,
              t.sla_status,
              t.metadata,
              t.created_at,
              t.conversation_id,
              t.technical_subcategory,
              l.full_name AS learner_name,
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
        requester_role = get_ticket_requester_role(existing_ticket.get("metadata"))
        next_priority = derive_requester_ticket_priority(requester_role, existing_ticket.get("priority"))

        apply_ticket_sla_policy(existing_ticket, persist=True)

        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE tickets
                SET
                  category = %s,
                  technical_subcategory = %s,
                  inquiry = %s,
                  priority = %s,
                  evidence_count = %s,
                  updated_at = NOW()
                WHERE id = %s
                """,
                [category, technical_subcategory or None, inquiry, next_priority, len(evidence), existing_ticket["id"]],
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
                                "chat_public_id": build_public_chat_id(
                                    existing_ticket.get("public_id"),
                                    existing_ticket.get("conversation_id"),
                                ),
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
            {"role": requester_role, "label": existing_ticket["email"]},
            {
                "category": category,
                "technical_subcategory": technical_subcategory or None,
                "priority": next_priority,
                "evidence_count": len(evidence),
            },
        )

    return {
        "ticket": {
            "id": existing_ticket["public_id"],
            "learnerName": existing_ticket.get("learner_name") or "",
            "email": existing_ticket["email"],
            "requesterRole": requester_role,
            "category": category,
            "technicalSubcategory": technical_subcategory,
            "inquiry": inquiry,
            "status": existing_ticket["status"],
            "statusReason": existing_ticket.get("status_reason") or "",
            "assignedTeam": existing_ticket["assigned_team"],
            "slaStatus": existing_ticket["sla_status"],
            "createdAt": existing_ticket["created_at"],
            "chatState": derive_ticket_chat_state(existing_ticket.get("status"), None),
            "liveChatRequested": is_live_chat_requested(existing_ticket.get("metadata")),
        }
    }


def save_chat_history(public_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    status = sanitize_text(payload.get("status")) or "Open"
    status_reason = sanitize_text(payload.get("statusReason")) if "statusReason" in payload else None
    actor_username = sanitize_text(payload.get("actorUsername")).lower()
    messages = payload.get("messages") if isinstance(payload.get("messages"), list) else []

    if not public_id:
        raise ApiError(400, "Ticket id is required.")
    if status not in ALLOWED_STATUSES:
        raise ApiError(400, "Invalid ticket status.")

    sync_open_ticket_inactivity(public_id=public_id, allow_reminder=False)
    with transaction.atomic():
        ticket = run_query_one(
            """
            SELECT
              t.id,
              t.public_id,
              t.conversation_id,
              t.status,
              t.status_reason,
              t.assigned_agent_id,
              t.assigned_team,
              t.sla_status,
              t.metadata,
              t.created_at,
              c.status AS conversation_status,
              a.full_name AS assigned_agent_name,
              a.username AS assigned_agent_username
            FROM tickets t
            LEFT JOIN conversations c
              ON c.id = t.conversation_id
            LEFT JOIN support_accounts a
              ON a.id = t.assigned_agent_id
            WHERE t.public_id = %s
            LIMIT 1
            """,
            [public_id],
        )

        if not ticket:
            raise ApiError(404, "Ticket not found.")
        if not ticket.get("conversation_id"):
            raise ApiError(400, "This ticket is not linked to a conversation.")
        if actor_username and any(sanitize_text(message.get("sender")) == "agent" for message in messages):
            if sanitize_text(ticket.get("assigned_agent_username")).lower() != actor_username:
                raise ApiError(403, "Only the assigned agent can reply to this live chat.")
        if is_ticket_chat_closed(ticket.get("status"), ticket.get("conversation_status")) and status != "Closed":
            raise ApiError(409, "This chat has been closed by support. Start a new chat to continue.")

        preview_status_reason = status_reason if status_reason is not None else (ticket.get("status_reason") or "")
        if status == "Pending" and not preview_status_reason:
            preview_status_reason = get_default_status_reason_for_status(status)
        elif status == "Pending" and status_reason is None and not is_status_reason_allowed_for_status(status, preview_status_reason):
            preview_status_reason = get_default_status_reason_for_status(status)

        if status == "Pending" and is_quick_ticket_status_reason(preview_status_reason):
            clear_prepared_support_teams_call(ticket)

        if not is_ticket_chat_closed(ticket.get("status"), ticket.get("conversation_status")) and map_conversation_status(status) != "closed":
            mark_conversation_as_active(ticket["public_id"], ticket.get("conversation_id"))
        persisted_at = datetime.now(timezone.utc)
        preview_messages = normalize_chat_messages(messages)
        filtered_messages, next_status_reason, next_sla_status, next_sla_attention_required = apply_ticket_chat_history_sync(
            ticket,
            status=status,
            status_reason=status_reason,
            messages=messages,
            conversation_metadata_patch=build_inactivity_metadata_patch_for_messages(
                status,
                preview_messages,
                reference_time=persisted_at,
            ),
            reference_time=persisted_at,
        )

    return {
        "ok": True,
        "ticket": {
            "id": ticket["public_id"],
            "status": status,
            "statusReason": next_status_reason,
            "assignedTeam": ticket["assigned_team"],
            "assignedAgentId": int(ticket["assigned_agent_id"]) if ticket.get("assigned_agent_id") else None,
            "assignedAgentName": ticket.get("assigned_agent_name") or None,
            "assignedAgentUsername": ticket.get("assigned_agent_username") or None,
            "slaStatus": next_sla_status,
            "slaAttentionRequired": next_sla_attention_required,
            "createdAt": ticket["created_at"],
            "chatState": derive_ticket_chat_state(status, map_conversation_status(status)),
        },
    }


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


def execute_http_request(request: urllib_request.Request) -> tuple[bool, bool, int | None, Any]:
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


def post_form_request(url: str, payload: dict[str, Any]) -> tuple[bool, bool, int | None, Any]:
    if not url:
        return False, False, None, None

    request = urllib_request.Request(
        url,
        data=urllib_parse.urlencode(payload, doseq=True).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    return execute_http_request(request)


def post_json_request(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> tuple[bool, bool, int | None, Any]:
    if not url:
        return False, False, None, None

    request_headers = {"Content-Type": "application/json", **(headers or {})}
    request = urllib_request.Request(
        url,
        data=json.dumps(payload, default=str).encode("utf-8"),
        headers=request_headers,
        method="POST",
    )
    return execute_http_request(request)


def delete_request(url: str, headers: dict[str, str] | None = None) -> tuple[bool, bool, int | None, Any]:
    if not url:
        return False, False, None, None

    request = urllib_request.Request(
        url,
        headers=headers or {},
        method="DELETE",
    )
    return execute_http_request(request)


def post_json_webhook(url: str, payload: dict[str, Any]) -> tuple[bool, bool, int | None, Any]:
    return post_json_request(url, payload)


def send_booking_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    configured, delivered, status, response_payload = post_json_webhook(settings.BOOKING_WEBHOOK_URL, payload)
    booking_result = extract_booking_webhook_result(response_payload, delivered, status)
    return {
        "configured": configured,
        "delivered": delivered,
        "status": status,
        **booking_result,
    }


def get_admin_ai_webhook_url() -> str:
    return sanitize_text(getattr(settings, "ADMIN_AI_WEBHOOK_URL", "")) or sanitize_text(settings.CHATBOT_WEBHOOK_URL)


def send_admin_ai_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    configured, delivered, status, response_payload = post_json_webhook(get_admin_ai_webhook_url(), payload)
    return {
        "configured": configured,
        "delivered": delivered,
        "status": status,
        "reply": extract_chatbot_reply(response_payload),
    }


def build_support_session_cancellation_webhook_payload(
    ticket: dict[str, Any],
    session_request: dict[str, Any],
) -> dict[str, Any]:
    session_metadata = normalize_json_object(session_request.get("metadata"))

    return {
        "event": "support_session_cancelled",
        "source": "support_portal",
        "bookingProvider": "microsoft_teams",
        "reserveSlot": False,
        "ticketId": ticket["public_id"],
        "learnerEmail": ticket["learner_email"],
        "learnerName": ticket.get("learner_full_name"),
        "sessionRequestId": int(session_request["id"]),
        "requestedDate": serialize_requested_date(session_request.get("requested_date")),
        "requestedTime": serialize_requested_time(session_request.get("requested_time")),
        "requestedStartAt": sanitize_text(session_metadata.get("requested_start_at")) or None,
        "requestedEndAt": sanitize_text(session_metadata.get("requested_end_at")) or None,
        "calendarEventId": sanitize_text(session_metadata.get("calendar_event_id")) or None,
        "calendarEventUrl": sanitize_text(session_metadata.get("calendar_event_url")) or None,
        "meetingJoinUrl": sanitize_text(session_metadata.get("meeting_join_url")) or None,
        "organizerEmail": sanitize_text(session_metadata.get("organizer_email")) or None,
        "bookingReference": sanitize_text(session_metadata.get("booking_reference")) or None,
        "ticket": {
            "id": ticket["public_id"],
            "category": ticket["category"],
            "technicalSubcategory": ticket.get("technical_subcategory"),
            "inquiry": ticket["inquiry"],
            "status": ticket["status"],
            "statusReason": ticket.get("status_reason"),
            "assignedTeam": ticket["assigned_team"],
        },
    }


def request_microsoft_graph_access_token() -> tuple[bool, bool, int | None, Any]:
    token_url = f"https://login.microsoftonline.com/{settings.AZURE_TENANT_ID}/oauth2/v2.0/token"
    return post_form_request(
        token_url,
        {
            "client_id": settings.AZURE_CLIENT_ID,
            "client_secret": settings.AZURE_CLIENT_SECRET,
            "scope": MICROSOFT_GRAPH_SCOPE,
            "grant_type": "client_credentials",
        },
    )


def send_microsoft_graph_booking(
    ticket: dict[str, Any],
    requested_datetime: datetime,
    client_time_zone: str,
) -> dict[str, Any]:
    configured = is_direct_microsoft_booking_configured()
    if not configured:
        return {
            "configured": False,
            "delivered": False,
            "status": None,
            "bookingMode": "graph",
            "reservationConfirmed": False,
            "slotUnavailable": False,
            "meetingJoinUrl": None,
            "calendarEventId": None,
            "calendarEventUrl": None,
            "organizerEmail": None,
            "bookingReference": None,
            "message": "",
        }

    _, token_delivered, token_status, token_payload = request_microsoft_graph_access_token()
    access_token = (
        sanitize_text(token_payload.get("access_token"))
        if isinstance(token_payload, dict)
        else ""
    )
    if not token_delivered or not access_token:
        return {
            "configured": True,
            "delivered": False,
            "status": token_status,
            "bookingMode": "graph",
            "reservationConfirmed": False,
            "slotUnavailable": False,
            "meetingJoinUrl": None,
            "calendarEventId": None,
            "calendarEventUrl": None,
            "organizerEmail": None,
            "bookingReference": None,
            "message": extract_external_service_message(token_payload) or "We could not authenticate with Microsoft Bookings right now.",
        }

    _, service_delivered, service_status, service_payload = get_microsoft_booking_service_details(access_token)
    if not service_delivered:
        return {
            "configured": True,
            "delivered": False,
            "status": service_status,
            "bookingMode": "graph",
            "reservationConfirmed": False,
            "slotUnavailable": False,
            "meetingJoinUrl": None,
            "calendarEventId": None,
            "calendarEventUrl": None,
            "organizerEmail": None,
            "bookingReference": None,
            "message": extract_external_service_message(service_payload) or "We could not read the Microsoft Bookings service configuration right now.",
        }

    duration_minutes = get_direct_booking_duration_minutes(service_payload)
    selected_staff_member_ids = select_microsoft_booking_staff_member_ids(
        access_token,
        service_payload,
        requested_datetime,
        duration_minutes,
    )
    business_id = urllib_parse.quote(sanitize_text(settings.BOOKING_BUSINESS_ID), safe="")
    booking_url = f"{MICROSOFT_GRAPH_V1_BASE_URL}/solutions/bookingBusinesses/{business_id}/appointments"
    payload = build_microsoft_booking_appointment_payload(
        ticket,
        requested_datetime,
        client_time_zone,
        duration_minutes=duration_minutes,
        service_payload=service_payload,
        staff_member_ids=selected_staff_member_ids,
    )
    _, delivered, status, response_payload = post_json_request(
        booking_url,
        payload,
        headers={"Authorization": f"Bearer {access_token}"},
    )

    graph_api_version = "v1.0"
    if should_retry_with_microsoft_graph_beta(status, response_payload):
        beta_booking_url = f"{MICROSOFT_GRAPH_BETA_BASE_URL}/solutions/bookingBusinesses/{business_id}/appointments"
        _, delivered, status, response_payload = post_json_request(
            beta_booking_url,
            payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        graph_api_version = "beta"

    booking_result = extract_booking_webhook_result(response_payload, delivered, status)

    return {
        "configured": True,
        "delivered": delivered,
        "status": status,
        "bookingMode": "graph",
        "graphApiVersion": graph_api_version,
        "durationMinutes": duration_minutes,
        **booking_result,
        "message": booking_result["message"] or extract_external_service_message(response_payload),
    }


def cancel_microsoft_graph_booking(session_metadata: dict[str, Any]) -> dict[str, Any]:
    configured = is_direct_microsoft_booking_configured()
    appointment_id = sanitize_text(session_metadata.get("calendar_event_id"))

    if not configured:
        return {
            "configured": False,
            "delivered": False,
            "status": None,
            "cancelled": False,
            "message": "Microsoft Bookings is not configured on the server.",
        }

    if not appointment_id:
        return {
            "configured": True,
            "delivered": False,
            "status": None,
            "cancelled": False,
            "message": "We could not locate the Microsoft Teams appointment to cancel.",
        }

    _, token_delivered, token_status, token_payload = request_microsoft_graph_access_token()
    access_token = (
        sanitize_text(token_payload.get("access_token"))
        if isinstance(token_payload, dict)
        else ""
    )
    if not token_delivered or not access_token:
        return {
            "configured": True,
            "delivered": False,
            "status": token_status,
            "cancelled": False,
            "message": extract_external_service_message(token_payload) or "We could not authenticate with Microsoft Bookings right now.",
        }

    business_id = urllib_parse.quote(sanitize_text(settings.BOOKING_BUSINESS_ID), safe="")
    encoded_appointment_id = urllib_parse.quote(appointment_id, safe="")
    booking_url = f"{MICROSOFT_GRAPH_V1_BASE_URL}/solutions/bookingBusinesses/{business_id}/appointments/{encoded_appointment_id}"
    _, delivered, status, response_payload = delete_request(
        booking_url,
        headers={"Authorization": f"Bearer {access_token}"},
    )

    if delivered or status == 404:
        return {
            "configured": True,
            "delivered": delivered or status == 404,
            "status": status,
            "cancelled": True,
            "message": "Your support meeting has been cancelled.",
        }

    return {
        "configured": True,
        "delivered": False,
        "status": status,
        "cancelled": False,
        "message": extract_external_service_message(response_payload) or "We could not cancel the Microsoft Teams appointment right now.",
    }


def send_support_session_cancellation(
    ticket: dict[str, Any],
    session_request: dict[str, Any],
) -> dict[str, Any]:
    session_metadata = normalize_json_object(session_request.get("metadata"))
    booking_mode = sanitize_text(session_metadata.get("booking_mode")) or "webhook"
    reservation_confirmed = (
        normalize_bool(session_metadata.get("reservation_confirmed"))
        or sanitize_text(session_request.get("status")).lower() == "scheduled"
    )

    if booking_mode == "graph" and reservation_confirmed:
        return cancel_microsoft_graph_booking(session_metadata)

    if booking_mode == "graph":
        return {
            "configured": True,
            "delivered": True,
            "status": 200,
            "cancelled": True,
            "message": "Your support session request has been cancelled.",
        }

    configured, delivered, status, response_payload = post_json_webhook(
        settings.BOOKING_WEBHOOK_URL,
        build_support_session_cancellation_webhook_payload(ticket, session_request),
    )
    external_message = extract_external_service_message(response_payload)

    if not configured:
        return {
            "configured": False,
            "delivered": False,
            "status": None,
            "cancelled": True,
            "message": "Your support meeting has been cancelled in the portal. Please contact support if your Teams invite remains active.",
        }

    if not delivered:
        return {
            "configured": True,
            "delivered": False,
            "status": status,
            "cancelled": True,
            "message": external_message or "Your support meeting has been cancelled in the portal. External confirmation may take a little longer than usual.",
        }

    return {
        "configured": True,
        "delivered": True,
        "status": status,
        "cancelled": True,
        "message": external_message or "Your support meeting has been cancelled.",
    }


def send_support_session_booking(
    ticket: dict[str, Any],
    session_request_id: int,
    requested_date: str,
    requested_time: str,
    requested_datetime: datetime,
    client_time_zone: str,
    created_at: Any,
) -> dict[str, Any]:
    if is_direct_microsoft_booking_configured():
        return send_microsoft_graph_booking(ticket, requested_datetime, client_time_zone)

    return {
        "bookingMode": "webhook",
        "durationMinutes": settings.SUPPORT_SESSION_DURATION_MINUTES,
        **send_booking_webhook(
            build_support_session_webhook_payload(
                ticket,
                session_request_id,
                requested_date,
                requested_time,
                requested_datetime,
                client_time_zone,
                created_at,
            )
        ),
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

    sync_open_ticket_inactivity(public_id=public_id, allow_reminder=False)
    ticket = run_query_one(
        """
        SELECT
          t.id,
          t.public_id,
          t.conversation_id,
          t.metadata,
          t.category,
          t.technical_subcategory,
          t.inquiry,
          t.status,
          t.status_reason,
          t.priority,
          t.assigned_team,
          c.status AS conversation_status,
          l.id AS learner_id,
          l.full_name AS learner_full_name,
          l.email AS learner_email,
          l.phone AS learner_phone
        FROM tickets t
        JOIN learners l
          ON l.id = t.learner_id
        LEFT JOIN conversations c
          ON c.id = t.conversation_id
        WHERE t.public_id = %s
        LIMIT 1
        """,
        [public_id],
    )

    if not ticket:
        raise ApiError(404, "Ticket not found.")
    ensure_ticket_allows_chat_features(ticket.get("metadata"))
    if is_chat_locked_for_learner(ticket.get("status"), ticket.get("status_reason")):
        raise ApiError(409, "Chat is unavailable while a support meeting is active. Cancel the meeting to continue in chat.")
    if is_ticket_chat_closed(ticket.get("status"), ticket.get("conversation_status")):
        raise ApiError(409, "This chat has been closed by support. Start a new chat to continue.")

    mark_conversation_as_active(ticket["public_id"], ticket.get("conversation_id"))

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
            "statusReason": ticket.get("status_reason"),
            "priority": ticket["priority"],
            "assignedTeam": ticket["assigned_team"],
            },
            "messages": recent_messages,
        }
    )

    if ticket.get("conversation_id"):
        persisted_at = datetime.now(timezone.utc)
        synced_messages = (
            messages
            + [{"sender": "bot", "text": webhook_result["reply"], "timestamp": format_chat_message_timestamp(persisted_at)}]
            if webhook_result.get("reply")
            else messages
        )

        try:
            with transaction.atomic():
                sync_conversation_messages(
                    int(ticket["conversation_id"]),
                    ticket["status"],
                    synced_messages,
                    conversation_metadata_patch=build_inactivity_metadata_patch_for_messages(
                        ticket["status"],
                        normalize_chat_messages(synced_messages),
                        reference_time=persisted_at,
                    ),
                    reference_time=persisted_at,
                )
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
              t.conversation_id,
              t.category,
              t.technical_subcategory,
              t.inquiry,
              t.status,
              t.sla_status,
              t.priority,
              t.assigned_team,
              t.metadata,
              t.created_at,
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
        ensure_ticket_allows_chat_features(ticket.get("metadata"))

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

        apply_ticket_sla_policy(ticket)
        next_sla_status, next_sla_attention_required, next_sla_attention_reason = resolve_next_sla_state(
            "Pending",
            ticket.get("created_at"),
            ticket["sla_status"],
        )
        sla_metadata_patch = build_sla_metadata_patch(next_sla_attention_required, next_sla_attention_reason)

        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE tickets
                SET status = %s,
                    status_reason = %s,
                    sla_status = %s,
                    metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb,
                    updated_at = NOW(),
                    closed_at = CASE
                      WHEN status = 'Closed' THEN NULL
                      ELSE closed_at
                    END
                WHERE id = %s
                """,
                ["Pending", STATUS_REASON_AWAITING_MEETING, next_sla_status, json.dumps(sla_metadata_patch), ticket["id"]],
            )

            if ticket.get("conversation_id"):
                cursor.execute(
                    """
                    UPDATE conversations
                    SET status = %s,
                        last_message_at = NOW(),
                        metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb
                    WHERE id = %s
                    """,
                    [
                        map_conversation_status("Pending"),
                        json.dumps(
                            {
                                "ticket_status": "Pending",
                                "status_reason": STATUS_REASON_AWAITING_MEETING,
                                "sla_status": next_sla_status,
                            }
                        ),
                        ticket["conversation_id"],
                    ],
                )

        ticket["status"] = "Pending"
        ticket["status_reason"] = STATUS_REASON_AWAITING_MEETING
        ticket["sla_status"] = next_sla_status

    booking_result = send_support_session_booking(
        ticket,
        int(created_session_request["id"]),
        requested_date,
        requested_time,
        requested_datetime,
        client_time_zone,
        created_session_request["created_at"],
    )
    booking_duration_minutes = int(booking_result.get("durationMinutes") or settings.SUPPORT_SESSION_DURATION_MINUTES)

    session_request_metadata = {
        "booking_provider": "microsoft_teams",
        "booking_mode": booking_result.get("bookingMode") or "webhook",
        "graph_api_version": booking_result.get("graphApiVersion") or None,
        "webhook_configured": booking_result["configured"],
        "webhook_delivered": booking_result["delivered"],
        "webhook_status": booking_result["status"],
        "requested_start_at": requested_datetime.isoformat(),
        "requested_end_at": (requested_datetime + timedelta(minutes=booking_duration_minutes)).isoformat(),
        "duration_minutes": booking_duration_minutes,
        "reservation_confirmed": booking_result["reservationConfirmed"],
        "slot_unavailable": booking_result["slotUnavailable"],
        "calendar_event_id": booking_result["calendarEventId"],
        "calendar_event_url": booking_result["calendarEventUrl"],
        "meeting_join_url": booking_result["meetingJoinUrl"],
        "organizer_email": booking_result["organizerEmail"],
        "booking_reference": booking_result["bookingReference"],
    }
    if booking_result["reservationConfirmed"]:
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
                "meetingJoinUrl": booking_result["meetingJoinUrl"],
                "calendarEventId": booking_result["calendarEventId"],
            },
        )
    elif booking_result["slotUnavailable"]:
        update_support_session_request_record(
            int(created_session_request["id"]),
            status="cancelled",
            notes=booking_result["message"] or "The selected Teams slot is no longer available.",
            metadata_patch=session_request_metadata,
        )
        insert_history_event(
            int(ticket["id"]),
            "support_session_unavailable",
            {"role": "system", "label": "booking_webhook"},
            {
                "sessionRequestId": int(created_session_request["id"]),
                "message": booking_result["message"] or "The selected Teams slot is no longer available.",
            },
        )
        raise ApiError(409, booking_result["message"] or "This Teams slot is no longer available. Please choose a different time.")
    elif booking_result.get("bookingMode") == "graph":
        update_support_session_request_record(
            int(created_session_request["id"]),
            status="cancelled",
            notes=booking_result["message"] or "We could not reserve this Teams slot right now.",
            metadata_patch=session_request_metadata,
        )
        insert_history_event(
            int(ticket["id"]),
            "support_session_booking_failed",
            {"role": "system", "label": "microsoft_graph"},
            {
                "sessionRequestId": int(created_session_request["id"]),
                "status": booking_result["status"],
                "message": booking_result["message"] or "We could not reserve this Teams slot right now.",
            },
        )
        raise ApiError(502, booking_result["message"] or "We could not reserve this Teams slot right now. Please try again.")
    else:
        update_support_session_request_record(
            int(created_session_request["id"]),
            status="requested",
            notes=booking_result["message"] or None,
            metadata_patch=session_request_metadata,
        )

    return {
        "ok": True,
        "webhookConfigured": booking_result["configured"],
        "webhookDelivered": booking_result["delivered"],
        "webhookStatus": booking_result["status"],
        "reservationConfirmed": booking_result["reservationConfirmed"],
        "meetingJoinUrl": booking_result["meetingJoinUrl"],
        "calendarEventId": booking_result["calendarEventId"],
        "calendarEventUrl": booking_result["calendarEventUrl"],
        "organizerEmail": booking_result["organizerEmail"],
        "bookingReference": booking_result["bookingReference"],
        "message": booking_result["message"] or "",
        "ticket": {
            "id": ticket["public_id"],
            "status": ticket["status"],
            "statusReason": ticket.get("status_reason") or "",
            "slaStatus": ticket["sla_status"],
            "slaAttentionRequired": next_sla_attention_required,
            "assignedTeam": ticket["assigned_team"],
            "createdAt": ticket["created_at"],
        },
    }


def cancel_support_session_request(public_id: str) -> dict[str, Any]:
    if not public_id:
        raise ApiError(400, "Ticket id is required.")

    ticket = run_query_one(
        """
        SELECT
          t.id,
          t.public_id,
          t.conversation_id,
          t.metadata,
          t.category,
          t.technical_subcategory,
          t.inquiry,
          t.status,
          t.status_reason,
          t.sla_status,
          t.assigned_team,
          t.metadata,
          t.created_at,
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

    latest_session_request = run_query_one(
        """
        SELECT id, requested_date, requested_time, status, notes, metadata, created_at
        FROM support_session_requests
        WHERE ticket_id = %s
          AND status IN ('requested', 'scheduled')
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        [ticket["id"]],
    )

    if not latest_session_request:
        raise ApiError(409, "No active support session request was found for this ticket.")

    cancellation_result = send_support_session_cancellation(ticket, latest_session_request)
    if not cancellation_result["cancelled"]:
        raise ApiError(502, cancellation_result["message"] or "We could not cancel the support meeting right now.")

    next_sla_status, next_sla_attention_required, next_sla_attention_reason = resolve_next_sla_state(
        "Open",
        ticket.get("created_at"),
        ticket["sla_status"],
    )
    sla_metadata_patch = build_sla_metadata_patch(next_sla_attention_required, next_sla_attention_reason)
    cancellation_metadata_patch = {
        "cancelled_at": datetime.now(timezone.utc).isoformat(),
        "cancellation_configured": cancellation_result["configured"],
        "cancellation_delivered": cancellation_result["delivered"],
        "cancellation_status": cancellation_result["status"],
        "reservation_confirmed": False,
        "meeting_join_url": None,
    }

    with transaction.atomic():
        update_support_session_request_record(
            int(latest_session_request["id"]),
            status="cancelled",
            notes=cancellation_result["message"] or "Support meeting cancelled by learner.",
            metadata_patch=cancellation_metadata_patch,
        )

        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE tickets
                SET status = %s,
                    status_reason = %s,
                    sla_status = %s,
                    metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb,
                    updated_at = NOW(),
                    closed_at = CASE
                      WHEN status = 'Closed' THEN NULL
                      ELSE closed_at
                    END
                WHERE id = %s
                """,
                ["Open", "", next_sla_status, json.dumps(sla_metadata_patch), ticket["id"]],
            )

            if ticket.get("conversation_id"):
                cursor.execute(
                    """
                    UPDATE conversations
                    SET status = %s,
                        last_message_at = NOW(),
                        metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb
                    WHERE id = %s
                    """,
                    [
                        map_conversation_status("Open"),
                        json.dumps(
                            {
                                "ticket_status": "Open",
                                "status_reason": "",
                                "sla_status": next_sla_status,
                            }
                        ),
                        ticket["conversation_id"],
                    ],
                )

        insert_history_event(
            int(ticket["id"]),
            "support_session_cancelled",
            {"role": "learner", "label": public_id},
            {
                "sessionRequestId": int(latest_session_request["id"]),
                "requestedDate": serialize_requested_date(latest_session_request.get("requested_date")),
                "requestedTime": serialize_requested_time(latest_session_request.get("requested_time")),
                "message": cancellation_result["message"] or "",
            },
        )

    return {
        "ok": True,
        "message": cancellation_result["message"] or "Your support meeting has been cancelled.",
        "ticket": {
            "id": ticket["public_id"],
            "status": "Open",
            "statusReason": "",
            "slaStatus": next_sla_status,
            "slaAttentionRequired": next_sla_attention_required,
            "assignedTeam": ticket["assigned_team"],
            "createdAt": ticket["created_at"],
        },
    }


def serve_frontend_asset(request_path: str) -> Path:
    dist_dir = settings.BASE_DIR.parent / "frontend" / "dist"
    index_file = dist_dir / "index.html"

    if request_path:
        candidate = (dist_dir / request_path.lstrip("/")).resolve()
        if candidate.exists() and candidate.is_file() and str(candidate).startswith(str(dist_dir.resolve())):
            return candidate

    return index_file

