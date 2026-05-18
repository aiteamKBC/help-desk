# Production Readiness Requirements

## Purpose

This document defines the minimum requirements for operating the support portal in a robust and safe production environment.

Scope:

- security
- privacy
- operational resilience
- data durability
- authentication and authorization
- support-data handling

This file is a requirements checklist only.
It does not indicate that the listed controls are already implemented.

## Current Change Boundary

This document was added without changing application behavior.
No backend, frontend, infrastructure, or database logic was modified as part of this update.

## 1. Environment and Database Requirements

- [ ] Production must require `DATABASE_URL` to be present at startup.
- [ ] Production must not silently fall back to local SQLite for live support data.
- [ ] The production database must be a managed PostgreSQL environment with backups enabled.
- [ ] Point-in-time recovery or an equivalent restore strategy must be configured.
- [ ] Database credentials must come from environment variables or a secrets manager, never hardcoded files committed to the repo.
- [ ] Schema migration procedures must be documented and repeatable.
- [ ] A production readiness check must confirm the target database before migrations or deployments.
- [ ] Test databases must be isolated from production and staging databases.

Acceptance criteria:

- The app fails fast if production database configuration is missing or invalid.
- Live support records are never written to `db.sqlite3` in production.

## 2. Authentication and Session Requirements

- [ ] Admin authentication must be server-managed rather than relying on browser storage alone.
- [ ] Admin sessions must use `HttpOnly`, `Secure`, and `SameSite` cookies.
- [ ] Session identifiers must be rotated on login.
- [ ] Sessions must expire after inactivity and after an absolute maximum age.
- [ ] Logout must invalidate the server-side session.
- [ ] Concurrent-session handling must be defined and enforced.
- [ ] Admin passwords must remain hashed using approved password hashing.
- [ ] Rate limiting or lockout protections must exist for admin login.
- [ ] MFA must be evaluated and added for production admin access if required by policy.

Acceptance criteria:

- An attacker cannot obtain or reuse admin access solely from `localStorage` or `sessionStorage`.
- Admin sessions can be revoked immediately by the server.

## 3. Authorization and Access Control Requirements

- [ ] Every `/api/admin/*` endpoint must require an authenticated staff session.
- [ ] Authorization must be deny-by-default.
- [ ] Role checks must be enforced server-side for `admin`, `superadmin`, and any future `agent` role behavior.
- [ ] Object-level authorization must be enforced for ticket actions such as reply, transfer, escalation, and reassignment.
- [ ] Client-supplied actor identity fields must not be trusted without server-side session binding.
- [ ] Superadmin-only actions must be explicitly protected server-side.
- [ ] Access failures must be logged in an audit-safe manner.

Acceptance criteria:

- Omitting `actorUsername` or similar client fields must not bypass authorization checks.
- All admin data reads and writes require validated session context.

## 4. Browser Storage and Privacy Requirements

- [ ] Public support flow must not persist full PII and full chat history in `localStorage` for production use.
- [ ] Admin authentication data must not be stored in browser storage as the primary security control.
- [ ] Only minimal client-side resume state may be stored, and only when justified.
- [ ] Any stored client-side state must have a defined retention window.
- [ ] Stored client-side state must be cleared on logout, session expiry, and defined inactivity conditions.
- [ ] Privacy-sensitive data categories must be documented for browser persistence decisions.

Acceptance criteria:

- A shared or compromised browser cannot expose full support transcripts and admin session material from local storage alone.

## 5. Ticket, Chat, and Attachment Requirements

- [ ] Ticket numbers, chat identifiers, and conversation history must be treated as support records and retained server-side.
- [ ] Attachment handling must support real file persistence, not metadata-only placeholders, if uploads are presented to users as uploaded evidence.
- [ ] File storage must use approved managed storage with access controls.
- [ ] Attachment download access must be authenticated and authorized.
- [ ] File type, size, and content validation must be enforced server-side.
- [ ] Malware scanning or equivalent file-safety controls must be implemented for uploaded files.
- [ ] Signed URLs or controlled download endpoints must be used for attachment access.

Acceptance criteria:

- If the UI says a file was uploaded, authorized staff can retrieve the real file securely.
- Unsupported or dangerous files are blocked server-side even if the client is bypassed.

## 6. Audit and Traceability Requirements

- [ ] Ticket lifecycle events must continue to be recorded in the server-side audit history.
- [ ] Audit history must include actor, action, timestamp, and relevant ticket/chat identifiers.
- [ ] Security-sensitive actions must be auditable, including login, logout, reassignment, escalation, transfer, closure, and session cancellation.
- [ ] Audit records must be tamper-resistant through database permissions and operational controls.
- [ ] Audit retention requirements must be defined.

Acceptance criteria:

- Investigators can reconstruct who changed a ticket, when it happened, and what action occurred.

## 7. Secrets and Configuration Requirements

- [ ] Secrets must be stored outside version control.
- [ ] Production secrets must be delivered through a secret manager or secured deployment environment.
- [ ] Webhook URLs, API credentials, Azure credentials, and booking credentials must be rotated through documented procedures.
- [ ] Separate environments must use separate secrets.
- [ ] Debug settings must be disabled in production.

Acceptance criteria:

- Production deployment can be performed without editing committed files that contain secrets.

## 8. Logging, Monitoring, and Alerting Requirements

- [ ] Application errors must be centrally logged.
- [ ] Authentication failures and authorization failures must be monitored.
- [ ] Database connectivity failures must be monitored.
- [ ] Webhook failures for chatbot, AI, and booking flows must be monitored.
- [ ] Alerts must exist for repeated admin auth failures, database unavailability, and critical integration outages.
- [ ] Logs must avoid leaking sensitive payloads unnecessarily.

Acceptance criteria:

- Operations staff can detect authentication, database, or integration failures before they become prolonged outages.

## 9. Data Retention and Compliance Requirements

- [ ] A retention policy must define how long tickets, chats, attachments, and audit history are kept.
- [ ] A deletion and redaction process must exist for expired or regulated records.
- [ ] Data classification must identify PII and any higher-risk categories stored in tickets or chats.
- [ ] User-facing privacy notices must match actual data handling.
- [ ] Backup retention must align with policy and compliance needs.

Acceptance criteria:

- The team can explain where support data lives, how long it remains there, and how it is removed when required.

## 10. Testing and Verification Requirements

- [ ] Automated tests must cover authentication and authorization on all admin endpoints.
- [ ] Tests must cover coach restrictions, ticket assignment rules, transfer flows, escalation flows, and attachment rules.
- [ ] Security regression tests must be added for bypass attempts involving missing actor fields.
- [ ] Production build and backend checks must run in CI.
- [ ] Pre-release verification must include database connectivity, migration safety, webhook health, and session handling checks.

Acceptance criteria:

- Security-sensitive flows fail closed under automated test coverage.

## 11. Deployment and Recovery Requirements

- [ ] Production deployment must have a rollback plan.
- [ ] Backup restore procedures must be tested.
- [ ] A service recovery runbook must exist for database failure, secret rotation, and webhook outages.
- [ ] Deployment must separate dev, staging, and production configuration.
- [ ] Production must not depend on local developer machines or local files for persistent support data.

Acceptance criteria:

- The team can restore service and data within defined recovery objectives.

## 12. Recommended Implementation Priorities

Priority 1:

- [ ] Enforce authenticated session checks on all admin endpoints
- [ ] Remove production SQLite fallback
- [ ] Replace browser-stored admin session model with secure server-managed sessions

Priority 2:

- [ ] Remove full transcript and PII persistence from public `localStorage`
- [ ] Implement real attachment storage and protected retrieval
- [ ] Add authorization regression tests

Priority 3:

- [ ] Add centralized monitoring and alerting
- [ ] Formalize retention and deletion policies
- [ ] Add recovery drills and restore verification

## 13. Sign-Off Checklist

- [ ] Engineering sign-off
- [ ] Security sign-off
- [ ] Operations sign-off
- [ ] Product/data-handling sign-off
- [ ] Production go-live approval

