"""PyChronicle Demonstration Script.

Demonstrates variables, branching, loops, nested functions, and mutable objects.
"""


def compute_factorials(limit: int) -> list:
    results = []
    total = 1
    for n in range(1, limit + 1):
        total *= n
        results.append(total)
    return results


def main():
    greeting = "Hello PyChronicle"
    x = 10
    y = 20
    sum_val = x + y

    if sum_val > 25:
        flag = True
    else:
        flag = False

    facts = compute_factorials(4)
    summary = {"total": sum_val, "facts": facts, "flag": flag}
    return summary


if __name__ == "__main__":
    final_output = main()
    print("PyChronicle Demo Execution:")
    print("Final result:", final_output["total"])
    print("Factorials:", final_output["facts"])
    print("Flag:", final_output["flag"])
