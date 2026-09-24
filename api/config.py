"""API configuration, loaded from environment variables (.env). No
credentials or secrets live in code — everything configurable comes from
here. See .env.example for the full list and defaults.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_VERSION = "0.1.0"  # RouteWise application version — bump on real behavioral changes, not just any commit
API_VERSION = "v1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", protected_namespaces=(),
    )

    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    api_cors_origins: str = Field(default="", alias="API_CORS_ORIGINS")

    mlflow_tracking_uri: str = Field(default="./mlruns", alias="MLFLOW_TRACKING_URI")
    mlflow_experiment_name: str = Field(default="RouteWise-Disruption-Prediction", alias="MLFLOW_EXPERIMENT_NAME")
    registered_model_name: str = Field(default="RouteWise-Disruption-Model", alias="REGISTERED_MODEL_NAME")

    # "production" or "candidate" — see prediction_source_kind rationale in
    # src/routing/prediction_source.py. Never silently falls back between them.
    model_source: str = Field(default="candidate", alias="MODEL_SOURCE")
    model_candidate_version: str | None = Field(default=None, alias="MODEL_CANDIDATE_VERSION")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
