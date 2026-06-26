from kr_vector_index.export import should_vectorize


def test_should_vectorize_excludes_visitor_statistics() -> None:
    assert should_vectorize({"entity_type": "visitor_statistics", "quality_status": "passed"}) is False


def test_should_vectorize_requires_passed_quality() -> None:
    assert should_vectorize({"entity_type": "attraction", "quality_status": "review"}) is False
    assert should_vectorize({"entity_type": "attraction", "quality_status": "passed"}) is True
