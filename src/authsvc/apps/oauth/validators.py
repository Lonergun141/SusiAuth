"""Custom OIDC validator: enrich id_token / UserInfo with standard claims.

Claims are still scope-gated by django-oauth-toolkit's ``oidc_claim_scope``
mapping (email -> "email" scope, name/given_name/family_name -> "profile").
"""
from oauth2_provider.oauth2_validators import OAuth2Validator


class CustomOAuth2Validator(OAuth2Validator):
    def get_additional_claims(self, request):
        user = request.user
        full_name = f"{user.first_name} {user.last_name}".strip()
        return {
            "sub": str(user.uuid),
            "email": user.email,
            "email_verified": user.is_email_verified,
            "name": full_name,
            "given_name": user.first_name,
            "family_name": user.last_name,
        }
