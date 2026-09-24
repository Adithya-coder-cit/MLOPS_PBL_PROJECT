"""POST /recommend-route."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import get_routing_service
from api.schemas.common import ROUTING_ERROR_RESPONSES
from api.schemas.routing import RouteRecommendationRequest, RouteRecommendationResponse
from api.services.routing_service import RoutingService

router = APIRouter(tags=["routing"])


@router.post("/recommend-route", response_model=RouteRecommendationResponse, responses=ROUTING_ERROR_RESPONSES,
             summary="Ranked candidate routes via the Stage 6 routing engine")
async def recommend_route(
    body: RouteRecommendationRequest, service: RoutingService = Depends(get_routing_service),
) -> RouteRecommendationResponse:
    candidates = service.recommend(body.origin, body.destination, top_n=body.top_n,
                                    departure_time=body.departure_time)
    return RouteRecommendationResponse(
        origin=body.origin, destination=body.destination, candidates=candidates, selected=candidates[0],
    )
