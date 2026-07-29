# preference-feed

## ADDED Requirements

### Requirement: Per-user taste vector
The system SHALL maintain a per-user taste vector derived from the user's explicit signals —
onboarding categories/vibes (`profiles`), `user_events` (interested/going), and
`interested_venues` — computed as a recency-weighted aggregate of the embeddings of liked
items, minus disliked/dismissed ones.

#### Scenario: Taste vector builds from signals
- **WHEN** a user has marked at least one event "interested" or "going"
- **THEN** a taste vector exists for that user, weighted toward the embeddings of those events

#### Scenario: Taste updates on new signal
- **WHEN** the user marks a new event "going"
- **THEN** the taste vector is updated to move toward that event's embedding

### Requirement: Ranked personalized feed
The system SHALL return a ranked list of upcoming events for a signed-in user, scored by
cosine similarity to the taste vector and boosted by freshness and proximity to the user's
home location.

#### Scenario: Personalized ordering
- **WHEN** a signed-in user with a taste vector opens the feed
- **THEN** events more similar to their taste, sooner in time, and nearer their home rank higher

#### Scenario: Only upcoming, active events
- **WHEN** the feed is generated
- **THEN** only events that are active and start in the future appear

### Requirement: Exploration to avoid filter bubbles
The feed SHALL include a bounded share (10–20%) of novel or diverse events not closely
matched to the taste vector.

#### Scenario: Feed is not fully homogeneous
- **WHEN** a feed page is generated
- **THEN** between 10% and 20% of its items are exploration items outside the user's dominant categories

### Requirement: Cold-start behavior
The system SHALL produce a useful feed before any behaviour exists.

#### Scenario: Onboarding-only user
- **WHEN** a user has completed onboarding but has no likes yet
- **THEN** the feed is ranked from their onboarding categories/vibes

#### Scenario: No signals at all
- **WHEN** a user has neither onboarding nor likes
- **THEN** the feed falls back to popular and nearby upcoming events

### Requirement: Behaviour logging feeds learning
The system SHALL log sampled feed interactions (impression, open, dismiss) per user and use
them to refine the taste vector.

#### Scenario: Dismissed item lowers similar items
- **WHEN** a user dismisses an event
- **THEN** the interaction is recorded AND subsequent feeds down-weight events similar to it

### Requirement: Per-user data is access-controlled
All per-user data (taste vector, interaction log, bookmarks) SHALL be read and written only
through the Supabase anon key with the user's JWT, so Row Level Security scopes every row to
`auth.uid()`. The `service_role` key MUST NOT be used to serve user requests.

#### Scenario: User cannot read another user's data
- **WHEN** user A requests feed/taste data
- **THEN** only rows where `user_id = auth.uid()` (user A) are returned

#### Scenario: RLS enabled on new tables
- **WHEN** a per-user table is created via SQL
- **THEN** Row Level Security is explicitly enabled and owner-scoped policies exist for select/insert/update/delete

### Requirement: Taste data is private and deletable
Person-level taste and interaction data SHALL remain internal and SHALL be deleted on account
deletion or on request.

#### Scenario: Account deletion removes taste data
- **WHEN** a user deletes their account
- **THEN** their taste vector and interaction log are deleted

### Requirement: Optional recommendation reason
The feed MAY show a short "why we picked this" line per card, generated only from structured
event fields and cached; it MUST NOT be on the ranking hot path.

#### Scenario: Reason uses only structured fields
- **WHEN** a "why" line is shown for an event
- **THEN** it references only the event's category/venue/price/tags and the user's stated taste, never free-form scraped text passed to a model at request time
