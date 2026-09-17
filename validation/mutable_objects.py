"""Validation Dataset H: Mutable Objects.

Tests in-place list mutation (append, pop) and ensures past snapshots remain intact.
"""

numbers = [1, 2, 3]
numbers.append(4)
numbers.append(5)
popped = numbers.pop()
