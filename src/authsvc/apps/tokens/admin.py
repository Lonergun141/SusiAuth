from django.contrib import admin

from .models import OneTimeToken, RefreshToken

admin.site.register(RefreshToken)
admin.site.register(OneTimeToken)
