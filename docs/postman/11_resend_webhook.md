# Resend Webhook

Receives email delivery events from Resend (delivered, bounced, complained,
failed, suppressed, ...). Called by Resend, not by clients.

**Method**: `POST`
**URL**: `{{base_url}}/api/webhooks/resend`

## Headers
- `Content-Type`: `application/json`
- `svix-id`: `<message id>` (sent by Resend)
- `svix-timestamp`: `<unix seconds>` (sent by Resend)
- `svix-signature`: `<v1,...>` (sent by Resend)

The signature is verified against the **raw request body** using
`RESEND_WEBHOOK_SECRET` before any JSON is trusted. Configure the endpoint URL
and copy the signing secret from the Resend dashboard → Webhooks.

## Body (example)
```json
{
  "type": "email.delivered",
  "data": { "email_id": "49a3999c-0ce1-4ea6-ab68-afcd6dc2e794" }
}
```

## Responses
- **200 OK** — `{"status": "ok"}` (valid signature; processed or a duplicate no-op)
- **400 Bad Request** — `{"error": "invalid signature"}` (bad/missing signature or unset secret)
- **413 Payload Too Large** — body exceeds 1 MB

## Notes
- Idempotent on `svix-id` — repeated deliveries do not re-apply.
- Out-of-order events never downgrade a later status (e.g. a late `email.sent`
  after `email.delivered` is ignored).
- Updates the matching `OutboundEmail` (by provider message id) status.
