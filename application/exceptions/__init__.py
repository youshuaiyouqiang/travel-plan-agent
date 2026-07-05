from __future__ import annotations

from application.exceptions.base import ClawException
from application.exceptions.not_found import NotFoundException
from application.exceptions.auth import UnauthorizedException, ForbiddenException
from application.exceptions.validation import ValidationException
from application.exceptions.conflict import ConflictException
from application.exceptions.rate_limit import RateLimitException
from application.exceptions.internal import InternalException, ServiceUnavailableException

__all__ = [
    "ClawException",
    "NotFoundException",
    "UnauthorizedException",
    "ForbiddenException",
    "ValidationException",
    "ConflictException",
    "RateLimitException",
    "InternalException",
    "ServiceUnavailableException",
]
