import os
import sys
import django

# Add src to sys.path
current_path = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(current_path, 'src'))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'authsvc.config.settings.dev')
django.setup()

print("Attempting to import auth router...")
try:
    from authsvc.api.v1.routers import auth
    print("Successfully imported authsvc.api.v1.routers.auth")
except Exception as e:
    print(f"Failed to import: {e}")
    import traceback
    traceback.print_exc()
