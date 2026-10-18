"""Upcoming deadlines derived from verified date facts."""
from __future__ import annotations

from datetime import date

from docmind.models import Deadline, DocumentSummary, KeyFact

DEADLINE_ROLES = {"due", "renewal", "expiry", "end", "last_date"}
# One date often appears under two roles ("renewal on X" and "period ... to X"): keep the most useful.
_ROLE_RANK = {"due": 0, "renewal": 1, "last_date": 2, "expiry": 3, "end": 4}
# Dates this far in the past are history (e.g. a clause effective from 2002), not a missed deadline.
MAX_DAYS_OVERDUE = 365
_STATUS_TEXT = {"overdue": "Overdue", "within_30": "Within 30 days", "later": "Later"}


def status_for(days: int) -> str:
    return "overdue" if days < 0 else "within_30" if days <= 30 else "later"


def collect_deadlines(summaries: list[DocumentSummary], today: date) -> list[Deadline]:
    best: dict[tuple[str, date], KeyFact] = {}
    for s in summaries:
        for f in s.dates:
            if f.date_value is None or f.role not in DEADLINE_ROLES:
                continue
            if (f.date_value - today).days < -MAX_DAYS_OVERDUE:
                continue
            key = (f.doc_id, f.date_value)
            if key not in best or _ROLE_RANK[f.role] < _ROLE_RANK[best[key].role]:
                best[key] = f
    out = []
    for f in best.values():
        days = (f.date_value - today).days
        st = status_for(days)
        out.append(Deadline(label=f.label, role=f.role, date=f.date_value, days_remaining=days,
                            status=st, status_text=_STATUS_TEXT[st], doc_id=f.doc_id,
                            doc_name=f.doc_name, source_quote=f.source_quote))
    return sorted(out, key=lambda d: (d.date, d.doc_name, d.label))
