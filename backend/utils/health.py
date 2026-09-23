"""
Health-check utilities for the AI Software Engineer backend.
"""


def health_check() -> dict:
    """
    Return the current application health status.

    Returns:
        dict: Health information for the application.
    """

    return {
        "status": "healthy",
        "workflow": "ready",
    }


__all__ = [
    "health_check",
]
