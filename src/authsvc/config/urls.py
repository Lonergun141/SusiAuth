from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from authsvc.api.v1.api import api_v1

urlpatterns = [
    path("admin/", admin.site.urls),
    # Minimal login/logout for the OAuth authorization (consent) flow, where the
    # resource owner authenticates in the browser before granting access.
    path("accounts/login/", auth_views.LoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    # OAuth 2.1 / OIDC endpoints: /o/authorize, /o/token, /o/userinfo,
    # /o/.well-known/openid-configuration, /o/.well-known/jwks.json, ...
    path("o/", include("oauth2_provider.urls", namespace="oauth2_provider")),
    path("api/v1/", api_v1.urls),
]
