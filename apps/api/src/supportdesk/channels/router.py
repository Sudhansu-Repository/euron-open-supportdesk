"""Inbox settings (agents), and the customer-facing channels: widget, inbound email, portal.

The widget and portal endpoints are public and called from customers' browsers: every one
checks a visitor or portal token, bodies are small, and sending is rate limited.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

import orjson
from fastapi import APIRouter, Header, Request
from pydantic import Field
from sqlalchemy import func, select

from supportdesk.auth.dependencies import Admin, Agent
from supportdesk.channels import email as email_channel
from supportdesk.channels import portal, sns
from supportdesk.channels import service as channels
from supportdesk.channels.models import Inbox
from supportdesk.core.db import OrgScope
from supportdesk.core.deps import ContainerDep, SessionDep, client_ip
from supportdesk.core.errors import AppError, AuthenticationError, NotFoundError, RateLimitedError
from supportdesk.core.events import commit
from supportdesk.core.schemas import Ack, ApiModel, Email
from supportdesk.core.security import constant_time_equals, hash_key_secret
from supportdesk.customers.models import Customer
from supportdesk.customers.service import contact_address, find_or_create, get_token_customer
from supportdesk.org.service import load_settings
from supportdesk.tickets import queries
from supportdesk.tickets import service as tickets
from supportdesk.tickets.models import Message, Ticket
from supportdesk.tickets.schemas import PortalTicket, PortalTicketDetail, PublicMessage
from supportdesk.users.models import User

router = APIRouter(prefix="/api/v1", tags=["channels"])
public = APIRouter(prefix="/api/v1", tags=["widget and portal (public)"])


class InboxOut(ApiModel):
    id: uuid.UUID
    name: str
    channel: str
    public_key: str | None
    allowed_origins: list[str]
    appearance: dict[str, Any]
    identity_required: bool
    identity_secret_set: bool
    email_address: str | None
    inbound_configured: bool
    team_id: uuid.UUID | None
    ai_enabled: bool
    active: bool
    snippet: str | None = None
    inbound_url: str | None = None


class InboxIn(ApiModel):
    name: str = Field(min_length=1, max_length=80)
    channel: str


class InboxPatch(ApiModel):
    name: str | None = Field(None, min_length=1, max_length=80)
    allowed_origins: list[str] | None = Field(None, max_length=50)
    appearance: dict[str, Any] | None = None
    identity_required: bool | None = None
    email_address: Email | None = None
    team_id: uuid.UUID | None = None
    ai_enabled: bool | None = None
    active: bool | None = None
    rotate_identity_secret: bool = False
    rotate_inbound_token: bool = False


class InboxSaved(ApiModel):
    inbox: InboxOut
    secret: str | None = Field(None, description="A newly generated secret or token, shown once")


def inbox_out(container: Any, inbox: Inbox) -> InboxOut:
    s = container.settings
    snippet = None
    if inbox.channel == "widget" and inbox.public_key:
        snippet = (
            f'<script src="{s.public_url}/widget.js" data-key="{inbox.public_key}" '
            f'data-api="{s.public_api_url}" async></script>'
        )
    return InboxOut(
        id=inbox.id,
        name=inbox.name,
        channel=inbox.channel,
        public_key=inbox.public_key,
        allowed_origins=inbox.allowed_origins,
        appearance=inbox.appearance,
        identity_required=inbox.identity_required,
        identity_secret_set=inbox.identity_secret_sealed is not None,
        email_address=inbox.email_address,
        inbound_configured=inbox.inbound_secret_hash is not None,
        team_id=inbox.team_id,
        ai_enabled=inbox.ai_enabled,
        active=inbox.active,
        snippet=snippet,
        inbound_url=f"{s.public_api_url}/api/v1/channels/email/inbound/<token>"
        if inbox.channel == "email"
        else None,
    )


@router.get("/inboxes", response_model=list[InboxOut], summary="Inboxes")
async def list_inboxes(
    actor: Agent, session: SessionDep, container: ContainerDep
) -> list[InboxOut]:
    rows = (
        await session.scalars(
            select(Inbox).where(Inbox.org_id == actor.org_id).order_by(Inbox.created_at)
        )
    ).all()
    return [inbox_out(container, i) for i in rows]


@router.post("/inboxes", response_model=InboxOut, status_code=201, summary="Add an inbox")
async def create_inbox(
    body: InboxIn, actor: Admin, session: SessionDep, container: ContainerDep
) -> InboxOut:
    return inbox_out(
        container, await channels.create_inbox(session, actor, body.name, body.channel)
    )


@router.patch("/inboxes/{inbox_id}", response_model=InboxSaved, summary="Change an inbox")
async def update_inbox(
    inbox_id: uuid.UUID,
    body: InboxPatch,
    actor: Admin,
    session: SessionDep,
    container: ContainerDep,
) -> InboxSaved:
    data = body.model_dump(exclude_unset=True)
    inbox, secret = await channels.update_inbox(container, session, actor, inbox_id, data)
    return InboxSaved(inbox=inbox_out(container, inbox), secret=secret)


# ----- website widget (public) -----


class WidgetSessionIn(ApiModel):
    token: str | None = Field(
        None, max_length=2000, description="A visitor token from an earlier session"
    )
    external_id: str | None = Field(None, max_length=200)
    email: Email | None = None
    name: str | None = Field(None, max_length=200)
    signature: str | None = Field(
        None, max_length=128, description="HMAC-SHA256(identity secret, external_id)"
    )
    parent_origin: str | None = Field(
        None, max_length=300, description="The site embedding the widget"
    )


class WidgetConfig(ApiModel):
    title: str
    greeting: str
    color: str
    position: str
    suggestions: list[str]
    launcher_label: str
    company: str
    agents_online: bool
    ai_enabled: bool


class WidgetSessionOut(ApiModel):
    token: str
    customer_name: str
    customer_email: str | None
    config: WidgetConfig
    ticket_id: uuid.UUID | None


class WidgetMessageIn(ApiModel):
    body: str = Field(min_length=1, max_length=5000)
    ticket_id: uuid.UUID | None = None


class WidgetConversation(ApiModel):
    ticket_id: uuid.UUID
    number: int
    status: str
    handled_by: str
    agents_online: bool
    messages: list[PublicMessage]


class FeedbackIn(ApiModel):
    helpful: bool


class RatingIn(ApiModel):
    score: int = Field(ge=1, le=5)
    comment: str | None = Field(None, max_length=2000)


class EmailIn(ApiModel):
    email: Email
    name: str | None = Field(None, max_length=200)


async def _agents_online(session: SessionDep, org_id: uuid.UUID) -> bool:
    count = await session.scalar(
        select(func.count())
        .select_from(User)
        .where(User.org_id == org_id, User.availability == "online", User.disabled.is_(False))
    )
    return bool(count)


async def _config(session: SessionDep, inbox: Inbox) -> WidgetConfig:
    bundle = await load_settings(session, inbox.org_id)
    a = {**channels.DEFAULT_APPEARANCE, **inbox.appearance}
    return WidgetConfig(
        title=str(a["title"]),
        greeting=str(a["greeting"]),
        color=str(a["color"]),
        position=str(a["position"]),
        suggestions=[str(x) for x in a.get("suggestions") or []][:6],
        launcher_label=str(a["launcher_label"]),
        company=bundle.brand.company_name,
        agents_online=await _agents_online(session, inbox.org_id),
        ai_enabled=inbox.ai_enabled and bundle.policy.mode != "off",
    )


async def _visitor(
    request: Request, container: ContainerDep, session: SessionDep, authorization: str | None
) -> tuple[Inbox, Customer]:
    token = (
        authorization[7:] if authorization and authorization.lower().startswith("bearer ") else None
    )
    org_id, inbox_id, customer_id = channels.read_visitor(container, token)
    inbox = await session.get(Inbox, inbox_id)
    if inbox is None or not inbox.active or inbox.org_id != org_id:
        raise AuthenticationError("This chat is no longer available", code="visitor_expired")
    channels.check_origin(inbox, request.headers.get("origin"), container.settings.public_url)
    customer = await get_token_customer(session, OrgScope(org_id), customer_id)
    return inbox, customer


async def _latest_ticket(session: SessionDep, inbox: Inbox, customer: Customer) -> Ticket | None:
    return await session.scalar(
        select(Ticket)
        .where(
            Ticket.org_id == inbox.org_id,
            Ticket.customer_id == customer.id,
            Ticket.inbox_id == inbox.id,
        )
        .order_by(Ticket.last_message_at.desc())
        .limit(1)
    )


async def _limit(container: ContainerDep, key: str, rpm: int) -> None:
    try:
        decision = await container.kv.hit(key, rpm)
    except Exception:
        return  # throttling is best effort while the cache is down
    if not decision.allowed:
        raise RateLimitedError(
            "You are sending messages too quickly. Wait a moment",
            headers={"retry-after": str(decision.retry_after_s)},
        )


@public.post(
    "/widget/{public_key}/session",
    response_model=WidgetSessionOut,
    summary="Start or resume a chat",
)
async def widget_session(
    public_key: str,
    body: WidgetSessionIn,
    request: Request,
    container: ContainerDep,
    session: SessionDep,
) -> WidgetSessionOut:
    await _limit(container, f"wsess:{client_ip(request)}", container.settings.widget_rpm * 2)
    inbox = await channels.widget_inbox(session, public_key)
    channels.check_origin(inbox, request.headers.get("origin"), container.settings.public_url)
    if inbox.allowed_origins:
        # The browser enforces this through frame-ancestors too; checking here turns a
        # silently blocked frame into a clear message for the site owner.
        # The app's own help center embeds the widget too, so its origin always counts.
        channels.check_origin(inbox, body.parent_origin, container.settings.public_url)
    customer: Customer | None = None
    if body.token:
        try:
            org_id, inbox_id, customer_id = channels.read_visitor(container, body.token)
            if inbox_id == inbox.id:
                customer = await get_token_customer(session, OrgScope(org_id), customer_id)
        except (AuthenticationError, NotFoundError):
            customer = None
    verified = await channels.verify_identity(container, inbox, body.external_id, body.signature)
    if verified:
        identified = await find_or_create(
            session,
            inbox.org_id,
            external_id=body.external_id,
            email=body.email,
            name=body.name,
            verified_id_only=True,
        )
        customer = identified
    elif customer is None:
        customer = await find_or_create(session, inbox.org_id)
    await session.commit()
    latest = await _latest_ticket(session, inbox, customer)
    return WidgetSessionOut(
        token=channels.visitor_token(container, inbox, customer.id),
        customer_name=customer.name,
        customer_email=customer.email,
        config=await _config(session, inbox),
        ticket_id=latest.id if latest and latest.status not in ("closed",) else None,
    )


class FramePolicy(ApiModel):
    frame_ancestors: list[str]


@public.get(
    "/widget/{public_key}/frame-policy",
    response_model=FramePolicy,
    summary="Sites allowed to embed this widget (for the frame's CSP)",
)
async def frame_policy(public_key: str, session: SessionDep) -> FramePolicy:
    inbox = await channels.widget_inbox(session, public_key)
    return FramePolicy(frame_ancestors=channels.frame_ancestors(inbox))


async def _conversation(session: SessionDep, ticket: Ticket) -> WidgetConversation:
    full = await queries.detail(session, ticket, include_internal=False)
    return WidgetConversation(
        ticket_id=ticket.id,
        number=ticket.number,
        status=ticket.status,
        handled_by=ticket.handled_by,
        agents_online=await _agents_online(session, ticket.org_id),
        messages=queries.public_messages(full),
    )


async def _own_ticket(session: SessionDep, customer: Customer, ticket_id: uuid.UUID) -> Ticket:
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None or ticket.customer_id != customer.id:
        raise NotFoundError("Conversation not found", code="ticket_not_found")
    return ticket


@public.post(
    "/widget/messages", response_model=WidgetConversation, status_code=201, summary="Send a message"
)
async def widget_send(
    body: WidgetMessageIn,
    request: Request,
    container: ContainerDep,
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> WidgetConversation:
    inbox, customer = await _visitor(request, container, session, authorization)
    await _limit(container, f"wmsg:{customer.id}", container.settings.widget_rpm)
    await _limit(container, f"wmsg-ip:{client_ip(request)}", container.settings.widget_rpm * 3)
    ticket = await _own_ticket(session, customer, body.ticket_id) if body.ticket_id else None
    if ticket is None or ticket.status == "closed":
        ticket, _ = await tickets.open_ticket(session, inbox, customer, body.body)
    else:
        await session.refresh(ticket, with_for_update=True)
        await tickets.add_customer_message(session, ticket, customer, body.body)
    await commit(container, session)
    return await _conversation(session, ticket)


@public.get(
    "/widget/tickets/{ticket_id}",
    response_model=WidgetConversation,
    summary="The visitor's conversation",
)
async def widget_conversation(
    ticket_id: uuid.UUID,
    request: Request,
    container: ContainerDep,
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> WidgetConversation:
    _, customer = await _visitor(request, container, session, authorization)
    return await _conversation(session, await _own_ticket(session, customer, ticket_id))


@public.post(
    "/widget/tickets/{ticket_id}/human",
    response_model=WidgetConversation,
    summary="Ask for a person",
)
async def widget_human(
    ticket_id: uuid.UUID,
    request: Request,
    container: ContainerDep,
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> WidgetConversation:
    _, customer = await _visitor(request, container, session, authorization)
    ticket = await _own_ticket(session, customer, ticket_id)
    await session.refresh(ticket, with_for_update=True)
    if ticket.handled_by == "ai":
        from supportdesk.ai.pipeline import HANDOFF, HANDOFF_EMAIL
        from supportdesk.ai.policy import CUSTOMER_REQUESTED

        session.add(
            Message(
                org_id=ticket.org_id,
                ticket_id=ticket.id,
                author_type="system",
                kind="reply",
                status="sent",
                body=HANDOFF_EMAIL if contact_address(customer) else HANDOFF,
                ai_meta={"handoff": True, "reasons": [CUSTOMER_REQUESTED]},
            )
        )
        await tickets.escalate(session, ticket, [CUSTOMER_REQUESTED], actor_type="customer")
    await commit(container, session)
    return await _conversation(session, ticket)


@public.post(
    "/widget/messages/{message_id}/feedback", response_model=Ack, summary="Was this answer helpful?"
)
async def widget_feedback(
    message_id: uuid.UUID,
    body: FeedbackIn,
    request: Request,
    container: ContainerDep,
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> Ack:
    _, customer = await _visitor(request, container, session, authorization)
    await customer_feedback(container, session, customer, message_id, body.helpful)
    return Ack(message="Thanks for the feedback")


async def customer_feedback(
    container: Any, session: Any, customer: Customer, message_id: uuid.UUID, helpful: bool
) -> None:
    """Helpful: the conversation is resolved by the AI. Unhelpful: the answer leaves the
    cache, the question becomes a knowledge gap, and (per policy) a person takes over."""
    message = await session.get(Message, message_id)
    if message is None or message.author_type != "ai" or message.status != "sent":
        raise NotFoundError("Answer not found")
    ticket = await _own_ticket(session, customer, message.ticket_id)
    await session.refresh(ticket, with_for_update=True)
    if message.feedback is not None:
        return
    message.feedback = "helpful" if helpful else "unhelpful"
    latest_ai = await session.scalar(
        select(Message.id)
        .where(
            Message.ticket_id == ticket.id, Message.author_type == "ai", Message.status == "sent"
        )
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    if helpful:
        # Only the answer the AI is still standing on can resolve the conversation: a
        # thumbs-up on an old answer must not close a case people now own.
        if ticket.handled_by == "ai" and not ticket.pending_approval and latest_ai == message.id:
            await tickets.customer_resolves(session, ticket, customer)
    else:
        from supportdesk.ai import cache
        from supportdesk.ai.policy import UNHELPFUL
        from supportdesk.gaps.service import record_question

        question = await session.get(Message, message.reply_to_id) if message.reply_to_id else None
        bundle = await load_settings(session, ticket.org_id)
        if question is not None:
            await cache.disable(
                session,
                container.kv,
                ticket.org_id,
                bundle.org.kb_version,
                question.body,
                message.body,
            )
            await record_question(session, ticket, question, question.body, "unhelpful", None)
        unhelpful = await session.scalar(
            select(func.count())
            .select_from(Message)
            .where(
                Message.ticket_id == ticket.id,
                Message.author_type == "ai",
                Message.feedback == "unhelpful",
            )
        )
        if (
            ticket.handled_by == "ai"
            and bundle.policy.max_unhelpful
            and (unhelpful or 0) >= bundle.policy.max_unhelpful
        ):
            from supportdesk.ai.pipeline import HANDOFF, HANDOFF_EMAIL

            session.add(
                Message(
                    org_id=ticket.org_id,
                    ticket_id=ticket.id,
                    author_type="system",
                    kind="reply",
                    status="sent",
                    body=HANDOFF_EMAIL if contact_address(customer) else HANDOFF,
                    ai_meta={"handoff": True, "reasons": [UNHELPFUL]},
                )
            )
            await tickets.escalate(session, ticket, [UNHELPFUL], actor_type="customer")
        tickets.announce(session, ticket)
    await commit(container, session)


@public.post(
    "/widget/tickets/{ticket_id}/rating", response_model=Ack, summary="Rate the conversation"
)
async def widget_rate(
    ticket_id: uuid.UUID,
    body: RatingIn,
    request: Request,
    container: ContainerDep,
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> Ack:
    _, customer = await _visitor(request, container, session, authorization)
    ticket = await _own_ticket(session, customer, ticket_id)
    await tickets.rate(session, ticket, body.score, body.comment)
    await commit(container, session)
    return Ack(message="Thanks for rating us")


@public.post("/widget/email", response_model=Ack, summary="Leave an email for follow-up")
async def widget_email(
    body: EmailIn,
    request: Request,
    container: ContainerDep,
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> Ack:
    _, customer = await _visitor(request, container, session, authorization)
    # An address typed into the widget is not proof of identity: it is kept as a contact
    # for emailing replies, never matched against (or claimed from) other customers.
    customer.attributes = {**(customer.attributes or {}), "contact_email": body.email.lower()}
    if body.name and customer.name.startswith("Visitor "):
        customer.name = body.name
    await session.commit()
    return Ack(message="Thanks! We'll reply by email too")


# ----- inbound email (provider webhook) -----


class InboundOut(ApiModel):
    outcome: str
    ticket_id: uuid.UUID | None


@public.post(
    "/channels/email/inbound/{token}",
    response_model=InboundOut,
    summary="Receive an email (raw RFC 822)",
)
async def inbound_email(
    token: str, request: Request, container: ContainerDep, session: SessionDep
) -> InboundOut:
    token_hash = hash_key_secret(token, container.settings.token_pepper)
    inbox = await session.scalar(
        select(Inbox).where(Inbox.inbound_secret_hash == token_hash, Inbox.channel == "email")
    )
    if (
        inbox is None
        or not constant_time_equals(inbox.inbound_secret_hash or "", token_hash)
        or not inbox.active
    ):
        raise AuthenticationError("Unknown inbound email token", code="invalid_inbound_token")
    raw = await request.body()
    content_type = request.headers.get("content-type", "")
    if "json" in content_type or request.headers.get("x-amz-sns-message-type"):
        # An Amazon SNS envelope (SES inbound): check it is genuinely from SNS first.
        try:
            envelope = orjson.loads(raw)
            if not isinstance(envelope, dict):
                raise sns.SnsError("Not an SNS message")
            await sns.verify(container.http, envelope)
            if envelope.get("Type") == "SubscriptionConfirmation":
                await sns.confirm(container.http, envelope)
                return InboundOut(outcome="subscribed", ticket_id=None)
            if envelope.get("Type") != "Notification":
                return InboundOut(outcome="ignored", ticket_id=None)
        except (sns.SnsError, orjson.JSONDecodeError) as exc:
            raise AuthenticationError(str(exc), code="invalid_sns_message") from exc
    try:
        message = await email_channel.raw_message(container, raw, content_type)
        outcome, ticket_id = await email_channel.receive(container, inbox, message)
    except email_channel.InboundError as exc:
        raise AppError(str(exc), code="invalid_email") from exc
    return InboundOut(outcome=outcome, ticket_id=ticket_id)


# ----- customer portal (public) -----


class PortalLinkIn(ApiModel):
    email: Email


class PortalTokenIn(ApiModel):
    token: str = Field(min_length=10, max_length=200)


class PortalSessionOut(ApiModel):
    token: str
    customer_name: str
    customer_email: str | None


class PortalTicketIn(ApiModel):
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=20_000)


class PortalReplyIn(ApiModel):
    body: str = Field(min_length=1, max_length=20_000)


async def _portal_customer(
    container: Any, session: Any, slug: str, authorization: str | None
) -> tuple[Any, Customer]:
    org = await portal.org_by_slug(session, slug)
    token = (
        authorization[7:] if authorization and authorization.lower().startswith("bearer ") else None
    )
    org_id, customer_id = portal.read_portal(container, token)
    if org_id != org.id:
        raise AuthenticationError("Sign in again to see your tickets", code="portal_expired")
    return org, await get_token_customer(session, OrgScope(org.id), customer_id)


@public.post("/portal/{slug}/link", response_model=Ack, summary="Email me a sign-in link")
async def portal_link(
    slug: str, body: PortalLinkIn, request: Request, container: ContainerDep, session: SessionDep
) -> Ack:
    await _limit(container, f"plink:{client_ip(request)}", 5)
    await _limit(container, f"plink-email:{body.email}", 3)
    org = await portal.org_by_slug(session, slug)
    await portal.request_link(container, session, org, body.email)
    return Ack(message="If this address has conversations with us, a sign-in link is on its way")


@public.post(
    "/portal/{slug}/session", response_model=PortalSessionOut, summary="Redeem a sign-in link"
)
async def portal_session(
    slug: str, body: PortalTokenIn, container: ContainerDep, session: SessionDep
) -> PortalSessionOut:
    org = await portal.org_by_slug(session, slug)
    token, customer = await portal.redeem(container, session, org, body.token)
    return PortalSessionOut(token=token, customer_name=customer.name, customer_email=customer.email)


@public.get("/portal/{slug}/tickets", response_model=list[PortalTicket], summary="My conversations")
async def portal_tickets(
    slug: str,
    container: ContainerDep,
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> list[PortalTicket]:
    org, customer = await _portal_customer(container, session, slug, authorization)
    items, _ = await queries.list_tickets(
        session, OrgScope(org.id), customer_id=customer.id, limit=100
    )
    return [queries.portal_ticket(item) for item in items]


@public.post(
    "/portal/{slug}/tickets",
    response_model=PortalTicketDetail,
    status_code=201,
    summary="Open a ticket",
)
async def portal_create(
    slug: str,
    body: PortalTicketIn,
    request: Request,
    container: ContainerDep,
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> PortalTicketDetail:
    org, customer = await _portal_customer(container, session, slug, authorization)
    await _limit(container, f"pmsg:{customer.id}", 10)
    inbox = await channels.inbox_for_channel(session, org.id, "portal")
    ticket, _ = await tickets.open_ticket(session, inbox, customer, body.body, subject=body.subject)
    await commit(container, session)
    return await queries.portal_detail(session, ticket)


@public.get(
    "/portal/{slug}/tickets/{ticket_id}",
    response_model=PortalTicketDetail,
    summary="One of my conversations",
)
async def portal_ticket(
    slug: str,
    ticket_id: uuid.UUID,
    container: ContainerDep,
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> PortalTicketDetail:
    _, customer = await _portal_customer(container, session, slug, authorization)
    return await queries.portal_detail(session, await _own_ticket(session, customer, ticket_id))


@public.post(
    "/portal/{slug}/tickets/{ticket_id}/messages",
    response_model=PortalTicketDetail,
    summary="Reply",
)
async def portal_reply(
    slug: str,
    ticket_id: uuid.UUID,
    body: PortalReplyIn,
    container: ContainerDep,
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> PortalTicketDetail:
    _, customer = await _portal_customer(container, session, slug, authorization)
    await _limit(container, f"pmsg:{customer.id}", 10)
    ticket = await _own_ticket(session, customer, ticket_id)
    await session.refresh(ticket, with_for_update=True)
    await tickets.add_customer_message(session, ticket, customer, body.body)
    await commit(container, session)
    return await queries.portal_detail(session, ticket)


@public.post(
    "/portal/{slug}/messages/{message_id}/feedback",
    response_model=Ack,
    summary="Was this answer helpful?",
)
async def portal_feedback(
    slug: str,
    message_id: uuid.UUID,
    body: FeedbackIn,
    container: ContainerDep,
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> Ack:
    _, customer = await _portal_customer(container, session, slug, authorization)
    await customer_feedback(container, session, customer, message_id, body.helpful)
    return Ack(message="Thanks for the feedback")


@public.post(
    "/portal/{slug}/tickets/{ticket_id}/rating", response_model=Ack, summary="Rate a conversation"
)
async def portal_rate(
    slug: str,
    ticket_id: uuid.UUID,
    body: RatingIn,
    container: ContainerDep,
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> Ack:
    _, customer = await _portal_customer(container, session, slug, authorization)
    await tickets.rate(
        session, await _own_ticket(session, customer, ticket_id), body.score, body.comment
    )
    await commit(container, session)
    return Ack(message="Thanks for rating us")
