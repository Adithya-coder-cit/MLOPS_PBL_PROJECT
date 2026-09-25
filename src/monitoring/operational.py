"""Local/development operational monitoring (Stage 9 §3): in-process
counters over ACTUALLY OBSERVABLE FastAPI request outcomes. This is
explicitly not distributed production monitoring — one instance, one
process, counters reset on restart. The only writer is
api/middleware.py's OperationalMetricsMiddleware, which wraps every
request that reaches the app.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field

_MAX_LATENCY_SAMPLES = 1000


@dataclass
class OperationalMetrics:
    request_count: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    prediction_errors: int = 0
    route_recommendation_errors: int = 0
    _latencies_ms: list[float] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record_request(self, path: str, status_code: int, duration_ms: float) -> None:
        with self._lock:
            self.request_count += 1
            if status_code < 400:
                self.successful_requests += 1
            else:
                self.failed_requests += 1
                if "predict" in path:
                    self.prediction_errors += 1
                if "recommend-route" in path or "reroute" in path:
                    self.route_recommendation_errors += 1
            self._latencies_ms.append(duration_ms)
            if len(self._latencies_ms) > _MAX_LATENCY_SAMPLES:
                self._latencies_ms.pop(0)

    def _latency_summary(self) -> dict:
        with self._lock:
            latencies = sorted(self._latencies_ms)
        n = len(latencies)
        if n == 0:
            return {"mean": None, "p50": None, "p95": None, "max": None, "sample_size": 0}
        return {
            "mean": sum(latencies) / n,
            "p50": latencies[int(n * 0.5)] if n > 1 else latencies[0],
            "p95": latencies[max(0, int(n * 0.95) - 1)],
            "max": latencies[-1],
            "sample_size": n,
        }

    def snapshot(self, model_available: bool) -> dict:
        return {
            "request_count": self.request_count,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "prediction_errors": self.prediction_errors,
            "route_recommendation_errors": self.route_recommendation_errors,
            "latency_ms": self._latency_summary(),
            "model_load_status": "available" if model_available else "unavailable",
            "scope": "local/development process-lifetime counters — reset on API restart, not distributed",
        }
