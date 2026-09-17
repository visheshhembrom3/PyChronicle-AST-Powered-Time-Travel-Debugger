"""Validation Dataset N: Complex Integration Program.

Combines variables, functions, recursion, closures, loops, conditionals,
mutable lists and dicts, and handled exceptions into a single workload.
"""


def compute_statistics(raw_numbers):
    cleaned = []
    for num in raw_numbers:
        try:
            val = float(num)
            cleaned.append(val)
        except (ValueError, TypeError):
            continue

    if not cleaned:
        return {"count": 0, "sum": 0.0, "mean": 0.0}

    total = sum(cleaned)
    count = len(cleaned)
    mean = total / count

    def calculate_variance():
        diff_sq = [(x - mean) ** 2 for x in cleaned]
        return sum(diff_sq) / count

    variance = calculate_variance()
    return {
        "count": count,
        "sum": total,
        "mean": mean,
        "variance": variance,
    }


dataset = ["10", 20, "invalid", 30, "40.5", None]
stats = compute_statistics(dataset)
summary_tag = "valid" if stats["count"] > 3 else "sparse"
