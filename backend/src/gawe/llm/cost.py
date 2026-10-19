"""Cost estimation.

Unknown price returns None. Never invent a price when D1 is OPEN.
"""

from __future__ import annotations


def estimate_cost_usd(
    input_tokens: int | None,
    output_tokens: int | None,
    price_per_mtok_in: float | None = None,
    price_per_mtok_out: float | None = None,
) -> float | None:
    if input_tokens is None or output_tokens is None:
        return None
    if price_per_mtok_in is None or price_per_mtok_out is None:
        return None
    return (
        input_tokens / 1_000_000 * price_per_mtok_in
        + output_tokens / 1_000_000 * price_per_mtok_out
    )
