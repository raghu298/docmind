"""Citation and fact verification (Constitution Principle I: never fabricate).

A quote is accepted only if it is an exact substring of the named document's extracted text
after collapsing runs of whitespace. No other differences (case, punctuation, curly vs straight
quotes, ellipses) are tolerated.
"""
from __future__ import annotations

import re

from .models import Answer, Citation, Document, DocumentSummary, KeyFact

CITATION_DROPPED_NOTICE = "An unverifiable citation was removed."
FACT_DROPPED_NOTICE = "An unverifiable fact was removed."

_WS = re.compile(r"\s+")


def normalize_ws(s: str) -> str:
    """Collapse every run of whitespace to a single space and strip the ends."""
    return _WS.sub(" ", s).strip()


def verify_quote(doc_text: str, quote: str) -> bool:
    """True when ``quote`` (whitespace-normalised, non-empty) occurs in ``doc_text``."""
    q = normalize_ws(quote or "")
    if not q:
        return False
    return q in normalize_ws(doc_text or "")


def _find_start(doc_text: str, quote: str) -> int | None:
    idx = doc_text.find(quote)
    return idx if idx >= 0 else None


def verify_answer(answer: Answer, docs_by_name: dict[str, Document]) -> Answer:
    """Keep only citations whose quote is verified in the named readable document.

    Dropped citations add the notice ``CITATION_DROPPED_NOTICE`` (once). If no citation
    survives, the result is ``Answer.not_found`` (keeping mode, fell_back and notices).
    """
    notices = list(answer.notices)
    if not answer.found or not answer.citations:
        return Answer.not_found(answer.question, answer.mode, notices=notices,
                                fell_back=answer.fell_back)

    kept: list[Citation] = []
    seen: set[tuple[str, str]] = set()
    dropped = False
    for c in answer.citations:
        doc = docs_by_name.get(c.doc_name)
        if doc is None or not doc.readable or not verify_quote(doc.text, c.quote):
            dropped = True
            continue
        key = (doc.name, normalize_ws(c.quote))
        if key in seen:
            continue
        seen.add(key)
        start = c.start if c.start is not None else _find_start(doc.text, c.quote)
        kept.append(c.model_copy(update={"doc_id": doc.id, "start": start}))

    if dropped and CITATION_DROPPED_NOTICE not in notices:
        notices.append(CITATION_DROPPED_NOTICE)
    if not kept:
        return Answer.not_found(answer.question, answer.mode, notices=notices,
                                fell_back=answer.fell_back)
    return answer.model_copy(update={"citations": kept, "notices": notices})


def verify_facts(facts: list[KeyFact], doc: Document) -> tuple[list[KeyFact], int]:
    """Return (facts whose source_quote is verified in ``doc``, number dropped)."""
    if not doc.readable:
        return [], len(facts)
    kept = [f.model_copy(update={"doc_id": doc.id, "doc_name": doc.name})
            for f in facts if verify_quote(doc.text, f.source_quote)]
    return kept, len(facts) - len(kept)


def verify_summary(summary: DocumentSummary, doc: Document) -> DocumentSummary:
    """Drop every fact whose quote is not verified; add ``FACT_DROPPED_NOTICE`` if any dropped."""
    update: dict = {}
    total_dropped = 0
    for field in ("parties", "dates", "amounts", "obligations"):
        kept, dropped = verify_facts(getattr(summary, field), doc)
        update[field] = kept
        total_dropped += dropped
    notices = list(summary.notices)
    if total_dropped and FACT_DROPPED_NOTICE not in notices:
        notices.append(FACT_DROPPED_NOTICE)
    update["notices"] = notices
    return summary.model_copy(update=update)
