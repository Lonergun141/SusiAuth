from django.http import JsonResponse
from ninja import Router

from authsvc.apps.notifications.webhooks import WebhookError, process_event, verify_and_parse

router = Router(tags=["webhooks"])

# Reject absurdly large webhook bodies before doing any work.
_MAX_BODY_BYTES = 1_000_000


@router.post("/resend")
def resend_webhook(request):
    """Receive Resend delivery events. Verifies the Svix signature over the raw
    body before trusting any JSON; idempotent on the svix-id header."""
    raw = request.body
    if len(raw) > _MAX_BODY_BYTES:
        return JsonResponse({"error": "payload too large"}, status=413)

    headers = {k.lower(): v for k, v in request.headers.items()}
    try:
        event = verify_and_parse(raw, headers)
    except WebhookError:
        return JsonResponse({"error": "invalid signature"}, status=400)

    process_event(headers.get("svix-id", ""), event)
    return {"status": "ok"}
