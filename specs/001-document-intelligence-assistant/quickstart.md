# Quickstart & Validation Guide: DocuMind

This guide shows how to run DocuMind and check the feature end to end. For the interfaces, see
[contracts/](./contracts/), and for the entities, see [data-model.md](./data-model.md).

## Prerequisites

- Python 3.11+ and [uv](https://docs.astral.sh/uv/). Without uv, `pip install -e .` and `pip install pytest` also work.
- Optional: an Anthropic API key, needed only for the Live-mode checks.

## Setup and run

```bash
uv sync                          # installs streamlit, anthropic (1.x), pydantic, pypdf + dev pytest
uv run pytest -q                 # offline; LLM mocked
uv run streamlit run app.py      # opens http://localhost:8501
```

Sanity-check the SDK line:

```bash
uv run python -c "import anthropic; print(anthropic.__version__)"
```

This should print `1.x`.

## Validation scenarios

### V1. Offline Demo flow (US1, SC-001, SC-004, SC-005)

Unset `ANTHROPIC_API_KEY` and disconnect from the network.

1. Start the app. The sidebar shows **🟢 Demo mode**.
2. Click **Load sample documents**. Six documents are listed, each with a name, type and size. Click it again and nothing is duplicated.
3. Open **Ask** and click each chip:
   - "notice period … rental" returns a passage from the rental agreement.
   - "policies expire this year" returns passages from the health and car insurance docs, listed per document.
   - "broadband bill due …" returns a passage from the bill.
   - "passport number" returns exactly `Not found in your documents`.
4. Expand each citation. Use Ctrl+F in the Documents view to confirm the quote appears verbatim.

### V2. Deadlines (US2, SC-006)

1. Open **Deadlines**.
2. Check that the list is in ascending date order. It should contain one 🔴 Overdue item (the previous bill), the car renewal and the current bill under 🟠 Within 30 days, and the health renewal (+45 d), gym/OTT renewal (+52 d), lease notice/end and warranty expiry under 🟢 Later.
3. Confirm that no start, issue or purchase dates appear.
4. Remove the bill document. Its two rows disappear.

### V3. Extraction (US3, SC-007)

Open the rental agreement in **Documents**. It should show:
- the type "Rental agreement"
- the landlord and tenant
- start and end dates
- monthly rent and security deposit in ₹ (lakh grouping)
- the notice period obligation

Each item should have a source quote. Categories with no data show "None found".

### V4. Upload edge cases (FR-001, FR-007)

Upload a .txt file, a text PDF, a .docx and an empty .txt in one batch.
- The .txt and PDF files load.
- The .docx shows "Unsupported file type — supported: .pdf, .txt, .md".
- The empty file is rejected.
- The app keeps running.

Re-upload the same .txt name. It replaces the earlier document instead of duplicating it.

### V5. Live mode errors (US4, SC-008)

1. Switch to **Live** and paste `sk-ant-invalid`. Ask a chip question. You should see the invalid-key message and a Demo-mode answer, and the mode stays Live.
2. Disconnect from the network and ask again. You should see the "Couldn't reach the Claude service" message and a Demo answer.
3. With a valid key, ask a chip question. A spinner shows, then the answer appears captioned "Answered by Claude (claude-opus-5-5)" with verified citations.

### V6. Automated gates (Constitution workflow)

```bash
uv run pytest -q                                   # all green, no network
grep -rn "import streamlit" docmind/ && exit 1     # must find nothing
git grep -nE "sk-ant-[A-Za-z0-9]{10,}" && exit 1   # no committed keys
```

The key tests to look for:
- `test_verify.py`: a verified quote passes, a fabricated quote is rejected, and a whitespace-only difference passes.
- `test_llm_engine.py`: checks the exact `parse` kwargs (no temperature or thinking), and that each SDK error maps to its message.
- `test_engine.py`: checks the Live→Demo fallback and the four chips.
