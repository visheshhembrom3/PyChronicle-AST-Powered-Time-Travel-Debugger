# PyChronicle Database

PyChronicle uses SQLite to store execution history.

## Main Tables

### sessions

Stores information about each debugging session, including
the target filename and session metadata.

### snapshots

Stores execution steps, events, scopes, and variable changes.

## Delta Storage

PyChronicle records variable changes as deltas rather than
repeatedly storing complete program states.

This allows previous execution states to be reconstructed
during time-travel debugging.
