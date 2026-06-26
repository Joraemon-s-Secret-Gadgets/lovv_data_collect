from kr_vector_index.chunks import build_chunk


def test_build_chunk_is_deterministic_for_same_item() -> None:
    item = {
        "PK": "CITY#Andong",
        "SK": "ATTRACTION#200",
        "entity_type": "attraction",
        "content_id": "200",
        "entity_id": "ATTR-200",
        "city_id": "KR-Andong",
        "city_name_en": "Andong",
        "title": "하회마을",
        "address": "경상북도 안동시 풍천면",
        "description": "관광지 설명",
        "theme": "history",
    }

    assert build_chunk(item) == build_chunk(item)


def test_build_chunk_includes_classification_tags_in_vector_payload() -> None:
    item = {
        "PK": "CITY#Andong",
        "SK": "ATTRACTION#300",
        "entity_type": "attraction",
        "content_id": "300",
        "entity_id": "ATTR-300",
        "city_id": "KR-Andong",
        "city_name_en": "Andong",
        "title": "월영교",
        "description": "야간 경관 명소",
        "theme": "night_view",
        "theme_tags": ["bridge"],
        "class_tags": ["date_course"],
        "classification": {"theme": "scenery", "tags": ["photo_spot"]},
        "category_tags": ["walk"],
    }

    chunk = build_chunk(item)

    assert "분류: date_course, walk, scenery, photo_spot" in chunk.embedding_text
    assert chunk.metadata["class_tags"] == ["date_course", "walk", "scenery", "photo_spot"]
    assert chunk.metadata["theme_tags"] == ["bridge", "night_view", "date_course", "walk", "scenery", "photo_spot"]
