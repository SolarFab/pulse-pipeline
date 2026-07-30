# Experiment protocol (pinned configuration)

Methodology: every experiment varies **exactly one variable**; everything below stays pinned.
Golden set is **frozen** per version — changing it bumps the version (`eval/golden_set/v2.jsonl`),
never edits v1. Results are written to `eval/results/` as JSON; tables in the showcase are
generated from those files, never typed by hand.

## Pinned configuration

| Variable | Pinned value |
|---|---|
| Golden set | `eval/golden_set/v1.jsonl` (25 items: 16 embedding/retrieval, 13 chat, overlapping) |
| Event sample | 300 active events with category labels, ordered by start_time (deterministic) |
| K | 5 (precision@K, top-K retrievals) |
| Embedding gateway | OpenRouter (`/v1/embeddings`), native model dimensions |
| Embed text | `build_embed_text()` v1: title + description[:1500] + category/subcategory + sorted tags[:15] |
| Chat judge model | must differ from the answering model (self-preference bias) |
| Chat temperature | 0 for eval runs |

## Experiments

| # | Variable under test | Status |
|---|---|---|
| 1 | Embedding model (text-embedding-3-small vs gemini-embedding-001 vs qwen3-embedding-8b) | ready, blocked on OPENROUTER_API_KEY |
| 1b | Embed-text composition ablation (title / +description / +category / +tags; truncation length) | planned |
| 2 | Retrieval mode on golden queries (filter-only vs semantic vs hybrid) | planned (needs pgvector live) |
| 3 | Prompt technique × chat model grid (zero-shot / few-shot / +reasoning / policy variants) | planned (promptfoo; needs tool-calling chat) |

## Why one-variable-at-a-time

Stacked changes can't be attributed; see the riester-kompass Experiment 2 finding that combined
retrieval tricks performed worse than either alone. Also: classical metrics and judge metrics can
disagree (HyDE effect) — both are always reported, decisions name which metric they optimized.
