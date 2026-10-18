"""Split documents into paragraph chunks with character offsets."""
from __future__ import annotations

import re

from docmind.models import Chunk, Document

MAX_CHUNK_CHARS = 900
_PARA = re.compile(r"\n\s*\n")


def _spans(text: str) -> list[tuple[int, int]]:
    spans, pos = [], 0
    for m in _PARA.finditer(text):
        spans.append((pos, m.start()))
        pos = m.end()
    spans.append((pos, len(text)))
    out = []
    for s, e in spans:
        while s < e and text[s].isspace():
            s += 1
        while e > s and text[e - 1].isspace():
            e -= 1
        # split very long paragraphs on line breaks
        while e - s > MAX_CHUNK_CHARS:
            cut = text.rfind("\n", s, s + MAX_CHUNK_CHARS)
            if cut <= s:
                cut = s + MAX_CHUNK_CHARS
            out.append((s, cut))
            s = cut
            while s < e and text[s].isspace():
                s += 1
        if e > s:
            out.append((s, e))
    return out


def chunk_document(doc: Document) -> list[Chunk]:
    return [Chunk(id=f"{doc.id}:{i}", doc_id=doc.id, doc_name=doc.name, index=i,
                  start=s, end=e, text=doc.text[s:e])
            for i, (s, e) in enumerate(_spans(doc.text))]
