"""The email channel.

Inbound: a mail provider posts the raw RFC 822 message to
``/api/v1/channels/email/inbound/<token>`` (SES receipt rules through SNS, Mailgun and
Postmark "raw" forwarding, or the ``scripts/send-test-email.sh`` helper locally). The
message joins an existing conversation when it was sent to that conversation's reply
address (``<local>+<reply token>@<domain>``) or replies to one of its messages
(``In-Reply-To``/``References``); otherwise it opens a new conversation. Automatic mail
(out-of-office, bounces, lists) and our own messages are ignored, so two auto-responders
cannot loop.

Outbound: the ``mail.reply`` job sends an agent's or the AI's reply with a ``Message-ID``,
``In-Reply-To`` and ``References`` that keep the customer's mail client threading, and a
``Reply-To`` carrying the conversation's token.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import re
import secrets
import uuid
from dataclasses import dataclass, field
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses, parseaddr

import orjson
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from supportdesk.channels.models import Inbox
from supportdesk.core import jobs
from supportdesk.core.container import Container
from supportdesk.core.mail import MailError, send
from supportdesk.customers.service import contact_address, find_or_create
from supportdesk.tickets import service as tickets
from supportdesk.tickets.models import Attachment, Message, Ticket

MAX_ATTACHMENTS = 10
_QUOTE_MARKERS = [
    re.compile(r"^On .{5,200} wrote:\s*$", re.M),
    re.compile(r"^-{2,}\s*Original Message\s*-{2,}", re.M | re.I),
    re.compile(r"^From: .+$\n^(Sent|Date): .+$", re.M),
    re.compile(r"^_{10,}\s*$", re.M),
]


class InboundError(Exception):
    """The posted message cannot be used (malformed, or not for us)."""


@dataclass
class ParsedMail:
    from_email: str
    from_name: str | None
    subject: str
    text: str
    message_id: str | None
    references: list[str]
    recipients: list[str]
    automatic: bool
    attachments: list[tuple[str, str, bytes]] = field(default_factory=list)


def strip_quoted(text: str) -> str:
    """The customer's new text, without the quoted history mail clients append."""
    cut = len(text)
    for marker in _QUOTE_MARKERS:
        match = marker.search(text)
        if match and match.start() < cut:
            cut = match.start()
    lines = [line for line in text[:cut].splitlines() if not line.startswith(">")]
    return "\n".join(lines).strip()


def _text_of(msg: EmailMessage) -> str:
    body = msg.get_body(preferencelist=("plain", "html"))
    if body is None:
        return ""
    content = body.get_content()
    if body.get_content_type() == "text/html":
        from bs4 import BeautifulSoup

        content = BeautifulSoup(content, "html.parser").get_text("\n")
    return str(content)


def parse(raw: bytes) -> ParsedMail:
    try:
        msg = BytesParser(policy=policy.default).parsebytes(raw)
    except Exception as exc:
        raise InboundError("The email could not be parsed") from exc
    assert isinstance(msg, EmailMessage)
    name, address = parseaddr(str(msg.get("from", "")))
    if "@" not in address:
        raise InboundError("The email has no sender address")
    auto_submitted = str(msg.get("auto-submitted", "no")).lower()
    precedence = str(msg.get("precedence", "")).lower()
    automatic = (
        auto_submitted not in ("", "no")
        or precedence in ("bulk", "list", "junk", "auto_reply")
        or msg.get("x-autoreply") is not None
        or msg.get("x-autorespond") is not None
        or msg.get("list-id") is not None
        or address.lower().startswith(("mailer-daemon@", "postmaster@", "no-reply@", "noreply@"))
    )
    refs: list[str] = []
    for header in ("in-reply-to", "references"):
        refs.extend(re.findall(r"<[^>]+>", str(msg.get(header, ""))))
    # Only headers that are present: Python 3.12's strict getaddresses refuses the whole
    # list when empty values are joined in, which would lose every recipient.
    present = [str(v) for h in ("to", "cc", "delivered-to", "x-original-to") if (v := msg.get(h))]
    recipients = [a.lower() for _, a in getaddresses(present) if a]
    attachments: list[tuple[str, str, bytes]] = []
    for part in msg.iter_attachments():
        if len(attachments) >= MAX_ATTACHMENTS:
            break
        payload = part.get_payload(decode=True)
        if isinstance(payload, bytes):
            attachments.append(
                (part.get_filename() or "attachment", part.get_content_type(), payload)
            )
    text = strip_quoted(_text_of(msg)) or "(no text)"
    return ParsedMail(
        from_email=address.lower(),
        from_name=name or None,
        subject=str(msg.get("subject", "")).strip()[:300],
        text=text[:50_000],
        message_id=str(msg.get("message-id", "")).strip() or None,
        references=refs,
        recipients=recipients,
        automatic=automatic,
        attachments=attachments,
    )


def raw_from_request(body: bytes, content_type: str) -> bytes:
    """Accept the raw message, or an SNS notification wrapping an SES receipt."""
    if "json" not in content_type:
        return body
    try:
        data = orjson.loads(body)
    except orjson.JSONDecodeError as exc:
        raise InboundError("The JSON body could not be read") from exc
    if isinstance(data, dict) and data.get("Type") == "Notification":
        data = orjson.loads(data.get("Message") or "{}")
    content = data.get("content") if isinstance(data, dict) else None
    if not isinstance(content, str):
        raise InboundError(
            "The notification carries no message content (enable raw content in SES)"
        )
    try:
        return base64.b64decode(content)
    except ValueError:
        return content.encode()


async def raw_message(container: Container, body: bytes, content_type: str) -> bytes:
    """The RFC 822 message: inline, in the SNS envelope, or (mail over the 150 KB SNS limit)
    in the bucket's ``inbound/`` prefix, where the SES receipt rule stored it."""
    try:
        return raw_from_request(body, content_type)
    except InboundError:
        if "json" not in content_type:
            raise
    data = orjson.loads(body)
    if isinstance(data, dict) and data.get("Type") == "Notification":
        data = orjson.loads(data.get("Message") or "{}")
    action = (
        ((data or {}).get("receipt") or {}).get("action") or {} if isinstance(data, dict) else {}
    )
    key = action.get("objectKey") if isinstance(action, dict) else None
    if not isinstance(key, str) or not key.startswith("inbound/") or ".." in key:
        raise InboundError("The notification carries no message content and no stored copy")
    try:
        return await container.storage.get(key)
    except Exception as exc:
        raise InboundError("The stored copy of the message could not be read") from exc


def reply_address(container: Container, ticket: Ticket) -> str:
    local = container.settings.mail_from_address.split("@", 1)[0]
    return f"{local}+{ticket.reply_token}@{container.settings.mail_reply_domain}"


async def receive(container: Container, inbox: Inbox, raw: bytes) -> tuple[str, uuid.UUID | None]:
    """Store an inbound email. Returns ("ignored"|"new"|"reply", ticket id)."""
    # Parsing (MIME, HTML to text) can take a while on a large message: off the event loop.
    mail = await asyncio.to_thread(parse, raw)
    own = container.settings.mail_from_address.lower()
    if mail.automatic or mail.from_email == own:
        return "ignored", None
    async with container.db.sessionmaker() as session:
        if mail.message_id:
            duplicate = await session.scalar(
                select(Message.ticket_id).where(
                    Message.org_id == inbox.org_id, Message.email_message_id == mail.message_id
                )
            )
            if duplicate is not None:
                return "ignored", duplicate  # providers retry deliveries
        ticket: Ticket | None = None
        for recipient in mail.recipients:
            match = re.search(r"\+([0-9a-f]{24})@", recipient)
            if match:
                ticket = await session.scalar(
                    select(Ticket).where(
                        Ticket.org_id == inbox.org_id, Ticket.reply_token == match.group(1)
                    )
                )
                if ticket:
                    break
        if ticket is None and mail.references:
            ticket_id = await session.scalar(
                select(Message.ticket_id).where(
                    Message.org_id == inbox.org_id, Message.email_message_id.in_(mail.references)
                )
            )
            ticket = await session.get(Ticket, ticket_id) if ticket_id else None
        customer = await find_or_create(
            session, inbox.org_id, email=mail.from_email, name=mail.from_name
        )
        if ticket is not None and ticket.customer_id == customer.id:
            message = await tickets.add_customer_message(
                session, ticket, customer, mail.text, email_message_id=mail.message_id
            )
            outcome = "reply"
        else:
            subject = re.sub(r"^\s*(re|fwd?|aw):\s*", "", mail.subject, flags=re.I) or None
            ticket, message = await tickets.open_ticket(
                session,
                inbox,
                customer,
                mail.text,
                subject=subject,
                email_message_id=mail.message_id,
            )
            outcome = "new"
        for filename, content_type, data in mail.attachments:
            if len(data) > container.settings.max_attachment_bytes:
                continue
            digest = hashlib.sha256(data).hexdigest()
            key = f"orgs/{inbox.org_id}/attachments/{ticket.id}/{digest}"
            await container.storage.put(key, data, content_type)
            session.add(
                Attachment(
                    org_id=inbox.org_id,
                    ticket_id=ticket.id,
                    message_id=message.id,
                    filename=filename[:255],
                    content_type=content_type[:120],
                    size=len(data),
                    sha256=digest,
                    storage_key=key,
                )
            )
        from supportdesk.core.events import commit

        try:
            await commit(container, session)
        except IntegrityError:
            # A provider retry raced this delivery and stored the same Message-ID first.
            await session.rollback()
            return "ignored", None
        return outcome, ticket.id


@jobs.handles(tickets.MAIL_REPLY)
async def send_reply(ctx: jobs.JobContext) -> None:
    container = ctx.container
    message_id = uuid.UUID(ctx.payload["message_id"])
    async with container.db.sessionmaker() as session:
        message = await session.get(Message, message_id)
        if message is None or message.status != "sent" or message.delivery.get("email") == "sent":
            return
        ticket = await session.get(Ticket, message.ticket_id)
        assert ticket is not None
        from supportdesk.customers.models import Customer
        from supportdesk.org.service import load_settings

        customer = await session.get(Customer, ticket.customer_id)
        address = contact_address(customer) if customer is not None else None
        if customer is None or not address:
            message.delivery = {**message.delivery, "email": "no_address"}
            await session.commit()
            return
        bundle = await load_settings(session, ticket.org_id)
        refs: list[str] = [
            r
            for r in list(
                (
                    await session.scalars(
                        select(Message.email_message_id)
                        .where(
                            Message.ticket_id == ticket.id, Message.email_message_id.is_not(None)
                        )
                        .order_by(Message.created_at)
                    )
                ).all()
            )
            if r
        ]
        own_id: str = (
            message.email_message_id
            or f"<{secrets.token_hex(12)}@{container.settings.mail_reply_domain}>"
        )
        message.email_message_id = own_id
        await session.commit()
    headers = {"Message-ID": own_id, "Reply-To": reply_address(container, ticket)}
    if message.author_type == "ai":
        # RFC 3834: automatic replies say so, so other auto-responders do not answer them.
        headers["Auto-Submitted"] = "auto-replied"
    if refs:
        headers["In-Reply-To"] = refs[-1]
        headers["References"] = " ".join(r for r in refs[-10:] if r)
    company = bundle.brand.company_name
    text = (
        f"{message.body}\n\n--\n{company} Support\n"
        f"Reply to this email to continue the conversation (#{ticket.number})."
    )
    try:
        await send(
            container.settings,
            address,
            f"Re: [#{ticket.number}] {ticket.subject}",
            text,
            headers=headers,
            from_name=f"{company} Support",
        )
    except MailError as exc:
        if not ctx.last_attempt:
            raise jobs.RetryLaterError(str(exc)) from exc
        status = "failed"
    else:
        status = "sent"
    async with ctx.fenced() as session:
        row = await session.get(Message, message_id)
        if row is not None:
            row.delivery = {**row.delivery, "email": status}
