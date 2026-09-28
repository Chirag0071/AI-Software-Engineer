from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Optional

from dotenv import load_dotenv
from jose import jwt
from jose.exceptions import JWTError
from passlib.context import CryptContext


load_dotenv()


SECRET_KEY: str = os.getenv(
    "SECRET_KEY",
    "dev-secret-key",
)

ALGORITHM: str = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES: int = 15

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)


def hash_password(
    password: str,
) -> str:
    return pwd_context.hash(password)


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
    expires_delta: Optional[timedelta] = None,
) -> str:
    to_encode = data.copy()

    if "exp" not in to_encode:
        if expires_delta is None:
            expires_delta = timedelta(
                minutes=ACCESS_TOKEN_EXPIRE_MINUTES
            )

        expire = (
            datetime.utcnow()
            + expires_delta
        )

        to_encode["exp"] = expire

    return jwt.encode(
        to_encode,
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def verify_token(
    token: str,
) -> dict[str, Any]:
    payload = jwt.decode(
        token,
        SECRET_KEY,
        algorithms=[ALGORITHM],
    )

    return payload


def get_role_from_token(
    token: str,
) -> Optional[str]:
    try:
        payload = verify_token(token)

        role = payload.get("role")

        if role is None:
            return None

        return str(role)

    except JWTError:
        return None