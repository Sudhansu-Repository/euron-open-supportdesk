"""Amazon SNS messages (SES inbound mail arrives this way): signature check and
subscription confirmation.

The inbound URL already carries a secret token; the signature check is defence in depth,
so a leaked token alone cannot inject mail through a fake SNS envelope. Certificates and
confirmation links are fetched only from ``sns.<region>.amazonaws.com`` over HTTPS, never
from an address the message chose freely.
"""

from __future__ import annotations

import base64
import re
from typing import Any
from urllib.parse import urlsplit

import httpx
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

_SNS_HOST = re.compile(r"^sns\.[a-z0-9-]+\.amazonaws\.com(\.cn)?$")
_CERTS: dict[str, x509.Certificate] = {}
_FIELDS = {
    "Notification": ("Message", "MessageId", "Subject", "Timestamp", "TopicArn", "Type"),
    "SubscriptionConfirmation": (
        "Message",
        "MessageId",
        "SubscribeURL",
        "Timestamp",
        "Token",
        "TopicArn",
        "Type",
    ),
    "UnsubscribeConfirmation": (
        "Message",
        "MessageId",
        "SubscribeURL",
        "Timestamp",
        "Token",
        "TopicArn",
        "Type",
    ),
}


class SnsError(Exception):
    """The SNS envelope is not genuine or not usable."""


def aws_url(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme == "https" and bool(_SNS_HOST.match(parts.hostname or ""))


def canonical(data: dict[str, Any]) -> bytes:
    fields = _FIELDS.get(str(data.get("Type")))
    if fields is None:
        raise SnsError("Unknown SNS message type")
    return "".join(f"{k}\n{data[k]}\n" for k in fields if k in data).encode()


async def _cert(client: httpx.AsyncClient, url: str) -> x509.Certificate:
    if url in _CERTS:
        return _CERTS[url]
    if not aws_url(url) or not urlsplit(url).path.endswith(".pem"):
        raise SnsError("The signing certificate is not on an Amazon SNS host")
    try:
        resp = await client.get(url, timeout=10)
        resp.raise_for_status()
        cert = x509.load_pem_x509_certificate(resp.content)
    except (httpx.HTTPError, ValueError) as exc:
        raise SnsError("The SNS signing certificate could not be loaded") from exc
    _CERTS[url] = cert
    return cert


async def verify(client: httpx.AsyncClient, data: dict[str, Any]) -> None:
    """Raise :class:`SnsError` unless the message is signed by Amazon SNS."""
    version = str(data.get("SignatureVersion", "1"))
    algorithm: hashes.HashAlgorithm = hashes.SHA256() if version == "2" else hashes.SHA1()  # noqa: S303 SNS v1 is SHA1
    cert = await _cert(client, str(data.get("SigningCertURL", "")))
    key = cert.public_key()
    if not isinstance(key, rsa.RSAPublicKey):
        raise SnsError("Unexpected SNS key type")
    try:
        key.verify(
            base64.b64decode(str(data.get("Signature", ""))),
            canonical(data),
            padding.PKCS1v15(),
            algorithm,
        )
    except (InvalidSignature, ValueError) as exc:
        raise SnsError("The SNS signature is invalid") from exc


async def confirm(client: httpx.AsyncClient, data: dict[str, Any]) -> None:
    url = str(data.get("SubscribeURL", ""))
    if not aws_url(url):
        raise SnsError("The subscription link is not on an Amazon SNS host")
    try:
        (await client.get(url, timeout=10)).raise_for_status()
    except httpx.HTTPError as exc:
        raise SnsError("Confirming the SNS subscription failed") from exc
