from types import SimpleNamespace

import httpx
import pytest
from fastapi import BackgroundTasks, HTTPException
from fastapi.testclient import TestClient

from app.main import app, get_session, settings, start_assessment
from app.models import DocumentAnalysis, DocumentAssessment
from app.schemas import AnalysisContent, CompanyProfile, RequirementComparison
from app.services import assessment as service


def profile() -> CompanyProfile:
    return CompanyProfile(name="Example Ltd", capabilities="Electrical maintenance", registrations="No PEC registration")


def requirement(index=0, mandatory=True, pages=None) -> dict:
    return {
        "requirement_id": f"eligibility:{index}", "category": "eligibility", "label": "PEC registration",
        "requirement": "Active PEC registration required", "page_numbers": [2] if pages is None else pages,
        "mandatory": mandatory,
    }


def comparison(index=0, status="met", evidence="Electrical maintenance") -> RequirementComparison:
    return RequirementComparison(requirement_id=f"eligibility:{index}", status=status,
                                 reason="Compared to supplied company evidence", profile_evidence=evidence)


def test_confirmed_mandatory_gap_blocks_bid_even_with_high_score():
    result = service.score_assessment(profile(), [requirement(i) for i in range(10)], [
        *[comparison(i) for i in range(9)], comparison(9, "unmet", "No PEC registration"),
    ])
    assert result.score == 90
    assert result.coverage == 100
    assert result.recommendation == "no_bid"


def test_missing_comparison_is_unknown_and_blocks_bid():
    result = service.score_assessment(profile(), [requirement(0), requirement(1)], [comparison(0)])
    assert result.score == 50
    assert result.coverage == 50
    assert result.comparisons[1].status == "unknown"
    assert result.recommendation == "review_required"


def test_invented_profile_evidence_cannot_raise_score():
    result = service.score_assessment(profile(), [requirement()], [comparison(evidence="PEC C6 certified")])
    assert result.score == 0
    assert result.comparisons[0].status == "unknown"


def test_missing_tender_citation_cannot_produce_bid():
    result = service.score_assessment(profile(), [requirement(pages=[])], [comparison()])
    assert result.recommendation == "review_required"


def test_all_matched_requirements_produce_bid():
    result = service.score_assessment(profile(), [requirement()], [comparison()])
    assert result.score == result.coverage == 100
    assert result.recommendation == "bid"


def test_empty_requirements_produce_review():
    result = service.score_assessment(profile(), [], [])
    assert result.recommendation == "review_required"
    assert result.score == result.coverage == 0


def test_private_assessment_routes_require_access_code(monkeypatch):
    monkeypatch.setattr(settings, "demo_access_code", "test-only-secret")

    async def unused_session():
        yield None

    app.dependency_overrides[get_session] = unused_session
    try:
        client = TestClient(app)
        try:
            assert client.get("/documents/sample/assessment").status_code == 401
            assert client.post("/documents/sample/assessment", json=profile().model_dump()).status_code == 401
        finally:
            client.close()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_assessment_requires_completed_analysis():
    class Session:
        async def scalar(self, _):
            return SimpleNamespace(status="ready")

        async def get(self, model, _):
            return None

    tasks = BackgroundTasks()
    with pytest.raises(HTTPException) as error:
        await start_assessment("doc", profile(), tasks, None, Session())
    assert error.value.status_code == 409
    assert not tasks.tasks


@pytest.mark.asyncio
async def test_completed_analysis_queues_profile_snapshot_without_calling_provider():
    snapshot = {"overview": {"label": "Tender", "detail": "Scope", "page_numbers": [1]}}

    class Session:
        saved = None
        async def scalar(self, _): return SimpleNamespace(status="ready")
        async def get(self, model, _):
            return SimpleNamespace(status="ready", content=snapshot) if model is DocumentAnalysis else None
        def add(self, item): self.saved = item
        async def commit(self): pass
        async def refresh(self, _): pass

    session, tasks = Session(), BackgroundTasks()
    result = await start_assessment("doc", profile(), tasks, None, session)
    assert result is session.saved
    assert result.status == "queued"
    assert result.profile["name"] == "Example Ltd"
    assert result.content is None
    assert len(tasks.tasks) == 1
    assert tasks.tasks[0].args == ("doc", snapshot)


@pytest.mark.asyncio
async def test_running_assessment_cannot_be_overwritten():
    class Session:
        async def scalar(self, _): return SimpleNamespace(status="ready")
        async def get(self, model, _):
            return SimpleNamespace(status="ready", content={"overview": "Tender"}) if model is DocumentAnalysis else SimpleNamespace(status="processing")

    tasks = BackgroundTasks()
    with pytest.raises(HTTPException) as error:
        await start_assessment("doc", profile(), tasks, None, Session())
    assert error.value.status_code == 409
    assert not tasks.tasks


@pytest.mark.asyncio
async def test_background_provider_failure_records_retryable_state(monkeypatch):
    saved = SimpleNamespace(profile=profile().model_dump(), status="queued", error_message=None)

    class Session:
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass
        async def get(self, model, _):
            assert model is DocumentAssessment
            return saved
        async def commit(self): pass

    async def fail(*_): raise RuntimeError("Provider quota reached")
    monkeypatch.setattr(service, "SessionLocal", Session)
    monkeypatch.setattr(service, "compare_requirements", fail)
    content = AnalysisContent(
        overview={"label": "Tender", "detail": "Scope", "page_numbers": [1]},
        important_dates=[], eligibility=[], mandatory_requirements=[], required_documents=[],
        financial_conditions=[], deliverables=[], risks=[],
    )
    await service.assess_document("doc", content.model_dump())
    assert saved.status == "failed"
    assert saved.error_message == "Provider quota reached"


@pytest.mark.asyncio
async def test_provider_comparisons_preserve_server_citations(monkeypatch):
    content = AnalysisContent(
        overview={"label": "Tender", "detail": "Maintenance", "page_numbers": [1]},
        eligibility=[{"label": "Capability", "detail": "Electrical maintenance", "page_numbers": [2]}],
        mandatory_requirements=[], required_documents=[], financial_conditions=[], deliverables=[],
        risks=[], important_dates=[],
    )
    monkeypatch.setattr(service.settings, "gemini_api_key", "test-only-key")

    class Client:
        def __init__(self, **_): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass
        async def post(self, url, headers, json):
            assert "generateContent" in url
            assert "Electrical maintenance" in json["contents"][0]["parts"][0]["text"]
            return httpx.Response(200, request=httpx.Request("POST", url), json={
                "candidates": [{"content": {"parts": [{"text": '{"comparisons":[{"requirement_id":"eligibility:0","status":"met","reason":"Supported capability","profile_evidence":"Electrical maintenance"}]}'}]}}],
            })

    monkeypatch.setattr(service.httpx, "AsyncClient", Client)
    result = await service.compare_requirements(profile(), content)
    assert result.comparisons[0].page_numbers == [2]
    assert result.recommendation == "bid"
