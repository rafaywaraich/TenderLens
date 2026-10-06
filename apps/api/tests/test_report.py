from types import SimpleNamespace

import pymupdf
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.schemas import AnalysisContent, AssessmentContent, CompanyProfile
from app.services.report import build_report


def sample_analysis():
    finding = {"label": "Tax registration", "detail": "Active NTN and GST registration are required.", "page_numbers": [3, 7]}
    return AnalysisContent(overview={"label": "Office IT equipment procurement", "detail": "Supply and install equipment for an Islamabad office.", "page_numbers": [1]},
        important_dates=[{"label": "Submission deadline", "detail": "9 June 2025 at 10:30 AM (historical).", "page_numbers": [1]}],
        eligibility=[finding], mandatory_requirements=[finding], required_documents=[finding],
        financial_conditions=[{"label": "Bid security", "detail": "Lot 1: PKR 379,500. Clarify the separate 5% clause.", "page_numbers": [5, 7]}],
        deliverables=[{"label": "Delivery", "detail": "Deliver and install IT equipment within one week.", "page_numbers": [14]}],
        risks=[{"label": "Security ambiguity", "detail": "Fixed amounts and a percentage appear in different clauses.", "page_numbers": [5, 7]}])


def sample_assessment(long=False):
    return AssessmentContent(company_name="Capital Office Solutions / Demo", recommendation="review_required", score=75, coverage=80,
        summary="Positive capabilities; review the security ambiguity before making a decision.", evaluated_on="2026-10-06",
        comparisons=[dict(requirement_id=f"eligibility:{i}", category="eligibility", label="Tax registration",
            requirement="Active NTN and GST registration", page_numbers=[3, 7], mandatory=True,
            status="unknown", reason="Supporting registration details need review.", profile_evidence="",
            missing_information="Provide registration identifiers and supporting records.",
            suggested_input="NTN: [identifier]; GST: [identifier]; active taxpayer status: [date].",
            entered_information=[{"field": "registrations", "value": "Registered supplier. " * (180 if long else 1)}])
            for i in range(8 if long else 1)])


def test_pdf_contains_saved_evidence_snapshot_and_disclaimer():
    profile = CompanyProfile(name="Demo & Sons <test>", capabilities="IT supply", registrations="Active NTN")
    pdf = build_report("Office <tender>.pdf", 17, sample_analysis(), sample_assessment(), profile)
    assert pdf.startswith(b"%PDF-")
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        text = "\n".join(p.get_text() for p in doc)
        assert "75%" in text and "80%" in text
        assert "Source PDF pages: 3, 7" in text
        assert "self-reported" in text
        assert "Demo & Sons <test>" in text
        assert "Answer template" in text


def test_tender_only_export_is_explicit():
    with pymupdf.open(stream=build_report("Tender.pdf", 17, sample_analysis()), filetype="pdf") as doc:
        assert "No company assessment included" in " ".join(p.get_text() for p in doc)


def test_long_profile_and_comparisons_paginate_without_losing_last_content():
    profile = CompanyProfile(name="Long Demo", capabilities="Maintenance & procurement. " * 200, constraints="FINAL SNAPSHOT SENTINEL")
    with pymupdf.open(stream=build_report("long.pdf", 17, sample_analysis(), sample_assessment(True), profile), filetype="pdf") as doc:
        assert len(doc) > 5
        text = " ".join(p.get_text() for p in doc)
        assert "FINAL SNAPSHOT SENTINEL" in text
        assert "Report page" in text
        for page in doc:
            for block in page.get_text("blocks"):
                assert block[1] >= 0 and block[3] < page.rect.height


def test_invalid_source_page_numbers_are_not_presented_as_valid():
    analysis = sample_analysis()
    analysis.overview.page_numbers = [0, -1, 99]
    with pymupdf.open(stream=build_report("Tender.pdf", 17, analysis), filetype="pdf") as doc:
        assert "No valid page citation" in doc[0].get_text()


def test_export_requires_demo_code():
    from app.main import app, settings
    old = settings.demo_access_code
    settings.demo_access_code = "test-only"
    try:
        assert TestClient(app).get("/documents/doc/report").status_code == 401
    finally:
        settings.demo_access_code = old


@pytest.mark.parametrize("state,expected", [(None, 404), ("processing", 409)])
async def test_export_requires_ready_document_and_analysis(state, expected):
    from app.main import download_report
    from app.models import Document
    class Session:
        async def get(self, model, _):
            return None if state is None else SimpleNamespace(status=state) if model is Document else None
    with pytest.raises(HTTPException) as error:
        await download_report("doc", True, None, Session())
    assert error.value.status_code == expected


async def test_export_waits_for_assessment_or_allows_tender_only():
    from app.main import download_report
    from app.models import Document, DocumentAnalysis
    class Session:
        async def get(self, model, _):
            if model is Document: return SimpleNamespace(status="ready", filename="test.pdf", page_count=17)
            if model is DocumentAnalysis: return SimpleNamespace(status="ready", content=sample_analysis().model_dump(), updated_at="today")
            return SimpleNamespace(status="processing")
        async def rollback(self): pass
    with pytest.raises(HTTPException) as error:
        await download_report("doc", True, None, Session())
    assert error.value.status_code == 409
    result = await download_report("doc", False, None, Session())
    assert result.media_type == "application/pdf"
    assert result.headers["cache-control"] == "no-store"
    assert result.body.startswith(b"%PDF-")
