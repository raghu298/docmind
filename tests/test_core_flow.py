"""Tests for samples, parsing, chunking, retrieval, extraction, deadlines and engine routing."""
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from docmind import engine
from docmind.chunking import chunk_document
from docmind.deadlines import DEADLINE_ROLES, collect_deadlines
from docmind.extract_demo import classify_doc_type, extract, find_amounts, find_dates
from docmind.models import NOT_FOUND, LLMAnswer, LLMCitation
from docmind.parsing import ParseError, load_file
from docmind.retrieval import BM25Index
from docmind.samples import SUGGESTED_QUESTIONS, build_samples

TODAY = date(2026, 10, 18)


@pytest.fixture
def store():
    s = engine.DocumentStore()
    engine.load_samples(s, TODAY)
    return s


# ---- samples / parsing / chunking ----
@pytest.mark.parametrize("today", [TODAY, date(2027, 2, 28), date(2028, 12, 31)])
def test_samples_always_have_upcoming_and_overdue_deadlines(today):
    s = engine.DocumentStore()
    engine.load_samples(s, today)
    dls = engine.deadlines(s, engine.Settings(), today)
    statuses = {d.status for d in dls}
    assert {"overdue", "within_30", "later"} <= statuses
    assert len(build_samples(today)) == 6


def test_load_samples_is_idempotent(store):
    assert engine.load_samples(store, TODAY) == []
    assert len(engine.list_documents(store)) == 6


def test_parsing_rules():
    doc = load_file("a.txt", b"Rent: Rs. 5,000\r\nDue 05/11/2026")
    assert doc.readable and "\r" not in doc.text and doc.source == "upload"
    assert not load_file("blank.md", b"   ").readable
    with pytest.raises(ParseError):
        load_file("x.docx", b"hello")
    with pytest.raises(ParseError):
        load_file("big.txt", b"x" * (10 * 1024 * 1024 + 1))
    with pytest.raises(ParseError):
        load_file("bad.pdf", b"not a pdf")


def test_chunk_offsets_match_text():
    for doc in build_samples(TODAY):
        chunks = chunk_document(doc)
        assert chunks
        for c in chunks:
            assert c.text == doc.text[c.start:c.end] and c.text.strip()


# ---- extraction ----
def test_date_and_amount_formats():
    text = "Due 15/11/2026, renew 15-Nov-2026 or 2 December 2026. Pay ₹1,25,000 or Rs. 999 or INR 12,500/-"
    assert {d for d, _, _ in find_dates(text)} == {date(2026, 11, 15), date(2026, 12, 2)}
    assert {int(a) for a, _, _ in find_amounts(text)} >= {125000, 999, 12500}


def test_doc_types_classified():
    types = {d.name: classify_doc_type(d.text) for d in build_samples(TODAY)}
    assert types["Health_Insurance_Policy.txt"] == "Health insurance"
    assert types["Rental_Agreement.txt"] == "Rental agreement"
    assert types["Broadband_Bill.txt"] == "Utility/Telecom bill"
    assert types["Laptop_Warranty.txt"] == "Warranty"


def test_every_extracted_fact_quote_is_in_the_document():
    for doc in build_samples(TODAY):
        sm = extract(doc)
        for f in sm.parties + sm.dates + sm.amounts + sm.obligations:
            assert f.source_quote in doc.text


def test_deadlines_sorted_and_dedupe(store):
    dls = engine.deadlines(store, engine.Settings(), TODAY)
    assert [d.date for d in dls] == sorted(d.date for d in dls)
    assert all(d.role in DEADLINE_ROLES for d in dls)
    assert len({(d.doc_id, d.date, d.role) for d in dls}) == len(dls)
    renewal = [d for d in dls if d.doc_name == "Health_Insurance_Policy.txt" and d.role == "renewal"]
    assert renewal and renewal[0].date == TODAY + timedelta(days=25) and renewal[0].status == "within_30"
    assert collect_deadlines([], TODAY) == []


# ---- retrieval / Q&A ----
def test_bm25_unrelated_query_returns_nothing(store):
    assert store.index.search("mutual fund NAV passport visa", k=3) == []


@pytest.mark.parametrize("q,expect", [
    ("When is my health insurance renewal due?", "renewal"),
    ("What is the notice period in my rental agreement?", "two (2) months"),
    ("How much is my security deposit?", "1,50,000"),
    ("What is my car's IDV?", "9,40,000"),
])
def test_demo_answers_are_cited(store, q, expect):
    a = engine.ask(store, q, engine.Settings())
    assert a.found and a.mode == "demo" and a.citations
    assert expect in a.text or any(expect in c.quote for c in a.citations)
    for c in a.citations:
        assert c.quote in store.docs[c.doc_name].text


@pytest.mark.parametrize("q", [SUGGESTED_QUESTIONS[-1], "What is my mutual fund NAV?", "passport expiry date"])
def test_unanswerable_questions_are_not_found(store, q):
    a = engine.ask(store, q, engine.Settings())
    assert not a.found and a.text == NOT_FOUND and a.citations == []


def test_no_documents_and_remove(store):
    empty = engine.DocumentStore()
    assert engine.ask(empty, "anything", engine.Settings()).text == NOT_FOUND
    engine.remove_document(store, "Rental_Agreement.txt")
    assert "Rental_Agreement.txt" not in store.docs
    a = engine.ask(store, "What is the notice period in my rental agreement?", engine.Settings())
    assert all(c.doc_name != "Rental_Agreement.txt" for c in a.citations)


# ---- live mode routing (Claude mocked) ----
def _client(parsed, stop="end_turn"):
    calls = []

    def parse(**kw):
        calls.append(kw)
        return SimpleNamespace(stop_reason=stop, parsed_output=parsed)

    return SimpleNamespace(messages=SimpleNamespace(parse=parse), calls=calls)


def _live():
    return engine.Settings(mode="live", api_key="sk-test")


def test_live_answer_verified_and_full_context(store):
    quote = "Notice Period: Either party may terminate this agreement by giving two (2) months' written notice."
    fake = _client(LLMAnswer(found=True, answer="Two months' written notice.",
                             citations=[LLMCitation(document_name="Rental_Agreement.txt", quote=quote)]))
    a = engine.ask(store, "notice period?", _live(), client_factory=lambda s: fake)
    assert a.found and a.mode == "live" and a.citations[0].doc_name == "Rental_Agreement.txt"
    sent = fake.calls[0]["messages"][0]["content"]
    assert all(f'name="{d.name}"' in sent for d in store.readable_docs())  # Principle VIII


def test_live_fabricated_quote_becomes_not_found(store):
    fake = _client(LLMAnswer(found=True, answer="Your death benefit is Rs. 1 crore.",
                             citations=[LLMCitation(document_name="Health_Insurance_Policy.txt",
                                                    quote="Death benefit: Rs. 1,00,00,000")]))
    a = engine.ask(store, "death benefit?", _live(), client_factory=lambda s: fake)
    assert not a.found and a.text == NOT_FOUND


def test_live_refusal_and_no_key_fall_back_to_demo(store):
    fake = _client(None, stop="refusal")
    a = engine.ask(store, "How much is my security deposit?", _live(), client_factory=lambda s: fake)
    assert a.fell_back and a.mode == "demo" and a.found
    b = engine.ask(store, "How much is my security deposit?", engine.Settings(mode="live"))
    assert b.fell_back and b.mode == "demo"


def test_settings_never_expose_key():
    s = _live()
    assert "sk-test" not in repr(s) and "sk-test" not in s.model_dump_json()
