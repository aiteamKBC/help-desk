from __future__ import annotations

import base64
import json
import logging
import mimetypes
import re
import threading
import time
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
from django.contrib.auth.hashers import check_password
from django.db import close_old_connections, connection, transaction
from django.utils import timezone as django_timezone

from .roles import (
    ACCOUNT_ROLES,
    ACCOUNT_SCOPE_REQUESTER,
    ACCOUNT_SCOPE_STAFF,
    ACCOUNT_SCOPES,
    ADMIN_ACCESS_GROUP_NAME,
    ADMIN_ACCESS_ROLES,
    COACH_ACCESS_GROUP_NAME,
    DEFAULT_ACCOUNT_ROLE,
    OPERATIONS_ACCESS_GROUP_NAME,
    PUBLIC_SUPPORT_ACCOUNT_ROLE_SET,
    PUBLIC_SUPPORT_ACCOUNT_ROLES,
    ROLE_ADMIN,
    ROLE_AGENT,
    ROLE_COACH,
    derive_account_scope_from_role,
    ROLE_EMPLOYER,
    ROLE_SUPERADMIN,
    ROLE_USER,
    SUPPORT_ACCESS_GROUP_NAME,
    SUPPORT_PORTAL_ACCESS_ROLES,
)

logger = logging.getLogger(__name__)
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
TICKET_PUBLIC_ID_PATTERN = re.compile(r"^KBC-\d{6}$", re.IGNORECASE)
ALLOWED_STATUSES = {"Open", "Pending", "Closed"}
ALLOWED_CATEGORIES = {"Learning", "Technical", "Others"}
ALLOWED_TECHNICAL_SUBCATEGORIES = {"Aptem", "Coverage", "LMS", "Teams", "Others"}
ALLOWED_SLA_STATUSES = {"Pending Review", "On Track", "Breached"}
ALLOWED_TICKET_PRIORITIES = {"Low", "Normal", "High", "Urgent"}
DEFAULT_TICKET_PRIORITY = "Normal"
EMPLOYER_TICKET_PRIORITY = "High"
COACH_TICKET_PRIORITY = "High"
ASSIGNED_TEAM_UNASSIGNED = "Unassigned"
ASSIGNED_TEAM_SUPPORT_DESK = "Support Desk"
ASSIGNED_TEAM_LEARNING_PLAN = "Learning Plan Team"
DEFAULT_ASSIGNED_TEAMS = {
    ASSIGNED_TEAM_UNASSIGNED,
    ASSIGNED_TEAM_SUPPORT_DESK,
}
TICKET_RECEIVER_SCOPE_SUPPORT = "support"
TICKET_RECEIVER_SCOPE_OPERATIONS = "operations"
TEAM_ROUTING_POLICIES = {
    ASSIGNED_TEAM_SUPPORT_DESK: {
        "key": TICKET_RECEIVER_SCOPE_SUPPORT,
        "assigned_team": ASSIGNED_TEAM_SUPPORT_DESK,
        "receiver_access_metadata_key": "legacy_support_access",
        "receiver_error_ticket_label": "support",
    },
    ASSIGNED_TEAM_LEARNING_PLAN: {
        "key": TICKET_RECEIVER_SCOPE_OPERATIONS,
        "assigned_team": ASSIGNED_TEAM_LEARNING_PLAN,
        "receiver_access_metadata_key": "legacy_operations_access",
        "receiver_error_ticket_label": "Learning Plan",
    },
}
ALLOWED_ASSIGNED_TEAMS = {ASSIGNED_TEAM_UNASSIGNED, *TEAM_ROUTING_POLICIES.keys()}
TICKET_PRIORITY_RANKS = {
    "Urgent": 0,
    "High": 1,
    "Normal": 2,
    "Low": 3,
}
ACTIVE_PRIORITY_TICKET_STATUSES = {"Open", "Pending"}
STATUS_REASON_CLOSED_DUE_TO_INACTIVITY = "Closed due to inactivity"
STATUS_REASON_CLOSING_BY_CHATBOT = "Closed via Chatbot"
STATUS_REASON_CLOSED_BY_REQUESTER = "Closed by Requester"
STATUS_REASON_CLOSED_BY_AGENT = "Closed via Agent"
STATUS_REASON_AWAITING_MEETING = "Awaiting support meeting"
STATUS_REASON_ESCALATION = "Escalation"
STATUS_REASON_QUICK_TICKET = "Quick Ticket"
STATUS_REASON_COVERAGE_TICKET = "Coverage Ticket"
STATUS_REASON_TUTOR_REQUESTED = "Tutor Requested"
STATUS_REASON_TUTOR_ACCEPTED = "Tutor Accepted"
STATUS_REASON_TUTOR_REJECTED = "Tutor Rejected"
STATUS_REASON_TUTOR_REFUSED = "Tutor Refused"
STATUS_REASON_REREQUESTING = "Rerequesting"
SUPPORT_FLOW_STAGE_METADATA_KEY = "support_flow_stage"
SUPPORT_FLOW_STAGE_BOOKING_IN_PROGRESS = "booking_in_progress"
TICKET_STATE_METADATA_KEY = "ticket_state"
TICKET_STATE_COLUMN_PAYLOAD_KEYS = {
    "ticket_type": "ticketType",
    "workflow_stage": "workflowStage",
    "queue_scope": "queueScope",
    "dashboard_bucket": "dashboardBucket",
    "can_show_conversation": "canShowConversation",
    "can_receive_chat": "canReceiveChat",
    "resolution_reason": "resolutionReason",
}
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
INITIAL_COVERAGE_STATUS_REASONS = {
    STATUS_REASON_COVERAGE_TICKET,
    *QUICK_TICKET_STATUS_REASONS,
}
COVERAGE_TUTOR_STATUS_REASONS = {
    STATUS_REASON_TUTOR_REQUESTED,
    STATUS_REASON_TUTOR_ACCEPTED,
    STATUS_REASON_TUTOR_REJECTED,
    STATUS_REASON_TUTOR_REFUSED,
    STATUS_REASON_REREQUESTING,
}
ALLOWED_CHAT_STATES = {"open", "closed"}
ALLOWED_STATUS_REASONS_BY_STATUS = {
    "Closed": {
        STATUS_REASON_CLOSED_DUE_TO_INACTIVITY,
        STATUS_REASON_CLOSING_BY_CHATBOT,
        STATUS_REASON_CLOSED_BY_REQUESTER,
        STATUS_REASON_CLOSED_BY_AGENT,
    },
    "Pending": {
        STATUS_REASON_AWAITING_MEETING,
        STATUS_REASON_ESCALATION,
        STATUS_REASON_COVERAGE_TICKET,
        *QUICK_TICKET_STATUS_REASONS,
        *COVERAGE_TUTOR_STATUS_REASONS,
    },
}
AUTO_MANAGED_SLA_STATUSES = {"Open", "Pending", "Closed"}
PENDING_SLA_BREACH_AFTER = timedelta(days=3)
MEETING_SLA_BREACH_AFTER = timedelta(days=3)
SLA_ATTENTION_REASON_PENDING_OVERDUE = "pending_over_3_days"
SLA_ATTENTION_REASON_MEETING_OVERDUE = "meeting_over_3_days"
SLA_POLICY_KEY_METADATA_KEY = "sla_policy_key"
SLA_STARTED_AT_METADATA_KEY = "sla_started_at"
SLA_DUE_AT_METADATA_KEY = "sla_due_at"
SLA_BREACHED_AT_METADATA_KEY = "sla_breached_at"
SLA_RESOLVED_AT_METADATA_KEY = "sla_resolved_at"
SLA_OUTCOME_STATUS_METADATA_KEY = "sla_outcome_status"
SLA_POLICY_OPEN_REVIEW = "open_review"
SLA_POLICY_PENDING_AGE = "pending_age"
SLA_POLICY_AWAITING_SUPPORT_MEETING = "awaiting_support_meeting"
SLA_POLICY_COVERAGE_SESSION_DEADLINE = "coverage_session_deadline"
SLA_POLICY_CLOSED = "closed"
SLA_POLICY_ARCHIVED = "archived"
CHAT_INACTIVITY_REMINDER_AFTER = timedelta(minutes=2)
CHAT_INACTIVITY_AUTO_CLOSE_AFTER = timedelta(minutes=3)
OPEN_TICKET_INACTIVITY_SYNC_MIN_INTERVAL_SECONDS = 10
BACKGROUND_TICKET_SYNC_MIN_INTERVAL_SECONDS = 10
INACTIVITY_WAITING_SINCE_METADATA_KEY = "inactivity_waiting_since"
INACTIVITY_REMINDER_SENT_AT_METADATA_KEY = "inactivity_reminder_sent_at"
UK_SUPPORT_TIMEZONE = "Europe/London"
UK_SUPPORT_SESSION_START_MINUTES = 8 * 60
UK_SUPPORT_SESSION_END_MINUTES = 16 * 60
SUPPORT_SESSION_LEAD_TIME_SECONDS = 24 * 60 * 60
WEBHOOK_RESPONSE_WRAPPER_KEYS = ("data", "body", "result", "payload", "json", "content", "booking", "meeting", "event", "error")
CHATBOT_WEBHOOK_TIMEOUT_SECONDS = 45
AGENT_SESSION_TIMEOUT = timedelta(minutes=60)
DEFAULT_AGENT_CONSOLE_STATUS = "Off"
AGENT_CONSOLE_STATUSES = {"Available", "Busy", "Off"}
SELECTABLE_AGENT_CONSOLE_STATUSES = {"Available", "Off"}
NON_ASSIGNABLE_AGENT_CONSOLE_STATUSES = {"Off"}
EXCLUDED_APTEM_OWNER_NAMES = {"default owner", "enrolment team"}
PENDING_TRANSFER_REQUEST_METADATA_KEY = "pending_transfer_request"
LATEST_TRANSFER_DECISION_METADATA_KEY = "latest_transfer_decision"
PENDING_ESCALATION_NOTIFICATION_METADATA_KEY = "pending_escalation_notification"
LATEST_ESCALATION_CLOSURE_METADATA_KEY = "latest_escalation_closure"
PENDING_TEAMS_CALL_NOTIFICATION_METADATA_KEY = "pending_teams_call_notification"
PENDING_SUPPORT_QUEUE_NOTIFICATION_METADATA_KEY = "pending_support_queue_notification"
PENDING_COVERAGE_TICKET_NOTIFICATION_METADATA_KEY = "pending_coverage_ticket_notification"
PENDING_LEARNING_PLAN_TRANSFER_NOTIFICATION_METADATA_KEY = "pending_learning_plan_transfer_notification"
TEAMS_CALL_REQUESTED_METADATA_KEY = "teams_call_requested"
LAST_QUICK_TICKET_ASSIGNED_AT_METADATA_KEY = "last_quick_ticket_assigned_at"
QUICK_TICKET_ORIGIN_METADATA_KEY = "quick_ticket_origin"
LATEST_COVERAGE_TUTOR_RESPONSE_METADATA_KEY = "latest_coverage_tutor_response"
QUICK_TICKET_SUBMITTED_NOTIFICATION_SENT_AT_METADATA_KEY = "quick_ticket_confirmation_email_sent_at"
QUICK_TICKET_CLOSED_NOTIFICATION_SENT_AT_METADATA_KEY = "quick_ticket_closed_email_sent_at"
LIVE_AGENT_UNAVAILABLE_NOTIFICATION_SENT_AT_METADATA_KEY = "live_agent_unavailable_operations_notified_at"
SUPPORT_NOTIFICATION_EVENT_QUICK_TICKET_SUBMITTED = "quick_ticket_submitted"
SUPPORT_NOTIFICATION_EVENT_QUICK_TICKET_CLOSED = "quick_ticket_closed"
SUPPORT_NOTIFICATION_EVENT_LIVE_AGENT_UNAVAILABLE = "live_agent_unavailable"
LEARNING_PLAN_TICKET_TRANSFER_WEBHOOK_EVENT = "learning_plan_ticket_transferred"
SUPPORT_NOTIFICATION_WEBHOOK_TIMEOUT_SECONDS = 8
SUPPORT_NOTIFICATION_HISTORY_EVENTS = {
    SUPPORT_NOTIFICATION_EVENT_QUICK_TICKET_SUBMITTED: (
        "quick_ticket_confirmation_email_sent",
        "quick_ticket_confirmation_email_failed",
    ),
    SUPPORT_NOTIFICATION_EVENT_QUICK_TICKET_CLOSED: (
        "quick_ticket_closed_email_sent",
        "quick_ticket_closed_email_failed",
    ),
    SUPPORT_NOTIFICATION_EVENT_LIVE_AGENT_UNAVAILABLE: (
        "live_agent_unavailable_operations_notified",
        "live_agent_unavailable_operations_notification_failed",
    ),
}
MICROSOFT_GRAPH_V1_BASE_URL = "https://graph.microsoft.com/v1.0"
MICROSOFT_GRAPH_BETA_BASE_URL = "https://graph.microsoft.com/beta"
MICROSOFT_GRAPH_SCOPE = "https://graph.microsoft.com/.default"
MICROSOFT_OIDC_AUTHORIZE_BASE_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
MICROSOFT_OIDC_TOKEN_BASE_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
MICROSOFT_OIDC_SCOPES = ("openid", "profile", "email", "User.Read", "Directory.Read.All")
MICROSOFT_GRAPH_ME_URL = f"{MICROSOFT_GRAPH_V1_BASE_URL}/me?$select=id,displayName,mail,userPrincipalName"
MICROSOFT_GRAPH_USERS_URL = f"{MICROSOFT_GRAPH_V1_BASE_URL}/users"
MICROSOFT_GRAPH_ME_DIRECTORY_ROLES_URL = (
    f"{MICROSOFT_GRAPH_V1_BASE_URL}/me/transitiveMemberOf/microsoft.graph.directoryRole"
    "?$select=id,displayName,roleTemplateId"
)
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
MANAGED_PUBLIC_REQUESTER_SOURCE = "support_portal_requester"
KBC_USERS_DATA_REQUESTER_SOURCE = "kbc_users_data"
MICROSOFT_ENTRA_REQUESTER_SOURCE = "microsoft_entra"
DEFAULT_SUPPORT_ATTACHMENT_MAX_FILE_BYTES = 50 * 1024 * 1024
CHAT_MESSAGE_ID_METADATA_KEY = "client_message_id"
CHAT_ATTACHMENTS_METADATA_KEY = "attachments"
CHAT_ATTACHMENT_STORAGE_SEGMENT = "chat"
COVERAGE_TUTOR_WEBHOOK_TIMEOUT_SECONDS = 30
COVERAGE_TICKET_WEBHOOK_TIMEOUT_SECONDS = 8
COVERAGE_SLA_WEBHOOK_TIMEOUT_SECONDS = 8
COVERAGE_TUTOR_RESPONSE_WEBHOOK_TIMEOUT_SECONDS = 8
COVERAGE_SLA_STAGE_WARNING = "warning"
COVERAGE_SLA_STAGE_ESCALATED = "escalated"
COVERAGE_SLA_STAGES = {COVERAGE_SLA_STAGE_WARNING, COVERAGE_SLA_STAGE_ESCALATED}
COVERAGE_SLA_STATE_METADATA_KEY = "coverage_sla_state"
COVERAGE_SLA_BREACH_LEAD_TIME = timedelta(days=3)
COVERAGE_SLA_ESCALATION_AFTER = timedelta(days=1)
SLA_ATTENTION_REASON_COVERAGE_SESSION_DEADLINE = "coverage_session_deadline"
_open_ticket_inactivity_sync_lock = threading.Lock()
_last_open_ticket_inactivity_sync_started_monotonic = 0.0
_ticket_background_sync_lock = threading.Lock()
_ticket_background_sync_in_progress = False
_last_ticket_background_sync_started_monotonic = 0.0


@dataclass
class ApiError(Exception):
    status_code: int
    message: str


def sanitize_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def sanitize_support_attachment_name(value: Any) -> str:
    normalized_value = sanitize_text(value).replace("\\", "/").split("/")[-1]
    if not normalized_value:
        return "attachment"
    return normalized_value[:255]


def get_support_attachment_root() -> Path:
    configured_root = getattr(settings, "SUPPORT_ATTACHMENT_ROOT", settings.BASE_DIR / "media" / "support_attachments")
    return Path(configured_root)


def get_support_attachment_max_file_bytes() -> int:
    configured_value = getattr(settings, "SUPPORT_ATTACHMENT_MAX_FILE_BYTES", DEFAULT_SUPPORT_ATTACHMENT_MAX_FILE_BYTES)

    try:
        normalized_value = int(configured_value)
    except (TypeError, ValueError):
        normalized_value = DEFAULT_SUPPORT_ATTACHMENT_MAX_FILE_BYTES

    return max(normalized_value, 1024)


def get_open_ticket_inactivity_sync_min_interval_seconds() -> int:
    configured_value = getattr(
        settings,
        "SUPPORT_TICKET_INACTIVITY_SYNC_MIN_INTERVAL_SECONDS",
        OPEN_TICKET_INACTIVITY_SYNC_MIN_INTERVAL_SECONDS,
    )

    try:
        normalized_value = int(configured_value)
    except (TypeError, ValueError):
        normalized_value = OPEN_TICKET_INACTIVITY_SYNC_MIN_INTERVAL_SECONDS

    return max(normalized_value, 0)


def get_ticket_background_sync_min_interval_seconds() -> int:
    configured_value = getattr(
        settings,
        "SUPPORT_TICKET_BACKGROUND_SYNC_MIN_INTERVAL_SECONDS",
        BACKGROUND_TICKET_SYNC_MIN_INTERVAL_SECONDS,
    )

    try:
        normalized_value = int(configured_value)
    except (TypeError, ValueError):
        normalized_value = BACKGROUND_TICKET_SYNC_MIN_INTERVAL_SECONDS

    return max(normalized_value, 0)


def get_support_attachment_extension(file_name: str) -> str:
    return Path(file_name).suffix.lower()


def build_support_attachment_storage_key(ticket_public_id: str, file_name: str) -> str:
    extension = get_support_attachment_extension(file_name)
    ticket_segment = sanitize_text(ticket_public_id) or "ticket"
    created_at = datetime.now(timezone.utc)
    return (
        f"{ticket_segment}/"
        f"{created_at.strftime('%Y/%m')}/"
        f"{uuid4().hex}{extension}"
    )


def resolve_support_attachment_path(storage_key: str) -> Path:
    normalized_storage_key = sanitize_text(storage_key)
    if not normalized_storage_key or "://" in normalized_storage_key:
        raise ApiError(404, "Attachment file is unavailable.")

    attachment_root = get_support_attachment_root().resolve()
    candidate_path = (attachment_root / normalized_storage_key).resolve()
    if attachment_root not in candidate_path.parents and candidate_path != attachment_root:
        raise ApiError(404, "Attachment file is unavailable.")

    return candidate_path


def delete_support_attachment_file(storage_key: str) -> None:
    normalized_storage_key = sanitize_text(storage_key)
    if not normalized_storage_key or "://" in normalized_storage_key:
        return

    try:
        attachment_path = resolve_support_attachment_path(normalized_storage_key)
    except ApiError:
        return

    if attachment_path.exists():
        attachment_path.unlink()

    attachment_root = get_support_attachment_root().resolve()
    current_directory = attachment_path.parent
    while current_directory != attachment_root and current_directory.exists():
        try:
            current_directory.rmdir()
        except OSError:
            break
        current_directory = current_directory.parent


def build_admin_ticket_attachment_download_url(public_id: str, attachment_id: int) -> str:
    return f"/api/admin/tickets/{urllib_parse.quote(public_id)}/attachments/{attachment_id}/download"


def build_ticket_chat_attachment_download_url(public_id: str, client_attachment_id: str) -> str:
    return (
        f"/api/tickets/{urllib_parse.quote(public_id)}/chat-attachments/"
        f"{urllib_parse.quote(sanitize_text(client_attachment_id))}/download"
    )


def build_admin_ticket_chat_attachment_download_url(public_id: str, client_attachment_id: str) -> str:
    return (
        f"/api/admin/tickets/{urllib_parse.quote(public_id)}/chat-attachments/"
        f"{urllib_parse.quote(sanitize_text(client_attachment_id))}/download"
    )


def normalize_ticket_attachment_row_payload(file: dict[str, Any]) -> dict[str, Any]:
    metadata = normalize_json_object(file.get("metadata"))
    return {
        "name": sanitize_support_attachment_name(file.get("name")),
        "mimeType": sanitize_text(file.get("mimeType")) or None,
        "size": int(file["size"]) if isinstance(file.get("size"), (int, float)) else None,
        "storageKey": sanitize_text(file.get("storageKey")) or sanitize_text(file.get("storageUrl")) or None,
        "metadata": metadata or file,
    }


def normalize_chat_attachment_row_payload(file: dict[str, Any]) -> dict[str, Any]:
    metadata = normalize_json_object(file.get("metadata"))
    size_value = file.get("size")
    try:
        normalized_size = int(size_value) if size_value not in (None, "") else None
    except (TypeError, ValueError):
        normalized_size = None

    return {
        "clientAttachmentId": sanitize_text(file.get("clientAttachmentId") or file.get("id")),
        "name": sanitize_support_attachment_name(file.get("name")),
        "mimeType": sanitize_text(file.get("mimeType")) or None,
        "size": normalized_size,
        "storageUrl": sanitize_chat_attachment_storage_reference(file.get("storageUrl") or file.get("storageKey")),
        "metadata": metadata or file,
    }


def extract_returned_database_id(row: Any) -> int | None:
    value = None
    if isinstance(row, dict):
        value = row.get("id")
    elif isinstance(row, (list, tuple)) and row:
        value = row[0]

    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def insert_ticket_attachment_rows(
    ticket_id: int,
    ticket_public_id: str,
    attachment_rows: list[dict[str, Any]],
    *,
    metadata_overrides: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    inserted_attachments: list[dict[str, Any]] = []

    with connection.cursor() as cursor:
        for attachment_row in attachment_rows:
            normalized_file = normalize_ticket_attachment_row_payload(attachment_row)
            metadata = {
                **normalize_json_object(normalized_file.get("metadata")),
                **normalize_json_object(metadata_overrides),
            }
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
                RETURNING id
                """,
                [
                    ticket_id,
                    normalized_file["name"],
                    normalized_file["mimeType"],
                    normalized_file["size"],
                    normalized_file["storageKey"],
                    json.dumps(metadata),
                ],
            )
            attachment_id = extract_returned_database_id(cursor.fetchone())
            inserted_attachments.append(
                {
                    "id": sanitize_text(attachment_row.get("id")) or f"ticket-attachment-{attachment_id or uuid4().hex}",
                    "attachmentId": attachment_id,
                    "name": normalized_file["name"],
                    "mimeType": normalized_file["mimeType"] or "application/octet-stream",
                    "size": int(normalized_file["size"] or 0),
                    "storageKey": normalized_file["storageKey"],
                    "storageUrl": (
                        build_admin_ticket_attachment_download_url(ticket_public_id, attachment_id)
                        if attachment_id
                        else ""
                    ),
                    "dataUrl": "",
                }
            )

    return inserted_attachments


def sanitize_chat_attachment_storage_reference(value: Any) -> str | None:
    normalized_value = sanitize_text(value)
    if not normalized_value:
        return None
    if normalized_value.startswith("/api/") or "://" in normalized_value:
        return None
    return normalized_value


def store_uploaded_ticket_attachment(ticket_public_id: str, uploaded_file: Any) -> dict[str, Any]:
    file_name = sanitize_support_attachment_name(getattr(uploaded_file, "name", ""))
    mime_type = sanitize_text(getattr(uploaded_file, "content_type", "")) or mimetypes.guess_type(file_name)[0] or ""
    file_size = int(getattr(uploaded_file, "size", 0) or 0)

    if file_size <= 0:
        raise ApiError(400, "Uploaded attachments must not be empty.")
    if file_size > get_support_attachment_max_file_bytes():
        raise ApiError(400, "Uploaded attachments exceed the maximum allowed size.")
    storage_key = build_support_attachment_storage_key(ticket_public_id, file_name)
    attachment_path = resolve_support_attachment_path(storage_key)
    attachment_path.parent.mkdir(parents=True, exist_ok=True)

    with attachment_path.open("wb") as destination:
        if hasattr(uploaded_file, "chunks"):
            for chunk in uploaded_file.chunks():
                destination.write(chunk)
        else:
            destination.write(uploaded_file.read())

    return {
        "name": file_name,
        "mimeType": mime_type or None,
        "size": file_size,
        "storageKey": storage_key,
        "metadata": {
            "originalName": file_name,
            "storage": "local_filesystem",
        },
    }


def store_uploaded_ticket_attachments(ticket_public_id: str, uploaded_files: list[Any]) -> list[dict[str, Any]]:
    stored_attachments: list[dict[str, Any]] = []

    try:
        for uploaded_file in uploaded_files:
            stored_attachments.append(store_uploaded_ticket_attachment(ticket_public_id, uploaded_file))
    except Exception:
        for attachment in stored_attachments:
            delete_support_attachment_file(attachment.get("storageKey", ""))
        raise

    return stored_attachments


def store_uploaded_message_attachment(ticket_public_id: str, uploaded_file: Any) -> dict[str, Any]:
    return store_uploaded_ticket_attachment(f"{sanitize_text(ticket_public_id)}/{CHAT_ATTACHMENT_STORAGE_SEGMENT}", uploaded_file)


def list_ticket_attachment_storage_keys(ticket_id: int) -> list[str]:
    rows = run_query(
        """
        SELECT storage_url
        FROM ticket_attachments
        WHERE ticket_id = %s
        """,
        [ticket_id],
    )
    return [sanitize_text(row.get("storage_url")) for row in rows if sanitize_text(row.get("storage_url"))]


def get_admin_ticket_attachment_file(
    public_id: str,
    attachment_id: int,
    *,
    actor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not public_id:
        raise ApiError(400, "Ticket id is required.")
    if attachment_id <= 0:
        raise ApiError(400, "Attachment id is required.")

    attachment = run_query_one(
        """
        SELECT
          a.id,
          a.file_name,
          a.mime_type,
          a.storage_url,
          t.public_id,
          t.technical_subcategory,
          t.assigned_team,
          t.metadata
        FROM ticket_attachments a
        JOIN tickets t
          ON t.id = a.ticket_id
        WHERE t.public_id = %s
          AND a.id = %s
        LIMIT 1
        """,
        [public_id, attachment_id],
    )

    if not attachment:
        raise ApiError(404, "Attachment not found.")

    if actor is not None:
        require_actor_can_access_admin_ticket(actor, attachment)

    storage_key = sanitize_text(attachment.get("storage_url"))
    if not storage_key:
        raise ApiError(404, "Attachment file is unavailable.")

    attachment_path = resolve_support_attachment_path(storage_key)
    if not attachment_path.exists() or not attachment_path.is_file():
        raise ApiError(404, "Attachment file is unavailable.")

    return {
        "fileName": sanitize_support_attachment_name(attachment.get("file_name")),
        "mimeType": sanitize_text(attachment.get("mime_type")) or None,
        "path": attachment_path,
    }


def get_ticket_chat_attachment_file(
    public_id: str,
    client_attachment_id: str,
    *,
    actor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not public_id:
        raise ApiError(400, "Ticket id is required.")

    normalized_client_attachment_id = sanitize_text(client_attachment_id)
    if not normalized_client_attachment_id:
        raise ApiError(400, "Attachment id is required.")

    attachment = run_query_one(
        """
        SELECT
          ma.file_name,
          ma.mime_type,
          ma.storage_url,
          t.public_id,
          t.technical_subcategory,
          t.assigned_team,
          t.metadata
        FROM message_attachments ma
        JOIN tickets t
          ON t.conversation_id = ma.conversation_id
        WHERE t.public_id = %s
          AND ma.client_attachment_id = %s
        LIMIT 1
        """,
        [public_id, normalized_client_attachment_id],
    )

    if not attachment:
        raise ApiError(404, "Attachment not found.")

    if actor is not None:
        require_actor_can_access_admin_ticket(actor, attachment)

    storage_key = sanitize_text(attachment.get("storage_url"))
    if not storage_key:
        raise ApiError(404, "Attachment file is unavailable.")

    attachment_path = resolve_support_attachment_path(storage_key)
    if not attachment_path.exists() or not attachment_path.is_file():
        raise ApiError(404, "Attachment file is unavailable.")

    return {
        "fileName": sanitize_support_attachment_name(attachment.get("file_name")),
        "mimeType": sanitize_text(attachment.get("mime_type")) or None,
        "path": attachment_path,
    }


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


def normalize_pending_support_queue_notification(value: Any) -> dict[str, Any] | None:
    payload = normalize_json_object(value)
    if not payload:
        return None

    ticket_id = sanitize_text(payload.get("ticketId")) or sanitize_text(payload.get("chatId"))
    requester_name = sanitize_text(payload.get("requesterName"))
    requester_email = sanitize_text(payload.get("requesterEmail"))
    requester_role = normalize_public_requester_role(payload.get("requesterRole"))
    reason = sanitize_text(payload.get("reason")) or "support_ticket_created"
    queue = sanitize_text(payload.get("queue")) or ASSIGNED_TEAM_SUPPORT_DESK
    created_at = serialize_datetime_value(coerce_datetime(payload.get("createdAt")))

    if not ticket_id or not requester_email or not created_at:
        return None

    return {
        "ticketId": ticket_id,
        "requesterName": requester_name,
        "requesterEmail": requester_email,
        "requesterRole": requester_role,
        "queue": queue,
        "reason": reason,
        "createdAt": created_at,
    }


def get_pending_support_queue_notification(metadata: Any) -> dict[str, Any] | None:
    return normalize_pending_support_queue_notification(
        normalize_json_object(metadata).get(PENDING_SUPPORT_QUEUE_NOTIFICATION_METADATA_KEY)
    )


def build_support_queue_notification_payload(
    *,
    ticket_id: str,
    requester_name: Any,
    requester_email: Any,
    requester_role: Any,
    reason: str,
    created_at: Any,
) -> dict[str, Any]:
    return {
        "ticketId": ticket_id,
        "requesterName": sanitize_text(requester_name),
        "requesterEmail": normalize_email(requester_email),
        "requesterRole": normalize_public_requester_role(requester_role),
        "queue": ASSIGNED_TEAM_SUPPORT_DESK,
        "reason": sanitize_text(reason) or "support_ticket_created",
        "createdAt": serialize_datetime_value(coerce_datetime(created_at)) or serialize_datetime_value(datetime.now(timezone.utc)),
    }


def normalize_pending_coverage_ticket_notification(value: Any) -> dict[str, Any] | None:
    payload = normalize_json_object(value)
    if not payload:
        return None

    ticket_id = sanitize_text(payload.get("ticketId")) or sanitize_text(payload.get("chatId"))
    requester_name = sanitize_text(payload.get("requesterName"))
    requester_email = sanitize_text(payload.get("requesterEmail"))
    requester_role = normalize_public_requester_role(payload.get("requesterRole"))
    created_at = serialize_datetime_value(coerce_datetime(payload.get("createdAt")))

    if not ticket_id or not requester_email or not created_at:
        return None

    return {
        "ticketId": ticket_id,
        "requesterName": requester_name,
        "requesterEmail": requester_email,
        "requesterRole": requester_role,
        "createdAt": created_at,
    }


def get_pending_coverage_ticket_notification(metadata: Any) -> dict[str, Any] | None:
    return normalize_pending_coverage_ticket_notification(
        normalize_json_object(metadata).get(PENDING_COVERAGE_TICKET_NOTIFICATION_METADATA_KEY)
    )


def normalize_pending_learning_plan_transfer_notification(value: Any) -> dict[str, Any] | None:
    payload = normalize_json_object(value)
    if not payload:
        return None

    ticket_id = sanitize_text(payload.get("ticketId")) or sanitize_text(payload.get("chatId"))
    requester_name = sanitize_text(payload.get("requesterName"))
    requester_email = sanitize_text(payload.get("requesterEmail"))
    requester_role = normalize_public_requester_role(payload.get("requesterRole"))
    from_team = sanitize_text(payload.get("fromTeam"))
    to_team = sanitize_text(payload.get("toTeam"))
    transferred_at = serialize_datetime_value(coerce_datetime(payload.get("transferredAt")))
    transferred_by_id = parse_assigned_agent_id(payload.get("transferredById"))
    transferred_by_name = sanitize_text(payload.get("transferredByName"))
    transferred_by_username = sanitize_text(payload.get("transferredByUsername"))
    assigned_agent_id = parse_assigned_agent_id(payload.get("assignedAgentId"))
    assigned_agent_name = sanitize_text(payload.get("assignedAgentName"))
    assigned_agent_username = sanitize_text(payload.get("assignedAgentUsername"))
    note = sanitize_text(payload.get("note"))

    if not ticket_id or not requester_email or not from_team or not to_team or not transferred_at:
        return None

    return {
        "ticketId": ticket_id,
        "requesterName": requester_name,
        "requesterEmail": requester_email,
        "requesterRole": requester_role,
        "fromTeam": from_team,
        "toTeam": to_team,
        "transferredAt": transferred_at,
        "transferredById": transferred_by_id,
        "transferredByName": transferred_by_name,
        "transferredByUsername": transferred_by_username,
        "assignedAgentId": assigned_agent_id,
        "assignedAgentName": assigned_agent_name,
        "assignedAgentUsername": assigned_agent_username,
        "note": note,
    }


def get_pending_learning_plan_transfer_notification(metadata: Any) -> dict[str, Any] | None:
    return normalize_pending_learning_plan_transfer_notification(
        normalize_json_object(metadata).get(PENDING_LEARNING_PLAN_TRANSFER_NOTIFICATION_METADATA_KEY)
    )


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


def normalize_latest_coverage_tutor_response(value: Any) -> dict[str, Any] | None:
    payload = normalize_json_object(value)
    if not payload:
        return None

    outcome = sanitize_text(payload.get("outcome")).lower()
    if outcome == "refused":
        outcome = "rejected"
    to_agent_id = parse_assigned_agent_id(payload.get("toAgentId"))
    ticket_id = sanitize_text(payload.get("ticketId")) or sanitize_text(payload.get("chatId"))
    tutor = sanitize_text(payload.get("tutor"))
    tutor_email = sanitize_text(payload.get("tutorEmail"))
    card_id = sanitize_text(payload.get("cardId"))
    related_tutor_choice_card_id = sanitize_text(payload.get("relatedTutorChoiceCardId"))
    responded_at = serialize_datetime_value(coerce_datetime(payload.get("respondedAt")))
    request_submitted_at = serialize_datetime_value(coerce_datetime(payload.get("requestedAt")))
    session_details = sanitize_text(payload.get("sessionDetails"))
    reply_text = sanitize_text(payload.get("replyText"))
    session_start_at = serialize_datetime_value(coerce_datetime(payload.get("sessionStartAt")))
    session_end_at = serialize_datetime_value(coerce_datetime(payload.get("sessionEndAt")))
    requester_acknowledged = normalize_bool(payload.get("requesterAcknowledged"))

    if (
        outcome not in {"accepted", "rejected"}
        or not to_agent_id
        or not ticket_id
        or not tutor
        or not card_id
        or not related_tutor_choice_card_id
        or not responded_at
    ):
        return None

    return {
        "outcome": outcome,
        "toAgentId": to_agent_id,
        "toAgentName": sanitize_text(payload.get("toAgentName")),
        "toAgentUsername": sanitize_text(payload.get("toAgentUsername")),
        "ticketId": ticket_id,
        "tutor": tutor,
        "tutorEmail": tutor_email,
        "cardId": card_id,
        "relatedTutorChoiceCardId": related_tutor_choice_card_id,
        "requestedAt": request_submitted_at,
        "respondedAt": responded_at,
        "sessionDetails": session_details,
        "replyText": reply_text,
        "sessionStartAt": session_start_at,
        "sessionEndAt": session_end_at,
        "requesterAcknowledged": requester_acknowledged,
    }


def get_latest_coverage_tutor_response(metadata: Any) -> dict[str, Any] | None:
    return normalize_latest_coverage_tutor_response(normalize_json_object(metadata).get(LATEST_COVERAGE_TUTOR_RESPONSE_METADATA_KEY))


def normalize_coverage_sla_state(value: Any) -> dict[str, Any] | None:
    payload = normalize_json_object(value)
    if not payload:
        return None

    stage = sanitize_text(payload.get("stage")).lower()
    if stage not in COVERAGE_SLA_STAGES:
        stage = ""

    session_start_at = serialize_datetime_value(coerce_datetime(payload.get("sessionStartAt")))
    breach_deadline_at = serialize_datetime_value(coerce_datetime(payload.get("breachDeadlineAt")))
    breached_at = serialize_datetime_value(coerce_datetime(payload.get("breachedAt")))
    warning_triggered_at = serialize_datetime_value(coerce_datetime(payload.get("warningTriggeredAt")))
    escalated_at = serialize_datetime_value(coerce_datetime(payload.get("escalatedAt")))

    if not stage:
        if escalated_at:
            stage = COVERAGE_SLA_STAGE_ESCALATED
        elif warning_triggered_at or breached_at:
            stage = COVERAGE_SLA_STAGE_WARNING

    if not stage and not session_start_at and not breach_deadline_at and not breached_at:
        return None

    return {
        "stage": stage,
        "sessionStartAt": session_start_at,
        "breachDeadlineAt": breach_deadline_at,
        "breachedAt": breached_at,
        "warningTriggeredAt": warning_triggered_at,
        "escalatedAt": escalated_at,
    }


def get_coverage_sla_state(metadata: Any) -> dict[str, Any] | None:
    return normalize_coverage_sla_state(normalize_json_object(metadata).get(COVERAGE_SLA_STATE_METADATA_KEY))


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


def normalize_public_requester_source(value: Any) -> str:
    normalized_value = sanitize_text(value).lower()
    if normalized_value == "legacy_kbc_users_data":
        return KBC_USERS_DATA_REQUESTER_SOURCE
    return normalized_value


def is_auto_synced_learner_requester_account(account: dict[str, Any] | None) -> bool:
    if not account:
        return False

    metadata = normalize_json_object(account.get("metadata"))
    return (
        normalize_public_requester_role(account.get("role")) == ROLE_USER
        and (
            normalize_bool(metadata.get("synced_from_learners"))
            or sanitize_text(metadata.get("provisioned_by")).lower() == "sync_learners_to_support_accounts"
        )
    )


def get_public_requester_source(requester: dict[str, Any] | None) -> str:
    if not requester:
        return ""

    explicit_source = normalize_public_requester_source(requester.get("source"))
    if explicit_source:
        return explicit_source
    if is_auto_synced_learner_requester_account(requester.get("account")):
        return KBC_USERS_DATA_REQUESTER_SOURCE
    if requester.get("account"):
        return MANAGED_PUBLIC_REQUESTER_SOURCE
    if requester.get("entra_user"):
        return MICROSOFT_ENTRA_REQUESTER_SOURCE
    return ""


def get_ticket_requester_source(
    ticket_metadata: Any,
    *,
    learner_source: Any = None,
    learner_metadata: Any = None,
    default: str = "",
) -> str:
    metadata = normalize_json_object(ticket_metadata)
    normalized_learner_source = normalize_public_requester_source(learner_source)
    normalized_learner_metadata = normalize_json_object(learner_metadata)
    learner_is_kbc = (
        normalized_learner_source == KBC_USERS_DATA_REQUESTER_SOURCE
        or sanitize_text(normalized_learner_metadata.get("legacy_source")).lower() == KBC_USERS_DATA_REQUESTER_SOURCE
    )
    explicit_source = normalize_public_requester_source(metadata.get("requester_source"))
    requester_role = normalize_public_requester_role(metadata.get("requester_role"))
    if learner_is_kbc and (
        not explicit_source
        or (
            explicit_source == MANAGED_PUBLIC_REQUESTER_SOURCE
            and requester_role == ROLE_USER
        )
    ):
        return KBC_USERS_DATA_REQUESTER_SOURCE

    if explicit_source:
        return explicit_source

    if metadata.get("requester_account_id") not in (None, "", 0):
        return MANAGED_PUBLIC_REQUESTER_SOURCE

    return normalize_public_requester_source(default)


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


def can_requester_submit_coverage_ticket(requester_source: Any) -> bool:
    return normalize_public_requester_source(requester_source) != KBC_USERS_DATA_REQUESTER_SOURCE


def ensure_requester_can_submit_coverage_ticket(requester_source: Any) -> None:
    if not can_requester_submit_coverage_ticket(requester_source):
        raise ApiError(403, "Coverage requests are not available for standard KBC learner accounts.")


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


def normalize_coverage_card_attachment(value: Any, *, allow_pending_upload: bool = False) -> dict[str, Any] | None:
    source = normalize_json_object(value)
    data_url = sanitize_text(source.get("dataUrl"))
    storage_url = sanitize_text(source.get("storageUrl"))
    storage_key = sanitize_text(source.get("storageKey"))
    if data_url and not data_url.startswith("data:"):
        data_url = ""
    has_pending_upload_metadata = bool(sanitize_text(source.get("id")) or sanitize_text(source.get("name")))
    if not data_url and not storage_url and not storage_key and not (allow_pending_upload and has_pending_upload_metadata):
        return None

    attachment_id = None
    try:
        raw_attachment_id = source.get("attachmentId")
        attachment_id = int(raw_attachment_id) if raw_attachment_id not in (None, "") else None
    except (TypeError, ValueError):
        attachment_id = None

    return {
        "id": sanitize_text(source.get("id")),
        "name": sanitize_text(source.get("name")) or "attachment",
        "mimeType": sanitize_text(source.get("mimeType")) or "application/octet-stream",
        "size": int(source.get("size") or 0),
        "dataUrl": data_url,
        "storageUrl": storage_url,
        "storageKey": storage_key,
        "attachmentId": attachment_id,
    }


def normalize_coverage_cards(value: Any) -> list[dict[str, Any]]:
    raw_cards = value if isinstance(value, list) else []
    normalized_cards: list[dict[str, Any]] = []
    allowed_types = {"tutor_choice", "tutor_reply", "note"}
    allowed_request_statuses = {"draft", "requested", "pending", "accepted", "refused"}
    allowed_reply_outcomes = {"accepted", "refused"}

    for item in raw_cards:
        source = normalize_json_object(item)
        card_type = sanitize_text(source.get("type")).lower()
        if card_type not in allowed_types:
            continue

        attachments = []
        raw_attachments = source.get("presentationFiles") if isinstance(source.get("presentationFiles"), list) else []
        for attachment in raw_attachments:
            normalized_attachment = normalize_coverage_card_attachment(attachment)
            if normalized_attachment:
                attachments.append(normalized_attachment)

        request_status = sanitize_text(source.get("requestStatus")).lower()
        if request_status not in allowed_request_statuses:
            request_status = "draft"
        elif request_status == "pending":
            request_status = "requested"

        reply_outcome = sanitize_text(source.get("replyOutcome")).lower()
        if reply_outcome not in allowed_reply_outcomes:
            reply_outcome = ""

        normalized_cards.append(
            {
                "id": sanitize_text(source.get("id")),
                "type": card_type,
                "title": sanitize_text(source.get("title")),
                "note": sanitize_text(source.get("note")),
                "tutor": sanitize_text(source.get("tutor")),
                "tutorEmail": sanitize_text(source.get("tutorEmail")),
                "coach": sanitize_text(source.get("coach")),
                "coachEmail": sanitize_text(source.get("coachEmail")),
                "sessionDetails": sanitize_text(source.get("sessionDetails")),
                "replyText": sanitize_text(source.get("replyText")),
                "requestStatus": request_status,
                "replyOutcome": reply_outcome,
                "locked": normalize_bool(source.get("locked")),
                "createdAt": sanitize_text(source.get("createdAt")),
                "updatedAt": sanitize_text(source.get("updatedAt")),
                "createdByAgentId": parse_assigned_agent_id(source.get("createdByAgentId")),
                "createdByAgentName": sanitize_text(source.get("createdByAgentName")),
                "createdByAgentUsername": sanitize_text(source.get("createdByAgentUsername")),
                "updatedByAgentId": parse_assigned_agent_id(source.get("updatedByAgentId")),
                "updatedByAgentName": sanitize_text(source.get("updatedByAgentName")),
                "updatedByAgentUsername": sanitize_text(source.get("updatedByAgentUsername")),
                "submittedAt": sanitize_text(source.get("submittedAt")),
                "respondedAt": sanitize_text(source.get("respondedAt")),
                "relatedTutorChoiceCardId": sanitize_text(source.get("relatedTutorChoiceCardId")),
                "requestSubmittedByAgentId": parse_assigned_agent_id(source.get("requestSubmittedByAgentId")),
                "requestSubmittedByAgentName": sanitize_text(source.get("requestSubmittedByAgentName")),
                "requestSubmittedByAgentUsername": sanitize_text(source.get("requestSubmittedByAgentUsername")),
                "responseToken": sanitize_text(source.get("responseToken")),
                "sessionStartAt": serialize_datetime_value(coerce_datetime(source.get("sessionStartAt"))),
                "sessionEndAt": serialize_datetime_value(coerce_datetime(source.get("sessionEndAt"))),
                "confirmedAt": serialize_datetime_value(coerce_datetime(source.get("confirmedAt"))),
                "confirmedByAgentId": parse_assigned_agent_id(source.get("confirmedByAgentId")),
                "confirmedByAgentName": sanitize_text(source.get("confirmedByAgentName")),
                "confirmedByAgentUsername": sanitize_text(source.get("confirmedByAgentUsername")),
                "presentationFiles": attachments,
            }
        )

    return normalized_cards


COVERAGE_CARD_ACTOR_FIELDS = {
    "createdByAgentId",
    "createdByAgentName",
    "createdByAgentUsername",
    "updatedByAgentId",
    "updatedByAgentName",
    "updatedByAgentUsername",
}


def build_coverage_card_actor_stamp(actor_row: dict[str, Any] | None, prefix: str) -> dict[str, Any]:
    if not actor_row:
        return {}

    actor_id = parse_assigned_agent_id(actor_row.get("id"))
    actor_username = sanitize_text(actor_row.get("username"))
    actor_name = sanitize_text(actor_row.get("full_name")) or actor_username
    if not actor_id and not actor_username and not actor_name:
        return {}

    return {
        f"{prefix}ByAgentId": actor_id,
        f"{prefix}ByAgentName": actor_name,
        f"{prefix}ByAgentUsername": actor_username,
    }


def normalize_coverage_card_for_actor_comparison(card: Any) -> dict[str, Any]:
    normalized_card = normalize_json_object(card)
    for field in COVERAGE_CARD_ACTOR_FIELDS:
        normalized_card.pop(field, None)
    return normalized_card


def stamp_coverage_documentation_card_actors(
    documentation: Any,
    previous_documentation: Any,
    actor_row: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized_documentation = normalize_admin_documentation(documentation)
    if not actor_row:
        return normalized_documentation

    previous_cards = {
        sanitize_text(card.get("id")): normalize_json_object(card)
        for card in normalize_admin_documentation(previous_documentation).get("coverageCards", [])
        if sanitize_text(card.get("id"))
    }
    created_stamp = build_coverage_card_actor_stamp(actor_row, "created")
    updated_stamp = build_coverage_card_actor_stamp(actor_row, "updated")
    stamped_cards: list[dict[str, Any]] = []

    for card in normalized_documentation.get("coverageCards", []):
        normalized_card = normalize_json_object(card)
        card_id = sanitize_text(normalized_card.get("id"))
        previous_card = previous_cards.get(card_id)

        if not previous_card:
            stamped_cards.append({**normalized_card, **created_stamp, **updated_stamp})
            continue

        stamped_card = {**normalized_card}
        for field in ("createdByAgentId", "createdByAgentName", "createdByAgentUsername"):
            if previous_card.get(field) not in (None, ""):
                stamped_card[field] = previous_card.get(field)

        card_changed = (
            normalize_coverage_card_for_actor_comparison(stamped_card)
            != normalize_coverage_card_for_actor_comparison(previous_card)
        )
        if card_changed:
            stamped_card.update(updated_stamp)
        else:
            has_created_actor = any(stamped_card.get(field) not in (None, "") for field in ("createdByAgentId", "createdByAgentName", "createdByAgentUsername"))
            has_updated_actor = False
            for field in ("updatedByAgentId", "updatedByAgentName", "updatedByAgentUsername"):
                if previous_card.get(field) not in (None, ""):
                    stamped_card[field] = previous_card.get(field)
                    has_updated_actor = True
            if not has_created_actor and not has_updated_actor and updated_stamp:
                stamped_card.update(updated_stamp)
                stamped_card["updatedAt"] = serialize_datetime_value(datetime.now(timezone.utc)) or datetime.now(timezone.utc).isoformat()

        stamped_cards.append(stamped_card)

    normalized_documentation["coverageCards"] = stamped_cards
    return normalized_documentation


def normalize_documentation_cards(value: Any) -> list[dict[str, Any]]:
    raw_cards = value if isinstance(value, list) else []
    normalized_cards: list[dict[str, Any]] = []

    for item in raw_cards:
        source = normalize_json_object(item)
        if not source:
            continue

        normalized_cards.append(
            {
                "id": sanitize_text(source.get("id")),
                "inquiry": sanitize_text(source.get("inquiry")),
                "symptoms": sanitize_text(source.get("symptoms")),
                "errors": sanitize_text(source.get("errors")),
                "steps": sanitize_text(source.get("steps")),
                "resources": sanitize_text(source.get("resources")),
                "attachments": [
                    normalized_attachment
                    for attachment in (source.get("attachments") if isinstance(source.get("attachments"), list) else [])
                    if (normalized_attachment := normalize_coverage_card_attachment(attachment, allow_pending_upload=True))
                ],
                "locked": normalize_bool(source.get("locked")),
                "createdAt": sanitize_text(source.get("createdAt")),
                "updatedAt": sanitize_text(source.get("updatedAt")),
                "createdByAgentId": parse_assigned_agent_id(source.get("createdByAgentId")),
                "createdByAgentName": sanitize_text(source.get("createdByAgentName")),
                "createdByAgentUsername": sanitize_text(source.get("createdByAgentUsername")),
                "updatedByAgentId": parse_assigned_agent_id(source.get("updatedByAgentId")),
                "updatedByAgentName": sanitize_text(source.get("updatedByAgentName")),
                "updatedByAgentUsername": sanitize_text(source.get("updatedByAgentUsername")),
            }
        )

    return normalized_cards


def normalize_documentation_card_for_actor_comparison(card: Any) -> dict[str, Any]:
    normalized_card = normalize_json_object(card)
    for field in COVERAGE_CARD_ACTOR_FIELDS:
        normalized_card.pop(field, None)
    return normalized_card


def normalize_documentation_card_for_history_comparison(card: Any) -> dict[str, Any]:
    normalized_card = normalize_documentation_card_for_actor_comparison(card)
    for field in ("createdAt", "updatedAt"):
        normalized_card.pop(field, None)
    return normalized_card


def normalize_card_content_for_history_comparison(card: Any, attachment_field: str) -> dict[str, Any]:
    normalized_card = normalize_documentation_card_for_history_comparison(card)
    normalized_card.pop(attachment_field, None)
    return normalized_card


CARD_HISTORY_ATTACHMENT_FIELDS = {
    "attachmentId",
    "id",
    "mimeType",
    "name",
    "size",
    "storageUrl",
}
CARD_HISTORY_EXCLUDED_FIELDS = {"dataUrl", "responseToken", "storageKey"}


def has_history_payload_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def build_history_attachment_details(attachment: Any) -> dict[str, Any]:
    source = normalize_json_object(attachment)
    return {
        field: source.get(field)
        for field in CARD_HISTORY_ATTACHMENT_FIELDS
        if has_history_payload_value(source.get(field))
    }


def build_card_history_details(card: Any, attachment_field: str) -> dict[str, Any]:
    source = normalize_json_object(card)
    details: dict[str, Any] = {}
    for key, value in source.items():
        if key in CARD_HISTORY_EXCLUDED_FIELDS:
            continue
        if key == attachment_field:
            attachments = value if isinstance(value, list) else []
            attachment_details = [
                item
                for attachment in attachments
                if (item := build_history_attachment_details(attachment))
            ]
            if attachment_details:
                details[key] = attachment_details
            continue
        if has_history_payload_value(value):
            details[key] = value
    return details


def build_card_history_diff(previous_card: Any, next_card: Any, attachment_field: str) -> dict[str, Any]:
    previous_details = normalize_card_content_for_history_comparison(previous_card, attachment_field)
    next_details = normalize_card_content_for_history_comparison(next_card, attachment_field)
    changed_fields = sorted(
        field
        for field in set(previous_details) | set(next_details)
        if previous_details.get(field) != next_details.get(field)
    )
    return {
        "changedFields": changed_fields,
        "previousValues": {
            field: previous_details.get(field)
            for field in changed_fields
            if has_history_payload_value(previous_details.get(field))
        },
        "currentValues": {
            field: next_details.get(field)
            for field in changed_fields
            if has_history_payload_value(next_details.get(field))
        },
    }


def get_card_attachment_identity(attachment: Any) -> str:
    source = normalize_json_object(attachment)
    for field in ("attachmentId", "id", "storageKey", "storageUrl"):
        value = sanitize_text(source.get(field))
        if value:
            return f"{field}:{value}"
    name = sanitize_text(source.get("name"))
    size = sanitize_text(source.get("size"))
    if name or size:
        return f"name:{name}:size:{size}"
    return ""


def get_card_attachment_identities(card: Any, attachment_field: str) -> set[str]:
    source = normalize_json_object(card)
    attachments = source.get(attachment_field) if isinstance(source.get(attachment_field), list) else []
    return {
        identity
        for attachment in attachments
        if (identity := get_card_attachment_identity(attachment))
    }


def get_added_card_attachments(previous_card: Any, next_card: Any, attachment_field: str) -> list[dict[str, Any]]:
    previous_identities = get_card_attachment_identities(previous_card, attachment_field)
    source = normalize_json_object(next_card)
    attachments = source.get(attachment_field) if isinstance(source.get(attachment_field), list) else []
    added_attachments: list[dict[str, Any]] = []
    for attachment in attachments:
        identity = get_card_attachment_identity(attachment)
        if identity and identity not in previous_identities:
            added_attachments.append(normalize_json_object(attachment))
    return added_attachments


def build_card_history_payload(
    card: Any,
    *,
    card_kind: str,
    attachment_field: str,
    previous_card: Any | None = None,
    added_attachments: list[dict[str, Any]] | None = None,
    include_diff: bool = False,
) -> dict[str, Any]:
    source = normalize_json_object(card)
    attachments = source.get(attachment_field) if isinstance(source.get(attachment_field), list) else []
    added_files = list(added_attachments or [])
    card_type = sanitize_text(source.get("type")) or "documentation"
    card_title = (
        sanitize_text(source.get("title"))
        or sanitize_text(source.get("inquiry"))
        or sanitize_text(source.get("note"))
        or card_type.replace("_", " ").title()
    )
    payload: dict[str, Any] = {
        "cardId": sanitize_text(source.get("id")),
        "cardKind": card_kind,
        "cardType": card_type,
        "cardTitle": card_title,
        "attachmentCount": len(attachments),
        "cardDetails": build_card_history_details(source, attachment_field),
    }
    if added_attachments is not None:
        payload["addedAttachmentCount"] = len(added_files)
        payload["fileCount"] = len(added_files)
        payload["fileNames"] = [
            sanitize_text(attachment.get("name"))
            for attachment in added_files
            if sanitize_text(attachment.get("name"))
        ]
        payload["addedAttachments"] = [
            item
            for attachment in added_files
            if (item := build_history_attachment_details(attachment))
        ]
        payload["allAttachments"] = [
            item
            for attachment in attachments
            if (item := build_history_attachment_details(attachment))
        ]
    if include_diff and previous_card is not None:
        payload.update(build_card_history_diff(previous_card, source, attachment_field))
    return payload


def build_card_collection_history_events(
    previous_cards: Any,
    next_cards: Any,
    *,
    card_kind: str,
    attachment_field: str,
    create_event_type: str,
    update_event_type: str,
    attachment_event_type: str,
) -> list[tuple[str, dict[str, Any]]]:
    previous_by_id: dict[str, dict[str, Any]] = {}
    for card in previous_cards if isinstance(previous_cards, list) else []:
        normalized_previous_card = normalize_json_object(card)
        previous_card_id = sanitize_text(normalized_previous_card.get("id"))
        if previous_card_id:
            previous_by_id[previous_card_id] = normalized_previous_card

    events: list[tuple[str, dict[str, Any]]] = []

    for card in next_cards if isinstance(next_cards, list) else []:
        normalized_card = normalize_json_object(card)
        card_id = sanitize_text(normalized_card.get("id"))
        previous_card = previous_by_id.get(card_id)

        if not previous_card:
            events.append(
                (
                    create_event_type,
                    build_card_history_payload(
                        normalized_card,
                        card_kind=card_kind,
                        attachment_field=attachment_field,
                    ),
                )
            )
            continue

        added_attachments = get_added_card_attachments(previous_card, normalized_card, attachment_field)
        if added_attachments:
            events.append(
                (
                    attachment_event_type,
                    build_card_history_payload(
                        normalized_card,
                        card_kind=card_kind,
                        attachment_field=attachment_field,
                        previous_card=previous_card,
                        added_attachments=added_attachments,
                    ),
                )
            )

        if (
            normalize_card_content_for_history_comparison(normalized_card, attachment_field)
            != normalize_card_content_for_history_comparison(previous_card, attachment_field)
        ):
            events.append(
                (
                    update_event_type,
                    build_card_history_payload(
                        normalized_card,
                        card_kind=card_kind,
                        attachment_field=attachment_field,
                        previous_card=previous_card,
                        include_diff=True,
                    ),
                )
            )

    return events


def build_documentation_card_history_events(
    previous_documentation: Any,
    next_documentation: Any,
) -> list[tuple[str, dict[str, Any]]]:
    previous_payload = normalize_admin_documentation(previous_documentation)
    next_payload = normalize_admin_documentation(next_documentation)
    events: list[tuple[str, dict[str, Any]]] = []
    events.extend(
        build_card_collection_history_events(
            previous_payload.get("documentationCards"),
            next_payload.get("documentationCards"),
            card_kind="Documentation",
            attachment_field="attachments",
            create_event_type="documentation_card_created",
            update_event_type="documentation_card_updated",
            attachment_event_type="documentation_attachment_added",
        )
    )
    events.extend(
        build_card_collection_history_events(
            previous_payload.get("coverageCards"),
            next_payload.get("coverageCards"),
            card_kind="Coverage",
            attachment_field="presentationFiles",
            create_event_type="coverage_card_created",
            update_event_type="coverage_card_updated",
            attachment_event_type="coverage_attachment_added",
        )
    )
    return events


def stamp_documentation_card_actors(
    documentation: Any,
    previous_documentation: Any,
    actor_row: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized_documentation = normalize_admin_documentation(documentation)
    if not actor_row:
        return normalized_documentation

    previous_cards = {
        sanitize_text(card.get("id")): normalize_json_object(card)
        for card in normalize_admin_documentation(previous_documentation).get("documentationCards", [])
        if sanitize_text(card.get("id"))
    }
    created_stamp = build_coverage_card_actor_stamp(actor_row, "created")
    updated_stamp = build_coverage_card_actor_stamp(actor_row, "updated")
    stamped_cards: list[dict[str, Any]] = []

    for card in normalized_documentation.get("documentationCards", []):
        normalized_card = normalize_json_object(card)
        card_id = sanitize_text(normalized_card.get("id"))
        previous_card = previous_cards.get(card_id)

        if not previous_card:
            stamped_cards.append({**normalized_card, **created_stamp, **updated_stamp})
            continue

        stamped_card = {**normalized_card}
        for field in ("createdByAgentId", "createdByAgentName", "createdByAgentUsername"):
            if previous_card.get(field) not in (None, ""):
                stamped_card[field] = previous_card.get(field)

        card_changed = (
            normalize_documentation_card_for_actor_comparison(stamped_card)
            != normalize_documentation_card_for_actor_comparison(previous_card)
        )
        if card_changed:
            stamped_card.update(updated_stamp)
        else:
            has_created_actor = any(stamped_card.get(field) not in (None, "") for field in ("createdByAgentId", "createdByAgentName", "createdByAgentUsername"))
            has_updated_actor = False
            for field in ("updatedByAgentId", "updatedByAgentName", "updatedByAgentUsername"):
                if previous_card.get(field) not in (None, ""):
                    stamped_card[field] = previous_card.get(field)
                    has_updated_actor = True
            if not has_created_actor and not has_updated_actor and updated_stamp:
                stamped_card.update(updated_stamp)
                stamped_card["updatedAt"] = serialize_datetime_value(datetime.now(timezone.utc)) or datetime.now(timezone.utc).isoformat()

        stamped_cards.append(stamped_card)

    normalized_documentation["documentationCards"] = stamped_cards
    return normalized_documentation


def attach_uploaded_documentation_card_files(
    *,
    ticket_id: int,
    ticket_public_id: str,
    documentation: Any,
    uploaded_files: list[Any],
) -> dict[str, Any]:
    normalized_documentation = normalize_admin_documentation(documentation)
    files_to_store = list(uploaded_files or [])
    if not files_to_store:
        return normalized_documentation

    upload_slots: list[tuple[dict[str, Any], int]] = []
    for card_index, card in enumerate(normalized_documentation.get("documentationCards", [])):
        attachments = card.get("attachments") if isinstance(card.get("attachments"), list) else []
        for attachment_index, attachment in enumerate(attachments):
            normalized_attachment = normalize_json_object(attachment)
            if (
                sanitize_text(normalized_attachment.get("storageUrl"))
                or sanitize_text(normalized_attachment.get("storageKey"))
                or normalized_attachment.get("attachmentId") not in (None, "")
                or sanitize_text(normalized_attachment.get("dataUrl")).startswith("data:")
            ):
                continue
            upload_slots.append((card, attachment_index))

    if len(upload_slots) != len(files_to_store):
        raise ApiError(400, "One or more documentation attachments are missing an uploaded file.")

    stored_attachment_keys: list[str] = []
    try:
        stored_attachment_rows = store_uploaded_ticket_attachments(ticket_public_id, files_to_store)
        stored_attachment_keys = [
            attachment.get("storageKey")
            for attachment in stored_attachment_rows
            if sanitize_text(attachment.get("storageKey"))
        ]
        inserted_attachments = insert_ticket_attachment_rows(
            ticket_id,
            ticket_public_id,
            stored_attachment_rows,
            metadata_overrides={"source": "documentation_card"},
        )
    except Exception:
        for storage_key in stored_attachment_keys:
            delete_support_attachment_file(storage_key)
        raise

    for (card, attachment_index), inserted_attachment in zip(upload_slots, inserted_attachments):
        attachments = list(card.get("attachments") or [])
        client_attachment = normalize_json_object(attachments[attachment_index])
        attachments[attachment_index] = {
            **inserted_attachment,
            "id": sanitize_text(client_attachment.get("id")) or inserted_attachment.get("id"),
        }
        card["attachments"] = attachments

    normalized_documentation["documentationCards"] = normalized_documentation.get("documentationCards", [])
    return normalized_documentation


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
        "coverageNotes": sanitize_text(source.get("coverageNotes")),
        "coverageCards": normalize_coverage_cards(source.get("coverageCards")),
        "documentationCards": normalize_documentation_cards(source.get("documentationCards")),
        "errorImages": error_images,
    }


def freeze_coverage_documentation_snapshot(
    existing_documentation: Any,
    requested_documentation: Any,
) -> dict[str, Any]:
    existing = normalize_admin_documentation(existing_documentation)
    requested = normalize_admin_documentation(requested_documentation)

    existing_cards = list(existing.get("coverageCards") or [])
    existing_card_ids = {
        sanitize_text(card.get("id"))
        for card in existing_cards
        if sanitize_text(card.get("id"))
    }
    has_existing_saved_snapshot = bool(existing_cards) or bool(existing.get("coverageNotes"))

    frozen_cards: list[dict[str, Any]] = [normalize_json_object(card) for card in existing_cards]
    for card in requested.get("coverageCards") or []:
        normalized_card = normalize_json_object(card)
        card_id = sanitize_text(normalized_card.get("id"))
        if card_id and card_id in existing_card_ids:
            continue

        created_at = sanitize_text(normalized_card.get("createdAt"))
        updated_at = sanitize_text(normalized_card.get("updatedAt")) or created_at
        frozen_cards.append(
            {
                **normalized_card,
                "locked": True,
                "updatedAt": updated_at,
            }
        )

    return {
        **requested,
        "inquiry": existing.get("inquiry") if has_existing_saved_snapshot else requested.get("inquiry") or "",
        "coverageNotes": existing.get("coverageNotes") if has_existing_saved_snapshot else requested.get("coverageNotes") or "",
        "coverageCards": frozen_cards,
    }


def parse_coverage_session_date_label(value: Any):
    normalized_value = sanitize_text(value)
    if not normalized_value:
        return None

    for pattern in ("%A %d %b %Y", "%a %d %b %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(normalized_value, pattern).date()
        except ValueError:
            continue

    fallback_datetime = coerce_datetime(normalized_value)
    return fallback_datetime.date() if fallback_datetime else None


def parse_coverage_time_start_parts(value: Any) -> tuple[int, int] | None:
    normalized_value = sanitize_text(value)
    if not normalized_value:
        return None

    time_match = re.search(r"(?<!\d)(\d{1,2}):(\d{2})(?:\s*([AaPp][Mm]))?", normalized_value)
    if not time_match:
        return None

    hour = int(time_match.group(1))
    minute = int(time_match.group(2))
    meridiem = sanitize_text(time_match.group(3)).lower()

    if meridiem:
        if hour == 12:
            hour = 0
        if meridiem == "pm":
            hour += 12

    if hour > 23 or minute > 59:
        return None

    return hour, minute


def resolve_coverage_session_start_from_inquiry(inquiry: Any, *, now: datetime | None = None) -> datetime | None:
    parsed_inquiry = parse_coverage_inquiry_details(inquiry)
    if not parsed_inquiry:
        return None

    session_dates = [
        parsed_date
        for parsed_date in (
            parse_coverage_session_date_label(raw_date)
            for raw_date in parsed_inquiry.get("sessionDates") or []
        )
        if parsed_date
    ]
    if not session_dates:
        return None

    time_parts = parse_coverage_time_start_parts(parsed_inquiry.get("time"))
    start_hour, start_minute = time_parts if time_parts else (0, 0)
    session_timezone = ZoneInfo(UK_SUPPORT_TIMEZONE)
    candidate_datetimes = [
        datetime(
            session_date.year,
            session_date.month,
            session_date.day,
            start_hour,
            start_minute,
            tzinfo=session_timezone,
        ).astimezone(timezone.utc)
        for session_date in sorted(set(session_dates))
    ]

    comparison_now = now or datetime.now(timezone.utc)
    upcoming_candidates = [candidate for candidate in candidate_datetimes if candidate >= comparison_now]
    if upcoming_candidates:
        return min(upcoming_candidates)

    return min(candidate_datetimes) if candidate_datetimes else None


def has_submitted_coverage_tutor_request(cards: list[dict[str, Any]]) -> bool:
    for card in cards:
        normalized_card = normalize_json_object(card)
        if sanitize_text(normalized_card.get("type")) != "tutor_choice":
            continue

        if (
            sanitize_text(normalized_card.get("submittedAt"))
            or sanitize_text(normalized_card.get("requestStatus")).lower() in {"requested", "accepted", "refused"}
            or parse_assigned_agent_id(normalized_card.get("requestSubmittedByAgentId"))
        ):
            return True

    return False


def is_coverage_ticket_waiting_for_initial_action(row: dict[str, Any]) -> bool:
    if not is_coverage_ticket_record(row):
        return False

    if sanitize_text(row.get("status")) != "Pending":
        return False

    normalized_status_reason = sanitize_text(row.get("status_reason"))
    if normalized_status_reason and normalized_status_reason not in INITIAL_COVERAGE_STATUS_REASONS:
        return False

    metadata = normalize_json_object(row.get("metadata"))
    if get_latest_coverage_tutor_response(metadata):
        return False

    documentation = normalize_admin_documentation(
        metadata.get("admin_documentation"),
        fallback_inquiry=sanitize_text(row.get("inquiry")),
        fallback_ticket_id=sanitize_text(row.get("public_id")),
    )
    coverage_cards = list(documentation.get("coverageCards") or [])
    if any(sanitize_text(card.get("type")) == "tutor_reply" for card in coverage_cards):
        return False
    if any(sanitize_text(card.get("confirmedAt")) for card in coverage_cards):
        return False

    return not has_submitted_coverage_tutor_request(coverage_cards)


def normalize_sla_status(value: Any, fallback: str = "Pending Review") -> str:
    normalized_value = sanitize_text(value)
    return normalized_value if normalized_value in ALLOWED_SLA_STATUSES else fallback


def get_sla_comparison_now(reference_time: datetime | None = None, tzinfo: Any = timezone.utc) -> datetime:
    comparison_now = reference_time or datetime.now(tzinfo or timezone.utc)
    if comparison_now.tzinfo is None:
        comparison_now = comparison_now.replace(tzinfo=timezone.utc)
    return comparison_now


def get_sla_started_at(metadata: Any, created_at: Any) -> datetime | None:
    normalized_metadata = normalize_json_object(metadata)
    return (
        coerce_datetime(normalized_metadata.get(SLA_STARTED_AT_METADATA_KEY))
        or coerce_datetime(normalized_metadata.get("queue_assigned_at"))
        or coerce_datetime(normalized_metadata.get("quick_ticket_assigned_at"))
        or coerce_datetime(created_at)
    )


def build_pending_age_due_at(started_at: datetime | None) -> datetime | None:
    if not started_at:
        return None
    return started_at + PENDING_SLA_BREACH_AFTER


def build_sla_metadata_patch(
    attention_required: bool,
    attention_reason: str | None,
    *,
    policy_key: str | None = None,
    started_at: datetime | None = None,
    due_at: datetime | None = None,
    breached_at: datetime | None = None,
    resolved_at: datetime | None = None,
    outcome_status: str | None = None,
) -> dict[str, Any]:
    patch: dict[str, Any] = {
        "sla_attention_required": attention_required,
        "sla_attention_reason": attention_reason,
        "sla_attention_updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if policy_key is not None:
        patch[SLA_POLICY_KEY_METADATA_KEY] = policy_key
    if started_at is not None:
        patch[SLA_STARTED_AT_METADATA_KEY] = serialize_datetime_value(started_at)
    if due_at is not None:
        patch[SLA_DUE_AT_METADATA_KEY] = serialize_datetime_value(due_at)
    else:
        patch[SLA_DUE_AT_METADATA_KEY] = None
    if breached_at is not None:
        patch[SLA_BREACHED_AT_METADATA_KEY] = serialize_datetime_value(breached_at)
    elif not attention_required:
        patch[SLA_BREACHED_AT_METADATA_KEY] = None
    if resolved_at is not None:
        patch[SLA_RESOLVED_AT_METADATA_KEY] = serialize_datetime_value(resolved_at)
    elif policy_key != SLA_POLICY_CLOSED:
        patch[SLA_RESOLVED_AT_METADATA_KEY] = None
    if outcome_status is not None:
        patch[SLA_OUTCOME_STATUS_METADATA_KEY] = normalize_sla_status(outcome_status)
    elif policy_key != SLA_POLICY_CLOSED:
        patch[SLA_OUTCOME_STATUS_METADATA_KEY] = None
    return patch


def derive_sla_policy_key(status: Any, status_reason: Any = None) -> str:
    normalized_status = sanitize_text(status)
    normalized_status_reason = sanitize_text(status_reason)

    if normalized_status == "Open":
        return SLA_POLICY_OPEN_REVIEW
    if normalized_status == "Closed":
        return SLA_POLICY_CLOSED
    if normalized_status == "Pending" and normalized_status_reason == STATUS_REASON_AWAITING_MEETING:
        return SLA_POLICY_AWAITING_SUPPORT_MEETING
    if normalized_status == "Pending":
        return SLA_POLICY_PENDING_AGE
    return SLA_POLICY_OPEN_REVIEW


def derive_sla_state(
    status: Any,
    created_at: Any,
    current_sla_status: Any,
    *,
    status_reason: Any = None,
    metadata: Any = None,
    reference_time: datetime | None = None,
) -> tuple[str, bool, str | None]:
    normalized_status = sanitize_text(status)
    fallback_sla_status = normalize_sla_status(current_sla_status)

    if normalized_status == "Open":
        return "Pending Review", False, None

    if normalized_status == "Closed":
        return "On Track", False, None

    if normalized_status == "Pending":
        if sanitize_text(status_reason) == STATUS_REASON_AWAITING_MEETING:
            normalized_metadata = normalize_json_object(metadata)
            meeting_due_at = (
                coerce_datetime(normalized_metadata.get(SLA_DUE_AT_METADATA_KEY))
                or coerce_datetime(normalized_metadata.get("support_session_requested_start_at"))
                or coerce_datetime(normalized_metadata.get("requested_start_at"))
                or coerce_datetime(normalized_metadata.get("scheduled_at"))
            )
            if meeting_due_at:
                comparison_now = get_sla_comparison_now(reference_time, meeting_due_at.tzinfo)
                if comparison_now > meeting_due_at + MEETING_SLA_BREACH_AFTER:
                    return "Breached", True, SLA_ATTENTION_REASON_MEETING_OVERDUE

            return "On Track", False, None

        started_at = get_sla_started_at(metadata, created_at)
        due_at = build_pending_age_due_at(started_at)
        if due_at:
            comparison_now = get_sla_comparison_now(reference_time, due_at.tzinfo)
            if comparison_now > due_at:
                return "Breached", True, SLA_ATTENTION_REASON_PENDING_OVERDUE

        return "On Track", False, None

    return fallback_sla_status, False, None


def resolve_next_sla_state(
    status: Any,
    created_at: Any,
    current_sla_status: Any,
    requested_sla_status: Any = None,
    *,
    status_reason: Any = None,
    metadata: Any = None,
    reference_time: datetime | None = None,
) -> tuple[str, bool, str | None]:
    normalized_status = sanitize_text(status)
    normalized_requested_sla_status = sanitize_text(requested_sla_status)

    if normalized_status in AUTO_MANAGED_SLA_STATUSES:
        return derive_sla_state(
            normalized_status,
            created_at,
            current_sla_status,
            status_reason=status_reason,
            metadata=metadata,
            reference_time=reference_time,
        )

    if normalized_requested_sla_status in ALLOWED_SLA_STATUSES:
        return normalized_requested_sla_status, False, None

    return derive_sla_state(
        normalized_status,
        created_at,
        current_sla_status,
        status_reason=status_reason,
        metadata=metadata,
        reference_time=reference_time,
    )


def resolve_sla_policy_update(
    ticket: dict[str, Any],
    status: Any,
    *,
    status_reason: Any = None,
    metadata: Any = None,
    requested_sla_status: Any = None,
    reference_time: datetime | None = None,
) -> tuple[str, bool, str | None, dict[str, Any]]:
    base_metadata = normalize_json_object(ticket.get("metadata") if metadata is None else metadata)
    normalized_status = sanitize_text(status)
    normalized_status_reason = sanitize_text(status_reason if status_reason is not None else ticket.get("status_reason"))
    started_at = get_sla_started_at(base_metadata, ticket.get("created_at"))
    if sanitize_text(ticket.get("status")) != normalized_status:
        started_at = get_sla_comparison_now(reference_time)
    if normalized_status == "Pending" and normalized_status_reason == STATUS_REASON_AWAITING_MEETING:
        due_at = (
            coerce_datetime(base_metadata.get("support_session_requested_start_at"))
            or coerce_datetime(base_metadata.get("requested_start_at"))
            or coerce_datetime(base_metadata.get("scheduled_at"))
        )
    elif normalized_status == "Pending":
        due_at = build_pending_age_due_at(started_at)
    else:
        due_at = None

    next_sla_status, attention_required, attention_reason = resolve_next_sla_state(
        normalized_status,
        ticket.get("created_at"),
        ticket.get("sla_status"),
        requested_sla_status,
        status_reason=normalized_status_reason,
        metadata={
            **base_metadata,
            SLA_STARTED_AT_METADATA_KEY: serialize_datetime_value(started_at) if started_at else None,
            SLA_DUE_AT_METADATA_KEY: serialize_datetime_value(due_at) if due_at else None,
        },
        reference_time=reference_time,
    )
    comparison_now = get_sla_comparison_now(reference_time)
    policy_key = derive_sla_policy_key(normalized_status, normalized_status_reason)
    metadata_patch = build_sla_metadata_patch(
        attention_required,
        attention_reason,
        policy_key=policy_key,
        started_at=started_at,
        due_at=due_at,
        breached_at=comparison_now if attention_required else None,
        resolved_at=comparison_now if normalized_status == "Closed" else None,
        outcome_status=normalize_sla_status(ticket.get("sla_status")) if normalized_status == "Closed" else None,
    )
    return next_sla_status, attention_required, attention_reason, {**base_metadata, **metadata_patch}


def extract_sla_metadata_signature(metadata: Any) -> dict[str, Any]:
    normalized_metadata = normalize_json_object(metadata)
    return {
        "attentionRequired": normalize_bool(normalized_metadata.get("sla_attention_required")),
        "attentionReason": sanitize_text(normalized_metadata.get("sla_attention_reason")) or None,
        "policyKey": sanitize_text(normalized_metadata.get(SLA_POLICY_KEY_METADATA_KEY)),
        "startedAt": sanitize_text(normalized_metadata.get(SLA_STARTED_AT_METADATA_KEY)),
        "dueAt": sanitize_text(normalized_metadata.get(SLA_DUE_AT_METADATA_KEY)),
        "breachedAt": sanitize_text(normalized_metadata.get(SLA_BREACHED_AT_METADATA_KEY)),
        "resolvedAt": sanitize_text(normalized_metadata.get(SLA_RESOLVED_AT_METADATA_KEY)),
        "outcomeStatus": sanitize_text(normalized_metadata.get(SLA_OUTCOME_STATUS_METADATA_KEY)),
    }


def build_resolved_coverage_sla_metadata(metadata: Any) -> dict[str, Any]:
    next_metadata = {
        **normalize_json_object(metadata),
        **build_sla_metadata_patch(False, None, policy_key=SLA_POLICY_COVERAGE_SESSION_DEADLINE),
    }
    next_metadata.pop(COVERAGE_SLA_STATE_METADATA_KEY, None)
    return next_metadata


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
    current_sla_status = normalize_sla_status(row.get("sla_status"))
    current_attention_required = normalize_bool(metadata.get("sla_attention_required"))
    current_attention_reason = sanitize_text(metadata.get("sla_attention_reason")) or None

    if normalize_bool(row.get("is_archived")):
        row["sla_status"] = current_sla_status
        row["sla_attention_required"] = current_attention_required
        row["metadata"] = metadata
        return row

    if is_coverage_ticket_record(row):
        coverage_sla_state = get_coverage_sla_state(metadata)
        if (
            is_coverage_ticket_waiting_for_initial_action(row)
            and (
                current_attention_reason == SLA_ATTENTION_REASON_COVERAGE_SESSION_DEADLINE
                or coverage_sla_state
            )
        ):
            next_sla_status = "Breached"
            metadata_patch = build_sla_metadata_patch(
                True,
                SLA_ATTENTION_REASON_COVERAGE_SESSION_DEADLINE,
                policy_key=SLA_POLICY_COVERAGE_SESSION_DEADLINE,
                breached_at=get_sla_comparison_now(),
            )
            next_metadata = {**metadata, **metadata_patch}
            next_attention_required = True
            next_attention_reason = SLA_ATTENTION_REASON_COVERAGE_SESSION_DEADLINE
        else:
            next_sla_status = "On Track"
            next_metadata = build_resolved_coverage_sla_metadata(metadata)
            next_attention_required = False
            next_attention_reason = None

        row["sla_status"] = next_sla_status
        row["sla_attention_required"] = next_attention_required
        row["metadata"] = next_metadata
        next_coverage_sla_state = get_coverage_sla_state(next_metadata)

        if (
            persist
            and row.get("id")
            and (
                current_sla_status != next_sla_status
                or current_attention_required != next_attention_required
                or current_attention_reason != next_attention_reason
                or normalize_coverage_sla_state(coverage_sla_state) != normalize_coverage_sla_state(next_coverage_sla_state)
            )
        ):
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE tickets
                        SET sla_status = %s,
                        metadata = %s::jsonb,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    [next_sla_status, json.dumps(next_metadata), row["id"]],
        )
        return row

    next_sla_status, attention_required, attention_reason, next_metadata = resolve_sla_policy_update(
        row,
        row.get("status"),
        status_reason=row.get("status_reason"),
        metadata=metadata,
    )

    row["sla_status"] = next_sla_status
    row["sla_attention_required"] = attention_required
    row["metadata"] = next_metadata

    if (
        persist
        and row.get("id")
        and (
            next_sla_status != current_sla_status
            or attention_required != current_attention_required
            or attention_reason != current_attention_reason
            or extract_sla_metadata_signature(next_metadata) != extract_sla_metadata_signature(metadata)
        )
    ):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE tickets
                SET sla_status = %s,
                    metadata = %s::jsonb,
                    updated_at = NOW()
                WHERE id = %s
                """,
                [next_sla_status, json.dumps(next_metadata), row["id"]],
            )

    return row


def resolve_ticket_sla_update(
    ticket: dict[str, Any],
    status: Any,
    *,
    status_reason: Any = None,
    metadata: Any = None,
    requested_sla_status: Any = None,
) -> tuple[str, bool, str | None, dict[str, Any]]:
    base_metadata = normalize_json_object(ticket.get("metadata") if metadata is None else metadata)
    normalized_status_reason = sanitize_text(status_reason if status_reason is not None else ticket.get("status_reason"))

    if is_coverage_ticket_record(ticket):
        coverage_row = {
            **ticket,
            "status": sanitize_text(status),
            "status_reason": normalized_status_reason,
            "metadata": base_metadata,
            "sla_status": normalize_sla_status(ticket.get("sla_status")),
        }
        apply_ticket_sla_policy(coverage_row)
        resolved_metadata = normalize_json_object(coverage_row.get("metadata"))
        return (
            normalize_sla_status(coverage_row.get("sla_status"), "On Track"),
            normalize_bool(coverage_row.get("sla_attention_required")),
            sanitize_text(resolved_metadata.get("sla_attention_reason")) or None,
            resolved_metadata,
        )

    return resolve_sla_policy_update(
        ticket,
        status,
        status_reason=normalized_status_reason,
        metadata=base_metadata,
        requested_sla_status=requested_sla_status,
    )


def sync_auto_managed_ticket_sla_statuses() -> dict[str, int]:
    tickets = run_query(
        """
        SELECT id, public_id, category, technical_subcategory, inquiry, status, status_reason, sla_status, metadata, created_at, is_archived
        FROM tickets
        WHERE status = ANY(%s)
          AND COALESCE(is_archived, FALSE) = FALSE
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


def build_coverage_sla_alert_webhook_payload(
    ticket: dict[str, Any],
    *,
    alert_level: str,
    session_start_at: datetime,
    breach_deadline_at: datetime,
    breached_at: datetime,
) -> dict[str, Any]:
    normalized_alert_level = sanitize_text(alert_level).lower() or COVERAGE_SLA_STAGE_WARNING
    parsed_inquiry = parse_coverage_inquiry_details(ticket.get("inquiry")) or {}
    public_base_url = get_support_portal_public_base_url("")
    dashboard_url = f"{public_base_url}/admin" if public_base_url else ""

    return {
        "event": "coverage_sla",
        "alertLevel": normalized_alert_level,
        "source": "support_portal",
        "ticket": {
            "id": ticket.get("public_id") or "",
            "status": ticket.get("status") or "",
            "statusReason": ticket.get("status_reason") or "",
            "slaStatus": "Breached",
            "sessionStartAt": serialize_datetime_value(session_start_at),
            "breachDeadlineAt": serialize_datetime_value(breach_deadline_at),
            "breachedAt": serialize_datetime_value(breached_at),
            "dashboardUrl": dashboard_url,
        },
        "requester": {
            "name": ticket.get("learner_name") or ticket.get("learner_email") or "",
            "email": ticket.get("learner_email") or "",
        },
        "coverage": {
            "tutor": parsed_inquiry.get("tutor") or "",
            "module": parsed_inquiry.get("module") or "",
            "preferredTime": parsed_inquiry.get("time") or "",
            "sessionDates": parsed_inquiry.get("sessionDates") or [],
            "sessionNumbers": parsed_inquiry.get("sessionNumbers") or [],
            "sessionSubjects": parsed_inquiry.get("sessionSubjects") or [],
            "sessions": build_coverage_session_items_from_inquiry_details(parsed_inquiry),
        },
    }


def send_coverage_sla_alert_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    configured, delivered, status, response_payload = post_json_webhook(
        get_coverage_sla_alerts_webhook_url(),
        payload,
        timeout_seconds=COVERAGE_SLA_WEBHOOK_TIMEOUT_SECONDS,
    )
    return {
        "configured": configured,
        "delivered": delivered,
        "status": status,
        "response": response_payload,
    }


def build_coverage_sla_state(
    *,
    stage: str,
    session_start_at: datetime,
    breach_deadline_at: datetime,
    breached_at: datetime | None = None,
    warning_triggered_at: datetime | None = None,
    escalated_at: datetime | None = None,
) -> dict[str, Any]:
    return {
        "stage": stage,
        "sessionStartAt": serialize_datetime_value(session_start_at),
        "breachDeadlineAt": serialize_datetime_value(breach_deadline_at),
        "breachedAt": serialize_datetime_value(breached_at),
        "warningTriggeredAt": serialize_datetime_value(warning_triggered_at),
        "escalatedAt": serialize_datetime_value(escalated_at),
    }


def sync_coverage_ticket_sla_alerts(reference_now: datetime | None = None) -> dict[str, int]:
    comparison_now = reference_now or datetime.now(timezone.utc)
    if comparison_now.tzinfo is None:
        comparison_now = comparison_now.replace(tzinfo=timezone.utc)

    tickets = run_query(
        """
        SELECT
          t.id,
          t.public_id,
          l.full_name AS learner_name,
          l.email AS learner_email,
          t.category,
          t.technical_subcategory,
          t.inquiry,
          t.status,
          t.status_reason,
          t.sla_status,
          t.metadata,
          t.created_at,
          t.updated_at
        FROM tickets t
        JOIN learners l
          ON l.id = t.learner_id
        WHERE t.status = 'Pending'
          AND COALESCE(t.is_archived, FALSE) = FALSE
          AND (
            LOWER(TRIM(COALESCE(t.technical_subcategory, ''))) = 'coverage'
            OR LOWER(TRIM(COALESCE(t.metadata ->> 'technical_subcategory', ''))) = 'coverage'
          )
        ORDER BY t.id ASC
        """
    )

    scanned_count = 0
    updated_count = 0
    warning_count = 0
    escalation_count = 0
    breached_count = 0
    attention_required_count = 0

    for ticket in tickets:
        scanned_count += 1
        if not is_coverage_ticket_waiting_for_initial_action(ticket):
            continue

        metadata = normalize_json_object(ticket.get("metadata"))
        documentation = normalize_admin_documentation(
            metadata.get("admin_documentation"),
            fallback_inquiry=sanitize_text(ticket.get("inquiry")),
            fallback_ticket_id=sanitize_text(ticket.get("public_id")),
        )
        effective_inquiry = sanitize_text(ticket.get("inquiry")) or sanitize_text(documentation.get("inquiry"))
        ticket["inquiry"] = effective_inquiry
        session_start_at = resolve_coverage_session_start_from_inquiry(effective_inquiry, now=comparison_now)
        coverage_sla_state = get_coverage_sla_state(metadata)

        if not session_start_at:
            next_metadata = {**metadata, **build_sla_metadata_patch(False, None, policy_key=SLA_POLICY_COVERAGE_SESSION_DEADLINE)}
            next_metadata.pop(COVERAGE_SLA_STATE_METADATA_KEY, None)
            if (
                sanitize_text(ticket.get("sla_status")) != "On Track"
                or normalize_bool(metadata.get("sla_attention_required"))
                or coverage_sla_state is not None
            ):
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE tickets
                        SET sla_status = %s,
                            metadata = %s::jsonb,
                            updated_at = NOW()
                        WHERE id = %s
                        """,
                        ["On Track", json.dumps(next_metadata), ticket["id"]],
                    )
                updated_count += 1
            continue

        breach_deadline_at = session_start_at - COVERAGE_SLA_BREACH_LEAD_TIME
        if comparison_now < breach_deadline_at:
            next_metadata = {**metadata, **build_sla_metadata_patch(False, None, policy_key=SLA_POLICY_COVERAGE_SESSION_DEADLINE)}
            next_metadata.pop(COVERAGE_SLA_STATE_METADATA_KEY, None)
            if (
                sanitize_text(ticket.get("sla_status")) != "On Track"
                or normalize_bool(metadata.get("sla_attention_required"))
                or coverage_sla_state is not None
            ):
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE tickets
                        SET sla_status = %s,
                            metadata = %s::jsonb,
                            updated_at = NOW()
                        WHERE id = %s
                        """,
                        ["On Track", json.dumps(next_metadata), ticket["id"]],
                    )
                updated_count += 1
            continue

        previous_warning_triggered_at = coerce_datetime((coverage_sla_state or {}).get("warningTriggeredAt"))
        previous_breached_at = coerce_datetime((coverage_sla_state or {}).get("breachedAt"))
        previous_escalated_at = coerce_datetime((coverage_sla_state or {}).get("escalatedAt"))
        alert_level = ""

        if not previous_warning_triggered_at:
            alert_level = COVERAGE_SLA_STAGE_WARNING
            breached_at = comparison_now
            warning_triggered_at = comparison_now
            escalated_at = None
        else:
            breached_at = previous_breached_at or previous_warning_triggered_at
            warning_triggered_at = previous_warning_triggered_at
            escalation_due_at = breached_at + COVERAGE_SLA_ESCALATION_AFTER
            if not previous_escalated_at and comparison_now >= escalation_due_at:
                alert_level = COVERAGE_SLA_STAGE_ESCALATED
                escalated_at = comparison_now
            else:
                escalated_at = previous_escalated_at

        stage = COVERAGE_SLA_STAGE_ESCALATED if (previous_escalated_at or alert_level == COVERAGE_SLA_STAGE_ESCALATED) else COVERAGE_SLA_STAGE_WARNING
        next_state = build_coverage_sla_state(
            stage=stage,
            session_start_at=session_start_at,
            breach_deadline_at=breach_deadline_at,
            breached_at=breached_at,
            warning_triggered_at=warning_triggered_at,
            escalated_at=escalated_at,
        )
        next_metadata = {
            **metadata,
            **build_sla_metadata_patch(
                True,
                SLA_ATTENTION_REASON_COVERAGE_SESSION_DEADLINE,
                policy_key=SLA_POLICY_COVERAGE_SESSION_DEADLINE,
                due_at=breach_deadline_at,
                breached_at=breached_at,
            ),
            COVERAGE_SLA_STATE_METADATA_KEY: next_state,
        }

        should_persist = (
            sanitize_text(ticket.get("sla_status")) != "Breached"
            or not normalize_bool(metadata.get("sla_attention_required"))
            or sanitize_text(metadata.get("sla_attention_reason")) != SLA_ATTENTION_REASON_COVERAGE_SESSION_DEADLINE
            or normalize_coverage_sla_state(coverage_sla_state) != normalize_coverage_sla_state(next_state)
        )

        if should_persist:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE tickets
                    SET sla_status = %s,
                        metadata = %s::jsonb,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    ["Breached", json.dumps(next_metadata), ticket["id"]],
                )
            updated_count += 1

        if alert_level:
            if alert_level == COVERAGE_SLA_STAGE_WARNING:
                warning_count += 1
            elif alert_level == COVERAGE_SLA_STAGE_ESCALATED:
                escalation_count += 1

            alert_payload = build_coverage_sla_alert_webhook_payload(
                {**ticket, "sla_status": "Breached"},
                alert_level=alert_level,
                session_start_at=session_start_at,
                breach_deadline_at=breach_deadline_at,
                breached_at=breached_at,
            )
            webhook_result = send_coverage_sla_alert_webhook(alert_payload)
            insert_history_event(
                ticket["id"],
                "coverage_sla_alert",
                {"role": "system", "label": "System"},
                {
                    "ticketId": ticket.get("public_id"),
                    "alertLevel": alert_level,
                    "sessionStartAt": serialize_datetime_value(session_start_at),
                    "breachDeadlineAt": serialize_datetime_value(breach_deadline_at),
                    "breachedAt": serialize_datetime_value(breached_at),
                    "webhookConfigured": bool(webhook_result.get("configured")),
                    "webhookDelivered": bool(webhook_result.get("delivered")),
                    "webhookStatus": webhook_result.get("status"),
                },
            )

        breached_count += 1
        attention_required_count += 1

    return {
        "scanned": scanned_count,
        "updated": updated_count,
        "warnings": warning_count,
        "escalations": escalation_count,
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
    if not cursor.description:
        return []
    columns = [column[0] for column in cursor.description]
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

    try:
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
    except Exception:
        logger.warning("Legacy database lookup failed for email verification; skipping kbc_users_data check.")
        return None

    if not row:
        return None

    external_learner_id, full_name, normalized_email, phone = row
    return {
        "external_learner_id": external_learner_id,
        "full_name": full_name,
        "email": normalized_email,
        "phone": phone,
    }


def run_communication_centre_query(
    sql: str,
    params: list[Any] | tuple[Any, ...] | None = None,
) -> list[dict[str, Any]]:
    communication_centre_url = sanitize_text(getattr(settings, "COMMUNICATION_CENTRE_DATABASE_URL", ""))
    if not communication_centre_url:
        raise ApiError(503, "Coverage options are not configured on the server.")

    with psycopg.connect(communication_centre_url) as source_connection:
        with source_connection.cursor() as cursor:
            cursor.execute(sql, params or [])
            return dictfetchall(cursor)


def run_aptem_auto_extracting_query(
    sql: str,
    params: list[Any] | tuple[Any, ...] | None = None,
) -> list[dict[str, Any]]:
    aptem_auto_extracting_url = sanitize_text(getattr(settings, "APTEM_AUTO_EXTRACTING_DATABASE_URL", ""))
    if not aptem_auto_extracting_url:
        raise ApiError(503, "Aptem coach options are not configured on the server.")

    with psycopg.connect(aptem_auto_extracting_url) as source_connection:
        with source_connection.cursor() as cursor:
            cursor.execute(sql, params or [])
            return dictfetchall(cursor)


def format_coverage_time_option_label(
    week_day: Any,
    start_time: Any,
    end_time: Any,
    group_name: Any,
    cohort_name: Any,
) -> str:
    normalized_week_day = sanitize_text(week_day).title()
    normalized_start_time = sanitize_text(start_time)
    normalized_end_time = sanitize_text(end_time)
    normalized_group_name = sanitize_text(group_name)
    normalized_cohort_name = sanitize_text(cohort_name)

    day_and_time_parts = [part for part in [normalized_week_day, normalized_start_time] if part]
    if normalized_end_time:
        if normalized_start_time:
            day_and_time_parts[-1] = f"{normalized_start_time} - {normalized_end_time}"
        else:
            day_and_time_parts.append(normalized_end_time)

    label_parts = []
    if day_and_time_parts:
        label_parts.append(" ".join(day_and_time_parts))
    if normalized_group_name:
        label_parts.append(normalized_group_name)
    if normalized_cohort_name:
        label_parts.append(normalized_cohort_name)

    return " | ".join(label_parts)


def parse_coverage_plan_date(value: Any):
    normalized_value = sanitize_text(value)
    if not normalized_value:
        return None

    try:
        return datetime.strptime(normalized_value, "%Y-%m-%d").date()
    except ValueError:
        try:
            return datetime.fromisoformat(normalized_value.replace("Z", "+00:00")).date()
        except ValueError:
            return None


def get_coverage_weekday_index(value: Any) -> int | None:
    normalized_value = re.sub(r"[^a-z]", "", sanitize_text(value).lower())
    if not normalized_value:
        return None

    weekday_indexes = {
        "monday": 0,
        "mon": 0,
        "tuesday": 1,
        "tue": 1,
        "tues": 1,
        "wednesday": 2,
        "wed": 2,
        "thursday": 3,
        "thu": 3,
        "thur": 3,
        "thurs": 3,
        "friday": 4,
        "fri": 4,
        "saturday": 5,
        "sat": 5,
        "sunday": 6,
        "sun": 6,
    }
    return weekday_indexes.get(normalized_value)


def format_coverage_session_date_option_label(value) -> str:
    return value.strftime("%A %d %b %Y")


def parse_coverage_session_date_label(value: Any):
    normalized_value = sanitize_text(value).replace(",", " ")
    normalized_value = re.sub(r"\s+", " ", normalized_value).strip()
    if not normalized_value:
        return None

    for date_format in ("%A %d %b %Y", "%A %d %B %Y", "%d %b %Y", "%d %B %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(normalized_value, date_format).date()
        except ValueError:
            continue

    return parse_coverage_plan_date(normalized_value)


def parse_coverage_session_date_values(value: Any) -> list:
    raw_values = value if isinstance(value, list) else sanitize_text(value).split(";")
    parsed_dates = []
    seen_dates = set()

    for raw_value in raw_values:
        parsed_date = parse_coverage_session_date_label(raw_value)
        if not parsed_date or parsed_date in seen_dates:
            continue
        seen_dates.add(parsed_date)
        parsed_dates.append(parsed_date)

    return parsed_dates


def parse_coverage_time_value_to_minutes(value: str) -> int | None:
    normalized_value = sanitize_text(value).lower()
    if not normalized_value:
        return None

    match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", normalized_value)
    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2) or "0")
    meridiem = match.group(3)
    if meridiem == "pm" and hour < 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0

    if hour > 23 or minute > 59:
        return None
    return hour * 60 + minute


def parse_coverage_time_range(value: Any) -> tuple[int, int] | None:
    normalized_value = sanitize_text(value)
    if not normalized_value:
        return None

    time_matches = re.findall(r"\d{1,2}(?::\d{2})?\s*(?:am|pm)?", normalized_value, flags=re.IGNORECASE)
    if len(time_matches) < 2:
        return None

    start_minutes = parse_coverage_time_value_to_minutes(time_matches[0])
    end_minutes = parse_coverage_time_value_to_minutes(time_matches[1])
    if start_minutes is None or end_minutes is None or start_minutes >= end_minutes:
        return None

    return start_minutes, end_minutes


def get_coverage_plan_effective_end_date(row: dict[str, Any], start_date):
    end_date = parse_coverage_plan_date(row.get("end_date"))
    if end_date or not start_date:
        return end_date

    try:
        sessions_number = int(sanitize_text(row.get("sessions_number")))
    except ValueError:
        sessions_number = 0

    if sessions_number > 0:
        return start_date + timedelta(days=7 * (sessions_number - 1))

    return None


def coverage_plan_row_occurs_on_date(row: dict[str, Any], session_date) -> bool:
    start_date = parse_coverage_plan_date(row.get("start_date"))
    if not start_date:
        return False

    weekday_index = get_coverage_weekday_index(row.get("session_week_day"))
    if weekday_index is None:
        return False

    effective_end_date = get_coverage_plan_effective_end_date(row, start_date)
    if session_date < start_date or (effective_end_date and session_date > effective_end_date):
        return False

    first_occurrence = start_date + timedelta(days=(weekday_index - start_date.weekday()) % 7)
    return session_date >= first_occurrence and (session_date - first_occurrence).days % 7 == 0


def coverage_time_ranges_overlap(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left[0] < right[1] and right[0] < left[1]


def list_coverage_time_rows(tutor: Any, module: Any) -> list[dict[str, Any]]:
    normalized_tutor = sanitize_text(tutor).lower()
    normalized_module = sanitize_text(module).lower()
    if not normalized_tutor or not normalized_module:
        return []

    return run_communication_centre_query(
        """
        SELECT DISTINCT
          NULLIF(TRIM("session_week_day"), '') AS session_week_day,
          NULLIF(TRIM("session_start_time"), '') AS session_start_time,
          NULLIF(TRIM("session_end_time"), '') AS session_end_time,
          NULLIF(TRIM("group_name"), '') AS group_name,
          NULLIF(TRIM("Cohort_name"), '') AS cohort_name,
          NULLIF(TRIM("start_date"), '') AS start_date,
          NULLIF(TRIM("end_date"), '') AS end_date
        FROM public."Training_plan"
        WHERE (
          LOWER(TRIM("Tutor_name")) = %s
          OR EXISTS (
            SELECT 1
            FROM regexp_split_to_table(COALESCE("Tutor_name", ''), '\\+') AS tutor_part
            WHERE LOWER(TRIM(tutor_part)) = %s
          )
        )
          AND LOWER(TRIM("module_name")) = %s
        ORDER BY session_week_day, session_start_time, session_end_time, group_name, cohort_name, start_date, end_date
        """,
        [normalized_tutor, normalized_tutor, normalized_module],
    )


def list_coverage_tutor_options(module: Any = None) -> list[str]:
    normalized_module = sanitize_text(module).lower()
    if normalized_module:
        rows = run_communication_centre_query(
            """
            SELECT tutor_name
            FROM (
              SELECT DISTINCT NULLIF(TRIM("Tutor_name"), '') AS tutor_name
              FROM public."Training_plan"
              WHERE LOWER(TRIM("module_name")) = %s
            ) coverage_tutors
            WHERE tutor_name IS NOT NULL
            ORDER BY LOWER(tutor_name), tutor_name
            """,
            [normalized_module],
        )
    else:
        rows = run_communication_centre_query(
            """
            SELECT tutor_name
            FROM (
              SELECT DISTINCT NULLIF(TRIM("Tutor_name"), '') AS tutor_name
              FROM public."Training_plan"
            ) coverage_tutors
            WHERE tutor_name IS NOT NULL
            ORDER BY LOWER(tutor_name), tutor_name
            """
        )
    tutor_names_by_key: dict[str, str] = {}

    for row in rows:
        raw_tutor_name = sanitize_text(row.get("tutor_name"))
        if not raw_tutor_name:
            continue

        for tutor_name_part in raw_tutor_name.split("+"):
            tutor_name = sanitize_text(tutor_name_part)
            if not tutor_name:
                continue
            tutor_names_by_key.setdefault(tutor_name.lower(), tutor_name)

    return [tutor_names_by_key[key] for key in sorted(tutor_names_by_key)]


def list_coverage_tutor_availability_plan_rows() -> list[dict[str, Any]]:
    return run_communication_centre_query(
        """
        SELECT DISTINCT
          NULLIF(TRIM("Tutor_name"), '') AS tutor_name,
          NULLIF(TRIM("module_name"), '') AS module_name,
          NULLIF(TRIM("session_week_day"), '') AS session_week_day,
          NULLIF(TRIM("session_start_time"), '') AS session_start_time,
          NULLIF(TRIM("session_end_time"), '') AS session_end_time,
          NULLIF(TRIM("group_name"), '') AS group_name,
          NULLIF(TRIM("Cohort_name"), '') AS cohort_name,
          NULLIF(TRIM("start_date"), '') AS start_date,
          NULLIF(TRIM("end_date"), '') AS end_date,
          NULLIF(TRIM("sessions_number"), '') AS sessions_number
        FROM public."Training_plan"
        WHERE NULLIF(TRIM("Tutor_name"), '') IS NOT NULL
        ORDER BY tutor_name, module_name, session_week_day, session_start_time, start_date
        """
    )


def summarize_coverage_tutor_plan_module(row: dict[str, Any]) -> dict[str, Any]:
    start_date = parse_coverage_plan_date(row.get("start_date"))
    effective_end_date = get_coverage_plan_effective_end_date(row, start_date)
    return {
        "moduleName": sanitize_text(row.get("module_name")),
        "timeLabel": format_coverage_time_option_label(
            row.get("session_week_day"),
            row.get("session_start_time"),
            row.get("session_end_time"),
            row.get("group_name"),
            row.get("cohort_name"),
        ),
        "startDate": start_date.isoformat() if start_date else "",
        "endDate": effective_end_date.isoformat() if effective_end_date else "",
    }


def build_coverage_tutor_availability_items(
    rows: list[dict[str, Any]],
    *,
    time_label: Any,
    session_dates: Any,
) -> list[dict[str, Any]]:
    requested_dates = parse_coverage_session_date_values(session_dates)
    requested_time_range = parse_coverage_time_range(time_label)
    rows_by_tutor_key: dict[str, dict[str, Any]] = {}

    for row in rows:
        raw_tutor_name = sanitize_text(row.get("tutor_name"))
        if not raw_tutor_name:
            continue

        for tutor_name_part in raw_tutor_name.split("+"):
            tutor_name = sanitize_text(tutor_name_part)
            if not tutor_name:
                continue

            tutor_key = tutor_name.lower()
            tutor_payload = rows_by_tutor_key.setdefault(tutor_key, {"tutor": tutor_name, "rows": []})
            tutor_payload["rows"].append(row)

    items = []
    for tutor_key in sorted(rows_by_tutor_key):
        tutor_payload = rows_by_tutor_key[tutor_key]
        tutor_rows = tutor_payload["rows"]
        module_summaries_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
        conflicts: list[dict[str, Any]] = []

        for row in tutor_rows:
            module_summary = summarize_coverage_tutor_plan_module(row)
            module_key = (
                module_summary["moduleName"].lower(),
                module_summary["timeLabel"].lower(),
                module_summary["startDate"],
            )
            if module_summary["moduleName"] or module_summary["timeLabel"]:
                module_summaries_by_key.setdefault(module_key, module_summary)

            row_time_range = parse_coverage_time_range(
                f"{sanitize_text(row.get('session_start_time'))} - {sanitize_text(row.get('session_end_time'))}"
            )
            if not requested_dates or not requested_time_range or not row_time_range:
                continue

            for requested_date in requested_dates:
                if (
                    coverage_plan_row_occurs_on_date(row, requested_date)
                    and coverage_time_ranges_overlap(requested_time_range, row_time_range)
                ):
                    conflicts.append(
                        {
                            **module_summary,
                            "date": requested_date.isoformat(),
                            "dateLabel": format_coverage_session_date_option_label(requested_date),
                        }
                    )
                    break

        if not requested_dates or not requested_time_range:
            status = "unknown"
            label = "Need date/time"
            summary = "Choose the coverage date and time to check this tutor's training plan availability."
        elif conflicts:
            status = "busy"
            label = "Busy"
            first_conflict = conflicts[0]
            conflict_module = sanitize_text(first_conflict.get("moduleName")) or "another module"
            summary = f"Busy with {conflict_module} on {first_conflict.get('dateLabel') or first_conflict.get('date')}."
        elif tutor_rows:
            status = "available"
            label = "Available"
            summary = "No Training_plan conflict was found for the selected coverage date and time."
        else:
            status = "no_plan"
            label = "No plan data"
            summary = "No Training_plan rows were found for this tutor."

        items.append(
            {
                "tutor": tutor_payload["tutor"],
                "status": status,
                "label": label,
                "summary": summary,
                "conflictCount": len(conflicts),
                "conflicts": conflicts[:3],
                "modules": list(module_summaries_by_key.values())[:6],
            }
        )

    return items


def list_coverage_tutor_availability_items(time_label: Any, session_dates: Any) -> list[dict[str, Any]]:
    return build_coverage_tutor_availability_items(
        list_coverage_tutor_availability_plan_rows(),
        time_label=time_label,
        session_dates=session_dates,
    )


def list_coverage_module_options(tutor: Any) -> list[str]:
    normalized_tutor = sanitize_text(tutor).lower()
    if not normalized_tutor:
        return []

    rows = run_communication_centre_query(
        """
        SELECT DISTINCT
          NULLIF(TRIM("module_name"), '') AS module_name,
          NULLIF(TRIM("session_week_day"), '') AS session_week_day,
          NULLIF(TRIM("session_start_time"), '') AS session_start_time,
          NULLIF(TRIM("session_end_time"), '') AS session_end_time,
          NULLIF(TRIM("group_name"), '') AS group_name,
          NULLIF(TRIM("Cohort_name"), '') AS cohort_name,
          NULLIF(TRIM("end_date"), '') AS end_date
        FROM public."Training_plan"
        WHERE (
          LOWER(TRIM("Tutor_name")) = %s
          OR EXISTS (
            SELECT 1
            FROM regexp_split_to_table(COALESCE("Tutor_name", ''), '\\+') AS tutor_part
            WHERE LOWER(TRIM(tutor_part)) = %s
          )
        )
        ORDER BY module_name
        """,
        [normalized_tutor, normalized_tutor],
    )
    module_names_by_key: dict[str, str] = {}
    today = django_timezone.localdate()

    for row in rows:
        module_name = sanitize_text(row.get("module_name"))
        if not module_name:
            continue

        time_label = format_coverage_time_option_label(
            row.get("session_week_day"),
            row.get("session_start_time"),
            row.get("session_end_time"),
            row.get("group_name"),
            row.get("cohort_name"),
        )
        if not time_label:
            continue

        end_date = parse_coverage_plan_date(row.get("end_date"))
        if end_date and end_date < today:
            continue

        module_names_by_key.setdefault(module_name.lower(), module_name)

    return [module_names_by_key[key] for key in sorted(module_names_by_key)]


def list_coverage_time_options(tutor: Any, module: Any) -> list[str]:
    return [item["label"] for item in list_coverage_time_option_items(tutor, module)]


def list_coverage_time_option_items(tutor: Any, module: Any) -> list[dict[str, Any]]:
    rows = list_coverage_time_rows(tutor, module)

    items: list[dict[str, Any]] = []
    item_indexes_by_label: dict[str, int] = {}
    today = django_timezone.localdate()
    for row in rows:
        label = format_coverage_time_option_label(
            row.get("session_week_day"),
            row.get("session_start_time"),
            row.get("session_end_time"),
            row.get("group_name"),
            row.get("cohort_name"),
        )
        if not label:
            continue

        end_date = parse_coverage_plan_date(row.get("end_date"))
        is_completed = bool(end_date and end_date < today)
        if label in item_indexes_by_label:
            existing_item = items[item_indexes_by_label[label]]
            existing_item["completed"] = bool(existing_item.get("completed")) and is_completed
            existing_end_date = sanitize_text(existing_item.get("endDate"))
            next_end_date = end_date.isoformat() if end_date else ""
            if next_end_date and (not existing_end_date or next_end_date > existing_end_date):
                existing_item["endDate"] = next_end_date
            continue

        item_indexes_by_label[label] = len(items)
        items.append(
            {
                "label": label,
                "completed": is_completed,
                "endDate": end_date.isoformat() if end_date else "",
            }
        )

    return items


def list_coverage_session_date_options(tutor: Any, module: Any, time_label: Any) -> list[str]:
    normalized_time_label = sanitize_text(time_label)
    if not normalized_time_label:
        return []

    rows = list_coverage_time_rows(tutor, module)
    labels: list[str] = []
    seen_labels: set[str] = set()
    today = django_timezone.localdate()

    for row in rows:
        row_time_label = format_coverage_time_option_label(
            row.get("session_week_day"),
            row.get("session_start_time"),
            row.get("session_end_time"),
            row.get("group_name"),
            row.get("cohort_name"),
        )
        if row_time_label != normalized_time_label:
            continue

        start_date = parse_coverage_plan_date(row.get("start_date"))
        end_date = parse_coverage_plan_date(row.get("end_date"))
        weekday_index = get_coverage_weekday_index(row.get("session_week_day"))
        if not start_date or not end_date or weekday_index is None or end_date < start_date or end_date < today:
            continue

        first_possible_date = max(start_date, today)
        days_until_weekday = (weekday_index - first_possible_date.weekday()) % 7
        candidate_date = first_possible_date + timedelta(days=days_until_weekday)

        while candidate_date <= end_date:
            label = format_coverage_session_date_option_label(candidate_date)
            if label not in seen_labels:
                seen_labels.add(label)
                labels.append(label)
            candidate_date += timedelta(days=7)

    return labels


def get_coverage_tutor_email(tutor: Any) -> str:
    normalized_tutor = sanitize_text(tutor).lower()
    if not normalized_tutor:
        return ""

    rows = run_communication_centre_query(
        """
        SELECT NULLIF(TRIM("Tutor_email"), '') AS tutor_email
        FROM public."Tutors_Modules"
        WHERE (
          LOWER(TRIM("Tutor_name")) = %s
          OR EXISTS (
            SELECT 1
            FROM regexp_split_to_table(COALESCE("Tutor_name", ''), '\\+') AS tutor_part
            WHERE LOWER(TRIM(tutor_part)) = %s
          )
        )
        ORDER BY
          CASE WHEN LOWER(TRIM("Tutor_name")) = %s THEN 0 ELSE 1 END,
          NULLIF(TRIM("Tutor_email"), '') DESC NULLS LAST
        """,
        [normalized_tutor, normalized_tutor, normalized_tutor],
    )

    for row in rows:
        email = normalize_email(row.get("tutor_email"))
        if is_valid_email(email):
            return email

    return ""


def list_coverage_coach_options() -> list[str]:
    rows = run_aptem_auto_extracting_query(
        """
        SELECT coach_name
        FROM (
          SELECT DISTINCT NULLIF(TRIM("OwnerName"), '') AS coach_name
          FROM public.aptem_auto_extracting
        ) coverage_coaches
        WHERE coach_name IS NOT NULL
          AND LOWER(coach_name) <> ALL(%s)
        ORDER BY LOWER(coach_name), coach_name
        """,
        [sorted(EXCLUDED_APTEM_OWNER_NAMES)],
    )
    coach_names_by_key: dict[str, str] = {}

    for row in rows:
        coach_name = sanitize_text(row.get("coach_name"))
        if coach_name and coach_name.lower() not in EXCLUDED_APTEM_OWNER_NAMES:
            coach_names_by_key.setdefault(coach_name.lower(), coach_name)

    return [coach_names_by_key[key] for key in sorted(coach_names_by_key)]


def get_coverage_coach_email(coach: Any) -> str:
    normalized_coach = sanitize_text(coach).lower()
    if not normalized_coach:
        return ""

    rows = run_aptem_auto_extracting_query(
        """
        SELECT DISTINCT NULLIF(TRIM("OwnerEmail"), '') AS coach_email
        FROM public.aptem_auto_extracting
        WHERE LOWER(TRIM("OwnerName")) = %s
        ORDER BY
          NULLIF(TRIM("OwnerEmail"), '') DESC NULLS LAST
        """,
        [normalized_coach],
    )

    for row in rows:
        email = normalize_email(row.get("coach_email"))
        if is_valid_email(email):
            return email

    return ""


def get_coverage_options_response(payload: dict[str, Any]) -> dict[str, Any]:
    option_type = sanitize_text(payload.get("type")).lower()
    tutor = payload.get("tutor")
    coach = payload.get("coach")
    module = payload.get("module")
    time_label = payload.get("time")
    session_dates = payload.get("sessionDates")

    if option_type == "tutors":
        options = list_coverage_tutor_options(module)
    elif option_type == "tutor-availability":
        items = list_coverage_tutor_availability_items(time_label, session_dates)
        options = [item["tutor"] for item in items]
    elif option_type == "coaches":
        options = list_coverage_coach_options()
    elif option_type == "modules":
        options = list_coverage_module_options(tutor)
    elif option_type == "times":
        items = list_coverage_time_option_items(tutor, module)
        options = [item["label"] for item in items]
    elif option_type == "session-dates":
        options = list_coverage_session_date_options(tutor, module, time_label)
    elif option_type == "tutor-email":
        return {
            "type": option_type,
            "value": get_coverage_tutor_email(tutor),
        }
    elif option_type == "coach-email":
        return {
            "type": option_type,
            "value": get_coverage_coach_email(coach),
        }
    else:
        raise ApiError(400, "Please choose a valid coverage option type.")

    return {
        "type": option_type,
        "options": options,
        **({"items": items} if option_type in {"times", "tutor-availability"} else {}),
    }


def get_coverage_tutor_request_webhook_url() -> str:
    return sanitize_text(getattr(settings, "MAIL_WEBHOOK_URL", ""))


def get_support_notification_webhook_url() -> str:
    return sanitize_text(getattr(settings, "SUPPORT_NOTIFICATION_WEBHOOK_URL", ""))


def is_support_notification_delivery_enabled() -> bool:
    return bool(getattr(settings, "SUPPORT_NOTIFICATION_DELIVERY_ENABLED", True))


def get_coverage_ticket_operations_webhook_url() -> str:
    return sanitize_text(getattr(settings, "COVERAGE_TICKET_WEBHOOK_URL", ""))


def get_coverage_ticket_operations_webhook_secret() -> str:
    return sanitize_text(getattr(settings, "COVERAGE_TICKET_WEBHOOK_SECRET", ""))


def build_coverage_ticket_operations_webhook_headers() -> dict[str, str]:
    secret = get_coverage_ticket_operations_webhook_secret()
    if not secret:
        return {}
    return {"x-support-webhook-secret": secret}


def get_coverage_sla_alerts_webhook_url() -> str:
    return sanitize_text(getattr(settings, "COVERAGE_SLA_WEBHOOK_URL", ""))


def get_coverage_tutor_response_mail_webhook_url() -> str:
    return sanitize_text(getattr(settings, "COVERAGE_TUTOR_RESPONSE_MAIL_WEBHOOK_URL", ""))


def get_coverage_tutor_attachment_reply_webhook_url() -> str:
    return (
        sanitize_text(getattr(settings, "COVERAGE_TUTOR_ATTACHMENT_REPLY_WEBHOOK_URL", ""))
        or get_coverage_tutor_request_webhook_url()
    )


def normalize_support_portal_public_base_url(value: Any) -> str:
    normalized_value = sanitize_text(value).rstrip("/")
    if not normalized_value:
        return ""

    parsed = urllib_parse.urlparse(normalized_value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path not in {"", "/"}:
        return ""

    return f"{parsed.scheme}://{parsed.netloc}"


def get_support_portal_public_base_url(fallback_origin: Any = "") -> str:
    configured_base_url = normalize_support_portal_public_base_url(
        getattr(settings, "SUPPORT_PORTAL_PUBLIC_BASE_URL", ""),
    )
    if configured_base_url:
        return configured_base_url

    return normalize_support_portal_public_base_url(fallback_origin)


def build_coverage_tutor_public_response_base_url(fallback_origin: Any = "") -> str:
    public_base_url = get_support_portal_public_base_url(fallback_origin)
    if not public_base_url:
        return ""

    return f"{public_base_url}/coverage/tutor-response"


def build_coverage_tutor_public_result_base_url(fallback_origin: Any = "") -> str:
    public_base_url = get_support_portal_public_base_url(fallback_origin)
    if not public_base_url:
        return ""

    return f"{public_base_url}/coverage/tutor-response/result"


def build_coverage_tutor_public_response_action_url(
    public_response_base_url: Any,
    *,
    action: str,
    ticket_public_id: Any,
    card_id: Any,
    response_token: Any,
    tutor_email: Any = "",
) -> str:
    normalized_base_url = sanitize_text(public_response_base_url).rstrip("/")
    if not normalized_base_url:
        return ""

    query_payload = {
        "action": sanitize_text(action).lower(),
        "ticketId": sanitize_text(ticket_public_id),
        "cardId": sanitize_text(card_id),
        "responseToken": sanitize_text(response_token),
    }
    normalized_tutor_email = normalize_email(tutor_email)
    if normalized_tutor_email:
        query_payload["tutorEmail"] = normalized_tutor_email

    query_string = urllib_parse.urlencode({key: value for key, value in query_payload.items() if value})
    return f"{normalized_base_url}?{query_string}" if query_string else normalized_base_url


def build_coverage_tutor_public_result_action_url(
    public_result_base_url: Any,
    *,
    action: str,
) -> str:
    normalized_base_url = sanitize_text(public_result_base_url).rstrip("/")
    if not normalized_base_url:
        return ""

    normalized_action = sanitize_text(action).lower()
    if not normalized_action:
        return normalized_base_url

    return f"{normalized_base_url}?{urllib_parse.urlencode({'action': normalized_action})}"


def build_coverage_tutor_request_webhook_payload(
    ticket: dict[str, Any],
    documentation: dict[str, Any],
    card: dict[str, Any],
    actor_row: dict[str, Any],
    *,
    callback_url: str = "",
    result_base_url: str = "",
) -> dict[str, Any]:
    accept_url = build_coverage_tutor_public_response_action_url(
        callback_url,
        action="accept",
        ticket_public_id=ticket["public_id"],
        card_id=card["id"],
        response_token=card.get("responseToken"),
        tutor_email=card.get("tutorEmail"),
    )
    refuse_url = build_coverage_tutor_public_response_action_url(
        callback_url,
        action="refuse",
        ticket_public_id=ticket["public_id"],
        card_id=card["id"],
        response_token=card.get("responseToken"),
        tutor_email=card.get("tutorEmail"),
    )
    accept_result_url = build_coverage_tutor_public_result_action_url(
        result_base_url,
        action="accept",
    )
    refuse_result_url = build_coverage_tutor_public_result_action_url(
        result_base_url,
        action="refuse",
    )

    return {
        "event": "coverage_tutor_requested",
        "source": "support_portal",
        "ticketId": ticket["public_id"],
        "cardId": card["id"],
        "responseToken": card.get("responseToken"),
        "acceptUrl": accept_url,
        "refuseUrl": refuse_url,
        "acceptResultUrl": accept_result_url,
        "refuseResultUrl": refuse_result_url,
        "tutor": {
            "name": card.get("tutor"),
            "email": card.get("tutorEmail"),
        },
        "coach": {
            "name": card.get("coach"),
            "email": card.get("coachEmail"),
        },
        "learner": {
            "name": ticket.get("learner_name"),
            "email": ticket.get("learner_email"),
        },
        "request": {
            "category": ticket.get("category"),
            "technicalSubcategory": ticket.get("technical_subcategory"),
            "inquiry": ticket.get("inquiry"),
            "sessionDetails": card.get("sessionDetails"),
            "notes": documentation.get("coverageNotes") or "",
            "presentationFiles": card.get("presentationFiles") or [],
        },
        "requestedBy": {
            "agentId": int(actor_row["id"]),
            "agentName": actor_row.get("full_name") or actor_row["username"],
            "agentUsername": actor_row["username"],
            "agentEmail": actor_row.get("email") or "",
        },
        "callback": {
            "ticketId": ticket["public_id"],
            "cardId": card["id"],
            "responseToken": card.get("responseToken"),
            "url": callback_url or "",
            "path": "/coverage/tutor-response",
            "acceptUrl": accept_url,
            "refuseUrl": refuse_url,
            "result": {
                "path": "/coverage/tutor-response/result",
                "acceptUrl": accept_result_url,
                "refuseUrl": refuse_result_url,
            },
        },
    }


def build_coverage_tutor_original_email_payload(tutor_emails: Any, tutor_email: Any) -> dict[str, Any]:
    normalized_tutor_email = normalize_email(tutor_email)
    if not normalized_tutor_email:
        return {
            "recipientEmail": "",
            "sentAt": "",
            "gmailThreadId": "",
            "gmailMessageId": "",
            "canReplyToExistingThread": False,
        }

    email_records = normalize_json_object(tutor_emails)
    original_email_record = normalize_json_object(email_records.get(normalized_tutor_email))
    if not original_email_record:
        for email_key, value in email_records.items():
            if normalize_email(email_key) == normalized_tutor_email:
                original_email_record = normalize_json_object(value)
                break

    gmail_thread_id = sanitize_text(
        original_email_record.get("gmail_thread_id") or original_email_record.get("gmailThreadId")
    )
    gmail_message_id = sanitize_text(
        original_email_record.get("gmail_message_id") or original_email_record.get("gmailMessageId")
    )

    return {
        "recipientEmail": normalized_tutor_email,
        "sentAt": sanitize_text(original_email_record.get("sent_at") or original_email_record.get("sentAt")),
        "gmailThreadId": gmail_thread_id,
        "gmailMessageId": gmail_message_id,
        "canReplyToExistingThread": bool(gmail_thread_id or gmail_message_id),
    }


def build_coverage_tutor_follow_up_webhook_payload(
    ticket: dict[str, Any],
    documentation: dict[str, Any],
    card: dict[str, Any],
    follow_up_files: list[dict[str, Any]],
    actor_row: dict[str, Any],
    *,
    sent_at: str = "",
) -> dict[str, Any]:
    public_base_url = get_support_portal_public_base_url("")
    dashboard_url = f"{public_base_url}/admin" if public_base_url else ""
    original_email_payload = build_coverage_tutor_original_email_payload(
        ticket.get("tutor_emails"),
        card.get("tutorEmail"),
    )

    return {
        "event": "coverage_tutor_follow_up",
        "source": "support_portal",
        "ticketId": ticket["public_id"],
        "cardId": card["id"],
        "responseToken": card.get("responseToken"),
        "dashboardUrl": dashboard_url,
        "originalEmail": original_email_payload,
        # Keep top-level aliases for automation workflows that do not read nested payloads.
        "tutorName": card.get("tutor"),
        "tutorEmail": card.get("tutorEmail"),
        "coachName": card.get("coach"),
        "coachEmail": card.get("coachEmail"),
        "note": documentation.get("coverageNotes") or "",
        "attachments": follow_up_files,
        "gmailThreadId": original_email_payload.get("gmailThreadId"),
        "gmailMessageId": original_email_payload.get("gmailMessageId"),
        "canReplyToExistingThread": original_email_payload.get("canReplyToExistingThread"),
        "tutor": {
            "name": card.get("tutor"),
            "email": card.get("tutorEmail"),
        },
        "coach": {
            "name": card.get("coach"),
            "email": card.get("coachEmail"),
        },
        "learner": {
            "name": ticket.get("learner_name"),
            "email": ticket.get("learner_email"),
        },
        "request": {
            "category": ticket.get("category"),
            "technicalSubcategory": ticket.get("technical_subcategory"),
            "inquiry": ticket.get("inquiry"),
            "requestStatus": sanitize_text(card.get("requestStatus")) or "requested",
            "requestedAt": card.get("submittedAt") or "",
            "respondedAt": card.get("respondedAt") or "",
            "sessionDetails": card.get("sessionDetails"),
            "notes": documentation.get("coverageNotes") or "",
            "presentationFiles": card.get("presentationFiles") or [],
        },
        "followUp": {
            "sentAt": sent_at,
            "fileCount": len(follow_up_files),
            "presentationFiles": follow_up_files,
        },
        "sentBy": {
            "agentId": int(actor_row["id"]),
            "agentName": actor_row.get("full_name") or actor_row["username"],
            "agentUsername": actor_row["username"],
            "agentEmail": actor_row.get("email") or "",
        },
    }


def strip_webhook_attachment_binary_fields(value: Any) -> Any:
    if isinstance(value, list):
        return [strip_webhook_attachment_binary_fields(item) for item in value]
    if isinstance(value, dict):
        return {
            key: strip_webhook_attachment_binary_fields(item)
            for key, item in value.items()
            if key not in {"dataUrl", "storageKey"}
        }
    return value


def send_coverage_tutor_request_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    url = get_coverage_tutor_request_webhook_url()
    request_payload = normalize_json_object(payload.get("request"))
    files = request_payload.get("presentationFiles") if isinstance(request_payload.get("presentationFiles"), list) else []
    if files:
        configured, delivered, status, response_payload = post_multipart_webhook(
            url,
            strip_webhook_attachment_binary_fields(payload),
            files,
            timeout_seconds=COVERAGE_TUTOR_WEBHOOK_TIMEOUT_SECONDS,
        )
    else:
        configured, delivered, status, response_payload = post_json_webhook(
            url,
            payload,
            timeout_seconds=COVERAGE_TUTOR_WEBHOOK_TIMEOUT_SECONDS,
        )
    return {
        "configured": configured,
        "delivered": delivered,
        "status": status,
        "response": response_payload,
    }


def send_coverage_tutor_follow_up_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    url = get_coverage_tutor_attachment_reply_webhook_url()
    follow_up_payload = normalize_json_object(payload.get("followUp"))
    files = follow_up_payload.get("presentationFiles") if isinstance(follow_up_payload.get("presentationFiles"), list) else []
    if not files and isinstance(payload.get("attachments"), list):
        files = payload["attachments"]
    configured, delivered, status, response_payload = post_multipart_webhook(
        url,
        strip_webhook_attachment_binary_fields(payload),
        files,
        timeout_seconds=COVERAGE_TUTOR_WEBHOOK_TIMEOUT_SECONDS,
    )
    return {
        "configured": configured,
        "delivered": delivered,
        "status": status,
        "response": response_payload,
    }


def ensure_coverage_tutor_request_webhook_configured() -> None:
    if not get_coverage_tutor_request_webhook_url():
        raise ApiError(503, "The tutor request webhook is not configured on the server.")


def ensure_coverage_tutor_follow_up_webhook_configured() -> None:
    if not get_coverage_tutor_attachment_reply_webhook_url():
        raise ApiError(503, "The tutor follow-up files webhook is not configured on the server.")


def queue_coverage_tutor_request_webhook_delivery(
    *,
    ticket_id: int,
    ticket_public_id: str,
    card_id: str,
    payload: dict[str, Any],
) -> None:
    if not get_coverage_tutor_request_webhook_url():
        return

    def deliver() -> None:
        result = send_coverage_tutor_request_webhook(payload)
        event_type = (
            "coverage_tutor_request_webhook_delivered"
            if result.get("delivered")
            else "coverage_tutor_request_webhook_failed"
        )
        try:
            insert_history_event(
                ticket_id,
                event_type,
                {"role": "system", "label": "System"},
                {
                    "ticketId": ticket_public_id,
                    "cardId": card_id,
                    "webhookConfigured": bool(result.get("configured")),
                    "webhookDelivered": bool(result.get("delivered")),
                    "webhookStatus": result.get("status"),
                },
            )
        except Exception:
            # Webhook delivery must never break the saved tutor request.
            return

    thread = threading.Thread(
        target=deliver,
        name=f"coverage-tutor-request-webhook-{ticket_public_id}-{card_id}",
        daemon=True,
    )
    thread.start()


def queue_coverage_tutor_follow_up_webhook_delivery(
    *,
    ticket_id: int,
    ticket_public_id: str,
    card_id: str,
    payload: dict[str, Any],
) -> None:
    if not get_coverage_tutor_attachment_reply_webhook_url():
        return

    def deliver() -> None:
        result = send_coverage_tutor_follow_up_webhook(payload)
        event_type = (
            "coverage_tutor_follow_up_webhook_delivered"
            if result.get("delivered")
            else "coverage_tutor_follow_up_webhook_failed"
        )
        try:
            insert_history_event(
                ticket_id,
                event_type,
                {"role": "system", "label": "System"},
                {
                    "ticketId": ticket_public_id,
                    "cardId": card_id,
                    "webhookConfigured": bool(result.get("configured")),
                    "webhookDelivered": bool(result.get("delivered")),
                    "webhookStatus": result.get("status"),
                },
            )
        except Exception:
            return

    thread = threading.Thread(
        target=deliver,
        name=f"coverage-tutor-follow-up-webhook-{ticket_public_id}-{card_id}",
        daemon=True,
    )
    thread.start()


def build_coverage_tutor_refusal_mail_webhook_payload(
    *,
    ticket: dict[str, Any],
    tutor_choice_card: dict[str, Any],
    latest_response_payload: dict[str, Any],
    next_status: str,
    next_status_reason: str,
) -> dict[str, Any]:
    public_base_url = get_support_portal_public_base_url("")
    dashboard_url = f"{public_base_url}/admin" if public_base_url else ""
    session_details = sanitize_text(tutor_choice_card.get("sessionDetails")) or sanitize_text(
        latest_response_payload.get("sessionDetails")
    )

    return {
        "event": "coverage_tutor_refused",
        "source": "support_portal",
        "ticket": {
            "id": ticket["public_id"],
            "status": next_status,
            "statusReason": next_status_reason,
            "category": "Technical",
            "technicalSubcategory": "Coverage",
            "dashboardUrl": dashboard_url,
        },
        "tutor": {
            "name": sanitize_text(latest_response_payload.get("tutor")) or sanitize_text(tutor_choice_card.get("tutor")),
            "email": sanitize_text(latest_response_payload.get("tutorEmail")) or sanitize_text(tutor_choice_card.get("tutorEmail")),
        },
        "request": {
            "cardId": tutor_choice_card.get("id"),
            "requestedAt": tutor_choice_card.get("submittedAt"),
            "coach": sanitize_text(tutor_choice_card.get("coach")),
            "coachEmail": sanitize_text(tutor_choice_card.get("coachEmail")),
            "sessionDetails": session_details,
            "presentationFiles": tutor_choice_card.get("presentationFiles") or [],
        },
        "response": {
            "outcome": "rejected",
            "respondedAt": latest_response_payload.get("respondedAt"),
            "replyText": latest_response_payload.get("replyText") or "",
        },
        "requestedBy": {
            "agentId": tutor_choice_card.get("requestSubmittedByAgentId"),
            "agentName": tutor_choice_card.get("requestSubmittedByAgentName") or "",
            "agentUsername": tutor_choice_card.get("requestSubmittedByAgentUsername") or "",
        },
    }


def send_coverage_tutor_response_mail_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    configured, delivered, status, response_payload = post_json_webhook(
        get_coverage_tutor_response_mail_webhook_url(),
        payload,
        timeout_seconds=COVERAGE_TUTOR_RESPONSE_WEBHOOK_TIMEOUT_SECONDS,
    )
    return {
        "configured": configured,
        "delivered": delivered,
        "status": status,
        "response": response_payload,
    }


def notify_coverage_tutor_refusal_mail_webhook(ticket_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    if not get_coverage_tutor_response_mail_webhook_url():
        return {"configured": False, "delivered": False, "status": None, "response": None}

    try:
        webhook_result = send_coverage_tutor_response_mail_webhook(payload)
    except Exception:
        webhook_result = {"configured": True, "delivered": False, "status": None, "response": None}

    event_type = (
        "coverage_tutor_refusal_mail_notified"
        if webhook_result["delivered"]
        else "coverage_tutor_refusal_mail_failed"
    )
    try:
        insert_history_event(
            ticket_id,
            event_type,
            None,
            {
                "ticketId": payload.get("ticket", {}).get("id"),
                "tutor": payload.get("tutor", {}).get("name"),
                "tutorEmail": payload.get("tutor", {}).get("email"),
                "webhookStatus": webhook_result.get("status"),
                "webhookDelivered": webhook_result.get("delivered"),
            },
        )
    except Exception:
        pass

    return webhook_result


def find_coverage_card_index(
    cards: list[dict[str, Any]],
    *,
    card_id: Any = None,
    response_token: Any = None,
) -> int | None:
    normalized_card_id = sanitize_text(card_id)
    normalized_response_token = sanitize_text(response_token)

    for index, card in enumerate(cards):
        if normalized_card_id and sanitize_text(card.get("id")) == normalized_card_id:
            return index
        if normalized_response_token and sanitize_text(card.get("responseToken")) == normalized_response_token:
            return index

    return None


def normalize_recorded_coverage_tutor_response_outcome(value: Any) -> str:
    normalized_value = sanitize_text(value).lower()
    if normalized_value in {"accepted", "accept", "approved", "confirmed"}:
        return "accepted"
    if normalized_value in {"rejected", "reject", "refused", "refuse", "declined", "decline"}:
        return "rejected"
    return ""


def get_recorded_coverage_tutor_response_outcome(
    tutor_choice_card: dict[str, Any],
    coverage_cards: list[dict[str, Any]],
) -> str:
    normalized_card_id = sanitize_text(tutor_choice_card.get("id"))
    for card in coverage_cards:
        if (
            sanitize_text(card.get("type")) == "tutor_reply"
            and sanitize_text(card.get("relatedTutorChoiceCardId")) == normalized_card_id
        ):
            return (
                normalize_recorded_coverage_tutor_response_outcome(card.get("replyOutcome"))
                or normalize_recorded_coverage_tutor_response_outcome(card.get("requestStatus"))
                or "recorded"
            )

    return (
        normalize_recorded_coverage_tutor_response_outcome(tutor_choice_card.get("replyOutcome"))
        or normalize_recorded_coverage_tutor_response_outcome(tutor_choice_card.get("requestStatus"))
        or ("recorded" if sanitize_text(tutor_choice_card.get("respondedAt")) else "")
    )


def build_already_recorded_coverage_tutor_response_detail(
    ticket_public_id: str,
    *,
    recorded_outcome: str = "",
    requested_outcome: str = "",
) -> dict[str, Any]:
    detail = fetch_admin_ticket_detail(ticket_public_id)
    if not detail:
        raise ApiError(404, "Ticket not found.")

    detail["coverageTutorResponseAlreadyRecorded"] = True
    detail["recordedCoverageTutorResponseOutcome"] = normalize_recorded_coverage_tutor_response_outcome(recorded_outcome) or "recorded"
    detail["requestedCoverageTutorResponseOutcome"] = normalize_recorded_coverage_tutor_response_outcome(requested_outcome)
    detail["message"] = "This coverage request has already been responded to."
    return detail


def extract_coverage_tutor_response_outcome(payload: dict[str, Any]) -> str:
    normalized_outcome = sanitize_text(
        payload.get("outcome")
        or payload.get("status")
        or payload.get("decision")
        or payload.get("replyOutcome")
    ).lower()

    if normalized_outcome in {"accepted", "accept", "approved", "confirmed"}:
        return "accepted"
    if normalized_outcome in {"rejected", "reject", "refused", "refuse", "declined", "decline"}:
        return "rejected"

    accepted_flag = payload.get("accepted")
    if accepted_flag is True:
        return "accepted"
    if accepted_flag is False:
        return "rejected"

    return ""


def extract_coverage_tutor_response_session_details(payload: dict[str, Any]) -> str:
    explicit_value = sanitize_text(payload.get("sessionDetails"))
    if explicit_value:
        return explicit_value

    parts = [
        sanitize_text(payload.get("summary")),
        sanitize_text(payload.get("module")),
        sanitize_text(payload.get("preferredTime")),
        sanitize_text(payload.get("sessionSubject")),
        sanitize_text(payload.get("sessionWindow")),
        sanitize_text(payload.get("sessionJoinUrl")),
    ]
    filtered_parts = [part for part in parts if part]
    if filtered_parts:
        return "\n".join(filtered_parts)

    return ""


def build_coverage_tutor_response_payload(
    *,
    ticket_public_id: str,
    tutor_choice_card: dict[str, Any],
    response_payload: dict[str, Any],
    outcome: str,
    responded_at: str,
) -> dict[str, Any]:
    return {
        "outcome": outcome,
        "toAgentId": tutor_choice_card.get("requestSubmittedByAgentId"),
        "toAgentName": tutor_choice_card.get("requestSubmittedByAgentName"),
        "toAgentUsername": tutor_choice_card.get("requestSubmittedByAgentUsername"),
        "ticketId": ticket_public_id,
        "tutor": sanitize_text(response_payload.get("tutor")) or tutor_choice_card.get("tutor"),
        "tutorEmail": sanitize_text(response_payload.get("tutorEmail")) or tutor_choice_card.get("tutorEmail"),
        "coach": sanitize_text(response_payload.get("coach")) or tutor_choice_card.get("coach"),
        "coachEmail": sanitize_text(response_payload.get("coachEmail")) or tutor_choice_card.get("coachEmail"),
        "cardId": sanitize_text(response_payload.get("cardId")),
        "relatedTutorChoiceCardId": tutor_choice_card.get("id"),
        "requestedAt": tutor_choice_card.get("submittedAt"),
        "respondedAt": responded_at,
        "sessionDetails": extract_coverage_tutor_response_session_details(response_payload),
        "replyText": sanitize_text(response_payload.get("replyText") or response_payload.get("message") or response_payload.get("note")),
        "sessionStartAt": serialize_datetime_value(
            coerce_datetime(
                response_payload.get("sessionStartAt")
                or response_payload.get("sessionAt")
                or response_payload.get("startAt")
            )
        ),
        "sessionEndAt": serialize_datetime_value(
            coerce_datetime(
                response_payload.get("sessionEndAt")
                or response_payload.get("endAt")
            )
        ),
        "requesterAcknowledged": False,
    }


def build_coverage_tutor_reply_card(
    *,
    tutor_choice_card: dict[str, Any],
    response_payload: dict[str, Any],
    outcome: str,
    responded_at: str,
) -> dict[str, Any]:
    reply_text = sanitize_text(response_payload.get("replyText") or response_payload.get("message") or response_payload.get("note"))
    session_details = extract_coverage_tutor_response_session_details(response_payload)

    return {
        "id": sanitize_text(response_payload.get("responseCardId")) or uuid4().hex,
        "type": "tutor_reply",
        "title": "Tutor Accepted" if outcome == "accepted" else "Tutor Rejected",
        "note": reply_text,
        "tutor": sanitize_text(response_payload.get("tutor")) or tutor_choice_card.get("tutor") or "",
        "tutorEmail": sanitize_text(response_payload.get("tutorEmail")) or tutor_choice_card.get("tutorEmail") or "",
        "coach": sanitize_text(response_payload.get("coach")) or tutor_choice_card.get("coach") or "",
        "coachEmail": sanitize_text(response_payload.get("coachEmail")) or tutor_choice_card.get("coachEmail") or "",
        "sessionDetails": session_details,
        "replyText": reply_text,
        "requestStatus": "accepted" if outcome == "accepted" else "refused",
        "replyOutcome": "accepted" if outcome == "accepted" else "refused",
        "locked": True,
        "createdAt": responded_at,
        "updatedAt": responded_at,
        "submittedAt": "",
        "respondedAt": responded_at,
        "relatedTutorChoiceCardId": tutor_choice_card.get("id") or "",
        "requestSubmittedByAgentId": tutor_choice_card.get("requestSubmittedByAgentId"),
        "requestSubmittedByAgentName": tutor_choice_card.get("requestSubmittedByAgentName") or "",
        "requestSubmittedByAgentUsername": tutor_choice_card.get("requestSubmittedByAgentUsername") or "",
        "responseToken": "",
        "sessionStartAt": serialize_datetime_value(
            coerce_datetime(
                response_payload.get("sessionStartAt")
                or response_payload.get("sessionAt")
                or response_payload.get("startAt")
            )
        ),
        "sessionEndAt": serialize_datetime_value(
            coerce_datetime(
                response_payload.get("sessionEndAt")
                or response_payload.get("endAt")
            )
        ),
        "confirmedAt": "",
        "confirmedByAgentId": None,
        "confirmedByAgentName": "",
        "confirmedByAgentUsername": "",
        "presentationFiles": [],
    }


coverage_inquiry_line_patterns = {
    "tutor": re.compile(r"^Tutor:\s*(.+)$", re.IGNORECASE | re.MULTILINE),
    "module": re.compile(r"^Module:\s*(.+)$", re.IGNORECASE | re.MULTILINE),
    "time": re.compile(r"^Preferred Time:\s*(.+)$", re.IGNORECASE | re.MULTILINE),
    "session_dates": re.compile(r"^Session Date:\s*(.+)$", re.IGNORECASE | re.MULTILINE),
    "session_numbers": re.compile(r"^Session Number:\s*(.+)$", re.IGNORECASE | re.MULTILINE),
    "session_subject": re.compile(r"^Session Subject:\s*(.+)$", re.IGNORECASE | re.MULTILINE),
}


def parse_coverage_inquiry_details(inquiry: Any) -> dict[str, Any] | None:
    normalized_inquiry = sanitize_text(inquiry)
    if not normalized_inquiry:
        return None

    tutor_match = coverage_inquiry_line_patterns["tutor"].search(normalized_inquiry)
    module_match = coverage_inquiry_line_patterns["module"].search(normalized_inquiry)
    time_match = coverage_inquiry_line_patterns["time"].search(normalized_inquiry)
    session_dates_match = coverage_inquiry_line_patterns["session_dates"].search(normalized_inquiry)
    session_numbers_match = coverage_inquiry_line_patterns["session_numbers"].search(normalized_inquiry)
    session_subject_match = coverage_inquiry_line_patterns["session_subject"].search(normalized_inquiry)

    tutor = sanitize_text(tutor_match.group(1) if tutor_match else "")
    module = sanitize_text(module_match.group(1) if module_match else "")
    time_label = sanitize_text(time_match.group(1) if time_match else "")
    session_dates = [
        sanitize_text(value)
        for value in sanitize_text(session_dates_match.group(1) if session_dates_match else "").split(";")
        if sanitize_text(value)
    ]
    session_numbers = [
        sanitize_text(value)
        for value in sanitize_text(session_numbers_match.group(1) if session_numbers_match else "").split(";")
        if sanitize_text(value)
    ]
    session_subjects = [
        sanitize_text(value)
        for value in sanitize_text(session_subject_match.group(1) if session_subject_match else "").split(";")
        if sanitize_text(value)
    ]
    session_subject = "; ".join(session_subjects) if len(session_subjects) > 1 else (session_subjects[0] if session_subjects else "")

    if not tutor and not module and not time_label and not session_dates and not session_numbers and not session_subjects:
        return None

    return {
        "tutor": tutor,
        "module": module,
        "time": time_label,
        "sessionDates": session_dates,
        "sessionNumbers": session_numbers,
        "sessionSubjects": session_subjects,
        "sessionSubject": session_subject,
    }


def build_coverage_session_details_from_inquiry(inquiry: Any) -> str:
    parsed_inquiry = parse_coverage_inquiry_details(inquiry)
    if not parsed_inquiry:
        return ""

    session_dates = parsed_inquiry.get("sessionDates") or []
    session_numbers = parsed_inquiry.get("sessionNumbers") or []
    session_subjects = parsed_inquiry.get("sessionSubjects") or []
    session_detail_lines = []
    max_session_count = max(len(session_dates), len(session_numbers), len(session_subjects))
    if max_session_count > 0:
        for index in range(max_session_count):
            session_parts = []
            session_date = sanitize_text(session_dates[index] if index < len(session_dates) else "")
            session_number = sanitize_text(session_numbers[index] if index < len(session_numbers) else "")
            session_subject = sanitize_text(session_subjects[index] if index < len(session_subjects) else "")
            if session_date:
                session_parts.append(session_date)
            if session_number:
                session_parts.append(f"No. {session_number}")
            if session_subject:
                session_parts.append(session_subject)
            if session_parts:
                session_detail_lines.append(f"{index + 1}. {' | '.join(session_parts)}")

    return "\n".join(
        [
            f"Module: {parsed_inquiry['module']}" if parsed_inquiry.get("module") else "",
            f"Preferred Time: {parsed_inquiry['time']}" if parsed_inquiry.get("time") else "",
            "Sessions:" if session_detail_lines else "",
            *session_detail_lines,
        ]
    ).strip()


def build_coverage_session_items_from_inquiry_details(parsed_inquiry: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not parsed_inquiry:
        return []

    session_dates = parsed_inquiry.get("sessionDates") or []
    session_numbers = parsed_inquiry.get("sessionNumbers") or []
    session_subjects = parsed_inquiry.get("sessionSubjects") or []
    max_session_count = max(len(session_dates), len(session_numbers), len(session_subjects))
    sessions: list[dict[str, Any]] = []
    for index in range(max_session_count):
        session_date = sanitize_text(session_dates[index] if index < len(session_dates) else "")
        session_number = sanitize_text(session_numbers[index] if index < len(session_numbers) else "")
        session_subject = sanitize_text(session_subjects[index] if index < len(session_subjects) else "")
        sessions.append(
            {
                "index": index + 1,
                "date": session_date,
                "sessionNumber": session_number,
                "subject": session_subject,
            }
        )

    return sessions


def build_coverage_ticket_operations_webhook_payload(
    *,
    public_id: str,
    ticket_row: dict[str, Any],
    requester: dict[str, Any],
    learner: dict[str, Any],
    requester_role: str,
    category: str,
    technical_subcategory: str,
    inquiry: str,
    priority: str,
    evidence_count: int,
    attachment_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    parsed_inquiry = parse_coverage_inquiry_details(inquiry) or {}
    public_base_url = get_support_portal_public_base_url("")
    dashboard_url = f"{public_base_url}/admin" if public_base_url else ""
    created_at = serialize_datetime_value(ticket_row.get("created_at")) or datetime.now(timezone.utc).isoformat()

    return {
        "event": "coverage_ticket_created",
        "source": "support_portal",
        "ticket": {
            "id": public_id,
            "status": ticket_row.get("status"),
            "statusReason": "Coverage Ticket",
            "category": category,
            "technicalSubcategory": technical_subcategory,
            "priority": priority,
            "assignedTeam": ticket_row.get("assigned_team") or "Unassigned",
            "slaStatus": ticket_row.get("sla_status") or "",
            "createdAt": created_at,
            "dashboardUrl": dashboard_url,
        },
        "requester": {
            "name": requester.get("display_name") or learner.get("full_name") or learner.get("email") or "",
            "email": learner.get("email") or "",
            "role": requester_role,
        },
        "coverage": {
            "tutor": parsed_inquiry.get("tutor") or "",
            "module": parsed_inquiry.get("module") or "",
            "preferredTime": parsed_inquiry.get("time") or "",
            "sessionDates": parsed_inquiry.get("sessionDates") or [],
            "sessionNumbers": parsed_inquiry.get("sessionNumbers") or [],
            "sessionSubjects": parsed_inquiry.get("sessionSubjects") or [],
            "sessions": build_coverage_session_items_from_inquiry_details(parsed_inquiry),
            "inquiry": inquiry,
        },
        "evidence": {
            "count": evidence_count,
            "files": [
                {
                    "name": sanitize_text(file.get("name")),
                    "mimeType": sanitize_text(file.get("mimeType")),
                    "size": int(file.get("size") or 0),
                    "storageKey": sanitize_text(file.get("storageKey")),
                }
                for file in (attachment_rows or [])
            ],
        },
    }


def build_learning_plan_ticket_transfer_webhook_payload(
    *,
    ticket_row: dict[str, Any],
    from_team: str,
    to_team: str,
    transferred_by: dict[str, Any] | None = None,
    transferred_at: Any = None,
    assigned_agent_id: Any = None,
    assigned_agent_name: Any = None,
    assigned_agent_username: Any = None,
    note: Any = "",
) -> dict[str, Any]:
    public_base_url = get_support_portal_public_base_url("")
    dashboard_url = f"{public_base_url}/admin" if public_base_url else ""
    ticket_metadata = normalize_json_object(ticket_row.get("metadata"))
    requester_role = get_ticket_requester_role(ticket_metadata)
    requester_source = get_ticket_requester_source(
        ticket_metadata,
        learner_source=ticket_row.get("learner_source"),
        learner_metadata=ticket_row.get("learner_metadata"),
    )
    requester_email = sanitize_text(ticket_row.get("learner_email"))
    requester_name = (
        sanitize_text(ticket_row.get("learner_name"))
        or sanitize_text(ticket_row.get("requester_name"))
        or requester_email
    )
    resolved_assigned_agent_id = parse_assigned_agent_id(
        assigned_agent_id if assigned_agent_id is not None else ticket_row.get("assigned_agent_id")
    )
    resolved_assigned_agent_name = (
        sanitize_text(assigned_agent_name)
        or sanitize_text(ticket_row.get("assigned_agent_name"))
    )
    resolved_assigned_agent_username = (
        sanitize_text(assigned_agent_username)
        or sanitize_text(ticket_row.get("assigned_agent_username"))
    )
    transferred_by_row = transferred_by or {}

    return {
        "event": LEARNING_PLAN_TICKET_TRANSFER_WEBHOOK_EVENT,
        "source": "support_portal",
        "ticket": {
            "id": sanitize_text(ticket_row.get("public_id")),
            "status": sanitize_text(ticket_row.get("status")),
            "statusReason": sanitize_text(ticket_row.get("status_reason")),
            "category": sanitize_text(ticket_row.get("category")),
            "technicalSubcategory": sanitize_text(ticket_row.get("technical_subcategory")),
            "priority": sanitize_text(ticket_row.get("priority")),
            "assignedTeam": sanitize_text(to_team) or ASSIGNED_TEAM_UNASSIGNED,
            "slaStatus": sanitize_text(ticket_row.get("sla_status")),
            "createdAt": serialize_datetime_value(ticket_row.get("created_at")),
            "dashboardUrl": dashboard_url,
        },
        "requester": {
            "name": requester_name,
            "email": requester_email,
            "role": requester_role,
            "source": requester_source,
        },
        "transfer": {
            "fromTeam": sanitize_text(from_team) or ASSIGNED_TEAM_UNASSIGNED,
            "toTeam": sanitize_text(to_team) or ASSIGNED_TEAM_UNASSIGNED,
            "transferredAt": serialize_datetime_value(transferred_at) or datetime.now(timezone.utc).isoformat(),
            "note": sanitize_text(note),
            "transferredBy": {
                "id": parse_assigned_agent_id(transferred_by_row.get("id")),
                "name": sanitize_text(transferred_by_row.get("full_name")) or sanitize_text(transferred_by_row.get("username")),
                "username": sanitize_text(transferred_by_row.get("username")),
                "email": sanitize_text(transferred_by_row.get("email")),
                "role": sanitize_text(transferred_by_row.get("role")),
            },
            "assignedAgent": {
                "id": resolved_assigned_agent_id,
                "name": resolved_assigned_agent_name,
                "username": resolved_assigned_agent_username,
            },
        },
    }


def build_learning_plan_transfer_notification_payload(
    *,
    ticket_id: Any,
    requester_name: Any,
    requester_email: Any,
    requester_role: Any,
    from_team: Any,
    to_team: Any,
    transferred_at: Any,
    transferred_by: dict[str, Any] | None = None,
    assigned_agent_id: Any = None,
    assigned_agent_name: Any = None,
    assigned_agent_username: Any = None,
    note: Any = "",
) -> dict[str, Any]:
    transferred_by_row = transferred_by or {}

    return {
        "ticketId": sanitize_text(ticket_id),
        "requesterName": sanitize_text(requester_name),
        "requesterEmail": sanitize_text(requester_email),
        "requesterRole": normalize_public_requester_role(requester_role),
        "fromTeam": sanitize_text(from_team) or ASSIGNED_TEAM_UNASSIGNED,
        "toTeam": sanitize_text(to_team) or ASSIGNED_TEAM_UNASSIGNED,
        "transferredAt": serialize_datetime_value(transferred_at) or datetime.now(timezone.utc).isoformat(),
        "transferredById": parse_assigned_agent_id(transferred_by_row.get("id")),
        "transferredByName": sanitize_text(transferred_by_row.get("full_name")) or sanitize_text(transferred_by_row.get("username")),
        "transferredByUsername": sanitize_text(transferred_by_row.get("username")),
        "assignedAgentId": parse_assigned_agent_id(assigned_agent_id),
        "assignedAgentName": sanitize_text(assigned_agent_name),
        "assignedAgentUsername": sanitize_text(assigned_agent_username),
        "note": sanitize_text(note),
    }


def send_coverage_ticket_operations_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    request_kwargs: dict[str, Any] = {
        "timeout_seconds": COVERAGE_TICKET_WEBHOOK_TIMEOUT_SECONDS,
    }
    webhook_headers = build_coverage_ticket_operations_webhook_headers()
    if webhook_headers:
        request_kwargs["headers"] = webhook_headers

    configured, delivered, status, response_payload = post_json_webhook(
        get_coverage_ticket_operations_webhook_url(),
        payload,
        **request_kwargs,
    )
    return {
        "configured": configured,
        "delivered": delivered,
        "status": status,
        "response": response_payload,
    }


def send_learning_plan_ticket_transfer_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    request_kwargs: dict[str, Any] = {
        "timeout_seconds": COVERAGE_TICKET_WEBHOOK_TIMEOUT_SECONDS,
    }
    webhook_headers = build_coverage_ticket_operations_webhook_headers()
    if webhook_headers:
        request_kwargs["headers"] = webhook_headers

    configured, delivered, status, response_payload = post_json_webhook(
        get_coverage_ticket_operations_webhook_url(),
        payload,
        **request_kwargs,
    )
    return {
        "configured": configured,
        "delivered": delivered,
        "status": status,
        "response": response_payload,
    }


def notify_coverage_ticket_operations_team(ticket_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    if not get_coverage_ticket_operations_webhook_url():
        return {"configured": False, "delivered": False, "status": None, "response": None}

    webhook_result = send_coverage_ticket_operations_webhook(payload)
    event_type = (
        "coverage_ticket_operations_notified"
        if webhook_result["delivered"]
        else "coverage_ticket_operations_notification_failed"
    )
    try:
        insert_history_event(
            ticket_id,
            event_type,
            None,
            {
                "ticketId": payload.get("ticket", {}).get("id"),
                "requesterName": payload.get("requester", {}).get("name"),
                "requesterEmail": payload.get("requester", {}).get("email"),
                "module": payload.get("coverage", {}).get("module"),
                "tutor": payload.get("coverage", {}).get("tutor"),
                "sessionCount": len(payload.get("coverage", {}).get("sessions") or []),
                "webhookStatus": webhook_result.get("status"),
                "webhookDelivered": webhook_result.get("delivered"),
            },
        )
    except Exception:
        pass

    return webhook_result


def notify_learning_plan_ticket_transfer(ticket_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    if not get_coverage_ticket_operations_webhook_url():
        return {"configured": False, "delivered": False, "status": None, "response": None}

    webhook_result = send_learning_plan_ticket_transfer_webhook(payload)
    event_type = (
        "learning_plan_ticket_transfer_notified"
        if webhook_result["delivered"]
        else "learning_plan_ticket_transfer_notification_failed"
    )
    try:
        insert_history_event(
            ticket_id,
            event_type,
            None,
            {
                "ticketId": payload.get("ticket", {}).get("id"),
                "requesterName": payload.get("requester", {}).get("name"),
                "requesterEmail": payload.get("requester", {}).get("email"),
                "fromTeam": payload.get("transfer", {}).get("fromTeam"),
                "toTeam": payload.get("transfer", {}).get("toTeam"),
                "transferredByName": payload.get("transfer", {}).get("transferredBy", {}).get("name"),
                "assignedAgentName": payload.get("transfer", {}).get("assignedAgent", {}).get("name"),
                "webhookStatus": webhook_result.get("status"),
                "webhookDelivered": webhook_result.get("delivered"),
            },
        )
    except Exception:
        pass

    return webhook_result


def build_support_notification_webhook_payload(
    event: str,
    ticket: dict[str, Any],
    *,
    status: str | None = None,
    status_reason: str | None = None,
    requested_at: Any = None,
    closed_at: Any = None,
) -> dict[str, Any]:
    public_base_url = get_support_portal_public_base_url("")
    dashboard_url = f"{public_base_url}/admin" if public_base_url else ""
    recipient_type = "operations" if event == SUPPORT_NOTIFICATION_EVENT_LIVE_AGENT_UNAVAILABLE else "requester"
    ticket_metadata = normalize_json_object(ticket.get("metadata"))
    requester_role = get_ticket_requester_role(ticket_metadata)
    requester_source = get_ticket_requester_source(
        ticket_metadata,
        learner_source=ticket.get("learner_source"),
        learner_metadata=ticket.get("learner_metadata"),
    )
    requester_email = normalize_email(ticket.get("learner_email") or ticket.get("email") or "")
    requester_name = (
        sanitize_text(ticket.get("learner_name"))
        or sanitize_text(ticket.get("requester_name"))
        or requester_email
    )
    notification_status = status or sanitize_text(ticket.get("status"))
    notification_status_reason = status_reason if status_reason is not None else sanitize_text(ticket.get("status_reason"))

    return {
        "event": event,
        "source": "support_portal",
        "recipientType": recipient_type,
        "ticket": {
            "id": ticket.get("public_id"),
            "status": notification_status,
            "statusReason": notification_status_reason,
            "category": ticket.get("category"),
            "technicalSubcategory": ticket.get("technical_subcategory") or "",
            "priority": ticket.get("priority") or "",
            "assignedTeam": ticket.get("assigned_team") or "Unassigned",
            "slaStatus": ticket.get("sla_status") or "",
            "createdAt": serialize_datetime_value(ticket.get("created_at")),
            "dashboardUrl": dashboard_url,
        },
        "requester": {
            "name": requester_name,
            "email": requester_email,
            "role": requester_role,
            "source": requester_source,
        },
        "liveChat": {
            "requestedAt": serialize_datetime_value(requested_at) if requested_at else "",
            "assignedAgentId": int(ticket["assigned_agent_id"]) if ticket.get("assigned_agent_id") else None,
            "assignedAgentName": ticket.get("assigned_agent_name") or "",
            "assignedAgentUsername": ticket.get("assigned_agent_username") or "",
        },
        "closure": {
            "closedAt": serialize_datetime_value(closed_at) if closed_at else "",
        },
    }


def send_support_notification_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    configured, delivered, status, response_payload = post_json_webhook(
        get_support_notification_webhook_url(),
        payload,
        timeout_seconds=SUPPORT_NOTIFICATION_WEBHOOK_TIMEOUT_SECONDS,
    )
    return {
        "configured": configured,
        "delivered": delivered,
        "status": status,
        "response": response_payload,
    }


def deliver_support_notification(
    *,
    ticket_id: int,
    ticket_public_id: str,
    event: str,
    payload: dict[str, Any],
    sent_metadata_key: str,
) -> dict[str, Any]:
    delivered_event_type, failed_event_type = SUPPORT_NOTIFICATION_HISTORY_EVENTS.get(
        event,
        ("support_notification_delivered", "support_notification_failed"),
    )

    try:
        result = send_support_notification_webhook(payload)
    except Exception:
        result = {"configured": True, "delivered": False, "status": None, "response": None}

    delivered_at = datetime.now(timezone.utc)
    delivered = bool(result.get("delivered"))
    if delivered and sent_metadata_key:
        try:
            persist_ticket_metadata_patch(ticket_id, {sent_metadata_key: serialize_datetime_value(delivered_at)})
        except Exception:
            logger.warning(
                "Failed to persist support notification metadata for ticket %s",
                ticket_public_id,
                exc_info=True,
            )

    try:
        insert_history_event(
            ticket_id,
            delivered_event_type if delivered else failed_event_type,
            {"role": "system", "label": "support_notification"},
            {
                "event": event,
                "ticketId": ticket_public_id,
                "recipientType": payload.get("recipientType"),
                "requesterName": payload.get("requester", {}).get("name"),
                "requesterEmail": payload.get("requester", {}).get("email"),
                "webhookConfigured": bool(result.get("configured")),
                "webhookDelivered": delivered,
                "webhookStatus": result.get("status"),
                "deliveredAt": serialize_datetime_value(delivered_at) if delivered else "",
            },
        )
    except Exception:
        logger.warning(
            "Failed to record support notification history for ticket %s",
            ticket_public_id,
            exc_info=True,
        )

    return {
        **result,
        "deliveredAt": delivered_at,
        "historyEventType": delivered_event_type if delivered else failed_event_type,
    }


def queue_support_notification_delivery(
    *,
    ticket_id: int,
    ticket_public_id: str,
    event: str,
    payload: dict[str, Any],
    sent_metadata_key: str,
) -> None:
    if not get_support_notification_webhook_url() or not is_support_notification_delivery_enabled():
        return

    def deliver() -> None:
        close_old_connections()
        try:
            deliver_support_notification(
                ticket_id=ticket_id,
                ticket_public_id=ticket_public_id,
                event=event,
                payload=payload,
                sent_metadata_key=sent_metadata_key,
            )
        finally:
            close_old_connections()

    thread = threading.Thread(
        target=deliver,
        name=f"support-notification-{event}-{ticket_public_id}",
        daemon=True,
    )
    thread.start()


def should_notify_quick_ticket_submitted(
    ticket: dict[str, Any],
    *,
    previous_status: Any,
    previous_status_reason: Any,
    next_status: Any,
    next_status_reason: Any,
) -> bool:
    if is_coverage_ticket_record(ticket):
        return False

    metadata = normalize_json_object(ticket.get("metadata"))
    if metadata.get(QUICK_TICKET_SUBMITTED_NOTIFICATION_SENT_AT_METADATA_KEY):
        return False

    was_quick_ticket = sanitize_text(previous_status) == "Pending" and is_quick_ticket_status_reason(previous_status_reason)
    is_now_quick_ticket = sanitize_text(next_status) == "Pending" and is_quick_ticket_status_reason(next_status_reason)
    return is_now_quick_ticket and not was_quick_ticket


def should_notify_quick_ticket_closed(
    ticket: dict[str, Any],
    *,
    previous_status: Any,
    previous_status_reason: Any,
    next_status: Any,
) -> bool:
    if is_coverage_ticket_record(ticket):
        return False

    metadata = normalize_json_object(ticket.get("metadata"))
    if metadata.get(QUICK_TICKET_CLOSED_NOTIFICATION_SENT_AT_METADATA_KEY):
        return False

    return (
        sanitize_text(previous_status) != "Closed"
        and sanitize_text(next_status) == "Closed"
        and is_quick_ticket_status_reason(previous_status_reason)
    )


def queue_quick_ticket_submitted_notification(ticket: dict[str, Any], *, status: str, status_reason: str) -> None:
    payload = build_support_notification_webhook_payload(
        SUPPORT_NOTIFICATION_EVENT_QUICK_TICKET_SUBMITTED,
        ticket,
        status=status,
        status_reason=status_reason,
    )
    queue_support_notification_delivery(
        ticket_id=int(ticket["id"]),
        ticket_public_id=sanitize_text(ticket.get("public_id")),
        event=SUPPORT_NOTIFICATION_EVENT_QUICK_TICKET_SUBMITTED,
        payload=payload,
        sent_metadata_key=QUICK_TICKET_SUBMITTED_NOTIFICATION_SENT_AT_METADATA_KEY,
    )


def queue_quick_ticket_closed_notification(ticket: dict[str, Any], *, status: str, status_reason: str, closed_at: Any = None) -> None:
    payload = build_support_notification_webhook_payload(
        SUPPORT_NOTIFICATION_EVENT_QUICK_TICKET_CLOSED,
        ticket,
        status=status,
        status_reason=status_reason,
        closed_at=closed_at or datetime.now(timezone.utc),
    )
    queue_support_notification_delivery(
        ticket_id=int(ticket["id"]),
        ticket_public_id=sanitize_text(ticket.get("public_id")),
        event=SUPPORT_NOTIFICATION_EVENT_QUICK_TICKET_CLOSED,
        payload=payload,
        sent_metadata_key=QUICK_TICKET_CLOSED_NOTIFICATION_SENT_AT_METADATA_KEY,
    )


def should_notify_live_agent_unavailable(ticket: dict[str, Any], *, assigned_agent_id: Any) -> bool:
    if assigned_agent_id:
        return False

    metadata = normalize_json_object(ticket.get("metadata"))
    if metadata.get(LIVE_AGENT_UNAVAILABLE_NOTIFICATION_SENT_AT_METADATA_KEY):
        return False

    return True


def queue_live_agent_unavailable_notification(ticket: dict[str, Any], *, requested_at: Any) -> None:
    payload = build_support_notification_webhook_payload(
        SUPPORT_NOTIFICATION_EVENT_LIVE_AGENT_UNAVAILABLE,
        ticket,
        requested_at=requested_at,
    )
    queue_support_notification_delivery(
        ticket_id=int(ticket["id"]),
        ticket_public_id=sanitize_text(ticket.get("public_id")),
        event=SUPPORT_NOTIFICATION_EVENT_LIVE_AGENT_UNAVAILABLE,
        payload=payload,
        sent_metadata_key=LIVE_AGENT_UNAVAILABLE_NOTIFICATION_SENT_AT_METADATA_KEY,
    )


def build_derived_coverage_tutor_choice_card(
    *,
    ticket_public_id: str,
    inquiry: Any,
    created_at: Any,
    updated_at: Any,
    request_submitted_by_agent_id: Any = None,
    request_submitted_by_agent_name: Any = "",
    request_submitted_by_agent_username: Any = "",
) -> dict[str, Any] | None:
    parsed_inquiry = parse_coverage_inquiry_details(inquiry)
    if not parsed_inquiry:
        return None

    created_at_value = serialize_datetime_value(coerce_datetime(created_at)) or datetime.now(timezone.utc).isoformat()
    updated_at_value = serialize_datetime_value(coerce_datetime(updated_at)) or created_at_value

    return {
        "id": f"{sanitize_text(ticket_public_id).lower() or 'coverage-ticket'}-tutor-choice",
        "type": "tutor_choice",
        "title": "",
        "note": "",
        "tutor": parsed_inquiry.get("tutor") or "",
        "tutorEmail": "",
        "coach": "",
        "coachEmail": "",
        "sessionDetails": build_coverage_session_details_from_inquiry(inquiry),
        "replyText": "",
        "requestStatus": "requested",
        "replyOutcome": "",
        "locked": True,
        "createdAt": created_at_value,
        "updatedAt": updated_at_value,
        "submittedAt": created_at_value,
        "respondedAt": "",
        "relatedTutorChoiceCardId": "",
        "requestSubmittedByAgentId": parse_assigned_agent_id(request_submitted_by_agent_id),
        "requestSubmittedByAgentName": sanitize_text(request_submitted_by_agent_name),
        "requestSubmittedByAgentUsername": sanitize_text(request_submitted_by_agent_username),
        "responseToken": "",
        "sessionStartAt": "",
        "sessionEndAt": "",
        "confirmedAt": "",
        "confirmedByAgentId": None,
        "confirmedByAgentName": "",
        "confirmedByAgentUsername": "",
        "presentationFiles": [],
    }


def get_coverage_tutor_response_outcome_for_status_reason(status_reason: Any) -> str:
    normalized_status_reason = sanitize_text(status_reason).lower()
    if normalized_status_reason == sanitize_text(STATUS_REASON_TUTOR_ACCEPTED).lower():
        return "accepted"
    if normalized_status_reason in {
        sanitize_text(STATUS_REASON_TUTOR_REJECTED).lower(),
        sanitize_text(STATUS_REASON_TUTOR_REFUSED).lower(),
        "rejected",
        "refused",
    }:
        return "rejected"
    return ""


def get_coverage_workflow_card_sort_timestamp(card: dict[str, Any]) -> float:
    normalized_card = normalize_json_object(card)
    for field_name in ("respondedAt", "submittedAt", "updatedAt", "createdAt"):
        field_value = coerce_datetime(normalized_card.get(field_name))
        if field_value:
            return field_value.timestamp()
    return 0.0


def build_derived_coverage_tutor_reply_card_id(related_tutor_choice_card_id: Any, outcome: Any) -> str:
    normalized_related_id = sanitize_text(related_tutor_choice_card_id) or "coverage-card"
    normalized_outcome = sanitize_text(outcome).lower() or "response"
    return f"{normalized_related_id}-reply-{normalized_outcome}"


def does_coverage_reply_card_match_outcome(card: dict[str, Any], outcome: str) -> bool:
    normalized_card = normalize_json_object(card)
    normalized_reply_outcome = sanitize_text(normalized_card.get("replyOutcome")).lower()
    normalized_request_status = sanitize_text(normalized_card.get("requestStatus")).lower()
    normalized_title = sanitize_text(normalized_card.get("title")).lower()

    if outcome == "accepted":
        return (
            normalized_reply_outcome == "accepted"
            or normalized_request_status == "accepted"
            or normalized_title == "tutor accepted"
        )

    if outcome == "rejected":
        return (
            normalized_reply_outcome == "refused"
            or normalized_request_status == "refused"
            or normalized_title == "tutor rejected"
        )

    return False


def find_latest_submitted_coverage_tutor_choice_card(cards: list[dict[str, Any]]) -> dict[str, Any] | None:
    tutor_choice_cards = [
        normalize_json_object(card)
        for card in cards
        if sanitize_text(normalize_json_object(card).get("type")) == "tutor_choice"
    ]
    if not tutor_choice_cards:
        return None

    submitted_cards = [
        card for card in tutor_choice_cards
        if (
            sanitize_text(card.get("submittedAt"))
            or sanitize_text(card.get("requestStatus")).lower() in {"requested", "accepted", "refused"}
            or parse_assigned_agent_id(card.get("requestSubmittedByAgentId"))
        )
    ]
    candidate_cards = submitted_cards or tutor_choice_cards
    return max(
        candidate_cards,
        key=lambda card: (
            get_coverage_workflow_card_sort_timestamp(card),
            sanitize_text(card.get("id")),
        ),
    )


def find_coverage_reply_card_for_tutor_choice(
    cards: list[dict[str, Any]],
    related_tutor_choice_card_id: Any,
    outcome: str,
) -> dict[str, Any] | None:
    normalized_related_id = sanitize_text(related_tutor_choice_card_id)
    reply_cards = [
        normalize_json_object(card)
        for card in cards
        if (
            sanitize_text(normalize_json_object(card).get("type")) == "tutor_reply"
            and sanitize_text(normalize_json_object(card).get("relatedTutorChoiceCardId")) == normalized_related_id
            and does_coverage_reply_card_match_outcome(normalize_json_object(card), outcome)
        )
    ]
    if not reply_cards:
        return None

    return max(
        reply_cards,
        key=lambda card: (
            get_coverage_workflow_card_sort_timestamp(card),
            sanitize_text(card.get("id")),
        ),
    )


def get_canonical_coverage_reply_outcome_for_tutor_choice(cards: list[dict[str, Any]], related_tutor_choice_card_id: Any) -> str:
    normalized_related_id = sanitize_text(related_tutor_choice_card_id)
    has_accepted_reply = False
    has_rejected_reply = False

    for card in cards:
        normalized_card = normalize_json_object(card)
        if (
            sanitize_text(normalized_card.get("type")) != "tutor_reply"
            or sanitize_text(normalized_card.get("relatedTutorChoiceCardId")) != normalized_related_id
        ):
            continue
        if does_coverage_reply_card_match_outcome(normalized_card, "accepted"):
            has_accepted_reply = True
        elif does_coverage_reply_card_match_outcome(normalized_card, "rejected"):
            has_rejected_reply = True

    if has_accepted_reply:
        return "accepted"
    if has_rejected_reply:
        return "rejected"
    return ""


def get_coverage_status_reason_for_outcome(outcome: str, current_status_reason: Any = "") -> str:
    if outcome == "accepted":
        return STATUS_REASON_TUTOR_ACCEPTED
    if outcome == "rejected":
        normalized_current_status_reason = sanitize_text(current_status_reason).lower()
        if normalized_current_status_reason in {
            sanitize_text(STATUS_REASON_TUTOR_REFUSED).lower(),
            "refused",
        }:
            return STATUS_REASON_TUTOR_REFUSED
        return STATUS_REASON_TUTOR_REJECTED
    return sanitize_text(current_status_reason)


def derive_coverage_tutor_response_state(
    *,
    ticket_public_id: str,
    inquiry: Any = "",
    status_reason: Any,
    updated_at: Any,
    created_at: Any = None,
    assigned_agent_id: Any = None,
    assigned_agent_name: Any = "",
    assigned_agent_username: Any = "",
    documentation: dict[str, Any],
    metadata: Any,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    normalized_documentation = normalize_admin_documentation(
        documentation,
        fallback_ticket_id=ticket_public_id,
    )
    normalized_metadata = normalize_json_object(metadata)
    latest_response = get_latest_coverage_tutor_response(normalized_metadata)
    outcome = get_coverage_tutor_response_outcome_for_status_reason(status_reason)
    if outcome not in {"accepted", "rejected"}:
        return normalized_documentation, latest_response

    coverage_cards = list(normalized_documentation.get("coverageCards") or [])
    tutor_choice_card = find_latest_submitted_coverage_tutor_choice_card(coverage_cards)
    if not tutor_choice_card:
        fallback_tutor_choice_card = build_derived_coverage_tutor_choice_card(
            ticket_public_id=ticket_public_id,
            inquiry=inquiry or normalized_documentation.get("inquiry"),
            created_at=created_at or updated_at,
            updated_at=updated_at or created_at,
            request_submitted_by_agent_id=(
                latest_response.get("toAgentId") if latest_response else assigned_agent_id
            ),
            request_submitted_by_agent_name=(
                latest_response.get("toAgentName") if latest_response else assigned_agent_name
            ),
            request_submitted_by_agent_username=(
                latest_response.get("toAgentUsername") if latest_response else assigned_agent_username
            ),
        )
        if not fallback_tutor_choice_card:
            return normalized_documentation, latest_response
        coverage_cards.append(fallback_tutor_choice_card)
        normalized_documentation["coverageCards"] = coverage_cards
        tutor_choice_card = fallback_tutor_choice_card

    related_tutor_choice_card_id = sanitize_text(tutor_choice_card.get("id"))
    if not related_tutor_choice_card_id:
        return normalized_documentation, latest_response

    existing_terminal_outcome = get_canonical_coverage_reply_outcome_for_tutor_choice(
        coverage_cards,
        related_tutor_choice_card_id,
    )
    if existing_terminal_outcome in {"accepted", "rejected"} and existing_terminal_outcome != outcome:
        outcome = existing_terminal_outcome

    latest_response_matches_current = bool(
        latest_response
        and sanitize_text(latest_response.get("outcome")).lower() == outcome
        and sanitize_text(latest_response.get("relatedTutorChoiceCardId")) == related_tutor_choice_card_id
    )
    existing_reply_card = find_coverage_reply_card_for_tutor_choice(
        coverage_cards,
        related_tutor_choice_card_id,
        outcome,
    )

    responded_at = (
        serialize_datetime_value(coerce_datetime(latest_response.get("respondedAt")) if latest_response_matches_current else None)
        or serialize_datetime_value(coerce_datetime(existing_reply_card.get("respondedAt")) if existing_reply_card else None)
        or serialize_datetime_value(coerce_datetime(updated_at))
        or datetime.now(timezone.utc).isoformat()
    )
    session_details = (
        sanitize_text(latest_response.get("sessionDetails")) if latest_response_matches_current and latest_response else ""
    ) or sanitize_text(existing_reply_card.get("sessionDetails") if existing_reply_card else "") or sanitize_text(tutor_choice_card.get("sessionDetails"))
    reply_text = (
        sanitize_text(latest_response.get("replyText")) if latest_response_matches_current and latest_response else ""
    ) or sanitize_text(existing_reply_card.get("replyText") if existing_reply_card else "") or sanitize_text(existing_reply_card.get("note") if existing_reply_card else "")
    session_start_at = (
        serialize_datetime_value(coerce_datetime(latest_response.get("sessionStartAt")) if latest_response_matches_current and latest_response else None)
        or serialize_datetime_value(coerce_datetime(existing_reply_card.get("sessionStartAt")) if existing_reply_card else None))
    session_start_at = session_start_at or serialize_datetime_value(coerce_datetime(tutor_choice_card.get("sessionStartAt")))
    session_end_at = (
        serialize_datetime_value(coerce_datetime(latest_response.get("sessionEndAt")) if latest_response_matches_current and latest_response else None)
        or serialize_datetime_value(coerce_datetime(existing_reply_card.get("sessionEndAt")) if existing_reply_card else None))
    session_end_at = session_end_at or serialize_datetime_value(coerce_datetime(tutor_choice_card.get("sessionEndAt")))
    tutor = (
        sanitize_text(latest_response.get("tutor")) if latest_response_matches_current and latest_response else ""
    ) or sanitize_text(existing_reply_card.get("tutor") if existing_reply_card else "") or sanitize_text(tutor_choice_card.get("tutor"))
    tutor_email = (
        sanitize_text(latest_response.get("tutorEmail")) if latest_response_matches_current and latest_response else ""
    ) or sanitize_text(existing_reply_card.get("tutorEmail") if existing_reply_card else "") or sanitize_text(tutor_choice_card.get("tutorEmail"))
    coach = (
        sanitize_text(latest_response.get("coach")) if latest_response_matches_current and latest_response else ""
    ) or sanitize_text(existing_reply_card.get("coach") if existing_reply_card else "") or sanitize_text(tutor_choice_card.get("coach"))
    coach_email = (
        sanitize_text(latest_response.get("coachEmail")) if latest_response_matches_current and latest_response else ""
    ) or sanitize_text(existing_reply_card.get("coachEmail") if existing_reply_card else "") or sanitize_text(tutor_choice_card.get("coachEmail"))
    effective_reply_card_id = sanitize_text(existing_reply_card.get("id") if existing_reply_card else "") or build_derived_coverage_tutor_reply_card_id(
        related_tutor_choice_card_id,
        outcome,
    )
    requester_acknowledged = bool(latest_response.get("requesterAcknowledged")) if latest_response_matches_current and latest_response else False

    response_payload = {
        "responseCardId": effective_reply_card_id,
        "cardId": effective_reply_card_id,
        "tutor": tutor,
        "tutorEmail": tutor_email,
        "coach": coach,
        "coachEmail": coach_email,
        "sessionDetails": session_details,
        "replyText": reply_text,
        "sessionStartAt": session_start_at,
        "sessionEndAt": session_end_at,
    }

    effective_reply_card = build_coverage_tutor_reply_card(
        tutor_choice_card=tutor_choice_card,
        response_payload=response_payload,
        outcome=outcome,
        responded_at=responded_at,
    )
    if existing_reply_card:
        effective_reply_card = {
            **existing_reply_card,
            **effective_reply_card,
            "id": sanitize_text(existing_reply_card.get("id")) or effective_reply_card["id"],
            "createdAt": sanitize_text(existing_reply_card.get("createdAt")) or effective_reply_card["createdAt"],
            "updatedAt": sanitize_text(existing_reply_card.get("updatedAt")) or effective_reply_card["updatedAt"],
            "submittedAt": sanitize_text(existing_reply_card.get("submittedAt")) or effective_reply_card["submittedAt"],
            "confirmedAt": sanitize_text(existing_reply_card.get("confirmedAt")) or effective_reply_card["confirmedAt"],
            "confirmedByAgentId": parse_assigned_agent_id(existing_reply_card.get("confirmedByAgentId")),
            "confirmedByAgentName": sanitize_text(existing_reply_card.get("confirmedByAgentName")),
            "confirmedByAgentUsername": sanitize_text(existing_reply_card.get("confirmedByAgentUsername")),
        }

    effective_tutor_choice_card = {
        **tutor_choice_card,
        "requestStatus": "accepted" if outcome == "accepted" else "refused",
        "locked": True,
        "respondedAt": sanitize_text(tutor_choice_card.get("respondedAt")) or responded_at,
        "updatedAt": responded_at,
        "tutor": tutor,
        "tutorEmail": tutor_email,
        "coach": coach,
        "coachEmail": coach_email,
        "sessionDetails": session_details or sanitize_text(tutor_choice_card.get("sessionDetails")),
        "sessionStartAt": session_start_at or serialize_datetime_value(coerce_datetime(tutor_choice_card.get("sessionStartAt"))),
        "sessionEndAt": session_end_at or serialize_datetime_value(coerce_datetime(tutor_choice_card.get("sessionEndAt"))),
    }

    updated_cards: list[dict[str, Any]] = []
    reply_card_replaced = False
    tutor_choice_replaced = False
    for card in coverage_cards:
        normalized_card = normalize_json_object(card)
        if sanitize_text(normalized_card.get("id")) == related_tutor_choice_card_id:
            updated_cards.append(effective_tutor_choice_card)
            tutor_choice_replaced = True
            continue
        if (
            sanitize_text(normalized_card.get("type")) == "tutor_reply"
            and sanitize_text(normalized_card.get("relatedTutorChoiceCardId")) == related_tutor_choice_card_id
            and not does_coverage_reply_card_match_outcome(normalized_card, outcome)
        ):
            continue
        if sanitize_text(normalized_card.get("id")) == sanitize_text(existing_reply_card.get("id") if existing_reply_card else ""):
            updated_cards.append(effective_reply_card)
            reply_card_replaced = True
            continue
        updated_cards.append(normalized_card)

    if not tutor_choice_replaced:
        updated_cards.append(effective_tutor_choice_card)
    if not reply_card_replaced:
        updated_cards.append(effective_reply_card)

    normalized_documentation["coverageCards"] = updated_cards
    derived_latest_response = normalize_latest_coverage_tutor_response(
        {
            **build_coverage_tutor_response_payload(
                ticket_public_id=ticket_public_id,
                tutor_choice_card=effective_tutor_choice_card,
                response_payload={
                    "cardId": effective_reply_card["id"],
                    "tutor": effective_reply_card.get("tutor"),
                    "tutorEmail": effective_reply_card.get("tutorEmail"),
                    "sessionDetails": effective_reply_card.get("sessionDetails"),
                    "replyText": effective_reply_card.get("replyText") or effective_reply_card.get("note"),
                    "sessionStartAt": effective_reply_card.get("sessionStartAt"),
                    "sessionEndAt": effective_reply_card.get("sessionEndAt"),
                },
                outcome=outcome,
                responded_at=responded_at,
            ),
            "requesterAcknowledged": requester_acknowledged,
        }
    )

    return normalized_documentation, (derived_latest_response or latest_response)


def is_coverage_session_confirmation_available(card: dict[str, Any], *, now: datetime | None = None) -> bool:
    if sanitize_text(card.get("type")) != "tutor_reply":
        return False
    if sanitize_text(card.get("replyOutcome")) != "accepted":
        return False
    if sanitize_text(card.get("confirmedAt")):
        return False

    session_start_at = coerce_datetime(card.get("sessionStartAt"))
    if not session_start_at:
        return False

    comparison_now = now or datetime.now(timezone.utc)
    return comparison_now >= session_start_at


def list_coverage_tutor_request_history_rows(ticket_ids: list[Any]) -> dict[int, list[dict[str, Any]]]:
    normalized_ticket_ids: list[int] = []
    for ticket_id in ticket_ids:
        try:
            parsed_ticket_id = int(ticket_id or 0)
        except (TypeError, ValueError):
            continue
        if parsed_ticket_id > 0:
            normalized_ticket_ids.append(parsed_ticket_id)

    if not normalized_ticket_ids:
        return {}

    request_history_rows = run_query(
        """
        SELECT ticket_id, payload, created_at
        FROM ticket_history
        WHERE ticket_id = ANY(%s)
          AND event_type = 'coverage_tutor_requested'
        ORDER BY ticket_id ASC, created_at ASC, id ASC
        """,
        [normalized_ticket_ids],
    )

    request_history_rows_by_ticket_id: dict[int, list[dict[str, Any]]] = {}
    for row in request_history_rows:
        try:
            normalized_ticket_id = int(row.get("ticket_id") or 0)
        except (TypeError, ValueError):
            continue
        if normalized_ticket_id <= 0:
            continue
        request_history_rows_by_ticket_id.setdefault(normalized_ticket_id, []).append(row)

    return request_history_rows_by_ticket_id


def reconcile_coverage_tutor_requests_from_request_history(
    documentation: dict[str, Any],
    request_history_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized_documentation = normalize_admin_documentation(documentation)
    coverage_cards = list(normalized_documentation.get("coverageCards") or [])
    if not request_history_rows:
        return normalized_documentation

    latest_request_by_card_id: dict[str, dict[str, Any]] = {}
    for row in request_history_rows:
        payload = normalize_json_object(row.get("payload"))
        card_id = sanitize_text(payload.get("cardId"))
        if not card_id:
            continue
        latest_request_by_card_id[card_id] = {
            "payload": payload,
            "createdAt": serialize_datetime_value(coerce_datetime(row.get("created_at"))),
        }

    if not latest_request_by_card_id:
        return normalized_documentation

    if not coverage_cards:
        reconstructed_cards: list[dict[str, Any]] = []
        for request_entry in latest_request_by_card_id.values():
            payload = request_entry["payload"]
            requested_at = sanitize_text(payload.get("requestedAt")) or sanitize_text(request_entry.get("createdAt"))
            reconstructed_cards.append(
                {
                    "id": sanitize_text(payload.get("cardId")) or f"{normalized_documentation.get('ticketId') or 'coverage-ticket'}-tutor-choice",
                    "type": "tutor_choice",
                    "title": "",
                    "note": "",
                    "tutor": sanitize_text(payload.get("tutor")),
                    "tutorEmail": sanitize_text(payload.get("tutorEmail")),
                    "coach": sanitize_text(payload.get("coach")),
                    "coachEmail": sanitize_text(payload.get("coachEmail")),
                    "sessionDetails": sanitize_text(payload.get("sessionDetails")),
                    "replyText": "",
                    "requestStatus": "requested",
                    "replyOutcome": "",
                    "locked": True,
                    "createdAt": requested_at,
                    "updatedAt": requested_at,
                    "submittedAt": requested_at,
                    "respondedAt": "",
                    "relatedTutorChoiceCardId": "",
                    "requestSubmittedByAgentId": parse_assigned_agent_id(payload.get("toAgentId")),
                    "requestSubmittedByAgentName": sanitize_text(payload.get("toAgentName")),
                    "requestSubmittedByAgentUsername": sanitize_text(payload.get("toAgentUsername")),
                    "responseToken": "",
                    "sessionStartAt": "",
                    "sessionEndAt": "",
                    "confirmedAt": "",
                    "confirmedByAgentId": None,
                    "confirmedByAgentName": "",
                    "confirmedByAgentUsername": "",
                    "presentationFiles": [],
                }
            )

        normalized_documentation["coverageCards"] = sorted(
            reconstructed_cards,
            key=lambda card: (
                get_coverage_workflow_card_sort_timestamp(card),
                sanitize_text(card.get("id")),
            ),
        )
        coverage_cards = list(normalized_documentation.get("coverageCards") or [])

    did_change = False
    reconciled_cards: list[dict[str, Any]] = []
    for card in coverage_cards:
        normalized_card = normalize_json_object(card)
        if sanitize_text(normalized_card.get("type")) != "tutor_choice":
            reconciled_cards.append(normalized_card)
            continue

        card_id = sanitize_text(normalized_card.get("id"))
        request_entry = latest_request_by_card_id.get(card_id)
        if not request_entry:
            reconciled_cards.append(normalized_card)
            continue

        current_request_status = sanitize_text(normalized_card.get("requestStatus")).lower()
        if current_request_status == "pending":
            current_request_status = "requested"

        payload = request_entry["payload"]
        requested_at = (
            sanitize_text(normalized_card.get("submittedAt"))
            or sanitize_text(payload.get("requestedAt"))
            or sanitize_text(request_entry.get("createdAt"))
        )
        reconciled_card = {
            **normalized_card,
            "tutor": sanitize_text(normalized_card.get("tutor")) or sanitize_text(payload.get("tutor")),
            "tutorEmail": sanitize_text(normalized_card.get("tutorEmail")) or sanitize_text(payload.get("tutorEmail")),
            "coach": sanitize_text(normalized_card.get("coach")) or sanitize_text(payload.get("coach")),
            "coachEmail": sanitize_text(normalized_card.get("coachEmail")) or sanitize_text(payload.get("coachEmail")),
            "sessionDetails": sanitize_text(normalized_card.get("sessionDetails")) or sanitize_text(payload.get("sessionDetails")),
            "locked": True,
            "requestStatus": current_request_status if current_request_status in {"accepted", "refused"} else "requested",
            "submittedAt": requested_at,
            "requestSubmittedByAgentId": parse_assigned_agent_id(normalized_card.get("requestSubmittedByAgentId")) or parse_assigned_agent_id(payload.get("toAgentId")),
            "requestSubmittedByAgentName": sanitize_text(normalized_card.get("requestSubmittedByAgentName")) or sanitize_text(payload.get("toAgentName")),
            "requestSubmittedByAgentUsername": sanitize_text(normalized_card.get("requestSubmittedByAgentUsername")) or sanitize_text(payload.get("toAgentUsername")),
            "updatedAt": sanitize_text(normalized_card.get("updatedAt")) or requested_at,
        }
        if reconciled_card != normalized_card:
            did_change = True
        reconciled_cards.append(reconciled_card)

    if not did_change:
        return normalized_documentation

    normalized_documentation["coverageCards"] = reconciled_cards
    return normalized_documentation


def reconcile_coverage_tutor_requests_from_history(ticket_id: Any, documentation: dict[str, Any]) -> dict[str, Any]:
    try:
        normalized_ticket_id = int(ticket_id or 0)
    except (TypeError, ValueError):
        normalized_ticket_id = 0
    if normalized_ticket_id <= 0:
        return normalize_admin_documentation(documentation)

    request_history_rows = list_coverage_tutor_request_history_rows([normalized_ticket_id]).get(normalized_ticket_id, [])
    return reconcile_coverage_tutor_requests_from_request_history(documentation, request_history_rows)


def synchronize_coverage_tutor_workflow_ticket(
    ticket: dict[str, Any],
    request_history_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not is_coverage_ticket_record(ticket):
        return ticket

    ticket_metadata = normalize_json_object(ticket.get("metadata"))
    current_documentation = normalize_admin_documentation(
        ticket_metadata.get("admin_documentation"),
        fallback_inquiry=sanitize_text(ticket.get("inquiry")),
        fallback_chat_id=build_public_chat_id(ticket.get("public_id"), ticket.get("conversation_id"), ticket.get("conversation_metadata")),
        fallback_ticket_id=ticket.get("public_id") or "",
    )
    if request_history_rows is None:
        recovered_documentation = reconcile_coverage_tutor_requests_from_history(ticket.get("id"), current_documentation)
    else:
        recovered_documentation = reconcile_coverage_tutor_requests_from_request_history(current_documentation, request_history_rows)
    current_latest_response = get_latest_coverage_tutor_response(ticket_metadata)
    outcome = get_coverage_tutor_response_outcome_for_status_reason(ticket.get("status_reason"))
    if outcome in {"accepted", "rejected"}:
        derived_documentation, derived_latest_response = derive_coverage_tutor_response_state(
            ticket_public_id=ticket.get("public_id") or "",
            inquiry=ticket.get("inquiry"),
            status_reason=ticket.get("status_reason"),
            updated_at=ticket.get("updated_at"),
            created_at=ticket.get("created_at"),
            assigned_agent_id=ticket.get("assigned_agent_id"),
            assigned_agent_name=ticket.get("assigned_agent_name"),
            assigned_agent_username=ticket.get("assigned_agent_username"),
            documentation=recovered_documentation,
            metadata=ticket_metadata,
        )
    else:
        derived_documentation = recovered_documentation
        derived_latest_response = current_latest_response

    resolved_ticket = {
        **ticket,
        "_resolved_documentation": derived_documentation,
        "_resolved_latest_coverage_tutor_response": derived_latest_response,
        "_coverage_state_resolved": True,
    }
    effective_outcome = sanitize_text(derived_latest_response.get("outcome") if derived_latest_response else "").lower() or outcome
    documentation_changed = derived_documentation != current_documentation
    latest_response_changed = normalize_latest_coverage_tutor_response(current_latest_response) != normalize_latest_coverage_tutor_response(derived_latest_response)
    next_status_reason = (
        get_coverage_status_reason_for_outcome(effective_outcome, ticket.get("status_reason"))
        if effective_outcome in {"accepted", "rejected"}
        else sanitize_text(ticket.get("status_reason"))
    )
    status_reason_changed = next_status_reason != sanitize_text(ticket.get("status_reason"))
    next_status = "Closed" if effective_outcome == "accepted" else sanitize_text(ticket.get("status")) or "Pending"
    status_changed = next_status != sanitize_text(ticket.get("status"))

    if not documentation_changed and not latest_response_changed and not status_changed and not status_reason_changed:
        return resolved_ticket

    next_sla_status = ticket.get("sla_status")
    next_sla_attention_required = bool(ticket.get("sla_attention_required"))
    next_sla_attention_reason = None
    updated_ticket_metadata = normalize_json_object(ticket_metadata)
    updated_ticket_metadata["admin_documentation"] = derived_documentation
    updated_ticket_metadata[LATEST_COVERAGE_TUTOR_RESPONSE_METADATA_KEY] = derived_latest_response
    if status_changed:
        next_sla_status, next_sla_attention_required, next_sla_attention_reason, updated_ticket_metadata = resolve_ticket_sla_update(
            ticket,
            next_status,
            status_reason=next_status_reason,
            metadata=updated_ticket_metadata,
        )

    next_chat_state = sanitize_text(ticket.get("conversation_status")) or map_conversation_status(next_status)
    if status_changed:
        next_chat_state = map_conversation_status(next_status)
    updated_ticket_metadata, ticket_state_columns = build_ticket_state_persistence(
        updated_ticket_metadata,
        {
            **ticket,
            "status": next_status,
            "status_reason": next_status_reason,
        },
        chat_state=next_chat_state,
    )

    sync_timestamp = datetime.now(timezone.utc)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE tickets
            SET
              status = %s,
              status_reason = %s,
              sla_status = %s,
              metadata = %s::jsonb,
              ticket_type = %s,
              workflow_stage = %s,
              queue_scope = %s,
              dashboard_bucket = %s,
              can_show_conversation = %s,
              can_receive_chat = %s,
              resolution_reason = %s,
              updated_at = NOW(),
              closed_at = CASE
                WHEN %s = 'Closed' THEN COALESCE(closed_at, NOW())
                ELSE closed_at
              END
            WHERE id = %s
            """,
            [
                next_status,
                next_status_reason,
                next_sla_status,
                json.dumps(updated_ticket_metadata),
                *get_ticket_state_column_params(ticket_state_columns),
                next_status,
                ticket["id"],
            ],
        )

        if ticket.get("conversation_id") and (status_changed or latest_response_changed or documentation_changed):
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
                            "assigned_agent_id": ticket.get("assigned_agent_id"),
                            "assigned_team": ticket.get("assigned_team"),
                        }
                    ),
                    ticket["conversation_id"],
                ],
            )

    if status_changed:
        insert_history_event(ticket["id"], "status_changed", None, {"from": ticket.get("status") or "", "to": next_status})
        if ticket.get("conversation_id") and sanitize_text(next_chat_state).lower() == "closed":
            persist_conversation_chat_duration(ticket["id"], ticket["conversation_id"])

    if status_reason_changed:
        insert_history_event(
            ticket["id"],
            "status_reason_changed",
            None,
            {"from": ticket.get("status_reason") or "", "to": next_status_reason},
        )

    if latest_response_changed:
        insert_history_event(ticket["id"], "coverage_tutor_response", None, derived_latest_response)

    synchronized_ticket = dict(resolved_ticket)
    synchronized_ticket["status"] = next_status
    synchronized_ticket["status_reason"] = next_status_reason
    synchronized_ticket["sla_status"] = next_sla_status
    synchronized_ticket["metadata"] = updated_ticket_metadata
    synchronized_ticket["updated_at"] = sync_timestamp
    if next_status == "Closed":
        synchronized_ticket["closed_at"] = ticket.get("closed_at") or sync_timestamp
    if ticket.get("conversation_id"):
        synchronized_ticket["conversation_status"] = next_chat_state
    if status_changed:
        synchronized_ticket["sla_attention_required"] = next_sla_attention_required

    return synchronized_ticket


def synchronize_coverage_tutor_workflow_tickets(tickets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    coverage_ticket_ids: list[int] = []
    for ticket in tickets:
        if not is_coverage_ticket_record(ticket):
            continue
        try:
            normalized_ticket_id = int(ticket.get("id") or 0)
        except (TypeError, ValueError):
            continue
        if normalized_ticket_id > 0:
            coverage_ticket_ids.append(normalized_ticket_id)

    request_history_rows_by_ticket_id = list_coverage_tutor_request_history_rows(coverage_ticket_ids)
    synchronized_tickets: list[dict[str, Any]] = []
    for ticket in tickets:
        try:
            normalized_ticket_id = int(ticket.get("id") or 0)
        except (TypeError, ValueError):
            normalized_ticket_id = 0
        if normalized_ticket_id > 0:
            synchronized_tickets.append(
                synchronize_coverage_tutor_workflow_ticket(
                    ticket,
                    request_history_rows=request_history_rows_by_ticket_id.get(normalized_ticket_id, []),
                )
            )
            continue
        synchronized_tickets.append(synchronize_coverage_tutor_workflow_ticket(ticket))

    return synchronized_tickets


def get_support_auth_database_url() -> str:
    return (
        sanitize_text(getattr(settings, "KBC_AUTH_DATABASE_URL", ""))
        or sanitize_text(getattr(settings, "LEGACY_DATABASE_URL", ""))
    )


def _fetch_legacy_support_user_by_lookup(value: str, *, lookup_kind: str) -> dict[str, Any] | None:
    normalized_value = sanitize_text(value).lower()
    auth_database_url = get_support_auth_database_url()
    if not normalized_value or not auth_database_url:
        return None

    lookup_params: list[Any]
    if lookup_kind == "id":
        try:
            lookup_value = int(normalized_value)
        except (TypeError, ValueError):
            return None
        if lookup_value <= 0:
            return None
        lookup_clause = "u.id = %s"
        lookup_params = [lookup_value]
    else:
        lookup_column = "u.email" if lookup_kind == "email" else "u.username"
        lookup_clause = f"LOWER(TRIM({lookup_column})) = %s"
        lookup_params = [normalized_value]

    with psycopg.connect(auth_database_url) as source_connection:
        with source_connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                  u.id,
                  u.username,
                  u.first_name,
                  u.last_name,
                  LOWER(TRIM(u.email)) AS email,
                  u.password,
                  u.is_staff,
                  u.is_superuser,
                  u.is_active,
                  EXISTS(
                    SELECT 1
                    FROM auth_user_groups ug
                    INNER JOIN auth_group g ON g.id = ug.group_id
                    WHERE ug.user_id = u.id
                      AND LOWER(TRIM(g.name)) = %s
                  ) AS has_support_access,
                  EXISTS(
                    SELECT 1
                    FROM auth_user_groups ug
                    INNER JOIN auth_group g ON g.id = ug.group_id
                    WHERE ug.user_id = u.id
                      AND LOWER(TRIM(g.name)) = %s
                  ) AS has_operations_access,
                  EXISTS(
                    SELECT 1
                    FROM auth_user_groups ug
                    INNER JOIN auth_group g ON g.id = ug.group_id
                    WHERE ug.user_id = u.id
                      AND LOWER(TRIM(g.name)) = %s
                  ) AS has_admin_access
                FROM auth_user u
                WHERE {lookup_clause}
                  AND u.is_active = TRUE
                LIMIT 1
                """,
                [
                    SUPPORT_ACCESS_GROUP_NAME,
                    OPERATIONS_ACCESS_GROUP_NAME,
                    ADMIN_ACCESS_GROUP_NAME,
                    *lookup_params,
                ],
            )
            row = cursor.fetchone()

    if not row:
        return None

    (
        user_id,
        username_val,
        first_name,
        last_name,
        returned_email,
        password_hash,
        is_staff,
        is_superuser,
        is_active,
        has_support_access,
        has_operations_access,
        has_admin_access,
    ) = row
    if not (bool(has_support_access) or bool(has_operations_access) or bool(has_admin_access)):
        return None

    full_name = " ".join(part for part in [sanitize_text(first_name), sanitize_text(last_name)] if part).strip()

    return {
        "id": int(user_id),
        "username": sanitize_text(username_val),
        "first_name": sanitize_text(first_name),
        "last_name": sanitize_text(last_name),
        "full_name": full_name,
        "email": sanitize_text(returned_email).lower(),
        "password_hash": sanitize_text(password_hash),
        "is_staff": bool(is_staff),
        "is_superuser": bool(is_superuser),
        "is_active": bool(is_active),
        "has_support_access": bool(has_support_access),
        "has_operations_access": bool(has_operations_access),
        "has_admin_access": bool(has_admin_access),
    }


def fetch_legacy_support_user_by_username(username: str) -> dict[str, Any] | None:
    return _fetch_legacy_support_user_by_lookup(username, lookup_kind="username")


def fetch_legacy_support_user_by_email(email: str) -> dict[str, Any] | None:
    return _fetch_legacy_support_user_by_lookup(email, lookup_kind="email")


def fetch_legacy_support_user_by_id(user_id: Any) -> dict[str, Any] | None:
    return _fetch_legacy_support_user_by_lookup(str(user_id), lookup_kind="id")


def legacy_auth_user_has_group_by_email(email: Any, group_name: Any) -> bool:
    normalized_email = normalize_email(email)
    normalized_group_name = sanitize_text(group_name).lower()
    auth_database_url = get_support_auth_database_url()
    if not normalized_email or not normalized_group_name or not auth_database_url:
        return False

    with psycopg.connect(auth_database_url) as source_connection:
        with source_connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT 1
                FROM auth_user u
                INNER JOIN auth_user_groups ug
                  ON ug.user_id = u.id
                INNER JOIN auth_group g
                  ON g.id = ug.group_id
                WHERE LOWER(TRIM(u.email)) = %s
                  AND LOWER(TRIM(g.name)) = %s
                  AND u.is_active = TRUE
                LIMIT 1
                """,
                [normalized_email, normalized_group_name],
            )
            return bool(cursor.fetchone())


def has_public_requester_coach_access(email: Any) -> bool:
    return legacy_auth_user_has_group_by_email(email, COACH_ACCESS_GROUP_NAME)


def apply_public_requester_role_overrides(email: Any, requester_role: Any) -> str:
    normalized_role = normalize_public_requester_role(requester_role)
    if normalized_role == ROLE_USER and has_public_requester_coach_access(email):
        return ROLE_COACH
    return normalized_role


def _legacy_support_user_from_row(row: tuple[Any, ...]) -> dict[str, Any] | None:
    (
        user_id,
        username_val,
        first_name,
        last_name,
        returned_email,
        password_hash,
        is_staff,
        is_superuser,
        is_active,
        has_support_access,
        has_operations_access,
        has_admin_access,
    ) = row
    if not (bool(has_support_access) or bool(has_operations_access) or bool(has_admin_access)):
        return None

    full_name = " ".join(part for part in [sanitize_text(first_name), sanitize_text(last_name)] if part).strip()

    return {
        "id": int(user_id),
        "username": sanitize_text(username_val),
        "first_name": sanitize_text(first_name),
        "last_name": sanitize_text(last_name),
        "full_name": full_name,
        "email": sanitize_text(returned_email).lower(),
        "password_hash": sanitize_text(password_hash),
        "is_staff": bool(is_staff),
        "is_superuser": bool(is_superuser),
        "is_active": bool(is_active),
        "has_support_access": bool(has_support_access),
        "has_operations_access": bool(has_operations_access),
        "has_admin_access": bool(has_admin_access),
    }


def _positive_int(value: Any) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def fetch_legacy_support_users_for_accounts(accounts: list[dict[str, Any]]) -> dict[str, dict[Any, dict[str, Any]]]:
    """Load current Communication Centre access for all visible agents in one query."""
    auth_database_url = get_support_auth_database_url()
    if not auth_database_url or not accounts:
        return {"id": {}, "email": {}, "username": {}}

    legacy_ids: set[int] = set()
    emails: set[str] = set()
    usernames: set[str] = set()
    for account in accounts:
        metadata = normalize_json_object(account.get("metadata"))
        legacy_auth_user_id = _positive_int(metadata.get("legacy_auth_user_id"))
        if legacy_auth_user_id:
            legacy_ids.add(legacy_auth_user_id)

        for email_candidate in (
            account.get("email"),
            metadata.get("legacy_auth_email"),
            metadata.get("entra_email"),
        ):
            normalized_email = normalize_email(sanitize_text(email_candidate or ""))
            if normalized_email:
                emails.add(normalized_email)

        username_candidate = sanitize_text(account.get("username") or "").lower()
        if username_candidate:
            usernames.add(username_candidate)

    if not legacy_ids and not emails and not usernames:
        return {"id": {}, "email": {}, "username": {}}

    with psycopg.connect(auth_database_url) as source_connection:
        with source_connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                  u.id,
                  u.username,
                  u.first_name,
                  u.last_name,
                  LOWER(TRIM(u.email)) AS email,
                  u.password,
                  u.is_staff,
                  u.is_superuser,
                  u.is_active,
                  EXISTS(
                    SELECT 1
                    FROM auth_user_groups ug
                    INNER JOIN auth_group g ON g.id = ug.group_id
                    WHERE ug.user_id = u.id
                      AND LOWER(TRIM(g.name)) = %s
                  ) AS has_support_access,
                  EXISTS(
                    SELECT 1
                    FROM auth_user_groups ug
                    INNER JOIN auth_group g ON g.id = ug.group_id
                    WHERE ug.user_id = u.id
                      AND LOWER(TRIM(g.name)) = %s
                  ) AS has_operations_access,
                  EXISTS(
                    SELECT 1
                    FROM auth_user_groups ug
                    INNER JOIN auth_group g ON g.id = ug.group_id
                    WHERE ug.user_id = u.id
                      AND LOWER(TRIM(g.name)) = %s
                  ) AS has_admin_access
                FROM auth_user u
                WHERE u.is_active = TRUE
                  AND (
                    u.id = ANY(%s::int[])
                    OR LOWER(TRIM(u.email)) = ANY(%s::text[])
                    OR LOWER(TRIM(u.username)) = ANY(%s::text[])
                  )
                """,
                [
                    SUPPORT_ACCESS_GROUP_NAME,
                    OPERATIONS_ACCESS_GROUP_NAME,
                    ADMIN_ACCESS_GROUP_NAME,
                    list(legacy_ids),
                    list(emails),
                    list(usernames),
                ],
            )
            rows = cursor.fetchall()

    users_by_id: dict[int, dict[str, Any]] = {}
    users_by_email: dict[str, dict[str, Any]] = {}
    users_by_username: dict[str, dict[str, Any]] = {}
    for row in rows:
        legacy_user = _legacy_support_user_from_row(row)
        if not legacy_user:
            continue
        users_by_id[int(legacy_user["id"])] = legacy_user
        if legacy_user.get("email"):
            users_by_email[normalize_email(legacy_user["email"])] = legacy_user
        if legacy_user.get("username"):
            users_by_username[sanitize_text(legacy_user["username"]).lower()] = legacy_user

    return {
        "id": users_by_id,
        "email": users_by_email,
        "username": users_by_username,
    }


def refresh_staff_account_legacy_access(
    account: dict[str, Any],
    legacy_lookup: dict[str, dict[Any, dict[str, Any]]] | None = None,
    *,
    persist: bool = False,
) -> dict[str, Any]:
    """Refresh Communication Centre access flags before showing staff accounts."""
    if not get_support_auth_database_url():
        return account

    metadata = normalize_json_object(account.get("metadata"))
    legacy_user = None
    legacy_auth_user_id = _positive_int(metadata.get("legacy_auth_user_id"))

    if legacy_lookup is not None:
        if legacy_auth_user_id:
            legacy_user = legacy_lookup.get("id", {}).get(legacy_auth_user_id)
        if not legacy_user:
            for email_candidate in (
                account.get("email"),
                metadata.get("legacy_auth_email"),
                metadata.get("entra_email"),
            ):
                normalized_email = normalize_email(sanitize_text(email_candidate or ""))
                if normalized_email:
                    legacy_user = legacy_lookup.get("email", {}).get(normalized_email)
                if legacy_user:
                    break
        if not legacy_user:
            username_candidate = sanitize_text(account.get("username") or "").lower()
            if username_candidate:
                legacy_user = legacy_lookup.get("username", {}).get(username_candidate)
    elif legacy_auth_user_id > 0:
        legacy_user = fetch_legacy_support_user_by_id(legacy_auth_user_id)

    if legacy_lookup is None and not legacy_user:
        for email_candidate in (
            account.get("email"),
            metadata.get("legacy_auth_email"),
            metadata.get("entra_email"),
        ):
            normalized_email = normalize_email(sanitize_text(email_candidate or ""))
            if not normalized_email:
                continue
            legacy_user = fetch_legacy_support_user_by_email(normalized_email)
            if legacy_user:
                break

    if legacy_lookup is None and not legacy_user:
        username_candidate = sanitize_text(account.get("username") or "")
        if username_candidate:
            legacy_user = fetch_legacy_support_user_by_username(username_candidate)

    refreshed_metadata = dict(metadata)
    has_legacy_marker = any(
        key in refreshed_metadata
        for key in (
            "legacy_auth_user_id",
            "legacy_auth_email",
            "legacy_support_access",
            "legacy_operations_access",
            "legacy_admin_access",
        )
    )

    if legacy_user:
        refreshed_metadata.update(
            {
                "legacy_auth_user_id": int(legacy_user["id"]),
                "legacy_auth_source": "kbc_auth_user",
                "legacy_auth_synced_at": datetime.now(timezone.utc).isoformat(),
                "legacy_auth_email": normalize_email(legacy_user.get("email")),
                "legacy_support_access": normalize_bool(legacy_user.get("has_support_access")),
                "legacy_operations_access": normalize_bool(legacy_user.get("has_operations_access")),
                "legacy_admin_access": normalize_bool(legacy_user.get("has_admin_access")),
            }
        )
    elif has_legacy_marker:
        refreshed_metadata.update(
            {
                "legacy_auth_synced_at": datetime.now(timezone.utc).isoformat(),
                "legacy_support_access": False,
                "legacy_operations_access": False,
                "legacy_admin_access": False,
                "session_active": False,
                "console_status": DEFAULT_AGENT_CONSOLE_STATUS,
            }
        )

    if refreshed_metadata != metadata:
        if persist:
            persist_agent_metadata(int(account["id"]), refreshed_metadata)
        return {
            **account,
            "metadata": refreshed_metadata,
        }

    return account







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


def find_kbc_learner_by_email(email: str) -> dict[str, Any] | None:
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




def normalize_entra_public_requester_user(profile: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(profile, dict):
        return None

    if profile.get("accountEnabled") is False:
        return None

    try:
        mail = normalize_account_email(profile.get("mail")) or ""
        user_principal_name = normalize_account_email(profile.get("userPrincipalName")) or ""
    except ApiError:
        return None

    email = mail or user_principal_name
    if not email:
        return None

    display_name = sanitize_text(profile.get("displayName")) or email
    return {
        "id": sanitize_text(profile.get("id")),
        "displayName": display_name,
        "mail": mail,
        "userPrincipalName": user_principal_name,
        "email": email,
        "accountEnabled": profile.get("accountEnabled") is not False,
    }


def build_entra_public_requester_learner_payload(email: str, entra_user: dict[str, Any]) -> dict[str, Any]:
    return {
        "external_learner_id": sanitize_text(entra_user.get("id")) or None,
        "support_account_id": None,
        "full_name": sanitize_text(entra_user.get("displayName")) or email,
        "email": email,
        "phone": None,
    }


def get_ticket_requester_role(ticket_metadata: Any, *, default: str = ROLE_USER) -> str:
    normalized_metadata = normalize_json_object(ticket_metadata)
    return normalize_public_requester_role(normalized_metadata.get("requester_role"), default=default)


def promote_ticket_requester_role_if_needed(
    ticket: dict[str, Any],
    *,
    requester_email: Any,
    default_role: Any = ROLE_USER,
) -> tuple[dict[str, Any], str]:
    ticket_metadata = normalize_json_object(ticket.get("metadata"))
    current_role = get_ticket_requester_role(ticket_metadata, default=default_role)
    effective_role = apply_public_requester_role_overrides(requester_email, current_role)
    normalized_default_role = normalize_public_requester_role(default_role, default=current_role)
    if current_role == ROLE_USER and normalized_default_role != ROLE_USER:
        effective_role = normalized_default_role
    if effective_role != ROLE_COACH or current_role == ROLE_COACH:
        return ticket, effective_role

    ticket_id = parse_int(ticket.get("id"), 0)
    if ticket_id <= 0:
        return ticket, effective_role

    updated_metadata = dict(ticket_metadata)
    updated_metadata["requester_role"] = ROLE_COACH

    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE tickets
            SET metadata = %s::jsonb,
                updated_at = NOW()
            WHERE id = %s
            """,
            [json.dumps(updated_metadata), ticket_id],
        )

    return {**ticket, "metadata": updated_metadata}, effective_role


def is_coach_requester_role(value: Any) -> bool:
    return sanitize_text(value).lower() == ROLE_COACH


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


def normalize_support_booking_return_path(value: Any) -> str:
    normalized_value = sanitize_text(value)
    return normalized_value if normalized_value in {"/support/chat", "/support/options"} else ""


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
    return_path = normalize_support_booking_return_path(metadata.get("return_path"))

    if not requested_date or not requested_time:
        return None

    booking_summary = {
        "requestedDate": requested_date,
        "requestedTime": requested_time,
        "reservationConfirmed": reservation_confirmed,
        "meetingJoinUrl": meeting_join_url,
    }
    if return_path:
        booking_summary["returnPath"] = return_path

    return booking_summary


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
            WHEN t.status = 'Pending' AND COALESCE(t.metadata #>> '{ticket_state,workflowStage}', '') = 'awaiting_meeting' THEN 0
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
        *COVERAGE_TUTOR_STATUS_REASONS,
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


def is_quick_ticket_record(ticket: dict[str, Any] | None) -> bool:
    if not ticket or is_coverage_ticket_record(ticket):
        return False

    if normalize_bool(ticket.get("_derived_is_quick_ticket")):
        return True

    metadata = normalize_json_object(ticket.get("metadata"))
    if not normalize_bool(ticket.get("_ignore_persisted_ticket_state")):
        ticket_state = normalize_json_object(metadata.get(TICKET_STATE_METADATA_KEY))
        if sanitize_text(ticket_state.get("ticketType")) == "quick":
            return True
    return (
        normalize_bool(metadata.get(QUICK_TICKET_ORIGIN_METADATA_KEY))
        or is_quick_ticket_status_reason(ticket.get("status_reason"))
    )


def has_quick_ticket_status_reason_history(history_rows: list[dict[str, Any]]) -> bool:
    for history_row in history_rows:
        if sanitize_text(history_row.get("event_type")) != "status_reason_changed":
            continue

        payload = normalize_json_object(history_row.get("payload"))
        if (
            is_quick_ticket_status_reason(payload.get("from"))
            or is_quick_ticket_status_reason(payload.get("to"))
        ):
            return True

    return False


def is_coverage_tutor_status_reason(status_reason: Any) -> bool:
    return sanitize_text(status_reason).lower() in {
        sanitize_text(reason).lower() for reason in COVERAGE_TUTOR_STATUS_REASONS
    }


def get_ticket_scope_value(ticket: dict[str, Any], snake_case_key: str, camel_case_key: str) -> Any:
    if snake_case_key in ticket:
        return ticket.get(snake_case_key)
    return ticket.get(camel_case_key)


def is_coverage_ticket_record(ticket: dict[str, Any] | None) -> bool:
    if not isinstance(ticket, dict):
        return False

    direct_value = sanitize_text(get_ticket_scope_value(ticket, "technical_subcategory", "technicalSubcategory")).lower()
    if direct_value == "coverage":
        return True

    metadata = normalize_json_object(ticket.get("metadata"))
    if not normalize_bool(ticket.get("_ignore_persisted_ticket_state")):
        ticket_state = normalize_json_object(metadata.get(TICKET_STATE_METADATA_KEY))
        if sanitize_text(ticket_state.get("ticketType")) == "coverage":
            return True
    return sanitize_text(metadata.get("technical_subcategory")).lower() == "coverage"


def get_team_routing_policy_by_assigned_team(assigned_team: Any) -> dict[str, str]:
    normalized_assigned_team = sanitize_text(assigned_team).casefold()
    for team_name, policy in TEAM_ROUTING_POLICIES.items():
        if normalized_assigned_team == team_name.casefold():
            return policy

    return TEAM_ROUTING_POLICIES[ASSIGNED_TEAM_SUPPORT_DESK]


def get_ticket_routing_policy(ticket: dict[str, Any] | None) -> dict[str, str]:
    if is_coverage_ticket_record(ticket):
        return TEAM_ROUTING_POLICIES[ASSIGNED_TEAM_LEARNING_PLAN]

    assigned_team = get_ticket_scope_value(ticket or {}, "assigned_team", "assignedTeam")
    return get_team_routing_policy_by_assigned_team(assigned_team)


def is_learning_plan_ticket_record(ticket: dict[str, Any] | None) -> bool:
    if not isinstance(ticket, dict):
        return False

    return get_ticket_routing_policy(ticket)["key"] == TICKET_RECEIVER_SCOPE_OPERATIONS


def actor_has_metadata_flag(
    actor: dict[str, Any] | None,
    key: str,
    *,
    default: bool = False,
) -> bool:
    if not isinstance(actor, dict):
        return False

    metadata = normalize_json_object(actor.get("metadata"))
    if key in metadata:
        return normalize_bool(metadata.get(key))
    return default


def actor_has_admin_dashboard_access(actor: dict[str, Any] | None) -> bool:
    if not isinstance(actor, dict):
        return False

    role = sanitize_text(actor.get("role")).lower()
    return (
        role in ADMIN_ACCESS_ROLES
        or actor_has_metadata_flag(actor, "legacy_admin_access")
        or actor_has_metadata_flag(actor, "entra_directory_admin_access")
    )


def actor_has_support_dashboard_access(actor: dict[str, Any] | None) -> bool:
    return actor_has_team_routing_access(actor, TEAM_ROUTING_POLICIES[ASSIGNED_TEAM_SUPPORT_DESK])


def actor_has_operations_dashboard_access(actor: dict[str, Any] | None) -> bool:
    return actor_has_team_routing_access(actor, TEAM_ROUTING_POLICIES[ASSIGNED_TEAM_LEARNING_PLAN])


def actor_has_team_routing_access(actor: dict[str, Any] | None, policy: dict[str, str]) -> bool:
    if not isinstance(actor, dict):
        return False

    role = sanitize_text(actor.get("role")).lower()
    legacy_default = policy["key"] == TICKET_RECEIVER_SCOPE_SUPPORT and role == ROLE_AGENT
    return actor_has_metadata_flag(
        actor,
        policy["receiver_access_metadata_key"],
        default=legacy_default,
    )


def actor_can_access_admin_ticket(actor: dict[str, Any] | None, ticket: dict[str, Any] | None) -> bool:
    if not isinstance(ticket, dict):
        return False

    if actor_has_admin_dashboard_access(actor):
        return True

    return actor_has_team_routing_access(actor, get_ticket_routing_policy(ticket))


def actor_can_transfer_ticket_between_teams(
    actor: dict[str, Any] | None,
    ticket: dict[str, Any] | None,
    target_assigned_team: Any,
) -> bool:
    if not isinstance(ticket, dict):
        return False

    if actor_has_admin_dashboard_access(actor):
        return True

    try:
        normalize_assigned_team(target_assigned_team)
    except ApiError:
        return False

    return actor_has_team_routing_access(actor, get_ticket_routing_policy(ticket))


def require_actor_can_access_admin_ticket(actor: dict[str, Any] | None, ticket: dict[str, Any] | None) -> None:
    if not actor_can_access_admin_ticket(actor, ticket):
        raise ApiError(403, "You do not have permission to access this ticket.")


def filter_admin_tickets_for_actor(tickets: list[dict[str, Any]], actor: dict[str, Any] | None) -> list[dict[str, Any]]:
    if actor is None:
        return tickets
    return [ticket for ticket in tickets if actor_can_access_admin_ticket(actor, ticket)]


def fetch_ticket_scope_record(public_id: str) -> dict[str, Any] | None:
    normalized_public_id = sanitize_text(public_id)
    if not normalized_public_id:
        return None

    return run_query_one(
        """
        SELECT public_id, technical_subcategory, assigned_team, metadata
        FROM tickets
        WHERE public_id = %s
        LIMIT 1
        """,
        [normalized_public_id],
    )


def serialize_agent(row: dict[str, Any], *, open_assigned_chat_agent_ids: set[int] | None = None) -> dict[str, Any]:
    metadata = normalize_json_object(row.get("metadata"))
    is_active = normalize_bool(row.get("is_active")) if "is_active" in row else True
    account_scope = normalize_account_scope(row.get("account_scope"), fallback_role=row.get("role"))
    is_staff_account = account_scope == ACCOUNT_SCOPE_STAFF
    session_active = is_active and is_staff_account and is_agent_session_active(metadata)
    agent_id = int(row["id"])
    has_open_assigned_chat = agent_id in (open_assigned_chat_agent_ids or set())
    selected_console_status = normalize_selectable_console_status(metadata.get("console_status")) if session_active else "Off"
    display_email = (
        row.get("email")
        or sanitize_text(metadata.get("legacy_auth_email"))
        or None
    )
    return {
        "id": agent_id,
        "username": row["username"],
        "fullName": row.get("full_name") or row["username"],
        "email": display_email,
        "accountScope": account_scope,
        "role": row["role"],
        "isActive": is_active,
        "sessionActive": session_active,
        "legacySupportAccess": normalize_bool(metadata.get("legacy_support_access")),
        "legacyOperationsAccess": normalize_bool(metadata.get("legacy_operations_access")),
        "legacyAdminAccess": normalize_bool(metadata.get("legacy_admin_access")),
        "entraDirectoryAdmin": normalize_bool(metadata.get("entra_directory_admin_access")),
        "consoleStatus": resolve_agent_console_status(
            metadata,
            session_active=session_active,
            has_open_assigned_chat=has_open_assigned_chat,
        ) if is_active and is_staff_account else "Off",
        "selectedConsoleStatus": selected_console_status,
    }


def is_active_staff_support_account(account: dict[str, Any] | None) -> bool:
    if not account:
        return False

    is_active = normalize_bool(account.get("is_active")) if "is_active" in account else True
    if not is_active:
        return False

    account_scope = normalize_account_scope(account.get("account_scope"), fallback_role=account.get("role"))
    if account_scope != ACCOUNT_SCOPE_STAFF:
        return False

    return True


def account_has_team_receiver_access(account: dict[str, Any] | None, policy: dict[str, str]) -> bool:
    if not is_active_staff_support_account(account):
        return False

    metadata = normalize_json_object(account.get("metadata"))
    return normalize_bool(metadata.get(policy["receiver_access_metadata_key"]))


def is_ticket_receiving_staff_account(account: dict[str, Any] | None) -> bool:
    return account_has_team_receiver_access(account, TEAM_ROUTING_POLICIES[ASSIGNED_TEAM_SUPPORT_DESK])


def is_operations_ticket_receiving_staff_account(account: dict[str, Any] | None) -> bool:
    return account_has_team_receiver_access(account, TEAM_ROUTING_POLICIES[ASSIGNED_TEAM_LEARNING_PLAN])


def get_ticket_receiver_scope(ticket: dict[str, Any] | None) -> str:
    return get_ticket_routing_policy(ticket)["key"]


def account_can_receive_ticket_assignment(
    account: dict[str, Any] | None,
    ticket: dict[str, Any] | None,
) -> bool:
    return account_has_team_receiver_access(account, get_ticket_routing_policy(ticket))


def get_ticket_assignment_receiver_error(ticket: dict[str, Any] | None) -> str:
    ticket_label = get_ticket_routing_policy(ticket)["receiver_error_ticket_label"]
    return f"The selected agent does not receive {ticket_label} tickets."


def is_booking_in_progress_ticket_record(ticket: dict[str, Any] | None) -> bool:
    if not ticket:
        return False

    if normalize_bool(ticket.get("is_archived")):
        return False

    metadata = normalize_json_object(ticket.get("metadata"))
    return (
        sanitize_text(ticket.get("status")) == "Open"
        and sanitize_text(metadata.get(SUPPORT_FLOW_STAGE_METADATA_KEY)) == SUPPORT_FLOW_STAGE_BOOKING_IN_PROGRESS
    )


def is_cancelled_direct_booking_waiting_for_support_route(ticket: dict[str, Any] | None) -> bool:
    if not ticket:
        return False

    if normalize_bool(ticket.get("is_archived")):
        return False

    if sanitize_text(ticket.get("status")) != "Open":
        return False

    if sanitize_text(ticket.get("status_reason")):
        return False

    if is_live_chat_requested(ticket.get("metadata"), ticket.get("conversation_metadata")):
        return False

    latest_session_status = sanitize_text(ticket.get("latest_session_request_status")).lower()
    latest_session_metadata = normalize_json_object(ticket.get("latest_session_request_metadata"))
    return (
        latest_session_status == "cancelled"
        and normalize_support_booking_return_path(latest_session_metadata.get("return_path")) == "/support/options"
    )


def is_admin_hidden_support_flow_ticket_record(ticket: dict[str, Any] | None) -> bool:
    return (
        is_booking_in_progress_ticket_record(ticket)
        or is_cancelled_direct_booking_waiting_for_support_route(ticket)
    )


def derive_legacy_ticket_state(row: dict[str, Any], *, chat_state: str | None = None) -> dict[str, Any]:
    normalized_status = sanitize_text(row.get("status")) or "Open"
    normalized_status_reason = sanitize_text(row.get("status_reason"))
    normalized_chat_state = sanitize_text(chat_state or row.get("conversation_status")).lower()
    if normalized_chat_state not in ALLOWED_CHAT_STATES:
        normalized_chat_state = "closed" if normalized_status == "Closed" else "open"

    is_coverage = is_coverage_ticket_record(row)
    is_quick = is_quick_ticket_record(row)
    ticket_routing_policy = get_ticket_routing_policy(row)
    is_learning_plan_other = ticket_routing_policy["key"] == TICKET_RECEIVER_SCOPE_OPERATIONS and not is_coverage
    live_chat_requested = is_live_chat_requested(row.get("metadata"), row.get("conversation_metadata"))
    teams_call_requested = is_teams_call_requested(row.get("metadata"))
    ticket_metadata = normalize_json_object(row.get("metadata"))
    booking_in_progress = sanitize_text(ticket_metadata.get(SUPPORT_FLOW_STAGE_METADATA_KEY)) == SUPPORT_FLOW_STAGE_BOOKING_IN_PROGRESS
    assigned_agent_id = parse_assigned_agent_id(row.get("assigned_agent_id"))

    if is_coverage:
        ticket_type = "coverage"
    elif is_quick:
        ticket_type = "quick"
    elif booking_in_progress:
        ticket_type = "booking"
    elif normalized_status_reason == STATUS_REASON_AWAITING_MEETING:
        ticket_type = "booking"
    elif teams_call_requested:
        ticket_type = "teams_call"
    elif live_chat_requested:
        ticket_type = "live_chat"
    else:
        ticket_type = "standard"

    if is_coverage:
        if normalized_status_reason == STATUS_REASON_TUTOR_REQUESTED:
            workflow_stage = "tutor_requested"
        elif normalized_status_reason == STATUS_REASON_REREQUESTING:
            workflow_stage = "rerequesting"
        elif normalized_status_reason == STATUS_REASON_TUTOR_ACCEPTED:
            workflow_stage = "tutor_accepted"
        elif normalized_status_reason in {STATUS_REASON_TUTOR_REJECTED, STATUS_REASON_TUTOR_REFUSED}:
            workflow_stage = "tutor_rejected"
        elif normalized_status == "Closed":
            workflow_stage = "closed"
        else:
            workflow_stage = "coverage_review"
    elif normalized_status == "Closed":
        workflow_stage = "closed"
    elif is_quick:
        workflow_stage = "awaiting_review"
    elif booking_in_progress:
        workflow_stage = "booking_in_progress"
    elif normalized_status_reason == STATUS_REASON_AWAITING_MEETING:
        workflow_stage = "awaiting_meeting"
    elif normalized_status_reason == STATUS_REASON_ESCALATION:
        workflow_stage = "escalated"
    elif teams_call_requested:
        workflow_stage = "awaiting_staff_call"
    elif live_chat_requested:
        workflow_stage = "with_agent" if assigned_agent_id else "awaiting_agent"
    elif normalized_status == "Pending":
        workflow_stage = "pending"
    else:
        workflow_stage = "active"

    if normalized_status == "Closed":
        dashboard_bucket = "closed"
    elif is_coverage:
        dashboard_bucket = "coverage"
    elif is_learning_plan_other:
        dashboard_bucket = "learning_plan"
    elif is_quick:
        dashboard_bucket = "quick"
    elif normalized_status_reason == STATUS_REASON_ESCALATION:
        dashboard_bucket = "escalation"
    elif live_chat_requested:
        dashboard_bucket = "live_chat"
    elif normalized_status == "Pending":
        dashboard_bucket = "pending"
    else:
        dashboard_bucket = "support"

    queue_scope = ticket_routing_policy["key"]
    can_show_conversation = not (is_coverage or is_quick)
    can_receive_chat = (
        can_show_conversation
        and normalized_status == "Open"
        and normalized_chat_state != "closed"
        and live_chat_requested
    )
    resolution_reason = normalized_status_reason if normalized_status == "Closed" else ""

    return {
        "ticketType": ticket_type,
        "workflowStage": workflow_stage,
        "queueScope": queue_scope,
        "dashboardBucket": dashboard_bucket,
        "canShowConversation": can_show_conversation,
        "canReceiveChat": can_receive_chat,
        "resolutionReason": resolution_reason,
    }


def normalize_ticket_state_payload(value: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    payload = normalize_json_object(value)
    return {
        "ticketType": sanitize_text(payload.get("ticketType")) or fallback["ticketType"],
        "workflowStage": sanitize_text(payload.get("workflowStage")) or fallback["workflowStage"],
        "queueScope": sanitize_text(payload.get("queueScope")) or fallback["queueScope"],
        "dashboardBucket": sanitize_text(payload.get("dashboardBucket")) or fallback["dashboardBucket"],
        "canShowConversation": normalize_bool(payload.get("canShowConversation"))
        if payload.get("canShowConversation") is not None
        else fallback["canShowConversation"],
        "canReceiveChat": normalize_bool(payload.get("canReceiveChat"))
        if payload.get("canReceiveChat") is not None
        else fallback["canReceiveChat"],
        "resolutionReason": sanitize_text(payload.get("resolutionReason")) or fallback["resolutionReason"],
    }


def build_ticket_state_metadata(ticket: dict[str, Any], *, chat_state: str | None = None) -> dict[str, Any]:
    return derive_legacy_ticket_state(ticket, chat_state=chat_state)


def build_ticket_state_column_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for column_key, payload_key in TICKET_STATE_COLUMN_PAYLOAD_KEYS.items():
        if column_key not in row:
            continue

        value = row.get(column_key)
        if payload_key in {"canShowConversation", "canReceiveChat"}:
            if value is not None:
                payload[payload_key] = value
            continue

        normalized_value = sanitize_text(value)
        if normalized_value:
            payload[payload_key] = normalized_value

    return payload


def build_ticket_state_column_values(ticket_state: dict[str, Any]) -> dict[str, Any]:
    return {
        "ticket_type": sanitize_text(ticket_state.get("ticketType")),
        "workflow_stage": sanitize_text(ticket_state.get("workflowStage")),
        "queue_scope": sanitize_text(ticket_state.get("queueScope")),
        "dashboard_bucket": sanitize_text(ticket_state.get("dashboardBucket")),
        "can_show_conversation": bool(ticket_state.get("canShowConversation")),
        "can_receive_chat": bool(ticket_state.get("canReceiveChat")),
        "resolution_reason": sanitize_text(ticket_state.get("resolutionReason")),
    }


def get_ticket_state_column_params(ticket_state_columns: dict[str, Any]) -> list[Any]:
    return [
        ticket_state_columns.get("ticket_type") or None,
        ticket_state_columns.get("workflow_stage") or None,
        ticket_state_columns.get("queue_scope") or None,
        ticket_state_columns.get("dashboard_bucket") or None,
        ticket_state_columns.get("can_show_conversation"),
        ticket_state_columns.get("can_receive_chat"),
        ticket_state_columns.get("resolution_reason") or None,
    ]


def build_ticket_state_persistence(
    metadata: Any,
    ticket: dict[str, Any],
    *,
    chat_state: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    next_metadata = normalize_json_object(metadata)
    ticket_state = build_ticket_state_metadata(
        {
            **ticket,
            "metadata": next_metadata,
            "_ignore_persisted_ticket_state": True,
        },
        chat_state=chat_state,
    )
    next_metadata[TICKET_STATE_METADATA_KEY] = ticket_state
    return next_metadata, build_ticket_state_column_values(ticket_state)


def with_ticket_state_metadata(
    metadata: Any,
    ticket: dict[str, Any],
    *,
    chat_state: str | None = None,
) -> dict[str, Any]:
    next_metadata, _ticket_state_columns = build_ticket_state_persistence(
        metadata,
        ticket,
        chat_state=chat_state,
    )
    return next_metadata


def derive_ticket_state(row: dict[str, Any], *, chat_state: str | None = None) -> dict[str, Any]:
    fallback = derive_legacy_ticket_state(row, chat_state=chat_state)
    metadata = normalize_json_object(row.get("metadata"))
    persisted_state = (
        build_ticket_state_column_payload(row)
        or row.get(TICKET_STATE_METADATA_KEY)
        or metadata.get(TICKET_STATE_METADATA_KEY)
    )
    if not persisted_state:
        return fallback

    return normalize_ticket_state_payload(persisted_state, fallback)


def serialize_ticket_summary(row: dict[str, Any]) -> dict[str, Any]:
    ticket_metadata = normalize_json_object(row.get("metadata"))
    conversation_metadata = normalize_json_object(row.get("conversation_metadata"))
    requester_name = row.get("learner_name") or ""
    documentation = normalize_admin_documentation(
        row.get("_resolved_documentation", ticket_metadata.get("admin_documentation")),
        fallback_inquiry=sanitize_text(row.get("inquiry")),
        fallback_chat_id=build_public_chat_id(row.get("public_id"), row.get("conversation_id"), conversation_metadata),
        fallback_ticket_id=row.get("public_id") or "",
    )
    latest_coverage_tutor_response = (
        normalize_latest_coverage_tutor_response(row.get("_resolved_latest_coverage_tutor_response"))
        or get_latest_coverage_tutor_response(ticket_metadata)
    )
    if is_coverage_ticket_record(row) and not row.get("_coverage_state_resolved"):
        documentation, latest_coverage_tutor_response = derive_coverage_tutor_response_state(
            ticket_public_id=row.get("public_id") or "",
            inquiry=row.get("inquiry"),
            status_reason=row.get("status_reason"),
            updated_at=row.get("updated_at"),
            created_at=row.get("created_at"),
            assigned_agent_id=row.get("assigned_agent_id"),
            assigned_agent_name=row.get("assigned_agent_name"),
            assigned_agent_username=row.get("assigned_agent_username"),
            documentation=documentation,
            metadata=ticket_metadata,
        )
    chat_state = sanitize_text(row.get("conversation_status")).lower()
    if not chat_state:
        chat_state = "closed" if sanitize_text(row.get("status")) == "Closed" else "open"
    chat_duration_minutes = int(row.get("chat_duration_minutes") or 0)

    return {
        "id": row["public_id"],
        "learnerName": requester_name,
        "requesterName": requester_name,
        "email": row.get("learner_email") or "",
        "learnerPhone": row.get("learner_phone") or "",
        "requesterRole": get_ticket_requester_role(ticket_metadata),
        "requesterSource": get_ticket_requester_source(
            ticket_metadata,
            learner_source=row.get("learner_source"),
            learner_metadata=row.get("learner_metadata"),
        ),
        "priority": normalize_ticket_priority(row.get("priority")),
        "category": row["category"],
        "technicalSubcategory": row.get("technical_subcategory") or "",
        "inquiryPreview": sanitize_text(row.get("inquiry")),
        "status": row["status"],
        "statusReason": row.get("status_reason") or "",
        "ticketState": derive_ticket_state(row, chat_state=chat_state),
        "isQuickTicket": is_quick_ticket_record(row),
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
        "pendingSupportQueueNotification": get_pending_support_queue_notification(ticket_metadata),
        "pendingCoverageTicketNotification": get_pending_coverage_ticket_notification(ticket_metadata),
        "pendingLearningPlanTransferNotification": get_pending_learning_plan_transfer_notification(ticket_metadata),
        "teamsCallRequested": is_teams_call_requested(ticket_metadata),
        "latestEscalationClosure": get_latest_escalation_closure(ticket_metadata),
        "latestTransferDecision": get_latest_transfer_decision(ticket_metadata),
        "latestCoverageTutorResponse": latest_coverage_tutor_response,
        "documentation": documentation,
        "slaStatus": row["sla_status"],
        "slaAttentionRequired": bool(row.get("sla_attention_required")),
        "evidenceCount": int(row.get("evidence_count") or 0),
        "isArchived": normalize_bool(row.get("is_archived")),
        "archivedAt": row.get("archived_at"),
        "archivedById": int(row["archived_by_id"]) if row.get("archived_by_id") else None,
        "archivedByName": row.get("archived_by_name") or "",
        "archivedByUsername": row.get("archived_by_username") or "",
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def serialize_ticket_detail(row: dict[str, Any]) -> dict[str, Any]:
    detail = serialize_ticket_summary(row)
    detail.update(
        {
            "inquiry": row["inquiry"],
            "priority": normalize_ticket_priority(row.get("priority")),
            "closedAt": row.get("closed_at"),
            "documentation": detail.get("documentation"),
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
    *,
    ticket_public_id: str = "",
    admin_view: bool = False,
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
        client_message_id = sanitize_text(message_metadata.get(CHAT_MESSAGE_ID_METADATA_KEY)) or f"message-{row['id']}"
        is_bot_message = (
            sanitize_text(row.get("role")).lower() == "assistant"
            and sanitize_text(message_metadata.get("original_sender")).lower() == "bot"
        )
        if is_bot_message and sanitize_text(row.get("content")) in assignment_notice_texts:
            continue

        timeline_entries.append(
            {
                "id": str(row["id"]),
                "clientMessageId": client_message_id,
                "role": row["role"],
                "metadata": message_metadata,
                "source": "intro" if str(row.get("id", "")).startswith("intro-") else "message",
                "text": row["content"],
                "attachments": serialize_chat_message_attachments_from_metadata(
                    ticket_public_id,
                    message_metadata,
                    admin_view=admin_view,
                ),
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
                "clientMessageId": None,
                "role": "assistant",
                "metadata": {"original_sender": "bot", "source_event": sanitize_text(row.get("event_type")).lower()},
                "source": "history_event",
                "text": notice_text,
                "attachments": [],
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


def serialize_chat_message_attachments_from_metadata(
    public_id: str,
    metadata: Any,
    *,
    admin_view: bool = False,
) -> list[dict[str, Any]]:
    attachment_payloads = normalize_json_object(metadata).get(CHAT_ATTACHMENTS_METADATA_KEY)
    if not isinstance(attachment_payloads, list):
        return []

    serialized_attachments: list[dict[str, Any]] = []
    seen_attachment_ids: set[str] = set()
    for attachment_payload in attachment_payloads:
        if not isinstance(attachment_payload, dict):
            continue

        attachment = normalize_chat_attachment_row_payload(attachment_payload)
        client_attachment_id = attachment["clientAttachmentId"]
        if not client_attachment_id or client_attachment_id in seen_attachment_ids:
            continue

        seen_attachment_ids.add(client_attachment_id)
        storage_url = attachment.get("storageUrl")
        serialized_attachments.append(
            {
                "id": client_attachment_id,
                "clientAttachmentId": client_attachment_id,
                "name": attachment["name"],
                "mimeType": attachment.get("mimeType"),
                "size": attachment.get("size") or 0,
                "storageUrl": (
                    build_admin_ticket_chat_attachment_download_url(public_id, client_attachment_id)
                    if admin_view and storage_url
                    else (
                        build_ticket_chat_attachment_download_url(public_id, client_attachment_id)
                        if storage_url
                        else None
                    )
                ),
            }
        )

    return serialized_attachments


def serialize_chat_timeline_rows(
    public_id: str,
    message_rows: list[dict[str, Any]],
    history_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    timeline_entries = build_chat_timeline_entries(
        message_rows,
        history_rows,
        ticket_public_id=public_id,
    )

    return [
        {
            "id": entry["id"],
            "clientMessageId": entry.get("clientMessageId"),
            "sender": map_role_to_sender(entry["role"], entry.get("metadata")),
            "source": entry.get("source") or "message",
            "text": entry["text"],
            "attachments": entry.get("attachments") or [],
            "timestamp": entry["timestamp"],
        }
        for entry in timeline_entries
    ]


def serialize_admin_chat_timeline_rows(
    public_id: str,
    message_rows: list[dict[str, Any]],
    history_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    timeline_entries = build_chat_timeline_entries(
        message_rows,
        history_rows,
        ticket_public_id=public_id,
        admin_view=True,
    )

    return [
        {
            "id": int(entry["id"]) if isinstance(entry.get("id"), int) else str(entry.get("id")),
            "clientMessageId": entry.get("clientMessageId"),
            "role": entry["role"],
            "source": entry.get("source") or "message",
            "senderLabel": to_sender_label(entry["role"], entry.get("metadata")),
            "text": entry["text"],
            "attachments": entry.get("attachments") or [],
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


def get_effective_assigned_team(value: Any) -> str:
    normalized_value = sanitize_text(value)
    return normalized_value or ASSIGNED_TEAM_UNASSIGNED


def normalize_assigned_team(value: Any) -> str:
    normalized_value = sanitize_text(value)
    if not normalized_value:
        return ASSIGNED_TEAM_UNASSIGNED

    normalized_lookup = normalized_value.casefold()
    for allowed_value in ALLOWED_ASSIGNED_TEAMS:
        if allowed_value.casefold() == normalized_lookup:
            return allowed_value

    raise ApiError(400, "Invalid assigned team.")


def derive_assigned_team_for_ticket_assignment(current_assigned_team: Any, agent: dict[str, Any] | None) -> str:
    effective_current_team = get_effective_assigned_team(current_assigned_team)
    if effective_current_team not in DEFAULT_ASSIGNED_TEAMS:
        return effective_current_team
    return derive_assigned_team(agent)


def derive_assigned_team(agent: dict[str, Any] | None) -> str:
    return ASSIGNED_TEAM_SUPPORT_DESK if agent else ASSIGNED_TEAM_UNASSIGNED


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


def get_support_session_buffer_minutes() -> int:
    try:
        return max(int(settings.SUPPORT_SESSION_BUFFER_MINUTES or 0), 0)
    except (TypeError, ValueError):
        return 0


def normalize_session_datetime_for_comparison(value: datetime) -> datetime:
    return (value if value.tzinfo else value.replace(tzinfo=ZoneInfo(settings.TIME_ZONE))).astimezone(timezone.utc)


def get_support_session_block_end(
    requested_datetime: datetime,
    duration_minutes: int,
    *,
    include_buffer: bool = False,
) -> datetime:
    safe_duration_minutes = max(int(duration_minutes or settings.SUPPORT_SESSION_DURATION_MINUTES), 1)
    buffer_minutes = get_support_session_buffer_minutes() if include_buffer else 0
    return requested_datetime + timedelta(minutes=safe_duration_minutes + buffer_minutes)


def is_within_support_session_window(requested_datetime: datetime, duration_minutes: int | None = None) -> bool:
    uk_zone = ZoneInfo(UK_SUPPORT_TIMEZONE)
    session_start = requested_datetime if requested_datetime.tzinfo else requested_datetime.replace(tzinfo=ZoneInfo(settings.TIME_ZONE))
    localized_start = session_start.astimezone(uk_zone)
    start_minutes = (localized_start.hour * 60) + localized_start.minute

    if duration_minutes is None:
        return is_minutes_within_range(
            start_minutes,
            UK_SUPPORT_SESSION_START_MINUTES,
            UK_SUPPORT_SESSION_END_MINUTES,
        )

    localized_end = get_support_session_block_end(
        session_start,
        duration_minutes,
        include_buffer=False,
    ).astimezone(uk_zone)
    end_minutes = (localized_end.hour * 60) + localized_end.minute
    return (
        localized_start.date() == localized_end.date()
        and start_minutes >= UK_SUPPORT_SESSION_START_MINUTES
        and end_minutes <= UK_SUPPORT_SESSION_END_MINUTES
    )


def is_support_session_time_aligned(requested_datetime: datetime) -> bool:
    slot_interval = max(int(settings.SUPPORT_SESSION_SLOT_INTERVAL_MINUTES or 30), 1)
    localized_datetime = requested_datetime.astimezone(ZoneInfo(settings.TIME_ZONE))
    total_minutes = (localized_datetime.hour * 60) + localized_datetime.minute
    return total_minutes % slot_interval == 0


def support_session_blocks_overlap(
    left_start: datetime,
    left_end: datetime,
    right_start: datetime,
    right_end: datetime,
) -> bool:
    return left_start < right_end and left_end > right_start


def get_support_session_request_bounds(
    session_request: dict[str, Any],
    *,
    default_duration_minutes: int | None = None,
) -> tuple[datetime, datetime] | None:
    metadata = normalize_json_object(session_request.get("metadata"))
    try:
        duration_minutes = int(metadata.get("duration_minutes") or default_duration_minutes or settings.SUPPORT_SESSION_DURATION_MINUTES)
    except (TypeError, ValueError):
        duration_minutes = int(default_duration_minutes or settings.SUPPORT_SESSION_DURATION_MINUTES)
    session_start = coerce_datetime(metadata.get("requested_start_at")) or coerce_datetime(metadata.get("scheduled_at"))
    session_end = coerce_datetime(metadata.get("requested_end_at"))

    if not session_start:
        requested_date = session_request.get("requested_date")
        requested_time = session_request.get("requested_time")
        if hasattr(requested_date, "strftime") and hasattr(requested_time, "strftime"):
            session_start = datetime.combine(requested_date, requested_time).replace(tzinfo=ZoneInfo(settings.TIME_ZONE))

    if not session_start:
        return None

    if not session_end:
        session_end = session_start + timedelta(minutes=max(duration_minutes, 1))

    return (
        normalize_session_datetime_for_comparison(session_start),
        normalize_session_datetime_for_comparison(session_end),
    )


def list_active_support_session_request_rows() -> list[dict[str, Any]]:
    return run_query(
        """
        SELECT id, ticket_id, requested_date, requested_time, status, metadata
        FROM support_session_requests
        WHERE status IN ('requested', 'scheduled')
        ORDER BY created_at ASC, id ASC
        """
    )


def is_support_session_slot_available_against_rows(
    requested_datetime: datetime,
    duration_minutes: int,
    session_requests: list[dict[str, Any]],
) -> bool:
    requested_start = normalize_session_datetime_for_comparison(requested_datetime)
    requested_end = normalize_session_datetime_for_comparison(
        get_support_session_block_end(requested_datetime, duration_minutes, include_buffer=True)
    )
    buffer_minutes = get_support_session_buffer_minutes()

    for session_request in session_requests:
        bounds = get_support_session_request_bounds(
            session_request,
            default_duration_minutes=duration_minutes,
        )
        if not bounds:
            continue

        existing_start, existing_end = bounds
        existing_block_end = existing_end + timedelta(minutes=buffer_minutes)
        if support_session_blocks_overlap(requested_start, requested_end, existing_start, existing_block_end):
            return False

    return True


def is_support_session_slot_locally_available(requested_datetime: datetime, duration_minutes: int) -> bool:
    return is_support_session_slot_available_against_rows(
        requested_datetime,
        duration_minutes,
        list_active_support_session_request_rows(),
    )


def filter_locally_available_support_session_candidates(
    candidates: list[dict[str, Any]],
    duration_minutes: int,
) -> list[dict[str, Any]]:
    session_requests = list_active_support_session_request_rows()
    return [
        candidate
        for candidate in candidates
        if is_support_session_slot_available_against_rows(
            candidate["requestedDateTime"],
            duration_minutes,
            session_requests,
        )
    ]


def lock_support_session_booking_date(requested_datetime: datetime) -> None:
    lock_date = requested_datetime.astimezone(ZoneInfo(UK_SUPPORT_TIMEZONE)).date().isoformat()
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [f"support-session-date:{lock_date}"])


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

    if not is_within_support_session_window(requested_datetime, settings.SUPPORT_SESSION_DURATION_MINUTES):
        return "Support sessions must fit between 8:00 AM and 4:00 PM UK time."

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
        "bufferMinutes": get_support_session_buffer_minutes(),
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
            settings.AZURE_BOOKING_TENANT_ID,
            settings.AZURE_BOOKING_CLIENT_ID,
            settings.AZURE_BOOKING_CLIENT_SECRET,
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
    return get_microsoft_booking_staff_availability_window(
        access_token,
        staff_ids,
        requested_datetime,
        requested_datetime + timedelta(minutes=duration_minutes),
    )


def get_microsoft_booking_staff_availability_window(
    access_token: str,
    staff_ids: list[str],
    window_start: datetime,
    window_end: datetime,
) -> tuple[bool, bool, int | None, Any]:
    business_id = urllib_parse.quote(sanitize_text(settings.BOOKING_BUSINESS_ID), safe="")
    availability_url = f"{MICROSOFT_GRAPH_V1_BASE_URL}/solutions/bookingBusinesses/{business_id}/getStaffAvailability"
    payload = {
        "staffIds": staff_ids,
        "startDateTime": build_microsoft_graph_date_time_time_zone(window_start, MICROSOFT_GRAPH_BOOKINGS_TIMEZONE),
        "endDateTime": build_microsoft_graph_date_time_time_zone(window_end, MICROSOFT_GRAPH_BOOKINGS_TIMEZONE),
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
    maximum_attendees_count = 1

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


def resolve_support_session_client_timezone(client_time_zone: Any) -> ZoneInfo:
    normalized_time_zone = sanitize_text(client_time_zone) or settings.TIME_ZONE
    try:
        return ZoneInfo(normalized_time_zone)
    except Exception:
        return ZoneInfo(settings.TIME_ZONE)


def format_support_session_time_label(value: datetime) -> str:
    hour = value.hour
    minute = value.minute
    period = "AM" if hour < 12 else "PM"
    hour_12 = hour % 12 or 12
    return f"{hour_12}:{minute:02d} {period}"


def build_support_session_candidate_slots(
    date_value: str,
    client_time_zone: Any = "",
    *,
    duration_minutes: int | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", sanitize_text(date_value)):
        return []

    slot_interval = max(int(settings.SUPPORT_SESSION_SLOT_INTERVAL_MINUTES or 30), 1)
    session_duration_minutes = int(duration_minutes or settings.SUPPORT_SESSION_DURATION_MINUTES)
    client_zone = resolve_support_session_client_timezone(client_time_zone)
    current_time = now or datetime.now(tz=ZoneInfo(settings.TIME_ZONE))
    candidates: list[dict[str, Any]] = []

    for minutes in range(0, 24 * 60, slot_interval):
        hours = minutes // 60
        mins = minutes % 60
        value = f"{hours:02d}:{mins:02d}"
        parsed_datetime = parse_local_datetime(date_value, value)

        if not parsed_datetime:
            continue

        requested_datetime = parsed_datetime.replace(tzinfo=client_zone)
        if (requested_datetime - current_time).total_seconds() <= SUPPORT_SESSION_LEAD_TIME_SECONDS:
            continue

        if not is_within_support_session_window(requested_datetime, session_duration_minutes):
            continue

        candidates.append(
            {
                "value": value,
                "label": format_support_session_time_label(requested_datetime),
                "requestedDateTime": requested_datetime,
            }
        )

    return candidates


def serialize_support_session_time_options(candidates: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "value": sanitize_text(candidate.get("value")),
            "label": sanitize_text(candidate.get("label")),
        }
        for candidate in candidates
        if sanitize_text(candidate.get("value")) and sanitize_text(candidate.get("label"))
    ]


def get_microsoft_booking_available_time_options(
    date_value: str,
    client_time_zone: Any = "",
    *,
    now: datetime | None = None,
) -> list[dict[str, str]] | None:
    if not is_direct_microsoft_booking_configured():
        return None

    _, token_delivered, _, token_payload = request_microsoft_graph_access_token()
    access_token = (
        sanitize_text(token_payload.get("access_token"))
        if token_delivered and isinstance(token_payload, dict)
        else ""
    )
    if not access_token:
        return None

    _, service_delivered, _, service_payload = get_microsoft_booking_service_details(access_token)
    if not service_delivered or not isinstance(service_payload, dict):
        return None

    staff_ids = [sanitize_text(staff_id) for staff_id in (service_payload.get("staffMemberIds") or []) if sanitize_text(staff_id)]
    if not staff_ids:
        return None

    duration_minutes = get_direct_booking_duration_minutes(service_payload)
    candidates = build_support_session_candidate_slots(
        date_value,
        client_time_zone,
        duration_minutes=duration_minutes,
        now=now,
    )
    if not candidates:
        return []

    window_start = candidates[0]["requestedDateTime"]
    window_end = candidates[-1]["requestedDateTime"] + timedelta(minutes=duration_minutes)
    _, availability_delivered, _, availability_payload = get_microsoft_booking_staff_availability_window(
        access_token,
        staff_ids,
        window_start,
        window_end,
    )
    if not availability_delivered or not isinstance(availability_payload, dict):
        return None

    available_candidates: list[dict[str, Any]] = []
    staff_availability_items = [
        availability_item
        for staff_item in (availability_payload.get("value") or [])
        if isinstance(staff_item, dict)
        for availability_item in (staff_item.get("availabilityItems") or [])
    ]

    for candidate in candidates:
        requested_datetime = candidate["requestedDateTime"]
        slot_start = parse_microsoft_graph_local_datetime(
            build_microsoft_graph_date_time_time_zone(requested_datetime, MICROSOFT_GRAPH_BOOKINGS_TIMEZONE)["dateTime"]
        )
        slot_end = parse_microsoft_graph_local_datetime(
            build_microsoft_graph_date_time_time_zone(
                requested_datetime + timedelta(minutes=duration_minutes),
                MICROSOFT_GRAPH_BOOKINGS_TIMEZONE,
            )["dateTime"]
        )

        if slot_start and slot_end and any(
            availability_window_covers_slot(availability_item, slot_start, slot_end)
            for availability_item in staff_availability_items
        ):
            available_candidates.append(candidate)

    return serialize_support_session_time_options(
        filter_locally_available_support_session_candidates(
            available_candidates,
            duration_minutes,
        )
    )


def get_support_session_availability_response(public_id: str, date_value: str, client_time_zone: str = "") -> dict[str, Any]:
    if not public_id:
        raise ApiError(400, "Ticket id is required.")

    normalized_date = sanitize_text(date_value)
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", normalized_date):
        raise ApiError(400, "Please choose a valid session date.")

    ticket = run_query_one(
        """
        SELECT id, public_id
        FROM tickets
        WHERE public_id = %s
        LIMIT 1
        """,
        [public_id],
    )
    if not ticket:
        raise ApiError(404, "Ticket not found.")

    graph_options = get_microsoft_booking_available_time_options(normalized_date, client_time_zone)
    if graph_options is not None:
        return {
            "ok": True,
            "date": normalized_date,
            "source": "microsoft_graph",
            "options": graph_options,
        }

    fallback_candidates = filter_locally_available_support_session_candidates(
        build_support_session_candidate_slots(
            normalized_date,
            client_time_zone,
            duration_minutes=settings.SUPPORT_SESSION_DURATION_MINUTES,
        ),
        settings.SUPPORT_SESSION_DURATION_MINUTES,
    )

    return {
        "ok": True,
        "date": normalized_date,
        "source": "fallback",
        "options": serialize_support_session_time_options(fallback_candidates),
    }


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


def serialize_chat_message_attachment_metadata_payload(attachments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "clientAttachmentId": sanitize_text(attachment.get("client_attachment_id")),
            "name": sanitize_support_attachment_name(attachment.get("name")),
            "mimeType": sanitize_text(attachment.get("mime_type")) or None,
            "size": int(attachment["size"]) if isinstance(attachment.get("size"), int) else None,
            "storageUrl": sanitize_text(attachment.get("storage_url")) or None,
            "metadata": normalize_json_object(attachment.get("metadata")),
        }
        for attachment in attachments
        if sanitize_text(attachment.get("client_attachment_id"))
    ]


def normalize_chat_message_attachments(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    normalized_attachments: list[dict[str, Any]] = []
    seen_attachment_ids: set[str] = set()
    for attachment in value:
        if not isinstance(attachment, dict):
            continue

        normalized_attachment = normalize_chat_attachment_row_payload(attachment)
        client_attachment_id = normalized_attachment["clientAttachmentId"]
        if not client_attachment_id or client_attachment_id in seen_attachment_ids:
            continue

        seen_attachment_ids.add(client_attachment_id)
        normalized_attachments.append(
            {
                "client_attachment_id": client_attachment_id,
                "name": normalized_attachment["name"],
                "mime_type": normalized_attachment.get("mimeType"),
                "size": normalized_attachment.get("size"),
                "storage_url": normalized_attachment.get("storageUrl"),
                "metadata": normalize_json_object(normalized_attachment.get("metadata")),
            }
        )

    return normalized_attachments


def normalize_chat_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []

    for message in messages or []:
        content = sanitize_text(message.get("text"))
        attachments = normalize_chat_message_attachments(message.get("attachments"))
        if not content and not attachments:
            continue

        client_message_id = sanitize_text(message.get("clientMessageId") or message.get("id")) or f"message-{uuid4().hex}"
        metadata = {
            "original_sender": sanitize_text(message.get("sender")),
            "client_timestamp": sanitize_text(message.get("timestamp")),
            CHAT_MESSAGE_ID_METADATA_KEY: client_message_id,
        }
        if attachments:
            metadata[CHAT_ATTACHMENTS_METADATA_KEY] = serialize_chat_message_attachment_metadata_payload(attachments)

        normalized.append(
            {
                "client_message_id": client_message_id,
                "role": map_sender_to_role(sanitize_text(message.get("sender"))),
                "content": content,
                "attachments": attachments,
                "metadata": metadata,
            }
        )

    return normalized


def sync_chat_message_attachments(
    ticket_public_id: str,
    conversation_id: int,
    normalized_messages: list[dict[str, Any]],
    uploaded_files: list[Any] | None = None,
) -> list[dict[str, Any]]:
    uploaded_files = list(uploaded_files or [])
    attachment_specs: list[dict[str, Any]] = []
    attachment_owner_by_id: dict[str, str] = {}

    for message in normalized_messages:
        client_message_id = sanitize_text(message.get("client_message_id"))
        message_attachments: list[dict[str, Any]] = []
        for attachment in message.get("attachments") or []:
            client_attachment_id = sanitize_text(attachment.get("client_attachment_id"))
            if not client_attachment_id:
                continue

            previous_owner = attachment_owner_by_id.get(client_attachment_id)
            if previous_owner and previous_owner != client_message_id:
                raise ApiError(400, "Each chat attachment must belong to only one message.")

            attachment_owner_by_id[client_attachment_id] = client_message_id
            attachment_spec = {
                "client_message_id": client_message_id,
                "client_attachment_id": client_attachment_id,
                "name": sanitize_support_attachment_name(attachment.get("name")),
                "mime_type": sanitize_text(attachment.get("mime_type")) or None,
                "size": int(attachment["size"]) if isinstance(attachment.get("size"), int) else None,
                "storage_url": sanitize_text(attachment.get("storage_url")) or None,
                "metadata": normalize_json_object(attachment.get("metadata")),
            }
            message_attachments.append(attachment_spec)
            attachment_specs.append(attachment_spec)

        message["attachments"] = message_attachments

    pending_attachment_specs = [
        attachment
        for attachment in attachment_specs
        if not sanitize_text(attachment.get("storage_url"))
    ]
    if len(pending_attachment_specs) != len(uploaded_files):
        raise ApiError(400, "Chat attachment upload data is incomplete. Please try attaching the files again.")

    stored_storage_keys: list[str] = []
    try:
        for attachment_spec, uploaded_file in zip(pending_attachment_specs, uploaded_files):
            stored_attachment = store_uploaded_message_attachment(ticket_public_id, uploaded_file)
            stored_storage_key = sanitize_text(stored_attachment.get("storageKey"))
            if stored_storage_key:
                stored_storage_keys.append(stored_storage_key)

            attachment_spec["name"] = stored_attachment["name"]
            attachment_spec["mime_type"] = stored_attachment.get("mimeType")
            attachment_spec["size"] = stored_attachment.get("size")
            attachment_spec["storage_url"] = stored_storage_key or None
            attachment_spec["metadata"] = {
                **normalize_json_object(attachment_spec.get("metadata")),
                **normalize_json_object(stored_attachment.get("metadata")),
            }

        existing_rows = run_query(
            """
            SELECT client_message_id, client_attachment_id, file_name, mime_type, file_size, storage_url, metadata
            FROM message_attachments
            WHERE conversation_id = %s
            ORDER BY created_at ASC, id ASC
            """,
            [conversation_id],
        )
        existing_rows_by_attachment_id = {
            sanitize_text(row.get("client_attachment_id")): row
            for row in existing_rows
            if sanitize_text(row.get("client_attachment_id"))
        }

        prepared_attachment_rows: list[dict[str, Any]] = []
        referenced_attachment_ids: set[str] = set()
        for attachment_spec in attachment_specs:
            client_attachment_id = sanitize_text(attachment_spec.get("client_attachment_id"))
            if not client_attachment_id or client_attachment_id in referenced_attachment_ids:
                continue

            referenced_attachment_ids.add(client_attachment_id)
            existing_row = existing_rows_by_attachment_id.get(client_attachment_id) or {}
            storage_url = sanitize_text(attachment_spec.get("storage_url")) or sanitize_text(existing_row.get("storage_url"))
            if not storage_url:
                raise ApiError(400, "One or more chat attachments are missing an uploaded file.")

            existing_size = existing_row.get("file_size")
            prepared_attachment_rows.append(
                {
                    "client_message_id": sanitize_text(attachment_spec.get("client_message_id")),
                    "client_attachment_id": client_attachment_id,
                    "file_name": sanitize_support_attachment_name(attachment_spec.get("name") or existing_row.get("file_name")),
                    "mime_type": sanitize_text(attachment_spec.get("mime_type") or existing_row.get("mime_type")) or None,
                    "file_size": (
                        int(attachment_spec["size"])
                        if isinstance(attachment_spec.get("size"), int)
                        else (
                            int(existing_size)
                            if isinstance(existing_size, (int, float))
                            else None
                        )
                    ),
                    "storage_url": storage_url,
                    "metadata": {
                        **normalize_json_object(existing_row.get("metadata")),
                        **normalize_json_object(attachment_spec.get("metadata")),
                        "clientMessageId": sanitize_text(attachment_spec.get("client_message_id")),
                        "clientAttachmentId": client_attachment_id,
                    },
                }
            )

        attachments_by_message_id: dict[str, list[dict[str, Any]]] = {}
        for attachment_row in prepared_attachment_rows:
            attachments_by_message_id.setdefault(sanitize_text(attachment_row.get("client_message_id")), []).append(attachment_row)

        for message in normalized_messages:
            client_message_id = sanitize_text(message.get("client_message_id"))
            message_attachments = attachments_by_message_id.get(client_message_id, [])
            if message_attachments:
                message["attachments"] = message_attachments
                message["metadata"][CHAT_ATTACHMENTS_METADATA_KEY] = serialize_chat_message_attachment_metadata_payload(message_attachments)
            else:
                message["attachments"] = []
                message["metadata"].pop(CHAT_ATTACHMENTS_METADATA_KEY, None)

        replaced_storage_keys: set[str] = set()
        pending_storage_keys_by_attachment_id = {
            sanitize_text(attachment.get("client_attachment_id")): sanitize_text(attachment.get("storage_url"))
            for attachment in pending_attachment_specs
            if sanitize_text(attachment.get("client_attachment_id")) and sanitize_text(attachment.get("storage_url"))
        }
        for row in existing_rows:
            client_attachment_id = sanitize_text(row.get("client_attachment_id"))
            existing_storage_key = sanitize_text(row.get("storage_url"))
            if not client_attachment_id or not existing_storage_key:
                continue

            if client_attachment_id not in referenced_attachment_ids:
                replaced_storage_keys.add(existing_storage_key)
                continue

            replacement_storage_key = pending_storage_keys_by_attachment_id.get(client_attachment_id)
            if replacement_storage_key and replacement_storage_key != existing_storage_key:
                replaced_storage_keys.add(existing_storage_key)

        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM message_attachments WHERE conversation_id = %s", [conversation_id])
            for attachment_row in prepared_attachment_rows:
                cursor.execute(
                    """
                    INSERT INTO message_attachments (
                      conversation_id,
                      client_message_id,
                      client_attachment_id,
                      file_name,
                      mime_type,
                      file_size,
                      storage_url,
                      metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    [
                        conversation_id,
                        attachment_row["client_message_id"],
                        attachment_row["client_attachment_id"],
                        attachment_row["file_name"],
                        attachment_row["mime_type"],
                        attachment_row["file_size"],
                        attachment_row["storage_url"],
                        json.dumps(attachment_row["metadata"]),
                    ],
                )

        if replaced_storage_keys:
            transaction.on_commit(
                lambda keys=tuple(replaced_storage_keys): [
                    delete_support_attachment_file(storage_key)
                    for storage_key in keys
                ]
            )
    except Exception:
        for storage_key in stored_storage_keys:
            delete_support_attachment_file(storage_key)
        raise

    return normalized_messages


def sync_conversation_messages(
    conversation_id: int,
    status: str,
    messages: list[dict[str, Any]],
    *,
    ticket_public_id: str,
    uploaded_files: list[Any] | None = None,
    conversation_metadata_patch: dict[str, Any] | None = None,
    reference_time: datetime | None = None,
) -> list[dict[str, Any]]:
    filtered_messages = sync_chat_message_attachments(
        ticket_public_id,
        conversation_id,
        normalize_chat_messages(messages),
        uploaded_files=uploaded_files,
    )
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
    ticket_public_id: str,
    uploaded_files: list[Any] | None = None,
    conversation_metadata_patch: dict[str, Any] | None = None,
    reference_time: datetime | None = None,
) -> tuple[list[dict[str, Any]], str, str, bool]:
    persisted_at = reference_time or datetime.now(timezone.utc)
    apply_ticket_sla_policy(ticket)
    filtered_messages = sync_conversation_messages(
        int(ticket["conversation_id"]),
        status,
        messages,
        ticket_public_id=ticket_public_id,
        uploaded_files=uploaded_files,
        conversation_metadata_patch=conversation_metadata_patch,
        reference_time=persisted_at,
    )
    next_status_reason = status_reason if status_reason is not None else (ticket.get("status_reason") or "")
    if status == "Pending" and not next_status_reason:
        next_status_reason = get_default_status_reason_for_status(status)
    elif status == "Pending" and status_reason is None and not is_status_reason_allowed_for_status(status, next_status_reason):
        next_status_reason = get_default_status_reason_for_status(status)
    next_sla_status, next_sla_attention_required, next_sla_attention_reason, updated_ticket_metadata = resolve_ticket_sla_update(
        ticket,
        status,
        status_reason=next_status_reason,
    )
    updated_ticket_metadata, ticket_state_columns = build_ticket_state_persistence(
        updated_ticket_metadata,
        {
            **ticket,
            "status": status,
            "status_reason": next_status_reason,
        },
        chat_state=map_conversation_status(status),
    )

    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE tickets
            SET status = %s,
                status_reason = %s,
                sla_status = %s,
                metadata = %s::jsonb,
                ticket_type = %s,
                workflow_stage = %s,
                queue_scope = %s,
                dashboard_bucket = %s,
                can_show_conversation = %s,
                can_receive_chat = %s,
                resolution_reason = %s,
                updated_at = NOW(),
                closed_at = CASE
                  WHEN %s = 'Closed' THEN NOW()
                  WHEN status = 'Closed' AND %s <> 'Closed' THEN NULL
                  ELSE closed_at
                END
            WHERE id = %s
            """,
            [
                status,
                next_status_reason,
                next_sla_status,
                json.dumps(updated_ticket_metadata),
                *get_ticket_state_column_params(ticket_state_columns),
                status,
                status,
                ticket["id"],
            ],
        )

    if status == "Pending" and is_quick_ticket_status_reason(next_status_reason) and not is_coverage_ticket_record(ticket):
        assignment_ticket = {
            **ticket,
            "status": status,
            "status_reason": next_status_reason,
            "metadata": updated_ticket_metadata,
        }
        if try_auto_assign_quick_ticket(assignment_ticket, now=persisted_at):
            ticket.update(
                {
                    "assigned_agent_id": assignment_ticket.get("assigned_agent_id"),
                    "assigned_agent_username": assignment_ticket.get("assigned_agent_username"),
                    "assigned_agent_name": assignment_ticket.get("assigned_agent_name"),
                    "assigned_team": assignment_ticket.get("assigned_team"),
                    "metadata": assignment_ticket.get("metadata"),
                }
            )

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
            ticket_public_id=ticket["public_id"],
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
            ticket_public_id=ticket["public_id"],
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
    global _last_open_ticket_inactivity_sync_started_monotonic

    if not public_id:
        min_interval_seconds = get_open_ticket_inactivity_sync_min_interval_seconds()
        if min_interval_seconds > 0:
            comparison_now = time.monotonic()
            with _open_ticket_inactivity_sync_lock:
                if (
                    _last_open_ticket_inactivity_sync_started_monotonic
                    and (comparison_now - _last_open_ticket_inactivity_sync_started_monotonic) < min_interval_seconds
                ):
                    return {"scanned": 0, "reminded": 0, "closed": 0}
                _last_open_ticket_inactivity_sync_started_monotonic = comparison_now

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
        SELECT id, username, full_name, email, account_scope, role, is_active, metadata
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


def fetch_staff_admin_account_by_email(email: str | None) -> dict[str, Any] | None:
    normalized_email = normalize_account_email(email)
    if not normalized_email:
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
        [normalized_email, ACCOUNT_SCOPE_STAFF, list(ADMIN_ACCESS_ROLES)],
    )


def fetch_staff_support_account_by_email(email: str | None) -> dict[str, Any] | None:
    normalized_email = normalize_account_email(email)
    if not normalized_email:
        return None

    return run_query_one(
        """
        SELECT id, username, full_name, email, account_scope, role, is_active, metadata
        FROM support_accounts
        WHERE LOWER(TRIM(email)) = %s
          AND account_scope = %s
        ORDER BY
          CASE WHEN is_active = TRUE THEN 0 ELSE 1 END,
          id ASC
        LIMIT 1
        """,
        [normalized_email, ACCOUNT_SCOPE_STAFF],
    )


def fetch_staff_support_account_by_legacy_auth_user_id(legacy_auth_user_id: int) -> dict[str, Any] | None:
    if legacy_auth_user_id <= 0:
        return None

    return run_query_one(
        """
        SELECT id, username, full_name, email, account_scope, role, is_active, metadata
        FROM support_accounts
        WHERE account_scope = %s
          AND COALESCE(metadata->>'legacy_auth_user_id', '') ~ '^[0-9]+$'
          AND (metadata->>'legacy_auth_user_id')::integer = %s
        ORDER BY
          CASE WHEN is_active = TRUE THEN 0 ELSE 1 END,
          id ASC
        LIMIT 1
        """,
        [ACCOUNT_SCOPE_STAFF, legacy_auth_user_id],
    )


def fetch_staff_support_account_by_entra_object_id(entra_object_id: str | None) -> dict[str, Any] | None:
    normalized_object_id = sanitize_text(entra_object_id)
    if not normalized_object_id:
        return None

    return run_query_one(
        """
        SELECT id, username, full_name, email, account_scope, role, is_active, metadata
        FROM support_accounts
        WHERE account_scope = %s
          AND metadata->>'entra_object_id' = %s
        ORDER BY
          CASE WHEN is_active = TRUE THEN 0 ELSE 1 END,
          id ASC
        LIMIT 1
        """,
        [ACCOUNT_SCOPE_STAFF, normalized_object_id],
    )


def legacy_auth_user_has_admin_login_access(legacy_user: dict[str, Any]) -> bool:
    return (
        normalize_bool(legacy_user.get("has_support_access"))
        or normalize_bool(legacy_user.get("has_operations_access"))
        or normalize_bool(legacy_user.get("has_admin_access"))
    )


def build_support_staff_role_from_legacy_auth_user(legacy_user: dict[str, Any]) -> str:
    if normalize_bool(legacy_user.get("is_superuser")):
        return ROLE_SUPERADMIN
    if normalize_bool(legacy_user.get("has_admin_access")):
        return ROLE_ADMIN
    return ROLE_AGENT


def build_support_staff_username_candidate(legacy_user: dict[str, Any]) -> str:
    base_username = sanitize_text(legacy_user.get("username")).lower()
    if not base_username:
        email = sanitize_text(legacy_user.get("email")).lower()
        base_username = email.split("@", 1)[0] if "@" in email else ""
    if not base_username:
        base_username = f"kbcstaff{int(legacy_user.get('id') or 0)}"

    normalized_username = re.sub(r"[^a-z0-9._-]+", ".", base_username).strip("._-")
    return normalized_username or f"kbcstaff{int(legacy_user.get('id') or 0)}"


def build_support_staff_username_candidate_from_entra_profile(profile: dict[str, Any], email: str) -> str:
    for key in ("userPrincipalName", "mail", "preferred_username", "upn", "email"):
        raw_value = sanitize_text(profile.get(key)).lower()
        if raw_value:
            base_username = raw_value.split("@", 1)[0]
            break
    else:
        base_username = sanitize_text(profile.get("displayName") or profile.get("name")).lower()

    if not base_username:
        base_username = email.split("@", 1)[0] if "@" in email else ""
    if not base_username:
        base_username = f"entrauser{sanitize_text(profile.get('id') or profile.get('oid'))[:8]}"

    normalized_username = re.sub(r"[^a-z0-9._-]+", ".", base_username).strip("._-")
    return normalized_username or "entrauser"


def resolve_unique_support_staff_username(base_username: str, *, exclude_agent_id: int | None = None) -> str:
    normalized_base_username = sanitize_text(base_username).lower()
    if not normalized_base_username:
        normalized_base_username = "kbcstaff"

    if not find_agent_account_by_username(normalized_base_username, exclude_agent_id=exclude_agent_id):
        return normalized_base_username

    suffix = 2
    while True:
        candidate_username = f"{normalized_base_username}.{suffix}"
        if not find_agent_account_by_username(candidate_username, exclude_agent_id=exclude_agent_id):
            return candidate_username
        suffix += 1


def sync_support_staff_account_from_legacy_auth_user(legacy_user: dict[str, Any]) -> dict[str, Any]:
    normalized_email = normalize_account_email(legacy_user.get("email"))
    if not normalized_email:
        raise ApiError(403, "Your Microsoft account must provide a valid email address.")

    legacy_auth_user_id = int(legacy_user.get("id") or 0)
    legacy_full_name = sanitize_text(legacy_user.get("full_name")) or sanitize_text(legacy_user.get("username"))
    legacy_role = build_support_staff_role_from_legacy_auth_user(legacy_user)
    metadata_patch = {
        "legacy_auth_user_id": legacy_auth_user_id,
        "legacy_auth_source": "kbc_auth_user",
        "legacy_auth_synced_at": datetime.now(timezone.utc).isoformat(),
        "legacy_auth_email": normalized_email,
        "legacy_support_access": normalize_bool(legacy_user.get("has_support_access")),
        "legacy_operations_access": normalize_bool(legacy_user.get("has_operations_access")),
        "legacy_admin_access": normalize_bool(legacy_user.get("has_admin_access")),
    }

    existing_account = (
        fetch_staff_support_account_by_legacy_auth_user_id(legacy_auth_user_id)
        or fetch_staff_support_account_by_email(normalized_email)
        or fetch_staff_admin_account_by_email(normalized_email)
    )
    if existing_account:
        updated_metadata = normalize_json_object(existing_account.get("metadata"))
        updated_metadata.update(metadata_patch)
        email_owner = find_agent_account_by_email(normalized_email, exclude_agent_id=int(existing_account["id"]))
        resolved_email = normalized_email if not email_owner else None

        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE support_accounts
                    SET
                      username = %s,
                      full_name = %s,
                      email = %s,
                      account_scope = %s,
                      role = %s,
                      is_active = TRUE,
                      metadata = %s::jsonb,
                      updated_at = NOW()
                    WHERE id = %s
                    """,
                    [
                        resolve_unique_support_staff_username(
                            build_support_staff_username_candidate(legacy_user),
                            exclude_agent_id=int(existing_account["id"]),
                        ),
                        legacy_full_name,
                        resolved_email,
                        ACCOUNT_SCOPE_STAFF,
                        legacy_role,
                        json.dumps(updated_metadata),
                        int(existing_account["id"]),
                    ],
                )

        refreshed_account = fetch_agent_account_by_id(int(existing_account["id"]))
        if refreshed_account:
            return refreshed_account
        raise ApiError(500, "We could not refresh the linked support account right now.")

    username_candidate = resolve_unique_support_staff_username(
        build_support_staff_username_candidate(legacy_user)
    )
    email_owner = find_agent_account_by_email(normalized_email)
    initial_metadata = {
        **metadata_patch,
        "session_active": False,
        "console_status": DEFAULT_AGENT_CONSOLE_STATUS,
        "created_via": "microsoft_legacy_auth_sync",
    }

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
                VALUES (%s, %s, %s, %s, %s, TRUE, %s::jsonb)
                RETURNING id
                """,
                [
                    username_candidate,
                    legacy_full_name,
                    None if email_owner else normalized_email,
                    ACCOUNT_SCOPE_STAFF,
                    legacy_role,
                    json.dumps(initial_metadata),
                ],
            )
            created_row = cursor.fetchone()

    if not created_row:
        raise ApiError(500, "We could not create the linked support account right now.")

    created_account = fetch_agent_account_by_id(int(created_row[0]))
    if created_account:
        return created_account

    raise ApiError(500, "We could not load the linked support account right now.")


def normalize_entra_directory_role(role: dict[str, Any]) -> dict[str, str]:
    return {
        "id": sanitize_text(role.get("id")),
        "displayName": sanitize_text(role.get("displayName")),
        "roleTemplateId": sanitize_text(role.get("roleTemplateId")),
    }


def normalize_directory_role_name(value: Any) -> str:
    return sanitize_text(value).lower()


def get_configured_directory_role_names(values: list[str]) -> set[str]:
    return {normalize_directory_role_name(value) for value in values if normalize_directory_role_name(value)}


def derive_support_role_from_entra_directory_roles(directory_roles: list[dict[str, Any]]) -> str | None:
    role_names = {
        normalize_directory_role_name(role.get("displayName"))
        for role in directory_roles
        if normalize_directory_role_name(role.get("displayName"))
    }
    if not role_names:
        return None

    superadmin_role_names = get_configured_directory_role_names(settings.AZURE_LOGIN_SUPERADMIN_DIRECTORY_ROLES)
    if role_names & superadmin_role_names:
        return ROLE_SUPERADMIN

    admin_role_names = get_configured_directory_role_names(settings.AZURE_LOGIN_ADMIN_DIRECTORY_ROLES)
    if admin_role_names and role_names & admin_role_names:
        return ROLE_ADMIN

    if normalize_bool(settings.AZURE_LOGIN_ALLOW_ANY_DIRECTORY_ROLE):
        return ROLE_ADMIN

    return None


def sync_support_staff_account_from_entra_directory_user(
    profile: dict[str, Any],
    directory_roles: list[dict[str, Any]],
    support_role: str,
) -> dict[str, Any]:
    candidate_emails = extract_microsoft_login_email_candidates(profile)
    normalized_email = candidate_emails[0] if candidate_emails else ""
    if not normalized_email:
        raise ApiError(403, "Your Microsoft account must provide a valid email address.")

    normalized_role = ROLE_SUPERADMIN if support_role == ROLE_SUPERADMIN else ROLE_ADMIN
    entra_object_id = sanitize_text(profile.get("id") or profile.get("oid") or profile.get("sub"))
    if not entra_object_id:
        raise ApiError(403, "Your Microsoft account must provide a directory object id.")

    full_name = (
        sanitize_text(profile.get("displayName"))
        or sanitize_text(profile.get("name"))
        or normalized_email.split("@", 1)[0]
    )
    normalized_directory_roles = [normalize_entra_directory_role(role) for role in directory_roles]
    metadata_patch = {
        "entra_object_id": entra_object_id,
        "entra_source": "microsoft_graph_directory_roles",
        "entra_synced_at": datetime.now(timezone.utc).isoformat(),
        "entra_email": normalized_email,
        "entra_directory_admin_access": True,
        "entra_directory_roles": normalized_directory_roles,
    }

    existing_account = (
        fetch_staff_support_account_by_entra_object_id(entra_object_id)
        or fetch_staff_support_account_by_email(normalized_email)
        or fetch_staff_admin_account_by_email(normalized_email)
    )
    if existing_account:
        updated_metadata = normalize_json_object(existing_account.get("metadata"))
        updated_metadata.update(metadata_patch)
        email_owner = find_agent_account_by_email(normalized_email, exclude_agent_id=int(existing_account["id"]))
        resolved_email = normalized_email if not email_owner else None

        existing_username = sanitize_text(existing_account.get("username"))
        preserved_username = existing_username or resolve_unique_support_staff_username(
            build_support_staff_username_candidate_from_entra_profile(profile, normalized_email),
            exclude_agent_id=int(existing_account["id"]),
        )

        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE support_accounts
                    SET
                      username = %s,
                      full_name = %s,
                      email = %s,
                      account_scope = %s,
                      role = %s,
                      is_active = TRUE,
                      metadata = %s::jsonb,
                      updated_at = NOW()
                    WHERE id = %s
                    """,
                    [
                        preserved_username,
                        full_name,
                        resolved_email,
                        ACCOUNT_SCOPE_STAFF,
                        normalized_role,
                        json.dumps(updated_metadata),
                        int(existing_account["id"]),
                    ],
                )

        refreshed_account = fetch_agent_account_by_id(int(existing_account["id"]))
        if refreshed_account:
            return refreshed_account
        raise ApiError(500, "We could not refresh the Microsoft support account right now.")

    username_candidate = resolve_unique_support_staff_username(
        build_support_staff_username_candidate_from_entra_profile(profile, normalized_email)
    )
    email_owner = find_agent_account_by_email(normalized_email)
    initial_metadata = {
        **metadata_patch,
        "session_active": False,
        "console_status": DEFAULT_AGENT_CONSOLE_STATUS,
        "created_via": "microsoft_entra_directory_role_sync",
    }

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
                VALUES (%s, %s, %s, %s, %s, TRUE, %s::jsonb)
                RETURNING id
                """,
                [
                    username_candidate,
                    full_name,
                    None if email_owner else normalized_email,
                    ACCOUNT_SCOPE_STAFF,
                    normalized_role,
                    json.dumps(initial_metadata),
                ],
            )
            created_row = cursor.fetchone()

    if not created_row:
        raise ApiError(500, "We could not create the Microsoft support account right now.")

    created_account = fetch_agent_account_by_id(int(created_row[0]))
    if created_account:
        return created_account

    raise ApiError(500, "We could not load the Microsoft support account right now.")


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
    local_learner = find_kbc_learner_by_email(email)

    if local_learner:
        managed_account = fetch_public_requester_account_by_email(email)
        if managed_account and not is_auto_synced_learner_requester_account(managed_account):
            requester_role = apply_public_requester_role_overrides(email, managed_account.get("role"))
            return {
                "email": email,
                "role": requester_role,
                "account": managed_account,
                "learner": local_learner,
                "display_name": (
                    sanitize_text(managed_account.get("full_name"))
                    or sanitize_text(local_learner.get("full_name") if local_learner else "")
                    or sanitize_text(managed_account.get("username"))
                ),
                "source": MANAGED_PUBLIC_REQUESTER_SOURCE,
            }

        return {
            "email": email,
            "role": apply_public_requester_role_overrides(email, ROLE_USER),
            "account": None,
            "learner": local_learner,
            "display_name": sanitize_text(local_learner.get("full_name")) or email,
            "source": "kbc_users_data",
        }

    entra_user = fetch_microsoft_entra_user_by_email(email)
    if not entra_user:
        return None

    return {
        "email": email,
        "role": apply_public_requester_role_overrides(email, ROLE_USER),
        "account": None,
        "learner": fetch_local_learner_by_email(email),
        "display_name": sanitize_text(entra_user.get("displayName")) or email,
        "entra_user": entra_user,
        "source": MICROSOFT_ENTRA_REQUESTER_SOURCE,
    }


def ensure_public_requester_learner(requester: dict[str, Any]) -> dict[str, Any]:
    existing_learner = requester.get("learner")
    managed_account = requester.get("account")

    if not managed_account:
        if existing_learner:
            return existing_learner

        entra_user = requester.get("entra_user")
        if entra_user:
            ensured_entra_learner = upsert_learner_record(
                build_entra_public_requester_learner_payload(requester["email"], entra_user),
                source=MICROSOFT_ENTRA_REQUESTER_SOURCE,
                metadata={
                    "microsoft_entra_requester": True,
                    "entra_object_id": sanitize_text(entra_user.get("id")),
                    "entra_user_principal_name": sanitize_text(entra_user.get("userPrincipalName")),
                    "synced_on_demand": True,
                },
            )
            if not ensured_entra_learner:
                raise ApiError(500, "We could not prepare this Microsoft Entra requester right now.")
            return ensured_entra_learner

        raise ApiError(404, "This email is not registered in our records.")

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


def persist_ticket_metadata_patch(ticket_id: int, metadata_patch: dict[str, Any]) -> None:
    if not metadata_patch:
        return

    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE tickets
            SET metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb,
                updated_at = NOW()
            WHERE id = %s
            """,
            [json.dumps(metadata_patch), ticket_id],
        )


def sync_legacy_access_group_membership(legacy_auth_user_id: int, group_name: str, enabled: bool) -> None:
    normalized_user_id = int(legacy_auth_user_id or 0)
    if normalized_user_id <= 0:
        raise ApiError(400, "A linked KBC auth user is required.")
    normalized_group_name = sanitize_text(group_name).lower()
    if not normalized_group_name:
        raise ApiError(400, "A valid KBC auth access group is required.")
    auth_database_url = get_support_auth_database_url()
    if not auth_database_url:
        raise ApiError(503, "KBC auth database is not configured.")

    try:
        with psycopg.connect(auth_database_url) as source_connection:
            with source_connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id FROM auth_user WHERE id = %s AND is_active = TRUE LIMIT 1",
                    [normalized_user_id],
                )
                if not cursor.fetchone():
                    raise ApiError(404, "Linked KBC auth user was not found.")

                cursor.execute(
                    "SELECT id FROM auth_group WHERE LOWER(TRIM(name)) = %s LIMIT 1",
                    [normalized_group_name],
                )
                group_row = cursor.fetchone()
                if group_row:
                    group_id = int(group_row[0])
                elif enabled:
                    cursor.execute(
                        "INSERT INTO auth_group (name) VALUES (%s) RETURNING id",
                        [SUPPORT_ACCESS_GROUP_NAME],
                    )
                    group_id = int(cursor.fetchone()[0])
                else:
                    return

                if enabled:
                    cursor.execute(
                        """
                        INSERT INTO auth_user_groups (user_id, group_id)
                        SELECT %s, %s
                        WHERE NOT EXISTS (
                          SELECT 1
                          FROM auth_user_groups
                          WHERE user_id = %s AND group_id = %s
                        )
                        """,
                        [normalized_user_id, group_id, normalized_user_id, group_id],
                    )
                else:
                    cursor.execute(
                        "DELETE FROM auth_user_groups WHERE user_id = %s AND group_id = %s",
                        [normalized_user_id, group_id],
                    )
    except ApiError:
        raise
    except Exception as exc:
        log_unexpected_api_error("Failed to sync KBC access group membership.", exc)
        raise ApiError(502, "We could not update this agent in the KBC auth database right now.") from exc


def sync_legacy_support_access_group_membership(legacy_auth_user_id: int, enabled: bool) -> None:
    sync_legacy_access_group_membership(legacy_auth_user_id, SUPPORT_ACCESS_GROUP_NAME, enabled)


def sync_legacy_operations_access_group_membership(legacy_auth_user_id: int, enabled: bool) -> None:
    sync_legacy_access_group_membership(legacy_auth_user_id, OPERATIONS_ACCESS_GROUP_NAME, enabled)


def update_agent_ticket_access(
    agent_id: int,
    *,
    support_access: bool | None = None,
    operations_access: bool | None = None,
) -> dict[str, Any]:
    from django.contrib.auth import get_user_model
    from .admin import sync_operations_access_group_membership, sync_support_access_group_membership

    if support_access is None and operations_access is None:
        raise ApiError(400, "At least one ticket access field is required.")

    agent = run_query_one(
        """
        SELECT id, username, full_name, email, account_scope, role, is_active, metadata
        FROM support_accounts
        WHERE id = %s AND account_scope = %s
        LIMIT 1
        """,
        [agent_id, ACCOUNT_SCOPE_STAFF],
    )
    if not agent:
        raise ApiError(404, "Agent not found.")

    metadata = normalize_json_object(agent.get("metadata"))
    legacy_auth_user_id = int(metadata.get("legacy_auth_user_id") or 0)
    if legacy_auth_user_id > 0:
        if support_access is not None:
            sync_legacy_support_access_group_membership(legacy_auth_user_id, support_access)
        if operations_access is not None:
            sync_legacy_operations_access_group_membership(legacy_auth_user_id, operations_access)
    else:
        User = get_user_model()
        django_user = None
        agent_email = normalize_email(agent.get("email") or "")
        if agent_email:
            django_user = User.objects.filter(email__iexact=agent_email).first()
        if django_user:
            if support_access is not None:
                sync_support_access_group_membership(django_user, support_access)
            if operations_access is not None:
                sync_operations_access_group_membership(django_user, operations_access)

    if support_access is not None:
        metadata["legacy_support_access"] = support_access
    if operations_access is not None:
        metadata["legacy_operations_access"] = operations_access
    persist_agent_metadata(agent_id, metadata)

    agent["metadata"] = metadata
    return serialize_agent(agent, open_assigned_chat_agent_ids=get_open_assigned_live_chat_agent_ids())


def update_agent_support_access(agent_id: int, *, support_access: bool) -> dict[str, Any]:
    return update_agent_ticket_access(agent_id, support_access=support_access)


def update_agent_operations_access(agent_id: int, *, operations_access: bool) -> dict[str, Any]:
    return update_agent_ticket_access(agent_id, operations_access=operations_access)


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


def sort_agents_for_quick_ticket_queue(
    agents: list[dict[str, Any]],
    now: datetime | None = None,
    open_assigned_chat_agent_ids: set[int] | None = None,
) -> list[dict[str, Any]]:
    comparison_now = now or datetime.now(timezone.utc)
    busy_agent_ids = open_assigned_chat_agent_ids or set()

    def queue_sort_key(agent: dict[str, Any]) -> tuple[int, datetime, datetime, int]:
        metadata = normalize_json_object(agent.get("metadata"))
        agent_id = int(agent["id"])
        session_active = is_agent_session_active(metadata, comparison_now)
        effective_console_status = resolve_agent_console_status(
            metadata,
            session_active=session_active,
            has_open_assigned_chat=agent_id in busy_agent_ids,
        )
        queue_joined_at = get_agent_queue_joined_at(metadata, comparison_now) or comparison_now
        last_assigned_at = (
            get_agent_last_quick_ticket_assigned_at(metadata)
            or get_agent_last_live_chat_assigned_at(metadata)
            or queue_joined_at
            or comparison_now
        )
        priority = 0 if effective_console_status == "Available" else 1
        return (priority, last_assigned_at, queue_joined_at, agent_id)

    return sorted(agents, key=queue_sort_key)


def select_next_quick_ticket_agent(
    agents: list[dict[str, Any]],
    now: datetime | None = None,
    open_assigned_chat_agent_ids: set[int] | None = None,
) -> dict[str, Any] | None:
    comparison_now = now or datetime.now(timezone.utc)
    busy_agent_ids = open_assigned_chat_agent_ids or set()
    sorted_agents = sort_agents_for_quick_ticket_queue(agents, comparison_now, busy_agent_ids)

    for agent in sorted_agents:
        metadata = normalize_json_object(agent.get("metadata"))
        agent_id = int(agent["id"])
        session_active = is_agent_session_active(metadata, comparison_now)
        effective_console_status = resolve_agent_console_status(
            metadata,
            session_active=session_active,
            has_open_assigned_chat=agent_id in busy_agent_ids,
        )
        if effective_console_status == "Available":
            return agent

    return None


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
    ticket_metadata_patch, ticket_state_columns = build_ticket_state_persistence(
        {
            **ticket_metadata,
            "queue_assigned_at": assigned_at_value,
            "queue_assigned_agent_username": agent["username"],
            "queue_assigned_agent_name": agent_name,
        },
        {
            **ticket,
            "assigned_agent_id": next_assigned_agent_id,
            "assigned_team": assigned_team,
        },
        chat_state=ticket.get("conversation_status"),
    )

    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE tickets
            SET assigned_agent_id = %s,
                assigned_team = %s,
                metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb,
                ticket_type = %s,
                workflow_stage = %s,
                queue_scope = %s,
                dashboard_bucket = %s,
                can_show_conversation = %s,
                can_receive_chat = %s,
                resolution_reason = %s,
                updated_at = NOW()
            WHERE id = %s
            """,
            [
                next_assigned_agent_id,
                assigned_team,
                json.dumps(ticket_metadata_patch),
                *get_ticket_state_column_params(ticket_state_columns),
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
    ticket["metadata"] = ticket_metadata_patch
    ticket["conversation_metadata"] = {
        **conversation_metadata,
        "assigned_agent_id": next_assigned_agent_id,
        "assigned_agent_username": agent["username"],
        "assigned_agent_name": agent_name,
        "queue_assigned_at": assigned_at_value,
    }
    return True


def assign_quick_ticket_to_agent(ticket: dict[str, Any], agent: dict[str, Any], assigned_at: datetime) -> bool:
    next_assigned_agent_id = int(agent["id"])
    current_assigned_agent_id = int(ticket["assigned_agent_id"]) if ticket.get("assigned_agent_id") else None

    if current_assigned_agent_id == next_assigned_agent_id:
        return False

    assigned_at_value = serialize_datetime_value(assigned_at)
    ticket_metadata = normalize_json_object(ticket.get("metadata"))
    conversation_metadata = normalize_json_object(ticket.get("conversation_metadata"))
    assigned_team = derive_assigned_team(agent)
    agent_name = agent.get("full_name") or agent["username"]
    ticket_metadata_patch, ticket_state_columns = build_ticket_state_persistence(
        {
            **ticket_metadata,
            "quick_ticket_assigned_at": assigned_at_value,
            "quick_ticket_assigned_admin_username": agent["username"],
            "quick_ticket_assigned_admin_name": agent_name,
        },
        {
            **ticket,
            "assigned_agent_id": next_assigned_agent_id,
            "assigned_team": assigned_team,
        },
        chat_state=ticket.get("conversation_status"),
    )

    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE tickets
            SET assigned_agent_id = %s,
                assigned_team = %s,
                metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb,
                ticket_type = %s,
                workflow_stage = %s,
                queue_scope = %s,
                dashboard_bucket = %s,
                can_show_conversation = %s,
                can_receive_chat = %s,
                resolution_reason = %s,
                updated_at = NOW()
            WHERE id = %s
            """,
            [
                next_assigned_agent_id,
                assigned_team,
                json.dumps(ticket_metadata_patch),
                *get_ticket_state_column_params(ticket_state_columns),
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
            "fromAgentId": current_assigned_agent_id,
            "toAgentId": next_assigned_agent_id,
            "toAgentName": agent_name,
            "assignedAt": assigned_at_value,
            "assignmentSource": "quick_ticket",
            "statusReason": STATUS_REASON_QUICK_TICKET,
        },
    )

    next_agent_metadata = normalize_json_object(agent.get("metadata"))
    next_agent_metadata[LAST_QUICK_TICKET_ASSIGNED_AT_METADATA_KEY] = assigned_at_value
    persist_agent_metadata(int(agent["id"]), next_agent_metadata)
    agent["metadata"] = next_agent_metadata

    ticket["assigned_agent_id"] = next_assigned_agent_id
    ticket["assigned_agent_username"] = agent["username"]
    ticket["assigned_agent_name"] = agent_name
    ticket["assigned_team"] = assigned_team
    ticket["metadata"] = ticket_metadata_patch
    ticket["conversation_metadata"] = {
        **conversation_metadata,
        "assigned_agent_id": next_assigned_agent_id,
        "assigned_agent_username": agent["username"],
        "assigned_agent_name": agent_name,
        "quick_ticket_assigned_at": assigned_at_value,
    }
    return True


def try_auto_assign_quick_ticket(ticket: dict[str, Any], now: datetime | None = None) -> dict[str, Any] | None:
    if ticket.get("assigned_agent_id"):
        return None

    agent_candidates = run_query(
        """
        SELECT id, username, full_name, email, account_scope, role, metadata
        FROM support_accounts
        WHERE is_active = TRUE
          AND account_scope = %s
          AND (metadata->>'legacy_support_access')::boolean = TRUE
        ORDER BY id ASC
        """,
        [ACCOUNT_SCOPE_STAFF],
    )
    if not agent_candidates:
        return None

    assignment_now = now or datetime.now(timezone.utc)
    open_assigned_chat_agent_ids = get_open_assigned_live_chat_agent_ids()
    next_agent = select_next_quick_ticket_agent(agent_candidates, assignment_now, open_assigned_chat_agent_ids)
    if not next_agent:
        return None
    if not assign_quick_ticket_to_agent(ticket, next_agent, assignment_now):
        return None
    return next_agent


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
              AND (metadata->>'legacy_support_access')::boolean = TRUE
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
          t.is_archived,
          t.archived_at,
          t.archived_by_id,
          t.created_at,
          t.updated_at,
          t.closed_at,
          t.conversation_id,
          c.status AS conversation_status,
          c.metadata AS conversation_metadata,
          c.chat_duration_minutes,
          c.last_message_at,
          latest_session_request.status AS latest_session_request_status,
          latest_session_request.metadata AS latest_session_request_metadata,
          l.full_name AS learner_name,
          l.email AS learner_email,
          l.phone AS learner_phone,
          a.id AS assigned_agent_id,
          a.username AS assigned_agent_username,
          a.full_name AS assigned_agent_name,
          archived_by.username AS archived_by_username,
          archived_by.full_name AS archived_by_name
        FROM tickets t
        JOIN learners l
          ON l.id = t.learner_id
        LEFT JOIN conversations c
          ON c.id = t.conversation_id
        LEFT JOIN LATERAL (
          SELECT ssr.status, ssr.metadata
          FROM support_session_requests ssr
          WHERE ssr.ticket_id = t.id
          ORDER BY ssr.created_at DESC, ssr.id DESC
          LIMIT 1
        ) latest_session_request ON TRUE
        LEFT JOIN support_accounts a
          ON a.id = t.assigned_agent_id
        LEFT JOIN support_accounts archived_by
          ON archived_by.id = t.archived_by_id
        WHERE t.public_id = %s
        LIMIT 1
        """,
        [public_id],
    )

    if not ticket:
        return None

    ticket = synchronize_coverage_tutor_workflow_ticket(ticket)
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
    if has_quick_ticket_status_reason_history(history):
        ticket["_derived_is_quick_ticket"] = True
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
        "chatHistory": serialize_admin_chat_timeline_rows(ticket["public_id"], messages, chat_history_events),
        "attachments": [
            {
                "id": int(row["id"]),
                "name": row["file_name"],
                "mimeType": row.get("mime_type"),
                "size": int(row["file_size"]) if row.get("file_size") else 0,
                "storageUrl": (
                    row.get("storage_url")
                    if "://" in sanitize_text(row.get("storage_url"))
                    else (
                        build_admin_ticket_attachment_download_url(ticket["public_id"], int(row["id"]))
                        if sanitize_text(row.get("storage_url"))
                        else None
                    )
                ),
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
    requester_source = get_public_requester_source(requester)
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
    if requester_source:
        response["requesterSource"] = requester_source

    if not learner:
        return response

    existing_ticket = find_latest_active_ticket_for_learner(int(learner["id"]))
    if not existing_ticket:
        return response

    existing_ticket, existing_ticket_requester_role = promote_ticket_requester_role_if_needed(
        existing_ticket,
        requester_email=email,
        default_role=requester_role,
    )
    existing_ticket_metadata = normalize_json_object(existing_ticket.get("metadata"))
    existing_ticket_requester_source = get_ticket_requester_source(
        existing_ticket_metadata,
        default=requester_source,
    )
    response["ticket"] = {
        "id": existing_ticket["public_id"],
        "learnerName": requester.get("display_name") or learner.get("full_name") or "",
        "requesterName": requester.get("display_name") or learner.get("full_name") or "",
        "email": learner["email"],
        "requesterRole": existing_ticket_requester_role,
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
    if existing_ticket_requester_source:
        response["ticket"]["requesterSource"] = existing_ticket_requester_source

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

    # Staff-account password login is optional; KBC auth remains the fallback.
    dashboard_access_agent = (
        fetch_agent_account_by_username(username, active_only=True)
        or run_query_one(
            """
            SELECT id, username, full_name, email, account_scope, role, is_active, metadata
            FROM support_accounts
            WHERE LOWER(TRIM(email)) = %s
              AND account_scope = %s
              AND is_active = TRUE
            LIMIT 1
            """,
            [normalize_email(username), ACCOUNT_SCOPE_STAFF],
        )
    )
    if dashboard_access_agent and (
        actor_has_support_dashboard_access(dashboard_access_agent)
        or actor_has_operations_dashboard_access(dashboard_access_agent)
        or actor_has_admin_dashboard_access(dashboard_access_agent)
    ):
        agent_metadata = normalize_json_object(dashboard_access_agent.get("metadata"))
        if get_agent_password_hash(agent_metadata):
            if not verify_agent_password(dashboard_access_agent, password):
                raise ApiError(401, "Invalid username or password.")
            return {
                "admin": register_agent_session(
                    sanitize_text(dashboard_access_agent.get("username")).lower(),
                    instance_id,
                    console_status,
                ),
                "message": "Login successful.",
            }

        # Passwordless staff accounts should continue through the KBC auth
        # fallback below or Microsoft sign-in.
        if not fetch_legacy_support_user_by_username(username):
            raise ApiError(401, "This account does not have a password set. Please sign in with Microsoft.")

    # Fallback: legacy database login
    legacy_user = fetch_legacy_support_user_by_username(username)
    if not legacy_user:
        raise ApiError(401, "Invalid username or password.")

    password_hash = legacy_user.get("password_hash") or ""
    if not password_hash or not check_password(password, password_hash):
        raise ApiError(401, "Invalid username or password.")

    if not legacy_auth_user_has_admin_login_access(legacy_user):
        raise ApiError(403, "This account must have support, operations, or admin access.")

    matched_agent = sync_support_staff_account_from_legacy_auth_user(legacy_user)

    return {
        "admin": register_agent_session(
            sanitize_text(matched_agent.get("username")).lower(),
            instance_id,
            console_status,
        ),
        "message": "Login successful.",
    }


def is_microsoft_admin_login_configured() -> bool:
    return all(
        sanitize_text(value)
        for value in (
            settings.AZURE_LOGIN_TENANT_ID,
            settings.AZURE_LOGIN_CLIENT_ID,
            settings.AZURE_LOGIN_CLIENT_SECRET,
        )
    )


def build_microsoft_admin_authorize_url(*, redirect_uri: str, state: str, nonce: str) -> str:
    if not is_microsoft_admin_login_configured():
        raise ApiError(503, "Microsoft sign-in is not configured on the server.")

    query_string = urllib_parse.urlencode(
        {
            "client_id": settings.AZURE_LOGIN_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "response_mode": "query",
            "scope": " ".join(MICROSOFT_OIDC_SCOPES),
            "state": state,
            "nonce": nonce,
            "prompt": "select_account",
        },
        quote_via=urllib_parse.quote,
    )
    return f"{MICROSOFT_OIDC_AUTHORIZE_BASE_URL.format(tenant=settings.AZURE_LOGIN_TENANT_ID)}?{query_string}"


def decode_microsoft_jwt_payload(token: str) -> dict[str, Any]:
    normalized_token = sanitize_text(token)
    if not normalized_token:
        return {}

    segments = normalized_token.split(".")
    if len(segments) < 2:
        return {}

    payload_segment = segments[1]
    padding = "=" * (-len(payload_segment) % 4)
    try:
        decoded_payload = base64.urlsafe_b64decode(f"{payload_segment}{padding}".encode("utf-8"))
        parsed_payload = json.loads(decoded_payload.decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return {}

    return parsed_payload if isinstance(parsed_payload, dict) else {}


def get_json_request(url: str, headers: dict[str, str] | None = None) -> tuple[bool, bool, int | None, Any]:
    if not url:
        return False, False, None, None

    request = urllib_request.Request(
        url,
        headers=headers or {},
        method="GET",
    )
    return execute_http_request(request)


def request_microsoft_login_graph_access_token() -> tuple[bool, bool, int | None, Any]:
    if not is_microsoft_admin_login_configured():
        return False, False, None, None

    return post_form_request(
        MICROSOFT_OIDC_TOKEN_BASE_URL.format(tenant=settings.AZURE_LOGIN_TENANT_ID),
        {
            "client_id": settings.AZURE_LOGIN_CLIENT_ID,
            "client_secret": settings.AZURE_LOGIN_CLIENT_SECRET,
            "grant_type": "client_credentials",
            "scope": MICROSOFT_GRAPH_SCOPE,
        },
    )


def fetch_microsoft_graph_me(access_token: str) -> tuple[bool, bool, int | None, Any]:
    normalized_access_token = sanitize_text(access_token)
    if not normalized_access_token:
        return False, False, None, None

    return get_json_request(
        MICROSOFT_GRAPH_ME_URL,
        headers={"Authorization": f"Bearer {normalized_access_token}"},
    )


def fetch_microsoft_graph_user_by_email(access_token: str, email: str) -> tuple[bool, bool, int | None, Any]:
    normalized_access_token = sanitize_text(access_token)
    normalized_email = normalize_email(email)
    if not normalized_access_token or not is_valid_email(normalized_email):
        return False, False, None, None

    escaped_email = normalized_email.replace("'", "''")
    query_string = urllib_parse.urlencode(
        {
            "$select": "id,displayName,mail,userPrincipalName,accountEnabled",
            "$filter": f"mail eq '{escaped_email}' or userPrincipalName eq '{escaped_email}'",
        },
        quote_via=urllib_parse.quote,
    )
    return get_json_request(
        f"{MICROSOFT_GRAPH_USERS_URL}?{query_string}",
        headers={"Authorization": f"Bearer {normalized_access_token}"},
    )


def fetch_microsoft_entra_user_by_email(email: str) -> dict[str, Any] | None:
    normalized_email = normalize_email(email)
    if not is_valid_email(normalized_email):
        return None

    _, token_delivered, token_status, token_payload = request_microsoft_login_graph_access_token()
    if not token_delivered:
        return None
    if token_status is None or not (200 <= token_status < 300) or not isinstance(token_payload, dict):
        return None

    access_token = sanitize_text(token_payload.get("access_token"))
    if not access_token:
        return None

    _, user_delivered, user_status, user_payload = fetch_microsoft_graph_user_by_email(access_token, normalized_email)
    if user_status == 404:
        return None
    if user_status is None or not (200 <= user_status < 300) or not isinstance(user_payload, dict):
        if not user_delivered or user_status in {401, 403}:
            return None
        raise ApiError(
            502,
            extract_external_service_message(user_payload) or "We could not verify this email in Microsoft Entra right now.",
        )

    values = user_payload.get("value")
    if not isinstance(values, list) or not values:
        return None

    for candidate in values:
        normalized_candidate = normalize_entra_public_requester_user(candidate)
        if normalized_candidate:
            return normalized_candidate

    return None


def fetch_microsoft_graph_directory_roles(access_token: str) -> tuple[bool, bool, int | None, Any]:
    normalized_access_token = sanitize_text(access_token)
    if not normalized_access_token:
        return False, False, None, None

    directory_roles: list[dict[str, Any]] = []
    next_url = MICROSOFT_GRAPH_ME_DIRECTORY_ROLES_URL
    while next_url:
        delivered, response_delivered, status_code, payload = get_json_request(
            next_url,
            headers={"Authorization": f"Bearer {normalized_access_token}"},
        )
        if not delivered or not response_delivered:
            return delivered, response_delivered, status_code, payload
        if status_code is None or not (200 <= status_code < 300) or not isinstance(payload, dict):
            return delivered, response_delivered, status_code, payload

        page_values = payload.get("value")
        if isinstance(page_values, list):
            directory_roles.extend(role for role in page_values if isinstance(role, dict))

        next_url = sanitize_text(payload.get("@odata.nextLink"))

    return True, True, 200, directory_roles


def extract_microsoft_login_email_candidates(profile: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    for key in ("email", "preferred_username", "upn", "userPrincipalName", "mail", "unique_name"):
        raw_value = sanitize_text(profile.get(key))
        if not raw_value:
            continue
        try:
            normalized_value = normalize_account_email(raw_value)
        except ApiError:
            continue
        if normalized_value:
            candidates.append(normalized_value)

    return list(dict.fromkeys(candidates))


def _login_support_access_agent_from_entra(profile: dict[str, Any], normalized_email: str) -> dict[str, Any]:
    """Login path for staff who have KBC auth access but no Entra admin role."""
    candidate_emails = list(dict.fromkeys([normalized_email, *extract_microsoft_login_email_candidates(profile)]))
    legacy_user = next(
        (candidate for email in candidate_emails if (candidate := fetch_legacy_support_user_by_email(email))),
        None,
    )
    if not legacy_user:
        raise ApiError(403, "Your Microsoft account does not have access to the support portal.")
    if not legacy_auth_user_has_admin_login_access(legacy_user):
        raise ApiError(403, "Your Microsoft account does not have access to the support portal.")

    agent = sync_support_staff_account_from_legacy_auth_user(legacy_user)

    if not normalize_bool(agent.get("is_active")):
        raise ApiError(403, "Your account has been disabled. Please contact an administrator.")

    entra_object_id = sanitize_text(profile.get("id") or profile.get("oid") or profile.get("sub"))
    full_name = (
        sanitize_text(profile.get("displayName"))
        or sanitize_text(profile.get("name"))
        or normalized_email.split("@", 1)[0]
    )
    metadata = normalize_json_object(agent.get("metadata"))
    metadata["entra_object_id"] = entra_object_id or metadata.get("entra_object_id", "")
    metadata["entra_synced_at"] = datetime.now(timezone.utc).isoformat()
    metadata["entra_email"] = normalized_email
    persist_agent_metadata(int(agent["id"]), metadata)

    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE support_accounts SET full_name = %s, updated_at = NOW() WHERE id = %s",
            [full_name, int(agent["id"])],
        )

    refreshed = fetch_agent_account_by_id(int(agent["id"]))
    if not refreshed:
        raise ApiError(500, "We could not complete Microsoft sign-in right now.")
    return refreshed


def get_admin_microsoft_login_response(payload: dict[str, Any]) -> dict[str, Any]:
    code = sanitize_text(payload.get("code"))
    redirect_uri = sanitize_text(payload.get("redirectUri"))
    expected_nonce = sanitize_text(payload.get("expectedNonce"))

    if not code or not redirect_uri:
        raise ApiError(400, "Microsoft sign-in details are required.")
    if not is_microsoft_admin_login_configured():
        raise ApiError(503, "Microsoft sign-in is not configured on the server.")

    _, token_delivered, token_status, token_payload = post_form_request(
        MICROSOFT_OIDC_TOKEN_BASE_URL.format(tenant=settings.AZURE_LOGIN_TENANT_ID),
        {
            "client_id": settings.AZURE_LOGIN_CLIENT_ID,
            "client_secret": settings.AZURE_LOGIN_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "scope": " ".join(MICROSOFT_OIDC_SCOPES),
        },
    )
    if not token_delivered:
        raise ApiError(502, "We could not reach Microsoft sign-in right now.")
    if token_status is None or not (200 <= token_status < 300) or not isinstance(token_payload, dict):
        raise ApiError(
            401 if token_status in {400, 401, 403} else 502,
            extract_external_service_message(token_payload) or "Microsoft sign-in could not be completed right now.",
        )

    id_token_payload = decode_microsoft_jwt_payload(sanitize_text(token_payload.get("id_token")))
    returned_nonce = sanitize_text(id_token_payload.get("nonce"))
    if expected_nonce and returned_nonce != expected_nonce:
        raise ApiError(401, "Microsoft sign-in validation failed. Please try again.")

    access_token = sanitize_text(token_payload.get("access_token"))
    if not access_token:
        raise ApiError(401, "Microsoft sign-in did not return a Graph access token.")

    _, graph_delivered, graph_status, graph_payload = fetch_microsoft_graph_me(access_token)
    if not graph_delivered or graph_status is None or not (200 <= graph_status < 300) or not isinstance(graph_payload, dict):
        raise ApiError(
            401 if graph_status in {400, 401, 403} else 502,
            extract_external_service_message(graph_payload) or "We could not read your Microsoft directory profile.",
        )

    _, roles_delivered, roles_status, roles_payload = fetch_microsoft_graph_directory_roles(access_token)
    if not roles_delivered or roles_status is None or not (200 <= roles_status < 300) or not isinstance(roles_payload, list):
        raise ApiError(
            401 if roles_status in {400, 401, 403} else 502,
            extract_external_service_message(roles_payload) or "We could not read your Microsoft admin center access.",
        )

    merged_profile = {
        **id_token_payload,
        **graph_payload,
    }
    support_role = derive_support_role_from_entra_directory_roles(roles_payload)
    if not support_role:
        candidate_emails = extract_microsoft_login_email_candidates(merged_profile)
        normalized_email = candidate_emails[0] if candidate_emails else ""
        if not normalized_email:
            raise ApiError(403, "Your Microsoft account must provide a valid email address.")
        matched_agent = _login_support_access_agent_from_entra(merged_profile, normalized_email)
    else:
        matched_agent = sync_support_staff_account_from_entra_directory_user(merged_profile, roles_payload, support_role)

    instance_id = sanitize_text(payload.get("instanceId")) or uuid4().hex
    console_status = normalize_selectable_console_status(payload.get("consoleStatus"))
    registered_session = register_agent_session(
        sanitize_text(matched_agent.get("username")).lower(),
        instance_id,
        console_status,
    )

    return {
        "admin": registered_session,
        "message": "Microsoft sign-in successful.",
    }


def list_agents(*, include_inactive: bool = True) -> dict[str, Any]:
    where_clause = "WHERE account_scope = %s"
    query_params: list[Any] = [ACCOUNT_SCOPE_STAFF]
    if not include_inactive:
        where_clause += " AND is_active = TRUE"
    accounts = run_query(
        f"""
        SELECT id, username, full_name, email, account_scope, role, is_active, metadata
        FROM support_accounts
        {where_clause}
        ORDER BY
          CASE WHEN is_active = TRUE THEN 0 ELSE 1 END,
          full_name ASC NULLS LAST,
          username ASC
        """,
        query_params,
    )
    open_assigned_chat_agent_ids = get_open_assigned_live_chat_agent_ids()
    legacy_lookup = fetch_legacy_support_users_for_accounts(accounts)
    refreshed_accounts = [
        refresh_staff_account_legacy_access(account, legacy_lookup)
        for account in accounts
    ]
    serialized_accounts = [
        serialize_agent(account, open_assigned_chat_agent_ids=open_assigned_chat_agent_ids)
        for account in refreshed_accounts
    ]

    return {
        "accounts": serialized_accounts,
        "agents": serialized_accounts,
    }


def search_entra_agents(q: str) -> dict[str, Any]:
    normalized_q = sanitize_text(q)
    if not normalized_q or len(normalized_q) < 2:
        raise ApiError(400, "Search query must be at least 2 characters.")

    if not is_microsoft_admin_login_configured():
        raise ApiError(503, "Microsoft Entra is not configured on the server.")

    _, token_delivered, token_status, token_payload = request_microsoft_login_graph_access_token()
    if not token_delivered or token_status is None or not (200 <= token_status < 300) or not isinstance(token_payload, dict):
        raise ApiError(502, "We could not reach Microsoft Entra right now.")

    access_token = sanitize_text(token_payload.get("access_token"))
    if not access_token:
        raise ApiError(502, "We could not authenticate with Microsoft Entra right now.")

    escaped_q = normalized_q.replace("'", "''")
    query_string = urllib_parse.urlencode(
        {
            "$select": "id,displayName,mail,userPrincipalName,accountEnabled",
            "$filter": (
                f"accountEnabled eq true and ("
                f"startswith(displayName,'{escaped_q}') or "
                f"startswith(mail,'{escaped_q}') or "
                f"startswith(userPrincipalName,'{escaped_q}')"
                f")"
            ),
            "$top": "10",
        },
        quote_via=urllib_parse.quote,
    )
    _, delivered, status, payload = get_json_request(
        f"{MICROSOFT_GRAPH_USERS_URL}?{query_string}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if not delivered or status is None or not (200 <= status < 300) or not isinstance(payload, dict):
        raise ApiError(502, extract_external_service_message(payload) or "We could not search Microsoft Entra right now.")

    values = payload.get("value")
    if not isinstance(values, list):
        return {"results": []}

    existing_usernames: set[str] = set()
    existing_emails: set[str] = set()
    for account in run_query(
        """
        SELECT username, email
        FROM support_accounts
        WHERE account_scope = %s
          AND is_active = TRUE
          AND (metadata->>'legacy_support_access')::boolean = TRUE
        """,
        [ACCOUNT_SCOPE_STAFF],
    ):
        if account.get("username"):
            existing_usernames.add(sanitize_text(account["username"]).lower())
        if account.get("email"):
            existing_emails.add(normalize_email(account["email"]))

    results = []
    for user in values:
        if not isinstance(user, dict):
            continue
        if user.get("accountEnabled") is False:
            continue
        mail = normalize_email(sanitize_text(user.get("mail") or user.get("userPrincipalName") or ""))
        upn = sanitize_text(user.get("userPrincipalName") or "").lower()
        display_name = sanitize_text(user.get("displayName") or "")
        entra_id = sanitize_text(user.get("id") or "")
        if not mail and not upn:
            continue
        username = (upn.split("@")[0] if upn else mail.split("@")[0]).lower()
        already_added = username in existing_usernames or (mail and mail in existing_emails)
        results.append({
            "entraId": entra_id,
            "displayName": display_name,
            "email": mail or upn,
            "username": username,
            "alreadyAdded": already_added,
        })

    return {"results": results}


def _get_kbc_auth_db_connection():
    """Get a connection to the KBC auth database if configured, else use the default connection."""
    kbc_url = sanitize_text(settings.KBC_AUTH_DATABASE_URL) if hasattr(settings, "KBC_AUTH_DATABASE_URL") else ""
    if kbc_url:
        return psycopg.connect(kbc_url)
    return None


def _ensure_django_support_access(email: str, full_name: str) -> int | None:
    """Ensure the person has a Django user in the KBC auth database Support Access group. Returns the Django user id."""
    kbc_conn = _get_kbc_auth_db_connection()
    normalized_email = email.strip().lower()
    try:
        if kbc_conn:
            cursor_ctx = kbc_conn.cursor()
        else:
            cursor_ctx = connection.cursor()

        with cursor_ctx as cursor:
            cursor.execute(
                "SELECT id FROM auth_user WHERE LOWER(TRIM(email)) = %s LIMIT 1",
                [normalized_email],
            )
            row = cursor.fetchone()
            if row:
                django_user_id = row[0]
            else:
                name_parts = full_name.split(" ", 1)
                first_name = name_parts[0] if name_parts else ""
                last_name = name_parts[1] if len(name_parts) > 1 else ""
                django_username = normalized_email.split("@")[0]
                cursor.execute(
                    "SELECT id FROM auth_user WHERE LOWER(TRIM(username)) = %s LIMIT 1",
                    [django_username],
                )
                if cursor.fetchone():
                    django_username = normalized_email
                cursor.execute(
                    """
                    INSERT INTO auth_user
                      (username, email, first_name, last_name, password,
                       is_staff, is_active, is_superuser, date_joined)
                    VALUES (%s, %s, %s, %s, '', FALSE, TRUE, FALSE, NOW())
                    RETURNING id
                    """,
                    [django_username, normalized_email, first_name, last_name],
                )
                django_user_id = cursor.fetchone()[0]

            cursor.execute(
                "SELECT id FROM auth_group WHERE LOWER(TRIM(name)) = %s LIMIT 1",
                [SUPPORT_ACCESS_GROUP_NAME],
            )
            group_row = cursor.fetchone()
            if not group_row:
                if kbc_conn:
                    kbc_conn.commit()
                return django_user_id
            group_id = group_row[0]

            cursor.execute(
                "SELECT 1 FROM auth_user_groups WHERE user_id = %s AND group_id = %s LIMIT 1",
                [django_user_id, group_id],
            )
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO auth_user_groups (user_id, group_id) VALUES (%s, %s)",
                    [django_user_id, group_id],
                )

            if kbc_conn:
                kbc_conn.commit()

        return django_user_id
    finally:
        if kbc_conn:
            kbc_conn.close()


def add_entra_agent(payload: dict[str, Any]) -> dict[str, Any]:
    entra_id = sanitize_text(payload.get("entraId"))
    display_name = sanitize_text(payload.get("displayName"))
    email = normalize_email(sanitize_text(payload.get("email") or ""))
    username = sanitize_text(payload.get("username") or "").lower()

    if not entra_id or not email:
        raise ApiError(400, "Entra ID and email are required.")

    if not is_valid_email(email):
        raise ApiError(400, "Invalid email address.")

    existing = run_query_one(
        "SELECT id, role, is_active, metadata FROM support_accounts WHERE LOWER(TRIM(email)) = %s AND account_scope = %s LIMIT 1",
        [email, ACCOUNT_SCOPE_STAFF],
    )
    if existing:
        existing_metadata = normalize_json_object(existing.get("metadata"))
        if normalize_bool(existing_metadata.get("legacy_support_access")) and normalize_bool(existing.get("is_active", True)):
            raise ApiError(409, "This person is already added as an agent.")
        existing_metadata["legacy_support_access"] = True
        existing_metadata.pop("manually_added_agent", None)
        existing_metadata.pop("agent_removed_at", None)
        django_user_id = _ensure_django_support_access(email, display_name or email)
        if django_user_id and not existing_metadata.get("legacy_auth_user_id"):
            existing_metadata["legacy_auth_user_id"] = django_user_id
        persist_agent_metadata(int(existing["id"]), existing_metadata)
        preserved_role = sanitize_text(existing.get("role")).lower()
        next_role = preserved_role if preserved_role in {ROLE_ADMIN, ROLE_SUPERADMIN} else ROLE_AGENT
        run_query(
            """
            UPDATE support_accounts
            SET full_name = COALESCE(NULLIF(%s, ''), full_name),
                role = %s,
                is_active = TRUE,
                updated_at = NOW()
            WHERE id = %s AND account_scope = %s
            """,
            [display_name, next_role, int(existing["id"]), ACCOUNT_SCOPE_STAFF],
        )
        updated = run_query_one(
            "SELECT id, username, full_name, email, account_scope, role, is_active, metadata FROM support_accounts WHERE id = %s LIMIT 1",
            [int(existing["id"])],
        )
        return {"agent": serialize_agent(updated, open_assigned_chat_agent_ids=get_open_assigned_live_chat_agent_ids())}

    if not username:
        username = email.split("@")[0].lower()

    username_taken = run_query_one(
        "SELECT id FROM support_accounts WHERE username = %s LIMIT 1",
        [username],
    )
    if username_taken:
        username = f"{username}.{entra_id[:6].lower()}"

    full_name = display_name or email
    django_user_id = _ensure_django_support_access(email, full_name)

    new_account = run_query_one(
        """
        INSERT INTO support_accounts (username, full_name, email, account_scope, role, is_active, metadata)
        VALUES (%s, %s, %s, %s, %s, TRUE, %s::jsonb)
        RETURNING id, username, full_name, email, account_scope, role, is_active, metadata
        """,
        [
            username,
            full_name,
            email,
            ACCOUNT_SCOPE_STAFF,
            ROLE_AGENT,
            json.dumps({
                "entra_object_id": entra_id,
                "entra_user_principal_name": sanitize_text(payload.get("email") or ""),
                "entra_directory_admin_access": False,
                "legacy_support_access": True,
                **({"legacy_auth_user_id": django_user_id} if django_user_id else {}),
            }),
        ],
    )
    if not new_account:
        raise ApiError(500, "We could not add this agent right now.")

    return {"agent": serialize_agent(new_account, open_assigned_chat_agent_ids=get_open_assigned_live_chat_agent_ids())}


def _remove_django_support_access(email: str) -> None:
    """Remove user from KBC auth database Support Access group (does not delete the user)."""
    kbc_conn = _get_kbc_auth_db_connection()
    try:
        cursor_ctx = kbc_conn.cursor() if kbc_conn else connection.cursor()
        with cursor_ctx as cursor:
            cursor.execute(
                "SELECT id FROM auth_user WHERE LOWER(TRIM(email)) = %s LIMIT 1",
                [email],
            )
            row = cursor.fetchone()
            if not row:
                return
            django_user_id = row[0]
            cursor.execute(
                "SELECT id FROM auth_group WHERE LOWER(TRIM(name)) = %s LIMIT 1",
                [SUPPORT_ACCESS_GROUP_NAME],
            )
            group_row = cursor.fetchone()
            if not group_row:
                return
            cursor.execute(
                "DELETE FROM auth_user_groups WHERE user_id = %s AND group_id = %s",
                [django_user_id, group_row[0]],
            )
            if kbc_conn:
                kbc_conn.commit()
    except Exception as exc:
        log_unexpected_api_error("Failed to remove Django support access group membership.", exc)
    finally:
        if kbc_conn:
            kbc_conn.close()


def remove_agent(account_id: int) -> None:
    agent = run_query_one(
        "SELECT id, email, metadata FROM support_accounts WHERE id = %s AND account_scope = %s LIMIT 1",
        [account_id, ACCOUNT_SCOPE_STAFF],
    )
    if not agent:
        raise ApiError(404, "Agent not found.")

    metadata = normalize_json_object(agent.get("metadata"))
    email = normalize_email(agent.get("email") or "")
    metadata["legacy_support_access"] = False
    metadata["session_active"] = False
    metadata["console_status"] = DEFAULT_AGENT_CONSOLE_STATUS
    metadata["agent_removed_at"] = datetime.now(timezone.utc).isoformat()
    metadata.pop("manually_added_agent", None)
    run_query(
        """
        UPDATE support_accounts
        SET metadata = %s::jsonb,
            updated_at = NOW()
        WHERE id = %s AND account_scope = %s
        """,
        [json.dumps(metadata), account_id, ACCOUNT_SCOPE_STAFF],
    )
    if email:
        _remove_django_support_access(email)


def _sync_tickets_background() -> None:
    global _ticket_background_sync_in_progress

    try:
        sync_open_ticket_inactivity()
        tickets = run_query(
            """
            SELECT
              t.id,
              t.public_id,
              t.inquiry,
              t.technical_subcategory,
              t.status,
              t.status_reason,
              t.sla_status,
              t.metadata,
              t.created_at,
              t.updated_at,
              t.conversation_id,
              t.assigned_agent_id,
              t.assigned_team,
              c.status AS conversation_status,
              c.metadata AS conversation_metadata,
              a.username AS assigned_agent_username,
              a.full_name AS assigned_agent_name
            FROM tickets t
            LEFT JOIN conversations c
              ON c.id = t.conversation_id
            LEFT JOIN support_accounts a
              ON a.id = t.assigned_agent_id
            WHERE t.is_archived = FALSE
            """
        )
        try:
            synced_tickets = synchronize_coverage_tutor_workflow_tickets(tickets)
        except Exception:
            synced_tickets = []
            for ticket in tickets:
                try:
                    synced_tickets.append(synchronize_coverage_tutor_workflow_ticket(ticket))
                except Exception:
                    synced_tickets.append(ticket)

        for ticket in synced_tickets:
            try:
                apply_ticket_sla_policy(ticket, persist=True)
            except Exception:
                pass
    except Exception:
        pass
    finally:
        with _ticket_background_sync_lock:
            _ticket_background_sync_in_progress = False


def trigger_ticket_background_sync() -> None:
    global _ticket_background_sync_in_progress, _last_ticket_background_sync_started_monotonic

    min_interval_seconds = get_ticket_background_sync_min_interval_seconds()
    comparison_now = time.monotonic()
    with _ticket_background_sync_lock:
        if _ticket_background_sync_in_progress:
            return
        if (
            min_interval_seconds > 0
            and _last_ticket_background_sync_started_monotonic
            and (comparison_now - _last_ticket_background_sync_started_monotonic) < min_interval_seconds
        ):
            return
        _ticket_background_sync_in_progress = True
        _last_ticket_background_sync_started_monotonic = comparison_now

    threading.Thread(target=_sync_tickets_background, daemon=True).start()


def list_admin_tickets(actor: dict[str, Any] | None = None) -> dict[str, Any]:
    trigger_ticket_background_sync()

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
          t.is_archived,
          t.archived_at,
          t.archived_by_id,
          t.created_at,
          t.updated_at,
          t.conversation_id,
          c.status AS conversation_status,
          c.metadata AS conversation_metadata,
          c.chat_duration_minutes,
          c.last_message_at,
          latest_session_request.status AS latest_session_request_status,
          latest_session_request.metadata AS latest_session_request_metadata,
          l.full_name AS learner_name,
          l.email AS learner_email,
          l.phone AS learner_phone,
          a.id AS assigned_agent_id,
          a.username AS assigned_agent_username,
          a.full_name AS assigned_agent_name,
          archived_by.username AS archived_by_username,
          archived_by.full_name AS archived_by_name
        FROM tickets t
        JOIN learners l
          ON l.id = t.learner_id
        LEFT JOIN conversations c
          ON c.id = t.conversation_id
        LEFT JOIN LATERAL (
          SELECT ssr.status, ssr.metadata
          FROM support_session_requests ssr
          WHERE ssr.ticket_id = t.id
          ORDER BY ssr.created_at DESC, ssr.id DESC
          LIMIT 1
        ) latest_session_request ON TRUE
        LEFT JOIN support_accounts a
          ON a.id = t.assigned_agent_id
        LEFT JOIN support_accounts archived_by
          ON archived_by.id = t.archived_by_id
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

    tickets = [ticket for ticket in tickets if not is_admin_hidden_support_flow_ticket_record(ticket)]
    tickets = filter_admin_tickets_for_actor(tickets, actor)
    tickets = [apply_ticket_sla_policy(ticket) for ticket in tickets]
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


def do_coverage_tutor_response_payloads_match(left: Any, right: Any) -> bool:
    left_payload = normalize_latest_coverage_tutor_response(left)
    right_payload = normalize_latest_coverage_tutor_response(right)
    if not left_payload or not right_payload:
        return False

    return (
        sanitize_text(left_payload["outcome"]) == sanitize_text(right_payload["outcome"])
        and int(left_payload["toAgentId"]) == int(right_payload["toAgentId"])
        and sanitize_text(left_payload["ticketId"]) == sanitize_text(right_payload["ticketId"])
        and sanitize_text(left_payload["cardId"]) == sanitize_text(right_payload["cardId"])
        and sanitize_text(left_payload["relatedTutorChoiceCardId"]) == sanitize_text(right_payload["relatedTutorChoiceCardId"])
        and sanitize_text(left_payload["respondedAt"]) == sanitize_text(right_payload["respondedAt"])
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

    if normalized_event_type == "coverage_tutor_response":
        latest_coverage_tutor_response = get_latest_coverage_tutor_response(normalized_ticket_metadata)
        return bool(
            latest_coverage_tutor_response
            and not normalize_bool(latest_coverage_tutor_response.get("requesterAcknowledged"))
            and do_coverage_tutor_response_payloads_match(payload, latest_coverage_tutor_response)
        )

    return False


def serialize_admin_notification_log_item(row: dict[str, Any]) -> dict[str, Any]:
    ticket_metadata = normalize_json_object(row.get("metadata"))
    conversation_metadata = normalize_json_object(row.get("conversation_metadata"))
    requester_name = row.get("learner_name") or ""
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
        "learnerName": requester_name,
        "requesterName": requester_name,
        "email": row.get("learner_email") or "",
        "requesterRole": get_ticket_requester_role(ticket_metadata),
        "status": row["status"],
        "statusReason": row.get("status_reason") or "",
        "isCurrent": is_current_admin_notification_history_item(row.get("event_type"), normalized_payload, ticket_metadata),
    }


def list_admin_notifications(actor_username: Any, instance_id: Any, *, limit: Any = 25) -> dict[str, Any]:
    actor = require_agent_session_actor(actor_username, instance_id, allowed_roles=SUPPORT_PORTAL_ACCESS_ROLES)
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
          t.technical_subcategory,
          t.assigned_team,
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
          OR (h.event_type = 'coverage_tutor_response' AND COALESCE(h.payload ->> 'toAgentId', '') = %s)
        ORDER BY h.created_at DESC, h.id DESC
        LIMIT %s
        """,
        [actor_id, actor_id, actor_id, actor_id, actor_id, actor_id, actor_id, resolved_limit],
    )
    notifications = filter_admin_tickets_for_actor(notifications, actor)

    return {"notifications": [serialize_admin_notification_log_item(row) for row in notifications]}


def get_admin_ticket_detail_response(public_id: str, actor: dict[str, Any] | None = None) -> dict[str, Any]:
    if not public_id:
        raise ApiError(400, "Ticket id is required.")

    if actor is not None:
        ticket_scope = fetch_ticket_scope_record(public_id)
        if not ticket_scope:
            raise ApiError(404, "Ticket not found.")
        require_actor_can_access_admin_ticket(actor, ticket_scope)

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
        if not is_coach_requester_role(requester_role):
            raise ApiError(403, "Only coach accounts can request a direct Microsoft Teams support call from the support portal.")

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
        next_assigned_team = derive_assigned_team_for_ticket_assignment(ticket.get("assigned_team"), target_agent)
        ticket_metadata, ticket_state_columns = build_ticket_state_persistence(
            ticket_metadata,
            {
                **ticket,
                "assigned_agent_id": target_agent["id"],
                "assigned_team": next_assigned_team,
            },
        )

        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE tickets
                SET assigned_agent_id = %s,
                    assigned_team = %s,
                    metadata = %s::jsonb,
                    ticket_type = %s,
                    workflow_stage = %s,
                    queue_scope = %s,
                    dashboard_bucket = %s,
                    can_show_conversation = %s,
                    can_receive_chat = %s,
                    resolution_reason = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                [
                    target_agent["id"],
                    next_assigned_team,
                    json.dumps(ticket_metadata),
                    *get_ticket_state_column_params(ticket_state_columns),
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
    ticket_metadata, ticket_state_columns = build_ticket_state_persistence(
        ticket_metadata,
        {
            **ticket,
            "assigned_agent_id": next_assigned_agent_id,
            "assigned_team": next_assigned_team,
        },
    )

    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE tickets
            SET assigned_agent_id = %s,
                assigned_team = %s,
                metadata = %s::jsonb,
                ticket_type = %s,
                workflow_stage = %s,
                queue_scope = %s,
                dashboard_bucket = %s,
                can_show_conversation = %s,
                can_receive_chat = %s,
                resolution_reason = %s,
                updated_at = NOW()
            WHERE id = %s
            """,
            [
                next_assigned_agent_id,
                next_assigned_team,
                json.dumps(ticket_metadata),
                *get_ticket_state_column_params(ticket_state_columns),
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
            SELECT id, username, full_name, email, account_scope, role, is_active, metadata
            FROM support_accounts
            WHERE id = %s
              AND is_active = TRUE
              AND account_scope = %s
            LIMIT 1
            """,
            [target_agent_id, ACCOUNT_SCOPE_STAFF],
        )

        if not target_agent:
            raise ApiError(400, "The selected admin does not exist.")
        if not account_can_receive_ticket_assignment(target_agent, ticket):
            raise ApiError(400, get_ticket_assignment_receiver_error(ticket))
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
            SELECT id, username, full_name, email, account_scope, role, is_active, metadata
            FROM support_accounts
            WHERE id = %s
              AND is_active = TRUE
              AND account_scope = %s
            LIMIT 1
            """,
            [pending_transfer_request["toAgentId"], ACCOUNT_SCOPE_STAFF],
        )

        if not target_agent:
            raise ApiError(409, "The requested admin is no longer available.")
        if not account_can_receive_ticket_assignment(target_agent, ticket):
            raise ApiError(409, "The requested admin no longer receives this ticket type.")

        actor = {
            "id": actor_row["id"],
            "role": actor_row["role"],
            "label": actor_row.get("full_name") or actor_row["username"],
        }
        next_assigned_team = derive_assigned_team_for_ticket_assignment(ticket.get("assigned_team"), target_agent)
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
        ticket_metadata, ticket_state_columns = build_ticket_state_persistence(
            ticket_metadata,
            {
                **ticket,
                "assigned_agent_id": target_agent["id"],
                "assigned_team": next_assigned_team,
            },
        )

        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE tickets
                SET assigned_agent_id = %s,
                    assigned_team = %s,
                    metadata = %s::jsonb,
                    ticket_type = %s,
                    workflow_stage = %s,
                    queue_scope = %s,
                    dashboard_bucket = %s,
                    can_show_conversation = %s,
                    can_receive_chat = %s,
                    resolution_reason = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                [
                    target_agent["id"],
                    next_assigned_team,
                    json.dumps(ticket_metadata),
                    *get_ticket_state_column_params(ticket_state_columns),
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
                                "assigned_agent_id": int(target_agent["id"]),
                                "assigned_team": next_assigned_team,
                            }
                        ),
                        ticket["conversation_id"],
                    ],
                )

        target_agent_metadata = normalize_json_object(target_agent.get("metadata"))
        target_agent_metadata["console_status"] = "Available"
        persist_agent_metadata(int(target_agent["id"]), target_agent_metadata)

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
              t.status_reason,
              t.updated_at,
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


def submit_coverage_tutor_request(
    public_id: str,
    payload: dict[str, Any],
    *,
    uploaded_files: list[Any] | None = None,
) -> dict[str, Any]:
    actor_username = sanitize_text(payload.get("actorUsername")).lower()
    card_id = sanitize_text(payload.get("cardId"))
    callback_origin = sanitize_text(payload.get("origin")).rstrip("/")
    requested_documentation = payload.get("documentation")
    requested_card_payload = payload.get("card") if isinstance(payload.get("card"), dict) else None
    raw_request_files = payload.get("presentationFiles") if isinstance(payload.get("presentationFiles"), list) else []
    uploaded_request_files = list(uploaded_files or [])
    webhook_delivery: dict[str, Any] | None = None
    stored_attachment_keys: list[str] = []

    if not public_id:
        raise ApiError(400, "Ticket id is required.")
    if not actor_username:
        raise ApiError(403, "Admin sign-in is required.")
    if not card_id:
        raise ApiError(400, "Coverage card id is required.")

    actor_row = fetch_actor_by_username(actor_username)
    if not actor_row:
        raise ApiError(403, "Admin sign-in is required.")

    if requested_card_payload is not None and raw_request_files:
        requested_card_files = (
            requested_card_payload.get("presentationFiles")
            if isinstance(requested_card_payload.get("presentationFiles"), list)
            else []
        )
        requested_card_payload = {
            **requested_card_payload,
            "presentationFiles": [*requested_card_files, *raw_request_files],
        }

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
              t.status_reason,
              t.assigned_team,
              t.assigned_agent_id,
              t.sla_status,
              t.metadata,
              t.is_archived,
              t.created_at,
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
        if not is_coverage_ticket_record(ticket):
            raise ApiError(409, "This ticket is not a coverage ticket.")
        if normalize_bool(ticket.get("is_archived")):
            raise ApiError(409, "Restore this ticket before editing it.")

        ticket_metadata = normalize_json_object(ticket.get("metadata"))
        existing_documentation = normalize_admin_documentation(
            ticket_metadata.get("admin_documentation"),
            fallback_inquiry=sanitize_text(ticket.get("inquiry")),
            fallback_ticket_id=ticket["public_id"],
        )
        if requested_documentation is not None:
            documentation = freeze_coverage_documentation_snapshot(
                existing_documentation,
                normalize_admin_documentation(
                    requested_documentation,
                    fallback_inquiry=sanitize_text(ticket.get("inquiry")),
                    fallback_ticket_id=ticket["public_id"],
                ),
            )
        else:
            documentation = existing_documentation
        coverage_cards = list(documentation.get("coverageCards") or [])
        if requested_card_payload is not None:
            normalized_requested_cards = normalize_coverage_cards([requested_card_payload])
            if normalized_requested_cards and sanitize_text(normalized_requested_cards[0].get("id")) == card_id:
                requested_card = normalized_requested_cards[0]
                requested_card_index = find_coverage_card_index(coverage_cards, card_id=card_id)
                if requested_card_index is None:
                    coverage_cards.append(requested_card)
                else:
                    existing_card = normalize_json_object(coverage_cards[requested_card_index])
                    existing_request_status = sanitize_text(existing_card.get("requestStatus"))
                    existing_is_submitted = normalize_bool(existing_card.get("locked")) and existing_request_status in {
                        "requested",
                        "accepted",
                        "refused",
                    }
                    if not existing_is_submitted:
                        coverage_cards[requested_card_index] = {
                            **existing_card,
                            **requested_card,
                            "createdAt": sanitize_text(existing_card.get("createdAt"))
                            or sanitize_text(requested_card.get("createdAt")),
                        }
                documentation["coverageCards"] = coverage_cards
        documentation = stamp_coverage_documentation_card_actors(documentation, existing_documentation, actor_row)
        coverage_cards = list(documentation.get("coverageCards") or [])
        card_index = find_coverage_card_index(coverage_cards, card_id=card_id)
        if card_index is None:
            raise ApiError(404, "Coverage card not found.")

        target_card = normalize_json_object(coverage_cards[card_index])
        if sanitize_text(target_card.get("type")) != "tutor_choice":
            raise ApiError(409, "Only tutor choice cards can be submitted.")
        if normalize_bool(target_card.get("locked")) and sanitize_text(target_card.get("requestStatus")) in {"requested", "accepted", "refused"}:
            raise ApiError(409, "This tutor request has already been submitted.")

        tutor = sanitize_text(target_card.get("tutor"))
        tutor_email = normalize_email(target_card.get("tutorEmail"))
        coach = sanitize_text(target_card.get("coach"))
        coach_email = normalize_email(target_card.get("coachEmail")) if coach else ""
        session_details = sanitize_text(target_card.get("sessionDetails"))
        if not tutor:
            raise ApiError(400, "Choose a tutor or coach before submitting the request.")
        if (not tutor_email or not is_valid_email(tutor_email)) and tutor:
            tutor_email = get_coverage_tutor_email(tutor)
        if (not tutor_email or not is_valid_email(tutor_email)) and tutor:
            tutor_email = get_coverage_coach_email(tutor)
        if not tutor_email or not is_valid_email(tutor_email):
            raise ApiError(400, "Please enter a valid recipient e-mail before submitting the request.")
        if coach and (not coach_email or not is_valid_email(coach_email)):
            coach_email = get_coverage_coach_email(coach)
        if coach and (not coach_email or not is_valid_email(coach_email)):
            raise ApiError(400, "Please enter a valid coach e-mail before submitting the request.")
        if not session_details:
            raise ApiError(400, "Add the session details before submitting the request.")
        ensure_coverage_tutor_request_webhook_configured()

        existing_presentation_files = [
            normalized_attachment
            for attachment in target_card.get("presentationFiles") or []
            if (normalized_attachment := normalize_coverage_card_attachment(attachment))
        ]
        uploaded_presentation_files: list[dict[str, Any]] = []
        if uploaded_request_files:
            try:
                stored_attachment_rows = store_uploaded_ticket_attachments(ticket["public_id"], uploaded_request_files)
                stored_attachment_keys = [
                    attachment.get("storageKey")
                    for attachment in stored_attachment_rows
                    if sanitize_text(attachment.get("storageKey"))
                ]
                uploaded_presentation_files = insert_ticket_attachment_rows(
                    int(ticket["id"]),
                    ticket["public_id"],
                    stored_attachment_rows,
                    metadata_overrides={
                        "source": "coverage_tutor_request",
                        "coverageCardId": card_id,
                    },
                )
            except Exception:
                for storage_key in stored_attachment_keys:
                    delete_support_attachment_file(storage_key)
                raise
        if uploaded_presentation_files:
            target_card = {
                **target_card,
                "presentationFiles": [*existing_presentation_files, *uploaded_presentation_files],
            }

        current_assigned_agent_id = parse_assigned_agent_id(ticket.get("assigned_agent_id"))
        next_assigned_agent_id = current_assigned_agent_id or int(actor_row["id"])
        next_assigned_team = ticket.get("assigned_team") or "Unassigned"
        if current_assigned_agent_id is None:
            next_assigned_team = derive_assigned_team(actor_row)

        timestamp = serialize_datetime_value(datetime.now(timezone.utc)) or datetime.now(timezone.utc).isoformat()
        response_token = uuid4().hex
        request_status_reason = (
            STATUS_REASON_REREQUESTING
            if any(
                sanitize_text(card.get("type")) == "tutor_reply"
                or (
                    sanitize_text(card.get("id")) != card_id
                    and sanitize_text(card.get("type")) == "tutor_choice"
                    and sanitize_text(card.get("submittedAt"))
                )
                for card in coverage_cards
            )
            else STATUS_REASON_TUTOR_REQUESTED
        )

        updated_target_card = {
            **target_card,
            "tutorEmail": tutor_email,
            "coach": coach,
            "coachEmail": coach_email,
            "locked": True,
            "requestStatus": "requested",
            "submittedAt": sanitize_text(target_card.get("submittedAt")) or timestamp,
            "updatedAt": timestamp,
            **(
                {}
                if (
                    parse_assigned_agent_id(target_card.get("createdByAgentId"))
                    or sanitize_text(target_card.get("createdByAgentName"))
                    or sanitize_text(target_card.get("createdByAgentUsername"))
                )
                else build_coverage_card_actor_stamp(actor_row, "created")
            ),
            **build_coverage_card_actor_stamp(actor_row, "updated"),
            "respondedAt": "",
            "responseToken": response_token,
            "requestSubmittedByAgentId": int(actor_row["id"]),
            "requestSubmittedByAgentName": actor_row.get("full_name") or actor_row["username"],
            "requestSubmittedByAgentUsername": actor_row["username"],
        }
        coverage_cards[card_index] = updated_target_card
        documentation["coverageCards"] = coverage_cards

        webhook_delivery = {
            "ticket_id": int(ticket["id"]),
            "ticket_public_id": ticket["public_id"],
            "card_id": updated_target_card["id"],
            "payload": build_coverage_tutor_request_webhook_payload(
                ticket,
                documentation,
                updated_target_card,
                actor_row,
                callback_url=build_coverage_tutor_public_response_base_url(callback_origin),
                result_base_url=build_coverage_tutor_public_result_base_url(callback_origin),
            ),
        }

        next_status = "Pending"
        next_status_reason = request_status_reason
        next_sla_status = "On Track"
        updated_ticket_metadata = build_resolved_coverage_sla_metadata(ticket_metadata)
        updated_ticket_metadata["admin_documentation"] = documentation
        # A fresh tutor request supersedes any prior accepted/refused response.
        updated_ticket_metadata.pop(LATEST_COVERAGE_TUTOR_RESPONSE_METADATA_KEY, None)
        updated_ticket_metadata, ticket_state_columns = build_ticket_state_persistence(
            updated_ticket_metadata,
            {
                **ticket,
                "status": next_status,
                "status_reason": next_status_reason,
                "assigned_agent_id": next_assigned_agent_id,
                "assigned_team": next_assigned_team,
            },
            chat_state=map_conversation_status(next_status),
        )

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
                  ticket_type = %s,
                  workflow_stage = %s,
                  queue_scope = %s,
                  dashboard_bucket = %s,
                  can_show_conversation = %s,
                  can_receive_chat = %s,
                  resolution_reason = %s,
                  updated_at = NOW()
                WHERE id = %s
                """,
                [
                    next_status,
                    next_status_reason,
                    next_assigned_agent_id,
                    next_assigned_team,
                    next_sla_status,
                    json.dumps(updated_ticket_metadata),
                    *get_ticket_state_column_params(ticket_state_columns),
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
                                "status_reason": next_status_reason,
                                "chat_state": map_conversation_status(next_status),
                                "assigned_agent_id": next_assigned_agent_id,
                                "assigned_team": next_assigned_team,
                            }
                        ),
                        ticket["conversation_id"],
                    ],
                )

        actor = {
            "id": actor_row["id"],
            "role": actor_row["role"],
            "label": actor_row.get("full_name") or actor_row["username"],
        }
        if ticket["status"] != next_status:
            insert_history_event(ticket["id"], "status_changed", actor, {"from": ticket["status"], "to": next_status})
        if (ticket.get("status_reason") or "") != next_status_reason:
            insert_history_event(
                ticket["id"],
                "status_reason_changed",
                actor,
                {"from": ticket.get("status_reason") or "", "to": next_status_reason},
            )
        if current_assigned_agent_id != next_assigned_agent_id:
            insert_history_event(
                ticket["id"],
                "assignment_changed",
                actor,
                {
                    "fromAgentId": current_assigned_agent_id,
                    "toAgentId": next_assigned_agent_id,
                    "toAgentName": actor_row.get("full_name") or actor_row["username"],
                },
            )
        insert_history_event(
            ticket["id"],
            "coverage_tutor_requested",
            actor,
            {
                "toAgentId": int(actor_row["id"]),
                "toAgentName": actor_row.get("full_name") or actor_row["username"],
                "toAgentUsername": actor_row["username"],
                "ticketId": ticket["public_id"],
                "cardId": updated_target_card["id"],
                "tutor": tutor,
                "tutorEmail": tutor_email,
                "coach": coach,
                "coachEmail": coach_email,
                "requestedAt": updated_target_card["submittedAt"],
                "sessionDetails": session_details,
            },
        )

    if webhook_delivery:
        queue_coverage_tutor_request_webhook_delivery(**webhook_delivery)

    detail = fetch_admin_ticket_detail(public_id)
    if not detail:
        raise ApiError(404, "Ticket not found.")

    return detail


def send_coverage_tutor_follow_up_files(
    public_id: str,
    payload: dict[str, Any],
    *,
    uploaded_files: list[Any] | None = None,
) -> dict[str, Any]:
    actor_username = sanitize_text(payload.get("actorUsername")).lower()
    card_id = sanitize_text(payload.get("cardId"))
    raw_follow_up_files = payload.get("presentationFiles") if isinstance(payload.get("presentationFiles"), list) else []
    uploaded_follow_up_files = list(uploaded_files or [])
    webhook_delivery: dict[str, Any] | None = None
    stored_attachment_keys: list[str] = []

    if not public_id:
        raise ApiError(400, "Ticket id is required.")
    if not actor_username:
        raise ApiError(403, "Admin sign-in is required.")
    if not card_id:
        raise ApiError(400, "Coverage card id is required.")

    actor_row = fetch_actor_by_username(actor_username)
    if not actor_row:
        raise ApiError(403, "Admin sign-in is required.")

    follow_up_files: list[dict[str, Any]] = []
    for attachment in raw_follow_up_files:
        normalized_attachment = normalize_coverage_card_attachment(attachment)
        if normalized_attachment:
            follow_up_files.append(normalized_attachment)

    if not follow_up_files and not uploaded_follow_up_files:
        raise ApiError(400, "Add at least one presentation file before sending the follow-up.")

    ensure_coverage_tutor_follow_up_webhook_configured()

    try:
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
                  t.status_reason,
                  t.sla_status,
                  t.metadata,
                  t.tutor_emails,
                  t.is_archived,
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
            if not is_coverage_ticket_record(ticket):
                raise ApiError(409, "This ticket is not a coverage ticket.")
            if normalize_bool(ticket.get("is_archived")):
                raise ApiError(409, "Restore this ticket before editing it.")

            ticket_metadata = normalize_json_object(ticket.get("metadata"))
            documentation = normalize_admin_documentation(
                ticket_metadata.get("admin_documentation"),
                fallback_inquiry=sanitize_text(ticket.get("inquiry")),
                fallback_ticket_id=ticket["public_id"],
            )
            coverage_cards = list(documentation.get("coverageCards") or [])
            card_index = find_coverage_card_index(coverage_cards, card_id=card_id)
            if card_index is None:
                raise ApiError(404, "Coverage card not found.")

            target_card = normalize_json_object(coverage_cards[card_index])
            if sanitize_text(target_card.get("type")) != "tutor_choice":
                raise ApiError(409, "Only tutor choice cards can receive follow-up files.")

            request_status = sanitize_text(target_card.get("requestStatus")).lower()
            if request_status == "pending":
                request_status = "requested"
            if request_status not in {"requested", "accepted"}:
                raise ApiError(409, "Follow-up files can only be sent for requested or accepted tutor requests.")

            if uploaded_follow_up_files:
                stored_attachment_rows = store_uploaded_ticket_attachments(ticket["public_id"], uploaded_follow_up_files)
                stored_attachment_keys = [
                    attachment.get("storageKey")
                    for attachment in stored_attachment_rows
                    if sanitize_text(attachment.get("storageKey"))
                ]
                follow_up_files.extend(
                    insert_ticket_attachment_rows(
                        int(ticket["id"]),
                        ticket["public_id"],
                        stored_attachment_rows,
                        metadata_overrides={
                            "source": "coverage_tutor_follow_up",
                            "coverageCardId": card_id,
                        },
                    )
                )

            existing_files = [
                normalized_attachment
                for attachment in target_card.get("presentationFiles") or []
                if (normalized_attachment := normalize_coverage_card_attachment(attachment))
            ]
            existing_file_ids = {
                sanitize_text(existing_file.get("id"))
                for existing_file in existing_files
                if sanitize_text(existing_file.get("id"))
            }
            new_follow_up_files = [
                follow_up_file
                for follow_up_file in follow_up_files
                if sanitize_text(follow_up_file.get("id")) not in existing_file_ids
            ]
            if not new_follow_up_files:
                raise ApiError(400, "Add at least one new presentation file before sending the follow-up.")

            timestamp = serialize_datetime_value(datetime.now(timezone.utc)) or datetime.now(timezone.utc).isoformat()
            updated_target_card = {
                **target_card,
                "presentationFiles": [*existing_files, *new_follow_up_files],
                "updatedAt": timestamp,
                **build_coverage_card_actor_stamp(actor_row, "updated"),
            }
            coverage_cards[card_index] = updated_target_card
            documentation["coverageCards"] = coverage_cards

            updated_ticket_metadata = build_resolved_coverage_sla_metadata(ticket_metadata)
            updated_ticket_metadata["admin_documentation"] = documentation

            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE tickets
                    SET sla_status = %s,
                        metadata = %s::jsonb,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    ["On Track", json.dumps(updated_ticket_metadata), ticket["id"]],
                )

            actor = {
                "id": actor_row["id"],
                "role": actor_row["role"],
                "label": actor_row.get("full_name") or actor_row["username"],
            }
            insert_history_event(
                ticket["id"],
                "coverage_tutor_follow_up_sent",
                actor,
                {
                    "ticketId": ticket["public_id"],
                    "cardId": updated_target_card["id"],
                    "tutor": sanitize_text(updated_target_card.get("tutor")),
                    "tutorEmail": sanitize_text(updated_target_card.get("tutorEmail")),
                    "requestStatus": request_status,
                    "sentAt": timestamp,
                    "fileCount": len(new_follow_up_files),
                    "fileNames": [sanitize_text(file.get("name")) or "attachment" for file in new_follow_up_files],
                },
            )

            webhook_delivery = {
                "ticket_id": int(ticket["id"]),
                "ticket_public_id": ticket["public_id"],
                "card_id": updated_target_card["id"],
                "payload": build_coverage_tutor_follow_up_webhook_payload(
                    ticket,
                    documentation,
                    updated_target_card,
                    new_follow_up_files,
                    actor_row,
                    sent_at=timestamp,
                ),
            }
    except Exception:
        for storage_key in stored_attachment_keys:
            delete_support_attachment_file(storage_key)
        raise

    if webhook_delivery:
        queue_coverage_tutor_follow_up_webhook_delivery(**webhook_delivery)

    detail = fetch_admin_ticket_detail(public_id)
    if not detail:
        raise ApiError(404, "Ticket not found.")

    return detail


def process_coverage_tutor_response(payload: dict[str, Any]) -> dict[str, Any]:
    ticket_public_id = sanitize_text(payload.get("ticketId") or payload.get("publicId"))
    if not ticket_public_id:
        raise ApiError(400, "Ticket id is required.")

    outcome = extract_coverage_tutor_response_outcome(payload)
    if not outcome:
        raise ApiError(400, "Please provide a valid tutor response outcome.")

    requested_card_id = sanitize_text(payload.get("cardId") or payload.get("relatedTutorChoiceCardId"))
    response_token = sanitize_text(payload.get("responseToken"))
    refusal_mail_webhook_ticket_id: int | None = None
    refusal_mail_webhook_payload: dict[str, Any] | None = None

    with transaction.atomic():
        ticket = run_query_one(
            """
            SELECT
              t.id,
              t.public_id,
              t.status,
              t.status_reason,
              t.technical_subcategory,
              t.metadata,
              t.assigned_team,
              t.assigned_agent_id,
              t.sla_status,
              t.created_at,
              t.conversation_id
            FROM tickets t
            WHERE t.public_id = %s
            LIMIT 1
            """,
            [ticket_public_id],
        )

        if not ticket:
            raise ApiError(404, "Ticket not found.")
        if not is_coverage_ticket_record(ticket):
            raise ApiError(409, "This ticket is not a coverage ticket.")

        ticket_metadata = normalize_json_object(ticket.get("metadata"))
        latest_response = get_latest_coverage_tutor_response(ticket_metadata)
        if latest_response and do_coverage_tutor_response_payloads_match(
            latest_response,
            {
                "outcome": outcome,
                "toAgentId": latest_response.get("toAgentId"),
                "ticketId": ticket_public_id,
                "cardId": requested_card_id or latest_response.get("cardId"),
                "relatedTutorChoiceCardId": requested_card_id or latest_response.get("relatedTutorChoiceCardId"),
                "respondedAt": latest_response.get("respondedAt"),
            },
        ):
            return build_already_recorded_coverage_tutor_response_detail(
                ticket_public_id,
                recorded_outcome=latest_response.get("outcome"),
                requested_outcome=outcome,
            )

        documentation = normalize_admin_documentation(
            ticket_metadata.get("admin_documentation"),
            fallback_ticket_id=ticket["public_id"],
        )
        coverage_cards = list(documentation.get("coverageCards") or [])
        card_index = find_coverage_card_index(coverage_cards, card_id=requested_card_id, response_token=response_token)
        if card_index is None:
            raise ApiError(404, "The related tutor request was not found.")

        tutor_choice_card = normalize_json_object(coverage_cards[card_index])
        if sanitize_text(tutor_choice_card.get("type")) != "tutor_choice":
            raise ApiError(409, "The related coverage card is not a tutor choice card.")

        recorded_outcome = get_recorded_coverage_tutor_response_outcome(tutor_choice_card, coverage_cards)
        if recorded_outcome:
            return build_already_recorded_coverage_tutor_response_detail(
                ticket_public_id,
                recorded_outcome=recorded_outcome,
                requested_outcome=outcome,
            )

        responded_at = serialize_datetime_value(
            coerce_datetime(payload.get("respondedAt")) or datetime.now(timezone.utc)
        ) or datetime.now(timezone.utc).isoformat()
        existing_reply_card = next(
            (
                card for card in coverage_cards
                if sanitize_text(card.get("type")) == "tutor_reply"
                and sanitize_text(card.get("relatedTutorChoiceCardId")) == sanitize_text(tutor_choice_card.get("id"))
            ),
            None,
        )
        if existing_reply_card:
            return build_already_recorded_coverage_tutor_response_detail(
                ticket_public_id,
                recorded_outcome=get_recorded_coverage_tutor_response_outcome(tutor_choice_card, coverage_cards),
                requested_outcome=outcome,
            )

        updated_tutor_choice_card = {
            **tutor_choice_card,
            "requestStatus": "accepted" if outcome == "accepted" else "refused",
            "locked": True,
            "respondedAt": responded_at,
            "updatedAt": responded_at,
        }
        coverage_cards[card_index] = updated_tutor_choice_card
        coverage_cards.append(
            build_coverage_tutor_reply_card(
                tutor_choice_card=updated_tutor_choice_card,
                response_payload=payload,
                outcome=outcome,
                responded_at=responded_at,
            )
        )
        documentation["coverageCards"] = coverage_cards

        next_status = "Closed" if outcome == "accepted" else "Pending"
        next_status_reason = STATUS_REASON_TUTOR_ACCEPTED if outcome == "accepted" else STATUS_REASON_TUTOR_REJECTED
        next_sla_status = "On Track"
        updated_ticket_metadata = build_resolved_coverage_sla_metadata(ticket_metadata)
        updated_ticket_metadata["admin_documentation"] = documentation
        latest_response_payload = build_coverage_tutor_response_payload(
            ticket_public_id=ticket_public_id,
            tutor_choice_card=updated_tutor_choice_card,
            response_payload={
                **payload,
                "cardId": requested_card_id or payload.get("cardId") or payload.get("relatedTutorChoiceCardId"),
            },
            outcome=outcome,
            responded_at=responded_at,
        )
        updated_ticket_metadata[LATEST_COVERAGE_TUTOR_RESPONSE_METADATA_KEY] = latest_response_payload
        if outcome == "rejected":
            refusal_mail_webhook_ticket_id = int(ticket["id"])
            refusal_mail_webhook_payload = build_coverage_tutor_refusal_mail_webhook_payload(
                ticket=ticket,
                tutor_choice_card=updated_tutor_choice_card,
                latest_response_payload=latest_response_payload,
                next_status=next_status,
                next_status_reason=next_status_reason,
            )
        updated_ticket_metadata, ticket_state_columns = build_ticket_state_persistence(
            updated_ticket_metadata,
            {
                **ticket,
                "status": next_status,
                "status_reason": next_status_reason,
            },
            chat_state=map_conversation_status(next_status),
        )

        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE tickets
                SET
                  status = %s,
                  status_reason = %s,
                  sla_status = %s,
                  metadata = %s::jsonb,
                  ticket_type = %s,
                  workflow_stage = %s,
                  queue_scope = %s,
                  dashboard_bucket = %s,
                  can_show_conversation = %s,
                  can_receive_chat = %s,
                  resolution_reason = %s,
                  updated_at = NOW(),
                  closed_at = CASE
                    WHEN %s = 'Closed' THEN COALESCE(closed_at, NOW())
                    ELSE closed_at
                  END
                WHERE id = %s
                """,
                [
                    next_status,
                    next_status_reason,
                    next_sla_status,
                    json.dumps(updated_ticket_metadata),
                    *get_ticket_state_column_params(ticket_state_columns),
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
                                "status_reason": next_status_reason,
                                "chat_state": map_conversation_status(next_status),
                                "assigned_agent_id": ticket.get("assigned_agent_id"),
                                "assigned_team": ticket.get("assigned_team"),
                            }
                        ),
                        ticket["conversation_id"],
                    ],
                )

        if ticket.get("conversation_id") and sanitize_text(map_conversation_status(next_status)).lower() == "closed":
            persist_conversation_chat_duration(ticket["id"], ticket["conversation_id"])

        if ticket["status"] != next_status:
            insert_history_event(ticket["id"], "status_changed", None, {"from": ticket["status"], "to": next_status})
        if (ticket.get("status_reason") or "") != next_status_reason:
            insert_history_event(
                ticket["id"],
                "status_reason_changed",
                None,
                {"from": ticket.get("status_reason") or "", "to": next_status_reason},
            )
        insert_history_event(ticket["id"], "coverage_tutor_response", None, latest_response_payload)

    if refusal_mail_webhook_ticket_id and refusal_mail_webhook_payload:
        notify_coverage_tutor_refusal_mail_webhook(refusal_mail_webhook_ticket_id, refusal_mail_webhook_payload)

    detail = fetch_admin_ticket_detail(ticket_public_id)
    if not detail:
        raise ApiError(404, "Ticket not found.")

    return detail


def acknowledge_coverage_tutor_response(public_id: str, payload: dict[str, Any]) -> dict[str, Any]:
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

        ticket_metadata = normalize_json_object(ticket.get("metadata"))
        documentation, latest_coverage_tutor_response = derive_coverage_tutor_response_state(
            ticket_public_id=ticket["public_id"],
            status_reason=ticket.get("status_reason"),
            updated_at=ticket.get("updated_at"),
            documentation=ticket_metadata.get("admin_documentation"),
            metadata=ticket_metadata,
        )
        if not latest_coverage_tutor_response:
            raise ApiError(409, "There is no coverage tutor update to acknowledge.")

        actor_row = fetch_actor_by_username(actor_username)
        if not actor_row or int(actor_row["id"]) != int(latest_coverage_tutor_response["toAgentId"]):
            raise ApiError(403, "Only the requesting admin can acknowledge this tutor update.")

        if latest_coverage_tutor_response.get("requesterAcknowledged"):
            return fetch_admin_ticket_detail(public_id) or {"ticket": {"id": public_id}}

        ticket_metadata["admin_documentation"] = documentation
        ticket_metadata[LATEST_COVERAGE_TUTOR_RESPONSE_METADATA_KEY] = {
            **latest_coverage_tutor_response,
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


def acknowledge_coverage_ticket_notification(public_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    actor_username = sanitize_text(payload.get("actorUsername")).lower()

    if not public_id:
        raise ApiError(400, "Ticket id is required.")
    if not actor_username:
        raise ApiError(403, "Admin sign-in is required.")

    actor_row = fetch_actor_by_username(actor_username)
    if not actor_row:
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

        ticket_metadata = normalize_json_object(ticket.get("metadata"))
        if not get_pending_coverage_ticket_notification(ticket_metadata):
            return fetch_admin_ticket_detail(public_id) or {"ticket": {"id": public_id}}

        ticket_metadata.pop(PENDING_COVERAGE_TICKET_NOTIFICATION_METADATA_KEY, None)

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


def acknowledge_support_queue_notification(public_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    actor_username = sanitize_text(payload.get("actorUsername")).lower()

    if not public_id:
        raise ApiError(400, "Ticket id is required.")
    if not actor_username:
        raise ApiError(403, "Admin sign-in is required.")

    actor_row = fetch_actor_by_username(actor_username)
    if not actor_row:
        raise ApiError(403, "Admin sign-in is required.")

    with transaction.atomic():
        ticket = run_query_one(
            """
            SELECT
              t.id,
              t.public_id,
              t.technical_subcategory,
              t.assigned_team,
              t.metadata
            FROM tickets t
            WHERE t.public_id = %s
            LIMIT 1
            """,
            [public_id],
        )

        if not ticket:
            raise ApiError(404, "Ticket not found.")

        require_actor_can_access_admin_ticket(actor_row, ticket)

        ticket_metadata = normalize_json_object(ticket.get("metadata"))
        if not get_pending_support_queue_notification(ticket_metadata):
            return fetch_admin_ticket_detail(public_id) or {"ticket": {"id": public_id}}

        ticket_metadata.pop(PENDING_SUPPORT_QUEUE_NOTIFICATION_METADATA_KEY, None)

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


def acknowledge_learning_plan_transfer_notification(public_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    actor_username = sanitize_text(payload.get("actorUsername")).lower()

    if not public_id:
        raise ApiError(400, "Ticket id is required.")
    if not actor_username:
        raise ApiError(403, "Admin sign-in is required.")

    actor_row = fetch_actor_by_username(actor_username)
    if not actor_row:
        raise ApiError(403, "Admin sign-in is required.")

    with transaction.atomic():
        ticket = run_query_one(
            """
            SELECT
              t.id,
              t.public_id,
              t.technical_subcategory,
              t.assigned_team,
              t.metadata
            FROM tickets t
            WHERE t.public_id = %s
            LIMIT 1
            """,
            [public_id],
        )

        if not ticket:
            raise ApiError(404, "Ticket not found.")

        require_actor_can_access_admin_ticket(actor_row, ticket)

        ticket_metadata = normalize_json_object(ticket.get("metadata"))
        if not get_pending_learning_plan_transfer_notification(ticket_metadata):
            return fetch_admin_ticket_detail(public_id) or {"ticket": {"id": public_id}}

        ticket_metadata.pop(PENDING_LEARNING_PLAN_TRANSFER_NOTIFICATION_METADATA_KEY, None)

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


def confirm_coverage_tutor_session(public_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    actor_username = sanitize_text(payload.get("actorUsername")).lower()
    card_id = sanitize_text(payload.get("cardId"))

    if not public_id:
        raise ApiError(400, "Ticket id is required.")
    if not actor_username:
        raise ApiError(403, "Admin sign-in is required.")
    if not card_id:
        raise ApiError(400, "Coverage card id is required.")

    actor_row = fetch_actor_by_username(actor_username)
    if not actor_row:
        raise ApiError(403, "Admin sign-in is required.")

    with transaction.atomic():
        ticket = run_query_one(
            """
            SELECT
              t.id,
              t.public_id,
              t.status,
              t.status_reason,
              t.technical_subcategory,
              t.metadata,
              t.assigned_team,
              t.assigned_agent_id,
              t.sla_status,
              t.is_archived,
              t.created_at,
              t.updated_at,
              t.conversation_id
            FROM tickets t
            WHERE t.public_id = %s
            LIMIT 1
            """,
            [public_id],
        )

        if not ticket:
            raise ApiError(404, "Ticket not found.")
        if not is_coverage_ticket_record(ticket):
            raise ApiError(409, "This ticket is not a coverage ticket.")
        if normalize_bool(ticket.get("is_archived")):
            raise ApiError(409, "Restore this ticket before editing it.")

        ticket_metadata = normalize_json_object(ticket.get("metadata"))
        documentation, _ = derive_coverage_tutor_response_state(
            ticket_public_id=ticket["public_id"],
            status_reason=ticket.get("status_reason"),
            updated_at=ticket.get("updated_at"),
            documentation=ticket_metadata.get("admin_documentation"),
            metadata=ticket_metadata,
        )
        coverage_cards = list(documentation.get("coverageCards") or [])
        card_index = find_coverage_card_index(coverage_cards, card_id=card_id)
        if card_index is None:
            raise ApiError(404, "Coverage card not found.")

        target_card = normalize_json_object(coverage_cards[card_index])
        if not is_coverage_session_confirmation_available(target_card):
            raise ApiError(409, "This session cannot be confirmed yet.")

        confirmed_at = serialize_datetime_value(datetime.now(timezone.utc)) or datetime.now(timezone.utc).isoformat()
        updated_cards: list[dict[str, Any]] = []
        for card in coverage_cards:
            updated_card = {
                **card,
                "locked": True,
                "updatedAt": confirmed_at,
                **build_coverage_card_actor_stamp(actor_row, "updated"),
            }
            if sanitize_text(card.get("id")) == card_id:
                updated_card.update(
                    {
                        "confirmedAt": confirmed_at,
                        "confirmedByAgentId": int(actor_row["id"]),
                        "confirmedByAgentName": actor_row.get("full_name") or actor_row["username"],
                        "confirmedByAgentUsername": actor_row["username"],
                    }
                )
            updated_cards.append(updated_card)
        documentation["coverageCards"] = updated_cards

        next_status = "Closed"
        next_status_reason = STATUS_REASON_CLOSED_BY_AGENT
        next_sla_status = "On Track"
        updated_ticket_metadata = build_resolved_coverage_sla_metadata(ticket_metadata)
        updated_ticket_metadata["admin_documentation"] = documentation
        updated_ticket_metadata, ticket_state_columns = build_ticket_state_persistence(
            updated_ticket_metadata,
            {
                **ticket,
                "status": next_status,
                "status_reason": next_status_reason,
            },
            chat_state=map_conversation_status(next_status),
        )

        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE tickets
                SET
                  status = %s,
                  status_reason = %s,
                  sla_status = %s,
                  metadata = %s::jsonb,
                  ticket_type = %s,
                  workflow_stage = %s,
                  queue_scope = %s,
                  dashboard_bucket = %s,
                  can_show_conversation = %s,
                  can_receive_chat = %s,
                  resolution_reason = %s,
                  updated_at = NOW(),
                  closed_at = NOW()
                WHERE id = %s
                """,
                [
                    next_status,
                    next_status_reason,
                    next_sla_status,
                    json.dumps(updated_ticket_metadata),
                    *get_ticket_state_column_params(ticket_state_columns),
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
                                "status_reason": next_status_reason,
                                "chat_state": map_conversation_status(next_status),
                                "assigned_agent_id": ticket.get("assigned_agent_id"),
                                "assigned_team": ticket.get("assigned_team"),
                            }
                        ),
                        ticket["conversation_id"],
                    ],
                )

        actor = {
            "id": actor_row["id"],
            "role": actor_row["role"],
            "label": actor_row.get("full_name") or actor_row["username"],
        }
        if ticket["status"] != next_status:
            insert_history_event(ticket["id"], "status_changed", actor, {"from": ticket["status"], "to": next_status})
        if (ticket.get("status_reason") or "") != next_status_reason:
            insert_history_event(
                ticket["id"],
                "status_reason_changed",
                actor,
                {"from": ticket.get("status_reason") or "", "to": next_status_reason},
            )
        insert_history_event(
            ticket["id"],
            "coverage_session_confirmed",
            actor,
            {
                "ticketId": ticket["public_id"],
                "cardId": card_id,
                "tutor": sanitize_text(target_card.get("tutor")),
                "confirmedAt": confirmed_at,
                "confirmedById": int(actor_row["id"]),
                "confirmedByName": actor_row.get("full_name") or actor_row["username"],
                "confirmedByUsername": actor_row["username"],
            },
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
    follow_up_ticket_metadata, ticket_state_columns = build_ticket_state_persistence(
        {
            "source": "support_portal_follow_up",
            "parent_ticket_public_id": ticket["public_id"],
            "chat_public_id": chat_public_id,
            "technical_subcategory": ticket.get("technical_subcategory") or None,
            "requester_role": requester_role,
            "requester_account_id": requester_account_id,
            "requester_username": requester_username,
        },
        {
            **ticket,
            "status": "Open",
            "status_reason": "",
            "assigned_team": ticket.get("assigned_team") or "Unassigned",
        },
        chat_state="open",
    )

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
              metadata,
              ticket_type,
              workflow_stage,
              queue_scope,
              dashboard_bucket,
              can_show_conversation,
              can_receive_chat,
              resolution_reason
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s)
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
                json.dumps(follow_up_ticket_metadata),
                *get_ticket_state_column_params(ticket_state_columns),
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


def set_ticket_booking_progress(public_id: str, *, active: bool) -> dict[str, Any]:
    if not public_id:
        raise ApiError(400, "Ticket id is required.")

    ticket = run_query_one(
        """
        SELECT id, public_id, status, status_reason, technical_subcategory, assigned_team, metadata
        FROM tickets
        WHERE public_id = %s
        LIMIT 1
        """,
        [public_id],
    )

    if not ticket:
        raise ApiError(404, "Ticket not found.")

    metadata_patch = {
        **normalize_json_object(ticket.get("metadata")),
        SUPPORT_FLOW_STAGE_METADATA_KEY: SUPPORT_FLOW_STAGE_BOOKING_IN_PROGRESS if active else None,
        "booking_started_at": serialize_datetime_value(datetime.now(timezone.utc)) if active else None,
    }
    metadata_patch, ticket_state_columns = build_ticket_state_persistence(metadata_patch, ticket)

    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE tickets
            SET metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb,
                ticket_type = %s,
                workflow_stage = %s,
                queue_scope = %s,
                dashboard_bucket = %s,
                can_show_conversation = %s,
                can_receive_chat = %s,
                resolution_reason = %s,
                updated_at = NOW()
            WHERE id = %s
            """,
            [
                json.dumps(metadata_patch),
                *get_ticket_state_column_params(ticket_state_columns),
                ticket["id"],
            ],
        )

    return {
        "ok": True,
        "ticket": {
            "id": ticket["public_id"],
            "bookingInProgress": bool(active),
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
        "chatHistory": serialize_chat_timeline_rows(ticket["public_id"], messages, history_rows),
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
              t.category,
              t.technical_subcategory,
              t.priority,
              t.metadata,
              t.created_at,
              t.assigned_team,
              t.conversation_id,
              t.assigned_agent_id,
              c.status AS conversation_status,
              l.full_name AS learner_name,
              l.email AS learner_email,
              l.source AS learner_source,
              l.metadata AS learner_metadata
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
        if is_chat_locked_for_learner(ticket.get("status"), ticket.get("status_reason")):
            raise ApiError(409, "Chat is unavailable while a support meeting is active. Cancel the meeting to continue in chat.")
        if is_ticket_chat_closed(ticket.get("status"), ticket.get("conversation_status")):
            raise ApiError(409, "This chat has been closed by support. Start a new chat to continue.")

        mark_conversation_as_active(ticket["public_id"], ticket.get("conversation_id"))
        chat_public_id = build_public_chat_id(ticket.get("public_id"), ticket.get("conversation_id"))
        ticket_metadata_patch, ticket_state_columns = build_ticket_state_persistence(
            {
                **normalize_json_object(ticket.get("metadata")),
                "live_chat_requested": True,
                "live_chat_requested_at": request_time.isoformat(),
            },
            ticket,
            chat_state="open",
        )

        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE tickets
                SET
                  metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb,
                  ticket_type = %s,
                  workflow_stage = %s,
                  queue_scope = %s,
                  dashboard_bucket = %s,
                  can_show_conversation = %s,
                  can_receive_chat = %s,
                  resolution_reason = %s,
                  updated_at = NOW()
                WHERE id = %s
                """,
                [
                    json.dumps(ticket_metadata_patch),
                    *get_ticket_state_column_params(ticket_state_columns),
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
        refreshed_assigned_agent_id = refreshed_ticket.get("assigned_agent_id") if refreshed_ticket else None
        notification_ticket = {
            **ticket,
            "assigned_agent_id": refreshed_assigned_agent_id,
            "assigned_agent_name": refreshed_ticket.get("assigned_agent_name") if refreshed_ticket else None,
            "assigned_agent_username": refreshed_ticket.get("assigned_agent_username") if refreshed_ticket else None,
        }
        should_queue_live_agent_unavailable_notification = should_notify_live_agent_unavailable(
            notification_ticket,
            assigned_agent_id=refreshed_assigned_agent_id,
        )

    if should_queue_live_agent_unavailable_notification:
        queue_live_agent_unavailable_notification(notification_ticket, requested_at=request_time)

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


def update_admin_ticket(public_id: str, payload: dict[str, Any], *, uploaded_files: list[Any] | None = None) -> dict[str, Any]:
    requested_status = sanitize_text(payload.get("status")) if "status" in payload else None
    requested_status_reason = sanitize_text(payload.get("statusReason")) if "statusReason" in payload else None
    requested_chat_state = sanitize_text(payload.get("chatState")).lower() if "chatState" in payload else None
    requested_sla_status = sanitize_text(payload.get("slaStatus")) if "slaStatus" in payload else None
    requested_assigned_team = sanitize_text(payload.get("assignedTeam")) if "assignedTeam" in payload else None
    requested_documentation = payload.get("documentation") if isinstance(payload.get("documentation"), dict) else None
    uploaded_documentation_files = list(uploaded_files or [])
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

    if uploaded_documentation_files and requested_documentation is None:
        raise ApiError(400, "Documentation payload is required when uploading documentation attachments.")

    parsed_assigned_agent_id = parse_assigned_agent_id(payload.get("assignedAgentId")) if has_assigned_agent_input else None
    parsed_escalation_agent_id = parse_assigned_agent_id(payload.get("escalationAgentId")) if has_escalation_agent_input else None
    learning_plan_transfer_webhook_ticket_id: int | None = None
    learning_plan_transfer_webhook_payload: dict[str, Any] | None = None
    learning_plan_transfer_notification_payload: dict[str, Any] | None = None
    documentation_history_events: list[tuple[str, dict[str, Any]]] = []

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
              t.is_archived,
              t.created_at,
              t.closed_at,
              t.conversation_id,
              l.full_name AS learner_name,
              l.email AS learner_email,
              l.source AS learner_source,
              l.metadata AS learner_metadata,
              c.metadata AS conversation_metadata,
              a.username AS assigned_agent_username,
              a.full_name AS assigned_agent_name
            FROM tickets t
            JOIN learners l
              ON l.id = t.learner_id
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

        if normalize_bool(ticket.get("is_archived")):
            raise ApiError(409, "Restore this ticket before editing it.")

        apply_ticket_sla_policy(ticket)

        actor_row = fetch_actor_by_username(actor_username) if actor_username else None
        require_actor_can_access_admin_ticket(actor_row, ticket)
        actor = (
            {
                "id": actor_row["id"],
                "role": actor_row["role"],
                "label": actor_row.get("full_name") or actor_row["username"],
            }
            if actor_row
            else None
        )

        if (
            requested_status_reason is not None
            and is_coverage_ticket_record(ticket)
            and is_coverage_tutor_status_reason(requested_status_reason)
        ):
            raise ApiError(
                409,
                "Coverage tutor status reasons are managed by the tutor workflow only.",
            )

        if requested_status is not None and requested_status != ticket["status"] and not note:
            raise ApiError(400, "Add an internal note before changing the ticket status.")

        current_assigned_agent_id = int(ticket["assigned_agent_id"]) if ticket.get("assigned_agent_id") else None
        current_assigned_team = get_effective_assigned_team(ticket.get("assigned_team"))
        requested_assignment_changed = has_assigned_agent_input and current_assigned_agent_id != parsed_assigned_agent_id
        requested_team_changed = False
        normalized_requested_assigned_team = None
        actor_role = sanitize_text(actor_row.get("role") if actor_row else "").lower()

        if requested_assignment_changed:
            if actor_role not in ADMIN_ACCESS_ROLES:
                raise ApiError(403, "Only admins and superadmins can assign tickets.")

        if requested_assigned_team is not None:
            normalized_requested_assigned_team = normalize_assigned_team(requested_assigned_team)
            requested_team_changed = normalized_requested_assigned_team != current_assigned_team
            if requested_team_changed and not actor_can_transfer_ticket_between_teams(
                actor_row,
                ticket,
                normalized_requested_assigned_team,
            ):
                raise ApiError(403, "You do not have permission to transfer this ticket to another team.")
            if requested_team_changed and actor_role not in ADMIN_ACCESS_ROLES and has_assigned_agent_input:
                raise ApiError(403, "Team transfers by agents cannot assign a receiver.")
            if requested_team_changed and not note:
                raise ApiError(400, "Add a transfer note before moving this ticket to another team.")

        target_assignment_ticket = {
            **ticket,
            "assigned_team": normalized_requested_assigned_team
            if requested_assigned_team is not None
            else current_assigned_team,
        }

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
                SELECT id, username, full_name, email, account_scope, role, is_active, metadata
                FROM support_accounts
                WHERE id = %s
                  AND is_active = TRUE
                  AND account_scope = %s
                LIMIT 1
                """,
                [parsed_assigned_agent_id, ACCOUNT_SCOPE_STAFF],
            )
            if not account_can_receive_ticket_assignment(assigned_agent, target_assignment_ticket):
                raise ApiError(400, get_ticket_assignment_receiver_error(target_assignment_ticket))
        elif not has_assigned_agent_input and ticket.get("assigned_agent_id") and not requested_team_changed:
            assigned_agent = {
                "id": ticket["assigned_agent_id"],
                "username": ticket.get("assigned_agent_username"),
                "full_name": ticket.get("assigned_agent_name"),
                "role": "agent",
            }

        auto_assigned_actor = None
        if (
            not has_assigned_agent_input
            and current_assigned_agent_id is None
            and not requested_team_changed
            and actor_row
            and sanitize_text(actor_row.get("role")).lower() in {ROLE_ADMIN, ROLE_SUPERADMIN}
            and account_can_receive_ticket_assignment(actor_row, target_assignment_ticket)
        ):
            auto_assigned_actor = {
                "id": int(actor_row["id"]),
                "username": actor_row["username"],
                "full_name": actor_row.get("full_name") or actor_row["username"],
                "email": actor_row.get("email"),
                "role": actor_row["role"],
            }
            assigned_agent = auto_assigned_actor

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
        next_chat_state = requested_chat_state or map_conversation_status(next_status)
        ensure_open_ticket_uses_open_chat(next_status, next_chat_state)
        updated_ticket_metadata = normalize_json_object(ticket.get("metadata"))
        if is_quick_ticket_record(ticket) or (
            is_quick_ticket_status_reason(next_status_reason)
            and not is_coverage_ticket_record(ticket)
        ):
            updated_ticket_metadata[QUICK_TICKET_ORIGIN_METADATA_KEY] = True
        chat_public_id = build_public_chat_id(ticket.get("public_id"), ticket.get("conversation_id"), ticket.get("conversation_metadata"))
        if requested_documentation is not None:
            previous_documentation_payload = normalize_json_object(ticket.get("metadata")).get("admin_documentation")
            documentation_payload = normalize_admin_documentation(
                requested_documentation,
                fallback_inquiry=sanitize_text(ticket.get("inquiry")),
                fallback_chat_id=chat_public_id,
                fallback_ticket_id=ticket["public_id"],
            )
            if uploaded_documentation_files:
                documentation_payload = attach_uploaded_documentation_card_files(
                    ticket_id=int(ticket["id"]),
                    ticket_public_id=ticket["public_id"],
                    documentation=documentation_payload,
                    uploaded_files=uploaded_documentation_files,
                )
            if is_coverage_ticket_record(ticket):
                documentation_payload = freeze_coverage_documentation_snapshot(
                    previous_documentation_payload,
                    documentation_payload,
                )
                documentation_payload = stamp_coverage_documentation_card_actors(
                    documentation_payload,
                    previous_documentation_payload,
                    actor_row,
                )
            documentation_payload = stamp_documentation_card_actors(
                documentation_payload,
                previous_documentation_payload,
                actor_row,
            )
            documentation_history_events = build_documentation_card_history_events(
                previous_documentation_payload,
                documentation_payload,
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

        next_sla_status, next_sla_attention_required, next_sla_attention_reason, updated_ticket_metadata = resolve_ticket_sla_update(
            ticket,
            next_status,
            status_reason=next_status_reason,
            metadata=updated_ticket_metadata,
            requested_sla_status=requested_sla_status,
        )

        if has_assigned_agent_input:
            next_assigned_agent_id = parsed_assigned_agent_id
        elif auto_assigned_actor:
            next_assigned_agent_id = auto_assigned_actor["id"]
        elif requested_team_changed:
            next_assigned_agent_id = None
        else:
            next_assigned_agent_id = ticket.get("assigned_agent_id")

        if requested_assigned_team is not None:
            next_assigned_team = normalized_requested_assigned_team or derive_assigned_team_for_ticket_assignment(
                current_assigned_team,
                assigned_agent,
            )
        elif has_assigned_agent_input or auto_assigned_actor:
            next_assigned_team = derive_assigned_team_for_ticket_assignment(current_assigned_team, assigned_agent)
        else:
            next_assigned_team = current_assigned_team
        if next_assigned_agent_id is None:
            next_assigned_agent_name = ""
            next_assigned_agent_username = ""
        elif isinstance(assigned_agent, dict):
            next_assigned_agent_name = sanitize_text(assigned_agent.get("full_name") or assigned_agent.get("username"))
            next_assigned_agent_username = sanitize_text(assigned_agent.get("username"))
        else:
            next_assigned_agent_name = sanitize_text(ticket.get("assigned_agent_name"))
            next_assigned_agent_username = sanitize_text(ticket.get("assigned_agent_username"))

        next_requester_role = get_ticket_requester_role(updated_ticket_metadata)
        next_requester_email = sanitize_text(ticket.get("learner_email"))
        next_requester_name = sanitize_text(ticket.get("learner_name")) or next_requester_email
        is_next_learning_plan_team = next_assigned_team.casefold() == ASSIGNED_TEAM_LEARNING_PLAN.casefold()

        if requested_team_changed:
            updated_ticket_metadata.pop(PENDING_TRANSFER_REQUEST_METADATA_KEY, None)
            updated_ticket_metadata.pop(LATEST_TRANSFER_DECISION_METADATA_KEY, None)

        if not is_next_learning_plan_team:
            updated_ticket_metadata.pop(PENDING_LEARNING_PLAN_TRANSFER_NOTIFICATION_METADATA_KEY, None)

        if requested_team_changed and is_next_learning_plan_team:
            learning_plan_transfer_notification_payload = build_learning_plan_transfer_notification_payload(
                ticket_id=ticket["public_id"],
                requester_name=next_requester_name,
                requester_email=next_requester_email,
                requester_role=next_requester_role,
                from_team=current_assigned_team,
                to_team=next_assigned_team,
                transferred_at=datetime.now(timezone.utc),
                transferred_by=actor_row,
                assigned_agent_id=next_assigned_agent_id,
                assigned_agent_name=next_assigned_agent_name,
                assigned_agent_username=next_assigned_agent_username,
                note=note,
            )
            updated_ticket_metadata[PENDING_LEARNING_PLAN_TRANSFER_NOTIFICATION_METADATA_KEY] = (
                learning_plan_transfer_notification_payload
            )

        updated_ticket_metadata, ticket_state_columns = build_ticket_state_persistence(
            updated_ticket_metadata,
            {
                **ticket,
                "status": next_status,
                "status_reason": next_status_reason,
                "assigned_agent_id": next_assigned_agent_id,
                "assigned_team": next_assigned_team,
            },
            chat_state=next_chat_state,
        )

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
                  ticket_type = %s,
                  workflow_stage = %s,
                  queue_scope = %s,
                  dashboard_bucket = %s,
                  can_show_conversation = %s,
                  can_receive_chat = %s,
                  resolution_reason = %s,
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
                    *get_ticket_state_column_params(ticket_state_columns),
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

        if requested_team_changed:
            insert_history_event(
                ticket["id"],
                "team_transferred",
                actor,
                {
                    "fromTeam": current_assigned_team,
                    "toTeam": next_assigned_team,
                },
            )
            if next_assigned_team.casefold() == ASSIGNED_TEAM_LEARNING_PLAN.casefold():
                learning_plan_transfer_webhook_ticket_id = int(ticket["id"])
                learning_plan_transfer_webhook_payload = build_learning_plan_ticket_transfer_webhook_payload(
                    ticket_row={
                        **ticket,
                        "status": next_status,
                        "status_reason": next_status_reason,
                        "assigned_agent_id": next_assigned_agent_id,
                        "assigned_agent_name": next_assigned_agent_name,
                        "assigned_agent_username": next_assigned_agent_username,
                        "assigned_team": next_assigned_team,
                        "sla_status": next_sla_status,
                        "metadata": updated_ticket_metadata,
                    },
                    from_team=current_assigned_team,
                    to_team=next_assigned_team,
                    transferred_by=actor_row,
                    transferred_at=datetime.now(timezone.utc),
                    assigned_agent_id=next_assigned_agent_id,
                    assigned_agent_name=next_assigned_agent_name,
                    assigned_agent_username=next_assigned_agent_username,
                    note=note,
                )

        if ticket["sla_status"] != next_sla_status:
            insert_history_event(ticket["id"], "sla_changed", actor, {"from": ticket["sla_status"], "to": next_sla_status})

        if note:
            insert_history_event(ticket["id"], "internal_note", actor, {"note": note})

        for event_type, event_payload in documentation_history_events:
            insert_history_event(ticket["id"], event_type, actor, event_payload)

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

        should_queue_admin_quick_closed_notification = should_notify_quick_ticket_closed(
            ticket,
            previous_status=ticket.get("status"),
            previous_status_reason=ticket.get("status_reason"),
            next_status=next_status,
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

    if should_queue_admin_quick_closed_notification:
        queue_quick_ticket_closed_notification(
            ticket,
            status=next_status,
            status_reason=next_status_reason,
        )
    if learning_plan_transfer_webhook_ticket_id and learning_plan_transfer_webhook_payload:
        notify_learning_plan_ticket_transfer(
            learning_plan_transfer_webhook_ticket_id,
            learning_plan_transfer_webhook_payload,
        )

    detail_public_id = follow_up_public_id or public_id
    detail = fetch_admin_ticket_detail(detail_public_id)
    if not detail:
        raise ApiError(404, "Ticket not found.")

    return detail


def update_admin_ticket_archive_state(public_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not public_id:
        raise ApiError(400, "Ticket id is required.")
    if "archived" not in payload:
        raise ApiError(400, "archived field is required.")

    should_archive = normalize_bool(payload.get("archived"))
    actor_username = sanitize_text(payload.get("actorUsername")).lower()

    with transaction.atomic():
        ticket = run_query_one(
            """
            SELECT id, public_id, technical_subcategory, assigned_team, metadata, is_archived
            FROM tickets
            WHERE public_id = %s
            LIMIT 1
            """,
            [public_id],
        )

        if not ticket:
            raise ApiError(404, "Ticket not found.")

        actor_row = fetch_actor_by_username(actor_username) if actor_username else None
        require_actor_can_access_admin_ticket(actor_row, ticket)
        actor = (
            {
                "id": actor_row["id"],
                "role": actor_row["role"],
                "label": actor_row.get("full_name") or actor_row["username"],
            }
            if actor_row
            else None
        )
        current_archive_state = normalize_bool(ticket.get("is_archived"))

        if current_archive_state != should_archive:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE tickets
                    SET
                      is_archived = %s,
                      archived_at = CASE WHEN %s THEN NOW() ELSE NULL END,
                      archived_by_id = CASE WHEN %s THEN %s ELSE NULL END,
                      updated_at = NOW()
                    WHERE id = %s
                    """,
                    [
                        should_archive,
                        should_archive,
                        should_archive,
                        actor_row["id"] if actor_row else None,
                        ticket["id"],
                    ],
                )

            insert_history_event(
                ticket["id"],
                "ticket_archived" if should_archive else "ticket_unarchived",
                actor,
                {
                    "archived": should_archive,
                    "from": current_archive_state,
                    "to": should_archive,
                },
            )

    detail = fetch_admin_ticket_detail(public_id)
    if not detail:
        raise ApiError(404, "Ticket not found.")

    return detail


def delete_admin_ticket_permanently(public_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    normalized_public_id = sanitize_text(public_id).upper()
    if not normalized_public_id:
        raise ApiError(400, "Ticket id is required.")

    actor_username = sanitize_text(payload.get("actorUsername")).lower()
    confirm_ticket_id = sanitize_text(payload.get("confirmTicketId")).upper()
    if not confirm_ticket_id or confirm_ticket_id != normalized_public_id:
        raise ApiError(400, "Type the ticket ID to confirm permanent deletion.")

    actor_row = fetch_actor_by_username(actor_username) if actor_username else None
    actor_role = sanitize_text(actor_row.get("role") if actor_row else "").lower()
    if actor_role != ROLE_SUPERADMIN:
        raise ApiError(403, "Only superadmins can permanently delete archived tickets.")

    attachment_storage_keys: list[str] = []
    conversation_deleted = False

    with transaction.atomic():
        ticket = run_query_one(
            """
            SELECT
              t.id,
              t.public_id,
              t.technical_subcategory,
              t.assigned_team,
              t.metadata,
              t.is_archived,
              t.conversation_id,
              c.metadata AS conversation_metadata
            FROM tickets t
            LEFT JOIN conversations c
              ON c.id = t.conversation_id
            WHERE t.public_id = %s
            LIMIT 1
            """,
            [normalized_public_id],
        )
        if not ticket:
            raise ApiError(404, "Ticket not found.")

        require_actor_can_access_admin_ticket(actor_row, ticket)

        if not normalize_bool(ticket.get("is_archived")):
            raise ApiError(409, "Archive this ticket before deleting it permanently.")

        ticket_id = int(ticket["id"])
        attachment_storage_keys = list_ticket_attachment_storage_keys(ticket_id)

        try:
            conversation_id = int(ticket["conversation_id"]) if ticket.get("conversation_id") else None
        except (TypeError, ValueError):
            conversation_id = None

        remaining_conversation_tickets: list[dict[str, Any]] = []
        if conversation_id is not None:
            remaining_conversation_tickets = run_query(
                """
                SELECT id, public_id, metadata, created_at
                FROM tickets
                WHERE conversation_id = %s
                  AND id <> %s
                ORDER BY created_at ASC, id ASC
                """,
                [conversation_id, ticket_id],
            )

        with connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM tickets
                WHERE id = %s
                """,
                [ticket_id],
            )

            if conversation_id is not None:
                if remaining_conversation_tickets:
                    latest_remaining_ticket = remaining_conversation_tickets[-1]
                    latest_remaining_public_id = sanitize_text(latest_remaining_ticket.get("public_id"))
                    previous_remaining_public_id = (
                        sanitize_text(remaining_conversation_tickets[-2].get("public_id"))
                        if len(remaining_conversation_tickets) > 1
                        else latest_remaining_public_id
                    )
                    updated_conversation_metadata = {
                        **normalize_json_object(ticket.get("conversation_metadata")),
                        "latest_ticket_public_id": latest_remaining_public_id or None,
                        "parent_ticket_public_id": previous_remaining_public_id or latest_remaining_public_id or None,
                    }
                    updated_conversation_metadata["chat_public_id"] = (
                        build_public_chat_id(
                            latest_remaining_public_id,
                            conversation_id,
                            updated_conversation_metadata,
                        )
                        or None
                    )
                    cursor.execute(
                        """
                        UPDATE conversations
                        SET metadata = %s::jsonb
                        WHERE id = %s
                        """,
                        [json.dumps(updated_conversation_metadata), conversation_id],
                    )
                else:
                    cursor.execute(
                        """
                        DELETE FROM conversations
                        WHERE id = %s
                        """,
                        [conversation_id],
                    )
                    conversation_deleted = True

    for storage_key in attachment_storage_keys:
        try:
            delete_support_attachment_file(storage_key)
        except OSError:
            logger.warning(
                "Failed to delete attachment file for permanently deleted ticket %s",
                normalized_public_id,
                exc_info=True,
            )

    return {
        "ok": True,
        "ticketId": normalized_public_id,
        "conversationDeleted": conversation_deleted,
        "message": "Ticket deleted permanently.",
    }


def create_ticket(payload: dict[str, Any], *, uploaded_files: list[Any] | None = None) -> dict[str, Any]:
    email = normalize_email(payload.get("email"))
    category = sanitize_text(payload.get("category"))
    technical_subcategory = normalize_technical_subcategory(payload.get("technicalSubcategory"))
    inquiry = sanitize_text(payload.get("inquiry"))
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), list) else []
    uploaded_files = list(uploaded_files or [])
    evidence_count = len(uploaded_files) if uploaded_files else len(evidence)
    stored_attachment_keys: list[str] = []
    attachment_rows: list[dict[str, Any]] = []

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

    try:
        with transaction.atomic():
            requester = resolve_public_support_requester(email)
            if not requester:
                raise ApiError(404, "This email is not registered in our records.")

            requester_role = requester["role"]
            requester_source = get_public_requester_source(requester)
            if technical_subcategory == "Coverage":
                ensure_requester_can_submit_coverage_ticket(requester_source)
            ticket_priority = derive_requester_ticket_priority(requester_role)
            learner = ensure_public_requester_learner(requester)
            managed_account = requester.get("account")
            ticket_metadata = {
                "source": "support_portal",
                "technical_subcategory": technical_subcategory or None,
                "requester_role": requester_role,
                "requester_source": requester_source or None,
            }
            if managed_account:
                ticket_metadata.update(
                    {
                        "requester_account_id": int(managed_account["id"]),
                        "requester_username": sanitize_text(managed_account.get("username")),
                    }
                )
            entra_user = requester.get("entra_user")
            if entra_user:
                ticket_metadata.update(
                    {
                        "requester_source": MICROSOFT_ENTRA_REQUESTER_SOURCE,
                        "entra_object_id": sanitize_text(entra_user.get("id")),
                        "entra_user_principal_name": sanitize_text(entra_user.get("userPrincipalName")),
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
                        evidence_count,
                        json.dumps(ticket_metadata),
                    ],
                )
                ticket_row = dictfetchone(cursor)
                if not ticket_row:
                    raise ApiError(500, "We could not create the ticket right now.")

                public_id = build_public_ticket_id(int(ticket_row["id"]))
                initial_sla_status = "On Track" if technical_subcategory == "Coverage" else ticket_row["sla_status"]
                if technical_subcategory == "Coverage":
                    ticket_metadata[PENDING_COVERAGE_TICKET_NOTIFICATION_METADATA_KEY] = {
                        "ticketId": public_id,
                        "requesterName": requester.get("display_name") or learner.get("full_name") or learner["email"],
                        "requesterEmail": learner["email"],
                        "requesterRole": requester_role,
                        "createdAt": serialize_datetime_value(ticket_row.get("created_at")) or serialize_datetime_value(datetime.now(timezone.utc)),
                    }
                else:
                    ticket_metadata[PENDING_SUPPORT_QUEUE_NOTIFICATION_METADATA_KEY] = build_support_queue_notification_payload(
                        ticket_id=public_id,
                        requester_name=requester.get("display_name") or learner.get("full_name") or learner["email"],
                        requester_email=learner["email"],
                        requester_role=requester_role,
                        reason="support_ticket_created",
                        created_at=ticket_row.get("created_at") or datetime.now(timezone.utc),
                    )
                if technical_subcategory == "Coverage":
                    ticket_metadata = build_resolved_coverage_sla_metadata(ticket_metadata)
                else:
                    _initial_sla_status, _initial_sla_attention_required, _initial_sla_attention_reason, ticket_metadata = resolve_sla_policy_update(
                        {
                            "status": ticket_row["status"],
                            "status_reason": "",
                            "created_at": ticket_row.get("created_at"),
                            "sla_status": initial_sla_status,
                            "metadata": ticket_metadata,
                        },
                        ticket_row["status"],
                        status_reason="",
                        metadata=ticket_metadata,
                    )
                ticket_metadata, ticket_state_columns = build_ticket_state_persistence(
                    ticket_metadata,
                    {
                        "public_id": public_id,
                        "category": category,
                        "technical_subcategory": technical_subcategory or "",
                        "status": ticket_row["status"],
                        "status_reason": "",
                        "assigned_team": ticket_row["assigned_team"],
                    },
                    chat_state="open",
                )

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
                                "requester_source": requester_source or None,
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
                    SET public_id = %s,
                        conversation_id = %s,
                        sla_status = %s,
                        metadata = %s::jsonb,
                        ticket_type = %s,
                        workflow_stage = %s,
                        queue_scope = %s,
                        dashboard_bucket = %s,
                        can_show_conversation = %s,
                        can_receive_chat = %s,
                        resolution_reason = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    [
                        public_id,
                        conversation_id,
                        initial_sla_status,
                        json.dumps(ticket_metadata),
                        *get_ticket_state_column_params(ticket_state_columns),
                        ticket_row["id"],
                    ],
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

                attachment_rows = [normalize_ticket_attachment_row_payload(file) for file in evidence]
                if uploaded_files:
                    attachment_rows = store_uploaded_ticket_attachments(public_id, uploaded_files)
                    stored_attachment_keys = [
                        attachment.get("storageKey")
                        for attachment in attachment_rows
                        if sanitize_text(attachment.get("storageKey"))
                    ]

                for file in attachment_rows:
                    normalized_file = normalize_ticket_attachment_row_payload(file)
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
                            normalized_file["name"],
                            normalized_file["mimeType"],
                            normalized_file["size"],
                            normalized_file["storageKey"],
                            json.dumps(normalized_file["metadata"]),
                        ],
                    )

            insert_history_event(
                int(ticket_row["id"]),
                "ticket_created",
                {"role": requester_role, "label": learner["email"]},
                {
                    "category": category,
                    "technical_subcategory": technical_subcategory or None,
                    "evidence_count": evidence_count,
                },
            )
    except Exception:
        for storage_key in stored_attachment_keys:
            delete_support_attachment_file(storage_key)
        raise

    if technical_subcategory == "Coverage":
        notify_coverage_ticket_operations_team(
            int(ticket_row["id"]),
            build_coverage_ticket_operations_webhook_payload(
                public_id=public_id,
                ticket_row=ticket_row,
                requester=requester,
                learner=learner,
                requester_role=requester_role,
                category=category,
                technical_subcategory=technical_subcategory,
                inquiry=inquiry,
                priority=ticket_priority,
                evidence_count=evidence_count,
                attachment_rows=attachment_rows,
            ),
        )

    return {
        "ticket": {
            "id": public_id,
            "learnerName": requester.get("display_name") or learner.get("full_name") or "",
            "requesterName": requester.get("display_name") or learner.get("full_name") or "",
            "email": learner["email"],
            "requesterRole": requester_role,
            "requesterSource": requester_source,
            "category": category,
            "technicalSubcategory": technical_subcategory,
            "inquiry": inquiry,
            "status": ticket_row["status"],
        "statusReason": "",
        "assignedTeam": ticket_row["assigned_team"],
        "slaStatus": initial_sla_status,
        "createdAt": ticket_row["created_at"],
        "chatState": "open",
        "liveChatRequested": False,
    }
    }


def update_ticket(public_id: str, payload: dict[str, Any], *, uploaded_files: list[Any] | None = None) -> dict[str, Any]:
    category = sanitize_text(payload.get("category"))
    technical_subcategory = normalize_technical_subcategory(payload.get("technicalSubcategory"))
    inquiry = sanitize_text(payload.get("inquiry"))
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), list) else []
    uploaded_files = list(uploaded_files or [])
    evidence_count = len(uploaded_files) if uploaded_files else len(evidence)
    stored_attachment_keys: list[str] = []
    existing_attachment_storage_keys: list[str] = []

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

    try:
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
                  l.email,
                  l.source AS learner_source,
                  l.metadata AS learner_metadata
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
            requester_source = get_ticket_requester_source(
                existing_ticket.get("metadata"),
                learner_source=existing_ticket.get("learner_source"),
                learner_metadata=existing_ticket.get("learner_metadata"),
            )
            if technical_subcategory == "Coverage":
                ensure_requester_can_submit_coverage_ticket(requester_source)
            next_priority = derive_requester_ticket_priority(requester_role, existing_ticket.get("priority"))
            existing_attachment_storage_keys = list_ticket_attachment_storage_keys(int(existing_ticket["id"]))

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
                      metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb,
                      updated_at = NOW()
                    WHERE id = %s
                    """,
                    [
                        category,
                        technical_subcategory or None,
                        inquiry,
                        next_priority,
                        evidence_count,
                        json.dumps({"requester_source": requester_source} if requester_source else {}),
                        existing_ticket["id"],
                    ],
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
                                    "evidence_count": evidence_count,
                                    "requester_source": requester_source or None,
                                }
                            ),
                            existing_ticket["conversation_id"],
                        ],
                    )

                attachment_rows = [normalize_ticket_attachment_row_payload(file) for file in evidence]
                if uploaded_files:
                    attachment_rows = store_uploaded_ticket_attachments(existing_ticket["public_id"], uploaded_files)
                    stored_attachment_keys = [
                        attachment.get("storageKey")
                        for attachment in attachment_rows
                        if sanitize_text(attachment.get("storageKey"))
                    ]

                cursor.execute("DELETE FROM ticket_attachments WHERE ticket_id = %s", [existing_ticket["id"]])

                for file in attachment_rows:
                    normalized_file = normalize_ticket_attachment_row_payload(file)
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
                            normalized_file["name"],
                            normalized_file["mimeType"],
                            normalized_file["size"],
                            normalized_file["storageKey"],
                            json.dumps(normalized_file["metadata"]),
                        ],
                    )

            transaction.on_commit(
                lambda old_storage_keys=list(existing_attachment_storage_keys): [
                    delete_support_attachment_file(storage_key)
                    for storage_key in old_storage_keys
                ]
            )

            insert_history_event(
                int(existing_ticket["id"]),
                "ticket_updated",
                {"role": requester_role, "label": existing_ticket["email"]},
                {
                    "category": category,
                    "technical_subcategory": technical_subcategory or None,
                    "priority": next_priority,
                    "evidence_count": evidence_count,
                },
            )
    except Exception:
        for storage_key in stored_attachment_keys:
            delete_support_attachment_file(storage_key)
        raise

    return {
        "ticket": {
            "id": existing_ticket["public_id"],
            "learnerName": existing_ticket.get("learner_name") or "",
            "requesterName": existing_ticket.get("learner_name") or "",
            "email": existing_ticket["email"],
            "requesterRole": requester_role,
            "requesterSource": requester_source,
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


def save_chat_history(public_id: str, payload: dict[str, Any], *, uploaded_files: list[Any] | None = None) -> dict[str, Any]:
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
              t.category,
              t.technical_subcategory,
              t.priority,
              t.status,
              t.status_reason,
              t.assigned_agent_id,
              t.assigned_team,
              t.sla_status,
              t.metadata,
              t.created_at,
              l.full_name AS learner_name,
              l.email AS learner_email,
              l.source AS learner_source,
              l.metadata AS learner_metadata,
              c.status AS conversation_status,
              a.full_name AS assigned_agent_name,
              a.username AS assigned_agent_username
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
        previous_status = ticket.get("status")
        previous_status_reason = ticket.get("status_reason")
        preview_messages = normalize_chat_messages(messages)
        filtered_messages, next_status_reason, next_sla_status, next_sla_attention_required = apply_ticket_chat_history_sync(
            ticket,
            status=status,
            status_reason=status_reason,
            messages=messages,
            ticket_public_id=ticket["public_id"],
            uploaded_files=uploaded_files,
            conversation_metadata_patch=build_inactivity_metadata_patch_for_messages(
                status,
                preview_messages,
                reference_time=persisted_at,
            ),
            reference_time=persisted_at,
        )
        should_queue_quick_submitted_notification = should_notify_quick_ticket_submitted(
            ticket,
            previous_status=previous_status,
            previous_status_reason=previous_status_reason,
            next_status=status,
            next_status_reason=next_status_reason,
        )
        should_queue_quick_closed_notification = should_notify_quick_ticket_closed(
            ticket,
            previous_status=previous_status,
            previous_status_reason=previous_status_reason,
            next_status=status,
        )

    if should_queue_quick_submitted_notification:
        queue_quick_ticket_submitted_notification(ticket, status=status, status_reason=next_status_reason)
    if should_queue_quick_closed_notification:
        queue_quick_ticket_closed_notification(
            ticket,
            status=status,
            status_reason=next_status_reason,
            closed_at=persisted_at,
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


def execute_http_request(request: urllib_request.Request, *, timeout_seconds: int = 20) -> tuple[bool, bool, int | None, Any]:
    try:
        with urllib_request.urlopen(request, timeout=timeout_seconds) as response:
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
    except TimeoutError:
        return True, False, None, {"message": "Request timed out."}
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


def post_json_request(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
    *,
    timeout_seconds: int = 20,
) -> tuple[bool, bool, int | None, Any]:
    if not url:
        return False, False, None, None

    request_headers = {"Content-Type": "application/json", **(headers or {})}
    request = urllib_request.Request(
        url,
        data=json.dumps(payload, default=str).encode("utf-8"),
        headers=request_headers,
        method="POST",
    )
    return execute_http_request(request, timeout_seconds=timeout_seconds)


def delete_request(url: str, headers: dict[str, str] | None = None) -> tuple[bool, bool, int | None, Any]:
    if not url:
        return False, False, None, None

    request = urllib_request.Request(
        url,
        headers=headers or {},
        method="DELETE",
    )
    return execute_http_request(request)


def post_json_webhook(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    timeout_seconds: int = 20,
) -> tuple[bool, bool, int | None, Any]:
    return post_json_request(url, payload, headers=headers, timeout_seconds=timeout_seconds)


def post_multipart_webhook(
    url: str,
    payload: dict[str, Any],
    files: list[dict[str, Any]],
    *,
    timeout_seconds: int = 30,
) -> tuple[bool, bool, int | None, Any]:
    """Send a multipart/form-data POST with a JSON body field and binary file attachments."""
    import mimetypes
    import uuid

    if not url:
        return False, False, None, None

    boundary = uuid.uuid4().hex
    crlf = b"\r\n"
    parts = []

    json_bytes = json.dumps(payload, default=str).encode("utf-8")
    parts.append(
        b"--" + boundary.encode() + crlf +
        b'Content-Disposition: form-data; name="body"' + crlf +
        b"Content-Type: application/json" + crlf + crlf +
        json_bytes + crlf
    )

    for i, file in enumerate(files):
        data_url = sanitize_text(file.get("dataUrl") or "")
        storage_key = sanitize_text(file.get("storageKey") or "")
        file_bytes = b""
        try:
            if data_url.startswith("data:"):
                _header, b64data = data_url.split(",", 1)
                import base64 as _b64
                file_bytes = _b64.b64decode(b64data)
            elif storage_key:
                file_bytes = resolve_support_attachment_path(storage_key).read_bytes()
            else:
                continue
        except Exception:
            continue
        file_name = sanitize_text(file.get("name") or f"attachment_{i}")
        mime_type = sanitize_text(file.get("mimeType") or "application/octet-stream")
        parts.append(
            b"--" + boundary.encode() + crlf +
            f'Content-Disposition: form-data; name="file_{i}"; filename="{file_name}"'.encode() + crlf +
            f"Content-Type: {mime_type}".encode() + crlf + crlf +
            file_bytes + crlf
        )

    body = b"".join(parts) + b"--" + boundary.encode() + b"--" + crlf
    request = urllib_request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    return execute_http_request(request, timeout_seconds=timeout_seconds)


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
    token_url = f"https://login.microsoftonline.com/{settings.AZURE_BOOKING_TENANT_ID}/oauth2/v2.0/token"
    return post_form_request(
        token_url,
        {
            "client_id": settings.AZURE_BOOKING_CLIENT_ID,
            "client_secret": settings.AZURE_BOOKING_CLIENT_SECRET,
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
    configured, delivered, status, response_payload = post_json_webhook(
        settings.CHATBOT_WEBHOOK_URL,
        payload,
        timeout_seconds=CHATBOT_WEBHOOK_TIMEOUT_SECONDS,
    )
    return {
        "configured": configured,
        "delivered": delivered,
        "status": status,
        "reply": extract_chatbot_reply(response_payload) if delivered else "",
    }


def build_chat_attachment_fallback_message(attachments: list[dict[str, Any]]) -> str:
    if not attachments:
        return ""

    if len(attachments) == 1:
        attachment_name = sanitize_support_attachment_name(attachments[0].get("name"))
        return f"Shared attachment: {attachment_name}." if attachment_name else "Shared one attachment."

    return f"Shared {len(attachments)} attachments."


def send_chatbot_message(public_id: str, payload: dict[str, Any], *, uploaded_files: list[Any] | None = None) -> dict[str, Any]:
    uploaded_files = list(uploaded_files or [])
    raw_messages = payload.get("messages") if isinstance(payload.get("messages"), list) else []
    normalized_messages = normalize_chat_messages(raw_messages)
    latest_normalized_message = normalized_messages[-1] if normalized_messages else None
    latest_attachments = list(latest_normalized_message.get("attachments") or []) if latest_normalized_message else []
    message = (
        sanitize_text(payload.get("message"))
        or (sanitize_text(latest_normalized_message.get("content")) if latest_normalized_message else "")
    )
    webhook_message = message or build_chat_attachment_fallback_message(latest_attachments)
    client_time_zone = sanitize_text(payload.get("clientTimeZone"))

    if not public_id:
        raise ApiError(400, "Ticket id is required.")
    if not webhook_message and not latest_attachments:
        raise ApiError(400, "Message text or attachment is required.")

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
    if is_chat_locked_for_learner(ticket.get("status"), ticket.get("status_reason")):
        raise ApiError(409, "Chat is unavailable while a support meeting is active. Cancel the meeting to continue in chat.")
    if is_ticket_chat_closed(ticket.get("status"), ticket.get("conversation_status")):
        raise ApiError(409, "This chat has been closed by support. Start a new chat to continue.")

    mark_conversation_as_active(ticket["public_id"], ticket.get("conversation_id"))

    recent_messages = [
        {
            "sender": sanitize_text(entry.get("metadata", {}).get("original_sender")) or map_role_to_sender(entry.get("role")),
            "text": sanitize_text(entry.get("content")),
            "timestamp": sanitize_text(entry.get("metadata", {}).get("client_timestamp")),
            "attachments": serialize_chat_message_attachment_metadata_payload(list(entry.get("attachments") or [])),
        }
        for entry in normalized_messages[-12:]
        if sanitize_text(entry.get("content")) or entry.get("attachments")
    ]

    webhook_result = send_chatbot_webhook(
        {
            "event": "support_chat_message",
            "source": "support_portal",
            "message": webhook_message,
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
            raw_messages
            + [{"sender": "bot", "text": webhook_result["reply"], "timestamp": format_chat_message_timestamp(persisted_at)}]
            if webhook_result.get("reply")
            else raw_messages
        )

        with transaction.atomic():
            sync_conversation_messages(
                int(ticket["conversation_id"]),
                ticket["status"],
                synced_messages,
                ticket_public_id=ticket["public_id"],
                uploaded_files=uploaded_files,
                conversation_metadata_patch=build_inactivity_metadata_patch_for_messages(
                    ticket["status"],
                    normalize_chat_messages(synced_messages),
                    reference_time=persisted_at,
                ),
                reference_time=persisted_at,
            )

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
    return_path = normalize_support_booking_return_path(payload.get("returnPath"))

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

        lock_support_session_booking_date(requested_datetime)
        guard_duration_minutes = int(settings.SUPPORT_SESSION_DURATION_MINUTES)
        if not is_support_session_slot_locally_available(requested_datetime, guard_duration_minutes):
            raise ApiError(409, "This Teams slot is no longer available. Please choose a different time.")

        requested_end_at = requested_datetime + timedelta(minutes=guard_duration_minutes)
        initial_session_metadata = {
            "source": "support_portal",
            "scheduled_at": scheduled_at or None,
            "client_time_zone": client_time_zone or None,
            "return_path": return_path or None,
            "requested_start_at": requested_datetime.isoformat(),
            "requested_end_at": requested_end_at.isoformat(),
            "duration_minutes": guard_duration_minutes,
            "buffer_minutes": get_support_session_buffer_minutes(),
        }
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
                    json.dumps(initial_session_metadata),
                ],
            )
            created_session_request = dictfetchone(cursor)

        insert_history_event(
            int(ticket["id"]),
            "support_session_requested",
            {"role": "learner", "label": public_id},
            {"requestedDate": requested_date, "requestedTime": requested_time},
        )

        support_session_ticket_metadata = {
            **normalize_json_object(ticket.get("metadata")),
            "support_session_requested_start_at": requested_datetime.isoformat(),
            "support_session_requested_end_at": requested_end_at.isoformat(),
        }
        next_sla_status, next_sla_attention_required, _next_sla_attention_reason, updated_ticket_metadata = resolve_ticket_sla_update(
            ticket,
            "Pending",
            status_reason=STATUS_REASON_AWAITING_MEETING,
            metadata=support_session_ticket_metadata,
        )
        session_ticket_metadata_patch = {
            **updated_ticket_metadata,
            SUPPORT_FLOW_STAGE_METADATA_KEY: None,
            "booking_started_at": None,
        }
        if not is_coverage_ticket_record(ticket):
            session_ticket_metadata_patch[PENDING_SUPPORT_QUEUE_NOTIFICATION_METADATA_KEY] = build_support_queue_notification_payload(
                ticket_id=ticket["public_id"],
                requester_name=ticket.get("learner_full_name") or ticket.get("learner_email"),
                requester_email=ticket.get("learner_email"),
                requester_role=get_ticket_requester_role(session_ticket_metadata_patch),
                reason="support_session_requested",
                created_at=datetime.now(timezone.utc),
            )
        session_ticket_metadata_patch, ticket_state_columns = build_ticket_state_persistence(
            session_ticket_metadata_patch,
            {
                **ticket,
                "status": "Pending",
                "status_reason": STATUS_REASON_AWAITING_MEETING,
            },
            chat_state=map_conversation_status("Pending"),
        )

        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE tickets
                SET status = %s,
                    status_reason = %s,
                    sla_status = %s,
                    metadata = %s::jsonb,
                    ticket_type = %s,
                    workflow_stage = %s,
                    queue_scope = %s,
                    dashboard_bucket = %s,
                    can_show_conversation = %s,
                    can_receive_chat = %s,
                    resolution_reason = %s,
                    updated_at = NOW(),
                    closed_at = CASE
                      WHEN status = 'Closed' THEN NULL
                      ELSE closed_at
                    END
                WHERE id = %s
                """,
                [
                    "Pending",
                    STATUS_REASON_AWAITING_MEETING,
                    next_sla_status,
                    json.dumps(session_ticket_metadata_patch),
                    *get_ticket_state_column_params(ticket_state_columns),
                    ticket["id"],
                ],
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
        "buffer_minutes": get_support_session_buffer_minutes(),
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

    next_sla_status, next_sla_attention_required, _next_sla_attention_reason, updated_ticket_metadata = resolve_ticket_sla_update(
        ticket,
        "Open",
        status_reason="",
    )
    cancellation_metadata_patch = {
        "cancelled_at": datetime.now(timezone.utc).isoformat(),
        "cancellation_configured": cancellation_result["configured"],
        "cancellation_delivered": cancellation_result["delivered"],
        "cancellation_status": cancellation_result["status"],
        "reservation_confirmed": False,
        "meeting_join_url": None,
    }
    updated_ticket_metadata, ticket_state_columns = build_ticket_state_persistence(
        updated_ticket_metadata,
        {
            **ticket,
            "status": "Open",
            "status_reason": "",
        },
        chat_state=map_conversation_status("Open"),
    )

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
                    metadata = %s::jsonb,
                    ticket_type = %s,
                    workflow_stage = %s,
                    queue_scope = %s,
                    dashboard_bucket = %s,
                    can_show_conversation = %s,
                    can_receive_chat = %s,
                    resolution_reason = %s,
                    updated_at = NOW(),
                    closed_at = CASE
                      WHEN status = 'Closed' THEN NULL
                      ELSE closed_at
                    END
                WHERE id = %s
                """,
                [
                    "Open",
                    "",
                    next_sla_status,
                    json.dumps(updated_ticket_metadata),
                    *get_ticket_state_column_params(ticket_state_columns),
                    ticket["id"],
                ],
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
