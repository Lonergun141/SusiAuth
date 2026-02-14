import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'authsvc.config.settings.prod')

application = get_asgi_application()
