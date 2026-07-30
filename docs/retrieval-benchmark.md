# Retrieval benchmark — Experiment 2 (frozen corpus v1, qrels v1)

Latency = per-query wall time incl. any LLM expansion (chat hot path budget ~2s). `unlabeled@5` = top-5 results outside the labeled pool, scored irrelevant until the delta labeling round (pool bias, reported honestly).

| config | recall@5 | precision@5 | MRR | nDCG@5 | ms/query | LLM tokens | unlabeled@5 |
|---|---|---|---|---|---|---|---|
| baseline | 0.776 | 0.477 | 0.78 | 0.716 | 610 | 0 | 0 |
| bm25 | 0.288 | 0.138 | 0.377 | 0.239 | 2 | 0 | 25 |
| hybrid | 0.506 | 0.323 | 0.7 | 0.501 | 609 | 0 | 6 |
| mq | 0.436 | 0.262 | 0.589 | 0.422 | 2439 | 1032 | 9 |
| hyde | 0.417 | 0.246 | 0.475 | 0.36 | 3096 | 2026 | 14 |
