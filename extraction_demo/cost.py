"""Parametric cost model. Every price and volume is supplied by the caller; nothing is built in."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


def _non_negative(**values: float) -> None:
    for name, value in values.items():
        if value < 0:
            raise ValueError(f"{name} must not be negative")


@dataclass(frozen=True)
class Volumes:
    docs_per_run: int
    runs_per_month: int
    calls_per_doc: float = 1.0
    retry_rate: float = 0.0

    def __post_init__(self) -> None:
        _non_negative(
            docs_per_run=self.docs_per_run,
            runs_per_month=self.runs_per_month,
            calls_per_doc=self.calls_per_doc,
            retry_rate=self.retry_rate,
        )

    @property
    def calls_per_run(self) -> float:
        return self.docs_per_run * self.calls_per_doc * (1 + self.retry_rate)

    @property
    def calls_per_month(self) -> float:
        return self.calls_per_run * self.runs_per_month


@dataclass(frozen=True)
class MeteredPricing:
    """Pay per call."""

    price_per_call: float

    def __post_init__(self) -> None:
        _non_negative(price_per_call=self.price_per_call)

    def cost_per_run(self, volumes: Volumes) -> float:
        return volumes.calls_per_run * self.price_per_call

    def cost_per_month(self, volumes: Volumes) -> float:
        return volumes.calls_per_month * self.price_per_call


@dataclass(frozen=True)
class FlatPricing:
    """Pay a fixed fee for a pack of calls; another pack is bought once the month exceeds capacity."""

    fee_per_pack: float
    calls_per_pack: int

    def __post_init__(self) -> None:
        _non_negative(fee_per_pack=self.fee_per_pack)
        if self.calls_per_pack <= 0:
            raise ValueError("calls_per_pack must be positive")

    def packs_needed(self, volumes: Volumes) -> int:
        return max(1, math.ceil(round(volumes.calls_per_month / self.calls_per_pack, 6)))

    def cost_per_month(self, volumes: Volumes) -> float:
        return self.packs_needed(volumes) * self.fee_per_pack

    def cost_per_run(self, volumes: Volumes) -> float:
        """Monthly fee amortised over runs."""
        return self.cost_per_month(volumes) / volumes.runs_per_month if volumes.runs_per_month else 0.0


def break_even_runs(volumes: Volumes, metered: MeteredPricing, flat: FlatPricing) -> Optional[int]:
    """Smallest runs per month at which one flat pack costs no more than metered pricing.

    Returns None when metered stays cheaper for every volume that fits in one pack.
    """
    metered_per_run = metered.cost_per_run(volumes)
    if metered_per_run <= 0:
        return None
    runs = max(1, math.ceil(round(flat.fee_per_pack / metered_per_run, 6)))
    if round(runs * volumes.calls_per_run, 6) > flat.calls_per_pack:
        return None
    return runs
