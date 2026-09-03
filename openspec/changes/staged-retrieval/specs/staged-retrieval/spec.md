# staged-retrieval

## ADDED Requirements

### Requirement: Constraints are classified by hardness
The system SHALL classify every search constraint as always-hard, relaxable, semantic, or a ranking
signal, and SHALL NOT apply a taxonomy filter as a hard gate unless the user explicitly selected one.

#### Scenario: Taxonomy is a ranking signal, not a gate
- **WHEN** the user asks for "comedy" in free text
- **THEN** the search matches semantically and SHALL NOT filter on `subcategory = 'comedy'`
- **AND** an event whose subcategory is NULL but whose text means comedy is eligible

#### Scenario: An explicit UI filter is hard
- **WHEN** the user has selected the "Workshops only" filter in the interface
- **THEN** the search applies `category = 'workshops'` as a hard constraint

#### Scenario: Date is never relaxed
- **WHEN** the user asks for "tonight" and nothing matches at any rung
- **THEN** the system reports that nothing was found tonight and SHALL NOT return events on other days

### Requirement: Constraints shape the query rather than filtering its output
The system SHALL apply constraints inside the ranked query and SHALL NOT retrieve a global top-N
and filter it afterwards.

#### Scenario: A strong local match is not discarded
- **WHEN** a highly relevant event in the requested neighbourhood ranks outside the global top-10
- **THEN** it is still returned, because the neighbourhood constraint was applied before ranking

### Requirement: Relaxation follows a deterministic ladder
The system SHALL relax at most one constraint per attempt, in the order venue → neighbourhood →
radius → city-wide, and SHALL NOT relax an always-hard constraint.

#### Scenario: Location relaxes, meaning does not
- **WHEN** "comedy tonight in Prenzlauer Berg" yields nothing above threshold in Prenzlauer Berg
- **THEN** the next attempt widens the location and keeps the semantic meaning of "comedy"
- **AND** the answer states that the search was widened beyond Prenzlauer Berg

#### Scenario: Nothing anywhere is a valid answer
- **WHEN** no attempt clears the threshold even city-wide
- **THEN** the system says so plainly and SHALL NOT present unrelated events as matches

### Requirement: Sufficiency is a relevance threshold, not a row count
The system SHALL decide whether to relax using at least `k` results scoring at or above a calibrated
similarity floor, and SHALL NOT treat any non-zero row count as sufficient.

#### Scenario: Weak results do not suppress relaxation
- **WHEN** a query returns three results all scoring below the floor
- **THEN** the system relaxes to the next rung rather than answering from them

#### Scenario: The floor is calibrated, not guessed
- **WHEN** the embedding model or its dimension changes
- **THEN** the recorded floor is invalid until recalibrated against the golden set, and the retrieval gate fails

### Requirement: Deduplication precedes limiting and the relevance test
The system SHALL collapse duplicate events before applying the result limit and before evaluating
the relevance threshold.

#### Scenario: Duplicates do not manufacture sufficiency
- **WHEN** the only matches are three near-identical copies of one event
- **THEN** they count as one result when testing the threshold

### Requirement: The model is told what was relaxed
Every result set SHALL carry the rung that produced it, the constraints relaxed, and the candidate
count of the unrelaxed query.

#### Scenario: Widened results are labelled as widened
- **WHEN** results come from a relaxed rung
- **THEN** the metadata says which constraint was dropped, and the answer reflects it

### Requirement: Every attempt is traced
The system SHALL emit, for each retrieval attempt, the arguments as sent, the rung, the returned
event ids, their scores, and the relaxation reason.

#### Scenario: A failure is diagnosable from traces alone
- **WHEN** a user reports that a search returned nothing
- **THEN** the trace alone is sufficient to reproduce the query and identify which rung failed, without database access
