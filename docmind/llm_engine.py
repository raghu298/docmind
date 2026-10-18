"""Live mode: Claude via the official anthropic SDK (see contracts/llm-schemas.md).

No Streamlit imports. The API key is never logged, stored, or included in any message.
Errors are mapped to ``LiveError`` subclasses carrying fixed, friendly ``user_message`` text.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, get_args

import anthropic
from pydantic import ValidationError

from .models import (
    Answer, Chunk, Citation, DateRole, Document, DocumentSummary, KeyFact, LLMAnswer,
    LLMExtraction, AmountRole,
)
from .verify import verify_answer, verify_summary

MODELS: tuple[str, ...] = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5")
DEFAULT_MODEL: str = "claude-opus-5-5"

TOKEN_BUDGET = 150_000
MAX_TOKENS = 16000
FALLBACK_TOP_K = 12
LARGE_DOC_NOTICE = "Large document: only the first part was analysed in Live mode."

_DATE_ROLES = frozenset(get_args(DateRole))
_AMOUNT_ROLES = frozenset(get_args(AmountRole))

_COMMON_RULES = """\
Rules you must always follow:
- Use ONLY the documents provided inside <document> tags. Never use outside or general knowledge.
- Every claim must be supported by a citation. "document_name" must exactly match the name attribute \
of a <document> tag, and "quote" must be copied VERBATIM from that document: one contiguous span of \
its text, with no ellipses, no paraphrasing and no added words, at most 300 characters.
- Dates in the documents are day-first (Indian convention). Write dates as YYYY-MM-DD and amounts in INR.
"""

ANSWER_SYSTEM = (
    "You are DocuMind, an assistant that answers questions about the user's personal documents.\n"
    + _COMMON_RULES
    + "- If the documents do not contain the answer, return found=false, answer=\"\" and citations=[]. "
    "Never guess.\n"
    "- Keep answers concise, in plain English, with no markdown headings.\n"
)

EXTRACT_SYSTEM = (
    "You are DocuMind, an assistant that extracts key facts from one of the user's personal documents.\n"
    + _COMMON_RULES
    + "- Extract parties, dates, amounts and obligations. Each fact's \"quote\" must be the verbatim "
    "passage it comes from.\n"
    "- For date facts set date_iso (YYYY-MM-DD) and role to one of: due, renewal, expiry, end, "
    "last_date, start, issue, bill, purchase, other.\n"
    "- For amount facts set amount_inr (a number in rupees) and role to one of: premium, rent, "
    "deposit, bill_total, coverage, fee, amount.\n"
    "- If a fact is not in the document, leave it out. Never invent facts.\n"
)


# ---------------------------------------------------------------- errors
class LiveError(Exception):
    user_message: str = "Live mode is unavailable right now."

    def __init__(self, user_message: str | None = None):
        if user_message is not None:
            self.user_message = user_message
        super().__init__(self.user_message)


class LiveAuthError(LiveError):
    user_message = "Your Anthropic API key was rejected. Check the key in the sidebar."


class LivePermissionError(LiveAuthError):
    user_message = ("Your Anthropic API key does not have access to this model. "
                    "Try another model or check the key in the sidebar.")


class LiveRateLimitError(LiveError):
    user_message = "Claude is rate-limiting requests right now. Please wait a moment and try again."


class LiveConnectionError(LiveError):
    user_message = "Couldn't reach the Claude service. Check your internet connection."


class LiveServiceError(LiveError):
    user_message = "The Claude service returned an error. Please try again later."


class LiveMalformedError(LiveError):
    user_message = "Claude returned an unexpected response, so it was not shown."


class LiveRefusalError(LiveError):
    user_message = "Claude declined to answer this question."


# ---------------------------------------------------------------- helpers
def make_client(api_key: str) -> "anthropic.Anthropic":
    """Default client factory. The key is passed straight to the SDK and not kept anywhere else."""
    return anthropic.Anthropic(api_key=api_key, max_retries=0, timeout=60)


def estimate_tokens(text: str) -> int:
    return len(text) // 4


def _wrap(parts: Iterable[tuple[str, str]]) -> str:
    body = "\n".join(f'<document name="{name}">\n{text}\n</document>' for name, text in parts)
    return f"<documents>\n{body}\n</documents>"


def _call(client: Any, model: str, system: str, user_content: str, output_format: type) -> Any:
    """Run messages.parse and return parsed_output, mapping every failure to a LiveError.

    ``from None`` suppresses the SDK exception chain so raw text never travels with the error.
    """
    try:
        response = client.messages.parse(
            model=model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user_content}],
            output_format=output_format,
            output_config={"effort": "medium"},
        )
    except anthropic.AuthenticationError:
        raise LiveAuthError() from None
    except anthropic.PermissionDeniedError:
        raise LivePermissionError() from None
    except anthropic.RateLimitError:
        raise LiveRateLimitError() from None
    except anthropic.APIConnectionError:  # includes APITimeoutError
        raise LiveConnectionError() from None
    except anthropic.APIStatusError:
        raise LiveServiceError() from None
    except ValidationError:
        raise LiveMalformedError() from None
    except anthropic.APIError:
        raise LiveServiceError() from None

    stop = getattr(response, "stop_reason", None)
    if stop == "refusal":
        raise LiveRefusalError()
    if stop in {"max_tokens", "model_context_window_exceeded"}:
        raise LiveMalformedError()
    parsed = getattr(response, "parsed_output", None)
    if parsed is None:
        raise LiveMalformedError()
    if not isinstance(parsed, output_format):
        try:
            parsed = output_format.model_validate(parsed)
        except ValidationError:
            raise LiveMalformedError() from None
    return parsed


ChunkSource = Any  # BM25Index-like (has .search), callable(question, k), or a precomputed list


def _fallback_chunks(index: ChunkSource, question: str, k: int) -> list[Chunk]:
    if index is None:
        return []
    if callable(index) and not hasattr(index, "search"):
        hits = index(question, k)
    elif hasattr(index, "search"):
        hits = index.search(question, k=k)
    else:
        hits = index
    chunks: list[Chunk] = []
    for h in list(hits)[:k]:
        chunks.append(h[0] if isinstance(h, tuple) else h)
    return chunks


def build_answer_content(question: str, docs: list[Document],
                         index: ChunkSource = None) -> tuple[str, bool]:
    """Return (user_content, used_full_context). Full text when within TOKEN_BUDGET."""
    readable = [d for d in docs if d.readable]
    total = estimate_tokens("".join(d.text for d in readable))
    if total <= TOKEN_BUDGET:
        return _wrap((d.name, d.text) for d in readable) + f"\n\nQuestion: {question}", True

    chunks = _fallback_chunks(index, question, FALLBACK_TOP_K)
    by_doc: dict[str, list[Chunk]] = {}
    for c in chunks:
        by_doc.setdefault(c.doc_id, []).append(c)
    parts = []
    for d in readable:  # keep document order stable
        cs = by_doc.get(d.id)
        if cs:
            cs = sorted(cs, key=lambda c: c.index)
            parts.append((d.name, "\n...\n".join(c.text for c in cs)))
    return _wrap(parts) + f"\n\nQuestion: {question}", False


# ---------------------------------------------------------------- public API
def answer_live(client: Any, model: str, question: str, docs: list[Document],
                index: ChunkSource = None) -> Answer:
    """Ask Claude. Raises LiveError. The returned Answer is already passed through verify_answer.

    ``index`` is only used when the documents exceed TOKEN_BUDGET. It may be a BM25Index-like
    object (``.search(question, k=12)``), a callable ``(question, k) -> hits``, or a precomputed
    list of hits; a hit is a ``Chunk`` or a ``(Chunk, score)`` tuple. Callers should retrieve
    WITHOUT the relevance threshold so recall stays high.
    """
    readable = [d for d in docs if d.readable]
    content, _full = build_answer_content(question, readable, index)
    parsed: LLMAnswer = _call(client, model, ANSWER_SYSTEM, content, LLMAnswer)

    if not parsed.found or not parsed.citations or not parsed.answer.strip():
        return Answer.not_found(question, "live")
    citations = [Citation(doc_name=c.document_name, quote=c.quote)
                 for c in parsed.citations if c.quote and c.quote.strip()]
    if not citations:
        return Answer.not_found(question, "live")
    answer = Answer(question=question, text=parsed.answer.strip(), found=True,
                    citations=citations, mode="live")
    return verify_answer(answer, {d.name: d for d in readable})


def _convert_fact(f: Any, doc: Document) -> KeyFact | None:
    role = (f.role or "").strip()
    date_value = None
    amount = None
    if f.category == "date":
        try:
            date_value = date.fromisoformat((f.date_iso or "").strip())
        except ValueError:
            return None
        if role not in _DATE_ROLES:
            role = "other"
    elif f.category == "amount":
        if f.amount_inr is None:
            return None
        try:
            amount = Decimal(str(f.amount_inr))
        except InvalidOperation:
            return None
        if not amount.is_finite() or amount < 0:
            return None
        if role not in _AMOUNT_ROLES:
            role = "amount"
    try:
        return KeyFact(category=f.category, role=role or "other", label=f.label, value=f.value,
                       date_value=date_value, amount_inr=amount, source_quote=f.quote,
                       doc_id=doc.id, doc_name=doc.name)
    except ValidationError:
        return None


def extract_live(client: Any, model: str, doc: Document) -> DocumentSummary:
    """Extract key facts with Claude. Raises LiveError. Result is passed through verify_summary."""
    notices: list[str] = []
    text = doc.text
    if estimate_tokens(text) > TOKEN_BUDGET:
        text = text[: TOKEN_BUDGET * 4]
        notices.append(LARGE_DOC_NOTICE)
    content = _wrap([(doc.name, text)]) + "\n\nExtract key facts from this document."
    parsed: LLMExtraction = _call(client, model, EXTRACT_SYSTEM, content, LLMExtraction)

    buckets: dict[str, list[KeyFact]] = {"party": [], "date": [], "amount": [], "obligation": []}
    for f in parsed.facts:
        kf = _convert_fact(f, doc)
        if kf is not None:
            buckets[kf.category].append(kf)
    summary = DocumentSummary(
        doc_id=doc.id, doc_name=doc.name, doc_type=parsed.doc_type, produced_by="live",
        model=model, parties=buckets["party"], dates=buckets["date"],
        amounts=buckets["amount"], obligations=buckets["obligation"], notices=notices,
    )
    return verify_summary(summary, doc)


__all__ = [
    "MODELS", "DEFAULT_MODEL", "TOKEN_BUDGET", "ANSWER_SYSTEM", "EXTRACT_SYSTEM",
    "LiveError", "LiveAuthError", "LivePermissionError", "LiveRateLimitError",
    "LiveConnectionError", "LiveServiceError", "LiveMalformedError", "LiveRefusalError",
    "make_client", "estimate_tokens", "build_answer_content", "answer_live", "extract_live",
]
