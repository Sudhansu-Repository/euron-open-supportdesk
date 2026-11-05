"""Runtime configuration, validated once at boot.

Every setting comes from the environment. The API, the background worker and the CLI all
read ``Settings``. Security-relevant settings are checked by ``guard()`` so a misconfigured
production deployment refuses to start instead of running with demo secrets.

Per-organisation choices (AI provider, models, policy, budgets) live in the database and
are edited in the app; the environment only sets deployment-wide defaults and limits.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

INSECURE_SECRETS = {"", "change-me", "replace-with-output-of-make-env", "dev", "secret"}


def _split(v: object) -> object:
    if isinstance(v, str):
        return [item.strip() for item in v.split(",") if item.strip()]
    return v


def _insecure(value: str) -> bool:
    return value in INSECURE_SECRETS or "not-for-production" in value or len(value) < 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False)

    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    cloud: Literal["local", "floci", "aws"] = Field("local", alias="SUPPORTDESK_CLOUD")

    database_url: str = "postgresql+asyncpg://supportdesk:supportdesk@localhost:4842/supportdesk"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    # Live updates across API replicas, caches, budget counters and rate limits. Without it
    # each process keeps its own (exact for one replica); jobs never depend on it.
    redis_url: str = ""
    memory_cache_max_bytes: int = Field(64_000_000, ge=1_000_000)

    session_secret: str = "dev-session-secret-not-for-production"  # noqa: S105 dev default, refused in production by guard()
    # Peppers the hashes of API keys, invitation, portal and widget tokens.
    token_pepper: str = "dev-token-pepper-not-for-production"  # noqa: S105 refused in production
    session_ttl_hours: int = 12
    cookie_secure: bool = False
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:4810"]
    )
    # Where agents and customers open the app (links in emails, the widget snippet).
    public_url: str = "http://localhost:4810"
    # Where browsers on customer websites reach the API (the widget talks to it directly).
    public_api_url: str = "http://localhost:4830"
    # Anyone may create an organisation from the sign-up page. Turn off on a private install
    # once the first organisation exists; invitations still work.
    signup_enabled: bool = True

    # Secrets stored in the database (AI provider keys, webhook signing secrets) are sealed.
    key_mode: Literal["local", "kms"] = "local"
    local_master_key: str = "dev-local-master-key-not-for-production"
    kms_key_id: str = "alias/supportdesk-local"

    aws_region: str = "us-east-1"
    aws_endpoint_url: str | None = None
    s3_force_path_style: bool = False
    # Attachments, uploaded knowledge files, exports and backups. Rows keep only the key.
    objects_bucket: str = "supportdesk-local-objects"
    storage: Literal["local", "s3"] = "local"
    local_storage_dir: str = "./.data/objects"

    # Outgoing mail: "log" keeps it in memory (development, tests), "smtp" (Mailpit
    # locally, any relay in production), "ses" (AWS).
    mail_backend: Literal["log", "smtp", "ses"] = "log"
    mail_from_name: str = "Support"
    mail_from_address: str = "support@supportdesk.local"
    # Replies to ticket emails go to <local>+<ticket token>@<domain>, so they thread back.
    mail_reply_domain: str = "supportdesk.local"
    smtp_host: str = "localhost"
    smtp_port: int = Field(4826, ge=1, le=65535)

    # Embeddings: "local" runs fastembed (ONNX, CPU) in the process; "hash" is a
    # deterministic test embedder with no model download; org settings may pick a remote
    # embedder (Ollama, OpenAI-compatible) instead.
    embedder: Literal["local", "hash"] = "local"
    local_embedding_model: str = "BAAI/bge-small-en-v1.5"
    model_cache_dir: str = "./.data/models"
    # Ollama endpoint offered as the default for the zero-API-key mode.
    ollama_url: str = "http://localhost:4834"
    # Remote AI endpoints may be private addresses (Ollama in the same network) unless off.
    ai_allow_private_endpoints: bool = True
    ai_timeout_s: float = Field(60.0, gt=0, le=600)

    # Knowledge ingestion bounds.
    max_upload_bytes: int = Field(25_000_000, ge=10_000)
    max_attachment_bytes: int = Field(10_000_000, ge=10_000)
    max_crawl_pages: int = Field(50, ge=1, le=1000)
    # Webhook targets and crawled URLs must be public unless this is on (local demos).
    allow_private_urls: bool = False

    # Bodies above this are refused before parsing (uploads use max_upload_bytes).
    max_body_bytes: int = Field(1_000_000, ge=10_000)
    # Messages per minute one widget visitor may send.
    widget_rpm: int = Field(20, ge=1)
    # Sign-in and sign-up attempts per minute from one address (lockout is separate).
    login_rpm: int = Field(20, ge=1)
    signup_rpm: int = Field(5, ge=1)
    # Keep idle HTTP connections longer than the load balancer does (ALB idle timeout 300 s),
    # or the balancer reuses a connection the API already closed: intermittent 502s.
    http_keep_alive_s: int = Field(75, ge=5, le=3600)
    worker_poll_interval_s: float = Field(5.0, gt=0)
    worker_concurrency: int = Field(8, ge=1, le=64)
    job_lease_s: int = Field(120, ge=10, le=3600)
    worker_metrics_port: int = Field(9464, ge=0, le=65535)
    otel_enabled: bool = False

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        return _split(v)

    @property
    def cache_backend(self) -> Literal["redis", "memory"]:
        return "redis" if self.redis_url else "memory"

    @property
    def mail_from(self) -> str:
        return f"{self.mail_from_name} <{self.mail_from_address}>"

    def guard(self) -> None:
        """Refuse to boot in production with demo secrets or unsafe options."""
        if self.environment != "production":
            return
        names = ("session_secret", "token_pepper")
        problems: list[str] = [
            f"{name.upper()} must be a random value of at least 32 chars"
            for name in names
            if _insecure(getattr(self, name))
        ]
        if self.key_mode == "local" and _insecure(self.local_master_key):
            problems.append("LOCAL_MASTER_KEY must be set (or use KEY_MODE=kms)")
        if self.session_secret == self.token_pepper:
            problems.append("SESSION_SECRET and TOKEN_PEPPER must differ")
        if self.cloud == "aws" and self.aws_endpoint_url:
            problems.append("AWS_ENDPOINT_URL must be unset when SUPPORTDESK_CLOUD=aws")
        if not self.cookie_secure:
            problems.append("COOKIE_SECURE must be true in production")
        if self.mail_backend == "log":
            problems.append("MAIL_BACKEND must be smtp or ses in production (ticket email)")
        if self.embedder == "hash":
            problems.append("EMBEDDER=hash is for tests; use local in production")
        if "*" in self.cors_origins:
            problems.append("CORS_ORIGINS must list the app's origins, not *")
        if self.allow_private_urls:
            problems.append("ALLOW_PRIVATE_URLS must be false in production (SSRF)")
        if self.ai_allow_private_endpoints and self.signup_enabled:
            # With open sign-up any stranger becomes a tenant admin who can point the AI
            # endpoint at internal hosts. A private model (Ollama in the VPC) is fine on an
            # installation that does not let strangers in.
            problems.append(
                "AI_ALLOW_PRIVATE_ENDPOINTS=true needs SIGNUP_ENABLED=false in production (SSRF)"
            )
        for name in ("public_url", "public_api_url"):
            if not getattr(self, name).startswith("https://"):
                problems.append(f"{name.upper()} must be https in production")
        if problems:
            raise RuntimeError("unsafe production configuration: " + "; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.guard()
    return settings
