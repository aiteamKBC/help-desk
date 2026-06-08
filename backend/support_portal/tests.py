import base64
import json
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from io import StringIO
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ImproperlyConfigured
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.utils import OperationalError as DjangoOperationalError
from django.core.management import call_command
from django.test import RequestFactory, SimpleTestCase
from psycopg import OperationalError as PsycopgOperationalError
from unittest.mock import MagicMock, patch
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
                {"module_name": "Commercial Intelligence"},
                {"module_name": "Martech"},
            ],
        ) as run_communication_centre_query:
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
                    "legacyAdminAccess": False,
                    "entraDirectoryAdmin": False,
                }
            },
        )
        self.assertIn("csrftoken", response.cookies)

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
                    "legacyAdminAccess": False,
                    "entraDirectoryAdmin": False,
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
            patch.object(views, "list_admin_tickets", return_value={"tickets": []}) as list_admin_tickets,
        ):
            response = views.admin_tickets(request)

        self.assertEqual(response.status_code, 200)
        require_agent_session_actor.assert_called_once_with(
            "admin1",
            "instance-1",
            allowed_roles=views.ADMIN_ACCESS_ROLES,
        )
        list_admin_tickets.assert_called_once_with()

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
        save_chat_history.assert_called_once_with(
            "KBC-000001",
            {
                "status": "Open",
                "actorUsername": "fatma",
                "instanceId": "current-instance",
                "messages": [{"sender": "agent", "text": "Hello"}],
            },
        )


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


class SupportSessionValidationTests(SimpleTestCase):
    databases = {"default"}

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
        self.assertEqual(ticket_insert_params[6], 1)

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
        ticket_metadata = json.loads(ticket_insert_params[7])
        self.assertEqual(ticket_metadata["technical_subcategory"], "Others")

    def test_create_ticket_accepts_coverage_technical_subcategory(self):
        requester = {
            "email": "employer@example.com",
            "role": "employer",
            "display_name": "Employer One",
            "learner": None,
            "account": {
                "id": 31,
                "username": "employer1",
                "full_name": "Employer One",
                "email": "employer@example.com",
                "role": "employer",
            },
        }
        learner = {
            "id": 12,
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
                    "email": "employer@example.com",
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
        ticket_insert_call = next(
            call for call in cursor.execute.call_args_list
            if "INSERT INTO tickets" in call.args[0]
        )
        ticket_insert_params = ticket_insert_call.args[1]
        self.assertEqual(ticket_insert_params[3], "Coverage")
        ticket_metadata = json.loads(ticket_insert_params[7])
        self.assertEqual(ticket_metadata["technical_subcategory"], "Coverage")
        notify_operations_team.assert_called_once()
        notification_ticket_id, notification_payload = notify_operations_team.call_args.args
        self.assertEqual(notification_ticket_id, 73)
        self.assertEqual(notification_payload["event"], "coverage_ticket_created")
        self.assertEqual(notification_payload["ticket"]["id"], "KBC-000073")
        self.assertEqual(notification_payload["requester"]["email"], "employer@example.com")
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
            "Coverage requests are only available for coach and employer accounts.",
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
        self.assertEqual(ticket_insert_params[5], "High")

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
        self.assertEqual(ticket_insert_params[5], "High")

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
            "maximumAttendeesCount": 1,
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

    def test_send_chatbot_message_rejects_coach_quick_ticket_only_role(self):
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
        ):
            with self.assertRaises(services.ApiError) as error_context:
                services.send_chatbot_message("KBC-000077", {"message": "hello"})

        self.assertEqual(error_context.exception.status_code, 403)
        self.assertEqual(error_context.exception.message, "Coach accounts can only submit quick tickets or quick calls from the support portal.")

    def test_request_live_chat_rejects_coach_quick_ticket_only_role(self):
        ticket = {
            "id": 77,
            "public_id": "KBC-000077",
            "conversation_id": 55,
            "metadata": {"requester_role": "coach"},
            "status": "Open",
            "status_reason": "",
            "assigned_agent_id": None,
            "learner_email": "coach@example.com",
        }

        with (
            patch.object(services, "sync_open_ticket_inactivity"),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
        ):
            with self.assertRaises(services.ApiError) as error_context:
                services.request_live_chat("KBC-000077")

        self.assertEqual(error_context.exception.status_code, 403)
        self.assertEqual(error_context.exception.message, "Coach accounts can only submit quick tickets or quick calls from the support portal.")

    def test_create_support_session_request_rejects_coach_quick_ticket_only_role(self):
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

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "validate_support_session_request", return_value=""),
            patch.object(services, "resolve_support_session_datetime", return_value=datetime(2026, 6, 12, 9, 0, tzinfo=timezone.utc)),
            patch.object(services, "run_query_one", return_value=ticket),
        ):
            with self.assertRaises(services.ApiError) as error_context:
                services.create_support_session_request(
                    "KBC-000077",
                    {
                        "date": "2026-06-12",
                        "time": "09:00",
                        "scheduledAt": "2026-06-12T09:00:00+00:00",
                    },
                )

        self.assertEqual(error_context.exception.status_code, 403)
        self.assertEqual(error_context.exception.message, "Coach accounts can only submit quick tickets or quick calls from the support portal.")

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
        self.assertEqual(summary["priority"], "Normal")
        self.assertFalse(inactive_summary["chatIsActive"])
        self.assertFalse(inactive_summary["liveChatRequested"])

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
            patch.object(services, "sync_open_ticket_inactivity"),
            patch.object(services, "run_query", return_value=[normal_priority_ticket, closed_high_priority_ticket, high_priority_active_ticket]),
            patch.object(services, "apply_ticket_sla_policy", side_effect=lambda ticket, persist=True: ticket),
        ):
            result = services.list_admin_tickets()

        self.assertEqual([ticket["id"] for ticket in result["tickets"]], ["KBC-000010", "KBC-000011", "KBC-000012"])
        self.assertEqual(result["tickets"][0]["priority"], "High")


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
            "role": "admin",
            "metadata": {},
        }
        registered_session = {
            "id": 4,
            "username": "omar1",
            "fullName": "Omar One",
            "email": "omar1@kentbusinesscollege.com",
            "role": "admin",
            "sessionActive": True,
            "consoleStatus": "Off",
        }

        with (
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
            patch.object(services, "fetch_legacy_support_user_by_username", return_value=legacy_user),
            patch.object(services, "sync_support_staff_account_from_legacy_auth_user") as sync_support_staff_account_from_legacy_auth_user,
            patch.object(services, "register_agent_session") as register_agent_session,
        ):
            with self.assertRaises(services.ApiError) as error_context:
                services.get_admin_login_response(
                    {"username": "coach1", "password": "coach-pass", "instanceId": "instance-3"}
                )

        self.assertEqual(error_context.exception.status_code, 403)
        self.assertEqual(error_context.exception.message, "This account must have support access or admin access.")
        sync_support_staff_account_from_legacy_auth_user.assert_not_called()
        register_agent_session.assert_not_called()

    def test_admin_login_rejects_kbc_auth_user_without_support_or_admin_access(self):
        with patch.object(services, "fetch_legacy_support_user_by_username", return_value=None):
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
        self.assertEqual(error_context.exception.message, "Your Microsoft account does not have Entra admin center access.")

    def test_build_support_staff_role_from_legacy_auth_user_uses_django_superuser_for_superadmin(self):
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
            "role": "admin",
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
            patch.object(services, "persist_agent_metadata") as persist_agent_metadata,
            patch.object(services, "get_open_assigned_live_chat_agent_ids", return_value=set()),
        ):
            response = services.update_agent_support_access(23, support_access=False)

        sync_legacy_support_access_group_membership.assert_called_once_with(77, False)
        saved_metadata = persist_agent_metadata.call_args.args[1]
        self.assertFalse(saved_metadata["legacy_support_access"])
        self.assertFalse(response["legacySupportAccess"])

    def test_remove_agent_soft_removes_manually_added_agent(self):
        agent = {
            "id": 31,
            "email": "omar.badr@kentbusinesscollege.com",
            "metadata": {
                "manually_added_agent": True,
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
        self.assertFalse(saved_metadata["manually_added_agent"])
        self.assertFalse(saved_metadata["legacy_support_access"])
        self.assertFalse(saved_metadata["session_active"])
        self.assertEqual(saved_metadata["console_status"], "Off")
        remove_django_support_access.assert_called_once_with("omar.badr@kentbusinesscollege.com")

    def test_list_agents_returns_only_current_support_access_staff_profiles(self):
        with (
            patch.object(
                services,
                "fetch_legacy_support_directory_users",
                return_value=[
                    {
                        "id": 77,
                        "username": "omar1",
                        "first_name": "Omar",
                        "last_name": "One",
                        "full_name": "Omar One",
                        "email": "omar1@kentbusinesscollege.com",
                        "is_staff": False,
                        "is_superuser": False,
                        "is_active": True,
                        "has_support_access": True,
                        "has_admin_access": False,
                    }
                ],
            ),
            patch.object(
                services,
                "sync_support_staff_account_from_legacy_auth_user",
                return_value={
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
            ),
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
                    {
                        "id": 24,
                        "username": "legacyadmin",
                        "full_name": "Legacy Admin",
                        "email": "legacyadmin@example.com",
                        "account_scope": "staff",
                        "role": "admin",
                        "is_active": True,
                        "metadata": {
                            "legacy_auth_user_id": 88,
                            "legacy_support_access": False,
                            "legacy_admin_access": True,
                        },
                    },
                    {
                        "id": 25,
                        "username": "student1",
                        "full_name": "Student One",
                        "email": "student1@example.com",
                        "account_scope": "requester",
                        "role": "user",
                        "is_active": True,
                        "metadata": {},
                    },
                ],
            ),
            patch.object(services, "get_open_assigned_live_chat_agent_ids", return_value=set()),
        ):
            response = services.list_agents()

        returned_ids = {account["id"] for account in response["accounts"]}
        self.assertEqual(returned_ids, {23})

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
        ):
            response = services.sync_support_staff_account_from_legacy_auth_user(legacy_user)

        self.assertEqual(response, refreshed_account)
        update_params = cursor.execute.call_args.args[1]
        updated_metadata = json.loads(update_params[5])
        self.assertTrue(updated_metadata["session_active"])
        self.assertEqual(updated_metadata["session_instance_id"], "instance-123")
        self.assertEqual(updated_metadata["console_status"], "Available")
        self.assertTrue(updated_metadata["legacy_support_access"])
        self.assertTrue(updated_metadata["legacy_admin_access"])

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
        new_ticket_metadata = json.loads(ticket_insert_params[-1])
        self.assertEqual(new_ticket_metadata["requester_role"], "employer")
        self.assertEqual(new_ticket_metadata["requester_account_id"], 71)
        self.assertEqual(new_ticket_metadata["requester_username"], "employer1")

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
            "role": "admin",
            "metadata": {
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
            "role": "admin",
            "metadata": {
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

    def test_update_admin_ticket_allows_superadmin_to_reassign_existing_ticket(self):
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
            "username": "super",
            "full_name": "Super Admin",
            "role": "superadmin",
            "email": "super@example.com",
        }
        selected_agent = {
            "id": 9,
            "username": "omar",
            "full_name": "Omar Helmy",
            "role": "admin",
            "email": "omar@example.com",
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
                {"note": "Reassigned", "actorUsername": "super", "assignedAgentId": 9},
            )

        self.assertEqual(response, detail)
        update_params = cursor.execute.call_args_list[0].args[1]
        self.assertEqual(update_params[2], 9)
        self.assertEqual(update_params[3], "Support Desk")
        insert_history_event.assert_any_call(
            17,
            "assignment_changed",
            {"id": 1, "role": "superadmin", "label": "Super Admin"},
            {"fromAgentId": 5, "toAgentId": 9, "toAgentName": "Omar Helmy"},
        )


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

        self.assertEqual(run_query.call_args.args[1], ["9", "9", "9", "9", "9", "9", 12])
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

    def test_try_auto_assign_quick_ticket_prefers_available_admin_and_updates_ticket(self):
        ticket = {
            "id": 23,
            "public_id": "KBC-000023",
            "conversation_id": 88,
            "assigned_agent_id": None,
            "assigned_team": "",
            "metadata": {},
            "conversation_metadata": {},
        }
        available_admin = {
            "id": 5,
            "username": "ahmed",
            "full_name": "Ahmed Hamamo",
            "role": "admin",
            "metadata": {
                "session_active": True,
                "session_started_at": "2026-05-14T09:00:00+00:00",
                "queue_joined_at": "2026-05-14T09:00:00+00:00",
                "console_status": "Available",
            },
        }
        off_admin = {
            "id": 8,
            "username": "omar",
            "full_name": "Omar1",
            "role": "admin",
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
            patch.object(services, "run_query", return_value=[off_admin, available_admin]),
            patch.object(services, "get_open_assigned_live_chat_agent_ids", return_value=set()),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event"),
            patch.object(services, "persist_agent_metadata") as persist_agent_metadata,
        ):
            assigned_admin = services.try_auto_assign_quick_ticket(ticket, now=assignment_time)

        self.assertEqual(assigned_admin, available_admin)
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

    def test_submit_coverage_tutor_request_does_not_persist_when_webhook_fails(self):
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
            patch.object(
                services,
                "send_coverage_tutor_request_webhook",
                return_value={"configured": True, "delivered": False, "status": 500, "response": {"message": "Workflow execution failed"}},
            ),
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

        self.assertEqual(raised_error.exception.status_code, 502)
        self.assertEqual(raised_error.exception.message, "We could not send this tutor request right now.")
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
                "admin_documentation": {
                    "inquiry": "Coverage request",
                    "ticketId": "KBC-000041",
                    "coverageCards": [
                        {
                            "id": "card-1",
                            "type": "tutor_choice",
                            "tutor": "Nathan",
                            "tutorEmail": "nathan@example.com",
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
            patch.object(services, "send_coverage_tutor_request_webhook", return_value={"configured": True, "delivered": True, "status": 200, "response": {"ok": True}}) as send_webhook,
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
        send_webhook.assert_called_once()
        webhook_payload = send_webhook.call_args.args[0]
        self.assertEqual(webhook_payload["tutor"]["name"], "Nathan")
        self.assertEqual(webhook_payload["tutor"]["email"], "nathan@example.com")
        self.assertEqual(len(webhook_payload["request"]["presentationFiles"]), 1)

        update_params = cursor.execute.call_args_list[0].args[1]
        self.assertEqual(update_params[0], "Pending")
        self.assertEqual(update_params[1], "Tutor Requested")
        self.assertEqual(update_params[2], 7)
        self.assertEqual(update_params[3], "Support Desk")
        persisted_metadata = json.loads(update_params[5])
        persisted_card = persisted_metadata["admin_documentation"]["coverageCards"][0]
        self.assertEqual(persisted_card["requestStatus"], "requested")
        self.assertEqual(persisted_card["requestSubmittedByAgentId"], 7)
        self.assertTrue(persisted_card["responseToken"])

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
            patch.object(services, "send_coverage_tutor_request_webhook", return_value={"configured": True, "delivered": True, "status": 200, "response": {"ok": True}}) as send_webhook,
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
        webhook_payload = send_webhook.call_args.args[0]
        self.assertEqual(webhook_payload["tutor"]["email"], "andrew.millington@kentbusinesscollege.com")
        update_params = cursor.execute.call_args_list[0].args[1]
        self.assertEqual(update_params[2], 7)
        self.assertEqual(update_params[3], "Support Desk")
        persisted_metadata = json.loads(update_params[5])
        persisted_card = persisted_metadata["admin_documentation"]["coverageCards"][0]
        self.assertEqual(persisted_card["tutorEmail"], "andrew.millington@kentbusinesscollege.com")

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
            patch.object(services, "send_coverage_tutor_request_webhook", return_value={"configured": True, "delivered": True, "status": 200, "response": {"ok": True}}),
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
            patch.object(services, "notify_coverage_tutor_refusal_mail_webhook") as notify_refusal_mail,
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
        persisted_metadata = json.loads(update_params[3])
        persisted_cards = persisted_metadata["admin_documentation"]["coverageCards"]
        self.assertEqual(persisted_metadata["latest_coverage_tutor_response"]["outcome"], "rejected")
        self.assertEqual(persisted_cards[0]["requestStatus"], "refused")
        self.assertEqual(persisted_cards[1]["replyOutcome"], "refused")
        notify_refusal_mail.assert_called_once()
        self.assertEqual(notify_refusal_mail.call_args.args[0], 53)
        webhook_payload = notify_refusal_mail.call_args.args[1]
        self.assertEqual(webhook_payload["event"], "coverage_tutor_refused")
        self.assertEqual(webhook_payload["ticket"]["id"], "KBC-000053")
        self.assertEqual(webhook_payload["ticket"]["statusReason"], "Tutor Rejected")
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
                        "sessionDetails": "Module: APM",
                        "requestStatus": "pending",
                        "locked": True,
                        "submittedAt": "2026-06-03T10:30:00Z",
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
        self.assertEqual(normalized_documentation["coverageCards"][0]["requestStatus"], "requested")
        self.assertEqual(len(normalized_documentation["coverageCards"][0]["presentationFiles"]), 1)
        self.assertEqual(normalized_documentation["coverageCards"][1]["type"], "note")
        self.assertEqual(normalized_documentation["coverageCards"][1]["note"], "Follow up with another tutor if needed.")

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

    def test_get_ticket_chat_context_response_rejects_coach_quick_ticket_only_role(self):
        ticket_row = {
            "public_id": "KBC-000123",
            "metadata": {"requester_role": "coach"},
            "status": "Open",
            "status_reason": "",
            "category": "Technical",
            "technical_subcategory": "Teams",
            "learner_id": 11,
            "learner_full_name": "Coach One",
            "learner_email": "coach@example.com",
        }

        with (
            patch.object(services, "sync_open_ticket_inactivity"),
            patch.object(services, "run_query_one", return_value=ticket_row),
        ):
            with self.assertRaises(services.ApiError) as error_context:
                services.get_ticket_chat_context_response("KBC-000123")

        self.assertEqual(error_context.exception.status_code, 403)
        self.assertEqual(error_context.exception.message, "Coach accounts can only submit quick tickets or quick calls from the support portal.")

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
