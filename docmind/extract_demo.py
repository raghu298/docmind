"""Deterministic Demo-mode extraction (research R8).

Regex dates (day-first Indian formats) and INR amounts, keyword document typing, cue-based
date/amount roles, party lines and obligation sentences. Every KeyFact.source_quote is a
slice of ``doc.text`` (a stripped sentence or line), so it verifies by construction.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from docmind.models import DateRole, DocType, Document, DocumentSummary, KeyFact

# --------------------------------------------------------------------------- dates
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MON = (r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
        r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)")
_ORD = r"(?:st|nd|rd|th)?"

_RE_NUM = re.compile(r"(?<![\d/.\-])(\d{1,2})([/.\-])(\d{1,2})\2(\d{4})(?!\d)")
_RE_ISO = re.compile(r"(?<![\d/.\-])(\d{4})-(\d{1,2})-(\d{1,2})(?![\d\-/])")
_RE_DMY = re.compile(rf"(?<![\d/.\-])(\d{{1,2}}){_ORD}(?:\s+of)?(?:\s+|-){_MON}\b\.?(?:,?\s+|-)(\d{{4}})(?!\d)",
                     re.IGNORECASE)
_RE_MDY = re.compile(rf"\b{_MON}\b\.?\s+(\d{{1,2}}){_ORD},?\s+(\d{{4}})(?!\d)", re.IGNORECASE)


def _mk_date(y: str, m: str | int, d: str) -> date | None:
    try:
        month = m if isinstance(m, int) else int(m)
        return date(int(y), month, int(d))
    except (ValueError, TypeError):
        return None


def find_dates(text: str) -> list[tuple[date, int, int]]:
    """All valid day-first dates as (value, start, end), in text order, non-overlapping."""
    found: list[tuple[date, int, int]] = []
    for m in _RE_NUM.finditer(text):
        v = _mk_date(m.group(4), m.group(3), m.group(1))
        if v:
            found.append((v, m.start(), m.end()))
    for m in _RE_ISO.finditer(text):
        v = _mk_date(m.group(1), m.group(2), m.group(3))
        if v:
            found.append((v, m.start(), m.end()))
    for m in _RE_DMY.finditer(text):
        v = _mk_date(m.group(3), _MONTHS[m.group(2)[:3].lower()], m.group(1))
        if v:
            found.append((v, m.start(), m.end()))
    for m in _RE_MDY.finditer(text):
        v = _mk_date(m.group(3), _MONTHS[m.group(1)[:3].lower()], m.group(2))
        if v:
            found.append((v, m.start(), m.end()))
    found.sort(key=lambda t: (t[1], -(t[2] - t[1])))
    out: list[tuple[date, int, int]] = []
    last_end = -1
    for item in found:
        if item[1] >= last_end:
            out.append(item)
            last_end = item[2]
    return out


# --------------------------------------------------------------------------- amounts
_RE_AMT = re.compile(
    r"(?:₹|(?<![A-Za-z])(?:Rs|RS|rs|INR|inr)\b\.?)\s*"
    r"(\d{1,3}(?:,\d{3})+(?!,?\d)|\d{1,3}(?:,\d{2})*,\d{3}(?!,?\d)|\d+)"
    r"(\.\d{1,2})?"
    r"(?:\s*/-)?"
    r"(?:\s*(lakhs?|lacs?|crores?)\b)?",
)
_MULT = {"lakh": Decimal(100000), "lac": Decimal(100000), "crore": Decimal(10000000)}


def find_amounts(text: str) -> list[tuple[Decimal, int, int]]:
    """INR amounts (₹, Rs., Rs, INR; lakh-style commas; /-; lakh/crore) as (value, start, end)."""
    out: list[tuple[Decimal, int, int]] = []
    for m in _RE_AMT.finditer(text):
        try:
            value = Decimal(m.group(1).replace(",", "") + (m.group(2) or ""))
        except InvalidOperation:
            continue
        if m.group(3):
            word = m.group(3).lower().rstrip("s")
            value *= _MULT[word]
        out.append((value, m.start(), m.end()))
    return out


# --------------------------------------------------------------------------- sentences
_ABBREV = {"rs", "no", "mr", "mrs", "ms", "dr", "ltd", "pvt", "co", "st", "sr", "jr", "vs",
           "inc", "approx", "e.g", "i.e", "nos", "a/c", "ac", "sl", "regd", "dt"}
_SENT_BREAK = re.compile(r"[.!?]\s+(?=[A-Z(\"'₹*])")


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    """Stripped (start, end) spans of sentences; a newline always ends a sentence."""
    spans: list[tuple[int, int]] = []
    pos = 0
    for line in text.split("\n"):
        line_start = pos
        pos += len(line) + 1
        seg_start = 0
        for m in _SENT_BREAK.finditer(line):
            before = line[seg_start:m.start()]
            word = re.split(r"\s+", before.strip())[-1].lower() if before.strip() else ""
            if word in _ABBREV or (len(word) == 1 and word.isalpha()) or word.endswith(".")\
                    or re.fullmatch(r"[a-z]\.[a-z]", word):
                continue
            spans.append((line_start + seg_start, line_start + m.start() + 1))
            seg_start = m.end()
        spans.append((line_start + seg_start, line_start + len(line)))
    out = []
    for s, e in spans:
        seg = text[s:e]
        ls = len(seg) - len(seg.lstrip())
        rs = len(seg.rstrip())
        if rs > ls:
            out.append((s + ls, s + rs))
    return out


def _span_for(spans: list[tuple[int, int]], start: int, end: int) -> tuple[int, int]:
    for s, e in spans:
        if s <= start and end <= e:
            return s, e
    # match crosses a sentence boundary: widen to cover it
    s = max((sp[0] for sp in spans if sp[0] <= start), default=start)
    e = min((sp[1] for sp in spans if sp[1] >= end), default=end)
    return s, e


# --------------------------------------------------------------------------- date roles
_DATE_CUES: list[tuple[str, re.Pattern[str]]] = [
    ("renewal", re.compile(r"auto[- ]?renew\w*|renew\w*|next due(?: date)?|next billing(?: date)?", re.I)),
    ("due", re.compile(r"due date|due on|due by|pay by|payment due|pay before|\bdue\b", re.I)),
    ("expiry", re.compile(r"expir\w*|valid till|valid upto|valid up to|valid until|valid thru"
                          r"|warranty ends|warranty end date|coverage ends", re.I)),
    ("end", re.compile(r"end date|ends? on|terminat\w*|lease end\w*|end of (?:the )?(?:lease|term|agreement)"
                       r"|\btill\b|\buntil\b|\bupto\b", re.I)),
    ("last_date", re.compile(r"last date|notice by|on or before|no later than|latest by|deadline", re.I)),
    ("start", re.compile(r"start\w*|commenc\w*|effective|\bfrom\b|w\.e\.f|joining date|\bjoined\b"
                         r"|inception|activation|activated", re.I)),
    ("issue", re.compile(r"issued?\b|issue date|date of issue|\bdated\b", re.I)),
    ("bill", re.compile(r"bill(?:ing)? date|statement date|bill(?:ing)? period|bill generated", re.I)),
    ("purchase", re.compile(r"purchas\w*|invoice\w*|\bbought\b|date of sale", re.I)),
]
_DATE_PRIORITY = {role: i for i, (role, _) in enumerate(_DATE_CUES)}
_RANGE_CONNECTOR = re.compile(r"^\s*(?:to|till|until|upto|-|–|—|and)\s*$", re.I)


def _best_cue(cues, window: str, before: bool) -> tuple[str, str] | None:
    best = None
    for role, rx in cues:
        for m in rx.finditer(window):
            dist = (len(window) - m.end()) if before else m.start()
            key = (dist, _DATE_PRIORITY.get(role, 0) if cues is _DATE_CUES else 0)
            if best is None or key < best[0]:
                best = (key, role, m.group(0))
    return (best[1], best[2]) if best else None


def _date_role_and_cue(text: str, start: int, end: int,
                       spans: list[tuple[int, int]] | None = None,
                       dates: list[tuple[date, int, int]] | None = None) -> tuple[DateRole, str]:
    spans = spans if spans is not None else _sentence_spans(text)
    s_start, s_end = _span_for(spans, start, end)
    dates = dates if dates is not None else find_dates(text)
    prev_end = max((d[2] for d in dates if d[2] <= start and d[2] > s_start), default=None)
    next_start = min((d[1] for d in dates if d[1] >= end and d[1] < s_end), default=None)

    w_from = max(s_start, start - 80, prev_end if prev_end is not None else s_start)
    before = text[w_from:start]
    # "01/12/2025 to 30/11/2026": second date of a range inherits from the first
    if prev_end is not None and _RANGE_CONNECTOR.match(before):
        prev = next(d for d in dates if d[2] == prev_end)
        prev_role, _ = _date_role_and_cue(text, prev[1], prev[2], spans, dates)
        return ("bill" if prev_role == "bill" else "end"), before.strip()
    hit = _best_cue(_DATE_CUES, before, before=True)
    if hit:
        return hit  # type: ignore[return-value]
    w_to = min(s_end, end + 30, next_start if next_start is not None else s_end)
    hit = _best_cue(_DATE_CUES, text[end:w_to], before=False)
    if hit:
        return hit  # type: ignore[return-value]
    return "other", ""


def label_date_role(text: str, start: int, end: int) -> DateRole:
    """Role of the date at text[start:end] from the nearest cue word in its sentence."""
    return _date_role_and_cue(text, start, end)[0]


_INS = ("Health insurance", "Car insurance")


def _date_label(role: str, doc_type: str, context: str) -> str:
    prev = "Previous " if re.search(r"\b(?:previous|earlier|past|last month'?s?)\b", context, re.I) else ""
    if role == "renewal":
        base = ("Policy renewal" if doc_type in _INS else
                "Subscription renewal" if doc_type == "Subscription" else "Renewal")
    elif role == "due":
        base = ("Bill due" if doc_type == "Utility/Telecom bill" else
                "Rent due" if doc_type == "Rental agreement" else "Payment due")
    elif role == "expiry":
        base = ("Policy expiry" if doc_type in _INS else
                "Warranty expiry" if doc_type == "Warranty" else
                "Subscription expiry" if doc_type == "Subscription" else "Expiry")
    elif role == "end":
        base = ("Lease end" if doc_type == "Rental agreement" else
                "Warranty end" if doc_type == "Warranty" else
                "Policy end" if doc_type in _INS else "End date")
    elif role == "last_date":
        base = "Notice deadline" if doc_type == "Rental agreement" else "Last date"
    elif role == "start":
        base = ("Policy start" if doc_type in _INS else
                "Lease start" if doc_type == "Rental agreement" else "Start date")
    else:
        base = {"issue": "Issue date", "bill": "Bill date", "purchase": "Purchase date"}.get(role, "Date")
    if prev and base[0].isupper():
        return prev + base[0].lower() + base[1:]
    return base


# --------------------------------------------------------------------------- amount roles
_AMT_CUES: list[tuple[str, re.Pattern[str]]] = [
    ("premium", re.compile(r"premium", re.I)),
    ("deposit", re.compile(r"deposit|advance", re.I)),
    ("rent", re.compile(r"\brent(?:al)?\b", re.I)),
    ("bill_total", re.compile(r"total|amount payable|amount due|payable|balance|outstanding|\bdue\b", re.I)),
    ("coverage", re.compile(r"sum insured|coverage|\bcover\b|\bidv\b|insured declared value", re.I)),
    ("fee", re.compile(r"\bfees?\b|charges?|subscription|\bplan\b|price|\bcost\b|membership|tariff", re.I)),
]
_AMT_LABEL = {"premium": "Premium", "rent": "Rent", "deposit": "Security deposit",
              "bill_total": "Amount due", "coverage": "Sum insured", "fee": "Fee", "amount": "Amount"}


def _amount_role(text: str, start: int, end: int, s_start: int, s_end: int,
                 amounts: list[tuple[Decimal, int, int]]) -> tuple[str, str]:
    prev_end = max((a[2] for a in amounts if a[2] <= start and a[2] > s_start), default=s_start)
    w_from = max(s_start, start - 60, prev_end)
    hit = _best_cue(_AMT_CUES, text[w_from:start], before=True)
    if hit is None:
        next_start = min((a[1] for a in amounts if a[1] >= end and a[1] < s_end), default=s_end)
        hit = _best_cue(_AMT_CUES, text[end:min(s_end, end + 30, next_start)], before=False)
    if hit is None:
        return "amount", ""
    return hit


def _amount_label(role: str, cue: str, sentence: str) -> str:
    if role == "rent" and re.search(r"month|p\.?m\.?\b|/\s*month", sentence, re.I):
        return "Monthly rent"
    if role == "coverage" and cue.lower() == "idv":
        return "IDV (insured value)"
    if role == "premium" and re.search(r"annual|yearly|per annum", sentence, re.I):
        return "Annual premium"
    if role == "fee" and cue:
        return cue[0].upper() + cue[1:].lower()
    return _AMT_LABEL[role]


# --------------------------------------------------------------------------- doc type
_TYPE_KEYWORDS: list[tuple[DocType, list[str]]] = [
    ("Health insurance", [r"\bhealth\b", r"hospitali[sz]ation", r"sum insured", r"mediclaim",
                          r"cashless", r"pre-existing", r"\bmedical\b"]),
    ("Car insurance", [r"\bmotor\b", r"\bvehicle\b", r"\bidv\b", r"registration no", r"\bcar\b",
                       r"own damage", r"third[- ]party", r"chassis", r"no claim bonus|\bncb\b"]),
    ("Rental agreement", [r"\blease\b", r"\brent\b", r"landlord", r"tenant", r"licensor", r"licensee",
                          r"leave and licen[cs]e", r"rental agreement", r"lock[- ]in"]),
    ("Utility/Telecom bill", [r"\bbill\b", r"broadband", r"\bmobile\b", r"\bdata\b", r"due date",
                              r"account no", r"postpaid", r"electricity", r"\bunits?\b", r"telecom"]),
    ("Warranty", [r"warranty", r"serial no", r"\bpurchase", r"manufacturer", r"defect"]),
    ("Subscription", [r"subscription", r"membership", r"auto[- ]?renew", r"\bplan\b", r"streaming",
                      r"\bgym\b", r"\bott\b"]),
]
_TYPE_RX = [(t, [re.compile(k, re.I) for k in kws]) for t, kws in _TYPE_KEYWORDS]


def classify_doc_type(text: str) -> DocType:
    """Keyword score per type (each keyword counts up to 3 hits); best score >= 2 wins."""
    best: tuple[int, DocType] = (0, "Other")
    for doc_type, rxs in _TYPE_RX:
        score = sum(min(len(rx.findall(text)), 3) for rx in rxs)
        if score > best[0]:
            best = (score, doc_type)
    return best[1] if best[0] >= 2 else "Other"


# --------------------------------------------------------------------------- parties
_PARTY_RE = re.compile(
    r"^[ \t>*#\-•|]*"
    r"(insured(?: person)?|policy ?holder|proposer|landlord|licensor|lessor|owner|tenant|licensee|lessee"
    r"|customer|subscriber|member|account holder|buyer|insurer|insurance company|provider"
    r"|service provider|issued by|seller|dealer|retailer|manufacturer|brand)"
    r"(?:[ \t]+name)?[ \t*]*[:|–-][ \t*|]*(\S[^\n]*?)[ \t*|]*$",
    re.I | re.M,
)
_PARTY_ROLE = {"policy holder": "policyholder", "policyholder": "policyholder",
               "insured person": "insured", "insurance company": "insurer",
               "service provider": "provider", "issued by": "issuer"}


# --------------------------------------------------------------------------- obligations
_OBLIG_CUES: list[tuple[str, re.Pattern[str]]] = [
    ("notice period", re.compile(r"notice period|notice of|months?'? notice|days?'? notice|written notice", re.I)),
    ("lock-in", re.compile(r"lock[- ]in", re.I)),
    ("late fee", re.compile(r"late (?:payment )?(?:fee|charge)|penalt\w*|interest of", re.I)),
    ("payment due", re.compile(r"on or before|before the \d+(?:st|nd|rd|th)|\bpay(?:able)?\b.*\bby\b"
                               r"|\d+(?:st|nd|rd|th) (?:day )?of (?:every|each) month", re.I)),
    ("intimation", re.compile(r"intimat\w*", re.I)),
    ("auto-renewal", re.compile(r"auto[- ]?renew\w*", re.I)),
    ("cancellation", re.compile(r"cancel\w*", re.I)),
    ("time limit", re.compile(r"within \d+ (?:days|hours|months)", re.I)),
    ("obligation", re.compile(r"\bmust\b|\bshall\b|\brequired to\b", re.I)),
]
MAX_OBLIGATIONS = 8


# --------------------------------------------------------------------------- extract
def extract(doc: Document) -> DocumentSummary:
    """Demo-mode summary of one document (deterministic)."""
    text = doc.text
    doc_type = classify_doc_type(text) if doc.readable else "Other"
    summary = DocumentSummary(doc_id=doc.id, doc_name=doc.name, doc_type=doc_type, produced_by="demo")
    if not doc.readable or not text.strip():
        return summary

    spans = _sentence_spans(text)

    def fact(category, role, label, value, quote_span, **kw) -> KeyFact:
        return KeyFact(category=category, role=role, label=label, value=value,
                       source_quote=text[quote_span[0]:quote_span[1]],
                       doc_id=doc.id, doc_name=doc.name, **kw)

    # parties
    parties: list[KeyFact] = []
    seen_p: set[tuple[str, str]] = set()
    for m in _PARTY_RE.finditer(text):
        cue = re.sub(r"\s+", " ", m.group(1).lower())
        role = _PARTY_ROLE.get(cue, cue)
        value = m.group(2).strip()[:80].strip()
        if not value or (role, value) in seen_p:
            continue
        seen_p.add((role, value))
        ls, le = m.start(), m.end()
        seg = text[ls:le]
        ls += len(seg) - len(seg.lstrip())
        le = ls + len(text[ls:le].rstrip())
        parties.append(fact("party", role, role.capitalize() if role != "issuer" else "Issued by",
                            value, (ls, le)))

    # dates
    dates_found = find_dates(text)
    date_facts: list[KeyFact] = []
    seen_d: set[tuple[date, str]] = set()
    for value, s, e in dates_found:
        role, _cue = _date_role_and_cue(text, s, e, spans, dates_found)
        if (value, role) in seen_d:
            continue
        seen_d.add((value, role))
        span = _span_for(spans, s, e)
        context = text[max(span[0], s - 80):s]
        date_facts.append(fact("date", role, _date_label(role, doc_type, context), text[s:e], span,
                               date_value=value))

    # amounts
    amounts_found = find_amounts(text)
    amount_facts: list[KeyFact] = []
    seen_a: set[tuple[Decimal, str]] = set()
    for value, s, e in amounts_found:
        span = _span_for(spans, s, e)
        role, cue = _amount_role(text, s, e, span[0], span[1], amounts_found)
        if (value, role) in seen_a:
            continue
        seen_a.add((value, role))
        amount_facts.append(fact("amount", role, _amount_label(role, cue, text[span[0]:span[1]]),
                                 text[s:e].strip(), span, amount_inr=value))

    # obligations
    oblig: list[KeyFact] = []
    seen_o: set[str] = set()
    for s, e in spans:
        sentence = text[s:e]
        if len(sentence) < 15:
            continue
        for role, rx in _OBLIG_CUES:
            if rx.search(sentence):
                if sentence not in seen_o:
                    seen_o.add(sentence)
                    value = sentence.strip(" *#->•|")
                    oblig.append(fact("obligation", role, role.capitalize(), value or sentence, (s, e)))
                break
        if len(oblig) >= MAX_OBLIGATIONS:
            break

    return summary.model_copy(update={"parties": parties, "dates": date_facts,
                                      "amounts": amount_facts, "obligations": oblig})
