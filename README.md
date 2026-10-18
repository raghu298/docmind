# 📄 DocuMind — Personal Document Intelligence Assistant

Build with AI · Challenge 05. Ask questions across your contracts, bills, insurance policies and
warranties, and get answers **linked to the exact source passage**, never a made-up one.
Built with [Spec Kit](https://github.com/github/spec-kit) (see `specs/` and `.specify/memory/constitution.md`).

## Features
- Upload `.pdf` / `.txt` / `.md` files, or load 6 sample Indian documents (health and car insurance,
  rental agreement, broadband bill, laptop warranty, gym membership).
- **Key information** per document: parties, dates, ₹ amounts, obligations, each with its source passage.
- **Deadlines dashboard**: renewals, due dates and expiries with days remaining (overdue / within 30 days / later).
- **Ask**: chat across all documents; each answer cites the document and quotes the passage.
- **No fabrication**: if the answer isn't in your documents you get *"Not found in your documents"*.

## How it works
| | Demo mode (offline, default) | Live mode (Claude) |
|---|---|---|
| Retrieval | Pure-Python BM25 over paragraph chunks, with a relevance threshold | Full documents in context (long-context grounding); BM25 top passages only above ~150k tokens |
| Extraction | Regex for Indian date formats and ₹ / Rs. / INR amounts | Claude structured output (Pydantic) |
| Grounding | Quotes are verbatim chunks | Every quote is **verified** against the document text; unverifiable quotes are dropped |

There's no vector DB: a personal document set fits in Claude's context, and exact terms (policy
numbers, amounts, dates) suit keyword search. The next step at scale would be hybrid BM25 + vector search.

## Run locally
```bash
uv sync
uv run streamlit run app.py
uv run pytest -q
```

## Deploy to Streamlit Community Cloud
1. Go to https://share.streamlit.io and sign in with GitHub.
2. **Create app → Deploy a public app from GitHub**: repo `raghu298/docmind`, branch `main`, main file `app.py`.
3. Optional, to let judges use Live mode with your key: **Advanced settings → Secrets**:
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   ACCESS_CODE = "choose-a-code"
   ```
   Visitors unlock Live mode with the access code (capped at 20 Live requests per session);
   the key is never shown. Without secrets, the app runs in Demo mode and visitors can paste their own key.

## 2-minute demo script
1. **Problem (15 s):** "Important dates and amounts are buried in PDFs: renewals get missed, deposits forgotten."
2. **Load sample documents (15 s):** show the metrics (3 due within 30 days, 1 overdue).
3. **Deadlines (20 s):** the overdue broadband bill and the health-insurance renewal in 25 days, each with its source passage.
4. **Documents (20 s):** extracted parties, dates, ₹ amounts and obligations, each linked to its passage.
5. **Ask (40 s):** "What is the notice period in my rental agreement?" → cited answer. Then
   "What is my life insurance policy's death benefit?" → **Not found in your documents**: it never guesses.
6. **Next (10 s):** email/calendar reminders, OCR for scanned docs, hybrid search for large archives.
