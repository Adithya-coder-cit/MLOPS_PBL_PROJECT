"""RouteWise FastAPI application factory.

Endpoints are versioned under /api/v1/*; the same routers are also
mounted at the root path as explicit aliases (not duplicated
implementations — identical handler functions, two paths) for
compatibility with the originally specified unversioned endpoint list.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import API_VERSION, APP_VERSION, get_settings
from api.exceptions import register_exception_handlers
from api.routers import health, model_info, predict, recommend_route, reroute, stops, system
from api.startup import build_app_state

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("routewise.api")

ROUTERS = [health.router, system.router, model_info.router, stops.router, predict.router, recommend_route.router,
           reroute.router]


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("Starting RouteWise API v%s (model_source=%s)", APP_VERSION, settings.model_source)
    app.state.routewise = build_app_state(settings)
    if not app.state.routewise.model_available:
        logger.warning("Started with NO usable model — inference endpoints will return 503 until this is fixed")
    yield
    logger.info("Shutting down RouteWise API")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="RouteWise API",
        description="AI-powered smart travel recommendation system — disruption prediction, "
                     "multi-modal routing, and adaptive rerouting.",
        version=APP_VERSION,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    for router in ROUTERS:
        app.include_router(router, prefix=f"/api/{API_VERSION}")
        app.include_router(router, include_in_schema=False)  # root-path alias, same handlers, hidden from docs

    return app


app = create_app()
