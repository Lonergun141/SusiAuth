from ninja import NinjaAPI
from authsvc.api.v1.routers.auth import router as auth_router

api_v1 = NinjaAPI(title="Auth Service API", version="1.0.0")
api_v1.add_router("/auth", auth_router)
