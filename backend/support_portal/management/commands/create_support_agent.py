from __future__ import annotations

import json
from datetime import datetime, timezone

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from support_portal.roles import ACCOUNT_ROLES, DEFAULT_ACCOUNT_ROLE, derive_account_scope_from_role
from support_portal.services import normalize_json_object


class Command(BaseCommand):
    help = "Create or update a support account with a hashed password stored in support account metadata."

    def add_arguments(self, parser):
        parser.add_argument("username", help="Support account username")
        parser.add_argument("password", help="Support account password")
        parser.add_argument("--full-name", dest="full_name", default="", help="Full name to store for the support account")
        parser.add_argument("--email", default="", help="Optional email address")
        parser.add_argument(
            "--role",
            choices=ACCOUNT_ROLES,
            default=DEFAULT_ACCOUNT_ROLE,
            help="Account role to assign",
        )

    def handle(self, *args, **options):
        username = str(options["username"]).strip()
        password = str(options["password"])
        full_name = str(options.get("full_name") or "").strip()
        email = str(options.get("email") or "").strip() or None
        role = str(options.get("role") or DEFAULT_ACCOUNT_ROLE).strip()
        account_scope = derive_account_scope_from_role(role)

        if not username:
            raise CommandError("Username is required.")
        if not password:
            raise CommandError("Password is required.")
        if account_scope == "requester" and not email:
            raise CommandError("Email is required for support requester accounts.")

        password_hash = make_password(password)
        updated_at = datetime.now(timezone.utc).isoformat()

        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, username, metadata
                    FROM support_accounts
                    WHERE LOWER(username) = %s
                    LIMIT 1
                    """,
                    [username.lower()],
                )
                existing_row = cursor.fetchone()

                if existing_row:
                    agent_id, stored_username, raw_metadata = existing_row
                    metadata = normalize_json_object(raw_metadata)
                    metadata.update(
                        {
                            "password_hash": password_hash,
                            "password_updated_at": updated_at,
                        }
                    )
                    if account_scope != "staff":
                        metadata["session_active"] = False
                        metadata["console_status"] = "Off"
                    cursor.execute(
                        """
                        UPDATE support_accounts
                        SET username = %s,
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
                            username,
                            full_name or stored_username or username,
                            email,
                            account_scope,
                            role,
                            json.dumps(metadata),
                            agent_id,
                        ],
                    )
                    self.stdout.write(self.style.SUCCESS(f"Updated {role} account {username}."))
                    return

                metadata = {
                    "password_hash": password_hash,
                    "password_updated_at": updated_at,
                }
                if account_scope != "staff":
                    metadata["session_active"] = False
                    metadata["console_status"] = "Off"
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
                    """,
                    [
                        username,
                        full_name or username,
                        email,
                        account_scope,
                        role,
                        json.dumps(metadata),
                    ],
                )

        self.stdout.write(self.style.SUCCESS(f"Created {role} account {username}."))

