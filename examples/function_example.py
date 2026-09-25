# PyChronicle Example: Function Calls & Scoped Variables
def multiply(a: int, b: int) -> int:
    result = a * b
    return result


def calculate() -> int:
    val1 = 5
    val2 = 12
    product = multiply(val1, val2)
    return product


if __name__ == "__main__":
    ans = calculate()
    print("Function result:", ans)
