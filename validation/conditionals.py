"""Validation Dataset D: Conditionals.

Tests branching logic and ensures non-executed branch does not affect state.
"""

x = 10

if x > 5:
    y = 100
else:
    y = 200
