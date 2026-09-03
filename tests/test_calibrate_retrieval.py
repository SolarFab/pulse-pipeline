"""Calibration: freshness, the sweep, and the config it writes.

No database and no embedding calls — the parts that decide the floor are pure,
and they are the parts a wrong answer would silently corrupt.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("cal", ROOT / "scripts" / "calibrate_retrieval.py")
cal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cal)


JUDGED = [
    {
        "query": "comedy",
        "candidates": [{"id": "a", "relevant": True}, {"id": "b", "relevant": False}],
    }
]


def fixture(tmp_path: Path, age_days: int, cases=None) -> Path:
    p = tmp_path / "fx.json"
    p.write_text(
        json.dumps(
            {
                "id": "test-fx",
                "captured_at": (date.today() - timedelta(days=age_days)).isoformat(),
                "cases": cases if cases is not None else JUDGED,
            }
        )
    )
    return p


def test_a_fresh_fixture_loads(tmp_path):
    assert cal.load_fixture(fixture(tmp_path, 1))["id"] == "test-fx"


def test_the_boundary_is_exactly_the_limit(tmp_path):
    """14 days passes, 15 fails — stated, so it cannot drift into a judgement call."""
    assert cal.load_fixture(fixture(tmp_path, cal.FIXTURE_MAX_AGE_DAYS))
    with pytest.raises(SystemExit):
        cal.load_fixture(fixture(tmp_path, cal.FIXTURE_MAX_AGE_DAYS + 1))


def test_a_stale_fixture_cannot_be_refreshed_by_rewriting_it(tmp_path):
    """Age comes from the recorded capture date, never file mtime."""
    p = fixture(tmp_path, 99)
    p.write_text(p.read_text())  # touch
    with pytest.raises(SystemExit):
        cal.load_fixture(p)


def test_an_empty_fixture_is_refused(tmp_path):
    with pytest.raises(SystemExit):
        cal.load_fixture(fixture(tmp_path, 1, cases=[]))


def test_the_sweep_finds_the_separating_floor():
    # relevant cluster high, irrelevant low: the floor belongs between them
    scored = [(0.9, True), (0.85, True), (0.8, True), (0.3, False), (0.2, False), (0.1, False)]
    floor, j = cal.sweep(scored)
    assert 0.3 < floor <= 0.8
    assert j == pytest.approx(1.0)


def test_the_sweep_does_not_pick_a_floor_that_rejects_everything():
    """Accuracy alone would maximise by rejecting all when most are irrelevant —
    the degenerate floor that stops the ladder ever widening. Youden's J does not."""
    scored = [(0.9, True)] + [(0.1, False)] * 50
    floor, _ = cal.sweep(scored)
    assert floor <= 0.9, "a floor above every relevant score would reject them all"


def test_labels_on_one_side_only_are_refused():
    with pytest.raises(SystemExit):
        cal.sweep([(0.9, True), (0.8, True)])
    with pytest.raises(SystemExit):
        cal.sweep([(0.1, False), (0.2, False)])


def test_the_shipped_fixture_is_valid_and_carries_the_real_failures():
    fx = json.loads((ROOT / "eval" / "fixtures" / "beta-scenarios-v1.json").read_text())
    queries = " ".join(c["query"].lower() for c in fx["cases"])
    for scenario in ["comedy tonight", "prenzlauer berg", "hip hop"]:
        assert scenario in queries
    date.fromisoformat(fx["captured_at"])


def test_dry_run_writes_nothing(capsys):
    cal.write_config(0.5, 3, "m", 1536, {"id": "f", "captured_at": "2026-09-03"}, dry=True)
    assert "dry run" in capsys.readouterr().out


def test_a_dry_run_needs_no_credentials(monkeypatch, capsys):
    """The reason CI caught this: write_config read SUPABASE_URL before checking
    the dry flag, so a dry run demanded credentials it never used. A command that
    cannot run without production access cannot run where production must not."""
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    cal.write_config(0.5, 3, "m", 1536, {"id": "f", "captured_at": "2026-09-03"}, dry=True)
    assert "dry run" in capsys.readouterr().out


def test_config_write_uses_the_atomic_rpc(monkeypatch):
    calls = []

    class Response:
        def raise_for_status(self):
            return None

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-key")
    monkeypatch.setattr(cal.httpx, "post", post)
    monkeypatch.setattr(
        cal.httpx,
        "patch",
        lambda *args, **kwargs: pytest.fail("config swap must not use a separate PATCH"),
    )

    cal.write_config(0.5, 3, "model", 1536, {"id": "f", "captured_at": "2026-09-03"}, False)

    assert len(calls) == 1
    url, request = calls[0]
    assert url.endswith("/rest/v1/rpc/set_active_retrieval_config")
    assert request["json"] == {
        "p_floor": 0.5,
        "p_k": 3,
        "p_embedding_model": "model",
        "p_embedding_dim": 1536,
        "p_fixture_id": "f",
        "p_fixture_captured_at": "2026-09-03",
    }


def test_an_unjudged_fixture_is_refused_with_the_next_step(tmp_path):
    """The review's finding: the shipped fixture had no labels, so sweep() could
    never separate anything. Refusing loudly beats calibrating against nothing."""
    p = tmp_path / "fx.json"
    p.write_text(
        json.dumps(
            {
                "id": "unjudged",
                "captured_at": date.today().isoformat(),
                "cases": [{"query": "comedy", "candidates": [{"id": "a", "relevant": None}]}],
            }
        )
    )
    with pytest.raises(SystemExit) as e:
        cal.load_fixture(p)
    assert "capture_fixture" in str(e.value)


def test_a_judged_fixture_loads(tmp_path):
    p = tmp_path / "fx.json"
    p.write_text(
        json.dumps(
            {
                "id": "judged",
                "captured_at": date.today().isoformat(),
                "cases": [
                    {
                        "query": "comedy",
                        "candidates": [
                            {"id": "a", "relevant": True},
                            {"id": "b", "relevant": False},
                        ],
                    }
                ],
            }
        )
    )
    assert cal.load_fixture(p)["id"] == "judged"
