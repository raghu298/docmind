# Research: DocuMind – Personal Document Intelligence Assistant

**Date**: 2026-10-18 | **Plan**: [plan.md](./plan.md)

Each section records a **Decision**, its **Rationale** and the **Alternatives considered**. Every
Technical Context unknown is resolved here.

---

## R1. Packaging and tooling

- **Decision**: Use `uv` with a single `pyproject.toml` (`requires-python = ">=3.11"`).
  Runtime deps: `streamlit`, `anthropic>=1.15,<2`, `pydantic>=2.7`, `pypdf>=5`. Dev group (`[dependency-groups] dev`): `pytest`.
  `[tool.pytest.ini_options] pythonpath = ["."]`, `testpaths = ["tests"]`. Run with `uv sync`, `uv run pytest`, `uv run streamlit run app.py`.
- **Rationale**: The user specified this. `pythonpath=["."]` lets tests import `docmind` without an editable install. `pip install -e .` still works for judges without uv (Principle VII).
- **Alternatives**: `requirements.txt` + venv (no lockfile); `src/` layout (needs install step, so rejected for demo simplicity).

## R2. Anthropic SDK surface, verified against the installed package

The SDK was checked on 2026-10-18 against the newest `anthropic` from PyPI in a scratch venv: **anthropic 1.15.0, httpx2 2.13.1, pydantic 2.14.1, pypdf 6.21.1**.
The system-wide Python has an older `anthropic 0.116.0` / `httpx 0.28.1`. The project MUST pin `anthropic>=1.15,<2` so that `uv sync` gets the 1.x line.

Verified facts:

| Item | Verified result |
|------|-----------------|
| Client | `anthropic.Anthropic(api_key=..., max_retries=0, timeout=60)` constructs fine |
| Method | `client.messages.parse` exists. Params: `max_tokens, messages, model, diagnostics, metadata, output_config, output_format, service_tier, speed, stop_sequences, system, thinking, tool_choice, tools, extra_*, timeout`. **There is no `temperature` param on `parse`**. We never send `thinking`. |
| `output_config` | TypedDict `{effort: 'low'|'medium'|'high'|'xhigh'|'max', format: ...}`. We send `{"effort": "medium"}`. |
| Return | `ParsedMessage`. `.parsed_output` returns the first text block's parsed Pydantic object or `None`. `.stop_reason` ∈ `end_turn, max_tokens, stop_sequence, tool_use, pause_turn, refusal, model_context_window_exceeded`. |
| Parse failure | `parse_text` calls `TypeAdapter(output_format).validate_json(text)`, so malformed JSON **raises `pydantic.ValidationError` from inside `parse()`**. It does not return `None`. We must catch it. |
| Exceptions | `AuthenticationError`, `RateLimitError`, `PermissionDeniedError`, `BadRequestError`, `InternalServerError` ⊂ `APIStatusError` ⊂ `APIError`. `APITimeoutError` ⊂ `APIConnectionError` ⊂ `APIError`. |
| Exception ctor (tests) | `APIStatusError` subclasses: `(message, *, response: httpx2.Response, body)`. `APIConnectionError(*, message="Connection error.", request: httpx2.Request)`. Example: `anthropic.AuthenticationError("bad", response=httpx2.Response(401, request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages")), body=None)`. |

- **Decision**: `llm_engine` makes exactly this call:
  `client.messages.parse(model=settings.model, max_tokens=16000, system=SYSTEM, messages=[{"role":"user","content":...}], output_format=<Model>, output_config={"effort":"medium"})`.
  Map errors with `except` clauses ordered most-specific first:
  1. `anthropic.AuthenticationError` → `LiveAuthError`: "Your Anthropic API key was rejected. Check the key in the sidebar."
  2. `anthropic.RateLimitError` → `LiveRateLimitError`: "Claude is rate-limiting requests right now. Please wait a moment and try again."
  3. `anthropic.APIConnectionError` (includes timeout) → `LiveConnectionError`: "Couldn't reach the Claude service. Check your internet connection."
  4. `anthropic.APIStatusError` (anything else, e.g. 400/403/5xx) → `LiveServiceError`: "The Claude service returned an error. Please try again later."
  5. `pydantic.ValidationError`, `parsed_output is None`, `stop_reason in {"max_tokens","model_context_window_exceeded"}` → `LiveMalformedError`: "Claude returned an unexpected response, so it was not shown."
  6. `stop_reason == "refusal"` → `LiveRefusalError`: "Claude declined to answer this question."

  These fixed strings live in one dict. Raw exception text is never shown.
  We check `stop_reason` before reading `parsed_output`. A refusal or truncated output may raise `ValidationError` inside `parse()` first, and either path ends in the same no-answer handling.
- **Rationale**: `max_retries=0` and `timeout=60` give fast, predictable failure on demo day. Distinct classes let us show the specific messages FR-025 requires. Structured outputs satisfy Principle V.
- **Alternatives**: `messages.create` + manual JSON parsing (more code, weaker typing); tool-use forced JSON (more ceremony); SDK retries (slower failure in a demo).

## R3. LLM wire schemas vs. domain models

- **Decision**: Define small **wire models** used only as `output_format`: `LLMAnswer` and `LLMExtraction`, both in `models.py`. They use only simple JSON-schema-friendly types (`str`, `list`, `Literal`, `Optional`), with dates as ISO `YYYY-MM-DD` strings and amounts as strings plus an optional number. `llm_engine` converts them to domain models (`Answer`, `Citation`, `KeyFact`) and parses or validates dates in Python. Invalid values are dropped and never guessed.
- **Rationale**: Structured-output JSON schema supports a subset of keywords. Keeping wire models flat avoids schema rejections. Domain models can then carry computed fields (offsets, `verified`, `status`) that the model must not author.
- **Alternatives**: Passing domain models directly as `output_format` (exposes fields the model shouldn't fill; risk of unsupported schema features).

## R4. Live-mode prompt strategy (Principle VIII)

- **Decision**: `estimate_tokens(text) = len(text) // 4`. If the sum over all readable docs is ≤ 150_000, the user message contains every document as `<document name="...">…full text…</document>`, followed by the question. Otherwise it contains the top **12** BM25 chunks with their doc names. The system prompt says to answer only from the documents, give each citation's `document_name` and a **verbatim** `quote` copied character-for-character, keep quotes ≤ ~300 chars, and return `found=false` with no citations if the documents don't answer the question.
  For extraction, there is one call per document with that document's full text. If a single document exceeds the budget, it is truncated to the budget with a notice.
- **Rationale**: Personal corpora are small. Full context gives the best recall, and exact quotes stay verifiable.
- **Alternatives**: Always retrieving chunks (lower recall); embeddings (prohibited).

## R5. Citation verification (`verify.py`)

- **Decision**: `normalize_ws(s) = re.sub(r"\s+", " ", s).strip()`. Python's `\s` is Unicode-aware, so NBSP, tabs and newlines count. A quote is verified if and only if `normalize_ws(quote)` is non-empty **and** is a substring of `normalize_ws(doc.text)` for the document whose name exactly equals `citation.document_name`. There is no case-folding and no punctuation or quote-character normalisation. Each failed citation is dropped and the notice "An unverifiable citation was removed." is added. If 0 citations remain, the answer becomes `Answer.not_found(...)`, with text exactly `Not found in your documents` and `citations=[]`. The same function filters `KeyFact.source_quote`.
- **Rationale**: This is exactly the spec/constitution rule ("whitespace differences only").
- **Alternatives**: Fuzzy matching (violates Principle I); also matching against other documents (would mis-attribute sources).

## R6. BM25 retrieval and relevance threshold (Demo mode)

- **Decision**: A pure-Python Okapi BM25 with `k1=1.5`, `b=0.75`, and `idf = ln(1 + (N - df + 0.5)/(df + 0.5))`.
  Tokenizer: lowercase, `re.findall(r"[a-z0-9₹]+")`, drop a small English stopword list (including question words like what/when/which/my/is). A light suffix stemmer strips `ies→y`, `es`, `s`, `ing`, `ed` (min stem length 3). This gives `expires/expiry/expire → expir`, `renewal/renew → renew`.
  **Threshold**: a chunk qualifies only if (a) its BM25 score ≥ `MIN_SCORE = 1.0` **and** (b) its **IDF-weighted query coverage** is ≥ `MIN_COVERAGE = 0.5`. Coverage is the sum of idf for matched query terms divided by the sum of idf for all query terms, and terms not in the corpus get `idf_max = ln(1 + (N + 0.5)/0.5)`. So "What is my passport number?" fails: `passport` is unseen and has high idf, while `number` is common, so coverage is low and the result is `Not found`.
  Return at most **3** qualifying chunks (FR-020), grouped by document in the order of each document's best rank. Ties break deterministically on `(doc_name, chunk.start)`.
- **Rationale**: Deterministic and fast, it handles exact terms like policy numbers, and coverage stops a single generic word from producing an answer. Constants are tuned against the sample corpus and the four chips, and tests lock them in (SC-004/SC-005).
- **Alternatives**: A raw score threshold only (unstable across corpus sizes); TF-IDF cosine (similar effort, weaker on length); `rank-bm25` package (extra dependency, prohibited by Principle VI).

## R7. Chunking

- **Decision**: Split `doc.text` on blank lines (`\n\s*\n`) and record `start`/`end` char offsets so that the invariant `chunk.text == doc.text[start:end]` holds. Merge consecutive paragraphs shorter than 200 chars (headings, single lines) with the following paragraph until ≥200 chars, ending the merge at the next blank line. Split paragraphs longer than 1,200 chars at sentence boundaries (`(?<=[.!?])\s+`), falling back to a hard split at 1,200. Chunk IDs are `f"{doc_id}:{i}"`.
- **Rationale**: Paragraph-sized passages make readable citations. Offsets make Demo citations verifiable by construction.
- **Alternatives**: Fixed-size windows (cut sentences mid-quote); per-line (too small for BM25).

## R8. Demo extraction (`extract_demo.py`)

- **Dates (day-first)**: Regexes cover:
  - `dd/mm/yyyy`, `dd-mm-yyyy` and `dd.mm.yyyy` (1–2 digit day/month, 4-digit year)
  - `dd-Mon-yyyy` and `dd Mon yyyy` (`Jan`…`Dec`, case-insensitive, optional `.`)
  - `dd(st|nd|rd|th)? Month[,]? yyyy`
  - `Month dd(st|nd|rd|th)?, yyyy`

  Everything is validated through `datetime.date(y, m, d)`, and invalid matches are skipped. `03/04/2026` is read as 3 April. Dates without a year ("5th of every month") don't match the date regex. They are caught by obligation cues instead.
- **Date roles**: Look at the text window of up to 80 chars before the match, clipped to the start of the sentence or line, and up to 30 chars after it. Pick the cue closest to the date from an ordered map:
  - deadline roles: `renewal|renew|next due` → *renewal*; `due date|due on|pay by|payment due|due` → *due*; `expiry|expires|valid till|valid upto|valid until|warranty ends` → *expiry*; `end date|ends on|terminat|lease end|till` → *end*; `last date|notice by|on or before` → *last_date*
  - non-deadline roles: `start|commence|effective from|from` → *start*; `issue|issued|dated` → *issue*; `bill date|billing date|statement date` → *bill*; `purchase|invoice` → *purchase*
  - otherwise → *other*, which is never put on the dashboard

  The label is human-readable, for example `Policy renewal`, `Bill due`, `Warranty expiry`, `Lease end` and `Notice deadline`. The doc type is used as a prefix where helpful.
- **INR amounts**: `(?:₹|Rs\.?|INR)\s*([0-9]{1,3}(?:,[0-9]{2})*,[0-9]{3}|[0-9]+)(?:\.[0-9]{1,2})?\s*(?:/-)?` plus an optional `\s*(lakh|lakhs|crore)` multiplier. Commas are stripped and the value parsed as `Decimal`. The role comes from nearby cues: `premium`, `rent`, `deposit`, `total|amount payable|amount due`, `sum insured|coverage|IDV`, `fee|charges|subscription|plan`, otherwise `amount`.
- **Doc type**: Each type gets a keyword score, and the highest score ≥2 wins. Otherwise the type is `Other`. Types: *Health insurance* (health, hospitalisation, sum insured, mediclaim), *Car insurance* (motor, vehicle, IDV, registration no), *Rental agreement* (lease, rent, landlord, tenant, licensor), *Utility/Telecom bill* (bill, broadband, mobile, data, due date, account no), *Warranty* (warranty, serial no, purchase), *Subscription* (subscription, membership, auto-renew, plan).
- **Parties**: Line cues such as `Insured:`, `Policyholder:`, `Landlord|Licensor:`, `Tenant|Licensee:`, `Customer|Subscriber|Member Name:`, `Insurer|Provider|Issued by:` and `between X and Y`. The party value is the rest of the line, up to 80 chars.
- **Obligations**: Sentences containing `notice period|notice of|must|shall|within \d+ days|on or before|before the \d+(st|nd|rd|th)|intimat` become `KeyFact(category="obligation")`, and the value is the sentence.
- **Source quote**: Every Demo KeyFact's `source_quote` is the exact sentence or line slice from `doc.text`, so it passes verification by construction. It still goes through `verify.py`.
- **Rationale**: Deterministic and offline, and it covers SC-007 on the samples.
- **Alternatives**: `dateparser`/`price-parser` (extra dependencies, and not reliably day-first).

## R9. Samples (`samples.py`)

- **Decision**: `build_samples(today: date) -> list[Document]` renders 6 text templates with dates at fixed offsets from `today`. Dates use the varied Indian formats from R8, and amounts use ₹ / Rs. / INR with lakh grouping. The output is deterministic for a given `today`. Offsets:

| Sample | Deadline (role) | Offset | Status |
|--------|-----------------|--------|--------|
| Broadband/phone bill (Airtel-style) | Current bill due | +9 d | Within 30 |
| Broadband/phone bill | Previous bill due | −21 d | Overdue |
| Car insurance (motor) | Policy renewal/expiry | +21 d | Within 30 |
| Health insurance | Policy renewal | +45 d | Later (30–60 band) |
| Gym/OTT subscription | Auto-renewal | +52 d | Later (30–60 band) |
| Rental agreement | Notice-by last date | +140 d | Later |
| Rental agreement | Lease end | +200 d | Later |
| Laptop warranty | Warranty expiry | +300 d | Later |

  Start, issue and purchase dates use negative offsets and don't appear on the dashboard. Each sample includes a policy/contract/account number, named parties, an INR amount and an obligation (FR-003). Suggested chips:
  1. "What is the notice period for my rental agreement?" → rental
  2. "Which of my policies expire this year?" → health + car, multi-document
  3. "When is my broadband bill due and how much do I owe?" → bill
  4. "What is my passport number?" → `Not found in your documents`

  `test_samples.py` checks the FR-004 bands for several `today` values, including month-end and leap-year days. It also checks that chips 1–3 return the expected source doc in Demo mode.
- **Rationale**: Keeps the dashboard interesting whatever day the demo runs, while staying deterministic per day.
- **Alternatives**: Static files with fixed dates (they go stale); computing "this year" relative to fixed dates (fragile).

## R10. Parsing (`parsing.py`)

- **Decision**: Use `load_file(name, data: bytes) -> Document`.
  - Reject if `len(data) > 10*1024*1024` ("File is larger than 10 MB"), if it is empty, or if the extension is not in `{.pdf,.txt,.md}` ("Unsupported file type — supported: .pdf, .txt, .md").
  - txt/md: decode as `utf-8-sig`, falling back to `cp1252`, then normalise `\r\n` to `\n`.
  - pdf: `pypdf.PdfReader(io.BytesIO(data))`. If `reader.is_encrypted`, try `decrypt("")` and reject on failure. Join `page.extract_text() or ""` with `"\n\n"`. If any `pypdf.errors.PdfReadError` or other `Exception` is raised, reject with "This PDF could not be read".
  - If the text is empty or whitespace only, the document is still returned with `readable=False` (flagged "No readable text — scanned documents are not supported").

  `doc_id = sha256(data)[:12]`. Duplicate names replace the earlier document, and that is handled in `engine` (spec edge case).
- **Rationale**: Covers the FR-007 and edge cases without crashing the app.
- **Alternatives**: `pdfplumber`/`pymupdf` (extra dependencies).

## R11. Deadlines (`deadlines.py`)

- **Decision**: `DEADLINE_ROLES = {"due","renewal","expiry","end","last_date"}`. `collect_deadlines(summaries, today)` keeps verified date KeyFacts with those roles and deduplicates on `(doc_id, date, role)`. It computes `days_remaining = (date - today).days` and the status: `<0` → `overdue`, `0..30` → `within_30`, `>30` → `later`. Text labels are "Overdue" / "Within 30 days" / "Later", and day 0 shows "Due today". Results are sorted by `(date, doc_name, label)`.
- **Rationale**: Directly encodes FR-012..FR-014. Status has a text label, not just colour.

## R12. Engine facade, modes, fallback and caching

- **Decision**:
  - `Settings` is a frozen Pydantic model with `mode: Literal["demo","live"]`, `model: Literal["claude-opus-5-5","claude-sonnet-5-5","claude-haiku-5-5"] = "claude-opus-5-5"`, and `api_key: SecretStr | None` with `repr=False`. `Settings.has_key` is a property. `MODELS` and `DEFAULT_MODEL` are defined once in `engine.py` (constitution: model ID from configuration, not scattered).
  - `DocumentStore` is a plain class held in `st.session_state`. It maps `name → Document` and caches chunks, a BM25 index (rebuilt when the doc set changes), and summaries keyed by `(doc_id, "demo")` / `(doc_id, model)`.
  - `ask(question, store, settings, today, client_factory=...)`:
    - With no readable documents it returns the prompt-to-load notice.
    - In Demo mode it calls `demo_answer`.
    - In Live mode with no key it calls `demo_answer` and adds the notice "Live mode needs an API key — answered in Demo mode."
    - In Live mode with a key it calls `llm_engine.answer_live`. On `LiveError` it returns `demo_answer` with `mode="demo"`, `fell_back=True` and notices `[friendly message, "Answered in Demo mode instead."]`.
    - The result always passes through `verify.verify_answer`.
  - `summarize(doc, ...)`: Demo extraction runs on load. When Live mode is on and a key is present, Live extraction runs once per `(doc_id, model)`. If it fails, the document keeps its Demo summary and a notice is added.
  - The client is created per call via `anthropic.Anthropic(api_key=settings.api_key.get_secret_value(), max_retries=0, timeout=60)`. `client_factory` is injectable so tests can pass a fake.
- **Rationale**: One facade keeps `app.py` thin, and injected `today`/`client_factory` make it testable (Principle IV). Live mode stays selected after a failure (clarification Q2).
- **Alternatives**: Caching the client in session state (would hold the key in another object, with no benefit).

## R13. Streamlit UI (`app.py`)

- **Decision**:
  - **Sidebar**: a mode badge (`🟢 Demo mode` / `🔵 Live mode`); `st.radio` for the mode; when Live, `st.selectbox` for the model and `st.text_input("Anthropic API key", type="password")`, shown only if `ANTHROPIC_API_KEY` is not set (the caption says "Using key from environment" otherwise); a "Load sample documents" button; `st.file_uploader(type=["pdf","txt","md"], accept_multiple_files=True)`; and a document list with a ✕ remove button for each document.
  - **Views**: `st.tabs(["Documents","Deadlines","Ask"])`.
  - **Ask view**: `st.chat_message` history, 4 chips as `st.button`s in columns, `st.chat_input`, and `st.spinner("Asking Claude…")` in Live mode. Each citation renders as `st.expander(f"📄 {doc_name}")` containing the quote in a highlighted block. Notices render as `st.info`/`st.warning`.
  - **Deadlines view**: a table-like list with coloured status chips plus text labels, and an expander per row showing the source quote.
  - Uploads are deduplicated by `(name, size, sha)` across reruns, so the uploader doesn't reprocess files on every rerun.
- **Rationale**: Meets FR-021..FR-026 and Principle VII using only Streamlit primitives.
- **Alternatives**: Multipage app (more files, slower demo navigation).

## R14. Testing strategy

- **Decision**:
  - `conftest.py` provides `TODAY = date(2026, 10, 18)`, a `samples` fixture, `FakeClient` (an object with `.messages.parse(**kw)` that records kwargs and returns a canned `SimpleNamespace(stop_reason=..., parsed_output=...)` or raises a configured exception), and helpers `make_status_error(cls, code)` / `make_conn_error()` built with `httpx2`.
  - Tests assert that the `parse` kwargs contain exactly `model`, `max_tokens=16000`, `system`, `messages`, `output_format` and `output_config={"effort":"medium"}`, and that **no** `temperature`/`thinking` is sent.
  - Each exception class maps to its fixed message, and a Live-mode failure produces a Demo answer with `fell_back=True`.
  - A test asserts that no file in `docmind/` imports `streamlit`.
  - The suite runs fully offline.
- **Rationale**: Principle IV; FR-025/SC-008 coverage.
