"""Full immutable inputs and bounded evidence identity for structural risk."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from market_platform._fingerprint import canonical_fingerprint
from market_platform.instruments import (
    CanonicalInstrument,
    CanonicalInstrumentId,
    ExternalInstrumentIdentity,
    InstrumentDomainError,
    InstrumentMapping,
    InstrumentMappingSourceIdentity,
    InstrumentResolution,
    resolve_instrument_mapping,
)
from market_platform.risk._canonical import canonical_timestamp, timestamp_text
from market_platform.risk.errors import (
    RiskCorrespondenceError,
    RiskValidationError,
)
from market_platform.risk.policy import (
    StructuralRiskPolicy,
    require_policy_correspondence,
)
from market_platform.trading import (
    ExactTargetPositionIntentPolicy,
    OrderIntent,
    TradingInstrumentIdentity,
    TradingSignal,
    TradingSignalSourceIdentity,
    create_order_intent_from_signal,
)
from market_platform.trading_state import (
    AccountCashSnapshot,
    MarketQuoteCollectionSnapshot,
    OpenOrderExposureSnapshot,
    PositionCollectionSnapshot,
    TradingStateDomainError,
)

RISK_EVALUATION_CONTEXT_SCHEMA_VERSION = "risk_evaluation_context/v1"


class EvidenceCoverageScope(StrEnum):
    """Explicit trusted-orchestration coverage assertion."""

    UNVERIFIED = "unverified"
    COMPLETE_ACCOUNT = "complete_account"
    TARGET_INSTRUMENT = "target_instrument"


@dataclass(frozen=True, slots=True)
class RiskEvidenceCoverage:
    """Typed scope declarations without authentication claims."""

    cash: EvidenceCoverageScope
    positions: EvidenceCoverageScope
    open_orders: EvidenceCoverageScope
    quotes: EvidenceCoverageScope

    def __post_init__(self) -> None:
        for name in ("cash", "positions", "open_orders", "quotes"):
            if type(getattr(self, name)) is not EvidenceCoverageScope:
                raise RiskValidationError(
                    f"{name} coverage must be an EvidenceCoverageScope"
                )
        if self.cash is EvidenceCoverageScope.TARGET_INSTRUMENT:
            raise RiskValidationError("cash coverage cannot target an instrument")
        if self.positions is EvidenceCoverageScope.TARGET_INSTRUMENT:
            raise RiskValidationError("position coverage cannot target an instrument")
        if self.open_orders is EvidenceCoverageScope.TARGET_INSTRUMENT:
            raise RiskValidationError("open-order coverage cannot target an instrument")
        if self.quotes is EvidenceCoverageScope.COMPLETE_ACCOUNT:
            raise RiskValidationError("quote coverage cannot cover an account")

    def to_dict(self) -> dict[str, object]:
        """Return the bounded coverage assertion."""

        return {
            "cash": self.cash.value,
            "positions": self.positions.value,
            "open_orders": self.open_orders.value,
            "quotes": self.quotes.value,
        }


def require_coverage_correspondence(value: object) -> RiskEvidenceCoverage:
    if type(value) is not RiskEvidenceCoverage:
        raise RiskCorrespondenceError("coverage has invalid runtime type")
    coverage = value
    try:
        reconstructed = RiskEvidenceCoverage(
            cash=coverage.cash,
            positions=coverage.positions,
            open_orders=coverage.open_orders,
            quotes=coverage.quotes,
        )
    except (TypeError, ValueError) as error:
        raise RiskCorrespondenceError(
            "coverage retains invalid canonical state"
        ) from error
    if coverage.to_dict() != reconstructed.to_dict():
        raise RiskCorrespondenceError("coverage does not match public reconstruction")
    return coverage


@dataclass(frozen=True, slots=True)
class RiskEvaluationContext:
    """Full independently timed inputs with a bounded audit identity."""

    order_intent: OrderIntent = field(repr=False)
    instrument_resolution: InstrumentResolution = field(repr=False)
    cash_snapshot: AccountCashSnapshot = field(repr=False)
    position_snapshot: PositionCollectionSnapshot = field(repr=False)
    open_order_snapshot: OpenOrderExposureSnapshot = field(repr=False)
    quote_snapshot: MarketQuoteCollectionSnapshot = field(repr=False)
    coverage: RiskEvidenceCoverage
    policy: StructuralRiskPolicy = field(repr=False)
    evaluation_as_of: datetime
    schema_version: str = field(
        init=False, default=RISK_EVALUATION_CONTEXT_SCHEMA_VERSION
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        require_order_intent_correspondence(self.order_intent)
        require_resolution_correspondence(self.instrument_resolution)
        require_snapshot_correspondence(
            self.cash_snapshot,
            self.position_snapshot,
            self.open_order_snapshot,
            self.quote_snapshot,
        )
        require_coverage_correspondence(self.coverage)
        require_policy_correspondence(self.policy)
        evaluation_as_of = canonical_timestamp(
            self.evaluation_as_of, "evaluation_as_of"
        )
        object.__setattr__(self, "evaluation_as_of", evaluation_as_of)
        object.__setattr__(
            self, "fingerprint", canonical_fingerprint(self._fingerprint_payload())
        )

    def _fingerprint_payload(self) -> dict[str, object]:
        mapping = self.instrument_resolution.mapping
        canonical = mapping.canonical_instrument
        return {
            "schema_version": self.schema_version,
            "order_intent": {
                "fingerprint": self.order_intent.intent_fingerprint,
                "signal_fingerprint": self.order_intent.source_signal_fingerprint,
            },
            "instrument_resolution": {
                "resolved_as_of": timestamp_text(
                    self.instrument_resolution.resolved_as_of
                ),
                "mapping_fingerprint": mapping.fingerprint,
                "canonical_instrument_id": canonical.instrument_id.instrument_id,
                "canonical_instrument_fingerprint": canonical.fingerprint,
            },
            "account_evidence": {
                "cash_account_fingerprint": self.cash_snapshot.account.fingerprint,
                "position_account_fingerprint": (
                    self.position_snapshot.account.fingerprint
                ),
                "open_order_account_fingerprint": (
                    self.open_order_snapshot.account.fingerprint
                ),
            },
            "snapshots": {
                "cash_fingerprint": self.cash_snapshot.fingerprint,
                "position_fingerprint": self.position_snapshot.fingerprint,
                "open_order_fingerprint": self.open_order_snapshot.fingerprint,
                "quote_fingerprint": self.quote_snapshot.fingerprint,
            },
            "coverage": self.coverage.to_dict(),
            "policy_fingerprint": self.policy.fingerprint,
            "evaluation_as_of": timestamp_text(self.evaluation_as_of),
        }

    def _validate(self) -> None:
        if self.schema_version != RISK_EVALUATION_CONTEXT_SCHEMA_VERSION:
            raise RiskCorrespondenceError("risk context schema_version is invalid")
        reconstructed = RiskEvaluationContext(
            order_intent=self.order_intent,
            instrument_resolution=self.instrument_resolution,
            cash_snapshot=self.cash_snapshot,
            position_snapshot=self.position_snapshot,
            open_order_snapshot=self.open_order_snapshot,
            quote_snapshot=self.quote_snapshot,
            coverage=self.coverage,
            policy=self.policy,
            evaluation_as_of=self.evaluation_as_of,
        )
        if self.fingerprint != reconstructed.fingerprint or self.to_dict(
            validate=False
        ) != reconstructed.to_dict(validate=False):
            raise RiskCorrespondenceError(
                "risk context does not match public reconstruction"
            )

    def to_dict(self, *, validate: bool = True) -> dict[str, object]:
        """Return bounded fingerprint references, never full snapshot rows."""

        if validate:
            self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


def require_context_correspondence(value: object) -> RiskEvaluationContext:
    if type(value) is not RiskEvaluationContext:
        raise RiskCorrespondenceError("context has invalid runtime type")
    value._validate()
    return value


def require_order_intent_correspondence(value: object) -> OrderIntent:
    if type(value) is not OrderIntent:
        raise RiskCorrespondenceError("order intent has invalid runtime type")
    intent = value
    signal = intent.source_signal
    try:
        if type(signal) is not TradingSignal:
            raise TypeError("source signal has invalid runtime type")
        source = signal.source
        instrument = signal.instrument
        if type(source) is not TradingSignalSourceIdentity:
            raise TypeError("signal source has invalid runtime type")
        if type(instrument) is not TradingInstrumentIdentity:
            raise TypeError("trading instrument has invalid runtime type")
        reconstructed_source = TradingSignalSourceIdentity(
            source_id=source.source_id,
            source_version=source.source_version,
            configuration_fingerprint=source.configuration_fingerprint,
        )
        reconstructed_instrument = TradingInstrumentIdentity(
            symbol=instrument.symbol,
            venue=instrument.venue,
        )
        reconstructed_signal = TradingSignal(
            source=reconstructed_source,
            source_event_id=signal.source_event_id,
            instrument=reconstructed_instrument,
            timeframe=signal.timeframe,
            target_position=signal.target_position,
            target_units=signal.target_units,
            generated_at=signal.generated_at,
            valid_from=signal.valid_from,
            expires_at=signal.expires_at,
        )
        if type(intent.policy) is not ExactTargetPositionIntentPolicy:
            raise TypeError("intent policy has invalid runtime type")
        reconstructed_policy = ExactTargetPositionIntentPolicy()
        reconstructed = create_order_intent_from_signal(
            reconstructed_signal,
            reconstructed_policy,
            intent.decision_as_of,
        )
    except (TypeError, ValueError) as error:
        raise RiskCorrespondenceError(
            "order intent retains invalid released state"
        ) from error
    if (
        signal.to_dict() != reconstructed_signal.to_dict()
        or intent.policy.to_dict() != reconstructed_policy.to_dict()
        or intent.to_dict() != reconstructed.to_dict()
        or intent.schema_version != reconstructed.schema_version
        or intent.intent_fingerprint != reconstructed.intent_fingerprint
    ):
        raise RiskCorrespondenceError(
            "order intent does not match released reconstruction"
        )
    return intent


def require_resolution_correspondence(value: object) -> InstrumentResolution:
    if type(value) is not InstrumentResolution:
        raise RiskCorrespondenceError("resolution has invalid runtime type")
    resolution = value
    mapping = _required_retained_attribute(resolution, "mapping", "resolution")
    external = _required_retained_attribute(
        resolution, "external_identity", "resolution"
    )
    resolved_as_of = _required_retained_attribute(
        resolution, "resolved_as_of", "resolution"
    )
    _required_retained_attribute(resolution, "schema_version", "resolution")
    if type(mapping) is not InstrumentMapping:
        raise RiskCorrespondenceError("resolution mapping has invalid runtime type")
    if type(external) is not ExternalInstrumentIdentity:
        raise RiskCorrespondenceError(
            "resolution external identity has invalid runtime type"
        )
    mapping_external = _required_retained_attribute(
        mapping, "external_identity", "mapping"
    )
    canonical = _required_retained_attribute(
        mapping, "canonical_instrument", "mapping"
    )
    source = _required_retained_attribute(mapping, "source", "mapping")
    valid_from = _required_retained_attribute(mapping, "valid_from", "mapping")
    expires_at = _required_retained_attribute(mapping, "expires_at", "mapping")
    _required_retained_attribute(mapping, "schema_version", "mapping")
    _required_retained_attribute(mapping, "fingerprint", "mapping")
    if type(mapping_external) is not ExternalInstrumentIdentity:
        raise RiskCorrespondenceError(
            "mapping external identity has invalid runtime type"
        )
    if type(canonical) is not CanonicalInstrument:
        raise RiskCorrespondenceError(
            "mapping canonical instrument has invalid runtime type"
        )
    if type(source) is not InstrumentMappingSourceIdentity:
        raise RiskCorrespondenceError("mapping source has invalid runtime type")
    canonical_id = _required_retained_attribute(
        canonical, "instrument_id", "canonical instrument"
    )
    trading_identity = _required_retained_attribute(
        canonical, "trading_identity", "canonical instrument"
    )
    asset_class = _required_retained_attribute(
        canonical, "asset_class", "canonical instrument"
    )
    trading_currency = _required_retained_attribute(
        canonical, "trading_currency", "canonical instrument"
    )
    _required_retained_attribute(canonical, "schema_version", "canonical instrument")
    _required_retained_attribute(canonical, "fingerprint", "canonical instrument")
    if type(canonical_id) is not CanonicalInstrumentId:
        raise RiskCorrespondenceError(
            "canonical instrument ID has invalid runtime type"
        )
    if type(trading_identity) is not TradingInstrumentIdentity:
        raise RiskCorrespondenceError(
            "canonical trading identity has invalid runtime type"
        )
    external_namespace = _required_retained_attribute(
        external, "namespace", "resolution external identity"
    )
    external_symbol = _required_retained_attribute(
        external, "external_symbol", "resolution external identity"
    )
    external_venue = _required_retained_attribute(
        external, "external_venue", "resolution external identity"
    )
    _required_retained_attribute(
        external, "schema_version", "resolution external identity"
    )
    _required_retained_attribute(
        external, "fingerprint", "resolution external identity"
    )
    mapping_namespace = _required_retained_attribute(
        mapping_external, "namespace", "mapping external identity"
    )
    mapping_symbol = _required_retained_attribute(
        mapping_external, "external_symbol", "mapping external identity"
    )
    mapping_venue = _required_retained_attribute(
        mapping_external, "external_venue", "mapping external identity"
    )
    _required_retained_attribute(
        mapping_external, "schema_version", "mapping external identity"
    )
    _required_retained_attribute(
        mapping_external, "fingerprint", "mapping external identity"
    )
    instrument_id = _required_retained_attribute(
        canonical_id, "instrument_id", "canonical instrument ID"
    )
    trading_symbol = _required_retained_attribute(
        trading_identity, "symbol", "trading instrument identity"
    )
    trading_venue = _required_retained_attribute(
        trading_identity, "venue", "trading instrument identity"
    )
    _required_retained_attribute(
        trading_identity, "schema_version", "trading instrument identity"
    )
    _required_retained_attribute(
        trading_identity, "instrument_fingerprint", "trading instrument identity"
    )
    source_id = _required_retained_attribute(source, "source_id", "mapping source")
    source_version = _required_retained_attribute(
        source, "source_version", "mapping source"
    )
    configuration_fingerprint = _required_retained_attribute(
        source, "configuration_fingerprint", "mapping source"
    )
    _required_retained_attribute(source, "schema_version", "mapping source")
    _required_retained_attribute(source, "fingerprint", "mapping source")
    try:
        reconstructed_external = ExternalInstrumentIdentity(
            namespace=external_namespace,
            external_symbol=external_symbol,
            external_venue=external_venue,
        )
        reconstructed_mapping_external = ExternalInstrumentIdentity(
            namespace=mapping_namespace,
            external_symbol=mapping_symbol,
            external_venue=mapping_venue,
        )
        reconstructed_canonical = CanonicalInstrument(
            instrument_id=CanonicalInstrumentId(instrument_id),
            trading_identity=TradingInstrumentIdentity(
                symbol=trading_symbol,
                venue=trading_venue,
            ),
            asset_class=asset_class,
            trading_currency=trading_currency,
        )
        reconstructed_source = InstrumentMappingSourceIdentity(
            source_id=source_id,
            source_version=source_version,
            configuration_fingerprint=configuration_fingerprint,
        )
        reconstructed_mapping = InstrumentMapping(
            external_identity=reconstructed_mapping_external,
            canonical_instrument=reconstructed_canonical,
            source=reconstructed_source,
            valid_from=valid_from,
            expires_at=expires_at,
        )
        reconstructed = resolve_instrument_mapping(
            reconstructed_external,
            [reconstructed_mapping],
            resolved_as_of,
        )
    except (TypeError, ValueError, InstrumentDomainError) as error:
        raise RiskCorrespondenceError(
            "resolution retains invalid released state"
        ) from error
    pairs = (
        (external, reconstructed_external),
        (mapping_external, reconstructed_mapping_external),
        (canonical, reconstructed_canonical),
        (source, reconstructed_source),
        (mapping, reconstructed_mapping),
        (resolution, reconstructed),
    )
    if any(actual.to_dict() != expected.to_dict() for actual, expected in pairs):
        raise RiskCorrespondenceError(
            "resolution does not match released reconstruction"
        )
    return resolution


def _required_retained_attribute(
    value: object,
    attribute_name: str,
    subject: str,
) -> Any:
    try:
        return object.__getattribute__(value, attribute_name)
    except AttributeError as error:
        raise RiskCorrespondenceError(
            f"{subject} is missing required retained state"
        ) from error


def require_snapshot_correspondence(
    cash: object,
    positions: object,
    open_orders: object,
    quotes: object,
) -> None:
    if type(cash) is not AccountCashSnapshot:
        raise RiskCorrespondenceError("cash snapshot has invalid runtime type")
    if type(positions) is not PositionCollectionSnapshot:
        raise RiskCorrespondenceError("position snapshot has invalid runtime type")
    if type(open_orders) is not OpenOrderExposureSnapshot:
        raise RiskCorrespondenceError("open-order snapshot has invalid runtime type")
    if type(quotes) is not MarketQuoteCollectionSnapshot:
        raise RiskCorrespondenceError("quote snapshot has invalid runtime type")
    try:
        reconstructed_cash = AccountCashSnapshot(
            account=cash.account,
            source=cash.source,
            as_of=cash.as_of,
            balances=list(cash.balances),
        )
        reconstructed_positions = PositionCollectionSnapshot(
            account=positions.account,
            source=positions.source,
            as_of=positions.as_of,
            positions=list(positions.positions),
        )
        reconstructed_orders = OpenOrderExposureSnapshot(
            account=open_orders.account,
            source=open_orders.source,
            as_of=open_orders.as_of,
            exposures=list(open_orders.exposures),
        )
        reconstructed_quotes = MarketQuoteCollectionSnapshot(
            source=quotes.source,
            as_of=quotes.as_of,
            quotes=list(quotes.quotes),
        )
    except (TypeError, ValueError, TradingStateDomainError) as error:
        raise RiskCorrespondenceError(
            "snapshot retains invalid released state"
        ) from error
    pairs = (
        (cash, reconstructed_cash),
        (positions, reconstructed_positions),
        (open_orders, reconstructed_orders),
        (quotes, reconstructed_quotes),
    )
    try:
        projections_match = all(
            actual.to_dict() == expected.to_dict() for actual, expected in pairs
        )
    except TradingStateDomainError as error:
        raise RiskCorrespondenceError(
            "snapshot retains invalid released state"
        ) from error
    if not projections_match:
        raise RiskCorrespondenceError(
            "snapshot does not match released reconstruction"
        )


__all__ = [
    "RISK_EVALUATION_CONTEXT_SCHEMA_VERSION",
    "EvidenceCoverageScope",
    "RiskEvaluationContext",
    "RiskEvidenceCoverage",
]
