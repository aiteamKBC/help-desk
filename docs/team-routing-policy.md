# Team Routing & Ticket Ownership Policy

This document describes the current ticket routing, ownership, assignment, and transfer rules for the support portal.

## Core Model

The system uses a Team Routing Policy model.

Each ticket belongs to a team queue. Each team queue defines which staff access flag is required to receive tickets from that queue.

Current team policies:

| Team | Queue key | Receiver access |
| --- | --- | --- |
| Support Desk | support | Support Access |
| Learning Plan Team | operations | Operations Access |

Coverage tickets are always treated as Learning Plan / Operations tickets, even if older records have a different assigned team.

## Access Types

| Access | Meaning |
| --- | --- |
| Support Access | Can receive and work Support Desk tickets. |
| Operations Access | Can receive and work Learning Plan / Coverage tickets. |
| Admin Access | Can manage dashboards and controls, but does not automatically make the account a ticket receiver. |
| Super Admin | Full authority across the system. |

A staff account can have more than one access type. For example, a person with both Support Access and Operations Access can receive tickets from both queues.

## Assignment Rules

Assignment means selecting the person who owns the ticket.

Current rules:

- Support Desk tickets can only be assigned to staff with Support Access.
- Learning Plan / Coverage tickets can only be assigned to staff with Operations Access.
- Admin and Super Admin can assign or unassign tickets, but only to eligible receivers for the ticket's team.
- Admin Access alone does not make a person assignable as a receiver.
- First-edit auto-assignment can happen only when the editor is Admin/Super Admin and is eligible for the ticket's current team.
- Learning Plan assignment is not availability-routed.

## Availability Rules

Availability matters for Support Desk receiving because support work includes live-chat and real-time queue behavior.

Current rules:

- Support assignment/receiving can use availability and console status.
- Learning Plan / Operations work is treated as an async/manual queue.
- Operations availability is not currently used for automatic Learning Plan assignment.

## Internal Agent Transfer

Internal transfer means moving ticket ownership from one staff member to another inside the same ticket queue.

Current rules:

- The currently assigned staff member can request an internal transfer.
- The target staff member must be eligible for the ticket's team.
- The target must accept or reject the request.
- The ticket ownership changes only after the target accepts.
- If the target rejects, ownership stays with the original assigned staff member.

## Team Transfer

Team transfer means moving the ticket from one team queue to another, for example:

- Support Desk -> Learning Plan Team
- Learning Plan Team -> Support Desk

Current rules:

- Admin and Super Admin can transfer tickets between teams.
- Eligible Support staff can transfer Support Desk tickets to another team.
- Eligible Operations staff can return Learning Plan tickets to another team.
- Team transfer requires a handoff note.
- Team transfer clears the current assigned staff member by default.
- Team transfer clears any pending internal agent transfer request.
- Team transfer creates an activity log entry.
- Agent/Operator team transfer cannot assign a receiver in the destination team.
- The receiving team assigns an eligible receiver after the move.
- Archived tickets must be restored before team transfer.

## Handoff Notes

A handoff note is required for team transfer because team transfer changes workflow ownership, not just personal ownership.

The handoff note should explain:

- Why the ticket is moving.
- What the receiving team needs to review.
- Any context that prevents the ticket from being bounced back incorrectly.

## Admin Structure Direction

Recommended long-term structure:

```text
Agent / Operator -> Team Admin -> Super Admin
```

Current implementation:

- Admin and Super Admin have broad management control.
- Receiver eligibility is team-policy based.
- Scoped Team Admin authority is not fully separated yet.

Future direction:

- Support Admin controls Support Desk queue operations.
- Operations Admin controls Learning Plan queue operations.
- Super Admin controls all teams and global settings.

## Adding Future Teams

The goal of the routing policy refactor is to make new teams easier to add.

Example future team:

| Team | Queue key | Receiver access |
| --- | --- | --- |
| Curriculum Team | curriculum | Curriculum Access |

Expected implementation shape:

```text
Team -> queue key -> required receiver access -> assignment/transfer rules
```

When adding a new team, update:

- Backend team routing policy.
- Frontend team routing policy.
- Access flag or account permission model.
- Dashboard or queue view, if the team needs a dedicated screen.
- Notification/webhook behavior, if required.
- Tests for assignment, transfer, visibility, and receiver eligibility.

## Current Source Of Truth

Backend:

- `backend/support_portal/services.py`
- `TEAM_ROUTING_POLICIES`
- `get_ticket_routing_policy`
- `account_can_receive_ticket_assignment`
- `actor_can_transfer_ticket_between_teams`

Frontend:

- `frontend/src/pages/support/AgentDashboard.tsx`
- `teamRoutingPolicies`
- `getTicketRoutingPolicy`
- `canReceiveTicketAssignment`
- `canTransferTicketToTeam`

## Important Distinctions

| Concept | Meaning |
| --- | --- |
| Visibility | Whether a user can see a ticket. |
| Assignment | Who owns the ticket. |
| Receiver eligibility | Whether a user can be assigned to receive that team's tickets. |
| Internal transfer | Ownership handoff between staff members. |
| Team transfer | Queue/workflow handoff between teams. |
| Escalation | Notification/review path, not ownership by default. |

Admin access can allow visibility/control without receiver eligibility.
