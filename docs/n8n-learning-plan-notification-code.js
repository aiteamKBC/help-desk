const inputJson = $input.first().json || {};
const body = inputJson.body ?? inputJson;

const event = body.event || "";
const ticket = body.ticket || {};
const coverage = body.coverage || {};
const requester = body.requester || {};
const transfer = body.transfer || {};

const ticketId = ticket.id || "N/A";
const status = ticket.status || "N/A";
const statusReason = ticket.statusReason || "N/A";
const priority = ticket.priority || "N/A";
const slaStatus = ticket.slaStatus || "N/A";
const assignedTeam = ticket.assignedTeam || "N/A";
const dashboardUrl = ticket.dashboardUrl || "#";

function formatUtcDateTime(value) {
  if (!value) return "N/A";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "N/A";
  return date.toLocaleString("en-GB", { timeZone: "UTC" });
}

const createdAt = formatUtcDateTime(ticket.createdAt);
const requesterName = requester.name || "N/A";
const requesterEmail = requester.email || "N/A";
const requesterRole = requester.role || "N/A";

function escapeHtml(value) {
  return String(value ?? "N/A")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function infoRow(label, value) {
  return `
    <tr>
      <td style="width:180px;padding:6px 12px 6px 0;font-family:Arial,Helvetica,sans-serif;font-size:13px;line-height:18px;font-weight:bold;color:#1f2937;vertical-align:top;">
        ${escapeHtml(label)}
      </td>
      <td style="padding:6px 0;font-family:Arial,Helvetica,sans-serif;font-size:13px;line-height:18px;color:#4b5563;vertical-align:top;word-break:break-word;">
        ${escapeHtml(value)}
      </td>
    </tr>
  `;
}

function sectionTitle(title) {
  return `
    <tr>
      <td style="padding:24px 0 10px 0;">
        <div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:16px;font-weight:bold;color:#6b7280;text-transform:uppercase;letter-spacing:0.7px;">
          ${escapeHtml(title)}
        </div>
      </td>
    </tr>
  `;
}

function infoBox(rowsHtml, accentColor = "#1e3a8a") {
  return `
    <tr>
      <td style="background:#f8fafc;border-left:4px solid ${accentColor};border-radius:0 6px 6px 0;padding:14px 18px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
          ${rowsHtml}
        </table>
      </td>
    </tr>
  `;
}

function wrapEmail({ title, intro, sectionsHtml, buttonLabel = "Open Dashboard" }) {
  return `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${escapeHtml(title)}</title>
</head>
<body style="margin:0;padding:0;background:#eef2f7;font-family:Arial,Helvetica,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#eef2f7;">
    <tr>
      <td align="center" style="padding:24px 12px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:640px;background:#ffffff;border:1px solid #dbe3ee;border-radius:10px;overflow:hidden;">
          <tr>
            <td style="background:#0f172a;padding:28px 32px;">
              <div style="font-family:Arial,Helvetica,sans-serif;color:#93c5fd;font-size:12px;line-height:16px;font-weight:bold;letter-spacing:1px;">
                KENT BUSINESS COLLEGE
              </div>
              <div style="font-family:Arial,Helvetica,sans-serif;color:#ffffff;font-size:22px;line-height:28px;font-weight:bold;margin-top:8px;">
                ${escapeHtml(title)}
              </div>
            </td>
          </tr>
          <tr>
            <td style="padding:30px 32px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td style="font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:22px;color:#475569;padding:0 0 6px 0;">
                    ${escapeHtml(intro)}
                  </td>
                </tr>
                ${sectionsHtml}
                <tr>
                  <td style="padding-top:22px;">
                    <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                      <tr>
                        <td bgcolor="#0f172a" style="border-radius:6px;">
                          <a href="${escapeHtml(dashboardUrl)}" style="display:inline-block;padding:14px 30px;font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:18px;font-weight:bold;color:#ffffff;text-decoration:none;border-radius:6px;">
                            ${escapeHtml(buttonLabel)}
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
}

function buildCoverageEmail() {
  const tutorName = coverage.tutor || "N/A";
  const moduleName = coverage.module || "N/A";
  const preferredTime = coverage.preferredTime || "N/A";
  const sessions = Array.isArray(coverage.sessions) ? coverage.sessions : [];

  const sessionCards = sessions.map((session) => {
    return `
      <tr>
        <td style="background:#f8fafc;border-left:4px solid #2563eb;border-radius:0 6px 6px 0;padding:14px 18px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
            ${infoRow("Date", session.date || "N/A")}
            ${infoRow("Session No.", session.sessionNumber || session.index || "N/A")}
            ${infoRow("Subject", session.subject || "N/A")}
          </table>
        </td>
      </tr>
      <tr>
        <td style="height:12px;line-height:12px;font-size:12px;">&nbsp;</td>
      </tr>
    `;
  }).join("");

  const sectionsHtml =
    sectionTitle("Ticket Overview") +
    infoBox(
      infoRow("Ticket ID", ticketId) +
      infoRow("Status", status) +
      infoRow("Priority", priority) +
      infoRow("SLA Status", slaStatus) +
      infoRow("Created At", createdAt) +
      infoRow("Requester", `${requesterName} (${requesterEmail})`)
    ) +
    sectionTitle("Coverage Details") +
    infoBox(
      infoRow("Tutor", tutorName) +
      infoRow("Module", moduleName) +
      infoRow("Preferred Time", preferredTime)
    ) +
    sectionTitle("Sessions") +
    (sessionCards || infoBox(infoRow("Details", "No session details were provided."), "#2563eb"));

  return {
    emailSubject: `New Coverage Ticket - ${ticketId}`,
    emailHtml: wrapEmail({
      title: "New Coverage Ticket Opened",
      intro: "A new coverage ticket has been created and requires review from the Learning Plan Team.",
      sectionsHtml,
      buttonLabel: "View Ticket",
    }),
  };
}

function buildLearningPlanTransferEmail() {
  const transferredAt = formatUtcDateTime(transfer.transferredAt);
  const fromTeam = transfer.fromTeam || "N/A";
  const toTeam = transfer.toTeam || "N/A";
  const transferNote = transfer.note || "No internal note was provided.";
  const transferredBy = transfer.transferredBy || {};
  const assignedAgent = transfer.assignedAgent || {};

  const transferredByName = transferredBy.name || transferredBy.username || "N/A";
  const assignedAgentName = assignedAgent.name || assignedAgent.username || "Unassigned";

  const sectionsHtml =
    sectionTitle("Ticket Overview") +
    infoBox(
      infoRow("Ticket ID", ticketId) +
      infoRow("Status", status) +
      infoRow("Status Reason", statusReason) +
      infoRow("Priority", priority) +
      infoRow("SLA Status", slaStatus) +
      infoRow("Assigned Team", assignedTeam) +
      infoRow("Created At", createdAt)
    ) +
    sectionTitle("Requester") +
    infoBox(
      infoRow("Name", requesterName) +
      infoRow("Email", requesterEmail) +
      infoRow("Role", requesterRole),
      "#0f766e"
    ) +
    sectionTitle("Transfer Details") +
    infoBox(
      infoRow("From Team", fromTeam) +
      infoRow("To Team", toTeam) +
      infoRow("Transferred By", transferredByName) +
      infoRow("Assigned Agent", assignedAgentName) +
      infoRow("Transferred At", transferredAt) +
      infoRow("Internal Note", transferNote),
      "#0f766e"
    );

  return {
    emailSubject: `Learning Plan Ticket Transfer - ${ticketId}`,
    emailHtml: wrapEmail({
      title: "Learning Plan Ticket Transferred",
      intro: "A support ticket has been transferred to the Learning Plan Team queue and is ready for review.",
      sectionsHtml,
      buttonLabel: "Open Dashboard",
    }),
  };
}

function buildFallbackEmail() {
  const sectionsHtml =
    sectionTitle("Event Details") +
    infoBox(
      infoRow("Event", event || "N/A") +
      infoRow("Ticket ID", ticketId) +
      infoRow("Status", status) +
      infoRow("Assigned Team", assignedTeam)
    );

  return {
    emailSubject: `Support Portal Notification - ${ticketId}`,
    emailHtml: wrapEmail({
      title: "Support Portal Notification",
      intro: "A new support portal event was received.",
      sectionsHtml,
      buttonLabel: "Open Dashboard",
    }),
  };
}

let notification;

if (event === "coverage_ticket_created") {
  notification = buildCoverageEmail();
} else if (event === "learning_plan_ticket_transferred") {
  notification = buildLearningPlanTransferEmail();
} else {
  notification = buildFallbackEmail();
}

return [
  {
    json: {
      emailHtml: notification.emailHtml,
      emailSubject: notification.emailSubject,
      ticketId,
      event,
    },
  },
];
