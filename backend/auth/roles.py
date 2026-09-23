"""Centralized role definitions and helper utilities.

This module defines the role constants used throughout the application and provides
simple helper functions to check a user's role.  The helpers are intentionally
light‑weight so they can be used in FastAPI dependencies or directly in
business logic without pulling in heavy frameworks.

The role hierarchy is:

* ``ADMIN`` – Full access to all resources.
* ``USER`` – Standard authenticated user.
* ``GUEST`` – Unauthenticated or limited access.

The helpers return ``True``/``False`` and are safe to call with ``None``.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Role constants
# ---------------------------------------------------------------------------

ADMIN: str = "admin"
USER: str = "user"
GUEST: str = "guest"

# A tuple of all defined roles – useful for validation.
ALL_ROLES = (ADMIN, USER, GUEST)

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def is_admin(role: str | None) -> bool:
    """Return ``True`` if the role is :data:`ADMIN`.

    Parameters
    ----------
    role: str | None
        The role to check.  ``None`` is treated as not an admin.
    """
    return role == ADMIN


def is_user(role: str | None) -> bool:
    """Return ``True`` if the role is :data:`USER`.

    Parameters
    ----------
    role: str | None
        The role to check.  ``None`` is treated as not a user.
    """
    return role == USER


def is_guest(role: str | None) -> bool:
    """Return ``True`` if the role is :data:`GUEST`.

    Parameters
    ----------
    role: str | None
        The role to check.  ``None`` is treated as not a guest.
    """
    return role == GUEST


def has_role(role: str | None, *expected: str) -> bool:
    """Generic helper to check if ``role`` matches any of ``expected``.

    Parameters
    ----------
    role: str | None
        The role to validate.
    *expected: str
        One or more role constants to compare against.

    Returns
    -------
    bool
        ``True`` if ``role`` is in ``expected``.
    """
    return role in expected

__all__ = [
    "ADMIN",
    "USER",
    "GUEST",
    "ALL_ROLES",
    "is_admin",
    "is_user",
    "is_guest",
    "has_role",
]
