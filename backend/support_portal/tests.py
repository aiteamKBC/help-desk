import base64
import json
import os
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib import parse as urllib_parse
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ImproperlyConfigured
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.utils import OperationalError as DjangoOperationalError
from django.core.management import call_command
from django.test import RequestFactory, SimpleTestCase, override_settings
from psycopg import OperationalError as PsycopgOperationalError
from unittest.mock import ANY, MagicMock, patch
from zoneinfo import ZoneInfo

from config import env as config_env
from support_portal import services
from support_portal import views


class DummySession(dict):
    def __init__(self, initial: dict | None = None):
        super().__init__(initial or {})
        self.cycle_key_called = False
        self.expiry = None
        self.flushed = False

    def cycle_key(self):
        self.cycle_key_called = True

    def set_expiry(self, value):
        self.expiry = value

    def flush(self):
        self.flushed = True
        self.clear()


def build_unverified_jwt(payload: dict) -> str:
    encoded_header = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode("utf-8")).decode("utf-8").rstrip("=")
    encoded_payload = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8").rstrip("=")
    return f"{encoded_header}.{encoded_payload}.signature"


class EnvLoadingTests(SimpleTestCase):
    def test_load_env_file_uses_file_value_when_existing_env_var_is_blank(self):
        with TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env.local"
            env_path.write_text("N8N_COVERAGE_TICKET_WEBHOOK_SECRET=file-secret\n", encoding="utf-8")

            with patch.dict(os.environ, {"N8N_COVERAGE_TICKET_WEBHOOK_SECRET": ""}, clear=True):
                config_env.load_env_file(env_path)

                self.assertEqual(os.environ["N8N_COVERAGE_TICKET_WEBHOOK_SECRET"], "file-secret")

    def test_load_env_file_preserves_non_empty_existing_env_var(self):
        with TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env.local"
            env_path.write_text("N8N_COVERAGE_TICKET_WEBHOOK_SECRET=file-secret\n", encoding="utf-8")

            with patch.dict(os.environ, {"N8N_COVERAGE_TICKET_WEBHOOK_SECRET": "runtime-secret"}, clear=True):
                config_env.load_env_file(env_path)

                self.assertEqual(os.environ["N8N_COVERAGE_TICKET_WEBHOOK_SECRET"], "runtime-secret")


class LearnerLookupTests(SimpleTestCase):
    def test_find_learner_by_email_returns_local_match_without_legacy_lookup(self):
        learner = {"id": 7, "full_name": "Local Learner", "email": "local@example.com", "phone": None}

        with (
            patch.object(services, "fetch_local_learner_by_email", return_value=learner) as fetch_local,
            patch.object(services, "fetch_legacy_learner_by_email") as fetch_legacy,
        ):
            result = services.find_learner_by_email("local@example.com")

        self.assertEqual(result, learner)
        fetch_local.assert_called_once_with("local@example.com")
        fetch_legacy.assert_not_called()

    def test_find_learner_by_email_syncs_legacy_match_on_local_miss(self):
        legacy_learner = {
            "external_learner_id": "123",
            "full_name": "Legacy Learner",
            "email": "legacy@example.com",
            "phone": "01000000000",
        }
        synced_learner = {"id": 8, **legacy_learner}

        with (
            patch.object(services, "fetch_local_learner_by_email", return_value=None),
            patch.object(services, "fetch_legacy_learner_by_email", return_value=legacy_learner) as fetch_legacy,
            patch.object(services, "upsert_learner_record", return_value=synced_learner) as upsert_learner,
        ):
            result = services.find_learner_by_email("legacy@example.com")

        self.assertEqual(result, synced_learner)
        fetch_legacy.assert_called_once_with("legacy@example.com")
        upsert_learner.assert_called_once_with(
            legacy_learner,
            source="legacy_kbc_users_data",
            metadata={"legacy_source": "kbc_users_data", "synced_on_demand": True},
        )

    def test_find_kbc_learner_by_email_ignores_local_support_requester_records(self):
        local_requester_learner = {
            "id": 11,
            "full_name": "Manual Requester",
            "email": "manual@example.com",
            "source": "support_portal_requester",
            "metadata": {"managed_public_requester": True},
        }

        with (
            patch.object(services, "fetch_local_learner_by_email", return_value=local_requester_learner),
            patch.object(services, "fetch_legacy_learner_by_email", return_value=None) as fetch_legacy,
        ):
            result = services.find_kbc_learner_by_email("manual@example.com")

        self.assertIsNone(result)
        fetch_legacy.assert_called_once_with("manual@example.com")

    def test_find_kbc_learner_by_email_does_not_authorize_cached_kbc_records_without_legacy_match(self):
        cached_kbc_learner = {
            "id": 12,
            "full_name": "Cached Learner",
            "email": "cached@example.com",
            "source": "legacy_kbc_users_data",
            "metadata": {"legacy_source": "kbc_users_data"},
        }

        with (
            patch.object(services, "fetch_local_learner_by_email", return_value=cached_kbc_learner) as fetch_local,
            patch.object(services, "fetch_legacy_learner_by_email", return_value=None) as fetch_legacy,
        ):
            result = services.find_kbc_learner_by_email("cached@example.com")

        self.assertIsNone(result)
        fetch_local.assert_not_called()
        fetch_legacy.assert_called_once_with("cached@example.com")

    def test_verify_email_response_uses_synced_learner(self):
        learner = {"id": 9, "full_name": "Synced Learner", "email": "synced@example.com"}
        requester = {
            "email": "synced@example.com",
            "role": "user",
            "display_name": "Synced Learner",
            "learner": learner,
            "account": None,
        }

        with (
            patch.object(services, "resolve_public_support_requester", return_value=requester) as resolve_public_support_requester,
            patch.object(services, "find_latest_active_ticket_for_learner", return_value=None),
        ):
            response = services.get_verify_email_response({"email": "SYNCED@EXAMPLE.COM"})

        self.assertEqual(
            response,
            {
                "exists": True,
                "requesterRole": "user",
                "learner": {
                    "id": 9,
                    "fullName": "Synced Learner",
                    "email": "synced@example.com",
                },
                "message": "Email verified.",
            },
        )
        resolve_public_support_requester.assert_called_once_with("synced@example.com")

    def test_resolve_public_support_requester_accepts_entra_user_after_kbc_miss(self):
        entra_user = {
            "id": "entra-user-123",
            "displayName": "Entra User",
            "mail": "entra.user@kentbusinesscollege.com",
            "userPrincipalName": "entra.user@kentbusinesscollege.com",
            "email": "entra.user@kentbusinesscollege.com",
        }

        with (
            patch.object(services, "find_kbc_learner_by_email", return_value=None) as find_kbc_learner_by_email,
            patch.object(services, "fetch_microsoft_entra_user_by_email", return_value=entra_user) as fetch_microsoft_entra_user_by_email,
            patch.object(services, "fetch_local_learner_by_email", return_value=None) as fetch_local_learner_by_email,
        ):
            requester = services.resolve_public_support_requester("entra.user@kentbusinesscollege.com")

        self.assertEqual(requester["email"], "entra.user@kentbusinesscollege.com")
        self.assertEqual(requester["role"], "user")
        self.assertIsNone(requester["learner"])
        self.assertEqual(requester["display_name"], "Entra User")
        self.assertEqual(requester["source"], "microsoft_entra")
        self.assertEqual(requester["entra_user"], entra_user)
        find_kbc_learner_by_email.assert_called_once_with("entra.user@kentbusinesscollege.com")
        fetch_microsoft_entra_user_by_email.assert_called_once_with("entra.user@kentbusinesscollege.com")
        fetch_local_learner_by_email.assert_called_once_with("entra.user@kentbusinesscollege.com")

    def test_ensure_public_requester_learner_creates_entra_runtime_learner(self):
        entra_user = {
            "id": "entra-user-123",
            "displayName": "Entra User",
            "mail": "entra.user@kentbusinesscollege.com",
            "userPrincipalName": "entra.user@kentbusinesscollege.com",
            "email": "entra.user@kentbusinesscollege.com",
        }
        requester = {
            "email": "entra.user@kentbusinesscollege.com",
            "role": "user",
            "display_name": "Entra User",
            "learner": None,
            "account": None,
            "entra_user": entra_user,
        }
        synced_learner = {
            "id": 44,
            "external_learner_id": "entra-user-123",
            "full_name": "Entra User",
            "email": "entra.user@kentbusinesscollege.com",
            "phone": None,
        }

        with patch.object(services, "upsert_learner_record", return_value=synced_learner) as upsert_learner_record:
            learner = services.ensure_public_requester_learner(requester)

        self.assertEqual(learner, synced_learner)
        upsert_learner_record.assert_called_once_with(
            {
                "external_learner_id": "entra-user-123",
                "support_account_id": None,
                "full_name": "Entra User",
                "email": "entra.user@kentbusinesscollege.com",
                "phone": None,
            },
            source="microsoft_entra",
            metadata={
                "microsoft_entra_requester": True,
                "entra_object_id": "entra-user-123",
                "entra_user_principal_name": "entra.user@kentbusinesscollege.com",
                "synced_on_demand": True,
            },
        )

    def test_fetch_microsoft_entra_user_by_email_returns_first_enabled_match(self):
        with (
            patch.object(
                services,
                "request_microsoft_login_graph_access_token",
                return_value=(True, True, 200, {"access_token": "graph-token"}),
            ) as request_microsoft_login_graph_access_token,
            patch.object(
                services,
                "fetch_microsoft_graph_user_by_email",
                return_value=(
                    True,
                    True,
                    200,
                    {
                        "value": [
                            {
                                "id": "entra-user-123",
                                "displayName": "Entra User",
                                "mail": "entra.user@kentbusinesscollege.com",
                                "userPrincipalName": "entra.user@kentbusinesscollege.com",
                                "accountEnabled": True,
                            }
                        ]
                    },
                ),
            ) as fetch_microsoft_graph_user_by_email,
        ):
            user = services.fetch_microsoft_entra_user_by_email("ENTRA.USER@kentbusinesscollege.com")

        self.assertEqual(user["id"], "entra-user-123")
        self.assertEqual(user["email"], "entra.user@kentbusinesscollege.com")
        request_microsoft_login_graph_access_token.assert_called_once_with()
        fetch_microsoft_graph_user_by_email.assert_called_once_with("graph-token", "entra.user@kentbusinesscollege.com")

    def test_fetch_microsoft_entra_user_by_email_returns_none_on_missing_graph_permission(self):
        with (
            patch.object(
                services,
                "request_microsoft_login_graph_access_token",
                return_value=(True, True, 200, {"access_token": "graph-token"}),
            ),
            patch.object(
                services,
                "fetch_microsoft_graph_user_by_email",
                return_value=(
                    True,
                    False,
                    403,
                    {"error": {"code": "Authorization_RequestDenied", "message": "Insufficient privileges to complete the operation."}},
                ),
            ),
        ):
            user = services.fetch_microsoft_entra_user_by_email("entra.user@kentbusinesscollege.com")

        self.assertIsNone(user)

    def test_verify_email_response_includes_existing_ticket_and_booking_summary(self):
        learner = {"id": 9, "full_name": "Synced Learner", "email": "synced@example.com"}
        requester = {
            "email": "synced@example.com",
            "role": "user",
            "display_name": "Synced Learner",
            "learner": learner,
            "account": None,
        }
        ticket = {
            "id": 77,
            "public_id": "KBC-000077",
            "category": "Technical",
            "technical_subcategory": "Teams",
            "inquiry": "Need the meeting link",
            "status": "Pending",
            "status_reason": "Awaiting support meeting",
            "assigned_team": "Support Desk",
            "sla_status": "On Track",
            "created_at": datetime(2026, 5, 10, 11, 0, tzinfo=timezone.utc),
            "metadata": {},
            "conversation_metadata": {},
        }
        booking_summary = {
            "requestedDate": "2026-05-12",
            "requestedTime": "11:30",
            "reservationConfirmed": True,
            "meetingJoinUrl": "https://teams.microsoft.com/l/meetup-join/example",
        }

        with (
            patch.object(services, "resolve_public_support_requester", return_value=requester),
            patch.object(services, "find_latest_active_ticket_for_learner", return_value=ticket),
            patch.object(services, "get_latest_ticket_booking_summary", return_value=booking_summary),
        ):
            response = services.get_verify_email_response({"email": "SYNCED@EXAMPLE.COM"})

        self.assertEqual(response["ticket"]["id"], "KBC-000077")
        self.assertEqual(response["ticket"]["status"], "Pending")
        self.assertEqual(response["ticket"]["requesterRole"], "user")
        self.assertEqual(response["bookingSummary"], booking_summary)

    def test_verify_email_response_promotes_existing_ticket_to_coach_when_coach_access_is_enabled(self):
        learner = {"id": 9, "full_name": "Coach Learner", "email": "coach@example.com"}
        requester = {
            "email": "coach@example.com",
            "role": "coach",
            "display_name": "Coach Learner",
            "learner": learner,
            "account": None,
        }
        ticket = {
            "id": 77,
            "public_id": "KBC-000077",
            "category": "Technical",
            "technical_subcategory": "Teams",
            "inquiry": "Need coach support",
            "status": "Open",
            "status_reason": "",
            "assigned_agent_id": None,
            "assigned_team": "Unassigned",
            "sla_status": "Pending Review",
            "created_at": datetime(2026, 5, 15, 10, 0, tzinfo=timezone.utc),
            "metadata": {"requester_role": "user"},
            "conversation_status": "open",
            "conversation_metadata": {},
        }
        cursor = MagicMock()
        cursor_manager = MagicMock()
        cursor_manager.__enter__.return_value = cursor
        cursor_manager.__exit__.return_value = False
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_manager

        with (
            patch.object(services, "resolve_public_support_requester", return_value=requester),
            patch.object(services, "find_latest_active_ticket_for_learner", return_value=ticket),
            patch.object(services, "get_latest_ticket_booking_summary", return_value=None),
            patch.object(services, "connection", mock_connection),
        ):
            response = services.get_verify_email_response({"email": "COACH@EXAMPLE.COM"})

        self.assertEqual(response["ticket"]["requesterRole"], "coach")
        update_call = cursor.execute.call_args
        self.assertIn("UPDATE tickets", update_call.args[0])
        self.assertEqual(update_call.args[1][1], 77)
        updated_metadata = json.loads(update_call.args[1][0])
        self.assertEqual(updated_metadata["requester_role"], "coach")

    def test_verify_email_response_uses_managed_public_requester_account(self):
        requester = {
            "email": "coach@example.com",
            "role": "coach",
            "display_name": "Coach One",
            "learner": None,
            "account": {
                "id": 14,
                "username": "coach1",
                "full_name": "Coach One",
                "email": "coach@example.com",
                "role": "coach",
            },
        }

        with patch.object(services, "resolve_public_support_requester", return_value=requester) as resolve_public_support_requester:
            response = services.get_verify_email_response({"email": "COACH@EXAMPLE.COM"})

        self.assertEqual(
            response,
            {
                "exists": True,
                "requesterRole": "coach",
                "requesterSource": "support_portal_requester",
                "learner": {
                    "id": None,
                    "fullName": "Coach One",
                    "email": "coach@example.com",
                },
                "message": "Email verified.",
            },
        )
        resolve_public_support_requester.assert_called_once_with("coach@example.com")

    def test_resolve_public_support_requester_accepts_legacy_kbc_learner_without_managed_requester_account(self):
        learner = {"id": 22, "full_name": "Legacy Learner", "email": "legacy@example.com", "source": "legacy_kbc_users_data"}

        with (
            patch.object(services, "fetch_public_requester_account_by_email", return_value=None),
            patch.object(services, "find_kbc_learner_by_email", return_value=learner),
        ):
            result = services.resolve_public_support_requester("legacy@example.com")

        self.assertEqual(
            result,
            {
                "email": "legacy@example.com",
                "role": "user",
                "account": None,
                "learner": learner,
                "display_name": "Legacy Learner",
                "source": "kbc_users_data",
            },
        )

    def test_resolve_public_support_requester_treats_synced_support_account_as_kbc_user(self):
        learner = {
            "id": 22,
            "full_name": "Legacy Learner",
            "email": "legacy@example.com",
            "source": "legacy_kbc_users_data",
            "metadata": {"legacy_source": "kbc_users_data"},
        }
        synced_account = {
            "id": 14,
            "username": "legacy",
            "full_name": "Legacy Learner",
            "email": "legacy@example.com",
            "role": "user",
            "account_scope": "requester",
            "metadata": {
                "synced_from_learners": True,
                "provisioned_by": "sync_learners_to_support_accounts",
            },
        }

        with (
            patch.object(services, "fetch_public_requester_account_by_email", return_value=synced_account),
            patch.object(services, "find_kbc_learner_by_email", return_value=learner),
        ):
            result = services.resolve_public_support_requester("legacy@example.com")

        self.assertEqual(result["role"], "user")
        self.assertIsNone(result["account"])
        self.assertEqual(result["source"], "kbc_users_data")

    def test_resolve_public_support_requester_promotes_kbc_learner_with_coach_access(self):
        learner = {"id": 22, "full_name": "Legacy Coach", "email": "legacy@example.com", "source": "legacy_kbc_users_data"}

        with (
            patch.object(services, "fetch_public_requester_account_by_email", return_value=None),
            patch.object(services, "find_kbc_learner_by_email", return_value=learner),
            patch.object(services, "has_public_requester_coach_access", return_value=True),
        ):
            result = services.resolve_public_support_requester("legacy@example.com")

        self.assertEqual(
            result,
            {
                "email": "legacy@example.com",
                "role": "coach",
                "account": None,
                "learner": learner,
                "display_name": "Legacy Coach",
                "source": "kbc_users_data",
            },
        )

    def test_resolve_public_support_requester_rejects_email_without_kbc_or_entra_match(self):
        managed_account = {
            "id": 14,
            "username": "coach1",
            "full_name": "Coach One",
            "email": "coach@example.com",
            "role": "coach",
        }

        with (
            patch.object(services, "find_kbc_learner_by_email", return_value=None),
            patch.object(services, "fetch_microsoft_entra_user_by_email", return_value=None) as fetch_microsoft_entra_user_by_email,
            patch.object(services, "fetch_public_requester_account_by_email", return_value=managed_account) as fetch_public_requester,
        ):
            result = services.resolve_public_support_requester("coach@example.com")

        self.assertIsNone(result)
        fetch_microsoft_entra_user_by_email.assert_called_once_with("coach@example.com")
        fetch_public_requester.assert_not_called()


class ApiErrorHandlingTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_handle_api_error_returns_service_unavailable_for_django_database_errors(self):
        response = views.handle_api_error(DjangoOperationalError("database unavailable"))

        self.assertEqual(response.status_code, 503)
        self.assertJSONEqual(
            response.content.decode(),
            {"message": "The support data service is unavailable right now. Please try again in a moment."},
        )

    def test_handle_api_error_returns_service_unavailable_for_legacy_database_errors(self):
        response = views.handle_api_error(PsycopgOperationalError("legacy database unavailable"))

        self.assertEqual(response.status_code, 503)
        self.assertJSONEqual(
            response.content.decode(),
            {"message": "The support data service is unavailable right now. Please try again in a moment."},
        )

    def test_verify_email_returns_service_unavailable_when_database_is_down(self):
        request = self.factory.post(
            "/api/verify-email",
            data='{"email":"learner@example.com"}',
            content_type="application/json",
        )

        with patch.object(views, "get_verify_email_response", side_effect=DjangoOperationalError("database unavailable")):
            response = views.verify_email(request)

        self.assertEqual(response.status_code, 503)
        self.assertJSONEqual(
            response.content.decode(),
            {"message": "The support data service is unavailable right now. Please try again in a moment."},
        )


class DatabaseEnvironmentConfigTests(SimpleTestCase):
    def test_build_database_config_allows_sqlite_fallback_for_local_development(self):
        config = config_env.build_database_config("")

        self.assertEqual(config["default"]["ENGINE"], "django.db.backends.sqlite3")
        self.assertTrue(str(config["default"]["NAME"]).endswith("db.sqlite3"))

    def test_build_database_config_requires_database_url_for_production_style_settings(self):
        with self.assertRaises(ImproperlyConfigured) as error_context:
            config_env.build_database_config("", require_database_url=True)

        self.assertIn("DATABASE_URL is required", str(error_context.exception))

    def test_build_database_config_rejects_sqlite_url_for_production_style_settings(self):
        with self.assertRaises(ImproperlyConfigured) as error_context:
            config_env.build_database_config(
                "sqlite:///tmp/support.db",
                require_database_url=True,
                require_postgresql=True,
            )

        self.assertIn("target PostgreSQL", str(error_context.exception))


class CoverageOptionsTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_list_coverage_tutor_options_splits_composite_names(self):
        with patch.object(
            services,
            "run_communication_centre_query",
            return_value=[
                {"tutor_name": "Nathan"},
                {"tutor_name": "Nathan + Safiyah"},
                {"tutor_name": "Ray"},
            ],
        ):
            response = services.list_coverage_tutor_options()

        self.assertEqual(response, ["Nathan", "Ray", "Safiyah"])

    def test_list_coverage_tutor_options_can_filter_by_module(self):
        with patch.object(
            services,
            "run_communication_centre_query",
            return_value=[
                {"tutor_name": "Adey"},
                {"tutor_name": "Andrew"},
            ],
        ) as run_communication_centre_query:
            response = services.list_coverage_tutor_options("EVM")

        self.assertEqual(response, ["Adey", "Andrew"])
        run_communication_centre_query.assert_called_once()
        sql = run_communication_centre_query.call_args.args[0]
        params = run_communication_centre_query.call_args.args[1]
        self.assertIn('LOWER(TRIM("module_name")) = %s', sql)
        self.assertEqual(params, ["evm"])

    def test_list_coverage_module_options_matches_exact_and_composite_tutor_names(self):
        with patch.object(
            services,
            "run_communication_centre_query",
            return_value=[
                {
                    "module_name": "Commercial Intelligence",
                    "session_week_day": "Wednesday",
                    "session_start_time": "09:00",
                    "session_end_time": "11:00",
                    "group_name": "G1",
                    "cohort_name": "Jun 2026",
                    "end_date": "2026-09-30",
                },
                {
                    "module_name": "Completed Module",
                    "session_week_day": "Friday",
                    "session_start_time": "12:00",
                    "session_end_time": "14:00",
                    "group_name": "G2",
                    "cohort_name": "Feb 2026",
                    "end_date": "2026-01-30",
                },
                {
                    "module_name": "Martech",
                    "session_week_day": "Thursday",
                    "session_start_time": "09:00",
                    "session_end_time": "11:00",
                    "group_name": "G1",
                    "cohort_name": "Jun 2026",
                    "end_date": "",
                },
            ],
        ) as run_communication_centre_query:
            with patch.object(services.django_timezone, "localdate", return_value=datetime(2026, 6, 1).date()):
                response = services.list_coverage_module_options("Nathan")

        self.assertEqual(response, ["Commercial Intelligence", "Martech"])
        run_communication_centre_query.assert_called_once()
        sql = run_communication_centre_query.call_args.args[0]
        params = run_communication_centre_query.call_args.args[1]
        self.assertIn('regexp_split_to_table(COALESCE("Tutor_name", \'\'),', sql)
        self.assertEqual(params, ["nathan", "nathan"])

    def test_list_coverage_time_options_matches_exact_and_composite_tutor_names(self):
        with patch.object(
            services,
            "run_communication_centre_query",
            return_value=[
                {
                    "session_week_day": "wednesday",
                    "session_start_time": "09:00",
                    "session_end_time": "11:00",
                    "group_name": "G1 - Wed - 9AM",
                    "cohort_name": "Jun 2026",
                },
            ],
        ) as run_communication_centre_query:
            response = services.list_coverage_time_options("Nathan", "Martech")

        self.assertEqual(response, ["Wednesday 09:00 - 11:00 | G1 - Wed - 9AM | Jun 2026"])
        run_communication_centre_query.assert_called_once()
        sql = run_communication_centre_query.call_args.args[0]
        params = run_communication_centre_query.call_args.args[1]
        self.assertIn('regexp_split_to_table(COALESCE("Tutor_name", \'\'),', sql)
        self.assertEqual(params, ["nathan", "nathan", "martech"])

    def test_get_coverage_tutor_email_prefers_valid_match(self):
        with patch.object(
            services,
            "run_communication_centre_query",
            return_value=[
                {"tutor_email": ""},
                {"tutor_email": "Nathan.Shields@kentbusinesscollege.com"},
            ],
        ) as run_communication_centre_query:
            response = services.get_coverage_tutor_email("Nathan")

        self.assertEqual(response, "nathan.shields@kentbusinesscollege.com")
        run_communication_centre_query.assert_called_once()
        sql = run_communication_centre_query.call_args.args[0]
        params = run_communication_centre_query.call_args.args[1]
        self.assertIn('FROM public."Tutors_Modules"', sql)
        self.assertEqual(params, ["nathan", "nathan", "nathan"])

    def test_list_coverage_coach_options_returns_aptem_owner_names(self):
        with patch.object(
            services,
            "run_aptem_auto_extracting_query",
            return_value=[
                {"coach_name": "Mona Adel"},
                {"coach_name": "mona adel"},
                {"coach_name": "Youssef Samir"},
                {"coach_name": "Default Owner"},
                {"coach_name": "Enrolment Team"},
                {"coach_name": ""},
            ],
        ) as run_aptem_auto_extracting_query:
            response = services.list_coverage_coach_options()

        self.assertEqual(response, ["Mona Adel", "Youssef Samir"])
        run_aptem_auto_extracting_query.assert_called_once()
        sql = run_aptem_auto_extracting_query.call_args.args[0]
        self.assertIn("FROM public.aptem_auto_extracting", sql)
        self.assertIn('"OwnerName"', sql)

    def test_get_coverage_coach_email_prefers_valid_match(self):
        with patch.object(
            services,
            "run_aptem_auto_extracting_query",
            return_value=[
                {"coach_email": ""},
                {"coach_email": "Mona.Adel@kentbusinesscollege.com"},
            ],
        ) as run_aptem_auto_extracting_query:
            response = services.get_coverage_coach_email("Mona Adel")

        self.assertEqual(response, "mona.adel@kentbusinesscollege.com")
        run_aptem_auto_extracting_query.assert_called_once()
        sql = run_aptem_auto_extracting_query.call_args.args[0]
        params = run_aptem_auto_extracting_query.call_args.args[1]
        self.assertIn("FROM public.aptem_auto_extracting", sql)
        self.assertIn('"OwnerEmail"', sql)
        self.assertEqual(params, ["mona adel"])

    def test_get_coverage_options_response_formats_and_deduplicates_times(self):
        with patch.object(
            services,
            "run_communication_centre_query",
            return_value=[
                {
                    "session_week_day": "friday",
                    "session_start_time": "09:00",
                    "session_end_time": "11:00",
                    "group_name": "G3-Crispin-Fri-9",
                    "cohort_name": "May 2025",
                    "end_date": "2025-05-30",
                },
                {
                    "session_week_day": "friday",
                    "session_start_time": "09:00",
                    "session_end_time": "11:00",
                    "group_name": "G3-Crispin-Fri-9",
                    "cohort_name": "May 2025",
                    "end_date": "2025-05-30",
                },
                {
                    "session_week_day": "wednesday",
                    "session_start_time": "09:00",
                    "session_end_time": "11:00",
                    "group_name": "G4-Nathan-Wed-9",
                    "cohort_name": "Jun 2026",
                    "end_date": "2026-07-31",
                },
            ],
        ), patch.object(services.django_timezone, "localdate", return_value=datetime(2026, 6, 7).date()):
            response = services.get_coverage_options_response(
                {"type": "times", "tutor": "Nathan", "module": "Martech"}
            )

        self.assertEqual(
            response,
            {
                "type": "times",
                "options": [
                    "Friday 09:00 - 11:00 | G3-Crispin-Fri-9 | May 2025",
                    "Wednesday 09:00 - 11:00 | G4-Nathan-Wed-9 | Jun 2026",
                ],
                "items": [
                    {
                        "label": "Friday 09:00 - 11:00 | G3-Crispin-Fri-9 | May 2025",
                        "completed": True,
                        "endDate": "2025-05-30",
                    },
                    {
                        "label": "Wednesday 09:00 - 11:00 | G4-Nathan-Wed-9 | Jun 2026",
                        "completed": False,
                        "endDate": "2026-07-31",
                    },
                ],
            },
        )

    def test_list_coverage_session_date_options_returns_weekly_matching_dates_within_plan_window(self):
        with patch.object(
            services,
            "list_coverage_time_rows",
            return_value=[
                {
                    "session_week_day": "wednesday",
                    "session_start_time": "09:00",
                    "session_end_time": "11:00",
                    "group_name": "G1 - Wed - 9AM",
                    "cohort_name": "Jun 2026",
                    "start_date": "2026-06-01",
                    "end_date": "2026-06-30",
                },
                {
                    "session_week_day": "friday",
                    "session_start_time": "09:00",
                    "session_end_time": "11:00",
                    "group_name": "G3 - Fri - 9AM",
                    "cohort_name": "Jun 2026",
                    "start_date": "2026-06-01",
                    "end_date": "2026-06-30",
                },
            ],
        ), patch.object(services.django_timezone, "localdate", return_value=datetime(2026, 6, 7).date()):
            response = services.list_coverage_session_date_options(
                "Nathan",
                "Martech",
                "Wednesday 09:00 - 11:00 | G1 - Wed - 9AM | Jun 2026",
            )

        self.assertEqual(
            response,
            [
                "Wednesday 10 Jun 2026",
                "Wednesday 17 Jun 2026",
                "Wednesday 24 Jun 2026",
            ],
        )

    def test_list_coverage_session_date_options_returns_empty_for_completed_group(self):
        with patch.object(
            services,
            "list_coverage_time_rows",
            return_value=[
                {
                    "session_week_day": "friday",
                    "session_start_time": "09:00",
                    "session_end_time": "11:00",
                    "group_name": "G2 - Fri - 9AM",
                    "cohort_name": "May 2025",
                    "start_date": "2025-05-01",
                    "end_date": "2025-05-30",
                },
            ],
        ), patch.object(services.django_timezone, "localdate", return_value=datetime(2026, 6, 7).date()):
            response = services.list_coverage_session_date_options(
                "Karim Hatem",
                "PMI SP 14",
                "Friday 09:00 - 11:00 | G2 - Fri - 9AM | May 2025",
            )

        self.assertEqual(response, [])

    def test_get_coverage_options_response_returns_session_dates(self):
        with patch.object(
            services,
            "list_coverage_session_date_options",
            return_value=["Wednesday 10 Jun 2026", "Wednesday 17 Jun 2026"],
        ) as list_coverage_session_date_options:
            response = services.get_coverage_options_response(
                {
                    "type": "session-dates",
                    "tutor": "Nathan",
                    "module": "Martech",
                    "time": "Wednesday 09:00 - 11:00 | G1 - Wed - 9AM | Jun 2026",
                }
            )

        self.assertEqual(
            response,
            {
                "type": "session-dates",
                "options": ["Wednesday 10 Jun 2026", "Wednesday 17 Jun 2026"],
            },
        )
        list_coverage_session_date_options.assert_called_once_with(
            "Nathan",
            "Martech",
            "Wednesday 09:00 - 11:00 | G1 - Wed - 9AM | Jun 2026",
        )

    def test_get_coverage_options_response_returns_tutor_availability_from_training_plan(self):
        with patch.object(
            services,
            "run_communication_centre_query",
            return_value=[
                {
                    "tutor_name": "Ray",
                    "module_name": "APM",
                    "session_week_day": "Thursday",
                    "session_start_time": "09:00",
                    "session_end_time": "11:00",
                    "group_name": "G1",
                    "cohort_name": "Jun 2026",
                    "start_date": "2026-06-04",
                    "end_date": "2026-06-25",
                    "sessions_number": "4",
                },
                {
                    "tutor_name": "Amgad",
                    "module_name": "Martech",
                    "session_week_day": "Friday",
                    "session_start_time": "09:00",
                    "session_end_time": "11:00",
                    "group_name": "G2",
                    "cohort_name": "Jun 2026",
                    "start_date": "2026-06-05",
                    "end_date": "2026-06-26",
                    "sessions_number": "4",
                },
            ],
        ):
            response = services.get_coverage_options_response(
                {
                    "type": "tutor-availability",
                    "time": "Thursday 09:00 - 11:00 | G1 - Thu - 9AM",
                    "sessionDates": "Thursday 18 Jun 2026",
                }
            )

        items_by_tutor = {item["tutor"]: item for item in response["items"]}
        self.assertEqual(items_by_tutor["Ray"]["status"], "busy")
        self.assertEqual(items_by_tutor["Ray"]["label"], "Busy")
        self.assertEqual(items_by_tutor["Ray"]["conflicts"][0]["moduleName"], "APM")
        self.assertEqual(items_by_tutor["Ray"]["conflicts"][0]["date"], "2026-06-18")
        self.assertEqual(items_by_tutor["Amgad"]["status"], "available")

    def test_tutor_availability_uses_sessions_number_when_end_date_is_missing(self):
        items = services.build_coverage_tutor_availability_items(
            [
                {
                    "tutor_name": "Andrew",
                    "module_name": "EVM",
                    "session_week_day": "Thursday",
                    "session_start_time": "09:00",
                    "session_end_time": "11:00",
                    "group_name": "G1",
                    "cohort_name": "Jun 2026",
                    "start_date": "2026-06-04",
                    "end_date": "",
                    "sessions_number": "3",
                }
            ],
            time_label="Thursday 09:00 - 11:00",
            session_dates="Thursday 18 Jun 2026",
        )

        self.assertEqual(items[0]["tutor"], "Andrew")
        self.assertEqual(items[0]["status"], "busy")
        self.assertEqual(items[0]["conflicts"][0]["endDate"], "2026-06-18")

    def test_get_coverage_options_response_returns_tutor_email_value(self):
        with patch.object(
            services,
            "get_coverage_tutor_email",
            return_value="nathan.shields@kentbusinesscollege.com",
        ) as get_coverage_tutor_email:
            response = services.get_coverage_options_response(
                {"type": "tutor-email", "tutor": "Nathan"}
            )

        self.assertEqual(
            response,
            {
                "type": "tutor-email",
                "value": "nathan.shields@kentbusinesscollege.com",
            },
        )
        get_coverage_tutor_email.assert_called_once_with("Nathan")

    def test_get_coverage_options_response_returns_coach_email_value(self):
        with patch.object(
            services,
            "get_coverage_coach_email",
            return_value="mona.adel@kentbusinesscollege.com",
        ) as get_coverage_coach_email:
            response = services.get_coverage_options_response(
                {"type": "coach-email", "coach": "Mona Adel"}
            )

        self.assertEqual(
            response,
            {
                "type": "coach-email",
                "value": "mona.adel@kentbusinesscollege.com",
            },
        )
        get_coverage_coach_email.assert_called_once_with("Mona Adel")

    def test_coverage_options_view_returns_json_payload(self):
        request = self.factory.get("/api/coverage-options?type=tutors")

        with patch.object(
            views,
            "get_coverage_options_response",
            return_value={"type": "tutors", "options": ["Nathan", "Ray"]},
        ) as get_coverage_options_response:
            response = views.coverage_options(request)

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(
            response.content.decode(),
            {"type": "tutors", "options": ["Nathan", "Ray"]},
        )
        get_coverage_options_response.assert_called_once_with({"type": "tutors"})


class CoverageTutorResponsePageTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_coverage_tutor_response_result_shows_accepted_message_without_processing(self):
        request = self.factory.get("/coverage/tutor-response/result?action=accept")

        response = views.coverage_tutor_response_result(request)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn("Response Recorded", content)
        self.assertIn("accepted", content.lower())

    def test_coverage_tutor_response_result_shows_generic_preview_message(self):
        request = self.factory.get("/coverage/tutor-response/result")

        response = views.coverage_tutor_response_result(request)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn("Tutor Response", content)
        self.assertIn("workflow completes", content)

    def test_coverage_tutor_response_get_shows_already_recorded_message(self):
        request = self.factory.get(
            "/coverage/tutor-response?action=refuse&ticketId=KBC-000052&cardId=card-1&responseToken=token-1"
        )

        with patch.object(
            views,
            "process_coverage_tutor_response",
            return_value={
                "ticket": {"id": "KBC-000052"},
                "coverageTutorResponseAlreadyRecorded": True,
                "recordedCoverageTutorResponseOutcome": "accepted",
                "requestedCoverageTutorResponseOutcome": "rejected",
            },
        ):
            response = views.coverage_tutor_response(request)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn("Decision Locked", content)
        self.assertIn("original response was ACCEPTED", content)
        self.assertIn("no new decision was recorded", content)


class AdminSessionViewTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def attach_session(self, request, session_payload: dict | None = None) -> DummySession:
        session = DummySession(session_payload)
        request.session = session
        return session

    def test_admin_login_stores_server_managed_session(self):
        request = self.factory.post(
            "/api/admin/login",
            data=json.dumps({"username": "omar1", "password": "omar1", "instanceId": "instance-1"}),
            content_type="application/json",
        )
        session = self.attach_session(request)

        with patch.object(
            views,
            "get_admin_login_response",
            return_value={
                "admin": {
                    "id": 4,
                    "username": "omar1",
                    "fullName": "Omar One",
                    "email": None,
                    "role": "admin",
                    "consoleStatus": "Off",
                },
                "message": "Login successful.",
            },
        ):
            response = views.admin_login(request)

        payload = json.loads(response.content.decode())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(session.cycle_key_called)
        self.assertEqual(session[views.ADMIN_SESSION_KEY]["username"], "omar1")
        self.assertEqual(session[views.ADMIN_SESSION_KEY]["instanceId"], "instance-1")
        self.assertEqual(payload["admin"]["instanceId"], "instance-1")

    def test_admin_microsoft_login_redirects_to_authorize_url_and_stores_oauth_state(self):
        request = self.factory.get("/api/admin/microsoft/login?origin=http://127.0.0.1:3000")
        session = self.attach_session(request)

        with (
            patch.object(views.settings, "AZURE_LOGIN_REDIRECT_URI", "http://localhost:3000/api/admin/microsoft/callback"),
            patch.object(views.settings, "CSRF_TRUSTED_ORIGINS", ["http://127.0.0.1:3000"]),
            patch.object(
                views,
                "build_microsoft_admin_authorize_url",
                return_value="https://login.microsoftonline.com/example/oauth2/v2.0/authorize?state=test-state",
            ) as build_microsoft_admin_authorize_url,
        ):
            response = views.admin_microsoft_login(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "https://login.microsoftonline.com/example/oauth2/v2.0/authorize?state=test-state")
        self.assertIn(views.ADMIN_MICROSOFT_AUTH_SESSION_KEY, session)
        self.assertEqual(
            session[views.ADMIN_MICROSOFT_AUTH_SESSION_KEY]["redirectUri"],
            "http://localhost:3000/api/admin/microsoft/callback",
        )
        build_microsoft_admin_authorize_url.assert_called_once()

    def test_admin_microsoft_callback_stores_admin_session_and_redirects_to_dashboard(self):
        request = self.factory.get("/api/admin/microsoft/callback?state=state-1&code=auth-code-1")
        session = self.attach_session(
            request,
            {
                views.ADMIN_MICROSOFT_AUTH_SESSION_KEY: {
                    "state": "state-1",
                    "nonce": "nonce-1",
                    "redirectUri": "http://localhost:3000/api/admin/microsoft/callback",
                }
            },
        )

        with patch.object(
            views,
            "get_admin_microsoft_login_response",
            return_value={
                "admin": {
                    "id": 23,
                    "username": "omar1",
                    "fullName": "Omar One",
                    "email": "omar1@kentbusinesscollege.com",
                    "role": "admin",
                    "consoleStatus": "Off",
                },
                "message": "Microsoft sign-in successful.",
            },
        ) as get_admin_microsoft_login_response:
            response = views.admin_microsoft_callback(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/admin")
        self.assertTrue(session.cycle_key_called)
        self.assertEqual(session[views.ADMIN_SESSION_KEY]["username"], "omar1")
        self.assertNotIn(views.ADMIN_MICROSOFT_AUTH_SESSION_KEY, session)
        get_admin_microsoft_login_response.assert_called_once()

    def test_admin_session_returns_authenticated_admin_from_server_session(self):
        request = self.factory.get("/api/admin/session")
        self.attach_session(
            request,
            {
                views.ADMIN_SESSION_KEY: {
                    "id": 4,
                    "username": "omar1",
                    "fullName": "Omar One",
                    "email": None,
                    "role": "admin",
                    "instanceId": "instance-1",
                }
            },
        )

        with patch.object(
            views,
            "require_agent_session_actor",
            return_value={
                "id": 4,
                "username": "omar1",
                "full_name": "Omar One",
                "email": None,
                "role": "admin",
                "metadata": {},
            },
        ), patch.object(views, "get_open_assigned_live_chat_agent_ids", return_value=set()):
            response = views.admin_session(request)

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(
            response.content.decode(),
            {
                "admin": {
                    "id": 4,
                    "username": "omar1",
                    "fullName": "Omar One",
                    "email": None,
                    "role": "admin",
                    "instanceId": "instance-1",
                    "sessionActive": False,
                    "consoleStatus": "Off",
                    "selectedConsoleStatus": "Off",
                    "legacySupportAccess": False,
                    "legacyOperationsAccess": False,
                    "legacyAdminAccess": False,
                    "entraDirectoryAdmin": False,
                    "teamAccess": [],
                    "teamAccessKeys": [],
                }
            },
        )
        self.assertIn("csrftoken", response.cookies)

    def test_admin_session_returns_dynamic_team_access(self):
        request = self.factory.get("/api/admin/session")
        self.attach_session(
            request,
            {
                views.ADMIN_SESSION_KEY: {
                    "id": 4,
                    "username": "omar1",
                    "fullName": "Omar One",
                    "email": None,
                    "role": "agent",
                    "instanceId": "instance-1",
                }
            },
        )
        actor = {
            "id": 4,
            "username": "omar1",
            "full_name": "Omar One",
            "email": None,
            "role": "agent",
            "metadata": {},
        }
        actor_with_team_access = {
            **actor,
            "team_access": [
                {
                    "key": "curriculum",
                    "name": "Curriculum Team",
                    "assignedTeam": "Curriculum Team",
                    "label": "Curriculum Team",
                    "canReceiveTickets": True,
                }
            ],
        }

        with (
            patch.object(views, "require_agent_session_actor", return_value=actor),
            patch.object(views, "attach_account_team_access", return_value=[actor_with_team_access]),
            patch.object(views, "get_open_assigned_live_chat_agent_ids", return_value=set()),
        ):
            response = views.admin_session(request)

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode())
        self.assertEqual(payload["admin"]["teamAccessKeys"], ["curriculum"])
        self.assertEqual(
            payload["admin"]["teamAccess"],
            [
                {
                    "key": "curriculum",
                    "name": "Curriculum Team",
                    "assignedTeam": "Curriculum Team",
                    "label": "Curriculum Team",
                    "canReceiveTickets": True,
                }
            ],
        )

    def test_admin_session_heartbeat_returns_server_managed_admin_identity(self):
        request = self.factory.post(
            "/api/admin/session-heartbeat",
            data=json.dumps({"consoleStatus": "Available", "actorUsername": "attacker", "instanceId": "stale-instance"}),
            content_type="application/json",
        )
        self.attach_session(
            request,
            {
                views.ADMIN_SESSION_KEY: {
                    "id": 4,
                    "username": "omar1",
                    "fullName": "Omar One",
                    "email": None,
                    "role": "admin",
                    "instanceId": "instance-1",
                }
            },
        )

        actor = {
            "id": 4,
            "username": "omar1",
            "full_name": "Omar One",
            "email": None,
            "role": "admin",
            "metadata": {},
        }

        with (
            patch.object(views, "require_agent_session_actor", side_effect=[actor, actor]),
            patch.object(views, "get_open_assigned_live_chat_agent_ids", return_value=set()),
            patch.object(
                views,
                "heartbeat_agent_session",
                return_value={"ok": True, "sessionActive": True, "sessionReplaced": False},
            ) as heartbeat_agent_session,
        ):
            response = views.admin_session_heartbeat(request)

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(
            response.content.decode(),
            {
                "ok": True,
                "sessionActive": True,
                "sessionReplaced": False,
                "admin": {
                    "id": 4,
                    "username": "omar1",
                    "fullName": "Omar One",
                    "email": None,
                    "role": "admin",
                    "instanceId": "instance-1",
                    "sessionActive": False,
                    "consoleStatus": "Off",
                    "selectedConsoleStatus": "Off",
                    "legacySupportAccess": False,
                    "legacyOperationsAccess": False,
                    "legacyAdminAccess": False,
                    "entraDirectoryAdmin": False,
                    "teamAccess": [],
                    "teamAccessKeys": [],
                },
            },
        )
        heartbeat_agent_session.assert_called_once_with(
            {
                "actorUsername": "omar1",
                "instanceId": "instance-1",
                "consoleStatus": "Available",
            }
        )

    def test_admin_tickets_requires_server_session(self):
        request = self.factory.get("/api/admin/tickets")
        self.attach_session(
            request,
            {
                views.ADMIN_SESSION_KEY: {
                    "id": 7,
                    "username": "admin1",
                    "fullName": "Admin One",
                    "email": None,
                    "role": "agent",
                    "instanceId": "instance-1",
                }
            },
        )

        with (
            patch.object(
                views,
                "require_agent_session_actor",
                return_value={
                    "id": 7,
                    "username": "admin1",
                    "full_name": "Admin One",
                    "email": None,
                    "role": "agent",
                },
            ) as require_agent_session_actor,
            patch.object(views, "list_admin_tickets", return_value={"tickets": []}) as list_admin_tickets,
        ):
            response = views.admin_tickets(request)

        self.assertEqual(response.status_code, 200)
        require_agent_session_actor.assert_called_once_with(
            "admin1",
            "instance-1",
            allowed_roles=views.SUPPORT_PORTAL_ACCESS_ROLES,
        )
        list_admin_tickets.assert_called_once_with(
            {
                "id": 7,
                "username": "admin1",
                "full_name": "Admin One",
                "email": None,
                "role": "agent",
            }
        )

    def test_admin_tickets_passes_query_params_to_list_service(self):
        request = self.factory.get("/api/admin/tickets?page=2&pageSize=25&search=coach")
        self.attach_session(
            request,
            {
                views.ADMIN_SESSION_KEY: {
                    "id": 7,
                    "username": "admin1",
                    "fullName": "Admin One",
                    "email": None,
                    "role": "agent",
                    "instanceId": "instance-1",
                }
            },
        )

        actor = {
            "id": 7,
            "username": "admin1",
            "full_name": "Admin One",
            "email": None,
            "role": "agent",
        }
        with (
            patch.object(views, "require_agent_session_actor", return_value=actor),
            patch.object(views, "list_admin_tickets", return_value={"tickets": []}) as list_admin_tickets,
        ):
            response = views.admin_tickets(request)

        self.assertEqual(response.status_code, 200)
        list_admin_tickets.assert_called_once_with(
            actor,
            query_params={"page": "2", "pageSize": "25", "search": "coach"},
        )

    def test_admin_ticket_metrics_passes_query_params_to_service(self):
        request = self.factory.get("/api/admin/tickets/metrics?team=operations&dashboardFilter=coverage")
        self.attach_session(
            request,
            {
                views.ADMIN_SESSION_KEY: {
                    "id": 7,
                    "username": "admin1",
                    "fullName": "Admin One",
                    "email": None,
                    "role": "agent",
                    "instanceId": "instance-1",
                }
            },
        )

        actor = {
            "id": 7,
            "username": "admin1",
            "full_name": "Admin One",
            "email": None,
            "role": "agent",
        }
        with (
            patch.object(views, "require_agent_session_actor", return_value=actor),
            patch.object(views, "get_admin_ticket_metrics", return_value={"metrics": {"total": 0}}) as get_admin_ticket_metrics,
        ):
            response = views.admin_ticket_metrics(request)

        self.assertEqual(response.status_code, 200)
        get_admin_ticket_metrics.assert_called_once_with(
            actor,
            query_params={"team": "operations", "dashboardFilter": "coverage"},
        )

    def test_admin_accounts_get_allows_agent_session(self):
        request = self.factory.get("/api/admin/accounts")
        self.attach_session(
            request,
            {
                views.ADMIN_SESSION_KEY: {
                    "id": 7,
                    "username": "admin1",
                    "fullName": "Admin One",
                    "email": None,
                    "role": "agent",
                    "instanceId": "instance-1",
                }
            },
        )

        with (
            patch.object(
                views,
                "require_agent_session_actor",
                return_value={
                    "id": 7,
                    "username": "admin1",
                    "full_name": "Admin One",
                    "email": None,
                    "role": "agent",
                },
            ) as require_agent_session_actor,
            patch.object(views, "list_agents", return_value={"accounts": []}) as list_agents,
        ):
            response = views.admin_accounts(request)

        self.assertEqual(response.status_code, 200)
        require_agent_session_actor.assert_called_once_with(
            "admin1",
            "instance-1",
            allowed_roles=views.SUPPORT_PORTAL_ACCESS_ROLES,
        )
        list_agents.assert_called_once_with(include_inactive=True, refresh_legacy=True)

    def test_admin_accounts_get_can_skip_legacy_refresh_for_fast_local_load(self):
        request = self.factory.get("/api/admin/accounts?refreshLegacy=false")
        self.attach_session(
            request,
            {
                views.ADMIN_SESSION_KEY: {
                    "id": 7,
                    "username": "admin1",
                    "fullName": "Admin One",
                    "email": None,
                    "role": "admin",
                    "instanceId": "instance-1",
                }
            },
        )

        with (
            patch.object(
                views,
                "require_agent_session_actor",
                return_value={
                    "id": 7,
                    "username": "admin1",
                    "full_name": "Admin One",
                    "email": None,
                    "role": "admin",
                },
            ),
            patch.object(views, "list_agents", return_value={"accounts": []}) as list_agents,
        ):
            response = views.admin_accounts(request)

        self.assertEqual(response.status_code, 200)
        list_agents.assert_called_once_with(include_inactive=True, refresh_legacy=False)

    def test_admin_accounts_post_still_requires_admin_access_role(self):
        request = self.factory.post(
            "/api/admin/accounts",
            data=json.dumps({"email": "agent@example.com"}),
            content_type="application/json",
        )
        self.attach_session(
            request,
            {
                views.ADMIN_SESSION_KEY: {
                    "id": 7,
                    "username": "admin1",
                    "fullName": "Admin One",
                    "email": None,
                    "role": "admin",
                    "instanceId": "instance-1",
                }
            },
        )

        with (
            patch.object(
                views,
                "require_agent_session_actor",
                return_value={
                    "id": 7,
                    "username": "admin1",
                    "full_name": "Admin One",
                    "email": None,
                    "role": "admin",
                },
            ) as require_agent_session_actor,
            patch.object(views, "add_entra_agent", return_value={"agent": {"id": 8}}) as add_entra_agent,
        ):
            response = views.admin_accounts(request)

        self.assertEqual(response.status_code, 201)
        require_agent_session_actor.assert_called_once_with(
            "admin1",
            "instance-1",
            allowed_roles=views.ADMIN_ACCESS_ROLES,
        )
        add_entra_agent.assert_called_once_with({"email": "agent@example.com"})

    def test_admin_account_detail_patch_allows_operations_access_update(self):
        request = self.factory.patch(
            "/api/admin/accounts/24",
            data=json.dumps({"operationsAccess": True}),
            content_type="application/json",
        )
        self.attach_session(
            request,
            {
                views.ADMIN_SESSION_KEY: {
                    "id": 7,
                    "username": "admin1",
                    "fullName": "Admin One",
                    "email": None,
                    "role": "admin",
                    "instanceId": "instance-1",
                }
            },
        )

        with (
            patch.object(
                views,
                "require_agent_session_actor",
                return_value={
                    "id": 7,
                    "username": "admin1",
                    "full_name": "Admin One",
                    "email": None,
                    "role": "admin",
                },
            ) as require_agent_session_actor,
            patch.object(
                views,
                "update_agent_operations_access",
                return_value={"id": 24, "legacyOperationsAccess": True},
            ) as update_agent_operations_access,
        ):
            response = views.admin_account_detail(request, 24)

        self.assertEqual(response.status_code, 200)
        require_agent_session_actor.assert_called_once_with(
            "admin1",
            "instance-1",
            allowed_roles=views.ADMIN_ACCESS_ROLES,
        )
        update_agent_operations_access.assert_called_once_with(24, operations_access=True)

    def test_admin_ticket_detail_uses_server_session_actor_for_updates(self):
        request = self.factory.patch(
            "/api/admin/tickets/KBC-000001",
            data=json.dumps({"note": "Resolved", "actorUsername": "attacker", "instanceId": "stale-instance"}),
            content_type="application/json",
        )
        self.attach_session(
            request,
            {
                views.ADMIN_SESSION_KEY: {
                    "id": 9,
                    "username": "fatma",
                    "fullName": "Fatma Queue",
                    "email": "fatma@example.com",
                    "role": "admin",
                    "instanceId": "current-instance",
                }
            },
        )

        with (
            patch.object(
                views,
                "require_agent_session_actor",
                return_value={
                    "id": 9,
                    "username": "fatma",
                    "full_name": "Fatma Queue",
                    "email": "fatma@example.com",
                    "role": "admin",
                },
            ),
            patch.object(views, "update_admin_ticket", return_value={"ticket": {"id": "KBC-000001"}}) as update_admin_ticket,
        ):
            response = views.admin_ticket_detail(request, "KBC-000001")

        self.assertEqual(response.status_code, 200)
        update_admin_ticket.assert_called_once_with(
            "KBC-000001",
            {
                "note": "Resolved",
                "actorUsername": "fatma",
                "instanceId": "current-instance",
            },
            uploaded_files=[],
        )

    def test_admin_ticket_chat_history_uses_server_session_actor(self):
        request = self.factory.post(
            "/api/admin/tickets/KBC-000001/chat-history",
            data=json.dumps(
                {
                    "status": "Open",
                    "actorUsername": "attacker",
                    "messages": [{"sender": "agent", "text": "Hello"}],
                }
            ),
            content_type="application/json",
        )
        self.attach_session(
            request,
            {
                views.ADMIN_SESSION_KEY: {
                    "id": 9,
                    "username": "fatma",
                    "fullName": "Fatma Queue",
                    "email": "fatma@example.com",
                    "role": "admin",
                    "instanceId": "current-instance",
                }
            },
        )

        with (
            patch.object(
                views,
                "require_agent_session_actor",
                return_value={
                    "id": 9,
                    "username": "fatma",
                    "full_name": "Fatma Queue",
                    "email": "fatma@example.com",
                    "role": "admin",
                },
            ),
            patch.object(views, "save_chat_history", return_value={"ok": True}) as save_chat_history,
        ):
            response = views.admin_ticket_chat_history(request, "KBC-000001")

        self.assertEqual(response.status_code, 200)
        save_chat_history.assert_called_once()
        self.assertEqual(
            save_chat_history.call_args.args,
            (
                "KBC-000001",
                {
                    "status": "Open",
                    "actorUsername": "fatma",
                    "instanceId": "current-instance",
                    "messages": [{"sender": "agent", "text": "Hello"}],
                },
            ),
        )
        self.assertEqual(save_chat_history.call_args.kwargs["uploaded_files"], [])

    def test_admin_ticket_chat_history_accepts_multipart_attachments_and_uses_server_session_actor(self):
        uploaded_file = SimpleUploadedFile("chat-proof.png", b"png", content_type="image/png")
        request = self.factory.post(
            "/api/admin/tickets/KBC-000001/chat-history",
            data={
                "status": "Open",
                "actorUsername": "attacker",
                "messages": json.dumps([{"sender": "agent", "text": "", "attachments": [{"clientAttachmentId": "att-1", "name": "chat-proof.png", "size": 3}]}]),
                "attachmentFiles": uploaded_file,
            },
        )
        self.attach_session(
            request,
            {
                views.ADMIN_SESSION_KEY: {
                    "id": 9,
                    "username": "fatma",
                    "fullName": "Fatma Queue",
                    "email": "fatma@example.com",
                    "role": "admin",
                    "instanceId": "current-instance",
                }
            },
        )

        with (
            patch.object(
                views,
                "require_agent_session_actor",
                return_value={
                    "id": 9,
                    "username": "fatma",
                    "full_name": "Fatma Queue",
                    "email": "fatma@example.com",
                    "role": "admin",
                },
            ),
            patch.object(views, "save_chat_history", return_value={"ok": True}) as save_chat_history,
        ):
            response = views.admin_ticket_chat_history(request, "KBC-000001")

        self.assertEqual(response.status_code, 200)
        save_chat_history.assert_called_once()
        self.assertEqual(
            save_chat_history.call_args.args,
            (
                "KBC-000001",
                {
                    "status": "Open",
                    "actorUsername": "fatma",
                    "instanceId": "current-instance",
                    "messages": [{"sender": "agent", "text": "", "attachments": [{"clientAttachmentId": "att-1", "name": "chat-proof.png", "size": 3}]}],
                },
            ),
        )
        uploaded_files = save_chat_history.call_args.kwargs["uploaded_files"]
        self.assertEqual(len(uploaded_files), 1)
        self.assertEqual(uploaded_files[0].name, "chat-proof.png")


class TicketAttachmentUploadTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_tickets_create_accepts_multipart_attachment_uploads(self):
        uploaded_file = SimpleUploadedFile("evidence.png", b"png", content_type="image/png")
        request = self.factory.post(
            "/api/tickets",
            data={
                "email": "learner@example.com",
                "requesterRole": "user",
                "category": "Technical",
                "technicalSubcategory": "Teams",
                "inquiry": "Need help with Teams.",
                "evidenceFiles": uploaded_file,
            },
        )

        with patch.object(views, "create_ticket", return_value={"ticket": {"id": "KBC-000001"}}) as create_ticket:
            response = views.tickets_create(request)

        self.assertEqual(response.status_code, 201)
        create_ticket.assert_called_once()
        payload = create_ticket.call_args.args[0]
        uploaded_files = create_ticket.call_args.kwargs["uploaded_files"]
        self.assertEqual(payload["email"], "learner@example.com")
        self.assertEqual(payload["technicalSubcategory"], "Teams")
        self.assertEqual(len(uploaded_files), 1)
        self.assertEqual(uploaded_files[0].name, "evidence.png")

    def test_tickets_update_accepts_multipart_attachment_uploads_via_post(self):
        uploaded_file = SimpleUploadedFile("evidence.pdf", b"%PDF-1.7", content_type="application/pdf")
        request = self.factory.post(
            "/api/tickets/KBC-000001",
            data={
                "category": "Technical",
                "technicalSubcategory": "Teams",
                "inquiry": "Updated inquiry details.",
                "evidenceFiles": uploaded_file,
            },
        )

        with patch.object(views, "update_ticket", return_value={"ticket": {"id": "KBC-000001"}}) as update_ticket:
            response = views.tickets_update(request, "KBC-000001")

        self.assertEqual(response.status_code, 200)
        update_ticket.assert_called_once()
        self.assertEqual(update_ticket.call_args.args[0], "KBC-000001")
        self.assertEqual(update_ticket.call_args.args[1]["inquiry"], "Updated inquiry details.")
        uploaded_files = update_ticket.call_args.kwargs["uploaded_files"]
        self.assertEqual(len(uploaded_files), 1)
        self.assertEqual(uploaded_files[0].name, "evidence.pdf")

    def test_ticket_chat_history_accepts_multipart_attachment_uploads(self):
        uploaded_file = SimpleUploadedFile("chat-proof.png", b"png", content_type="image/png")
        request = self.factory.post(
            "/api/tickets/KBC-000001/chat-history",
            data={
                "status": "Open",
                "messages": json.dumps([{"sender": "user", "text": "", "attachments": [{"clientAttachmentId": "att-1", "name": "chat-proof.png", "size": 3}]}]),
                "attachmentFiles": uploaded_file,
            },
        )

        with patch.object(views, "save_chat_history", return_value={"ok": True}) as save_chat_history:
            response = views.ticket_chat_history(request, "KBC-000001")

        self.assertEqual(response.status_code, 200)
        save_chat_history.assert_called_once()
        self.assertEqual(
            save_chat_history.call_args.args,
            (
                "KBC-000001",
                {
                    "status": "Open",
                    "messages": [{"sender": "user", "text": "", "attachments": [{"clientAttachmentId": "att-1", "name": "chat-proof.png", "size": 3}]}],
                },
            ),
        )
        uploaded_files = save_chat_history.call_args.kwargs["uploaded_files"]
        self.assertEqual(len(uploaded_files), 1)
        self.assertEqual(uploaded_files[0].name, "chat-proof.png")

    def test_ticket_chatbot_message_accepts_multipart_attachment_uploads(self):
        uploaded_file = SimpleUploadedFile("chat-proof.png", b"png", content_type="image/png")
        request = self.factory.post(
            "/api/tickets/KBC-000001/chatbot-message",
            data={
                "message": "",
                "clientTimeZone": "Africa/Cairo",
                "messages": json.dumps([{"sender": "user", "text": "", "attachments": [{"clientAttachmentId": "att-1", "name": "chat-proof.png", "size": 3}]}]),
                "attachmentFiles": uploaded_file,
            },
        )

        with patch.object(views, "send_chatbot_message", return_value={"ok": True}) as send_chatbot_message:
            response = views.ticket_chatbot_message(request, "KBC-000001")

        self.assertEqual(response.status_code, 200)
        send_chatbot_message.assert_called_once()
        self.assertEqual(
            send_chatbot_message.call_args.args,
            (
                "KBC-000001",
                {
                    "message": "",
                    "clientTimeZone": "Africa/Cairo",
                    "messages": [{"sender": "user", "text": "", "attachments": [{"clientAttachmentId": "att-1", "name": "chat-proof.png", "size": 3}]}],
                },
            ),
        )
        uploaded_files = send_chatbot_message.call_args.kwargs["uploaded_files"]
        self.assertEqual(len(uploaded_files), 1)
        self.assertEqual(uploaded_files[0].name, "chat-proof.png")


class SupportSessionValidationTests(SimpleTestCase):
    databases = {"default"}

    def test_uploaded_ticket_attachments_accept_powerpoint_files(self):
        uploaded_file = SimpleUploadedFile(
            "coverage-plan.pptx",
            b"pptx",
            content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )

        with TemporaryDirectory() as temp_dir, patch.object(services, "get_support_attachment_root", return_value=Path(temp_dir)):
            attachment = services.store_uploaded_ticket_attachment("KBC-000071", uploaded_file)

            self.assertEqual(attachment["name"], "coverage-plan.pptx")
            self.assertEqual(
                attachment["mimeType"],
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )
            self.assertTrue(attachment["storageKey"].endswith(".pptx"))
            self.assertTrue((Path(temp_dir) / attachment["storageKey"]).exists())

    def test_create_ticket_persists_uploaded_attachment_storage_key(self):
        requester = {
            "email": "employer@example.com",
            "role": "employer",
            "display_name": "Employer One",
            "learner": None,
            "account": {
                "id": 21,
                "username": "employer1",
                "full_name": "Employer One",
                "email": "employer@example.com",
                "role": "employer",
            },
        }
        learner = {
            "id": 11,
            "full_name": "Employer One",
            "email": "employer@example.com",
            "phone": None,
        }
        cursor = MagicMock()
        cursor_manager = MagicMock()
        cursor_manager.__enter__.return_value = cursor
        cursor_manager.__exit__.return_value = False
        stored_attachment = {
            "name": "evidence.png",
            "mimeType": "image/png",
            "size": 3,
            "storageKey": "KBC-000071/2026/05/evidence.png",
            "metadata": {"storage": "local_filesystem"},
        }

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "resolve_public_support_requester", return_value=requester),
            patch.object(services, "ensure_public_requester_learner", return_value=learner),
            patch.object(services, "dictfetchone", side_effect=[{"id": 71, "status": "Open", "assigned_team": "Unassigned", "sla_status": "Pending Review", "created_at": datetime(2026, 5, 14, 10, 0, tzinfo=timezone.utc)}, {"id": 88}]),
            patch.object(services, "build_public_ticket_id", return_value="KBC-000071"),
            patch.object(services, "store_uploaded_ticket_attachments", return_value=[stored_attachment]),
            patch.object(services, "insert_history_event"),
            patch.object(services.connection, "cursor", return_value=cursor_manager),
        ):
            services.create_ticket(
                {
                    "email": "employer@example.com",
                    "category": "Technical",
                    "technicalSubcategory": "Teams",
                    "inquiry": "Need urgent employer support.",
                    "evidence": [],
                },
                uploaded_files=[SimpleUploadedFile("evidence.png", b"png", content_type="image/png")],
            )

        ticket_insert_call = next(
            call for call in cursor.execute.call_args_list
            if "INSERT INTO tickets" in call.args[0]
        )
        ticket_insert_params = ticket_insert_call.args[1]
        self.assertEqual(ticket_insert_params[8], 1)

        attachment_insert_call = next(
            call for call in cursor.execute.call_args_list
            if "INSERT INTO ticket_attachments" in call.args[0]
        )
        attachment_insert_params = attachment_insert_call.args[1]
        self.assertEqual(attachment_insert_params[1], "evidence.png")
        self.assertEqual(attachment_insert_params[4], "KBC-000071/2026/05/evidence.png")

    def test_create_ticket_accepts_others_technical_subcategory(self):
        requester = {
            "email": "learner@example.com",
            "role": "user",
            "display_name": "Learner One",
            "learner": None,
            "account": {
                "id": 31,
                "username": "learner1",
                "full_name": "Learner One",
                "email": "learner@example.com",
                "role": "user",
            },
        }
        learner = {
            "id": 12,
            "full_name": "Learner One",
            "email": "learner@example.com",
            "phone": None,
        }
        cursor = MagicMock()
        cursor_manager = MagicMock()
        cursor_manager.__enter__.return_value = cursor
        cursor_manager.__exit__.return_value = False

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "resolve_public_support_requester", return_value=requester),
            patch.object(services, "ensure_public_requester_learner", return_value=learner),
            patch.object(
                services,
                "dictfetchone",
                side_effect=[
                    {
                        "id": 72,
                        "status": "Open",
                        "assigned_team": "Unassigned",
                        "sla_status": "Pending Review",
                        "created_at": datetime(2026, 5, 23, 17, 0, tzinfo=timezone.utc),
                    },
                    {"id": 89},
                ],
            ),
            patch.object(services, "build_public_ticket_id", return_value="KBC-000072"),
            patch.object(services, "insert_history_event"),
            patch.object(services, "notify_coverage_ticket_operations_team") as notify_operations_team,
            patch.object(services.connection, "cursor", return_value=cursor_manager),
        ):
            response = services.create_ticket(
                {
                    "email": "learner@example.com",
                    "category": "Technical",
                    "technicalSubcategory": "Others",
                    "inquiry": "I need support with a different platform.",
                    "evidence": [],
                }
            )

        self.assertEqual(response["ticket"]["technicalSubcategory"], "Others")
        ticket_insert_call = next(
            call for call in cursor.execute.call_args_list
            if "INSERT INTO tickets" in call.args[0]
        )
        ticket_insert_params = ticket_insert_call.args[1]
        self.assertEqual(ticket_insert_params[3], "Others")
        ticket_metadata = json.loads(ticket_insert_params[9])
        self.assertEqual(ticket_metadata["technical_subcategory"], "Others")
        ticket_update_call = next(
            call for call in cursor.execute.call_args_list
            if "UPDATE tickets" in call.args[0] and "SET public_id" in call.args[0]
        )
        persisted_metadata = json.loads(ticket_update_call.args[1][3])
        self.assertEqual(
            persisted_metadata["pending_support_queue_notification"]["ticketId"],
            "KBC-000072",
        )
        self.assertEqual(
            persisted_metadata["pending_support_queue_notification"]["reason"],
            "support_ticket_created",
        )
        self.assertNotIn("pending_coverage_ticket_notification", persisted_metadata)
        notify_operations_team.assert_not_called()

    def test_create_ticket_accepts_coverage_for_entra_requester(self):
        requester = {
            "email": "entra.user@kentbusinesscollege.com",
            "role": "user",
            "display_name": "Entra User",
            "learner": None,
            "account": None,
            "entra_user": {
                "id": "entra-user-1",
                "displayName": "Entra User",
                "userPrincipalName": "entra.user@kentbusinesscollege.com",
            },
            "source": "microsoft_entra",
        }
        learner = {
            "id": 12,
            "full_name": "Entra User",
            "email": "entra.user@kentbusinesscollege.com",
            "phone": None,
        }
        cursor = MagicMock()
        cursor_manager = MagicMock()
        cursor_manager.__enter__.return_value = cursor
        cursor_manager.__exit__.return_value = False

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "resolve_public_support_requester", return_value=requester),
            patch.object(services, "ensure_public_requester_learner", return_value=learner),
            patch.object(
                services,
                "dictfetchone",
                side_effect=[
                    {
                        "id": 73,
                        "status": "Open",
                        "assigned_team": "Unassigned",
                        "sla_status": "Pending Review",
                        "created_at": datetime(2026, 6, 3, 10, 0, tzinfo=timezone.utc),
                    },
                    {"id": 90},
                ],
            ),
            patch.object(services, "build_public_ticket_id", return_value="KBC-000073"),
            patch.object(services, "insert_history_event"),
            patch.object(services, "notify_coverage_ticket_operations_team") as notify_operations_team,
            patch.object(services.connection, "cursor", return_value=cursor_manager),
        ):
            response = services.create_ticket(
                {
                    "email": "entra.user@kentbusinesscollege.com",
                    "category": "Technical",
                    "technicalSubcategory": "Coverage",
                    "inquiry": (
                        "Coverage session request\n"
                        "Tutor: Amgad\n"
                        "Module: PMP 3 Months\n"
                        "Preferred Time: Friday 09:00 - 11:00 | G1-Fri-9 | Oct 2024\n"
                        "Session Date: Friday 18 Oct 2024\n"
                        "Session Number: 1\n"
                        "Session Subject: test"
                    ),
                    "evidence": [],
                }
            )

        self.assertEqual(response["ticket"]["technicalSubcategory"], "Coverage")
        self.assertEqual(response["ticket"]["requesterRole"], "user")
        self.assertEqual(response["ticket"]["requesterSource"], "microsoft_entra")
        ticket_insert_call = next(
            call for call in cursor.execute.call_args_list
            if "INSERT INTO tickets" in call.args[0]
        )
        ticket_insert_params = ticket_insert_call.args[1]
        self.assertEqual(ticket_insert_params[3], "Coverage")
        ticket_metadata = json.loads(ticket_insert_params[9])
        self.assertEqual(ticket_metadata["technical_subcategory"], "Coverage")
        self.assertEqual(ticket_metadata["requester_source"], "microsoft_entra")
        ticket_update_call = next(
            call for call in cursor.execute.call_args_list
            if "UPDATE tickets" in call.args[0] and "SET public_id" in call.args[0]
        )
        self.assertEqual(ticket_update_call.args[1][2], "On Track")
        persisted_metadata = json.loads(ticket_update_call.args[1][3])
        self.assertEqual(
            persisted_metadata["pending_coverage_ticket_notification"]["ticketId"],
            "KBC-000073",
        )
        self.assertNotIn("pending_support_queue_notification", persisted_metadata)
        notify_operations_team.assert_called_once()
        notification_ticket_id, notification_payload = notify_operations_team.call_args.args
        self.assertEqual(notification_ticket_id, 73)
        self.assertEqual(notification_payload["event"], "coverage_ticket_created")
        self.assertEqual(notification_payload["ticket"]["id"], "KBC-000073")
        self.assertEqual(notification_payload["requester"]["email"], "entra.user@kentbusinesscollege.com")
        self.assertEqual(notification_payload["coverage"]["tutor"], "Amgad")
        self.assertEqual(notification_payload["coverage"]["module"], "PMP 3 Months")
        self.assertEqual(notification_payload["coverage"]["sessions"][0]["sessionNumber"], "1")

    def test_create_ticket_rejects_coverage_for_regular_kbc_user(self):
        requester = {
            "email": "learner@example.com",
            "role": "user",
            "display_name": "Learner One",
            "learner": {
                "id": 12,
                "full_name": "Learner One",
                "email": "learner@example.com",
                "phone": None,
                "source": "legacy_kbc_users_data",
                "metadata": {"legacy_source": "kbc_users_data"},
            },
            "account": None,
            "source": "kbc_users_data",
        }

        with (
            patch.object(services, "resolve_public_support_requester", return_value=requester),
            patch.object(services, "ensure_public_requester_learner") as ensure_learner,
        ):
            with self.assertRaises(services.ApiError) as error_context:
                services.create_ticket(
                    {
                        "email": "learner@example.com",
                        "category": "Technical",
                        "technicalSubcategory": "Coverage",
                        "inquiry": "Coverage session request",
                        "evidence": [],
                    }
                )

        self.assertEqual(error_context.exception.status_code, 403)
        self.assertEqual(
            error_context.exception.message,
            "Coverage requests are not available for standard KBC learner accounts.",
        )
        ensure_learner.assert_not_called()

    def test_create_ticket_sets_high_priority_for_employer_requester(self):
        requester = {
            "email": "employer@example.com",
            "role": "employer",
            "display_name": "Employer One",
            "learner": None,
            "account": {
                "id": 21,
                "username": "employer1",
                "full_name": "Employer One",
                "email": "employer@example.com",
                "role": "employer",
            },
        }
        learner = {
            "id": 11,
            "full_name": "Employer One",
            "email": "employer@example.com",
            "phone": None,
        }
        cursor = MagicMock()
        cursor_manager = MagicMock()
        cursor_manager.__enter__.return_value = cursor
        cursor_manager.__exit__.return_value = False

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "resolve_public_support_requester", return_value=requester),
            patch.object(services, "ensure_public_requester_learner", return_value=learner),
            patch.object(services, "dictfetchone", side_effect=[{"id": 71, "status": "Open", "assigned_team": "Unassigned", "sla_status": "Pending Review", "created_at": datetime(2026, 5, 14, 10, 0, tzinfo=timezone.utc)}, {"id": 88}]),
            patch.object(services, "build_public_ticket_id", return_value="KBC-000071"),
            patch.object(services, "insert_history_event"),
            patch.object(services.connection, "cursor", return_value=cursor_manager),
        ):
            services.create_ticket(
                {
                    "email": "employer@example.com",
                    "category": "Technical",
                    "technicalSubcategory": "Teams",
                    "inquiry": "Need urgent employer support.",
                    "evidence": [],
                }
            )

        ticket_insert_call = next(
            call for call in cursor.execute.call_args_list
            if "INSERT INTO tickets" in call.args[0]
        )
        ticket_insert_params = ticket_insert_call.args[1]
        self.assertEqual(ticket_insert_params[7], "High")

    def test_create_ticket_sets_high_priority_for_coach_requester(self):
        requester = {
            "email": "coach@example.com",
            "role": "coach",
            "display_name": "Coach One",
            "learner": None,
            "account": {
                "id": 22,
                "username": "coach1",
                "full_name": "Coach One",
                "email": "coach@example.com",
                "role": "coach",
            },
        }
        learner = {
            "id": 12,
            "full_name": "Coach One",
            "email": "coach@example.com",
            "phone": None,
        }
        cursor = MagicMock()
        cursor_manager = MagicMock()
        cursor_manager.__enter__.return_value = cursor
        cursor_manager.__exit__.return_value = False

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "resolve_public_support_requester", return_value=requester),
            patch.object(services, "ensure_public_requester_learner", return_value=learner),
            patch.object(services, "dictfetchone", side_effect=[{"id": 72, "status": "Open", "assigned_team": "Unassigned", "sla_status": "Pending Review", "created_at": datetime(2026, 5, 14, 10, 0, tzinfo=timezone.utc)}, {"id": 89}]),
            patch.object(services, "build_public_ticket_id", return_value="KBC-000072"),
            patch.object(services, "insert_history_event"),
            patch.object(services.connection, "cursor", return_value=cursor_manager),
        ):
            services.create_ticket(
                {
                    "email": "coach@example.com",
                    "category": "Technical",
                    "technicalSubcategory": "Teams",
                    "inquiry": "Need coach support.",
                    "evidence": [],
                }
            )

        ticket_insert_call = next(
            call for call in cursor.execute.call_args_list
            if "INSERT INTO tickets" in call.args[0]
        )
        ticket_insert_params = ticket_insert_call.args[1]
        self.assertEqual(ticket_insert_params[7], "High")

    def test_create_ticket_does_not_auto_prepare_support_teams_call_for_coach_requester(self):
        requester = {
            "email": "coach@example.com",
            "role": "coach",
            "display_name": "Coach One",
            "learner": None,
            "account": {
                "id": 22,
                "username": "coach1",
                "full_name": "Coach One",
                "email": "coach@example.com",
                "role": "coach",
            },
        }
        learner = {
            "id": 12,
            "full_name": "Coach One",
            "email": "coach@example.com",
            "phone": None,
        }
        cursor = MagicMock()
        cursor_manager = MagicMock()
        cursor_manager.__enter__.return_value = cursor
        cursor_manager.__exit__.return_value = False

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "resolve_public_support_requester", return_value=requester),
            patch.object(services, "ensure_public_requester_learner", return_value=learner),
            patch.object(services, "dictfetchone", side_effect=[{"id": 73, "status": "Open", "assigned_team": "Unassigned", "sla_status": "Pending Review", "created_at": datetime(2026, 5, 14, 10, 0, tzinfo=timezone.utc)}, {"id": 90}]),
            patch.object(services, "build_public_ticket_id", return_value="KBC-000073"),
            patch.object(services, "insert_history_event"),
            patch.object(services.connection, "cursor", return_value=cursor_manager),
        ):
            response = services.create_ticket(
                {
                    "email": "coach@example.com",
                    "category": "Technical",
                    "technicalSubcategory": "Teams",
                    "inquiry": "Need coach support.",
                    "evidence": [],
                }
            )

        self.assertEqual(response["ticket"]["assignedTeam"], "Unassigned")
        self.assertFalse(any("SET assigned_agent_id = %s" in call.args[0] for call in cursor.execute.call_args_list))

    def test_support_session_window_accepts_uk_hours_until_four_pm(self):
        requested_datetime = datetime(2026, 5, 10, 15, 0, tzinfo=ZoneInfo("Europe/London"))

        self.assertTrue(services.is_within_support_session_window(requested_datetime))

    def test_support_session_window_rejects_after_four_pm_uk_time(self):
        requested_datetime = datetime(2026, 5, 10, 16, 30, tzinfo=ZoneInfo("Europe/London"))

        self.assertFalse(services.is_within_support_session_window(requested_datetime))

    def test_support_session_alignment_rejects_non_slot_interval_start(self):
        requested_datetime = datetime(2026, 5, 10, 16, 34, tzinfo=ZoneInfo("Africa/Cairo"))

        with patch.object(services.settings, "SUPPORT_SESSION_SLOT_INTERVAL_MINUTES", 30):
            self.assertFalse(services.is_support_session_time_aligned(requested_datetime))

    def test_support_session_availability_uses_microsoft_graph_slots(self):
        ticket = {"id": 77, "public_id": "KBC-000077"}
        availability_payload = {
            "value": [
                {
                    "staffId": "staff-1",
                    "availabilityItems": [
                        {
                            "status": "available",
                            "startDateTime": {"dateTime": "2099-01-07T08:00:00"},
                            "endDateTime": {"dateTime": "2099-01-07T09:00:00"},
                        }
                    ],
                }
            ]
        }

        with (
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "is_direct_microsoft_booking_configured", return_value=True),
            patch.object(services, "request_microsoft_graph_access_token", return_value=(True, True, 200, {"access_token": "token"})),
            patch.object(
                services,
                "get_microsoft_booking_service_details",
                return_value=(True, True, 200, {"staffMemberIds": ["staff-1"], "defaultDuration": "PT1H"}),
            ),
            patch.object(
                services,
                "get_microsoft_booking_staff_availability_window",
                return_value=(True, True, 200, availability_payload),
            ),
            patch.object(services, "list_active_support_session_request_rows", return_value=[]),
        ):
            response = services.get_support_session_availability_response(
                "KBC-000077",
                "2099-01-07",
                "Europe/London",
            )

        self.assertEqual(response["source"], "microsoft_graph")
        self.assertEqual(response["options"], [{"value": "08:00", "label": "8:00 AM"}])

    def test_support_session_availability_falls_back_when_graph_is_not_configured(self):
        ticket = {"id": 77, "public_id": "KBC-000077"}

        with (
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "is_direct_microsoft_booking_configured", return_value=False),
            patch.object(services, "list_active_support_session_request_rows", return_value=[]),
        ):
            response = services.get_support_session_availability_response(
                "KBC-000077",
                "2099-01-07",
                "Europe/London",
            )

        self.assertEqual(response["source"], "fallback")
        self.assertIn({"value": "08:00", "label": "8:00 AM"}, response["options"])

    def test_filter_locally_available_support_session_candidates_respects_buffer(self):
        candidates = [
            {
                "value": "10:30",
                "label": "10:30 AM",
                "requestedDateTime": datetime(2099, 1, 7, 10, 30, tzinfo=ZoneInfo("Europe/London")),
            },
            {
                "value": "11:00",
                "label": "11:00 AM",
                "requestedDateTime": datetime(2099, 1, 7, 11, 0, tzinfo=ZoneInfo("Europe/London")),
            },
            {
                "value": "11:30",
                "label": "11:30 AM",
                "requestedDateTime": datetime(2099, 1, 7, 11, 30, tzinfo=ZoneInfo("Europe/London")),
            },
        ]
        existing_session = {
            "id": 31,
            "ticket_id": 77,
            "status": "scheduled",
            "metadata": {
                "requested_start_at": "2099-01-07T10:00:00+00:00",
                "requested_end_at": "2099-01-07T11:00:00+00:00",
                "duration_minutes": 60,
            },
        }

        with (
            patch.object(services.settings, "SUPPORT_SESSION_BUFFER_MINUTES", 30),
            patch.object(services, "list_active_support_session_request_rows", return_value=[existing_session]),
        ):
            result = services.filter_locally_available_support_session_candidates(candidates, 60)

        self.assertEqual([candidate["value"] for candidate in result], ["11:30"])

    def test_build_support_session_candidate_slots_requires_session_to_finish_inside_support_hours(self):
        with patch.object(services.settings, "SUPPORT_SESSION_DURATION_MINUTES", 60):
            slots = services.build_support_session_candidate_slots(
                "2099-01-07",
                "Europe/London",
                now=datetime(2099, 1, 1, 9, 0, tzinfo=ZoneInfo("Europe/London")),
            )

        self.assertIn("15:00", [slot["value"] for slot in slots])
        self.assertNotIn("15:30", [slot["value"] for slot in slots])
        self.assertNotIn("16:00", [slot["value"] for slot in slots])

    def test_extract_booking_webhook_result_marks_teams_reservation_as_confirmed(self):
        result = services.extract_booking_webhook_result(
            {
                "eventId": "evt_123",
                "joinUrl": "https://teams.microsoft.com/l/meetup-join/example",
                "organizerEmail": "support@example.com",
            },
            delivered=True,
            status=201,
        )

        self.assertTrue(result["reservationConfirmed"])
        self.assertEqual(result["calendarEventId"], "evt_123")
        self.assertEqual(result["meetingJoinUrl"], "https://teams.microsoft.com/l/meetup-join/example")

    def test_extract_booking_webhook_result_marks_conflict_as_unavailable(self):
        result = services.extract_booking_webhook_result(
            {"available": False, "message": "This slot is already booked."},
            delivered=False,
            status=409,
        )

        self.assertFalse(result["reservationConfirmed"])
        self.assertTrue(result["slotUnavailable"])
        self.assertEqual(result["message"], "This slot is already booked.")

    def test_extract_booking_webhook_result_marks_graph_join_url_as_confirmed(self):
        result = services.extract_booking_webhook_result(
            {
                "id": "apt_123",
                "joinWebUrl": "https://teams.microsoft.com/l/meetup-join/direct-booking",
            },
            delivered=True,
            status=201,
        )

        self.assertTrue(result["reservationConfirmed"])
        self.assertEqual(result["calendarEventId"], "apt_123")
        self.assertEqual(result["meetingJoinUrl"], "https://teams.microsoft.com/l/meetup-join/direct-booking")

    def test_build_microsoft_booking_appointment_payload_uses_service_settings_and_graph_timezones(self):
        requested_datetime = datetime(2026, 5, 11, 15, 22, tzinfo=ZoneInfo("Europe/London"))
        ticket = {
            "learner_full_name": "Ali Test",
            "learner_email": "ali@example.com",
            "learner_phone": "01000000000",
        }
        service_payload = {
            "displayName": "Technical Support Meeting",
            "isCustomerAllowedToManageBooking": False,
            "isLocationOnline": True,
            "smsNotificationsEnabled": False,
            "maximumAttendeesCount": 5,
        }

        with (
            patch.object(services.settings, "BOOKING_SERVICE_ID", "service-123"),
        ):
            payload = services.build_microsoft_booking_appointment_payload(
                ticket,
                requested_datetime,
                "Africa/Cairo",
                duration_minutes=120,
                service_payload=service_payload,
                staff_member_ids=["staff-1"],
            )

        self.assertEqual(payload["serviceId"], "service-123")
        self.assertEqual(payload["serviceName"], "Technical Support Meeting")
        self.assertEqual(payload["customerEmailAddress"], "ali@example.com")
        self.assertEqual(payload["customerTimeZone"], "Egypt Standard Time")
        self.assertEqual(payload["staffMemberIds"], ["staff-1"])
        self.assertEqual(payload["maximumAttendeesCount"], 1)
        self.assertEqual(payload["filledAttendeesCount"], 1)
        self.assertEqual(payload["start"]["timeZone"], "GMT Standard Time")
        self.assertEqual(payload["start"]["dateTime"], "2026-05-11T15:22:00")
        self.assertEqual(payload["end"]["dateTime"], "2026-05-11T17:22:00")

    def test_send_microsoft_graph_booking_returns_reserved_result(self):
        requested_datetime = datetime(2026, 5, 11, 15, 22, tzinfo=ZoneInfo("Europe/London"))
        ticket = {
            "learner_full_name": "Ali Test",
            "learner_email": "ali@example.com",
            "learner_phone": "01000000000",
        }

        with (
            patch.object(services, "is_direct_microsoft_booking_configured", return_value=True),
            patch.object(services, "request_microsoft_graph_access_token", return_value=(True, True, 200, {"access_token": "token-123"})),
            patch.object(
                services,
                "get_microsoft_booking_service_details",
                return_value=(True, True, 200, {"defaultDuration": "PT2H", "displayName": "Technical Support Meeting", "staffMemberIds": ["staff-1"]}),
            ),
            patch.object(services, "select_microsoft_booking_staff_member_ids", return_value=["staff-1"]),
            patch.object(
                services,
                "post_json_request",
                return_value=(True, True, 201, {"id": "apt_123", "joinWebUrl": "https://teams.microsoft.com/l/meetup-join/direct-booking"}),
            ) as post_json_request,
            patch.object(services.settings, "BOOKING_BUSINESS_ID", "StudentSupport1@kentbusinesscollege.com"),
            patch.object(services.settings, "BOOKING_SERVICE_ID", "service-123"),
            patch.object(services.settings, "SUPPORT_SESSION_DURATION_MINUTES", 60),
        ):
            result = services.send_microsoft_graph_booking(ticket, requested_datetime, "Africa/Cairo")

        self.assertTrue(result["configured"])
        self.assertTrue(result["delivered"])
        self.assertTrue(result["reservationConfirmed"])
        self.assertEqual(result["bookingMode"], "graph")
        self.assertEqual(result["graphApiVersion"], "v1.0")
        self.assertEqual(result["durationMinutes"], 120)
        self.assertEqual(result["calendarEventId"], "apt_123")
        self.assertEqual(result["meetingJoinUrl"], "https://teams.microsoft.com/l/meetup-join/direct-booking")
        self.assertIn("/solutions/bookingBusinesses/StudentSupport1%40kentbusinesscollege.com/appointments", post_json_request.call_args.args[0])
        self.assertEqual(post_json_request.call_args.kwargs["headers"]["Authorization"], "Bearer token-123")

    def test_send_microsoft_graph_booking_retries_beta_after_v1_unknown_error(self):
        requested_datetime = datetime(2026, 5, 11, 15, 22, tzinfo=ZoneInfo("Europe/London"))
        ticket = {
            "learner_full_name": "Ali Test",
            "learner_email": "ali@example.com",
            "learner_phone": "01000000000",
        }

        with (
            patch.object(services, "is_direct_microsoft_booking_configured", return_value=True),
            patch.object(services, "request_microsoft_graph_access_token", return_value=(True, True, 200, {"access_token": "token-123"})),
            patch.object(
                services,
                "get_microsoft_booking_service_details",
                return_value=(True, True, 200, {"defaultDuration": "PT2H", "displayName": "Technical Support Meeting", "staffMemberIds": ["staff-1"]}),
            ),
            patch.object(services, "select_microsoft_booking_staff_member_ids", return_value=["staff-1"]),
            patch.object(
                services,
                "post_json_request",
                side_effect=[
                    (True, False, 500, {"error": {"code": "UnknownError", "message": ""}}),
                    (True, True, 201, {"id": "apt_456", "joinWebUrl": "https://teams.microsoft.com/l/meetup-join/beta-booking"}),
                ],
            ) as post_json_request,
            patch.object(services.settings, "BOOKING_BUSINESS_ID", "StudentSupport1@kentbusinesscollege.com"),
            patch.object(services.settings, "BOOKING_SERVICE_ID", "service-123"),
        ):
            result = services.send_microsoft_graph_booking(ticket, requested_datetime, "Africa/Cairo")

        self.assertTrue(result["reservationConfirmed"])
        self.assertEqual(result["graphApiVersion"], "beta")
        self.assertEqual(result["calendarEventId"], "apt_456")
        self.assertEqual(post_json_request.call_count, 2)
        self.assertIn("https://graph.microsoft.com/beta/", post_json_request.call_args.args[0])

    def test_send_microsoft_graph_booking_returns_auth_failure_message(self):
        requested_datetime = datetime(2026, 5, 11, 15, 22, tzinfo=ZoneInfo("Europe/London"))
        ticket = {
            "learner_full_name": "Ali Test",
            "learner_email": "ali@example.com",
            "learner_phone": "01000000000",
        }

        with (
            patch.object(services, "is_direct_microsoft_booking_configured", return_value=True),
            patch.object(
                services,
                "request_microsoft_graph_access_token",
                return_value=(True, False, 401, {"error": {"message": "Invalid client secret."}}),
            ),
        ):
            result = services.send_microsoft_graph_booking(ticket, requested_datetime, "Africa/Cairo")

        self.assertTrue(result["configured"])
        self.assertFalse(result["delivered"])
        self.assertFalse(result["reservationConfirmed"])
        self.assertEqual(result["message"], "Invalid client secret.")

    def test_send_support_session_booking_falls_back_to_webhook_when_graph_not_configured(self):
        ticket = {
            "public_id": "KBC-000123",
            "learner_id": 11,
            "learner_full_name": "Ali Test",
            "learner_email": "ali@example.com",
            "learner_phone": "01000000000",
            "category": "Technical",
            "technical_subcategory": "Teams",
            "inquiry": "Need help joining my live class.",
            "status": "Pending",
            "status_reason": "Awaiting support meeting",
            "priority": "Normal",
            "assigned_team": "Student Support",
        }
        requested_datetime = datetime(2026, 5, 11, 15, 22, tzinfo=ZoneInfo("Europe/London"))

        with (
            patch.object(services, "is_direct_microsoft_booking_configured", return_value=False),
            patch.object(services, "send_booking_webhook", return_value={"configured": True, "delivered": True, "status": 201, "reservationConfirmed": True, "slotUnavailable": False, "meetingJoinUrl": "https://teams.microsoft.com/example", "calendarEventId": "evt_123", "calendarEventUrl": None, "organizerEmail": "support@example.com", "bookingReference": "ref_123", "message": ""}) as send_booking_webhook,
        ):
            result = services.send_support_session_booking(
                ticket,
                19,
                "2026-05-11",
                "15:22",
                requested_datetime,
                "Africa/Cairo",
                datetime(2026, 5, 10, 11, 0, tzinfo=timezone.utc),
            )

        self.assertEqual(result["bookingMode"], "webhook")
        self.assertTrue(result["reservationConfirmed"])
        send_booking_webhook.assert_called_once()

    def test_get_latest_ticket_booking_summary_returns_none_for_cancelled_request(self):
        with patch.object(
            services,
            "run_query_one",
            return_value={
                "requested_date": "2026-05-12",
                "requested_time": "11:30",
                "status": "cancelled",
                "metadata": {"meeting_join_url": "https://teams.microsoft.com/example"},
                "created_at": datetime(2026, 5, 10, 11, 0, tzinfo=timezone.utc),
            },
        ):
            result = services.get_latest_ticket_booking_summary(17)

        self.assertIsNone(result)

    def test_get_latest_ticket_booking_summary_includes_return_path(self):
        with patch.object(
            services,
            "run_query_one",
            return_value={
                "requested_date": "2026-05-12",
                "requested_time": "11:30",
                "status": "scheduled",
                "metadata": {
                    "reservation_confirmed": True,
                    "meeting_join_url": "https://teams.microsoft.com/example",
                    "return_path": "/support/options",
                },
                "created_at": datetime(2026, 5, 10, 11, 0, tzinfo=timezone.utc),
            },
        ):
            result = services.get_latest_ticket_booking_summary(17)

        self.assertEqual(result["returnPath"], "/support/options")

    def test_send_chatbot_message_rejects_when_ticket_is_awaiting_meeting(self):
        ticket = {
            "id": 77,
            "public_id": "KBC-000077",
            "conversation_id": 55,
            "category": "Technical",
            "technical_subcategory": "Teams",
            "inquiry": "Need the meeting link",
            "status": "Pending",
            "status_reason": "Awaiting support meeting",
            "priority": "Normal",
            "assigned_team": "Support Desk",
            "learner_id": 9,
            "learner_full_name": "Ali Test",
            "learner_email": "ali@example.com",
            "learner_phone": "01000000000",
        }

        with (
            patch.object(services, "sync_open_ticket_inactivity"),
            patch.object(services, "run_query_one", return_value=ticket),
        ):
            with self.assertRaises(services.ApiError) as error_context:
                services.send_chatbot_message("KBC-000077", {"message": "hello"})

        self.assertEqual(error_context.exception.status_code, 409)

    def test_send_chatbot_message_allows_coach_requester_role(self):
        ticket = {
            "id": 77,
            "public_id": "KBC-000077",
            "conversation_id": 55,
            "metadata": {"requester_role": "coach"},
            "category": "Technical",
            "technical_subcategory": "Teams",
            "inquiry": "Need the meeting link",
            "status": "Open",
            "status_reason": "",
            "priority": "Normal",
            "assigned_team": "Support Desk",
            "learner_id": 9,
            "learner_full_name": "Ali Test",
            "learner_email": "ali@example.com",
            "learner_phone": "01000000000",
        }

        with (
            patch.object(services, "sync_open_ticket_inactivity"),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "mark_conversation_as_active"),
            patch.object(
                services,
                "send_chatbot_webhook",
                return_value={"configured": True, "delivered": True, "status": 200, "reply": "Thanks"},
            ) as send_chatbot_webhook,
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "sync_conversation_messages", return_value=[]),
        ):
            response = services.send_chatbot_message("KBC-000077", {"message": "hello"})

        self.assertTrue(response["ok"])
        self.assertEqual(send_chatbot_webhook.call_args.args[0]["message"], "hello")

    def test_send_chatbot_webhook_uses_dedicated_timeout_and_suppresses_failed_reply(self):
        with patch.object(
            services,
            "post_json_webhook",
            return_value=(True, False, None, {"message": "Request timed out."}),
        ) as post_json_webhook:
            response = services.send_chatbot_webhook({"message": "hello"})

        post_json_webhook.assert_called_once_with(
            services.settings.CHATBOT_WEBHOOK_URL,
            {"message": "hello"},
            timeout_seconds=services.CHATBOT_WEBHOOK_TIMEOUT_SECONDS,
        )
        self.assertTrue(response["configured"])
        self.assertFalse(response["delivered"])
        self.assertEqual(response["reply"], "")

    def test_send_chatbot_message_accepts_attachment_only_message(self):
        ticket = {
            "id": 77,
            "public_id": "KBC-000077",
            "conversation_id": 55,
            "metadata": {},
            "category": "Technical",
            "technical_subcategory": "Teams",
            "inquiry": "Need help with Teams",
            "status": "Open",
            "status_reason": "",
            "priority": "Normal",
            "assigned_team": "Support Desk",
            "learner_id": 9,
            "learner_full_name": "Ali Test",
            "learner_email": "ali@example.com",
            "learner_phone": "01000000000",
        }
        uploaded_file = SimpleUploadedFile("chat-proof.png", b"png", content_type="image/png")

        with (
            patch.object(services, "sync_open_ticket_inactivity"),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "mark_conversation_as_active"),
            patch.object(services, "send_chatbot_webhook", return_value={"configured": True, "delivered": True, "status": 200, "reply": "Thanks"}) as send_chatbot_webhook,
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "sync_conversation_messages", return_value=[] ) as sync_conversation_messages,
        ):
            response = services.send_chatbot_message(
                "KBC-000077",
                {
                    "message": "",
                    "clientTimeZone": "Africa/Cairo",
                    "messages": [
                        {
                            "sender": "user",
                            "text": "",
                            "timestamp": "10:30 AM",
                            "clientMessageId": "msg-1",
                            "attachments": [{"clientAttachmentId": "att-1", "name": "chat-proof.png", "size": 3}],
                        }
                    ],
                },
                uploaded_files=[uploaded_file],
            )

        self.assertTrue(response["ok"])
        self.assertEqual(send_chatbot_webhook.call_args.args[0]["message"], "Shared attachment: chat-proof.png.")
        self.assertEqual(sync_conversation_messages.call_args.kwargs["ticket_public_id"], "KBC-000077")
        self.assertEqual(sync_conversation_messages.call_args.kwargs["uploaded_files"], [uploaded_file])

    def test_request_live_chat_allows_coach_requester_role(self):
        ticket = {
            "id": 77,
            "public_id": "KBC-000077",
            "conversation_id": 55,
            "metadata": {"requester_role": "coach"},
            "status": "Open",
            "status_reason": "",
            "category": "Technical",
            "technical_subcategory": "Teams",
            "priority": "High",
            "created_at": datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc),
            "assigned_team": "Unassigned",
            "assigned_agent_id": None,
            "conversation_status": "open",
            "learner_name": "Coach One",
            "learner_email": "coach@example.com",
            "learner_source": "kbc_users_data",
            "learner_metadata": {},
        }
        refreshed_ticket = {
            "public_id": "KBC-000077",
            "assigned_agent_id": None,
            "assigned_agent_name": None,
            "assigned_agent_username": None,
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services, "sync_open_ticket_inactivity"),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", side_effect=[ticket, refreshed_ticket]),
            patch.object(services, "mark_conversation_as_active"),
            patch.object(services, "assign_waiting_live_chat_tickets", return_value=[]),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event"),
            patch.object(services, "queue_live_agent_unavailable_notification") as queue_unavailable,
        ):
            response = services.request_live_chat("KBC-000077")

        self.assertTrue(response["ok"])
        self.assertIsNone(response["ticket"]["assignedAgentId"])
        queue_unavailable.assert_called_once()

    def test_create_support_session_request_allows_coach_requester_role(self):
        ticket = {
            "id": 77,
            "public_id": "KBC-000077",
            "conversation_id": 55,
            "metadata": {"requester_role": "coach"},
            "category": "Technical",
            "technical_subcategory": "Teams",
            "inquiry": "Need a support session",
            "status": "Open",
            "sla_status": "Pending Review",
            "priority": "Normal",
            "assigned_team": "Support Desk",
            "created_at": datetime(2026, 5, 10, 11, 0, tzinfo=timezone.utc),
            "learner_id": 9,
            "learner_full_name": "Ali Test",
            "learner_email": "coach@example.com",
            "learner_phone": "01000000000",
        }
        created_session_request = {
            "id": 31,
            "created_at": datetime(2026, 6, 10, 9, 0, tzinfo=timezone.utc),
        }
        booking_result = {
            "configured": True,
            "delivered": True,
            "status": 201,
            "reservationConfirmed": True,
            "slotUnavailable": False,
            "meetingJoinUrl": "https://teams.microsoft.com/example",
            "calendarEventId": "evt_123",
            "calendarEventUrl": None,
            "organizerEmail": "support@example.com",
            "bookingReference": "ref_123",
            "message": "",
            "bookingMode": "webhook",
            "graphApiVersion": None,
            "durationMinutes": 30,
        }
        cursor = MagicMock()
        cursor_manager = MagicMock()
        cursor_manager.__enter__.return_value = cursor
        cursor_manager.__exit__.return_value = False
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_manager

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "validate_support_session_request", return_value=""),
            patch.object(services, "resolve_support_session_datetime", return_value=datetime(2026, 6, 12, 9, 0, tzinfo=timezone.utc)),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "dictfetchone", return_value=created_session_request),
            patch.object(services, "insert_history_event"),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "resolve_next_sla_state", return_value=("On Track", False, None)),
            patch.object(services, "lock_support_session_booking_date"),
            patch.object(services, "is_support_session_slot_locally_available", return_value=True),
            patch.object(services, "send_support_session_booking", return_value=booking_result),
            patch.object(services, "update_support_session_request_record"),
            patch.object(services, "connection", mock_connection),
        ):
            response = services.create_support_session_request(
                "KBC-000077",
                {
                    "date": "2026-06-12",
                    "time": "09:00",
                    "scheduledAt": "2026-06-12T09:00:00+00:00",
                    "returnPath": "/support/options",
                },
            )

        self.assertTrue(response["ok"])
        self.assertTrue(response["reservationConfirmed"])
        self.assertEqual(response["ticket"]["status"], "Pending")
        insert_call = next(
            call for call in cursor.execute.call_args_list
            if "INSERT INTO support_session_requests" in call.args[0]
        )
        insert_params = insert_call.args[1]
        self.assertEqual(json.loads(insert_params[3])["return_path"], "/support/options")
        ticket_update_call = next(
            call for call in cursor.execute.call_args_list
            if "UPDATE tickets" in call.args[0] and "SET status" in call.args[0]
        )
        persisted_metadata = json.loads(ticket_update_call.args[1][3])
        self.assertEqual(
            persisted_metadata["pending_support_queue_notification"]["ticketId"],
            "KBC-000077",
        )
        self.assertEqual(
            persisted_metadata["pending_support_queue_notification"]["reason"],
            "support_session_requested",
        )

    def test_cancel_support_session_request_reopens_ticket_after_cancellation(self):
        ticket = {
            "id": 77,
            "public_id": "KBC-000077",
            "conversation_id": 55,
            "category": "Technical",
            "technical_subcategory": "Teams",
            "inquiry": "Need the meeting link",
            "status": "Pending",
            "status_reason": "Awaiting support meeting",
            "sla_status": "On Track",
            "assigned_team": "Support Desk",
            "metadata": {},
            "created_at": datetime(2026, 5, 10, 11, 0, tzinfo=timezone.utc),
            "learner_id": 9,
            "learner_full_name": "Ali Test",
            "learner_email": "ali@example.com",
            "learner_phone": "01000000000",
        }
        session_request = {
            "id": 31,
            "requested_date": "2026-05-12",
            "requested_time": "11:30",
            "status": "scheduled",
            "notes": None,
            "metadata": {"booking_mode": "graph", "reservation_confirmed": True, "calendar_event_id": "apt_123"},
            "created_at": datetime(2026, 5, 10, 11, 5, tzinfo=timezone.utc),
        }
        cursor = MagicMock()
        cursor_manager = MagicMock()
        cursor_manager.__enter__.return_value = cursor
        cursor_manager.__exit__.return_value = False

        with (
            patch.object(services, "run_query_one", side_effect=[ticket, session_request]),
            patch.object(
                services,
                "send_support_session_cancellation",
                return_value={"configured": True, "delivered": True, "status": 204, "cancelled": True, "message": "Your support meeting has been cancelled."},
            ),
            patch.object(services, "resolve_next_sla_state", return_value=("Pending Review", False, None)),
            patch.object(services.connection, "cursor", return_value=cursor_manager),
            patch.object(services, "insert_history_event"),
        ):
            response = services.cancel_support_session_request("KBC-000077")

        self.assertTrue(response["ok"])
        self.assertEqual(response["ticket"]["status"], "Open")
        self.assertEqual(response["ticket"]["statusReason"], "")
        self.assertEqual(response["message"], "Your support meeting has been cancelled.")
        self.assertGreaterEqual(cursor.execute.call_count, 3)

    def test_send_admin_ai_webhook_uses_dedicated_admin_ai_url(self):
        payload = {"message": "What should I do next?"}

        with (
            patch.object(services.settings, "ADMIN_AI_WEBHOOK_URL", "https://example.com/admin-ai"),
            patch.object(services.settings, "CHATBOT_WEBHOOK_URL", "https://example.com/chatbot"),
            patch.object(
                services,
                "post_json_webhook",
                return_value=(True, True, 200, {"reply": "Escalate this ticket."}),
            ) as post_json_webhook,
        ):
            result = services.send_admin_ai_webhook(payload)

        self.assertTrue(result["configured"])
        self.assertTrue(result["delivered"])
        self.assertEqual(result["reply"], "Escalate this ticket.")
        post_json_webhook.assert_called_once_with("https://example.com/admin-ai", payload)

    def test_send_admin_ai_webhook_falls_back_to_chatbot_url(self):
        payload = {"message": "Summarize the case."}

        with (
            patch.object(services.settings, "ADMIN_AI_WEBHOOK_URL", ""),
            patch.object(services.settings, "CHATBOT_WEBHOOK_URL", "https://example.com/chatbot"),
            patch.object(
                services,
                "post_json_webhook",
                return_value=(True, True, 200, {"reply": "The learner needs a follow-up."}),
            ) as post_json_webhook,
        ):
            result = services.send_admin_ai_webhook(payload)

        self.assertEqual(result["reply"], "The learner needs a follow-up.")
        post_json_webhook.assert_called_once_with("https://example.com/chatbot", payload)

    def test_send_coverage_ticket_operations_webhook_uses_short_timeout(self):
        payload = {"event": "coverage_ticket_created", "ticket": {"id": "KBC-000073"}}

        with (
            patch.object(
                services,
                "get_coverage_ticket_operations_webhook_url",
                return_value="https://n8n.example/coverage-ticket",
            ),
            patch.object(
                services,
                "get_coverage_ticket_operations_webhook_secret",
                return_value="",
            ),
            patch.object(
                services,
                "post_json_webhook",
                return_value=(True, True, 200, {"ok": True}),
            ) as post_json_webhook,
        ):
            response = services.send_coverage_ticket_operations_webhook(payload)

        self.assertTrue(response["delivered"])
        post_json_webhook.assert_called_once_with(
            "https://n8n.example/coverage-ticket",
            payload,
            timeout_seconds=services.COVERAGE_TICKET_WEBHOOK_TIMEOUT_SECONDS,
        )

    def test_send_coverage_ticket_operations_webhook_includes_secret_header_when_configured(self):
        payload = {"event": "coverage_ticket_created", "ticket": {"id": "KBC-000073"}}

        with (
            patch.object(
                services,
                "get_coverage_ticket_operations_webhook_url",
                return_value="https://n8n.example/coverage-ticket",
            ),
            patch.object(
                services,
                "get_coverage_ticket_operations_webhook_secret",
                return_value="super-secret-value",
            ),
            patch.object(
                services,
                "post_json_webhook",
                return_value=(True, True, 200, {"ok": True}),
            ) as post_json_webhook,
        ):
            response = services.send_coverage_ticket_operations_webhook(payload)

        self.assertTrue(response["delivered"])
        post_json_webhook.assert_called_once_with(
            "https://n8n.example/coverage-ticket",
            payload,
            headers={"x-support-webhook-secret": "super-secret-value"},
            timeout_seconds=services.COVERAGE_TICKET_WEBHOOK_TIMEOUT_SECONDS,
        )

    def test_send_learning_plan_ticket_transfer_webhook_uses_same_operations_url_and_timeout(self):
        payload = {"event": services.LEARNING_PLAN_TICKET_TRANSFER_WEBHOOK_EVENT, "ticket": {"id": "KBC-000073"}}

        with (
            patch.object(
                services,
                "get_coverage_ticket_operations_webhook_url",
                return_value="https://n8n.example/coverage-ticket",
            ),
            patch.object(
                services,
                "get_coverage_ticket_operations_webhook_secret",
                return_value="",
            ),
            patch.object(
                services,
                "post_json_webhook",
                return_value=(True, True, 200, {"ok": True}),
            ) as post_json_webhook,
        ):
            response = services.send_learning_plan_ticket_transfer_webhook(payload)

        self.assertTrue(response["delivered"])
        post_json_webhook.assert_called_once_with(
            "https://n8n.example/coverage-ticket",
            payload,
            timeout_seconds=services.COVERAGE_TICKET_WEBHOOK_TIMEOUT_SECONDS,
        )

    def test_send_learning_plan_ticket_transfer_webhook_includes_secret_header_when_configured(self):
        payload = {"event": services.LEARNING_PLAN_TICKET_TRANSFER_WEBHOOK_EVENT, "ticket": {"id": "KBC-000073"}}

        with (
            patch.object(
                services,
                "get_coverage_ticket_operations_webhook_url",
                return_value="https://n8n.example/coverage-ticket",
            ),
            patch.object(
                services,
                "get_coverage_ticket_operations_webhook_secret",
                return_value="super-secret-value",
            ),
            patch.object(
                services,
                "post_json_webhook",
                return_value=(True, True, 200, {"ok": True}),
            ) as post_json_webhook,
        ):
            response = services.send_learning_plan_ticket_transfer_webhook(payload)

        self.assertTrue(response["delivered"])
        post_json_webhook.assert_called_once_with(
            "https://n8n.example/coverage-ticket",
            payload,
            headers={"x-support-webhook-secret": "super-secret-value"},
            timeout_seconds=services.COVERAGE_TICKET_WEBHOOK_TIMEOUT_SECONDS,
        )

    def test_send_coverage_tutor_response_mail_webhook_uses_short_timeout(self):
        payload = {"event": "coverage_tutor_refused", "ticket": {"id": "KBC-000073"}}

        with (
            patch.object(
                services,
                "get_coverage_tutor_response_mail_webhook_url",
                return_value="https://n8n.example/coverage-response",
            ),
            patch.object(
                services,
                "post_json_webhook",
                return_value=(True, True, 200, {"ok": True}),
            ) as post_json_webhook,
        ):
            response = services.send_coverage_tutor_response_mail_webhook(payload)

        self.assertTrue(response["delivered"])
        post_json_webhook.assert_called_once_with(
            "https://n8n.example/coverage-response",
            payload,
            timeout_seconds=services.COVERAGE_TUTOR_RESPONSE_WEBHOOK_TIMEOUT_SECONDS,
        )


class SupportTeamManagementTests(SimpleTestCase):
    def build_team_row(self, **overrides):
        return {
            "id": 3,
            "key": "curriculum",
            "name": "Curriculum Team",
            "description": "",
            "receiver_access_metadata_key": "team_access:curriculum",
            "receiver_error_ticket_label": "Curriculum Team",
            "is_active": True,
            "metadata": {},
            **overrides,
        }

    def test_create_support_team_stores_auth_group_name_and_ensures_group(self):
        created_team = self.build_team_row(metadata={"auth_group_name": "Curriculum Team Access"})

        with (
            patch.object(services, "run_query_one", side_effect=[None, created_team]) as run_query_one,
            patch.object(services, "ensure_legacy_auth_group_exists") as ensure_legacy_auth_group_exists,
        ):
            result = services.create_support_team({"name": "Curriculum Team"})

        self.assertEqual(result["team"]["authGroupName"], "Curriculum Team Access")
        ensure_legacy_auth_group_exists.assert_called_once_with("Curriculum Team Access")
        insert_params = run_query_one.call_args_list[1].args[1]
        self.assertEqual(insert_params[0], "curriculum_team")
        self.assertEqual(json.loads(insert_params[5])["auth_group_name"], "Curriculum Team Access")

    def test_create_support_team_reactivates_inactive_team_and_ensures_group(self):
        inactive_team = self.build_team_row(
            key="curriculum_team",
            is_active=False,
            metadata={},
        )
        reactivated_team = self.build_team_row(
            key="curriculum_team",
            metadata={"auth_group_name": "Curriculum Team Access"},
        )

        with (
            patch.object(services, "run_query_one", side_effect=[inactive_team, reactivated_team]) as run_query_one,
            patch.object(services, "ensure_legacy_auth_group_exists") as ensure_legacy_auth_group_exists,
        ):
            result = services.create_support_team({"name": "Curriculum Team"})

        self.assertTrue(result["team"]["isActive"])
        self.assertEqual(result["team"]["key"], "curriculum_team")
        self.assertEqual(result["team"]["authGroupName"], "Curriculum Team Access")
        ensure_legacy_auth_group_exists.assert_called_once_with("Curriculum Team Access")
        update_sql = run_query_one.call_args_list[1].args[0]
        update_params = run_query_one.call_args_list[1].args[1]
        self.assertIn("UPDATE support_teams", update_sql)
        self.assertEqual(update_params[2], "team_access:curriculum_team")
        self.assertEqual(json.loads(update_params[4])["auth_group_name"], "Curriculum Team Access")

    def test_create_support_team_rejects_active_duplicate_with_clear_error(self):
        with patch.object(services, "run_query_one", return_value=self.build_team_row()):
            with self.assertRaises(services.ApiError) as context:
                services.create_support_team({"name": "Curriculum Team"})

        self.assertEqual(context.exception.status_code, 400)
        self.assertEqual(context.exception.message, "Team already exists.")

    def test_update_agent_team_access_syncs_custom_group_for_legacy_user(self):
        agent = {
            "id": 21,
            "username": "curriculum.agent",
            "full_name": "Curriculum Agent",
            "email": "curriculum.agent@kentbusinesscollege.com",
            "account_scope": "staff",
            "role": "agent",
            "is_active": True,
            "metadata": {"legacy_auth_user_id": 42},
        }
        team = self.build_team_row(metadata={"auth_group_name": "Curriculum Team Access"})
        attached_agent = {
            **agent,
            "team_access": [
                {
                    "key": "curriculum",
                    "name": "Curriculum Team",
                    "assignedTeam": "Curriculum Team",
                    "canReceiveTickets": True,
                }
            ],
        }

        with (
            patch.object(services, "run_query_one", side_effect=[agent, team]),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "persist_account_team_access") as persist_account_team_access,
            patch.object(services, "sync_legacy_access_group_membership") as sync_legacy_access_group_membership,
            patch.object(services, "attach_account_team_access", return_value=[attached_agent]),
            patch.object(services, "get_open_assigned_live_chat_agent_ids", return_value=set()),
        ):
            result = services.update_agent_team_access(21, team_key="curriculum", receive_tickets=True)

        self.assertIn("curriculum", result["teamAccessKeys"])
        persist_account_team_access.assert_called_once_with(21, "curriculum", True, strict=True)
        sync_legacy_access_group_membership.assert_called_once_with(42, "Curriculum Team Access", True)

    def test_update_agent_team_access_disable_removes_stale_metadata_key(self):
        agent = {
            "id": 21,
            "username": "curriculum.agent",
            "full_name": "Curriculum Agent",
            "email": "curriculum.agent@kentbusinesscollege.com",
            "account_scope": "staff",
            "role": "agent",
            "is_active": True,
            "metadata": {
                "legacy_auth_user_id": 42,
                "team_access_keys": ["curriculum", "other_team"],
                "teamAccessKeys": ["curriculum"],
                "team_access": [{"key": "curriculum", "canReceiveTickets": True}],
            },
        }
        team = self.build_team_row(metadata={"auth_group_name": "Curriculum Team Access"})

        with (
            patch.object(services, "run_query_one", side_effect=[agent, team]),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "persist_account_team_access") as persist_account_team_access,
            patch.object(services, "persist_agent_metadata") as persist_agent_metadata,
            patch.object(services, "sync_legacy_access_group_membership") as sync_legacy_access_group_membership,
            patch.object(services, "attach_account_team_access", side_effect=lambda accounts: accounts),
            patch.object(services, "get_open_assigned_live_chat_agent_ids", return_value=set()),
        ):
            result = services.update_agent_team_access(21, team_key="curriculum", receive_tickets=False)

        self.assertNotIn("curriculum", result["teamAccessKeys"])
        persist_account_team_access.assert_called_once_with(21, "curriculum", False, strict=True)
        sync_legacy_access_group_membership.assert_called_once_with(42, "Curriculum Team Access", False)
        saved_metadata = persist_agent_metadata.call_args.args[1]
        self.assertEqual(saved_metadata["team_access_keys"], ["other_team"])
        self.assertNotIn("teamAccessKeys", saved_metadata)
        self.assertNotIn("team_access", saved_metadata)

    def test_update_agent_team_access_allows_admin_receiver_enable(self):
        admin_account = {
            "id": 22,
            "username": "curriculum.admin",
            "full_name": "Curriculum Admin",
            "email": "curriculum.admin@kentbusinesscollege.com",
            "account_scope": "staff",
            "role": "admin",
            "is_active": True,
            "metadata": {"legacy_auth_user_id": 43},
        }
        team = self.build_team_row(metadata={"auth_group_name": "Curriculum Team Access"})
        attached_admin = {
            **admin_account,
            "team_access": [
                {
                    "key": "curriculum",
                    "name": "Curriculum Team",
                    "assignedTeam": "Curriculum Team",
                    "canReceiveTickets": True,
                }
            ],
        }

        with (
            patch.object(services, "run_query_one", side_effect=[admin_account, team]),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "persist_account_team_access") as persist_account_team_access,
            patch.object(services, "sync_legacy_access_group_membership") as sync_legacy_access_group_membership,
            patch.object(services, "attach_account_team_access", return_value=[attached_admin]),
            patch.object(services, "get_open_assigned_live_chat_agent_ids", return_value=set()),
        ):
            result = services.update_agent_team_access(22, team_key="curriculum", receive_tickets=True)

        self.assertEqual(result["role"], "admin")
        self.assertIn("curriculum", result["teamAccessKeys"])
        persist_account_team_access.assert_called_once_with(22, "curriculum", True, strict=True)
        sync_legacy_access_group_membership.assert_called_once_with(43, "Curriculum Team Access", True)

    def test_legacy_auth_user_from_row_accepts_custom_team_group_only(self):
        legacy_user = services._legacy_support_user_from_row(
            (
                42,
                "curriculum.agent",
                "Curriculum",
                "Agent",
                "curriculum.agent@kentbusinesscollege.com",
                "hashed-password",
                False,
                False,
                True,
                False,
                False,
                False,
                ["curriculum team access"],
            ),
            {"curriculum team access": "curriculum"},
        )

        self.assertIsNotNone(legacy_user)
        self.assertEqual(legacy_user["team_access_keys"], ["curriculum"])
        self.assertTrue(services.legacy_auth_user_has_admin_login_access(legacy_user))

    def test_metadata_team_access_keys_count_as_preloaded_access(self):
        self.assertEqual(
            services.get_preloaded_account_team_access_keys(
                {"metadata": {"team_access_keys": ["curriculum"]}}
            ),
            {"curriculum"},
        )

    def test_update_support_team_renames_matching_ticket_assignments(self):
        current_team = self.build_team_row()
        updated_team = self.build_team_row(
            name="Curriculum Ops",
            description="Curriculum routing",
            receiver_error_ticket_label="Curriculum Ops",
        )
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None

        with (
            patch.object(services, "run_query_one", side_effect=[current_team, updated_team]) as run_query_one,
            patch.object(services, "support_team_transaction", return_value=nullcontext()),
            patch.object(services, "support_team_cursor", return_value=cursor_context),
            patch.object(services, "ensure_legacy_auth_group_exists"),
        ):
            result = services.update_support_team(
                "curriculum",
                {"name": "Curriculum Ops", "description": "Curriculum routing"},
            )

        self.assertEqual(result["team"]["name"], "Curriculum Ops")
        self.assertEqual(run_query_one.call_count, 2)
        cursor.execute.assert_called_once()
        self.assertIn("UPDATE tickets", cursor.execute.call_args.args[0])
        self.assertEqual(cursor.execute.call_args.args[1], ["Curriculum Ops", "curriculum team"])

    def test_disable_support_team_rejects_active_tickets(self):
        with patch.object(services, "run_query_one", side_effect=[self.build_team_row(), {"count": 2}]):
            with self.assertRaises(services.ApiError) as context:
                services.disable_support_team("curriculum")

        self.assertEqual(context.exception.status_code, 400)
        self.assertEqual(context.exception.message, "Move or close active tickets before disabling this team.")

    def test_disable_support_team_soft_disables_custom_team(self):
        disabled_team = self.build_team_row(is_active=False)

        with patch.object(services, "run_query_one", side_effect=[self.build_team_row(), {"count": 0}, disabled_team]) as run_query_one:
            result = services.disable_support_team("curriculum")

        self.assertFalse(result["team"]["isActive"])
        self.assertEqual(run_query_one.call_count, 3)


class SlaPolicyTests(SimpleTestCase):
    def test_open_ticket_keeps_pending_review(self):
        sla_status, attention_required, attention_reason = services.derive_sla_state(
            "Open",
            datetime.now(timezone.utc),
            "Breached",
        )

        self.assertEqual(sla_status, "Pending Review")
        self.assertFalse(attention_required)
        self.assertIsNone(attention_reason)

    def test_closed_ticket_becomes_on_track(self):
        sla_status, attention_required, attention_reason = services.derive_sla_state(
            "Closed",
            datetime.now(timezone.utc),
            "Pending Review",
        )

        self.assertEqual(sla_status, "On Track")
        self.assertFalse(attention_required)
        self.assertIsNone(attention_reason)

    def test_pending_ticket_within_three_days_is_on_track(self):
        created_at = datetime.now(timezone.utc) - timedelta(days=2, hours=23)

        sla_status, attention_required, attention_reason = services.derive_sla_state(
            "Pending",
            created_at,
            "Pending Review",
        )

        self.assertEqual(sla_status, "On Track")
        self.assertFalse(attention_required)
        self.assertIsNone(attention_reason)

    def test_pending_ticket_after_three_days_is_breached_and_flagged(self):
        created_at = datetime.now(timezone.utc) - timedelta(days=3, minutes=1)

        sla_status, attention_required, attention_reason = services.derive_sla_state(
            "Pending",
            created_at,
            "Pending Review",
        )

        self.assertEqual(sla_status, "Breached")
        self.assertTrue(attention_required)
        self.assertEqual(attention_reason, services.SLA_ATTENTION_REASON_PENDING_OVERDUE)

    def test_awaiting_support_meeting_does_not_breach_by_ticket_age(self):
        created_at = datetime.now(timezone.utc) - timedelta(days=8)

        sla_status, attention_required, attention_reason = services.derive_sla_state(
            "Pending",
            created_at,
            "Pending Review",
            status_reason=services.STATUS_REASON_AWAITING_MEETING,
        )

        self.assertEqual(sla_status, "On Track")
        self.assertFalse(attention_required)
        self.assertIsNone(attention_reason)

    def test_resolve_ticket_sla_update_records_meeting_policy_context(self):
        requested_start_at = datetime.now(timezone.utc) + timedelta(days=5)
        ticket = {
            "id": 61,
            "public_id": "KBC-000061",
            "status": "Open",
            "status_reason": "",
            "sla_status": "Pending Review",
            "created_at": datetime.now(timezone.utc) - timedelta(days=8),
            "metadata": {
                "support_session_requested_start_at": requested_start_at.isoformat(),
            },
        }

        sla_status, attention_required, attention_reason, metadata = services.resolve_ticket_sla_update(
            ticket,
            "Pending",
            status_reason=services.STATUS_REASON_AWAITING_MEETING,
            metadata=ticket["metadata"],
        )

        self.assertEqual(sla_status, "On Track")
        self.assertFalse(attention_required)
        self.assertIsNone(attention_reason)
        self.assertEqual(metadata["sla_policy_key"], services.SLA_POLICY_AWAITING_SUPPORT_MEETING)
        self.assertEqual(metadata["sla_due_at"], services.serialize_datetime_value(requested_start_at))

    def test_awaiting_support_meeting_breaches_three_days_after_meeting(self):
        requested_start_at = datetime.now(timezone.utc) - timedelta(days=3, minutes=1)
        ticket = {
            "id": 65,
            "public_id": "KBC-000065",
            "status": "Pending",
            "status_reason": services.STATUS_REASON_AWAITING_MEETING,
            "sla_status": "On Track",
            "created_at": datetime.now(timezone.utc) - timedelta(days=10),
            "metadata": {
                "support_session_requested_start_at": requested_start_at.isoformat(),
            },
        }

        sla_status, attention_required, attention_reason, metadata = services.resolve_ticket_sla_update(
            ticket,
            "Pending",
            status_reason=services.STATUS_REASON_AWAITING_MEETING,
            metadata=ticket["metadata"],
        )

        self.assertEqual(sla_status, "Breached")
        self.assertTrue(attention_required)
        self.assertEqual(attention_reason, services.SLA_ATTENTION_REASON_MEETING_OVERDUE)
        self.assertEqual(metadata["sla_policy_key"], services.SLA_POLICY_AWAITING_SUPPORT_MEETING)
        self.assertEqual(metadata["sla_due_at"], services.serialize_datetime_value(requested_start_at))

    def test_resolve_ticket_sla_update_preserves_breached_outcome_when_closed(self):
        ticket = {
            "id": 64,
            "public_id": "KBC-000064",
            "status": "Pending",
            "status_reason": services.STATUS_REASON_QUICK_TICKET,
            "sla_status": "Breached",
            "created_at": datetime.now(timezone.utc) - timedelta(days=4),
            "metadata": {
                "sla_attention_required": True,
                "sla_attention_reason": services.SLA_ATTENTION_REASON_PENDING_OVERDUE,
            },
        }

        sla_status, attention_required, attention_reason, metadata = services.resolve_ticket_sla_update(
            ticket,
            "Closed",
            status_reason=services.STATUS_REASON_CLOSED_BY_AGENT,
        )

        self.assertEqual(sla_status, "On Track")
        self.assertFalse(attention_required)
        self.assertIsNone(attention_reason)
        self.assertEqual(metadata["sla_policy_key"], services.SLA_POLICY_CLOSED)
        self.assertEqual(metadata["sla_outcome_status"], "Breached")
        self.assertTrue(metadata["sla_resolved_at"])

    def test_apply_ticket_sla_policy_freezes_archived_ticket(self):
        ticket = {
            "id": 62,
            "public_id": "KBC-000062",
            "status": "Pending",
            "status_reason": services.STATUS_REASON_QUICK_TICKET,
            "sla_status": "On Track",
            "metadata": {"sla_attention_required": False},
            "created_at": datetime.now(timezone.utc) - timedelta(days=8),
            "is_archived": True,
        }

        result = services.apply_ticket_sla_policy(ticket, persist=True)

        self.assertEqual(result["sla_status"], "On Track")
        self.assertFalse(result["sla_attention_required"])
        self.assertNotIn("sla_policy_key", result["metadata"])

    def test_apply_ticket_sla_policy_records_pending_age_context(self):
        started_at = datetime.now(timezone.utc) - timedelta(days=4)
        ticket = {
            "id": 63,
            "public_id": "KBC-000063",
            "status": "Pending",
            "status_reason": services.STATUS_REASON_QUICK_TICKET,
            "sla_status": "On Track",
            "metadata": {"sla_started_at": started_at.isoformat()},
            "created_at": started_at,
        }

        result = services.apply_ticket_sla_policy(ticket)

        self.assertEqual(result["sla_status"], "Breached")
        self.assertTrue(result["sla_attention_required"])
        self.assertEqual(result["metadata"]["sla_policy_key"], services.SLA_POLICY_PENDING_AGE)
        self.assertEqual(result["metadata"]["sla_due_at"], services.serialize_datetime_value(started_at + services.PENDING_SLA_BREACH_AFTER))

    def test_apply_ticket_sla_policy_does_not_breach_waiting_coverage_ticket_by_age(self):
        old_created_at = datetime.now(timezone.utc) - timedelta(days=6)
        ticket = {
            "id": 51,
            "public_id": "KBC-000051",
            "technical_subcategory": "Coverage",
            "inquiry": "Tutor: Nathan\nModule: Martech\nPreferred Time: 10:00 AM\nSession Date: Wednesday 24 Jun 2026",
            "status": "Pending",
            "status_reason": "Coverage Ticket",
            "sla_status": "On Track",
            "metadata": {"technical_subcategory": "Coverage"},
            "created_at": old_created_at,
        }

        result = services.apply_ticket_sla_policy(ticket, persist=True)

        self.assertEqual(result["sla_status"], "On Track")
        self.assertFalse(result["sla_attention_required"])

    def test_apply_ticket_sla_policy_restores_legacy_quick_coverage_ticket(self):
        old_created_at = datetime.now(timezone.utc) - timedelta(days=6)
        ticket = {
            "id": 511,
            "public_id": "KBC-000511",
            "technical_subcategory": "Coverage",
            "inquiry": "Tutor: Juliane\nModule: Marketing Impact\nPreferred Time: 09:00 AM\nSession Date: Wednesday 01 Jul 2026",
            "status": "Pending",
            "status_reason": "Quick Ticket",
            "sla_status": "Breached",
            "metadata": {
                "technical_subcategory": "Coverage",
                "sla_attention_required": True,
                "sla_attention_reason": services.SLA_ATTENTION_REASON_PENDING_OVERDUE,
            },
            "created_at": old_created_at,
        }

        result = services.apply_ticket_sla_policy(ticket)

        self.assertEqual(result["sla_status"], "On Track")
        self.assertFalse(result["sla_attention_required"])
        self.assertFalse(result["metadata"]["sla_attention_required"])
        self.assertIsNone(result["metadata"]["sla_attention_reason"])

    def test_apply_ticket_sla_policy_preserves_coverage_deadline_breach(self):
        old_created_at = datetime.now(timezone.utc) - timedelta(days=6)
        ticket = {
            "id": 513,
            "public_id": "KBC-000513",
            "technical_subcategory": "Coverage",
            "inquiry": "Tutor: Juliane\nModule: Marketing Impact\nPreferred Time: 09:00 AM\nSession Date: Wednesday 17 Jun 2026",
            "status": "Pending",
            "status_reason": "Quick Ticket",
            "sla_status": "Breached",
            "metadata": {
                "technical_subcategory": "Coverage",
                "sla_attention_required": True,
                "sla_attention_reason": services.SLA_ATTENTION_REASON_COVERAGE_SESSION_DEADLINE,
            },
            "created_at": old_created_at,
        }

        result = services.apply_ticket_sla_policy(ticket)

        self.assertEqual(result["sla_status"], "Breached")
        self.assertTrue(result["sla_attention_required"])
        self.assertEqual(result["metadata"]["sla_attention_reason"], services.SLA_ATTENTION_REASON_COVERAGE_SESSION_DEADLINE)

    def test_apply_ticket_sla_policy_repairs_coverage_state_breach_metadata(self):
        old_created_at = datetime.now(timezone.utc) - timedelta(days=6)
        ticket = {
            "id": 514,
            "public_id": "KBC-000514",
            "technical_subcategory": "Coverage",
            "inquiry": "Tutor: Juliane\nModule: Marketing Impact\nPreferred Time: 09:00 AM\nSession Date: Wednesday 17 Jun 2026",
            "status": "Pending",
            "status_reason": "Quick Ticket",
            "sla_status": "On Track",
            "metadata": {
                "technical_subcategory": "Coverage",
                "sla_attention_required": False,
                "sla_attention_reason": None,
                "coverage_sla_state": {
                    "stage": "warning",
                    "sessionStartAt": "2026-06-17T08:00:00+00:00",
                    "breachDeadlineAt": "2026-06-14T08:00:00+00:00",
                    "breachedAt": "2026-06-15T09:00:00+00:00",
                    "warningTriggeredAt": "2026-06-15T09:00:00+00:00",
                    "escalatedAt": None,
                },
            },
            "created_at": old_created_at,
        }

        result = services.apply_ticket_sla_policy(ticket)

        self.assertEqual(result["sla_status"], "Breached")
        self.assertTrue(result["sla_attention_required"])
        self.assertEqual(result["metadata"]["sla_attention_reason"], services.SLA_ATTENTION_REASON_COVERAGE_SESSION_DEADLINE)
        self.assertEqual(result["metadata"]["coverage_sla_state"]["stage"], "warning")

    def test_apply_ticket_sla_policy_resolves_coverage_after_tutor_request_without_pending_age_breach(self):
        old_created_at = datetime.now(timezone.utc) - timedelta(days=6)
        ticket = {
            "id": 515,
            "public_id": "KBC-000515",
            "technical_subcategory": "Coverage",
            "inquiry": "Tutor: Nathan\nModule: Martech\nPreferred Time: 09:00 AM\nSession Date: Wednesday 17 Jun 2026",
            "status": "Pending",
            "status_reason": "Tutor Requested",
            "sla_status": "Breached",
            "metadata": {
                "technical_subcategory": "Coverage",
                "sla_attention_required": True,
                "sla_attention_reason": services.SLA_ATTENTION_REASON_COVERAGE_SESSION_DEADLINE,
                "coverage_sla_state": {
                    "stage": "warning",
                    "sessionStartAt": "2026-06-17T08:00:00+00:00",
                    "breachDeadlineAt": "2026-06-14T08:00:00+00:00",
                    "breachedAt": "2026-06-15T09:00:00+00:00",
                    "warningTriggeredAt": "2026-06-15T09:00:00+00:00",
                    "escalatedAt": None,
                },
                "admin_documentation": {
                    "ticketId": "KBC-000515",
                    "coverageCards": [
                        {
                            "id": "card-1",
                            "type": "tutor_choice",
                            "tutor": "Nathan",
                            "tutorEmail": "nathan@example.com",
                            "sessionDetails": "Module: Martech",
                            "requestStatus": "requested",
                            "submittedAt": "2026-06-16T10:00:00Z",
                            "requestSubmittedByAgentId": 7,
                        }
                    ],
                },
            },
            "created_at": old_created_at,
        }

        result = services.apply_ticket_sla_policy(ticket)

        self.assertEqual(result["sla_status"], "On Track")
        self.assertFalse(result["sla_attention_required"])
        self.assertFalse(result["metadata"]["sla_attention_required"])
        self.assertIsNone(result["metadata"]["sla_attention_reason"])
        self.assertNotIn("coverage_sla_state", result["metadata"])

    def test_sync_coverage_ticket_sla_alerts_restores_legacy_quick_ticket_before_deadline(self):
        reference_now = datetime(2026, 6, 15, 15, 0, tzinfo=timezone.utc)
        ticket = {
            "id": 512,
            "public_id": "KBC-000512",
            "learner_name": "Ella",
            "learner_email": "ella@example.com",
            "technical_subcategory": "Coverage",
            "inquiry": "Tutor: Juliane\nModule: Marketing Impact\nPreferred Time: 09:00 AM\nSession Date: Wednesday 01 Jul 2026",
            "status": "Pending",
            "status_reason": "Quick Ticket",
            "sla_status": "Breached",
            "metadata": {
                "technical_subcategory": "Coverage",
                "sla_attention_required": True,
                "sla_attention_reason": services.SLA_ATTENTION_REASON_PENDING_OVERDUE,
            },
            "created_at": datetime(2026, 6, 12, 16, 45, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 6, 12, 16, 45, tzinfo=timezone.utc),
        }
        cursor = MagicMock()
        mock_connection = MagicMock()
        mock_connection.cursor.return_value.__enter__.return_value = cursor

        with (
            patch.object(services, "run_query", return_value=[ticket]),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "send_coverage_sla_alert_webhook") as send_webhook,
            patch.object(services, "insert_history_event") as insert_history_event,
        ):
            result = services.sync_coverage_ticket_sla_alerts(reference_now)

        self.assertEqual(result, {"scanned": 1, "updated": 1, "warnings": 0, "escalations": 0, "breached": 0, "attentionRequired": 0})
        update_params = cursor.execute.call_args.args[1]
        self.assertEqual(update_params[0], "On Track")
        persisted_metadata = json.loads(update_params[1])
        self.assertFalse(persisted_metadata["sla_attention_required"])
        self.assertIsNone(persisted_metadata["sla_attention_reason"])
        self.assertNotIn("coverage_sla_state", persisted_metadata)
        send_webhook.assert_not_called()
        insert_history_event.assert_not_called()

    def test_sync_coverage_ticket_sla_alerts_sends_warning_at_three_day_deadline(self):
        reference_now = datetime(2026, 6, 21, 9, 0, tzinfo=timezone.utc)
        ticket = {
            "id": 52,
            "public_id": "KBC-000052",
            "learner_name": "Ella",
            "learner_email": "ella@example.com",
            "technical_subcategory": "Coverage",
            "inquiry": "Tutor: Nathan\nModule: Martech\nPreferred Time: 10:00 AM\nSession Date: Wednesday 24 Jun 2026",
            "status": "Pending",
            "status_reason": "Coverage Ticket",
            "sla_status": "On Track",
            "metadata": {"technical_subcategory": "Coverage"},
            "created_at": datetime(2026, 6, 12, 16, 45, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 6, 12, 16, 45, tzinfo=timezone.utc),
        }
        cursor = MagicMock()
        mock_connection = MagicMock()
        mock_connection.cursor.return_value.__enter__.return_value = cursor

        with (
            patch.object(services, "run_query", return_value=[ticket]),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "send_coverage_sla_alert_webhook", return_value={"configured": True, "delivered": True, "status": 200}) as send_webhook,
            patch.object(services, "insert_history_event") as insert_history_event,
        ):
            result = services.sync_coverage_ticket_sla_alerts(reference_now)

        self.assertEqual(result, {"scanned": 1, "updated": 1, "warnings": 1, "escalations": 0, "breached": 1, "attentionRequired": 1})
        update_params = cursor.execute.call_args.args[1]
        self.assertEqual(update_params[0], "Breached")
        persisted_metadata = json.loads(update_params[1])
        self.assertEqual(persisted_metadata["sla_attention_reason"], services.SLA_ATTENTION_REASON_COVERAGE_SESSION_DEADLINE)
        self.assertEqual(persisted_metadata["coverage_sla_state"]["stage"], services.COVERAGE_SLA_STAGE_WARNING)
        send_webhook.assert_called_once()
        self.assertEqual(send_webhook.call_args.args[0]["alertLevel"], "warning")
        insert_history_event.assert_called_once()

    def test_sync_coverage_ticket_sla_alerts_escalates_one_day_after_warning(self):
        reference_now = datetime(2026, 6, 22, 9, 1, tzinfo=timezone.utc)
        ticket = {
            "id": 53,
            "public_id": "KBC-000053",
            "learner_name": "Ella",
            "learner_email": "ella@example.com",
            "technical_subcategory": "Coverage",
            "inquiry": "Tutor: Nathan\nModule: Martech\nPreferred Time: 10:00 AM\nSession Date: Wednesday 24 Jun 2026",
            "status": "Pending",
            "status_reason": "Coverage Ticket",
            "sla_status": "Breached",
            "metadata": {
                "technical_subcategory": "Coverage",
                "sla_attention_required": True,
                "sla_attention_reason": services.SLA_ATTENTION_REASON_COVERAGE_SESSION_DEADLINE,
                "coverage_sla_state": {
                    "stage": "warning",
                    "sessionStartAt": "2026-06-24T09:00:00+00:00",
                    "breachDeadlineAt": "2026-06-21T09:00:00+00:00",
                    "breachedAt": "2026-06-21T09:00:00+00:00",
                    "warningTriggeredAt": "2026-06-21T09:00:00+00:00",
                },
            },
            "created_at": datetime(2026, 6, 12, 16, 45, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 6, 12, 16, 45, tzinfo=timezone.utc),
        }
        cursor = MagicMock()
        mock_connection = MagicMock()
        mock_connection.cursor.return_value.__enter__.return_value = cursor

        with (
            patch.object(services, "run_query", return_value=[ticket]),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "send_coverage_sla_alert_webhook", return_value={"configured": True, "delivered": True, "status": 200}) as send_webhook,
            patch.object(services, "insert_history_event"),
        ):
            result = services.sync_coverage_ticket_sla_alerts(reference_now)

        self.assertEqual(result["escalations"], 1)
        update_params = cursor.execute.call_args.args[1]
        persisted_metadata = json.loads(update_params[1])
        self.assertEqual(persisted_metadata["coverage_sla_state"]["stage"], services.COVERAGE_SLA_STAGE_ESCALATED)
        self.assertTrue(persisted_metadata["coverage_sla_state"]["escalatedAt"])
        send_webhook.assert_called_once()
        self.assertEqual(send_webhook.call_args.args[0]["alertLevel"], "escalated")

    def test_sync_coverage_ticket_sla_alerts_does_not_duplicate_warning(self):
        reference_now = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
        ticket = {
            "id": 54,
            "public_id": "KBC-000054",
            "learner_name": "Ella",
            "learner_email": "ella@example.com",
            "technical_subcategory": "Coverage",
            "inquiry": "Tutor: Nathan\nModule: Martech\nPreferred Time: 10:00 AM\nSession Date: Wednesday 24 Jun 2026",
            "status": "Pending",
            "status_reason": "Coverage Ticket",
            "sla_status": "Breached",
            "metadata": {
                "technical_subcategory": "Coverage",
                "sla_attention_required": True,
                "sla_attention_reason": services.SLA_ATTENTION_REASON_COVERAGE_SESSION_DEADLINE,
                "coverage_sla_state": {
                    "stage": "warning",
                    "sessionStartAt": "2026-06-24T09:00:00+00:00",
                    "breachDeadlineAt": "2026-06-21T09:00:00+00:00",
                    "breachedAt": "2026-06-21T09:00:00+00:00",
                    "warningTriggeredAt": "2026-06-21T09:00:00+00:00",
                },
            },
            "created_at": datetime(2026, 6, 12, 16, 45, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 6, 12, 16, 45, tzinfo=timezone.utc),
        }

        with (
            patch.object(services, "run_query", return_value=[ticket]),
            patch.object(services, "send_coverage_sla_alert_webhook") as send_webhook,
            patch.object(services, "insert_history_event"),
        ):
            result = services.sync_coverage_ticket_sla_alerts(reference_now)

        self.assertEqual(result["warnings"], 0)
        self.assertEqual(result["escalations"], 0)
        send_webhook.assert_not_called()

    def test_to_sender_label_accepts_string_metadata_payload(self):
        label = services.to_sender_label("assistant", '{"original_sender":"bot"}')

        self.assertEqual(label, "Bot")

    def test_sync_auto_managed_ticket_sla_statuses_counts_updates_and_breaches(self):
        tickets = [
            {
                "id": 1,
                "status": "Pending",
                "sla_status": "On Track",
                "metadata": {"sla_attention_required": False},
                "created_at": datetime.now(timezone.utc) - timedelta(days=4),
            },
            {
                "id": 2,
                "status": "Open",
                "sla_status": "Pending Review",
                "metadata": {"sla_attention_required": False},
                "created_at": datetime.now(timezone.utc),
            },
        ]

        synced_tickets = [
            {
                **tickets[0],
                "sla_status": "Breached",
                "metadata": {"sla_attention_required": True, "sla_attention_reason": services.SLA_ATTENTION_REASON_PENDING_OVERDUE},
            },
            {
                **tickets[1],
                "sla_status": "Pending Review",
                "metadata": {"sla_attention_required": False},
            },
        ]

        with (
            patch.object(services, "run_query", return_value=tickets) as run_query,
            patch.object(services, "apply_ticket_sla_policy", side_effect=synced_tickets) as apply_ticket_sla_policy,
        ):
            result = services.sync_auto_managed_ticket_sla_statuses()

        self.assertEqual(result, {"scanned": 2, "updated": 1, "breached": 1, "attentionRequired": 1})
        run_query.assert_called_once()
        self.assertEqual(apply_ticket_sla_policy.call_count, 2)

    def test_team_routing_policy_maps_ticket_scope_and_receiver_access(self):
        support_ticket = {"assigned_team": services.ASSIGNED_TEAM_SUPPORT_DESK}
        learning_plan_ticket = {"assigned_team": services.ASSIGNED_TEAM_LEARNING_PLAN}
        coverage_ticket_with_legacy_team = {
            "technical_subcategory": "Coverage",
            "assigned_team": services.ASSIGNED_TEAM_SUPPORT_DESK,
        }
        support_agent = {
            "account_scope": "staff",
            "role": "agent",
            "is_active": True,
            "metadata": {"legacy_support_access": True, "legacy_operations_access": False},
        }
        operations_agent = {
            "account_scope": "staff",
            "role": "agent",
            "is_active": True,
            "metadata": {"legacy_support_access": False, "legacy_operations_access": True},
        }
        support_admin = {
            "account_scope": "staff",
            "role": "admin",
            "is_active": True,
            "metadata": {"legacy_support_access": True, "legacy_operations_access": True},
        }

        self.assertEqual(services.get_ticket_receiver_scope(support_ticket), "support")
        self.assertEqual(services.get_ticket_receiver_scope(learning_plan_ticket), "operations")
        self.assertEqual(services.get_ticket_receiver_scope(coverage_ticket_with_legacy_team), "operations")
        self.assertTrue(services.account_can_receive_ticket_assignment(support_agent, support_ticket))
        self.assertFalse(services.account_can_receive_ticket_assignment(support_agent, learning_plan_ticket))
        self.assertTrue(services.account_can_receive_ticket_assignment(operations_agent, learning_plan_ticket))
        self.assertTrue(services.account_can_receive_ticket_assignment(operations_agent, coverage_ticket_with_legacy_team))
        self.assertTrue(services.account_can_receive_ticket_assignment(support_admin, support_ticket))
        self.assertTrue(services.account_can_receive_ticket_assignment(support_admin, learning_plan_ticket))

    def test_dynamic_team_routing_policy_uses_team_access(self):
        curriculum_team = {
            "id": 3,
            "key": "curriculum",
            "name": "Curriculum Team",
            "description": "",
            "receiver_access_metadata_key": "team_access:curriculum",
            "receiver_error_ticket_label": "Curriculum",
            "is_active": True,
            "metadata": {},
        }
        curriculum_ticket = {"assigned_team": "Curriculum Team"}
        curriculum_agent = {
            "id": 91,
            "account_scope": "staff",
            "role": "agent",
            "is_active": True,
            "metadata": {},
            "team_access": [
                {
                    "key": "curriculum",
                    "name": "Curriculum Team",
                    "assignedTeam": "Curriculum Team",
                    "canReceiveTickets": True,
                }
            ],
        }
        support_agent = {
            "id": 92,
            "account_scope": "staff",
            "role": "agent",
            "is_active": True,
            "metadata": {"legacy_support_access": True},
        }
        curriculum_admin = {
            "id": 93,
            "account_scope": "staff",
            "role": "superadmin",
            "is_active": True,
            "metadata": {},
            "team_access": [
                {
                    "key": "curriculum",
                    "name": "Curriculum Team",
                    "assignedTeam": "Curriculum Team",
                    "canReceiveTickets": True,
                }
            ],
        }

        with patch.object(services, "fetch_optional_dynamic_team_row_by_assigned_team", return_value=curriculum_team):
            self.assertEqual(services.normalize_assigned_team("Curriculum Team"), "Curriculum Team")
            self.assertEqual(services.get_ticket_receiver_scope(curriculum_ticket), "curriculum")
            self.assertTrue(services.account_can_receive_ticket_assignment(curriculum_agent, curriculum_ticket))
            self.assertFalse(services.account_can_receive_ticket_assignment(support_agent, curriculum_ticket))
            self.assertTrue(services.account_can_receive_ticket_assignment(curriculum_admin, curriculum_ticket))

    def test_agent_role_does_not_imply_support_access_without_explicit_permission(self):
        actor = {
            "id": 91,
            "account_scope": "staff",
            "role": "agent",
            "is_active": True,
            "metadata": {},
        }

        with patch.object(services, "fetch_optional_account_team_access", return_value=False):
            self.assertFalse(services.actor_has_support_dashboard_access(actor))

    def test_serialize_ticket_summary_marks_chat_active_only_when_conversation_is_active(self):
        ticket_row = {
            "public_id": "KBC-000123",
            "learner_name": "Ali Test",
            "learner_email": "ali@example.com",
            "learner_phone": "01000000000",
            "category": "Learning",
            "technical_subcategory": "",
            "inquiry": "Need help",
            "status": "Open",
            "status_reason": "",
            "assigned_agent_id": None,
            "assigned_agent_name": None,
            "assigned_agent_username": None,
            "assigned_team": "Unassigned",
            "conversation_id": 12,
            "conversation_status": "open",
            "conversation_metadata": {"is_active_conversation": True, "live_chat_requested": True},
            "last_message_at": None,
            "sla_status": "Pending Review",
            "evidence_count": 0,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "metadata": {},
        }

        summary = services.serialize_ticket_summary(ticket_row)
        inactive_summary = services.serialize_ticket_summary({**ticket_row, "conversation_metadata": {}})

        self.assertTrue(summary["chatIsActive"])
        self.assertTrue(summary["liveChatRequested"])
        self.assertEqual(summary["requesterRole"], "user")
        self.assertEqual(summary["requesterName"], "Ali Test")
        self.assertEqual(summary["priority"], "Normal")
        self.assertEqual(summary["ticketState"]["ticketType"], "live_chat")
        self.assertEqual(summary["ticketState"]["workflowStage"], "awaiting_agent")
        self.assertEqual(summary["ticketState"]["dashboardBucket"], "live_chat")
        self.assertTrue(summary["ticketState"]["canShowConversation"])
        self.assertTrue(summary["ticketState"]["canReceiveChat"])
        self.assertFalse(inactive_summary["chatIsActive"])
        self.assertFalse(inactive_summary["liveChatRequested"])

    def test_serialize_ticket_summary_includes_sla_policy_context(self):
        started_at = datetime(2026, 6, 25, 9, 0, tzinfo=timezone.utc)
        due_at = datetime(2026, 6, 28, 9, 0, tzinfo=timezone.utc)
        breached_at = datetime(2026, 6, 29, 10, 15, tzinfo=timezone.utc)
        ticket_row = {
            "public_id": "KBC-000124",
            "learner_name": "SLA Learner",
            "learner_email": "sla@example.com",
            "learner_phone": "",
            "category": "Technical",
            "technical_subcategory": "LMS",
            "inquiry": "SLA context",
            "status": "Pending",
            "status_reason": services.STATUS_REASON_QUICK_TICKET,
            "assigned_agent_id": None,
            "assigned_agent_name": None,
            "assigned_agent_username": None,
            "assigned_team": services.ASSIGNED_TEAM_SUPPORT_DESK,
            "conversation_id": None,
            "conversation_status": "",
            "conversation_metadata": {},
            "last_message_at": None,
            "sla_status": "Breached",
            "sla_attention_required": True,
            "evidence_count": 0,
            "created_at": started_at,
            "updated_at": breached_at,
            "metadata": {
                services.SLA_POLICY_KEY_METADATA_KEY: services.SLA_POLICY_PENDING_AGE,
                services.SLA_STARTED_AT_METADATA_KEY: services.serialize_datetime_value(started_at),
                services.SLA_DUE_AT_METADATA_KEY: services.serialize_datetime_value(due_at),
                services.SLA_BREACHED_AT_METADATA_KEY: services.serialize_datetime_value(breached_at),
                "sla_attention_reason": services.SLA_ATTENTION_REASON_PENDING_OVERDUE,
            },
        }

        summary = services.serialize_ticket_summary(ticket_row)

        self.assertEqual(summary["slaStatus"], "Breached")
        self.assertTrue(summary["slaAttentionRequired"])
        self.assertEqual(summary["slaAttentionReason"], services.SLA_ATTENTION_REASON_PENDING_OVERDUE)
        self.assertEqual(summary["slaPolicyKey"], services.SLA_POLICY_PENDING_AGE)
        self.assertEqual(summary["slaStartedAt"], services.serialize_datetime_value(started_at))
        self.assertEqual(summary["slaDueAt"], services.serialize_datetime_value(due_at))
        self.assertEqual(summary["slaBreachedAt"], services.serialize_datetime_value(breached_at))

    def test_serialize_ticket_summary_includes_standard_chatbot_ticket_state(self):
        ticket_row = {
            "public_id": "KBC-000122",
            "learner_name": "Mona Standard",
            "learner_email": "mona@example.com",
            "learner_phone": "",
            "category": "Technical",
            "technical_subcategory": "Aptem",
            "inquiry": "Chatbot help",
            "status": "Open",
            "status_reason": "",
            "assigned_agent_id": None,
            "assigned_agent_name": None,
            "assigned_agent_username": None,
            "assigned_team": "Unassigned",
            "conversation_id": 10,
            "conversation_status": "open",
            "conversation_metadata": {"is_active_conversation": True},
            "last_message_at": None,
            "sla_status": "Pending Review",
            "evidence_count": 0,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "metadata": {},
        }

        summary = services.serialize_ticket_summary(ticket_row)

        self.assertEqual(summary["ticketState"]["ticketType"], "standard")
        self.assertEqual(summary["ticketState"]["workflowStage"], "active")
        self.assertEqual(summary["ticketState"]["dashboardBucket"], "support")
        self.assertEqual(summary["ticketState"]["queueScope"], "support")
        self.assertTrue(summary["ticketState"]["canShowConversation"])
        self.assertFalse(summary["ticketState"]["canReceiveChat"])

    def test_serialize_ticket_summary_prefers_persisted_ticket_state_metadata(self):
        ticket_row = {
            "public_id": "KBC-000131",
            "learner_name": "Persisted State",
            "learner_email": "persisted@example.com",
            "learner_phone": "",
            "category": "Technical",
            "technical_subcategory": "LMS",
            "inquiry": "State should not come from status reason",
            "status": "Pending",
            "status_reason": "Quick Ticket",
            "assigned_agent_id": None,
            "assigned_agent_name": None,
            "assigned_agent_username": None,
            "assigned_team": "Learning Plan Team",
            "conversation_id": 10,
            "conversation_status": "open",
            "conversation_metadata": {},
            "last_message_at": None,
            "sla_status": "On Track",
            "evidence_count": 0,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "metadata": {
                services.TICKET_STATE_METADATA_KEY: {
                    "ticketType": "learning_plan",
                    "workflowStage": "learning_plan_review",
                    "queueScope": "operations",
                    "dashboardBucket": "learning_plan",
                    "canShowConversation": False,
                    "canReceiveChat": False,
                    "resolutionReason": "",
                }
            },
        }

        summary = services.serialize_ticket_summary(ticket_row)

        self.assertEqual(summary["ticketState"]["ticketType"], "learning_plan")
        self.assertEqual(summary["ticketState"]["workflowStage"], "learning_plan_review")
        self.assertEqual(summary["ticketState"]["dashboardBucket"], "learning_plan")
        self.assertEqual(summary["ticketState"]["queueScope"], "operations")

    def test_serialize_ticket_summary_prefers_ticket_state_columns_over_metadata(self):
        ticket_row = {
            "public_id": "KBC-000133",
            "learner_name": "Column State",
            "learner_email": "column@example.com",
            "learner_phone": "",
            "category": "Technical",
            "technical_subcategory": "LMS",
            "inquiry": "Columns should be preferred",
            "status": "Pending",
            "status_reason": "Quick Ticket",
            "assigned_agent_id": None,
            "assigned_agent_name": None,
            "assigned_agent_username": None,
            "assigned_team": "Support Desk",
            "conversation_id": 10,
            "conversation_status": "open",
            "conversation_metadata": {},
            "last_message_at": None,
            "sla_status": "On Track",
            "evidence_count": 0,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "metadata": {
                services.TICKET_STATE_METADATA_KEY: {
                    "ticketType": "quick",
                    "workflowStage": "awaiting_review",
                    "queueScope": "support",
                    "dashboardBucket": "quick",
                    "canShowConversation": False,
                    "canReceiveChat": False,
                    "resolutionReason": "",
                }
            },
            "ticket_type": "learning_plan",
            "workflow_stage": "learning_plan_review",
            "queue_scope": "operations",
            "dashboard_bucket": "learning_plan",
            "can_show_conversation": False,
            "can_receive_chat": False,
            "resolution_reason": "",
        }

        summary = services.serialize_ticket_summary(ticket_row)

        self.assertEqual(summary["ticketState"]["ticketType"], "learning_plan")
        self.assertEqual(summary["ticketState"]["workflowStage"], "learning_plan_review")
        self.assertEqual(summary["ticketState"]["dashboardBucket"], "learning_plan")
        self.assertEqual(summary["ticketState"]["queueScope"], "operations")

    def test_with_ticket_state_metadata_persists_current_state_snapshot(self):
        metadata = services.with_ticket_state_metadata(
            {"technical_subcategory": "Coverage"},
            {
                "public_id": "KBC-000132",
                "category": "Technical",
                "technical_subcategory": "Coverage",
                "status": "Pending",
                "status_reason": "Tutor Requested",
                "assigned_agent_id": None,
                "assigned_team": "Learning Plan Team",
                "metadata": {"technical_subcategory": "Coverage"},
            },
        )

        self.assertEqual(
            metadata[services.TICKET_STATE_METADATA_KEY],
            {
                "ticketType": "coverage",
                "workflowStage": "tutor_requested",
                "queueScope": "operations",
                "dashboardBucket": "coverage",
                "canShowConversation": False,
                "canReceiveChat": False,
                "resolutionReason": "",
            },
        )

    def test_serialize_ticket_summary_includes_assigned_live_chat_ticket_state(self):
        ticket_row = {
            "public_id": "KBC-000127",
            "learner_name": "Omar Live",
            "learner_email": "omar@example.com",
            "learner_phone": "",
            "category": "Technical",
            "technical_subcategory": "Teams",
            "inquiry": "Need an agent",
            "status": "Open",
            "status_reason": "",
            "assigned_agent_id": 5,
            "assigned_agent_name": "Omar Agent",
            "assigned_agent_username": "omar.agent",
            "assigned_team": "Support Desk",
            "conversation_id": 14,
            "conversation_status": "open",
            "conversation_metadata": {
                "is_active_conversation": True,
                "live_chat_requested": True,
            },
            "last_message_at": None,
            "sla_status": "Pending Review",
            "evidence_count": 0,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "metadata": {},
        }

        summary = services.serialize_ticket_summary(ticket_row)

        self.assertEqual(summary["ticketState"]["ticketType"], "live_chat")
        self.assertEqual(summary["ticketState"]["workflowStage"], "with_agent")
        self.assertEqual(summary["ticketState"]["dashboardBucket"], "live_chat")
        self.assertTrue(summary["ticketState"]["canShowConversation"])
        self.assertTrue(summary["ticketState"]["canReceiveChat"])

    def test_serialize_ticket_summary_includes_booking_ticket_state(self):
        ticket_row = {
            "public_id": "KBC-000128",
            "learner_name": "Nour Booking",
            "learner_email": "nour@example.com",
            "learner_phone": "",
            "category": "Technical",
            "technical_subcategory": "LMS",
            "inquiry": "Need a meeting",
            "status": "Pending",
            "status_reason": "Awaiting support meeting",
            "assigned_agent_id": None,
            "assigned_agent_name": None,
            "assigned_agent_username": None,
            "assigned_team": "Support Desk",
            "conversation_id": 15,
            "conversation_status": "pending",
            "conversation_metadata": {},
            "last_message_at": None,
            "sla_status": "On Track",
            "evidence_count": 0,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "metadata": {},
        }

        summary = services.serialize_ticket_summary(ticket_row)

        self.assertEqual(summary["ticketState"]["ticketType"], "booking")
        self.assertEqual(summary["ticketState"]["workflowStage"], "awaiting_meeting")
        self.assertEqual(summary["ticketState"]["dashboardBucket"], "pending")
        self.assertEqual(summary["ticketState"]["queueScope"], "support")
        self.assertTrue(summary["ticketState"]["canShowConversation"])
        self.assertFalse(summary["ticketState"]["canReceiveChat"])

    def test_serialize_ticket_summary_includes_quick_ticket_state(self):
        ticket_row = {
            "public_id": "KBC-000124",
            "learner_name": "Sara Quick",
            "learner_email": "sara@example.com",
            "learner_phone": "",
            "category": "Technical",
            "technical_subcategory": "LMS",
            "inquiry": "Quick help",
            "status": "Pending",
            "status_reason": "Quick Ticket",
            "assigned_agent_id": None,
            "assigned_agent_name": None,
            "assigned_agent_username": None,
            "assigned_team": "Support Desk",
            "conversation_id": 13,
            "conversation_status": "open",
            "conversation_metadata": {},
            "last_message_at": None,
            "sla_status": "On Track",
            "evidence_count": 0,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "metadata": {},
        }

        summary = services.serialize_ticket_summary(ticket_row)

        self.assertEqual(summary["ticketState"]["ticketType"], "quick")
        self.assertEqual(summary["ticketState"]["workflowStage"], "awaiting_review")
        self.assertEqual(summary["ticketState"]["dashboardBucket"], "quick")
        self.assertEqual(summary["ticketState"]["queueScope"], "support")
        self.assertFalse(summary["ticketState"]["canShowConversation"])

    def test_serialize_ticket_summary_includes_coverage_ticket_state(self):
        ticket_row = {
            "public_id": "KBC-000126",
            "learner_name": "Ray Ops",
            "learner_email": "ray@example.com",
            "learner_phone": "",
            "category": "Technical",
            "technical_subcategory": "Coverage",
            "inquiry": "Coverage request",
            "status": "Pending",
            "status_reason": "Tutor Requested",
            "assigned_agent_id": None,
            "assigned_agent_name": None,
            "assigned_agent_username": None,
            "assigned_team": "Learning Plan Team",
            "conversation_id": None,
            "conversation_status": None,
            "conversation_metadata": {},
            "last_message_at": None,
            "sla_status": "On Track",
            "evidence_count": 0,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "metadata": {"technical_subcategory": "Coverage"},
        }

        summary = services.serialize_ticket_summary(ticket_row)

        self.assertEqual(summary["ticketState"]["ticketType"], "coverage")
        self.assertEqual(summary["ticketState"]["workflowStage"], "tutor_requested")
        self.assertEqual(summary["ticketState"]["dashboardBucket"], "coverage")
        self.assertEqual(summary["ticketState"]["queueScope"], "operations")
        self.assertFalse(summary["ticketState"]["canShowConversation"])

    def test_serialize_ticket_summary_includes_coverage_tutor_outcome_states(self):
        base_ticket_row = {
            "public_id": "KBC-000129",
            "learner_name": "Ray Ops",
            "learner_email": "ray@example.com",
            "learner_phone": "",
            "category": "Technical",
            "technical_subcategory": "Coverage",
            "inquiry": "Coverage request",
            "priority": "Normal",
            "assigned_agent_id": None,
            "assigned_agent_name": None,
            "assigned_agent_username": None,
            "assigned_team": "Learning Plan Team",
            "conversation_id": None,
            "conversation_status": None,
            "conversation_metadata": {},
            "chat_duration_minutes": 0,
            "last_message_at": None,
            "sla_status": "On Track",
            "sla_attention_required": False,
            "evidence_count": 0,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "metadata": {"technical_subcategory": "Coverage"},
        }

        accepted_summary = services.serialize_ticket_summary({
            **base_ticket_row,
            "status": "Closed",
            "status_reason": "Tutor Accepted",
        })
        rejected_summary = services.serialize_ticket_summary({
            **base_ticket_row,
            "public_id": "KBC-000130",
            "status": "Pending",
            "status_reason": "Tutor Rejected",
        })

        self.assertEqual(accepted_summary["ticketState"]["ticketType"], "coverage")
        self.assertEqual(accepted_summary["ticketState"]["workflowStage"], "tutor_accepted")
        self.assertEqual(accepted_summary["ticketState"]["dashboardBucket"], "closed")
        self.assertEqual(accepted_summary["ticketState"]["resolutionReason"], "Tutor Accepted")
        self.assertEqual(rejected_summary["ticketState"]["ticketType"], "coverage")
        self.assertEqual(rejected_summary["ticketState"]["workflowStage"], "tutor_rejected")
        self.assertEqual(rejected_summary["ticketState"]["dashboardBucket"], "coverage")
        self.assertEqual(rejected_summary["ticketState"]["queueScope"], "operations")

    def test_serialize_ticket_summary_marks_teams_call_requested_without_pending_notification(self):
        ticket_row = {
            "public_id": "KBC-000125",
            "learner_name": "Coach One",
            "learner_email": "coach@example.com",
            "learner_phone": "01000000000",
            "category": "Technical",
            "technical_subcategory": "Teams",
            "inquiry": "Need call",
            "status": "Open",
            "status_reason": "",
            "assigned_agent_id": 5,
            "assigned_agent_name": "Omar1",
            "assigned_agent_username": "omar1",
            "assigned_team": "Support Desk",
            "conversation_id": 22,
            "conversation_status": "open",
            "conversation_metadata": {"chat_public_id": "CHAT-000022"},
            "last_message_at": None,
            "sla_status": "Pending Review",
            "evidence_count": 0,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "metadata": {
                "requester_role": "coach",
                "teams_call_requested": True,
            },
        }

        summary = services.serialize_ticket_summary(ticket_row)

        self.assertTrue(summary["teamsCallRequested"])
        self.assertIsNone(summary["pendingTeamsCallNotification"])

    def test_serialize_ticket_summary_includes_escalation_documentation(self):
        ticket_row = {
            "public_id": "KBC-000124",
            "learner_name": "Ali Test",
            "learner_email": "ali@example.com",
            "learner_phone": "01000000000",
            "category": "Technical",
            "technical_subcategory": "Aptem",
            "inquiry": "Need help",
            "status": "Pending",
            "status_reason": "Escalation",
            "assigned_agent_id": 5,
            "assigned_agent_name": "Omar",
            "assigned_agent_username": "omar",
            "assigned_team": "Support Desk",
            "conversation_id": 12,
            "conversation_status": "open",
            "conversation_metadata": {"is_active_conversation": True, "chat_public_id": "CHAT-000012"},
            "last_message_at": None,
            "sla_status": "On Track",
            "evidence_count": 0,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "metadata": {
                "admin_documentation": {
                    "inquiry": "Need help",
                    "chatId": "CHAT-000012",
                    "ticketId": "KBC-000124",
                    "ticketStatus": "Pending",
                    "statusReason": "Escalation",
                    "escalationAgentId": 9,
                    "escalationAgentName": "Ahmed Hamamo",
                    "escalationNote": "Please review this chat urgently",
                }
            },
        }

        summary = services.serialize_ticket_summary(ticket_row)

        self.assertEqual(summary["documentation"]["escalationAgentId"], 9)
        self.assertEqual(summary["documentation"]["escalationAgentName"], "Ahmed Hamamo")
        self.assertEqual(summary["documentation"]["escalationNote"], "Please review this chat urgently")

    def test_list_admin_tickets_prioritizes_high_priority_active_tickets_but_not_closed_ones(self):
        high_priority_active_ticket = {
            "id": 10,
            "public_id": "KBC-000010",
            "learner_name": "Coach One",
            "learner_email": "coach@example.com",
            "learner_phone": "01000000000",
            "category": "Technical",
            "technical_subcategory": "Teams",
            "inquiry": "Coach issue",
            "status": "Pending",
            "status_reason": "",
            "priority": "High",
            "assigned_agent_id": None,
            "assigned_agent_name": None,
            "assigned_agent_username": None,
            "assigned_team": "Unassigned",
            "conversation_id": 12,
            "conversation_status": "open",
            "conversation_metadata": {"is_active_conversation": True},
            "last_message_at": None,
            "sla_status": "Pending Review",
            "evidence_count": 0,
            "created_at": datetime(2026, 5, 13, 9, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 5, 13, 9, 0, tzinfo=timezone.utc),
            "metadata": {"requester_role": "coach"},
        }
        normal_priority_ticket = {
            "id": 11,
            "public_id": "KBC-000011",
            "learner_name": "User One",
            "learner_email": "user@example.com",
            "learner_phone": "01000000001",
            "category": "Technical",
            "technical_subcategory": "Teams",
            "inquiry": "User issue",
            "status": "Open",
            "status_reason": "",
            "priority": "Normal",
            "assigned_agent_id": None,
            "assigned_agent_name": None,
            "assigned_agent_username": None,
            "assigned_team": "Unassigned",
            "conversation_id": 13,
            "conversation_status": "open",
            "conversation_metadata": {"is_active_conversation": True},
            "last_message_at": None,
            "sla_status": "Pending Review",
            "evidence_count": 0,
            "created_at": datetime(2026, 5, 14, 9, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 5, 14, 9, 0, tzinfo=timezone.utc),
            "metadata": {"requester_role": "user"},
        }
        closed_high_priority_ticket = {
            "id": 12,
            "public_id": "KBC-000012",
            "learner_name": "Employer Closed",
            "learner_email": "employer.closed@example.com",
            "learner_phone": "01000000002",
            "category": "Technical",
            "technical_subcategory": "Teams",
            "inquiry": "Closed employer issue",
            "status": "Closed",
            "status_reason": "Closed via Agent",
            "priority": "High",
            "assigned_agent_id": None,
            "assigned_agent_name": None,
            "assigned_agent_username": None,
            "assigned_team": "Unassigned",
            "conversation_id": 14,
            "conversation_status": "closed",
            "conversation_metadata": {"is_active_conversation": False},
            "last_message_at": None,
            "sla_status": "On Track",
            "evidence_count": 0,
            "created_at": datetime(2026, 5, 15, 9, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 5, 15, 9, 0, tzinfo=timezone.utc),
            "metadata": {"requester_role": "employer"},
        }

        with (
            patch.object(services, "trigger_ticket_background_sync"),
            patch.object(services, "run_query", return_value=[normal_priority_ticket, closed_high_priority_ticket, high_priority_active_ticket]),
            patch.object(services, "apply_ticket_sla_policy", side_effect=lambda ticket, persist=True: ticket),
        ):
            result = services.list_admin_tickets()

        self.assertEqual([ticket["id"] for ticket in result["tickets"]], ["KBC-000010", "KBC-000011", "KBC-000012"])
        self.assertEqual(result["tickets"][0]["priority"], "High")

    def test_list_admin_tickets_supports_query_filters_and_pagination(self):
        base_ticket = {
            "learner_phone": "",
            "category": "Technical",
            "technical_subcategory": "LMS",
            "inquiry": "Needs help",
            "status_reason": "",
            "priority": "Normal",
            "assigned_agent_id": None,
            "assigned_agent_name": None,
            "assigned_agent_username": None,
            "assigned_team": services.ASSIGNED_TEAM_SUPPORT_DESK,
            "conversation_id": 13,
            "conversation_status": "open",
            "conversation_metadata": {"is_active_conversation": True},
            "last_message_at": None,
            "sla_status": "Pending Review",
            "evidence_count": 0,
            "is_archived": False,
            "metadata": {"requester_role": "user"},
        }
        older_matching_ticket = {
            **base_ticket,
            "id": 21,
            "public_id": "KBC-000021",
            "learner_name": "Alice Learner",
            "learner_email": "alice@example.com",
            "status": "Open",
            "created_at": datetime(2026, 5, 11, 9, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 5, 11, 9, 0, tzinfo=timezone.utc),
        }
        newer_matching_ticket = {
            **base_ticket,
            "id": 22,
            "public_id": "KBC-000022",
            "learner_name": "Alice Coach",
            "learner_email": "alice.coach@example.com",
            "status": "Open",
            "created_at": datetime(2026, 5, 12, 9, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 5, 12, 9, 0, tzinfo=timezone.utc),
        }
        hidden_status_ticket = {
            **base_ticket,
            "id": 23,
            "public_id": "KBC-000023",
            "learner_name": "Alice Pending",
            "learner_email": "alice.pending@example.com",
            "status": "Pending",
            "created_at": datetime(2026, 5, 13, 9, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 5, 13, 9, 0, tzinfo=timezone.utc),
        }
        hidden_archive_ticket = {
            **base_ticket,
            "id": 24,
            "public_id": "KBC-000024",
            "learner_name": "Alice Archived",
            "learner_email": "alice.archived@example.com",
            "status": "Open",
            "is_archived": True,
            "created_at": datetime(2026, 5, 14, 9, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 5, 14, 9, 0, tzinfo=timezone.utc),
        }

        pagination = {
            "page": 2,
            "pageSize": 1,
            "total": 2,
            "totalPages": 2,
            "hasNext": False,
            "hasPrevious": True,
            "isPaginated": True,
        }

        with (
            patch.object(services, "trigger_ticket_background_sync"),
            patch.object(
                services,
                "fetch_admin_ticket_page_for_actor",
                return_value=([newer_matching_ticket], pagination),
            ) as fetch_page,
        ):
            result = services.list_admin_tickets(
                query_params={
                    "search": "alice",
                    "status": "open",
                    "archiveScope": "active",
                    "sort": "oldest",
                    "page": "2",
                    "pageSize": "1",
                }
            )

        list_params = fetch_page.call_args.args[1]
        self.assertEqual([ticket["id"] for ticket in result["tickets"]], ["KBC-000022"])
        self.assertEqual(list_params["search"], "alice")
        self.assertEqual(list_params["status"], "Open")
        self.assertEqual(list_params["archiveScope"], "active")
        self.assertEqual(list_params["sort"], "oldest")
        self.assertEqual(list_params["page"], 2)
        self.assertEqual(list_params["pageSize"], 1)
        self.assertEqual(
            result["pagination"],
            {
                "page": 2,
                "pageSize": 1,
                "total": 2,
                "totalPages": 2,
                "hasNext": False,
                "hasPrevious": True,
                "isPaginated": True,
            },
        )
        self.assertEqual(result["filters"]["search"], "alice")
        self.assertEqual(result["filters"]["status"], "Open")
        self.assertEqual(result["filters"]["archiveScope"], "active")

    def test_list_admin_tickets_filters_by_actor_assignment_and_team(self):
        base_ticket = {
            "learner_phone": "",
            "category": "Technical",
            "technical_subcategory": "LMS",
            "inquiry": "Needs help",
            "status": "Open",
            "status_reason": "",
            "priority": "Normal",
            "conversation_id": 13,
            "conversation_status": "open",
            "conversation_metadata": {"is_active_conversation": True},
            "last_message_at": None,
            "sla_status": "Pending Review",
            "evidence_count": 0,
            "is_archived": False,
            "created_at": datetime(2026, 5, 14, 9, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 5, 14, 9, 0, tzinfo=timezone.utc),
            "metadata": {"requester_role": "user"},
        }
        support_ticket = {
            **base_ticket,
            "id": 31,
            "public_id": "KBC-000031",
            "learner_name": "Support Ticket",
            "learner_email": "support@example.com",
            "assigned_agent_id": 5,
            "assigned_agent_name": "Support Agent",
            "assigned_agent_username": "support.agent",
            "assigned_team": services.ASSIGNED_TEAM_SUPPORT_DESK,
        }
        operations_ticket = {
            **base_ticket,
            "id": 32,
            "public_id": "KBC-000032",
            "learner_name": "Operations Ticket",
            "learner_email": "operations@example.com",
            "technical_subcategory": "Coverage",
            "assigned_agent_id": 5,
            "assigned_agent_name": "Operations Agent",
            "assigned_agent_username": "operations.agent",
            "assigned_team": services.ASSIGNED_TEAM_LEARNING_PLAN,
        }
        other_agent_operations_ticket = {
            **operations_ticket,
            "id": 33,
            "public_id": "KBC-000033",
            "assigned_agent_id": 6,
        }

        with (
            patch.object(services, "trigger_ticket_background_sync"),
            patch.object(
                services,
                "run_query",
                return_value=[support_ticket, operations_ticket, other_agent_operations_ticket],
            ),
            patch.object(services, "apply_ticket_sla_policy", side_effect=lambda ticket, persist=True: ticket),
        ):
            result = services.list_admin_tickets(
                {"id": 5, "role": "admin", "metadata": {"legacy_admin_access": True}},
                query_params={"assigned": "me", "team": "operations", "sort": "newest"},
            )

        self.assertEqual([ticket["id"] for ticket in result["tickets"]], ["KBC-000032"])
        self.assertFalse(result["pagination"]["isPaginated"])
        self.assertEqual(result["filters"]["assigned"], "me")
        self.assertEqual(result["filters"]["team"], "operations")

    def test_list_admin_tickets_supports_dashboard_filter_param(self):
        base_ticket = {
            "learner_phone": "",
            "category": "Technical",
            "technical_subcategory": "LMS",
            "inquiry": "Needs help",
            "status": "Pending",
            "priority": "Normal",
            "assigned_agent_id": None,
            "assigned_agent_name": None,
            "assigned_agent_username": None,
            "assigned_team": services.ASSIGNED_TEAM_SUPPORT_DESK,
            "conversation_id": 13,
            "conversation_status": "open",
            "conversation_metadata": {"is_active_conversation": True},
            "last_message_at": None,
            "sla_status": "Pending Review",
            "evidence_count": 0,
            "is_archived": False,
            "created_at": datetime(2026, 5, 14, 9, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 5, 14, 9, 0, tzinfo=timezone.utc),
            "metadata": {"requester_role": "user"},
        }
        quick_ticket = {
            **base_ticket,
            "id": 41,
            "public_id": "KBC-000041",
            "learner_name": "Quick Ticket",
            "learner_email": "quick@example.com",
            "status_reason": services.STATUS_REASON_QUICK_TICKET,
        }
        escalation_ticket = {
            **base_ticket,
            "id": 42,
            "public_id": "KBC-000042",
            "learner_name": "Escalation Ticket",
            "learner_email": "escalation@example.com",
            "status_reason": services.STATUS_REASON_ESCALATION,
        }

        with (
            patch.object(services, "trigger_ticket_background_sync"),
            patch.object(services, "run_query", return_value=[quick_ticket, escalation_ticket]),
            patch.object(services, "apply_ticket_sla_policy", side_effect=lambda ticket, persist=True: ticket),
        ):
            result = services.list_admin_tickets(query_params={"dashboardFilter": "quickResolution"})

        self.assertEqual([ticket["id"] for ticket in result["tickets"]], ["KBC-000041"])
        self.assertEqual(result["filters"]["dashboardFilter"], "quickResolution")

    def test_list_admin_tickets_supports_learning_plan_other_dashboard_filter(self):
        base_ticket = {
            "learner_phone": "",
            "category": "Technical",
            "inquiry": "Needs help",
            "status": "Pending",
            "status_reason": "",
            "priority": "Normal",
            "assigned_agent_id": None,
            "assigned_agent_name": None,
            "assigned_agent_username": None,
            "assigned_team": services.ASSIGNED_TEAM_LEARNING_PLAN,
            "conversation_id": 13,
            "conversation_status": "open",
            "conversation_metadata": {"is_active_conversation": True},
            "last_message_at": None,
            "sla_status": "Pending Review",
            "evidence_count": 0,
            "is_archived": False,
            "created_at": datetime(2026, 5, 14, 9, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 5, 14, 9, 0, tzinfo=timezone.utc),
            "metadata": {"requester_role": "user"},
        }
        other_learning_plan_ticket = {
            **base_ticket,
            "id": 43,
            "public_id": "KBC-000043",
            "learner_name": "Learning Plan Transfer",
            "learner_email": "learning-plan@example.com",
            "technical_subcategory": "LMS",
        }
        coverage_ticket = {
            **base_ticket,
            "id": 44,
            "public_id": "KBC-000044",
            "learner_name": "Coverage Ticket",
            "learner_email": "coverage@example.com",
            "technical_subcategory": "Coverage",
        }

        with (
            patch.object(services, "trigger_ticket_background_sync"),
            patch.object(services, "run_query", return_value=[other_learning_plan_ticket, coverage_ticket]),
            patch.object(services, "apply_ticket_sla_policy", side_effect=lambda ticket, persist=True: ticket),
        ):
            result = services.list_admin_tickets(query_params={"dashboardFilter": "learningPlanOther"})

        self.assertEqual([ticket["id"] for ticket in result["tickets"]], ["KBC-000043"])
        self.assertEqual(result["filters"]["dashboardFilter"], "learningPlanOther")

    def test_admin_ticket_metrics_supports_dashboard_scope_counts(self):
        base_ticket = {
            "learner_phone": "",
            "category": "Technical",
            "inquiry": "Needs help",
            "status_reason": "",
            "priority": "Normal",
            "assigned_agent_id": 5,
            "assigned_agent_name": "Operations Agent",
            "assigned_agent_username": "operations.agent",
            "conversation_id": 13,
            "conversation_status": "open",
            "conversation_metadata": {"is_active_conversation": True},
            "last_message_at": None,
            "sla_status": "On Track",
            "evidence_count": 0,
            "is_archived": False,
            "created_at": datetime(2026, 5, 14, 9, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 5, 14, 9, 0, tzinfo=timezone.utc),
            "metadata": {"requester_role": "user"},
        }
        coverage_ticket = {
            **base_ticket,
            "id": 45,
            "public_id": "KBC-000045",
            "learner_name": "Coverage Ticket",
            "learner_email": "coverage@example.com",
            "technical_subcategory": "Coverage",
            "status": "Pending",
            "assigned_team": services.ASSIGNED_TEAM_LEARNING_PLAN,
        }
        other_learning_plan_ticket = {
            **base_ticket,
            "id": 46,
            "public_id": "KBC-000046",
            "learner_name": "Learning Plan Transfer",
            "learner_email": "learning-plan@example.com",
            "technical_subcategory": "LMS",
            "status": "Open",
            "assigned_team": services.ASSIGNED_TEAM_LEARNING_PLAN,
        }
        support_ticket = {
            **base_ticket,
            "id": 47,
            "public_id": "KBC-000047",
            "learner_name": "Support Ticket",
            "learner_email": "support@example.com",
            "technical_subcategory": "LMS",
            "status": "Open",
            "assigned_team": services.ASSIGNED_TEAM_SUPPORT_DESK,
        }

        expected_metrics = {
            "total": 1,
            "open": 0,
            "pending": 1,
            "escalation": 0,
            "closed": 0,
            "slaBreached": 0,
            "coverage": 1,
            "quickResolution": 0,
            "sections": {"coverage": 1, "learningPlanOther": 1},
        }

        with (
            patch.object(services, "trigger_ticket_background_sync"),
            patch.object(services, "get_admin_ticket_metrics_from_sql", return_value=expected_metrics) as get_metrics_from_sql,
        ):
            result = services.get_admin_ticket_metrics(
                {"id": 5, "role": "admin", "metadata": {"legacy_admin_access": True}},
                query_params={
                    "assigned": "me",
                    "team": "operations",
                    "dashboardFilter": "coverage",
                    "status": "closed",
                    "search": "ignored",
                },
            )

        metrics_params = get_metrics_from_sql.call_args.args[1]
        self.assertEqual(result["metrics"]["total"], 1)
        self.assertEqual(result["metrics"]["pending"], 1)
        self.assertEqual(result["metrics"]["coverage"], 1)
        self.assertEqual(result["metrics"]["sections"], {"coverage": 1, "learningPlanOther": 1})
        self.assertEqual(metrics_params["dashboardFilter"], "coverage")
        self.assertEqual(metrics_params["status"], "")
        self.assertEqual(metrics_params["search"], "")
        self.assertEqual(result["filters"]["assigned"], "me")
        self.assertEqual(result["filters"]["team"], "operations")
        self.assertEqual(result["filters"]["dashboardFilter"], "coverage")
        self.assertEqual(result["filters"]["status"], "")
        self.assertEqual(result["filters"]["search"], "")

    def test_list_admin_tickets_hides_open_pre_submission_support_flow_tickets(self):
        visible_ticket = {
            "id": 11,
            "public_id": "KBC-000011",
            "learner_name": "User One",
            "learner_email": "user@example.com",
            "learner_phone": "01000000001",
            "category": "Technical",
            "technical_subcategory": "Teams",
            "inquiry": "User issue",
            "status": "Open",
            "status_reason": "",
            "priority": "Normal",
            "assigned_agent_id": None,
            "assigned_agent_name": None,
            "assigned_agent_username": None,
            "assigned_team": "Unassigned",
            "conversation_id": 13,
            "conversation_status": "open",
            "conversation_metadata": {"is_active_conversation": True},
            "last_message_at": None,
            "sla_status": "Pending Review",
            "evidence_count": 0,
            "is_archived": False,
            "created_at": datetime(2026, 5, 14, 9, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 5, 14, 9, 0, tzinfo=timezone.utc),
            "metadata": {"requester_role": "user"},
        }
        hidden_booking_ticket = {
            **visible_ticket,
            "id": 12,
            "public_id": "KBC-000012",
            "metadata": {
                "requester_role": "user",
                services.SUPPORT_FLOW_STAGE_METADATA_KEY: services.SUPPORT_FLOW_STAGE_BOOKING_IN_PROGRESS,
            },
        }
        hidden_cancelled_direct_booking_ticket = {
            **visible_ticket,
            "id": 13,
            "public_id": "KBC-000013",
            "metadata": {"requester_role": "user"},
            "latest_session_request_status": "cancelled",
            "latest_session_request_metadata": {"return_path": "/support/options"},
        }
        visible_cancelled_chat_booking_ticket = {
            **visible_ticket,
            "id": 14,
            "public_id": "KBC-000014",
            "metadata": {"requester_role": "user", "live_chat_requested": True},
            "latest_session_request_status": "cancelled",
            "latest_session_request_metadata": {"return_path": "/support/options"},
        }

        with (
            patch.object(services, "trigger_ticket_background_sync"),
            patch.object(
                services,
                "run_query",
                return_value=[
                    hidden_booking_ticket,
                    hidden_cancelled_direct_booking_ticket,
                    visible_cancelled_chat_booking_ticket,
                    visible_ticket,
                ],
            ),
            patch.object(services, "apply_ticket_sla_policy", side_effect=lambda ticket, persist=True: ticket),
        ):
            result = services.list_admin_tickets()

        self.assertEqual([ticket["id"] for ticket in result["tickets"]], ["KBC-000014", "KBC-000011"])

    def test_list_admin_tickets_scopes_support_and_operations_access(self):
        base_ticket = {
            "id": 11,
            "public_id": "KBC-000011",
            "learner_name": "User One",
            "learner_email": "user@example.com",
            "learner_phone": "01000000001",
            "category": "Technical",
            "technical_subcategory": "Teams",
            "inquiry": "User issue",
            "status": "Open",
            "status_reason": "",
            "priority": "Normal",
            "assigned_agent_id": None,
            "assigned_agent_name": None,
            "assigned_agent_username": None,
            "assigned_team": services.ASSIGNED_TEAM_UNASSIGNED,
            "conversation_id": 13,
            "conversation_status": "open",
            "conversation_metadata": {"is_active_conversation": True},
            "last_message_at": None,
            "sla_status": "Pending Review",
            "evidence_count": 0,
            "is_archived": False,
            "created_at": datetime(2026, 5, 14, 9, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 5, 14, 9, 0, tzinfo=timezone.utc),
            "metadata": {"requester_role": "user"},
        }
        support_ticket = {
            **base_ticket,
            "id": 11,
            "public_id": "KBC-000011",
            "created_at": datetime(2026, 5, 14, 11, 0, tzinfo=timezone.utc),
        }
        coverage_ticket = {
            **base_ticket,
            "id": 12,
            "public_id": "KBC-000012",
            "technical_subcategory": "Coverage",
            "status_reason": services.STATUS_REASON_COVERAGE_TICKET,
            "created_at": datetime(2026, 5, 14, 10, 0, tzinfo=timezone.utc),
        }
        learning_plan_ticket = {
            **base_ticket,
            "id": 13,
            "public_id": "KBC-000013",
            "technical_subcategory": "LMS",
            "assigned_team": services.ASSIGNED_TEAM_LEARNING_PLAN,
            "created_at": datetime(2026, 5, 14, 9, 0, tzinfo=timezone.utc),
        }

        support_actor = {
            "id": 1,
            "role": "agent",
            "metadata": {"legacy_support_access": True, "legacy_operations_access": False},
        }
        operations_actor = {
            "id": 2,
            "role": "agent",
            "metadata": {"legacy_support_access": False, "legacy_operations_access": True},
        }
        support_operations_actor = {
            "id": 3,
            "role": "agent",
            "metadata": {"legacy_support_access": True, "legacy_operations_access": True},
        }
        admin_actor = {
            "id": 4,
            "role": "admin",
            "metadata": {"legacy_admin_access": True},
        }

        with (
            patch.object(services, "trigger_ticket_background_sync"),
            patch.object(services, "run_query", return_value=[support_ticket, coverage_ticket, learning_plan_ticket]),
            patch.object(services, "apply_ticket_sla_policy", side_effect=lambda ticket, persist=True: ticket),
        ):
            support_result = services.list_admin_tickets(support_actor)
            operations_result = services.list_admin_tickets(operations_actor)
            support_operations_result = services.list_admin_tickets(support_operations_actor)
            admin_result = services.list_admin_tickets(admin_actor)

        self.assertEqual([ticket["id"] for ticket in support_result["tickets"]], ["KBC-000011"])
        self.assertEqual(
            [ticket["id"] for ticket in operations_result["tickets"]],
            ["KBC-000012", "KBC-000013"],
        )
        self.assertEqual(
            [ticket["id"] for ticket in support_operations_result["tickets"]],
            ["KBC-000011", "KBC-000012", "KBC-000013"],
        )
        self.assertEqual(
            [ticket["id"] for ticket in admin_result["tickets"]],
            ["KBC-000011", "KBC-000012", "KBC-000013"],
        )

    def test_get_admin_ticket_detail_rejects_support_only_coverage_ticket(self):
        actor = {
            "id": 1,
            "role": "agent",
            "metadata": {"legacy_support_access": True, "legacy_operations_access": False},
        }
        ticket_scope = {
            "public_id": "KBC-000012",
            "technical_subcategory": "Coverage",
            "assigned_team": services.ASSIGNED_TEAM_SUPPORT_DESK,
            "metadata": {},
        }

        with (
            patch.object(services, "fetch_ticket_scope_record", return_value=ticket_scope),
            patch.object(services, "sync_open_ticket_inactivity") as sync_open_ticket_inactivity,
            patch.object(services, "fetch_admin_ticket_detail") as fetch_admin_ticket_detail,
        ):
            with self.assertRaises(services.ApiError) as raised_error:
                services.get_admin_ticket_detail_response("KBC-000012", actor)

        self.assertEqual(raised_error.exception.status_code, 403)
        sync_open_ticket_inactivity.assert_not_called()
        fetch_admin_ticket_detail.assert_not_called()

    def test_list_coverage_tutor_request_history_rows_groups_rows_by_ticket(self):
        request_history_rows = [
            {"ticket_id": 21, "payload": {"cardId": "card-1"}, "created_at": datetime(2026, 5, 14, 9, 0, tzinfo=timezone.utc)},
            {"ticket_id": 22, "payload": {"cardId": "card-2"}, "created_at": datetime(2026, 5, 14, 9, 5, tzinfo=timezone.utc)},
            {"ticket_id": 21, "payload": {"cardId": "card-3"}, "created_at": datetime(2026, 5, 14, 9, 10, tzinfo=timezone.utc)},
        ]

        with patch.object(services, "run_query", return_value=request_history_rows) as run_query:
            result = services.list_coverage_tutor_request_history_rows(["21", 22, None, 0, "bad"])

        self.assertEqual(run_query.call_count, 1)
        self.assertEqual(run_query.call_args.args[1], [[21, 22]])
        self.assertEqual([row["payload"]["cardId"] for row in result[21]], ["card-1", "card-3"])
        self.assertEqual([row["payload"]["cardId"] for row in result[22]], ["card-2"])

    def test_trigger_ticket_background_sync_skips_recent_restart(self):
        original_in_progress = services._ticket_background_sync_in_progress
        original_last_started = services._last_ticket_background_sync_started_monotonic
        services._ticket_background_sync_in_progress = False
        services._last_ticket_background_sync_started_monotonic = 100.0

        try:
            with (
                patch.object(services, "get_ticket_background_sync_min_interval_seconds", return_value=10),
                patch.object(services.time, "monotonic", return_value=105.0),
                patch.object(services.threading, "Thread") as thread_cls,
            ):
                services.trigger_ticket_background_sync()

            thread_cls.assert_not_called()
        finally:
            services._ticket_background_sync_in_progress = original_in_progress
            services._last_ticket_background_sync_started_monotonic = original_last_started


class AdminLoginTests(SimpleTestCase):
    def test_admin_login_accepts_kbc_auth_password_for_support_access_user(self):
        legacy_user = {
            "id": 4,
            "username": "omar1",
            "first_name": "Omar",
            "last_name": "One",
            "full_name": "Omar One",
            "email": "omar1@kentbusinesscollege.com",
            "password_hash": make_password("omar1"),
            "is_staff": False,
            "is_superuser": False,
            "is_active": True,
            "has_support_access": True,
            "has_admin_access": False,
        }
        synced_agent = {
            "id": 4,
            "username": "omar1",
            "full_name": "Omar One",
            "email": "omar1@kentbusinesscollege.com",
            "role": "agent",
            "metadata": {},
        }
        registered_session = {
            "id": 4,
            "username": "omar1",
            "fullName": "Omar One",
            "email": "omar1@kentbusinesscollege.com",
            "role": "agent",
            "sessionActive": True,
            "consoleStatus": "Off",
        }

        with (
            patch.object(services, "fetch_agent_account_by_username", return_value=None),
            patch.object(services, "run_query_one", return_value=None),
            patch.object(services, "fetch_legacy_support_user_by_username", return_value=legacy_user) as fetch_legacy_support_user_by_username,
            patch.object(services, "sync_support_staff_account_from_legacy_auth_user", return_value=synced_agent) as sync_support_staff_account_from_legacy_auth_user,
            patch.object(services, "register_agent_session", return_value=registered_session) as register_agent_session,
        ):
            response = services.get_admin_login_response(
                {"username": "Omar1", "password": "omar1", "instanceId": "instance-1"}
            )

        self.assertEqual(response["admin"], registered_session)
        self.assertEqual(response["message"], "Login successful.")
        fetch_legacy_support_user_by_username.assert_called_once_with("omar1")
        sync_support_staff_account_from_legacy_auth_user.assert_called_once_with(legacy_user)
        register_agent_session.assert_called_once_with("omar1", "instance-1", "Off")

    def test_admin_login_accepts_kbc_auth_password_for_admin_access_user(self):
        legacy_user = {
            "id": 5,
            "username": "ayman",
            "first_name": "Ayman",
            "last_name": "Admin",
            "full_name": "Ayman Admin",
            "email": "ayman@kentbusinesscollege.com",
            "password_hash": make_password("admin-pass"),
            "is_staff": False,
            "is_superuser": False,
            "is_active": True,
            "has_support_access": False,
            "has_admin_access": True,
        }
        synced_agent = {
            "id": 5,
            "username": "ayman",
            "full_name": "Ayman Admin",
            "email": "ayman@kentbusinesscollege.com",
            "role": "admin",
            "metadata": {},
        }
        registered_session = {
            "id": 5,
            "username": "ayman",
            "fullName": "Ayman Admin",
            "email": "ayman@kentbusinesscollege.com",
            "role": "admin",
            "sessionActive": True,
            "consoleStatus": "Off",
        }

        with (
            patch.object(services, "fetch_agent_account_by_username", return_value=None),
            patch.object(services, "run_query_one", return_value=None),
            patch.object(services, "fetch_legacy_support_user_by_username", return_value=legacy_user) as fetch_legacy_support_user_by_username,
            patch.object(services, "sync_support_staff_account_from_legacy_auth_user", return_value=synced_agent) as sync_support_staff_account_from_legacy_auth_user,
            patch.object(services, "register_agent_session", return_value=registered_session) as register_agent_session,
        ):
            response = services.get_admin_login_response(
                {"username": "Ayman", "password": "admin-pass", "instanceId": "instance-2"}
            )

        self.assertEqual(response["admin"], registered_session)
        self.assertEqual(response["message"], "Login successful.")
        fetch_legacy_support_user_by_username.assert_called_once_with("ayman")
        sync_support_staff_account_from_legacy_auth_user.assert_called_once_with(legacy_user)
        register_agent_session.assert_called_once_with("ayman", "instance-2", "Off")

    def test_admin_login_accepts_kbc_auth_password_for_operations_access_user(self):
        legacy_user = {
            "id": 9,
            "username": "operations1",
            "first_name": "Operations",
            "last_name": "Agent",
            "full_name": "Operations Agent",
            "email": "operations.agent@kentbusinesscollege.com",
            "password_hash": make_password("ops-pass"),
            "is_staff": False,
            "is_superuser": False,
            "is_active": True,
            "has_support_access": False,
            "has_operations_access": True,
            "has_admin_access": False,
        }
        synced_agent = {
            "id": 9,
            "username": "operations1",
            "full_name": "Operations Agent",
            "email": "operations.agent@kentbusinesscollege.com",
            "role": "agent",
            "metadata": {},
        }
        registered_session = {
            "id": 9,
            "username": "operations1",
            "fullName": "Operations Agent",
            "email": "operations.agent@kentbusinesscollege.com",
            "role": "agent",
            "sessionActive": True,
            "consoleStatus": "Off",
        }

        with (
            patch.object(services, "fetch_agent_account_by_username", return_value=None),
            patch.object(services, "run_query_one", return_value=None),
            patch.object(services, "fetch_legacy_support_user_by_username", return_value=legacy_user) as fetch_legacy_support_user_by_username,
            patch.object(services, "sync_support_staff_account_from_legacy_auth_user", return_value=synced_agent) as sync_support_staff_account_from_legacy_auth_user,
            patch.object(services, "register_agent_session", return_value=registered_session) as register_agent_session,
        ):
            response = services.get_admin_login_response(
                {"username": "Operations1", "password": "ops-pass", "instanceId": "instance-ops"}
            )

        self.assertEqual(response["admin"], registered_session)
        self.assertEqual(response["message"], "Login successful.")
        fetch_legacy_support_user_by_username.assert_called_once_with("operations1")
        sync_support_staff_account_from_legacy_auth_user.assert_called_once_with(legacy_user)
        register_agent_session.assert_called_once_with("operations1", "instance-ops", "Off")

    def test_admin_login_accepts_staff_password_for_operations_access_account(self):
        operations_agent = {
            "id": 9,
            "username": "operations1",
            "full_name": "Operations Agent",
            "email": "operations.agent@kentbusinesscollege.com",
            "account_scope": "staff",
            "role": "agent",
            "is_active": True,
            "metadata": {
                "legacy_support_access": False,
                "legacy_operations_access": True,
                "legacy_admin_access": False,
                "password_hash": make_password("ops-pass"),
            },
        }
        registered_session = {
            "id": 9,
            "username": "operations1",
            "fullName": "Operations Agent",
            "email": "operations.agent@kentbusinesscollege.com",
            "role": "agent",
            "sessionActive": True,
            "consoleStatus": "Off",
        }

        with (
            patch.object(services, "fetch_agent_account_by_username", return_value=operations_agent),
            patch.object(services, "run_query_one") as run_query_one,
            patch.object(services, "fetch_legacy_support_user_by_username") as fetch_legacy_support_user_by_username,
            patch.object(services, "register_agent_session", return_value=registered_session) as register_agent_session,
        ):
            response = services.get_admin_login_response(
                {"username": "Operations1", "password": "ops-pass", "instanceId": "instance-ops"}
            )

        self.assertEqual(response["admin"], registered_session)
        self.assertEqual(response["message"], "Login successful.")
        run_query_one.assert_not_called()
        fetch_legacy_support_user_by_username.assert_not_called()
        register_agent_session.assert_called_once_with("operations1", "instance-ops", "Off")

    def test_admin_login_accepts_staff_password_for_custom_team_access_account(self):
        curriculum_agent = {
            "id": 31,
            "username": "curriculum1",
            "full_name": "Curriculum Agent",
            "email": "curriculum.agent@kentbusinesscollege.com",
            "account_scope": "staff",
            "role": "agent",
            "is_active": True,
            "team_access": [
                {
                    "key": "curriculum",
                    "name": "Curriculum Team",
                    "assignedTeam": "Curriculum Team",
                    "canReceiveTickets": True,
                },
            ],
            "metadata": {
                "legacy_support_access": False,
                "legacy_operations_access": False,
                "legacy_admin_access": False,
                "password_hash": make_password("curriculum-pass"),
            },
        }
        registered_session = {
            "id": 31,
            "username": "curriculum1",
            "fullName": "Curriculum Agent",
            "email": "curriculum.agent@kentbusinesscollege.com",
            "role": "agent",
            "sessionActive": True,
            "consoleStatus": "Off",
        }

        with (
            patch.object(services, "fetch_agent_account_by_username", return_value=curriculum_agent),
            patch.object(services, "run_query_one") as run_query_one,
            patch.object(services, "fetch_legacy_support_user_by_username") as fetch_legacy_support_user_by_username,
            patch.object(services, "register_agent_session", return_value=registered_session) as register_agent_session,
        ):
            response = services.get_admin_login_response(
                {"username": "Curriculum1", "password": "curriculum-pass", "instanceId": "instance-curriculum"}
            )

        self.assertEqual(response["admin"], registered_session)
        self.assertEqual(response["message"], "Login successful.")
        run_query_one.assert_not_called()
        fetch_legacy_support_user_by_username.assert_not_called()
        register_agent_session.assert_called_once_with("curriculum1", "instance-curriculum", "Off")

    def test_admin_login_rejects_staff_password_account_without_team_or_admin_access(self):
        no_access_agent = {
            "id": 32,
            "username": "noaccess1",
            "full_name": "No Access",
            "email": "noaccess@kentbusinesscollege.com",
            "account_scope": "staff",
            "role": "agent",
            "is_active": True,
            "metadata": {
                "legacy_support_access": False,
                "legacy_operations_access": False,
                "legacy_admin_access": False,
                "password_hash": make_password("no-access-pass"),
            },
        }

        with (
            patch.object(services, "fetch_agent_account_by_username", return_value=no_access_agent),
            patch.object(services, "fetch_optional_any_account_team_access", return_value=False),
            patch.object(services, "fetch_legacy_support_user_by_username") as fetch_legacy_support_user_by_username,
            patch.object(services, "register_agent_session") as register_agent_session,
        ):
            with self.assertRaises(services.ApiError) as error_context:
                services.get_admin_login_response(
                    {"username": "noaccess1", "password": "no-access-pass", "instanceId": "instance-noaccess"}
                )

        self.assertEqual(error_context.exception.status_code, 403)
        self.assertEqual(error_context.exception.message, "This account must have team, support, operations, or admin access.")
        fetch_legacy_support_user_by_username.assert_not_called()
        register_agent_session.assert_not_called()

    def test_admin_login_rejects_kbc_auth_user_without_support_or_admin_access_after_password_check(self):
        legacy_user = {
            "id": 6,
            "username": "coach1",
            "first_name": "Coach",
            "last_name": "One",
            "full_name": "Coach One",
            "email": "coach1@kentbusinesscollege.com",
            "password_hash": make_password("coach-pass"),
            "is_staff": False,
            "is_superuser": False,
            "is_active": True,
            "has_support_access": False,
            "has_admin_access": False,
        }

        with (
            patch.object(services, "fetch_agent_account_by_username", return_value=None),
            patch.object(services, "run_query_one", return_value=None),
            patch.object(services, "fetch_legacy_support_user_by_username", return_value=legacy_user),
            patch.object(services, "sync_support_staff_account_from_legacy_auth_user") as sync_support_staff_account_from_legacy_auth_user,
            patch.object(services, "register_agent_session") as register_agent_session,
        ):
            with self.assertRaises(services.ApiError) as error_context:
                services.get_admin_login_response(
                    {"username": "coach1", "password": "coach-pass", "instanceId": "instance-3"}
                )

        self.assertEqual(error_context.exception.status_code, 403)
        self.assertEqual(error_context.exception.message, "This account must have team, support, operations, or admin access.")
        sync_support_staff_account_from_legacy_auth_user.assert_not_called()
        register_agent_session.assert_not_called()

    def test_admin_login_rejects_kbc_auth_user_without_support_or_admin_access(self):
        with (
            patch.object(services, "fetch_agent_account_by_username", return_value=None),
            patch.object(services, "run_query_one", return_value=None),
            patch.object(services, "fetch_legacy_support_user_by_username", return_value=None),
        ):
            with self.assertRaises(services.ApiError) as error_context:
                services.get_admin_login_response({"username": "coach1", "password": "coach-pass", "instanceId": "instance-1"})

        self.assertEqual(error_context.exception.status_code, 401)
        self.assertEqual(error_context.exception.message, "Invalid username or password.")

    def test_build_microsoft_admin_authorize_url_uses_expected_query_parameters(self):
        with (
            patch.object(services.settings, "AZURE_LOGIN_TENANT_ID", "tenant-123"),
            patch.object(services.settings, "AZURE_LOGIN_CLIENT_ID", "client-123"),
            patch.object(services.settings, "AZURE_LOGIN_CLIENT_SECRET", "secret-123"),
        ):
            authorize_url = services.build_microsoft_admin_authorize_url(
                redirect_uri="http://127.0.0.1:3000/api/admin/microsoft/callback",
                state="state-123",
                nonce="nonce-123",
            )

        self.assertIn("login.microsoftonline.com/tenant-123/oauth2/v2.0/authorize", authorize_url)
        self.assertIn("client_id=client-123", authorize_url)
        self.assertIn("response_type=code", authorize_url)
        self.assertIn("state=state-123", authorize_url)
        self.assertIn("nonce=nonce-123", authorize_url)

    def test_admin_microsoft_login_allows_entra_directory_admin_and_registers_session(self):
        id_token = build_unverified_jwt(
            {
                "nonce": "nonce-123",
                "preferred_username": "omar1@kentbusinesscollege.com",
                "name": "Omar One",
            }
        )
        registered_session = {
            "id": 23,
            "username": "omar1",
            "fullName": "Omar One",
            "email": "omar1@kentbusinesscollege.com",
            "role": "admin",
            "sessionActive": True,
            "consoleStatus": "Off",
        }

        with (
            patch.object(services.settings, "AZURE_LOGIN_TENANT_ID", "tenant-123"),
            patch.object(services.settings, "AZURE_LOGIN_CLIENT_ID", "client-123"),
            patch.object(services.settings, "AZURE_LOGIN_CLIENT_SECRET", "secret-123"),
            patch.object(
                services,
                "post_form_request",
                return_value=(
                    True,
                    True,
                    200,
                    {
                        "access_token": "access-token-123",
                        "id_token": id_token,
                    },
                ),
            ),
            patch.object(
                services,
                "fetch_microsoft_graph_me",
                return_value=(
                    True,
                    True,
                    200,
                    {
                        "id": "entra-object-123",
                        "mail": "omar1@kentbusinesscollege.com",
                        "userPrincipalName": "omar1@kentbusinesscollege.com",
                        "displayName": "Omar One",
                    },
                ),
            ),
            patch.object(
                services,
                "fetch_microsoft_graph_directory_roles",
                return_value=(
                    True,
                    True,
                    200,
                    [
                        {
                            "id": "role-1",
                            "displayName": "User Administrator",
                            "roleTemplateId": "role-template-1",
                        }
                    ],
                ),
            ) as fetch_microsoft_graph_directory_roles,
            patch.object(
                services,
                "sync_support_staff_account_from_entra_directory_user",
                return_value={
                    "id": 23,
                    "username": "omar1",
                    "full_name": "Omar One",
                    "email": "omar1@kentbusinesscollege.com",
                    "role": "admin",
                    "account_scope": "staff",
                    "is_active": True,
                    "metadata": {},
                },
            ) as sync_support_staff_account_from_entra_directory_user,
            patch.object(services, "register_agent_session", return_value=registered_session) as register_agent_session,
        ):
            response = services.get_admin_microsoft_login_response(
                {
                    "code": "auth-code-123",
                    "redirectUri": "http://127.0.0.1:3000/api/admin/microsoft/callback",
                    "expectedNonce": "nonce-123",
                    "instanceId": "instance-123",
                    "consoleStatus": "Off",
                }
            )

        self.assertEqual(response["admin"], registered_session)
        fetch_microsoft_graph_directory_roles.assert_called_once_with("access-token-123")
        sync_support_staff_account_from_entra_directory_user.assert_called_once()
        sync_args = sync_support_staff_account_from_entra_directory_user.call_args.args
        self.assertEqual(sync_args[0]["id"], "entra-object-123")
        self.assertEqual(sync_args[2], "admin")
        register_agent_session.assert_called_once_with("omar1", "instance-123", "Off")

    def test_admin_microsoft_login_rejects_user_without_entra_directory_admin_role(self):
        id_token = build_unverified_jwt(
            {
                "nonce": "nonce-123",
                "preferred_username": "learner@kentbusinesscollege.com",
            }
        )

        with (
            patch.object(services.settings, "AZURE_LOGIN_TENANT_ID", "tenant-123"),
            patch.object(services.settings, "AZURE_LOGIN_CLIENT_ID", "client-123"),
            patch.object(services.settings, "AZURE_LOGIN_CLIENT_SECRET", "secret-123"),
            patch.object(
                services,
                "post_form_request",
                return_value=(True, True, 200, {"access_token": "access-token-123", "id_token": id_token}),
            ),
            patch.object(
                services,
                "fetch_microsoft_graph_me",
                return_value=(
                    True,
                    True,
                    200,
                    {
                        "id": "entra-object-456",
                        "mail": "learner@kentbusinesscollege.com",
                        "userPrincipalName": "learner@kentbusinesscollege.com",
                        "displayName": "Learner One",
                    },
                ),
            ),
            patch.object(
                services,
                "fetch_microsoft_graph_directory_roles",
                return_value=(True, True, 200, []),
            ),
            patch.object(
                services,
                "_login_support_access_agent_from_entra",
                side_effect=services.ApiError(403, "Your Microsoft account does not have access to the support portal."),
            ),
        ):
            with self.assertRaises(services.ApiError) as error_context:
                services.get_admin_microsoft_login_response(
                    {
                        "code": "auth-code-123",
                        "redirectUri": "http://127.0.0.1:3000/api/admin/microsoft/callback",
                        "expectedNonce": "nonce-123",
                        "instanceId": "instance-123",
                    }
                )

        self.assertEqual(error_context.exception.status_code, 403)
        self.assertEqual(error_context.exception.message, "Your Microsoft account does not have access to the support portal.")

    def test_admin_microsoft_login_allows_custom_team_access_user_without_entra_admin_role(self):
        id_token = build_unverified_jwt(
            {
                "nonce": "nonce-curriculum",
                "preferred_username": "curriculum.agent@kentbusinesscollege.com",
            }
        )
        curriculum_agent = {
            "id": 31,
            "username": "curriculum1",
            "full_name": "Curriculum Agent",
            "email": "curriculum.agent@kentbusinesscollege.com",
            "role": "agent",
            "account_scope": "staff",
            "is_active": True,
            "team_access": [
                {
                    "key": "curriculum",
                    "name": "Curriculum Team",
                    "assignedTeam": "Curriculum Team",
                    "canReceiveTickets": True,
                },
            ],
            "metadata": {
                "legacy_support_access": False,
                "legacy_operations_access": False,
                "legacy_admin_access": False,
            },
        }
        refreshed_agent = {
            **curriculum_agent,
            "metadata": {
                **curriculum_agent["metadata"],
                "entra_object_id": "entra-object-curriculum",
                "entra_email": "curriculum.agent@kentbusinesscollege.com",
            },
        }
        registered_session = {
            "id": 31,
            "username": "curriculum1",
            "fullName": "Curriculum Agent",
            "email": "curriculum.agent@kentbusinesscollege.com",
            "role": "agent",
            "sessionActive": True,
            "consoleStatus": "Off",
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services.settings, "AZURE_LOGIN_TENANT_ID", "tenant-123"),
            patch.object(services.settings, "AZURE_LOGIN_CLIENT_ID", "client-123"),
            patch.object(services.settings, "AZURE_LOGIN_CLIENT_SECRET", "secret-123"),
            patch.object(
                services,
                "post_form_request",
                return_value=(True, True, 200, {"access_token": "access-token-curriculum", "id_token": id_token}),
            ),
            patch.object(
                services,
                "fetch_microsoft_graph_me",
                return_value=(
                    True,
                    True,
                    200,
                    {
                        "id": "entra-object-curriculum",
                        "mail": "curriculum.agent@kentbusinesscollege.com",
                        "userPrincipalName": "curriculum.agent@kentbusinesscollege.com",
                        "displayName": "Curriculum Agent",
                    },
                ),
            ),
            patch.object(services, "fetch_microsoft_graph_directory_roles", return_value=(True, True, 200, [])),
            patch.object(services, "fetch_staff_support_account_by_email", return_value=curriculum_agent) as fetch_staff_support_account_by_email,
            patch.object(services, "refresh_staff_account_legacy_access", return_value=curriculum_agent) as refresh_staff_account_legacy_access,
            patch.object(services, "fetch_legacy_support_user_by_email") as fetch_legacy_support_user_by_email,
            patch.object(services, "persist_agent_metadata") as persist_agent_metadata,
            patch.object(services, "connection", mock_connection),
            patch.object(services, "fetch_agent_account_by_id", return_value=refreshed_agent),
            patch.object(services, "register_agent_session", return_value=registered_session) as register_agent_session,
        ):
            response = services.get_admin_microsoft_login_response(
                {
                    "code": "auth-code-curriculum",
                    "redirectUri": "http://127.0.0.1:3000/api/admin/microsoft/callback",
                    "expectedNonce": "nonce-curriculum",
                    "instanceId": "instance-curriculum",
                }
            )

        self.assertEqual(response["admin"], registered_session)
        fetch_staff_support_account_by_email.assert_called()
        refresh_staff_account_legacy_access.assert_called_once_with(curriculum_agent, persist=True)
        fetch_legacy_support_user_by_email.assert_not_called()
        saved_metadata = persist_agent_metadata.call_args.args[1]
        self.assertEqual(saved_metadata["entra_object_id"], "entra-object-curriculum")
        self.assertEqual(saved_metadata["entra_email"], "curriculum.agent@kentbusinesscollege.com")
        register_agent_session.assert_called_once_with("curriculum1", "instance-curriculum", "Off")

    def test_support_access_entra_login_refreshes_stale_local_account_before_permission_check(self):
        stale_agent = {
            "id": 694,
            "username": "test.test.kentbusinesscollege.com",
            "full_name": "test test",
            "email": "test.test@kentbusinesscollege.com",
            "role": "agent",
            "account_scope": "staff",
            "is_active": True,
            "metadata": {
                "legacy_support_access": True,
                "legacy_operations_access": True,
                "legacy_admin_access": False,
            },
        }
        refreshed_agent = {
            **stale_agent,
            "metadata": {
                "legacy_support_access": False,
                "legacy_operations_access": False,
                "legacy_admin_access": False,
                "team_access_keys": ["curriculum_team"],
            },
        }
        final_agent = {
            **refreshed_agent,
            "metadata": {
                **refreshed_agent["metadata"],
                "entra_object_id": "entra-object-test",
                "entra_email": "test.test@kentbusinesscollege.com",
            },
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services, "fetch_staff_support_account_by_email", return_value=stale_agent) as fetch_staff_support_account_by_email,
            patch.object(services, "refresh_staff_account_legacy_access", return_value=refreshed_agent) as refresh_staff_account_legacy_access,
            patch.object(services, "fetch_legacy_support_user_by_email") as fetch_legacy_support_user_by_email,
            patch.object(services, "persist_agent_metadata") as persist_agent_metadata,
            patch.object(services, "connection", mock_connection),
            patch.object(services, "fetch_agent_account_by_id", return_value=final_agent),
        ):
            agent = services._login_support_access_agent_from_entra(
                {
                    "id": "entra-object-test",
                    "displayName": "test test",
                    "mail": "test.test@kentbusinesscollege.com",
                },
                "test.test@kentbusinesscollege.com",
            )

        self.assertEqual(agent, final_agent)
        fetch_staff_support_account_by_email.assert_called_once_with("test.test@kentbusinesscollege.com")
        refresh_staff_account_legacy_access.assert_called_once_with(stale_agent, persist=True)
        fetch_legacy_support_user_by_email.assert_not_called()
        saved_metadata = persist_agent_metadata.call_args.args[1]
        self.assertFalse(saved_metadata["legacy_support_access"])
        self.assertFalse(saved_metadata["legacy_operations_access"])
        self.assertEqual(saved_metadata["team_access_keys"], ["curriculum_team"])
        self.assertEqual(saved_metadata["entra_object_id"], "entra-object-test")

    def test_admin_microsoft_login_syncs_operations_access_user_without_entra_admin_role(self):
        id_token = build_unverified_jwt(
            {
                "nonce": "nonce-ops",
                "preferred_username": "holom.mark@kentbusinesscollege.com",
            }
        )
        legacy_user = {
            "id": 19,
            "username": "holom.mark",
            "first_name": "Holom",
            "last_name": "Mark",
            "full_name": "Holom Mark",
            "email": "holom.mark@kentbusinesscollege.com",
            "password_hash": "",
            "is_staff": False,
            "is_superuser": False,
            "is_active": True,
            "has_support_access": False,
            "has_operations_access": True,
            "has_admin_access": False,
        }
        synced_agent = {
            "id": 19,
            "username": "holom.mark",
            "full_name": "Holom Mark",
            "email": "holom.mark@kentbusinesscollege.com",
            "role": "agent",
            "account_scope": "staff",
            "is_active": True,
            "metadata": {"legacy_operations_access": True},
        }
        refreshed_agent = {
            **synced_agent,
            "metadata": {
                "legacy_operations_access": True,
                "entra_object_id": "entra-object-ops",
                "entra_email": "holom.mark@kentbusinesscollege.com",
            },
        }
        registered_session = {
            "id": 19,
            "username": "holom.mark",
            "fullName": "Holom Mark",
            "email": "holom.mark@kentbusinesscollege.com",
            "role": "agent",
            "sessionActive": True,
            "consoleStatus": "Off",
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services.settings, "AZURE_LOGIN_TENANT_ID", "tenant-123"),
            patch.object(services.settings, "AZURE_LOGIN_CLIENT_ID", "client-123"),
            patch.object(services.settings, "AZURE_LOGIN_CLIENT_SECRET", "secret-123"),
            patch.object(
                services,
                "post_form_request",
                return_value=(True, True, 200, {"access_token": "access-token-ops", "id_token": id_token}),
            ),
            patch.object(
                services,
                "fetch_microsoft_graph_me",
                return_value=(
                    True,
                    True,
                    200,
                    {
                        "id": "entra-object-ops",
                        "mail": "holom.mark@kentbusinesscollege.com",
                        "userPrincipalName": "holom.mark@kentbusinesscollege.com",
                        "displayName": "Holom Mark",
                    },
                ),
            ),
            patch.object(services, "fetch_microsoft_graph_directory_roles", return_value=(True, True, 200, [])),
            patch.object(services, "fetch_legacy_support_user_by_email", return_value=legacy_user) as fetch_legacy_support_user_by_email,
            patch.object(services, "sync_support_staff_account_from_legacy_auth_user", return_value=synced_agent) as sync_support_staff_account_from_legacy_auth_user,
            patch.object(services, "persist_agent_metadata") as persist_agent_metadata,
            patch.object(services, "connection", mock_connection),
            patch.object(services, "fetch_agent_account_by_id", return_value=refreshed_agent),
            patch.object(services, "register_agent_session", return_value=registered_session) as register_agent_session,
        ):
            response = services.get_admin_microsoft_login_response(
                {
                    "code": "auth-code-ops",
                    "redirectUri": "http://127.0.0.1:3000/api/admin/microsoft/callback",
                    "expectedNonce": "nonce-ops",
                    "instanceId": "instance-ops",
                }
            )

        self.assertEqual(response["admin"], registered_session)
        fetch_legacy_support_user_by_email.assert_called_with("holom.mark@kentbusinesscollege.com")
        sync_support_staff_account_from_legacy_auth_user.assert_called_once_with(legacy_user)
        saved_metadata = persist_agent_metadata.call_args.args[1]
        self.assertEqual(saved_metadata["entra_object_id"], "entra-object-ops")
        self.assertTrue(saved_metadata["legacy_operations_access"])
        register_agent_session.assert_called_once_with("holom.mark", "instance-ops", "Off")

    def test_build_support_staff_role_from_legacy_auth_user_uses_django_superuser_for_superadmin(self):
        self.assertEqual(
            services.build_support_staff_role_from_legacy_auth_user(
                {"has_support_access": True, "has_admin_access": False, "is_superuser": False}
            ),
            "agent",
        )
        self.assertEqual(
            services.build_support_staff_role_from_legacy_auth_user(
                {"has_support_access": False, "has_operations_access": True, "has_admin_access": False, "is_superuser": False}
            ),
            "agent",
        )
        self.assertEqual(
            services.build_support_staff_role_from_legacy_auth_user(
                {"has_support_access": True, "has_admin_access": True, "is_superuser": False}
            ),
            "admin",
        )
        self.assertEqual(
            services.build_support_staff_role_from_legacy_auth_user(
                {"has_support_access": True, "has_admin_access": True, "is_superuser": True}
            ),
            "superadmin",
        )


class SupportDirectoryTests(SimpleTestCase):
    def test_update_agent_support_access_syncs_linked_kbc_auth_group(self):
        agent = {
            "id": 23,
            "username": "omar1",
            "full_name": "Omar One",
            "email": "omar1@kentbusinesscollege.com",
            "account_scope": "staff",
            "role": "agent",
            "is_active": True,
            "metadata": {
                "legacy_auth_user_id": 77,
                "legacy_support_access": True,
                "legacy_admin_access": True,
            },
        }

        with (
            patch.object(services, "run_query_one", return_value=agent),
            patch.object(services, "sync_legacy_support_access_group_membership") as sync_legacy_support_access_group_membership,
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "persist_agent_metadata") as persist_agent_metadata,
            patch.object(services, "sync_legacy_team_access_memberships") as sync_legacy_team_access_memberships,
            patch.object(services, "get_open_assigned_live_chat_agent_ids", return_value=set()),
        ):
            response = services.update_agent_support_access(23, support_access=False)

        sync_legacy_support_access_group_membership.assert_called_once_with(77, False)
        sync_legacy_team_access_memberships.assert_called_once_with(
            23,
            support_access=False,
            operations_access=None,
            strict=True,
        )
        saved_metadata = persist_agent_metadata.call_args.args[1]
        self.assertFalse(saved_metadata["legacy_support_access"])
        self.assertFalse(response["legacySupportAccess"])

    def test_update_agent_ticket_access_allows_admin_receiver_enable(self):
        admin_account = {
            "id": 29,
            "username": "admin.user",
            "full_name": "Admin User",
            "email": "admin.user@kentbusinesscollege.com",
            "account_scope": "staff",
            "role": "admin",
            "is_active": True,
            "metadata": {
                "legacy_auth_user_id": 79,
                "legacy_admin_access": True,
                "legacy_support_access": False,
            },
        }

        with (
            patch.object(services, "run_query_one", return_value=admin_account),
            patch.object(services, "sync_legacy_support_access_group_membership") as sync_legacy_support_access_group_membership,
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "persist_agent_metadata") as persist_agent_metadata,
            patch.object(services, "sync_legacy_team_access_memberships") as sync_legacy_team_access_memberships,
            patch.object(services, "get_open_assigned_live_chat_agent_ids", return_value=set()),
        ):
            response = services.update_agent_support_access(29, support_access=True)

        self.assertEqual(response["role"], "admin")
        self.assertTrue(response["legacySupportAccess"])
        sync_legacy_support_access_group_membership.assert_called_once_with(79, True)
        sync_legacy_team_access_memberships.assert_called_once_with(
            29,
            support_access=True,
            operations_access=None,
            strict=True,
        )
        saved_metadata = persist_agent_metadata.call_args.args[1]
        self.assertTrue(saved_metadata["legacy_support_access"])

    def test_update_agent_operations_access_syncs_linked_kbc_auth_group(self):
        agent = {
            "id": 24,
            "username": "learning.plan",
            "full_name": "Learning Plan",
            "email": "learning.plan@kentbusinesscollege.com",
            "account_scope": "staff",
            "role": "agent",
            "is_active": True,
            "metadata": {
                "legacy_auth_user_id": 78,
                "legacy_support_access": False,
                "legacy_operations_access": False,
                "legacy_admin_access": False,
            },
        }

        with (
            patch.object(services, "run_query_one", return_value=agent),
            patch.object(services, "sync_legacy_operations_access_group_membership") as sync_legacy_operations_access_group_membership,
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "persist_agent_metadata") as persist_agent_metadata,
            patch.object(services, "sync_legacy_team_access_memberships") as sync_legacy_team_access_memberships,
            patch.object(services, "get_open_assigned_live_chat_agent_ids", return_value=set()),
        ):
            response = services.update_agent_operations_access(24, operations_access=True)

        sync_legacy_operations_access_group_membership.assert_called_once_with(78, True)
        sync_legacy_team_access_memberships.assert_called_once_with(
            24,
            support_access=None,
            operations_access=True,
            strict=True,
        )
        saved_metadata = persist_agent_metadata.call_args.args[1]
        self.assertTrue(saved_metadata["legacy_operations_access"])
        self.assertTrue(response["legacyOperationsAccess"])
        self.assertFalse(response["legacySupportAccess"])

    def test_remove_agent_turns_off_support_access(self):
        agent = {
            "id": 31,
            "email": "omar.badr@kentbusinesscollege.com",
            "metadata": {
                "legacy_support_access": True,
                "session_active": True,
                "console_status": "Available",
            },
        }

        with (
            patch.object(services, "run_query_one", return_value=agent),
            patch.object(services, "run_query") as run_query,
            patch.object(services, "_remove_django_support_access") as remove_django_support_access,
        ):
            services.remove_agent(31)

        update_sql = run_query.call_args.args[0]
        update_params = run_query.call_args.args[1]
        self.assertIn("UPDATE support_accounts", update_sql)
        self.assertNotIn("DELETE FROM support_accounts", update_sql)
        saved_metadata = json.loads(update_params[0])
        self.assertNotIn("manually_added_agent", saved_metadata)
        self.assertFalse(saved_metadata["legacy_support_access"])
        self.assertFalse(saved_metadata["session_active"])
        self.assertEqual(saved_metadata["console_status"], "Off")
        remove_django_support_access.assert_called_once_with("omar.badr@kentbusinesscollege.com")

    def test_list_agents_returns_only_current_support_access_staff_profiles(self):
        legacy_user = {
            "id": 77,
            "username": "omar1",
            "first_name": "Omar",
            "last_name": "One",
            "full_name": "Omar One",
            "email": "omar1@kentbusinesscollege.com",
            "password_hash": "",
            "is_staff": False,
            "is_superuser": False,
            "is_active": True,
            "has_support_access": True,
            "has_operations_access": False,
            "has_admin_access": False,
        }
        with (
            patch.object(
                services,
                "run_query",
                return_value=[
                    {
                        "id": 23,
                        "username": "omar1",
                        "full_name": "Omar One",
                        "email": "omar1@kentbusinesscollege.com",
                        "account_scope": "staff",
                        "role": "admin",
                        "is_active": True,
                        "metadata": {
                            "legacy_auth_user_id": 77,
                            "legacy_support_access": True,
                            "legacy_admin_access": False,
                        },
                    },
                ],
            ),
            patch.object(
                services,
                "fetch_legacy_support_users_for_accounts",
                return_value={"id": {77: legacy_user}, "email": {}, "username": {}},
            ),
            patch.object(services, "persist_agent_metadata") as persist_agent_metadata,
            patch.object(services, "get_open_assigned_live_chat_agent_ids", return_value=set()),
        ):
            response = services.list_agents()

        returned_ids = {account["id"] for account in response["accounts"]}
        self.assertEqual(returned_ids, {23})
        persist_agent_metadata.assert_not_called()

    def test_list_agents_refreshes_removed_communication_centre_access(self):
        stale_agent = {
            "id": 421,
            "username": "ahmedhamamo095@gmail.com",
            "full_name": "ahmedhamamo095@gmail.com",
            "email": "AHMEDHAMAMO095@gmail.com",
            "account_scope": "staff",
            "role": "agent",
            "is_active": True,
            "metadata": {
                "legacy_auth_user_id": 421,
                "legacy_support_access": True,
                "legacy_operations_access": False,
                "legacy_admin_access": False,
                "session_active": True,
                "console_status": "Available",
            },
        }

        with (
            patch.object(services, "run_query", return_value=[stale_agent]),
            patch.object(
                services,
                "fetch_legacy_support_users_for_accounts",
                return_value={"id": {}, "email": {}, "username": {}},
            ),
            patch.object(services, "persist_agent_metadata") as persist_agent_metadata,
            patch.object(services, "get_open_assigned_live_chat_agent_ids", return_value=set()),
        ):
            response = services.list_agents()

        refreshed_agent = response["accounts"][0]
        self.assertFalse(refreshed_agent["legacySupportAccess"])
        self.assertFalse(refreshed_agent["legacyOperationsAccess"])
        self.assertEqual(refreshed_agent["consoleStatus"], "Off")
        persist_agent_metadata.assert_not_called()

    def test_serialize_agent_falls_back_to_legacy_auth_email_for_support_profiles(self):
        serialized = services.serialize_agent(
            {
                "id": 77,
                "username": "rewan.yasser.staff",
                "full_name": "Rewan Yasser",
                "email": None,
                "account_scope": "staff",
                "role": "superadmin",
                "is_active": True,
                "metadata": {
                    "legacy_auth_email": "rewan.yasser@kentbusinesscollege.com",
                    "legacy_support_access": False,
                    "legacy_admin_access": True,
                    "console_status": "Off",
                    "session_active": False,
                },
            },
            open_assigned_chat_agent_ids=set(),
        )

        self.assertEqual(serialized["email"], "rewan.yasser@kentbusinesscollege.com")


class SupportStaffSyncTests(SimpleTestCase):
    def test_sync_support_staff_account_preserves_existing_console_session_metadata(self):
        legacy_user = {
            "id": 368,
            "username": "Rewan.yasser",
            "first_name": "Rewan",
            "last_name": "Yasser",
            "full_name": "Rewan Yasser",
            "email": "rewan.yasser@kentbusinesscollege.com",
            "is_staff": True,
            "is_superuser": False,
            "is_active": True,
            "has_support_access": True,
            "has_admin_access": True,
            "team_access_keys": ["curriculum"],
        }
        existing_account = {
            "id": 601,
            "username": "rewan.yasser",
            "full_name": "Rewan Yasser",
            "email": "rewan.yasser@kentbusinesscollege.com",
            "account_scope": "staff",
            "role": "admin",
            "is_active": True,
            "metadata": {
                "legacy_auth_user_id": 368,
                "session_active": True,
                "session_instance_id": "instance-123",
                "session_last_seen_at": "2026-05-31T10:00:00+00:00",
                "console_status": "Available",
            },
        }
        refreshed_account = {**existing_account, "metadata": existing_account["metadata"]}
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "fetch_staff_support_account_by_legacy_auth_user_id", return_value=existing_account),
            patch.object(services, "find_agent_account_by_email", return_value=None),
            patch.object(services, "resolve_unique_support_staff_username", return_value="rewan.yasser"),
            patch.object(services, "fetch_agent_account_by_id", return_value=refreshed_account),
            patch.object(services, "sync_account_team_access_from_legacy_user") as sync_account_team_access_from_legacy_user,
        ):
            response = services.sync_support_staff_account_from_legacy_auth_user(legacy_user)

        self.assertEqual(response, refreshed_account)
        sync_account_team_access_from_legacy_user.assert_called_once_with(601, legacy_user)
        update_params = cursor.execute.call_args.args[1]
        updated_metadata = json.loads(update_params[5])
        self.assertTrue(updated_metadata["session_active"])
        self.assertEqual(updated_metadata["session_instance_id"], "instance-123")
        self.assertEqual(updated_metadata["console_status"], "Available")
        self.assertTrue(updated_metadata["legacy_support_access"])
        self.assertTrue(updated_metadata["legacy_admin_access"])
        self.assertEqual(updated_metadata["team_access_keys"], ["curriculum"])

    def test_add_entra_agent_to_custom_team_does_not_grant_support_access(self):
        team = {
            "id": 8,
            "key": "curriculum_team",
            "name": "Curriculum Team",
            "description": "",
            "receiver_access_metadata_key": "team_access:curriculum_team",
            "receiver_error_ticket_label": "Curriculum Team",
            "is_active": True,
            "metadata": {"auth_group_name": "Curriculum Team Access"},
        }
        new_account = {
            "id": 77,
            "username": "curriculum.user",
            "full_name": "Curriculum User",
            "email": "curriculum.user@kentbusinesscollege.com",
            "account_scope": "staff",
            "role": "agent",
            "is_active": True,
            "metadata": {},
        }
        serialized_agent = {
            "id": 77,
            "username": "curriculum.user",
            "fullName": "Curriculum User",
            "legacySupportAccess": False,
            "teamAccessKeys": ["curriculum_team"],
        }

        with (
            patch.object(services, "fetch_support_team_by_key", return_value=team),
            patch.object(services, "_ensure_django_support_access", return_value=424) as ensure_django_support_access,
            patch.object(services, "run_query_one", side_effect=[None, None, new_account]) as run_query_one,
            patch.object(services, "update_agent_team_access", return_value=serialized_agent) as update_agent_team_access,
        ):
            response = services.add_entra_agent(
                {
                    "entraId": "entra-user-77",
                    "displayName": "Curriculum User",
                    "email": "curriculum.user@kentbusinesscollege.com",
                    "username": "curriculum.user",
                    "teamKey": "curriculum_team",
                }
            )

        self.assertEqual(response["agent"], serialized_agent)
        ensure_django_support_access.assert_called_once_with(
            "curriculum.user@kentbusinesscollege.com",
            "Curriculum User",
            add_support_access=False,
        )
        insert_params = run_query_one.call_args_list[2].args[1]
        inserted_metadata = json.loads(insert_params[5])
        self.assertFalse(inserted_metadata["legacy_support_access"])
        self.assertEqual(inserted_metadata["legacy_auth_user_id"], 424)
        update_agent_team_access.assert_called_once_with(77, team_key="curriculum_team", receive_tickets=True)

    def test_search_entra_agents_marks_existing_staff_account_without_support_access(self):
        graph_payload = {
            "value": [
                {
                    "id": "entra-user-77",
                    "displayName": "Curriculum User",
                    "mail": "curriculum.user@kentbusinesscollege.com",
                    "userPrincipalName": "curriculum.user@kentbusinesscollege.com",
                    "accountEnabled": True,
                }
            ]
        }
        existing_staff_account = {
            "id": 77,
            "username": "curriculum.user",
            "email": "curriculum.user@kentbusinesscollege.com",
            "is_active": True,
            "metadata": {
                "entra_object_id": "entra-user-77",
                "legacy_support_access": False,
                "team_access_keys": ["curriculum_team"],
            },
        }

        with (
            patch.object(services, "is_microsoft_admin_login_configured", return_value=True),
            patch.object(
                services,
                "request_microsoft_login_graph_access_token",
                return_value=(True, True, 200, {"access_token": "graph-token"}),
            ),
            patch.object(services, "get_json_request", return_value=(True, True, 200, graph_payload)),
            patch.object(services, "run_query", return_value=[existing_staff_account]),
        ):
            response = services.search_entra_agents("curr")

        self.assertEqual(len(response["results"]), 1)
        self.assertTrue(response["results"][0]["alreadyAdded"])
        self.assertEqual(response["results"][0]["existingAccountId"], 77)

    def test_sync_account_team_access_from_legacy_user_disables_stale_builtin_access(self):
        legacy_user = {
            "id": 424,
            "has_support_access": False,
            "has_operations_access": False,
            "team_access_keys": ["curriculum_team"],
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services, "get_custom_support_team_auth_group_lookup", return_value={"curriculum team access": "curriculum_team"}),
            patch.object(services, "persist_account_team_access") as persist_account_team_access,
            patch.object(services, "connection", mock_connection),
        ):
            services.sync_account_team_access_from_legacy_user(694, legacy_user)

        persist_account_team_access.assert_called_once_with(
            694,
            "curriculum_team",
            True,
            source="legacy_auth_group_sync",
        )
        update_params = cursor.execute.call_args.args[1]
        self.assertEqual(update_params[1], 694)
        self.assertEqual(update_params[2], ["operations", "support"])

    def test_refresh_staff_account_legacy_access_clears_team_rows_when_legacy_user_loses_access(self):
        account = {
            "id": 694,
            "username": "test.test.kentbusinesscollege.com",
            "full_name": "test test",
            "email": "test.test@kentbusinesscollege.com",
            "account_scope": "staff",
            "role": "agent",
            "is_active": True,
            "metadata": {
                "legacy_auth_user_id": 424,
                "legacy_support_access": True,
                "legacy_operations_access": True,
                "legacy_admin_access": False,
                "team_access_keys": ["curriculum_team"],
            },
        }

        with (
            patch.object(services, "get_support_auth_database_url", return_value="postgres://auth-db"),
            patch.object(services, "fetch_legacy_support_user_by_id", return_value=None),
            patch.object(services, "fetch_legacy_support_user_by_email", return_value=None),
            patch.object(services, "fetch_legacy_support_user_by_username", return_value=None),
            patch.object(services, "sync_account_team_access_from_legacy_user") as sync_account_team_access_from_legacy_user,
            patch.object(services, "persist_agent_metadata") as persist_agent_metadata,
        ):
            refreshed = services.refresh_staff_account_legacy_access(account, persist=True)

        sync_account_team_access_from_legacy_user.assert_called_once_with(694, {})
        saved_metadata = persist_agent_metadata.call_args.args[1]
        self.assertFalse(saved_metadata["legacy_support_access"])
        self.assertFalse(saved_metadata["legacy_operations_access"])
        self.assertFalse(saved_metadata["legacy_admin_access"])
        self.assertEqual(saved_metadata["team_access_keys"], [])
        self.assertFalse(services.normalize_json_object(refreshed["metadata"])["session_active"])

    def test_sync_entra_support_staff_account_preserves_existing_console_session_metadata(self):
        profile = {
            "id": "entra-object-123",
            "displayName": "Omar One",
            "mail": "omar1@kentbusinesscollege.com",
            "userPrincipalName": "omar1@kentbusinesscollege.com",
        }
        directory_roles = [{"id": "role-1", "displayName": "User Administrator", "roleTemplateId": "template-1"}]
        existing_account = {
            "id": 602,
            "username": "omar1",
            "full_name": "Omar One",
            "email": "omar1@kentbusinesscollege.com",
            "account_scope": "staff",
            "role": "admin",
            "is_active": True,
            "metadata": {
                "entra_object_id": "entra-object-123",
                "session_active": True,
                "session_instance_id": "instance-456",
                "session_last_seen_at": "2026-05-31T10:00:00+00:00",
                "console_status": "Available",
            },
        }
        refreshed_account = {**existing_account, "metadata": existing_account["metadata"]}
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "fetch_staff_support_account_by_entra_object_id", return_value=existing_account),
            patch.object(services, "find_agent_account_by_email", return_value=None),
            patch.object(services, "fetch_agent_account_by_id", return_value=refreshed_account),
        ):
            response = services.sync_support_staff_account_from_entra_directory_user(profile, directory_roles, "admin")

        self.assertEqual(response, refreshed_account)
        update_params = cursor.execute.call_args.args[1]
        updated_metadata = json.loads(update_params[5])
        self.assertTrue(updated_metadata["session_active"])
        self.assertEqual(updated_metadata["session_instance_id"], "instance-456")
        self.assertEqual(updated_metadata["console_status"], "Available")
        self.assertTrue(updated_metadata["entra_directory_admin_access"])

    def test_sync_support_staff_account_creates_runtime_profile_without_colliding_requester_email(self):
        legacy_user = {
            "id": 368,
            "username": "Rewan.yasser",
            "first_name": "Rewan",
            "last_name": "Yasser",
            "full_name": "Rewan Yasser",
            "email": "rewan.yasser@kentbusinesscollege.com",
            "is_staff": True,
            "is_superuser": True,
            "is_active": True,
            "has_support_access": False,
            "has_admin_access": True,
        }
        cursor = MagicMock()
        cursor.fetchone.return_value = (601,)
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context
        created_account = {
            "id": 601,
            "username": "rewan.yasser.staff",
            "full_name": "Rewan Yasser",
            "email": None,
            "account_scope": "staff",
            "role": "superadmin",
            "is_active": True,
            "metadata": {
                "legacy_auth_user_id": 368,
                "legacy_auth_email": "rewan.yasser@kentbusinesscollege.com",
                "legacy_admin_access": True,
            },
        }

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "fetch_staff_support_account_by_legacy_auth_user_id", return_value=None),
            patch.object(services, "fetch_staff_support_account_by_email", return_value=None),
            patch.object(services, "fetch_staff_admin_account_by_email", return_value=None),
            patch.object(services, "find_agent_account_by_email", return_value={"id": 380, "email": "rewan.yasser@kentbusinesscollege.com"}),
            patch.object(services, "resolve_unique_support_staff_username", return_value="rewan.yasser.staff"),
            patch.object(services, "fetch_agent_account_by_id", return_value=created_account),
            patch.object(services, "sync_account_team_access_from_legacy_user"),
        ):
            response = services.sync_support_staff_account_from_legacy_auth_user(legacy_user)

        self.assertEqual(response, created_account)
        insert_params = cursor.execute.call_args.args[1]
        self.assertIsNone(insert_params[2])
        inserted_metadata = json.loads(insert_params[5])
        self.assertEqual(inserted_metadata["legacy_auth_email"], "rewan.yasser@kentbusinesscollege.com")
        self.assertEqual(inserted_metadata["legacy_auth_user_id"], 368)


class SlaSyncCommandTests(SimpleTestCase):
    def test_sync_ticket_sla_statuses_command_reports_summary(self):
        output = StringIO()

        with patch(
            "support_portal.management.commands.sync_ticket_sla_statuses.sync_auto_managed_ticket_sla_statuses",
            return_value={"scanned": 7, "updated": 3, "breached": 2, "attentionRequired": 2},
        ) as sync_auto_managed_ticket_sla_statuses:
            call_command("sync_ticket_sla_statuses", stdout=output)

        self.assertIn("SLA sync completed. Scanned 7 ticket(s), updated 3, breached 2, attention required 2.", output.getvalue())
        sync_auto_managed_ticket_sla_statuses.assert_called_once_with()

    def test_sync_coverage_sla_alerts_command_reports_summary(self):
        output = StringIO()

        with patch(
            "support_portal.management.commands.sync_coverage_sla_alerts.sync_coverage_ticket_sla_alerts",
            return_value={"scanned": 4, "updated": 2, "warnings": 1, "escalations": 1, "breached": 2, "attentionRequired": 2},
        ) as sync_coverage_ticket_sla_alerts:
            call_command("sync_coverage_sla_alerts", stdout=output)

        self.assertIn(
            "Coverage SLA sync completed. Scanned 4 ticket(s), updated 2, warnings 1, escalations 1, breached 2, attention required 2.",
            output.getvalue(),
        )
        sync_coverage_ticket_sla_alerts.assert_called_once_with()


class SyncLearnersToSupportAccountsCommandTests(SimpleTestCase):
    def test_sync_learners_to_support_accounts_creates_missing_requesters(self):
        output = StringIO()
        cursor = MagicMock()
        cursor.fetchall.side_effect = [
            [
                (1, "Alice Learner", "alice@example.com", "legacy_kbc_users_data", '{"legacy_source":"kbc_users_data"}'),
                (2, "Existing Learner", "existing@example.com", "manual", "{}"),
            ],
            [
                ("alice", "someone-else@example.com"),
                ("existing-user", "existing@example.com"),
            ],
        ]
        cursor.rowcount = 1
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch("support_portal.management.commands.sync_learners_to_support_accounts.connection", mock_connection),
            patch("support_portal.management.commands.sync_learners_to_support_accounts.transaction.atomic", return_value=nullcontext()),
        ):
            call_command("sync_learners_to_support_accounts", stdout=output)

        insert_calls = [
            call
            for call in cursor.execute.call_args_list
            if "INSERT INTO support_accounts" in call.args[0]
        ]

        self.assertEqual(len(insert_calls), 1)
        insert_params = insert_calls[0].args[1]
        self.assertEqual(insert_params[0], "alice-2")
        self.assertEqual(insert_params[1], "Alice Learner")
        self.assertEqual(insert_params[2], "alice@example.com")
        self.assertEqual(insert_params[3], "requester")
        self.assertEqual(insert_params[4], "user")
        inserted_metadata = json.loads(insert_params[6])
        self.assertTrue(inserted_metadata["synced_from_learners"])
        self.assertEqual(inserted_metadata["provisioned_by"], "sync_learners_to_support_accounts")
        self.assertEqual(inserted_metadata["console_status"], "Off")
        self.assertIn(
            "Synced 1 learner account(s) into support_accounts. Linked 1 learner profile(s). Skipped 1 existing email(s) and 0 invalid email(s).",
            output.getvalue(),
        )


class ChatInactivitySyncCommandTests(SimpleTestCase):
    def test_sync_chat_inactivity_command_reports_counts(self):
        output = StringIO()

        with patch(
            "support_portal.management.commands.sync_chat_inactivity.sync_open_ticket_inactivity",
            return_value={"scanned": 3, "reminded": 1, "closed": 2},
        ) as sync_open_ticket_inactivity:
            call_command("sync_chat_inactivity", stdout=output)

        self.assertIn(
            "Chat inactivity sync completed. Scanned 3 open ticket(s), sent 1 reminder(s), closed 2 chat(s).",
            output.getvalue(),
        )
        sync_open_ticket_inactivity.assert_called_once_with(public_id=None)


class AdminTicketListPrefilterTests(SimpleTestCase):
    def test_fetch_admin_ticket_rows_prefilters_dynamic_team_in_sql(self):
        team = {
            "id": 7,
            "key": "curriculum_team",
            "name": "Curriculum Team",
            "metadata": {},
        }

        with (
            patch.object(services, "fetch_support_team_by_key", return_value=team),
            patch.object(services, "run_query", return_value=[]) as run_query,
        ):
            services.fetch_admin_ticket_rows({
                "team": "curriculum_team",
                "archiveScope": "active",
                "status": "Pending",
            })

        sql = run_query.call_args.args[0]
        params = run_query.call_args.args[1]
        self.assertIn("t.is_archived = FALSE", sql)
        self.assertIn("t.status = %s", sql)
        self.assertIn("NULLIF(LOWER(TRIM(COALESCE(t.queue_scope, ''))), '')", sql)
        self.assertIn("Pending", params)
        self.assertIn("curriculum_team", params)

    def test_fetch_admin_ticket_rows_prefilters_legacy_team_in_sql(self):
        with (
            patch.object(services, "fetch_support_team_by_key") as fetch_support_team_by_key,
            patch.object(services, "run_query", return_value=[]) as run_query,
        ):
            services.fetch_admin_ticket_rows({
                "team": "support",
                "archiveScope": "active",
            })

        fetch_support_team_by_key.assert_not_called()
        sql = run_query.call_args.args[0]
        params = run_query.call_args.args[1]
        self.assertIn("t.is_archived = FALSE", sql)
        self.assertIn("NULLIF(LOWER(TRIM(COALESCE(t.queue_scope, ''))), '')", sql)
        self.assertIn(services.TICKET_RECEIVER_SCOPE_SUPPORT, params)

    def test_fetch_admin_ticket_rows_prefilters_dashboard_and_sla_in_sql(self):
        with patch.object(services, "run_query", return_value=[]) as run_query:
            services.fetch_admin_ticket_rows({
                "archiveScope": "active",
                "dashboardFilter": "coverage",
                "slaStatus": "Breached",
            })

        sql = run_query.call_args.args[0]
        params = run_query.call_args.args[1]
        self.assertIn("t.is_archived = FALSE", sql)
        self.assertIn("t.sla_status = %s", sql)
        self.assertIn("LOWER(TRIM(COALESCE(t.technical_subcategory, ''))) = 'coverage'", sql)
        self.assertIn("Breached", params)

    def test_fetch_admin_ticket_rows_prefilters_quick_resolution_in_sql(self):
        with patch.object(services, "run_query", return_value=[]) as run_query:
            services.fetch_admin_ticket_rows({"dashboardFilter": "quickResolution"})

        sql = run_query.call_args.args[0]
        params = run_query.call_args.args[1]
        self.assertIn("t.status_reason = ANY(%s::text[])", sql)
        self.assertIn("NOT (", sql)
        self.assertIn("LOWER(TRIM(COALESCE(t.technical_subcategory, ''))) = 'coverage'", sql)
        self.assertIn(services.STATUS_REASON_QUICK_TICKET, params[0])

    def test_team_filter_uses_final_routing_policy_for_coverage_tickets(self):
        ticket = {
            "technical_subcategory": "Coverage",
            "assigned_team": "Curriculum Team",
            "metadata": {},
        }

        self.assertFalse(services.admin_ticket_matches_team_filter(ticket, "curriculum_team"))
        self.assertFalse(services.admin_ticket_matches_team_filter(ticket, "Curriculum Team"))
        self.assertTrue(services.admin_ticket_matches_team_filter(ticket, services.TICKET_RECEIVER_SCOPE_OPERATIONS))
        self.assertTrue(services.admin_ticket_matches_team_filter(ticket, services.ASSIGNED_TEAM_LEARNING_PLAN))

    def test_list_admin_tickets_passes_normalized_params_as_prefilter(self):
        actor = {"id": 4, "role": services.ROLE_SUPERADMIN}
        pagination = {
            "page": 1,
            "pageSize": 25,
            "total": 0,
            "totalPages": 0,
            "hasNext": False,
            "hasPrevious": False,
            "isPaginated": True,
        }

        with (
            patch.object(services, "trigger_ticket_background_sync"),
            patch.object(services, "fetch_admin_ticket_page_for_actor", return_value=([], pagination)) as fetch_page,
        ):
            response = services.list_admin_tickets(
                actor,
                query_params={
                    "team": "curriculum_team",
                    "archiveScope": "active",
                    "status": "Pending",
                    "page": "1",
                    "pageSize": "25",
                },
            )

        self.assertEqual(response["pagination"]["total"], 0)
        self.assertEqual(fetch_page.call_args.args[0], actor)
        list_params = fetch_page.call_args.args[1]
        self.assertEqual(list_params["team"], "curriculum_team")
        self.assertEqual(list_params["archiveScope"], "active")
        self.assertEqual(list_params["status"], "Pending")
        self.assertEqual(list_params["pageSize"], 25)

    def test_fetch_admin_ticket_page_uses_sql_count_limit_and_offset(self):
        actor = {"id": 4, "role": services.ROLE_SUPERADMIN}
        params = services.normalize_admin_ticket_list_params({
            "page": "2",
            "pageSize": "25",
            "archiveScope": "active",
            "sort": "newest",
        })

        with (
            patch.object(services, "run_query_one", return_value={"total": 51}) as run_query_one,
            patch.object(services, "run_query", return_value=[]) as run_query,
        ):
            _rows, pagination = services.fetch_admin_ticket_page_for_actor(actor, params)

        count_sql = run_query_one.call_args.args[0]
        page_sql = run_query.call_args.args[0]
        page_params = run_query.call_args.args[1]
        self.assertIn("COUNT(*) AS total", count_sql)
        self.assertIn("LIMIT %s OFFSET %s", page_sql)
        self.assertEqual(page_params[-2:], [25, 25])
        self.assertEqual(pagination["total"], 51)
        self.assertEqual(pagination["page"], 2)

    def test_list_admin_tickets_does_not_trigger_background_sync_by_default(self):
        with (
            patch.object(services, "trigger_ticket_background_sync") as trigger_ticket_background_sync,
            patch.object(services, "get_admin_ticket_rows_for_actor", return_value=[]),
        ):
            services.list_admin_tickets()

        trigger_ticket_background_sync.assert_not_called()

    def test_list_admin_tickets_can_trigger_background_sync_when_requested(self):
        with (
            patch.object(services, "trigger_ticket_background_sync") as trigger_ticket_background_sync,
            patch.object(services, "get_admin_ticket_rows_for_actor", return_value=[]),
        ):
            services.list_admin_tickets(run_background_sync=True)

        trigger_ticket_background_sync.assert_called_once_with()

    def test_admin_ticket_metrics_does_not_trigger_background_sync_by_default(self):
        with (
            patch.object(services, "trigger_ticket_background_sync") as trigger_ticket_background_sync,
            patch.object(services, "get_admin_ticket_metrics_from_sql", return_value={"total": 0, "sections": {"coverage": 0, "learningPlanOther": 0}}),
        ):
            services.get_admin_ticket_metrics()

        trigger_ticket_background_sync.assert_not_called()


class AdminTicketUpdateTests(SimpleTestCase):
    def test_update_admin_ticket_requires_note_when_status_changes(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "status": "Open",
            "status_reason": "",
            "assigned_agent_id": None,
            "assigned_team": "Unassigned",
            "sla_status": "Pending Review",
            "metadata": {},
            "created_at": datetime.now(timezone.utc),
            "closed_at": None,
            "conversation_id": None,
            "assigned_agent_username": None,
            "assigned_agent_name": None,
        }

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "require_actor_can_access_admin_ticket"),
        ):
            with self.assertRaises(services.ApiError) as error_context:
                services.update_admin_ticket("KBC-000017", {"status": "Closed", "note": ""})

        self.assertEqual(error_context.exception.status_code, 400)
        self.assertEqual(error_context.exception.message, "Add an internal note before changing the ticket status.")

    def test_update_admin_ticket_rejects_closing_chat_while_ticket_stays_open(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "status": "Open",
            "status_reason": "",
            "assigned_agent_id": None,
            "assigned_team": "Support Desk",
            "sla_status": "Pending Review",
            "metadata": {},
            "created_at": datetime.now(timezone.utc),
            "closed_at": None,
            "conversation_id": 44,
            "conversation_metadata": {},
            "assigned_agent_username": None,
            "assigned_agent_name": None,
            "inquiry": "Help needed",
        }

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "require_actor_can_access_admin_ticket"),
            patch.object(services, "resolve_next_sla_state", return_value=("On Track", False, None)),
        ):
            with self.assertRaises(services.ApiError) as error_context:
                services.update_admin_ticket("KBC-000017", {"chatState": "closed"})

        self.assertEqual(error_context.exception.status_code, 409)
        self.assertEqual(
            error_context.exception.message,
            "An open ticket must stay attached to an open chat. Change the ticket status before closing this chat.",
        )

    def test_update_admin_ticket_defaults_closed_reason_to_closed_via_agent(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "status": "Open",
            "status_reason": "",
            "assigned_agent_id": None,
            "assigned_team": "Unassigned",
            "sla_status": "Pending Review",
            "metadata": {},
            "created_at": datetime.now(timezone.utc),
            "closed_at": None,
            "conversation_id": None,
            "conversation_metadata": {},
            "assigned_agent_username": None,
            "assigned_agent_name": None,
            "inquiry": "Help needed",
        }
        detail = {
            "ticket": {
                "id": "KBC-000017",
                "status": "Closed",
                "statusReason": "Closed via Agent",
                "slaStatus": "On Track",
            }
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "require_actor_can_access_admin_ticket"),
            patch.object(services, "resolve_next_sla_state", return_value=("On Track", False, None)),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event") as insert_history_event,
            patch.object(services, "fetch_admin_ticket_detail", return_value=detail),
        ):
            response = services.update_admin_ticket("KBC-000017", {"status": "Closed", "note": "Resolved by admin"})

        self.assertEqual(response, detail)
        update_params = cursor.execute.call_args_list[0].args[1]
        self.assertEqual(update_params[1], "Closed via Agent")
        insert_history_event.assert_any_call(17, "status_changed", None, {"from": "Open", "to": "Closed"})
        insert_history_event.assert_any_call(
            17,
            "status_reason_changed",
            None,
            {"from": "", "to": "Closed via Agent"},
        )

    def test_update_admin_ticket_defaults_pending_reason_to_awaiting_resolution(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "status": "Open",
            "status_reason": "",
            "assigned_agent_id": None,
            "assigned_team": "Unassigned",
            "sla_status": "Pending Review",
            "metadata": {},
            "created_at": datetime.now(timezone.utc),
            "closed_at": None,
            "conversation_id": None,
            "conversation_metadata": {},
            "assigned_agent_username": None,
            "assigned_agent_name": None,
            "inquiry": "Help needed",
        }
        detail = {
            "ticket": {
                "id": "KBC-000017",
                "status": "Pending",
                "statusReason": "Awaiting resolution",
                "slaStatus": "On Track",
            }
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "require_actor_can_access_admin_ticket"),
            patch.object(services, "resolve_next_sla_state", return_value=("On Track", False, None)),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event") as insert_history_event,
            patch.object(services, "fetch_admin_ticket_detail", return_value=detail),
        ):
            response = services.update_admin_ticket("KBC-000017", {"status": "Pending", "note": "Waiting on resolution"})

        self.assertEqual(response, detail)
        update_params = cursor.execute.call_args_list[0].args[1]
        self.assertEqual(update_params[1], "Awaiting resolution")
        insert_history_event.assert_any_call(17, "status_changed", None, {"from": "Open", "to": "Pending"})
        insert_history_event.assert_any_call(
            17,
            "status_reason_changed",
            None,
            {"from": "", "to": "Awaiting resolution"},
        )

    def test_update_admin_ticket_requires_assigned_admin_for_escalation(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "status": "Open",
            "status_reason": "",
            "assigned_agent_id": 5,
            "assigned_team": "Support Desk",
            "sla_status": "Pending Review",
            "metadata": {},
            "created_at": datetime.now(timezone.utc),
            "closed_at": None,
            "conversation_id": None,
            "conversation_metadata": {},
            "assigned_agent_username": "omar",
            "assigned_agent_name": "Omar",
            "inquiry": "Help needed",
        }

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "require_actor_can_access_admin_ticket"),
        ):
            with self.assertRaises(services.ApiError) as error_context:
                services.update_admin_ticket(
                    "KBC-000017",
                    {"status": "Pending", "statusReason": "Escalation", "note": "Escalating case"},
                )

        self.assertEqual(error_context.exception.status_code, 400)
        self.assertEqual(error_context.exception.message, "Select an admin to escalate this ticket.")

    def test_update_admin_ticket_escalation_notifies_selected_admin_without_reassigning_ticket(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "status": "Open",
            "status_reason": "",
            "assigned_agent_id": 5,
            "assigned_team": "Support Desk",
            "sla_status": "Pending Review",
            "metadata": {},
            "created_at": datetime.now(timezone.utc),
            "closed_at": None,
            "conversation_id": 44,
            "conversation_metadata": {},
            "assigned_agent_username": "omar",
            "assigned_agent_name": "Omar",
            "inquiry": "Help needed",
        }
        escalation_target = {
            "id": 9,
            "username": "ahmedhamamo",
            "full_name": "Ahmed Hamamo",
            "email": None,
            "role": "admin",
        }
        actor_row = {
            "id": 5,
            "username": "omar",
            "full_name": "Omar",
            "role": "admin",
        }
        detail = {
            "ticket": {
                "id": "KBC-000017",
                "status": "Pending",
                "statusReason": "Escalation",
                "assignedAgentId": 5,
                "pendingEscalationNotification": {
                    "fromAgentId": 5,
                    "fromAgentName": "Omar",
                    "fromAgentUsername": "omar",
                    "toAgentId": 9,
                    "toAgentName": "Ahmed Hamamo",
                    "toAgentUsername": "ahmedhamamo",
                    "note": "Please review this chat urgently",
                    "ticketId": "KBC-000017",
                    "requestedAt": "2026-05-13T00:00:00+00:00",
                },
            }
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", side_effect=[ticket, escalation_target]),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services, "resolve_next_sla_state", return_value=("On Track", False, None)),
            patch.object(services, "build_public_chat_id", return_value="CHAT-000144"),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event") as insert_history_event,
            patch.object(services, "fetch_admin_ticket_detail", return_value=detail),
        ):
            response = services.update_admin_ticket(
                "KBC-000017",
                {
                    "status": "Pending",
                    "statusReason": "Escalation",
                    "chatState": "open",
                    "escalationAgentId": 9,
                    "escalationNote": "Please review this chat urgently",
                    "documentation": {
                        "inquiry": "Help needed",
                        "chatId": "CHAT-000144",
                        "ticketId": "KBC-000017",
                        "ticketStatus": "Pending",
                        "statusReason": "Escalation",
                        "escalationAgentId": 9,
                        "escalationAgentName": "Ahmed Hamamo",
                        "escalationNote": "Please review this chat urgently",
                    },
                    "note": "Workflow saved.",
                    "actorUsername": "omar",
                },
            )

        self.assertEqual(response, detail)
        update_params = cursor.execute.call_args_list[0].args[1]
        self.assertEqual(update_params[2], 5)
        updated_metadata = json.loads(update_params[5])
        self.assertEqual(updated_metadata["pending_escalation_notification"]["toAgentId"], 9)
        self.assertEqual(updated_metadata["pending_escalation_notification"]["ticketId"], "KBC-000017")
        self.assertEqual(updated_metadata["pending_escalation_notification"]["note"], "Please review this chat urgently")
        self.assertEqual(updated_metadata["admin_documentation"]["escalationAgentId"], 9)
        self.assertEqual(updated_metadata["admin_documentation"]["escalationNote"], "Please review this chat urgently")
        insert_history_event.assert_any_call(
            17,
            "escalation_notified",
            {"id": 5, "role": "admin", "label": "Omar"},
            {
                "fromAgentId": 5,
                "fromAgentName": "Omar",
                "fromAgentUsername": "omar",
                "ticketId": "KBC-000017",
                "toAgentId": 9,
                "toAgentName": "Ahmed Hamamo",
                "toAgentUsername": "ahmedhamamo",
                "note": "Please review this chat urgently",
                "requestedAt": updated_metadata["pending_escalation_notification"]["requestedAt"],
            },
        )

    def test_update_admin_ticket_preserves_pending_escalation_notification_on_documentation_save(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "learner_id": 11,
            "category": "Technical",
            "technical_subcategory": "LMS",
            "status": "Pending",
            "status_reason": "Escalation",
            "assigned_agent_id": 5,
            "assigned_team": "Support Desk",
            "sla_status": "On Track",
            "metadata": {
                "pending_escalation_notification": {
                    "fromAgentId": 5,
                    "fromAgentName": "Omar",
                    "fromAgentUsername": "omar",
                    "toAgentId": 9,
                    "toAgentName": "Ahmed Hamamo",
                    "toAgentUsername": "ahmedhamamo",
                    "note": "Please review this chat urgently",
                    "ticketId": "KBC-000017",
                    "requestedAt": "2026-05-13T00:00:00+00:00",
                }
            },
            "created_at": datetime.now(timezone.utc),
            "closed_at": None,
            "conversation_id": 44,
            "conversation_metadata": {},
            "assigned_agent_username": "omar",
            "assigned_agent_name": "Omar",
            "inquiry": "Help needed",
        }
        actor_row = {
            "id": 5,
            "username": "omar",
            "full_name": "Omar",
            "role": "admin",
        }
        detail = {
            "ticket": {
                "id": "KBC-000017",
                "pendingEscalationNotification": {
                    "ticketId": "KBC-000017",
                    "toAgentId": 9,
                },
            }
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services, "resolve_next_sla_state", return_value=("On Track", False, None)),
            patch.object(services, "build_public_chat_id", return_value="CHAT-000144"),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "fetch_admin_ticket_detail", return_value=detail),
        ):
            response = services.update_admin_ticket(
                "KBC-000017",
                {
                    "documentation": {
                        "inquiry": "Help needed",
                        "chatId": "CHAT-000144",
                        "ticketId": "KBC-000017",
                    },
                    "actorUsername": "omar",
                },
            )

        self.assertEqual(response, detail)
        updated_metadata = json.loads(cursor.execute.call_args_list[0].args[1][5])
        self.assertIn("pending_escalation_notification", updated_metadata)
        self.assertEqual(updated_metadata["pending_escalation_notification"]["ticketId"], "KBC-000017")

    def test_update_admin_ticket_create_follow_up_ticket_returns_new_ticket_detail(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "learner_id": 11,
            "category": "Technical",
            "technical_subcategory": "LMS",
            "status": "Open",
            "status_reason": "",
            "assigned_agent_id": 5,
            "assigned_team": "Support Desk",
            "sla_status": "Pending Review",
            "metadata": {},
            "created_at": datetime.now(timezone.utc),
            "closed_at": None,
            "conversation_id": 44,
            "conversation_metadata": {},
            "assigned_agent_username": "omar",
            "assigned_agent_name": "Omar",
            "inquiry": "Help needed",
        }
        escalation_target = {
            "id": 9,
            "username": "ahmedhamamo",
            "full_name": "Ahmed Hamamo",
            "email": None,
            "role": "admin",
        }
        actor_row = {
            "id": 5,
            "username": "omar",
            "full_name": "Omar",
            "role": "admin",
        }
        detail = {
            "ticket": {
                "id": "KBC-000018",
                "status": "Open",
                "statusReason": "",
                "pendingEscalationNotification": {
                    "ticketId": "KBC-000018",
                    "toAgentId": 9,
                },
            }
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", side_effect=[ticket, escalation_target]),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services, "resolve_next_sla_state", return_value=("On Track", False, None)),
            patch.object(services, "build_public_chat_id", return_value="CHAT-000144"),
            patch.object(services, "dictfetchone", return_value={"id": 18}),
            patch.object(services, "build_public_ticket_id", return_value="KBC-000018"),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event"),
            patch.object(services, "fetch_admin_ticket_detail", return_value=detail),
        ):
            response = services.update_admin_ticket(
                "KBC-000017",
                {
                    "status": "Pending",
                    "statusReason": "Escalation",
                    "chatState": "open",
                    "escalationAgentId": 9,
                    "escalationNote": "Please review this chat urgently",
                    "createFollowUpTicket": True,
                    "followUpInquiry": "Follow-up needed",
                    "documentation": {
                        "inquiry": "Follow-up needed",
                        "chatId": "CHAT-000144",
                        "ticketId": "KBC-000017",
                        "ticketStatus": "Pending",
                        "statusReason": "Escalation",
                        "issuesAddressed": "no",
                        "escalationAgentId": 9,
                        "escalationAgentName": "Ahmed Hamamo",
                        "escalationNote": "Please review this chat urgently",
                    },
                    "note": "Workflow saved.",
                    "actorUsername": "omar",
                },
            )

        self.assertEqual(response, detail)
        self.assertIn("INSERT INTO tickets", cursor.execute.call_args_list[2].args[0])
        new_ticket_metadata = json.loads(cursor.execute.call_args_list[4].args[1][0])
        self.assertEqual(new_ticket_metadata["pending_escalation_notification"]["ticketId"], "KBC-000018")
        parent_ticket_metadata = json.loads(cursor.execute.call_args_list[5].args[1][0])
        self.assertNotIn("pending_escalation_notification", parent_ticket_metadata)

    def test_acknowledge_ticket_escalation_notification_clears_notification(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "metadata": {
                "pending_escalation_notification": {
                    "fromAgentId": 5,
                    "fromAgentName": "Omar",
                    "fromAgentUsername": "omar",
                    "toAgentId": 9,
                    "toAgentName": "Ahmed Hamamo",
                    "toAgentUsername": "ahmedhamamo",
                    "note": "Please review this chat urgently",
                    "ticketId": "KBC-000017",
                    "requestedAt": "2026-05-13T00:00:00+00:00",
                }
            },
        }
        actor_row = {
            "id": 9,
            "username": "ahmedhamamo",
            "full_name": "Ahmed Hamamo",
            "role": "admin",
        }
        detail = {
            "ticket": {
                "id": "KBC-000017",
                "pendingEscalationNotification": None,
            }
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "fetch_admin_ticket_detail", return_value=detail),
        ):
            response = services.acknowledge_ticket_escalation_notification(
                "KBC-000017",
                {"actorUsername": "ahmedhamamo"},
            )

        self.assertEqual(response, detail)
        updated_metadata = json.loads(cursor.execute.call_args.args[1][0])
        self.assertNotIn("pending_escalation_notification", updated_metadata)

    def test_update_admin_ticket_closing_escalated_ticket_notifies_original_admin(self):
        pending_escalation_notification = {
            "fromAgentId": 5,
            "fromAgentName": "Omar",
            "fromAgentUsername": "omar",
            "toAgentId": 9,
            "toAgentName": "Ahmed Hamamo",
            "toAgentUsername": "ahmedhamamo",
            "note": "Please review this chat urgently",
            "ticketId": "KBC-000017",
            "requestedAt": "2026-05-13T00:00:00+00:00",
        }
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "learner_id": 11,
            "category": "Technical",
            "technical_subcategory": "LMS",
            "status": "Pending",
            "status_reason": "Escalation",
            "priority": "High",
            "assigned_agent_id": 9,
            "assigned_team": "Support Desk",
            "sla_status": "On Track",
            "metadata": {
                "pending_escalation_notification": pending_escalation_notification,
            },
            "created_at": datetime.now(timezone.utc),
            "closed_at": None,
            "conversation_id": 44,
            "conversation_metadata": {},
            "assigned_agent_username": "ahmedhamamo",
            "assigned_agent_name": "Ahmed Hamamo",
            "inquiry": "Help needed",
        }
        actor_row = {
            "id": 9,
            "username": "ahmedhamamo",
            "full_name": "Ahmed Hamamo",
            "role": "admin",
        }
        detail = {
            "ticket": {
                "id": "KBC-000017",
                "status": "Closed",
                "latestEscalationClosure": {
                    "fromAgentId": 5,
                    "toAgentId": 9,
                },
            }
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services, "resolve_next_sla_state", return_value=("On Track", False, None)),
            patch.object(services, "build_public_chat_id", return_value="CHAT-000144"),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event") as insert_history_event,
            patch.object(services, "fetch_admin_ticket_detail", return_value=detail),
            patch.object(services, "persist_conversation_chat_duration"),
        ):
            response = services.update_admin_ticket(
                "KBC-000017",
                {
                    "status": "Closed",
                    "note": "Resolved after escalation.",
                    "actorUsername": "ahmedhamamo",
                },
            )

        self.assertEqual(response, detail)
        updated_metadata = json.loads(cursor.execute.call_args_list[0].args[1][5])
        self.assertNotIn("pending_escalation_notification", updated_metadata)
        self.assertIn("latest_escalation_closure", updated_metadata)
        latest_escalation_closure = updated_metadata["latest_escalation_closure"]
        self.assertEqual(latest_escalation_closure["fromAgentId"], 5)
        self.assertEqual(latest_escalation_closure["toAgentId"], 9)
        self.assertEqual(latest_escalation_closure["closedById"], 9)
        self.assertEqual(latest_escalation_closure["closedByName"], "Ahmed Hamamo")
        self.assertEqual(latest_escalation_closure["closedStatusReason"], "Closed via Agent")
        self.assertFalse(latest_escalation_closure["requesterAcknowledged"])
        insert_history_event.assert_any_call(
            17,
            "escalation_closed",
            {"id": 9, "role": "admin", "label": "Ahmed Hamamo"},
            {
                "ticketId": "KBC-000017",
                "fromAgentId": 5,
                "fromAgentName": "Omar",
                "fromAgentUsername": "omar",
                "toAgentId": 9,
                "toAgentName": "Ahmed Hamamo",
                "toAgentUsername": "ahmedhamamo",
                "closedById": 9,
                "closedByName": "Ahmed Hamamo",
                "closedByUsername": "ahmedhamamo",
                "note": "Please review this chat urgently",
                "requestedAt": "2026-05-13T00:00:00+00:00",
                "closedAt": latest_escalation_closure["closedAt"],
                "closedStatusReason": "Closed via Agent",
            },
        )

    def test_update_admin_ticket_closing_after_dismissed_escalation_uses_latest_history_event(self):
        history_payload = {
            "fromAgentId": 5,
            "fromAgentName": "Omar",
            "fromAgentUsername": "omar",
            "toAgentId": 9,
            "toAgentName": "Ahmed Hamamo",
            "toAgentUsername": "ahmedhamamo",
            "note": "Please review this chat urgently",
            "ticketId": "KBC-000017",
            "requestedAt": "2026-05-13T00:00:00+00:00",
        }
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "learner_id": 11,
            "category": "Technical",
            "technical_subcategory": "LMS",
            "status": "Pending",
            "status_reason": "Escalation",
            "priority": "High",
            "assigned_agent_id": 9,
            "assigned_team": "Support Desk",
            "sla_status": "On Track",
            "metadata": {},
            "created_at": datetime.now(timezone.utc),
            "closed_at": None,
            "conversation_id": 44,
            "conversation_metadata": {},
            "assigned_agent_username": "ahmedhamamo",
            "assigned_agent_name": "Ahmed Hamamo",
            "inquiry": "Help needed",
        }
        actor_row = {
            "id": 9,
            "username": "ahmedhamamo",
            "full_name": "Ahmed Hamamo",
            "role": "admin",
        }
        detail = {
            "ticket": {
                "id": "KBC-000017",
                "status": "Closed",
                "latestEscalationClosure": {
                    "fromAgentId": 5,
                    "toAgentId": 9,
                },
            }
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", side_effect=[ticket, {"payload": history_payload}]),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services, "resolve_next_sla_state", return_value=("On Track", False, None)),
            patch.object(services, "build_public_chat_id", return_value="CHAT-000144"),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event") as insert_history_event,
            patch.object(services, "fetch_admin_ticket_detail", return_value=detail),
            patch.object(services, "persist_conversation_chat_duration"),
        ):
            response = services.update_admin_ticket(
                "KBC-000017",
                {
                    "status": "Closed",
                    "note": "Resolved after escalation.",
                    "actorUsername": "ahmedhamamo",
                },
            )

        self.assertEqual(response, detail)
        updated_metadata = json.loads(cursor.execute.call_args_list[0].args[1][5])
        latest_escalation_closure = updated_metadata["latest_escalation_closure"]
        self.assertEqual(latest_escalation_closure["fromAgentId"], 5)
        self.assertEqual(latest_escalation_closure["toAgentId"], 9)
        insert_history_event.assert_any_call(
            17,
            "escalation_closed",
            {"id": 9, "role": "admin", "label": "Ahmed Hamamo"},
            {
                "ticketId": "KBC-000017",
                "fromAgentId": 5,
                "fromAgentName": "Omar",
                "fromAgentUsername": "omar",
                "toAgentId": 9,
                "toAgentName": "Ahmed Hamamo",
                "toAgentUsername": "ahmedhamamo",
                "closedById": 9,
                "closedByName": "Ahmed Hamamo",
                "closedByUsername": "ahmedhamamo",
                "note": "Please review this chat urgently",
                "requestedAt": "2026-05-13T00:00:00+00:00",
                "closedAt": latest_escalation_closure["closedAt"],
                "closedStatusReason": "Closed via Agent",
            },
        )

    def test_acknowledge_ticket_escalation_closure_marks_original_admin_notification_as_read(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "metadata": {
                "latest_escalation_closure": {
                    "fromAgentId": 5,
                    "fromAgentName": "Omar",
                    "fromAgentUsername": "omar",
                    "toAgentId": 9,
                    "toAgentName": "Ahmed Hamamo",
                    "toAgentUsername": "ahmedhamamo",
                    "closedById": 9,
                    "closedByName": "Ahmed Hamamo",
                    "closedByUsername": "ahmedhamamo",
                    "note": "Please review this chat urgently",
                    "ticketId": "KBC-000017",
                    "requestedAt": "2026-05-13T00:00:00+00:00",
                    "closedAt": "2026-05-13T01:00:00+00:00",
                    "closedStatusReason": "Closed via Agent",
                    "requesterAcknowledged": False,
                }
            },
        }
        actor = {"id": 5, "username": "omar", "full_name": "Omar", "role": "admin"}
        detail = {
            "ticket": {
                "id": "KBC-000017",
                "latestEscalationClosure": {
                    "requesterAcknowledged": True,
                },
            }
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "fetch_actor_by_username", return_value=actor),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "fetch_admin_ticket_detail", return_value=detail),
        ):
            response = services.acknowledge_ticket_escalation_closure(
                "KBC-000017",
                {"actorUsername": "omar"},
            )

        self.assertEqual(response, detail)
        updated_metadata = json.loads(cursor.execute.call_args.args[1][0])
        self.assertTrue(updated_metadata["latest_escalation_closure"]["requesterAcknowledged"])

    def test_create_follow_up_ticket_moves_pending_escalation_notification_to_new_ticket(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "learner_id": 11,
            "conversation_id": 44,
            "category": "Technical",
            "technical_subcategory": "LMS",
            "inquiry": "Help needed",
            "status": "Pending",
            "priority": "High",
            "assigned_agent_id": 5,
            "assigned_team": "Support Desk",
            "metadata": {
                "requester_role": "employer",
                "pending_escalation_notification": {
                    "fromAgentId": 5,
                    "fromAgentName": "Omar",
                    "fromAgentUsername": "omar",
                    "toAgentId": 9,
                    "toAgentName": "Ahmed Hamamo",
                    "toAgentUsername": "ahmedhamamo",
                    "note": "Please review this chat urgently",
                    "ticketId": "KBC-000017",
                    "requestedAt": "2026-05-13T00:00:00+00:00",
                }
            },
            "conversation_status": "open",
            "conversation_metadata": {},
        }
        actor_row = {
            "id": 5,
            "username": "omar",
            "full_name": "Omar",
            "role": "admin",
        }
        detail = {
            "ticket": {
                "id": "KBC-000018",
                "pendingEscalationNotification": {
                    "ticketId": "KBC-000018",
                },
            }
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services, "build_public_chat_id", return_value="CHAT-000144"),
            patch.object(services, "dictfetchone", return_value={"id": 18}),
            patch.object(services, "build_public_ticket_id", return_value="KBC-000018"),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event"),
            patch.object(services, "fetch_admin_ticket_detail", return_value=detail),
        ):
            response = services.create_follow_up_ticket(
                "KBC-000017",
                {"actorUsername": "omar", "inquiry": "Follow-up needed"},
            )

        self.assertEqual(response, detail)
        new_ticket_metadata = json.loads(cursor.execute.call_args_list[2].args[1][0])
        self.assertEqual(new_ticket_metadata["pending_escalation_notification"]["ticketId"], "KBC-000018")
        parent_ticket_metadata = json.loads(cursor.execute.call_args_list[3].args[1][0])
        self.assertNotIn("pending_escalation_notification", parent_ticket_metadata)

    def test_create_follow_up_ticket_requires_source_ticket_to_leave_open_state_first(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "learner_id": 11,
            "conversation_id": 44,
            "category": "Technical",
            "technical_subcategory": "LMS",
            "inquiry": "Help needed",
            "status": "Open",
            "priority": "Normal",
            "assigned_agent_id": 5,
            "assigned_team": "Support Desk",
            "metadata": {},
            "conversation_status": "open",
            "conversation_metadata": {},
        }

        with (
            patch.object(services, "sync_open_ticket_inactivity"),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
        ):
            with self.assertRaises(services.ApiError) as error_context:
                services.create_follow_up_ticket(
                    "KBC-000017",
                    {"actorUsername": "omar", "inquiry": "Follow-up needed"},
                )

        self.assertEqual(error_context.exception.status_code, 409)
        self.assertEqual(
            error_context.exception.message,
            "Move the current ticket to Pending or Closed before creating a follow-up ticket for this chat.",
        )

    def test_create_follow_up_ticket_rejects_closed_chat(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "learner_id": 11,
            "conversation_id": 44,
            "category": "Technical",
            "technical_subcategory": "LMS",
            "inquiry": "Help needed",
            "status": "Pending",
            "priority": "Normal",
            "assigned_agent_id": 5,
            "assigned_team": "Support Desk",
            "metadata": {},
            "conversation_status": "closed",
            "conversation_metadata": {},
        }

        with (
            patch.object(services, "sync_open_ticket_inactivity"),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
        ):
            with self.assertRaises(services.ApiError) as error_context:
                services.create_follow_up_ticket(
                    "KBC-000017",
                    {"actorUsername": "omar", "inquiry": "Follow-up needed"},
                )

        self.assertEqual(error_context.exception.status_code, 409)
        self.assertEqual(
            error_context.exception.message,
            "This chat has already been closed. Start a new chat instead of creating a follow-up ticket.",
        )

    def test_create_follow_up_ticket_preserves_requester_context_and_priority(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "learner_id": 11,
            "conversation_id": 44,
            "category": "Technical",
            "technical_subcategory": "LMS",
            "inquiry": "Help needed",
            "status": "Pending",
            "priority": "Normal",
            "assigned_agent_id": 5,
            "assigned_team": "Support Desk",
            "metadata": {
                "source": "support_portal_follow_up",
            },
            "conversation_status": "open",
            "conversation_metadata": {
                "requester_role": "employer",
                "requester_account_id": 71,
                "requester_username": "employer1",
            },
        }
        actor_row = {
            "id": 5,
            "username": "omar",
            "full_name": "Omar",
            "role": "admin",
        }
        detail = {
            "ticket": {
                "id": "KBC-000018",
            }
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services, "build_public_chat_id", return_value="CHAT-000144"),
            patch.object(services, "dictfetchone", return_value={"id": 18}),
            patch.object(services, "build_public_ticket_id", return_value="KBC-000018"),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event"),
            patch.object(services, "fetch_admin_ticket_detail", return_value=detail),
        ):
            response = services.create_follow_up_ticket(
                "KBC-000017",
                {"actorUsername": "omar", "inquiry": "Follow-up needed"},
            )

        self.assertEqual(response, detail)
        ticket_insert_params = cursor.execute.call_args_list[0].args[1]
        self.assertEqual(ticket_insert_params[10], "High")
        new_ticket_metadata = json.loads(ticket_insert_params[12])
        self.assertEqual(new_ticket_metadata["requester_role"], "employer")
        self.assertEqual(new_ticket_metadata["requester_account_id"], 71)
        self.assertEqual(new_ticket_metadata["requester_username"], "employer1")
        self.assertEqual(ticket_insert_params[13:20], ["standard", "active", "support", "support", True, False, None])

    def test_request_ticket_transfer_creates_pending_transfer_request(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "assigned_agent_id": 5,
            "assigned_team": "Support Desk",
            "metadata": {},
            "conversation_id": 44,
            "assigned_agent_username": "omar",
            "assigned_agent_name": "Omar",
        }
        target_agent = {
            "id": 9,
            "username": "ahmedhamamo",
            "full_name": "Ahmed Hamamo",
            "email": None,
            "account_scope": "staff",
            "role": "admin",
            "is_active": True,
            "metadata": {
                "legacy_support_access": True,
                "session_active": True,
                "console_status": "Off",
            },
        }
        actor = {"id": 5, "username": "omar", "full_name": "Omar", "role": "admin"}
        detail = {
            "ticket": {
                "id": "KBC-000017",
                "assignedAgentId": 5,
                "assignedAgentName": "Omar",
                "pendingTransferRequest": {
                    "fromAgentId": 5,
                    "fromAgentName": "Omar",
                    "fromAgentUsername": "omar",
                    "toAgentId": 9,
                    "toAgentName": "Ahmed Hamamo",
                    "toAgentUsername": "ahmedhamamo",
                    "reason": "Needs LMS support",
                    "requestedAt": "2026-05-13T00:00:00+00:00",
                },
            }
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", side_effect=[ticket, target_agent]),
            patch.object(services, "fetch_actor_by_username", return_value=actor),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event") as insert_history_event,
            patch.object(services, "fetch_admin_ticket_detail", return_value=detail),
        ):
            response = services.request_ticket_transfer(
                "KBC-000017",
                {"actorUsername": "omar", "targetAgentId": 9, "reason": "Needs LMS support"},
            )

        self.assertEqual(response, detail)
        update_params = cursor.execute.call_args.args[1]
        updated_metadata = json.loads(update_params[0])
        self.assertEqual(updated_metadata["pending_transfer_request"]["toAgentId"], 9)
        self.assertEqual(updated_metadata["pending_transfer_request"]["reason"], "Needs LMS support")
        insert_history_event.assert_any_call(
            17,
            "transfer_requested",
            {"id": 5, "role": "admin", "label": "Omar"},
            {
                "fromAgentId": 5,
                "fromAgentName": "Omar",
                "fromAgentUsername": "omar",
                "toAgentId": 9,
                "toAgentName": "Ahmed Hamamo",
                "toAgentUsername": "ahmedhamamo",
                "reason": "Needs LMS support",
                "requestedAt": updated_metadata["pending_transfer_request"]["requestedAt"],
            },
        )
        insert_history_event.assert_any_call(
            17,
            "internal_note",
            {"id": 5, "role": "admin", "label": "Omar"},
            {"note": "Transfer to Ahmed Hamamo. Reason: Needs LMS support"},
        )

    def test_request_ticket_transfer_rejects_target_without_receiver_access(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "assigned_agent_id": 5,
            "assigned_team": "Support Desk",
            "metadata": {},
            "conversation_id": 44,
            "assigned_agent_username": "omar",
            "assigned_agent_name": "Omar",
        }
        target_agent = {
            "id": 9,
            "username": "ops.agent",
            "full_name": "Operations Agent",
            "email": None,
            "account_scope": "staff",
            "role": "admin",
            "is_active": True,
            "metadata": {"legacy_operations_access": True},
        }

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", side_effect=[ticket, target_agent]),
        ):
            with self.assertRaises(services.ApiError) as raised_error:
                services.request_ticket_transfer(
                    "KBC-000017",
                    {"actorUsername": "omar", "targetAgentId": 9, "reason": "Needs LMS support"},
                )

        self.assertEqual(raised_error.exception.status_code, 400)
        self.assertEqual(raised_error.exception.message, "The selected agent does not receive support tickets.")

    def test_accept_ticket_transfer_request_reassigns_ticket(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "assigned_agent_id": 5,
            "assigned_team": "Support Desk",
            "metadata": {
                "pending_transfer_request": {
                    "fromAgentId": 5,
                    "fromAgentName": "Omar",
                    "fromAgentUsername": "omar",
                    "toAgentId": 9,
                    "toAgentName": "Ahmed Hamamo",
                    "toAgentUsername": "ahmedhamamo",
                    "reason": "Needs LMS support",
                    "requestedAt": "2026-05-13T00:00:00+00:00",
                }
            },
            "conversation_id": 44,
            "assigned_agent_username": "omar",
            "assigned_agent_name": "Omar",
        }
        actor = {"id": 9, "username": "ahmedhamamo", "full_name": "Ahmed Hamamo", "role": "admin"}
        target_agent = {
            "id": 9,
            "username": "ahmedhamamo",
            "full_name": "Ahmed Hamamo",
            "email": None,
            "account_scope": "staff",
            "role": "admin",
            "is_active": True,
            "metadata": {
                "legacy_support_access": True,
                "password_hash": "hashed-password",
                "session_active": True,
                "session_instance_id": "session-123",
                "queue_joined_at": "2026-05-13T00:00:00+00:00",
            },
        }
        detail = {
            "ticket": {
                "id": "KBC-000017",
                "assignedAgentId": 9,
                "assignedAgentName": "Ahmed Hamamo",
                "pendingTransferRequest": None,
                "latestTransferDecision": {
                    "status": "accepted",
                    "fromAgentId": 5,
                    "fromAgentName": "Omar",
                    "fromAgentUsername": "omar",
                    "toAgentId": 9,
                    "toAgentName": "Ahmed Hamamo",
                    "toAgentUsername": "ahmedhamamo",
                    "reason": "Needs LMS support",
                    "requestedAt": "2026-05-13T00:00:00+00:00",
                    "decidedAt": "2026-05-13T00:00:10+00:00",
                    "decidedById": 9,
                    "decidedByName": "Ahmed Hamamo",
                    "decidedByUsername": "ahmedhamamo",
                    "requesterAcknowledged": False,
                },
            }
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", side_effect=[ticket, target_agent]),
            patch.object(services, "fetch_actor_by_username", return_value=actor),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event") as insert_history_event,
            patch.object(services, "fetch_admin_ticket_detail", return_value=detail),
        ):
            response = services.accept_ticket_transfer_request(
                "KBC-000017",
                {"actorUsername": "ahmedhamamo"},
            )

        self.assertEqual(response, detail)
        first_update_params = cursor.execute.call_args_list[0].args[1]
        self.assertEqual(first_update_params[0], 9)
        self.assertEqual(first_update_params[1], "Support Desk")
        updated_metadata = json.loads(first_update_params[2])
        self.assertEqual(updated_metadata["latest_transfer_decision"]["status"], "accepted")
        self.assertFalse(updated_metadata["latest_transfer_decision"]["requesterAcknowledged"])
        support_account_update_params = next(
            call.args[1]
            for call in cursor.execute.call_args_list
            if "UPDATE support_accounts" in call.args[0]
        )
        persisted_target_metadata = json.loads(support_account_update_params[0])
        self.assertEqual(persisted_target_metadata["console_status"], "Available")
        self.assertEqual(persisted_target_metadata["password_hash"], "hashed-password")
        self.assertTrue(persisted_target_metadata["session_active"])
        self.assertEqual(persisted_target_metadata["session_instance_id"], "session-123")
        self.assertEqual(support_account_update_params[1], 9)
        insert_history_event.assert_any_call(
            17,
            "transfer_request_accepted",
            {"id": 9, "role": "admin", "label": "Ahmed Hamamo"},
            {
                "fromAgentId": 5,
                "fromAgentName": "Omar",
                "fromAgentUsername": "omar",
                "toAgentId": 9,
                "toAgentName": "Ahmed Hamamo",
                "toAgentUsername": "ahmedhamamo",
                "reason": "Needs LMS support",
                "requestedAt": "2026-05-13T00:00:00+00:00",
            },
        )
        insert_history_event.assert_any_call(
            17,
            "assignment_changed",
            {"id": 9, "role": "admin", "label": "Ahmed Hamamo"},
            {"fromAgentId": 5, "toAgentId": 9, "toAgentName": "Ahmed Hamamo"},
        )

    def test_reject_ticket_transfer_request_clears_pending_request(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "metadata": {
                "pending_transfer_request": {
                    "fromAgentId": 5,
                    "fromAgentName": "Omar",
                    "fromAgentUsername": "omar",
                    "toAgentId": 9,
                    "toAgentName": "Ahmed Hamamo",
                    "toAgentUsername": "ahmedhamamo",
                    "reason": "Needs LMS support",
                    "requestedAt": "2026-05-13T00:00:00+00:00",
                }
            },
        }
        actor = {"id": 9, "username": "ahmedhamamo", "full_name": "Ahmed Hamamo", "role": "admin"}
        detail = {
            "ticket": {
                "id": "KBC-000017",
                "pendingTransferRequest": None,
                "latestTransferDecision": {
                    "status": "rejected",
                    "fromAgentId": 5,
                    "fromAgentName": "Omar",
                    "fromAgentUsername": "omar",
                    "toAgentId": 9,
                    "toAgentName": "Ahmed Hamamo",
                    "toAgentUsername": "ahmedhamamo",
                    "reason": "Needs LMS support",
                    "requestedAt": "2026-05-13T00:00:00+00:00",
                    "decidedAt": "2026-05-13T00:00:10+00:00",
                    "decidedById": 9,
                    "decidedByName": "Ahmed Hamamo",
                    "decidedByUsername": "ahmedhamamo",
                    "requesterAcknowledged": False,
                },
            }
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "fetch_actor_by_username", return_value=actor),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event") as insert_history_event,
            patch.object(services, "fetch_admin_ticket_detail", return_value=detail),
        ):
            response = services.reject_ticket_transfer_request(
                "KBC-000017",
                {"actorUsername": "ahmedhamamo"},
            )

        self.assertEqual(response, detail)
        update_params = cursor.execute.call_args.args[1]
        updated_metadata = json.loads(update_params[0])
        self.assertEqual(updated_metadata["latest_transfer_decision"]["status"], "rejected")
        self.assertFalse(updated_metadata["latest_transfer_decision"]["requesterAcknowledged"])
        insert_history_event.assert_any_call(
            17,
            "transfer_request_rejected",
            {"id": 9, "role": "admin", "label": "Ahmed Hamamo"},
            {
                "fromAgentId": 5,
                "fromAgentName": "Omar",
                "fromAgentUsername": "omar",
                "toAgentId": 9,
                "toAgentName": "Ahmed Hamamo",
                "toAgentUsername": "ahmedhamamo",
                "reason": "Needs LMS support",
                "requestedAt": "2026-05-13T00:00:00+00:00",
            },
        )

    def test_acknowledge_ticket_transfer_decision_marks_requester_notification_as_read(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "metadata": {
                "latest_transfer_decision": {
                    "status": "rejected",
                    "fromAgentId": 5,
                    "fromAgentName": "Omar",
                    "fromAgentUsername": "omar",
                    "toAgentId": 9,
                    "toAgentName": "Ahmed Hamamo",
                    "toAgentUsername": "ahmedhamamo",
                    "reason": "Needs LMS support",
                    "requestedAt": "2026-05-13T00:00:00+00:00",
                    "decidedAt": "2026-05-13T00:00:10+00:00",
                    "decidedById": 9,
                    "decidedByName": "Ahmed Hamamo",
                    "decidedByUsername": "ahmedhamamo",
                    "requesterAcknowledged": False,
                }
            },
        }
        actor = {"id": 5, "username": "omar", "full_name": "Omar", "role": "admin"}
        detail = {
            "ticket": {
                "id": "KBC-000017",
                "latestTransferDecision": {
                    "status": "rejected",
                    "requesterAcknowledged": True,
                },
            }
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "fetch_actor_by_username", return_value=actor),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "fetch_admin_ticket_detail", return_value=detail),
        ):
            response = services.acknowledge_ticket_transfer_decision(
                "KBC-000017",
                {"actorUsername": "omar"},
            )

        self.assertEqual(response, detail)
        update_params = cursor.execute.call_args.args[1]
        updated_metadata = json.loads(update_params[0])
        self.assertTrue(updated_metadata["latest_transfer_decision"]["requesterAcknowledged"])

    def test_update_admin_ticket_rejects_invalid_status_reason_for_pending(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "status": "Open",
            "status_reason": "",
            "assigned_agent_id": None,
            "assigned_team": "Unassigned",
            "sla_status": "Pending Review",
            "metadata": {},
            "created_at": datetime.now(timezone.utc),
            "closed_at": None,
            "conversation_id": None,
            "conversation_metadata": {},
            "assigned_agent_username": None,
            "assigned_agent_name": None,
            "inquiry": "Help needed",
        }

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "require_actor_can_access_admin_ticket"),
        ):
            with self.assertRaises(services.ApiError) as error_context:
                services.update_admin_ticket(
                    "KBC-000017",
                    {"status": "Pending", "statusReason": "Closed via Agent", "note": "Triage update"},
                )

        self.assertEqual(error_context.exception.status_code, 400)
        self.assertEqual(error_context.exception.message, "Invalid status reason for pending tickets.")

    def test_pending_ticket_accepts_tutor_requested_status_reason(self):
        self.assertTrue(
            services.is_status_reason_allowed_for_status("Pending", "Tutor Requested")
        )

    def test_update_admin_ticket_rejects_manual_coverage_tutor_status_reason(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "status": "Pending",
            "status_reason": "Tutor Requested",
            "technical_subcategory": "Coverage",
            "assigned_agent_id": None,
            "assigned_team": "Unassigned",
            "sla_status": "On Track",
            "metadata": {"technical_subcategory": "Coverage"},
            "created_at": datetime.now(timezone.utc),
            "closed_at": None,
            "conversation_id": None,
            "conversation_metadata": {},
            "assigned_agent_username": None,
            "assigned_agent_name": None,
            "inquiry": "Coverage help needed",
        }

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "require_actor_can_access_admin_ticket"),
        ):
            with self.assertRaises(services.ApiError) as error_context:
                services.update_admin_ticket(
                    "KBC-000017",
                    {"status": "Pending", "statusReason": "Tutor Accepted", "note": "Manual update"},
                )

        self.assertEqual(error_context.exception.status_code, 409)
        self.assertEqual(
            error_context.exception.message,
            "Coverage tutor status reasons are managed by the tutor workflow only.",
        )

    def test_pending_tutor_requested_ticket_keeps_learner_chat_locked(self):
        self.assertTrue(
            services.is_chat_locked_for_learner("Pending", "Tutor Requested")
        )

    def test_update_admin_ticket_clears_stale_status_reason_when_existing_reason_is_invalid_for_status(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "status": "Closed",
            "status_reason": "Quick Ticket",
            "assigned_agent_id": None,
            "assigned_team": "Unassigned",
            "sla_status": "On Track",
            "metadata": {},
            "created_at": datetime.now(timezone.utc),
            "closed_at": datetime.now(timezone.utc),
            "conversation_id": None,
            "conversation_metadata": {},
            "assigned_agent_username": None,
            "assigned_agent_name": None,
            "inquiry": "Help needed",
        }
        detail = {
            "ticket": {
                "id": "KBC-000017",
                "status": "Closed",
                "statusReason": "",
                "slaStatus": "On Track",
            }
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "require_actor_can_access_admin_ticket"),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event") as insert_history_event,
            patch.object(services, "fetch_admin_ticket_detail", return_value=detail),
        ):
            response = services.update_admin_ticket("KBC-000017", {"note": "ok"})

        self.assertEqual(response, detail)
        update_params = cursor.execute.call_args_list[0].args[1]
        self.assertEqual(update_params[1], "")
        insert_history_event.assert_any_call(
            17,
            "status_reason_changed",
            None,
            {"from": "Quick Ticket", "to": ""},
        )
        insert_history_event.assert_any_call(
            17,
            "internal_note",
            None,
            {"note": "ok"},
        )

    def test_update_admin_ticket_only_persists_chat_duration_when_chat_closes(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "status": "Open",
            "status_reason": "",
            "assigned_agent_id": None,
            "assigned_team": "Support Desk",
            "sla_status": "On Track",
            "metadata": {},
            "created_at": datetime.now(timezone.utc),
            "closed_at": None,
            "conversation_id": 44,
            "conversation_metadata": {},
            "assigned_agent_username": None,
            "assigned_agent_name": None,
            "inquiry": "Help needed",
        }
        detail = {
            "ticket": {
                "id": "KBC-000017",
                "status": "Open",
                "statusReason": "",
                "slaStatus": "On Track",
            }
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "require_actor_can_access_admin_ticket"),
            patch.object(services, "resolve_next_sla_state", return_value=("On Track", False, None)),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event"),
            patch.object(services, "fetch_admin_ticket_detail", return_value=detail),
            patch.object(services, "persist_conversation_chat_duration") as persist_conversation_chat_duration,
        ):
            services.update_admin_ticket("KBC-000017", {"chatState": "open"})
            persist_conversation_chat_duration.assert_not_called()

            services.update_admin_ticket("KBC-000017", {"status": "Closed", "chatState": "closed", "note": "Resolved"})
            persist_conversation_chat_duration.assert_called_once_with(17, 44)

    def test_update_admin_ticket_auto_assigns_first_saver_when_ticket_is_unassigned(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "status": "Open",
            "status_reason": "",
            "assigned_agent_id": None,
            "assigned_team": "Unassigned",
            "sla_status": "Pending Review",
            "metadata": {},
            "created_at": datetime.now(timezone.utc),
            "closed_at": None,
            "conversation_id": None,
            "conversation_metadata": {},
            "assigned_agent_username": None,
            "assigned_agent_name": None,
            "inquiry": "Help needed",
        }
        actor_row = {
            "id": 9,
            "username": "omar",
            "full_name": "Omar Helmy",
            "role": "admin",
            "email": "omar@example.com",
            "account_scope": "staff",
            "is_active": True,
            "metadata": {"legacy_support_access": True},
        }
        detail = {
            "ticket": {
                "id": "KBC-000017",
                "assignedAgentId": 9,
                "assignedTeam": "Support Desk",
                "status": "Open",
                "statusReason": "",
                "slaStatus": "Pending Review",
            }
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services, "resolve_next_sla_state", return_value=("Pending Review", False, None)),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event") as insert_history_event,
            patch.object(services, "fetch_admin_ticket_detail", return_value=detail),
        ):
            response = services.update_admin_ticket("KBC-000017", {"note": "First save", "actorUsername": "omar"})

        self.assertEqual(response, detail)
        update_params = cursor.execute.call_args_list[0].args[1]
        self.assertEqual(update_params[2], 9)
        self.assertEqual(update_params[3], "Support Desk")
        insert_history_event.assert_any_call(
            17,
            "assignment_changed",
            {"id": 9, "role": "admin", "label": "Omar Helmy"},
            {"fromAgentId": None, "toAgentId": 9, "toAgentName": "Omar Helmy"},
        )

    def test_update_admin_ticket_rejects_support_only_actor_for_coverage_ticket(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "status": "Pending",
            "status_reason": services.STATUS_REASON_COVERAGE_TICKET,
            "technical_subcategory": "Coverage",
            "assigned_agent_id": None,
            "assigned_team": services.ASSIGNED_TEAM_SUPPORT_DESK,
            "sla_status": "Pending Review",
            "metadata": {},
            "is_archived": False,
            "created_at": datetime.now(timezone.utc),
            "closed_at": None,
            "conversation_id": None,
            "conversation_metadata": {},
            "assigned_agent_username": None,
            "assigned_agent_name": None,
            "inquiry": "Coverage request",
        }
        actor_row = {
            "id": 9,
            "username": "support.agent",
            "full_name": "Support Agent",
            "role": "agent",
            "email": "support.agent@example.com",
            "metadata": {"legacy_support_access": True, "legacy_operations_access": False},
        }

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
        ):
            with self.assertRaises(services.ApiError) as raised_error:
                services.update_admin_ticket(
                    "KBC-000017",
                    {"note": "Trying to edit", "actorUsername": "support.agent"},
                )

        self.assertEqual(raised_error.exception.status_code, 403)
        self.assertEqual(raised_error.exception.message, "You do not have permission to access this ticket.")

    def test_update_admin_ticket_queues_quick_ticket_closed_notification(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "learner_id": 44,
            "category": "Technical",
            "technical_subcategory": "Aptem",
            "inquiry": "Help needed",
            "status": "Pending",
            "status_reason": services.STATUS_REASON_QUICK_TICKET,
            "priority": "Normal",
            "assigned_agent_id": 9,
            "assigned_team": "Support Desk",
            "sla_status": "On Track",
            "metadata": {},
            "is_archived": False,
            "created_at": datetime.now(timezone.utc),
            "closed_at": None,
            "conversation_id": 88,
            "conversation_metadata": {},
            "learner_name": "Omar Badr",
            "learner_email": "omar@example.com",
            "assigned_agent_username": "agent",
            "assigned_agent_name": "Support Agent",
        }
        actor_row = {
            "id": 9,
            "username": "agent",
            "full_name": "Support Agent",
            "role": "admin",
            "email": "agent@example.com",
        }
        detail = {
            "ticket": {
                "id": "KBC-000017",
                "status": "Closed",
                "statusReason": services.STATUS_REASON_CLOSED_BY_AGENT,
                "slaStatus": "On Track",
            }
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services, "get_latest_ticket_escalation_notification", return_value=None),
            patch.object(services, "resolve_next_sla_state", return_value=("On Track", False, None)),
            patch.object(services, "persist_conversation_chat_duration"),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event"),
            patch.object(services, "fetch_admin_ticket_detail", return_value=detail),
            patch.object(services, "queue_quick_ticket_closed_notification") as queue_closed,
        ):
            response = services.update_admin_ticket(
                "KBC-000017",
                {
                    "status": "Closed",
                    "statusReason": services.STATUS_REASON_CLOSED_BY_AGENT,
                    "note": "Resolved",
                    "actorUsername": "agent",
                },
            )

        self.assertEqual(response, detail)
        queue_closed.assert_called_once()
        self.assertEqual(queue_closed.call_args.kwargs["status"], "Closed")
        self.assertEqual(queue_closed.call_args.kwargs["status_reason"], services.STATUS_REASON_CLOSED_BY_AGENT)
        update_params = cursor.execute.call_args_list[0].args[1]
        updated_metadata = json.loads(update_params[5])
        self.assertTrue(updated_metadata[services.QUICK_TICKET_ORIGIN_METADATA_KEY])

    def test_update_admin_ticket_allows_admin_to_assign_ticket_receiver(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "status": "Open",
            "status_reason": "",
            "assigned_agent_id": 5,
            "assigned_team": "Support Desk",
            "sla_status": "Pending Review",
            "metadata": {},
            "created_at": datetime.now(timezone.utc),
            "closed_at": None,
            "conversation_id": None,
            "conversation_metadata": {},
            "assigned_agent_username": "ahmed",
            "assigned_agent_name": "Ahmed Hamamo",
            "inquiry": "Help needed",
        }
        actor_row = {
            "id": 1,
            "username": "manager",
            "full_name": "Support Manager",
            "role": "admin",
            "email": "manager@example.com",
        }
        selected_agent = {
            "id": 9,
            "username": "omar",
            "full_name": "Omar Helmy",
            "role": "agent",
            "email": "omar@example.com",
            "account_scope": "staff",
            "is_active": True,
            "metadata": {"legacy_support_access": True},
        }
        detail = {
            "ticket": {
                "id": "KBC-000017",
                "assignedAgentId": 9,
                "assignedTeam": "Support Desk",
                "status": "Open",
                "statusReason": "",
                "slaStatus": "Pending Review",
            }
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", side_effect=[ticket, selected_agent]),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services, "resolve_next_sla_state", return_value=("Pending Review", False, None)),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event") as insert_history_event,
            patch.object(services, "fetch_admin_ticket_detail", return_value=detail),
        ):
            response = services.update_admin_ticket(
                "KBC-000017",
                {"note": "Reassigned", "actorUsername": "manager", "assignedAgentId": 9},
            )

        self.assertEqual(response, detail)
        update_params = cursor.execute.call_args_list[0].args[1]
        self.assertEqual(update_params[2], 9)
        self.assertEqual(update_params[3], "Support Desk")
        insert_history_event.assert_any_call(
            17,
            "assignment_changed",
            {"id": 1, "role": "admin", "label": "Support Manager"},
            {"fromAgentId": 5, "toAgentId": 9, "toAgentName": "Omar Helmy"},
        )

    def test_update_admin_ticket_allows_learning_plan_assignment_to_operations_receiver(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "status": "Pending",
            "status_reason": services.STATUS_REASON_QUICK_TICKET,
            "assigned_agent_id": None,
            "assigned_team": services.ASSIGNED_TEAM_LEARNING_PLAN,
            "sla_status": "Pending Review",
            "metadata": {},
            "created_at": datetime.now(timezone.utc),
            "closed_at": None,
            "conversation_id": None,
            "conversation_metadata": {},
            "assigned_agent_username": None,
            "assigned_agent_name": None,
            "inquiry": "Learning plan request",
        }
        actor_row = {
            "id": 1,
            "username": "manager",
            "full_name": "Support Manager",
            "role": "admin",
            "email": "manager@example.com",
        }
        operations_agent = {
            "id": 12,
            "username": "ops.agent",
            "full_name": "Operations Agent",
            "role": "agent",
            "email": "ops@example.com",
            "account_scope": "staff",
            "is_active": True,
            "metadata": {"legacy_operations_access": True},
        }
        detail = {
            "ticket": {
                "id": "KBC-000017",
                "assignedAgentId": 12,
                "assignedTeam": services.ASSIGNED_TEAM_LEARNING_PLAN,
                "status": "Pending",
                "statusReason": services.STATUS_REASON_QUICK_TICKET,
                "slaStatus": "Pending Review",
            }
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", side_effect=[ticket, operations_agent]),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services, "resolve_next_sla_state", return_value=("Pending Review", False, None)),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event") as insert_history_event,
            patch.object(services, "fetch_admin_ticket_detail", return_value=detail),
        ):
            response = services.update_admin_ticket(
                "KBC-000017",
                {"note": "Assign to operations", "actorUsername": "manager", "assignedAgentId": 12},
            )

        self.assertEqual(response, detail)
        update_params = cursor.execute.call_args_list[0].args[1]
        self.assertEqual(update_params[2], 12)
        self.assertEqual(update_params[3], services.ASSIGNED_TEAM_LEARNING_PLAN)
        insert_history_event.assert_any_call(
            17,
            "assignment_changed",
            {"id": 1, "role": "admin", "label": "Support Manager"},
            {"fromAgentId": None, "toAgentId": 12, "toAgentName": "Operations Agent"},
        )

    def test_update_admin_ticket_rejects_learning_plan_assignment_to_support_only_receiver(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "status": "Pending",
            "status_reason": services.STATUS_REASON_QUICK_TICKET,
            "assigned_agent_id": None,
            "assigned_team": services.ASSIGNED_TEAM_LEARNING_PLAN,
            "sla_status": "Pending Review",
            "metadata": {},
            "created_at": datetime.now(timezone.utc),
            "closed_at": None,
            "conversation_id": None,
            "conversation_metadata": {},
            "assigned_agent_username": None,
            "assigned_agent_name": None,
            "inquiry": "Learning plan request",
        }
        actor_row = {
            "id": 1,
            "username": "manager",
            "full_name": "Support Manager",
            "role": "admin",
            "email": "manager@example.com",
        }
        support_agent = {
            "id": 9,
            "username": "support.agent",
            "full_name": "Support Agent",
            "role": "agent",
            "email": "support@example.com",
            "account_scope": "staff",
            "is_active": True,
            "metadata": {"legacy_support_access": True},
        }

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", side_effect=[ticket, support_agent]),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
        ):
            with self.assertRaises(services.ApiError) as raised_error:
                services.update_admin_ticket(
                    "KBC-000017",
                    {"note": "Assign to support", "actorUsername": "manager", "assignedAgentId": 9},
                )

        self.assertEqual(raised_error.exception.status_code, 400)
        self.assertEqual(raised_error.exception.message, "The selected agent does not receive Learning Plan tickets.")

    def test_update_admin_ticket_rejects_assignment_from_non_admin_actor(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "status": "Open",
            "status_reason": "",
            "assigned_agent_id": 5,
            "assigned_team": "Support Desk",
            "sla_status": "Pending Review",
            "metadata": {},
            "created_at": datetime.now(timezone.utc),
            "closed_at": None,
            "conversation_id": None,
            "conversation_metadata": {},
            "assigned_agent_username": "ahmed",
            "assigned_agent_name": "Ahmed Hamamo",
            "inquiry": "Help needed",
        }
        actor_row = {
            "id": 3,
            "username": "agent",
            "full_name": "Support Agent",
            "role": "agent",
            "email": "agent@example.com",
            "account_scope": "staff",
            "is_active": True,
            "metadata": {"legacy_support_access": True},
        }

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
        ):
            with self.assertRaises(services.ApiError) as raised_error:
                services.update_admin_ticket(
                    "KBC-000017",
                    {"note": "Reassigned", "actorUsername": "agent", "assignedAgentId": 9},
                )

        self.assertEqual(raised_error.exception.status_code, 403)
        self.assertEqual(raised_error.exception.message, "Only admins and superadmins can assign tickets.")

    def test_update_admin_ticket_rejects_assignment_to_account_without_ticket_access(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "status": "Open",
            "status_reason": "",
            "assigned_agent_id": 5,
            "assigned_team": "Support Desk",
            "sla_status": "Pending Review",
            "metadata": {},
            "created_at": datetime.now(timezone.utc),
            "closed_at": None,
            "conversation_id": None,
            "conversation_metadata": {},
            "assigned_agent_username": "ahmed",
            "assigned_agent_name": "Ahmed Hamamo",
            "inquiry": "Help needed",
        }
        actor_row = {
            "id": 1,
            "username": "manager",
            "full_name": "Support Manager",
            "role": "admin",
            "email": "manager@example.com",
        }

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", side_effect=[ticket, None]),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
        ):
            with self.assertRaises(services.ApiError) as raised_error:
                services.update_admin_ticket(
                    "KBC-000017",
                    {"note": "Reassigned", "actorUsername": "manager", "assignedAgentId": 9},
                )

        self.assertEqual(raised_error.exception.status_code, 400)
        self.assertEqual(raised_error.exception.message, "The selected agent does not receive support tickets.")

    def test_update_admin_ticket_requires_note_before_team_transfer(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "status": "Pending",
            "status_reason": services.STATUS_REASON_QUICK_TICKET,
            "assigned_agent_id": 5,
            "assigned_team": services.ASSIGNED_TEAM_SUPPORT_DESK,
            "sla_status": "On Track",
            "metadata": {},
            "is_archived": False,
            "created_at": datetime.now(timezone.utc),
            "closed_at": None,
            "conversation_id": None,
            "conversation_metadata": {},
            "assigned_agent_username": "omar",
            "assigned_agent_name": "Omar Helmy",
            "inquiry": "Help needed",
        }
        actor_row = {
            "id": 1,
            "username": "manager",
            "full_name": "Support Manager",
            "role": "admin",
            "email": "manager@example.com",
        }

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
        ):
            with self.assertRaises(services.ApiError) as raised_error:
                services.update_admin_ticket(
                    "KBC-000017",
                    {
                        "actorUsername": "manager",
                        "assignedTeam": services.ASSIGNED_TEAM_LEARNING_PLAN,
                    },
                )

        self.assertEqual(raised_error.exception.status_code, 400)
        self.assertEqual(raised_error.exception.message, "Add a transfer note before moving this ticket to another team.")

    def test_update_admin_ticket_rejects_coverage_transfer_to_dynamic_team(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "status": "Pending",
            "status_reason": services.STATUS_REASON_COVERAGE_TICKET,
            "assigned_agent_id": None,
            "assigned_team": services.ASSIGNED_TEAM_LEARNING_PLAN,
            "sla_status": "On Track",
            "metadata": {},
            "is_archived": False,
            "created_at": datetime.now(timezone.utc),
            "closed_at": None,
            "conversation_id": None,
            "conversation_metadata": {},
            "technical_subcategory": "Coverage",
            "inquiry": "Coverage request",
        }
        actor_row = {
            "id": 1,
            "username": "manager",
            "full_name": "Support Manager",
            "role": "admin",
            "email": "manager@example.com",
        }
        curriculum_team = {
            "id": 101,
            "key": "curriculum_team",
            "name": "Curriculum Team",
            "description": "",
            "receiver_access_metadata_key": "team_access:curriculum_team",
            "receiver_error_ticket_label": "Curriculum Team",
            "is_active": True,
            "metadata": {},
        }

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services, "fetch_optional_dynamic_team_row_by_assigned_team", return_value=curriculum_team),
        ):
            with self.assertRaises(services.ApiError) as raised_error:
                services.update_admin_ticket(
                    "KBC-000017",
                    {
                        "actorUsername": "manager",
                        "assignedTeam": "Curriculum Team",
                        "note": "Move to Curriculum.",
                    },
                )

        self.assertEqual(raised_error.exception.status_code, 409)
        self.assertEqual(raised_error.exception.message, "Coverage tickets must stay in the Learning Plan Team workflow.")

    def test_support_agent_can_transfer_ticket_to_learning_plan_team_with_note(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "learner_id": 44,
            "category": "Technical",
            "technical_subcategory": "LMS",
            "inquiry": "Help needed",
            "status": "Pending",
            "status_reason": services.STATUS_REASON_QUICK_TICKET,
            "priority": "High",
            "assigned_agent_id": 5,
            "assigned_team": services.ASSIGNED_TEAM_SUPPORT_DESK,
            "sla_status": "On Track",
            "metadata": {"requester_role": "coach", "requester_source": "legacy_portal"},
            "is_archived": False,
            "created_at": datetime.now(timezone.utc),
            "closed_at": None,
            "conversation_id": None,
            "conversation_metadata": {},
            "learner_name": "Tina Wright",
            "learner_email": "tina@example.com",
            "learner_source": "legacy_portal",
            "learner_metadata": {},
            "assigned_agent_username": "omar",
            "assigned_agent_name": "Omar Helmy",
        }
        actor_row = {
            "id": 5,
            "username": "omar",
            "full_name": "Omar Helmy",
            "role": "agent",
            "email": "omar@example.com",
            "account_scope": "staff",
            "is_active": True,
            "metadata": {"legacy_support_access": True, "legacy_operations_access": False},
        }
        detail = {
            "ticket": {
                "id": "KBC-000017",
                "assignedAgentId": None,
                "assignedTeam": services.ASSIGNED_TEAM_LEARNING_PLAN,
                "status": "Pending",
                "statusReason": services.STATUS_REASON_QUICK_TICKET,
                "slaStatus": "On Track",
            }
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services, "resolve_next_sla_state", return_value=("On Track", False, None)),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event") as insert_history_event,
            patch.object(services, "fetch_admin_ticket_detail", return_value=detail),
            patch.object(services, "notify_learning_plan_ticket_transfer") as notify_learning_plan_ticket_transfer,
        ):
            response = services.update_admin_ticket(
                "KBC-000017",
                {
                    "actorUsername": "omar",
                    "assignedTeam": services.ASSIGNED_TEAM_LEARNING_PLAN,
                    "note": "Needs Learning Plan review.",
                },
            )

        self.assertEqual(response, detail)
        update_params = cursor.execute.call_args_list[0].args[1]
        self.assertIsNone(update_params[2])
        self.assertEqual(update_params[3], services.ASSIGNED_TEAM_LEARNING_PLAN)
        insert_history_event.assert_any_call(
            17,
            "team_transferred",
            {"id": 5, "role": "agent", "label": "Omar Helmy"},
            {
                "fromTeam": services.ASSIGNED_TEAM_SUPPORT_DESK,
                "toTeam": services.ASSIGNED_TEAM_LEARNING_PLAN,
                "note": "Needs Learning Plan review.",
            },
        )
        notify_learning_plan_ticket_transfer.assert_called_once()

    def test_operations_agent_can_return_learning_plan_ticket_to_support_with_note(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "learner_id": 44,
            "category": "Technical",
            "technical_subcategory": "LMS",
            "inquiry": "Help needed",
            "status": "Pending",
            "status_reason": services.STATUS_REASON_QUICK_TICKET,
            "priority": "High",
            "assigned_agent_id": 12,
            "assigned_team": services.ASSIGNED_TEAM_LEARNING_PLAN,
            "sla_status": "On Track",
            "metadata": {"requester_role": "coach", "requester_source": "legacy_portal"},
            "is_archived": False,
            "created_at": datetime.now(timezone.utc),
            "closed_at": None,
            "conversation_id": None,
            "conversation_metadata": {},
            "learner_name": "Tina Wright",
            "learner_email": "tina@example.com",
            "learner_source": "legacy_portal",
            "learner_metadata": {},
            "assigned_agent_username": "ops.agent",
            "assigned_agent_name": "Operations Agent",
        }
        actor_row = {
            "id": 12,
            "username": "ops.agent",
            "full_name": "Operations Agent",
            "role": "agent",
            "email": "ops@example.com",
            "account_scope": "staff",
            "is_active": True,
            "metadata": {"legacy_support_access": False, "legacy_operations_access": True},
        }
        detail = {
            "ticket": {
                "id": "KBC-000017",
                "assignedAgentId": None,
                "assignedTeam": services.ASSIGNED_TEAM_SUPPORT_DESK,
                "status": "Pending",
                "statusReason": services.STATUS_REASON_QUICK_TICKET,
                "slaStatus": "On Track",
            }
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services, "resolve_next_sla_state", return_value=("On Track", False, None)),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event"),
            patch.object(services, "fetch_admin_ticket_detail", return_value=detail),
            patch.object(services, "notify_learning_plan_ticket_transfer") as notify_learning_plan_ticket_transfer,
        ):
            response = services.update_admin_ticket(
                "KBC-000017",
                {
                    "actorUsername": "ops.agent",
                    "assignedTeam": services.ASSIGNED_TEAM_SUPPORT_DESK,
                    "note": "Wrong queue; returning to support.",
                },
            )

        self.assertEqual(response, detail)
        update_params = cursor.execute.call_args_list[0].args[1]
        self.assertIsNone(update_params[2])
        self.assertEqual(update_params[3], services.ASSIGNED_TEAM_SUPPORT_DESK)
        notify_learning_plan_ticket_transfer.assert_not_called()

    def test_agent_team_transfer_cannot_assign_receiver(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "status": "Pending",
            "status_reason": services.STATUS_REASON_QUICK_TICKET,
            "assigned_agent_id": 5,
            "assigned_team": services.ASSIGNED_TEAM_SUPPORT_DESK,
            "sla_status": "On Track",
            "metadata": {},
            "is_archived": False,
            "created_at": datetime.now(timezone.utc),
            "closed_at": None,
            "conversation_id": None,
            "conversation_metadata": {},
            "assigned_agent_username": "omar",
            "assigned_agent_name": "Omar Helmy",
            "inquiry": "Help needed",
        }
        actor_row = {
            "id": 5,
            "username": "omar",
            "full_name": "Omar Helmy",
            "role": "agent",
            "email": "omar@example.com",
            "account_scope": "staff",
            "is_active": True,
            "metadata": {"legacy_support_access": True, "legacy_operations_access": False},
        }

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
        ):
            with self.assertRaises(services.ApiError) as raised_error:
                services.update_admin_ticket(
                    "KBC-000017",
                    {
                        "actorUsername": "omar",
                        "assignedTeam": services.ASSIGNED_TEAM_LEARNING_PLAN,
                        "assignedAgentId": 5,
                        "note": "Needs Learning Plan review.",
                    },
                )

        self.assertEqual(raised_error.exception.status_code, 403)
        self.assertEqual(raised_error.exception.message, "Team transfers by agents cannot assign a receiver.")

    def test_update_admin_ticket_notifies_learning_plan_team_on_team_transfer(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "learner_id": 44,
            "category": "Technical",
            "technical_subcategory": "LMS",
            "inquiry": "Help needed",
            "status": "Pending",
            "status_reason": services.STATUS_REASON_QUICK_TICKET,
            "priority": "High",
            "assigned_agent_id": 5,
            "assigned_team": services.ASSIGNED_TEAM_SUPPORT_DESK,
            "sla_status": "On Track",
            "metadata": {
                "requester_role": "coach",
                "requester_source": "legacy_portal",
                services.PENDING_TRANSFER_REQUEST_METADATA_KEY: {
                    "fromAgentId": 5,
                    "fromAgentName": "Omar Helmy",
                    "fromAgentUsername": "omar",
                    "toAgentId": 9,
                    "toAgentName": "Ahmed Hamamo",
                    "toAgentUsername": "ahmed",
                    "reason": "Please take over",
                    "requestedAt": "2026-06-17T19:00:00Z",
                },
                services.LATEST_TRANSFER_DECISION_METADATA_KEY: {
                    "status": "rejected",
                    "fromAgentId": 5,
                    "fromAgentName": "Omar Helmy",
                    "fromAgentUsername": "omar",
                    "toAgentId": 9,
                    "toAgentName": "Ahmed Hamamo",
                    "toAgentUsername": "ahmed",
                    "reason": "Please take over",
                    "requestedAt": "2026-06-17T19:00:00Z",
                    "decidedAt": "2026-06-17T19:05:00Z",
                    "decidedById": 9,
                    "decidedByName": "Ahmed Hamamo",
                    "decidedByUsername": "ahmed",
                    "requesterAcknowledged": False,
                },
            },
            "is_archived": False,
            "created_at": datetime.now(timezone.utc),
            "closed_at": None,
            "conversation_id": None,
            "conversation_metadata": {},
            "learner_name": "Tina Wright",
            "learner_email": "tina@example.com",
            "learner_source": "legacy_portal",
            "learner_metadata": {},
            "assigned_agent_username": "omar",
            "assigned_agent_name": "Omar Helmy",
        }
        actor_row = {
            "id": 1,
            "username": "manager",
            "full_name": "Support Manager",
            "role": "admin",
            "email": "manager@example.com",
            "metadata": {},
        }
        detail = {
            "ticket": {
                "id": "KBC-000017",
                "assignedAgentId": None,
                "assignedTeam": services.ASSIGNED_TEAM_LEARNING_PLAN,
                "status": "Pending",
                "statusReason": services.STATUS_REASON_QUICK_TICKET,
                "slaStatus": "On Track",
            }
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services, "resolve_next_sla_state", return_value=("On Track", False, None)),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event") as insert_history_event,
            patch.object(services, "fetch_admin_ticket_detail", return_value=detail),
            patch.object(services, "notify_learning_plan_ticket_transfer") as notify_learning_plan_ticket_transfer,
        ):
            response = services.update_admin_ticket(
                "KBC-000017",
                {
                    "actorUsername": "manager",
                    "assignedTeam": services.ASSIGNED_TEAM_LEARNING_PLAN,
                    "note": "Please review the learning plan request.",
                },
            )

        self.assertEqual(response, detail)
        update_params = cursor.execute.call_args_list[0].args[1]
        self.assertIsNone(update_params[2])
        self.assertEqual(update_params[3], services.ASSIGNED_TEAM_LEARNING_PLAN)
        insert_history_event.assert_any_call(
            17,
            "team_transferred",
            {"id": 1, "role": "admin", "label": "Support Manager"},
            {
                "fromTeam": services.ASSIGNED_TEAM_SUPPORT_DESK,
                "toTeam": services.ASSIGNED_TEAM_LEARNING_PLAN,
                "note": "Please review the learning plan request.",
            },
        )
        notify_learning_plan_ticket_transfer.assert_called_once()
        self.assertEqual(notify_learning_plan_ticket_transfer.call_args.args[0], 17)
        webhook_payload = notify_learning_plan_ticket_transfer.call_args.args[1]
        self.assertEqual(webhook_payload["event"], services.LEARNING_PLAN_TICKET_TRANSFER_WEBHOOK_EVENT)
        self.assertEqual(webhook_payload["ticket"]["assignedTeam"], services.ASSIGNED_TEAM_LEARNING_PLAN)
        self.assertEqual(webhook_payload["requester"]["email"], "tina@example.com")
        self.assertEqual(webhook_payload["transfer"]["fromTeam"], services.ASSIGNED_TEAM_SUPPORT_DESK)
        self.assertEqual(webhook_payload["transfer"]["toTeam"], services.ASSIGNED_TEAM_LEARNING_PLAN)
        self.assertEqual(webhook_payload["transfer"]["transferredBy"]["name"], "Support Manager")
        self.assertIsNone(webhook_payload["transfer"]["assignedAgent"]["id"])
        self.assertEqual(webhook_payload["transfer"]["assignedAgent"]["name"], "")
        self.assertEqual(webhook_payload["transfer"]["note"], "Please review the learning plan request.")
        persisted_metadata = json.loads(update_params[5])
        self.assertNotIn(services.PENDING_TRANSFER_REQUEST_METADATA_KEY, persisted_metadata)
        self.assertNotIn(services.LATEST_TRANSFER_DECISION_METADATA_KEY, persisted_metadata)
        self.assertEqual(
            persisted_metadata["pending_learning_plan_transfer_notification"]["ticketId"],
            "KBC-000017",
        )
        self.assertEqual(
            persisted_metadata["pending_learning_plan_transfer_notification"]["fromTeam"],
            services.ASSIGNED_TEAM_SUPPORT_DESK,
        )
        self.assertEqual(
            persisted_metadata["pending_learning_plan_transfer_notification"]["toTeam"],
            services.ASSIGNED_TEAM_LEARNING_PLAN,
        )
        self.assertEqual(
            persisted_metadata["pending_learning_plan_transfer_notification"]["note"],
            "Please review the learning plan request.",
        )

    def test_update_admin_ticket_does_not_notify_learning_plan_team_when_transferring_back_to_support(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "learner_id": 44,
            "category": "Technical",
            "technical_subcategory": "LMS",
            "inquiry": "Help needed",
            "status": "Pending",
            "status_reason": services.STATUS_REASON_QUICK_TICKET,
            "priority": "High",
            "assigned_agent_id": 5,
            "assigned_team": services.ASSIGNED_TEAM_LEARNING_PLAN,
            "sla_status": "On Track",
            "metadata": {
                "requester_role": "coach",
                "requester_source": "legacy_portal",
                "pending_learning_plan_transfer_notification": {
                    "ticketId": "KBC-000017",
                    "requesterName": "Tina Wright",
                    "requesterEmail": "tina@example.com",
                    "requesterRole": "coach",
                    "fromTeam": services.ASSIGNED_TEAM_SUPPORT_DESK,
                    "toTeam": services.ASSIGNED_TEAM_LEARNING_PLAN,
                    "transferredAt": "2026-06-17T20:00:00Z",
                },
            },
            "is_archived": False,
            "created_at": datetime.now(timezone.utc),
            "closed_at": None,
            "conversation_id": None,
            "conversation_metadata": {},
            "learner_name": "Tina Wright",
            "learner_email": "tina@example.com",
            "learner_source": "legacy_portal",
            "learner_metadata": {},
            "assigned_agent_username": "omar",
            "assigned_agent_name": "Omar Helmy",
        }
        actor_row = {
            "id": 1,
            "username": "manager",
            "full_name": "Support Manager",
            "role": "admin",
            "email": "manager@example.com",
            "metadata": {},
        }
        detail = {
            "ticket": {
                "id": "KBC-000017",
                "assignedAgentId": None,
                "assignedTeam": services.ASSIGNED_TEAM_SUPPORT_DESK,
                "status": "Pending",
                "statusReason": services.STATUS_REASON_QUICK_TICKET,
                "slaStatus": "On Track",
            }
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services, "resolve_next_sla_state", return_value=("On Track", False, None)),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event"),
            patch.object(services, "fetch_admin_ticket_detail", return_value=detail),
            patch.object(services, "notify_learning_plan_ticket_transfer") as notify_learning_plan_ticket_transfer,
        ):
            response = services.update_admin_ticket(
                "KBC-000017",
                {
                    "actorUsername": "manager",
                    "assignedTeam": services.ASSIGNED_TEAM_SUPPORT_DESK,
                    "note": "Returning to support desk.",
                },
            )

        self.assertEqual(response, detail)
        notify_learning_plan_ticket_transfer.assert_not_called()
        update_params = cursor.execute.call_args_list[0].args[1]
        self.assertIsNone(update_params[2])
        persisted_metadata = json.loads(update_params[5])
        self.assertNotIn("pending_learning_plan_transfer_notification", persisted_metadata)


class AdminTicketPermanentDeleteTests(SimpleTestCase):
    def build_mock_connection(self):
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context
        return mock_connection, cursor

    def test_delete_admin_ticket_permanently_requires_superadmin(self):
        actor_row = {
            "id": 9,
            "username": "omar",
            "full_name": "Omar Helmy",
            "role": "admin",
        }

        with patch.object(services, "fetch_actor_by_username", return_value=actor_row):
            with self.assertRaises(services.ApiError) as raised_error:
                services.delete_admin_ticket_permanently(
                    "KBC-000017",
                    {"actorUsername": "omar", "confirmTicketId": "KBC-000017"},
                )

        self.assertEqual(raised_error.exception.status_code, 403)
        self.assertEqual(raised_error.exception.message, "Only superadmins can permanently delete archived tickets.")

    def test_delete_admin_ticket_permanently_requires_archived_ticket(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "is_archived": False,
            "conversation_id": None,
            "conversation_metadata": {},
        }
        actor_row = {
            "id": 1,
            "username": "super",
            "full_name": "Super Admin",
            "role": "superadmin",
        }

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services, "run_query_one", return_value=ticket),
        ):
            with self.assertRaises(services.ApiError) as raised_error:
                services.delete_admin_ticket_permanently(
                    "KBC-000017",
                    {"actorUsername": "super", "confirmTicketId": "KBC-000017"},
                )

        self.assertEqual(raised_error.exception.status_code, 409)
        self.assertEqual(raised_error.exception.message, "Archive this ticket before deleting it permanently.")

    def test_delete_admin_ticket_permanently_deletes_orphaned_conversation_and_files(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "is_archived": True,
            "conversation_id": 42,
            "conversation_metadata": {
                "chat_public_id": "CHAT-000042",
                "latest_ticket_public_id": "KBC-000017",
            },
        }
        actor_row = {
            "id": 1,
            "username": "super",
            "full_name": "Super Admin",
            "role": "superadmin",
        }
        mock_connection, cursor = self.build_mock_connection()

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "run_query", return_value=[]),
            patch.object(services, "list_ticket_attachment_storage_keys", return_value=["attachments/file-1.pdf", "attachments/file-2.pdf"]),
            patch.object(services, "delete_support_attachment_file") as delete_attachment_file,
            patch.object(services, "connection", mock_connection),
        ):
            response = services.delete_admin_ticket_permanently(
                "KBC-000017",
                {"actorUsername": "super", "confirmTicketId": "KBC-000017"},
            )

        self.assertEqual(response["ticketId"], "KBC-000017")
        self.assertTrue(response["conversationDeleted"])
        self.assertEqual(
            [call.args[1][0] for call in cursor.execute.call_args_list],
            [17, 42],
        )
        executed_sql = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertIn("DELETE FROM tickets", executed_sql[0])
        self.assertIn("DELETE FROM conversations", executed_sql[1])
        self.assertEqual(
            [call.args[0] for call in delete_attachment_file.call_args_list],
            ["attachments/file-1.pdf", "attachments/file-2.pdf"],
        )

    def test_delete_admin_ticket_permanently_updates_shared_conversation_metadata(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "is_archived": True,
            "conversation_id": 42,
            "conversation_metadata": {
                "chat_public_id": "KBC-000017",
                "latest_ticket_public_id": "KBC-000017",
                "parent_ticket_public_id": "KBC-000017",
            },
        }
        actor_row = {
            "id": 1,
            "username": "super",
            "full_name": "Super Admin",
            "role": "superadmin",
        }
        remaining_tickets = [
            {
                "id": 16,
                "public_id": "KBC-000016",
                "metadata": {},
                "created_at": datetime(2026, 6, 13, 10, 0, tzinfo=timezone.utc),
            }
        ]
        mock_connection, cursor = self.build_mock_connection()

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "run_query", return_value=remaining_tickets),
            patch.object(services, "list_ticket_attachment_storage_keys", return_value=[]),
            patch.object(services, "delete_support_attachment_file"),
            patch.object(services, "connection", mock_connection),
        ):
            response = services.delete_admin_ticket_permanently(
                "KBC-000017",
                {"actorUsername": "super", "confirmTicketId": "KBC-000017"},
            )

        self.assertEqual(response["ticketId"], "KBC-000017")
        self.assertFalse(response["conversationDeleted"])
        self.assertEqual(len(cursor.execute.call_args_list), 2)
        update_params = cursor.execute.call_args_list[1].args[1]
        persisted_metadata = json.loads(update_params[0])
        self.assertEqual(update_params[1], 42)
        self.assertEqual(persisted_metadata["latest_ticket_public_id"], "KBC-000016")
        self.assertEqual(persisted_metadata["parent_ticket_public_id"], "KBC-000016")
        self.assertEqual(persisted_metadata["chat_public_id"], "CHAT-000042")


class AdminNotificationLogTests(SimpleTestCase):
    def test_list_admin_notifications_returns_notifications_for_current_admin(self):
        history_payload = {
            "fromAgentId": 5,
            "fromAgentName": "Omar",
            "fromAgentUsername": "omar",
            "toAgentId": 9,
            "toAgentName": "Ahmed Hamamo",
            "toAgentUsername": "ahmedhamamo",
            "reason": "Need another admin on this case",
            "requestedAt": "2026-05-16T10:00:00+00:00",
        }
        notification_row = {
            "id": 41,
            "event_type": "transfer_requested",
            "actor_type": "admin",
            "actor_label": "Omar",
            "payload": history_payload,
            "created_at": datetime(2026, 5, 16, 10, 0, tzinfo=timezone.utc),
            "public_id": "KBC-000017",
            "status": "Pending",
            "status_reason": "Escalation",
            "metadata": {
                "requester_role": "coach",
                "pending_transfer_request": history_payload,
            },
            "conversation_id": 44,
            "conversation_metadata": {"chat_public_id": "CHAT-000044"},
            "learner_name": "Lina",
            "learner_email": "lina@example.com",
        }

        with (
            patch.object(services, "require_agent_session_actor", return_value={"id": 9, "username": "ahmedhamamo", "role": "admin"}),
            patch.object(services, "run_query", return_value=[notification_row]) as run_query,
        ):
            response = services.list_admin_notifications("ahmedhamamo", "instance-1", limit="12")

        self.assertEqual(run_query.call_args.args[1], ["9", "9", "9", "9", "9", "9", "9", 12])
        self.assertEqual(len(response["notifications"]), 1)
        self.assertEqual(
            response["notifications"][0],
            {
                "id": 41,
                "eventType": "transfer_requested",
                "actorType": "admin",
                "actorLabel": "Omar",
                "payload": history_payload,
                "createdAt": datetime(2026, 5, 16, 10, 0, tzinfo=timezone.utc),
                "ticketId": "KBC-000017",
                "chatId": "CHAT-000044",
                "learnerName": "Lina",
                "requesterName": "Lina",
                "email": "lina@example.com",
                "requesterRole": "coach",
                "status": "Pending",
                "statusReason": "Escalation",
                "isCurrent": True,
            },
        )

    def test_serialize_admin_notification_log_item_marks_acknowledged_transfer_decision_as_not_current(self):
        history_payload = {
            "fromAgentId": 5,
            "fromAgentName": "Omar",
            "fromAgentUsername": "omar",
            "toAgentId": 9,
            "toAgentName": "Ahmed Hamamo",
            "toAgentUsername": "ahmedhamamo",
            "reason": "Please take over this ticket",
            "requestedAt": "2026-05-16T09:00:00+00:00",
        }
        notification = services.serialize_admin_notification_log_item(
            {
                "id": 52,
                "event_type": "transfer_request_accepted",
                "actor_type": "admin",
                "actor_label": "Ahmed Hamamo",
                "payload": history_payload,
                "created_at": datetime(2026, 5, 16, 9, 30, tzinfo=timezone.utc),
                "public_id": "KBC-000052",
                "status": "Pending",
                "status_reason": "Escalation",
                "metadata": {
                    "requester_role": "user",
                    "latest_transfer_decision": {
                        **history_payload,
                        "status": "accepted",
                        "decidedAt": "2026-05-16T09:30:00+00:00",
                        "decidedById": 9,
                        "decidedByName": "Ahmed Hamamo",
                        "decidedByUsername": "ahmedhamamo",
                        "requesterAcknowledged": True,
                    },
                },
                "conversation_id": 52,
                "conversation_metadata": {"chat_public_id": "CHAT-000052"},
                "learner_name": "Mona",
                "learner_email": "mona@example.com",
            }
        )

        self.assertFalse(notification["isCurrent"])
        self.assertEqual(notification["eventType"], "transfer_request_accepted")
        self.assertEqual(notification["chatId"], "CHAT-000052")
        self.assertEqual(notification["requesterName"], "Mona")

    def test_serialize_admin_notification_log_item_marks_current_teams_call_notification_as_current(self):
        history_payload = {
            "toAgentId": 9,
            "toAgentName": "Ahmed Hamamo",
            "toAgentUsername": "ahmedhamamo",
            "requesterName": "Coach One",
            "requesterEmail": "coach@example.com",
            "requesterRole": "coach",
            "note": "Coach requested a direct Microsoft Teams support call from the support portal.",
            "targetLabel": "Ahmed Hamamo",
            "ticketId": "KBC-000088",
            "requestedAt": "2026-05-16T11:00:00+00:00",
        }
        notification = services.serialize_admin_notification_log_item(
            {
                "id": 88,
                "event_type": "teams_call_requested",
                "actor_type": "coach",
                "actor_label": "coach@example.com",
                "payload": history_payload,
                "created_at": datetime(2026, 5, 16, 11, 0, tzinfo=timezone.utc),
                "public_id": "KBC-000088",
                "status": "Open",
                "status_reason": "",
                "metadata": {
                    "requester_role": "coach",
                    "pending_teams_call_notification": history_payload,
                },
                "conversation_id": 88,
                "conversation_metadata": {"chat_public_id": "CHAT-000088"},
                "learner_name": "Coach One",
                "learner_email": "coach@example.com",
            }
        )

        self.assertTrue(notification["isCurrent"])
        self.assertEqual(notification["eventType"], "teams_call_requested")
        self.assertEqual(notification["chatId"], "CHAT-000088")

    def test_serialize_admin_notification_log_item_marks_acknowledged_escalation_closure_as_not_current(self):
        history_payload = {
            "ticketId": "KBC-000071",
            "fromAgentId": 5,
            "fromAgentName": "Omar",
            "fromAgentUsername": "omar",
            "toAgentId": 9,
            "toAgentName": "Ahmed Hamamo",
            "toAgentUsername": "ahmedhamamo",
            "closedById": 9,
            "closedByName": "Ahmed Hamamo",
            "closedByUsername": "ahmedhamamo",
            "note": "Please review this chat urgently",
            "requestedAt": "2026-05-16T09:00:00+00:00",
            "closedAt": "2026-05-16T09:45:00+00:00",
            "closedStatusReason": "Closed via Agent",
        }
        notification = services.serialize_admin_notification_log_item(
            {
                "id": 71,
                "event_type": "escalation_closed",
                "actor_type": "admin",
                "actor_label": "Ahmed Hamamo",
                "payload": history_payload,
                "created_at": datetime(2026, 5, 16, 9, 45, tzinfo=timezone.utc),
                "public_id": "KBC-000071",
                "status": "Closed",
                "status_reason": "Closed via Agent",
                "metadata": {
                    "requester_role": "coach",
                    "latest_escalation_closure": {
                        **history_payload,
                        "requesterAcknowledged": True,
                    },
                },
                "conversation_id": 71,
                "conversation_metadata": {"chat_public_id": "CHAT-000071"},
                "learner_name": "Lina",
                "learner_email": "lina@example.com",
            }
        )

        self.assertFalse(notification["isCurrent"])
        self.assertEqual(notification["eventType"], "escalation_closed")
        self.assertEqual(notification["chatId"], "CHAT-000071")


class AgentQueueTests(SimpleTestCase):
    def test_process_ticket_chat_inactivity_sends_reminder_after_two_minutes(self):
        reference_time = datetime(2026, 5, 16, 12, 5, tzinfo=timezone.utc)
        waiting_since = reference_time - timedelta(minutes=3)
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "status": "Open",
            "status_reason": "",
            "sla_status": "Pending Review",
            "metadata": {},
            "created_at": reference_time - timedelta(minutes=10),
            "conversation_id": 44,
            "conversation_status": "open",
            "conversation_metadata": {"is_active_conversation": True},
            "last_message_at": waiting_since,
            "learner_name": "Ali Test",
            "last_message_role": "assistant",
            "last_message_content": "Please confirm your issue.",
            "last_message_metadata": {"original_sender": "bot"},
            "last_message_created_at": waiting_since,
        }

        with (
            patch.object(services, "run_query", return_value=[]),
            patch.object(services, "apply_ticket_chat_history_sync") as apply_ticket_chat_history_sync,
        ):
            action = services.process_ticket_chat_inactivity(ticket, reference_time=reference_time)

        self.assertEqual(action, "reminded")
        sync_kwargs = apply_ticket_chat_history_sync.call_args.kwargs
        self.assertEqual(sync_kwargs["status"], "Open")
        self.assertEqual(
            sync_kwargs["messages"][-1]["text"],
            services.build_chat_inactivity_reminder_message("Ali Test"),
        )
        self.assertEqual(
            sync_kwargs["conversation_metadata_patch"][services.INACTIVITY_WAITING_SINCE_METADATA_KEY],
            waiting_since.isoformat(),
        )
        self.assertEqual(
            sync_kwargs["conversation_metadata_patch"][services.INACTIVITY_REMINDER_SENT_AT_METADATA_KEY],
            reference_time.isoformat(),
        )

    def test_process_ticket_chat_inactivity_closes_after_reminder_grace_period(self):
        reference_time = datetime(2026, 5, 16, 12, 8, tzinfo=timezone.utc)
        reminder_sent_at = reference_time - timedelta(minutes=4)
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "status": "Open",
            "status_reason": "",
            "sla_status": "Pending Review",
            "metadata": {},
            "created_at": reference_time - timedelta(minutes=12),
            "conversation_id": 44,
            "conversation_status": "open",
            "conversation_metadata": {
                "is_active_conversation": True,
                services.INACTIVITY_WAITING_SINCE_METADATA_KEY: (reference_time - timedelta(minutes=6)).isoformat(),
                services.INACTIVITY_REMINDER_SENT_AT_METADATA_KEY: reminder_sent_at.isoformat(),
            },
            "last_message_at": reminder_sent_at,
            "learner_name": "Ali Test",
            "last_message_role": "assistant",
            "last_message_content": services.build_chat_inactivity_reminder_message("Ali Test"),
            "last_message_metadata": {"original_sender": "bot"},
            "last_message_created_at": reminder_sent_at,
        }

        with (
            patch.object(services, "run_query", return_value=[]),
            patch.object(services, "apply_ticket_chat_history_sync") as apply_ticket_chat_history_sync,
        ):
            action = services.process_ticket_chat_inactivity(ticket, reference_time=reference_time)

        self.assertEqual(action, "closed")
        sync_kwargs = apply_ticket_chat_history_sync.call_args.kwargs
        self.assertEqual(sync_kwargs["status"], "Closed")
        self.assertEqual(sync_kwargs["status_reason"], services.STATUS_REASON_CLOSED_DUE_TO_INACTIVITY)
        self.assertEqual(
            sync_kwargs["messages"][-1]["text"],
            services.build_chat_inactivity_closed_message(),
        )

    def test_process_ticket_chat_inactivity_close_guard_closes_after_total_timeout_without_prior_reminder(self):
        reference_time = datetime(2026, 5, 16, 12, 10, tzinfo=timezone.utc)
        waiting_since = reference_time - timedelta(minutes=6)
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "status": "Open",
            "status_reason": "",
            "sla_status": "Pending Review",
            "metadata": {},
            "created_at": reference_time - timedelta(minutes=15),
            "conversation_id": 44,
            "conversation_status": "open",
            "conversation_metadata": {
                "is_active_conversation": True,
                services.INACTIVITY_WAITING_SINCE_METADATA_KEY: waiting_since.isoformat(),
            },
            "last_message_at": waiting_since,
            "learner_name": "Ali Test",
            "last_message_role": "assistant",
            "last_message_content": "Please confirm your issue.",
            "last_message_metadata": {"original_sender": "bot"},
            "last_message_created_at": waiting_since,
        }

        with (
            patch.object(services, "run_query", return_value=[]),
            patch.object(services, "apply_ticket_chat_history_sync") as apply_ticket_chat_history_sync,
        ):
            action = services.process_ticket_chat_inactivity(
                ticket,
                reference_time=reference_time,
                allow_reminder=False,
            )

        self.assertEqual(action, "closed")
        self.assertEqual(apply_ticket_chat_history_sync.call_args.kwargs["status"], "Closed")

    def test_is_agent_session_active_respects_timeout(self):
        comparison_now = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)

        active_metadata = {
            "session_active": True,
            "session_last_seen_at": (comparison_now - timedelta(minutes=59)).isoformat(),
        }
        stale_metadata = {
            "session_active": True,
            "session_last_seen_at": (comparison_now - timedelta(minutes=61)).isoformat(),
        }

        self.assertTrue(services.is_agent_session_active(active_metadata, comparison_now))
        self.assertFalse(services.is_agent_session_active(stale_metadata, comparison_now))

    def test_select_next_live_chat_agent_prefers_oldest_queue_turn(self):
        comparison_now = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)
        agents = [
            {
                "id": 1,
                "username": "agent-one",
                "metadata": {
                    "session_active": True,
                    "session_last_seen_at": comparison_now.isoformat(),
                    "console_status": "Available",
                    "queue_joined_at": datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc).isoformat(),
                },
            },
            {
                "id": 2,
                "username": "agent-two",
                "metadata": {
                    "session_active": True,
                    "session_last_seen_at": comparison_now.isoformat(),
                    "console_status": "Available",
                    "queue_joined_at": datetime(2026, 5, 8, 9, 30, tzinfo=timezone.utc).isoformat(),
                    "last_live_chat_assigned_at": datetime(2026, 5, 8, 11, 45, tzinfo=timezone.utc).isoformat(),
                },
            },
        ]

        selected_agent = services.select_next_live_chat_agent(agents, comparison_now)

        self.assertIsNotNone(selected_agent)
        self.assertEqual(selected_agent["id"], 1)

    def test_serialize_agent_marks_stale_available_session_as_off(self):
        with patch.object(services, "is_agent_session_active", return_value=False):
            agent = services.serialize_agent(
                {
                    "id": 9,
                    "username": "omar1",
                    "full_name": "Omar One",
                    "email": None,
                    "role": "admin",
                    "metadata": {
                        "console_status": "Available",
                        "session_active": True,
                        "session_last_seen_at": datetime(2026, 5, 8, 11, 50, tzinfo=timezone.utc).isoformat(),
                    },
                }
            )

        self.assertFalse(agent["sessionActive"])
        self.assertEqual(agent["consoleStatus"], "Off")

    def test_serialize_agent_for_requester_scope_hides_console_session(self):
        with patch.object(services, "is_agent_session_active", return_value=True):
            agent = services.serialize_agent(
                {
                    "id": 12,
                    "username": "coach1",
                    "full_name": "Coach One",
                    "email": "coach@example.com",
                    "account_scope": "requester",
                    "role": "coach",
                    "metadata": {
                        "console_status": "Available",
                        "session_active": True,
                        "session_last_seen_at": datetime(2026, 5, 8, 11, 50, tzinfo=timezone.utc).isoformat(),
                    },
                }
            )

        self.assertEqual(agent["accountScope"], "requester")
        self.assertFalse(agent["sessionActive"])
        self.assertEqual(agent["consoleStatus"], "Off")

    def test_serialize_agent_marks_open_assigned_chat_owner_as_busy(self):
        comparison_now = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)
        with patch.object(services, "is_agent_session_active", return_value=True):
            agent = services.serialize_agent(
                {
                    "id": 9,
                    "username": "omar1",
                    "full_name": "Omar One",
                    "email": None,
                    "role": "admin",
                    "metadata": {
                        "console_status": "Available",
                        "session_active": True,
                        "session_last_seen_at": comparison_now.isoformat(),
                    },
                },
                open_assigned_chat_agent_ids={9},
            )

        self.assertTrue(agent["sessionActive"])
        self.assertEqual(agent["consoleStatus"], "Busy")
        self.assertEqual(agent["selectedConsoleStatus"], "Available")

    def test_serialize_agent_normalizes_legacy_busy_status_without_open_chat(self):
        comparison_now = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)
        with patch.object(services, "is_agent_session_active", return_value=True):
            agent = services.serialize_agent(
                {
                    "id": 10,
                    "username": "legacybusy",
                    "full_name": "Legacy Busy",
                    "email": None,
                    "role": "admin",
                    "metadata": {
                        "console_status": "Busy",
                        "session_active": True,
                        "session_last_seen_at": comparison_now.isoformat(),
                    },
                },
            )

        self.assertTrue(agent["sessionActive"])
        self.assertEqual(agent["consoleStatus"], "Available")
        self.assertEqual(agent["selectedConsoleStatus"], "Available")

    def test_select_next_live_chat_agent_prefers_available_agents_before_busy_agents(self):
        comparison_now = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)
        agents = [
            {
                "id": 1,
                "username": "busy-agent",
                "metadata": {
                    "session_active": True,
                    "session_last_seen_at": comparison_now.isoformat(),
                    "console_status": "Available",
                    "queue_joined_at": datetime(2026, 5, 8, 9, 0, tzinfo=timezone.utc).isoformat(),
                },
            },
            {
                "id": 2,
                "username": "available-agent",
                "metadata": {
                    "session_active": True,
                    "session_last_seen_at": comparison_now.isoformat(),
                    "console_status": "Available",
                    "queue_joined_at": datetime(2026, 5, 8, 11, 0, tzinfo=timezone.utc).isoformat(),
                },
            },
        ]

        selected_agent = services.select_next_live_chat_agent(agents, comparison_now, {1})

        self.assertIsNotNone(selected_agent)
        self.assertEqual(selected_agent["id"], 2)

    def test_select_next_live_chat_agent_returns_none_when_only_busy_agents_exist(self):
        comparison_now = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)
        agents = [
            {
                "id": 1,
                "username": "busy-agent",
                "metadata": {
                    "session_active": True,
                    "session_last_seen_at": comparison_now.isoformat(),
                    "console_status": "Available",
                    "queue_joined_at": datetime(2026, 5, 8, 9, 0, tzinfo=timezone.utc).isoformat(),
                },
            },
        ]

        selected_agent = services.select_next_live_chat_agent(agents, comparison_now, {1})

        self.assertIsNone(selected_agent)

    def test_assign_waiting_live_chat_tickets_keeps_active_assigned_chat_with_current_agent(self):
        comparison_now = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)
        busy_agent_metadata = {
            "session_active": True,
            "session_last_seen_at": comparison_now.isoformat(),
            "console_status": "Available",
            "queue_joined_at": datetime(2026, 5, 8, 9, 0, tzinfo=timezone.utc).isoformat(),
        }
        available_agent_metadata = {
            "session_active": True,
            "session_last_seen_at": comparison_now.isoformat(),
            "console_status": "Available",
            "queue_joined_at": datetime(2026, 5, 8, 11, 0, tzinfo=timezone.utc).isoformat(),
        }
        agents = [
            {"id": 1, "username": "busy-agent", "full_name": "Busy Agent", "metadata": busy_agent_metadata},
            {"id": 2, "username": "available-agent", "full_name": "Available Agent", "metadata": available_agent_metadata},
        ]
        ticket = {
            "id": 55,
            "public_id": "KBC-000055",
            "status": "Open",
            "metadata": {"live_chat_requested": True},
            "created_at": comparison_now - timedelta(minutes=5),
            "updated_at": comparison_now - timedelta(minutes=1),
            "conversation_id": 81,
            "assigned_agent_id": 1,
            "assigned_team": "Support Desk",
            "conversation_status": "open",
            "conversation_metadata": {
                "is_active_conversation": True,
                "live_chat_requested": True,
                "latest_ticket_public_id": "KBC-000055",
            },
            "assigned_agent_metadata": busy_agent_metadata,
        }

        with (
            patch.object(services, "run_query", side_effect=[agents, [ticket]]),
            patch.object(services, "assign_ticket_to_agent", return_value=True) as assign_ticket_to_agent,
            patch.object(services, "persist_agent_metadata") as persist_agent_metadata,
        ):
            assigned_ticket_ids = services.assign_waiting_live_chat_tickets(comparison_now)

        self.assertEqual(assigned_ticket_ids, [])
        assign_ticket_to_agent.assert_not_called()
        persist_agent_metadata.assert_not_called()

    def test_assign_waiting_live_chat_tickets_reassigns_when_assigned_agent_is_offline(self):
        comparison_now = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)
        offline_agent_metadata = {
            "session_active": False,
            "session_last_seen_at": (comparison_now - timedelta(minutes=10)).isoformat(),
            "console_status": "Off",
            "queue_joined_at": datetime(2026, 5, 8, 9, 0, tzinfo=timezone.utc).isoformat(),
        }
        available_agent_metadata = {
            "session_active": True,
            "session_last_seen_at": comparison_now.isoformat(),
            "console_status": "Available",
            "queue_joined_at": datetime(2026, 5, 8, 11, 0, tzinfo=timezone.utc).isoformat(),
        }
        agents = [
            {"id": 2, "username": "available-agent", "full_name": "Available Agent", "metadata": available_agent_metadata},
        ]
        ticket = {
            "id": 55,
            "public_id": "KBC-000055",
            "status": "Open",
            "metadata": {"live_chat_requested": True},
            "created_at": comparison_now - timedelta(minutes=5),
            "updated_at": comparison_now - timedelta(minutes=1),
            "conversation_id": 81,
            "assigned_agent_id": 1,
            "assigned_team": "Support Desk",
            "conversation_status": "open",
            "conversation_metadata": {
                "is_active_conversation": True,
                "live_chat_requested": True,
                "latest_ticket_public_id": "KBC-000055",
            },
            "assigned_agent_metadata": offline_agent_metadata,
        }

        with (
            patch.object(services, "run_query", side_effect=[agents, [ticket]]),
            patch.object(services, "assign_ticket_to_agent", return_value=True) as assign_ticket_to_agent,
            patch.object(services, "persist_agent_metadata") as persist_agent_metadata,
        ):
            assigned_ticket_ids = services.assign_waiting_live_chat_tickets(comparison_now)

        self.assertEqual(assigned_ticket_ids, [55])
        assign_ticket_to_agent.assert_called_once_with(ticket, agents[0], comparison_now)
        persisted_agent_metadata = persist_agent_metadata.call_args.args[1]
        self.assertEqual(persisted_agent_metadata["console_status"], "Available")
        self.assertEqual(persisted_agent_metadata["last_live_chat_assigned_at"], comparison_now.isoformat())

    def test_assign_waiting_live_chat_tickets_keeps_waiting_when_only_busy_agents_exist(self):
        comparison_now = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)
        busy_agent = {
            "id": 1,
            "username": "busy-agent",
            "full_name": "Busy Agent",
            "metadata": {
                "session_active": True,
                "session_last_seen_at": comparison_now.isoformat(),
                "console_status": "Available",
                "queue_joined_at": datetime(2026, 5, 8, 9, 0, tzinfo=timezone.utc).isoformat(),
            },
        }
        active_ticket = {
            "id": 54,
            "public_id": "KBC-000054",
            "status": "Open",
            "metadata": {"live_chat_requested": True},
            "created_at": comparison_now - timedelta(minutes=10),
            "updated_at": comparison_now - timedelta(minutes=2),
            "conversation_id": 80,
            "assigned_agent_id": 1,
            "assigned_team": "Support Desk",
            "conversation_status": "open",
            "conversation_metadata": {
                "is_active_conversation": True,
                "live_chat_requested": True,
                "latest_ticket_public_id": "KBC-000054",
            },
            "assigned_agent_metadata": busy_agent["metadata"],
        }
        waiting_ticket = {
            "id": 56,
            "public_id": "KBC-000056",
            "status": "Open",
            "metadata": {"live_chat_requested": True},
            "created_at": comparison_now - timedelta(minutes=5),
            "updated_at": comparison_now - timedelta(minutes=1),
            "conversation_id": 82,
            "assigned_agent_id": None,
            "assigned_team": "Unassigned",
            "conversation_status": "open",
            "conversation_metadata": {
                "is_active_conversation": True,
                "live_chat_requested": True,
                "latest_ticket_public_id": "KBC-000056",
            },
            "assigned_agent_metadata": None,
        }

        with (
            patch.object(services, "run_query", side_effect=[[busy_agent], [active_ticket, waiting_ticket]]),
            patch.object(services, "assign_ticket_to_agent", return_value=True) as assign_ticket_to_agent,
            patch.object(services, "persist_agent_metadata") as persist_agent_metadata,
        ):
            assigned_ticket_ids = services.assign_waiting_live_chat_tickets(comparison_now)

        self.assertEqual(assigned_ticket_ids, [])
        assign_ticket_to_agent.assert_not_called()
        persist_agent_metadata.assert_not_called()

    def test_request_live_chat_queues_operations_alert_when_no_agent_available(self):
        ticket = {
            "id": 56,
            "public_id": "KBC-000056",
            "status": "Open",
            "status_reason": "",
            "category": "Technical",
            "technical_subcategory": "Teams",
            "priority": "High",
            "metadata": {},
            "created_at": datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc),
            "assigned_team": "Unassigned",
            "conversation_id": 82,
            "assigned_agent_id": None,
            "conversation_status": "open",
            "learner_name": "Omar Badr",
            "learner_email": "omar@example.com",
            "learner_source": "kbc_users_data",
            "learner_metadata": {},
        }
        refreshed_ticket = {
            "public_id": "KBC-000056",
            "assigned_agent_id": None,
            "assigned_agent_name": None,
            "assigned_agent_username": None,
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services, "sync_open_ticket_inactivity"),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", side_effect=[ticket, refreshed_ticket]),
            patch.object(services, "mark_conversation_as_active"),
            patch.object(services, "assign_waiting_live_chat_tickets", return_value=[]),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event"),
            patch.object(services, "queue_live_agent_unavailable_notification") as queue_unavailable,
        ):
            response = services.request_live_chat("KBC-000056")

        self.assertTrue(response["ok"])
        self.assertIsNone(response["ticket"]["assignedAgentId"])
        queue_unavailable.assert_called_once()
        self.assertEqual(queue_unavailable.call_args.args[0]["public_id"], "KBC-000056")

    def test_assign_waiting_live_chat_tickets_assigns_one_ticket_per_available_agent(self):
        comparison_now = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)
        available_agent = {
            "id": 2,
            "username": "available-agent",
            "full_name": "Available Agent",
            "metadata": {
                "session_active": True,
                "session_last_seen_at": comparison_now.isoformat(),
                "console_status": "Available",
                "queue_joined_at": datetime(2026, 5, 8, 11, 0, tzinfo=timezone.utc).isoformat(),
            },
        }
        first_waiting_ticket = {
            "id": 56,
            "public_id": "KBC-000056",
            "status": "Open",
            "metadata": {"live_chat_requested": True},
            "created_at": comparison_now - timedelta(minutes=6),
            "updated_at": comparison_now - timedelta(minutes=2),
            "conversation_id": 82,
            "assigned_agent_id": None,
            "assigned_team": "Unassigned",
            "conversation_status": "open",
            "conversation_metadata": {
                "is_active_conversation": True,
                "live_chat_requested": True,
                "latest_ticket_public_id": "KBC-000056",
            },
            "assigned_agent_metadata": None,
        }
        second_waiting_ticket = {
            "id": 57,
            "public_id": "KBC-000057",
            "status": "Open",
            "metadata": {"live_chat_requested": True},
            "created_at": comparison_now - timedelta(minutes=5),
            "updated_at": comparison_now - timedelta(minutes=1),
            "conversation_id": 83,
            "assigned_agent_id": None,
            "assigned_team": "Unassigned",
            "conversation_status": "open",
            "conversation_metadata": {
                "is_active_conversation": True,
                "live_chat_requested": True,
                "latest_ticket_public_id": "KBC-000057",
            },
            "assigned_agent_metadata": None,
        }

        with (
            patch.object(services, "run_query", side_effect=[[available_agent], [first_waiting_ticket, second_waiting_ticket]]),
            patch.object(services, "assign_ticket_to_agent", return_value=True) as assign_ticket_to_agent,
            patch.object(services, "persist_agent_metadata") as persist_agent_metadata,
        ):
            assigned_ticket_ids = services.assign_waiting_live_chat_tickets(comparison_now)

        self.assertEqual(assigned_ticket_ids, [56])
        assign_ticket_to_agent.assert_called_once_with(first_waiting_ticket, available_agent, comparison_now)
        persist_agent_metadata.assert_called_once()

    def test_serialize_ticket_summary_exposes_queue_timestamps(self):
        ticket_row = {
            "public_id": "KBC-000321",
            "learner_name": "Mina Test",
            "learner_email": "mina@example.com",
            "learner_phone": "01010000000",
            "category": "Technical",
            "technical_subcategory": "Teams",
            "inquiry": "Need help joining the class",
            "status": "Open",
            "status_reason": "",
            "assigned_agent_id": 8,
            "assigned_agent_name": "Fatma Queue",
            "assigned_agent_username": "fatma",
            "assigned_team": "Support Desk",
            "conversation_id": 44,
            "conversation_status": "open",
            "conversation_metadata": {
                "is_active_conversation": True,
                "live_chat_requested": True,
                "queue_assigned_at": "2026-05-08T11:05:00+00:00",
            },
            "last_message_at": None,
            "chat_duration_minutes": 7,
            "sla_status": "Pending Review",
            "evidence_count": 0,
            "created_at": datetime(2026, 5, 8, 11, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 5, 8, 11, 6, tzinfo=timezone.utc),
            "metadata": {
                "live_chat_requested": True,
                "live_chat_requested_at": "2026-05-08T11:01:00+00:00",
            },
        }

        summary = services.serialize_ticket_summary(ticket_row)

        self.assertEqual(summary["liveChatRequestedAt"], "2026-05-08T11:01:00+00:00")
        self.assertEqual(summary["queueAssignedAt"], "2026-05-08T11:05:00+00:00")
        self.assertEqual(summary["chatDurationMinutes"], 7)

    def test_serialize_ticket_summary_hides_parent_ticket_from_active_chat_queue_after_follow_up(self):
        ticket_row = {
            "public_id": "KBC-000321",
            "learner_name": "Mina Test",
            "learner_email": "mina@example.com",
            "learner_phone": "01010000000",
            "category": "Technical",
            "technical_subcategory": "Teams",
            "inquiry": "Need help joining the class",
            "status": "Pending",
            "status_reason": "Escalation",
            "assigned_agent_id": 8,
            "assigned_agent_name": "Fatma Queue",
            "assigned_agent_username": "fatma",
            "assigned_team": "Support Desk",
            "conversation_id": 44,
            "conversation_status": "open",
            "conversation_metadata": {
                "is_active_conversation": True,
                "live_chat_requested": True,
                "latest_ticket_public_id": "KBC-000654",
            },
            "last_message_at": None,
            "chat_duration_minutes": 7,
            "sla_status": "Pending Review",
            "evidence_count": 0,
            "created_at": datetime(2026, 5, 8, 11, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 5, 8, 11, 6, tzinfo=timezone.utc),
            "metadata": {
                "live_chat_requested": True,
                "live_chat_requested_at": "2026-05-08T11:01:00+00:00",
            },
        }

        summary = services.serialize_ticket_summary(ticket_row)

        self.assertFalse(summary["chatIsActive"])

    def test_calculate_conversation_chat_duration_minutes_prefers_assignment_time(self):
        duration_minutes = services.calculate_conversation_chat_duration_minutes(
            {"live_chat_requested_at": "2026-05-08T11:01:00+00:00"},
            {"queue_assigned_at": "2026-05-08T11:05:00+00:00"},
            conversation_status="open",
            reference_time=datetime(2026, 5, 8, 11, 15, tzinfo=timezone.utc),
        )

        self.assertEqual(duration_minutes, 10)

    def test_persist_conversation_chat_duration_updates_conversation_record(self):
        row = {
            "metadata": {"live_chat_requested_at": "2026-05-08T11:01:00+00:00"},
            "created_at": datetime(2026, 5, 8, 11, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 5, 8, 11, 16, tzinfo=timezone.utc),
            "closed_at": datetime(2026, 5, 8, 11, 16, tzinfo=timezone.utc),
            "conversation_status": "closed",
            "conversation_metadata": {"queue_assigned_at": "2026-05-08T11:05:00+00:00"},
            "last_message_at": datetime(2026, 5, 8, 11, 15, tzinfo=timezone.utc),
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context
        reference_time = datetime(2026, 5, 8, 11, 20, tzinfo=timezone.utc)

        with (
            patch.object(services, "run_query_one", return_value=row),
            patch.object(services, "connection", mock_connection),
        ):
            duration_minutes = services.persist_conversation_chat_duration(17, 44, reference_time=reference_time)

        self.assertEqual(duration_minutes, 10)
        update_params = cursor.execute.call_args.args[1]
        self.assertEqual(update_params[0], 10)
        self.assertEqual(update_params[2], 44)

    def test_persist_conversation_chat_duration_skips_open_conversation(self):
        row = {
            "metadata": {"live_chat_requested_at": "2026-05-08T11:01:00+00:00"},
            "created_at": datetime(2026, 5, 8, 11, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 5, 8, 11, 16, tzinfo=timezone.utc),
            "closed_at": None,
            "conversation_status": "open",
            "conversation_metadata": {"queue_assigned_at": "2026-05-08T11:05:00+00:00"},
            "last_message_at": datetime(2026, 5, 8, 11, 15, tzinfo=timezone.utc),
        }
        mock_connection = MagicMock()

        with (
            patch.object(services, "run_query_one", return_value=row),
            patch.object(services, "connection", mock_connection),
        ):
            duration_minutes = services.persist_conversation_chat_duration(17, 44)

        self.assertIsNone(duration_minutes)
        mock_connection.cursor.assert_not_called()

    def test_save_chat_history_rejects_reply_from_non_assigned_agent(self):
        ticket = {
            "id": 23,
            "public_id": "KBC-000023",
            "conversation_id": 88,
            "status": "Open",
            "status_reason": "",
            "assigned_team": "Support Desk",
            "sla_status": "Pending Review",
            "metadata": {},
            "created_at": datetime.now(timezone.utc),
            "assigned_agent_username": "fatma",
        }

        with (
            patch.object(services, "sync_open_ticket_inactivity"),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
        ):
            with self.assertRaises(services.ApiError) as error_context:
                services.save_chat_history(
                    "KBC-000023",
                    {
                        "status": "Open",
                        "actorUsername": "ahmed",
                        "messages": [{"sender": "agent", "text": "Hello", "timestamp": "2026-05-08T12:00:00Z"}],
                    },
                )

        self.assertEqual(error_context.exception.status_code, 403)
        self.assertEqual(error_context.exception.message, "Only the assigned agent can reply to this live chat.")

    def test_save_chat_history_clears_inactivity_tracking_after_user_reply(self):
        ticket = {
            "id": 23,
            "public_id": "KBC-000023",
            "conversation_id": 88,
            "status": "Open",
            "status_reason": "",
            "assigned_team": "Support Desk",
            "sla_status": "Pending Review",
            "metadata": {},
            "created_at": datetime.now(timezone.utc),
            "assigned_agent_username": "fatma",
        }

        with (
            patch.object(services, "sync_open_ticket_inactivity"),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "mark_conversation_as_active"),
            patch.object(
                services,
                "apply_ticket_chat_history_sync",
                return_value=([], "", "Pending Review", False),
            ) as apply_ticket_chat_history_sync,
        ):
            services.save_chat_history(
                "KBC-000023",
                {
                    "status": "Open",
                    "messages": [{"sender": "user", "text": "Hello again", "timestamp": "12:00 PM"}],
                },
            )

        self.assertEqual(
            apply_ticket_chat_history_sync.call_args.kwargs["conversation_metadata_patch"],
            {
                services.INACTIVITY_WAITING_SINCE_METADATA_KEY: None,
                services.INACTIVITY_REMINDER_SENT_AT_METADATA_KEY: None,
            },
        )

    def test_save_chat_history_forwards_uploaded_files_to_chat_sync(self):
        ticket = {
            "id": 23,
            "public_id": "KBC-000023",
            "conversation_id": 88,
            "status": "Open",
            "status_reason": "",
            "assigned_team": "Support Desk",
            "sla_status": "Pending Review",
            "metadata": {},
            "created_at": datetime.now(timezone.utc),
            "assigned_agent_username": "fatma",
        }
        uploaded_file = SimpleUploadedFile("chat-proof.png", b"png", content_type="image/png")

        with (
            patch.object(services, "sync_open_ticket_inactivity"),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "mark_conversation_as_active"),
            patch.object(
                services,
                "apply_ticket_chat_history_sync",
                return_value=([], "", "Pending Review", False),
            ) as apply_ticket_chat_history_sync,
        ):
            services.save_chat_history(
                "KBC-000023",
                {
                    "status": "Open",
                    "messages": [{"sender": "user", "text": "", "attachments": [{"clientAttachmentId": "att-1", "name": "chat-proof.png", "size": 3}]}],
                },
                uploaded_files=[uploaded_file],
            )

        self.assertEqual(apply_ticket_chat_history_sync.call_args.kwargs["ticket_public_id"], "KBC-000023")
        self.assertEqual(apply_ticket_chat_history_sync.call_args.kwargs["uploaded_files"], [uploaded_file])

    def test_save_chat_history_queues_quick_ticket_submitted_notification(self):
        ticket = {
            "id": 23,
            "public_id": "KBC-000023",
            "conversation_id": 88,
            "category": "Technical",
            "technical_subcategory": "Aptem",
            "priority": "Normal",
            "status": "Open",
            "status_reason": "",
            "assigned_team": "Unassigned",
            "sla_status": "Pending Review",
            "metadata": {},
            "created_at": datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc),
            "conversation_status": "open",
            "learner_name": "Omar Badr",
            "learner_email": "omar@example.com",
            "assigned_agent_username": None,
        }

        with (
            patch.object(services, "sync_open_ticket_inactivity"),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "mark_conversation_as_active"),
            patch.object(services, "clear_prepared_support_teams_call"),
            patch.object(
                services,
                "apply_ticket_chat_history_sync",
                return_value=([], services.STATUS_REASON_QUICK_TICKET, "On Track", False),
            ),
            patch.object(services, "queue_quick_ticket_submitted_notification") as queue_submitted,
            patch.object(services, "queue_quick_ticket_closed_notification") as queue_closed,
        ):
            services.save_chat_history(
                "KBC-000023",
                {
                    "status": "Pending",
                    "statusReason": services.STATUS_REASON_QUICK_TICKET,
                    "messages": [],
                },
            )

        queue_submitted.assert_called_once()
        self.assertEqual(queue_submitted.call_args.kwargs["status"], "Pending")
        self.assertEqual(queue_submitted.call_args.kwargs["status_reason"], services.STATUS_REASON_QUICK_TICKET)
        queue_closed.assert_not_called()

    def test_save_chat_history_does_not_duplicate_quick_ticket_submitted_notification(self):
        ticket = {
            "id": 23,
            "public_id": "KBC-000023",
            "conversation_id": 88,
            "category": "Technical",
            "technical_subcategory": "Aptem",
            "priority": "Normal",
            "status": "Open",
            "status_reason": "",
            "assigned_team": "Unassigned",
            "sla_status": "Pending Review",
            "metadata": {
                services.QUICK_TICKET_SUBMITTED_NOTIFICATION_SENT_AT_METADATA_KEY: "2026-05-08T10:05:00+00:00",
            },
            "created_at": datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc),
            "conversation_status": "open",
            "learner_name": "Omar Badr",
            "learner_email": "omar@example.com",
            "assigned_agent_username": None,
        }

        with (
            patch.object(services, "sync_open_ticket_inactivity"),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "mark_conversation_as_active"),
            patch.object(services, "clear_prepared_support_teams_call"),
            patch.object(
                services,
                "apply_ticket_chat_history_sync",
                return_value=([], services.STATUS_REASON_QUICK_TICKET, "On Track", False),
            ),
            patch.object(services, "queue_quick_ticket_submitted_notification") as queue_submitted,
            patch.object(services, "queue_quick_ticket_closed_notification") as queue_closed,
        ):
            services.save_chat_history(
                "KBC-000023",
                {
                    "status": "Pending",
                    "statusReason": services.STATUS_REASON_QUICK_TICKET,
                    "messages": [],
                },
            )

        queue_submitted.assert_not_called()
        queue_closed.assert_not_called()

    def test_save_chat_history_queues_quick_ticket_closed_notification(self):
        ticket = {
            "id": 23,
            "public_id": "KBC-000023",
            "conversation_id": 88,
            "category": "Technical",
            "technical_subcategory": "Aptem",
            "priority": "Normal",
            "status": "Pending",
            "status_reason": services.STATUS_REASON_QUICK_TICKET,
            "assigned_team": "Support Desk",
            "sla_status": "On Track",
            "metadata": {},
            "created_at": datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc),
            "conversation_status": "open",
            "learner_name": "Omar Badr",
            "learner_email": "omar@example.com",
            "assigned_agent_username": "agent",
        }

        with (
            patch.object(services, "sync_open_ticket_inactivity"),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "persist_conversation_chat_duration"),
            patch.object(
                services,
                "apply_ticket_chat_history_sync",
                return_value=([], services.STATUS_REASON_CLOSED_BY_AGENT, "On Track", False),
            ),
            patch.object(services, "queue_quick_ticket_submitted_notification") as queue_submitted,
            patch.object(services, "queue_quick_ticket_closed_notification") as queue_closed,
        ):
            services.save_chat_history(
                "KBC-000023",
                {
                    "status": "Closed",
                    "statusReason": services.STATUS_REASON_CLOSED_BY_AGENT,
                    "messages": [],
                },
            )

        queue_submitted.assert_not_called()
        queue_closed.assert_called_once()
        self.assertEqual(queue_closed.call_args.kwargs["status"], "Closed")
        self.assertEqual(queue_closed.call_args.kwargs["status_reason"], services.STATUS_REASON_CLOSED_BY_AGENT)

    @override_settings(
        SUPPORT_NOTIFICATION_WEBHOOK_URL="https://example.test/support-notification",
        SUPPORT_NOTIFICATION_DELIVERY_ENABLED=False,
    )
    def test_queue_support_notification_delivery_skips_when_disabled(self):
        with (
            patch.object(services.threading, "Thread") as thread_class,
            patch.object(services, "deliver_support_notification") as deliver_support_notification,
        ):
            services.queue_support_notification_delivery(
                ticket_id=23,
                ticket_public_id="KBC-000023",
                event=services.SUPPORT_NOTIFICATION_EVENT_QUICK_TICKET_SUBMITTED,
                payload={"recipientType": "requester", "requester": {"name": "Omar", "email": "omar@example.com"}},
                sent_metadata_key=services.QUICK_TICKET_SUBMITTED_NOTIFICATION_SENT_AT_METADATA_KEY,
            )

        thread_class.assert_not_called()
        deliver_support_notification.assert_not_called()

    @override_settings(
        SUPPORT_NOTIFICATION_WEBHOOK_URL="https://example.test/support-notification",
        SUPPORT_NOTIFICATION_DELIVERY_ENABLED=True,
    )
    def test_queue_support_notification_delivery_starts_background_thread_when_enabled(self):
        thread = MagicMock()

        with patch.object(services.threading, "Thread", return_value=thread) as thread_class:
            services.queue_support_notification_delivery(
                ticket_id=23,
                ticket_public_id="KBC-000023",
                event=services.SUPPORT_NOTIFICATION_EVENT_QUICK_TICKET_SUBMITTED,
                payload={"recipientType": "requester", "requester": {"name": "Omar", "email": "omar@example.com"}},
                sent_metadata_key=services.QUICK_TICKET_SUBMITTED_NOTIFICATION_SENT_AT_METADATA_KEY,
            )

        thread_class.assert_called_once()
        self.assertEqual(
            thread_class.call_args.kwargs["name"],
            "support-notification-quick_ticket_submitted-KBC-000023",
        )
        self.assertTrue(thread_class.call_args.kwargs["daemon"])
        thread.start.assert_called_once()

    def test_deliver_support_notification_records_success_history(self):
        payload = {
            "recipientType": "requester",
            "requester": {"name": "Omar", "email": "omar@example.com"},
        }

        with (
            patch.object(
                services,
                "send_support_notification_webhook",
                return_value={"configured": True, "delivered": True, "status": 202, "response": {"ok": True}},
            ) as send_support_notification_webhook,
            patch.object(services, "persist_ticket_metadata_patch") as persist_ticket_metadata_patch,
            patch.object(services, "insert_history_event") as insert_history_event,
        ):
            result = services.deliver_support_notification(
                ticket_id=23,
                ticket_public_id="KBC-000023",
                event=services.SUPPORT_NOTIFICATION_EVENT_QUICK_TICKET_SUBMITTED,
                payload=payload,
                sent_metadata_key=services.QUICK_TICKET_SUBMITTED_NOTIFICATION_SENT_AT_METADATA_KEY,
            )

        send_support_notification_webhook.assert_called_once_with(payload)
        persist_ticket_metadata_patch.assert_called_once_with(
            23,
            {services.QUICK_TICKET_SUBMITTED_NOTIFICATION_SENT_AT_METADATA_KEY: ANY},
        )
        insert_history_event.assert_called_once()
        self.assertEqual(insert_history_event.call_args.args[0], 23)
        self.assertEqual(insert_history_event.call_args.args[1], "quick_ticket_confirmation_email_sent")
        self.assertEqual(insert_history_event.call_args.args[3]["ticketId"], "KBC-000023")
        self.assertTrue(insert_history_event.call_args.args[3]["webhookDelivered"])
        self.assertEqual(result["historyEventType"], "quick_ticket_confirmation_email_sent")

    def test_try_auto_assign_quick_ticket_prefers_available_ticket_receiving_agent_and_updates_ticket(self):
        ticket = {
            "id": 23,
            "public_id": "KBC-000023",
            "conversation_id": 88,
            "assigned_agent_id": None,
            "assigned_team": "",
            "metadata": {},
            "conversation_metadata": {},
        }
        available_agent = {
            "id": 5,
            "username": "ahmed",
            "full_name": "Ahmed Hamamo",
            "role": "agent",
            "account_scope": "staff",
            "metadata": {
                "session_active": True,
                "session_started_at": "2026-05-14T09:00:00+00:00",
                "session_last_seen_at": "2026-05-14T10:25:00+00:00",
                "queue_joined_at": "2026-05-14T09:00:00+00:00",
                "console_status": "Available",
            },
        }
        off_admin = {
            "id": 8,
            "username": "omar",
            "full_name": "Omar1",
            "role": "admin",
            "account_scope": "staff",
            "metadata": {
                "session_active": False,
                "console_status": "Off",
            },
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context
        assignment_time = datetime(2026, 5, 14, 10, 30, tzinfo=timezone.utc)

        with (
            patch.object(services, "run_query", return_value=[off_admin, available_agent]),
            patch.object(services, "get_open_assigned_live_chat_agent_ids", return_value=set()),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event"),
            patch.object(services, "persist_agent_metadata") as persist_agent_metadata,
        ):
            assigned_agent = services.try_auto_assign_quick_ticket(ticket, now=assignment_time)

        self.assertEqual(assigned_agent, available_agent)
        self.assertEqual(ticket["assigned_agent_id"], 5)
        self.assertEqual(ticket["assigned_agent_username"], "ahmed")
        self.assertEqual(ticket["assigned_agent_name"], "Ahmed Hamamo")
        self.assertEqual(ticket["assigned_team"], "Support Desk")
        persist_agent_metadata.assert_called_once()
        persisted_admin_id, persisted_metadata = persist_agent_metadata.call_args.args
        self.assertEqual(persisted_admin_id, 5)
        self.assertEqual(
            persisted_metadata["last_quick_ticket_assigned_at"],
            assignment_time.isoformat(),
        )
        self.assertEqual(cursor.execute.call_count, 2)

    def test_try_auto_assign_quick_ticket_keeps_ticket_unassigned_when_no_agent_is_available(self):
        ticket = {
            "id": 23,
            "public_id": "KBC-000023",
            "conversation_id": 88,
            "assigned_agent_id": None,
            "assigned_team": "",
            "metadata": {},
            "conversation_metadata": {},
        }
        busy_agent = {
            "id": 5,
            "username": "ahmed",
            "full_name": "Ahmed Hamamo",
            "role": "agent",
            "account_scope": "staff",
            "metadata": {
                "session_active": True,
                "session_started_at": "2026-05-14T09:00:00+00:00",
                "queue_joined_at": "2026-05-14T09:00:00+00:00",
                "console_status": "Available",
            },
        }
        off_agent = {
            "id": 8,
            "username": "omar",
            "full_name": "Omar1",
            "role": "agent",
            "account_scope": "staff",
            "metadata": {
                "session_active": False,
                "console_status": "Off",
            },
        }
        assignment_time = datetime(2026, 5, 14, 10, 30, tzinfo=timezone.utc)

        with (
            patch.object(services, "run_query", return_value=[busy_agent, off_agent]),
            patch.object(services, "get_open_assigned_live_chat_agent_ids", return_value={5}),
            patch.object(services, "connection") as mock_connection,
            patch.object(services, "insert_history_event"),
            patch.object(services, "persist_agent_metadata") as persist_agent_metadata,
        ):
            assigned_agent = services.try_auto_assign_quick_ticket(ticket, now=assignment_time)

        self.assertIsNone(assigned_agent)
        self.assertIsNone(ticket["assigned_agent_id"])
        self.assertEqual(ticket["assigned_team"], "")
        mock_connection.cursor.assert_not_called()
        persist_agent_metadata.assert_not_called()

    def test_try_auto_assign_quick_ticket_skips_stale_available_session(self):
        ticket = {
            "id": 23,
            "public_id": "KBC-000023",
            "conversation_id": 88,
            "assigned_agent_id": None,
            "assigned_team": "",
            "metadata": {},
            "conversation_metadata": {},
        }
        stale_available_agent = {
            "id": 7,
            "username": "omar",
            "full_name": "Omar Helmy",
            "role": "superadmin",
            "account_scope": "staff",
            "metadata": {
                "session_active": True,
                "session_started_at": "2026-05-14T09:00:00+00:00",
                "session_last_seen_at": "2026-05-14T09:30:00+00:00",
                "queue_joined_at": "2026-05-14T09:00:00+00:00",
                "console_status": "Available",
            },
        }
        assignment_time = datetime(2026, 5, 14, 12, 30, tzinfo=timezone.utc)

        with (
            patch.object(services, "run_query", return_value=[stale_available_agent]),
            patch.object(services, "get_open_assigned_live_chat_agent_ids", return_value=set()),
            patch.object(services, "connection") as mock_connection,
            patch.object(services, "insert_history_event"),
            patch.object(services, "persist_agent_metadata") as persist_agent_metadata,
        ):
            assigned_agent = services.try_auto_assign_quick_ticket(ticket, now=assignment_time)

        self.assertIsNone(assigned_agent)
        self.assertIsNone(ticket["assigned_agent_id"])
        self.assertEqual(ticket["assigned_team"], "")
        mock_connection.cursor.assert_not_called()
        persist_agent_metadata.assert_not_called()

    def test_save_chat_history_auto_assigns_pending_quick_ticket(self):
        ticket = {
            "id": 23,
            "public_id": "KBC-000023",
            "conversation_id": 88,
            "status": "Open",
            "status_reason": "",
            "assigned_agent_id": None,
            "assigned_team": "",
            "sla_status": "Pending Review",
            "metadata": {},
            "created_at": datetime.now(timezone.utc),
            "assigned_agent_name": None,
            "assigned_agent_username": None,
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        def assign_side_effect(current_ticket: dict[str, object], now: datetime | None = None):
            current_ticket["assigned_agent_id"] = 5
            current_ticket["assigned_agent_name"] = "Ahmed Hamamo"
            current_ticket["assigned_agent_username"] = "ahmed"
            current_ticket["assigned_team"] = "Support Desk"
            return {"id": 5, "username": "ahmed", "full_name": "Ahmed Hamamo"}

        with (
            patch.object(services, "sync_open_ticket_inactivity"),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "mark_conversation_as_active"),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "sync_conversation_messages", return_value=[]),
            patch.object(services, "resolve_next_sla_state", return_value=("On Track", False, None)),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event"),
            patch.object(services, "persist_conversation_chat_duration"),
            patch.object(services, "try_auto_assign_quick_ticket", side_effect=assign_side_effect) as try_auto_assign_quick_ticket,
        ):
            response = services.save_chat_history(
                "KBC-000023",
                {
                    "status": "Pending",
                    "statusReason": "Quick Ticket",
                    "messages": [],
                },
            )

        try_auto_assign_quick_ticket.assert_called_once()
        self.assertEqual(response["ticket"]["assignedAgentId"], 5)
        self.assertEqual(response["ticket"]["assignedAgentName"], "Ahmed Hamamo")
        self.assertEqual(response["ticket"]["assignedAgentUsername"], "ahmed")
        self.assertEqual(response["ticket"]["assignedTeam"], "Support Desk")

    def test_save_chat_history_keeps_pending_coverage_quick_ticket_unassigned(self):
        ticket = {
            "id": 23,
            "public_id": "KBC-000023",
            "conversation_id": 88,
            "technical_subcategory": "Coverage",
            "status": "Open",
            "status_reason": "",
            "assigned_agent_id": None,
            "assigned_team": "Unassigned",
            "sla_status": "Pending Review",
            "metadata": {"technical_subcategory": "Coverage"},
            "created_at": datetime.now(timezone.utc),
            "assigned_agent_name": None,
            "assigned_agent_username": None,
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services, "sync_open_ticket_inactivity"),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "mark_conversation_as_active"),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "sync_conversation_messages", return_value=[]),
            patch.object(services, "resolve_next_sla_state", return_value=("On Track", False, None)),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event"),
            patch.object(services, "persist_conversation_chat_duration"),
            patch.object(services, "try_auto_assign_quick_ticket") as try_auto_assign_quick_ticket,
        ):
            response = services.save_chat_history(
                "KBC-000023",
                {
                    "status": "Pending",
                    "statusReason": "Quick Ticket",
                    "messages": [],
                },
            )

        try_auto_assign_quick_ticket.assert_not_called()
        self.assertIsNone(response["ticket"]["assignedAgentId"])
        self.assertIsNone(response["ticket"]["assignedAgentName"])
        self.assertIsNone(response["ticket"]["assignedAgentUsername"])
        self.assertEqual(response["ticket"]["assignedTeam"], "Unassigned")

    def test_save_chat_history_releases_prepared_teams_call_before_quick_ticket_assignment(self):
        ticket = {
            "id": 23,
            "public_id": "KBC-000023",
            "conversation_id": 88,
            "status": "Open",
            "status_reason": "",
            "assigned_agent_id": 23,
            "assigned_team": "Support Desk",
            "sla_status": "Pending Review",
            "metadata": {
                "requester_role": "coach",
                "pending_teams_call_notification": {
                    "toAgentId": 23,
                    "toAgentName": "Omar1",
                },
            },
            "created_at": datetime.now(timezone.utc),
            "assigned_agent_name": "Omar1",
            "assigned_agent_username": "Omar1",
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        def clear_side_effect(current_ticket: dict[str, object]):
            current_ticket["assigned_agent_id"] = None
            current_ticket["assigned_agent_name"] = None
            current_ticket["assigned_agent_username"] = None
            current_ticket["assigned_team"] = "Unassigned"
            current_ticket["metadata"] = {"requester_role": "coach"}
            return True

        def assign_side_effect(current_ticket: dict[str, object], now: datetime | None = None):
            current_ticket["assigned_agent_id"] = 5
            current_ticket["assigned_agent_name"] = "Ahmed Hamamo"
            current_ticket["assigned_agent_username"] = "ahmed"
            current_ticket["assigned_team"] = "Support Desk"
            return {"id": 5, "username": "ahmed", "full_name": "Ahmed Hamamo"}

        with (
            patch.object(services, "sync_open_ticket_inactivity"),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "mark_conversation_as_active"),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "sync_conversation_messages", return_value=[]),
            patch.object(services, "resolve_next_sla_state", return_value=("On Track", False, None)),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event"),
            patch.object(services, "persist_conversation_chat_duration"),
            patch.object(services, "clear_prepared_support_teams_call", side_effect=clear_side_effect) as clear_prepared_support_teams_call,
            patch.object(services, "try_auto_assign_quick_ticket", side_effect=assign_side_effect) as try_auto_assign_quick_ticket,
        ):
            response = services.save_chat_history(
                "KBC-000023",
                {
                    "status": "Pending",
                    "statusReason": "Quick Ticket",
                    "messages": [],
                },
            )

        clear_prepared_support_teams_call.assert_called_once()
        try_auto_assign_quick_ticket.assert_called_once()
        self.assertEqual(response["ticket"]["assignedAgentId"], 5)
        self.assertEqual(response["ticket"]["assignedAgentName"], "Ahmed Hamamo")
        self.assertEqual(response["ticket"]["assignedAgentUsername"], "ahmed")
        self.assertEqual(response["ticket"]["assignedTeam"], "Support Desk")

    def test_save_chat_history_defaults_pending_reason_to_awaiting_resolution(self):
        ticket = {
            "id": 23,
            "public_id": "KBC-000023",
            "conversation_id": 88,
            "status": "Open",
            "status_reason": "",
            "assigned_team": "Support Desk",
            "sla_status": "Pending Review",
            "metadata": {},
            "created_at": datetime.now(timezone.utc),
            "assigned_agent_username": "fatma",
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services, "sync_open_ticket_inactivity"),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "mark_conversation_as_active"),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "sync_conversation_messages", return_value=[]),
            patch.object(services, "resolve_next_sla_state", return_value=("On Track", False, None)),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event"),
            patch.object(services, "persist_conversation_chat_duration"),
            patch.object(services, "try_auto_assign_quick_ticket") as try_auto_assign_quick_ticket,
        ):
            response = services.save_chat_history(
                "KBC-000023",
                {
                    "status": "Pending",
                    "messages": [],
                },
            )

        update_params = cursor.execute.call_args_list[0].args[1]
        self.assertEqual(update_params[1], "Awaiting resolution")
        self.assertEqual(response["ticket"]["statusReason"], "Awaiting resolution")
        try_auto_assign_quick_ticket.assert_called_once()

    def test_save_chat_history_only_persists_duration_when_chat_closes(self):
        ticket = {
            "id": 23,
            "public_id": "KBC-000023",
            "conversation_id": 88,
            "status": "Open",
            "status_reason": "",
            "assigned_team": "Support Desk",
            "sla_status": "Pending Review",
            "metadata": {},
            "created_at": datetime.now(timezone.utc),
            "assigned_agent_username": "fatma",
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services, "sync_open_ticket_inactivity"),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "mark_conversation_as_active"),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "sync_conversation_messages", return_value=[]),
            patch.object(services, "resolve_next_sla_state", return_value=("Pending Review", False, None)),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event"),
            patch.object(services, "persist_conversation_chat_duration") as persist_conversation_chat_duration,
        ):
            services.save_chat_history("KBC-000023", {"status": "Open", "messages": []})
            persist_conversation_chat_duration.assert_not_called()

            services.save_chat_history("KBC-000023", {"status": "Closed", "messages": []})
            persist_conversation_chat_duration.assert_called_once()
            self.assertEqual(persist_conversation_chat_duration.call_args.args[:2], (23, 88))

    def test_save_chat_history_accepts_closed_by_requester_reason(self):
        ticket = {
            "id": 23,
            "public_id": "KBC-000023",
            "conversation_id": 88,
            "status": "Open",
            "status_reason": "",
            "assigned_agent_id": None,
            "assigned_team": "Support Desk",
            "sla_status": "Pending Review",
            "metadata": {"live_chat_requested": True},
            "created_at": datetime.now(timezone.utc),
            "conversation_status": "open",
            "learner_name": "Omar Badr",
            "learner_email": "omar@example.com",
            "assigned_agent_name": None,
            "assigned_agent_username": None,
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services, "sync_open_ticket_inactivity"),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "sync_conversation_messages", return_value=[]),
            patch.object(services, "resolve_next_sla_state", return_value=("On Track", False, None)),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event"),
            patch.object(services, "persist_conversation_chat_duration"),
        ):
            response = services.save_chat_history(
                "KBC-000023",
                {
                    "status": "Closed",
                    "statusReason": services.STATUS_REASON_CLOSED_BY_REQUESTER,
                    "messages": [],
                },
            )

        update_params = cursor.execute.call_args_list[0].args[1]
        self.assertEqual(update_params[1], services.STATUS_REASON_CLOSED_BY_REQUESTER)
        self.assertEqual(response["ticket"]["statusReason"], services.STATUS_REASON_CLOSED_BY_REQUESTER)

    def test_heartbeat_agent_session_reports_replaced_session(self):
        active_metadata = {
            "session_active": True,
            "session_instance_id": "current-instance",
            "session_last_seen_at": datetime.now(timezone.utc).isoformat(),
        }

        with patch.object(
            services,
            "fetch_agent_with_metadata_by_username",
            return_value={"id": 7, "username": "fatma", "metadata": active_metadata},
        ):
            response = services.heartbeat_agent_session(
                {
                    "actorUsername": "fatma",
                    "instanceId": "stale-instance",
                    "consoleStatus": "Available",
                }
            )

        self.assertEqual(response, {"ok": True, "sessionActive": False, "sessionReplaced": True})


class CoverageTutorWorkflowTests(SimpleTestCase):
    def build_mock_connection(self):
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context
        return mock_connection, cursor

    @override_settings(SUPPORT_PORTAL_PUBLIC_BASE_URL="https://technicalsupport.kentbusinesscollege.net")
    def test_public_coverage_attachment_signed_link_resolves_file(self):
        with TemporaryDirectory() as temp_dir:
            storage_key = "KBC-000045/2026/06/deck.pdf"
            attachment_path = Path(temp_dir) / storage_key
            attachment_path.parent.mkdir(parents=True)
            attachment_path.write_bytes(b"deck")
            download_url = services.build_public_coverage_attachment_download_url("KBC-000045", 101)
            parsed_url = urllib_parse.urlparse(download_url)
            token = urllib_parse.parse_qs(parsed_url.query)["token"][0]

            with (
                patch.object(services, "get_support_attachment_root", return_value=Path(temp_dir)),
                patch.object(
                    services,
                    "run_query_one",
                    return_value={
                        "id": 101,
                        "file_name": "deck.pdf",
                        "mime_type": "application/pdf",
                        "file_size": 4,
                        "storage_url": storage_key,
                        "attachment_metadata": {"source": "coverage_tutor_request"},
                        "public_id": "KBC-000045",
                        "technical_subcategory": "Coverage",
                        "assigned_team": "Learning Plan Team",
                        "metadata": {},
                    },
                ),
            ):
                attachment = services.get_public_coverage_attachment_file("KBC-000045", 101, token)

        self.assertEqual(attachment["fileName"], "deck.pdf")
        self.assertEqual(attachment["mimeType"], "application/pdf")
        self.assertEqual(attachment["fileSize"], 4)
        self.assertTrue(download_url.startswith("https://technicalsupport.kentbusinesscollege.net/api/public/coverage-attachments/KBC-000045/101/download?token="))

    def test_send_coverage_tutor_request_webhook_uses_short_timeout(self):
        with (
            patch.object(services, "get_coverage_tutor_request_webhook_url", return_value="https://n8n.example/webhook"),
            patch.object(
                services,
                "post_json_webhook",
                return_value=(True, True, 200, {"ok": True}),
            ) as post_json_webhook,
        ):
            response = services.send_coverage_tutor_request_webhook({"ticketId": "KBC-000001"})

        self.assertTrue(response["delivered"])
        post_json_webhook.assert_called_once_with(
            "https://n8n.example/webhook",
            {"ticketId": "KBC-000001"},
            timeout_seconds=services.COVERAGE_TUTOR_WEBHOOK_TIMEOUT_SECONDS,
        )

    def test_send_coverage_tutor_request_webhook_uses_multipart_when_files_are_present(self):
        payload = {
            "ticketId": "KBC-000001",
            "request": {
                "presentationFiles": [
                    {
                        "id": "file-1",
                        "name": "deck.pdf",
                        "mimeType": "application/pdf",
                        "size": 128,
                        "dataUrl": "data:application/pdf;base64,ZmFrZQ==",
                    }
                ]
            },
        }

        with (
            patch.object(services, "get_coverage_tutor_request_webhook_url", return_value="https://n8n.example/webhook"),
            patch.object(
                services,
                "post_json_webhook",
                return_value=(True, True, 200, {"ok": True}),
            ) as post_json_webhook,
            patch.object(
                services,
                "post_multipart_webhook",
                return_value=(True, True, 200, {"ok": True}),
            ) as post_multipart_webhook,
        ):
            response = services.send_coverage_tutor_request_webhook(payload)

        self.assertTrue(response["delivered"])
        post_json_webhook.assert_not_called()
        post_multipart_webhook.assert_called_once()
        self.assertEqual(post_multipart_webhook.call_args.args[0], "https://n8n.example/webhook")
        self.assertEqual(post_multipart_webhook.call_args.args[2][0]["id"], "file-1")
        self.assertEqual(post_multipart_webhook.call_args.args[2][0]["deliveryMode"], "attachment")
        sent_payload = post_multipart_webhook.call_args.args[1]
        self.assertNotIn("dataUrl", sent_payload["request"]["presentationFiles"][0])
        post_multipart_webhook.assert_called_once_with(
            "https://n8n.example/webhook",
            sent_payload,
            post_multipart_webhook.call_args.args[2],
            timeout_seconds=services.COVERAGE_TUTOR_WEBHOOK_TIMEOUT_SECONDS,
        )

    def test_send_coverage_tutor_request_webhook_includes_session_files_in_multipart(self):
        general_file = {
            "id": "file-1",
            "name": "overview.pdf",
            "mimeType": "application/pdf",
            "size": 128,
            "dataUrl": "data:application/pdf;base64,ZmFrZQ==",
        }
        session_file = {
            "id": "file-2",
            "name": "session-1.pdf",
            "mimeType": "application/pdf",
            "size": 256,
            "dataUrl": "data:application/pdf;base64,c2Vzc2lvbg==",
        }
        payload = {
            "ticketId": "KBC-000001",
            "request": {
                "presentationFiles": [general_file],
                "sessionFiles": [
                    {
                        "id": "session-1",
                        "label": "Session 1",
                        "attachments": [session_file],
                    }
                ],
            },
        }

        with (
            patch.object(services, "get_coverage_tutor_request_webhook_url", return_value="https://n8n.example/webhook"),
            patch.object(
                services,
                "post_multipart_webhook",
                return_value=(True, True, 200, {"ok": True}),
            ) as post_multipart_webhook,
        ):
            response = services.send_coverage_tutor_request_webhook(payload)

        self.assertTrue(response["delivered"])
        post_multipart_webhook.assert_called_once()
        self.assertEqual([file["id"] for file in post_multipart_webhook.call_args.args[2]], ["file-1", "file-2"])
        self.assertEqual([file["deliveryMode"] for file in post_multipart_webhook.call_args.args[2]], ["attachment", "attachment"])
        sent_payload = post_multipart_webhook.call_args.args[1]
        self.assertNotIn("dataUrl", sent_payload["request"]["presentationFiles"][0])
        self.assertNotIn("dataUrl", sent_payload["request"]["sessionFiles"][0]["attachments"][0])

    @override_settings(
        SUPPORT_PORTAL_PUBLIC_BASE_URL="https://technicalsupport.kentbusinesscollege.net",
        COVERAGE_WEBHOOK_ATTACHMENT_MAX_FILE_BYTES=8 * 1024 * 1024,
        COVERAGE_WEBHOOK_ATTACHMENT_MAX_TOTAL_BYTES=18 * 1024 * 1024,
    )
    def test_send_coverage_tutor_request_webhook_converts_large_files_to_signed_links(self):
        payload = {
            "ticketId": "KBC-000045",
            "request": {
                "presentationFiles": [
                    {
                        "id": "file-1",
                        "attachmentId": 101,
                        "name": "large-deck.pptx",
                        "mimeType": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                        "size": 11 * 1024 * 1024,
                        "storageKey": "KBC-000045/2026/06/large-deck.pptx",
                    }
                ],
                "sessionFiles": [],
            },
        }

        with (
            patch.object(services, "get_coverage_tutor_request_webhook_url", return_value="https://n8n.example/webhook"),
            patch.object(
                services,
                "post_json_webhook",
                return_value=(True, True, 200, {"ok": True}),
            ) as post_json_webhook,
            patch.object(services, "post_multipart_webhook") as post_multipart_webhook,
        ):
            response = services.send_coverage_tutor_request_webhook(payload)

        self.assertTrue(response["delivered"])
        post_multipart_webhook.assert_not_called()
        post_json_webhook.assert_called_once()
        sent_payload = post_json_webhook.call_args.args[1]
        sent_file = sent_payload["request"]["presentationFiles"][0]
        self.assertEqual(sent_file["deliveryMode"], "link")
        self.assertEqual(sent_file["deliveryReason"], "file_size_limit")
        self.assertIn("/api/public/coverage-attachments/KBC-000045/101/download?token=", sent_file["downloadUrl"])
        self.assertNotIn("storageKey", sent_file)

    def test_send_coverage_tutor_follow_up_webhook_uses_attachment_reply_url(self):
        payload = {
            "event": "coverage_tutor_follow_up",
            "ticketId": "KBC-000045",
            "followUp": {
                "presentationFiles": [
                    {
                        "id": "file-2",
                        "name": "slides-2.pdf",
                        "mimeType": "application/pdf",
                        "size": 256,
                        "dataUrl": "data:application/pdf;base64,Zm9sbG93LXVw",
                    }
                ]
            },
        }

        with (
            patch.object(
                services,
                "get_coverage_tutor_attachment_reply_webhook_url",
                return_value="https://n8n.example/attachment-reply",
            ),
            patch.object(
                services,
                "post_multipart_webhook",
                return_value=(True, True, 200, {"ok": True}),
            ) as post_multipart_webhook,
        ):
            response = services.send_coverage_tutor_follow_up_webhook(payload)

        self.assertTrue(response["delivered"])
        post_multipart_webhook.assert_called_once()
        self.assertEqual(post_multipart_webhook.call_args.args[0], "https://n8n.example/attachment-reply")
        self.assertEqual(post_multipart_webhook.call_args.args[2][0]["id"], "file-2")
        self.assertEqual(post_multipart_webhook.call_args.args[2][0]["deliveryMode"], "attachment")
        sent_payload = post_multipart_webhook.call_args.args[1]
        self.assertNotIn("dataUrl", sent_payload["followUp"]["presentationFiles"][0])
        post_multipart_webhook.assert_called_once_with(
            "https://n8n.example/attachment-reply",
            sent_payload,
            post_multipart_webhook.call_args.args[2],
            timeout_seconds=services.COVERAGE_TUTOR_WEBHOOK_TIMEOUT_SECONDS,
        )

    @override_settings(
        SUPPORT_PORTAL_PUBLIC_BASE_URL="https://technicalsupport.kentbusinesscollege.net",
        COVERAGE_WEBHOOK_ATTACHMENT_MAX_FILE_BYTES=8 * 1024 * 1024,
    )
    def test_send_coverage_tutor_follow_up_webhook_converts_large_files_to_signed_links(self):
        payload = {
            "event": "coverage_tutor_follow_up",
            "ticketId": "KBC-000045",
            "attachments": [
                {
                    "id": "file-2",
                    "attachmentId": 202,
                    "name": "large-follow-up.pptx",
                    "mimeType": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    "size": 12 * 1024 * 1024,
                    "storageKey": "KBC-000045/2026/06/large-follow-up.pptx",
                }
            ],
            "followUp": {
                "presentationFiles": [
                    {
                        "id": "file-2",
                        "attachmentId": 202,
                        "name": "large-follow-up.pptx",
                        "mimeType": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                        "size": 12 * 1024 * 1024,
                        "storageKey": "KBC-000045/2026/06/large-follow-up.pptx",
                    }
                ],
            },
        }

        with (
            patch.object(
                services,
                "get_coverage_tutor_attachment_reply_webhook_url",
                return_value="https://n8n.example/attachment-reply",
            ),
            patch.object(
                services,
                "post_json_webhook",
                return_value=(True, True, 200, {"ok": True}),
            ) as post_json_webhook,
            patch.object(services, "post_multipart_webhook") as post_multipart_webhook,
        ):
            response = services.send_coverage_tutor_follow_up_webhook(payload)

        self.assertTrue(response["delivered"])
        post_multipart_webhook.assert_not_called()
        post_json_webhook.assert_called_once()
        sent_payload = post_json_webhook.call_args.args[1]
        sent_file = sent_payload["followUp"]["presentationFiles"][0]
        self.assertEqual(sent_file["deliveryMode"], "link")
        self.assertIn("/api/public/coverage-attachments/KBC-000045/202/download?token=", sent_file["downloadUrl"])
        self.assertEqual(sent_payload["attachments"][0]["deliveryMode"], "link")
        self.assertNotIn("storageKey", sent_file)

    def test_queue_coverage_tutor_request_webhook_delivery_starts_background_thread(self):
        thread = MagicMock()

        with (
            patch.object(services, "get_coverage_tutor_request_webhook_url", return_value="https://n8n.example/webhook"),
            patch.object(services.threading, "Thread", return_value=thread) as thread_class,
        ):
            services.queue_coverage_tutor_request_webhook_delivery(
                ticket_id=41,
                ticket_public_id="KBC-000041",
                card_id="card-1",
                payload={"ticketId": "KBC-000041"},
            )

        thread_class.assert_called_once()
        self.assertTrue(thread_class.call_args.kwargs["daemon"])
        thread.start.assert_called_once()

    def test_queue_coverage_tutor_follow_up_webhook_delivery_uses_attachment_reply_url(self):
        thread = MagicMock()

        with (
            patch.object(
                services,
                "get_coverage_tutor_attachment_reply_webhook_url",
                return_value="https://n8n.example/attachment-reply",
            ),
            patch.object(services.threading, "Thread", return_value=thread) as thread_class,
        ):
            services.queue_coverage_tutor_follow_up_webhook_delivery(
                ticket_id=45,
                ticket_public_id="KBC-000045",
                card_id="card-1",
                payload={"event": "coverage_tutor_follow_up"},
            )

        thread_class.assert_called_once()
        self.assertTrue(thread_class.call_args.kwargs["daemon"])
        self.assertIn("coverage-tutor-follow-up-webhook-KBC-000045-card-1", thread_class.call_args.kwargs["name"])
        thread.start.assert_called_once()

    def test_build_coverage_tutor_request_webhook_payload_includes_result_urls(self):
        payload = services.build_coverage_tutor_request_webhook_payload(
            {
                "public_id": "KBC-000999",
                "learner_name": "Ayman",
                "learner_email": "ayman@example.com",
                "category": "Technical",
                "technical_subcategory": "Coverage",
                "inquiry": "Coverage request",
            },
            {"coverageNotes": "Internal note"},
            {
                "id": "choice-1",
                "tutor": "Adey",
                "tutorEmail": "adey@example.com",
                "coach": "Mona Adel",
                "coachEmail": "mona.adel@example.com",
                "responseToken": "token-1",
                "sessionDetails": "Module: EVM",
                "presentationFiles": [],
            },
            {
                "id": 7,
                "username": "ahmed",
                "full_name": "Ahmed Hamamo",
                "email": "ahmed@example.com",
            },
            callback_url="https://technicalsupport.kentbusinesscollege.net/coverage/tutor-response",
            result_base_url="https://technicalsupport.kentbusinesscollege.net/coverage/tutor-response/result",
        )

        self.assertEqual(
            payload["acceptResultUrl"],
            "https://technicalsupport.kentbusinesscollege.net/coverage/tutor-response/result?action=accept",
        )
        self.assertEqual(
            payload["refuseResultUrl"],
            "https://technicalsupport.kentbusinesscollege.net/coverage/tutor-response/result?action=refuse",
        )
        self.assertEqual(
            payload["callback"]["result"]["acceptUrl"],
            "https://technicalsupport.kentbusinesscollege.net/coverage/tutor-response/result?action=accept",
        )
        self.assertEqual(
            payload["callback"]["result"]["refuseUrl"],
            "https://technicalsupport.kentbusinesscollege.net/coverage/tutor-response/result?action=refuse",
        )
        self.assertEqual(payload["coach"]["name"], "Mona Adel")
        self.assertEqual(payload["coach"]["email"], "mona.adel@example.com")

    def test_freeze_coverage_documentation_snapshot_locks_saved_cards_and_preserves_previous_content(self):
        existing_documentation = {
            "inquiry": "Original saved inquiry",
            "coverageNotes": "Initial saved note",
            "coverageCards": [
                {
                    "id": "choice-1",
                    "type": "tutor_choice",
                    "tutor": "Andrew",
                    "tutorEmail": "andrew@example.com",
                    "sessionDetails": "Module: PMI PMO",
                    "requestStatus": "draft",
                    "locked": True,
                    "createdAt": "2026-06-05T08:00:00Z",
                    "updatedAt": "2026-06-05T08:00:00Z",
                }
            ],
        }
        requested_documentation = {
            "inquiry": "Edited inquiry that should be ignored",
            "coverageNotes": "Edited later note that should be ignored",
            "coverageCards": [
                {
                    "id": "choice-1",
                    "type": "tutor_choice",
                    "tutor": "Charl",
                    "tutorEmail": "charl@example.com",
                    "sessionDetails": "Module: Changed",
                    "requestStatus": "draft",
                    "locked": False,
                    "createdAt": "2026-06-05T08:00:00Z",
                    "updatedAt": "2026-06-05T08:05:00Z",
                },
                {
                    "id": "note-2",
                    "type": "note",
                    "note": "New follow-up note",
                    "locked": False,
                    "createdAt": "2026-06-05T08:10:00Z",
                    "updatedAt": "2026-06-05T08:10:00Z",
                },
            ],
        }

        frozen = services.freeze_coverage_documentation_snapshot(existing_documentation, requested_documentation)

        self.assertEqual(frozen["inquiry"], "Original saved inquiry")
        self.assertEqual(frozen["coverageNotes"], "Initial saved note")
        self.assertEqual(len(frozen["coverageCards"]), 2)
        self.assertEqual(frozen["coverageCards"][0]["id"], "choice-1")
        self.assertEqual(frozen["coverageCards"][0]["tutor"], "Andrew")
        self.assertEqual(frozen["coverageCards"][0]["sessionDetails"], "Module: PMI PMO")
        self.assertTrue(frozen["coverageCards"][0]["locked"])
        self.assertEqual(frozen["coverageCards"][1]["id"], "note-2")
        self.assertEqual(frozen["coverageCards"][1]["note"], "New follow-up note")
        self.assertTrue(frozen["coverageCards"][1]["locked"])

    def test_freeze_coverage_documentation_snapshot_locks_first_saved_revision(self):
        requested_documentation = {
            "inquiry": "First saved inquiry",
            "coverageNotes": "First saved note",
            "coverageCards": [
                {
                    "id": "choice-1",
                    "type": "tutor_choice",
                    "tutor": "Andrew",
                    "tutorEmail": "andrew@example.com",
                    "sessionDetails": "Module: PMI PMO",
                    "requestStatus": "draft",
                    "locked": False,
                    "createdAt": "2026-06-05T08:00:00Z",
                    "updatedAt": "2026-06-05T08:01:00Z",
                }
            ],
        }

        frozen = services.freeze_coverage_documentation_snapshot({}, requested_documentation)

        self.assertEqual(frozen["inquiry"], "First saved inquiry")
        self.assertEqual(frozen["coverageNotes"], "First saved note")
        self.assertEqual(len(frozen["coverageCards"]), 1)
        self.assertEqual(frozen["coverageCards"][0]["id"], "choice-1")
        self.assertTrue(frozen["coverageCards"][0]["locked"])

    def test_submit_coverage_tutor_request_rejects_when_webhook_is_not_configured(self):
        ticket = {
            "id": 349,
            "public_id": "KBC-000349",
            "category": "Technical",
            "technical_subcategory": "Coverage",
            "inquiry": "Coverage session request",
            "status": "Pending",
            "status_reason": "Coverage Ticket",
            "assigned_team": "Unassigned",
            "assigned_agent_id": None,
            "sla_status": "On Track",
            "metadata": {"admin_documentation": {}},
            "created_at": datetime(2026, 6, 5, 7, 0, tzinfo=timezone.utc),
            "conversation_id": None,
            "learner_name": "Omar",
            "learner_email": "omar@example.com",
        }
        actor_row = {
            "id": 7,
            "username": "ahmed",
            "full_name": "Ahmed Hamamo",
            "role": "superadmin",
        }
        documentation = {
            "inquiry": "Coverage session request",
            "coverageCards": [
                {
                    "id": "choice-1",
                    "type": "tutor_choice",
                    "tutor": "Adey",
                    "tutorEmail": "adey@example.com",
                    "sessionDetails": "Module: PMI SP",
                    "requestStatus": "draft",
                    "locked": False,
                    "createdAt": "2026-06-05T09:57:00Z",
                    "updatedAt": "2026-06-05T09:57:00Z",
                }
            ],
        }
        mock_connection, _cursor = self.build_mock_connection()

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services, "get_coverage_tutor_request_webhook_url", return_value=""),
            patch.object(services, "connection", mock_connection),
        ):
            with self.assertRaises(services.ApiError) as raised_error:
                services.submit_coverage_tutor_request(
                    "KBC-000349",
                    {
                        "actorUsername": "ahmed",
                        "cardId": "choice-1",
                        "origin": "http://localhost:3000",
                        "documentation": documentation,
                    },
                )

        self.assertEqual(raised_error.exception.status_code, 503)
        self.assertEqual(raised_error.exception.message, "The tutor request webhook is not configured on the server.")
        mock_connection.cursor.assert_not_called()

    def test_serialize_ticket_summary_derives_coverage_reply_from_database_status(self):
        row = {
            "public_id": "KBC-000340",
            "learner_name": "Ayman",
            "learner_email": "ayman@example.com",
            "learner_phone": "",
            "category": "Technical",
            "technical_subcategory": "Coverage",
            "inquiry": "Coverage request",
            "status": "Pending",
            "status_reason": "Tutor Accepted",
            "priority": "Normal",
            "assigned_agent_id": None,
            "assigned_agent_name": None,
            "assigned_agent_username": None,
            "assigned_team": "Unassigned",
            "conversation_id": None,
            "conversation_metadata": {},
            "conversation_status": None,
            "chat_duration_minutes": 0,
            "last_message_at": None,
            "metadata": {
                "technical_subcategory": "Coverage",
                "admin_documentation": {
                    "ticketId": "KBC-000340",
                    "coverageCards": [
                        {
                            "id": "card-1",
                            "type": "tutor_choice",
                            "tutor": "Andrew",
                            "tutorEmail": "andrew@example.com",
                            "sessionDetails": "Module: PMI PMO",
                            "requestStatus": "requested",
                            "submittedAt": "2026-06-04T10:10:00Z",
                            "requestSubmittedByAgentId": 7,
                            "requestSubmittedByAgentName": "Ahmed Hamamo",
                            "requestSubmittedByAgentUsername": "ahmed",
                            "locked": True,
                        }
                    ],
                },
            },
            "sla_status": "On Track",
            "sla_attention_required": False,
            "evidence_count": 0,
            "created_at": datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 6, 4, 11, 0, tzinfo=timezone.utc),
        }

        summary = services.serialize_ticket_summary(row)

        self.assertEqual(summary["statusReason"], "Tutor Accepted")
        self.assertIsNotNone(summary["latestCoverageTutorResponse"])
        self.assertEqual(summary["latestCoverageTutorResponse"]["outcome"], "accepted")
        self.assertEqual(summary["latestCoverageTutorResponse"]["relatedTutorChoiceCardId"], "card-1")
        self.assertEqual(summary["documentation"]["coverageCards"][0]["requestStatus"], "accepted")
        self.assertEqual(summary["documentation"]["coverageCards"][1]["type"], "tutor_reply")
        self.assertEqual(summary["documentation"]["coverageCards"][1]["replyOutcome"], "accepted")

    def test_serialize_ticket_summary_builds_coverage_reply_from_inquiry_when_cards_are_missing(self):
        row = {
            "public_id": "KBC-000353",
            "learner_name": "Omar",
            "learner_email": "omar@example.com",
            "learner_phone": "",
            "category": "Technical",
            "technical_subcategory": "Coverage",
            "inquiry": (
                "Coverage session request\n"
                "Tutor: Adey\n"
                "Module: EVM\n"
                "Preferred Time: Wednesday 09:00 - 11:00 | G1-Wed-9 | July 2025\n"
                "Session Subject: test"
            ),
            "status": "Closed",
            "status_reason": "Tutor Accepted",
            "priority": "Normal",
            "assigned_agent_id": 7,
            "assigned_agent_name": "Ahmed Hamamo",
            "assigned_agent_username": "ahmed",
            "assigned_team": "Support Desk",
            "conversation_id": None,
            "conversation_metadata": {},
            "conversation_status": None,
            "chat_duration_minutes": 0,
            "last_message_at": None,
            "metadata": {
                "technical_subcategory": "Coverage",
                "admin_documentation": {
                    "ticketId": "KBC-000353",
                    "coverageCards": [],
                },
            },
            "sla_status": "On Track",
            "sla_attention_required": False,
            "evidence_count": 0,
            "created_at": datetime(2026, 6, 5, 11, 19, 48, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 6, 5, 12, 36, 2, tzinfo=timezone.utc),
        }

        summary = services.serialize_ticket_summary(row)

        self.assertEqual(summary["status"], "Closed")
        self.assertEqual(summary["statusReason"], "Tutor Accepted")
        self.assertIsNotNone(summary["latestCoverageTutorResponse"])
        persisted_cards = summary["documentation"]["coverageCards"]
        self.assertEqual(len(persisted_cards), 2)
        self.assertEqual(persisted_cards[0]["type"], "tutor_choice")
        self.assertEqual(persisted_cards[0]["tutor"], "Adey")
        self.assertEqual(persisted_cards[0]["requestStatus"], "accepted")
        self.assertEqual(persisted_cards[1]["type"], "tutor_reply")
        self.assertEqual(persisted_cards[1]["replyOutcome"], "accepted")

    def test_synchronize_coverage_tutor_workflow_ticket_closes_accepted_ticket_and_persists_response(self):
        ticket = {
            "id": 340,
            "public_id": "KBC-000340",
            "learner_name": "Ayman",
            "learner_email": "ayman@example.com",
            "learner_phone": "",
            "category": "Technical",
            "technical_subcategory": "Coverage",
            "inquiry": "Coverage request",
            "status": "Pending",
            "status_reason": "Tutor Accepted",
            "priority": "Normal",
            "assigned_agent_id": None,
            "assigned_agent_name": None,
            "assigned_agent_username": None,
            "assigned_team": "Unassigned",
            "conversation_id": None,
            "conversation_metadata": {},
            "conversation_status": None,
            "chat_duration_minutes": 0,
            "last_message_at": None,
            "metadata": {
                "technical_subcategory": "Coverage",
                "admin_documentation": {
                    "ticketId": "KBC-000340",
                    "coverageCards": [
                        {
                            "id": "card-1",
                            "type": "tutor_choice",
                            "tutor": "Andrew",
                            "tutorEmail": "andrew@example.com",
                            "sessionDetails": "Module: PMI PMO",
                            "requestStatus": "requested",
                            "submittedAt": "2026-06-04T10:10:00Z",
                            "requestSubmittedByAgentId": 7,
                            "requestSubmittedByAgentName": "Ahmed Hamamo",
                            "requestSubmittedByAgentUsername": "ahmed",
                            "locked": True,
                        }
                    ],
                },
            },
            "sla_status": "On Track",
            "sla_attention_required": False,
            "evidence_count": 0,
            "created_at": datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 6, 4, 11, 0, tzinfo=timezone.utc),
        }
        mock_connection, cursor = self.build_mock_connection()

        with (
            patch.object(services, "connection", mock_connection),
            patch.object(services, "resolve_next_sla_state", return_value=("On Track", False, None)),
            patch.object(services, "insert_history_event") as insert_history_event,
        ):
            synchronized_ticket = services.synchronize_coverage_tutor_workflow_ticket(ticket)

        self.assertEqual(synchronized_ticket["status"], "Closed")
        self.assertIsNotNone(synchronized_ticket.get("closed_at"))
        update_params = cursor.execute.call_args.args[1]
        self.assertEqual(update_params[0], "Closed")
        self.assertEqual(update_params[1], "Tutor Accepted")
        persisted_metadata = json.loads(update_params[3])
        self.assertEqual(persisted_metadata["latest_coverage_tutor_response"]["outcome"], "accepted")
        persisted_cards = persisted_metadata["admin_documentation"]["coverageCards"]
        self.assertEqual(persisted_cards[0]["requestStatus"], "accepted")
        self.assertEqual(persisted_cards[1]["type"], "tutor_reply")
        self.assertEqual(insert_history_event.call_count, 2)
        self.assertEqual(insert_history_event.call_args_list[0].args[1], "status_changed")
        self.assertEqual(insert_history_event.call_args_list[1].args[1], "coverage_tutor_response")

    def test_synchronize_coverage_tutor_workflow_ticket_builds_accepted_cards_from_inquiry_when_missing(self):
        ticket = {
            "id": 353,
            "public_id": "KBC-000353",
            "learner_name": "Omar",
            "learner_email": "omar@example.com",
            "learner_phone": "",
            "category": "Technical",
            "technical_subcategory": "Coverage",
            "inquiry": (
                "Coverage session request\n"
                "Tutor: Adey\n"
                "Module: EVM\n"
                "Preferred Time: Wednesday 09:00 - 11:00 | G1-Wed-9 | July 2025\n"
                "Session Subject: test"
            ),
            "status": "Closed",
            "status_reason": "Tutor Accepted",
            "priority": "Normal",
            "assigned_agent_id": 7,
            "assigned_agent_name": "Ahmed Hamamo",
            "assigned_agent_username": "ahmed",
            "assigned_team": "Support Desk",
            "conversation_id": None,
            "conversation_metadata": {},
            "conversation_status": None,
            "chat_duration_minutes": 0,
            "last_message_at": None,
            "metadata": {
                "technical_subcategory": "Coverage",
                "admin_documentation": {
                    "ticketId": "KBC-000353",
                    "coverageCards": [],
                },
            },
            "sla_status": "On Track",
            "sla_attention_required": False,
            "evidence_count": 0,
            "created_at": datetime(2026, 6, 5, 11, 19, 48, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 6, 5, 12, 36, 2, tzinfo=timezone.utc),
        }
        mock_connection, cursor = self.build_mock_connection()

        with (
            patch.object(services, "connection", mock_connection),
            patch.object(services, "resolve_next_sla_state", return_value=("On Track", False, None)),
            patch.object(services, "insert_history_event") as insert_history_event,
        ):
            synchronized_ticket = services.synchronize_coverage_tutor_workflow_ticket(ticket)

        self.assertEqual(synchronized_ticket["status"], "Closed")
        update_params = cursor.execute.call_args.args[1]
        self.assertEqual(update_params[1], "Tutor Accepted")
        persisted_metadata = json.loads(update_params[3])
        persisted_cards = persisted_metadata["admin_documentation"]["coverageCards"]
        self.assertEqual(len(persisted_cards), 2)
        self.assertEqual(persisted_cards[0]["type"], "tutor_choice")
        self.assertEqual(persisted_cards[0]["requestStatus"], "accepted")
        self.assertEqual(persisted_cards[1]["type"], "tutor_reply")
        self.assertEqual(persisted_cards[1]["replyOutcome"], "accepted")
        self.assertEqual(insert_history_event.call_count, 1)
        self.assertEqual(insert_history_event.call_args_list[0].args[1], "coverage_tutor_response")

    def test_synchronize_coverage_tutor_workflow_ticket_ignores_conflicting_late_refusal_after_acceptance(self):
        ticket = {
            "id": 354,
            "public_id": "KBC-000354",
            "learner_name": "Omar",
            "learner_email": "omar@example.com",
            "learner_phone": "",
            "category": "Technical",
            "technical_subcategory": "Coverage",
            "inquiry": (
                "Coverage session request\n"
                "Tutor: Adey\n"
                "Module: Marketing Impact\n"
                "Preferred Time: Friday 09:00 - 11:00 | G2-Fri | Jun 2026\n"
                "Session Date: Friday 12 Jun 2026\n"
                "Session Subject: test"
            ),
            "status": "Closed",
            "status_reason": "Tutor Refused",
            "priority": "Normal",
            "assigned_agent_id": 599,
            "assigned_agent_name": "Engagement",
            "assigned_agent_username": "engagement.kentbusinesscollege.com",
            "assigned_team": "Support Desk",
            "conversation_id": None,
            "conversation_metadata": {},
            "conversation_status": None,
            "chat_duration_minutes": 0,
            "last_message_at": None,
            "metadata": {
                "technical_subcategory": "Coverage",
                "admin_documentation": {
                    "ticketId": "KBC-000354",
                    "coverageCards": [
                        {
                            "id": "card-1",
                            "type": "tutor_choice",
                            "tutor": "Adey",
                            "tutorEmail": "omar.helmy@kentbusinesscollege.com",
                            "sessionDetails": "Module: Marketing Impact\nPreferred Time: Friday 09:00 - 11:00 | G2-Fri | Jun 2026\nSessions:\n1. Friday 12 Jun 2026 | test",
                            "requestStatus": "accepted",
                            "submittedAt": "2026-06-05T13:09:28.808965+00:00",
                            "respondedAt": "2026-06-05T13:10:00.388481+00:00",
                            "requestSubmittedByAgentId": 599,
                            "requestSubmittedByAgentName": "Engagement",
                            "requestSubmittedByAgentUsername": "engagement.kentbusinesscollege.com",
                            "locked": True,
                        },
                        {
                            "id": "card-1-reply-accepted",
                            "type": "tutor_reply",
                            "title": "Tutor Accepted",
                            "tutor": "Adey",
                            "tutorEmail": "omar.helmy@kentbusinesscollege.com",
                            "sessionDetails": "Module: Marketing Impact\nPreferred Time: Friday 09:00 - 11:00 | G2-Fri | Jun 2026\nSessions:\n1. Friday 12 Jun 2026 | test",
                            "requestStatus": "accepted",
                            "replyOutcome": "accepted",
                            "locked": True,
                            "createdAt": "2026-06-05T13:10:00.388481+00:00",
                            "updatedAt": "2026-06-05T13:10:00.388481+00:00",
                            "respondedAt": "2026-06-05T13:10:00.388481+00:00",
                            "relatedTutorChoiceCardId": "card-1",
                        },
                    ],
                },
            },
            "sla_status": "On Track",
            "sla_attention_required": False,
            "evidence_count": 0,
            "created_at": datetime(2026, 6, 5, 13, 7, 1, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 6, 5, 13, 13, 15, tzinfo=timezone.utc),
        }
        mock_connection, cursor = self.build_mock_connection()

        with (
            patch.object(services, "connection", mock_connection),
            patch.object(services, "resolve_next_sla_state", return_value=("On Track", False, None)),
            patch.object(services, "insert_history_event") as insert_history_event,
        ):
            synchronized_ticket = services.synchronize_coverage_tutor_workflow_ticket(ticket)

        self.assertEqual(synchronized_ticket["status"], "Closed")
        self.assertEqual(synchronized_ticket["status_reason"], "Tutor Accepted")
        update_params = cursor.execute.call_args.args[1]
        self.assertEqual(update_params[0], "Closed")
        self.assertEqual(update_params[1], "Tutor Accepted")
        persisted_metadata = json.loads(update_params[3])
        persisted_cards = persisted_metadata["admin_documentation"]["coverageCards"]
        self.assertEqual(len([card for card in persisted_cards if card["type"] == "tutor_reply"]), 1)
        self.assertEqual(persisted_cards[1]["replyOutcome"], "accepted")
        self.assertEqual(insert_history_event.call_count, 2)
        self.assertEqual(insert_history_event.call_args_list[0].args[1], "status_reason_changed")
        self.assertEqual(insert_history_event.call_args_list[1].args[1], "coverage_tutor_response")

    def test_synchronize_coverage_tutor_workflow_ticket_recovers_requested_card_from_history(self):
        ticket = {
            "id": 349,
            "public_id": "KBC-000349",
            "learner_name": "Ayman",
            "learner_email": "ayman@example.com",
            "learner_phone": "",
            "category": "Technical",
            "technical_subcategory": "Coverage",
            "inquiry": "Coverage request",
            "status": "Pending",
            "status_reason": "Rerequesting",
            "priority": "Normal",
            "assigned_agent_id": None,
            "assigned_agent_name": None,
            "assigned_agent_username": None,
            "assigned_team": "Unassigned",
            "conversation_id": None,
            "conversation_metadata": {},
            "conversation_status": None,
            "chat_duration_minutes": 0,
            "last_message_at": None,
            "metadata": {
                "technical_subcategory": "Coverage",
                "admin_documentation": {
                    "ticketId": "KBC-000349",
                    "coverageCards": [
                        {
                            "id": "card-1",
                            "type": "tutor_choice",
                            "tutor": "Charl",
                            "tutorEmail": "hamamoa842@gmail.com",
                            "sessionDetails": "Module: PMI SP",
                            "requestStatus": "draft",
                            "locked": False,
                            "createdAt": "2026-06-04T14:17:24.242Z",
                            "updatedAt": "2026-06-04T14:18:28.298Z",
                        }
                    ],
                },
            },
            "sla_status": "On Track",
            "sla_attention_required": False,
            "evidence_count": 0,
            "created_at": datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 6, 4, 14, 31, tzinfo=timezone.utc),
        }
        mock_connection, cursor = self.build_mock_connection()

        with (
            patch.object(
                services,
                "run_query",
                return_value=[
                    {
                        "ticket_id": 349,
                        "payload": {
                            "toAgentId": 599,
                            "toAgentName": "Engagement",
                            "toAgentUsername": "engagement.kentbusinesscollege.com",
                            "ticketId": "KBC-000349",
                            "cardId": "card-1",
                            "tutor": "Charl",
                            "tutorEmail": "hamamoa842@gmail.com",
                            "requestedAt": "2026-06-04T14:31:56.850806+00:00",
                            "sessionDetails": "Module: PMI SP",
                        },
                        "created_at": datetime(2026, 6, 4, 14, 31, 56, tzinfo=timezone.utc),
                    }
                ],
            ),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event") as insert_history_event,
        ):
            synchronized_ticket = services.synchronize_coverage_tutor_workflow_ticket(ticket)

        self.assertEqual(synchronized_ticket["status"], "Pending")
        update_params = cursor.execute.call_args.args[1]
        self.assertEqual(update_params[0], "Pending")
        persisted_metadata = json.loads(update_params[3])
        persisted_card = persisted_metadata["admin_documentation"]["coverageCards"][0]
        self.assertEqual(persisted_card["requestStatus"], "requested")
        self.assertTrue(persisted_card["locked"])
        self.assertEqual(persisted_card["submittedAt"], "2026-06-04T14:31:56.850806+00:00")
        self.assertEqual(persisted_card["requestSubmittedByAgentId"], 599)
        insert_history_event.assert_not_called()

    def test_serialize_ticket_summary_derives_coverage_reply_from_refused_status_reason(self):
        row = {
            "public_id": "KBC-000341",
            "learner_name": "Ayman",
            "learner_email": "ayman@example.com",
            "learner_phone": "",
            "category": "Technical",
            "technical_subcategory": "Coverage",
            "inquiry": "Coverage request",
            "status": "Pending",
            "status_reason": "Tutor Refused",
            "priority": "Normal",
            "assigned_agent_id": None,
            "assigned_agent_name": None,
            "assigned_agent_username": None,
            "assigned_team": "Unassigned",
            "conversation_id": None,
            "conversation_metadata": {},
            "conversation_status": None,
            "chat_duration_minutes": 0,
            "last_message_at": None,
            "metadata": {
                "technical_subcategory": "Coverage",
                "admin_documentation": {
                    "ticketId": "KBC-000341",
                    "coverageCards": [
                        {
                            "id": "card-1",
                            "type": "tutor_choice",
                            "tutor": "Amgad",
                            "tutorEmail": "amgad@example.com",
                            "sessionDetails": "Module: PMP 3 Months",
                            "requestStatus": "requested",
                            "submittedAt": "2026-06-04T10:10:00Z",
                            "requestSubmittedByAgentId": 7,
                            "requestSubmittedByAgentName": "Ahmed Hamamo",
                            "requestSubmittedByAgentUsername": "ahmed",
                            "locked": True,
                        }
                    ],
                },
            },
            "sla_status": "On Track",
            "sla_attention_required": False,
            "evidence_count": 0,
            "created_at": datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 6, 4, 11, 0, tzinfo=timezone.utc),
        }

        summary = services.serialize_ticket_summary(row)

        self.assertEqual(summary["status"], "Pending")
        self.assertEqual(summary["statusReason"], "Tutor Refused")
        self.assertIsNotNone(summary["latestCoverageTutorResponse"])
        self.assertEqual(summary["latestCoverageTutorResponse"]["outcome"], "rejected")
        self.assertEqual(summary["documentation"]["coverageCards"][0]["requestStatus"], "refused")
        self.assertEqual(summary["documentation"]["coverageCards"][1]["type"], "tutor_reply")
        self.assertEqual(summary["documentation"]["coverageCards"][1]["replyOutcome"], "refused")

    def test_serialize_ticket_summary_includes_pending_coverage_ticket_notification(self):
        row = {
            "public_id": "KBC-000341",
            "learner_name": "Ayman",
            "learner_email": "ayman@example.com",
            "learner_phone": "",
            "category": "Technical",
            "technical_subcategory": "Coverage",
            "inquiry": "Coverage request",
            "status": "Pending",
            "status_reason": "Quick Ticket",
            "priority": "Normal",
            "assigned_agent_id": None,
            "assigned_agent_name": None,
            "assigned_agent_username": None,
            "assigned_team": "Unassigned",
            "conversation_id": None,
            "conversation_metadata": {},
            "conversation_status": None,
            "chat_duration_minutes": 0,
            "last_message_at": None,
            "metadata": {
                "technical_subcategory": "Coverage",
                "pending_coverage_ticket_notification": {
                    "ticketId": "KBC-000341",
                    "requesterName": "Ayman",
                    "requesterEmail": "ayman@example.com",
                    "requesterRole": "user",
                    "createdAt": "2026-06-05T10:00:00Z",
                },
            },
            "sla_status": "On Track",
            "sla_attention_required": False,
            "evidence_count": 0,
            "created_at": datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc),
        }

        summary = services.serialize_ticket_summary(row)

        self.assertEqual(summary["pendingCoverageTicketNotification"]["ticketId"], "KBC-000341")
        self.assertEqual(summary["pendingCoverageTicketNotification"]["requesterEmail"], "ayman@example.com")

    def test_serialize_ticket_summary_includes_pending_learning_plan_transfer_notification(self):
        row = {
            "public_id": "KBC-000342",
            "learner_name": "Olivia Evans",
            "learner_email": "olivia@example.com",
            "learner_phone": "",
            "category": "Technical",
            "technical_subcategory": "ApTem",
            "inquiry": "Transferred to learning plan team",
            "status": "Pending",
            "status_reason": "Quick Ticket",
            "priority": "Normal",
            "assigned_agent_id": 5,
            "assigned_agent_name": "Omar Helmy",
            "assigned_agent_username": "omar",
            "assigned_team": services.ASSIGNED_TEAM_LEARNING_PLAN,
            "conversation_id": None,
            "conversation_metadata": {},
            "conversation_status": None,
            "chat_duration_minutes": 0,
            "last_message_at": None,
            "metadata": {
                "requester_role": "coach",
                "requester_source": "legacy_portal",
                "pending_learning_plan_transfer_notification": {
                    "ticketId": "KBC-000342",
                    "requesterName": "Olivia Evans",
                    "requesterEmail": "olivia@example.com",
                    "requesterRole": "coach",
                    "fromTeam": services.ASSIGNED_TEAM_SUPPORT_DESK,
                    "toTeam": services.ASSIGNED_TEAM_LEARNING_PLAN,
                    "transferredAt": "2026-06-05T11:00:00Z",
                    "transferredById": 1,
                    "transferredByName": "Support Manager",
                    "transferredByUsername": "manager",
                    "assignedAgentId": 5,
                    "assignedAgentName": "Omar Helmy",
                    "assignedAgentUsername": "omar",
                    "note": "Please continue with learning plan workflow.",
                },
            },
            "sla_status": "On Track",
            "sla_attention_required": False,
            "evidence_count": 0,
            "created_at": datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 6, 5, 11, 0, tzinfo=timezone.utc),
        }

        summary = services.serialize_ticket_summary(row)

        self.assertEqual(summary["pendingLearningPlanTransferNotification"]["ticketId"], "KBC-000342")
        self.assertEqual(
            summary["pendingLearningPlanTransferNotification"]["fromTeam"],
            services.ASSIGNED_TEAM_SUPPORT_DESK,
        )
        self.assertEqual(
            summary["pendingLearningPlanTransferNotification"]["toTeam"],
            services.ASSIGNED_TEAM_LEARNING_PLAN,
        )
        self.assertEqual(
            summary["pendingLearningPlanTransferNotification"]["assignedAgentName"],
            "Omar Helmy",
        )

    def test_submit_coverage_tutor_request_sends_webhook_and_persists_request_metadata(self):
        ticket = {
            "id": 41,
            "public_id": "KBC-000041",
            "category": "Technical",
            "technical_subcategory": "Coverage",
            "inquiry": "Coverage request",
            "status": "Open",
            "status_reason": "",
            "assigned_team": "Unassigned",
            "assigned_agent_id": None,
            "sla_status": "Pending Review",
            "created_at": datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc),
            "conversation_id": None,
            "learner_name": "Ayman",
            "learner_email": "ayman@example.com",
            "metadata": {
                "technical_subcategory": "Coverage",
                "sla_attention_required": True,
                "sla_attention_reason": services.SLA_ATTENTION_REASON_COVERAGE_SESSION_DEADLINE,
                "coverage_sla_state": {
                    "stage": "warning",
                    "sessionStartAt": "2026-06-07T09:00:00+00:00",
                    "breachDeadlineAt": "2026-06-04T09:00:00+00:00",
                    "breachedAt": "2026-06-05T09:00:00+00:00",
                    "warningTriggeredAt": "2026-06-05T09:00:00+00:00",
                    "escalatedAt": None,
                },
                "admin_documentation": {
                    "inquiry": "Coverage request",
                    "ticketId": "KBC-000041",
                    "coverageCards": [
                        {
                            "id": "card-1",
                            "type": "tutor_choice",
                            "tutor": "Nathan",
                            "tutorEmail": "nathan@example.com",
                            "coach": "Mona Adel",
                            "coachEmail": "mona.adel@example.com",
                            "sessionDetails": "Module: APM",
                            "presentationFiles": [
                                {
                                    "id": "file-1",
                                    "name": "deck.pdf",
                                    "mimeType": "application/pdf",
                                    "size": 128,
                                    "dataUrl": "data:application/pdf;base64,ZmFrZQ==",
                                }
                            ],
                        }
                    ],
                },
            },
        }
        actor_row = {"id": 7, "username": "ahmed", "full_name": "Ahmed Hamamo", "email": "ahmed@example.com", "role": "admin"}
        mock_connection, cursor = self.build_mock_connection()

        with (
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "ensure_coverage_tutor_request_webhook_configured"),
            patch.object(services, "queue_coverage_tutor_request_webhook_delivery") as queue_webhook,
            patch.object(services, "resolve_next_sla_state", return_value=("On Track", False, None)),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event"),
            patch.object(services, "fetch_admin_ticket_detail", return_value={"ticket": {"id": "KBC-000041"}}),
        ):
            response = services.submit_coverage_tutor_request(
                "KBC-000041",
                {"actorUsername": "ahmed", "cardId": "card-1"},
            )

        self.assertEqual(response["ticket"]["id"], "KBC-000041")
        queue_webhook.assert_called_once()
        webhook_payload = queue_webhook.call_args.kwargs["payload"]
        self.assertEqual(webhook_payload["tutor"]["name"], "Nathan")
        self.assertEqual(webhook_payload["tutor"]["email"], "nathan@example.com")
        self.assertEqual(webhook_payload["coach"]["name"], "Mona Adel")
        self.assertEqual(webhook_payload["coach"]["email"], "mona.adel@example.com")
        self.assertEqual(len(webhook_payload["request"]["presentationFiles"]), 1)
        self.assertEqual(queue_webhook.call_args.kwargs["ticket_public_id"], "KBC-000041")
        self.assertEqual(queue_webhook.call_args.kwargs["card_id"], "card-1")

        update_params = cursor.execute.call_args_list[0].args[1]
        self.assertEqual(update_params[0], "Pending")
        self.assertEqual(update_params[1], "Tutor Requested")
        self.assertEqual(update_params[2], 7)
        self.assertEqual(update_params[3], "Support Desk")
        self.assertEqual(update_params[4], "On Track")
        persisted_metadata = json.loads(update_params[5])
        self.assertFalse(persisted_metadata["sla_attention_required"])
        self.assertIsNone(persisted_metadata["sla_attention_reason"])
        self.assertNotIn("coverage_sla_state", persisted_metadata)
        persisted_card = persisted_metadata["admin_documentation"]["coverageCards"][0]
        self.assertEqual(persisted_card["requestStatus"], "requested")
        self.assertEqual(persisted_card["requestSubmittedByAgentId"], 7)
        self.assertTrue(persisted_card["responseToken"])
        self.assertEqual(persisted_card["emailDeliveryStatus"], "pending")
        self.assertEqual(persisted_card["coach"], "Mona Adel")
        self.assertEqual(persisted_card["coachEmail"], "mona.adel@example.com")

    def test_record_coverage_tutor_request_email_delivery_status_marks_card_sent(self):
        token = services.build_coverage_tutor_email_delivery_callback_token("KBC-000041", "card-1", "response-token-1")
        ticket = {
            "id": 41,
            "public_id": "KBC-000041",
            "metadata": {
                "admin_documentation": {
                    "coverageCards": [
                        {
                            "id": "card-1",
                            "type": "tutor_choice",
                            "tutor": "Nathan",
                            "tutorEmail": "nathan@example.com",
                            "requestStatus": "requested",
                            "locked": True,
                            "responseToken": "response-token-1",
                            "emailDeliveryStatus": "pending",
                        }
                    ]
                }
            },
        }
        mock_connection, cursor = self.build_mock_connection()

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event") as insert_history_event,
        ):
            result = services.record_coverage_tutor_request_email_delivery_status(
                {
                    "ticketId": "KBC-000041",
                    "cardId": "card-1",
                    "status": "sent",
                    "messageId": "gmail-message-1",
                    "threadId": "gmail-thread-1",
                    "token": token,
                }
            )

        self.assertEqual(result["emailDeliveryStatus"], "sent")
        persisted_metadata = json.loads(cursor.execute.call_args.args[1][0])
        persisted_card = persisted_metadata["admin_documentation"]["coverageCards"][0]
        self.assertEqual(persisted_card["emailDeliveryStatus"], "sent")
        self.assertEqual(persisted_card["emailDeliveryMessageId"], "gmail-message-1")
        self.assertEqual(persisted_card["emailDeliveryThreadId"], "gmail-thread-1")
        self.assertEqual(persisted_card["emailDeliveryError"], "")
        insert_history_event.assert_called_once()
        self.assertEqual(insert_history_event.call_args.args[1], "coverage_tutor_request_email_sent")

    def test_record_coverage_tutor_request_email_delivery_status_marks_card_failed(self):
        token = services.build_coverage_tutor_email_delivery_callback_token("KBC-000041", "card-1", "response-token-1")
        ticket = {
            "id": 41,
            "public_id": "KBC-000041",
            "metadata": {
                "admin_documentation": {
                    "coverageCards": [
                        {
                            "id": "card-1",
                            "type": "tutor_choice",
                            "tutor": "Nathan",
                            "tutorEmail": "nathan@example.com",
                            "requestStatus": "requested",
                            "locked": True,
                            "responseToken": "response-token-1",
                            "emailDeliveryStatus": "pending",
                        }
                    ]
                }
            },
        }
        mock_connection, cursor = self.build_mock_connection()

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event") as insert_history_event,
        ):
            result = services.record_coverage_tutor_request_email_delivery_status(
                {
                    "ticketId": "KBC-000041",
                    "cardId": "card-1",
                    "status": "failed",
                    "error": "Gmail rejected the message",
                    "token": token,
                }
            )

        self.assertEqual(result["emailDeliveryStatus"], "failed")
        persisted_metadata = json.loads(cursor.execute.call_args.args[1][0])
        persisted_card = persisted_metadata["admin_documentation"]["coverageCards"][0]
        self.assertEqual(persisted_card["emailDeliveryStatus"], "failed")
        self.assertEqual(persisted_card["emailDeliveryError"], "Gmail rejected the message")
        insert_history_event.assert_called_once()
        self.assertEqual(insert_history_event.call_args.args[1], "coverage_tutor_request_email_failed")

    def test_retry_coverage_tutor_request_email_sets_pending_and_requeues_webhook(self):
        ticket = {
            "id": 41,
            "public_id": "KBC-000041",
            "category": "Technical",
            "technical_subcategory": "Coverage",
            "inquiry": "Coverage request",
            "status": "Pending",
            "status_reason": "Tutor Requested",
            "assigned_team": "Learning Plan Team",
            "assigned_agent_id": 7,
            "sla_status": "On Track",
            "is_archived": False,
            "learner_name": "Ayman",
            "learner_email": "ayman@example.com",
            "metadata": {
                "technical_subcategory": "Coverage",
                "admin_documentation": {
                    "coverageCards": [
                        {
                            "id": "card-1",
                            "type": "tutor_choice",
                            "tutor": "Nathan",
                            "tutorEmail": "nathan@example.com",
                            "sessionDetails": "Module: APM",
                            "requestStatus": "requested",
                            "locked": True,
                            "submittedAt": "2026-06-04T10:10:00Z",
                            "responseToken": "response-token-1",
                            "emailDeliveryStatus": "failed",
                            "emailDeliveryError": "Request timed out.",
                            "emailDeliveryRetryCount": 2,
                        }
                    ]
                },
            },
        }
        actor_row = {"id": 7, "username": "ahmed", "full_name": "Ahmed Hamamo", "email": "ahmed@example.com", "role": "admin"}
        mock_connection, cursor = self.build_mock_connection()

        with (
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "ensure_coverage_tutor_request_webhook_configured"),
            patch.object(services, "queue_coverage_tutor_request_webhook_delivery") as queue_webhook,
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event") as insert_history_event,
            patch.object(services, "fetch_admin_ticket_detail", return_value={"ticket": {"id": "KBC-000041"}}),
        ):
            response = services.retry_coverage_tutor_request_email(
                "KBC-000041",
                {
                    "actorUsername": "ahmed",
                    "cardId": "card-1",
                    "origin": "https://technicalsupport.kentbusinesscollege.net",
                },
            )

        self.assertEqual(response["ticket"]["id"], "KBC-000041")
        update_params = cursor.execute.call_args.args[1]
        persisted_metadata = json.loads(update_params[0])
        persisted_card = persisted_metadata["admin_documentation"]["coverageCards"][0]
        self.assertEqual(persisted_card["requestStatus"], "requested")
        self.assertEqual(persisted_card["emailDeliveryStatus"], "pending")
        self.assertEqual(persisted_card["emailDeliveryError"], "")
        self.assertEqual(persisted_card["emailDeliveryRetryCount"], 3)

        queue_webhook.assert_called_once()
        webhook_payload = queue_webhook.call_args.kwargs["payload"]
        self.assertEqual(webhook_payload["event"], "coverage_tutor_requested")
        self.assertEqual(webhook_payload["ticketId"], "KBC-000041")
        self.assertEqual(webhook_payload["cardId"], "card-1")
        self.assertEqual(webhook_payload["responseToken"], "response-token-1")
        self.assertEqual(webhook_payload["tutor"]["email"], "nathan@example.com")
        self.assertTrue(webhook_payload["emailDeliveryCallback"]["token"])

        insert_history_event.assert_called_once()
        self.assertEqual(insert_history_event.call_args.args[1], "coverage_tutor_request_email_retry")
        self.assertEqual(insert_history_event.call_args.args[3]["previousEmailDeliveryError"], "Request timed out.")

    def test_send_coverage_tutor_follow_up_files_rejects_failed_email_delivery(self):
        ticket = {
            "id": 45,
            "public_id": "KBC-000045",
            "category": "Technical",
            "technical_subcategory": "Coverage",
            "inquiry": "Coverage request",
            "status": "Pending",
            "status_reason": "Tutor Requested",
            "sla_status": "On Track",
            "is_archived": False,
            "learner_name": "Ayman",
            "learner_email": "ayman@example.com",
            "metadata": {
                "technical_subcategory": "Coverage",
                "admin_documentation": {
                    "coverageCards": [
                        {
                            "id": "card-1",
                            "type": "tutor_choice",
                            "tutor": "Nathan",
                            "tutorEmail": "nathan@example.com",
                            "sessionDetails": "Module: APM",
                            "requestStatus": "requested",
                            "locked": True,
                            "responseToken": "response-token-1",
                            "emailDeliveryStatus": "failed",
                            "emailDeliveryError": "Request timed out.",
                        }
                    ],
                },
            },
        }
        actor_row = {"id": 7, "username": "ahmed", "full_name": "Ahmed Hamamo", "email": "ahmed@example.com", "role": "admin"}

        with (
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "ensure_coverage_tutor_follow_up_webhook_configured"),
        ):
            with self.assertRaises(services.ApiError) as raised_error:
                services.send_coverage_tutor_follow_up_files(
                    "KBC-000045",
                    {
                        "actorUsername": "ahmed",
                        "cardId": "card-1",
                        "presentationFiles": [
                            {
                                "id": "file-1",
                                "name": "follow-up.pdf",
                                "mimeType": "application/pdf",
                                "size": 512,
                                "dataUrl": "data:application/pdf;base64,ZmFrZQ==",
                            }
                        ],
                    },
                )

        self.assertEqual(raised_error.exception.status_code, 409)
        self.assertEqual(
            raised_error.exception.message,
            "Send the tutor request e-mail successfully before sending follow-up files.",
        )

    def test_submit_coverage_tutor_request_uses_compact_card_payload_files(self):
        ticket = {
            "id": 44,
            "public_id": "KBC-000044",
            "category": "Technical",
            "technical_subcategory": "Coverage",
            "inquiry": "Coverage request",
            "status": "Open",
            "status_reason": "",
            "assigned_team": "Unassigned",
            "assigned_agent_id": None,
            "sla_status": "Pending Review",
            "created_at": datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc),
            "conversation_id": None,
            "learner_name": "Ayman",
            "learner_email": "ayman@example.com",
            "metadata": {"technical_subcategory": "Coverage", "admin_documentation": {}},
        }
        actor_row = {"id": 7, "username": "ahmed", "full_name": "Ahmed Hamamo", "email": "ahmed@example.com", "role": "admin"}
        card_payload = {
            "id": "card-compact",
            "type": "tutor_choice",
            "tutor": "Ray",
            "tutorEmail": "ray@example.com",
            "sessionDetails": "Module: PMP",
            "presentationFiles": [
                {
                    "id": "file-1",
                    "name": "deck.pdf",
                    "mimeType": "application/pdf",
                    "size": 128,
                    "dataUrl": "data:application/pdf;base64,ZmFrZQ==",
                }
            ],
        }
        lightweight_documentation = {
            "inquiry": "Coverage request",
            "ticketId": "KBC-000044",
            "coverageCards": [{**card_payload, "presentationFiles": []}],
        }
        mock_connection, cursor = self.build_mock_connection()

        with (
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "ensure_coverage_tutor_request_webhook_configured"),
            patch.object(services, "queue_coverage_tutor_request_webhook_delivery") as queue_webhook,
            patch.object(services, "resolve_next_sla_state", return_value=("On Track", False, None)),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event"),
            patch.object(services, "fetch_admin_ticket_detail", return_value={"ticket": {"id": "KBC-000044"}}),
        ):
            services.submit_coverage_tutor_request(
                "KBC-000044",
                {
                    "actorUsername": "ahmed",
                    "cardId": "card-compact",
                    "documentation": lightweight_documentation,
                    "card": card_payload,
                },
            )

        webhook_payload = queue_webhook.call_args.kwargs["payload"]
        self.assertEqual(len(webhook_payload["request"]["presentationFiles"]), 1)
        update_params = cursor.execute.call_args_list[0].args[1]
        persisted_metadata = json.loads(update_params[5])
        persisted_card = persisted_metadata["admin_documentation"]["coverageCards"][0]
        self.assertEqual(len(persisted_card["presentationFiles"]), 1)

    def test_submit_coverage_tutor_request_stores_uploaded_presentation_files(self):
        ticket = {
            "id": 45,
            "public_id": "KBC-000045",
            "category": "Technical",
            "technical_subcategory": "Coverage",
            "inquiry": "Coverage request",
            "status": "Open",
            "status_reason": "",
            "assigned_team": "Unassigned",
            "assigned_agent_id": None,
            "sla_status": "Pending Review",
            "created_at": datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc),
            "conversation_id": None,
            "learner_name": "Ayman",
            "learner_email": "ayman@example.com",
            "metadata": {"technical_subcategory": "Coverage", "admin_documentation": {}},
        }
        actor_row = {"id": 7, "username": "ahmed", "full_name": "Ahmed Hamamo", "email": "ahmed@example.com", "role": "admin"}
        card_payload = {
            "id": "card-uploaded",
            "type": "tutor_choice",
            "tutor": "Ray",
            "tutorEmail": "ray@example.com",
            "sessionDetails": "Module: PMP",
            "presentationFiles": [],
        }
        uploaded_file = SimpleUploadedFile(
            "coverage-plan.pptx",
            b"slides",
            content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
        stored_request_file = {
            "name": "coverage-plan.pptx",
            "mimeType": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "size": 6,
            "storageKey": "KBC-000045/2026/06/coverage-plan.pptx",
            "metadata": {"originalName": "coverage-plan.pptx", "storage": "local_filesystem"},
        }
        mock_connection, cursor = self.build_mock_connection()
        cursor.fetchone.return_value = (101,)

        with (
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "ensure_coverage_tutor_request_webhook_configured"),
            patch.object(services, "store_uploaded_ticket_attachments", return_value=[stored_request_file]),
            patch.object(services, "queue_coverage_tutor_request_webhook_delivery") as queue_webhook,
            patch.object(services, "resolve_next_sla_state", return_value=("On Track", False, None)),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event"),
            patch.object(services, "fetch_admin_ticket_detail", return_value={"ticket": {"id": "KBC-000045"}}),
        ):
            services.submit_coverage_tutor_request(
                "KBC-000045",
                {
                    "actorUsername": "ahmed",
                    "cardId": "card-uploaded",
                    "card": card_payload,
                    "documentation": {
                        "inquiry": "Coverage request",
                        "ticketId": "KBC-000045",
                        "coverageCards": [{**card_payload, "presentationFiles": []}],
                    },
                },
                uploaded_files=[uploaded_file],
            )

        queue_webhook.assert_called_once()
        webhook_payload = queue_webhook.call_args.kwargs["payload"]
        self.assertEqual(len(webhook_payload["request"]["presentationFiles"]), 1)
        self.assertEqual(webhook_payload["request"]["presentationFiles"][0]["attachmentId"], 101)
        self.assertEqual(
            webhook_payload["request"]["presentationFiles"][0]["storageUrl"],
            "/api/admin/tickets/KBC-000045/attachments/101/download",
        )

        insert_attachment_call = next(
            call
            for call in cursor.execute.call_args_list
            if "INSERT INTO ticket_attachments" in call.args[0]
        )
        self.assertIn("RETURNING id", insert_attachment_call.args[0])
        insert_metadata = json.loads(insert_attachment_call.args[1][5])
        self.assertEqual(insert_metadata["source"], "coverage_tutor_request")
        self.assertEqual(insert_metadata["coverageCardId"], "card-uploaded")

        update_call = next(
            call
            for call in cursor.execute.call_args_list
            if "UPDATE tickets" in call.args[0]
        )
        persisted_metadata = json.loads(update_call.args[1][5])
        persisted_card = persisted_metadata["admin_documentation"]["coverageCards"][0]
        self.assertEqual(len(persisted_card["presentationFiles"]), 1)
        self.assertEqual(persisted_card["presentationFiles"][0]["attachmentId"], 101)
        self.assertEqual(persisted_card["presentationFiles"][0]["storageUrl"], "/api/admin/tickets/KBC-000045/attachments/101/download")
        self.assertFalse(persisted_card["presentationFiles"][0]["dataUrl"])

    def test_upload_coverage_presentation_files_stores_pre_submit_metadata(self):
        ticket = {
            "id": 45,
            "public_id": "KBC-000045",
            "category": "Technical",
            "technical_subcategory": "Coverage",
            "is_archived": False,
        }
        actor_row = {"id": 7, "username": "ahmed", "full_name": "Ahmed Hamamo", "email": "ahmed@example.com", "role": "admin"}
        uploaded_file = SimpleUploadedFile(
            "coverage-plan.pptx",
            b"slides",
            content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
        stored_request_file = {
            "name": "coverage-plan.pptx",
            "mimeType": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "size": 6,
            "storageKey": "KBC-000045/2026/06/coverage-plan.pptx",
            "metadata": {"originalName": "coverage-plan.pptx", "storage": "local_filesystem"},
        }
        mock_connection, cursor = self.build_mock_connection()
        cursor.fetchone.return_value = (202,)

        with (
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "store_uploaded_ticket_attachments", return_value=[stored_request_file]) as store_files,
            patch.object(services, "connection", mock_connection),
        ):
            response = services.upload_coverage_presentation_files(
                "KBC-000045",
                {
                    "actorUsername": "ahmed",
                    "cardId": "card-uploaded",
                    "source": "coverage_tutor_request",
                },
                uploaded_files=[uploaded_file],
            )

        store_files.assert_called_once_with("KBC-000045", [uploaded_file])
        self.assertEqual(response["attachments"][0]["attachmentId"], 202)
        self.assertEqual(response["attachments"][0]["storageUrl"], "/api/admin/tickets/KBC-000045/attachments/202/download")
        insert_attachment_call = next(
            call
            for call in cursor.execute.call_args_list
            if "INSERT INTO ticket_attachments" in call.args[0]
        )
        insert_metadata = json.loads(insert_attachment_call.args[1][5])
        self.assertEqual(insert_metadata["source"], "coverage_tutor_request")
        self.assertEqual(insert_metadata["coverageCardId"], "card-uploaded")
        self.assertEqual(insert_metadata["uploadPhase"], "pre_submit")
        self.assertEqual(insert_metadata["uploadedByAgentId"], 7)

    def test_submit_coverage_tutor_request_stores_session_fallback_files(self):
        ticket = {
            "id": 46,
            "public_id": "KBC-000046",
            "category": "Technical",
            "technical_subcategory": "Coverage",
            "inquiry": "Coverage request",
            "status": "Open",
            "status_reason": "",
            "assigned_team": "Unassigned",
            "assigned_agent_id": None,
            "sla_status": "Pending Review",
            "created_at": datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc),
            "conversation_id": None,
            "learner_name": "Ayman",
            "learner_email": "ayman@example.com",
            "metadata": {"technical_subcategory": "Coverage", "admin_documentation": {}},
        }
        actor_row = {"id": 7, "username": "ahmed", "full_name": "Ahmed Hamamo", "email": "ahmed@example.com", "role": "admin"}
        card_payload = {
            "id": "card-session-uploaded",
            "type": "tutor_choice",
            "tutor": "Ray",
            "tutorEmail": "ray@example.com",
            "sessionDetails": "Module: PMP",
            "presentationFiles": [],
            "sessionFiles": [
                {
                    "id": "session-1",
                    "label": "Session 1",
                    "date": "Monday 06 Mar 2028",
                    "number": "1",
                    "subject": "test",
                    "attachments": [],
                }
            ],
        }
        uploaded_file = SimpleUploadedFile("session-plan.pdf", b"session", content_type="application/pdf")
        stored_request_file = {
            "name": "session-plan.pdf",
            "mimeType": "application/pdf",
            "size": 7,
            "storageKey": "KBC-000046/2026/06/session-plan.pdf",
            "metadata": {"originalName": "session-plan.pdf", "storage": "local_filesystem"},
        }
        mock_connection, cursor = self.build_mock_connection()
        cursor.fetchone.return_value = (303,)

        with (
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "ensure_coverage_tutor_request_webhook_configured"),
            patch.object(services, "store_uploaded_ticket_attachments", return_value=[stored_request_file]) as store_files,
            patch.object(services, "queue_coverage_tutor_request_webhook_delivery") as queue_webhook,
            patch.object(services, "resolve_next_sla_state", return_value=("On Track", False, None)),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event"),
            patch.object(services, "fetch_admin_ticket_detail", return_value={"ticket": {"id": "KBC-000046"}}),
        ):
            services.submit_coverage_tutor_request(
                "KBC-000046",
                {
                    "actorUsername": "ahmed",
                    "cardId": "card-session-uploaded",
                    "card": card_payload,
                    "documentation": {
                        "inquiry": "Coverage request",
                        "ticketId": "KBC-000046",
                        "coverageCards": [card_payload],
                    },
                    "sessionPresentationFileMetadata": [
                        {
                            "sessionId": "session-1",
                            "fileId": "local-session-file",
                            "label": "Session 1",
                            "date": "Monday 06 Mar 2028",
                            "number": "1",
                            "subject": "test",
                        }
                    ],
                },
                uploaded_session_files=[uploaded_file],
            )

        store_files.assert_called_once_with("KBC-000046", [uploaded_file])
        insert_attachment_call = next(
            call
            for call in cursor.execute.call_args_list
            if "INSERT INTO ticket_attachments" in call.args[0]
        )
        insert_metadata = json.loads(insert_attachment_call.args[1][5])
        self.assertEqual(insert_metadata["source"], "coverage_tutor_request")
        self.assertEqual(insert_metadata["coverageCardId"], "card-session-uploaded")
        self.assertEqual(insert_metadata["coverageSessionId"], "session-1")
        self.assertEqual(insert_metadata["uploadPhase"], "submit_fallback")

        webhook_payload = queue_webhook.call_args.kwargs["payload"]
        session_files = webhook_payload["request"]["sessionFiles"]
        self.assertEqual(len(session_files), 1)
        self.assertEqual(session_files[0]["attachments"][0]["attachmentId"], 303)

        update_call = next(
            call
            for call in cursor.execute.call_args_list
            if "UPDATE tickets" in call.args[0]
        )
        persisted_metadata = json.loads(update_call.args[1][5])
        persisted_card = persisted_metadata["admin_documentation"]["coverageCards"][0]
        self.assertEqual(persisted_card["sessionFiles"][0]["attachments"][0]["attachmentId"], 303)
        self.assertEqual(persisted_card["sessionFiles"][0]["attachments"][0]["id"], "local-session-file")

    def test_submit_coverage_tutor_request_falls_back_to_database_email_lookup(self):
        ticket = {
            "id": 42,
            "public_id": "KBC-000042",
            "category": "Technical",
            "technical_subcategory": "Coverage",
            "inquiry": "Coverage request",
            "status": "Open",
            "status_reason": "",
            "assigned_team": "Unassigned",
            "assigned_agent_id": None,
            "sla_status": "Pending Review",
            "created_at": datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc),
            "conversation_id": None,
            "learner_name": "Ayman",
            "learner_email": "ayman@example.com",
            "metadata": {
                "technical_subcategory": "Coverage",
                "admin_documentation": {
                    "inquiry": "Coverage request",
                    "ticketId": "KBC-000042",
                    "coverageCards": [
                        {
                            "id": "card-1",
                            "type": "tutor_choice",
                            "tutor": "Andrew",
                            "tutorEmail": "",
                            "sessionDetails": "Module: APM",
                            "presentationFiles": [],
                        }
                    ],
                },
            },
        }
        actor_row = {"id": 7, "username": "ahmed", "full_name": "Ahmed Hamamo", "email": "ahmed@example.com", "role": "admin"}
        mock_connection, cursor = self.build_mock_connection()

        with (
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "get_coverage_tutor_email", return_value="andrew.millington@kentbusinesscollege.com") as get_coverage_tutor_email,
            patch.object(services, "ensure_coverage_tutor_request_webhook_configured"),
            patch.object(services, "queue_coverage_tutor_request_webhook_delivery") as queue_webhook,
            patch.object(services, "resolve_next_sla_state", return_value=("On Track", False, None)),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event"),
            patch.object(services, "fetch_admin_ticket_detail", return_value={"ticket": {"id": "KBC-000042"}}),
        ):
            response = services.submit_coverage_tutor_request(
                "KBC-000042",
                {"actorUsername": "ahmed", "cardId": "card-1"},
            )

        self.assertEqual(response["ticket"]["id"], "KBC-000042")
        get_coverage_tutor_email.assert_called_once_with("Andrew")
        webhook_payload = queue_webhook.call_args.kwargs["payload"]
        self.assertEqual(webhook_payload["tutor"]["email"], "andrew.millington@kentbusinesscollege.com")
        update_params = cursor.execute.call_args_list[0].args[1]
        self.assertEqual(update_params[2], 7)
        self.assertEqual(update_params[3], "Support Desk")
        persisted_metadata = json.loads(update_params[5])
        persisted_card = persisted_metadata["admin_documentation"]["coverageCards"][0]
        self.assertEqual(persisted_card["tutorEmail"], "andrew.millington@kentbusinesscollege.com")

    def test_submit_coverage_tutor_request_falls_back_to_aptem_owner_email_for_recipient(self):
        ticket = {
            "id": 143,
            "public_id": "KBC-000143",
            "category": "Technical",
            "technical_subcategory": "Coverage",
            "inquiry": "Coverage request",
            "status": "Open",
            "status_reason": "",
            "assigned_team": "Unassigned",
            "assigned_agent_id": None,
            "sla_status": "Pending Review",
            "created_at": datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc),
            "conversation_id": None,
            "learner_name": "Ayman",
            "learner_email": "ayman@example.com",
            "metadata": {
                "technical_subcategory": "Coverage",
                "admin_documentation": {
                    "inquiry": "Coverage request",
                    "ticketId": "KBC-000143",
                    "coverageCards": [
                        {
                            "id": "card-1",
                            "type": "tutor_choice",
                            "tutor": "Mona Adel",
                            "tutorEmail": "",
                            "sessionDetails": "Module: APM",
                            "presentationFiles": [],
                        }
                    ],
                },
            },
        }
        actor_row = {"id": 7, "username": "ahmed", "full_name": "Ahmed Hamamo", "email": "ahmed@example.com", "role": "admin"}
        mock_connection, cursor = self.build_mock_connection()

        with (
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "get_coverage_tutor_email", return_value="") as get_coverage_tutor_email,
            patch.object(services, "get_coverage_coach_email", return_value="mona.adel@kentbusinesscollege.com") as get_coverage_coach_email,
            patch.object(services, "ensure_coverage_tutor_request_webhook_configured"),
            patch.object(services, "queue_coverage_tutor_request_webhook_delivery") as queue_webhook,
            patch.object(services, "resolve_next_sla_state", return_value=("On Track", False, None)),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event"),
            patch.object(services, "fetch_admin_ticket_detail", return_value={"ticket": {"id": "KBC-000143"}}),
        ):
            response = services.submit_coverage_tutor_request(
                "KBC-000143",
                {"actorUsername": "ahmed", "cardId": "card-1"},
            )

        self.assertEqual(response["ticket"]["id"], "KBC-000143")
        get_coverage_tutor_email.assert_called_once_with("Mona Adel")
        get_coverage_coach_email.assert_called_once_with("Mona Adel")
        webhook_payload = queue_webhook.call_args.kwargs["payload"]
        self.assertEqual(webhook_payload["tutor"]["email"], "mona.adel@kentbusinesscollege.com")
        update_params = cursor.execute.call_args_list[0].args[1]
        persisted_metadata = json.loads(update_params[5])
        persisted_card = persisted_metadata["admin_documentation"]["coverageCards"][0]
        self.assertEqual(persisted_card["tutorEmail"], "mona.adel@kentbusinesscollege.com")

    def test_submit_coverage_tutor_request_falls_back_to_database_coach_email_lookup(self):
        ticket = {
            "id": 142,
            "public_id": "KBC-000142",
            "category": "Technical",
            "technical_subcategory": "Coverage",
            "inquiry": "Coverage request",
            "status": "Open",
            "status_reason": "",
            "assigned_team": "Unassigned",
            "assigned_agent_id": None,
            "sla_status": "Pending Review",
            "created_at": datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc),
            "conversation_id": None,
            "learner_name": "Ayman",
            "learner_email": "ayman@example.com",
            "metadata": {
                "technical_subcategory": "Coverage",
                "admin_documentation": {
                    "inquiry": "Coverage request",
                    "ticketId": "KBC-000142",
                    "coverageCards": [
                        {
                            "id": "card-1",
                            "type": "tutor_choice",
                            "tutor": "Andrew",
                            "tutorEmail": "andrew@example.com",
                            "coach": "Mona Adel",
                            "coachEmail": "",
                            "sessionDetails": "Module: APM",
                            "presentationFiles": [],
                        }
                    ],
                },
            },
        }
        actor_row = {"id": 7, "username": "ahmed", "full_name": "Ahmed Hamamo", "email": "ahmed@example.com", "role": "admin"}
        mock_connection, cursor = self.build_mock_connection()

        with (
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "get_coverage_coach_email", return_value="mona.adel@kentbusinesscollege.com") as get_coverage_coach_email,
            patch.object(services, "ensure_coverage_tutor_request_webhook_configured"),
            patch.object(services, "queue_coverage_tutor_request_webhook_delivery") as queue_webhook,
            patch.object(services, "resolve_next_sla_state", return_value=("On Track", False, None)),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event"),
            patch.object(services, "fetch_admin_ticket_detail", return_value={"ticket": {"id": "KBC-000142"}}),
        ):
            response = services.submit_coverage_tutor_request(
                "KBC-000142",
                {"actorUsername": "ahmed", "cardId": "card-1"},
            )

        self.assertEqual(response["ticket"]["id"], "KBC-000142")
        get_coverage_coach_email.assert_called_once_with("Mona Adel")
        webhook_payload = queue_webhook.call_args.kwargs["payload"]
        self.assertEqual(webhook_payload["coach"]["email"], "mona.adel@kentbusinesscollege.com")
        update_params = cursor.execute.call_args_list[0].args[1]
        persisted_metadata = json.loads(update_params[5])
        persisted_card = persisted_metadata["admin_documentation"]["coverageCards"][0]
        self.assertEqual(persisted_card["coachEmail"], "mona.adel@kentbusinesscollege.com")

    def test_submit_coverage_tutor_request_clears_previous_latest_response_notification(self):
        ticket = {
            "id": 43,
            "public_id": "KBC-000043",
            "category": "Technical",
            "technical_subcategory": "Coverage",
            "inquiry": "Coverage request",
            "status": "Pending",
            "status_reason": "Tutor Refused",
            "assigned_team": "Unassigned",
            "assigned_agent_id": None,
            "sla_status": "On Track",
            "created_at": datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc),
            "conversation_id": None,
            "learner_name": "Ayman",
            "learner_email": "ayman@example.com",
            "metadata": {
                "technical_subcategory": "Coverage",
                "latest_coverage_tutor_response": {
                    "outcome": "rejected",
                    "toAgentId": 7,
                    "toAgentName": "Ahmed Hamamo",
                    "toAgentUsername": "ahmed",
                    "ticketId": "KBC-000043",
                    "tutor": "Nathan",
                    "tutorEmail": "nathan@example.com",
                    "cardId": "card-1-reply-rejected",
                    "relatedTutorChoiceCardId": "card-1",
                    "requestedAt": "2026-06-04T10:10:00Z",
                    "respondedAt": "2026-06-04T10:15:00Z",
                    "sessionDetails": "Module: APM",
                    "replyText": "",
                    "sessionStartAt": None,
                    "sessionEndAt": None,
                    "requesterAcknowledged": False,
                },
                "admin_documentation": {
                    "inquiry": "Coverage request",
                    "ticketId": "KBC-000043",
                    "coverageCards": [
                        {
                            "id": "card-1",
                            "type": "tutor_choice",
                            "tutor": "Nathan",
                            "tutorEmail": "nathan@example.com",
                            "sessionDetails": "Module: APM",
                            "presentationFiles": [],
                        }
                    ],
                },
            },
        }
        actor_row = {"id": 7, "username": "ahmed", "full_name": "Ahmed Hamamo", "email": "ahmed@example.com", "role": "admin"}
        mock_connection, cursor = self.build_mock_connection()

        with (
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "ensure_coverage_tutor_request_webhook_configured"),
            patch.object(services, "queue_coverage_tutor_request_webhook_delivery"),
            patch.object(services, "resolve_next_sla_state", return_value=("On Track", False, None)),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event"),
            patch.object(services, "fetch_admin_ticket_detail", return_value={"ticket": {"id": "KBC-000043"}}),
        ):
            response = services.submit_coverage_tutor_request(
                "KBC-000043",
                {"actorUsername": "ahmed", "cardId": "card-1"},
            )

        self.assertEqual(response["ticket"]["id"], "KBC-000043")
        update_params = cursor.execute.call_args_list[0].args[1]
        persisted_metadata = json.loads(update_params[5])
        self.assertNotIn("latest_coverage_tutor_response", persisted_metadata)

    def test_send_coverage_tutor_follow_up_files_sends_only_new_files_and_preserves_ticket_status(self):
        ticket = {
            "id": 45,
            "public_id": "KBC-000045",
            "category": "Technical",
            "technical_subcategory": "Coverage",
            "inquiry": "Coverage request",
            "status": "Pending",
            "status_reason": "Tutor Requested",
            "sla_status": "On Track",
            "is_archived": False,
            "learner_name": "Ayman",
            "learner_email": "ayman@example.com",
            "tutor_emails": {
                "Nathan@Example.com": {
                    "sent_at": "2026-06-04T10:11:00+00:00",
                    "gmail_thread_id": "gmail-thread-1",
                    "gmail_message_id": "gmail-message-1",
                },
            },
            "metadata": {
                "technical_subcategory": "Coverage",
                "admin_documentation": {
                    "inquiry": "Coverage request",
                    "ticketId": "KBC-000045",
                    "coverageCards": [
                        {
                            "id": "card-1",
                            "type": "tutor_choice",
                            "tutor": "Nathan",
                            "tutorEmail": "nathan@example.com",
                            "sessionDetails": "Module: APM",
                            "requestStatus": "requested",
                            "locked": True,
                            "responseToken": "response-token-1",
                            "submittedAt": "2026-06-04T10:10:00Z",
                            "presentationFiles": [
                                {
                                    "id": "file-1",
                                    "name": "deck.pdf",
                                    "mimeType": "application/pdf",
                                    "size": 128,
                                    "dataUrl": "data:application/pdf;base64,ZmFrZQ==",
                                }
                            ],
                        }
                    ],
                },
            },
        }
        actor_row = {"id": 7, "username": "ahmed", "full_name": "Ahmed Hamamo", "email": "ahmed@example.com", "role": "admin"}
        uploaded_file = SimpleUploadedFile(
            "slides-2.pptx",
            b"follow-up",
            content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
        stored_follow_up_file = {
            "name": "slides-2.pptx",
            "mimeType": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "size": 9,
            "storageKey": "KBC-000045/2026/06/slides-2.pptx",
            "metadata": {"originalName": "slides-2.pptx", "storage": "local_filesystem"},
        }
        mock_connection, cursor = self.build_mock_connection()
        cursor.fetchone.return_value = (101,)

        with (
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "ensure_coverage_tutor_follow_up_webhook_configured"),
            patch.object(services, "store_uploaded_ticket_attachments", return_value=[stored_follow_up_file]),
            patch.object(services, "queue_coverage_tutor_follow_up_webhook_delivery") as queue_webhook,
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event") as insert_history,
            patch.object(services, "fetch_admin_ticket_detail", return_value={"ticket": {"id": "KBC-000045"}}),
        ):
            response = services.send_coverage_tutor_follow_up_files(
                "KBC-000045",
                {
                    "actorUsername": "ahmed",
                    "cardId": "card-1",
                },
                uploaded_files=[uploaded_file],
            )

        self.assertEqual(response["ticket"]["id"], "KBC-000045")
        queue_webhook.assert_called_once()
        webhook_payload = queue_webhook.call_args.kwargs["payload"]
        self.assertEqual(webhook_payload["event"], "coverage_tutor_follow_up")
        self.assertEqual(webhook_payload["responseToken"], "response-token-1")
        self.assertEqual(webhook_payload["tutorName"], "Nathan")
        self.assertEqual(webhook_payload["tutorEmail"], "nathan@example.com")
        self.assertEqual(webhook_payload["gmailThreadId"], "gmail-thread-1")
        self.assertEqual(webhook_payload["gmailMessageId"], "gmail-message-1")
        self.assertEqual(webhook_payload["attachments"][0]["attachmentId"], 101)
        self.assertEqual(webhook_payload["attachments"][0]["storageKey"], "KBC-000045/2026/06/slides-2.pptx")
        self.assertEqual(webhook_payload["attachments"][0]["storageUrl"], "/api/admin/tickets/KBC-000045/attachments/101/download")
        self.assertNotIn("dataUrl", {key: value for key, value in webhook_payload["attachments"][0].items() if value})
        self.assertEqual(webhook_payload["request"]["requestStatus"], "requested")
        self.assertEqual(
            webhook_payload["originalEmail"],
            {
                "recipientEmail": "nathan@example.com",
                "sentAt": "2026-06-04T10:11:00+00:00",
                "gmailThreadId": "gmail-thread-1",
                "gmailMessageId": "gmail-message-1",
                "canReplyToExistingThread": True,
            },
        )
        self.assertEqual(webhook_payload["followUp"]["fileCount"], 1)
        self.assertEqual(len(webhook_payload["followUp"]["presentationFiles"]), 1)
        self.assertEqual(len(webhook_payload["request"]["presentationFiles"]), 2)

        insert_attachment_call = next(
            call
            for call in cursor.execute.call_args_list
            if "INSERT INTO ticket_attachments" in call.args[0]
        )
        self.assertIn("RETURNING id", insert_attachment_call.args[0])
        update_call = next(
            call
            for call in cursor.execute.call_args_list
            if "UPDATE tickets" in call.args[0]
        )
        update_sql = update_call.args[0]
        update_params = update_call.args[1]
        self.assertIn("SET sla_status = %s", update_sql)
        self.assertIn("metadata = %s::jsonb", update_sql)
        self.assertEqual(update_params[0], "On Track")
        persisted_metadata = json.loads(update_params[1])
        persisted_card = persisted_metadata["admin_documentation"]["coverageCards"][0]
        self.assertEqual(persisted_card["requestStatus"], "requested")
        self.assertEqual(len(persisted_card["presentationFiles"]), 2)
        self.assertEqual(persisted_card["presentationFiles"][1]["storageUrl"], "/api/admin/tickets/KBC-000045/attachments/101/download")
        self.assertFalse(persisted_card["presentationFiles"][1]["dataUrl"])
        self.assertEqual(insert_history.call_args.args[1], "coverage_tutor_follow_up_sent")

    def test_send_coverage_tutor_follow_up_files_allows_accepted_closed_ticket(self):
        ticket = {
            "id": 46,
            "public_id": "KBC-000046",
            "category": "Technical",
            "technical_subcategory": "Coverage",
            "inquiry": "Coverage request",
            "status": "Closed",
            "status_reason": "Tutor Accepted",
            "sla_status": "On Track",
            "is_archived": False,
            "learner_name": "Ayman",
            "learner_email": "ayman@example.com",
            "metadata": {
                "technical_subcategory": "Coverage",
                "admin_documentation": {
                    "inquiry": "Coverage request",
                    "ticketId": "KBC-000046",
                    "coverageCards": [
                        {
                            "id": "card-accepted",
                            "type": "tutor_choice",
                            "tutor": "Nathan",
                            "tutorEmail": "nathan@example.com",
                            "sessionDetails": "Module: APM",
                            "requestStatus": "accepted",
                            "locked": True,
                            "submittedAt": "2026-06-04T10:10:00Z",
                            "respondedAt": "2026-06-04T10:20:00Z",
                            "presentationFiles": [],
                        }
                    ],
                },
            },
        }
        actor_row = {"id": 7, "username": "ahmed", "full_name": "Ahmed Hamamo", "email": "ahmed@example.com", "role": "admin"}
        mock_connection, cursor = self.build_mock_connection()

        with (
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "ensure_coverage_tutor_follow_up_webhook_configured"),
            patch.object(services, "queue_coverage_tutor_follow_up_webhook_delivery") as queue_webhook,
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event"),
            patch.object(services, "fetch_admin_ticket_detail", return_value={"ticket": {"id": "KBC-000046"}}),
        ):
            response = services.send_coverage_tutor_follow_up_files(
                "KBC-000046",
                {
                    "actorUsername": "ahmed",
                    "cardId": "card-accepted",
                    "presentationFiles": [
                        {
                            "id": "file-accepted-1",
                            "name": "accepted-follow-up.pdf",
                            "mimeType": "application/pdf",
                            "size": 512,
                            "dataUrl": "data:application/pdf;base64,YWNjZXB0ZWQ=",
                        }
                    ],
                },
            )

        self.assertEqual(response["ticket"]["id"], "KBC-000046")
        webhook_payload = queue_webhook.call_args.kwargs["payload"]
        self.assertEqual(webhook_payload["request"]["requestStatus"], "accepted")
        self.assertEqual(webhook_payload["followUp"]["fileCount"], 1)
        update_params = cursor.execute.call_args_list[0].args[1]
        self.assertEqual(update_params[0], "On Track")
        persisted_metadata = json.loads(update_params[1])
        persisted_card = persisted_metadata["admin_documentation"]["coverageCards"][0]
        self.assertEqual(persisted_card["requestStatus"], "accepted")
        self.assertEqual(len(persisted_card["presentationFiles"]), 1)

    def test_send_coverage_tutor_follow_up_files_rejects_refused_request(self):
        ticket = {
            "id": 47,
            "public_id": "KBC-000047",
            "category": "Technical",
            "technical_subcategory": "Coverage",
            "inquiry": "Coverage request",
            "status": "Pending",
            "status_reason": "Tutor Rejected",
            "sla_status": "On Track",
            "is_archived": False,
            "learner_name": "Ayman",
            "learner_email": "ayman@example.com",
            "metadata": {
                "technical_subcategory": "Coverage",
                "admin_documentation": {
                    "inquiry": "Coverage request",
                    "ticketId": "KBC-000047",
                    "coverageCards": [
                        {
                            "id": "card-refused",
                            "type": "tutor_choice",
                            "tutor": "Nathan",
                            "tutorEmail": "nathan@example.com",
                            "sessionDetails": "Module: APM",
                            "requestStatus": "refused",
                            "locked": True,
                            "submittedAt": "2026-06-04T10:10:00Z",
                            "respondedAt": "2026-06-04T10:20:00Z",
                            "presentationFiles": [],
                        }
                    ],
                },
            },
        }
        actor_row = {"id": 7, "username": "ahmed", "full_name": "Ahmed Hamamo", "email": "ahmed@example.com", "role": "admin"}

        with (
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "ensure_coverage_tutor_follow_up_webhook_configured"),
        ):
            with self.assertRaises(services.ApiError) as raised_error:
                services.send_coverage_tutor_follow_up_files(
                    "KBC-000047",
                    {
                        "actorUsername": "ahmed",
                        "cardId": "card-refused",
                        "presentationFiles": [
                            {
                                "id": "file-refused-1",
                                "name": "refused-follow-up.pdf",
                                "mimeType": "application/pdf",
                                "size": 512,
                                "dataUrl": "data:application/pdf;base64,cmVmdXNlZA==",
                            }
                        ],
                    },
                )

        self.assertEqual(raised_error.exception.status_code, 409)
        self.assertEqual(
            raised_error.exception.message,
            "Follow-up files can only be sent for requested or accepted tutor requests.",
        )

    def test_process_coverage_tutor_response_adds_reply_card_and_updates_status_reason(self):
        ticket = {
            "id": 52,
            "public_id": "KBC-000052",
            "status": "Pending",
            "status_reason": "Tutor Requested",
            "technical_subcategory": "Coverage",
            "assigned_team": "Unassigned",
            "assigned_agent_id": None,
            "sla_status": "On Track",
            "created_at": datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc),
            "conversation_id": None,
            "metadata": {
                "technical_subcategory": "Coverage",
                "admin_documentation": {
                    "ticketId": "KBC-000052",
                    "coverageCards": [
                        {
                            "id": "card-1",
                            "type": "tutor_choice",
                            "tutor": "Nathan",
                            "tutorEmail": "nathan@example.com",
                            "sessionDetails": "Module: APM",
                            "requestStatus": "requested",
                            "submittedAt": "2026-06-04T10:10:00Z",
                            "responseToken": "token-1",
                            "requestSubmittedByAgentId": 7,
                            "requestSubmittedByAgentName": "Ahmed Hamamo",
                            "requestSubmittedByAgentUsername": "ahmed",
                            "locked": True,
                        }
                    ],
                },
            },
        }
        mock_connection, cursor = self.build_mock_connection()

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "resolve_next_sla_state", return_value=("On Track", False, None)),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event"),
            patch.object(services, "notify_coverage_tutor_response_mail_webhook") as notify_response_mail,
            patch.object(services, "fetch_admin_ticket_detail", return_value={"ticket": {"id": "KBC-000052"}}),
        ):
            response = services.process_coverage_tutor_response(
                {
                    "ticketId": "KBC-000052",
                    "responseToken": "token-1",
                    "outcome": "accepted",
                    "sessionDetails": "Friday 09:00 - 11:00",
                    "sessionStartAt": "2026-06-04T09:00:00Z",
                    "sessionEndAt": "2026-06-04T11:00:00Z",
                    "message": "Approved by tutor",
                }
            )

        self.assertEqual(response["ticket"]["id"], "KBC-000052")
        update_params = cursor.execute.call_args_list[0].args[1]
        self.assertEqual(update_params[0], "Closed")
        self.assertEqual(update_params[1], "Tutor Accepted")
        persisted_metadata = json.loads(update_params[3])
        self.assertEqual(persisted_metadata["latest_coverage_tutor_response"]["outcome"], "accepted")
        persisted_cards = persisted_metadata["admin_documentation"]["coverageCards"]
        self.assertEqual(persisted_cards[0]["requestStatus"], "accepted")
        self.assertEqual(persisted_cards[1]["type"], "tutor_reply")
        self.assertEqual(persisted_cards[1]["replyOutcome"], "accepted")
        self.assertEqual(persisted_cards[1]["sessionDetails"], "Friday 09:00 - 11:00")
        notify_response_mail.assert_called_once()
        self.assertEqual(notify_response_mail.call_args.args[0], 52)
        webhook_payload = notify_response_mail.call_args.args[1]
        self.assertEqual(webhook_payload["event"], "coverage_tutor_accepted")
        self.assertEqual(webhook_payload["ticket"]["id"], "KBC-000052")
        self.assertEqual(webhook_payload["ticket"]["statusReason"], "Tutor Accepted")
        self.assertEqual(webhook_payload["response"]["outcome"], "accepted")
        self.assertEqual(webhook_payload["tutor"]["email"], "nathan@example.com")

    def test_process_coverage_tutor_response_sends_refusal_mail_webhook_on_rejection(self):
        ticket = {
            "id": 53,
            "public_id": "KBC-000053",
            "status": "Pending",
            "status_reason": "Tutor Requested",
            "technical_subcategory": "Coverage",
            "assigned_team": "Unassigned",
            "assigned_agent_id": None,
            "sla_status": "On Track",
            "created_at": datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc),
            "conversation_id": None,
            "metadata": {
                "technical_subcategory": "Coverage",
                "sla_attention_required": True,
                "sla_attention_reason": services.SLA_ATTENTION_REASON_COVERAGE_SESSION_DEADLINE,
                "coverage_sla_state": {
                    "stage": "warning",
                    "sessionStartAt": "2026-06-07T09:00:00+00:00",
                    "breachDeadlineAt": "2026-06-04T09:00:00+00:00",
                    "breachedAt": "2026-06-05T09:00:00+00:00",
                    "warningTriggeredAt": "2026-06-05T09:00:00+00:00",
                    "escalatedAt": None,
                },
                "admin_documentation": {
                    "ticketId": "KBC-000053",
                    "coverageCards": [
                        {
                            "id": "card-1",
                            "type": "tutor_choice",
                            "tutor": "Nathan",
                            "tutorEmail": "nathan@example.com",
                            "sessionDetails": "Module: APM\nSessions:\n1. Friday 09:00 - 11:00",
                            "presentationFiles": [{"name": "slides.pdf", "size": 77}],
                            "requestStatus": "requested",
                            "submittedAt": "2026-06-04T10:10:00Z",
                            "responseToken": "token-1",
                            "requestSubmittedByAgentId": 7,
                            "requestSubmittedByAgentName": "Ahmed Hamamo",
                            "requestSubmittedByAgentUsername": "ahmed",
                            "locked": True,
                        }
                    ],
                },
            },
        }
        mock_connection, cursor = self.build_mock_connection()

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "resolve_next_sla_state", return_value=("On Track", False, None)),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event"),
            patch.object(services, "notify_coverage_tutor_response_mail_webhook") as notify_response_mail,
            patch.object(services, "fetch_admin_ticket_detail", return_value={"ticket": {"id": "KBC-000053"}}),
        ):
            response = services.process_coverage_tutor_response(
                {
                    "ticketId": "KBC-000053",
                    "responseToken": "token-1",
                    "outcome": "refuse",
                    "message": "Unavailable for this slot",
                }
            )

        self.assertEqual(response["ticket"]["id"], "KBC-000053")
        update_params = cursor.execute.call_args_list[0].args[1]
        self.assertEqual(update_params[0], "Pending")
        self.assertEqual(update_params[1], "Tutor Rejected")
        self.assertEqual(update_params[2], "On Track")
        persisted_metadata = json.loads(update_params[3])
        self.assertFalse(persisted_metadata["sla_attention_required"])
        self.assertIsNone(persisted_metadata["sla_attention_reason"])
        self.assertNotIn("coverage_sla_state", persisted_metadata)
        persisted_cards = persisted_metadata["admin_documentation"]["coverageCards"]
        self.assertEqual(persisted_metadata["latest_coverage_tutor_response"]["outcome"], "rejected")
        self.assertEqual(persisted_cards[0]["requestStatus"], "refused")
        self.assertEqual(persisted_cards[1]["replyOutcome"], "refused")
        notify_response_mail.assert_called_once()
        self.assertEqual(notify_response_mail.call_args.args[0], 53)
        webhook_payload = notify_response_mail.call_args.args[1]
        self.assertEqual(webhook_payload["event"], "coverage_tutor_refused")
        self.assertEqual(webhook_payload["ticket"]["id"], "KBC-000053")
        self.assertEqual(webhook_payload["ticket"]["statusReason"], "Tutor Rejected")
        self.assertEqual(webhook_payload["response"]["outcome"], "rejected")
        self.assertEqual(webhook_payload["tutor"]["email"], "nathan@example.com")
        self.assertEqual(webhook_payload["requestedBy"]["agentUsername"], "ahmed")

    def test_process_coverage_tutor_response_ignores_second_response_for_same_card(self):
        ticket = {
            "id": 52,
            "public_id": "KBC-000052",
            "status": "Closed",
            "status_reason": "Tutor Accepted",
            "technical_subcategory": "Coverage",
            "assigned_team": "Unassigned",
            "assigned_agent_id": None,
            "sla_status": "On Track",
            "created_at": datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc),
            "conversation_id": None,
            "metadata": {
                "technical_subcategory": "Coverage",
                "latest_coverage_tutor_response": {
                    "ticketId": "KBC-000052",
                    "cardId": "card-1",
                    "responseToken": "token-1",
                    "outcome": "accepted",
                    "respondedAt": "2026-06-04T10:20:00Z",
                },
                "admin_documentation": {
                    "ticketId": "KBC-000052",
                    "coverageCards": [
                        {
                            "id": "card-1",
                            "type": "tutor_choice",
                            "tutor": "Nathan",
                            "tutorEmail": "nathan@example.com",
                            "sessionDetails": "Module: APM",
                            "requestStatus": "accepted",
                            "replyOutcome": "accepted",
                            "submittedAt": "2026-06-04T10:10:00Z",
                            "respondedAt": "2026-06-04T10:20:00Z",
                            "responseToken": "token-1",
                            "requestSubmittedByAgentId": 7,
                            "requestSubmittedByAgentName": "Ahmed Hamamo",
                            "requestSubmittedByAgentUsername": "ahmed",
                            "locked": True,
                        },
                        {
                            "id": "reply-1",
                            "type": "tutor_reply",
                            "tutor": "Nathan",
                            "tutorEmail": "nathan@example.com",
                            "replyOutcome": "accepted",
                            "requestStatus": "accepted",
                            "relatedTutorChoiceCardId": "card-1",
                            "respondedAt": "2026-06-04T10:20:00Z",
                            "sessionDetails": "Friday 09:00 - 11:00",
                            "locked": True,
                        },
                    ],
                },
            },
        }
        mock_connection, _cursor = self.build_mock_connection()

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event") as insert_history_event,
            patch.object(services, "fetch_admin_ticket_detail", return_value={"ticket": {"id": "KBC-000052"}}),
        ):
            response = services.process_coverage_tutor_response(
                {
                    "ticketId": "KBC-000052",
                    "cardId": "card-1",
                    "responseToken": "token-1",
                    "outcome": "refuse",
                }
            )

        self.assertTrue(response["coverageTutorResponseAlreadyRecorded"])
        self.assertEqual(response["recordedCoverageTutorResponseOutcome"], "accepted")
        self.assertEqual(response["requestedCoverageTutorResponseOutcome"], "rejected")
        mock_connection.cursor.assert_not_called()
        insert_history_event.assert_not_called()

    def test_acknowledge_coverage_tutor_response_uses_database_derived_response(self):
        ticket = {
            "id": 62,
            "public_id": "KBC-000062",
            "status_reason": "Tutor Accepted",
            "updated_at": datetime(2026, 6, 4, 11, 0, tzinfo=timezone.utc),
            "metadata": {
                "technical_subcategory": "Coverage",
                "admin_documentation": {
                    "ticketId": "KBC-000062",
                    "coverageCards": [
                        {
                            "id": "card-1",
                            "type": "tutor_choice",
                            "tutor": "Nathan",
                            "tutorEmail": "nathan@example.com",
                            "sessionDetails": "Friday 09:00 - 11:00",
                            "requestStatus": "requested",
                            "submittedAt": "2026-06-04T10:10:00Z",
                            "requestSubmittedByAgentId": 7,
                            "requestSubmittedByAgentName": "Ahmed Hamamo",
                            "requestSubmittedByAgentUsername": "ahmed",
                            "locked": True,
                        }
                    ],
                },
            },
        }
        actor_row = {"id": 7, "username": "ahmed", "full_name": "Ahmed Hamamo", "email": "ahmed@example.com", "role": "admin"}
        mock_connection, cursor = self.build_mock_connection()

        with (
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "fetch_admin_ticket_detail", return_value={"ticket": {"id": "KBC-000062"}}),
        ):
            response = services.acknowledge_coverage_tutor_response(
                "KBC-000062",
                {"actorUsername": "ahmed"},
            )

        self.assertEqual(response["ticket"]["id"], "KBC-000062")
        update_params = cursor.execute.call_args.args[1]
        persisted_metadata = json.loads(update_params[0])
        self.assertTrue(persisted_metadata["latest_coverage_tutor_response"]["requesterAcknowledged"])
        self.assertEqual(
            persisted_metadata["admin_documentation"]["coverageCards"][1]["type"],
            "tutor_reply",
        )

    def test_acknowledge_coverage_ticket_notification_clears_pending_metadata(self):
        ticket = {
            "id": 65,
            "public_id": "KBC-000065",
            "metadata": {
                "technical_subcategory": "Coverage",
                "pending_coverage_ticket_notification": {
                    "ticketId": "KBC-000065",
                    "requesterName": "Ayman",
                    "requesterEmail": "ayman@example.com",
                    "requesterRole": "user",
                    "createdAt": "2026-06-05T10:00:00Z",
                },
            },
        }
        actor_row = {"id": 7, "username": "ahmed", "full_name": "Ahmed Hamamo", "email": "ahmed@example.com", "role": "admin"}
        mock_connection, cursor = self.build_mock_connection()

        with (
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "fetch_admin_ticket_detail", return_value={"ticket": {"id": "KBC-000065"}}),
        ):
            response = services.acknowledge_coverage_ticket_notification(
                "KBC-000065",
                {"actorUsername": "ahmed"},
            )

        self.assertEqual(response["ticket"]["id"], "KBC-000065")
        update_params = cursor.execute.call_args.args[1]
        persisted_metadata = json.loads(update_params[0])
        self.assertNotIn("pending_coverage_ticket_notification", persisted_metadata)

    def test_acknowledge_support_queue_notification_clears_pending_metadata(self):
        ticket = {
            "id": 67,
            "public_id": "KBC-000067",
            "assigned_team": services.ASSIGNED_TEAM_SUPPORT_DESK,
            "technical_subcategory": "LMS",
            "metadata": {
                "requester_role": "user",
                "pending_support_queue_notification": {
                    "ticketId": "KBC-000067",
                    "requesterName": "Ali Test",
                    "requesterEmail": "ali@example.com",
                    "requesterRole": "user",
                    "queue": services.ASSIGNED_TEAM_SUPPORT_DESK,
                    "reason": "support_ticket_created",
                    "createdAt": "2026-06-05T10:00:00Z",
                },
            },
        }
        actor_row = {
            "id": 7,
            "username": "support.agent",
            "full_name": "Support Agent",
            "email": "support.agent@example.com",
            "role": "agent",
            "metadata": {"legacy_support_access": True, "legacy_operations_access": False},
        }
        mock_connection, cursor = self.build_mock_connection()

        with (
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "fetch_admin_ticket_detail", return_value={"ticket": {"id": "KBC-000067"}}),
        ):
            response = services.acknowledge_support_queue_notification(
                "KBC-000067",
                {"actorUsername": "support.agent"},
            )

        self.assertEqual(response["ticket"]["id"], "KBC-000067")
        update_params = cursor.execute.call_args.args[1]
        persisted_metadata = json.loads(update_params[0])
        self.assertNotIn("pending_support_queue_notification", persisted_metadata)

    def test_acknowledge_learning_plan_transfer_notification_clears_pending_metadata(self):
        ticket = {
            "id": 66,
            "public_id": "KBC-000066",
            "assigned_team": services.ASSIGNED_TEAM_LEARNING_PLAN,
            "technical_subcategory": "ApTem",
            "metadata": {
                "requester_role": "coach",
                "pending_learning_plan_transfer_notification": {
                    "ticketId": "KBC-000066",
                    "requesterName": "Olivia Evans",
                    "requesterEmail": "olivia@example.com",
                    "requesterRole": "coach",
                    "fromTeam": services.ASSIGNED_TEAM_SUPPORT_DESK,
                    "toTeam": services.ASSIGNED_TEAM_LEARNING_PLAN,
                    "transferredAt": "2026-06-05T11:00:00Z",
                    "transferredById": 1,
                    "transferredByName": "Support Manager",
                    "transferredByUsername": "manager",
                    "assignedAgentId": 5,
                    "assignedAgentName": "Omar Helmy",
                    "assignedAgentUsername": "omar",
                    "note": "Please continue with learning plan workflow.",
                },
            },
        }
        actor_row = {"id": 7, "username": "ahmed", "full_name": "Ahmed Hamamo", "email": "ahmed@example.com", "role": "admin"}
        mock_connection, cursor = self.build_mock_connection()

        with (
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "fetch_admin_ticket_detail", return_value={"ticket": {"id": "KBC-000066"}}),
        ):
            response = services.acknowledge_learning_plan_transfer_notification(
                "KBC-000066",
                {"actorUsername": "ahmed"},
            )

        self.assertEqual(response["ticket"]["id"], "KBC-000066")
        update_params = cursor.execute.call_args.args[1]
        persisted_metadata = json.loads(update_params[0])
        self.assertNotIn("pending_learning_plan_transfer_notification", persisted_metadata)

    def test_confirm_coverage_tutor_session_closes_ticket_and_stamps_confirmation(self):
        ticket = {
            "id": 63,
            "public_id": "KBC-000063",
            "status": "Pending",
            "status_reason": "Tutor Accepted",
            "technical_subcategory": "Coverage",
            "assigned_team": "Unassigned",
            "assigned_agent_id": None,
            "sla_status": "On Track",
            "created_at": datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc),
            "conversation_id": None,
            "metadata": {
                "technical_subcategory": "Coverage",
                "admin_documentation": {
                    "ticketId": "KBC-000063",
                    "coverageCards": [
                        {
                            "id": "reply-1",
                            "type": "tutor_reply",
                            "tutor": "Nathan",
                            "replyOutcome": "accepted",
                            "sessionStartAt": "2026-06-04T09:00:00Z",
                            "locked": True,
                            "createdAt": "2026-06-04T08:00:00Z",
                            "updatedAt": "2026-06-04T08:00:00Z",
                        }
                    ],
                },
            },
        }
        actor_row = {"id": 7, "username": "ahmed", "full_name": "Ahmed Hamamo", "email": "ahmed@example.com", "role": "admin"}
        mock_connection, cursor = self.build_mock_connection()

        with (
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "resolve_next_sla_state", return_value=("On Track", False, None)),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event"),
            patch.object(services, "fetch_admin_ticket_detail", return_value={"ticket": {"id": "KBC-000063"}}),
        ):
            response = services.confirm_coverage_tutor_session(
                "KBC-000063",
                {"actorUsername": "ahmed", "cardId": "reply-1"},
            )

        self.assertEqual(response["ticket"]["id"], "KBC-000063")
        update_params = cursor.execute.call_args_list[0].args[1]
        self.assertEqual(update_params[0], "Closed")
        self.assertEqual(update_params[1], "Closed via Agent")
        persisted_metadata = json.loads(update_params[3])
        persisted_card = persisted_metadata["admin_documentation"]["coverageCards"][0]
        self.assertTrue(persisted_card["locked"])
        self.assertTrue(persisted_card["confirmedAt"])
        self.assertEqual(persisted_card["confirmedByAgentId"], 7)

    def test_confirm_coverage_tutor_session_uses_database_derived_reply_card(self):
        ticket = {
            "id": 64,
            "public_id": "KBC-000064",
            "status": "Pending",
            "status_reason": "Tutor Accepted",
            "technical_subcategory": "Coverage",
            "assigned_team": "Unassigned",
            "assigned_agent_id": None,
            "sla_status": "On Track",
            "created_at": datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 6, 4, 11, 0, tzinfo=timezone.utc),
            "conversation_id": None,
            "metadata": {
                "technical_subcategory": "Coverage",
                "admin_documentation": {
                    "ticketId": "KBC-000064",
                    "coverageCards": [
                        {
                            "id": "card-1",
                            "type": "tutor_choice",
                            "tutor": "Nathan",
                            "tutorEmail": "nathan@example.com",
                            "sessionDetails": "Friday 09:00 - 11:00",
                            "sessionStartAt": "2026-06-04T09:00:00Z",
                            "requestStatus": "requested",
                            "submittedAt": "2026-06-04T08:10:00Z",
                            "requestSubmittedByAgentId": 7,
                            "requestSubmittedByAgentName": "Ahmed Hamamo",
                            "requestSubmittedByAgentUsername": "ahmed",
                            "locked": True,
                        }
                    ],
                },
            },
        }
        actor_row = {"id": 7, "username": "ahmed", "full_name": "Ahmed Hamamo", "email": "ahmed@example.com", "role": "admin"}
        mock_connection, cursor = self.build_mock_connection()
        derived_reply_card_id = services.build_derived_coverage_tutor_reply_card_id("card-1", "accepted")

        with (
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "resolve_next_sla_state", return_value=("On Track", False, None)),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event"),
            patch.object(services, "fetch_admin_ticket_detail", return_value={"ticket": {"id": "KBC-000064"}}),
        ):
            response = services.confirm_coverage_tutor_session(
                "KBC-000064",
                {"actorUsername": "ahmed", "cardId": derived_reply_card_id},
            )

        self.assertEqual(response["ticket"]["id"], "KBC-000064")
        update_params = cursor.execute.call_args_list[0].args[1]
        self.assertEqual(update_params[0], "Closed")
        persisted_metadata = json.loads(update_params[3])
        persisted_cards = persisted_metadata["admin_documentation"]["coverageCards"]
        reply_card = next(card for card in persisted_cards if card["type"] == "tutor_reply")
        self.assertEqual(reply_card["id"], derived_reply_card_id)
        self.assertTrue(reply_card["confirmedAt"])
        self.assertEqual(reply_card["confirmedByAgentId"], 7)


class BookingContextTests(SimpleTestCase):
    def test_build_public_chat_id_prefers_conversation_id_over_ticket_public_id(self):
        self.assertEqual(services.build_public_chat_id("KBC-000123", 77), "CHAT-000077")

    def test_build_public_chat_id_ignores_legacy_ticket_mirrored_metadata_value(self):
        self.assertEqual(
            services.build_public_chat_id("KBC-000123", 77, {"chat_public_id": "KBC-000123"}),
            "CHAT-000077",
        )

    def test_build_public_chat_id_ignores_legacy_root_ticket_id_on_follow_up_ticket(self):
        self.assertEqual(
            services.build_public_chat_id("KBC-000132", 129, {"chat_public_id": "KBC-000130"}),
            "CHAT-000129",
        )

    def test_build_public_chat_id_prefers_conversation_metadata_value(self):
        self.assertEqual(
            services.build_public_chat_id("KBC-000123", 77, {"chat_public_id": "CHAT-KBC-ROOT"}),
            "CHAT-KBC-ROOT",
        )

    def test_normalize_admin_documentation_replaces_legacy_chat_id_with_normalized_value(self):
        normalized_documentation = services.normalize_admin_documentation(
            {
                "chatId": "KBC-000130",
                "ticketId": "KBC-000132",
                "inquiry": "Need LMS support.",
            },
            fallback_inquiry="Need LMS support.",
            fallback_chat_id="CHAT-000129",
            fallback_ticket_id="KBC-000132",
        )

        self.assertEqual(normalized_documentation["chatId"], "CHAT-000129")

    def test_normalize_admin_documentation_preserves_coverage_workflow_cards(self):
        normalized_documentation = services.normalize_admin_documentation(
            {
                "inquiry": "Coverage request",
                "coverageNotes": "Initial support note",
                "coverageCards": [
                    {
                        "id": "card-1",
                        "type": "tutor_choice",
                        "tutor": "Nathan",
                        "tutorEmail": "nathan.shields@kentbusinesscollege.com",
                        "coach": "Mona Adel",
                        "coachEmail": "mona.adel@kentbusinesscollege.com",
                        "sessionDetails": "Module: APM",
                        "requestStatus": "pending",
                        "locked": True,
                        "submittedAt": "2026-06-03T10:30:00Z",
                        "createdByAgentId": 7,
                        "createdByAgentName": "Ahmed Hamamo",
                        "createdByAgentUsername": "ahmed",
                        "updatedByAgentId": 8,
                        "updatedByAgentName": "Omar Helmy",
                        "updatedByAgentUsername": "omar",
                        "presentationFiles": [
                            {
                                "id": "file-1",
                                "name": "deck.pdf",
                                "mimeType": "application/pdf",
                                "size": 128,
                                "dataUrl": "data:application/pdf;base64,ZmFrZQ==",
                            },
                            {
                                "id": "file-2",
                                "name": "bad.txt",
                                "mimeType": "text/plain",
                                "size": 20,
                                "dataUrl": "https://example.com/file.txt",
                            },
                        ],
                        "sessionFiles": [
                            {
                                "id": "session-1",
                                "label": "Session 1",
                                "date": "Wednesday 01 Jul 2026",
                                "number": "3",
                                "subject": "Intro",
                                "attachments": [
                                    {
                                        "id": "session-file-1",
                                        "name": "session.pdf",
                                        "mimeType": "application/pdf",
                                        "size": 64,
                                        "dataUrl": "data:application/pdf;base64,c2Vzc2lvbg==",
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "id": "card-2",
                        "type": "note",
                        "note": "Follow up with another tutor if needed.",
                    },
                ],
            },
            fallback_inquiry="Coverage request",
            fallback_chat_id="CHAT-000200",
            fallback_ticket_id="KBC-000200",
        )

        self.assertEqual(normalized_documentation["coverageNotes"], "Initial support note")
        self.assertEqual(len(normalized_documentation["coverageCards"]), 2)
        self.assertEqual(normalized_documentation["coverageCards"][0]["type"], "tutor_choice")
        self.assertEqual(normalized_documentation["coverageCards"][0]["tutor"], "Nathan")
        self.assertEqual(normalized_documentation["coverageCards"][0]["tutorEmail"], "nathan.shields@kentbusinesscollege.com")
        self.assertEqual(normalized_documentation["coverageCards"][0]["coach"], "Mona Adel")
        self.assertEqual(normalized_documentation["coverageCards"][0]["coachEmail"], "mona.adel@kentbusinesscollege.com")
        self.assertEqual(normalized_documentation["coverageCards"][0]["requestStatus"], "requested")
        self.assertEqual(normalized_documentation["coverageCards"][0]["createdByAgentName"], "Ahmed Hamamo")
        self.assertEqual(normalized_documentation["coverageCards"][0]["updatedByAgentName"], "Omar Helmy")
        self.assertEqual(len(normalized_documentation["coverageCards"][0]["presentationFiles"]), 1)
        self.assertEqual(len(normalized_documentation["coverageCards"][0]["sessionFiles"]), 1)
        self.assertEqual(normalized_documentation["coverageCards"][0]["sessionFiles"][0]["attachments"][0]["name"], "session.pdf")
        self.assertEqual(normalized_documentation["coverageCards"][1]["type"], "note")
        self.assertEqual(normalized_documentation["coverageCards"][1]["note"], "Follow up with another tutor if needed.")

    def test_stamp_coverage_documentation_card_actors_marks_new_card_creator_and_editor(self):
        stamped_documentation = services.stamp_coverage_documentation_card_actors(
            {
                "coverageCards": [
                    {
                        "id": "new-card",
                        "type": "note",
                        "note": "Try another tutor.",
                        "createdAt": "2026-06-16T10:00:00Z",
                        "updatedAt": "2026-06-16T10:00:00Z",
                    }
                ]
            },
            {},
            {"id": 7, "username": "ahmed", "full_name": "Ahmed Hamamo"},
        )

        stamped_card = stamped_documentation["coverageCards"][0]
        self.assertEqual(stamped_card["createdByAgentId"], 7)
        self.assertEqual(stamped_card["createdByAgentName"], "Ahmed Hamamo")
        self.assertEqual(stamped_card["createdByAgentUsername"], "ahmed")
        self.assertEqual(stamped_card["updatedByAgentId"], 7)
        self.assertEqual(stamped_card["updatedByAgentName"], "Ahmed Hamamo")
        self.assertEqual(stamped_card["updatedByAgentUsername"], "ahmed")

    def test_normalize_admin_documentation_preserves_standard_documentation_cards(self):
        normalized_documentation = services.normalize_admin_documentation(
            {
                "inquiry": "Need Aptem help.",
                "documentationCards": [
                    {
                        "id": "doc-card-1",
                        "inquiry": "Confirmed the requester issue.",
                        "symptoms": "Learner cannot open module.",
                        "errors": "403 page",
                        "steps": "Checked account access.",
                        "resources": "Aptem admin portal",
                        "locked": True,
                        "createdAt": "2026-06-09T10:00:00Z",
                        "updatedAt": "2026-06-09T10:05:00Z",
                        "createdByAgentId": 7,
                        "createdByAgentName": "Ahmed Hamamo",
                        "createdByAgentUsername": "ahmed",
                        "updatedByAgentId": 8,
                        "updatedByAgentName": "Omar Helmy",
                        "updatedByAgentUsername": "omar",
                        "attachments": [
                            {
                                "id": "doc-file-1",
                                "name": "case-notes.pdf",
                                "mimeType": "application/pdf",
                                "size": 42,
                                "storageUrl": "/api/admin/tickets/KBC-000201/attachments/77/download",
                                "attachmentId": 77,
                            }
                        ],
                        "unexpected": "ignored",
                    },
                    "bad-card",
                ],
            },
            fallback_inquiry="Need Aptem help.",
            fallback_chat_id="CHAT-000201",
            fallback_ticket_id="KBC-000201",
        )

        self.assertEqual(len(normalized_documentation["documentationCards"]), 1)
        persisted_card = normalized_documentation["documentationCards"][0]
        self.assertEqual(persisted_card["id"], "doc-card-1")
        self.assertEqual(persisted_card["inquiry"], "Confirmed the requester issue.")
        self.assertEqual(persisted_card["symptoms"], "Learner cannot open module.")
        self.assertEqual(persisted_card["errors"], "403 page")
        self.assertEqual(persisted_card["steps"], "Checked account access.")
        self.assertEqual(persisted_card["resources"], "Aptem admin portal")
        self.assertTrue(persisted_card["locked"])
        self.assertEqual(persisted_card["createdAt"], "2026-06-09T10:00:00Z")
        self.assertEqual(persisted_card["updatedAt"], "2026-06-09T10:05:00Z")
        self.assertEqual(persisted_card["createdByAgentName"], "Ahmed Hamamo")
        self.assertEqual(persisted_card["updatedByAgentName"], "Omar Helmy")
        self.assertEqual(len(persisted_card["attachments"]), 1)
        self.assertEqual(persisted_card["attachments"][0]["name"], "case-notes.pdf")
        self.assertEqual(persisted_card["attachments"][0]["attachmentId"], 77)

    def test_stamp_documentation_card_actors_marks_new_card_creator_and_editor(self):
        stamped_documentation = services.stamp_documentation_card_actors(
            {
                "documentationCards": [
                    {
                        "id": "doc-card-new",
                        "inquiry": "Checked learner access.",
                        "createdAt": "2026-06-17T10:00:00Z",
                        "updatedAt": "2026-06-17T10:00:00Z",
                    }
                ]
            },
            {},
            {"id": 9, "username": "omar", "full_name": "Omar Helmy"},
        )

        stamped_card = stamped_documentation["documentationCards"][0]
        self.assertEqual(stamped_card["createdByAgentId"], 9)
        self.assertEqual(stamped_card["createdByAgentName"], "Omar Helmy")
        self.assertEqual(stamped_card["createdByAgentUsername"], "omar")
        self.assertEqual(stamped_card["updatedByAgentId"], 9)
        self.assertEqual(stamped_card["updatedByAgentName"], "Omar Helmy")
        self.assertEqual(stamped_card["updatedByAgentUsername"], "omar")

    def test_attach_uploaded_documentation_card_files_assigns_uploaded_rows_to_cards(self):
        uploaded_file = SimpleUploadedFile("case-notes.pdf", b"pdf", content_type="application/pdf")
        stored_attachment = {
            "name": "case-notes.pdf",
            "mimeType": "application/pdf",
            "size": 3,
            "storageKey": "KBC-000201/2026/06/case-notes.pdf",
            "metadata": {"originalName": "case-notes.pdf"},
        }
        inserted_attachment = {
            "id": "ticket-attachment-77",
            "attachmentId": 77,
            "name": "case-notes.pdf",
            "mimeType": "application/pdf",
            "size": 3,
            "storageKey": "KBC-000201/2026/06/case-notes.pdf",
            "storageUrl": "/api/admin/tickets/KBC-000201/attachments/77/download",
            "dataUrl": "",
        }

        with (
            patch.object(services, "store_uploaded_ticket_attachments", return_value=[stored_attachment]) as store_files,
            patch.object(services, "insert_ticket_attachment_rows", return_value=[inserted_attachment]) as insert_rows,
        ):
            documentation = services.attach_uploaded_documentation_card_files(
                ticket_id=201,
                ticket_public_id="KBC-000201",
                documentation={
                    "documentationCards": [
                        {
                            "id": "doc-card-1",
                            "inquiry": "Checked learner access.",
                            "attachments": [
                                {
                                    "id": "pending-file-1",
                                    "name": "case-notes.pdf",
                                    "mimeType": "application/pdf",
                                    "size": 3,
                                }
                            ],
                        }
                    ]
                },
                uploaded_files=[uploaded_file],
            )

        store_files.assert_called_once_with("KBC-000201", [uploaded_file])
        insert_rows.assert_called_once()
        persisted_attachment = documentation["documentationCards"][0]["attachments"][0]
        self.assertEqual(persisted_attachment["id"], "pending-file-1")
        self.assertEqual(persisted_attachment["attachmentId"], 77)
        self.assertEqual(persisted_attachment["storageUrl"], "/api/admin/tickets/KBC-000201/attachments/77/download")

    def test_build_documentation_card_history_events_tracks_card_and_attachment_changes(self):
        previous_documentation = {
            "documentationCards": [
                {
                    "id": "doc-card-1",
                    "inquiry": "Checked learner access.",
                    "attachments": [
                        {
                            "id": "doc-file-1",
                            "name": "old.png",
                            "mimeType": "image/png",
                            "size": 12,
                            "storageUrl": "/api/admin/tickets/KBC-000201/attachments/77/download",
                            "attachmentId": 77,
                        }
                    ],
                }
            ],
            "coverageCards": [
                {
                    "id": "coverage-card-1",
                    "type": "note",
                    "note": "Initial note.",
                    "presentationFiles": [],
                }
            ],
        }
        next_documentation = {
            "documentationCards": [
                {
                    "id": "doc-card-1",
                    "inquiry": "Confirmed learner access was restored.",
                    "attachments": [
                        {
                            "id": "doc-file-1",
                            "name": "old.png",
                            "mimeType": "image/png",
                            "size": 12,
                            "storageUrl": "/api/admin/tickets/KBC-000201/attachments/77/download",
                            "attachmentId": 77,
                        },
                        {
                            "id": "doc-file-2",
                            "name": "new.png",
                            "mimeType": "image/png",
                            "size": 18,
                            "dataUrl": "data:image/png;base64,large-value",
                            "storageKey": "internal/path/new.png",
                            "storageUrl": "/api/admin/tickets/KBC-000201/attachments/78/download",
                            "attachmentId": 78,
                        },
                    ],
                },
                {
                    "id": "doc-card-2",
                    "inquiry": "Created a second card.",
                },
            ],
            "coverageCards": [
                {
                    "id": "coverage-card-1",
                    "type": "note",
                    "note": "Initial note.",
                    "presentationFiles": [
                        {
                            "id": "coverage-file-1",
                            "name": "deck.pdf",
                            "mimeType": "application/pdf",
                            "size": 128,
                            "storageUrl": "/api/admin/tickets/KBC-000201/attachments/79/download",
                            "attachmentId": 79,
                        }
                    ],
                }
            ],
        }

        events = services.build_documentation_card_history_events(previous_documentation, next_documentation)
        event_types = [event_type for event_type, _payload in events]

        self.assertIn("documentation_card_created", event_types)
        self.assertIn("documentation_card_updated", event_types)
        self.assertIn("documentation_attachment_added", event_types)
        self.assertIn("coverage_attachment_added", event_types)
        attachment_payload = next(
            payload
            for event_type, payload in events
            if event_type == "documentation_attachment_added"
        )
        self.assertEqual(attachment_payload["addedAttachmentCount"], 1)
        self.assertEqual(attachment_payload["fileNames"], ["new.png"])
        self.assertEqual(attachment_payload["addedAttachments"][0]["name"], "new.png")
        self.assertEqual(attachment_payload["addedAttachments"][0]["mimeType"], "image/png")
        self.assertNotIn("dataUrl", attachment_payload["addedAttachments"][0])
        self.assertNotIn("storageKey", attachment_payload["addedAttachments"][0])
        update_payload = next(
            payload
            for event_type, payload in events
            if event_type == "documentation_card_updated"
        )
        self.assertEqual(update_payload["changedFields"], ["inquiry"])
        self.assertEqual(update_payload["previousValues"], {"inquiry": "Checked learner access."})
        self.assertEqual(update_payload["currentValues"], {"inquiry": "Confirmed learner access was restored."})
        self.assertEqual(update_payload["cardDetails"]["inquiry"], "Confirmed learner access was restored.")
        self.assertEqual(len(update_payload["cardDetails"]["attachments"]), 2)
        create_payload = next(
            payload
            for event_type, payload in events
            if event_type == "documentation_card_created"
        )
        self.assertEqual(create_payload["cardDetails"]["inquiry"], "Created a second card.")

    def test_stamp_documentation_card_actors_backfills_legacy_saved_card_editor(self):
        legacy_documentation = {
            "documentationCards": [
                {
                    "id": "legacy-doc-card",
                    "inquiry": "Checked learner access.",
                    "locked": True,
                    "createdAt": "2026-06-17T10:00:00Z",
                    "updatedAt": "2026-06-17T10:00:00Z",
                }
            ]
        }

        stamped_documentation = services.stamp_documentation_card_actors(
            legacy_documentation,
            legacy_documentation,
            {"id": 9, "username": "omar", "full_name": "Omar Helmy"},
        )

        stamped_card = stamped_documentation["documentationCards"][0]
        self.assertIsNone(stamped_card["createdByAgentId"])
        self.assertEqual(stamped_card["updatedByAgentId"], 9)
        self.assertEqual(stamped_card["updatedByAgentName"], "Omar Helmy")
        self.assertNotEqual(stamped_card["updatedAt"], "2026-06-17T10:00:00Z")

    def test_get_support_booking_url_returns_configured_value(self):
        with patch.object(services.settings, "SUPPORT_BOOKING_URL", "https://outlook.office.com/book/example"):
            response = services.get_support_booking_url()

        self.assertEqual(response, "https://outlook.office.com/book/example")

    def test_get_support_teams_call_url_returns_configured_value(self):
        with patch.object(services.settings, "SUPPORT_TEAMS_CALL_URL", "https://teams.microsoft.com/l/call/0/0?users=support@example.com"):
            response = services.get_support_teams_call_url()

        self.assertEqual(response, "https://teams.microsoft.com/l/call/0/0?users=support@example.com")

    def test_get_support_teams_call_context_response_builds_deep_link_from_targets(self):
        with (
            patch.object(services.settings, "SUPPORT_TEAMS_CALL_URL", ""),
            patch.object(services.settings, "SUPPORT_TEAMS_CALL_TARGETS", ["support@example.com", "backup@example.com"]),
            patch.object(services.settings, "SUPPORT_TEAMS_CALL_LABEL", "Support Team"),
            patch.object(services.settings, "BOOKING_BUSINESS_ID", ""),
        ):
            response = services.get_support_teams_call_context_response()

        self.assertEqual(
            response["callUrl"],
            "https://teams.microsoft.com/l/call/0/0?users=support%40example.com%2Cbackup%40example.com",
        )
        self.assertEqual(response["targetLabel"], "Support Team")
        self.assertEqual(response["targets"], ["support@example.com", "backup@example.com"])

    def test_get_support_teams_call_context_response_falls_back_to_booking_business_id(self):
        with (
            patch.object(services.settings, "SUPPORT_TEAMS_CALL_URL", ""),
            patch.object(services.settings, "SUPPORT_TEAMS_CALL_TARGETS", []),
            patch.object(services.settings, "SUPPORT_TEAMS_CALL_LABEL", ""),
            patch.object(services.settings, "BOOKING_BUSINESS_ID", "StudentSupport1@kentbusinesscollege.com"),
        ):
            response = services.get_support_teams_call_context_response()

        self.assertEqual(
            response["callUrl"],
            "https://teams.microsoft.com/l/call/0/0?users=StudentSupport1%40kentbusinesscollege.com",
        )
        self.assertEqual(response["targetLabel"], "StudentSupport1@kentbusinesscollege.com")

    def test_resolve_support_teams_call_notification_target_uses_single_name_match_when_email_missing(self):
        with (
            patch.object(services, "run_query_one", return_value=None),
            patch.object(
                services,
                "run_query",
                return_value=[
                    {
                        "id": 23,
                        "username": "Omar1",
                        "full_name": "Omar1",
                        "email": None,
                        "role": "admin",
                    }
                ],
            ),
        ):
            response = services.resolve_support_teams_call_notification_target(["Omar.Helmy@kentbusinesscollege.com"])

        self.assertEqual(response["id"], 23)
        self.assertEqual(response["username"], "Omar1")

    def test_request_support_teams_call_creates_pending_admin_notification(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "metadata": {
                "requester_role": "coach",
            },
            "assigned_agent_id": None,
            "assigned_team": "Unassigned",
            "conversation_id": 44,
            "learner_name": "Coach One",
            "learner_email": "coach@example.com",
        }
        target_agent = {
            "id": 9,
            "username": "ahmedhamamo",
            "full_name": "Ahmed Hamamo",
            "email": "ahmed@example.com",
            "role": "admin",
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services.settings, "SUPPORT_TEAMS_CALL_URL", ""),
            patch.object(services.settings, "SUPPORT_TEAMS_CALL_TARGETS", ["ahmed@example.com"]),
            patch.object(services.settings, "SUPPORT_TEAMS_CALL_LABEL", "Ahmed Hamamo"),
            patch.object(services.settings, "BOOKING_BUSINESS_ID", ""),
            patch.object(services, "resolve_support_teams_call_notification_target", return_value=target_agent),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event") as insert_history_event,
        ):
            response = services.request_support_teams_call("KBC-000017")

        self.assertTrue(response["ok"])
        self.assertTrue(response["notificationPending"])
        ticket_update_params = cursor.execute.call_args_list[0].args[1]
        self.assertEqual(ticket_update_params[0], 9)
        self.assertEqual(ticket_update_params[1], "Support Desk")
        updated_metadata = json.loads(ticket_update_params[2])
        self.assertEqual(updated_metadata["pending_teams_call_notification"]["toAgentId"], 9)
        self.assertEqual(updated_metadata["pending_teams_call_notification"]["requesterEmail"], "coach@example.com")
        self.assertTrue(updated_metadata["teams_call_requested"])
        insert_history_event.assert_any_call(
            17,
            "teams_call_requested",
            {"role": "coach", "label": "coach@example.com"},
            {
                "toAgentId": 9,
                "toAgentName": "Ahmed Hamamo",
                "toAgentUsername": "ahmedhamamo",
                "requesterName": "Coach One",
                "requesterEmail": "coach@example.com",
                "requesterRole": "coach",
                "note": "Coach requested a direct Microsoft Teams support call from the support portal.",
                "targetLabel": "Ahmed Hamamo",
                "ticketId": "KBC-000017",
                "requestedAt": updated_metadata["pending_teams_call_notification"]["requestedAt"],
            },
        )
        insert_history_event.assert_any_call(
            17,
            "assignment_changed",
            {"role": "coach", "label": "coach@example.com"},
            {
                "fromAgentId": None,
                "toAgentId": 9,
                "toAgentName": "Ahmed Hamamo",
            },
        )

    def test_acknowledge_ticket_teams_call_notification_clears_notification(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "metadata": {
                "teams_call_requested": True,
                "pending_teams_call_notification": {
                    "toAgentId": 9,
                    "toAgentName": "Ahmed Hamamo",
                    "toAgentUsername": "ahmedhamamo",
                    "requesterName": "Coach One",
                    "requesterEmail": "coach@example.com",
                    "requesterRole": "coach",
                    "note": "Coach requested a direct Microsoft Teams support call from the support portal.",
                    "targetLabel": "Ahmed Hamamo",
                    "ticketId": "KBC-000017",
                    "requestedAt": "2026-05-18T08:00:00+00:00",
                }
            },
        }
        actor_row = {
            "id": 9,
            "username": "ahmedhamamo",
            "full_name": "Ahmed Hamamo",
            "role": "admin",
        }
        detail = {
            "ticket": {
                "id": "KBC-000017",
                "pendingTeamsCallNotification": None,
            }
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "fetch_actor_by_username", return_value=actor_row),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "fetch_admin_ticket_detail", return_value=detail),
        ):
            response = services.acknowledge_ticket_teams_call_notification(
                "KBC-000017",
                {"actorUsername": "ahmedhamamo"},
            )

        self.assertEqual(response, detail)
        updated_metadata = json.loads(cursor.execute.call_args.args[1][0])
        self.assertNotIn("pending_teams_call_notification", updated_metadata)
        self.assertTrue(updated_metadata["teams_call_requested"])

    def test_get_ticket_booking_context_response_returns_prefill_payload(self):
        ticket_row = {
            "public_id": "KBC-000123",
            "category": "Technical",
            "technical_subcategory": "Teams",
            "inquiry": "Need help joining my live class.",
            "status": "Open",
            "learner_id": 11,
            "learner_full_name": "Ali Test",
            "learner_email": "ali@example.com",
            "learner_phone": "01000000000",
        }

        with (
            patch.object(services, "run_query_one", return_value=ticket_row) as run_query_one,
            patch.object(services.settings, "SUPPORT_BOOKING_URL", "https://outlook.office.com/book/example"),
        ):
            response = services.get_ticket_booking_context_response("KBC-000123")

        self.assertEqual(response["bookingUrl"], "https://outlook.office.com/book/example")
        self.assertFalse(response["externalAutofillSupported"])
        self.assertEqual(response["learner"]["fullName"], "Ali Test")
        self.assertEqual(response["prefill"]["email"], "ali@example.com")
        self.assertEqual(response["prefill"]["specialRequests"], "Need help joining my live class.")
        run_query_one.assert_called_once()

    def test_set_ticket_booking_progress_updates_ticket_metadata(self):
        ticket_row = {
            "id": 17,
            "public_id": "KBC-000017",
            "status": "Open",
            "metadata": {},
        }
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = None
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = cursor_context

        with (
            patch.object(services, "run_query_one", return_value=ticket_row),
            patch.object(services, "connection", mock_connection),
        ):
            response = services.set_ticket_booking_progress("KBC-000017", active=True)

        self.assertTrue(response["ticket"]["bookingInProgress"])
        metadata_patch = json.loads(cursor.execute.call_args.args[1][0])
        self.assertEqual(
            metadata_patch[services.SUPPORT_FLOW_STAGE_METADATA_KEY],
            services.SUPPORT_FLOW_STAGE_BOOKING_IN_PROGRESS,
        )
        self.assertTrue(metadata_patch["booking_started_at"])

    def test_get_ticket_chat_context_response_returns_intro_message(self):
        ticket_row = {
            "public_id": "KBC-000123",
            "metadata": {},
            "status": "Open",
            "status_reason": "",
            "assigned_agent_id": None,
            "category": "Technical",
            "technical_subcategory": "Teams",
            "learner_id": 11,
            "learner_full_name": "Ali Test",
            "learner_email": "ali@example.com",
        }

        with (
            patch.object(services, "sync_open_ticket_inactivity"),
            patch.object(services, "run_query_one", return_value=ticket_row) as run_query_one,
        ):
            response = services.get_ticket_chat_context_response("KBC-000123")

        self.assertEqual(
            response["introMessage"],
            "Hello Ali Test, Thank you for reaching Kent College Support, I understand you are reaching us for an issue related to Teams, am I correct?",
        )
        self.assertEqual(response["learner"]["fullName"], "Ali Test")
        self.assertEqual(response["ticket"]["category"], "Technical")
        self.assertEqual(response["ticket"]["technicalSubcategory"], "Teams")
        self.assertIsNone(response["ticket"]["assignedAgentId"])
        run_query_one.assert_called_once()

    def test_get_ticket_chat_context_response_allows_coach_requester_role(self):
        ticket_row = {
            "public_id": "KBC-000123",
            "metadata": {"requester_role": "coach"},
            "conversation_id": 55,
            "status": "Open",
            "status_reason": "",
            "assigned_agent_id": None,
            "category": "Technical",
            "technical_subcategory": "Teams",
            "conversation_status": "open",
            "conversation_metadata": {},
            "learner_id": 11,
            "learner_full_name": "Coach One",
            "learner_email": "coach@example.com",
        }

        with (
            patch.object(services, "sync_open_ticket_inactivity"),
            patch.object(services, "run_query_one", return_value=ticket_row),
            patch.object(services, "mark_conversation_as_active"),
        ):
            response = services.get_ticket_chat_context_response("KBC-000123")

        self.assertEqual(response["learner"]["fullName"], "Coach One")
        self.assertEqual(response["ticket"]["technicalSubcategory"], "Teams")
        self.assertIsNone(response["ticket"]["assignedAgentId"])

    def test_get_ticket_chat_history_response_keeps_intro_message_when_not_persisted_yet(self):
        ticket_row = {
            "id": 1,
            "public_id": "KBC-000123",
            "category": "Technical",
            "technical_subcategory": "Teams",
            "status": "Open",
            "status_reason": "",
            "assigned_agent_id": None,
            "assigned_team": "Unassigned",
            "sla_status": "Pending Review",
            "created_at": datetime(2026, 5, 7, 10, 0, tzinfo=timezone.utc),
            "metadata": {},
            "conversation_id": 55,
            "conversation_metadata": {},
            "learner_name": "Ali Test",
        }

        with (
            patch.object(services, "sync_open_ticket_inactivity"),
            patch.object(services, "run_query_one", return_value=ticket_row),
            patch.object(services, "run_query", return_value=[]),
            patch.object(services, "get_latest_ticket_booking_summary", return_value=None),
        ):
            response = services.get_ticket_chat_history_response("KBC-000123")

        self.assertEqual(len(response["chatHistory"]), 1)
        self.assertEqual(response["chatHistory"][0]["sender"], "bot")
        self.assertIn("Hello Ali Test", response["chatHistory"][0]["text"])
        self.assertIsNone(response["ticket"]["assignedAgentId"])

    def test_get_ticket_chat_history_response_moves_intro_message_to_top_when_it_was_persisted_late(self):
        ticket_row = {
            "id": 1,
            "public_id": "KBC-000123",
            "category": "Technical",
            "technical_subcategory": "Teams",
            "status": "Open",
            "status_reason": "",
            "assigned_agent_id": None,
            "assigned_team": "Unassigned",
            "sla_status": "Pending Review",
            "created_at": datetime(2026, 5, 7, 10, 0, tzinfo=timezone.utc),
            "metadata": {},
            "conversation_id": 55,
            "conversation_metadata": {},
            "learner_name": "Ali Test",
        }
        persisted_intro = "Hello Ali Test, Thank you for reaching Kent College Support, I understand you are reaching us for an issue related to Teams, am I correct?"
        message_rows = [
            {
                "id": 301,
                "role": "assistant",
                "content": "Live chat has been requested. Please stay connected while we connect you.",
                "metadata": {"original_sender": "bot", "client_timestamp": "10:51 AM"},
                "created_at": datetime(2026, 5, 7, 10, 51, tzinfo=timezone.utc),
            },
            {
                "id": 302,
                "role": "assistant",
                "content": persisted_intro,
                "metadata": {"original_sender": "bot", "client_timestamp": "10:51 AM"},
                "created_at": datetime(2026, 5, 7, 10, 51, tzinfo=timezone.utc),
            },
        ]

        with (
            patch.object(services, "sync_open_ticket_inactivity"),
            patch.object(services, "run_query_one", return_value=ticket_row),
            patch.object(services, "run_query", side_effect=[message_rows, []]),
            patch.object(services, "get_latest_ticket_booking_summary", return_value=None),
        ):
            response = services.get_ticket_chat_history_response("KBC-000123")

        self.assertEqual(response["chatHistory"][0]["text"], persisted_intro)
        self.assertEqual(response["chatHistory"][1]["text"], "Live chat has been requested. Please stay connected while we connect you.")

    def test_get_ticket_chat_history_response_includes_assigned_agent_id_when_present(self):
        ticket_row = {
            "id": 1,
            "public_id": "KBC-000123",
            "category": "Technical",
            "technical_subcategory": "Teams",
            "status": "Open",
            "status_reason": "",
            "assigned_agent_id": 7,
            "assigned_team": "Support Desk",
            "sla_status": "Pending Review",
            "created_at": datetime(2026, 5, 7, 10, 0, tzinfo=timezone.utc),
            "metadata": {"live_chat_requested": True},
            "conversation_id": 55,
            "conversation_status": "open",
            "conversation_metadata": {"live_chat_requested": True},
            "learner_name": "Ali Test",
        }

        with (
            patch.object(services, "sync_open_ticket_inactivity"),
            patch.object(services, "run_query_one", return_value=ticket_row),
            patch.object(services, "run_query", return_value=[]),
            patch.object(services, "get_latest_ticket_booking_summary", return_value=None),
        ):
            response = services.get_ticket_chat_history_response("KBC-000123")

        self.assertEqual(response["ticket"]["assignedAgentId"], 7)

    def test_get_ticket_chat_history_response_includes_assignment_change_notice(self):
        ticket_row = {
            "id": 1,
            "public_id": "KBC-000123",
            "category": "Technical",
            "technical_subcategory": "Teams",
            "status": "Open",
            "status_reason": "",
            "assigned_agent_id": 7,
            "assigned_team": "Support Desk",
            "sla_status": "Pending Review",
            "created_at": datetime(2026, 5, 7, 10, 0, tzinfo=timezone.utc),
            "metadata": {"live_chat_requested": True},
            "conversation_id": 55,
            "conversation_status": "open",
            "conversation_metadata": {"live_chat_requested": True},
            "learner_name": "Ali Test",
        }
        message_rows = [
            {
                "id": 101,
                "role": "user",
                "content": "Hello",
                "metadata": {"original_sender": "user"},
                "created_at": datetime(2026, 5, 7, 10, 1, tzinfo=timezone.utc),
            },
            {
                "id": 102,
                "role": "assistant",
                "content": "You are now talking to Ahmed Hamamo.",
                "metadata": {"original_sender": "bot", "client_timestamp": "10:02 AM"},
                "created_at": datetime(2026, 5, 7, 10, 2, tzinfo=timezone.utc),
            },
        ]
        history_rows = [
            {
                "id": 202,
                "event_type": "assignment_changed",
                "payload": {"toAgentName": "Ahmed Hamamo"},
                "created_at": datetime(2026, 5, 7, 10, 2, tzinfo=timezone.utc),
            },
        ]

        with (
            patch.object(services, "sync_open_ticket_inactivity"),
            patch.object(services, "run_query_one", return_value=ticket_row),
            patch.object(services, "run_query", side_effect=[message_rows, history_rows]),
            patch.object(services, "get_latest_ticket_booking_summary", return_value=None),
        ):
            response = services.get_ticket_chat_history_response("KBC-000123")

        matching_notices = [
            message
            for message in response["chatHistory"]
            if message["text"] == "You are now talking to Ahmed Hamamo."
        ]
        self.assertEqual(len(matching_notices), 1)
        self.assertEqual(matching_notices[0]["sender"], "bot")

    def test_fetch_admin_ticket_detail_includes_assignment_change_notice_in_chat_history(self):
        ticket_row = {
            "id": 1,
            "public_id": "KBC-000123",
            "category": "Technical",
            "technical_subcategory": "Teams",
            "inquiry": "Need help with LMS",
            "status": "Open",
            "status_reason": "",
            "assigned_team": "Support Desk",
            "sla_status": "Pending Review",
            "priority": "Normal",
            "evidence_count": 0,
            "metadata": {"live_chat_requested": True},
            "created_at": datetime(2026, 5, 7, 10, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 5, 7, 10, 3, tzinfo=timezone.utc),
            "closed_at": None,
            "conversation_id": 55,
            "conversation_status": "open",
            "conversation_metadata": {"live_chat_requested": True},
            "chat_duration_minutes": 0,
            "last_message_at": datetime(2026, 5, 7, 10, 2, tzinfo=timezone.utc),
            "learner_name": "Ali Test",
            "learner_email": "ali@example.com",
            "learner_phone": "01010000000",
            "assigned_agent_id": 7,
            "assigned_agent_username": "ahmed",
            "assigned_agent_name": "Ahmed Hamamo",
        }
        message_rows = [
            {
                "id": 101,
                "role": "user",
                "content": "Hello",
                "metadata": {"original_sender": "user"},
                "created_at": datetime(2026, 5, 7, 10, 1, tzinfo=timezone.utc),
            },
            {
                "id": 102,
                "role": "assistant",
                "content": "You are now talking to Ahmed Hamamo.",
                "metadata": {"original_sender": "bot", "client_timestamp": "10:02 AM"},
                "created_at": datetime(2026, 5, 7, 10, 2, tzinfo=timezone.utc),
            },
        ]
        history_rows = [
            {
                "id": 202,
                "event_type": "assignment_changed",
                "actor_type": "system",
                "actor_label": "live_chat_queue",
                "payload": {"toAgentName": "Ahmed Hamamo"},
                "created_at": datetime(2026, 5, 7, 10, 2, tzinfo=timezone.utc),
            },
        ]

        with (
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "run_query_one", return_value=ticket_row),
            patch.object(services, "run_query", side_effect=[message_rows, [], history_rows, []]),
        ):
            response = services.fetch_admin_ticket_detail("KBC-000123")

        self.assertIsNotNone(response)
        assert response is not None
        matching_notices = [
            message
            for message in response["chatHistory"]
            if message["text"] == "You are now talking to Ahmed Hamamo."
        ]
        self.assertEqual(len(matching_notices), 1)
        self.assertEqual(matching_notices[0]["senderLabel"], "Bot")

    def test_get_ticket_chat_history_response_includes_booking_summary(self):
        ticket_row = {
            "id": 1,
            "public_id": "KBC-000123",
            "category": "Technical",
            "technical_subcategory": "Teams",
            "status": "Pending",
            "status_reason": "Awaiting support meeting",
            "assigned_team": "Support Desk",
            "sla_status": "On Track",
            "created_at": datetime(2026, 5, 7, 10, 0, tzinfo=timezone.utc),
            "metadata": {},
            "conversation_id": 55,
            "conversation_metadata": {},
            "learner_name": "Ali Test",
        }
        booking_summary = {
            "requestedDate": "2026-05-12",
            "requestedTime": "11:30",
            "reservationConfirmed": True,
            "meetingJoinUrl": "https://teams.microsoft.com/l/meetup-join/example",
        }

        with (
            patch.object(services, "sync_open_ticket_inactivity"),
            patch.object(services, "run_query_one", return_value=ticket_row),
            patch.object(services, "run_query", return_value=[]),
            patch.object(services, "get_latest_ticket_booking_summary", return_value=booking_summary),
        ):
            response = services.get_ticket_chat_history_response("KBC-000123")

        self.assertEqual(response["bookingSummary"], booking_summary)
