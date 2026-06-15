# Support Notification Email Templates

These templates are designed for the n8n `Support Notifications` workflow Gmail nodes.
Set each Gmail node `Message` field to HTML/expression mode and paste the matching template.

## Quick Ticket Submitted

Use:

- `Send To`: `={{ $json.requester.email }}`
- `Subject`: `=Support ticket {{ $json.ticket.id }} submitted`
- `Message`:

```html
=<div style="margin:0;padding:0;background:#f4f6fb;font-family:Georgia,'Times New Roman',serif;color:#111827;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f4f6fb;margin:0;padding:28px 0;">
    <tr>
      <td align="center" style="padding:0 16px;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:640px;background:#ffffff;border:1px solid #dedede;border-radius:8px;overflow:hidden;">
          <tr>
            <td style="background:#17172b;color:#ffffff;padding:24px 28px;">
              <div style="font-size:13px;letter-spacing:1.3px;text-transform:uppercase;font-weight:700;color:#dbe7ff;">Kent Business College</div>
              <div style="font-size:22px;font-weight:700;margin-top:8px;">Support Ticket Submitted</div>
            </td>
          </tr>
          <tr>
            <td style="padding:26px 28px 30px;">
              <p style="margin:0 0 14px;font-size:16px;line-height:1.6;">Dear <strong>{{ $json.requester.name || "there" }}</strong>,</p>
              <p style="margin:0 0 22px;font-size:15px;line-height:1.7;">Your support ticket has been submitted successfully. Our support team will review the details and follow up as soon as possible.</p>

              <div style="font-size:12px;letter-spacing:1px;text-transform:uppercase;font-weight:700;color:#777;margin:0 0 8px;">Ticket Info</div>
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f8f9fc;border-left:4px solid #17172b;border-radius:4px;margin:0 0 22px;">
                <tr>
                  <td style="padding:16px 18px;">
                    <div style="font-size:15px;line-height:1.7;"><strong>Ticket ID</strong><br>{{ $json.ticket.id }}</div>
                    <div style="font-size:15px;line-height:1.7;margin-top:10px;"><strong>Category</strong><br>{{ $json.ticket.category }}{{ $json.ticket.technicalSubcategory ? " - " + $json.ticket.technicalSubcategory : "" }}</div>
                    <div style="font-size:15px;line-height:1.7;margin-top:10px;"><strong>Status</strong><br>{{ $json.ticket.statusReason || $json.ticket.status || "Quick Ticket" }}</div>
                    <div style="font-size:15px;line-height:1.7;margin-top:10px;"><strong>Priority</strong><br>{{ $json.ticket.priority || "Normal" }}</div>
                  </td>
                </tr>
              </table>

              <p style="margin:0 0 22px;font-size:15px;line-height:1.7;">You do not need to reply to this email unless you want to add more information to your request.</p>
              <p style="margin:0;font-size:15px;line-height:1.6;">Kind regards,<br><strong>Kent Business College Support</strong></p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</div>
```

## Quick Ticket Closed

Use:

- `Send To`: `={{ $json.requester.email }}`
- `Subject`: `=Support ticket {{ $json.ticket.id }} closed`
- `Message`:

```html
=
<div style="margin:0;padding:0;background:#f4f6fb;font-family:Georgia,'Times New Roman',serif;color:#111827;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f4f6fb;margin:0;padding:28px 0;">
    <tr>
      <td align="center" style="padding:0 16px;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:640px;background:#ffffff;border:1px solid #dedede;border-radius:8px;overflow:hidden;">
          <tr>
            <td style="background:#17172b;color:#ffffff;padding:24px 28px;">
              <div style="font-size:13px;letter-spacing:1.3px;text-transform:uppercase;font-weight:700;color:#dbe7ff;">Kent Business College</div>
              <div style="font-size:22px;font-weight:700;margin-top:8px;">Support Ticket Closed</div>
            </td>
          </tr>
          <tr>
            <td style="padding:26px 28px 30px;">
              <p style="margin:0 0 14px;font-size:16px;line-height:1.6;">Dear <strong>{{ $json.requester.name || "there" }}</strong>,</p>
              <p style="margin:0 0 22px;font-size:15px;line-height:1.7;">Your support ticket has now been closed. If you still need help, please submit a new support request through the support portal.</p>

              <div style="font-size:12px;letter-spacing:1px;text-transform:uppercase;font-weight:700;color:#777;margin:0 0 8px;">Closure Info</div>
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f8f9fc;border-left:4px solid #2f855a;border-radius:4px;margin:0 0 22px;">
                <tr>
                  <td style="padding:16px 18px;">
                    <div style="font-size:15px;line-height:1.7;"><strong>Ticket ID</strong><br>{{ $json.ticket.id }}</div>
                    <div style="font-size:15px;line-height:1.7;margin-top:10px;"><strong>Category</strong><br>{{ $json.ticket.category }}{{ $json.ticket.technicalSubcategory ? " - " + $json.ticket.technicalSubcategory : "" }}</div>
                    <div style="font-size:15px;line-height:1.7;margin-top:10px;"><strong>Status</strong><br>Closed</div>
                    <div style="font-size:15px;line-height:1.7;margin-top:10px;"><strong>Closed At</strong><br>{{ $json.closure.closedAt || "Confirmed by support" }}</div>
                  </td>
                </tr>
              </table>

              <p style="margin:0;font-size:15px;line-height:1.6;">Kind regards,<br><strong>Kent Business College Support</strong></p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</div>
```

## Live Agent Unavailable

Use:

- `Send To`: the operations/support mailbox, for example `support.agent@your-domain.com`
- `Subject`: `=Live chat waiting: {{ $json.ticket.id }} has no available agent`
- `Message`:

```html
=<div style="margin:0;padding:0;background:#f4f6fb;font-family:Georgia,'Times New Roman',serif;color:#111827;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f4f6fb;margin:0;padding:28px 0;">
    <tr>
      <td align="center" style="padding:0 16px;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:640px;background:#ffffff;border:1px solid #dedede;border-radius:8px;overflow:hidden;">
          <tr>
            <td style="background:#17172b;color:#ffffff;padding:24px 28px;">
              <div style="font-size:13px;letter-spacing:1.3px;text-transform:uppercase;font-weight:700;color:#dbe7ff;">Kent Business College</div>
              <div style="font-size:22px;font-weight:700;margin-top:8px;">Live Agent Required</div>
            </td>
          </tr>
          <tr>
            <td style="padding:26px 28px 30px;">
              <p style="margin:0 0 14px;font-size:16px;line-height:1.6;">Dear Operations Team,</p>
              <p style="margin:0 0 22px;font-size:15px;line-height:1.7;">A requester selected Live Agent, but no available support agent could be assigned automatically. Please review and assign a team member as soon as possible.</p>

              <div style="font-size:12px;letter-spacing:1px;text-transform:uppercase;font-weight:700;color:#777;margin:0 0 8px;">Request Info</div>
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f8f9fc;border-left:4px solid #b7791f;border-radius:4px;margin:0 0 22px;">
                <tr>
                  <td style="padding:16px 18px;">
                    <div style="font-size:15px;line-height:1.7;"><strong>Ticket ID</strong><br>{{ $json.ticket.id }}</div>
                    <div style="font-size:15px;line-height:1.7;margin-top:10px;"><strong>Requester</strong><br>{{ $json.requester.name }} - {{ $json.requester.email }}</div>
                    <div style="font-size:15px;line-height:1.7;margin-top:10px;"><strong>Category</strong><br>{{ $json.ticket.category }}{{ $json.ticket.technicalSubcategory ? " - " + $json.ticket.technicalSubcategory : "" }}</div>
                    <div style="font-size:15px;line-height:1.7;margin-top:10px;"><strong>Priority</strong><br>{{ $json.ticket.priority || "Normal" }}</div>
                    <div style="font-size:15px;line-height:1.7;margin-top:10px;"><strong>Requested At</strong><br>{{ $json.liveChat.requestedAt || "Just now" }}</div>
                  </td>
                </tr>
              </table>

              <p style="margin:0 0 24px;font-size:15px;line-height:1.7;">Open the admin dashboard and assign the ticket to an available support agent.</p>
              <a href="{{ $json.ticket.dashboardUrl }}" style="display:inline-block;background:#17172b;color:#ffffff;text-decoration:none;font-weight:700;border-radius:6px;padding:12px 18px;">Open Admin Dashboard</a>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</div>
```
