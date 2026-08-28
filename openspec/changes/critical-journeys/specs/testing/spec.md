# critical-journeys

## ADDED Requirements

### Requirement: The concierge answers with a grounded event
A signed-in user asking an answerable question SHALL receive a streamed answer citing at least one
event that exists.

#### SC-CJ-01: An answer arrives
- **WHEN** a signed-in user sends a question the catalogue can answer
- **THEN** streamed text appears

#### SC-CJ-02: The citation is real
- **WHEN** the answer cites an event id
- **THEN** that id resolves to an event that exists and is upcoming

#### SC-CJ-03: A failure is visible, not silent
- **WHEN** the model call fails
- **THEN** the user sees an error message rather than nothing — the failure mode observed in
  production, where a dead API key produced an empty chat window

### Requirement: An event renders on the map and opens
An upcoming event with coordinates SHALL become a pin whose detail view opens.

#### SC-CJ-04: Pin renders
- **WHEN** at least one upcoming event has a resolvable coordinate
- **THEN** a pin is present on the map

#### SC-CJ-05: Detail opens
- **WHEN** that pin is activated
- **THEN** the detail view shows the event's title and time

#### SC-CJ-06: An empty catalogue skips, it does not fail
- **WHEN** no upcoming event has coordinates
- **THEN** the journey skips with a message pointing at the data gauges, because inventory is not
  this journey's responsibility

### Requirement: Journeys are independent and resilient to styling
Each journey SHALL run in isolation and locate elements by role and text rather than by CSS
internals.

#### SC-CJ-07: Independence
- **WHEN** journeys run in any order, or one is run alone
- **THEN** each passes without depending on another's state

#### SC-CJ-08: Styling changes do not break them
- **WHEN** classes or layout change without changing what a user sees
- **THEN** the journeys still pass
