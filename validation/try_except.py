"""Validation Dataset L: Try/Except Handling.

Tests handled exception capture and ensures session is recorded as successful.
"""

a = 100
b = 0
try:
    c = a / b
except ZeroDivisionError as err:
    c = -1
    err_msg = str(err)

status = "recovered"
