import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.schemas import AnswerContent, QuestionRequest
from app.services import qa
from app.services.qa import EvidencePage, validate_answer


def content(quote="Must be registered for at least 04 years.", page=20):
    return AnswerContent(status="answered", points=[{
        "text": "At least four years of registration is required.",
        "citations": [{"page_number": page, "quote": quote}],
    }])


def test_quotes_accept_whitespace_but_not_changed_words():
    sources = {20: "Must be registered for at least\n04 years."}
    assert validate_answer(content(), sources).status == "answered"
    assert validate_answer(content("Must be registered for at least 05 years."), sources).status == "not_found"


def test_wrong_page_rejected_even_if_quote_exists_elsewhere():
    assert validate_answer(content(page=99), {20: content().points[0].citations[0].quote}).points == []


def test_any_invalid_citation_rejects_whole_claim():
    value = content()
    value.points[0].citations.append(value.points[0].citations[0].model_copy(update={"page_number": 99}))
    assert validate_answer(value, {20: "Must be registered for at least 04 years."}).status == "not_found"


def test_rejected_claim_yields_partial_answer():
    value = content()
    value.points.append(content(page=99).points[0])
    result = validate_answer(value, {20: "Must be registered for at least 04 years."})
    assert result.status == "partial"
    assert len(result.points) == 1


def test_not_found_discards_model_claims():
    value = content()
    value.status = "not_found"
    assert validate_answer(value, {20: value.points[0].citations[0].quote}).points == []


@pytest.mark.parametrize("question", ["  ", "ab", "a" * 201])
def test_question_bounds(question):
    with pytest.raises(ValidationError):
        QuestionRequest(question=question)


async def test_empty_retrieval_does_not_need_provider_key(monkeypatch):
    monkeypatch.setattr(qa.settings, "gemini_api_key", None)
    assert (await qa.generate_answer("Who is eligible?", [])).status == "not_found"


async def test_provider_response_is_quote_checked_and_context_included(monkeypatch):
    monkeypatch.setattr(qa.settings, "gemini_api_key", "test-key")
    class Client:
        def __init__(self, **_): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass
        async def post(self, url, headers, json):
            prompt = json["contents"][0]["parts"][0]["text"]
            assert "self-reported" in prompt
            assert "Demo Company" in prompt
            assert headers["x-goog-api-key"] == "test-key"
            assert "$defs" not in str(json["generationConfig"]["responseSchema"])
            return httpx.Response(200, request=httpx.Request("POST", url), json={
                "candidates": [{"content": {"parts": [{"text": content().model_dump_json()}]}}]})
    monkeypatch.setattr(qa.httpx, "AsyncClient", Client)
    result = await qa.generate_answer("What registration is required?", [
        EvidencePage(20, "Must be registered for at least 04 years.")], {"profile": {"name": "Demo Company"}})
    assert result.status == "answered"


async def test_provider_failure_is_sanitized(monkeypatch):
    monkeypatch.setattr(qa.settings, "gemini_api_key", "test-key")
    class Client:
        def __init__(self, **_): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass
        async def post(self, url, **_):
            return httpx.Response(429, request=httpx.Request("POST", url))
    monkeypatch.setattr(qa.httpx, "AsyncClient", Client)
    with pytest.raises(qa.QuestionUnavailableError) as error:
        await qa.generate_answer("What registration?", [EvidencePage(20, "source")])
    assert "googleapis" not in str(error.value)
    assert "test-key" not in str(error.value)


async def test_retrieval_is_document_scoped_and_falls_back(monkeypatch):
    calls = []
    async def keyword(session, query, document_id):
        calls.append((query, document_id))
        return [] if len(calls) == 1 else [{"page_id": 2, "page_number": 20}]
    async def unavailable(_):
        raise qa.EmbeddingUnavailableError("offline")
    class Session:
        async def scalars(self, statement):
            assert "document_id" in str(statement)
            return [SimpleNamespace(id=2, page_number=20, text="Evidence")]
    monkeypatch.setattr(qa, "keyword_search", keyword)
    monkeypatch.setattr(qa, "embed_query", unavailable)
    pages, method = await qa.retrieve_question_pages(Session(), "doc-a", "What documents and certificates are required?")
    assert all(doc == "doc-a" for _, doc in calls)
    assert calls[1][0] == "documents OR certificates"
    assert pages == [EvidencePage(20, "Evidence")]
    assert method == "keyword"


def test_http_requires_demo_access_before_database(monkeypatch):
    from app.main import app, settings
    monkeypatch.setattr(settings, "demo_access_code", "test-code")
    response = TestClient(app).post("/documents/doc/questions", json={"question": "Who is eligible?"})
    assert response.status_code == 401


@pytest.mark.parametrize("state,expected", [(None, 404), ("processing", 409)])
async def test_endpoint_checks_document_state(state, expected):
    from fastapi import HTTPException
    from app.main import answer_document_question
    class Session:
        async def get(self, *_): return None if state is None else SimpleNamespace(status=state)
    with pytest.raises(HTTPException) as error:
        await answer_document_question("doc", QuestionRequest(question="Who is eligible?"), None, Session())
    assert error.value.status_code == expected


async def test_endpoint_releases_transaction_before_generation(monkeypatch):
    from app import main
    from app.models import Document
    class Session:
        rolled_back = False
        async def get(self, model, _):
            return SimpleNamespace(status="ready") if model is Document else SimpleNamespace(
                status="ready", profile={"name": "Demo"}, content={"comparisons": []})
        async def rollback(self): self.rolled_back = True
    session = Session()
    async def retrieve(*_): return [EvidencePage(20, "Must be registered for at least 04 years.")], "hybrid"
    async def generate(question, pages, context):
        assert session.rolled_back
        assert context["profile"]["name"] == "Demo"
        return content()
    monkeypatch.setattr(main, "retrieve_question_pages", retrieve)
    monkeypatch.setattr(main, "generate_answer", generate)
    result = await main.answer_document_question("doc", QuestionRequest(question="Who is eligible?"), None, session)
    assert result.document_id == "doc"
    assert result.searched_pages == [20]
    assert result.used_company_assessment
