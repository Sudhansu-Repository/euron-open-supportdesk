"""Amazon SNS envelopes: only genuinely signed messages, only Amazon hosts."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID

from supportdesk.channels import sns

CERT_URL = "https://sns.us-east-1.amazonaws.com/SimpleNotificationService-test.pem"


def _keypair() -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "sns.amazonaws.com")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    return key, cert


def _signed(key: rsa.RSAPrivateKey, version: str = "2", **fields: str) -> dict[str, str]:
    data = {
        "Type": "Notification",
        "MessageId": "m-1",
        "TopicArn": "arn:aws:sns:us-east-1:000000000000:mail",
        "Message": '{"content": "x"}',
        "Timestamp": "2026-10-30T10:00:00Z",
        "SignatureVersion": version,
        "SigningCertURL": CERT_URL,
        **fields,
    }
    algorithm = hashes.SHA256() if version == "2" else hashes.SHA1()  # noqa: S303
    data["Signature"] = base64.b64encode(
        key.sign(sns.canonical(data), padding.PKCS1v15(), algorithm)
    ).decode()
    return data


@pytest.fixture
def key() -> rsa.RSAPrivateKey:
    private, cert = _keypair()
    sns._CERTS[CERT_URL] = cert
    yield private
    sns._CERTS.pop(CERT_URL, None)


@pytest.mark.parametrize("version", ["1", "2"])
async def test_a_genuine_message_verifies(key: rsa.RSAPrivateKey, version: str) -> None:
    async with httpx.AsyncClient() as client:
        await sns.verify(client, _signed(key, version))


async def test_a_tampered_message_is_refused(key: rsa.RSAPrivateKey) -> None:
    data = _signed(key)
    data["Message"] = '{"content": "injected"}'
    async with httpx.AsyncClient() as client:
        with pytest.raises(sns.SnsError, match="invalid"):
            await sns.verify(client, data)


async def test_certificates_and_links_must_be_on_amazon_hosts(key: rsa.RSAPrivateKey) -> None:
    async with httpx.AsyncClient() as client:
        with pytest.raises(sns.SnsError, match="Amazon"):
            await sns.verify(client, _signed(key, SigningCertURL="https://evil.example/cert.pem"))
        with pytest.raises(sns.SnsError, match="Amazon"):
            await sns.confirm(client, {"SubscribeURL": "http://169.254.169.254/latest"})
    assert sns.aws_url("https://sns.eu-west-1.amazonaws.com/?Action=ConfirmSubscription")
    assert not sns.aws_url("https://sns.eu-west-1.amazonaws.com.evil.example/")
    with pytest.raises(sns.SnsError):
        sns.canonical({"Type": "Strange"})
