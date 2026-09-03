# staged-retrieval

## ADDED Requirements

### Requirement: Inferred taxonomy is a ranking signal, not a gate
The system SHALL NOT apply `category`, `subcategory` or `genres` as an exclusive filter when they
were inferred from free text, and SHALL apply them as ordering signals instead.

#### Scenario: An untagged event is still retrievable
- **WHEN** the user asks for "comedy" and an event's `subcategory` is NULL but its text means comedy
- **THEN** the event is eligible, and its missing tag affects only its rank

#### Scenario: An explicit UI filter is hard
- **WHEN** the user has selected "Workshops only" in the interface
- **THEN** `category = 'workshops'` is applied as a hard constraint

### Requirement: Sufficiency is a scored threshold measured after deduplication
The system SHALL decide whether to relax using at least `k` deduplicated results at or above a
calibrated similarity floor, and SHALL NOT treat a non-zero row count as sufficient.

#### Scenario: Weak results do not suppress relaxation
- **WHEN** an attempt returns three results all scoring below the floor
- **THEN** the system advances to the next rung rather than answering from them

#### Scenario: Duplicates do not manufacture sufficiency
- **WHEN** the only matches are three copies of one event
- **THEN** they count as one when testing the threshold

### Requirement: The similarity floor is versioned and fails closed
A floor SHALL be stored with its embedding model id, embedding dimension, evaluator fixture id and
freshness date, and calibration date. On any mismatch the system SHALL run unrelaxed and report the
floor as uncalibrated.

#### Scenario: Changing the embedding model invalidates the floor
- **WHEN** the configured embedding model differs from the one recorded with the floor
- **THEN** the search does not relax, and the response and trace state that the floor is uncalibrated

### Requirement: The RPC returns ranking evidence and a dedup key
`match_events` SHALL return a similarity score and a stable dedup key per row, and SHALL collapse
duplicates before applying `LIMIT`.

#### Scenario: Deduplication precedes limiting
- **WHEN** five of the top ten rows are copies of two real events
- **THEN** the caller receives the distinct events, and the limit is applied to distinct events

#### Scenario: Scores are available to the caller
- **WHEN** a query supplies an embedding
- **THEN** each row carries its similarity, so the caller can apply a floor without re-querying

### Requirement: Location resolves from an authoritative ordered source
The system SHALL resolve a named area through postcode, then district, then the neighbourhood
label, then a radius from the area centroid, and SHALL record which source answered.

#### Scenario: A named area resolves by postcode
- **WHEN** the user names "Prenzlauer Berg"
- **THEN** it resolves through a checked-in postcode mapping rather than a model-supplied string
- **AND** the events hosted by venues in those postcodes are eligible

#### Scenario: The answering source is recorded
- **WHEN** an area resolves only by radius because no venue carried a postcode
- **THEN** the trace and the result metadata name radius as the source

### Requirement: Relaxation follows a deterministic ladder in application code
The system SHALL relax at most one constraint per attempt, in the order venue → area → radius →
city-wide, decided outside the model, and SHALL NOT relax an always-hard constraint.

#### Scenario: Location relaxes, meaning does not
- **WHEN** "comedy tonight in Prenzlauer Berg" clears no floor locally
- **THEN** the next attempt widens location and keeps the semantics of "comedy"

#### Scenario: The model does not choose to widen
- **WHEN** results are returned from a relaxed rung
- **THEN** the widening was decided by application code, and the model receives it as given metadata

#### Scenario: Nothing anywhere is a valid answer
- **WHEN** no rung clears the floor even city-wide
- **THEN** the system says so plainly and SHALL NOT present unrelated events as matches

### Requirement: Hard constraints are defined against real fields
Always-hard constraints SHALL be limited to the date/time window, `is_active`, and an explicitly
stated price limit. Rows with unknown price SHALL remain eligible under a price limit and SHALL be
labelled as price-unknown.

#### Scenario: Unknown price is eligible but disclosed
- **WHEN** the user says "under 15 euro" and a matching event has no price recorded
- **THEN** the event is returned and marked price-unknown, and the answer does not assert it is under 15 euro

#### Scenario: Date is never relaxed
- **WHEN** nothing matches "tonight" at any rung
- **THEN** the system reports nothing tonight and SHALL NOT return other days

### Requirement: The model is told what was relaxed
Every result set SHALL carry the rung, the constraints relaxed, the location source that answered,
and the unrelaxed candidate count.

#### Scenario: Widened results are labelled
- **WHEN** results come from a relaxed rung
- **THEN** the answer states which constraint was widened

### Requirement: Every attempt is traced well enough to diagnose routing
The system SHALL emit, per attempt, the arguments as sent, the rung, the location source, result
ids, similarity scores, the relaxation reason, the model and config version, and the catalogue
timestamp.

#### Scenario: A complaint is diagnosable from the trace
- **WHEN** a user reports an empty or narrow answer
- **THEN** the trace alone shows which rung fired, on what evidence, and why it did not widen further
- **AND** exact replay is not claimed, because results depend on mutable catalogue contents
