<!--
Sync Impact Report
==================
Version change: (unversioned template) → 1.0.0
Modified principles: N/A (initial ratification; all placeholders replaced)
Added principles:
  - I. Never Fabricate — Grounded, Cited Answers (NON-NEGOTIABLE)
  - II. Demo-First, Offline by Default
  - III. Secrets Never Hardcoded or Persisted
  - IV. Core Logic Separate from UI, Tested with pytest
  - V. Typed Structured Output via Pydantic
  - VI. Minimal Dependencies
  - VII. Two-Minute Demo Experience
Added sections:
  - Technology & Security Constraints
  - Development Workflow & Quality Gates
  - Governance
Removed sections: None
Deferred TODOs: None
Note: This report is scratch material for review; remove before committing.
-->

# DocuMind Constitution

DocuMind is a Streamlit app for the Build with AI challenge 05 (Personal Document
Intelligence Assistant), built for hackathon demos. Users ask questions about their own
documents and get answers that are always grounded in, and cited from, those documents.

## Core Principles

### I. Never Fabricate — Grounded, Cited Answers (NON-NEGOTIABLE)

- Every answer MUST cite at least one source document by name AND include an exact quoted
  passage from that document.
- Every quoted passage MUST be checked in code to confirm it exists in the cited
  document's extracted text. A match may ignore whitespace differences only; it MUST NOT
  ignore any other differences. A citation that fails this check MUST be dropped. It MUST
  NOT be shown to the user.
- If no verified citation supports an answer, the app MUST respond with exactly
  `Not found in your documents` and nothing else. It MUST NOT guess, rely on general
  knowledge, or give a partial answer without a citation.
- These rules apply the same way in Demo mode and Live mode.

**Rationale**: Trust is the product. One made-up quote undermines the whole demo and the
promise of a personal document assistant.

### II. Demo-First, Offline by Default

- The app MUST work end-to-end without an API key and without network access. In this
  **Demo mode** it uses deterministic keyword retrieval and regex-based extraction over
  sample documents bundled in the repository.
- Demo mode MUST be deterministic: the same input and documents always produce the same
  output.
- **Live mode** MUST use Claude through the official `anthropic` Python SDK. It is turned
  on only when the user provides a key.
- If a Live-mode call fails (missing or invalid key, network error, or rate limit), the
  app MUST show a clear message and keep working in Demo mode. It MUST NOT crash.
- The bundled sample documents MUST be enough to show every headline feature.

**Rationale**: Demos fail when the Wi-Fi or the API key fails. Judges need to be able to
run the app as-is.

### III. Secrets Never Hardcoded or Persisted

- The API key MUST come only from the `ANTHROPIC_API_KEY` environment variable or from a
  Streamlit password input field kept in `st.session_state`.
- The key MUST NOT be hardcoded, committed, written to disk, cached, logged, or shown back
  in the UI. This includes source code, config files, `.streamlit/secrets.toml` checked
  into the repo, and test fixtures.
- `.gitignore` MUST exclude `.env` and local secrets files.

**Rationale**: The app is demoed on shared screens and published in public repos. A leaked
key is a real cost and a security incident.

### IV. Core Logic Separate from UI, Tested with pytest

- All business logic MUST live in a plain Python package with no Streamlit imports.
  This covers document loading and parsing, chunking, retrieval, extraction, answer
  generation, and citation checking.
- The Streamlit app MUST be a thin layer: it collects inputs, calls the package, and
  displays the results.
- The package MUST have pytest unit tests. Tests MUST NOT make real network or LLM calls.
  Anthropic client calls MUST be mocked or stubbed.
- The citation check from Principle I MUST have tests for both outcomes: a verified quote,
  and a fabricated quote that is rejected.

**Rationale**: Logic that can be tested is logic that can be trusted. Keeping the UI thin
lets us iterate on it quickly without breaking the core.

### V. Typed Structured Output via Pydantic

- Every structured response from the LLM, such as answers, citations, and extracted
  fields, MUST be defined as a Pydantic model and validated against that model before
  use.
- Demo mode MUST return the same Pydantic models, so the UI never needs to know which mode
  produced a result.
- Output that fails validation MUST be handled the same way as "no verified answer"
  (Principle I). It MUST NOT be shown to the user raw.

**Rationale**: Validated schemas catch malformed model output early and give both modes a
single contract.

### VI. Minimal Dependencies

- Runtime dependencies are limited to `streamlit`, `anthropic`, `pydantic`, and `pypdf`.
  The only development dependency is `pytest`. The Python standard library is always
  allowed.
- Any other dependency requires a written justification in the feature plan's Complexity
  Tracking section and an amendment to this list.

**Rationale**: Fewer dependencies mean faster installs, fewer version conflicts on demo
day, and less code to review.

### VII. Two-Minute Demo Experience

- A first-time user MUST be able to load the app, see the sample documents, ask a
  question, and see a cited answer in under two minutes, with no setup beyond
  `pip install` and `streamlit run`.
- In Demo mode, responses MUST appear in under 2 seconds on a typical laptop. In Live
  mode, the app MUST show a visible progress indicator while waiting.
- The UI MUST be clean and easy to read. Citations MUST appear right next to the answer,
  with the document name and the quoted passage visually highlighted. The current mode
  (Demo or Live) MUST always be visible.

**Rationale**: The app is judged in a short live demo. Anything slow, cluttered, or unclear
costs points.

## Technology & Security Constraints

- **Language/Runtime**: Python 3.10 or newer.
- **UI**: Streamlit only. No separate frontend framework.
- **LLM**: Anthropic Claude through the official `anthropic` SDK. Use a current Claude
  model ID from configuration; it MUST NOT be scattered throughout the code.
- **Documents**: Plain text, Markdown, and PDF (through `pypdf`). Uploaded documents are
  processed in memory or in the session only. They MUST NOT be sent anywhere except the
  Anthropic API in Live mode.
- **Persistence**: No database. Nothing is stored across sessions except the bundled
  sample documents.

## Development Workflow & Quality Gates

- Each feature follows the Spec Kit flow: specify → plan → tasks → implement. Each plan's
  Constitution Check MUST confirm compliance with Principles I–VII.
- Before a change is merged or demoed:
  1. `pytest` passes with no network access.
  2. The app starts and answers a sample question in Demo mode with no API key set.
  3. A question about something not in the documents returns
     `Not found in your documents`.
  4. A search of the repo finds no committed secrets.
- Keep changes small and demo-focused. Features that do not improve the two-minute demo
  are deferred.

## Governance

- This constitution overrides all other project practices. If a plan, spec, or task
  conflicts with it, the constitution wins until it is amended.
- **Amendments**: Propose the change with a rationale, update this file through
  `/speckit-constitution`, and review dependent templates and specs for consistency.
- **Versioning**: Semantic versioning.
  - MAJOR: a principle is removed or redefined in a backward-incompatible way.
  - MINOR: a principle or section is added, or guidance is materially expanded.
  - PATCH: clarifications and wording fixes.
- **Compliance**: Every plan includes a Constitution Check gate. Every review verifies
  Principles I (grounding) and III (secrets) explicitly. Any approved exception MUST be
  recorded in the plan's Complexity Tracking section.

**Version**: 1.0.0 | **Ratified**: 2026-10-18 | **Last Amended**: 2026-10-18
