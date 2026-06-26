from kr_vector_index.chunks import VectorChunk
from kr_vector_index.upsert import build_vector_record, chunked, put_vectors_cli, put_vectors_sdk


def test_build_vector_record_matches_s3vectors_shape() -> None:
    chunk = VectorChunk(
        key="attraction#100#0",
        place_id="attraction#100",
        embedding_text="관광지 문서",
        metadata={"country": "KR", "entity_type": "attraction"},
    )

    record = build_vector_record(chunk, [0.1, 0.2, 0.3])

    assert record == {
        "key": "attraction#100#0",
        "data": {"float32": [0.1, 0.2, 0.3]},
        "metadata": {"country": "KR", "entity_type": "attraction"},
    }


def test_chunked_splits_batches() -> None:
    assert list(chunked([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]


def test_put_vectors_cli_calls_s3vectors_put_vectors(monkeypatch) -> None:
    calls = []

    class Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, check, capture_output, text):
        calls.append(
            {
                "command": command,
                "check": check,
                "capture_output": capture_output,
                "text": text,
            }
        )
        return Completed()

    monkeypatch.setattr("kr_vector_index.upsert.subprocess.run", fake_run)

    written = put_vectors_cli(
        [
            {
                "key": "attraction#100#0",
                "data": {"float32": [0.1, 0.2]},
                "metadata": {"country": "KR"},
            }
        ],
        vector_bucket="lovv-vector-dev",
        index_name="kr-tour-domain-v1",
        region="us-east-1",
        profile="skn26_final",
    )

    assert written == 1
    assert len(calls) == 1
    command = calls[0]["command"]
    assert command[:4] == ["aws", "s3vectors", "--profile", "skn26_final"]
    assert "put-vectors" in command
    assert command[command.index("--vector-bucket-name") + 1] == "lovv-vector-dev"
    assert command[command.index("--index-name") + 1] == "kr-tour-domain-v1"
    assert command[command.index("--vectors") + 1].startswith("file://")
    assert calls[0]["check"] is False
    assert calls[0]["capture_output"] is True
    assert calls[0]["text"] is True


def test_put_vectors_sdk_calls_s3vectors_client() -> None:
    class FakeS3Vectors:
        def __init__(self) -> None:
            self.calls = []

        def put_vectors(self, **kwargs):
            self.calls.append(kwargs)

    client = FakeS3Vectors()

    written = put_vectors_sdk(
        client,
        [
            {"key": "a", "data": {"float32": [0.1]}, "metadata": {"country": "KR"}},
            {"key": "b", "data": {"float32": [0.2]}, "metadata": {"country": "KR"}},
        ],
        vector_bucket="lovv-vector-dev",
        index_name="kr-tour-domain-v1",
        batch_size=1,
    )

    assert written == 2
    assert client.calls == [
        {
            "vectorBucketName": "lovv-vector-dev",
            "indexName": "kr-tour-domain-v1",
            "vectors": [{"key": "a", "data": {"float32": [0.1]}, "metadata": {"country": "KR"}}],
        },
        {
            "vectorBucketName": "lovv-vector-dev",
            "indexName": "kr-tour-domain-v1",
            "vectors": [{"key": "b", "data": {"float32": [0.2]}, "metadata": {"country": "KR"}}],
        },
    ]
