# Prompt benchmark — Experiment 3, stage 1 (tool-call accuracy)

First model action asserted deterministically per golden chat query: right tool, right args, dates resolved — or correctly NO tool (chitchat/ambiguous). No execution, no judge (that's stage 2). Cost = measured USD per turn (OpenRouter usage accounting).

| variant × model | score | ms/turn | $/turn |
|---|---|---|---|
| zero-shot × claude-haiku-4.5 | 10/13 (77%) | 2285 | 0.00169 |
| zero-shot × gpt-4o-mini | 9/13 (69%) | 1315 | 0.00006 |
| zero-shot × gemini-2.5-flash | 7/13 (54%) | 957 | 0.00016 |
| prod-v1 × claude-haiku-4.5 | 10/13 (77%) | 2234 | 0.00205 |
| prod-v1 × gpt-4o-mini | 8/13 (62%) | 1397 | 0.00012 |
| prod-v1 × gemini-2.5-flash | 11/13 (85%) | 866 | 0.00026 |
| few-shot × claude-haiku-4.5 | 12/13 (92%) | 2472 | 0.00225 |
| few-shot × gpt-4o-mini | 13/13 (100%) | 1540 | 0.00015 |
| few-shot × gemini-2.5-flash | 12/13 (92%) | 913 | 0.00037 |
| clarify-first × claude-haiku-4.5 | 4/13 (31%) | 2659 | 0.00192 |
| clarify-first × gpt-4o-mini | 6/13 (46%) | 1190 | 0.00011 |
| clarify-first × gemini-2.5-flash | 6/13 (46%) | 1015 | 0.00026 |

**Scatter (accuracy vs measured $/turn):** [showcase/prompt-scatter.html](showcase/prompt-scatter.html)

## Failures

**zero-shot × claude-haiku-4.5**: q07 (called search_events); q14 (geo params, Neukölln or Schillerkiez query); q23 (date_from = tomorrow evening, live-music intent in query/subcategory)
**zero-shot × gpt-4o-mini**: q07 (semantic query set (vibe needs ranking)); q14 (geo params, Neukölln or Schillerkiez query); q18 (no tool before clarifying, asked a clarifying question); q23 (live-music intent in query/subcategory)
**zero-shot × gemini-2.5-flash**: q07 (called search_events); q14 (geo params, Neukölln or Schillerkiez query); q16 (called search_events); q17 (searched first (answer-first policy)); q19 (attempted a search); q23 (date_from = tomorrow evening)
**prod-v1 × claude-haiku-4.5**: q14 (geo params, Neukölln or Schillerkiez query); q16 (date window covers Sunday); q23 (date_from = tomorrow evening)
**prod-v1 × gpt-4o-mini**: q07 (semantic query set (vibe needs ranking)); q14 (geo params, Neukölln or Schillerkiez query); q18 (no tool before clarifying, asked a clarifying question); q23 (live-music intent in query/subcategory); q25 (family_friendly=true)
**prod-v1 × gemini-2.5-flash**: q07 (called search_events); q14 (geo params, Neukölln or Schillerkiez query)
**few-shot × claude-haiku-4.5**: q16 (date window covers Sunday)
**few-shot × gemini-2.5-flash**: q07 (called search_events)
**clarify-first × claude-haiku-4.5**: q07 (called search_events); q11 (called search_events); q14 (called search_events); q16 (called search_events); q17 (searched first (answer-first policy)); q21 (called search_events); q23 (called search_events); q24 (called search_events); q25 (called search_events)
**clarify-first × gpt-4o-mini**: q07 (called search_events); q11 (called search_events); q14 (geo params, Neukölln or Schillerkiez query); q17 (searched first (answer-first policy)); q21 (called search_events); q23 (called search_events); q25 (called search_events)
**clarify-first × gemini-2.5-flash**: q07 (called search_events); q14 (called search_events); q16 (called search_events); q17 (searched first (answer-first policy)); q19 (attempted a search); q23 (called search_events); q24 (called search_events)
