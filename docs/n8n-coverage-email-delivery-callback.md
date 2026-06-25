# n8n Coverage Tutor Email Delivery Callback

The help-desk backend now separates two states:

- `requestStatus=requested`: the coverage tutor request was saved in the system.
- `emailDeliveryStatus=pending|sent|failed`: the tutor email delivery result.

The backend sets `emailDeliveryStatus` to `pending` when an agent submits a coverage tutor request. n8n must call the backend callback after the Gmail node succeeds or fails.

## 1. Keep the Callback Payload in Prepare Email Data1

In the `Prepare Email Data1` code node, make sure the output JSON includes the callback object received from the backend:

```js
emailDeliveryCallback: body.emailDeliveryCallback || {},
```

For example, the output object should include this field next to `ticketId`, `cardId`, `responseToken`, `emailSubject`, and `emailHtml`:

```js
const result = {
  json: {
    tutorEmail,
    tutorName,
    ticketId,
    cardId,
    responseToken,
    ccList,
    emailSubject,
    emailHtml,
    hasAttachments,
    emailDeliveryCallback: body.emailDeliveryCallback || {},
  },
};
```

## 2. Add a Success Callback After Gmail

After each successful Gmail send node, add an HTTP Request node.

Recommended node name:

```text
Report Email Sent
```

HTTP Request settings:

```text
Method: POST
URL: ={{ $('Prepare Email Data1').item.json.emailDeliveryCallback.url }}
Send Body: JSON
```

JSON body:

```json
{
  "ticketId": "={{ $('Prepare Email Data1').item.json.ticketId }}",
  "cardId": "={{ $('Prepare Email Data1').item.json.cardId }}",
  "status": "sent",
  "messageId": "={{ $json.id || $json.messageId || '' }}",
  "threadId": "={{ $json.threadId || '' }}",
  "token": "={{ $('Prepare Email Data1').item.json.emailDeliveryCallback.token }}"
}
```

Connect this after both Gmail branches:

- `Send Email to Tutor (Att)1`
- `Send Email to Tutor (No Att)1`

## 3. Add a Failure Callback

If a Gmail node fails, n8n should report the failure back to the backend.

Recommended node name:

```text
Report Email Failed
```

HTTP Request settings:

```text
Method: POST
URL: ={{ $('Prepare Email Data1').item.json.emailDeliveryCallback.url }}
Send Body: JSON
```

JSON body:

```json
{
  "ticketId": "={{ $('Prepare Email Data1').item.json.ticketId }}",
  "cardId": "={{ $('Prepare Email Data1').item.json.cardId }}",
  "status": "failed",
  "error": "={{ $json.message || $json.error?.message || 'Gmail delivery failed' }}",
  "token": "={{ $('Prepare Email Data1').item.json.emailDeliveryCallback.token }}"
}
```

There are two safe ways to trigger this:

- Enable `Continue On Fail` on the Gmail nodes, then branch to `Report Email Failed` when the Gmail result contains an error.
- Use an n8n error workflow that receives the failed execution context and calls the same callback.

## 4. Expected Backend Result

After the callback:

- The coverage card badge changes from `Email pending` to `Email sent` or `Email failed`.
- The ticket Activity Log records one of:
  - `coverage_tutor_request_email_sent`
  - `coverage_tutor_request_email_failed`
  - `coverage_tutor_request_email_pending`

## 5. Important Notes

- Do not mark the card as fully emailed from n8n unless the Gmail send node actually succeeds.
- Large files are intentionally sent as secure download links instead of binary attachments.
- The callback token is signed by the backend. n8n should pass it through unchanged.
