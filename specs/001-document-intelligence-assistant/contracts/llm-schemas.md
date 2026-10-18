# Contract: Live mode (Claude) requests, schemas and errors

This was verified against **anthropic 1.15.0** (httpx2 2.13.1). See [research.md §R2](../research.md).

## Client

```python
anthropic.Anthropic(api_key=<from Settings>, max_retries=0, timeout=60)
```

A new client is created per request. It is never stored outside the call and never logged.

## Call shape (the same for answers and extraction)

```python
response = client.messages.parse(
    model=settings.model,                 # one of MODELS
    max_tokens=16000,
    system=SYSTEM_PROMPT,                 # ANSWER_SYSTEM or EXTRACT_SYSTEM
    messages=[{"role": "user", "content": user_content}],
    output_format=LLMAnswer | LLMExtraction,
    output_config={"effort": "medium"},
)
```

**Forbidden kwargs**: `temperature`, `top_p`, `top_k` and `thinking`. Tests assert the exact
kwarg set.

Response handling, in this order:
1. If `response.stop_reason == "refusal"`, raise `LiveRefusalError`.
2. If `response.stop_reason in {"max_tokens", "model_context_window_exceeded"}`, raise `LiveMalformedError`.
3. Set `parsed = response.parsed_output`. If it is `None`, raise `LiveMalformedError`.
4. Convert `parsed` to domain models (see [data-model.md](../data-model.md)), then the engine runs `verify`.

## User content

**Answer, long-context path** (`estimate_tokens(all readable text) ≤ 150_000`):

```text
<documents>
<document name="{doc.name}">
{doc.text}
</document>
...
</documents>

Question: {question}
```

**Answer, over-budget path**: the same wrapper, but each `<document>` holds only that document's
chunks from the top 12 BM25 hits. The hits are retrieved **without** the relevance threshold so recall
stays high, and chunks are joined with `\n...\n`.

**Extraction**: one document per call, with the same `<document>` wrapper and the instruction
"Extract key facts from this document." If the document is over budget, its text is truncated to
`150_000 * 4` chars and the summary gets the notice "Large document: only the first part was analysed
in Live mode."

## System prompt requirements (both prompts)

- Use ONLY the provided documents. Never use outside knowledge.
- Every claim must be supported by a citation. `document_name` must exactly match a `name`
  attribute, and `quote` must be copied **verbatim**: a contiguous span from that document, no
  ellipses, no paraphrase, ≤ 300 characters.
- If the documents do not contain the answer, return `found: false`, `answer: ""` and
  `citations: []`.
- Dates are day-first (Indian convention). Output dates as `YYYY-MM-DD` and amounts in INR.
- Answers are concise, in plain English, with no markdown headings.

## Schemas (`output_format`)

```python
class LLMCitation(BaseModel):
    document_name: str
    quote: str

class LLMAnswer(BaseModel):
    found: bool
    answer: str
    citations: list[LLMCitation]

class LLMFact(BaseModel):
    category: Literal["party", "date", "amount", "obligation"]
    role: str            # dates: due|renewal|expiry|end|last_date|start|issue|bill|purchase|other
    label: str
    value: str
    date_iso: str | None
    amount_inr: float | None
    quote: str

class LLMExtraction(BaseModel):
    doc_type: Literal["Health insurance", "Car insurance", "Rental agreement",
                      "Utility/Telecom bill", "Warranty", "Subscription", "Other"]
    facts: list[LLMFact]
```

These schemas avoid constraints that structured outputs may not support (no regex `pattern`,
no `minLength`, and no numeric bounds). The engine validates those things in Python after
parsing.

## Error mapping (fixed user-facing messages)

| Raised by SDK / condition | Engine exception | Message shown |
|---------------------------|------------------|---------------|
| `anthropic.AuthenticationError` | `LiveAuthError` | "Your Anthropic API key was rejected. Check the key in the sidebar." |
| `anthropic.RateLimitError` | `LiveRateLimitError` | "Claude is rate-limiting requests right now. Please wait a moment and try again." |
| `anthropic.APIConnectionError` (incl. `APITimeoutError`) | `LiveConnectionError` | "Couldn't reach the Claude service. Check your internet connection." |
| `anthropic.APIStatusError` (any other status) | `LiveServiceError` | "The Claude service returned an error. Please try again later." |
| `pydantic.ValidationError`, `parsed_output is None`, truncated output | `LiveMalformedError` | "Claude returned an unexpected response, so it was not shown." |
| `stop_reason == "refusal"` | `LiveRefusalError` | "Claude declined to answer this question." |
| No key available in Live mode | (handled before any call) | "Live mode needs an API key — answered in Demo mode." |

The `except` order is `AuthenticationError` → `RateLimitError` → `APIConnectionError` →
`APIStatusError` → `ValidationError`, because the first two subclass `APIStatusError`. On any
`LiveError` the engine appends "Answered in Demo mode instead." and returns the Demo answer
(`fell_back=True`). Raw exception text and tracebacks are never displayed or logged.

## Test doubles

```python
import httpx2, anthropic
REQ = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
def status_error(cls, code):  return cls("x", response=httpx2.Response(code, request=REQ), body=None)
def conn_error():             return anthropic.APIConnectionError(request=REQ)

class FakeMessages:
    def __init__(self, result=None, exc=None): self.calls, self.result, self.exc = [], result, exc
    def parse(self, **kw):
        self.calls.append(kw)
        if self.exc: raise self.exc
        return self.result     # SimpleNamespace(stop_reason="end_turn", parsed_output=LLMAnswer(...))
class FakeClient:
    def __init__(self, **kw): self.messages = FakeMessages(**kw)
```
