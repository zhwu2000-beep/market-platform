"""Canonical trading instrument identity."""

from __future__ import annotations

from dataclasses import dataclass, field

from market_platform._fingerprint import canonical_fingerprint
from market_platform.trading._canonical import required_text

TRADING_INSTRUMENT_IDENTITY_SCHEMA_VERSION = "trading_instrument_identity/v1"


@dataclass(frozen=True, slots=True)
class TradingInstrumentIdentity:
    """Minimal venue-qualified identity for one tradable instrument."""

    symbol: str
    venue: str
    schema_version: str = field(
        init=False,
        default=TRADING_INSTRUMENT_IDENTITY_SCHEMA_VERSION,
    )
    instrument_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        symbol = required_text(self.symbol, "symbol", uppercase=True)
        venue = required_text(self.venue, "venue", uppercase=True)
        if ":" in symbol:
            raise ValueError(
                "symbol must not contain a venue prefix; provide venue separately"
            )
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "venue", venue)
        object.__setattr__(
            self,
            "instrument_fingerprint",
            canonical_fingerprint(
                {
                    "schema_version": self.schema_version,
                    "symbol": symbol,
                    "venue": venue,
                }
            ),
        )

    def to_dict(self) -> dict[str, object]:
        """Return a deterministic JSON-safe identity projection."""

        return {
            "schema_version": self.schema_version,
            "symbol": self.symbol,
            "venue": self.venue,
            "instrument_fingerprint": self.instrument_fingerprint,
        }


__all__ = [
    "TRADING_INSTRUMENT_IDENTITY_SCHEMA_VERSION",
    "TradingInstrumentIdentity",
]
