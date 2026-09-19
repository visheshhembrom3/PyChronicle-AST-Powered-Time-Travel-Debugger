# PyChronicle Development Notes

PyChronicle separates the debugging backend from its user
interfaces.

The tracer acts as the execution backend while the CLI and
TUI provide user-facing interaction.

The SQLite layer provides persistent execution history.
