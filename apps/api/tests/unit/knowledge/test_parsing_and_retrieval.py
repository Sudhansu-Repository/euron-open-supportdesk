"""Parsing each file type, chunking, and retrieval scoring."""

from __future__ import annotations

import pytest

from supportdesk.demo.seed import _docx, _pdf
from supportdesk.knowledge.chunking import MAX_TOKENS, chunk_document, embedding_text
from supportdesk.knowledge.fetch import sitemap_urls
from supportdesk.knowledge.parsing import ParseError, detect_kind, parse
from supportdesk.knowledge.retrieval import calibrate, tsquery, within_budget
from tests.unit.ai.test_text_and_redaction import hit


def test_detect_kind() -> None:
    assert detect_kind("a.PDF", None) == "pdf"
    assert detect_kind("notes", "text/markdown; charset=utf-8") == "markdown"
    with pytest.raises(ParseError):
        detect_kind("virus.exe", "application/octet-stream")


def test_pdf_pages_become_sections_with_page_anchors() -> None:
    doc = parse(_pdf(["Warranty", "Three years."]), "w.pdf", None, "Warranty")
    assert (
        doc.pages == 1
        and doc.sections[0].anchor == "#page=1"
        and "Three years." in doc.sections[0].text
    )


def test_damaged_pdf_fails_clearly() -> None:
    with pytest.raises(ParseError, match="PDF"):
        parse(b"%PDF-1.4 garbage", "x.pdf", None, "x")


def test_docx_headings_split_sections() -> None:
    doc = parse(
        _docx([("Guide", "title"), ("Pairing", "heading"), ("Hold five seconds.", "text")]),
        "g.docx",
        None,
        "g",
    )
    assert [s.heading for s in doc.sections] == ["Pairing"]


def test_markdown_headings_and_title() -> None:
    doc = parse(
        b"# Lumen\n\nIntro\n\n## Setup\n\nStep one\n```\n# not a heading\n```\n", "a.md", None, "a"
    )
    assert doc.title == "Lumen" and [s.heading for s in doc.sections] == ["Lumen", "Setup"]
    assert "# not a heading" in doc.sections[1].text


def test_html_drops_navigation_and_keeps_structure() -> None:
    html = b"<html><title>Help</title><nav>Menu</nav><main><h1>Billing</h1><p>Pay by card.</p><li>Visa</li></main></html>"
    doc = parse(html, "h.html", None, "x")
    assert doc.title == "Help" and doc.sections[0].heading == "Billing"
    assert "Menu" not in doc.sections[0].text and "- Visa" in doc.sections[0].text


def test_faq_csv_rows_are_atomic() -> None:
    doc = parse(b'Question,Answer\n"How?","Like this."\n,empty\n', "f.csv", None, "FAQ")
    assert len(doc.sections) == 1 and doc.sections[0].atomic and doc.sections[0].heading == "How?"
    with pytest.raises(ParseError, match="question"):
        parse(b"a,b\n1,2\n", "x.csv", None, "x")


def test_chunks_respect_size_and_overlap() -> None:
    text = " ".join(
        f"Sentence number {i} explains a detail about lamps." for i in range(200)
    ).encode()
    chunks = chunk_document(parse(text, "long.txt", None, "Long"))
    assert len(chunks) > 5 and all(c.tokens <= MAX_TOKENS for c in chunks)
    first_last = chunks[0].text.split(". ")[-1]
    assert first_last.split(" ")[2] in chunks[1].text  # one sentence of overlap
    assert embedding_text("Guide", "Pairing", "x").startswith("Guide > Pairing")


def test_calibration_and_tsquery_and_budget() -> None:
    assert calibrate(0.85, "local:BAAI/bge-small-en-v1.5") == 1.0
    assert calibrate(0.5, "local:BAAI/bge-small-en-v1.5") == 0.0
    assert tsquery("How do I reset my password?!") == "reset | password"
    assert tsquery("'; DROP TABLE users; --") == "drop | table | user"
    hits = [hit("a"), hit("b"), hit("c")]
    assert len(within_budget(hits, 120)) == 2 and len(within_budget(hits, 10)) == 1


def test_sitemap_keeps_same_host_pages_only() -> None:
    xml = b"<urlset><url><loc>/a</loc></url><url><loc>https://other.example/b</loc></url><url><loc>/a</loc></url></urlset>"
    assert sitemap_urls(xml, "https://docs.example/sitemap.xml", 10) == ["https://docs.example/a"]
