#!/usr/bin/env python3
"""Re-review sheet for the temporal queries (labeling-guideline fix -> qrels v2).

Guideline change: retrieval relevance = semantic/type match ONLY. Dates are hard SQL
filters in production and judged at the chat layer — a Saturday flea market IS relevant
to "Flohmarkt am Sonntag" at this layer.

Shows every pooled candidate for the affected queries with the CURRENT label pre-ticked;
the user flips date-only rejections. Export saves qrels_v2_temporal.jsonl.
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
TEMPORAL_QIDS = ["q01", "q02", "q03", "q23", "q25"]


def jsonl(p: Path) -> list[dict]:
    return [json.loads(ln) for ln in p.read_text().split("\n") if ln.strip()]


def main() -> None:
    events = {e["id"]: e for e in jsonl(ROOT / "eval" / "corpus" / "v1.jsonl")}
    queries = {g["id"]: g for g in jsonl(ROOT / "eval" / "golden_set" / "v1.jsonl")}
    pool_v1 = json.loads((ROOT / "eval" / "results" / "pool_v1.json").read_text())["rankings"]
    delta = json.loads((ROOT / "eval" / "results" / "delta_pool_v1.json").read_text())
    rels: dict[str, set[str]] = {}
    for f in ["qrels_v1.jsonl", "qrels_v1_delta.jsonl"]:
        p = ROOT / "eval" / "golden_set" / f
        if p.exists():
            for r in jsonl(p):
                rels.setdefault(r["query_id"], set()).add(r["event_id"])

    sections = []
    n_cards = 0
    for qid in TEMPORAL_QIDS:
        pooled = list(dict.fromkeys(
            [e for ranks in pool_v1.get(qid, {}).values() for e in ranks]
            + delta.get(qid, [])))
        cards = ""
        for eid in pooled:
            e = events.get(eid)
            if not e:
                continue
            n_cards += 1
            checked = " checked" if eid in rels.get(qid, set()) else ""
            desc = html.escape((e.get("description") or "")[:200])
            cards += (f'<label class="card"><input type="checkbox" data-q="{qid}" '
                      f'data-e="{eid}"{checked}><div><b>{html.escape(e["title"][:70])}</b>'
                      f'<span class="meta">{html.escape(e.get("category") or "")}/'
                      f'{html.escape(e.get("subcategory") or "")} · '
                      f'{html.escape(e.get("venue_name") or "")} · '
                      f'{html.escape((e.get("start_time") or "")[:16])}</span>'
                      f"<p>{desc}…</p></div></label>")
        sections.append(
            f"<section><h2>{qid} <em>{html.escape(queries[qid]['query'])}</em></h2>"
            f"<p class='hint'>IGNORIERE DAS DATUM. Frage nur: passt die ART des Events zur "
            f"Suche? (Flohmarkt = Flohmarkt, egal ob Samstag oder Sonntag.) "
            f"Deine bisherigen Haken sind vorausgefüllt — korrigiere nur, wo du wegen des "
            f"Datums abgelehnt hattest.</p>{cards}</section>")

    base = (ROOT / "docs" / "showcase" / "labeling-sheet.html").read_text()
    head = base.split("<h1>")[0]
    out = ROOT / "docs" / "showcase" / "labeling-sheet-temporal-fix.html"
    out.write_text(
        head + "<h1>Re-Review: Zeit-Queries (Guideline-Fix → qrels v2)</h1>"
        "<p>Nur die 5 Queries mit Zeitbezug. Regel: <b>Datum ignorieren</b> — nur Event-Art "
        "zählt. Export als <code>qrels_v2_temporal.jsonl</code> nach "
        "<code>eval/golden_set/</code> speichern.</p>"
        + "".join(sections)
        + base[base.rfind("<script>"):].replace("qrels_v1.jsonl", "qrels_v2_temporal.jsonl")
    )
    print(f"wrote {out} ({len(TEMPORAL_QIDS)} queries, {n_cards} candidates, "
          f"pre-ticked from current qrels)")


if __name__ == "__main__":
    main()
