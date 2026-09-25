"""Records LIVE operational metrics (Stage 9 §3) for every request that
reaches the app. The only writer of AppState.operational_metrics — never
fabricates a count, only observes what actually happened."""
from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class OperationalMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        state = getattr(request.app.state, "routewise", None)
        if state is not None:
            state.operational_metrics.record_request(request.url.path, response.status_code, duration_ms)
        return response
