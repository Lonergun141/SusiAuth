import concurrent.futures
from django.conf import settings
from django.core.mail import send_mail

# Keep a global executor to reuse thread pool
_email_executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)

def _sync_send_email(to_email: str, subject: str, body: str) -> None:
    send_mail(
        subject=subject,
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[to_email],
        fail_silently=False,
    )

def send_auth_email(to_email: str, subject: str, body: str) -> None:
    """
    Fire-and-forget email sending using a background thread.
    This prevents the main API loop from blocking while waiting for the SMTP server.
    """
    _email_executor.submit(_sync_send_email, to_email, subject, body)
