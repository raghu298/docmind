"""Load uploaded files (.pdf/.txt/.md) into Documents."""
from __future__ import annotations

import hashlib
import io

from docmind.models import DocSource, Document

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ACCEPTED_EXTENSIONS = (".pdf", ".txt", ".md")


class ParseError(ValueError):
    def __init__(self, user_message: str):
        super().__init__(user_message)
        self.user_message = user_message


def doc_id_for(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:12]


def load_file(name: str, data: bytes, source: DocSource = "upload") -> Document:
    low = name.lower()
    if not low.endswith(ACCEPTED_EXTENSIONS):
        raise ParseError(f"{name}: unsupported file type (use .pdf, .txt or .md)")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ParseError(f"{name}: file is larger than 10 MB")
    if low.endswith(".pdf"):
        from pypdf import PdfReader

        try:
            reader = PdfReader(io.BytesIO(data))
            text = "\n\n".join((p.extract_text() or "") for p in reader.pages)
        except Exception as exc:
            raise ParseError(f"{name}: this PDF could not be read") from exc
    else:
        text = data.decode("utf-8", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return Document(id=doc_id_for(data), name=name, source=source, size_bytes=len(data),
                    text=text, readable=bool(text.strip()))
