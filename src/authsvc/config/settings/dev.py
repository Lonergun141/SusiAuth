from .base import *  # noqa

DEBUG = True

import os

# Email
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")

# Database: Uses settings from base.py which loads from .env
# .env -> DB_HOST=localhost (for local)
# docker-compose -> DB_HOST=db (via override)
