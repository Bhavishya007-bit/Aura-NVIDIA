
import os
import time
from uuid import uuid4
from pathlib import Path
from dotenv import load_dotenv

import jwt
from pwdlib import PasswordHash


load_dotenv(Path(__file__).resolve().parent / ".env")
password_hash = PasswordHash.recommended()

JWT_SECRET = os.getenv("AUTH_JWT_SECRET")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


def hash_password(password: str) -> str:
    """Hash a password using the recommended Argon2 configuration."""
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """Check a password against its stored hash."""
    return password_hash.verify(password, hashed_password)


def create_access_token(student_id: int) -> str:
    """Create a signed access token for a student."""
    if not JWT_SECRET:
        raise RuntimeError(
            "AUTH_JWT_SECRET is missing. Configure it in your environment."
        )

    now = int(time.time())

    payload = {
        "jti": uuid4().hex,
        "sub": str(student_id),
        "iat": now,
        "exp": now + ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }

    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Validate a token and return its claims."""
    if not JWT_SECRET:
        raise RuntimeError(
            "AUTH_JWT_SECRET is missing. Configure it in your environment."
        )

    return jwt.decode(
        token,
        JWT_SECRET,
        algorithms=[JWT_ALGORITHM],
        options={"require": ["sub", "iat", "exp"]},
    )
