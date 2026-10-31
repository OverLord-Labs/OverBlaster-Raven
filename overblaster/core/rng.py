"""Seedable random numbers (a linear congruential generator). Port of web src/core/rng.ts.

Every random choice in the game goes through one of these, so a run is reproducible from its seed and
the same seed gives the same levels as the web game. The constants and the order of draws must not change.
"""

import math
from typing import Callable, List, TypeVar

T = TypeVar("T")


class Rng:
    def __init__(self, seed: float = 1) -> None:
        self.s = (int(seed) & 0xFFFFFFFF) % 4294967296

    def next(self) -> float:
        """Uniform in [0, 1)."""
        self.s = (self.s * 1664525 + 1013904223) % 4294967296
        return self.s / 4294967296

    def signed(self) -> float:
        """Uniform in [-1, 1)."""
        return self.next() * 2 - 1

    def gauss(self) -> float:
        """Standard normal (Box-Muller)."""
        return math.sqrt(-2 * math.log(1 - self.next())) * math.cos(math.pi * 2 * self.next())

    def shuffle(self, a: List[T]) -> List[T]:
        """Fisher-Yates shuffle in place, using this generator."""
        for i in range(len(a) - 1, 0, -1):
            j = math.floor(self.next() * (i + 1))
            a[i], a[j] = a[j], a[i]
        return a


def srng(seed: float) -> Callable[[], float]:
    """A generator for fixed decorative patterns (stars, sparks): same seed, same sequence."""
    s = [int(seed) % 4294967296]

    def nxt() -> float:
        s[0] = (s[0] * 1664525 + 1013904223) % 4294967296
        return s[0] / 4294967296

    return nxt
