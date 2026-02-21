import hashlib
import requests
from ninja.errors import HttpError

def is_password_pwned(password: str) -> bool:
    """
    Checks if a password has been exposed in a known data breach
    using the HaveIBeenPwned API (k-Anonymity model).
    """
    sha1_password = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    prefix, suffix = sha1_password[:5], sha1_password[5:]
    
    try:
        response = requests.get(f"https://api.pwnedpasswords.com/range/{prefix}", timeout=5)
        response.raise_for_status()
    except requests.exceptions.RequestException:
        # If the API is down, fail open (allow the password) to prevent blocking signups
        return False
        
    hashes = (line.split(":") for line in response.text.splitlines())
    for h, count in hashes:
        if h == suffix:
            return True
    
    return False

def check_password_complexity(password: str):
    """
    Validates password and checks HIBP database. 
    Raises HttpError if validation fails.
    """
    if len(password) < 10:
        raise HttpError(400, "Password must be at least 10 characters long.")
    
    if is_password_pwned(password):
        raise HttpError(400, "This password has appeared in a data breach. Please choose a different one.")
