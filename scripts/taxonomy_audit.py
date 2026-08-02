#!/usr/bin/env python3
"""unify-taxonomy §5: first run of the embedding-based miscategorization audit.

For a sample of embedded upcoming events, compare each event's category with the
majority category of its 10 nearest embedding-neighbors (audit_categories RPC).
Events whose neighbors disagree at >=70% land on a review list — read-only, never
auto-refiled. Writes eval/results/taxonomy-audit-<ts>.json + docs/taxonomy-audit.md.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv()

from db.supabase import get_client  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BATCH = 8
SAMPLE = 1500
THRESHOLD = 0.7


def main() -> None:
    client = get_client()
    rows = (client.table("events").select("id,title,category")
            .eq("is_active", True).gte("start_time", "now()")
            .not_.is_("embedding", "null")
            .order("start_time").limit(SAMPLE).execute().data) or []
    print(f"auditing {len(rows)} embedded upcoming events (k=10, flag >= {THRESHOLD:.0%} disagree)")
    titles = {r["id"]: r["title"] for r in rows}

    flagged, checked = [], 0
    for i in range(0, len(rows), BATCH):
        ids = [r["id"] for r in rows[i : i + BATCH]]
        res = client.rpc("audit_categories", {"p_ids": ids}).execute().data or []
        checked += len(res)
        for r in res:
            if r["suggested"] != r["category"] and r["agree_frac"] >= THRESHOLD:
                flagged.append({**r, "title": titles.get(r["id"], "")[:70]})
        if (i // BATCH) % 10 == 0:
            print(f"  {checked} checked, {len(flagged)} flagged", flush=True)

    rate = len(flagged) / checked if checked else 0.0
    pairs: dict[str, int] = {}
    for f in flagged:
        key = f"{f['category']} -> {f['suggested']}"
        pairs[key] = pairs.get(key, 0) + 1

    stamp = time.strftime("%Y%m%d-%H%M%S")
    (ROOT / "eval" / "results" / f"taxonomy-audit-{stamp}.json").write_text(json.dumps({
        "checked": checked, "flagged": len(flagged), "rate": round(rate, 4),
        "threshold": THRESHOLD, "pairs": pairs, "flagged_events": flagged}, indent=2))

    md = ["# Taxonomy audit — embedding-neighbor disagreement", "",
          f"Sample: {checked} embedded upcoming events · k=10 neighbors · flag when >= "
          f"{THRESHOLD:.0%} of neighbors carry a different category.", "",
          f"**Measured miscategorization-candidate rate: {rate:.1%} ({len(flagged)} events)**", "",
          "| miscategorization pattern | count |", "|---|---|"]
    for k, v in sorted(pairs.items(), key=lambda kv: -kv[1])[:15]:
        md.append(f"| {k} | {v} |")
    md += ["", "Review list (top 25):", ""]
    for f in sorted(flagged, key=lambda f: -f["agree_frac"])[:25]:
        md.append(f"- {f['agree_frac']:.0%} neighbors say **{f['suggested']}** "
                  f"(filed {f['category']}): {f['title']}")
    (ROOT / "docs" / "taxonomy-audit.md").write_text("\n".join(md) + "\n")
    print(f"\nrate {rate:.1%} · wrote docs/taxonomy-audit.md")


if __name__ == "__main__":
    main()
