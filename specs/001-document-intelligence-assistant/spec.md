# Feature Specification: DocuMind – Personal Document Intelligence Assistant

**Feature Branch**: `001-document-intelligence-assistant`

**Created**: 2026-10-18

**Status**: Draft

**Input**: User description: "DocuMind - Personal Document Intelligence Assistant. Problem: people struggle to find important information across contracts, bills, insurance policies, warranties and other documents. Requirements: (1) Documents: upload .pdf/.txt/.md files (multiple) or click 'Load sample documents' which loads 6 realistic bundled Indian-context sample documents … (2) Key information extraction per document … (3) Upcoming deadlines dashboard … (4) Ask questions across all documents in a chat UI … (5) Modes in the sidebar: Demo mode … and Live mode … Out of scope: user accounts, cloud storage, OCR of scanned images, email reminders."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Load documents and ask a grounded question (Priority: P1)

A person opens DocuMind for the first time, clicks "Load sample documents" (or uploads their own PDFs/text/Markdown files), and asks a question such as "What is the notice period for my rental agreement?". They get a short answer that names the source document and shows the exact passage it came from. If the answer is not in their documents, they are told "Not found in your documents" instead of a guess.

**Why this priority**: This is the core promise of the product — finding information across scattered documents with answers the user can trust. It alone is a viable demo and MVP.

**Independent Test**: With no API key and no network, load the sample documents, click each suggested question chip, and confirm every answer shows a document name and a quoted passage that appears word-for-word in that document, and that the "not in the documents" chip returns exactly "Not found in your documents".

**Acceptance Scenarios**:

1. **Given** the app is freshly opened with no documents, **When** the user clicks "Load sample documents", **Then** six sample documents appear in the document list, each with its name, detected type and size.
2. **Given** documents are loaded, **When** the user asks a question whose answer is in one document, **Then** the answer shows the source document name and an expandable exact quoted passage from that document.
3. **Given** documents are loaded, **When** the user asks a question whose answer spans several documents (e.g. "Which of my policies expire this year?"), **Then** the answer lists each relevant source document with its own quoted passage.
4. **Given** documents are loaded, **When** the user asks something not covered by any document (e.g. "What is my passport number?"), **Then** the app replies exactly "Not found in your documents" with no further speculation.
5. **Given** documents are loaded, **When** the user views the chat, **Then** four suggested example questions are shown as clickable chips, and clicking one asks that question.
6. **Given** no documents are loaded, **When** the user asks a question, **Then** the app prompts them to upload documents or load the samples rather than answering.
7. **Given** the user uploads several supported files at once, **When** the upload completes, **Then** each file appears in the document list and its content is included in subsequent answers.
8. **Given** a document is in the list, **When** the user removes it, **Then** it disappears from the list and is no longer used for answers, extraction or deadlines.

---

### User Story 2 - Upcoming deadlines dashboard (Priority: P2)

The user wants to know what is coming up: insurance renewals, bill due dates, lease end, warranty expiry, subscription renewal. A dashboard lists every date found across all documents, sorted soonest first, showing days remaining, a colour status (overdue / within 30 days / later) and the source document.

**Why this priority**: Missing a renewal or payment deadline is the most costly consequence of scattered documents; this view delivers value at a glance without any typing.

**Independent Test**: Load the sample documents and open the deadlines view; confirm dates are sorted ascending, days remaining are correct relative to today, colour status matches the rules, each row names its source document, and at least one deadline falls within the next 30–60 days.

**Acceptance Scenarios**:

1. **Given** sample documents are loaded, **When** the user opens the deadlines dashboard, **Then** all key dates from all documents are listed in ascending date order with a label (e.g. "Policy renewal", "Bill due"), the date, days remaining and the source document name.
2. **Given** a date is earlier than today, **When** it is displayed, **Then** it is marked "Overdue" (with negative/elapsed days shown) in the overdue colour.
3. **Given** a date is between today and 30 days from today inclusive, **When** it is displayed, **Then** it is marked "Within 30 days" in the warning colour.
4. **Given** a date is more than 30 days from today, **When** it is displayed, **Then** it is marked "Later" in the neutral colour.
5. **Given** the user selects a deadline row, **When** they expand it, **Then** they see the exact source passage the date was taken from.
6. **Given** a document is removed, **When** the dashboard refreshes, **Then** that document's dates no longer appear.

---

### User Story 3 - Key information extraction per document (Priority: P3)

For each document the user can see a structured summary: document type, parties, key dates (start, end, renewal, due), amounts (premium, rent, deposit, bill total, coverage), and obligations (e.g. notice period, payment due). Every item is linked to the exact passage it came from.

**Why this priority**: Gives a fast overview of each document and feeds the deadlines dashboard, but the user can still get value from Q&A without it.

**Independent Test**: Load the sample rental agreement and open its summary; confirm it shows type "Rental/Lease agreement", landlord and tenant names, start and end dates, monthly rent and security deposit in INR, and the notice period obligation, each with a viewable source passage that appears verbatim in the document.

**Acceptance Scenarios**:

1. **Given** a document is loaded, **When** the user opens its details, **Then** the app shows its detected type and any parties, key dates, amounts and obligations found.
2. **Given** an extracted item is shown, **When** the user expands it, **Then** the exact source passage is displayed and that passage appears in the document text.
3. **Given** amounts in the document are written in Indian formats (e.g. "₹12,500", "Rs. 1,25,000", "INR 4,999/-"), **When** the document is processed, **Then** those amounts are recognised and shown in INR.
4. **Given** dates in the document are written in common Indian formats (e.g. "15/11/2026", "15-Nov-2026", "15 November 2026"), **When** the document is processed, **Then** they are recognised as day-first calendar dates.
5. **Given** a category has no findings for a document, **When** the summary is shown, **Then** that category is shown as empty ("None found") rather than invented.

---

### User Story 4 - Choose Demo or Live mode (Priority: P4)

The sidebar always shows the current mode. Demo mode (default) works offline with no key. A user with an Anthropic API key can switch to Live mode, paste their key (or rely on a key already set in the environment), and choose a Claude model for higher-quality answers and extraction. If anything goes wrong, they get a friendly message and a suggestion to use Demo mode.

**Why this priority**: Live mode improves answer quality but is optional; the product must be fully demonstrable without it.

**Independent Test**: Start the app with no key — Demo mode is active and fully functional. Switch to Live mode with an invalid key and ask a question — a friendly "invalid API key" message appears with a suggestion to switch to Demo mode, and the app keeps working.

**Acceptance Scenarios**:

1. **Given** the app starts, **When** no choice has been made, **Then** Demo mode is active and the sidebar visibly shows "Demo mode".
2. **Given** the user selects Live mode, **When** a key is present in the environment, **Then** Live mode can be used without pasting a key; otherwise the user is asked to paste a key in a masked input.
3. **Given** Live mode is selected, **When** the user opens the model choice, **Then** they can pick claude-opus-5-5 (default), claude-sonnet-5-5 or claude-haiku-5-5.
4. **Given** Live mode with an invalid key, **When** a question is asked, **Then** the app shows a friendly invalid-key message suggesting Demo mode, and does not crash.
5. **Given** Live mode and a rate limit or network failure, **When** a question is asked, **Then** the app shows a friendly message specific to the failure (rate limited / cannot reach service) suggesting retrying later or using Demo mode.
6. **Given** Live mode returns an answer whose quote does not appear in the cited document, **When** the answer is displayed, **Then** that quote is dropped, the user sees a notice that an unverifiable citation was removed, and if no verified citation remains the answer is "Not found in your documents".
7. **Given** Live mode is waiting for a response, **When** the user looks at the screen, **Then** a visible progress indicator is shown.

---

### Edge Cases

- **Unsupported file type** (e.g. .docx, .jpg): the file is rejected with a message listing supported types (.pdf, .txt, .md); other files in the same upload still load.
- **Scanned/image-only PDF with no extractable text**: the document is listed but flagged "No readable text — scanned documents are not supported"; it contributes nothing to answers or deadlines.
- **Empty or corrupted file**: rejected with a friendly message; the app keeps running.
- **Duplicate upload (same file name)**: the new upload replaces the existing document of that name rather than creating a duplicate.
- **"Load sample documents" clicked twice**: samples are not duplicated.
- **Sample documents mixed with user uploads**: both are searched together; removing one does not affect the others.
- **Question with only weak keyword matches**: if no passage meets the relevance threshold, the answer is "Not found in your documents".
- **Ambiguous dates** (e.g. "03/04/2026"): interpreted day-first (3 April 2026), consistent with Indian convention.
- **Dates without a year or partial dates** (e.g. "the 5th of every month"): treated as a recurring obligation, not placed on the deadlines dashboard as a specific date.
- **Deadline exactly today**: shown as "Within 30 days" with "Due today".
- **Very large document** (e.g. a 100-page policy): processed without freezing the app; answers still cite exact passages.
- **Quote that differs only in whitespace/line breaks** from the document text: counts as verified; any other difference (wording, punctuation, numbers) causes it to be rejected.
- **Live mode selected but no key anywhere**: user is prompted for a key; until one is provided, questions are answered in Demo mode with a visible notice.
- **Model returns malformed/unexpected output**: treated as no verified answer ("Not found in your documents") and a friendly notice is shown; raw output is never displayed.

## Requirements *(mandatory)*

### Functional Requirements

**Documents**

- **FR-001**: Users MUST be able to upload one or more files at once in PDF, plain-text (.txt) or Markdown (.md) format.
- **FR-002**: The app MUST provide a "Load sample documents" action that loads six bundled sample documents with Indian context: a health insurance policy, a car insurance policy, a rental/lease agreement, a phone/broadband bill, a laptop warranty card, and a gym or OTT subscription contract.
- **FR-003**: Each sample document MUST contain concrete dates, amounts in INR, a policy/contract/account number, named parties and at least one obligation (e.g. notice period, payment due date).
- **FR-004**: The sample set MUST include at least two deadlines falling within the next 30–60 days of the day the samples are loaded, at least one within the next 30 days, and at least one more than 60 days away, so all dashboard colour states except possibly overdue are visible; at least one sample date SHOULD be already past to show the overdue state.
- **FR-005**: The app MUST show a document list with each document's name, detected document type and file size, and a control to remove each document.
- **FR-006**: Removing a document MUST remove it from Q&A, extraction results and the deadlines dashboard immediately.
- **FR-007**: The app MUST reject unsupported, empty or unreadable files with a friendly message without affecting other documents.

**Key information extraction**

- **FR-008**: For each document the app MUST determine a document type (at minimum: health insurance, car/motor insurance, rental/lease agreement, utility/telecom bill, warranty, subscription contract, or "Other").
- **FR-009**: For each document the app MUST extract, where present: parties; key dates labelled by role (start, end, renewal, due, expiry); amounts labelled by role (premium, rent, deposit, bill total, coverage/sum insured, fee); and obligations (e.g. notice period, payment due, claim intimation window).
- **FR-010**: Every extracted item MUST be linked to the exact source passage it came from, viewable by the user, and that passage MUST be verified to appear in the document text (whitespace differences only tolerated); unverifiable items MUST be dropped and not shown.
- **FR-011**: The app MUST recognise INR amounts in common Indian notations (₹, Rs., Rs, INR, "/-" suffix, lakh-style grouping such as 1,25,000) and day-first date formats.

**Deadlines dashboard**

- **FR-012**: The app MUST present a deadlines dashboard listing every specific calendar date extracted across all loaded documents, sorted ascending by date.
- **FR-013**: Each deadline row MUST show a label, the date, days remaining relative to today, the source document name, and access to the source passage.
- **FR-014**: Each row MUST be colour-coded and labelled with a status: "Overdue" (date before today), "Within 30 days" (today through today + 30 days inclusive), or "Later" (more than 30 days away). Status MUST NOT rely on colour alone.

**Question answering**

- **FR-015**: Users MUST be able to ask free-text questions in a chat interface that searches across all loaded documents and keeps the conversation history visible for the session.
- **FR-016**: Every answer MUST name at least one source document and include an exact quoted passage from it, shown in an expandable element next to the answer; when several documents are relevant, each MUST be listed with its own passage.
- **FR-017**: Every quoted passage MUST be verified to appear in the cited document's text (ignoring whitespace differences only); any quote failing verification MUST be dropped and not shown, and the user MUST be shown a notice that an unverifiable citation was removed.
- **FR-018**: If no verified citation supports an answer, the app MUST respond with exactly "Not found in your documents" and nothing else; it MUST never use general knowledge or guess.
- **FR-019**: The chat MUST show four clickable suggested-question chips relevant to the sample documents, at least one of which asks for information that is NOT in the samples (demonstrating the "Not found in your documents" behaviour).
- **FR-020**: In Demo mode, the app MUST rank document passages by keyword relevance to the question and MUST answer "Not found in your documents" when no passage meets a minimum relevance threshold.

**Modes and errors**

- **FR-021**: The sidebar MUST offer Demo mode and Live mode; Demo mode MUST be the default, and the active mode MUST always be visible.
- **FR-022**: Demo mode MUST work fully offline with no API key, and MUST produce the same results for the same documents, question and date.
- **FR-023**: Live mode MUST use Claude and accept a key either pasted by the user into a masked field or taken from the `ANTHROPIC_API_KEY` environment variable; the key MUST NOT be displayed back, saved to disk, logged or persisted beyond the session.
- **FR-024**: Live mode MUST let the user choose the model from claude-opus-5-5 (default), claude-sonnet-5-5 and claude-haiku-5-5.
- **FR-025**: Live-mode failures MUST produce a friendly, specific message for invalid/missing key, rate limiting and network/service unavailability, each suggesting Demo mode; the app MUST remain usable and MUST NOT crash or show raw error traces.
- **FR-026**: Live mode MUST show a visible progress indicator while waiting for a response.
- **FR-027**: In Live mode, document content MUST be sent only to the Claude service; in Demo mode, no document content leaves the user's machine.

### Key Entities

- **Document**: A loaded file. Attributes: name, source (uploaded or sample), size, detected type, extracted text, readability status.
- **Passage (chunk)**: A contiguous section of a document's text used for retrieval and citation; belongs to one document.
- **Extracted Item**: A typed fact from a document — category (party, date, amount, obligation), role label (e.g. "renewal date", "premium"), normalised value (date or INR amount where applicable), and a verified source passage.
- **Deadline**: A dated Extracted Item shown on the dashboard, with days remaining and status (Overdue / Within 30 days / Later) computed relative to today.
- **Answer**: The response to a question — answer text (or "Not found in your documents"), zero or more verified Citations, and any notices (e.g. "unverifiable citation removed").
- **Citation**: A reference from an Answer to a Document with the exact quoted passage; valid only if verified against the document text.
- **Session Settings**: Current mode (Demo/Live), chosen model, and whether a key is available (never the key's value in any visible form).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A first-time user can open the app, load the samples, ask a question and see a cited answer in under 2 minutes, with no setup beyond installing and starting the app.
- **SC-002**: In Demo mode, answers, extraction results and the deadlines dashboard appear in under 2 seconds for the six sample documents on a typical laptop.
- **SC-003**: 100% of citations and extracted-item passages shown to the user appear verbatim (whitespace aside) in the cited document — zero fabricated quotes in testing, in both modes.
- **SC-004**: 100% of questions whose answer is absent from the documents (including the suggested "not found" chip) return exactly "Not found in your documents".
- **SC-005**: Each of the three non-"not found" suggested questions returns a correct answer with the correct source document in Demo mode against the samples.
- **SC-006**: For the sample documents, the deadlines dashboard shows every dated deadline written in them, with days remaining and status correct for the current date, and at least two deadlines within the next 30–60 days.
- **SC-007**: For each sample document, extraction identifies the correct document type and at least 90% of the dates and INR amounts written in it.
- **SC-008**: Invalid key, rate limit and network failure scenarios each display a friendly, specific message and leave the app usable 100% of the time (no crash, no raw error text).

## Assumptions

- **Single user, single session**: No accounts; all documents and settings live only for the browser session and are cleared when it ends (user accounts and cloud storage are out of scope).
- **Sample dates stay current**: Because the samples must always have deadlines 30–60 days ahead "relative to today", sample-document dates are set relative to the day they are loaded (a fixed offset pattern), so the dashboard stays interesting whenever the demo is run. Given the same load date, the sample text is identical, so Demo mode stays deterministic and quotes are verified against the text actually loaded.
- **Demo-mode techniques**: Per the user's direction, Demo mode uses keyword (BM25-style) relevance ranking over document chunks with a relevance threshold, and pattern-based recognition of dates and INR amounts; document type, parties and obligations in Demo mode are found by keyword/phrase cues and may be less complete than Live mode.
- **Demo-mode answer form**: In Demo mode the "answer" is the most relevant verified passage(s) with their document names, rather than a newly written sentence; Live mode may phrase a concise answer but only alongside verified quotes.
- **Date conventions**: Dates are interpreted day-first (Indian convention); "today" is the user's local date; recurring obligations without a specific calendar date (e.g. "on or before the 5th of each month") appear as obligations, not dashboard dates.
- **File limits**: Reasonable personal-document sizes are assumed (up to ~10 MB and ~200 pages per file); text-based PDFs only — OCR of scanned images is out of scope.
- **Language**: Documents and questions are in English (Indian English conventions); other languages are not targeted.
- **Out of scope**: User accounts, cloud storage, OCR of scanned images, email or push reminders, editing documents, and exporting results.
- **Dependency**: Live mode requires the user's own Anthropic API key and internet access; all other functionality has no external dependency.
