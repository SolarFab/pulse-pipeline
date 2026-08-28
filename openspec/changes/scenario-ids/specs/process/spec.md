# process

## ADDED Requirements

### Requirement: Scenarios carry stable identifiers
Every scenario in a change's spec SHALL have an identifier that survives renaming of the tests
that cover it.

#### SC-ID-01: Format
- **WHEN** a scenario is written
- **THEN** its heading carries an ID of the form `SC-<CHANGE>-<NN>`

#### SC-ID-02: Stability
- **WHEN** a test covering a scenario is renamed or moved
- **THEN** the scenario's ID does not change

### Requirement: Tests declare what they cover
A test that verifies a scenario SHALL declare that scenario's ID.

#### SC-ID-03: Declaration
- **WHEN** a test covers a scenario
- **THEN** it carries a marker naming the scenario ID

### Requirement: Both directions are checked
CI SHALL report scenarios with no test and markers with no scenario. A stale marker misleads as
badly as a missing one.

#### SC-ID-04: Uncovered scenario
- **WHEN** a scenario has no test declaring its ID
- **THEN** CI reports it

#### SC-ID-05: Dangling marker
- **WHEN** a test declares an ID no scenario defines
- **THEN** CI reports it
