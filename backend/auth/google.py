"""Google OAuth 2.0 helper functions."""

from __future__ import annotations

import os
from typing import Any, Dict

import requests
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow


def create_oauth_flow(
    client_config: dict[str, Any],
    redirect_uri: str,
    scopes: list[str],
) -> Flow:
    """Create a Google OAuth authorization flow."""

    return Flow.from_client_config(
        client_config=client_config,
        scopes=scopes,
        redirect_uri=redirect_uri,
    )


def get_authorization_url(
    flow: Flow,
) -> tuple[str, str]:
    """Generate the Google authorization URL and CSRF state."""

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )

    return authorization_url, state


def exchange_code_for_credentials(
    flow: Flow,
    code: str,
):
    """Exchange the authorization code for Google credentials."""

    flow.fetch_token(
        code=code
    )

    return flow.credentials


def validate_id_token(
    id_token_str: str,
    audience: str,
) -> dict:
    """Validate a Google ID token."""

    request = Request()

    return id_token.verify_oauth2_token(
        id_token_str,
        request,
        audience,
    )


def fetch_user_profile(credentials) -> Dict[str, Any]:
    """Fetch the authenticated user's profile information.

    Parameters
    ----------
    credentials
        The credentials object returned by ``exchange_code_for_credentials``.

    Returns
    -------
    dict
        A dictionary containing user profile fields such as ``id``, ``email``,
        ``verified_email``, ``name``, ``picture`` and ``locale``.
    """

    if not credentials or not credentials.token:
        raise ValueError("Invalid credentials provided for profile fetch.")

    # Google UserInfo endpoint
    userinfo_endpoint = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {
        "alt": "json",
        "access_token": credentials.token,
    }
    response = requests.get(userinfo_endpoint, params=params)
    response.raise_for_status()
    return response.json()


def build_google_oauth_flow_from_env(
    redirect_uri: str,
    scopes: list[str],
) -> Flow:
    """Create a Google OAuth flow using environment variables."""

    client_id = os.getenv(
        "GOOGLE_CLIENT_ID"
    )

    client_secret = os.getenv(
        "GOOGLE_CLIENT_SECRET"
    )

    if not client_id:
        raise ValueError(
            "GOOGLE_CLIENT_ID is missing."
        )

    if not client_secret:
        raise ValueError(
            "GOOGLE_CLIENT_SECRET is missing."
        )

    client_config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": (
                "https://accounts.google.com/o/oauth2/auth"
            ),
            "token_uri": (
                "https://oauth2.googleapis.com/token"
            ),
            "redirect_uris": [
                redirect_uri
            ],
        }
    }

    return create_oauth_flow(
        client_config,
        redirect_uri,
        scopes,
    )
