from django.contrib import admin
from django.urls import path

# Import NinjaAPI instance when ready
# from authsvc.api.v1.api import api

urlpatterns = [
    path('admin/', admin.site.urls),
    # path('api/v1/', api.urls),
]
