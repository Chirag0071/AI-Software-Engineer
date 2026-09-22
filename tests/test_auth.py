"""
Authentication tests for the AI Software Engineer backend.
"""

import os
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from jose.exceptions import JWTError


# ---------------------------------------------------------------------------
# Test environment
# ---------------------------------------------------------------------------

# Set the test secret before importing the application and JWT module.
os.environ.setdefault(
    "SECRET_KEY",
    "testsecretkey123",
)


# ---------------------------------------------------------------------------
# Application imports
# ---------------------------------------------------------------------------

from backend.main import app
from backend.auth.jwt import (
    create_access_token,
    SECRET_KEY,
    ALGORITHM,
)


# ---------------------------------------------------------------------------
# Test client
# ---------------------------------------------------------------------------

client = TestClient(app)


# ---------------------------------------------------------------------------
# Test helper
# ---------------------------------------------------------------------------

def generate_token(
    role: str = "user",
) -> str:
    """
    Generate a valid JWT for testing.
    """

    payload = {
        "sub": "testuser",
        "email": "test@example.com",
        "role": role,
        "exp": datetime.utcnow() + timedelta(
            minutes=15
        ),
    }

    return create_access_token(
        payload
    )


# ---------------------------------------------------------------------------
# Google login endpoint
# ---------------------------------------------------------------------------

def test_google_login_endpoint():
    """
    Verify that the Google login endpoint returns
    the expected OAuth authorization URL.
    """

    response = client.get(
        "/auth/google/login"
    )

    assert response.status_code == 200

    data = response.json()

    assert "auth_url" in data

    assert data["auth_url"].startswith(
        "https://accounts.google.com"
    )


# ---------------------------------------------------------------------------
# Google callback endpoint
# ---------------------------------------------------------------------------

def test_google_callback_returns_jwt():
    """
    Verify that the Google callback endpoint
    returns a valid JWT access token.
    """

    response = client.get(
        "/auth/google/callback",
        params={
            "code": "dummycode"
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert "access_token" in data

    assert data["token_type"] == "bearer"

    token = data["access_token"]

    # jwt.decode() already returns a Python dictionary.
    # Do NOT use json.loads() here.
    payload = jwt.decode(
        token,
        SECRET_KEY,
        algorithms=[ALGORITHM],
    )

    assert payload["email"] == "user@example.com"

    assert payload["role"] == "admin"

    assert "exp" in payload


# ---------------------------------------------------------------------------
# Protected route
# ---------------------------------------------------------------------------

def test_protected_route_requires_admin_role():
    """
    Verify that:
    - admin users can access the protected endpoint
    - normal users receive HTTP 403
    """

    # ---------------------------------------------------------------
    # Admin user
    # ---------------------------------------------------------------

    admin_token = generate_token(
        "admin"
    )

    response = client.get(
        "/protected",
        headers={
            "Authorization": f"Bearer {admin_token}"
        },
    )

    assert response.status_code == 200

    response_data = response.json()

    assert "message" in response_data

    assert "Hello" in response_data["message"]

    # ---------------------------------------------------------------
    # Normal user
    # ---------------------------------------------------------------

    user_token = generate_token(
        "user"
    )

    response = client.get(
        "/protected",
        headers={
            "Authorization": f"Bearer {user_token}"
        },
    )

    assert response.status_code == 403

    response_data = response.json()

    assert (
        "Operation requires role"
        in response_data["detail"]
    )


# ---------------------------------------------------------------------------
# JWT expiration
# ---------------------------------------------------------------------------

def test_access_token_expiration():
    """
    Verify that an already-expired JWT is rejected.

    This test specifically checks that create_access_token()
    does not overwrite an explicitly supplied exp claim.
    """

    expired_payload = {
        "sub": "testuser",
        "email": "test@example.com",
        "role": "admin",
        "exp": datetime.utcnow() - timedelta(
            seconds=1
        ),
    }

    expired_token = create_access_token(
        expired_payload
    )

    with pytest.raises(JWTError):

        jwt.decode(
            expired_token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )