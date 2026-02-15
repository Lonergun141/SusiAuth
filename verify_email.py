import os
import sys
import django

# Add src to sys.path so we can import 'authsvc'
current_path = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(current_path, 'src'))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'authsvc.config.settings.dev')
from django.conf import settings
django.setup()

print(f"EMAIL_BACKEND: {settings.EMAIL_BACKEND}")
