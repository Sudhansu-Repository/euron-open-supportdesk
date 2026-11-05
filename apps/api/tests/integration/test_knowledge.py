"""AC1 (train on your business) and AC7 (knowledge gaps close themselves)."""

from __future__ import annotations

import httpx

from supportdesk.demo.seed import _docx, _pdf
from tests.integration.conftest import Stack, eventually


async def _asks(org: object, question: str) -> dict[str, object]:
    visitor = await org.visitor()  # type: ignore[attr-defined]
    conv = await visitor.say(question)
    result: dict[str, object] = visitor.last(conv)
    return result


async def test_every_source_type_becomes_searchable_and_cited(
    stack: Stack, mock: httpx.AsyncClient
) -> None:
    org = await stack.org("Sources", provider="openai")
    pdf = await org.upload(
        "warranty.pdf",
        _pdf(["Warranty", "Every Lumen bulb carries a three year warranty against defects."]),
        "application/pdf",
        "Warranty",
    )
    docx = await org.upload(
        "business.docx",
        _docx(
            [
                ("Business", "title"),
                ("Volume pricing", "heading"),
                ("Orders of 25 bulbs get ten percent off.", "text"),
            ]
        ),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    md = await org.upload(
        "setup.md",
        b"# Setup\n\n## Pairing\n\nHold the button for five seconds until the light blinks blue.\n",
        "text/markdown",
    )
    csv = await org.faq()
    url = await org.ok(
        "POST",
        "/api/v1/knowledge/sources/url",
        {"url": f"{stack.site_url}/docs/billing"},
        status=201,
    )
    url = await org.wait_source(url["id"])
    for source in (pdf, docx, md, csv, url):
        assert source["status"] == "ready", source
        assert source["chunk_count"] >= 1
    assert url["title"] == "Billing help"  # the page title replaces the URL

    cases = [
        ("How long is the warranty on a bulb?", "Warranty", "three year"),
        ("Is there volume pricing for 25 bulbs?", "business", "ten percent"),
        ("How do I start pairing, which button?", "Setup", "five seconds"),
        ("When are invoices emailed?", "Billing help", "first business day"),
    ]
    for question, title, needle in cases:
        answer = await _asks(org, question)
        assert answer["author_type"] == "ai", (question, answer)
        assert needle in str(answer["body"])
        assert any(title.lower() in str(c["title"]).lower() for c in answer["citations"])  # type: ignore[union-attr]


async def test_sitemap_import_respects_robots_and_same_host(stack: Stack) -> None:
    org = await stack.org("Sitemap")
    source = await org.ok(
        "POST",
        "/api/v1/knowledge/sources/url",
        {"url": f"{stack.site_url}/sitemap.xml", "sitemap": True},
        status=201,
    )
    source = await org.wait_source(source["id"])
    assert (
        source["status"] == "ready" and source["pages"] == 2
    )  # /private is disallowed by robots.txt
    chunks = await org.ok("GET", f"/api/v1/knowledge/sources/{source['id']}/chunks")
    text = " ".join(c["text"] for c in chunks)
    assert "twenty teammates" in text and "Do not import" not in text


async def test_unreadable_files_fail_with_a_reason(stack: Stack) -> None:
    org = await stack.org("Broken files")
    broken = await org.upload("broken.pdf", b"%PDF-1.4 not really a pdf", "application/pdf")
    assert broken["status"] == "failed" and "PDF" in broken["error"]
    bad_csv = await org.upload("bad.csv", b"name,email\nann,ann@example.com\n", "text/csv")
    assert bad_csv["status"] == "failed" and "question" in bad_csv["error"]
    resp = await org.client.post(
        "/api/v1/knowledge/sources/upload",
        files={"file": ("x.exe", b"MZ", "application/x-msdownload")},
    )
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "unsupported_file"


async def test_urls_to_metadata_are_refused_even_through_redirects(stack: Stack) -> None:
    org = await stack.org("SSRF")
    resp = await org.client.post(
        "/api/v1/knowledge/sources/url", json={"url": "http://169.254.169.254/latest/meta-data/"}
    )
    assert resp.status_code == 400
    source = await org.ok(
        "POST",
        "/api/v1/knowledge/sources/url",
        {"url": f"{stack.site_url}/redirect-to-metadata"},
        status=201,
    )
    source = await org.wait_source(source["id"])
    assert source["status"] == "failed" and "metadata" in source["error"].lower()


async def test_deleting_a_source_removes_its_answers(stack: Stack) -> None:
    org = await stack.org("Delete")
    csv = await org.faq()
    assert (await _asks(org, "How long does shipping take?"))["author_type"] == "ai"
    await org.ok("DELETE", f"/api/v1/knowledge/sources/{csv['id']}", status=204)
    assert (await _asks(org, "How long does shipping take?"))["author_type"] == "system"


async def test_reindex_replaces_chunks_atomically(stack: Stack) -> None:
    org = await stack.org("Reindex")
    source = await org.faq()
    again = await org.ok("POST", f"/api/v1/knowledge/sources/{source['id']}/reindex")
    again = await org.wait_source(again["id"])
    assert (
        again["version"] == source["version"] + 1 and again["chunk_count"] == source["chunk_count"]
    )


async def test_published_articles_answer_and_unpublished_ones_do_not(stack: Stack) -> None:
    org = await stack.org("Articles")
    article = await org.ok(
        "POST",
        "/api/v1/knowledge/articles",
        {
            "title": "Gift cards",
            "body": "Gift cards never expire and can be used on any order.",
            "status": "published",
        },
        status=201,
    )

    async def answered() -> bool:
        return (await _asks(org, "Do gift cards expire?"))["author_type"] == "ai"

    assert await eventually(answered)
    help_page = await stack.client().get(f"/api/v1/help/{org.slug}/articles/{article['slug']}")
    assert help_page.status_code == 200
    await org.ok(
        "PUT",
        f"/api/v1/knowledge/articles/{article['id']}",
        {"title": "Gift cards", "body": article["body"], "status": "draft"},
    )
    assert (await _asks(org, "Do gift cards expire?"))["author_type"] == "system"
    assert (
        await stack.client().get(f"/api/v1/help/{org.slug}/articles/{article['slug']}")
    ).status_code == 404


async def test_playground_shows_passages_scores_and_the_decision(stack: Stack) -> None:
    org = await stack.org("Playground")
    await org.faq()
    result = await org.ok(
        "POST", "/api/v1/knowledge/test", {"question": "How do I change my plan?"}
    )
    assert result["action"] == "send" and result["grounded"]
    assert result["passages"] and result["passages"][0]["relevance"] >= result["threshold"]


async def test_knowledge_gap_to_article_to_answer(stack: Stack, mock: httpx.AsyncClient) -> None:
    org = await stack.org("Gap loop", provider="openai")
    await org.faq()
    tickets = []
    for question in (
        "Do you integrate with Zapier?",
        "Is there a Zapier integration?",
        "Can I connect Zapier?",
    ):
        visitor = await org.visitor()
        conv = await visitor.say(question)
        assert visitor.last(conv)["author_type"] == "system"
        tickets.append(conv["ticket_id"])
    await org.ok(
        "POST",
        f"/api/v1/tickets/{tickets[0]}/messages",
        {
            "body": "Yes: Zapier connects through our webhooks. Add a webhook in Settings and pick a Zapier trigger."
        },
        status=201,
    )

    async def clustered() -> list[dict[str, object]]:
        gaps = await org.ok("GET", "/api/v1/gaps")
        return [
            g for g in gaps if "zapier" in str(g["title"]).lower() and int(g["question_count"]) >= 2
        ]  # type: ignore[call-overload]

    gap = (await eventually(clustered, wait_s=120))[0]
    draft = await org.ok("POST", f"/api/v1/gaps/{gap['id']}/draft")
    assert "webhook" in draft["body"].lower()
    await org.ok(
        "POST",
        "/api/v1/knowledge/articles",
        {
            "title": "Connecting Zapier",
            "body": draft["body"],
            "status": "published",
            "gap_id": gap["id"],
        },
        status=201,
    )
    assert (await org.ok("GET", f"/api/v1/gaps/{gap['id']}"))["status"] == "resolved"

    async def now_answered() -> bool:
        return (await _asks(org, "Do you integrate with Zapier?"))["author_type"] == "ai"

    assert await eventually(now_answered)
