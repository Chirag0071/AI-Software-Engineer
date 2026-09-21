"""Utility functions for Google OAuth 2.0 integration.

This module provides helpers to:
1. Create an OAuth flow object.
2. Generate the authorization URL.
3. Exchange an authorization code for credentials.
4. Validate an ID token and return its payload.

The implementation relies on the `google-auth` and `google-auth-oauthlib` packages.
"""

from __future__ import annotations

from typing import Dict, Tuple

from google.auth.transport.requests import Request
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow

# ---------------------------------------------------------------------------
# OAuth flow helpers
# ---------------------------------------------------------------------------

def create_oauth_flow(
    client_config: Dict,
    redirect_uri: str,
    scopes: list[str],
) -> Flow:
    """Create a :class:`google_auth_oauthlib.flow.Flow` instance.

    Parameters
    ----------
    client_config:
        The client configuration dictionary as returned by
        ``google.oauth2.service_account.Credentials.from_service_account_file``
        or a manually constructed dict containing ``client_id`` and
        ``client_secret``.
    redirect_uri:
        The URI to which Google will redirect after user consent.
    scopes:
        A list of OAuth scopes requested.

    Returns
    -------
    Flow
        Configured OAuth flow.
    """
    return Flow.from_client_config(
        client_config=client_config,
        scopes=scopes,
        redirect_uri=redirect_uri,
    )


def get_authorization_url(flow: Flow) -> Tuple[str, str]:
    """Generate the Google authorization URL.

    Parameters
    ----------
    flow:
        The OAuth flow instance.

    Returns
    -------
    tuple
        ``(authorization_url, state)`` where ``state`` is a CSRF token.
    """
    auth_url, state = flow.authorization_url()
    return auth_url, state


def exchange_code_for_credentials(flow: Flow, code: str):
    """Exchange an authorization code for credentials.

    Parameters
    ----------
    flow:
        The OAuth flow instance.
    code:
        The authorization code received from the redirect.

    Returns
    -------
    google.oauth2.credentials.Credentials
        The credentials object containing access and refresh tokens.
    """
    flow.fetch_token(code=code)
    return flow.credentials

# ---------------------------------------------------------------------------
# ID token validation helpers
# ---------------------------------------------------------------------------

def validate_id_token(id_token_str: str, audience: str) -> Dict:
    """Validate a Google ID token and return its payload.

    Parameters
    ----------
    id_token_str:
        The raw ID token string.
    audience:
        The expected audience (client ID) for the token.

    Returns
    -------
    dict
        The decoded token payload.

    Raises
    ------
    google.auth.exceptions.GoogleAuthError
        If the token is invalid or cannot be verified.
    """
    request = Request()
    return id_token.verify_oauth2_token(id_token_str, request, audience)

# ---------------------------------------------------------------------------
# Convenience wrapper for common flow creation
# ---------------------------------------------------------------------------

def build_google_oauth_flow_from_env(redirect_uri: str, scopes: list[str]) -> Flow:
    """Build an OAuth flow using client credentials stored in environment.

    The environment variables expected are:
    - ``GOOGLE_CLIENT_ID``
    - ``GOOGLE_CLIENT_SECRET``

    Parameters
    ----------
    redirect_uri:
        The redirect URI for the OAuth flow.
    scopes:
        List of scopes to request.

    Returns
    -------
    Flow
        Configured OAuth flow.
    """
    import os

    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise ValueError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in the environment")

    client_config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }
    return create_oauth_flow(client_config, redirect_uri, scopes)
