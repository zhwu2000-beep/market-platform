"""Pure EMA observations; structural correspondence grants no authority.

Calendar membership, the exact 250-session window, evaluation cutoff and attachment
to acquired current content remain production acceptance responsibilities. These
values do not establish those facts, persist state, or create Candidates.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from enum import StrEnum
from numbers import Real
from typing import cast

from market_platform.indicators.trend import calculate_ema
from market_platform.instruments.identity import CanonicalInstrumentId
from market_platform.radar.current_content import RadarCompletedDailyHistory
from market_platform.radar.observation import RadarMarketContentScope

EMA8_EMA20_OBSERVATION_DEFINITION_ID = "ema8_ema20_relation_observation"
EMA8_EMA20_CALCULATION_REVISION = "1"
EMA8_EMA20_OBSERVATION_SCHEMA = "radar_ema8_ema20_observation/v1"


class RadarEmaRelation(StrEnum):
    ABOVE = "ABOVE"
    EQUAL = "EQUAL"
    BELOW = "BELOW"


def _identity(value: object, name: str) -> None:
    # Bounded passive tokens allow independently valid definition migrations.
    if type(value) is not str:
        raise TypeError(f"{name} must be a string")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}", value) is None:
        raise ValueError(f"Invalid {name}")


@dataclass(frozen=True, slots=True)
class RadarLightweightObservation:
    """Structural observation, independent of Profile, Gate and acceptance time.

    Definition identities are bounded tokens, not a registry of supported producers.
    The evaluator assumes operands have passed their production acceptance boundary.
    """

    instrument: CanonicalInstrumentId
    definition_id: str
    calculation_revision: str
    observation_schema: str
    completed_session: date
    normalized_market_content_identity: str
    content_scope: RadarMarketContentScope
    relation: RadarEmaRelation
    as_of: datetime

    def __post_init__(self) -> None:
        if type(self.instrument) is not CanonicalInstrumentId:
            raise TypeError("instrument must be a CanonicalInstrumentId")
        CanonicalInstrumentId(self.instrument.instrument_id)
        for name in ("definition_id", "calculation_revision", "observation_schema"):
            _identity(getattr(self, name), name)
        if type(self.completed_session) is not date:
            raise TypeError("completed_session must be a plain date")
        if type(self.content_scope) is not RadarMarketContentScope:
            raise TypeError("content_scope must be RadarMarketContentScope")
        replace(self.content_scope)  # Unknown scope schemas remain invalid.
        if self.completed_session != self.content_scope.history_end:
            raise ValueError("completed_session must equal history_end")
        identity = self.normalized_market_content_identity
        if type(identity) is not str:
            raise TypeError("content identity must be a string")
        if re.fullmatch(r"sha256:[0-9a-f]{64}", identity) is None:
            raise ValueError("Invalid normalized market-content identity")
        if type(self.relation) is not RadarEmaRelation:
            raise TypeError("relation must be RadarEmaRelation")
        value = self.as_of
        if not isinstance(value, datetime):
            raise TypeError("as_of must be a datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        plain = datetime(
            value.year,
            value.month,
            value.day,
            value.hour,
            value.minute,
            value.second,
            value.microsecond,
            tzinfo=value.tzinfo,
            fold=value.fold,
        )
        object.__setattr__(self, "as_of", plain.astimezone(UTC))

    def to_dict(self) -> dict[str, object]:
        """Detached deterministic passive data; not a persistence operation."""
        return {
            "instrument": self.instrument.to_dict(),
            "definition_id": self.definition_id,
            "calculation_revision": self.calculation_revision,
            "observation_schema": self.observation_schema,
            "completed_session": self.completed_session.isoformat(),
            "normalized_market_content_identity": (
                self.normalized_market_content_identity
            ),
            "content_scope": self.content_scope.to_dict(),
            "relation": self.relation.value,
            "as_of": self.as_of.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: object) -> RadarLightweightObservation:
        """Reject malformed/unsupported input rather than infer a baseline."""
        fields = {
            "instrument",
            "definition_id",
            "calculation_revision",
            "observation_schema",
            "completed_session",
            "normalized_market_content_identity",
            "content_scope",
            "relation",
            "as_of",
        }
        if type(value) is not dict or set(value) != fields:
            raise ValueError("Expected exactly the observation fields")
        instrument = value["instrument"]
        if type(instrument) is not dict or set(instrument) != {"instrument_id"}:
            raise ValueError("Invalid instrument object")
        for name in fields - {"instrument", "content_scope"}:
            if type(value[name]) is not str:
                raise TypeError(f"{name} must be a string")
        session = date.fromisoformat(value["completed_session"])
        if session.isoformat() != value["completed_session"]:
            raise ValueError("completed_session must use YYYY-MM-DD")
        return cls(
            instrument=CanonicalInstrumentId(instrument["instrument_id"]),
            definition_id=value["definition_id"],
            calculation_revision=value["calculation_revision"],
            observation_schema=value["observation_schema"],
            completed_session=session,
            normalized_market_content_identity=value[
                "normalized_market_content_identity"
            ],
            content_scope=RadarMarketContentScope.from_dict(value["content_scope"]),
            relation=RadarEmaRelation(value["relation"]),
            as_of=datetime.fromisoformat(value["as_of"]),
        )


def calculate_ema8_ema20_relation(
    history: RadarCompletedDailyHistory,
) -> RadarEmaRelation:
    """Revision 1 mathematics over retained history, without selection or I/O."""
    if type(history) is not RadarCompletedDailyHistory:
        raise TypeError("history must be RadarCompletedDailyHistory")
    # Public row order: symbol, timestamp, open, high, low, close, volume, provider.
    closes = tuple(row[5] for row in history.series.full_prefix().iter_rows())
    ema8 = calculate_ema(cast(Sequence[Real], closes), period=8)
    ema20 = calculate_ema(cast(Sequence[Real], closes), period=20)
    if not ema8 or not ema20 or ema8[-1] is None or ema20[-1] is None:
        raise ValueError("Completed daily history must yield latest EMA8 and EMA20")
    if ema8[-1] > ema20[-1]:
        return RadarEmaRelation.ABOVE
    if ema8[-1] == ema20[-1]:
        return RadarEmaRelation.EQUAL
    return RadarEmaRelation.BELOW


def observe_ema8_ema20(
    history: RadarCompletedDailyHistory,
    *,
    as_of: datetime,
) -> RadarLightweightObservation:
    """Build the current definition from caller-validated retained history."""
    relation = calculate_ema8_ema20_relation(history)
    return RadarLightweightObservation(
        history.instrument,
        EMA8_EMA20_OBSERVATION_DEFINITION_ID,
        EMA8_EMA20_CALCULATION_REVISION,
        EMA8_EMA20_OBSERVATION_SCHEMA,
        history.completed_session,
        history.series.content_fingerprint,
        history.content_scope,
        relation,
        as_of,
    )
