# PyChronicle Example: Controlled Exception Handling
def safe_divide(a: int, b: int) -> float:
    try:
        res = a / b
    except ZeroDivisionError:
        res = 0.0
        print("Caught division by zero!")
    return res


if __name__ == "__main__":
    num = 100
    denom = 0
    outcome = safe_divide(num, denom)
    print("Outcome:", outcome)
