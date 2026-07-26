from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

import market_platform.replay.service as replay_service
from market_platform.replay import (
    HistoricalReplayService,
    HistoricalReplaySpecification,
    ReplaySignalDerivationIdentity,
    ReplayStrategyIdentity,
    ReplayStructureDerivationIdentity,
    SoftwareRevision,
    default_replay_signal_derivation_identity,
    default_replay_structure_derivation_identity,
)
from market_platform.state import BaselineMarketStateModel
from market_platform.strategy import (
    BaselineTrendRegimeStrategy,
    BaselineVolatilityRegimeStrategy,
    create_strategy_collection,
)
from market_platform.structure import PriceStructureService

_START = datetime(2026, 1, 1, tzinfo=UTC)
_SOFTWARE = SoftwareRevision("e014a5c", dirty=False)


def _prices(count: int = 60, *, provider: str = "test-provider") -> pd.DataFrame:
    closes = [100.0 + index * 0.5 for index in range(count)]
    return pd.DataFrame(
        {
            "symbol": ["MSFT"] * count,
            "timestamp": [_START + timedelta(days=index) for index in range(count)],
            "open": closes,
            "high": [close + 1.0 for close in closes],
            "low": [close - 1.0 for close in closes],
            "close": closes,
            "volume": [1_000_000.0] * count,
            "provider": [provider] * count,
        }
    )


def _specification(
    *,
    context_start: datetime = _START,
    evaluation_start: datetime = _START + timedelta(days=50),
    evaluation_end: datetime = _START + timedelta(days=52),
    interval: str = "1day",
) -> HistoricalReplaySpecification:
    return HistoricalReplaySpecification(
        symbol="MSFT",
        interval=interval,
        context_start=context_start,
        evaluation_start=evaluation_start,
        evaluation_end=evaluation_end,
    )


def _run_execution(
    prices: pd.DataFrame | None = None,
    specification: HistoricalReplaySpecification | None = None,
    *,
    service: HistoricalReplayService | None = None,
    software_revision: SoftwareRevision = _SOFTWARE,
    structure_derivation: ReplayStructureDerivationIdentity | None = None,
    state_model_configuration_fingerprint: str | None = None,
    reverse_strategies: bool = False,
):
    strategies = [BaselineTrendRegimeStrategy(), BaselineVolatilityRegimeStrategy()]
    if reverse_strategies:
        strategies.reverse()
    return (service or HistoricalReplayService()).run_execution(
        _prices() if prices is None else prices,
        _specification() if specification is None else specification,
        strategies=create_strategy_collection(strategies),
        state_model=BaselineMarketStateModel(),
        software_revision=software_revision,
        structure_derivation=structure_derivation,
        state_model_configuration_fingerprint=(
            state_model_configuration_fingerprint
        ),
    )


def test_derivation_and_software_identities_are_stable_and_immutable() -> None:
    signal = default_replay_signal_derivation_identity()
    structure = default_replay_structure_derivation_identity()

    assert signal == default_replay_signal_derivation_identity()
    assert structure == default_replay_structure_derivation_identity()
    assert signal.configuration_fingerprint.startswith("sha256:")
    assert structure.configuration_fingerprint.startswith("sha256:")
    assert _SOFTWARE.to_dict() == {"revision": "e014a5c", "dirty": False}
    with pytest.raises(FrozenInstanceError):
        _SOFTWARE.dirty = True  # type: ignore[misc]


def test_identity_values_reject_invalid_fields() -> None:
    with pytest.raises(ValueError, match="methodology"):
        ReplaySignalDerivationIdentity(" ", "1", "sha256:" + "0" * 64)
    with pytest.raises(ValueError, match="sha256"):
        ReplayStructureDerivationIdentity("method", "1", "not-a-fingerprint")
    with pytest.raises(TypeError, match="bool"):
        SoftwareRevision("revision", 1)  # type: ignore[arg-type]


def test_run_execution_matches_existing_result_and_records_actual_facts() -> None:
    prices = _prices()
    specification = _specification()
    service = HistoricalReplayService()
    execution = _run_execution(prices, specification, service=service)
    legacy_result = service.run_with_specification(
        prices,
        specification,
        strategies=create_strategy_collection(
            [BaselineTrendRegimeStrategy(), BaselineVolatilityRegimeStrategy()]
        ),
        state_model=BaselineMarketStateModel(),
    )

    assert execution.result.to_dict() == legacy_result.to_dict()
    assert execution.run_fingerprint == execution.provenance.run_fingerprint
    assert execution.provenance.specification == specification
    assert execution.provenance.provider == "test-provider"
    assert execution.provenance.context_start == _START
    assert execution.provenance.context_end == _START + timedelta(days=52)
    assert execution.provenance.context_row_count == 53
    assert execution.provenance.evaluation_start == _START + timedelta(days=50)
    assert execution.provenance.evaluation_end == _START + timedelta(days=52)
    assert execution.provenance.evaluation_step_count == 3
    assert "result" not in execution.provenance.to_dict()


def test_run_fingerprint_is_repeatable_and_separates_provider_from_content() -> None:
    first = _run_execution()
    repeated = _run_execution()
    other_provider = _run_execution(_prices(provider="other-provider"))

    assert repeated.run_fingerprint == first.run_fingerprint
    assert (
        other_provider.provenance.dataset_content_fingerprint
        == first.provenance.dataset_content_fingerprint
    )
    assert other_provider.run_fingerprint != first.run_fingerprint


def test_signed_zero_volume_produces_equivalent_run_identity() -> None:
    fingerprints: set[str] = set()
    for value in (0, 0.0, -0.0):
        prices = _prices()
        prices.loc[25, "volume"] = value
        fingerprints.add(_run_execution(prices).run_fingerprint)

    changed = _prices()
    changed.loc[25, "volume"] = 1.0

    assert len(fingerprints) == 1
    assert _run_execution(changed).run_fingerprint not in fingerprints


def test_run_execution_constructs_one_canonical_series(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = replay_service._build_historical_price_series
    call_count = 0

    def counted(prices: pd.DataFrame, symbol: str):
        nonlocal call_count
        call_count += 1
        return original(prices, symbol)

    monkeypatch.setattr(
        replay_service,
        "_build_historical_price_series",
        counted,
    )

    _run_execution()

    assert call_count == 1


def test_only_retained_context_changes_dataset_and_run_identity() -> None:
    baseline = _run_execution()
    outside = _prices(70)
    outside.loc[60:, "close"] = 5_000.0
    outside.loc[60:, "high"] = 5_001.0
    before = pd.concat(
        [
            _prices(1).assign(timestamp=_START - timedelta(days=1)),
            outside,
        ],
        ignore_index=True,
    )
    retained_change = _prices()
    retained_change.loc[25, "close"] += 0.25

    outside_execution = _run_execution(before)
    changed_execution = _run_execution(retained_change)

    assert (
        outside_execution.provenance.dataset_content_fingerprint
        == baseline.provenance.dataset_content_fingerprint
    )
    assert outside_execution.run_fingerprint == baseline.run_fingerprint
    assert (
        changed_execution.provenance.dataset_content_fingerprint
        != baseline.provenance.dataset_content_fingerprint
    )
    assert changed_execution.run_fingerprint != baseline.run_fingerprint


def test_declared_component_identities_change_run_fingerprint() -> None:
    baseline = _run_execution()
    changed_signal = ReplaySignalDerivationIdentity(
        methodology="changed-signals",
        version="1.0.0",
        configuration_fingerprint=(
            baseline.provenance.signal_derivation.configuration_fingerprint
        ),
    )
    changed_structure = ReplayStructureDerivationIdentity(
        methodology="changed-structure",
        version="1.0.0",
        configuration_fingerprint=(
            baseline.provenance.structure_derivation.configuration_fingerprint
        ),
    )

    assert replace(
        baseline.provenance,
        signal_derivation=changed_signal,
    ).run_fingerprint != baseline.run_fingerprint
    changed_signal_configuration = replace(
        baseline.provenance.signal_derivation,
        configuration_fingerprint=baseline.provenance.specification_fingerprint,
    )
    assert replace(
        baseline.provenance,
        signal_derivation=changed_signal_configuration,
    ).run_fingerprint != baseline.run_fingerprint
    assert replace(
        baseline.provenance,
        structure_derivation=changed_structure,
    ).run_fingerprint != baseline.run_fingerprint
    assert replace(
        baseline.provenance,
        state_model_version="2.0.0",
    ).run_fingerprint != baseline.run_fingerprint
    assert replace(
        baseline.provenance,
        state_model_id="different-state-model",
    ).run_fingerprint != baseline.run_fingerprint
    assert replace(
        baseline.provenance,
        state_model_configuration_fingerprint=(
            baseline.provenance.specification_fingerprint
        ),
    ).run_fingerprint != baseline.run_fingerprint
    assert replace(
        baseline.provenance,
        software_revision=SoftwareRevision("different", False),
    ).run_fingerprint != baseline.run_fingerprint
    assert replace(
        baseline.provenance,
        software_revision=SoftwareRevision("e014a5c", True),
    ).run_fingerprint != baseline.run_fingerprint


def test_specification_and_strategy_order_change_run_fingerprint() -> None:
    baseline = _run_execution()
    narrower_context = _run_execution(
        specification=_specification(context_start=_START + timedelta(days=1))
    )
    reversed_strategies = _run_execution(reverse_strategies=True)

    assert narrower_context.run_fingerprint != baseline.run_fingerprint
    assert reversed_strategies.run_fingerprint != baseline.run_fingerprint
    assert (
        tuple(item.strategy_id for item in reversed_strategies.provenance.strategies)
        == tuple(
            reversed(
                tuple(
                    item.strategy_id
                    for item in baseline.provenance.strategies
                )
            )
        )
    )


@pytest.mark.parametrize(
    "specification",
    [
        _specification(evaluation_start=_START + timedelta(days=51)),
        _specification(evaluation_end=_START + timedelta(days=51)),
        _specification(interval="daily"),
    ],
)
def test_evaluation_intent_changes_run_fingerprint(
    specification: HistoricalReplaySpecification,
) -> None:
    assert _run_execution(specification=specification).run_fingerprint != (
        _run_execution().run_fingerprint
    )


@pytest.mark.parametrize(
    "identity",
    [
        ReplayStrategyIdentity("different", "1.0.0", None),
        ReplayStrategyIdentity("baseline_trend_regime", "2.0.0", None),
        ReplayStrategyIdentity(
            "baseline_trend_regime",
            "1.0.0",
            "sha256:" + "0" * 64,
        ),
    ],
)
def test_strategy_identity_fields_change_run_fingerprint(
    identity: ReplayStrategyIdentity,
) -> None:
    baseline = _run_execution().provenance
    changed = replace(
        baseline,
        strategies=(identity, *baseline.strategies[1:]),
    )

    assert changed.run_fingerprint != baseline.run_fingerprint


def test_zero_and_duplicate_strategy_identities_are_ordered_and_deterministic() -> None:
    baseline = _run_execution().provenance
    empty = replace(baseline, strategies=())
    duplicate = replace(
        baseline,
        strategies=(baseline.strategies[0], baseline.strategies[0]),
    )

    assert empty.to_dict()["strategies"] == []
    assert replace(empty).run_fingerprint == empty.run_fingerprint
    assert replace(duplicate).run_fingerprint == duplicate.run_fingerprint


class _CustomStructureService:
    def __init__(self) -> None:
        self._delegate = PriceStructureService()

    def _uses_default_components(self) -> bool:
        return False

    def analyze(self, prices: pd.DataFrame, *, as_of: datetime):
        return self._delegate.analyze(prices, as_of=as_of)


def test_custom_structure_requires_identity_only_for_provenance_execution() -> None:
    custom = _CustomStructureService()
    service = HistoricalReplayService(
        price_structure_service=custom,  # type: ignore[arg-type]
    )
    specification = _specification()
    strategies = create_strategy_collection([BaselineTrendRegimeStrategy()])

    legacy = service.run_with_specification(
        _prices(),
        specification,
        strategies=strategies,
        state_model=BaselineMarketStateModel(),
    )
    with pytest.raises(ValueError, match="structure_derivation is required"):
        service.run_execution(
            _prices(),
            specification,
            strategies=strategies,
            state_model=BaselineMarketStateModel(),
            software_revision=_SOFTWARE,
        )

    identity = ReplayStructureDerivationIdentity(
        methodology="test-custom-structure",
        version="1.0.0",
        configuration_fingerprint=(
            default_replay_structure_derivation_identity().configuration_fingerprint
        ),
    )
    execution = service.run_execution(
        _prices(),
        specification,
        strategies=strategies,
        state_model=BaselineMarketStateModel(),
        software_revision=_SOFTWARE,
        structure_derivation=identity,
    )

    assert execution.result.to_dict() == legacy.to_dict()
    assert execution.provenance.structure_derivation == identity
