from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose.exceptions import JWTError

from .jwt import verify_token, get_role_from_token

# OAuth2 scheme for extracting the bearer token from the Authorization header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def get_current_user(token: str = Depends(oauth2_scheme)):
    """Dependency that extracts the current user from the JWT token.

    Parameters
    ----------
    token : str
        The JWT token extracted from the Authorization header.

    Returns
    -------
    dict
        The decoded token payload.

    Raises
    ------
    HTTPException
        If the token is invalid or expired.
    """
    try:
        payload = verify_token(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


def get_current_active_user(current_user: dict = Depends(get_current_user)):
    """Dependency that ensures the user is active.

    The token payload is expected to contain an ``is_active`` boolean claim.
    If the claim is missing or ``False`` an HTTP 403 error is raised.

    Returns
    -------
    dict
        The user payload.
    """
    if not current_user.get("is_active", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )
    return current_user


def get_current_active_admin(current_user: dict = Depends(get_current_active_user)):
    """Dependency that ensures the user has an admin role.

    The token payload is expected to contain a ``role`` claim. The admin
    role is identified by the string ``"admin"`` (case-insensitive).

    Returns
    -------
    dict
        The user payload.
    """
    role = current_user.get("role", "").lower()
    if role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    return current_user
