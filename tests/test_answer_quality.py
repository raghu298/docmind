"""Regression tests for Demo-mode answer quality, deadlines and extraction labels (review, 2026-10-18)."""
from datetime import date, timedelta

import pytest

from docmind import engine
from docmind.deadlines import collect_deadlines
from docmind.models import NOT_FOUND, DocumentSummary, KeyFact

TODAY = date(2026, 10, 18)


@pytest.fixture(scope="module")
def store():
    s = engine.DocumentStore()
    engine.load_samples(s, TODAY)
    return s


@pytest.mark.parametrize("question, must_contain", [
    ("What is my broadband bill amount?", "1,414.82"),             # amount line, not "Bill Date"
    ("When is my broadband bill due and how much do I owe?", "1,414.82"),
    ("How much do I owe for broadband?", "1,414.82"),              # owe -> due (synonym retry)
    ("What does the gym membership cost?", "28,000"),              # cost -> fee
    ("Who is my insurer?", "Star Shield General Insurance Co. Ltd."),  # label line, not "...to the insurer"
    ("Who is my landlord?", "Mr. Suresh Kumar (Landlord) and Mr. Raghav Menon"),  # wrapped line joined
    ("How much does the extended warranty cost?", "before the standard warranty expires"),
    ("Can I cancel my gym membership and get a refund?", "No refund"),
    ("When does my rental agreement end?", "Term: 11 months"),
    ("How long is the gym membership freeze allowed?", "30 days"),
    ("What is the grace period for health insurance renewal?", "grace period of 30 days"),
    ("What is the policy number of my health insurance?", "SSH/2025/4471982"),  # not the title line
    ("What is my broadband plan?", "Fiber Max"),
])
def test_demo_answer_picks_the_right_sentence(store, question, must_contain):
    a = engine.ask(store, question, engine.Settings())
    assert a.found and must_contain in a.text


@pytest.mark.parametrize("question", [
    "When is my car service due?",   # "service ... due" is in the broadband bill: must not answer
    "passport expiry date",          # "expiry" -> "valid" must not match the warranty
    "When does my driving licence expire?",
    "What is my PAN number?",
])
def test_no_made_up_answers(store, question):
    a = engine.ask(store, question, engine.Settings())
    assert not a.found and a.text == NOT_FOUND and a.citations == []


def test_one_deadline_per_document_and_date(store):
    dls = engine.deadlines(store, engine.Settings(), TODAY)
    assert len({(d.doc_id, d.date) for d in dls}) == len(dls)
    health = [d for d in dls if d.doc_name == "Health_Insurance_Policy.txt"]
    assert [d.role for d in health] == ["renewal"]        # renewal beats "policy end" on the same day
    assert sum(d.status == "within_30" for d in dls) == 2  # laptop warranty + health renewal


def _fact(day: date) -> KeyFact:
    return KeyFact(category="date", role="due", label="Payment due", value="x", date_value=day,
                   source_quote="x", doc_id="d", doc_name="d.txt")


def test_old_dates_are_not_deadlines():
    s = DocumentSummary(doc_id="d", doc_name="d.txt", doc_type="Other", produced_by="demo",
                        dates=[_fact(date(2002, 7, 1)), _fact(TODAY - timedelta(days=3))])
    dls = collect_deadlines([s], TODAY)
    assert [d.days_remaining for d in dls] == [-3]


def test_extraction_labels(store):
    health = engine.cached_summary(store, "Health_Insurance_Policy.txt", engine.Settings())
    amounts = {f.label: f.value for f in health.amounts}
    assert amounts["Room rent limit"] == "Rs. 10,000" and amounts["Sum insured"] == "Rs. 10,00,000"
    assert "Policy start" in {f.label for f in health.dates}
