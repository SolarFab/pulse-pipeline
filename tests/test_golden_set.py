"""Golden set v1 is frozen — these tests guard its integrity, not its content."""

import json
from pathlib import Path

GOLDEN = Path(__file__).resolve().parent.parent / "eval" / "golden_set" / "v1.jsonl"
VALID_TARGETS = {"embedding", "retrieval", "chat"}


def load():
    return [json.loads(ln) for ln in GOLDEN.read_text().splitlines() if ln.strip()]


def test_golden_set_is_valid_jsonl_with_required_fields():
    items = load()
    assert len(items) >= 20
    for it in items:
        assert it["id"] and it["category"] and it["query"] and it["expect"]
        assert set(it["applies_to"]) <= VALID_TARGETS and it["applies_to"]


def test_ids_unique_and_stable_format():
    ids = [it["id"] for it in load()]
    assert len(ids) == len(set(ids))
    assert all(i.startswith("q") for i in ids)


def test_coverage_of_critical_categories():
    cats = {it["category"] for it in load()}
    for required in ("cross_lingual", "vibe_no_keyword", "injection_probe",
                     "empty_honesty", "broad_policy", "profile_override"):
        assert required in cats, f"golden set lost its {required} probe"


def test_embedding_subset_size():
    items = [it for it in load() if "embedding" in it["applies_to"]]
    assert len(items) == 16  # frozen; growing it means a new golden set version
