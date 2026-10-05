from types import SimpleNamespace

from app.schemas import AnalysisContent, AnalysisFinding
from app.services.analysis import analysis_response_schema, build_analysis_source, validate_citations


def finding(label: str, pages: list[int]) -> AnalysisFinding:
    return AnalysisFinding(label=label, detail=f"Evidence for {label}", page_numbers=pages)


def test_build_analysis_source_preserves_page_markers(monkeypatch) -> None:
    from app.services import analysis as analysis_service

    monkeypatch.setattr(analysis_service.settings, "analysis_max_chars", 2000)
    monkeypatch.setattr(analysis_service.settings, "analysis_page_max_chars", 1000)
    pages = [
        SimpleNamespace(page_number=1, text="Submission deadline is 30 June."),
        SimpleNamespace(page_number=2, text="Bid security is mandatory."),
    ]

    source = build_analysis_source(pages)

    assert "--- PAGE 1 ---" in source
    assert "--- PAGE 2 ---" in source
    assert "Bid security is mandatory" in source


def test_validate_citations_removes_invalid_and_duplicate_pages() -> None:
    content = AnalysisContent(
        overview=finding("Overview", [1, 1, 99]),
        important_dates=[finding("Deadline", [2])],
        eligibility=[],
        mandatory_requirements=[finding("Security", [3, 50])],
        required_documents=[],
        financial_conditions=[],
        deliverables=[],
        risks=[],
    )

    cleaned = validate_citations(content, {1, 2, 3})

    assert cleaned.overview.page_numbers == [1]
    assert cleaned.important_dates[0].page_numbers == [2]
    assert cleaned.mandatory_requirements[0].page_numbers == [3]


def test_analysis_response_schema_is_inline_for_gemini_rest_api() -> None:
    schema = analysis_response_schema()

    assert "$defs" not in str(schema)
    assert schema["required"] == list(schema["properties"])
