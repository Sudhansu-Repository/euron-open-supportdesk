"""API application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from supportdesk import __version__
from supportdesk.analytics.router import router as analytics_router
from supportdesk.audit.router import router as audit_router
from supportdesk.auth.router import router as auth_router
from supportdesk.channels.router import public as channels_public
from supportdesk.channels.router import router as channels_router
from supportdesk.core.config import Settings, get_settings
from supportdesk.core.container import Container
from supportdesk.core.db import import_all_models
from supportdesk.core.errors import install_error_handlers
from supportdesk.core.logs import configure_logging
from supportdesk.core.middleware import BodySizeLimitMiddleware, RequestContextMiddleware
from supportdesk.core.tracing import configure_tracing
from supportdesk.customers.router import router as customers_router
from supportdesk.gaps.router import router as gaps_router
from supportdesk.integrations.router import router as integrations_router
from supportdesk.knowledge.router import public as help_public
from supportdesk.knowledge.router import router as knowledge_router
from supportdesk.org.router import router as org_router
from supportdesk.realtime.router import router as realtime_router
from supportdesk.system.router import router as system_router
from supportdesk.tickets.router import router as tickets_router
from supportdesk.users.router import router as users_router

DESCRIPTION = """
API of a self-hosted support desk whose AI agent answers from your own knowledge, hands
the rest to people with context, and records what every answer cost.

* Agents sign in with `POST /api/v1/auth/login` and send the session token as
  `Authorization: Bearer <token>` (the web app uses an HttpOnly cookie instead).
* Integrations use an API key from Settings > API keys: `Authorization: Bearer sdk_...`.
  Read keys list and read conversations, customers and articles; write keys also open
  conversations and reply.
* The website widget, the customer portal, the help center and inbound email are public
  endpoints, authenticated by visitor tokens, portal tokens and inbound tokens.
* Live updates: WebSockets at `/ws/agent`, `/ws/widget/{ticket_id}` and
  `/ws/portal/{ticket_id}` carry small "changed" events; fetch the data over REST.
* Webhooks are signed: `X-SupportDesk-Signature: t=<unix>,v1=<hex HMAC-SHA256 of t.body>`.
"""


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or get_settings()
    import_all_models()
    configure_logging(settings.log_level)
    configure_tracing(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.container = container or Container.build(settings)
        try:
            yield
        finally:
            if container is None:
                await app.state.container.close()

    app = FastAPI(
        title="Euron Open SupportDesk",
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
        separate_input_output_schemas=False,
    )
    install_error_handlers(app)
    for router in (
        auth_router,
        users_router,
        org_router,
        tickets_router,
        customers_router,
        channels_router,
        channels_public,
        knowledge_router,
        help_public,
        gaps_router,
        analytics_router,
        integrations_router,
        audit_router,
        system_router,
        realtime_router,
    ):
        app.include_router(router)

    app.add_middleware(GZipMiddleware, minimum_size=2048)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "authorization",
            "content-type",
            "x-supportdesk-csrf",
            "x-request-id",
        ],
        expose_headers=["x-request-id", "retry-after", "content-disposition"],
        max_age=600,
    )
    app.add_middleware(BodySizeLimitMiddleware, settings=settings)
    app.add_middleware(RequestContextMiddleware)
    return app
