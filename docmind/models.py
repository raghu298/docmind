"""Pydantic models shared by Demo and Live modes (see specs/001-*/data-model.md)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

DocType = Literal["Health insurance", "Car insurance", "Rental agreement", "Utility/Telecom bill",
                  "Warranty", "Subscription", "Other"]
DocSource = Literal["sample", "upload"]
FactCategory = Literal["party", "date", "amount", "obligation"]
DateRole = Literal["due", "renewal", "expiry", "end", "last_date", "start", "issue", "bill",
                   "purchase", "other"]
AmountRole = Literal["premium", "rent", "deposit", "bill_total", "coverage", "fee", "amount"]
DeadlineStatus = Literal["overdue", "within_30", "later"]
Mode = Literal["demo", "live"]

NOT_FOUND = "Not found in your documents"


class Document(BaseModel):
    id: str
    name: str
    source: DocSource
    size_bytes: int = Field(ge=0)
    text: str
    doc_type: DocType = "Other"
    readable: bool = True


class Chunk(BaseModel):
    id: str
    doc_id: str
    doc_name: str
    index: int
    start: int
    end: int
    text: str


class KeyFact(BaseModel):
    category: FactCategory
    role: str
    label: str
    value: str
    date_value: date | None = None
    amount_inr: Decimal | None = Field(default=None, ge=0)
    source_quote: str
    doc_id: str
    doc_name: str


class DocumentSummary(BaseModel):
    doc_id: str
    doc_name: str
    doc_type: DocType
    produced_by: Mode
    model: str | None = None
    parties: list[KeyFact] = []
    dates: list[KeyFact] = []
    amounts: list[KeyFact] = []
    obligations: list[KeyFact] = []
    notices: list[str] = []


class Deadline(BaseModel):
    label: str
    role: DateRole
    date: date
    days_remaining: int
    status: DeadlineStatus
    status_text: str
    doc_id: str
    doc_name: str
    source_quote: str


class Citation(BaseModel):
    doc_name: str
    doc_id: str | None = None
    quote: str = Field(min_length=1)
    start: int | None = None


class Answer(BaseModel):
    question: str
    text: str
    found: bool
    citations: list[Citation] = []
    mode: Mode
    fell_back: bool = False
    notices: list[str] = []

    @model_validator(mode="after")
    def _invariant(self) -> "Answer":
        if not self.citations:
            if self.text != NOT_FOUND or self.found:
                raise ValueError("an answer without citations must be NOT_FOUND with found=False")
        elif not self.found:
            raise ValueError("found must be True when citations exist")
        return self

    @classmethod
    def not_found(cls, question: str, mode: Mode, notices: list[str] | None = None,
                  fell_back: bool = False) -> "Answer":
        return cls(question=question, text=NOT_FOUND, found=False, citations=[], mode=mode,
                   fell_back=fell_back, notices=list(notices or []))


# ---- LLM wire models (output_format only) ----
class LLMCitation(BaseModel):
    document_name: str
    quote: str


class LLMAnswer(BaseModel):
    found: bool
    answer: str
    citations: list[LLMCitation]


class LLMFact(BaseModel):
    category: FactCategory
    role: str
    label: str
    value: str
    date_iso: str | None = None
    amount_inr: float | None = None
    quote: str


class LLMExtraction(BaseModel):
    doc_type: DocType
    facts: list[LLMFact]
