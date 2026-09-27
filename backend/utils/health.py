"""
Health-check utilities for the AI Software Engineer backend.
"""


def health_check() -> dict:
    """
    Return the health status of the application.

    The health-check contract intentionally contains exactly
    two fields:
        - status
        - workflow
    """

    return {
        "status": "healthy",
        "workflow": "ready",
    }


__all__ = [
    "health_check",
]