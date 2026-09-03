# Design — staged retrieval

## The relaxation ladder

Deterministic, one step at a time, most-specific constraint first. Each rung records why it fired.

| rung | relax | keep |
|---|---|---|
| 0 | nothing — all constraints applied | — |
| 1 | venue | neighbourhood, radius, semantics, hard set |
| 2 | neighbourhood → radius from its centroid | semantics, hard set |
| 3 | radius → city-wide | semantics, hard set |
| 4 | stop | — |

The always-hard set is never a rung. If nothing clears the threshold city-wide, the honest answer
is that there is nothing, which is a *correct* answer and must be presented as one.

## Why a threshold rather than `rows > 0`

`rows > 0` is what produced the 3 September failure: three weakly-matching rows suppressed
relaxation while stronger events sat one rung away. The test is instead **k results at or above a
similarity floor**, with `k` and the floor calibrated from the golden set rather than guessed.

Cosine similarity is not comparable across embedding models or corpora, so the floor cannot be a
literal constant chosen by hand. Calibrate it with `scripts/eval_retrieval_gate.py`: sweep the floor
over the labelled queries, choose the value that maximises the separation between labelled-relevant
and labelled-irrelevant results, and record it alongside the model id. Changing the embedding model
invalidates the floor, so the gate asserts it.

## Ordering, not post-filtering

Constraints belong **inside** the SQL that pgvector ranks, not applied to a global top-N afterwards.
`match_events` already takes filters as parameters — the fix is that the caller must stop asking for
a global top-10 and then narrowing. A strong local match must never be discarded before the location
constraint is considered.

## What the model is told

Each result set carries metadata: which rung fired, what was relaxed, and how many candidates the
unrelaxed query returned. Without this the model cannot distinguish "nothing in Prenzlauer Berg"
from "I widened the search", and will present city-wide results as if they were local — which is a
worse failure than the empty answer, because it is invisible.

## Tracing

Every attempt is traced, not just the last. The 2 September trace recorded row counts and nothing
else — no arguments, no scores, no reason — which is why this bug had to be diagnosed from the
database instead of from the traces that exist to diagnose it. Each attempt records: arguments as
sent, rung, result ids, scores, and the relaxation reason.
