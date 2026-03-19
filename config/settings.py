"""
Application settings loaded from environment variables.

Uses Pydantic Settings for validation and type coercion.
Secrets and environment-specific values come from env vars.
Business logic config comes from YAML files.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, PostgresDsn, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database connection settings."""

    model_config = SettingsConfigDict(env_prefix="DB_")

    host: str = "localhost"
    port: int = 5432
    user: str = "postgres"
    password: str = "postgres"
    name: str = "lead_scoring"
    pool_size: int = 5
    max_overflow: int = 10

    @computed_field
    @property
    def url(self) -> str:
        """Async PostgreSQL connection URL."""
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"

    @computed_field
    @property
    def sync_url(self) -> str:
        """Sync PostgreSQL connection URL (for Alembic migrations)."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


class CRMSettings(BaseSettings):
    """CRM integration settings."""

    model_config = SettingsConfigDict(env_prefix="CRM_")

    type: Literal["hubspot", "salesforce", "none"] = "none"

    # HubSpot
    hubspot_api_key: str | None = None
    hubspot_access_token: str | None = None

    # Salesforce
    salesforce_client_id: str | None = None
    salesforce_client_secret: str | None = None
    salesforce_username: str | None = None
    salesforce_password: str | None = None
    salesforce_security_token: str | None = None
    salesforce_domain: str = "login"  # or "test" for sandbox


class ModelSettings(BaseSettings):
    """ML model settings."""

    model_config = SettingsConfigDict(env_prefix="MODEL_")

    artifact_path: str = "models/current.joblib"
    version: str = "v0.0.0"

    # Scoring bucket thresholds
    bucket_a_threshold: float = 0.7
    bucket_b_threshold: float = 0.4
    bucket_c_threshold: float = 0.2


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "Lead Scoring API"
    app_version: str = "0.1.0"
    debug: bool = False
    environment: Literal["development", "staging", "production"] = "development"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Nested settings
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    crm: CRMSettings = Field(default_factory=CRMSettings)
    model: ModelSettings = Field(default_factory=ModelSettings)

    # Config file paths
    config_dir: Path = Path(__file__).parent

    def load_yaml_config(self, filename: str) -> dict:
        """Load a YAML configuration file from the config directory."""
        config_path = self.config_dir / filename
        if not config_path.exists():
            return {}
        with open(config_path) as f:
            return yaml.safe_load(f) or {}

    @property
    def features_config(self) -> dict:
        """Load feature definitions from YAML."""
        return self.load_yaml_config("features.yaml")

    @property
    def crm_mappings(self) -> dict:
        """Load CRM field mappings from YAML."""
        return self.load_yaml_config("crm.yaml")


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.
    
    Using lru_cache ensures settings are only loaded once.
    """
    return Settings()
