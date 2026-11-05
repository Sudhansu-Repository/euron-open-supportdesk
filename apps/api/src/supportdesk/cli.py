"""The ``supportdesk`` command: every service and admin task in one entry point."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from supportdesk.core.config import Settings


def _settings() -> Settings:
    from supportdesk.core.config import get_settings

    return get_settings()


def _uvicorn(target: str, args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run(
        target,
        factory=True,
        host=args.host,
        port=args.port,
        workers=1,  # one process per container: metrics and in-process state stay exact
        proxy_headers=True,
        # Only trust X-Forwarded-For from the load balancer's network (the VPC CIDR on AWS).
        forwarded_allow_ips=os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1"),
        access_log=False,
        log_config=None,
        timeout_graceful_shutdown=30,
        # Above the load balancer's idle timeout, or a reused connection can be closed by
        # the API just as the load balancer sends on it (502s). Terraform sets 310.
        timeout_keep_alive=_settings().http_keep_alive_s,
    )


def _serve(args: argparse.Namespace) -> None:
    _uvicorn("supportdesk.main:create_app", args)


def _worker(_: argparse.Namespace) -> None:
    from supportdesk.worker import main

    asyncio.run(main())


def _migrate(_: argparse.Namespace) -> None:
    from supportdesk.core.config import get_settings
    from supportdesk.migrations.runner import upgrade

    upgrade(get_settings().database_url)
    print("migrations applied")


def _revision(args: argparse.Namespace) -> None:
    from supportdesk.core.config import get_settings
    from supportdesk.migrations.runner import revision

    revision(get_settings().database_url, args.message)


async def _create_owner(email: str, name: str, org_name: str, password: str) -> None:
    from sqlalchemy import func, select

    from supportdesk.core.config import get_settings
    from supportdesk.core.db import Database, import_all_models
    from supportdesk.core.security import hash_password, password_problems
    from supportdesk.users.models import User

    if problems := password_problems(password):
        sys.exit("password needs " + ", ".join(problems))
    import_all_models()
    settings = get_settings()
    db = Database(settings.database_url, pool_size=1, max_overflow=0)
    try:
        async with db.sessionmaker() as session:
            existing = await session.scalar(
                select(User).where(func.lower(User.email) == email.lower())
            )
            if existing:
                existing.role = "owner"
                existing.password_hash = hash_password(password)
                existing.disabled = False
                existing.session_version += 1
                await session.commit()
                print(f"updated {email} (owner)")
                return
        async with db.sessionmaker() as session:
            from supportdesk.auth.service import signup

            await signup(
                session,
                settings.model_copy(update={"signup_enabled": True}),
                org_name,
                name,
                email,
                password,
                None,
            )
            print(f"created {email} (owner of {org_name})")
    finally:
        await db.dispose()


def _owner(args: argparse.Namespace) -> None:
    password = os.environ.get("SUPPORTDESK_OWNER_PASSWORD") or getpass.getpass("Password: ")
    asyncio.run(_create_owner(args.email, args.name, args.org, password))


def _seed(args: argparse.Namespace) -> None:
    from supportdesk.demo.seed import run

    asyncio.run(run())


def _openapi(_: argparse.Namespace) -> None:
    from supportdesk.openapi import spec, to_yaml

    sys.stdout.write(to_yaml(spec()))


def _server(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], name: str, fn: object, help_: str
) -> None:
    p = sub.add_parser(name, help=help_)
    p.add_argument("--host", default="0.0.0.0")  # noqa: S104 containers listen on all interfaces
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    p.set_defaults(fn=fn)


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(prog="supportdesk", description="Euron Open SupportDesk")
    sub = parser.add_subparsers(dest="command", required=True)
    _server(sub, "serve", _serve, "the API")
    sub.add_parser(
        "worker", help="background jobs: AI turns, indexing, email, webhooks, SLA, rollups"
    ).set_defaults(fn=_worker)
    sub.add_parser("migrate", help="apply database migrations").set_defaults(fn=_migrate)
    p = sub.add_parser("revision", help="autogenerate a migration from the models")
    p.add_argument("-m", "--message", required=True)
    p.set_defaults(fn=_revision)
    p = sub.add_parser(
        "create-owner", help="create an organisation and its owner, or reset an owner"
    )
    p.add_argument("--email", required=True)
    p.add_argument("--name", default="Owner")
    p.add_argument("--org", default="My Company")
    p.set_defaults(fn=_owner)
    sub.add_parser(
        "seed-demo", help="a demo company with agents, knowledge, conversations and history"
    ).set_defaults(fn=_seed)
    sub.add_parser("openapi", help="print the OpenAPI document as YAML").set_defaults(fn=_openapi)
    args = parser.parse_args(argv)
    args.fn(args)
