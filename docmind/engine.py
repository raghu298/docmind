"""Engine facade: settings, per-session document store, mode routing and Live→Demo fallback.

`app.py` talks only to this module. No Streamlit imports here (Principle IV).
See specs/001-document-intelligence-assistant/contracts/engine-api.md.
"""
from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from docmind import llm_engine
from docmind.chunking import chunk_document
from docmind.deadlines import collect_deadlines
from docmind.extract_demo import extract
from docmind.llm_engine import LiveError
from docmind.models import NOT_FOUND, Answer, Chunk, Citation, Deadline, Document, DocumentSummary, Mode
from docmind.parsing import ParseError, load_file
from docmind.retrieval import BM25Index, tokenize
from docmind.samples import build_samples
from docmind.verify import verify_answer, verify_summary

__all__ = [
    "MODELS", "DEFAULT_MODEL", "NOT_FOUND", "SUGGESTED_QUESTIONS", "Settings", "DocumentStore",
    "load_samples", "add_upload", "remove_document", "list_documents", "summarize",
    "cached_summary", "pending_live_summaries", "ensure_live_summaries", "clear_live_failures",
    "deadlines", "ask", "fact_count", "format_inr", "human_size", "days_text",
]

MODELS: tuple[str, ...] = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5")
DEFAULT_MODEL: str = "claude-opus-5-5"

SUGGESTED_QUESTIONS: tuple[str, str, str, str] = (
    "What is the notice period for my rental agreement?",
    "Which of my policies expire this year?",
    "When is my broadband bill due and how much do I owe?",
    "What is my passport number?",  # index 3: not answerable from the samples
)

NO_DOCS_NOTICE = "Upload documents or load the samples to start asking questions."
NO_KEY_NOTICE = "Live mode needs an API key — answered in Demo mode."
DEMO_INSTEAD = "Answered in Demo mode instead."
LIVE_SUMMARY_FAILED = "Live extraction failed — showing Demo results."
GENERIC_LIVE_ERROR = "The Claude service returned an error. Please try again later."


# --------------------------------------------------------------------------- settings
class Settings(BaseModel):
    """Per-request settings. Frozen; the key is never part of repr or serialisation."""

    model_config = ConfigDict(frozen=True)

    mode: Mode = "demo"
    model: str = DEFAULT_MODEL
    api_key: SecretStr | None = Field(default=None, repr=False, exclude=True)

    @field_validator("model")
    @classmethod
    def _known_model(cls, v: str) -> str:
        if v not in MODELS:
            raise ValueError(f"model must be one of {MODELS}")
        return v

    @property
    def has_key(self) -> bool:
        return self.api_key is not None and bool(self.api_key.get_secret_value().strip())

    @classmethod
    def from_inputs(cls, mode: str, model: str | None, pasted_key: str | None,
                    env: Mapping[str, str] | None = None) -> "Settings":
        """Pasted key wins; otherwise env ``ANTHROPIC_API_KEY``; blank → None."""
        env = os.environ if env is None else env
        mode_norm = "live" if str(mode).strip().lower() == "live" else "demo"
        key = (pasted_key or "").strip() or (env.get("ANTHROPIC_API_KEY") or "").strip()
        return cls(mode=mode_norm, model=model or DEFAULT_MODEL,
                   api_key=SecretStr(key) if key else None)


# --------------------------------------------------------------------------- store
class DocumentStore:
    """Session-scoped state, mutated only through engine functions."""

    def __init__(self) -> None:
        self.docs: dict[str, Document] = {}                      # name -> Document
        self.chunks: dict[str, list[Chunk]] = {}                 # doc_id -> chunks
        self.summaries: dict[tuple[str, str], DocumentSummary] = {}  # (doc_id, "demo"|model)
        self.live_failures: dict[tuple[str, str], list[str]] = {}    # (doc_id, model) -> notices
        self.rejected: list[str] = []
        self._index: BM25Index | None = None
        self._index_key: frozenset[str] | None = None

    def readable_docs(self) -> list[Document]:
        return [d for d in self.docs.values() if d.readable]

    @property
    def index(self) -> BM25Index | None:
        """BM25 index over all readable docs; rebuilt lazily when the doc set changes."""
        key = frozenset(d.id for d in self.readable_docs())
        if key != self._index_key:
            all_chunks = [c for d in self.readable_docs() for c in self.chunks.get(d.id, [])]
            self._index = BM25Index(all_chunks) if all_chunks else None
            self._index_key = key
        return self._index


def _add(store: DocumentStore, doc: Document) -> Document:
    if doc.name in store.docs:  # same name re-added → replaces previous
        remove_document(store, doc.name)
    if doc.readable:
        summary = verify_summary(extract(doc), doc)
        doc = doc.model_copy(update={"doc_type": summary.doc_type})
        store.chunks[doc.id] = chunk_document(doc)
        store.summaries[(doc.id, "demo")] = summary
    store.docs[doc.name] = doc
    return doc


def load_samples(store: DocumentStore, today: date) -> list[str]:
    """Idempotent: adds the bundled samples once (by name); returns names added."""
    added: list[str] = []
    for doc in build_samples(today):
        if doc.name not in store.docs:
            _add(store, doc)
            added.append(doc.name)
    return added


def add_upload(store: DocumentStore, name: str, data: bytes) -> Document | None:
    """Parse and add an upload. On rejection returns None and records a friendly message."""
    try:
        doc = load_file(name, data, "upload")
    except ParseError as exc:
        msg = getattr(exc, "user_message", "") or "This file could not be read"
        store.rejected.append(msg if name in msg else f"{name}: {msg}")
        return None
    except Exception:  # never crash the app on a bad file
        store.rejected.append(f"{name}: This file could not be read")
        return None
    return _add(store, doc)


def remove_document(store: DocumentStore, name: str) -> None:
    """Purge a document from docs, chunks, index and summaries (FR-006)."""
    doc = store.docs.pop(name, None)
    if doc is None:
        return
    if any(d.id == doc.id for d in store.docs.values()):
        return  # identical content still loaded under another name
    store.chunks.pop(doc.id, None)
    for k in [k for k in store.summaries if k[0] == doc.id]:
        del store.summaries[k]
    for k in [k for k in store.live_failures if k[0] == doc.id]:
        del store.live_failures[k]
    store._index_key = None  # force rebuild


def list_documents(store: DocumentStore) -> list[Document]:
    return list(store.docs.values())


# --------------------------------------------------------------------------- live client
def _default_client_factory(settings: Settings) -> Any:
    import anthropic

    return anthropic.Anthropic(api_key=settings.api_key.get_secret_value(),  # type: ignore[union-attr]
                               max_retries=0, timeout=60)


def _live_ready(settings: Settings) -> bool:
    return settings.mode == "live" and settings.has_key


def _friendly(exc: BaseException) -> str:
    return getattr(exc, "user_message", None) or GENERIC_LIVE_ERROR


# --------------------------------------------------------------------------- summaries
def _empty_summary(doc: Document, notices: list[str] | None = None) -> DocumentSummary:
    return DocumentSummary(doc_id=doc.id, doc_name=doc.name, doc_type=doc.doc_type,
                           produced_by="demo", notices=list(notices or []))


def _demo_summary(store: DocumentStore, doc: Document) -> DocumentSummary:
    s = store.summaries.get((doc.id, "demo"))
    if s is None:
        if not doc.readable:
            return _empty_summary(doc, ["No readable text — scanned documents are not supported"])
        s = verify_summary(extract(doc), doc)
        store.summaries[(doc.id, "demo")] = s
    return s


def cached_summary(store: DocumentStore, doc_name: str, settings: Settings) -> DocumentSummary:
    """Best summary available without any network call (for rendering on every rerun)."""
    doc = store.docs[doc_name]
    if settings.mode == "live":
        live = store.summaries.get((doc.id, settings.model))
        if live is not None:
            return live
        failed = store.live_failures.get((doc.id, settings.model))
        if failed:
            demo = _demo_summary(store, doc)
            return demo.model_copy(update={"notices": [*demo.notices, *failed]})
    return _demo_summary(store, doc)


def summarize(store: DocumentStore, doc_name: str, settings: Settings, *,
              client_factory: Callable[[Settings], Any] | None = None) -> DocumentSummary:
    """Demo summary is cached on add; the Live summary is computed once per (doc_id, model)."""
    doc = store.docs[doc_name]
    if not doc.readable or not _live_ready(settings):
        return _demo_summary(store, doc)
    key = (doc.id, settings.model)
    if key in store.summaries:
        return store.summaries[key]
    if key in store.live_failures:
        return cached_summary(store, doc_name, settings)
    try:
        client = (client_factory or _default_client_factory)(settings)
        live = verify_summary(llm_engine.extract_live(client, settings.model, doc), doc)
    except Exception as exc:  # LiveError or anything unexpected: never raise to the UI
        store.live_failures[key] = [_friendly(exc) if isinstance(exc, LiveError) else GENERIC_LIVE_ERROR,
                                    LIVE_SUMMARY_FAILED]
        return cached_summary(store, doc_name, settings)
    store.summaries[key] = live
    return live


def pending_live_summaries(store: DocumentStore, settings: Settings) -> list[str]:
    """Names of readable docs that still need a Live extraction for the current model."""
    if settings.mode != "live":
        return []
    return [d.name for d in store.readable_docs()
            if (d.id, settings.model) not in store.summaries
            and (d.id, settings.model) not in store.live_failures]


def ensure_live_summaries(store: DocumentStore, settings: Settings, *,
                          client_factory: Callable[[Settings], Any] | None = None,
                          limit: int | None = None) -> list[str]:
    """Run Live extraction for docs lacking one (at most `limit`); returns friendly notices."""
    if not _live_ready(settings):
        return []
    notices: list[str] = []
    names = pending_live_summaries(store, settings)
    if limit is not None:
        names = names[:max(0, limit)]
    for name in names:
        doc = store.docs[name]
        summarize(store, name, settings, client_factory=client_factory)
        failed = store.live_failures.get((doc.id, settings.model))
        if failed:
            msg = f"{failed[0]} Live extraction failed for {name} — showing Demo results."
            notices.append(msg)
            # Auth/connection problems will fail for every doc: stop early, mark the rest.
            if failed[0] not in (GENERIC_LIVE_ERROR,) and not failed[0].startswith("Claude returned"):
                for rest in names[names.index(name) + 1:]:
                    rid = store.docs[rest].id
                    store.live_failures.setdefault((rid, settings.model), list(failed))
                break
    return notices


def clear_live_failures(store: DocumentStore) -> None:
    """Forget failed Live extractions (call when the key/access code changes) so they retry."""
    store.live_failures.clear()


def deadlines(store: DocumentStore, settings: Settings, today: date) -> list[Deadline]:
    """Deadlines across docs, using the best cached summary per doc (no network)."""
    summaries = [cached_summary(store, d.name, settings) for d in store.readable_docs()]
    return collect_deadlines(summaries, today)


def fact_count(store: DocumentStore, settings: Settings) -> int:
    total = 0
    for d in store.readable_docs():
        s = cached_summary(store, d.name, settings)
        total += len(s.parties) + len(s.dates) + len(s.amounts) + len(s.obligations)
    return total


# --------------------------------------------------------------------------- ask
# split on line breaks or sentence ends, but not after abbreviations like "Rs." / "No."
_SENT_SPLIT = re.compile(r"(?<!\bRs)(?<!\bNo)(?<!\bMr)(?<=[.!?])\s+(?=[A-Z])|\n+")


def _best_sentence(text: str, question: str) -> str:
    """The sentence/line of `text` sharing the most query terms (verbatim slice of the chunk)."""
    q = set(tokenize(question))
    best, best_score = "", -1
    for sent in _SENT_SPLIT.split(text):
        sent = sent.strip()
        if not sent:
            continue
        score = len(q & set(tokenize(sent)))
        if score > best_score:
            best, best_score = sent, score
    return best or text.strip()


def _line_score(sent: str, question: str) -> tuple[float, int]:
    """Query-term overlap, plus a bonus for lines carrying a date or amount (the usual answer)."""
    overlap = len(set(tokenize(question)) & set(tokenize(sent)))
    has_value = bool(re.search(r"\d", sent))
    return (overlap + (1.5 if has_value else 0), -len(sent))


def _demo_answer(store: DocumentStore, question: str) -> Answer:
    index = store.index
    hits = index.search(question, k=3) if index is not None else []
    if not hits:
        return Answer.not_found(question, "demo")
    order: list[str] = []
    grouped: dict[str, list[Chunk]] = {}
    for chunk, _score in hits[:3]:
        if chunk.doc_name not in grouped:
            order.append(chunk.doc_name)
            grouped[chunk.doc_name] = []
        grouped[chunk.doc_name].append(chunk)
    citations = [Citation(doc_name=c.doc_name, doc_id=c.doc_id, quote=c.text, start=c.start)
                 for name in order for c in grouped[name]]
    # pick the best line across all hit chunks, so a title line can't win over the real answer
    text = max((_best_sentence(c.text, question) for c, _ in hits[:3]),
               key=lambda sent: _line_score(sent, question))
    return Answer(question=question, text=text, found=True, citations=citations, mode="demo")


def ask(store: DocumentStore, question: str, settings: Settings, *,
        client_factory: Callable[[Settings], Any] | None = None) -> Answer:
    """Answer one question (history is never used as context). Never raises."""
    question = (question or "").strip()
    docs = store.readable_docs()
    docs_by_name = {d.name: d for d in docs}
    if not docs:
        return Answer.not_found(question, "demo", [NO_DOCS_NOTICE],
                                fell_back=settings.mode == "live")
    if not question:
        return Answer.not_found(question, "demo")

    def demo(notices: list[str] | None = None, fell_back: bool = False) -> Answer:
        try:
            ans = verify_answer(_demo_answer(store, question), docs_by_name)
        except Exception:
            ans = Answer.not_found(question, "demo")
        if notices or fell_back:
            ans = ans.model_copy(update={"notices": [*(notices or []), *ans.notices],
                                         "fell_back": fell_back})
        return ans

    if settings.mode != "live":
        return demo()
    if not settings.has_key:
        return demo([NO_KEY_NOTICE], fell_back=True)
    try:
        client = (client_factory or _default_client_factory)(settings)
        raw = llm_engine.answer_live(client, settings.model, question, docs, store.index)
        return verify_answer(raw, docs_by_name)
    except LiveError as exc:
        return demo([_friendly(exc), DEMO_INSTEAD], fell_back=True)
    except Exception:
        return demo([GENERIC_LIVE_ERROR, DEMO_INSTEAD], fell_back=True)


# --------------------------------------------------------------------------- formatting
def format_inr(amount: Decimal | float | int | None) -> str:
    """₹ with Indian digit grouping, e.g. 125000 → ₹1,25,000; keeps paise when present."""
    if amount is None:
        return ""
    q = Decimal(str(amount))
    whole = int(q)
    frac = q - whole
    s = str(abs(whole))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    out = f"₹{'-' if whole < 0 else ''}{s}"
    if frac:
        out += f".{int(round(abs(frac) * 100)):02d}"
    return out


def human_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def days_text(days_remaining: int) -> str:
    if days_remaining == 0:
        return "Due today"
    if days_remaining > 0:
        return f"in {days_remaining} day{'s' if days_remaining != 1 else ''}"
    n = -days_remaining
    return f"{n} day{'s' if n != 1 else ''} ago"
