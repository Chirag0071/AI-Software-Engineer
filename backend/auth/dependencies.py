from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose.exceptions import JWTError

from .jwt import verify_token

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
