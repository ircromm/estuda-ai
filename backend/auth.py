"""
Auth utilities: PIN hashing and JWT tokens.
"""

import os
import time
import hmac
import hashlib
import secrets
import base64
import binascii
import json
from typing import Optional

# Use a simple HMAC-based token system instead of JWT to avoid extra deps.
# Token format: base64(payload).base64(signature)
# Payload is JSON: {"sub": user_id, "nome": nome, "exp": timestamp}

JWT_SECRET = os.getenv("JWT_SECRET", "")
if not JWT_SECRET:
    # Generate a random secret if not set. Warning: tokens won't survive restarts.
    JWT_SECRET = secrets.token_urlsafe(32)
    print("[WARN] JWT_SECRET not set; using random secret (tokens won't survive restart)")

TOKEN_EXPIRY_DAYS = 30


# ──────────────────────────────────────────────
# PIN hashing (bcrypt-compatible, using pbkdf2 from stdlib)
# ──────────────────────────────────────────────


def hash_pin(pin: str) -> str:
    """Hash a PIN using PBKDF2-HMAC-SHA256."""
    salt = secrets.token_bytes(16)
    hashed = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, 200_000)
    # Store as: salt_b64$hash_b64
    return f"{base64.b64encode(salt).decode()}${base64.b64encode(hashed).decode()}"


def verify_pin(pin: str, stored: str) -> bool:
    """Verify a PIN against a stored hash."""
    try:
        salt_b64, hash_b64 = stored.split("$")
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        actual = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, 200_000)
        return hmac.compare_digest(expected, actual)
    except (ValueError, binascii.Error):
        return False


# ──────────────────────────────────────────────
# Token management (simple HMAC-signed tokens)
# ──────────────────────────────────────────────


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(data: str) -> bytes:
    padding = 4 - (len(data) % 4)
    if padding != 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data)


def create_token(user_id: int, nome: str) -> str:
    """Create a signed token for a user."""
    payload = {
        "sub": user_id,
        "nome": nome,
        "exp": int(time.time()) + TOKEN_EXPIRY_DAYS * 86400,
    }
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode()
    payload_b64 = _b64url_encode(payload_bytes)
    signature = hmac.new(
        JWT_SECRET.encode(), payload_b64.encode(), hashlib.sha256
    ).digest()
    sig_b64 = _b64url_encode(signature)
    return f"{payload_b64}.{sig_b64}"


def verify_token(token: str) -> Optional[dict]:
    """Verify a token and return its payload, or None if invalid."""
    try:
        payload_b64, sig_b64 = token.split(".")
        expected_sig = hmac.new(
            JWT_SECRET.encode(), payload_b64.encode(), hashlib.sha256
        ).digest()
        actual_sig = _b64url_decode(sig_b64)
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
        payload = json.loads(_b64url_decode(payload_b64))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except (ValueError, json.JSONDecodeError, KeyError):
        return None


