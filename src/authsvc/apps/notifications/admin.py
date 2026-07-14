from django.contrib import admin

from .models import OutboundEmail, WebhookEvent


@admin.register(OutboundEmail)
class OutboundEmailAdmin(admin.ModelAdmin):
    list_display = ("email_type", "recipient", "status", "provider", "created_at")
    list_filter = ("status", "email_type", "provider")
    search_fields = ("recipient", "provider_message_id", "idempotency_key")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "provider_message_id", "processed", "received_at")
    list_filter = ("event_type", "processed")
    search_fields = ("svix_id", "provider_message_id")
    readonly_fields = ("received_at", "processed_at")
