"""Pure validation for strategy evaluation inputs."""

from __future__ import annotations

from market_platform.observation.models import MarketObservation
from market_platform.state.models import MarketState


def validate_strategy_inputs(
    state: MarketState,
    observation: MarketObservation,
) -> None:
    """Require an exact shared point-in-time identity and compatible provenance."""

    if not isinstance(state, MarketState):
        raise TypeError("state must be a MarketState")
    if not isinstance(observation, MarketObservation):
        raise TypeError("observation must be a MarketObservation")
    identity = observation.identity
    if state.symbol != identity.symbol:
        raise ValueError("state and observation symbols must match")
    if state.interval != identity.interval:
        raise ValueError("state and observation intervals must match")
    if state.as_of != identity.as_of:
        raise ValueError("state and observation as_of values must match")

    state_fingerprint = state.provenance.observation_fingerprint
    observation_fingerprint = observation.provenance.input_fingerprint
    if (
        state_fingerprint is not None
        and observation_fingerprint is not None
        and state_fingerprint != observation_fingerprint
    ):
        raise ValueError("state and observation fingerprints must match")
