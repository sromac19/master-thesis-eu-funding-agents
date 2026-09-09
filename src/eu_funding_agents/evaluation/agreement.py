from __future__ import annotations


def quadratic_weighted_kappa(first: list[int], second: list[int], *, grades: int = 4) -> float:
    if len(first) != len(second) or not first:
        raise ValueError("annotator ratings must be non-empty and equally sized")
    if grades < 2 or any(rating not in range(grades) for rating in first + second):
        raise ValueError("ratings must fit the configured grade range")

    observed = [[0 for _ in range(grades)] for _ in range(grades)]
    first_histogram = [0 for _ in range(grades)]
    second_histogram = [0 for _ in range(grades)]
    for left, right in zip(first, second, strict=True):
        observed[left][right] += 1
        first_histogram[left] += 1
        second_histogram[right] += 1

    count = len(first)
    observed_disagreement = 0.0
    expected_disagreement = 0.0
    for left in range(grades):
        for right in range(grades):
            weight = ((left - right) / (grades - 1)) ** 2
            observed_disagreement += weight * observed[left][right] / count
            expected_disagreement += (
                weight * first_histogram[left] * second_histogram[right] / (count * count)
            )
    if expected_disagreement == 0:
        return 1.0 if observed_disagreement == 0 else 0.0
    return 1 - observed_disagreement / expected_disagreement
