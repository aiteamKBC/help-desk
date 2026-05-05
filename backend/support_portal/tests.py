from datetime import datetime
from django.test import SimpleTestCase
from unittest.mock import patch
from zoneinfo import ZoneInfo

from support_portal import services


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

    def test_verify_email_response_uses_synced_learner(self):
        learner = {"id": 9, "full_name": "Synced Learner", "email": "synced@example.com"}

        with patch.object(services, "find_learner_by_email", return_value=learner) as find_learner:
            response = services.get_verify_email_response({"email": "SYNCED@EXAMPLE.COM"})

        self.assertEqual(
            response,
            {
                "exists": True,
                "learner": {
                    "id": 9,
                    "fullName": "Synced Learner",
                    "email": "synced@example.com",
                },
                "message": "Email verified.",
            },
        )
        find_learner.assert_called_once_with("synced@example.com")


class SupportSessionValidationTests(SimpleTestCase):
    def test_support_session_window_accepts_uk_hours_until_four_pm(self):
        requested_datetime = datetime(2026, 5, 10, 15, 0, tzinfo=ZoneInfo("Europe/London"))

        self.assertTrue(services.is_within_support_session_window(requested_datetime))

    def test_support_session_window_rejects_after_four_pm_uk_time(self):
        requested_datetime = datetime(2026, 5, 10, 16, 30, tzinfo=ZoneInfo("Europe/London"))

        self.assertFalse(services.is_within_support_session_window(requested_datetime))

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
