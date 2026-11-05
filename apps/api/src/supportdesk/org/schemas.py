"""Organisation settings: the public contract, and the JSONB documents' shapes."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, field_validator, model_validator

from supportdesk.core.net import check_url
from supportdesk.core.schemas import ApiModel

Provider = Literal["extractive", "ollama", "openai", "anthropic"]
EmbedderName = Literal["local", "ollama", "openai"]
AiMode = Literal["off", "draft", "approval", "auto"]

DEFAULT_CATEGORIES = ["billing", "technical", "account", "shipping", "general"]

# Intents that always need a person: refunds move money, account changes move ownership,
# legal and security questions carry liability. The AI may draft, never send, these.
DEFAULT_SENSITIVE = [
    "refund",
    "cancellation",
    "account_change",
    "billing_dispute",
    "legal",
    "security",
    "data_deletion",
]

DEFAULT_MODELS: dict[str, dict[str, str]] = {
    "extractive": {"answer": "extractive", "triage": "rules"},
    "ollama": {"answer": "qwen2.5:1.5b", "triage": "qwen2.5:1.5b"},
    "openai": {"answer": "gpt-4o-mini", "triage": "gpt-4o-mini"},
    "anthropic": {"answer": "claude-haiku-4-5", "triage": "claude-haiku-4-5"},
}
DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
}


class AiConfig(ApiModel):
    """Which models answer, triage and embed. ``extractive`` needs no model at all."""

    provider: Provider = "extractive"
    base_url: str | None = Field(
        None, description="Endpoint for ollama, openai (any compatible server) or anthropic"
    )
    answer_model: str | None = None
    triage_model: str | None = Field(
        None, description="A cheaper model for classification and summaries (model routing)"
    )
    # Use the LLM for triage too; with it off, deterministic rules triage (zero tokens).
    llm_triage: bool = True
    embedder: EmbedderName = "local"
    embed_base_url: str | None = None
    embed_model: str | None = None
    embed_dims: int | None = Field(None, ge=64, le=4096)
    temperature: float = Field(0.2, ge=0, le=1.5)
    max_answer_tokens: int = Field(400, ge=50, le=4000)
    # Retrieved passages are trimmed to this many tokens in the prompt (short context).
    context_tokens: int = Field(1800, ge=200, le=16000)
    top_k: int = Field(5, ge=1, le=20)

    @field_validator("base_url", "embed_base_url")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        return check_url(v, "base_url") if v else None

    def model_for(self, purpose: Literal["answer", "triage"]) -> str:
        defaults = DEFAULT_MODELS[self.provider]
        if purpose == "answer":
            return self.answer_model or defaults["answer"]
        return self.triage_model or self.answer_model or defaults["triage"]

    def endpoint(self, ollama_default: str) -> str | None:
        if self.provider == "ollama":
            return self.base_url or ollama_default
        return self.base_url or DEFAULT_BASE_URLS.get(self.provider)


class Policy(ApiModel):
    """When the AI may answer on its own. Decided by code, never by the model."""

    mode: AiMode = Field(
        "approval",
        description="off: humans only. draft: AI suggests, agents send. approval: AI answers "
        "in-policy questions, sensitive ones wait for approval. auto: like approval, but "
        "sensitive intents are still always escalated",
    )
    auto_categories: list[str] = Field(
        default_factory=lambda: ["technical", "account", "shipping", "general", "billing"],
        description="Categories the AI may resolve without a person",
    )
    min_relevance: float = Field(
        0.5, ge=0, le=1, description="A retrieved passage must score at least this to be cited"
    )
    sensitive_intents: list[str] = Field(default_factory=lambda: list(DEFAULT_SENSITIVE))
    custom_sensitive_keywords: list[str] = Field(
        default_factory=list, description="Extra words that always need a person"
    )
    escalate_negative_sentiment: bool = True
    escalate_vip: bool = True
    # After this many AI answers the customer marked unhelpful, hand over.
    max_unhelpful: int = Field(1, ge=0, le=5)
    # Hand over after this many AI turns in one conversation, whatever happens.
    max_ai_turns: int = Field(6, ge=1, le=50)

    @field_validator("custom_sensitive_keywords")
    @classmethod
    def _keywords(cls, v: list[str]) -> list[str]:
        cleaned = [k.strip().lower() for k in v if k.strip()]
        if len(cleaned) > 100:
            raise ValueError("at most 100 keywords")
        return cleaned


class Budgets(ApiModel):
    """Hard limits, checked atomically before every model call. 0 means unlimited."""

    daily_tokens: int = Field(0, ge=0)
    monthly_tokens: int = Field(0, ge=0)
    daily_cost_usd: Decimal = Field(Decimal("0"), ge=0)
    monthly_cost_usd: Decimal = Field(Decimal("0"), ge=0)
    on_exhausted: Literal["extractive", "human"] = Field(
        "extractive",
        description="When a budget is spent: answer extractively (no model) or hand over",
    )


class TokenSaver(ApiModel):
    exact_cache: bool = True
    semantic_cache: bool = True
    semantic_threshold: float = Field(0.92, ge=0.5, le=1.0)
    cache_ttl_hours: int = Field(24 * 14, ge=1, le=24 * 365)
    # Older turns are folded into a summary line so prompts stay short.
    history_turns: int = Field(6, ge=1, le=40)


class Brand(ApiModel):
    company_name: str = Field("Acme", max_length=120)
    support_email: str | None = Field(None, max_length=320)
    accent_color: str = Field("#4f46e5", pattern=r"^#[0-9a-fA-F]{6}$")
    help_center_title: str = Field("How can we help?", max_length=120)
    website: str | None = Field(None, max_length=500)


class OrgOut(ApiModel):
    id: uuid.UUID
    name: str
    slug: str
    kb_version: int
    created_at: datetime


class SettingsOut(ApiModel):
    org: OrgOut
    brand: Brand
    ai: AiConfig
    ai_key_set: bool
    policy: Policy
    budgets: Budgets
    token_saver: TokenSaver
    categories: list[str]


class SettingsPatch(ApiModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    brand: Brand | None = None
    ai: AiConfig | None = None
    ai_api_key: str | None = Field(
        None, max_length=500, description="Write-only. Empty string clears the stored key"
    )
    policy: Policy | None = None
    budgets: Budgets | None = None
    token_saver: TokenSaver | None = None
    categories: list[str] | None = None

    @field_validator("categories")
    @classmethod
    def _categories(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        cleaned: list[str] = []
        for c in v:
            c = c.strip().lower()
            if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,40}", c):
                raise ValueError(f"category {c!r}: lower case letters, digits, - and _ only")
            if c not in cleaned:
                cleaned.append(c)
        if not 1 <= len(cleaned) <= 30:
            raise ValueError("between 1 and 30 categories")
        return cleaned

    @model_validator(mode="after")
    def _embed_dims(self) -> SettingsPatch:
        ai = self.ai
        if ai and ai.embedder != "local" and not (ai.embed_model and ai.embed_dims):
            raise ValueError("a remote embedder needs embed_model and embed_dims")
        return self


class TeamIn(ApiModel):
    name: str = Field(min_length=1, max_length=80)
    member_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)


class TeamOut(ApiModel):
    id: uuid.UUID
    name: str
    member_ids: list[uuid.UUID]


class AiTestResult(ApiModel):
    ok: bool
    provider: str
    model: str
    latency_ms: int
    message: str
    sample: str | None = None
