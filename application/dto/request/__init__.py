from __future__ import annotations

from .agent import CreateAgentRequest, UpdateAgentRequest
from .auth import LoginRequest, RegisterRequest
from .chat import ChatRequest
from .feedback import FeedbackRequest
from .geocode import BatchGeocodeRequest, IntlGeocodeRequest
from .itinerary import (
    CheckinActivityRequest,
    CompareItinerariesRequest,
    ConfirmPlanRequest,
    CreateItineraryRequest,
    CreateShareLinkRequest,
    RevokeConfirmRequest,
    UpdateActivityCostRequest,
    UpdateItineraryRequest,
    UpdatePhotoRequest,
)
from .news import NewsFavoriteRequest

__all__ = [
    "BatchGeocodeRequest",
    "CheckinActivityRequest",
    "ChatRequest",
    "CompareItinerariesRequest",
    "ConfirmPlanRequest",
    "CreateAgentRequest",
    "CreateItineraryRequest",
    "CreateShareLinkRequest",
    "FeedbackRequest",
    "IntlGeocodeRequest",
    "LoginRequest",
    "NewsFavoriteRequest",
    "RegisterRequest",
    "RevokeConfirmRequest",
    "UpdateActivityCostRequest",
    "UpdateAgentRequest",
    "UpdateItineraryRequest",
    "UpdatePhotoRequest",
]
