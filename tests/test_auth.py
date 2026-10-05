import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from jose.exceptions import JWTError


os.environ.setdefault(
    "SECRET_KEY",
    "testsecretkey123",
)

from backend.auth.jwt import (
    ALGORITHM,
    SECRET_KEY,
    create_access_token,
)
from backend.main import app


client = TestClient(app)


def generate_token(
    role: str = "user",
) -> str:

    return create_access_token(
        {
            "sub": "testuser",
            "email": "test@example.com",
            "role": role,
            "exp": (
                datetime.now(timezone.utc)
                + timedelta(minutes=15)
            ),
        }
    )


def test_google_login_endpoint():

    response = client.get(
        "/auth/google/login"
    )

    assert response.status_code == 200

    data = response.json()

    assert "auth_url" in data

    assert data["auth_url"].startswith(
        "https://accounts.google.com"
    )


def test_google_callback_returns_jwt():

    response = client.get(
        "/auth/google/callback",
        params={"code": "dummycode"},
    )

    assert response.status_code == 200

    data = response.json()

    token = data["access_token"]

    payload = jwt.decode(
        token,
        SECRET_KEY,
        algorithms=[ALGORITHM],
    )

    assert payload["email"] == "user@example.com"
    assert payload["role"] == "admin"
    assert "exp" in payload


def test_protected_route_requires_admin_role():

    admin_token = generate_token(
        "admin"
    )

    response = client.get(
        "/protected",
        headers={
            "Authorization":
                f"Bearer {admin_token}"
        },
    )

    assert response.status_code == 200

    user_token = generate_token(
        "user"
    )

    response = client.get(
        "/protected",
        headers={
            "Authorization":
                f"Bearer {user_token}"
        },
    )

    assert response.status_code == 403


def test_access_token_expiration():

    expired_token = create_access_token(
        {
            "sub": "testuser",
            "role": "admin",
            "exp": (
                datetime.now(timezone.utc)
                - timedelta(seconds=1)
            ),
        }
    )

    with pytest.raises(JWTError):
        jwt.decode(
            expired_token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )