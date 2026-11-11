"""Integer allocation with the largest remainder rule."""

import numpy as np


def largest_remainder(*, weights: np.ndarray, totals: np.ndarray) -> np.ndarray:
    """Split each row total into integers in proportion to the row weights.

    The integers of a row sum to the row total.
    The largest fractional parts get the extra units; a tie goes to the lower column index.
    A row with zero weight sum gets zeros.
    """
    sums = weights.sum(axis=1, keepdims=True)
    raw = weights / np.where(sums > 0, sums, 1.0) * totals[:, None]
    base = np.floor(raw + 1e-9)
    remainder = np.where(sums[:, 0] > 0, totals - base.sum(axis=1), 0).astype(int)
    order = np.argsort(-(raw - base), axis=1, kind="stable")
    ranks = np.argsort(order, axis=1)
    return (base + (ranks < remainder[:, None])).astype(int)
