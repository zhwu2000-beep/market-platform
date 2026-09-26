"""Profile-specific acceptance of the latest EMA8/EMA20 relationship."""

from market_platform.radar.context import RadarEvaluationContext
from market_platform.radar.core import (
    RadarGateDisposition,
    RadarGateIdentity,
    RadarGateOccurrence,
    RadarGateResult,
)
from market_platform.radar.current_content import (
    COMPLETED_DAILY_HISTORY_LOOKUP,
    RadarCompletedDailyHistoryLookupStatus,
)
from market_platform.radar.lightweight_observation import (
    RadarEmaRelation as RadarEmaRelation,
)
from market_platform.radar.lightweight_observation import (
    calculate_ema8_ema20_relation,
)
from market_platform.radar.resolver import RadarGateImplementationKey

EMA8_EMA20_RELATION_KEY = RadarGateImplementationKey(
    "ema8_ema20_relation", "1", "ema8_ema20_relation/v1"
)


class RadarEma8Ema20RelationGate:
    """Accept only explicitly configured relations; PASS grants no authority."""

    __slots__ = ("_occurrence", "_accepted_relations")

    def __init__(self, occurrence: RadarGateOccurrence) -> None:
        if type(occurrence) is not RadarGateOccurrence:
            raise TypeError("occurrence must be a RadarGateOccurrence")
        identity = occurrence.gate_identity
        key = RadarGateImplementationKey(
            identity.gate_id,
            identity.behavioral_revision,
            identity.configuration_schema,
        )
        if key != EMA8_EMA20_RELATION_KEY:
            raise ValueError("Unsupported EMA8/EMA20 relation implementation")
        if set(identity.configuration) != {"accepted_relations"}:
            raise ValueError("EMA relation v1 requires only accepted_relations")
        values = identity.configuration["accepted_relations"]
        # RadarGateIdentity freezes list/tuple configuration as tuples.
        if type(values) is not tuple or any(type(value) is not str for value in values):
            raise TypeError("accepted_relations must be a sequence of strings")
        relations = tuple(RadarEmaRelation(value) for value in values)
        if not relations or relations != tuple(
            relation for relation in RadarEmaRelation if relation in relations
        ):
            raise ValueError(
                "accepted_relations must be nonempty, unique and canonical"
            )
        self._occurrence = occurrence
        self._accepted_relations = relations

    @property
    def identity(self) -> RadarGateIdentity:
        return self._occurrence.gate_identity

    def evaluate(self, context: RadarEvaluationContext) -> RadarGateResult:
        lookup = context.get_fact(COMPLETED_DAILY_HISTORY_LOOKUP)
        if lookup.status is RadarCompletedDailyHistoryLookupStatus.UNAVAILABLE:
            return RadarGateResult(
                self._occurrence, RadarGateDisposition.ATTENTION, "HISTORY_UNAVAILABLE"
            )
        history = lookup.history
        if history is None:
            raise ValueError("PRESENT completed daily history requires history")
        if history.instrument != context.instrument:
            raise ValueError("Completed daily history instrument must match context")
        relation = calculate_ema8_ema20_relation(history)
        disposition = (
            RadarGateDisposition.PASS
            if relation in self._accepted_relations
            else RadarGateDisposition.DROP
        )
        return RadarGateResult(
            self._occurrence, disposition, f"EMA8_{relation.value}_EMA20"
        )
