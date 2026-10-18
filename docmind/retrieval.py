"""Pure-Python Okapi BM25 retrieval with a relevance threshold (Demo mode, research R6).

A chunk is returned only if BOTH hold:
  * its BM25 score >= MIN_SCORE, and
  * its IDF-weighted query coverage >= MIN_COVERAGE, where coverage is
    sum(idf of query terms present in the chunk) / sum(idf of all query terms).
    Query terms never seen in the corpus count with the maximum possible idf,
    so a question about something absent ("passport number") cannot be carried
    by one common word ("number").
If nothing qualifies, the caller answers "Not found in your documents".
"""
from __future__ import annotations

import math
import re
from collections import Counter

from docmind.models import Chunk

MIN_SCORE: float = 1.0
MIN_COVERAGE: float = 0.5
MAX_RESULTS: int = 3

STOPWORDS: frozenset[str] = frozenset("""
a an the and or but if of to for in on at by with from as into onto about over under
is are was were be been being am do does did done have has had having can could will would
shall should may might must i me my mine we our ours you your yours he she it its they them
their this that these those there here what when where which who whom whose why how
much many any some all each every no not nor so than too very just also only own same
please tell show give find get know let s t
""".split())

_TOKEN_RE = re.compile(r"[a-z0-9₹]+")
# Identifiers such as HLT-2026-004512 or MH/12/AB/1234 also produce one joined token.
_COMPOUND_RE = re.compile(r"[a-z0-9]+(?:[-/][a-z0-9]+)+")


def _stem(tok: str) -> str:
    """Very light suffix stemmer (min stem length 3); only for purely alphabetic tokens."""
    if not tok.isalpha() or len(tok) <= 3:
        return tok

    def cut(word: str, suffix: str, repl: str = "") -> str | None:
        if word.endswith(suffix):
            new = word[: len(word) - len(suffix)] + repl
            if len(new) >= 3:
                return new
        return None

    w = tok
    for suffix, repl in (("ies", "y"), ("es", ""), ("ing", ""), ("ed", ""), ("al", "")):
        new = cut(w, suffix, repl)
        if new is not None:
            w = new
            break
    else:
        if w.endswith("s") and not w.endswith("ss"):
            new = cut(w, "s")
            if new is not None:
                w = new
    # Fold trailing e / y so expire/expires/expiry and policy/policies meet.
    for suffix in ("e", "y"):
        new = cut(w, suffix)
        if new is not None:
            w = new
            break
    return w


def tokenize(text: str) -> list[str]:
    """Lowercase, split on non-alphanumerics (keeping digits and ₹), drop stopwords, stem.

    Compound identifiers (``HLT-2026-0045``) additionally yield a joined token
    (``hlt20260045``) so an exact policy / account number matches strongly.
    """
    low = text.lower()
    out: list[str] = []
    for tok in _TOKEN_RE.findall(low):
        if tok in STOPWORDS:
            continue
        out.append(_stem(tok))
    for comp in _COMPOUND_RE.findall(low):
        if any(ch.isdigit() for ch in comp):
            out.append(re.sub(r"[-/]", "", comp))
    return out


class BM25Index:
    """Okapi BM25 over chunks. ``BM25Index(chunks)`` or ``BM25Index().build(chunks)``."""

    def __init__(self, chunks: list[Chunk] | None = None, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.chunks: list[Chunk] = []
        self._tfs: list[Counter[str]] = []
        self._lens: list[int] = []
        self._df: Counter[str] = Counter()
        self._avgdl = 0.0
        self.build(chunks or [])

    def build(self, chunks: list[Chunk]) -> "BM25Index":
        self.chunks = list(chunks)
        # include the document name so a passage like "Renewal: ... due on ..." still matches
        # "health insurance renewal" when the words only appear in the file name
        self._tfs = [Counter(tokenize(c.text + " " + c.doc_name.replace("_", " ")))
                     for c in self.chunks]
        self._lens = [sum(tf.values()) for tf in self._tfs]
        self._df = Counter()
        for tf in self._tfs:
            self._df.update(tf.keys())
        self._avgdl = (sum(self._lens) / len(self._lens)) if self._lens else 0.0
        return self

    def __len__(self) -> int:
        return len(self.chunks)

    @property
    def n(self) -> int:
        return len(self.chunks)

    def idf(self, term: str) -> float:
        df = self._df.get(term, 0)
        return math.log(1 + (self.n - df + 0.5) / (df + 0.5))

    def _score(self, i: int, terms: list[str]) -> tuple[float, float]:
        """Return (bm25 score, matched idf sum) for chunk i."""
        tf = self._tfs[i]
        dl = self._lens[i]
        norm = self.k1 * (1 - self.b + self.b * (dl / self._avgdl if self._avgdl else 0.0))
        score = 0.0
        matched = 0.0
        for t in terms:
            f = tf.get(t, 0)
            if not f:
                continue
            idf = self.idf(t)
            matched += idf
            score += idf * f * (self.k1 + 1) / (f + norm)
        return score, matched

    def search(self, query: str, k: int = MAX_RESULTS) -> list[tuple[Chunk, float]]:
        """Top-k chunks meeting MIN_SCORE and MIN_COVERAGE, grouped by document.

        Ranking ties break on (doc_name, chunk.start). The (at most k) hits are then
        grouped by document, documents ordered by their best hit's rank.
        """
        if not self.chunks or k <= 0:
            return []
        terms = list(dict.fromkeys(tokenize(query)))  # unique, order-preserving
        if not terms:
            return []
        total_idf = sum(self.idf(t) for t in terms)  # unseen terms get idf_max automatically
        if total_idf <= 0:
            return []
        hits: list[tuple[Chunk, float]] = []
        for i, chunk in enumerate(self.chunks):
            score, matched = self._score(i, terms)
            if score >= MIN_SCORE and matched / total_idf >= MIN_COVERAGE:
                hits.append((chunk, score))
        hits.sort(key=lambda h: (-h[1], h[0].doc_name, h[0].start))
        top = hits[:k]
        order: dict[str, int] = {}
        for chunk, _ in top:
            order.setdefault(chunk.doc_id, len(order))
        # stable sort keeps score order inside each document group
        return sorted(top, key=lambda h: order[h[0].doc_id])
