# Semantic Search — genre filter layer

## ADDED Requirements

### Requirement: Genre filter in event retrieval
`match_events` SHALL accept `p_genres text[]` (default NULL). When set, results MUST be
restricted to events whose `tags` overlap `p_genres` (array-overlap, GIN-indexed); the vector
query ranks within that set. The concierge `search_events` tool SHALL expose a `genres`
parameter whose values are the taxonomy genre enum, loaded at runtime like categories.

#### Scenario: Exact recall for a tagged genre
- **WHEN** search_events is called with genres:['hip-hop'] and a date window containing tagged hip-hop events
- **THEN** every event tagged `hip-hop` in the window is eligible (no top-k exclusion by the filter itself), ranked by the query embedding

#### Scenario: Model translates intent to enum
- **WHEN** a user asks "hip hop event tonight?"
- **THEN** the model calls search_events with genres:['hip-hop'] and a free-text query, never a subcategory

### Requirement: Genre-aware relax order
The relax-on-empty degrade SHALL drop filters in the order category/subcategory first, then
genres, retrying once per step only while a free-text query is present, and MUST report which
filters were relaxed in the tool result note.

#### Scenario: Genre kept while subcategory dropped
- **WHEN** a search with subcategory and genres returns zero rows
- **THEN** the retry drops subcategory but keeps genres; only if still empty does a final retry drop genres

#### Scenario: Discovery miss only after full relax
- **WHEN** all relax steps still return zero rows for a query
- **THEN** exactly one discovery miss is logged; recovered searches log none
