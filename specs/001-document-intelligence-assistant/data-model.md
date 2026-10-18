# Data Model: DocuMind

**Date**: 2026-10-18 | **Source**: [spec.md](./spec.md) Key Entities, [research.md](./research.md)

All entities are Pydantic v2 models in `docmind/models.py`, except where marked otherwise. Both
modes produce these same models (Principle V). Nothing is persisted. Instances live in
`st.session_state` for the session only.

## Enumerations (`Literal` types)

| Name | Values |
|------|--------|
| `DocType` | `"Health insurance"`, `"Car insurance"`, `"Rental agreement"`, `"Utility/Telecom bill"`, `"Warranty"`, `"Subscription"`, `"Other"` |
| `DocSource` | `"sample"`, `"upload"` |
| `FactCategory` | `"party"`, `"date"`, `"amount"`, `"obligation"` |
| `DateRole` | `"due"`, `"renewal"`, `"expiry"`, `"end"`, `"last_date"`, `"start"`, `"issue"`, `"bill"`, `"purchase"`, `"other"` |
| `AmountRole` | `"premium"`, `"rent"`, `"deposit"`, `"bill_total"`, `"coverage"`, `"fee"`, `"amount"` |
| `DeadlineStatus` | `"overdue"`, `"within_30"`, `"later"` |
| `Mode` | `"demo"`, `"live"` |

`DEADLINE_ROLES = {"due", "renewal", "expiry", "end", "last_date"}` is defined in `deadlines.py`.

## Document

| Field | Type | Rules |
|-------|------|-------|
| `id` | `str` | First 12 hex chars of the SHA-256 of the raw bytes, or of the rendered text for samples |
| `name` | `str` | File name. Unique within the store, and a re-upload with the same name replaces the earlier document |
| `source` | `DocSource` | |
| `size_bytes` | `int` | ≥ 0. Uploads are ≤ 10 × 1024 × 1024 |
| `text` | `str` | Extracted text with `\r\n` normalised to `\n`. This is the **only** ground truth for verification |
| `doc_type` | `DocType` | Set after Demo classification. Live may override it |
| `readable` | `bool` | `False` if `text.strip() == ""`. An unreadable document is listed with a flag and excluded from Q&A, extraction and deadlines |

## Chunk

| Field | Type | Rules |
|-------|------|-------|
| `id` | `str` | `f"{doc_id}:{index}"` |
| `doc_id` | `str` | FK → Document.id |
| `doc_name` | `str` | Denormalised for display |
| `index` | `int` | 0-based order within the document |
| `start`, `end` | `int` | `0 ≤ start < end ≤ len(doc.text)` |
| `text` | `str` | **Invariant**: `text == doc.text[start:end]` |

## KeyFact (extracted item)

| Field | Type | Rules |
|-------|------|-------|
| `category` | `FactCategory` | |
| `role` | `str` | A `DateRole` for dates, an `AmountRole` for amounts, and free text (e.g. "landlord", "notice period") for party and obligation facts |
| `label` | `str` | Human-readable, e.g. "Policy renewal", "Monthly rent" |
| `value` | `str` | Display value as written, or the party/obligation text |
| `date_value` | `date \| None` | Required when `category == "date"` |
| `amount_inr` | `Decimal \| None` | Required when `category == "amount"`. Must be ≥ 0 |
| `source_quote` | `str` | Must pass `verify_quote(doc, source_quote)`. Facts that fail are dropped (FR-010) |
| `doc_id`, `doc_name` | `str` | |

## DocumentSummary

| Field | Type | Rules |
|-------|------|-------|
| `doc_id`, `doc_name` | `str` | |
| `doc_type` | `DocType` | |
| `produced_by` | `Mode` | |
| `model` | `str \| None` | Set when `produced_by == "live"` |
| `parties`, `dates`, `amounts`, `obligations` | `list[KeyFact]` | Each list holds only its category. An empty list renders as "None found" (US3-AS5) |
| `notices` | `list[str]` | E.g. "Live extraction failed — showing Demo results." |

## Deadline

This is derived from date KeyFacts. It is never authored by the LLM.

| Field | Type | Rules |
|-------|------|-------|
| `label` | `str` | From KeyFact.label |
| `role` | `DateRole` | Must be in `DEADLINE_ROLES` |
| `date` | `date` | |
| `days_remaining` | `int` | `(date - today).days` |
| `status` | `DeadlineStatus` | `<0` → overdue, `0..30` → within_30, `>30` → later |
| `status_text` | `str` | "Overdue", "Within 30 days" or "Later". When `days_remaining == 0`, the days column shows "Due today" |
| `doc_id`, `doc_name` | `str` | |
| `source_quote` | `str` | Verified |

Ordering is ascending by `(date, doc_name, label)`. Duplicates are removed on `(doc_id, date, role)`.

## Citation

| Field | Type | Rules |
|-------|------|-------|
| `doc_name` | `str` | Must equal the name of a loaded readable Document |
| `doc_id` | `str \| None` | Filled in by verification |
| `quote` | `str` | Must be non-empty, and verified as a whitespace-normalised exact substring of that document's text |
| `start` | `int \| None` | Char offset when known (Demo mode) |

## Answer

| Field | Type | Rules |
|-------|------|-------|
| `question` | `str` | |
| `text` | `str` | If `citations == []`, MUST equal `NOT_FOUND = "Not found in your documents"` |
| `found` | `bool` | `False` ⇔ `citations == []` |
| `citations` | `list[Citation]` | Verified only. In Demo mode there are at most 3, grouped by document |
| `mode` | `Mode` | The mode that **produced** this answer |
| `fell_back` | `bool` | `True` when Live mode was selected but Demo mode answered |
| `notices` | `list[str]` | Friendly messages only, never raw errors |

The constructor helper is `Answer.not_found(question, mode, notices=[])`. It uses a model validator to
enforce the `text`/`citations` invariant.

## LLM wire models (used only as `output_format`)

These models use flat, schema-friendly types. See [contracts/llm-schemas.md](./contracts/llm-schemas.md).

- `LLMCitation { document_name: str, quote: str }`
- `LLMAnswer { found: bool, answer: str, citations: list[LLMCitation] }`
- `LLMFact { category: Literal["party","date","amount","obligation"], role: str, label: str, value: str, date_iso: str | None, amount_inr: float | None, quote: str }`
- `LLMExtraction { doc_type: DocType, facts: list[LLMFact] }`

Conversion happens in `llm_engine`:
- `date_iso` is parsed with `date.fromisoformat`, and the fact is dropped on failure.
- `amount_inr` becomes a `Decimal` via `str()`.
- An unknown `role` for a date becomes `"other"`.
- If `found == False`, or after verification no citations remain, the result is `Answer.not_found`.

## Settings (`engine.py`)

| Field | Type | Rules |
|-------|------|-------|
| `mode` | `Mode` | Default `"demo"` |
| `model` | `Literal[MODELS]` | `MODELS = ("claude-opus-5-5","claude-sonnet-5-5","claude-haiku-5-5")`. Default `claude-opus-5-5` |
| `api_key` | `SecretStr \| None` | `repr=False, exclude=True`. Comes from env `ANTHROPIC_API_KEY` or the password field. It is never serialised |
| `has_key` (property) | `bool` | |

## DocumentStore (`engine.py`, plain class)

This class holds state for one session. It is mutated only through engine functions.

- `docs: dict[str, Document]` (key = name)
- `chunks: dict[doc_id, list[Chunk]]`
- `index: BM25Index | None`, rebuilt lazily when the set of doc ids changes
- `summaries: dict[tuple[doc_id, str], DocumentSummary]`, keyed by `"demo"` or the model id
- `rejected: list[str]`, holding friendly messages from the last upload batch

## State transitions

```text
Document:  (bytes) --load_file--> Document[readable?]
           readable  --add--> chunked + indexed + demo summary cached
           [live on & key] --first view / mode switch--> live summary cached per (doc_id, model)
                                 └─ failure → keep demo summary + notice
           --remove--> purged from docs, chunks, index, summaries  (FR-006)
           same name re-added --> replaces previous (old id purged)

Ask:  question --(no readable docs)--> prompt-to-load notice
      demo   --> BM25 top≤3 above threshold --> verify --> Answer(mode=demo)
      live   --> parse() ok --> convert --> verify --> Answer(mode=live)
             └─ LiveError --> demo path --> Answer(mode=demo, fell_back=True, notices=[msg])
```
