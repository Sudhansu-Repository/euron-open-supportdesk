"""Production refuses to boot with demo secrets or unsafe options."""

from __future__ import annotations

import pytest

from supportdesk.core.config import Settings

STRONG = {"session_secret": "s" * 40, "token_pepper": "p" * 40, "local_master_key": "m" * 40}


def prod(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "production",
        "cookie_secure": True,
        "mail_backend": "smtp",
        "public_url": "https://support.example.com",
        "public_api_url": "https://api.support.example.com",
        "cors_origins": "https://support.example.com",
        "ai_allow_private_endpoints": False,
        **STRONG,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def test_a_safe_production_configuration_boots() -> None:
    prod().guard()


def test_development_never_refuses() -> None:
    Settings(environment="development").guard()


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"session_secret": "dev-session-secret-not-for-production"}, "SESSION_SECRET"),
        ({"token_pepper": "short"}, "TOKEN_PEPPER"),
        ({"token_pepper": "s" * 40}, "must differ"),
        ({"local_master_key": "change-me"}, "LOCAL_MASTER_KEY"),
        ({"cookie_secure": False}, "COOKIE_SECURE"),
        ({"mail_backend": "log"}, "MAIL_BACKEND"),
        ({"embedder": "hash"}, "EMBEDDER"),
        ({"cors_origins": "*"}, "CORS_ORIGINS"),
        ({"allow_private_urls": True}, "ALLOW_PRIVATE_URLS"),
        ({"ai_allow_private_endpoints": True}, "AI_ALLOW_PRIVATE_ENDPOINTS"),
        ({"public_url": "http://support.example.com"}, "PUBLIC_URL"),
        ({"SUPPORTDESK_CLOUD": "aws", "aws_endpoint_url": "http://floci:4566"}, "AWS_ENDPOINT_URL"),
    ],
)
def test_unsafe_production_settings_are_refused(overrides: dict[str, object], message: str) -> None:
    with pytest.raises(RuntimeError, match=message):
        prod(**overrides).guard()


def test_kms_mode_does_not_need_a_local_master_key() -> None:
    prod(key_mode="kms", local_master_key="").guard()


def test_cors_origins_split_from_a_comma_list() -> None:
    s = Settings(cors_origins="http://a.example, http://b.example,")  # type: ignore[arg-type]
    assert s.cors_origins == ["http://a.example", "http://b.example"]


def test_mail_from_is_composed() -> None:
    s = Settings(mail_from_name="Lumen Support", mail_from_address="help@lumen.example")
    assert s.mail_from == "Lumen Support <help@lumen.example>"
    assert (
        Settings().cache_backend == "memory"
        and Settings(redis_url="redis://r").cache_backend == "redis"
    )


def test_private_ai_endpoints_are_fine_on_a_closed_installation() -> None:
    prod(ai_allow_private_endpoints=True, signup_enabled=False).guard()
