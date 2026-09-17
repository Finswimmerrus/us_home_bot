from __future__ import annotations

from typing import Any


class DomainError(Exception):
    def __init__(
        self,
        message: str,
        code: str = "DOMAIN_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


class NotFound(DomainError):
    def __init__(self, resource: str, identifier: Any) -> None:
        super().__init__(
            f"{resource} not found",
            "NOT_FOUND",
            {"resource": resource, "id": identifier},
        )
        self.resource = resource
        self.identifier = identifier


class Forbidden(DomainError):
    def __init__(self, action: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(f"Forbidden: {action}", "FORBIDDEN", details or {})


class Conflict(DomainError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, "CONFLICT", details or {})


class ValidationError(DomainError):
    def __init__(
        self,
        message: str,
        field: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        payload = details or {}
        if field is not None:
            payload = {"field": field, **payload}
        super().__init__(message, "VALIDATION_ERROR", payload)
        self.field = field


class MembershipRequired(Forbidden):
    def __init__(self, couple_id: int, user_id: int) -> None:
        super().__init__(
            "membership required",
            {"couple_id": couple_id, "user_id": user_id},
        )


class CoupleFull(Forbidden):
    def __init__(self, couple_id: int) -> None:
        super().__init__("couple is full", {"couple_id": couple_id})


class InvalidStatusTransition(DomainError):
    def __init__(self, current: str, target: str, allowed: list[str]) -> None:
        super().__init__(
            f"Invalid status transition from {current} to {target}",
            "INVALID_STATUS_TRANSITION",
            {"current": current, "target": target, "allowed": allowed},
        )
