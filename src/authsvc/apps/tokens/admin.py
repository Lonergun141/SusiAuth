from django.contrib import admin
from .models import RefreshToken, OneTimeToken

admin.site.register(RefreshToken)
admin.site.register(OneTimeToken)
