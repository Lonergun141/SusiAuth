from .base import *
import os

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')
DEBUG = False

ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', '').split(',')

# Database
# Expects POSTGRES env vars
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB', 'authdb'),
        'USER': os.environ.get('POSTGRES_USER', 'authuser'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD', 'authpass'),
        'HOST': os.environ.get('POSTGRES_HOST', 'db'),
        'PORT': os.environ.get('POSTGRES_PORT', '5432'),
    }
}
