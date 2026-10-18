from datetime import date
from decimal import Decimal

from docmind.models import NOT_FOUND, Answer, Citation, Document, DocumentSummary, KeyFact
from docmind.verify import (CITATION_DROPPED_NOTICE, FACT_DROPPED_NOTICE, normalize_ws,
                            verify_answer, verify_facts, verify_quote, verify_summary)

TEXT = "Policy No. HX-1234\nThe annual premium is Rs. 18,500\npayable by 15/03/2027.\n"
DOC = Document(id="abc123", name="health.txt", source="sample", size_bytes=len(TEXT), text=TEXT)
DOCS = {DOC.name: DOC}


def test_normalize_ws():
    assert normalize_ws("  a \n\t b  c ") == "a b c"


def test_verified_quote_exact():
    assert verify_quote(TEXT, "The annual premium is Rs. 18,500")


def test_whitespace_different_quote_accepted():
    assert verify_quote(TEXT, "premium is   Rs. 18,500 payable\n by 15/03/2027.")


def test_fabricated_quote_rejected():
    assert not verify_quote(TEXT, "The annual premium is Rs. 20,000")


def test_case_and_curly_quotes_not_tolerated():
    assert not verify_quote(TEXT, "the annual premium is rs. 18,500")
    assert not verify_quote('He said "yes".', "He said “yes”.")


def test_empty_quote_rejected():
    assert not verify_quote(TEXT, "   ")


def _answer(*cits):
    return Answer(question="q", text="It is Rs. 18,500.", found=True, citations=list(cits), mode="live")


def test_verify_answer_keeps_good_drops_bad():
    a = _answer(Citation(doc_name="health.txt", quote="annual premium is Rs. 18,500"),
                Citation(doc_name="health.txt", quote="premium is Rs. 99"))
    out = verify_answer(a, DOCS)
    assert out.found and len(out.citations) == 1
    assert out.citations[0].doc_id == "abc123"
    assert out.citations[0].start == TEXT.find("annual premium")
    assert out.notices == [CITATION_DROPPED_NOTICE]


def test_verify_answer_unknown_document_dropped():
    a = _answer(Citation(doc_name="other.txt", quote="annual premium"))
    out = verify_answer(a, DOCS)
    assert out.text == NOT_FOUND and not out.found and out.citations == []
    assert CITATION_DROPPED_NOTICE in out.notices


def test_verify_answer_all_fabricated_is_not_found():
    out = verify_answer(_answer(Citation(doc_name="health.txt", quote="invented text")), DOCS)
    assert out.text == NOT_FOUND and out.mode == "live"


def test_verify_answer_unreadable_doc_rejected():
    d = DOC.model_copy(update={"readable": False})
    out = verify_answer(_answer(Citation(doc_name="health.txt", quote="annual premium")), {d.name: d})
    assert not out.found


def _fact(quote, category="amount"):
    return KeyFact(category=category, role="premium", label="Premium", value="Rs. 18,500",
                   amount_inr=Decimal("18500"), source_quote=quote, doc_id="x", doc_name="x")


def test_verify_facts_and_summary():
    good, bad = _fact("Rs. 18,500"), _fact("Rs. 1,000")
    kept, dropped = verify_facts([good, bad], DOC)
    assert dropped == 1 and kept[0].doc_id == "abc123" and kept[0].doc_name == "health.txt"
    s = DocumentSummary(doc_id="abc123", doc_name="health.txt", doc_type="Health insurance",
                        produced_by="live", amounts=[good, bad])
    out = verify_summary(s, DOC)
    assert len(out.amounts) == 1 and out.notices == [FACT_DROPPED_NOTICE]
    clean = verify_summary(s.model_copy(update={"amounts": [good]}), DOC)
    assert clean.notices == []
