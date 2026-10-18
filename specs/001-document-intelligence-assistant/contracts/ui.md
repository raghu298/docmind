# Contract: Streamlit UI (`app.py`)

`app.py` is a thin layer. It reads widgets, calls `docmind.engine`, and renders models. It contains no
parsing, retrieval, extraction or verification logic.

## Session state keys

| Key | Type | Notes |
|-----|------|-------|
| `store` | `DocumentStore` | Created once per session |
| `mode` | `"demo" \| "live"` | Default `"demo"` |
| `model` | `str` | Default `DEFAULT_MODEL` |
| `api_key_input` | `str` | Password widget value. Never rendered or logged, and not written anywhere else |
| `history` | `list[Answer]` | Chat history, for display only. It is never sent as context (FR-015) |
| `seen_uploads` | `set[str]` | `name:size:sha` of processed uploads. Prevents reprocessing on rerun |

## Sidebar (always visible)

1. The title "DocuMind" and a **mode badge**: `🟢 Demo mode (offline)` or `🔵 Live mode · {model}` (FR-021).
2. `st.radio("Mode", ["Demo", "Live"])`.
3. When Live:
   - `st.selectbox("Model", MODELS)`.
   - If `ANTHROPIC_API_KEY` is set, show the caption "Using API key from environment". Otherwise show `st.text_input("Anthropic API key", type="password")`. Until a key is present, show `st.warning("Add a key to use Live mode — questions are answered in Demo mode until then.")`.
   - On first switch to Live with a key, call `ensure_live_summaries` under `st.spinner`.
4. A **Documents** section with:
   - the "Load sample documents" button
   - `st.file_uploader("Upload", type=["pdf","txt","md"], accept_multiple_files=True)`
   - each rejection message shown as `st.error`
   - a list with one row per document: name · type · human size · `⚠ No readable text — scanned documents are not supported` if unreadable · `✕` remove button

## Views: `st.tabs(["📄 Documents", "📅 Deadlines", "💬 Ask"])`

### Documents
- An empty state that points to the sidebar actions.
- Per document, an `st.expander(f"{name} — {doc_type}")` with sections for Parties, Key dates, Amounts (₹ with Indian grouping) and Obligations. An empty section shows "None found".
- Each fact has a nested "Source" toggle that shows the exact `source_quote` in `st.markdown` blockquote/highlight.
- Summary `notices` appear as `st.info`.

### Deadlines
- Rows are sorted ascending. Columns: status chip (colour **and** text: 🔴 Overdue / 🟠 Within 30 days / 🟢 Later), label, date (`dd Mon yyyy`), days remaining ("Due today", "in 12 days", "21 days ago") and source document.
- Each row has an expander with the source quote (US2-AS5).
- The empty state reads "No upcoming deadlines found in your documents."

### Ask
- If no readable documents are loaded, show `st.info("Upload documents or load the samples to start asking questions.")`. The chips are disabled.
- Show 4 suggestion chips (`SUGGESTED_QUESTIONS`) as buttons. Clicking a chip asks that question.
- History renders with `st.chat_message("user")` / `st.chat_message("assistant")`.
  - The answer text is shown in **bold** when found. Otherwise it is exactly `Not found in your documents`.
  - The caption under each answer reads "Answered in Demo mode" / "Answered by Claude ({model})". If `fell_back`, it reads "Live mode failed — answered in Demo mode".
  - Each citation gets an `st.expander(f"📄 {doc_name}")` containing the highlighted quote. Citations are grouped by document.
  - Each notice is shown as `st.warning`/`st.info`.
- The input is `st.chat_input("Ask about your documents…")`. In Live mode the call is wrapped in `st.spinner("Asking Claude…")` (FR-026).

## Never

- Never render the API key, an exception message, a traceback or raw model output.
- Never call `st.cache_data`/`st.cache_resource` on anything that holds the key.
