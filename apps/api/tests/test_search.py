from app.services.search import fuse_ranked_results


def make_row(page_id: int, snippet: str) -> dict:
    return {
        "page_id": page_id,
        "document_id": "document-1",
        "filename": "tender.pdf",
        "page_number": page_id,
        "snippet": snippet,
        "extraction_method": "embedded",
        "ocr_confidence": None,
    }


def test_rrf_rewards_results_found_by_both_retrievers() -> None:
    keyword = [make_row(1, "keyword one"), make_row(2, "keyword two")]
    semantic = [make_row(2, "semantic two"), make_row(3, "semantic three")]
    semantic[0]["semantic_similarity"] = 0.88
    semantic[1]["semantic_similarity"] = 0.73

    results = fuse_ranked_results(keyword, semantic, limit=3)

    assert results[0]["page_id"] == 2
    assert results[0]["retrieval_method"] == "hybrid"
    assert results[0]["snippet"] == "keyword two"
    assert {item["retrieval_method"] for item in results[1:]} == {"keyword", "semantic"}
