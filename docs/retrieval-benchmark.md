# Retrieval benchmark — Experiment 2 (frozen corpus v1, qrels v1)

Latency = per-query wall time incl. any LLM expansion (chat hot path budget ~2s). `unlabeled@5` = top-5 results outside the labeled pool, scored irrelevant until the delta labeling round (pool bias, reported honestly).

| config | recall@5 | precision@5 | MRR | nDCG@5 | ms/query | LLM tokens | unlabeled@5 |
|---|---|---|---|---|---|---|---|
| baseline | 0.65 | 0.477 | 0.78 | 0.662 | 645 | 0 | 0 |
| bm25 | 0.374 | 0.246 | 0.488 | 0.336 | 1 | 0 | 0 |
| hybrid | 0.463 | 0.338 | 0.703 | 0.505 | 662 | 0 | 0 |
| mq | 0.54 | 0.354 | 0.628 | 0.5 | 2287 | 1042 | 0 |
| hyde | 0.448 | 0.338 | 0.529 | 0.416 | 2636 | 1996 | 2 |
