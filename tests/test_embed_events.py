"""attach_embeddings unit tests — no network: a fake embedder stands in for the API."""

from pipeline.embed_events import attach_embeddings
from pipeline.embedder import build_embed_text, embed_text_hash


class FakeEmbedder:
    model = "openai/text-embedding-3-small"
    total_tokens = 42
    total_seconds = 0.1

    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def embed_batch(self, texts):
        if self.fail:
            raise RuntimeError("api down")
        self.calls.append(texts)
        return [[0.1, 0.2] for _ in texts]


EVENT = {"title": "Jazz Night", "description": "Bebop trio.", "category": "music",
         "fingerprint": "fp1"}


def test_new_event_gets_embedded():
    e = dict(EVENT)
    m = attach_embeddings([e], db_hashes={}, embedder=FakeEmbedder())
    assert m["embedded"] == 1 and m["skipped"] == 0
    assert e["embedding"] == "[0.1, 0.2]"
    assert e["embed_model"] == "openai/text-embedding-3-small"
    assert e["embed_hash"] == embed_text_hash(build_embed_text(e))
    assert m["tokens"] == 42 and m["usd"] > 0


def test_unchanged_event_is_skipped_no_api_call():
    e = dict(EVENT)
    stored = embed_text_hash(build_embed_text(e))
    fake = FakeEmbedder()
    m = attach_embeddings([e], db_hashes={"fp1": stored}, embedder=fake)
    assert m["skipped"] == 1 and m["embedded"] == 0
    assert fake.calls == []          # hash-skip means zero API traffic
    assert "embedding" not in e      # nothing overwritten


def test_changed_text_reembeds():
    e = {**EVENT, "description": "NEW lineup announced!"}
    stored = embed_text_hash(build_embed_text(EVENT))  # hash of the OLD text
    m = attach_embeddings([e], db_hashes={"fp1": stored}, embedder=FakeEmbedder())
    assert m["embedded"] == 1


def test_api_failure_degrades_not_blocks():
    e = dict(EVENT)
    m = attach_embeddings([e], db_hashes={}, embedder=FakeEmbedder(fail=True))
    assert m["failed"] == 1 and m["embedded"] == 0
    assert "embedding" not in e      # event still upserts, just without a vector
