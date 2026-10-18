# Implementation Plan: DocuMind – Personal Document Intelligence Assistant

**Branch**: `001-document-intelligence-assistant` | **Date**: 2026-10-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-document-intelligence-assistant/spec.md`

## Summary

DocuMind is a single-user Streamlit app. Users load their own documents (.pdf/.txt/.md) or six bundled
Indian-context samples, then use three views: **Documents** (list plus per-document key facts),
**Deadlines** (dashboard sorted soonest first, with status) and **Ask** (chat with verified citations).

All logic lives in the plain-Python package `docmind/`, and `app.py` is a thin UI layer. There are two
interchangeable engines behind the facade in `engine.py`:

- **Demo mode** (default, offline, deterministic): pure-Python BM25 over paragraph chunks with an
  IDF-coverage relevance threshold. Regex extraction handles Indian date formats and INR amounts, and
  keyword cues set the document type and date roles.
- **Live mode**: Claude through `anthropic` 1.x `client.messages.parse(...)` with Pydantic
  `output_format`. If the corpus is ≤150k estimated tokens, the full text goes in the prompt; otherwise
  the top BM25 chunks are sent. Any failure falls back to Demo mode for that request and shows a
  specific friendly notice.

Both modes return the same Pydantic models. Every quote passes through `verify.py`, which does an
exact substring match after whitespace normalisation. Unverified citations are dropped. If no verified
citation remains, the answer is exactly `Not found in your documents`.

## Technical Context

**Language/Version**: Python 3.11+ (the constitution requires ≥3.10; 3.11 is the floor we choose)

**Primary Dependencies**: `streamlit`, `anthropic` (1.x, which uses `httpx2` internally),
`pydantic` v2 and `pypdf`. The only dev dependency is `pytest`. Everything else uses the standard library
(`re`, `math`, `datetime`, `hashlib`, `io`, `dataclasses`, `collections`).

**Storage**: None. State lives in `st.session_state` only. Samples are generated in code (`samples.py`).

**Testing**: `pytest`, configured in `pyproject.toml` with `[tool.pytest.ini_options] pythonpath = ["."]`
and `testpaths = ["tests"]`. The LLM is always mocked: a fake client object is injected into
`llm_engine`. SDK exceptions are built with `httpx2.Request`/`httpx2.Response`.

**Target Platform**: Local laptop (macOS/Linux/Windows) running `uv run streamlit run app.py`, in a desktop browser

**Project Type**: Single-project Python app (Streamlit UI + importable core package)

**Performance Goals**: In Demo mode, answers, extraction and dashboard take <2 s for the 6 samples (target
<200 ms in practice). A 200-page PDF is parsed and chunked without freezing the UI (parse once, then
cache by content hash).

**Constraints**: Works offline with no key. Demo output is deterministic for the same documents,
question and `today`. The API key is never persisted, logged or echoed. Files are limited to 10 MB.
Only text-based PDFs are supported. No vector store or embeddings (Principle VIII).

**Scale/Scope**: One user, usually 1–20 documents per session, 3 views, about 10 core modules, 6 sample
documents and 4 suggested-question chips.

All Technical Context items are resolved. See [research.md](./research.md). There are no remaining NEEDS CLARIFICATION items.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | How this plan complies | Status |
|---|-----------|------------------------|--------|
| I | Never fabricate: grounded, cited answers | `verify.py` checks every Citation and KeyFact quote against the cited document's text (whitespace-normalised exact substring). Failures are dropped and a notice is added. Zero verified citations means `Answer.text == "Not found in your documents"` with no citations. The same code path is used for Demo and Live. Tests cover both a verified quote and a fabricated quote. | ✅ PASS |
| II | Demo-first, offline by default | Demo mode is the default. BM25 and regex are pure Python. Samples are bundled in code. `today` is injected, so output is deterministic. Every Live failure (`AuthenticationError`, `RateLimitError`, `APIConnectionError`, `APIStatusError`, validation/refusal) maps to a friendly message, and that request is answered in Demo mode. | ✅ PASS |
| III | Secrets never hardcoded or persisted | The key comes from `os.environ["ANTHROPIC_API_KEY"]` or `st.text_input(type="password")` stored in `st.session_state`. It is passed only to `anthropic.Anthropic(api_key=...)` and is never logged, cached to disk or rendered. `Settings` exposes `has_key: bool`, and `repr` excludes the key. `.gitignore` covers `.env`, `.streamlit/secrets.toml` and `.venv/`. Test fixtures use a dummy placeholder string. | ✅ PASS |
| IV | Core logic separate from UI, pytest | All logic is in `docmind/`, and `docmind/` has no `import streamlit` (enforced by a test). `app.py` only collects input, calls `engine`, and renders. Tests never touch the network, and the Anthropic client is a stub. | ✅ PASS |
| V | Typed structured output via Pydantic | Live calls use `messages.parse(output_format=LLMAnswer / LLMExtraction)`. `pydantic.ValidationError`, a `None` parsed output, `stop_reason in {"refusal","max_tokens"}` are handled as no verified answer plus a notice. Demo returns the same `Answer`/`DocumentSummary` models. | ✅ PASS |
| VI | Minimal dependencies | Runtime: streamlit, anthropic, pydantic, pypdf. Dev: pytest. `httpx2` is a transitive dependency of `anthropic` and is imported only in tests to build exception objects. It is not a declared dependency. | ✅ PASS |
| VII | Two-minute demo experience | "Load sample documents" takes one click, suggested chips give one-click questions, and Demo latency is ≪2 s. Live mode shows `st.spinner`. A mode badge is always shown in the sidebar. Citations are expanders right under each answer, with the doc name and the quote highlighted. | ✅ PASS |
| VIII | Long-context first, no vector store | When `estimate_tokens(all_text) = chars/4 ≤ 150_000`, Live mode sends full documents. Otherwise it sends the top-K BM25 chunks. Demo mode uses BM25 with a threshold. No embeddings. | ✅ PASS |

**Post-design re-check (after Phase 1)**: ✅ PASS. The data model, contracts and quickstart add no new
dependencies and no persistence, and they keep the citation-verification choke point (`verify.py`)
mandatory for both engines. No violations, so Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/001-document-intelligence-assistant/
├── plan.md              # This file
├── research.md          # Phase 0: decisions + verified SDK surface
├── data-model.md        # Phase 1: Pydantic entities, invariants, state rules
├── quickstart.md        # Phase 1: run + validation scenarios
├── contracts/
│   ├── engine-api.md    # Public Python API of docmind/ consumed by app.py and tests
│   ├── llm-schemas.md   # Live-mode request shape, structured-output schemas, error mapping
│   └── ui.md            # Streamlit UI contract (sidebar, views, notices)
└── tasks.md             # Phase 2 (/speckit-tasks; not created here)
```

### Source Code (repository root)

```text
pyproject.toml           # uv-managed; deps + [tool.pytest.ini_options] pythonpath=["."]
.gitignore               # .env, .venv/, .streamlit/secrets.toml, __pycache__/
README.md                # setup + run (uv sync; uv run streamlit run app.py)
app.py                   # Streamlit UI only: sidebar (mode/model/key + doc manager), views Documents | Deadlines | Ask

docmind/
├── __init__.py
├── models.py            # Pydantic: Document, Chunk, KeyFact, Deadline, Citation, Answer, DocumentSummary (+ LLM wire models)
├── samples.py           # build_samples(today) -> 6 sample docs, dates offset from today
├── parsing.py           # load_file(name, data) -> Document | raises ParseError; txt/md/pdf (pypdf); 10 MB limit
├── chunking.py          # chunk_document(doc) -> list[Chunk] (paragraph chunks, char offsets)
├── retrieval.py         # BM25Index: build(chunks), search(query, k) with IDF-coverage threshold
├── extract_demo.py      # regex dates (day-first) / INR amounts; classify_doc_type; label date roles; parties; obligations
├── llm_engine.py        # Anthropic client wrapper: answer_live(), extract_live(); error → LiveError subclasses
├── verify.py            # normalize_ws(), verify_quote(), verify_answer(), verify_facts()
├── deadlines.py         # collect_deadlines(summaries, today) -> sorted list[Deadline] with status
└── engine.py            # Settings + facade: load/remove docs, summarize(), ask(), deadlines(); mode routing + fallback

tests/
├── conftest.py          # fixed TODAY, sample corpus fixture, FakeAnthropicClient, httpx2 error builders
├── test_parsing.py
├── test_chunking.py
├── test_retrieval.py
├── test_extract_demo.py
├── test_verify.py       # verified quote passes; fabricated quote rejected; whitespace-only diff passes
├── test_deadlines.py
├── test_samples.py      # FR-003/FR-004 offsets hold for any `today`
├── test_llm_engine.py   # parse() call shape, refusal, each exception class → friendly message
├── test_engine.py       # mode routing, Live→Demo fallback, caching, remove doc, chips (SC-004/SC-005)
└── test_no_streamlit_in_core.py
```

**Structure Decision**: This is a single project. There is a flat `docmind/` package at the repo root,
imported as `docmind.*` thanks to `pythonpath=["."]`, with `app.py` alongside it and tests in `tests/`.
We don't use a `src/` layout. That keeps `streamlit run app.py` and `pytest` working with no install
step beyond `uv sync`.

## Complexity Tracking

No constitution violations. This section is intentionally empty.
