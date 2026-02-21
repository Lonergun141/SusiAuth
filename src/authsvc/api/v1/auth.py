from ninja.security import HttpBearer
from authsvc.apps.common.security import jwt_verify_rs256

class AuthBearer(HttpBearer):
    def authenticate(self, request, token):
        try:
            payload = jwt_verify_rs256(token)
        except Exception:
            return None
        request.jwt = payload
        return payload

auth = AuthBearer()
