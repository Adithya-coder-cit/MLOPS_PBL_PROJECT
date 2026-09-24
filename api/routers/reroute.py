"""POST /reroute."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import get_routing_service
from api.schemas.common import ROUTING_ERROR_RESPONSES
from api.schemas.routing import RerouteRequest, RerouteResponse
from api.services.routing_service import RoutingService

router = APIRouter(tags=["routing"])


@router.post("/reroute", response_model=RerouteResponse, responses=ROUTING_ERROR_RESPONSES,
             summary="Adaptive rerouting given a caller-supplied update")
async def reroute_endpoint(
    body: RerouteRequest, service: RoutingService = Depends(get_routing_service),
) -> RerouteResponse:
    result = service.reroute(body.origin, body.destination, body.edge_updates, top_n=body.top_n)
    return RerouteResponse(**result)
