# Prompt benchmark — Experiment 3, stage 1 (tool-call accuracy)

First model action asserted deterministically per golden chat query: right tool, right args, dates resolved — or correctly NO tool (chitchat/ambiguous). No execution, no judge (that's stage 2).

| variant × model | score | mean ms/turn | tokens |
|---|---|---|---|
| zero-shot × claude-haiku-4.5 | 11/13 (85%) | 2188 | 13557 |
| zero-shot × gpt-4o-mini | 9/13 (69%) | 1779 | 3904 |
| prod-v1 × claude-haiku-4.5 | 10/13 (77%) | 2300 | 18558 |
| prod-v1 × gpt-4o-mini | 9/13 (69%) | 1770 | 8235 |
| few-shot × claude-haiku-4.5 | 13/13 (100%) | 2067 | 21626 |
| few-shot × gpt-4o-mini | 12/13 (92%) | 1686 | 11099 |
| clarify-first × claude-haiku-4.5 | 5/13 (38%) | 2569 | 16843 |
| clarify-first × gpt-4o-mini | 4/13 (31%) | 1555 | 6729 |

## Failures

**zero-shot × claude-haiku-4.5**: q14 (geo params, Neukölln or Schillerkiez query); q23 (date_from = tomorrow evening, live-music intent in query/subcategory)
**zero-shot × gpt-4o-mini**: q07 (semantic query set (vibe needs ranking)); q14 (geo params, Neukölln or Schillerkiez query); q18 (no tool before clarifying, asked a clarifying question); q23 (live-music intent in query/subcategory)
**prod-v1 × claude-haiku-4.5**: q14 (geo params, Neukölln or Schillerkiez query); q16 (date window covers Sunday); q23 (date_from = tomorrow evening)
**prod-v1 × gpt-4o-mini**: q07 (semantic query set (vibe needs ranking)); q14 (geo params, Neukölln or Schillerkiez query); q18 (no tool before clarifying, asked a clarifying question); q23 (live-music intent in query/subcategory)
**few-shot × gpt-4o-mini**: q18 (no tool before clarifying, asked a clarifying question)
**clarify-first × claude-haiku-4.5**: q07 (called search_events); q11 (called search_events); q14 (called search_events); q16 (called search_events); q17 (call failed: ReadTimeout); q23 (called search_events); q24 (called search_events); q25 (called search_events)
**clarify-first × gpt-4o-mini**: q07 (called search_events); q11 (called search_events); q14 (geo params, Neukölln or Schillerkiez query); q17 (searched first (answer-first policy)); q21 (called search_events); q22 (call failed: ReadTimeout); q23 (call failed: ConnectError); q24 (called search_events); q25 (called search_events)
