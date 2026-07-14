from django.apps import AppConfig


class MfaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "authsvc.apps.mfa"
    label = "mfa"
