import base64
import hashlib
import json
import os
import time
from typing import Any, Dict
from django.conf import settings

def b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

def b64url_decode(s: str) -> bytes:
    padding = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode((s + padding).encode("ascii"))

def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def secure_random_token(nbytes: int = 32) -> str:
    return b64url_encode(os.urandom(nbytes))

def _read_file(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()

def jwt_sign_rs256(payload: Dict[str, Any], kid: str | None = None) -> str:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    header = {"alg": "RS256", "typ": "JWT"}
    if kid:
        header["kid"] = kid
    header_b64 = b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")

    private_key = load_pem_private_key(_read_file(settings.JWT_PRIVATE_KEY_PATH), password=None)
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    sig_b64 = b64url_encode(signature)
    return f"{header_b64}.{payload_b64}.{sig_b64}"

def jwt_verify_rs256(token: str) -> Dict[str, Any]:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.serialization import load_pem_public_key

    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid token format")
    header_b64, payload_b64, sig_b64 = parts
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = b64url_decode(sig_b64)

    public_key = load_pem_public_key(_read_file(settings.JWT_PUBLIC_KEY_PATH))
    public_key.verify(signature, signing_input, padding.PKCS1v15(), hashes.SHA256())

    payload = json.loads(b64url_decode(payload_b64).decode("utf-8"))
    now = int(time.time())
    if payload.get("iss") != settings.JWT_ISSUER:
        raise ValueError("Invalid issuer")
    if payload.get("aud") != settings.JWT_AUDIENCE:
        raise ValueError("Invalid audience")
    if int(payload.get("exp", 0)) <= now:
        raise ValueError("Token expired")
    return payload

def get_jwks() -> Dict[str, Any]:
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    
    public_key = load_pem_public_key(_read_file(settings.JWT_PUBLIC_KEY_PATH))
    numbers = public_key.public_numbers()
    
    # n and e need to be base64url encoded without padding
    n_bytes = numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, byteorder="big")
    e_bytes = numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, byteorder="big")
    
    # We use a static key ID based on the issuer for simplicity
    kid = sha256_hex(settings.JWT_ISSUER)[:16]
    
    return {
        "keys": [
            {
                "kty": "RSA",
                "alg": "RS256",
                "use": "sig",
                "kid": kid,
                "n": b64url_encode(n_bytes),
                "e": b64url_encode(e_bytes),
            }
        ]
    }

def make_access_jwt(user_uuid: str, email: str, roles: list[str] | None = None, session_id: str | None = None) -> str:
    import uuid
    now = int(time.time())
    payload = {
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "sub": str(user_uuid),
        "email": email,
        "roles": roles or [],
        "iat": now,
        "exp": now + settings.JWT_ACCESS_TTL_SECONDS,
        "jti": str(uuid.uuid4())
    }
    if session_id:
        payload["sid"] = str(session_id)
        
    kid = sha256_hex(settings.JWT_ISSUER)[:16]
    return jwt_sign_rs256(payload, kid=kid)
