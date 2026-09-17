"""Validation Dataset F: Nested Scopes and Closures.

Tests inner functions, closures, and isolated local namespaces.
"""


def outer(multiplier):
    base = 10

    def inner(val):
        computed = (base + val) * multiplier
        return computed

    res1 = inner(5)
    res2 = inner(10)
    return res1 + res2


final_val = outer(2)
