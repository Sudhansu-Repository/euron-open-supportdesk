from __future__ import annotations

from fastapi import APIRouter, Request, Response
from redis.exceptions import RedisError

from supportdesk.audit.service import Actor, audit
from supportdesk.auth import service
from supportdesk.auth.dependencies import (
    SESSION_COOKIE,
    CurrentUser,
    current_user,
    revoke,
    session_token,
)
from supportdesk.auth.schemas import (
    AcceptInvitation,
    InvitationPreview,
    LoginRequest,
    PasswordChange,
    SignInOut,
    SignupRequest,
    UserOut,
)
from supportdesk.core.deps import ContainerDep, SessionDep, client_ip
from supportdesk.core.errors import AuthenticationError, RateLimitedError
from supportdesk.core.schemas import Ack, ApiModel
from supportdesk.core.security import decode_session, issue_session
from supportdesk.limits.limiter import LimitDecision
from supportdesk.org.models import Org
from supportdesk.users.models import User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


async def _throttle(container: ContainerDep, key: str, rpm: int, message: str) -> None:
    try:
        decision = await container.kv.hit(key, rpm)
    except (RedisError, OSError):
        # Throttling is a convenience; lockout lives in Postgres and still applies.
        decision = LimitDecision(allowed=True)
    if not decision.allowed:
        raise RateLimitedError(message, headers={"retry-after": str(decision.retry_after_s)})


async def _session(
    response: Response, container: ContainerDep, session: SessionDep, user: User
) -> SignInOut:
    settings = container.settings
    token = issue_session(
        user.id,
        user.role,
        user.session_version,
        settings.session_secret,
        settings.session_ttl_hours,
    )
    ttl = settings.session_ttl_hours * 3600
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=ttl,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )
    response.headers["cache-control"] = "no-store"
    org = await session.get(Org, user.org_id)
    return SignInOut(
        user=UserOut.model_validate(user),
        org_slug=org.slug if org else "",
        session_token=token,
        expires_in_s=ttl,
    )


@router.post("/login", response_model=SignInOut, summary="Sign in as an agent")
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    container: ContainerDep,
    session: SessionDep,
) -> SignInOut:
    ip = client_ip(request)
    await _throttle(
        container,
        f"login:{ip}",
        container.settings.login_rpm,
        "Too many sign-in attempts from this address. Wait a minute and try again",
    )
    user = await service.authenticate(session, container.settings, body.email, body.password, ip)
    return await _session(response, container, session, user)


@router.post(
    "/signup",
    response_model=SignInOut,
    status_code=201,
    summary="Create an organisation and its owner account",
)
async def signup(
    body: SignupRequest,
    request: Request,
    response: Response,
    container: ContainerDep,
    session: SessionDep,
) -> SignInOut:
    ip = client_ip(request)
    await _throttle(
        container,
        f"signup:{ip}",
        container.settings.signup_rpm,
        "Too many sign-ups from this address. Wait a minute",
    )
    user, _ = await service.signup(
        session, container.settings, body.org_name, body.name, body.email, body.password, ip
    )
    return await _session(response, container, session, user)


class SignupStatus(ApiModel):
    signup_enabled: bool


@router.get("/signup", response_model=SignupStatus, summary="Whether new organisations may sign up")
async def signup_status(container: ContainerDep) -> SignupStatus:
    return SignupStatus(signup_enabled=container.settings.signup_enabled)


@router.get(
    "/invitations/{token}", response_model=InvitationPreview, summary="Who an invitation is for"
)
async def preview_invitation(
    token: str, container: ContainerDep, session: SessionDep
) -> InvitationPreview:
    invitation = await service.find_invitation(session, container.settings, token)
    org = await session.get(Org, invitation.org_id)
    return InvitationPreview(
        email=invitation.email, role=invitation.role, org_name=org.name if org else ""
    )


@router.post(
    "/invitations/accept", response_model=SignInOut, status_code=201, summary="Accept an invitation"
)
async def accept_invitation(
    body: AcceptInvitation,
    request: Request,
    response: Response,
    container: ContainerDep,
    session: SessionDep,
) -> SignInOut:
    ip = client_ip(request)
    await _throttle(
        container, f"accept:{ip}", container.settings.signup_rpm, "Too many attempts. Wait a minute"
    )
    user = await service.accept(
        session, container.settings, body.token, body.name, body.password, ip
    )
    return await _session(response, container, session, user)


@router.post("/logout", response_model=Ack, summary="Sign out")
async def logout(
    request: Request, response: Response, container: ContainerDep, session: SessionDep
) -> Ack:
    """Ends this session server-side too: the token is refused until it expires."""
    token, _ = session_token(request)
    claims = decode_session(token, container.settings.session_secret) if token else None
    if claims is not None:
        await revoke(session, claims)
        user = await session.get(User, claims.user_id)
        if user is not None:
            audit(
                session,
                Actor(user.org_id, user.id, user.email, user.role, client_ip(request)),
                "auth.logout",
                "user",
                user.id,
            )
        await session.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return Ack(message="Signed out")


class SessionOut(ApiModel):
    user: UserOut | None
    org_slug: str | None = None
    org_name: str | None = None


@router.get("/session", response_model=SessionOut, summary="Who is signed in, if anyone")
async def current_session(
    request: Request, container: ContainerDep, session: SessionDep
) -> SessionOut:
    if not session_token(request)[0]:
        return SessionOut(user=None)
    try:
        user = await current_user(request, container, session)
    except AuthenticationError:
        return SessionOut(user=None)
    org = await session.get(Org, user.org_id)
    return SessionOut(
        user=UserOut.model_validate(user),
        org_slug=org.slug if org else None,
        org_name=org.name if org else None,
    )


@router.get("/me", response_model=UserOut, summary="The signed-in agent")
async def me(user: CurrentUser) -> User:
    return user


@router.post("/password", response_model=SignInOut, summary="Change your password")
async def password(
    body: PasswordChange,
    request: Request,
    response: Response,
    user: CurrentUser,
    container: ContainerDep,
    session: SessionDep,
) -> SignInOut:
    actor: Actor = request.state.actor
    user = await service.change_password(
        session, user, body.current_password, body.new_password, actor
    )
    return await _session(response, container, session, user)
