"""``supportdesk seed-demo``: a living demo company, "Lumen" (smart lighting).

Creates agents and teams, configures the AI (the bundled mock model when SEED_AI_URL is
set, so the demo runs offline; extractive otherwise), indexes five knowledge sources of
different types through the real ingestion jobs (the worker must be running), writes 30
days of realistic conversation history with the ledger behind it, leaves a live inbox
(AI handling, unassigned, SLA at risk, waiting for approval), clusters knowledge gaps and
rolls up analytics. Safe to run twice: an existing demo is left as it is.
"""

from __future__ import annotations

import asyncio
import io
import os
import random
import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select, text, update

from supportdesk.ai.ledger import cost as price_cost
from supportdesk.ai.models import LlmCall
from supportdesk.analytics.service import rollup_day
from supportdesk.audit.service import Actor
from supportdesk.auth.service import signup
from supportdesk.channels.models import Inbox
from supportdesk.core.config import get_settings
from supportdesk.core.container import Container
from supportdesk.core.db import import_all_models
from supportdesk.core.security import hash_password
from supportdesk.customers.models import Customer
from supportdesk.demo import content
from supportdesk.gaps.models import GapQuestion
from supportdesk.gaps.service import cluster_org
from supportdesk.integrations.service import create_webhook
from supportdesk.knowledge import service as kb
from supportdesk.knowledge.models import Chunk, Source
from supportdesk.org.models import Org, OrgSettings, Team, TeamMember
from supportdesk.tickets.models import Macro, Message, Ticket, TicketEvent
from supportdesk.users.models import User

PASSWORD = os.environ.get("SUPPORTDESK_DEMO_PASSWORD", "Demo-Pass-2026")
SLUG = "lumen"
RNG = random.Random(8)
NOW = datetime.now(UTC).replace(microsecond=0)
PRICES = (Decimal("0.15"), Decimal("0.60"))  # gpt-4o-mini, USD per million tokens

AGENTS = [
    ("Maya Chen", "maya@lumen.example", "owner", "online", 12),
    ("Ravi Patel", "ravi@lumen.example", "admin", "online", 10),
    ("Sofia Alvarez", "sofia@lumen.example", "agent", "online", 10),
    ("Tom Becker", "tom@lumen.example", "agent", "online", 8),
    ("Aisha Khan", "aisha@lumen.example", "agent", "away", 10),
]
FIRST = [
    "Olivia",
    "Liam",
    "Emma",
    "Noah",
    "Ava",
    "Arjun",
    "Mia",
    "Lucas",
    "Priya",
    "Ethan",
    "Zara",
    "Mateo",
    "Chloe",
    "Kenji",
    "Isla",
    "Omar",
    "Hannah",
    "Diego",
    "Leah",
    "Felix",
    "Ananya",
    "Jonas",
    "Sara",
    "Wei",
    "Nora",
    "Rahul",
    "Elena",
    "Samuel",
    "Fatima",
    "Theo",
]
LAST = [
    "Johnson",
    "Garcia",
    "Kim",
    "Nguyen",
    "Rossi",
    "Sharma",
    "Müller",
    "Okafor",
    "Silva",
    "Brown",
    "Tanaka",
    "Dubois",
    "Kowalski",
    "Haddad",
    "Martin",
    "Iyer",
    "Andersson",
    "Lopez",
    "Wright",
    "Chen",
]

AI_QUESTIONS = [
    ("How long does shipping take?", "How long does shipping take?", "shipping"),
    (
        "hi, when will my order arrive? how long is shipping usually",
        "How long does shipping take?",
        "shipping",
    ),
    ("Can I track my order?", "Can I track my order?", "shipping"),
    ("how do I reset my password", "How do I reset my password?", "account"),
    ("I forgot my password and can't sign in", "How do I reset my password?", "account"),
    ("What does Lumen Plus include?", "What does Lumen Plus include?", "billing"),
    ("How do I change my plan to yearly?", "How do I change my plan?", "billing"),
    ("Where can I download my invoice for March?", "Where can I download my invoice?", "billing"),
    ("Which payment methods do you take?", "Which payment methods do you accept?", "billing"),
    ("My bulb keeps flickering, why?", "Why is my bulb flickering?", "technical"),
    (
        "Do the bulbs work if the internet is down?",
        "Do Lumen bulbs work without internet?",
        "technical",
    ),
    ("How many bulbs can I connect at home?", "How many bulbs can I connect?", "technical"),
    ("How long is the warranty on the bridge?", "How long is the warranty?", "general"),
    ("Can my partner control the lights too?", "Can I share control with my family?", "account"),
    ("how much power does one bulb use", "How much energy does a bulb use?", "general"),
]
SENSITIVE = [
    (
        "I was charged twice for my Lumen Plus subscription this month. Please fix this.",
        "billing_dispute",
        "billing",
    ),
    ("I want a refund for the starter kit, two bulbs arrived broken.", "refund", "shipping"),
    ("Please cancel my subscription and close my account.", "cancellation", "billing"),
    ("I need to change the email on my account to my work address.", "account_change", "account"),
    ("Someone logged into my account from another country. Was I hacked?", "security", "account"),
    ("Delete all my data please, GDPR request.", "data_deletion", "account"),
]
GAP_QUESTIONS = [
    (
        "Does Lumen work with Apple HomeKit?",
        "Apple Home support is planned for later this year. Today Lumen works with Alexa and Google Home.",
    ),
    (
        "Is there HomeKit support for the bridge?",
        "Not yet, HomeKit is on our roadmap. You can use Alexa or Google Home in the meantime.",
    ),
    (
        "Can I use Lumen bulbs with Siri?",
        "Siri needs Apple Home, which we do not support yet. It is on the roadmap.",
    ),
    (
        "Do you offer a discount for 40 bulbs for our office?",
        "Yes: 25 bulbs or more get 10 percent off and 100 or more get 18 percent. I have sent you a quote.",
    ),
    (
        "Do you have bulk pricing for hotels?",
        "We do. Volume pricing starts at 25 bulbs (10 percent off). I am connecting you with our business team.",
    ),
    (
        "Are the bulbs compatible with Zigbee hubs?",
        "Lumen bulbs use Wi-Fi and the Lumen Bridge, not Zigbee, so a Zigbee hub cannot control them.",
    ),
    (
        "Will Lumen work with my SmartThings Zigbee hub?",
        "Not directly: Lumen is Wi-Fi based. SmartThings can control Lumen through the Google Home integration.",
    ),
]
HUMAN_EMAIL = [
    (
        "Partnership enquiry",
        "Hi, we run a chain of cafes and would like to talk about a lighting partnership.",
    ),
    (
        "Invoice address wrong",
        "Our invoice shows the old company address, can you correct it to 12 Harbour Street?",
    ),
    (
        "Press request",
        "I'm writing an article on smart lighting and would love a quote from your team.",
    ),
]
AGENT_REPLIES = {
    "billing_dispute": "I'm sorry about the double charge. I can see two payments on the 3rd; I have refunded the duplicate. It shows within 5 business days.",
    "refund": "I'm sorry the bulbs arrived broken. I've issued a refund for the two bulbs and you don't need to send them back.",
    "cancellation": "I've cancelled your subscription; it stays active until the end of the billing period. Your account is closed after that.",
    "account_change": "Thanks for confirming from both addresses. Your account email is now your work address.",
    "security": "I've signed out every session and reset your password. Please enable two-step verification in Settings, Security.",
    "data_deletion": "Your data deletion request is confirmed. Everything is erased within 30 days and you'll get an email when it's done.",
}


def _pdf(lines: list[str]) -> bytes:
    """A one-page PDF with a text layer (enough for the demo; no PDF library needed)."""

    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    body = (
        "BT /F1 12 Tf 60 760 Td 16 TL " + " ".join(f"({esc(line)}) Tj T*" for line in lines) + " ET"
    )
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(body)} >>\nstream\n{body}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n{obj}\nendobj\n".encode("latin-1"))
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return out.getvalue()


def _docx(blocks: list[tuple[str, str]]) -> bytes:
    import docx

    document = docx.Document()
    for value, kind in blocks:
        if kind == "title":
            document.add_heading(value, level=0)
        elif kind == "heading":
            document.add_heading(value, level=1)
        else:
            document.add_paragraph(value)
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def _when(days_back: float) -> datetime:
    return NOW - timedelta(days=days_back)


class Seeder:
    def __init__(self, container: Container) -> None:
        self.c = container
        self.org: Org
        self.users: dict[str, User] = {}
        self.inboxes: dict[str, Inbox] = {}
        self.customers: list[Customer] = []
        self.faq_chunks: dict[str, Chunk] = {}
        self.number = 0

    async def run(self) -> None:
        async with self.c.db.sessionmaker() as session:
            if await session.scalar(select(Org.id).where(Org.slug == SLUG)):
                print("The demo is already seeded.")
                await self.print_logins(session)
                return
        await self.create_org()
        await self.add_knowledge()
        await self.wait_for_index()
        await self.history()
        await self.live_inbox()
        await self.finish()
        async with self.c.db.sessionmaker() as session:
            await self.print_logins(session)

    async def create_org(self) -> None:
        settings = self.c.settings.model_copy(update={"signup_enabled": True})
        name, email, _, _, _ = AGENTS[0]
        async with self.c.db.sessionmaker() as session:
            owner, org = await signup(session, settings, "Lumen", name, email, PASSWORD, None)
            self.org = org
            self.users[email] = owner
            hashed = hash_password(PASSWORD)
            for name, email, role, availability, capacity in AGENTS[1:]:
                user = User(
                    org_id=org.id,
                    name=name,
                    email=email,
                    role=role,
                    availability=availability,
                    capacity=capacity,
                    password_hash=hashed,
                    last_login_at=NOW - timedelta(hours=RNG.randint(1, 30)),
                )
                session.add(user)
                self.users[email] = user
            await session.flush()
            support = await session.scalar(select(Team).where(Team.org_id == org.id))
            assert support is not None
            for email in [a[1] for a in AGENTS[1:]]:
                session.add(TeamMember(team_id=support.id, user_id=self.users[email].id))
            billing = Team(org_id=org.id, name="Billing")
            session.add(billing)
            await session.flush()
            for email in ("ravi@lumen.example", "aisha@lumen.example"):
                session.add(TeamMember(team_id=billing.id, user_id=self.users[email].id))
            row = await session.get(OrgSettings, org.id)
            assert row is not None
            ai_url = os.environ.get("SEED_AI_URL", "").strip()
            row.brand = {
                "company_name": "Lumen",
                "support_email": "support@lumen.example",
                "accent_color": "#4f46e5",
                "help_center_title": "Lumen Help Center",
                "website": "https://lumen.example",
            }
            row.ai = {
                **row.ai,
                **(
                    {
                        "provider": "openai",
                        "base_url": ai_url,
                        "answer_model": "gpt-4o-mini",
                        "triage_model": "gpt-4o-mini",
                    }
                    if ai_url
                    else {"provider": "extractive"}
                ),
            }
            row.budgets = {**row.budgets, "daily_cost_usd": "5", "monthly_cost_usd": "60"}
            for inbox in (await session.scalars(select(Inbox).where(Inbox.org_id == org.id))).all():
                self.inboxes[inbox.channel] = inbox
                if inbox.channel == "widget":
                    inbox.name = "Website chat"
                    inbox.allowed_origins = ["http://localhost:4810", "http://localhost:4815"]
                    inbox.appearance = {
                        **inbox.appearance,
                        "title": "Lumen Support",
                        "color": "#4f46e5",
                        "greeting": "Hi! I'm Lumen's assistant. Ask me about setup, orders or your plan, or talk to our team.",
                        "suggestions": [
                            "How long does shipping take?",
                            "My bulb won't pair",
                            "What does Lumen Plus include?",
                        ],
                    }
                if inbox.channel == "email":
                    inbox.email_address = "support@lumen.example"
            for title, body, actions in content.MACROS:
                session.add(
                    Macro(
                        org_id=org.id,
                        title=title,
                        body=body,
                        actions=actions,
                        uses=RNG.randint(3, 60),
                    )
                )
            await session.commit()
            hook, _ = await create_webhook(
                self.c,
                session,
                self.actor_for(owner, org.id),
                "https://hooks.example.com/supportdesk",
                ["ticket.escalated", "ticket.resolved"],
            )
            hook.active = False
            hook.disabled_reason = "Demo webhook: point it at your own endpoint, then switch it on"
            await session.commit()
            for user in self.users.values():
                await session.refresh(user)
        print("created the Lumen organisation, 5 agents and 2 teams")

    def actor(self) -> Actor:
        owner = self.users[AGENTS[0][1]]
        return self.actor_for(owner, self.org.id)

    @staticmethod
    def actor_for(owner: User, org_id: object) -> Actor:
        return Actor(org_id, owner.id, owner.email, "owner")  # type: ignore[arg-type]

    async def add_knowledge(self) -> None:
        files = [
            ("lumen-help-guide.md", "text/markdown", content.GUIDE_MD.encode(), "Lumen Help Guide"),
            ("lumen-faq.csv", "text/csv", content.FAQ_CSV.encode(), "Frequently asked questions"),
            (
                "shipping-and-returns.html",
                "text/html",
                content.SHIPPING_HTML.encode(),
                "Shipping and returns",
            ),
            (
                "lumen-warranty.pdf",
                "application/pdf",
                _pdf(content.WARRANTY_TEXT),
                "Lumen Limited Warranty",
            ),
            (
                "lumen-for-business.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                _docx(content.BUSINESS_DOC),
                "Lumen for Business",
            ),
        ]
        async with self.c.db.sessionmaker() as session:
            for filename, ctype, data, title in files:
                await kb.add_file(self.c, session, self.actor(), filename, ctype, data, title)
            for title, category, body in content.ARTICLES:
                await kb.save_article(
                    session,
                    self.actor(),
                    title=title,
                    body=body,
                    category=category,
                    status="published",
                )
            title, category, body = content.DRAFT_ARTICLE
            await kb.save_article(
                session, self.actor(), title=title, body=body, category=category, status="draft"
            )
        print("queued 5 knowledge sources and 6 articles for indexing")

    async def wait_for_index(self, timeout_s: float = 600) -> None:
        deadline = asyncio.get_running_loop().time() + timeout_s
        while True:
            async with self.c.db.sessionmaker() as session:
                statuses = (
                    await session.scalars(select(Source.status).where(Source.org_id == self.org.id))
                ).all()
                pending_jobs = await session.scalar(
                    text(
                        "SELECT count(*) FROM jobs WHERE org_id = :o AND status IN ('queued','running')"
                    ),
                    {"o": self.org.id},
                )
            if all(s in ("ready", "failed") for s in statuses) and not pending_jobs:
                break
            if asyncio.get_running_loop().time() > deadline:
                raise SystemExit(
                    "indexing did not finish: is the worker running? (make up starts it)"
                )
            await asyncio.sleep(1)
        async with self.c.db.sessionmaker() as session:
            failed = (
                await session.scalars(
                    select(Source).where(Source.org_id == self.org.id, Source.status == "failed")
                )
            ).all()
            for s in failed:
                print(f"  source {s.title!r} failed: {s.error}")
            for chunk in (
                await session.scalars(select(Chunk).where(Chunk.org_id == self.org.id))
            ).all():
                if chunk.heading:
                    self.faq_chunks.setdefault(chunk.heading, chunk)
        print(f"indexed the knowledge base ({len(statuses) - len(failed)} sources ready)")

    async def _customers(self, session: Any) -> None:
        used: set[str] = set()
        for i in range(64):
            first, last = RNG.choice(FIRST), RNG.choice(LAST)
            email = (
                f"{first.lower()}.{last.lower().replace('ü', 'u')}{RNG.randint(1, 99)}@example.com"
            )
            if email in used:
                continue
            used.add(email)
            customer = Customer(
                org_id=self.org.id,
                name=f"{first} {last}",
                email=email,
                vip=i in (3, 17, 41),
                attributes={
                    "plan": RNG.choice(["Free", "Plus", "Plus", "Business"]),
                    "devices": RNG.randint(1, 24),
                },
                created_at=_when(RNG.uniform(40, 400)),
                last_seen_at=_when(RNG.uniform(0, 30)),
            )
            session.add(customer)
            self.customers.append(customer)
        await session.flush()

    def _ticket(
        self, created: datetime, channel: str, customer: Customer, subject: str, **kw: Any
    ) -> Ticket:
        self.number += 1
        inbox = self.inboxes[channel]
        return Ticket(
            org_id=self.org.id,
            number=self.number,
            inbox_id=inbox.id,
            channel=channel,
            customer_id=customer.id,
            subject=subject[:300],
            reply_token=secrets.token_hex(12),
            created_at=created,
            updated_at=created,
            last_message_at=created,
            last_customer_message_at=created,
            team_id=inbox.team_id,
            **kw,
        )

    def _msg(self, ticket: Ticket, at: datetime, author: str, body: str, **kw: Any) -> Message:
        return Message(
            org_id=self.org.id,
            ticket_id=ticket.id,
            author_type=author,
            body=body,
            created_at=at,
            sent_at=at if kw.get("status", "sent") == "sent" else None,
            **kw,
        )

    def _ledger(
        self, session: Any, ticket: Ticket, at: datetime, cached: bool = False
    ) -> tuple[int, Decimal]:
        triage_in, triage_out = RNG.randint(180, 260), RNG.randint(40, 70)
        rows = [("triage", triage_in, triage_out)]
        if not cached:
            rows.append(("answer", RNG.randint(650, 1200), RNG.randint(45, 110)))
        total_tokens, total_cost = 0, Decimal(0)
        for purpose, tin, tout in rows:
            c = price_cost(PRICES, tin, tout)
            session.add(
                LlmCall(
                    org_id=self.org.id,
                    ticket_id=ticket.id,
                    purpose=purpose,
                    provider="openai",
                    model="gpt-4o-mini",
                    input_tokens=tin,
                    output_tokens=tout,
                    cost_usd=c,
                    latency_ms=RNG.randint(380, 1400)
                    if purpose == "answer"
                    else RNG.randint(150, 400),
                    created_at=at,
                )
            )
            total_tokens += tin + tout
            total_cost += c
        if cached:
            session.add(
                LlmCall(
                    org_id=self.org.id,
                    ticket_id=ticket.id,
                    purpose="answer",
                    provider="openai",
                    model="gpt-4o-mini",
                    cache="exact",
                    saved_tokens=900,
                    saved_cost_usd=price_cost(PRICES, 850, 60),
                    created_at=at,
                )
            )
        return total_tokens, total_cost

    def _citation(self, heading: str) -> list[dict[str, Any]]:
        chunk = self.faq_chunks.get(heading)
        if chunk is None:
            return []
        return [
            {
                "chunk_id": str(chunk.id),
                "source_id": str(chunk.source_id) if chunk.source_id else None,
                "article_id": None,
                "title": chunk.title,
                "heading": chunk.heading,
                "url": chunk.url,
                "relevance": round(RNG.uniform(0.72, 0.98), 3),
            }
        ]

    def _faq_answer(self, heading: str) -> str:
        chunk = self.faq_chunks.get(heading)
        return (
            chunk.text.split("\nA: ", 1)[1]
            if chunk and "\nA: " in chunk.text
            else "Here is how that works."
        )

    async def history(self) -> None:
        agents = [u for u in self.users.values() if u.role in ("agent", "admin")]
        async with self.c.db.sessionmaker() as session:
            await self._customers(session)
            plan = []
            for _ in range(150):
                days = RNG.betavariate(1.2, 2.2) * 30  # busier recently
                plan.append(max(days, 0.6))
            plan.sort(reverse=True)
            for days in plan:
                created = _when(days) + timedelta(minutes=RNG.randint(0, 600))
                if created > NOW - timedelta(hours=14):
                    created = NOW - timedelta(hours=RNG.randint(14, 30))
                customer = RNG.choice(self.customers)
                roll = RNG.random()
                if roll < 0.5:
                    await self._ai_resolved(session, created, customer)
                elif roll < 0.72:
                    await self._sensitive(session, created, customer, RNG.choice(agents))
                elif roll < 0.86:
                    await self._gap(session, created, customer, RNG.choice(agents))
                elif roll < 0.94:
                    await self._unhelpful(session, created, customer, RNG.choice(agents))
                else:
                    await self._email(session, created, customer, RNG.choice(agents))
            await session.commit()
        print(f"wrote {self.number} conversations of history over 30 days")

    async def _ai_resolved(self, session: Any, created: datetime, customer: Customer) -> None:
        question, heading, category = RNG.choice(AI_QUESTIONS)
        channel = RNG.choices(["widget", "portal", "email"], [0.75, 0.15, 0.1])[0]
        t = self._ticket(
            created,
            channel,
            customer,
            question,
            status="resolved",
            category=category,
            sentiment=RNG.choice(["neutral", "neutral", "positive"]),
            intent="question",
            handled_by="ai",
            ai_resolved=True,
        )
        session.add(t)
        await session.flush()
        q = self._msg(t, created, "customer", question, author_id=customer.id)
        session.add(q)
        await session.flush()
        answered = created + timedelta(seconds=RNG.uniform(2.5, 7.5))
        cached = RNG.random() < 0.28
        tokens, cost = self._ledger(session, t, answered, cached)
        meta = {
            "action": "send",
            "reasons": [],
            "method": "cache" if cached else "model",
            "grounded": True,
            "cache": "exact" if cached else None,
            "tokens": tokens,
            "cost_usd": str(cost),
            "triage": {
                "intent": "question",
                "category": category,
                "sentiment": "neutral",
                "priority": "normal",
                "sensitive": [],
                "source": "rules+model",
            },
        }
        helpful = RNG.random() < 0.55
        session.add(
            self._msg(
                t,
                answered,
                "ai",
                self._faq_answer(heading),
                citations=self._citation(heading),
                reply_to_id=q.id,
                ai_meta=meta,
                feedback="helpful" if helpful else None,
            )
        )
        t.first_response_at = answered
        t.ai_answered_at = answered
        t.last_message_at = answered
        t.resolved_at = answered + (
            timedelta(minutes=RNG.randint(1, 20)) if helpful else timedelta(hours=24)
        )
        t.ai_tokens, t.ai_cost_usd = tokens, cost
        if helpful and RNG.random() < 0.6:
            t.csat_score = RNG.choices([5, 4, 3], [0.7, 0.25, 0.05])[0]
        session.add(
            TicketEvent(
                org_id=self.org.id,
                ticket_id=t.id,
                type="ai.answered",
                actor_type="ai",
                data={},
                created_at=answered,
            )
        )

    async def _escalate(
        self,
        session: Any,
        t: Ticket,
        q: Message,
        at: datetime,
        reasons: list[str],
        agent: User,
        reply: str,
        summary: str,
    ) -> None:
        tokens, cost = self._ledger(session, t, at)
        session.add(
            self._msg(
                t,
                at,
                "system",
                "I'm connecting you with a teammate who can help with this. They'll reply here and by email.",
                reply_to_id=q.id,
                ai_meta={"handoff": True, "reasons": reasons},
            )
        )
        t.handled_by = "human"
        t.escalation_reasons = reasons
        t.escalated_at = at
        t.summary = summary
        t.assignee_id = agent.id
        t.ai_tokens, t.ai_cost_usd = tokens, cost
        t.first_response_at = at
        t.first_response_due_at = at + timedelta(hours=2 if t.priority == "high" else 8)
        t.resolution_due_at = at + timedelta(hours=24 if t.priority == "high" else 72)
        human = at + timedelta(minutes=RNG.choice([6, 11, 19, 25, 42, 64, 95, 140, 210]))
        session.add(self._msg(t, human, "agent", reply, author_id=agent.id))
        t.human_replied_at = human
        t.last_message_at = human
        t.status = "resolved"
        t.resolved_at = human + timedelta(minutes=RNG.randint(5, 600))
        t.sla_breached = human > t.first_response_due_at
        if RNG.random() < 0.7:
            t.csat_score = RNG.choices([5, 4, 3, 2], [0.55, 0.3, 0.1, 0.05])[0]
        session.add(
            TicketEvent(
                org_id=self.org.id,
                ticket_id=t.id,
                type="escalated",
                actor_type="ai",
                data={"reasons": reasons},
                created_at=at,
            )
        )
        session.add(
            TicketEvent(
                org_id=self.org.id,
                ticket_id=t.id,
                type="assigned",
                actor_type="system",
                data={"assignee_id": str(agent.id), "routed": True},
                created_at=at,
            )
        )

    async def _sensitive(
        self, session: Any, created: datetime, customer: Customer, agent: User
    ) -> None:
        text_, intent, category = RNG.choice(SENSITIVE)
        t = self._ticket(
            created,
            RNG.choice(["widget", "widget", "email", "portal"]),
            customer,
            text_,
            priority="high",
            category=category,
            intent=intent,
            sentiment=RNG.choice(["negative", "neutral"]),
        )
        session.add(t)
        await session.flush()
        q = self._msg(t, created, "customer", text_, author_id=customer.id)
        session.add(q)
        await session.flush()
        at = created + timedelta(seconds=RNG.uniform(1.5, 4))
        await self._escalate(
            session,
            t,
            q,
            at,
            ["sensitive_intent"],
            agent,
            AGENT_REPLIES[intent],
            f"Customer: {text_} Handed over because: Sensitive request.",
        )

    async def _gap(self, session: Any, created: datetime, customer: Customer, agent: User) -> None:
        question, reply = RNG.choice(GAP_QUESTIONS)
        t = self._ticket(
            created,
            "widget",
            customer,
            question,
            category="technical",
            intent="question",
            sentiment="neutral",
        )
        session.add(t)
        await session.flush()
        q = self._msg(t, created, "customer", question, author_id=customer.id)
        session.add(q)
        await session.flush()
        at = created + timedelta(seconds=RNG.uniform(2, 5))
        await self._escalate(
            session,
            t,
            q,
            at,
            ["no_grounded_answer"],
            agent,
            reply,
            f"Customer: {question} Handed over because: Not covered by the knowledge base.",
        )
        session.add(
            GapQuestion(
                org_id=self.org.id,
                ticket_id=t.id,
                message_id=q.id,
                question=question,
                reason="no_answer",
                created_at=at,
            )
        )

    async def _unhelpful(
        self, session: Any, created: datetime, customer: Customer, agent: User
    ) -> None:
        question = "The bulb still won't pair after I reset it, what else can I try?"
        t = self._ticket(
            created,
            "widget",
            customer,
            question,
            category="technical",
            intent="question",
            sentiment="negative",
            priority="high",
        )
        session.add(t)
        await session.flush()
        q = self._msg(t, created, "customer", question, author_id=customer.id)
        session.add(q)
        await session.flush()
        answered = created + timedelta(seconds=4)
        tokens, cost = self._ledger(session, t, answered)
        session.add(
            self._msg(
                t,
                answered,
                "ai",
                "Most pairing problems are the Wi-Fi band. Lumen bulbs use 2.4 GHz "
                "Wi-Fi only; turn on your router's 2.4 GHz compatibility mode for setup.",
                citations=self._citation("The bulb will not pair"),
                reply_to_id=q.id,
                feedback="unhelpful",
                ai_meta={"action": "send", "method": "model", "grounded": True, "reasons": []},
            )
        )
        later = answered + timedelta(minutes=2)
        session.add(
            GapQuestion(
                org_id=self.org.id,
                ticket_id=t.id,
                message_id=q.id,
                question=question,
                reason="unhelpful",
                created_at=later,
            )
        )
        await self._escalate(
            session,
            t,
            q,
            later,
            ["answer_unhelpful"],
            agent,
            "Thanks for trying that. Let's check the Bridge: is its light solid green? If not, "
            "unplug it for 10 seconds. I'll stay with you until it works.",
            "Customer reset the bulb and it still does not pair; the AI's Wi-Fi tip did not help.",
        )
        t.ai_tokens += tokens
        t.ai_cost_usd += cost

    async def _email(
        self, session: Any, created: datetime, customer: Customer, agent: User
    ) -> None:
        subject, body = RNG.choice(HUMAN_EMAIL)
        t = self._ticket(
            created,
            "email",
            customer,
            subject,
            category="general",
            intent="question",
            handled_by="human",
            assignee_id=agent.id,
            sentiment="neutral",
        )
        session.add(t)
        await session.flush()
        session.add(self._msg(t, created, "customer", body, author_id=customer.id))
        reply_at = created + timedelta(minutes=RNG.randint(20, 300))
        session.add(
            self._msg(
                t,
                reply_at,
                "agent",
                "Thanks for writing in! I've passed this to the right team and "
                "they'll follow up by email within a day.",
                author_id=agent.id,
            )
        )
        t.first_response_at = t.human_replied_at = reply_at
        t.last_message_at = reply_at
        t.status = "resolved"
        t.resolved_at = reply_at + timedelta(hours=RNG.randint(1, 30))

    async def live_inbox(self) -> None:
        """The open conversations an agent sees right now."""
        users = {u.email: u for u in self.users.values()}
        sofia, tom = users["sofia@lumen.example"], users["tom@lumen.example"]
        async with self.c.db.sessionmaker() as session:
            live: list[tuple[str, dict[str, Any]]] = [
                (
                    "I was charged twice for Lumen Plus this month, this is really frustrating!",
                    {
                        "reasons": ["sensitive_intent", "negative_sentiment"],
                        "priority": "high",
                        "category": "billing",
                        "sentiment": "negative",
                        "minutes": 95,
                        "breach": True,
                    },
                ),
                (
                    "Do you have bulk pricing for a 60-room hotel?",
                    {
                        "reasons": ["no_grounded_answer"],
                        "priority": "normal",
                        "category": "general",
                        "minutes": 300,
                    },
                ),
                (
                    "Is Lumen compatible with Apple HomeKit yet?",
                    {
                        "reasons": ["no_grounded_answer"],
                        "priority": "normal",
                        "category": "technical",
                        "minutes": 40,
                    },
                ),
                (
                    "Can I talk to a real person about my order? It's been a week.",
                    {
                        "reasons": ["customer_requested"],
                        "priority": "high",
                        "category": "shipping",
                        "minutes": 25,
                        "assignee": sofia,
                    },
                ),
                (
                    "The app says my Bridge is offline even though it's plugged in.",
                    {
                        "reasons": ["answer_unhelpful"],
                        "priority": "high",
                        "category": "technical",
                        "minutes": 70,
                        "assignee": tom,
                        "vip": True,
                    },
                ),
            ]
            for text_, opts in live:
                customer = (
                    RNG.choice([c for c in self.customers if c.vip])
                    if opts.get("vip")
                    else RNG.choice(self.customers)
                )
                created = NOW - timedelta(minutes=opts["minutes"])
                t = self._ticket(
                    created,
                    "widget",
                    customer,
                    text_,
                    priority=opts["priority"],
                    category=opts["category"],
                    sentiment=opts.get("sentiment", "neutral"),
                    handled_by="human",
                    escalation_reasons=opts["reasons"],
                    escalated_at=created,
                    assignee_id=opts["assignee"].id if opts.get("assignee") else None,
                    summary=f"Customer: {text_}",
                )
                due = created + timedelta(
                    minutes=60
                    if opts.get("breach")
                    else (120 if opts["priority"] == "high" else 480)
                )
                t.first_response_due_at = due
                t.resolution_due_at = created + timedelta(hours=24)
                t.sla_next_due_at = due
                t.sla_breached = bool(opts.get("breach"))
                t.first_response_at = created + timedelta(seconds=3)
                session.add(t)
                await session.flush()
                q = self._msg(t, created, "customer", text_, author_id=customer.id)
                session.add(q)
                await session.flush()
                session.add(
                    self._msg(
                        t,
                        created + timedelta(seconds=3),
                        "system",
                        "I'm connecting you with a teammate who can help with this. They'll reply right here.",
                        reply_to_id=q.id,
                        ai_meta={"handoff": True, "reasons": opts["reasons"]},
                    )
                )
                session.add(
                    TicketEvent(
                        org_id=self.org.id,
                        ticket_id=t.id,
                        type="escalated",
                        actor_type="ai",
                        data={"reasons": opts["reasons"]},
                        created_at=created,
                    )
                )
                if "no_grounded_answer" in opts["reasons"]:
                    session.add(
                        GapQuestion(
                            org_id=self.org.id,
                            ticket_id=t.id,
                            message_id=q.id,
                            question=text_,
                            reason="no_answer",
                            created_at=created,
                        )
                    )
                t.ai_tokens, t.ai_cost_usd = self._ledger(session, t, created)

            # Waiting for approval: a grounded answer to a sensitive request, held by policy.
            for text_, heading in (
                (
                    "I'd like to return my starter kit and get a refund, it's unused.",
                    "What is your return policy?",
                ),
                ("Please cancel my Lumen Plus, how do I downgrade?", "How do I change my plan?"),
            ):
                customer = RNG.choice(self.customers)
                created = NOW - timedelta(minutes=RNG.randint(8, 50))
                t = self._ticket(
                    created,
                    "widget",
                    customer,
                    text_,
                    priority="high",
                    category="billing",
                    intent="refund" if "refund" in text_ else "cancellation",
                    handled_by="human",
                    escalation_reasons=["sensitive_intent"],
                    escalated_at=created,
                    pending_approval=True,
                    summary=f"Customer: {text_} Handed over because: Sensitive request.",
                )
                t.first_response_due_at = created + timedelta(hours=2)
                t.sla_next_due_at = t.first_response_due_at
                session.add(t)
                await session.flush()
                q = self._msg(t, created, "customer", text_, author_id=customer.id)
                session.add(q)
                await session.flush()
                tokens, cost = self._ledger(session, t, created)
                session.add(
                    self._msg(
                        t,
                        created + timedelta(seconds=4),
                        "ai",
                        self._faq_answer(heading),
                        kind="reply",
                        status="pending",
                        citations=self._citation(heading),
                        reply_to_id=q.id,
                        ai_meta={
                            "action": "approval",
                            "reasons": ["sensitive_intent"],
                            "method": "model",
                            "grounded": True,
                            "tokens": tokens,
                            "cost_usd": str(cost),
                        },
                    )
                )
                session.add(
                    self._msg(
                        t,
                        created + timedelta(seconds=4),
                        "system",
                        "Thanks! A teammate is checking this and will reply shortly.",
                        reply_to_id=q.id,
                        ai_meta={"handoff": True, "reasons": ["sensitive_intent"]},
                    )
                )
                t.ai_tokens, t.ai_cost_usd = tokens, cost

            # The AI is handling these right now (answered, waiting for the customer).
            for question, heading, category in AI_QUESTIONS[:3]:
                customer = RNG.choice(self.customers)
                created = NOW - timedelta(minutes=RNG.randint(2, 30))
                t = self._ticket(
                    created,
                    "widget",
                    customer,
                    question,
                    status="pending",
                    category=category,
                    handled_by="ai",
                    intent="question",
                    sentiment="neutral",
                )
                session.add(t)
                await session.flush()
                q = self._msg(t, created, "customer", question, author_id=customer.id)
                session.add(q)
                await session.flush()
                answered = created + timedelta(seconds=4)
                tokens, cost = self._ledger(session, t, answered)
                session.add(
                    self._msg(
                        t,
                        answered,
                        "ai",
                        self._faq_answer(heading),
                        citations=self._citation(heading),
                        reply_to_id=q.id,
                        ai_meta={
                            "action": "send",
                            "method": "model",
                            "grounded": True,
                            "tokens": tokens,
                            "cost_usd": str(cost),
                            "reasons": [],
                        },
                    )
                )
                t.first_response_at = t.ai_answered_at = t.last_message_at = answered
                t.ai_tokens, t.ai_cost_usd = tokens, cost
            await session.commit()
        print("opened a live inbox: escalations, an SLA breach, two answers waiting for approval")

    async def finish(self) -> None:
        async with self.c.db.sessionmaker() as session:
            await session.execute(
                update(Org).where(Org.id == self.org.id).values(ticket_seq=self.number)
            )
            await session.commit()
            await cluster_org(self.c, session, self.org.id)
            today = NOW.date()
            for i in range(31):
                await rollup_day(session, self.org.id, today - timedelta(days=i))
            await session.commit()
        print("clustered knowledge gaps and rolled up 31 days of analytics")

    async def print_logins(self, session: Any) -> None:
        key = await session.scalar(
            select(Inbox.public_key)
            .join(Org, Org.id == Inbox.org_id)
            .where(Org.slug == SLUG, Inbox.channel == "widget")
        )
        s = self.c.settings
        print("")
        print("Demo ready. Sign in at", s.public_url)
        for name, email, role, _, _ in AGENTS:
            print(f"  {role:<6} {email:<22} {PASSWORD}   ({name})")
        print(f"Help center and portal: {s.public_url}/help/{SLUG}")
        print(f"Widget key: {key}   (the demo customer site on http://localhost:4815 uses it)")


async def run() -> None:
    settings = get_settings()
    import_all_models()
    container = Container.build(settings)
    try:
        await Seeder(container).run()
    finally:
        await container.close()
