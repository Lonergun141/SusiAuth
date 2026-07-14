import os

from .base import *  # noqa

DEBUG = True

# Email backend follows EMAIL_PROVIDER (see base.py); dev defaults to console.
# Run Celery email tasks inline in dev unless a broker is explicitly configured,
# so `runserver` works without Redis/a worker.
CELERY_TASK_ALWAYS_EAGER = os.getenv("CELERY_TASK_ALWAYS_EAGER", "1") == "1"

# Database: Uses settings from base.py which loads from .env
# .env -> DB_HOST=localhost (for local)
# docker-compose -> DB_HOST=db (via override)
