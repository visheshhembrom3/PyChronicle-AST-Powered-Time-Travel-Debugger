"""Validation Dataset I: Dictionary Mutation.

Tests in-place dictionary mutations (insert, update, delete).
"""

data = {"a": 1}
data["b"] = 2
data["a"] = 10
del data["b"]
