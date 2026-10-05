from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from dotenv import load_dotenv
from jose import jwt
from jose.exceptions import JWTError
from passlib.context import CryptContext


load_dotenv()

SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "dev-secret-key",
)

ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = 15

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)


def hash_password(
    password: str,
) -> str:

    return pwd_context.hash(
        password
    )


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:

    return pwd_context.verify(
        plain_password,
        hashed_password,
    )


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:

    payload = data.copy()

    if "exp" not in payload:
        expires_delta = (
            expires_delta
            or timedelta(
                minutes=ACCESS_TOKEN_EXPIRE_MINUTES
            )
        )

        payload["exp"] = (
            datetime.now(timezone.utc)
            + expires_delta
        )

    return jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def verify_token(
    token: str,
) -> dict[str, Any]:

    return jwt.decode(
        token,
        SECRET_KEY,
        algorithms=[ALGORITHM],
    )


def get_role_from_token(
    token: str,
) -> str | None:

    try:
        payload = verify_token(
            token
        )

        role = payload.get("role")

        return (
            str(role)
            if role is not None
            else None
        )

    except JWTError:
        return None