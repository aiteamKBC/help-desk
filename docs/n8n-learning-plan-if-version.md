# n8n IF Workflow Review And Recommended Fix

This file documents:

1. The main problems in the current `open/ticket` webhook workflow.
2. A cleaner `IF`-based structure for `coverage_ticket_created` and `learning_plan_ticket_transferred`.
3. The exact expressions and code snippets to use in n8n.

## Problems In The Current Workflow

### 1) No webhook protection

Your current `Webhook` node accepts any `POST` request on `open/ticket` and there is no secret check.
That means anyone who discovers the URL can trigger your Gmail node.

Recommended fix:

- Best option: enable webhook authentication in n8n.
- Simple option: add a secret header check before any email logic.

Example header:

```text
x-support-webhook-secret: REPLACE_WITH_YOUR_SECRET
```

## 2) Unknown events still send email

Right now, any unrecognized event falls into a fallback email.
That can create noise and also hide payload mistakes.

Recommended fix:

- Only send email for known events.
- Ignore unknown events, or log them separately.

## 3) `coverage.sessions` is not validated

The current code does:

```javascript
const sessions = coverage.sessions || [];
```

If `coverage.sessions` is not an array, `.map()` can fail.

Recommended fix:

```javascript
const sessions = Array.isArray(coverage.sessions) ? coverage.sessions : [];
```

## Recommended Flow

Use this structure:

```text
Webhook
  -> IF Secret Valid
      true  -> IF Coverage Event
                  true  -> Prepare Coverage Email -> Send Email
                  false -> IF Learning Plan Transfer Event
                              true  -> Prepare Learning Plan Transfer Email -> Send Email
                              false -> End
      false -> End
```

## Node 1: Webhook

Keep:

- Method: `POST`
- Path: `open/ticket`

If you can use native webhook auth in n8n, do that.
If not, add the secret check below.

## Node 2: IF Secret Valid

Node type: `IF`

Expression:

```javascript
{{
  ($json.headers?.['x-support-webhook-secret']
    ?? $json.headers?.['X-Support-Webhook-Secret']
    ?? '') === 'REPLACE_WITH_YOUR_SECRET'
}}
```

Behavior:

- `true`: continue
- `false`: stop the flow and do not send email

## Node 3: IF Coverage Event

Node type: `IF`

Expression:

```javascript
{{ ($json.body?.event ?? $json.event ?? '') === 'coverage_ticket_created' }}
```

Behavior:

- `true`: go to `Prepare Coverage Email`
- `false`: go to `IF Learning Plan Transfer Event`

## Node 4: Prepare Coverage Email

Node type: `Code`

```javascript
const inputJson = $input.first().json || {};
const body = inputJson.body ?? inputJson;

const ticket = body.ticket || {};
const coverage = body.coverage || {};
const requester = body.requester || {};

const ticketId = ticket.id || 'N/A';
const status = ticket.status || 'N/A';
const priority = ticket.priority || 'N/A';
const slaStatus = ticket.slaStatus || 'N/A';
const createdAt = ticket.createdAt
  ? new Date(ticket.createdAt).toLocaleString('en-GB', { timeZone: 'UTC' })
  : 'N/A';
const dashboardUrl = ticket.dashboardUrl || '#';

const tutorName = coverage.tutor || 'N/A';
const moduleName = coverage.module || 'N/A';
const preferredTime = coverage.preferredTime || 'N/A';
const sessions = Array.isArray(coverage.sessions) ? coverage.sessions : [];

const requesterName = requester.name || 'N/A';
const requesterEmail = requester.email || 'N/A';

function escapeHtml(value) {
  return String(value ?? 'N/A')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function infoRow(label, value) {
  return `
    <tr>
      <td style="width:170px;padding:4px 10px 4px 0;font-family:Arial,Helvetica,sans-serif;font-size:13px;line-height:18px;font-weight:bold;color:#222;vertical-align:top;">
        ${escapeHtml(label)}
      </td>
      <td style="padding:4px 0;font-family:Arial,Helvetica,sans-serif;font-size:13px;line-height:18px;color:#444;vertical-align:top;word-break:break-word;">
        ${escapeHtml(value)}
      </td>
    </tr>
  `;
}

function sectionTitle(title) {
  return `
    <tr>
      <td style="padding:22px 0 10px 0;">
        <div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:16px;font-weight:bold;color:#777;text-transform:uppercase;letter-spacing:0.5px;">
          ${escapeHtml(title)}
        </div>
      </td>
    </tr>
  `;
}

function infoBox(rowsHtml, accentColor = '#1a1a2e') {
  return `
    <tr>
      <td style="background:#f8f9fb;border-left:4px solid ${accentColor};border-radius:0 4px 4px 0;padding:14px 18px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
          ${rowsHtml}
        </table>
      </td>
    </tr>
  `;
}

const sessionCards = sessions.map((s) => `
  <tr>
    <td style="background:#f8f9fb;border-left:4px solid #4a6fa5;border-radius:0 4px 4px 0;padding:14px 18px;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
        ${infoRow('Date', s.date || 'N/A')}
        ${infoRow('Session No.', s.sessionNumber || s.index || 'N/A')}
        ${infoRow('Subject', s.subject || 'N/A')}
      </table>
    </td>
  </tr>
  <tr>
    <td style="height:12px;line-height:12px;font-size:12px;">&nbsp;</td>
  </tr>
`).join('');

const emailHtml = `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>New Coverage Ticket</title>
</head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,Helvetica,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f4f4f4;">
    <tr>
      <td align="center" style="padding:24px 12px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:620px;background:#ffffff;border:1px solid #e0e0e0;border-radius:8px;overflow:hidden;">
          <tr>
            <td style="background:#1a1a2e;padding:26px 30px;">
              <div style="font-family:Arial,Helvetica,sans-serif;color:#aac4f0;font-size:13px;line-height:18px;font-weight:bold;letter-spacing:1px;">
                KENT BUSINESS COLLEGE
              </div>
              <div style="font-family:Arial,Helvetica,sans-serif;color:#ffffff;font-size:20px;line-height:26px;font-weight:bold;margin-top:8px;">
                New Coverage Ticket Opened
              </div>
            </td>
          </tr>
          <tr>
            <td style="padding:28px 30px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td style="font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:22px;color:#555;padding:0 0 4px 0;">
                    A new coverage ticket has been submitted and requires your attention.
                  </td>
                </tr>

                ${sectionTitle('Ticket Info')}
                ${infoBox(
                  infoRow('Ticket ID', ticketId) +
                  infoRow('Status', status) +
                  infoRow('Priority', priority) +
                  infoRow('SLA Status', slaStatus) +
                  infoRow('Created At', createdAt) +
                  infoRow('Requested By', `${requesterName} (${requesterEmail})`)
                )}

                ${sectionTitle('Coverage Details')}
                ${infoBox(
                  infoRow('Tutor', tutorName) +
                  infoRow('Module', moduleName) +
                  infoRow('Preferred Time', preferredTime)
                )}

                ${sectionTitle('Sessions')}
                ${sessionCards || infoBox(infoRow('Details', 'No session details were provided.'), '#4a6fa5')}

                <tr>
                  <td style="padding-top:20px;">
                    <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                      <tr>
                        <td bgcolor="#1a1a2e" style="border-radius:6px;">
                          <a href="${escapeHtml(dashboardUrl)}" style="display:inline-block;padding:14px 34px;font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:18px;font-weight:bold;color:#ffffff;text-decoration:none;border-radius:6px;">
                            View Dashboard
                          </a>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
`;

return [{
  json: {
    emailHtml,
    emailSubject: `New Coverage Ticket - ${ticketId}`,
    ticketId
  }
}];
```









## Node 5: IF Learning Plan Transfer Event

Node type: `IF`

Expression:

```javascript
{{ ($json.body?.event ?? $json.event ?? '') === 'learning_plan_ticket_transferred' }}
```

Behavior:

- `true`: go to `Prepare Learning Plan Transfer Email`
- `false`: end the workflow

## Node 6: Prepare Learning Plan Transfer Email

Node type: `Code`

```javascript
const inputJson = $input.first().json || {};
const body = inputJson.body ?? inputJson;

const ticket = body.ticket || {};
const requester = body.requester || {};
const transfer = body.transfer || {};

const ticketId = ticket.id || 'N/A';
const status = ticket.status || 'N/A';
const statusReason = ticket.statusReason || 'N/A';
const priority = ticket.priority || 'N/A';
const slaStatus = ticket.slaStatus || 'N/A';
const assignedTeam = ticket.assignedTeam || 'N/A';
const createdAt = ticket.createdAt
  ? new Date(ticket.createdAt).toLocaleString('en-GB', { timeZone: 'UTC' })
  : 'N/A';
const dashboardUrl = ticket.dashboardUrl || '#';

const requesterName = requester.name || 'N/A';
const requesterEmail = requester.email || 'N/A';
const requesterRole = requester.role || 'N/A';

const fromTeam = transfer.fromTeam || 'N/A';
const toTeam = transfer.toTeam || 'N/A';
const transferredAt = transfer.transferredAt
  ? new Date(transfer.transferredAt).toLocaleString('en-GB', { timeZone: 'UTC' })
  : 'N/A';
const transferNote = transfer.note || 'No internal note was provided.';

const transferredBy = transfer.transferredBy || {};
const assignedAgent = transfer.assignedAgent || {};

const transferredByName = transferredBy.name || transferredBy.username || 'N/A';
const assignedAgentName = assignedAgent.name || assignedAgent.username || 'Unassigned';

function escapeHtml(value) {
  return String(value ?? 'N/A')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function infoRow(label, value) {
  return `
    <tr>
      <td style="width:170px;padding:4px 10px 4px 0;font-family:Arial,Helvetica,sans-serif;font-size:13px;line-height:18px;font-weight:bold;color:#222;vertical-align:top;">
        ${escapeHtml(label)}
      </td>
      <td style="padding:4px 0;font-family:Arial,Helvetica,sans-serif;font-size:13px;line-height:18px;color:#444;vertical-align:top;word-break:break-word;">
        ${escapeHtml(value)}
      </td>
    </tr>
  `;
}

function sectionTitle(title) {
  return `
    <tr>
      <td style="padding:22px 0 10px 0;">
        <div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:16px;font-weight:bold;color:#777;text-transform:uppercase;letter-spacing:0.5px;">
          ${escapeHtml(title)}
        </div>
      </td>
    </tr>
  `;
}

function infoBox(rowsHtml, accentColor = '#0f766e') {
  return `
    <tr>
      <td style="background:#f8f9fb;border-left:4px solid ${accentColor};border-radius:0 4px 4px 0;padding:14px 18px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
          ${rowsHtml}
        </table>
      </td>
    </tr>
  `;
}

const emailHtml = `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Learning Plan Ticket Transfer</title>
</head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,Helvetica,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f4f4f4;">
    <tr>
      <td align="center" style="padding:24px 12px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:620px;background:#ffffff;border:1px solid #e0e0e0;border-radius:8px;overflow:hidden;">
          <tr>
            <td style="background:#1a1a2e;padding:26px 30px;">
              <div style="font-family:Arial,Helvetica,sans-serif;color:#99f6e4;font-size:13px;line-height:18px;font-weight:bold;letter-spacing:1px;">
                KENT BUSINESS COLLEGE
              </div>
              <div style="font-family:Arial,Helvetica,sans-serif;color:#ffffff;font-size:20px;line-height:26px;font-weight:bold;margin-top:8px;">
                Ticket Transferred To Learning Plan Team
              </div>
            </td>
          </tr>
          <tr>
            <td style="padding:28px 30px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td style="font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:22px;color:#555;padding:0 0 4px 0;">
                    A support ticket has been transferred to the Learning Plan Team queue and is ready for review.
                  </td>
                </tr>

                ${sectionTitle('Ticket Info')}
                ${infoBox(
                  infoRow('Ticket ID', ticketId) +
                  infoRow('Status', status) +
                  infoRow('Status Reason', statusReason) +
                  infoRow('Priority', priority) +
                  infoRow('SLA Status', slaStatus) +
                  infoRow('Assigned Team', assignedTeam) +
                  infoRow('Created At', createdAt)
                )}

                ${sectionTitle('Requester')}
                ${infoBox(
                  infoRow('Name', requesterName) +
                  infoRow('Email', requesterEmail) +
                  infoRow('Role', requesterRole)
                )}

                ${sectionTitle('Transfer Details')}
                ${infoBox(
                  infoRow('From Team', fromTeam) +
                  infoRow('To Team', toTeam) +
                  infoRow('Transferred By', transferredByName) +
                  infoRow('Assigned Agent', assignedAgentName) +
                  infoRow('Transferred At', transferredAt) +
                  infoRow('Internal Note', transferNote)
                )}

                <tr>
                  <td style="padding-top:20px;">
                    <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                      <tr>
                        <td bgcolor="#0f172a" style="border-radius:6px;">
                          <a href="${escapeHtml(dashboardUrl)}" style="display:inline-block;padding:14px 34px;font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:18px;font-weight:bold;color:#ffffff;text-decoration:none;border-radius:6px;">
                            View Dashboard
                          </a>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
`;

return [{
  json: {
    emailHtml,
    emailSubject: `Learning Plan Ticket Transfer - ${ticketId}`,
    ticketId
  }
}];
```

## Node 7: Gmail

Use the same Gmail node in both branches:

- `Send To`: `LearningPlan.Team@kentbusinesscollege.com`
- `Subject`: `={{ $json.emailSubject }}`
- `Message`: `={{ $json.emailHtml }}`
- `Append attribution`: `false`

## Important Recommendation

If you want the workflow to be more professional and safer:

1. Add webhook authentication or the secret header check.
2. Do not send fallback email for unknown events.
3. Validate `coverage.sessions` with `Array.isArray(...)`.
4. Keep `coverage` and `learning_plan_ticket_transferred` in separate branches.

## What To Change In Your Current Workflow

If you do not want to rebuild the whole workflow, at minimum change these parts:

1. Protect the webhook with auth or a secret header.
2. Replace:

```javascript
const sessions = coverage.sessions || [];
```

with:

```javascript
const sessions = Array.isArray(coverage.sessions) ? coverage.sessions : [];
```

3. Replace the fallback email behavior with "end the workflow".

