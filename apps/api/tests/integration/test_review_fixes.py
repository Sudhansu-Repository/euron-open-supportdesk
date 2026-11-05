"""Regression tests for the independent production review (one per confirmed finding)."""

from __future__ import annotations

import hashlib
import hmac

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.integration.conftest import PASSWORD, Stack, eventually


async def _sql(stack: Stack, sql: str, **params: object) -> object:
    engine = create_async_engine(stack.settings.database_url)
    async with engine.begin() as conn:
        result = await conn.execute(text(sql), params)
        value = result.scalar() if result.returns_rows else None
    await engine.dispose()
    return value


async def test_a_verified_visitor_cannot_claim_another_customers_record_by_email(
    stack: Stack,
) -> None:
    org = await stack.org("Identity takeover")
    victim = await org.ok(
        "POST",
        "/api/v1/tickets",
        {"customer_email": "ceo@bigclient.com", "body": "Private"},
        status=201,
    )
    inboxes = await org.ok("GET", "/api/v1/inboxes")
    inbox = next(i for i in inboxes if i["channel"] == "widget")
    secret = (
        await org.ok("PATCH", f"/api/v1/inboxes/{inbox['id']}", {"rotate_identity_secret": True})
    )["secret"]
    signature = hmac.new(secret.encode(), b"u-999", hashlib.sha256).hexdigest()
    resp = await stack.client(origin="http://localhost:4810").post(
        f"/api/v1/widget/{inbox['public_key']}/session",
        json={"external_id": "u-999", "signature": signature, "email": "ceo@bigclient.com"},
    )
    assert resp.status_code == 200
    assert resp.json()["ticket_id"] is None  # not the CEO's conversation
    assert resp.json()["customer_email"] != "ceo@bigclient.com"
    profile = await org.ok("GET", f"/api/v1/customers/{victim['customer']['id']}")
    assert profile["external_id"] is None  # the victim's record was not rewritten


async def test_a_merged_customers_old_token_no_longer_works(stack: Stack) -> None:
    org = await stack.org("Merged tokens")
    real = await org.ok(
        "POST", "/api/v1/tickets", {"customer_email": "jane@corp.com", "body": "Mine"}, status=201
    )
    visitor = await org.visitor()
    conv = await visitor.say("hi I'm Jane, talk to a human", wait=False)
    duplicate = (await org.ticket(conv["ticket_id"]))["customer"]["id"]
    await org.ok(
        "POST", "/api/v1/customers/merge", {"keep_id": real["customer"]["id"], "drop_id": duplicate}
    )
    assert (await visitor.client.get(f"/api/v1/widget/tickets/{real['id']}")).status_code == 401
    resumed = await stack.client(origin="http://localhost:4810").post(
        f"/api/v1/widget/{await org.widget_key()}/session", json={"token": visitor.session["token"]}
    )
    assert resumed.json()["ticket_id"] != real["id"]


async def test_a_job_whose_worker_died_on_its_last_attempt_is_handed_over(stack: Stack) -> None:
    org = await stack.org("Dead jobs")
    await org.ok("PATCH", f"/api/v1/inboxes/{(await _widget(org))}", {"ai_enabled": False})
    visitor = await org.visitor()
    conv = await visitor.say("How long does shipping take?", wait=False)
    message_id = await _sql(
        stack, "SELECT id FROM messages WHERE ticket_id = :t", t=conv["ticket_id"]
    )
    await _sql(stack, "UPDATE tickets SET handled_by = 'ai' WHERE id = :t", t=conv["ticket_id"])
    await _sql(
        stack,
        "INSERT INTO jobs (id, org_id, kind, payload, status, attempts, max_attempts, run_after, lease_until, worker) "
        "SELECT gen_random_uuid(), org_id, 'ai.reply', jsonb_build_object('message_id', CAST(:m AS text)), 'running', "
        "3, 3, now(), now() - interval '1 second', 'oom-killed' FROM tickets WHERE id = :t",
        m=str(message_id),
        t=conv["ticket_id"],
    )
    await _sql(stack, "SELECT pg_notify('supportdesk_jobs', 'ai.reply')")
    reply = visitor.last(await visitor.wait_reply(30))
    assert reply["author_type"] == "system"  # handed to a person, never left unanswered
    ticket = await org.ticket(conv["ticket_id"])
    assert "ai_unavailable" in ticket["escalation_reasons"]
    status = await _sql(
        stack, "SELECT status FROM jobs WHERE payload->>'message_id' = :m", m=str(message_id)
    )
    assert status == "dead"


async def _widget(org: object) -> str:
    inboxes = await org.ok("GET", "/api/v1/inboxes")  # type: ignore[attr-defined]
    return str(next(i["id"] for i in inboxes if i["channel"] == "widget"))


async def test_greetings_respect_draft_mode_and_do_not_count_as_resolutions(stack: Stack) -> None:
    org = await stack.org("Smalltalk")
    await org.patch_settings(policy={"mode": "draft"})
    visitor = await org.visitor()
    conv = await visitor.say("hi")
    assert visitor.last(conv)["author_type"] == "system"  # no AI greeting in draft mode
    other = await stack.org("Smalltalk auto")
    v2 = await other.visitor()
    conv2 = await v2.say("hello")
    assert v2.last(conv2)["author_type"] == "ai"
    assert (await other.ticket(conv2["ticket_id"]))["first_response_at"] is None


async def test_customer_views_carry_no_internal_fields(stack: Stack) -> None:
    org = await stack.org("Whitelist")
    visitor = await org.visitor()
    conv = await visitor.say("This is the worst service ever, talk to a human now!")
    for field in ("summary", "escalation_reasons", "sentiment", "ai_cost_usd", "tags"):
        assert field not in conv
    for message in conv["messages"]:
        assert "ai_meta" not in message and "delivery" not in message and "author_id" not in message


async def test_an_answer_marked_unhelpful_is_never_served_from_cache_again(
    stack: Stack, mock: httpx.AsyncClient
) -> None:
    org = await stack.org("Sticky disable", provider="openai")
    await org.faq()
    first = await org.visitor()
    await first.say("How long does shipping take?")
    second = await org.visitor()
    answer = second.last(await second.say("how long does shipping take"))
    await second.client.post(
        f"/api/v1/widget/messages/{answer['id']}/feedback", json={"helpful": False}
    )
    third = await org.visitor()
    await third.say("How long does shipping take")
    cached = await _sql(
        stack,
        "SELECT count(*) FROM llm_calls JOIN orgs ON orgs.id = llm_calls.org_id "
        "WHERE orgs.slug = :s AND cache IS NOT NULL",
        s=org.slug,
    )
    assert cached == 1  # the second visitor's hit; the third was answered fresh


async def test_a_stale_thumbs_up_does_not_resolve_a_case_people_own(
    stack: Stack, mock: httpx.AsyncClient
) -> None:
    org = await stack.org("Stale vote", provider="openai")
    await org.faq()
    visitor = await org.visitor()
    answer = visitor.last(await visitor.say("How long does shipping take?"))
    await visitor.say("I want a refund for my order please")
    resp = await visitor.client.post(
        f"/api/v1/widget/messages/{answer['id']}/feedback", json={"helpful": True}
    )
    assert resp.status_code == 200
    assert (await org.ticket(str(visitor.ticket_id)))["status"] != "resolved"


async def test_an_owner_who_signed_in_before_is_not_locked_out_by_strangers(stack: Stack) -> None:
    from supportdesk.auth.service import PER_ACCOUNT, _key

    org = await stack.org("Owner lockout")
    first = await stack.client().post(
        "/api/v1/auth/login", json={"email": org.email, "password": PASSWORD}
    )
    assert first.status_code == 200  # the owner signs in from this address once
    pepper = stack.settings.token_pepper
    await _sql(
        stack,
        "INSERT INTO login_failures (key, failures, window_started_at, locked_until) "
        "VALUES (:k, :n, now(), now() + interval '15 minutes') ON CONFLICT (key) DO UPDATE SET "
        "failures = :n, locked_until = now() + interval '15 minutes'",
        k=_key(pepper, "acct", org.email.lower()),
        n=PER_ACCOUNT,
    )
    resp = await stack.client().post(
        "/api/v1/auth/login", json={"email": org.email, "password": PASSWORD}
    )
    assert resp.status_code == 200  # a known address is exempt from the account-wide lock


async def test_card_numbers_never_land_in_the_answer_cache(
    stack: Stack, mock: httpx.AsyncClient
) -> None:
    org = await stack.org("Redacted cache", provider="openai")
    await org.faq()
    visitor = await org.visitor()
    await visitor.say("How long does shipping take? my card is 4242 4242 4242 4242")

    async def stored() -> object:
        return await _sql(
            stack,
            "SELECT question FROM answer_cache JOIN orgs ON orgs.id = answer_cache.org_id "
            "WHERE orgs.slug = :s",
            s=org.slug,
        )

    question = await eventually(stored)
    assert "4242" not in str(question)


async def test_the_semantic_cache_never_answers_a_question_about_something_else(
    stack: Stack, mock: httpx.AsyncClient
) -> None:
    org = await stack.org("Entity cache", provider="openai", llm_triage=False)
    await org.faq(
        [
            ("How much does the Basic plan cost?", "The Basic plan costs 5 dollars a month."),
            ("How much does the Pro plan cost?", "The Pro plan costs 15 dollars a month."),
        ]
    )
    await org.patch_settings(
        token_saver={"exact_cache": False, "semantic_cache": True, "semantic_threshold": 0.5}
    )
    first = await org.visitor()
    assert "5 dollars" in first.last(await first.say("How much does the Basic plan cost?"))["body"]
    second = await org.visitor()
    reply = second.last(await second.say("How much does the Pro plan cost?"))
    assert "15 dollars" in reply["body"]  # not the Basic plan's cached answer
    third = await org.visitor()
    again = third.last(await third.say("how much does the Basic plan cost per month?"))
    assert "5 dollars" in again["body"]  # a paraphrase about the same plan still hits
