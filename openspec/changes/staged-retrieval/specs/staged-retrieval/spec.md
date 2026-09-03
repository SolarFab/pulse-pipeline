# staged-retrieval

## ADDED Requirements

### Requirement: Ranking taxonomy and filtering taxonomy are separate parameters
The RPC SHALL accept disjoint parameter sets — `p_rank_category`, `p_rank_subcategory`,
`p_rank_genres` affecting order only, and `p_filter_category`, `p_filter_subcategory` excluding
rows. Filter parameters SHALL be set only from an explicit user selection. The combined legacy
parameters SHALL be removed rather than reinterpreted.

#### Scenario: A ranking parameter never excludes
- **WHEN** `p_rank_subcategory = 'comedy'` is supplied
- **THEN** events with a different or NULL subcategory remain eligible, ranked lower

#### Scenario: A filter parameter excludes
- **WHEN** `p_filter_category = 'workshops'` is supplied from a UI selection
- **THEN** events in other categories are not returned

#### Scenario: A stale caller fails loudly
- **WHEN** a caller passes the removed legacy `p_subcategory`
- **THEN** the call fails rather than silently applying a hard gate

### Requirement: Inferred taxonomy ranks, it does not exclude
The system SHALL NOT apply an inferred `category`, `subcategory` or `genres` as an exclusive filter,
and SHALL order results by taxonomy agreement instead. A NULL taxonomy field SHALL be treated as a
non-match, never as an exclusion.

#### Scenario: An untagged event is retrievable
- **WHEN** the user asks for "comedy" and a matching event's `subcategory` is NULL
- **THEN** the event is eligible, ranked below tagged matches

#### Scenario: An explicit UI filter is hard
- **WHEN** the user selected "Workshops only" in the interface
- **THEN** `category = 'workshops'` is applied as a hard constraint

### Requirement: Results are ordered by a deterministic total comparator chain
Ordering SHALL be exact title match, then taxonomy agreement, then similarity descending with NULLs
last, then distance when an area or radius was requested, then `start_time`, then event `id`.
The final `id` tier SHALL make the ordering total.

#### Scenario: Ordering is stable across identical inputs
- **WHEN** the same query runs twice against an unchanged catalogue
- **THEN** the returned order is identical

#### Scenario: Events sharing a start time still order deterministically
- **WHEN** two events tie on every comparator through `start_time`
- **THEN** they are ordered by `id`, and the order does not vary between runs

#### Scenario: A tagged match outranks an untagged one of equal similarity
- **WHEN** two events have equal similarity and only one matches the inferred subcategory
- **THEN** the tagged event ranks first, and both are returned

### Requirement: The RPC returns similarity with defined semantics
`match_events` SHALL return `similarity = 1 - cosine_distance`, and SHALL return NULL when no query
embedding was supplied or the event has no embedding. A NULL similarity SHALL NOT satisfy a floor.

#### Scenario: Filter-only search does not apply the floor
- **WHEN** a search supplies filters but no query text
- **THEN** every similarity is NULL, the floor is not applied, and the response records `threshold_not_applicable`

#### Scenario: A title match keeps its true score
- **WHEN** an event matches the query text exactly
- **THEN** it ranks first and still reports its actual similarity

### Requirement: Sufficiency is k qualifying deduplicated results
The system SHALL treat a result set as sufficient when at least `k` deduplicated, qualifying results
score at or above the floor, and SHALL NOT treat a non-zero row count as sufficient. `k` SHALL be
stored in the versioned floor record.

#### Scenario: Weak results do not suppress relaxation
- **WHEN** an attempt returns three results all below the floor
- **THEN** the system advances to the next rung

#### Scenario: Duplicates do not manufacture sufficiency
- **WHEN** the only matches are three copies of one event
- **THEN** they count as one when testing sufficiency

#### Scenario: Fewer than k at the final rung is answered honestly
- **WHEN** the city-wide rung yields one qualifying result
- **THEN** that result is returned, described as fewer options than usual, and no rung is retried

### Requirement: Unknown price cannot satisfy a stated price limit
When the user states a price limit, only rows whose price is known and within it SHALL count toward
sufficiency. Rows with unknown price MAY be returned, and SHALL be labelled as unknown-price
alternatives.

#### Scenario: Unknown price is an alternative, not a match
- **WHEN** the user says "under 15 euro" and a candidate has no price recorded
- **THEN** it does not count toward `k`, and any answer mentioning it states the price is unknown

#### Scenario: Unknown-price rows cannot alone satisfy the threshold
- **WHEN** every candidate under a stated price limit has unknown price
- **THEN** the attempt is insufficient and the system relaxes

### Requirement: The floor and k are calibrated from the fresh dated fixture
The production floor and `k` SHALL be calibrated from the dated scenario fixture. The historical
golden set SHALL NOT gate product behaviour.

#### Scenario: The stale set does not set the shipping floor
- **WHEN** the floor is calibrated
- **THEN** the source is the dated fixture, and its capture date is recorded with the floor

### Requirement: The floor record is a single active database row
The floor SHALL live in a `retrieval_config` table holding floor, `k`, embedding model, embedding
dimension, fixture id, fixture capture date and calibration date. Exactly one row SHALL be active,
enforced by a unique index. It SHALL be readable by the anonymous role in one statement and
writable only by the service role, and replacement SHALL be atomic.

#### Scenario: A reader never sees a half-applied calibration
- **WHEN** a calibration replaces the active record while a search is running
- **THEN** the search reads either the old or the new record, never neither and never both

#### Scenario: Changing the embedding model invalidates the floor
- **WHEN** the configured model differs from the active record's
- **THEN** the search does not relax, and the response and trace say the floor is uncalibrated

#### Scenario: A missing active record fails closed
- **WHEN** no active record exists
- **THEN** the search runs unrelaxed and reports uncalibrated, rather than assuming a default floor

### Requirement: Fixture freshness has a defined maximum age
The scenario fixture's `fixture_captured_at` SHALL be within a configurable maximum age, default
14 days, evaluated in `Europe/Berlin`, and the check SHALL use the recorded capture date rather
than file modification time.

#### Scenario: The boundary is defined
- **WHEN** the fixture was captured exactly 14 days ago
- **THEN** the suite passes; at 15 days it fails

#### Scenario: Re-saving does not refresh a stale fixture
- **WHEN** a stale fixture file is rewritten without recapture
- **THEN** the suite still fails, because the capture date is unchanged

### Requirement: Location resolves event-first at every tier
Location SHALL resolve postcode, then district, then label, then centroid radius, and within each
tier SHALL prefer the event's own value over its venue's. The answering tier SHALL be returned.

#### Scenario: An event-specific location is not overwritten by its venue
- **WHEN** an event has its own address and coordinates differing from its venue row
- **THEN** the event's own location decides the area, and the venue is not consulted

#### Scenario: The answering tier is reported
- **WHEN** an area resolves only by radius
- **THEN** the metadata and trace name radius as the answering tier

### Requirement: Areas are canonical identifiers, never model strings
The RPC SHALL accept a canonical `area_id` from a checked-in mapping. Raw user or model text SHALL
NOT be passed as a location identifier.

#### Scenario: An unknown area does not silently filter
- **WHEN** the user names an area absent from the mapping
- **THEN** no area constraint is applied, `area_unknown` is recorded, and the answer says the search was city-wide

#### Scenario: Alias ambiguity is resolved before the RPC
- **WHEN** the user's words match several areas
- **THEN** the web resolver emits `area_ambiguous` and asks which was meant
- **AND** the RPC is not called, because raw words never reach it

### Requirement: Relaxation is a deterministic ladder in application code
The system SHALL relax one constraint per attempt, venue → area → radius → city-wide, decided
outside the model, and SHALL NOT relax the date window, `is_active`, or a stated price limit.

#### Scenario: Location relaxes, meaning does not
- **WHEN** "comedy tonight in Prenzlauer Berg" clears no floor locally
- **THEN** the next attempt widens location and keeps the semantics of "comedy"

#### Scenario: Nothing anywhere is a valid answer
- **WHEN** no rung yields a qualifying result city-wide
- **THEN** the system says so and SHALL NOT present unrelated events as matches

### Requirement: The public RPC has a performance and safety budget
`match_events` SHALL meet a recorded latency budget on representative windows, SHALL bound its
limit, and SHALL fix its `search_path`.

#### Scenario: Plan evidence and latency evidence are separate measurements
- **WHEN** the RPC is changed
- **THEN** `EXPLAIN (ANALYZE, BUFFERS)` is recorded for three representative queries, showing index use and no sequential scan on `events`
- **AND** a separate benchmark of 200 warm-cache runs per query at production volume reports p50 and p95, with p95 under 400 ms

#### Scenario: search_path cannot be redirected
- **WHEN** the function is called by an anonymous client
- **THEN** it executes with `search_path = public, pg_temp`

### Requirement: Traces carry structured arguments, never raw user text
The system SHALL record structured arguments verbatim, SHALL record the user's free text only as a
salted hash with its length and detected language, and SHALL NOT record scraped event descriptions,
credentials, embedding vectors, or user identifiers beyond an opaque session id. Traces SHALL expire
after 30 days and SHALL be deletable by session id.

#### Scenario: Free text is not stored in production
- **WHEN** a user asks a question containing personal detail
- **THEN** the trace records a salted hash, its length and language, and not the text
- **AND** verbatim capture is possible only behind a development-only flag

#### Scenario: Scraped descriptions never enter a span
- **WHEN** results are traced
- **THEN** only event ids and scores are recorded, not their descriptions

#### Scenario: Traces honour deletion
- **WHEN** an account deletion is processed
- **THEN** the spans for that session id are removed within the retention window

### Requirement: Every attempt is traced well enough to diagnose routing
The system SHALL emit per attempt the allowlisted structured arguments, rung, answering location
tier, `area_id`, result ids, similarities, relaxation reason, model and config version, and
catalogue timestamp.

#### Scenario: A complaint is diagnosable from the trace
- **WHEN** a user reports an empty or narrow answer
- **THEN** the trace shows which rung fired, on what evidence, and why it did not widen
- **AND** exact replay is not claimed, because the catalogue is mutable
