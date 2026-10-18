from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from docmind import llm_engine as le
from docmind.models import NOT_FOUND, Chunk, Document, LLMAnswer, LLMCitation, LLMExtraction, LLMFact

REQ = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
SECRET = "sk-ant-PLACEHOLDER-not-a-real-key"


def status_error(cls, code):
    return cls(f"boom {SECRET}", response=httpx2.Response(code, request=REQ), body=None)


class FakeMessages:
    def __init__(self, result=None, exc=None):
        self.calls, self.result, self.exc = [], result, exc

    def parse(self, **kw):
        self.calls.append(kw)
        if self.exc:
            raise self.exc
        return self.result


class FakeClient:
    def __init__(self, **kw):
        self.messages = FakeMessages(**kw)


def ok(parsed, stop="end_turn"):
    return SimpleNamespace(stop_reason=stop, parsed_output=parsed)


TEXT = "Rental agreement between Asha (landlord) and Ravi (tenant).\nMonthly rent is Rs. 25,000.\nLease ends on 31/12/2026.\n"
DOC = Document(id="d1", name="lease.txt", source="sample", size_bytes=len(TEXT), text=TEXT)
DOC2 = Document(id="d2", name="bill.txt", source="sample", size_bytes=10, text="Total due Rs. 999.")


def good_answer():
    return LLMAnswer(found=True, answer="Rs. 25,000 per month.",
                     citations=[LLMCitation(document_name="lease.txt", quote="Monthly rent is Rs. 25,000.")])


def test_call_kwargs_shape_and_full_context():
    client = FakeClient(result=ok(good_answer()))
    a = le.answer_live(client, "claude-opus-5-5", "What is the rent?", [DOC, DOC2])
    kw = client.messages.calls[0]
    assert set(kw) == {"model", "max_tokens", "system", "messages", "output_format", "output_config"}
    assert kw["model"] == "claude-opus-5-5" and kw["max_tokens"] == 16000
    assert kw["output_format"] is LLMAnswer and kw["output_config"] == {"effort": "medium"}
    assert kw["system"] == le.ANSWER_SYSTEM
    for bad in ("temperature", "top_p", "top_k", "thinking"):
        assert bad not in kw
    content = kw["messages"][0]["content"]
    assert kw["messages"][0]["role"] == "user"
    assert '<document name="lease.txt">' in content and TEXT in content
    assert '<document name="bill.txt">' in content and content.endswith("Question: What is the rent?")
    assert a.found and a.mode == "live" and a.citations[0].doc_id == "d1"


def test_system_prompt_rules():
    s = le.ANSWER_SYSTEM.lower()
    assert "only" in s and "verbatim" in s and "found=false" in s


def test_fallback_path_when_over_budget():
    big = "filler word " * 60_000 + "Monthly rent is Rs. 25,000."
    doc = Document(id="big", name="big.txt", source="upload", size_bytes=len(big), text=big)
    assert le.estimate_tokens(big) > le.TOKEN_BUDGET
    start = big.index("Monthly")
    chunk = Chunk(id="big:9", doc_id="big", doc_name="big.txt", index=9, start=start,
                  end=len(big), text=big[start:])
    chunk0 = Chunk(id="big:0", doc_id="big", doc_name="big.txt", index=0, start=0, end=11,
                   text=big[:11])
    seen = {}

    def retrieve(question, k):
        seen["args"] = (question, k)
        return [(chunk, 3.0), (chunk0, 1.0)]

    ans = LLMAnswer(found=True, answer="Rs. 25,000",
                    citations=[LLMCitation(document_name="big.txt", quote="Monthly rent is Rs. 25,000.")])
    client = FakeClient(result=ok(ans))
    a = le.answer_live(client, "claude-haiku-5-5", "rent?", [doc], retrieve)
    content = client.messages.calls[0]["messages"][0]["content"]
    assert seen["args"] == ("rent?", 12)
    assert len(content) < 1000
    assert content.index(big[:11]) < content.index("Monthly")  # chunk order by index
    assert "\n...\n" in content
    assert a.found


def test_fallback_accepts_index_object_and_plain_list():
    big = "x" * (le.TOKEN_BUDGET * 4 + 4)
    doc = Document(id="b", name="b.txt", source="upload", size_bytes=len(big), text=big)
    c = Chunk(id="b:0", doc_id="b", doc_name="b.txt", index=0, start=0, end=5, text="xxxxx")

    class Idx:
        def search(self, q, k=3):
            return [(c, 1.0)]

    for src in (Idx(), [c]):
        content, full = le.build_answer_content("q", [doc], src)
        assert not full and "xxxxx" in content and big not in content


def test_fabricated_quote_from_llm_becomes_not_found():
    ans = LLMAnswer(found=True, answer="Rs. 30,000",
                    citations=[LLMCitation(document_name="lease.txt", quote="Monthly rent is Rs. 30,000.")])
    a = le.answer_live(FakeClient(result=ok(ans)), "claude-opus-5-5", "rent?", [DOC])
    assert a.text == NOT_FOUND and not a.found and a.notices


def test_found_false_is_not_found():
    a = le.answer_live(FakeClient(result=ok(LLMAnswer(found=False, answer="", citations=[]))),
                       "claude-opus-5-5", "pets?", [DOC])
    assert a.text == NOT_FOUND and a.mode == "live"


@pytest.mark.parametrize("exc, cls", [
    (status_error(anthropic.AuthenticationError, 401), le.LiveAuthError),
    (status_error(anthropic.PermissionDeniedError, 403), le.LivePermissionError),
    (status_error(anthropic.RateLimitError, 429), le.LiveRateLimitError),
    (anthropic.APIConnectionError(message=SECRET, request=REQ), le.LiveConnectionError),
    (anthropic.APITimeoutError(request=REQ), le.LiveConnectionError),
    (status_error(anthropic.InternalServerError, 500), le.LiveServiceError),
    (status_error(anthropic.APIStatusError, 529), le.LiveServiceError),
])
def test_error_mapping(exc, cls):
    with pytest.raises(le.LiveError) as ei:
        le.answer_live(FakeClient(exc=exc), "claude-opus-5-5", "q", [DOC])
    assert type(ei.value) is cls
    assert ei.value.user_message == cls.user_message
    assert SECRET not in ei.value.user_message and SECRET not in str(ei.value)
    assert ei.value.__cause__ is None


def test_auth_message_fixed():
    assert le.LiveAuthError().user_message == "Your Anthropic API key was rejected. Check the key in the sidebar."


def test_refusal():
    with pytest.raises(le.LiveRefusalError) as ei:
        le.answer_live(FakeClient(result=ok(None, stop="refusal")), "claude-opus-5-5", "q", [DOC])
    assert ei.value.user_message == "Claude declined to answer this question."


@pytest.mark.parametrize("resp", [ok(None), ok(good_answer(), stop="max_tokens"),
                                  ok({"found": "maybe"})])
def test_malformed(resp):
    with pytest.raises(le.LiveMalformedError):
        le.answer_live(FakeClient(result=resp), "claude-opus-5-5", "q", [DOC])


def test_extract_live_converts_and_verifies():
    facts = [
        LLMFact(category="party", role="landlord", label="Landlord", value="Asha", quote="Asha (landlord)"),
        LLMFact(category="amount", role="rent", label="Monthly rent", value="Rs. 25,000",
                amount_inr=25000.0, quote="Monthly rent is Rs. 25,000."),
        LLMFact(category="date", role="lease end", label="Lease end", value="31/12/2026",
                date_iso="2026-12-31", quote="Lease ends on 31/12/2026."),
        LLMFact(category="date", role="due", label="Bad date", value="?", date_iso="31-12-2026",
                quote="Lease ends on 31/12/2026."),
        LLMFact(category="obligation", role="pets", label="No pets", value="No pets allowed",
                quote="No pets allowed."),  # fabricated
    ]
    client = FakeClient(result=ok(LLMExtraction(doc_type="Rental agreement", facts=facts)))
    s = le.extract_live(client, "claude-sonnet-5-5", DOC)
    kw = client.messages.calls[0]
    assert kw["output_format"] is LLMExtraction and kw["system"] == le.EXTRACT_SYSTEM
    assert "Extract key facts from this document." in kw["messages"][0]["content"]
    assert s.produced_by == "live" and s.model == "claude-sonnet-5-5" and s.doc_type == "Rental agreement"
    assert [f.value for f in s.parties] == ["Asha"]
    assert s.amounts[0].amount_inr == 25000 and s.amounts[0].doc_id == "d1"
    assert len(s.dates) == 1 and s.dates[0].role == "other" and str(s.dates[0].date_value) == "2026-12-31"
    assert s.obligations == [] and s.notices  # fabricated fact dropped with notice


def test_extract_live_truncates_large_doc():
    big = "y" * (le.TOKEN_BUDGET * 4 + 100)
    doc = Document(id="b", name="b.txt", source="upload", size_bytes=len(big), text=big)
    client = FakeClient(result=ok(LLMExtraction(doc_type="Other", facts=[])))
    s = le.extract_live(client, "claude-opus-5-5", doc)
    assert le.LARGE_DOC_NOTICE in s.notices
    assert big not in client.messages.calls[0]["messages"][0]["content"]


def test_make_client_settings():
    c = le.make_client(SECRET)
    assert c.max_retries == 0 and c.timeout == 60


def test_models():
    assert le.MODELS == ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5")
    assert le.DEFAULT_MODEL == "claude-opus-5-5"
