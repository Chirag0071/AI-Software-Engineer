"""JWT utilities for authentication.

This module provides functions to create and verify JSON Web Tokens (JWT)
using the `python-jose` library. It also includes utilities for hashing
and verifying passwords with `passlib`.

The secret key used for signing tokens is expected to be stored in the
environment variable ``SECRET_KEY``. The module will raise a
``RuntimeError`` if the key is not found.

The default token expiration is 15 minutes and the HS256 algorithm is
used.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Dict, Optional

from jose import jwt
from jose.exceptions import JWTError
from passlib.context import CryptContext

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Load the secret key from the environment. A clear error is raised if it
# is missing to avoid silent failures.
SECRET_KEY: str = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "Environment variable 'SECRET_KEY' is required for JWT operations."
    )

ALGORITHM: str = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES: int = 15

# ---------------------------------------------------------------------------
# Password hashing utilities
# ---------------------------------------------------------------------------

# Passlib context configured to use bcrypt. The ``deprecated`` flag ensures
# that any older schemes are automatically marked as deprecated.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a plain-text password.

    Parameters
    ----------
    password: str
        The plain-text password to hash.

    Returns
    -------
    str
        The hashed password.
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against a hashed password.

    Parameters
    ----------
    plain_password: str
        The plain-text password to verify.
    hashed_password: str
        The hashed password to compare against.

    Returns
    -------
    bool
        ``True`` if the passwords match, ``False`` otherwise.
    """
    return pwd_context.verify(plain_password, hashed_password)

# ---------------------------------------------------------------------------
# JWT utilities
# ---------------------------------------------------------------------------


def create_access_token(
    data: Dict[str, str], expires_delta: Optional[timedelta] = None
) -> str:
    """Create a signed JWT access token.

    Parameters
    ----------
    data: Dict[str, str]
        The payload data to encode in the token. Typically contains user
        identifiers such as ``sub``.
    expires_delta: Optional[timedelta]
        Optional custom expiration delta. If ``None`` a default of
        :data:`ACCESS_TOKEN_EXPIRE_MINUTES` minutes is used.

    Returns
    -------
    str
        The encoded JWT token.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta if expires_delta is not None else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Dict[str, str]:
    """Decode and verify a JWT token.

    Parameters
    ----------
    token: str
        The JWT token to verify.

    Returns
    -------
    Dict[str, str]
        The decoded payload if the token is valid.

    Raises
    ------
    jose.exceptions.JWTError
        If the token is invalid or expired.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as exc:
        # Re-raise the exception to let callers handle authentication errors.
        raise exc

__all__ = [
    "hash_password",
    "verify_password",
    "create_access_token",
    "verify_token",
]
