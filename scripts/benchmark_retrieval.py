#!/usr/bin/env python3
"""Experiment 2 — retrieval technique ladder (docs/EXPERIMENT.md).

Configs, one variable at a time, all on the frozen corpus v1 + qrels_v1:
    baseline   vector-only (Experiment-1 winner)
    bm25       lexical only (BM25, german+english tokens) — diagnostic rung
    hybrid     BM25 + vector fused with Reciprocal Rank Fusion
    mq         Multi-Query: LLM expands to 3 variants, RRF over vector runs
    hyde       HyDE: LLM writes a hypothetical event, embed that instead

Reports Recall@5 / P@5 / MRR / nDCG@5 AND per-query latency + LLM tokens (chat
hot path budget). Unlabeled results are counted irrelevant (pool bias) — the
script emits the delta pool for incremental labeling.

Outputs: eval/results/retrieval-<ts>.json, docs/retrieval-benchmark.md,
         docs/showcase/labeling-sheet-delta.html (only new candidates)
"""

from __future__ import annotations

import argparse
import html
import json
import math
import re
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv()

import os  # noqa: E402

from pipeline.embedder import build_embed_text, get_embedder  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "eval" / "corpus" / "v1.jsonl"
GOLDEN = ROOT / "eval" / "golden_set" / "v1.jsonl"
QRELS = ROOT / "eval" / "golden_set" / "qrels_v1.jsonl"
POOL_V1 = ROOT / "eval" / "results" / "pool_v1.json"
CACHE = ROOT / "eval" / "cache" / "corpus_vecs_v1.json"

K = 5
RRF_K = 60
CHAT_MODEL = "openai/gpt-4o-mini"   # for MQ/HyDE expansions; cheap, temp 0


# ── generic helpers ───────────────────────────────────────────────────────────

def jsonl(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text().split("\n") if ln.strip()]


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def ndcg_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    dcg = sum(1 / math.log2(i + 2) for i, e in enumerate(ranked[:k]) if e in relevant)
    ideal = sum(1 / math.log2(i + 2) for i in range(min(k, len(relevant))))
    return dcg / ideal if ideal else 0.0


def rrf(rank_lists: list[list[str]]) -> list[str]:
    scores: dict[str, float] = {}
    for ranks in rank_lists:
        for i, eid in enumerate(ranks):
            scores[eid] = scores.get(eid, 0.0) + 1 / (RRF_K + i + 1)
    return [e for e, _ in sorted(scores.items(), key=lambda s: -s[1])]


# ── BM25 (plain, ~30 lines — german+english lowercase word tokens) ────────────

def tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


class BM25:
    def __init__(self, docs: list[list[str]], k1=1.5, b=0.75):
        self.k1, self.b = k1, b
        self.docs = docs
        self.N = len(docs)
        self.avgdl = sum(len(d) for d in docs) / max(1, self.N)
        self.df: dict[str, int] = {}
        for d in docs:
            for t in set(d):
                self.df[t] = self.df.get(t, 0) + 1

    def score(self, query: list[str], idx: int) -> float:
        d = self.docs[idx]
        dl = len(d)
        tf: dict[str, int] = {}
        for t in d:
            tf[t] = tf.get(t, 0) + 1
        s = 0.0
        for t in query:
            if t not in self.df:
                continue
            idf = math.log(1 + (self.N - self.df[t] + 0.5) / (self.df[t] + 0.5))
            f = tf.get(t, 0)
            s += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
        return s

    def rank(self, query_text: str, ids: list[str]) -> list[str]:
        q = tokenize(query_text)
        order = sorted(range(self.N), key=lambda i: -self.score(q, i))
        return [ids[i] for i in order]


# ── LLM expansions (OpenRouter chat, temp 0) ─────────────────────────────────

def chat(prompt: str) -> tuple[str, int]:
    resp = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
        json={"model": CHAT_MODEL, "temperature": 0,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=60,
    )
    resp.raise_for_status()
    body = resp.json()
    return (body["choices"][0]["message"]["content"],
            (body.get("usage") or {}).get("total_tokens", 0))


def multi_query(q: str) -> tuple[list[str], int]:
    text, tok = chat(
        "Generate 3 alternative short search queries (mix German and English) for finding "
        f"Berlin events matching: '{q}'. One per line, no numbering, no explanations."
    )
    variants = [ln.strip() for ln in text.split("\n") if ln.strip()][:3]
    return [q, *variants], tok


def hyde(q: str) -> tuple[str, int]:
    text, tok = chat(
        "Write a short fictional Berlin event listing (title + 2-3 sentence description, "
        f"German or English as fits) that would perfectly answer the search: '{q}'. "
        "No preamble."
    )
    return text, tok


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", default="baseline,bm25,hybrid,mq,hyde")
    args = ap.parse_args()
    configs = args.configs.split(",")

    events = jsonl(CORPUS)
    ids = [e["id"] for e in events]
    texts = [build_embed_text(e) for e in events]
    queries = [g for g in jsonl(GOLDEN) if "retrieval" in g["applies_to"]]
    rels: dict[str, set[str]] = {}
    delta_file = QRELS.with_name("qrels_v1_delta.jsonl")
    qrel_files = [QRELS] + ([delta_file] if delta_file.exists() else [])
    for f in qrel_files:
        for r in jsonl(f):
            rels.setdefault(r["query_id"], set()).add(r["event_id"])
    labeled_pool = {eid for q in json.load(POOL_V1.open())["rankings"].values()
                    for ranks in q.values() for eid in ranks}
    if delta_file.exists():
        # everything shown on the delta sheet has now been judged (ticked or not)
        prev = json.loads((ROOT / "eval" / "results" / "delta_pool_v1.json").read_text()) \
            if (ROOT / "eval" / "results" / "delta_pool_v1.json").exists() else None
        if prev:
            labeled_pool |= {e for v in prev.values() for e in v}
        print(f"qrels: v1 + delta ({len(jsonl(delta_file))} extra relevant)")

    emb = get_embedder()  # openrouter / text-embedding-3-small (Experiment-1 winner)
    if CACHE.exists():
        vecs = json.loads(CACHE.read_text())
        print(f"corpus vectors from cache ({len(vecs)})")
    else:
        vecs = emb.embed_batch(texts)
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(vecs))
        print(f"embedded corpus ({len(vecs)}) and cached")
    bm25 = BM25([tokenize(t) for t in texts])

    def vec_rank(qvec) -> list[str]:
        order = sorted(range(len(ids)), key=lambda j: -cosine(qvec, vecs[j]))
        return [ids[j] for j in order]

    results: dict[str, dict] = {}
    delta: dict[str, list[str]] = {}
    for config in configs:
        per_q, lat_ms, llm_tok = [], [], 0
        for g in queries:
            qid, qtext = g["id"], g["query"]
            t0 = time.time()
            if config == "baseline":
                ranked = vec_rank(emb.embed_batch([qtext])[0])
            elif config == "bm25":
                ranked = bm25.rank(qtext, ids)
            elif config == "hybrid":
                ranked = rrf([vec_rank(emb.embed_batch([qtext])[0]), bm25.rank(qtext, ids)])
            elif config == "mq":
                variants, tok = multi_query(qtext)
                llm_tok += tok
                ranked = rrf([vec_rank(v) for v in
                              (emb.embed_batch(variants))])
            elif config == "hyde":
                doc, tok = hyde(qtext)
                llm_tok += tok
                ranked = vec_rank(emb.embed_batch([doc])[0])
            else:
                raise SystemExit(f"unknown config {config}")
            lat_ms.append((time.time() - t0) * 1000)

            relevant = rels.get(qid, set())
            top = ranked[:K]
            hits = [e for e in top if e in relevant]
            rr = next((1 / (i + 1) for i, e in enumerate(ranked) if e in relevant), 0.0)
            per_q.append({
                "query_id": qid,
                "recall": len(hits) / len(relevant) if relevant else None,
                "precision": len(hits) / K,
                "rr": rr,
                "ndcg": ndcg_at_k(ranked, relevant, K),
                "unlabeled_in_top": [e for e in top if e not in labeled_pool],
            })
            for e in top:
                if e not in labeled_pool:
                    delta.setdefault(qid, []).append(e)

        scored = [q for q in per_q if q["recall"] is not None]
        n = len(scored)
        results[config] = {
            "queries_scored": n,
            f"recall@{K}": round(sum(q["recall"] for q in scored) / n, 3),
            f"precision@{K}": round(sum(q["precision"] for q in scored) / n, 3),
            "mrr": round(sum(q["rr"] for q in scored) / n, 3),
            f"ndcg@{K}": round(sum(q["ndcg"] for q in scored) / n, 3),
            "mean_latency_ms": round(sum(lat_ms) / len(lat_ms)),
            "llm_tokens_total": llm_tok,
            "unlabeled_in_top5": sum(len(q["unlabeled_in_top"]) for q in per_q),
            "per_query": per_q,
        }
        r = results[config]
        print(f"{config:9} R@5={r[f'recall@{K}']} P@5={r[f'precision@{K}']} MRR={r['mrr']} "
              f"nDCG={r[f'ndcg@{K}']}  {r['mean_latency_ms']}ms/q  "
              f"unlabeled@5={r['unlabeled_in_top5']}  llm_tok={llm_tok}")

    stamp = time.strftime("%Y%m%d-%H%M%S")
    (ROOT / "eval" / "results" / f"retrieval-{stamp}.json").write_text(json.dumps({
        "experiment": "2-retrieval-ladder", "corpus": "v1", "golden_set": "v1",
        "qrels": "v1", "k": K, "embed_model": emb.model, "chat_model": CHAT_MODEL,
        "configs": results,
    }, indent=2))

    md = ["# Retrieval benchmark — Experiment 2 (frozen corpus v1, qrels v1)", "",
          "Latency = per-query wall time incl. any LLM expansion (chat hot path budget ~2s). "
          "`unlabeled@5` = top-5 results outside the labeled pool, scored irrelevant until the "
          "delta labeling round (pool bias, reported honestly).", "",
          f"| config | recall@{K} | precision@{K} | MRR | nDCG@{K} | ms/query | LLM tokens | unlabeled@5 |",
          "|---|---|---|---|---|---|---|---|"]
    for c, r in results.items():
        md.append(f"| {c} | {r[f'recall@{K}']} | {r[f'precision@{K}']} | {r['mrr']} | "
                  f"{r[f'ndcg@{K}']} | {r['mean_latency_ms']} | {r['llm_tokens_total']} | "
                  f"{r['unlabeled_in_top5']} |")
    (ROOT / "docs" / "retrieval-benchmark.md").write_text("\n".join(md) + "\n")

    # delta labeling sheet: only candidates the user has never judged
    if delta:
        (ROOT / "eval" / "results" / "delta_pool_v1.json").write_text(
            json.dumps({k: sorted(set(v)) for k, v in delta.items()}, indent=2))
        by_id = {e["id"]: e for e in events}
        qmap = {g["id"]: g for g in queries}
        sections = []
        for qid, eids in delta.items():
            uniq = list(dict.fromkeys(eids))
            cards = ""
            for eid in uniq:
                e = by_id[eid]
                desc = html.escape((e.get("description") or "")[:220])
                cards += (f'<label class="card"><input type="checkbox" data-q="{qid}" data-e="{eid}">'
                          f'<div><b>{html.escape(e["title"])}</b>'
                          f'<span class="meta">{html.escape(e.get("category") or "")}/'
                          f'{html.escape(e.get("subcategory") or "")} · '
                          f'{html.escape(e.get("venue_name") or "")} · '
                          f'{html.escape((e.get("start_time") or "")[:16])}</span>'
                          f"<p>{desc}…</p></div></label>")
            sections.append(f"<section><h2>{qid} <em>{html.escape(qmap[qid]['query'])}</em></h2>"
                            f"<p class='hint'>NEW candidates from Experiment-2 configs "
                            f"({len(uniq)}) — tick the relevant ones.</p>{cards}</section>")
        sheet = (ROOT / "docs" / "showcase" / "labeling-sheet.html").read_text()
        head = sheet.split("<h1>")[0]  # reuse styles + export bar
        (ROOT / "docs" / "showcase" / "labeling-sheet-delta.html").write_text(
            head + "<h1>Delta labeling — Experiment 2 candidates</h1>"
            "<p>Only events NOT in the first labeling round. Export appends as "
            "<code>qrels_v1_delta.jsonl</code> — save to eval/golden_set/ and re-run "
            "benchmark_retrieval after merging.</p>"
            + "".join(sections)
            + sheet[sheet.rfind("<script>"):].replace("qrels_v1.jsonl", "qrels_v1_delta.jsonl")
        )
        n_delta = sum(len(set(v)) for v in delta.values())
        print(f"\ndelta pool: {n_delta} new candidates -> docs/showcase/labeling-sheet-delta.html")
    print("wrote docs/retrieval-benchmark.md")


if __name__ == "__main__":
    main()
