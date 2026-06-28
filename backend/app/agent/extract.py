"""Best-effort text extraction for the agent's ``read_file`` tool.

The drive stores arbitrary blobs. To let the assistant group files by topic we
turn the common document types into plain text: text/code files decode
directly, PDFs go through ``pypdf`` and Word ``.docx`` through ``python-docx``.
Anything else (images, video, archives) returns a short descriptor instead of
raw bytes, and every result is capped so one large file can't blow the token
budget.
"""

from __future__ import annotations

import io

# Cap on how much extracted text we hand the model for one file.
MAX_TEXT_OUTPUT = 24_000
# Never read more than this many bytes off disk for extraction.
MAX_READ_BYTES = 5 * 1024 * 1024

_TEXT_CONTENT_TYPES = {
    "application/json",
    "application/xml",
    "application/javascript",
    "application/x-yaml",
    "application/yaml",
    "application/toml",
    "application/csv",
    "image/svg+xml",
}
_TEXT_EXTENSIONS = {
    "txt", "md", "markdown", "rst", "csv", "tsv", "log", "json", "jsonl", "yaml",
    "yml", "toml", "ini", "cfg", "conf", "xml", "html", "htm", "css", "js", "ts",
    "tsx", "jsx", "py", "rb", "go", "rs", "java", "c", "h", "cpp", "hpp", "sh",
    "bash", "sql", "env",
}
_PDF_TYPE = "application/pdf"
_DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _ext(filename: str) -> str:
    _, _, ext = filename.rpartition(".")
    return ext.lower() if ext and ext != filename else ""


def _truncate(text: str) -> str:
    if len(text) <= MAX_TEXT_OUTPUT:
        return text
    return text[:MAX_TEXT_OUTPUT] + "\n\n…(file truncated; it is longer than shown)"


def _is_textual(filename: str, content_type: str) -> bool:
    ct = content_type.split(";", 1)[0].strip().lower()
    if ct.startswith("text/"):
        return True
    if ct in _TEXT_CONTENT_TYPES:
        return True
    return _ext(filename) in _TEXT_EXTENSIONS


def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    parts = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(p for p in parts if p.strip())


def _extract_docx(data: bytes) -> str:
    from docx import Document

    document = Document(io.BytesIO(data))
    return "\n".join(p.text for p in document.paragraphs if p.text.strip())


def extract_text(filename: str, content_type: str, data: bytes) -> str:
    """Return extracted text (capped) for a file, or a short descriptor when the
    file has no usefully extractable text."""
    ext = _ext(filename)
    descriptor = f"[binary file “{filename}”; type {content_type or 'unknown'}; {len(data)} bytes; no extractable text]"

    if content_type.split(";", 1)[0].strip().lower() == _PDF_TYPE or ext == "pdf":
        try:
            text = _extract_pdf(data)
        except Exception:  # noqa: BLE001 - a malformed PDF must not abort the tool
            return f"[could not extract text from PDF “{filename}”]"
        if not text.strip():
            return f"[PDF “{filename}” has no extractable text (likely scanned images)]"
        return _truncate(text)

    if ext == "docx" or content_type.split(";", 1)[0].strip().lower() == _DOCX_TYPE:
        try:
            text = _extract_docx(data)
        except Exception:  # noqa: BLE001 - a malformed docx must not abort the tool
            return f"[could not extract text from Word document “{filename}”]"
        return _truncate(text) if text.strip() else f"[Word document “{filename}” has no extractable text]"

    if _is_textual(filename, content_type):
        return _truncate(data.decode("utf-8", errors="replace"))

    return descriptor
