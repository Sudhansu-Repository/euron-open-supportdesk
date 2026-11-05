"""Turn uploaded files and fetched pages into titled sections of plain text.

Every parser is bounded (pages, rows, characters) so a hostile or huge file costs a known
amount of work. Parsing runs in the worker, in a thread, never on the request path.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag

MAX_PDF_PAGES = 1000
MAX_CSV_ROWS = 5000
MAX_TEXT_CHARS = 5_000_000
# A DOCX is a zip: refuse one whose declared uncompressed size would blow up memory.
MAX_DOCX_UNCOMPRESSED = 100_000_000

KIND_BY_EXTENSION = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "text",
    ".html": "html",
    ".htm": "html",
    ".csv": "csv",
}
CONTENT_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/markdown": "markdown",
    "text/plain": "text",
    "text/html": "html",
    "application/xhtml+xml": "html",
    "text/csv": "csv",
}


class ParseError(Exception):
    """The file could not be read; the message is shown on the source."""


@dataclass
class Section:
    heading: str | None
    text: str
    # Appended to the source URL for a deep link (#page=3), or a full URL for crawled pages.
    anchor: str | None = None
    # FAQ rows are kept whole: one question and its answer is one chunk.
    atomic: bool = False


@dataclass
class Document:
    title: str
    sections: list[Section] = field(default_factory=list)
    pages: int = 0

    @property
    def chars(self) -> int:
        return sum(len(s.text) for s in self.sections)


def detect_kind(filename: str, content_type: str | None) -> str:
    lower = filename.lower()
    for ext, kind in KIND_BY_EXTENSION.items():
        if lower.endswith(ext):
            return kind
    if content_type:
        base = content_type.split(";")[0].strip().lower()
        if base in CONTENT_TYPES:
            return CONTENT_TYPES[base]
    raise ParseError(
        "Unsupported file type. Upload PDF, DOCX, Markdown, text, HTML or a CSV of questions "
        "and answers"
    )


def _clean(text: str) -> str:
    text = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def parse_pdf(data: bytes, title: str) -> Document:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ParseError("The PDF is password protected. Upload an unprotected copy")
        doc = Document(title=_pdf_title(reader) or title, pages=len(reader.pages))
        if len(reader.pages) > MAX_PDF_PAGES:
            raise ParseError(f"The PDF has more than {MAX_PDF_PAGES} pages. Split it first")
        for number, page in enumerate(reader.pages, start=1):
            text = _clean(page.extract_text() or "")
            if text:
                doc.sections.append(Section(None, text, anchor=f"#page={number}"))
    except ParseError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError) as exc:
        raise ParseError("The PDF could not be read. It may be damaged") from exc
    if not doc.sections:
        raise ParseError(
            "The PDF has no text layer (it may be a scan). Export it with text or use OCR first"
        )
    return doc


def _pdf_title(reader: object) -> str | None:
    meta = getattr(reader, "metadata", None)
    raw = getattr(meta, "title", None) if meta else None
    return str(raw).strip()[:300] if raw and str(raw).strip() else None


def parse_docx(data: bytes, title: str) -> Document:
    import zipfile

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            declared = sum(info.file_size for info in archive.infolist())
    except zipfile.BadZipFile as exc:
        raise ParseError("The DOCX file could not be read. It may be damaged") from exc
    if declared > MAX_DOCX_UNCOMPRESSED:
        raise ParseError("The DOCX file expands to more than 100 MB. Split it first")
    import docx

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:  # python-docx raises zipfile, KeyError, lxml errors
        raise ParseError("The DOCX file could not be read. It may be damaged") from exc
    doc = Document(title=(document.core_properties.title or "").strip()[:300] or title)
    heading: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        text = _clean("\n".join(buffer))
        if text:
            doc.sections.append(Section(heading, text))
        buffer.clear()

    for para in document.paragraphs:
        style = (para.style.name if para.style is not None else "") or ""
        text = para.text.strip()
        if not text:
            continue
        if style.lower().startswith(("heading", "title")):
            flush()
            heading = text[:300]
        else:
            buffer.append(text)
    flush()
    for table in document.tables:
        rows = [" | ".join(cell.text.strip() for cell in row.cells) for row in table.rows]
        text = _clean("\n".join(r for r in rows if r.strip(" |")))
        if text:
            doc.sections.append(Section("Table", text))
    if not doc.sections:
        raise ParseError("The DOCX file has no text")
    return doc


_MD_HEADING = re.compile(r"^(#{1,4})\s+(.+?)\s*#*\s*$")


def parse_markdown(text: str, title: str) -> Document:
    doc = Document(title=title)
    heading: str | None = None
    buffer: list[str] = []
    first_h1: str | None = None
    in_code = False

    def flush() -> None:
        body = _clean("\n".join(buffer))
        if body:
            doc.sections.append(Section(heading, body))
        buffer.clear()

    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
        match = None if in_code else _MD_HEADING.match(line)
        if match:
            flush()
            heading = match.group(2).strip()[:300]
            if match.group(1) == "#" and first_h1 is None:
                first_h1 = heading
        else:
            buffer.append(line)
    flush()
    if first_h1:
        doc.title = first_h1
    if not doc.sections:
        raise ParseError("The file has no text")
    return doc


def parse_html(html: str, title: str, url: str | None = None) -> Document:
    if len(html) > MAX_TEXT_CHARS:
        raise ParseError("The page has too much text to import")
    soup = BeautifulSoup(html, "html.parser")
    page_title = soup.title.get_text(" ", strip=True) if soup.title else ""
    for tag in soup(
        ["script", "style", "noscript", "nav", "footer", "header", "aside", "form", "svg", "iframe"]
    ):
        tag.decompose()
    found = soup.find("main") or soup.find("article") or soup.body
    root: Tag | BeautifulSoup = found if isinstance(found, Tag) else soup
    doc = Document(title=(page_title or title)[:300])
    heading: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        body = _clean("\n".join(buffer))
        if body:
            doc.sections.append(Section(heading, body, anchor=url))
        buffer.clear()

    for element in root.find_all(
        ["h1", "h2", "h3", "h4", "p", "li", "td", "pre", "blockquote", "dt", "dd"]
    ):
        text = element.get_text(" ", strip=True)
        if not text:
            continue
        if element.name in ("h1", "h2", "h3", "h4"):
            flush()
            heading = text[:300]
        elif element.name == "li":
            buffer.append(f"- {text}")
        else:
            buffer.append(text)
    flush()
    if not doc.sections:
        text = _clean(root.get_text("\n", strip=True))
        if text:
            doc.sections.append(Section(None, text, anchor=url))
    if not doc.sections:
        raise ParseError("The page has no readable text")
    return doc


def parse_faq_csv(text: str, title: str) -> Document:
    reader = csv.reader(io.StringIO(text))
    try:
        header = [h.strip().lower() for h in next(reader)]
    except StopIteration as exc:
        raise ParseError("The CSV file is empty") from exc
    q_names, a_names = ("question", "q", "questions"), ("answer", "a", "answers")
    try:
        qi = next(i for i, h in enumerate(header) if h in q_names)
        ai = next(i for i, h in enumerate(header) if h in a_names)
    except StopIteration as exc:
        raise ParseError('The CSV needs a "question" and an "answer" column') from exc
    doc = Document(title=title)
    for n, row in enumerate(reader):
        if n >= MAX_CSV_ROWS:
            raise ParseError(f"The CSV has more than {MAX_CSV_ROWS} rows. Split it first")
        if len(row) <= max(qi, ai):
            continue
        question, answer = row[qi].strip(), row[ai].strip()
        if not question or not answer:
            continue
        # The question is the heading: a citation then reads "FAQ > How do I ...?".
        doc.sections.append(Section(question[:300], f"Q: {question}\nA: {answer}", atomic=True))
    if not doc.sections:
        raise ParseError("The CSV has no question and answer rows")
    return doc


def parse(data: bytes, filename: str, content_type: str | None, title: str) -> Document:
    kind = detect_kind(filename, content_type)
    if kind == "pdf":
        return parse_pdf(data, title)
    if kind == "docx":
        return parse_docx(data, title)
    text = _decode(data)
    if len(text) > MAX_TEXT_CHARS:
        raise ParseError("The file has too much text. Split it first")
    if kind == "html":
        return parse_html(text, title)
    if kind == "csv":
        return parse_faq_csv(text, title)
    if kind == "markdown":
        return parse_markdown(text, title)
    return (
        Document(title=title, sections=[Section(None, _clean(text))]) if text.strip() else _empty()
    )


def _empty() -> Document:
    raise ParseError("The file has no text")
