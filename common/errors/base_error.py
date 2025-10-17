from __future__ import annotations

from typing import Any, Dict, Optional


class BaseServiceError(Exception):
    """Base class for service errors.

    Attributes:
        message: human-readable message
        code: optional machine-readable code
        details: optional dict with extra context
    """

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {"message": self.message, "code": self.code, "details": self.details}


class NotFoundError(BaseServiceError):
    """Resource not found (HTTP 404)."""


class ValidationError(BaseServiceError):
    """Validation error (HTTP 422)."""


class AuthenticationError(BaseServiceError):
    """Authentication / authorization failure (HTTP 401 / 403)."""
