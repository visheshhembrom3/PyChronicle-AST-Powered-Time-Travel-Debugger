"""Validation Dataset G: Recursion.

Tests recursive call stack frames, base cases, and return unwinding.
"""


def factorial(n):
    if n <= 1:
        return 1
    sub = factorial(n - 1)
    return n * sub


ans = factorial(4)
