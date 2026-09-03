#!/usr/bin/env python3
"""Capture a labellable retrieval fixture (FEAT-24 review finding 1).

The shipped fixture has empty `relevant_ids`, so the calibrator has nothing to
separate and exits. Labels cannot be invented — a floor calibrated against a
guess is worse than no floor, because it looks calibrated. They have to be
captured against the applied migration and then judged.

This is that step. It runs each query through match_events_v2, writes the
candidates with `relevant: null`, and a human turns each null into true or false.
Recapture rather than edit when the fixture goes stale: the capture date is what
the freshness check reads.

    uv run python scripts/capture_fixture.py --fixture eval/fixtures/beta-scenarios-v1.json
    # then label, then:
    uv run python scripts/calibrate_retrieval.py --fixture eval/fixtures/beta-scenarios-v1.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv()

import importlib.util  # noqa: E402

from pipeline.embedder import get_embedder  # noqa: E402

_spec = importlib.util.spec_from_file_location("cal", ROOT / "scripts" / "calibrate_retrieval.py")
_cal = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cal)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fixture", required=True, type=Path)
    ap.add_argument("--per-query", type=int, default=12)
    args = ap.parse_args()

    fx = json.loads(args.fixture.read_text())
    embedder = get_embedder()
    labelled = 0

    for case in fx["cases"]:
        vec = embedder.embed_batch([case["query"]])[0]
        rows = _cal.search(vec, case, limit=args.per_query)
        # Keep any judgements already made; only new ids arrive unlabelled.
        prior = {c["id"]: c.get("relevant") for c in case.get("candidates", [])}
        case["candidates"] = [
            {
                "id": r["id"],
                "title": r.get("title"),
                "venue": r.get("venue_name"),
                "similarity": r.get("similarity"),
                "relevant": prior.get(r["id"]),
            }
            for r in rows
        ]
        labelled += sum(1 for c in case["candidates"] if c["relevant"] is None)
        print(f"  {case['query'][:44]:<44} {len(rows):>3} candidates")

    fx["captured_at"] = date.today().isoformat()
    args.fixture.write_text(json.dumps(fx, indent=2, ensure_ascii=False) + "\n")
    print(
        f"\ncaptured {args.fixture} on {fx['captured_at']} — {labelled} candidates need a judgement"
    )
    print("set each `relevant` to true or false, then run calibrate_retrieval.py")


if __name__ == "__main__":
    main()
