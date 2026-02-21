from ninja import NinjaAPI
from authsvc.api.v1.routers.auth import router as auth_router
from authsvc.api.v1.routers.health import router as health_router
from authsvc.apps.common.security import get_jwks

api_v1 = NinjaAPI(title="Auth Service API", version="1.0.0")
api_v1.add_router("/auth", auth_router)
api_v1.add_router("/health", health_router)

@api_v1.get("/.well-known/jwks.json", response=dict, tags=["auth"])
def well_known_jwks(request):
    """
    Returns the JSON Web Key Set (JWKS) containing the public keys
    used to sign the JWTs. Downstream applications can use this to
    verify tokens statelessly.
    """
    return get_jwks()
