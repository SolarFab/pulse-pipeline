# Retrieval benchmark — Experiment 2 (frozen corpus v1, qrels v1)

Latency = per-query wall time incl. any LLM expansion (chat hot path budget ~2s). `unlabeled@5` = top-5 results outside the labeled pool, scored irrelevant until the delta labeling round (pool bias, reported honestly).

| config | recall@5 | precision@5 | MRR | nDCG@5 | ms/query | LLM tokens | unlabeled@5 |
|---|---|---|---|---|---|---|---|
| baseline | 0.65 | 0.477 | 0.78 | 0.662 | 563 | 0 | 0 |
| bm25 | 0.374 | 0.246 | 0.488 | 0.336 | 2 | 0 | 0 |
| hybrid | 0.437 | 0.323 | 0.703 | 0.491 | 576 | 0 | 0 |
| mq | 0.551 | 0.369 | 0.615 | 0.506 | 2080 | 1044 | 0 |
| hyde | 0.405 | 0.323 | 0.596 | 0.42 | 2578 | 1997 | 1 |
