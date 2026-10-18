# Contract: `docmind` package public API

This is the API that `app.py` and the tests use. Everything else is private (`_`-prefixed). No module
in `docmind/` imports `streamlit`. All functions that depend on dates take `today: date` explicitly, so
results are deterministic.

The entity shapes are defined in [data-model.md](../data-model.md).

## `docmind.engine`

```python
MODELS: tuple[str, ...] = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5")
DEFAULT_MODEL: str = "claude-opus-5-5"
NOT_FOUND: str = "Not found in your documents"   # re-exported from models
SUGGESTED_QUESTIONS: tuple[str, str, str, str]    # 4 chips; index 3 is the not-found chip

class Settings(BaseModel):            # frozen
    mode: Literal["demo", "live"] = "demo"
    model: str = DEFAULT_MODEL        # validated ∈ MODELS
    api_key: SecretStr | None = None  # repr=False, exclude=True
    @property
    def has_key(self) -> bool: ...
    @classmethod
    def from_inputs(cls, mode, model, pasted_key: str | None, env=os.environ) -> "Settings": ...
        # pasted key wins; else env ANTHROPIC_API_KEY; blank → None

class DocumentStore: ...              # see data-model.md

def load_samples(store, today: date) -> list[str]
    # idempotent: adds the 6 samples once (by name); returns names added
def add_upload(store, name: str, data: bytes) -> Document | None
    # on rejection: returns None and appends friendly message to store.rejected
def remove_document(store, name: str) -> None
def list_documents(store) -> list[Document]          # stable insertion order

def summarize(store, doc_name: str, settings: Settings, *, client_factory=None) -> DocumentSummary
    # demo summary always cached on add; live summary computed once per (doc_id, model)
def ensure_live_summaries(store, settings, *, client_factory=None) -> list[str]
    # runs live extraction for any doc lacking one; returns notices
def deadlines(store, settings, today: date) -> list[Deadline]
    # uses best available summary per doc (live for current model if present, else demo)
def ask(store, question: str, settings: Settings, *, client_factory=None) -> Answer
```

Guarantees:
- `ask` never raises for user or network conditions. Every failure path returns an `Answer` with friendly `notices`.
- Every `Answer`/`DocumentSummary` returned has passed through `verify`.
- `client_factory(settings) -> client` defaults to `anthropic.Anthropic(api_key=..., max_retries=0, timeout=60)`.

## `docmind.parsing`

```python
MAX_BYTES = 10 * 1024 * 1024
SUPPORTED = (".pdf", ".txt", ".md")
class ParseError(Exception): user_message: str
def load_file(name: str, data: bytes, source: DocSource = "upload") -> Document   # raises ParseError
```

## `docmind.chunking`

```python
def chunk_document(doc: Document) -> list[Chunk]   # invariant: c.text == doc.text[c.start:c.end]
```

## `docmind.retrieval`

```python
MIN_SCORE: float; MIN_COVERAGE: float
def tokenize(text: str) -> list[str]
class BM25Index:
    def __init__(self, chunks: list[Chunk], k1: float = 1.5, b: float = 0.75): ...
    def search(self, query: str, k: int = 3) -> list[tuple[Chunk, float]]
        # only hits meeting MIN_SCORE and MIN_COVERAGE; deterministic tie-break
```

## `docmind.extract_demo`

```python
def find_dates(text: str) -> list[tuple[date, int, int]]          # (value, start, end), day-first
def find_amounts(text: str) -> list[tuple[Decimal, int, int]]
def classify_doc_type(text: str) -> DocType
def label_date_role(text: str, start: int, end: int) -> DateRole
def extract(doc: Document) -> DocumentSummary                     # produced_by="demo"
```

## `docmind.llm_engine`

```python
class LiveError(Exception): user_message: str
class LiveAuthError(LiveError); class LiveRateLimitError(LiveError)
class LiveConnectionError(LiveError); class LiveServiceError(LiveError)
class LiveMalformedError(LiveError); class LiveRefusalError(LiveError)
TOKEN_BUDGET = 150_000
def estimate_tokens(text: str) -> int                  # len(text) // 4
def answer_live(client, model: str, question: str, docs: list[Document], index: BM25Index) -> Answer   # unverified; raises LiveError
def extract_live(client, model: str, doc: Document) -> DocumentSummary                                  # unverified; raises LiveError
```

See [llm-schemas.md](./llm-schemas.md) for the call shape and error mapping.

## `docmind.verify`

```python
def normalize_ws(s: str) -> str
def verify_quote(doc_text: str, quote: str) -> bool
def verify_answer(answer: Answer, docs_by_name: dict[str, Document]) -> Answer
    # drops bad citations (+ notice "An unverifiable citation was removed."); none left → NOT_FOUND
def verify_summary(summary: DocumentSummary, doc: Document) -> DocumentSummary
```

## `docmind.deadlines`

```python
DEADLINE_ROLES = frozenset({"due", "renewal", "expiry", "end", "last_date"})
def status_for(days_remaining: int) -> DeadlineStatus
def collect_deadlines(summaries: list[DocumentSummary], today: date) -> list[Deadline]   # sorted asc
```

## `docmind.samples`

```python
def build_samples(today: date) -> list[Document]   # 6 docs, source="sample", deterministic per `today`
```
