"""Construction boundary for minimal market observations."""

from __future__ import annotations

from market_platform.observation.models import (
    MarketObservation,
    ObservationIdentity,
    ObservationProvenance,
    PriceFacts,
    SignalFacts,
    StructureFacts,
)
from market_platform.signals.models import MarketSignalSnapshot
from market_platform.structure.models import PriceStructureSnapshot


def build_observation(
    identity: ObservationIdentity,
    provenance: ObservationProvenance,
    *,
    price_facts: PriceFacts | None = None,
    signal_facts: SignalFacts | None = None,
    structure_facts: StructureFacts | None = None,
) -> MarketObservation:
    """Build an observation from already-adapted fact groups."""

    if not isinstance(identity, ObservationIdentity):
        raise TypeError("identity must be an ObservationIdentity")
    if not isinstance(provenance, ObservationProvenance):
        raise TypeError("provenance must be an ObservationProvenance")
    return MarketObservation(
        identity=identity,
        provenance=provenance,
        price_facts=price_facts,
        signal_facts=signal_facts,
        structure_facts=structure_facts,
    )


def build_signal_facts(snapshot: MarketSignalSnapshot) -> SignalFacts:
    """Adapt an existing signal snapshot without interpreting its values."""

    if not isinstance(snapshot, MarketSignalSnapshot):
        raise TypeError("snapshot must be a MarketSignalSnapshot")
    return SignalFacts(
        symbol=snapshot.symbol,
        as_of=snapshot.timestamp,
        signals=snapshot.signals,
    )


def build_structure_facts(snapshot: PriceStructureSnapshot) -> StructureFacts:
    """Adapt a point-in-time structure snapshot without interpreting it."""

    if not isinstance(snapshot, PriceStructureSnapshot):
        raise TypeError("snapshot must be a PriceStructureSnapshot")
    return StructureFacts(
        status=snapshot.status,
        as_of=snapshot.as_of,
        current_price=snapshot.current_price,
        atr=snapshot.atr,
        confirmed_pivots=snapshot.candidates,
        available_zones=snapshot.observed_zones,
    )


def build_market_observation(
    identity: ObservationIdentity,
    provenance: ObservationProvenance,
    *,
    price_facts: PriceFacts,
    signal_snapshot: MarketSignalSnapshot,
    structure_snapshot: PriceStructureSnapshot,
) -> MarketObservation:
    """Adapt existing price, signal, and structure facts into one boundary."""

    if not isinstance(price_facts, PriceFacts):
        raise TypeError("price_facts must be a PriceFacts")
    return build_observation(
        identity,
        provenance,
        price_facts=price_facts,
        signal_facts=build_signal_facts(signal_snapshot),
        structure_facts=build_structure_facts(structure_snapshot),
    )
