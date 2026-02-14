from django.contrib import admin
from django.urls import path
from authsvc.api.v1.api import api_v1

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api_v1.urls),
]
