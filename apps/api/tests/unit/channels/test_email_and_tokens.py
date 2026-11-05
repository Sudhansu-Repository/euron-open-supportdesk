"""Email parsing, webhook signatures, tokens and widget origins."""

from __future__ import annotations

import base64
import json
import uuid
from datetime import timedelta

import pytest

from supportdesk.channels.email import InboundError, parse, raw_from_request, strip_quoted
from supportdesk.channels.service import check_origin, frame_ancestors, normalize_origin
from supportdesk.core.errors import PermissionDeniedError
from supportdesk.core.security import (
    decode_token,
    generate_api_key,
    hash_key_secret,
    issue_token,
    parse_api_key,
)
from supportdesk.integrations.service import sign

RAW = (
    b"From: Pat <PAT@Example.com>\r\nTo: Support <support+aaaaaaaaaaaaaaaaaaaaaaaa@acme.test>\r\n"
    b"Cc: other@acme.test\r\nSubject: Re: Help\r\nMessage-ID: <m2@x>\r\nIn-Reply-To: <m1@x>\r\n\r\n"
    b"Thanks, that worked.\r\n\r\nOn Monday, Support wrote:\r\n> try this\r\n"
)


def test_parse_reads_sender_threading_and_the_new_text() -> None:
    mail = parse(RAW)
    assert mail.from_email == "pat@example.com" and mail.subject == "Re: Help"
    assert (
        mail.references == ["<m1@x>"]
        and "support+aaaaaaaaaaaaaaaaaaaaaaaa@acme.test" in mail.recipients
    )
    assert mail.text == "Thanks, that worked." and not mail.automatic


@pytest.mark.parametrize(
    "header",
    [
        "Auto-Submitted: auto-replied",
        "Precedence: bulk",
        "List-Id: <news.example>",
        "X-Autoreply: yes",
    ],
)
def test_automatic_mail_is_recognised(header: str) -> None:
    raw = f"From: a@b.example\r\n{header}\r\nSubject: x\r\n\r\nbody".encode()
    assert parse(raw).automatic


def test_mail_without_a_sender_is_refused() -> None:
    with pytest.raises(InboundError):
        parse(b"Subject: x\r\n\r\nbody")


def test_strip_quoted_variants() -> None:
    assert strip_quoted("New text\n-----Original Message-----\nold") == "New text"
    assert strip_quoted("Hi\n> quoted\nmore") == "Hi\nmore"


def test_ses_notifications_are_unwrapped() -> None:
    inner = {"content": base64.b64encode(b"From: a@b.c\r\n\r\nhi").decode()}
    body = json.dumps({"Type": "Notification", "Message": json.dumps(inner)}).encode()
    assert raw_from_request(body, "application/json").startswith(b"From: a@b.c")
    assert raw_from_request(b"raw", "message/rfc822") == b"raw"
    with pytest.raises(InboundError):
        raw_from_request(b'{"nothing": 1}', "application/json")


def test_webhook_signature_format() -> None:
    sig = sign("whsec_x", 1700000000, b'{"a":1}')
    assert sig.startswith("t=1700000000,v1=") and len(sig.split("v1=")[1]) == 64


def test_tokens_are_bound_to_their_audience() -> None:
    token = issue_token({"sub": "1"}, "s" * 40, "supportdesk-widget", timedelta(minutes=5))
    assert decode_token(token, "s" * 40, "supportdesk-widget") is not None
    assert decode_token(token, "s" * 40, "supportdesk-portal") is None
    assert decode_token(token, "t" * 40, "supportdesk-widget") is None


def test_api_keys_round_trip() -> None:
    key = generate_api_key("pepper")
    prefix, secret = parse_api_key(key.plaintext)  # type: ignore[misc]
    assert prefix == key.prefix and hash_key_secret(secret, "pepper") == key.secret_hash
    assert parse_api_key("sdk_nothex_x") is None and parse_api_key("other_abc") is None


class _Inbox:
    def __init__(self, origins: list[str]) -> None:
        self.allowed_origins = origins
        self.id = uuid.uuid4()


def test_origins() -> None:
    assert normalize_origin("HTTPS://Shop.Example:443/path") == "https://shop.example:443"
    check_origin(_Inbox([]), "https://anything.example")  # open while trying it out
    inbox = _Inbox(["https://shop.example"])
    check_origin(inbox, "https://shop.example")
    check_origin(inbox, "http://localhost:4810", "http://localhost:4810")  # the widget frame itself
    check_origin(inbox, None, "http://localhost:4810")  # a same-origin GET carries no Origin
    with pytest.raises(PermissionDeniedError):
        check_origin(inbox, "https://evil.example", "http://localhost:4810")
    assert frame_ancestors(inbox) == ["https://shop.example"]  # type: ignore[arg-type]
    assert frame_ancestors(_Inbox([])) == ["*"]  # type: ignore[arg-type]


async def test_large_ses_mail_is_read_from_the_inbound_prefix() -> None:
    from types import SimpleNamespace

    from supportdesk.channels.email import raw_message

    class Store:
        async def get(self, key: str) -> bytes:
            assert key == "inbound/abc"
            return b"From: big@example.com\r\n\r\nlarge body"

    container = SimpleNamespace(storage=Store())
    envelope = {
        "Type": "Notification",
        "Message": json.dumps({"receipt": {"action": {"objectKey": "inbound/abc"}}}),
    }
    raw = await raw_message(container, json.dumps(envelope).encode(), "application/json")  # type: ignore[arg-type]
    assert raw.startswith(b"From: big@example.com")
    bad = {
        "Type": "Notification",
        "Message": json.dumps({"receipt": {"action": {"objectKey": "../secrets"}}}),
    }
    with pytest.raises(InboundError):
        await raw_message(container, json.dumps(bad).encode(), "application/json")  # type: ignore[arg-type]
