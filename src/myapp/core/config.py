from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseModel):
    url: SecretStr = SecretStr("postgresql+asyncpg://app:app@localhost:5432/app")
    pool_size: int = Field(default=5, ge=1, le=100)
    max_overflow: int = Field(default=5, ge=0, le=100)
    pool_timeout: float = Field(default=5, gt=0)
    readiness_timeout: float = Field(default=2, gt=0, le=10)

    @model_validator(mode="after")
    def validate_url(self) -> Self:
        if not self.url.get_secret_value().startswith("postgresql+asyncpg://"):
            raise ValueError("database must use postgresql+asyncpg")
        return self


class AuthSettings(BaseModel):
    issuer: str = ""
    audience: str = ""
    jwks_url: str = ""
    algorithms: list[Literal["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"]] = ["RS256"]
    clock_skew: int = Field(default=30, ge=0, le=120)
    cache_ttl: int = Field(default=300, ge=10, le=3600)
    required_claims: list[str] = ["sub", "iss", "aud", "exp", "iat"]
    expected_claims: dict[str, str] = {}
    allowed_claims: list[str] = []

    @property
    def configured(self) -> bool:
        return bool(self.issuer and self.audience)

    @model_validator(mode="after")
    def validate_auth(self) -> Self:
        if bool(self.issuer) != bool(self.audience) or (self.jwks_url and not self.configured):
            raise ValueError("configure issuer and audience together")
        if not self.algorithms:
            raise ValueError("at least one signature algorithm is required")
        for value in (self.issuer, self.jwks_url):
            if value and (urlsplit(value).scheme != "https" or not urlsplit(value).hostname):
                raise ValueError("SSO endpoints must use HTTPS")
        return self


class AuditSettings(BaseModel):
    enabled: bool = True
    retention_days: int = Field(default=90, ge=1)
    max_payload_bytes: int = Field(default=4096, ge=128, le=65536)
    excluded_fields: set[str] = {
        "password",
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "cookie",
        "authorization",
        "api_key",
        "cookies",
        "client_secret",
    }
    excluded_entities: set[str] = set()
    actions: set[str] = {"create", "update", "delete"}


class LoggingSettings(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    access: bool = True


class EmailSettings(BaseModel):
    provider: str | None = None
    api_key: SecretStr | None = None
    from_address: str | None = None


class IntegrationSettings(BaseModel):
    base_url: str
    timeout: float = Field(default=5, gt=0)
    api_key: SecretStr | None = None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore",
        hide_input_in_errors=True,
    )
    project_name: str = "Python Backend"
    description: str = "Modular backend infrastructure"
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False
    public_url: str = "http://localhost:8000"
    cors_origins: list[str] = []
    request_timeout: float = Field(default=30, gt=0, le=300)
    max_request_bytes: int = Field(default=1048576, ge=1024)
    build_version: str = "0.1.0"
    git_sha: str = "unknown"
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    audit: AuditSettings = Field(default_factory=AuditSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    email: EmailSettings = Field(default_factory=EmailSettings)
    integrations: dict[str, IntegrationSettings] = {}

    @model_validator(mode="after")
    def production_safety(self) -> Self:
        if "*" in self.cors_origins:
            raise ValueError("explicit CORS origins required")
        if self.environment == "production":
            if self.debug or self.logging.level == "DEBUG":
                raise ValueError("debug is forbidden in production")
            if not self.public_url.startswith("https://"):
                raise ValueError("production public URL must use HTTPS")
            db = urlsplit(self.database.url.get_secret_value())
            if not db.password or db.password in {"app", "password", "postgres"}:
                raise ValueError("inject a non-default database credential")
            if any(not origin.startswith("https://") for origin in self.cors_origins):
                raise ValueError("production CORS must use HTTPS")
        return self
