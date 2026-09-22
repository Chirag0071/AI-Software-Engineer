"""
JWT utilities for authentication.

This module provides:
- Password hashing and verification
- JWT access-token creation
- JWT verification
- Role extraction from JWT payloads
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Optional

from dotenv import load_dotenv
from jose import jwt
from jose.exceptions import JWTError
from passlib.context import CryptContext


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

load_dotenv()


# ---------------------------------------------------------------------------
# JWT configuration
# ---------------------------------------------------------------------------

SECRET_KEY: str = os.getenv(
    "SECRET_KEY",
    "dev-secret-key",
)

ALGORITHM: str = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES: int = 15


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)


def hash_password(password: str) -> str:
    """
    Hash a plain-text password.

    Args:
        password: Plain-text password.

    Returns:
        Secure password hash.
    """

    return pwd_context.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    """
    Verify a plain-text password against a password hash.

    Args:
        plain_password: Password supplied by the user.
        hashed_password: Previously generated password hash.

    Returns:
        True when the password matches, otherwise False.
    """

    return pwd_context.verify(
        plain_password,
        hashed_password,
    )


# ---------------------------------------------------------------------------
# JWT creation
# ---------------------------------------------------------------------------

def create_access_token(
    data: dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a signed JWT access token.

    Important:
        If the supplied payload already contains an ``exp`` claim,
        that value is preserved.

        This allows callers and tests to intentionally create tokens
        with custom expiration times, including already-expired tokens.

    Args:
        data:
            Payload data to place inside the JWT.

        expires_delta:
            Optional amount of time from now after which the token
            should expire.

    Returns:
        Encoded JWT string.
    """

    to_encode = data.copy()

    # Only create a default expiration when the caller did not
    # provide one.
    if "exp" not in to_encode:

        if expires_delta is None:
            expires_delta = timedelta(
                minutes=ACCESS_TOKEN_EXPIRE_MINUTES
            )

        expire = datetime.utcnow() + expires_delta

        to_encode["exp"] = expire

    return jwt.encode(
        to_encode,
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


# ---------------------------------------------------------------------------
# JWT verification
# ---------------------------------------------------------------------------

def verify_token(
    token: str,
) -> dict[str, Any]:
    """
    Decode and verify a JWT.

    Args:
        token:
            JWT string supplied by the client.

    Returns:
        Decoded JWT payload.

    Raises:
        JWTError:
            If the token is invalid, expired, incorrectly signed,
            or otherwise cannot be verified.
    """

    payload = jwt.decode(
        token,
        SECRET_KEY,
        algorithms=[ALGORITHM],
    )

    return payload


# ---------------------------------------------------------------------------
# Role extraction
# ---------------------------------------------------------------------------

def get_role_from_token(
    token: str,
) -> Optional[str]:
    """
    Extract the role from a verified JWT.

    Args:
        token:
            JWT string.

    Returns:
        Role string if present and valid, otherwise None.
    """

    try:
        payload = verify_token(token)

        role = payload.get("role")

        if role is None:
            return None

        return str(role)

    except JWTError:
        return None


# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------

__all__ = [
    "SECRET_KEY",
    "ALGORITHM",
    "ACCESS_TOKEN_EXPIRE_MINUTES",
    "hash_password",
    "verify_password",
    "create_access_token",
    "verify_token",
    "get_role_from_token",
]