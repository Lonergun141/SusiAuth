import random
import string

def generate_otp_code(length: int = 6) -> str:
    """Generate a numeric OTP code."""
    return ''.join(random.choices(string.digits, k=length))
