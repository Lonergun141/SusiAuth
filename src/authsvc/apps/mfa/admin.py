from django.contrib import admin

from .models import RecoveryCode, TOTPDevice


@admin.register(TOTPDevice)
class TOTPDeviceAdmin(admin.ModelAdmin):
    list_display = ("user", "confirmed", "created_at", "last_used_at")
    list_filter = ("confirmed",)
    search_fields = ("user__email",)
    readonly_fields = ("secret_encrypted", "created_at", "confirmed_at", "last_used_at")


@admin.register(RecoveryCode)
class RecoveryCodeAdmin(admin.ModelAdmin):
    list_display = ("user", "used_at", "created_at")
    list_filter = ("used_at",)
    search_fields = ("user__email",)
    readonly_fields = ("code_hash", "created_at", "used_at")
