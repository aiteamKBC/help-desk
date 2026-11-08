"""Per-user notification dismissals, ticket archiving and archived-ticket retention.

All tests are database-free: queries and the DB connection are mocked.
"""
from contextlib import nullcontext
from datetime import datetime, timezone
from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from . import services


def build_mock_connection():
    cursor = MagicMock()
    cursor_context = MagicMock()
    cursor_context.__enter__.return_value = cursor
    cursor_context.__exit__.return_value = None
    mock_connection = MagicMock()
    mock_connection.cursor.return_value = cursor_context
    return mock_connection, cursor


HABIBA = {"id": 7, "username": "habiba", "full_name": "Habiba", "role": "agent"}
RAWAN = {"id": 8, "username": "rawan", "full_name": "Rawan", "role": "agent"}

SUPPORT_QUEUE_EVENT = {
    "ticketId": "KBC-000846",
    "requesterName": "Meeka Hany",
    "requesterEmail": "meeka@example.com",
    "requesterRole": "user",
    "queue": services.ASSIGNED_TEAM_SUPPORT_DESK,
    "reason": "support_ticket_created",
    "createdAt": "2026-10-31T16:36:00+00:00",
}
SUPPORT_QUEUE_KEY = "support-queue:KBC-000846:support_ticket_created:2026-10-31T16:36:00+00:00"


def build_ticket(ticket_id=846, public_id="KBC-000846", metadata=None):
    return {
        "id": ticket_id,
        "public_id": public_id,
        "technical_subcategory": "LMS",
        "assigned_team": services.ASSIGNED_TEAM_SUPPORT_DESK,
        "metadata": {"pending_support_queue_notification": dict(SUPPORT_QUEUE_EVENT)} if metadata is None else metadata,
    }


class NotificationKeyTests(SimpleTestCase):
    def test_key_matches_admin_dashboard_key(self):
        key = services.build_ticket_notification_key(
            services.NOTIFICATION_KIND_SUPPORT_QUEUE,
            "KBC-000846",
            {"pending_support_queue_notification": SUPPORT_QUEUE_EVENT},
        )
        self.assertEqual(key, SUPPORT_QUEUE_KEY)

    def test_new_event_on_same_ticket_gets_a_new_key(self):
        later_event = {**SUPPORT_QUEUE_EVENT, "reason": "support_session_requested", "createdAt": "2026-11-02T09:00:00Z"}
        key = services.build_ticket_notification_key(
            services.NOTIFICATION_KIND_SUPPORT_QUEUE,
            "KBC-000846",
            {"pending_support_queue_notification": later_event},
        )
        self.assertNotEqual(key, SUPPORT_QUEUE_KEY)

    def test_same_event_processed_again_gets_the_same_key(self):
        metadata = {"pending_support_queue_notification": SUPPORT_QUEUE_EVENT}
        first = services.build_ticket_notification_key(services.NOTIFICATION_KIND_SUPPORT_QUEUE, "KBC-000846", metadata)
        second = services.build_ticket_notification_key(services.NOTIFICATION_KIND_SUPPORT_QUEUE, "KBC-000846", dict(metadata))
        self.assertEqual(first, second)

    def test_no_key_without_a_pending_event(self):
        self.assertIsNone(services.build_ticket_notification_key(services.NOTIFICATION_KIND_SUPPORT_QUEUE, "KBC-000846", {}))
        self.assertIsNone(services.build_ticket_notification_key("teams-call", "KBC-000846", {}))


class PersonalDismissTests(SimpleTestCase):
    def dismiss(self, actor, ticket, *, accessible=True, storage_ready=True, endpoint=None):
        mock_connection, cursor = build_mock_connection()
        endpoint = endpoint or services.acknowledge_support_queue_notification
        with (
            patch.object(services, "fetch_actor_by_username", return_value=actor),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "actor_can_access_admin_ticket", return_value=accessible),
            patch.object(services, "is_support_table_available", return_value=storage_ready),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "fetch_admin_ticket_detail", return_value={"ticket": {"id": ticket["public_id"]}}),
        ):
            response = endpoint(ticket["public_id"], {"actorUsername": actor["username"]})
        return response, cursor

    def test_dismiss_records_state_for_the_signed_in_admin_only(self):
        response, cursor = self.dismiss(HABIBA, build_ticket())

        cursor.executemany.assert_called_once()
        sql, rows = cursor.executemany.call_args.args
        self.assertIn("ON CONFLICT (account_id, notification_key) DO NOTHING", sql)
        self.assertEqual(rows, [(7, 846, SUPPORT_QUEUE_KEY)])
        self.assertEqual(response["dismissedNotificationKeys"], [SUPPORT_QUEUE_KEY])

    def test_dismiss_never_changes_the_ticket(self):
        _response, cursor = self.dismiss(HABIBA, build_ticket())
        # Only the dismissal insert runs: no UPDATE of tickets (status, metadata).
        cursor.execute.assert_not_called()

    def test_two_admins_get_independent_dismissal_rows(self):
        _r1, habiba_cursor = self.dismiss(HABIBA, build_ticket())
        _r2, rawan_cursor = self.dismiss(RAWAN, build_ticket())
        self.assertEqual(habiba_cursor.executemany.call_args.args[1], [(7, 846, SUPPORT_QUEUE_KEY)])
        self.assertEqual(rawan_cursor.executemany.call_args.args[1], [(8, 846, SUPPORT_QUEUE_KEY)])

    def test_coverage_and_learning_plan_dismissals_are_personal_too(self):
        coverage_ticket = build_ticket(metadata={
            "pending_coverage_ticket_notification": {
                "ticketId": "KBC-000846", "requesterEmail": "m@example.com", "createdAt": "2026-10-31T10:00:00Z",
            },
        })
        _response, cursor = self.dismiss(HABIBA, coverage_ticket, endpoint=services.acknowledge_coverage_ticket_notification)
        self.assertEqual(cursor.executemany.call_args.args[1][0][0], 7)
        cursor.execute.assert_not_called()

        transfer_ticket = build_ticket(metadata={
            "pending_learning_plan_transfer_notification": {
                "ticketId": "KBC-000846", "requesterEmail": "m@example.com", "fromTeam": "Support Desk",
                "toTeam": "Learning Plan Team", "transferredAt": "2026-10-31T10:00:00Z",
            },
        })
        _response, cursor = self.dismiss(HABIBA, transfer_ticket, endpoint=services.acknowledge_learning_plan_transfer_notification)
        self.assertEqual(cursor.executemany.call_args.args[1][0][0], 7)
        cursor.execute.assert_not_called()

    def test_admin_without_ticket_access_cannot_dismiss(self):
        with self.assertRaises(services.ApiError) as raised:
            self.dismiss(HABIBA, build_ticket(), accessible=False)
        self.assertEqual(raised.exception.status_code, 403)

    def test_without_the_new_table_the_dismissal_is_saved_on_the_admins_own_account(self):
        response, cursor = self.dismiss(HABIBA, build_ticket(), storage_ready=False)

        cursor.executemany.assert_not_called()
        sql, params = cursor.execute.call_args.args
        self.assertIn("UPDATE support_accounts", sql)
        self.assertIn("jsonb_set", sql)
        self.assertNotIn("UPDATE tickets", sql)
        self.assertEqual(params, [[SUPPORT_QUEUE_KEY], 7])
        self.assertEqual(response["dismissedNotificationKeys"], [SUPPORT_QUEUE_KEY])

    def test_account_metadata_writes_keep_saved_dismissals(self):
        mock_connection, cursor = build_mock_connection()
        with patch.object(services, "connection", mock_connection):
            services.persist_agent_metadata(7, {"session_instance_id": "abc"})
        sql = cursor.execute.call_args.args[0]
        self.assertIn("'dismissed_notification_keys'", sql)
        self.assertIn("'notifications_cleared_at'", sql)
        self.assertIn("jsonb_strip_nulls", sql)

    def test_sign_in_is_required(self):
        with self.assertRaises(services.ApiError) as raised:
            services.acknowledge_support_queue_notification("KBC-000846", {"actorUsername": ""})
        self.assertEqual(raised.exception.status_code, 403)


class DismissAllTests(SimpleTestCase):
    def dismiss_all(self, actor, tickets, notifications, *, accessible_ids=None):
        mock_connection, cursor = build_mock_connection()
        accessible_ids = set(accessible_ids if accessible_ids is not None else [ticket["id"] for ticket in tickets])
        with (
            patch.object(services, "fetch_actor_by_username", return_value=actor),
            patch.object(services, "run_query", return_value=tickets),
            patch.object(services, "actor_can_access_admin_ticket", side_effect=lambda _actor, ticket: ticket["id"] in accessible_ids),
            patch.object(services, "is_support_table_available", return_value=True),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "connection", mock_connection),
        ):
            response = services.dismiss_admin_ticket_notifications({
                "actorUsername": actor["username"],
                "accountId": 999,  # must be ignored: ownership comes from the session
                "notifications": notifications,
            })
        return response, cursor

    def test_dismiss_all_records_rows_only_for_the_signed_in_admin(self):
        tickets = [build_ticket(), build_ticket(845, "KBC-000845")]
        response, cursor = self.dismiss_all(HABIBA, tickets, [
            {"ticketId": "KBC-000846", "kind": "support-queue"},
            {"ticketId": "KBC-000845", "kind": "support-queue"},
        ])

        rows = cursor.executemany.call_args.args[1]
        self.assertEqual({row[0] for row in rows}, {7})
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(response["dismissedNotificationKeys"]), 2)
        cursor.execute.assert_not_called()

    def test_dismiss_all_skips_inaccessible_stale_and_unknown_items(self):
        tickets = [build_ticket(), build_ticket(845, "KBC-000845"), build_ticket(844, "KBC-000844", metadata={})]
        response, cursor = self.dismiss_all(HABIBA, tickets, [
            {"ticketId": "KBC-000846", "kind": "support-queue"},
            {"ticketId": "KBC-000845", "kind": "support-queue"},   # no access
            {"ticketId": "KBC-000844", "kind": "support-queue"},   # already handled / no event
            {"ticketId": "KBC-000846", "kind": "teams-call"},      # not a shared kind
            {"ticketId": "KBC-999999", "kind": "support-queue"},   # unknown ticket
        ], accessible_ids=[846, 844])

        self.assertEqual(cursor.executemany.call_args.args[1], [(7, 846, SUPPORT_QUEUE_KEY)])
        self.assertEqual(response["skipped"], 4)

    def test_dismiss_all_moves_only_this_admins_cut_off_to_now(self):
        mock_connection, cursor = build_mock_connection()
        with (
            patch.object(services, "fetch_actor_by_username", return_value=HABIBA),
            patch.object(services, "run_query", return_value=[build_ticket()]),
            patch.object(services, "actor_can_access_admin_ticket", return_value=True),
            patch.object(services, "is_support_table_available", return_value=True),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "connection", mock_connection),
        ):
            services.dismiss_admin_ticket_notifications({
                "actorUsername": "habiba",
                "notifications": [{"ticketId": "KBC-000846", "kind": "support-queue"}],
                "clearAll": True,
            })
        sql, params = cursor.execute.call_args.args
        self.assertIn("'{notifications_cleared_at}'", sql)
        self.assertNotIn("UPDATE tickets", sql)
        self.assertEqual(params[1], 7)

    def test_dismiss_all_limits_the_batch_size(self):
        with self.assertRaises(services.ApiError) as raised:
            self.dismiss_all(HABIBA, [], [{"ticketId": "KBC-1", "kind": "support-queue"}] * (services.MAX_BULK_NOTIFICATION_DISMISSALS + 1))
        self.assertEqual(raised.exception.status_code, 400)


class DismissedKeysInTicketListTests(SimpleTestCase):
    serialized = [{"id": "KBC-000846", "pendingSupportQueueNotification": SUPPORT_QUEUE_EVENT}]

    def test_list_returns_only_the_signed_in_admins_dismissals(self):
        with (
            patch.object(services, "is_support_table_available", return_value=True),
            patch.object(services, "run_query_one", return_value={"metadata": {"notifications_cleared_at": "2026-01-01T00:00:00+00:00"}}),
            patch.object(services, "run_query", return_value=[{"notification_key": SUPPORT_QUEUE_KEY}]) as run_query,
        ):
            keys = services.list_actor_dismissed_notification_keys(HABIBA, self.serialized)

        self.assertEqual(keys, [SUPPORT_QUEUE_KEY])
        self.assertEqual(run_query.call_args.args[1][0], 7)

    def test_dismissed_state_is_read_from_the_database_each_time(self):
        # Nothing is cached in the browser or session, so a dismissal stays after
        # refresh, logout and login: every list load reads the stored rows.
        with (
            patch.object(services, "is_support_table_available", return_value=True),
            patch.object(services, "run_query_one", return_value={"metadata": {"notifications_cleared_at": "2026-01-01T00:00:00+00:00"}}),
            patch.object(services, "run_query", return_value=[{"notification_key": SUPPORT_QUEUE_KEY}]) as run_query,
        ):
            services.list_actor_dismissed_notification_keys(HABIBA, self.serialized)
            services.list_actor_dismissed_notification_keys(HABIBA, self.serialized)
        self.assertEqual(run_query.call_count, 2)

    def test_no_actor_means_no_dismissals(self):
        self.assertEqual(services.list_actor_dismissed_notification_keys(None, self.serialized), [])

    def test_dismissals_saved_on_the_account_are_returned_without_the_new_table(self):
        account = {"metadata": {
            "dismissed_notification_keys": [SUPPORT_QUEUE_KEY, "support-queue:KBC-000001:x:y"],
            "notifications_cleared_at": "2026-01-01T00:00:00+00:00",
        }}
        with (
            patch.object(services, "is_support_table_available", return_value=False),
            patch.object(services, "run_query_one", return_value=account) as run_query_one,
        ):
            keys = services.list_actor_dismissed_notification_keys(HABIBA, self.serialized)
        # Only keys for notifications in this list, read from this admin's own row.
        self.assertEqual(keys, [SUPPORT_QUEUE_KEY])
        self.assertEqual(run_query_one.call_args.args[1], [7])

    def test_existing_backlog_is_cleared_the_first_time_an_admin_loads_the_dashboard(self):
        first_load_at = "2026-11-08T22:00:00+00:00"
        with (
            patch.object(services, "is_support_table_available", return_value=False),
            patch.object(services, "run_query_one", side_effect=[{"metadata": {}}, {"cleared_at": first_load_at}]) as run_query_one,
        ):
            keys = services.list_actor_dismissed_notification_keys(HABIBA, self.serialized)
        self.assertEqual(keys, [SUPPORT_QUEUE_KEY])
        init_sql, init_params = run_query_one.call_args_list[1].args
        self.assertIn("NOT (COALESCE(metadata, '{}'::jsonb) ? 'notifications_cleared_at')", init_sql)
        self.assertEqual(init_params[1], 7)

    def test_notifications_after_the_cut_off_still_show_and_count(self):
        newer = [{"id": "KBC-000900", "pendingSupportQueueNotification": {**SUPPORT_QUEUE_EVENT, "ticketId": "KBC-000900", "createdAt": "2026-11-09T08:00:00+00:00"}}]
        with (
            patch.object(services, "is_support_table_available", return_value=False),
            patch.object(services, "run_query_one", return_value={"metadata": {"notifications_cleared_at": "2026-11-08T22:00:00+00:00"}}),
        ):
            self.assertEqual(services.list_actor_dismissed_notification_keys(HABIBA, self.serialized + newer), [SUPPORT_QUEUE_KEY])


class ArchiveTests(SimpleTestCase):
    def archive(self, ticket, actor=HABIBA, archived=True, accessible=True):
        mock_connection, cursor = build_mock_connection()
        with (
            patch.object(services, "fetch_actor_by_username", return_value=actor),
            patch.object(services, "run_query_one", return_value=ticket) as run_query_one,
            patch.object(services, "actor_can_access_admin_ticket", return_value=accessible),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "insert_history_event") as insert_history_event,
            patch.object(services, "fetch_admin_ticket_detail", return_value={"ticket": {"id": ticket["public_id"]}}),
        ):
            services.update_admin_ticket_archive_state(ticket["public_id"], {"actorUsername": actor["username"], "archived": archived})
        return cursor, run_query_one, insert_history_event

    def test_archive_updates_only_the_selected_ticket_and_keeps_its_status(self):
        ticket = {**build_ticket(), "is_archived": False}
        cursor, run_query_one, insert_history_event = self.archive(ticket)

        sql, params = cursor.execute.call_args.args
        self.assertIn("WHERE id = %s", sql)
        self.assertIn("archived_at = CASE WHEN %s THEN NOW()", sql)
        self.assertNotIn("status", sql.replace("is_archived", ""))
        self.assertEqual(params[-1], 846)
        self.assertIn("FOR UPDATE", run_query_one.call_args.args[0])
        insert_history_event.assert_called_once()

    def test_archiving_an_already_archived_ticket_is_a_no_op(self):
        ticket = {**build_ticket(), "is_archived": True}
        cursor, _run_query_one, insert_history_event = self.archive(ticket)
        cursor.execute.assert_not_called()
        insert_history_event.assert_not_called()

    def test_unauthorised_archive_is_rejected(self):
        with self.assertRaises(services.ApiError) as raised:
            self.archive({**build_ticket(), "is_archived": False}, accessible=False)
        self.assertEqual(raised.exception.status_code, 403)


class RetentionDateTests(SimpleTestCase):
    def check(self, archived, expected):
        self.assertEqual(services.get_archived_ticket_deletion_at(archived), expected)

    def test_three_calendar_months(self):
        self.check(datetime(2026, 12, 15, 9, 30, tzinfo=timezone.utc), datetime(2027, 3, 15, 9, 30, tzinfo=timezone.utc))

    def test_month_end_clamps_to_the_last_day(self):
        self.check(datetime(2026, 11, 30, tzinfo=timezone.utc), datetime(2027, 2, 28, tzinfo=timezone.utc))
        self.check(datetime(2027, 11, 30, tzinfo=timezone.utc), datetime(2028, 2, 29, tzinfo=timezone.utc))
        self.check(datetime(2027, 1, 31, tzinfo=timezone.utc), datetime(2027, 4, 30, tzinfo=timezone.utc))
        self.check(datetime(2027, 8, 31, tzinfo=timezone.utc), datetime(2027, 11, 30, tzinfo=timezone.utc))

    def test_not_a_fixed_ninety_days(self):
        archived = datetime(2027, 1, 1, tzinfo=timezone.utc)
        self.assertEqual((services.get_archived_ticket_deletion_at(archived) - archived).days, 90)
        archived = datetime(2027, 6, 1, tzinfo=timezone.utc)
        self.assertEqual((services.get_archived_ticket_deletion_at(archived) - archived).days, 92)

    def test_converted_to_utc_and_unknown_dates_have_no_deletion_date(self):
        self.check("2026-11-30T23:30:00-02:00", datetime(2027, 3, 1, 1, 30, tzinfo=timezone.utc))
        self.check(None, None)


class PurgeArchivedTicketTests(SimpleTestCase):
    ARCHIVED_AT = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
    DEADLINE = datetime(2026, 11, 30, 12, 0, tzinfo=timezone.utc)

    def purge(self, ticket, now, *, conversation_deleted=False, delete_side_effect=None):
        mock_connection, _cursor = build_mock_connection()
        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "connection", mock_connection),
            patch.object(services, "run_query_one", side_effect=[ticket, {"id": 1}, {"id": 2}]) as run_query_one,
            patch.object(services, "list_ticket_attachment_storage_keys", return_value=["KBC-000017/a.pdf"]),
            patch.object(services, "list_conversation_attachment_storage_keys", return_value=["KBC-000017/chat/b.png"]),
            patch.object(services, "delete_ticket_database_records", return_value=conversation_deleted, side_effect=delete_side_effect) as delete_records,
            patch.object(services, "delete_unreferenced_attachment_files", return_value={"deleted": 1, "retained": 0, "failed": 0}) as delete_files,
        ):
            result = services.purge_archived_ticket(17, now=now)
        return result, delete_records, delete_files, run_query_one

    def ticket(self, **overrides):
        return {
            "id": 17, "public_id": "KBC-000017", "is_archived": True, "archived_at": self.ARCHIVED_AT,
            "conversation_id": 5, "conversation_metadata": {}, **overrides,
        }

    def test_ticket_is_kept_before_the_deadline(self):
        result, delete_records, delete_files, _q = self.purge(self.ticket(), self.DEADLINE.replace(second=0, minute=59, hour=11))
        self.assertEqual(result["outcome"], "skipped")
        delete_records.assert_not_called()
        delete_files.assert_not_called()

    def test_ticket_is_deleted_at_the_deadline(self):
        result, delete_records, delete_files, run_query_one = self.purge(self.ticket(), self.DEADLINE)
        self.assertEqual(result["outcome"], "deleted")
        delete_records.assert_called_once()
        delete_files.assert_called_once()
        self.assertIn("FOR UPDATE OF t SKIP LOCKED", run_query_one.call_args_list[0].args[0])

    def test_chat_files_are_only_removed_with_the_conversation(self):
        _r, _d, delete_files, _q = self.purge(self.ticket(), self.DEADLINE, conversation_deleted=False)
        self.assertEqual(delete_files.call_args.args[0], ["KBC-000017/a.pdf"])
        _r, _d, delete_files, _q = self.purge(self.ticket(), self.DEADLINE, conversation_deleted=True)
        self.assertEqual(delete_files.call_args.args[0], ["KBC-000017/a.pdf", "KBC-000017/chat/b.png"])

    def test_non_archived_and_legacy_tickets_are_never_deleted(self):
        result, delete_records, _f, _q = self.purge(self.ticket(is_archived=False), self.DEADLINE)
        self.assertEqual(result["outcome"], "skipped")
        result, delete_records2, _f, _q = self.purge(self.ticket(archived_at=None), self.DEADLINE)
        self.assertEqual(result["outcome"], "skipped")
        delete_records.assert_not_called()
        delete_records2.assert_not_called()

    def test_retry_after_deletion_or_while_locked_is_a_no_op(self):
        result, delete_records, _f, _q = self.purge(None, self.DEADLINE)
        self.assertEqual(result["outcome"], "skipped")
        delete_records.assert_not_called()

    def test_failure_is_audited_without_personal_content(self):
        result, _d, delete_files, run_query_one = self.purge(
            self.ticket(), self.DEADLINE, delete_side_effect=RuntimeError("learner said something private"),
        )
        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(result["detail"], "RuntimeError")
        delete_files.assert_not_called()
        audit_params = run_query_one.call_args_list[-1].args[1]
        self.assertEqual(audit_params[3], "failed")
        self.assertNotIn("private", " ".join(str(value) for value in audit_params))


class SharedAttachmentTests(SimpleTestCase):
    def test_files_still_referenced_elsewhere_are_kept(self):
        with (
            patch.object(services, "run_query", return_value=[{"storage_url": "shared/file.pdf"}]),
            patch.object(services, "delete_support_attachment_file") as delete_file,
        ):
            counts = services.delete_unreferenced_attachment_files(
                ["shared/file.pdf", "KBC-000017/own.pdf", "KBC-000017/own.pdf", ""],
                ticket_public_id="KBC-000017",
            )
        delete_file.assert_called_once_with("KBC-000017/own.pdf")
        self.assertEqual(counts, {"deleted": 1, "retained": 1, "failed": 0})


class PurgeExpiredArchivedTicketsTests(SimpleTestCase):
    NOW = datetime(2027, 3, 1, tzinfo=timezone.utc)

    def run_purge(self, *, execute):
        candidates = [{"id": 17, "public_id": "KBC-000017", "archived_at": datetime(2026, 11, 30, tzinfo=timezone.utc)}]
        with (
            patch.object(services, "is_support_table_available", return_value=True),
            patch.object(services, "run_query", side_effect=[[{"public_id": "KBC-000003"}], candidates, []]) as run_query,
            patch.object(services, "purge_archived_ticket", return_value={"outcome": "deleted", "ticketId": "KBC-000017"}) as purge_one,
        ):
            report = services.purge_expired_archived_tickets(now=self.NOW, execute=execute)
        return report, purge_one, run_query

    def test_dry_run_reports_without_deleting(self):
        report, purge_one, run_query = self.run_purge(execute=False)
        purge_one.assert_not_called()
        self.assertEqual([item["ticketId"] for item in report["eligible"]], ["KBC-000017"])
        self.assertEqual(report["legacyMissingArchivedAt"], ["KBC-000003"])
        candidate_sql = run_query.call_args_list[1].args[0]
        self.assertIn("is_archived = TRUE", candidate_sql)
        self.assertIn("archived_at IS NOT NULL", candidate_sql)
        self.assertIn("INTERVAL '3 months'", candidate_sql)

    def test_execute_deletes_eligible_tickets(self):
        report, purge_one, _q = self.run_purge(execute=True)
        purge_one.assert_called_once_with(17, now=self.NOW)
        self.assertEqual(len(report["deleted"]), 1)


class PurgeCommandTests(SimpleTestCase):
    @override_settings(ARCHIVED_TICKET_RETENTION_PURGE_ENABLED=False)
    def test_execute_is_refused_unless_explicitly_enabled(self):
        with patch.object(services, "purge_expired_archived_tickets") as purge:
            with self.assertRaises(CommandError):
                call_command("purge_expired_archived_tickets", "--execute", stdout=StringIO())
        purge.assert_not_called()

    def test_default_is_a_dry_run(self):
        report = {"now": "x", "eligible": [], "deleted": [], "skipped": [], "failed": [], "legacyMissingArchivedAt": []}
        with patch.object(services, "purge_expired_archived_tickets", return_value=report) as purge:
            out = StringIO()
            call_command("purge_expired_archived_tickets", stdout=out)
        self.assertFalse(purge.call_args.kwargs["execute"])
        self.assertIn('"mode": "dry-run"', out.getvalue())


class RecentLogDismissTests(SimpleTestCase):
    def test_dismissing_a_log_item_hides_it_for_the_signed_in_admin_only(self):
        rows = [
            {"history_id": 501, "id": 846, "public_id": "KBC-000846", "technical_subcategory": "LMS", "assigned_team": "Support Desk", "metadata": {}},
            {"history_id": 502, "id": 845, "public_id": "KBC-000845", "technical_subcategory": "LMS", "assigned_team": "Support Desk", "metadata": {}},
        ]
        mock_connection, cursor = build_mock_connection()
        with (
            patch.object(services, "fetch_actor_by_username", return_value=HABIBA),
            patch.object(services, "run_query", return_value=rows),
            patch.object(services, "actor_can_access_admin_ticket", side_effect=lambda _actor, row: row["id"] == 846),
            patch.object(services, "is_support_table_available", return_value=True),
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "connection", mock_connection),
        ):
            response = services.dismiss_admin_ticket_notifications({"actorUsername": "habiba", "logIds": [501, 502, "x"]})

        self.assertEqual(cursor.executemany.call_args.args[1], [(7, 846, "log:501")])
        self.assertEqual(response["dismissedNotificationKeys"], ["log:501"])
        cursor.execute.assert_not_called()  # the ticket and its history are untouched

    def test_recent_log_leaves_out_hidden_items(self):
        history = [{"id": 501}, {"id": 502}]
        with (
            patch.object(services, "require_agent_session_actor", return_value=HABIBA),
            patch.object(services, "run_query", return_value=history),
            patch.object(services, "filter_admin_tickets_for_actor", side_effect=lambda rows, _actor: rows),
            patch.object(services, "get_account_dismissed_notification_keys", return_value={"log:501"}) as dismissed,
            patch.object(services, "serialize_admin_notification_log_item", side_effect=lambda row: {"id": row["id"]}),
        ):
            response = services.list_admin_notifications("habiba", "instance")

        self.assertEqual(response["notifications"], [{"id": 502}])
        self.assertEqual(dismissed.call_args.args[0], 7)
