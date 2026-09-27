"""Small numeric helpers shared across modules. Stdlib only (math)."""

from math import sqrt


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def stdev(xs):
    """Sample standard deviation; 0.0 when fewer than 2 samples."""
    xs = list(xs)
    n = len(xs)
    if n < 2:
        return 0.0
    m = sum(xs) / n
    return sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def ema(values, period):
    """Exponential moving average.

    Returns a list aligned with `values`; entries are None until `period`
    samples have been seen (seeded with the first value, SMA-free by design
    so the seed is deterministic).
    """
    out = [None] * len(values)
    if period <= 0 or not values:
        return out
    k = 2.0 / (period + 1)
    prev = None
    for i, v in enumerate(values):
        if v is None:
            out[i] = prev
            continue
        prev = v if prev is None else v * k + prev * (1.0 - k)
        out[i] = prev if i >= period - 1 else None
    return out


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def sign(x):
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0
