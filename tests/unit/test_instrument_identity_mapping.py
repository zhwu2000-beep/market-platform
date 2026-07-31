"""Focused tests for stable instrument identity and temporal mapping."""

from __future__ import annotations

import json
from collections import OrderedDict, deque
from collections.abc import Sequence
from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta, timezone, tzinfo

import pytest

from market_platform._fingerprint import canonical_fingerprint
from market_platform.instruments import (
    CANONICAL_INSTRUMENT_SCHEMA_VERSION,
    EXTERNAL_INSTRUMENT_IDENTITY_SCHEMA_VERSION,
    INSTRUMENT_MAPPING_SCHEMA_VERSION,
    INSTRUMENT_MAPPING_SOURCE_SCHEMA_VERSION,
    INSTRUMENT_RESOLUTION_SCHEMA_VERSION,
    CanonicalInstrument,
    CanonicalInstrumentId,
    ExternalInstrumentIdentity,
    InstrumentAssetClass,
    InstrumentMapping,
    InstrumentMappingAmbiguousError,
    InstrumentMappingConflictError,
    InstrumentMappingDuplicateError,
    InstrumentMappingInactiveError,
    InstrumentMappingNotFoundError,
    InstrumentMappingSourceIdentity,
    InstrumentResolution,
    InstrumentResolutionCorrespondenceError,
    InstrumentValidationError,
    resolve_instrument_mapping,
)
from market_platform.trading import (
    TRADING_INSTRUMENT_IDENTITY_SCHEMA_VERSION,
    TradingInstrumentIdentity,
)

_START = datetime(2026, 7, 30, 0, 0, tzinfo=UTC)
_END = _START + timedelta(days=30)
_CONFIGURATION_FINGERPRINT = "sha256:" + ("1" * 64)


def _external(
    *,
    namespace: str = "tradingview",
    symbol: str = "NASDAQ:AAPL",
    venue: str | None = None,
) -> ExternalInstrumentIdentity:
    return ExternalInstrumentIdentity(
        namespace=namespace,
        external_symbol=symbol,
        external_venue=venue,
    )


def _canonical(
    *,
    instrument_id: str = "us_equity_apple",
    symbol: str = "AAPL",
    venue: str = "NASDAQ",
    asset_class: InstrumentAssetClass = InstrumentAssetClass.EQUITY,
    currency: str = "USD",
) -> CanonicalInstrument:
    return CanonicalInstrument(
        instrument_id=CanonicalInstrumentId(instrument_id),
        trading_identity=TradingInstrumentIdentity(symbol=symbol, venue=venue),
        asset_class=asset_class,
        trading_currency=currency,
    )


def _source(
    *,
    source_id: str = "internal.instrument_registry",
    version: str = "1",
    configuration: str | None = _CONFIGURATION_FINGERPRINT,
) -> InstrumentMappingSourceIdentity:
    return InstrumentMappingSourceIdentity(
        source_id=source_id,
        source_version=version,
        configuration_fingerprint=configuration,
    )


def _mapping(
    *,
    external: ExternalInstrumentIdentity | None = None,
    canonical: CanonicalInstrument | None = None,
    source: InstrumentMappingSourceIdentity | None = None,
    valid_from: datetime = _START,
    expires_at: datetime | None = _END,
) -> InstrumentMapping:
    return InstrumentMapping(
        external_identity=external or _external(),
        canonical_instrument=canonical or _canonical(),
        source=source or _source(),
        valid_from=valid_from,
        expires_at=expires_at,
    )


def _assert_json_safe(value: object) -> None:
    encoded = json.dumps(value, allow_nan=False, sort_keys=True)
    assert json.loads(encoded) == value


def _fabricated_trading_identity(
    *,
    symbol: str = "AAPL",
    venue: str = "NASDAQ",
    schema_version: str = TRADING_INSTRUMENT_IDENTITY_SCHEMA_VERSION,
) -> TradingInstrumentIdentity:
    identity = TradingInstrumentIdentity("AAPL", "NASDAQ")
    object.__setattr__(identity, "symbol", symbol)
    object.__setattr__(identity, "venue", venue)
    object.__setattr__(identity, "schema_version", schema_version)
    object.__setattr__(
        identity,
        "instrument_fingerprint",
        canonical_fingerprint(
            {
                "schema_version": schema_version,
                "symbol": symbol,
                "venue": venue,
            }
        ),
    )
    return identity


def test_public_schema_families_are_exact() -> None:
    assert CANONICAL_INSTRUMENT_SCHEMA_VERSION == "canonical_instrument/v1"
    assert (
        EXTERNAL_INSTRUMENT_IDENTITY_SCHEMA_VERSION
        == "external_instrument_identity/v1"
    )
    assert (
        INSTRUMENT_MAPPING_SOURCE_SCHEMA_VERSION
        == "instrument_mapping_source/v1"
    )
    assert INSTRUMENT_MAPPING_SCHEMA_VERSION == "instrument_mapping/v1"
    assert INSTRUMENT_RESOLUTION_SCHEMA_VERSION == "instrument_resolution/v1"


@pytest.mark.parametrize(
    "value",
    [
        "A",
        "AAPL",
        "instrument-0001",
        "us_equity_apple",
        "security.master.001",
        "A" * 128,
    ],
)
def test_canonical_instrument_id_accepts_exact_grammar(value: str) -> None:
    identity = CanonicalInstrumentId(value)
    assert identity.instrument_id == value
    assert identity.to_dict() == {"instrument_id": value}
    assert hash(identity) == hash(CanonicalInstrumentId(value))


@pytest.mark.parametrize(
    "value",
    [
        "",
        "A" * 129,
        " AAPL",
        "AAPL ",
        "AA PL",
        "/AAPL",
        "NASDAQ:AAPL",
        "AAPL/US",
        "AAPL\n",
        "AAPL\x00",
        "AAPL\x7f",
        "\uff21\uff21\uff30\uff2c",
        "A\u200bAPL",
    ],
)
def test_canonical_instrument_id_rejects_invalid_syntax(value: str) -> None:
    with pytest.raises(InstrumentValidationError):
        CanonicalInstrumentId(value)


def test_canonical_instrument_id_requires_actual_string_and_preserves_case() -> None:
    with pytest.raises(TypeError):
        CanonicalInstrumentId(1)  # type: ignore[arg-type]
    assert CanonicalInstrumentId("Aapl") != CanonicalInstrumentId("AAPL")


def test_asset_class_is_deliberately_narrow() -> None:
    assert tuple(InstrumentAssetClass) == (
        InstrumentAssetClass.EQUITY,
        InstrumentAssetClass.ETF,
    )
    with pytest.raises(ValueError):
        InstrumentAssetClass("future")


@pytest.mark.parametrize("currency", ["USD", "EUR", "HKD"])
def test_canonical_instrument_accepts_exact_currency(currency: str) -> None:
    assert _canonical(currency=currency).trading_currency == currency


@pytest.mark.parametrize("currency", ["usd", "US", "USDD", "U1D", "\uff35\uff33\uff24"])
def test_canonical_instrument_rejects_invalid_currency(currency: str) -> None:
    with pytest.raises(InstrumentValidationError):
        _canonical(currency=currency)


def test_canonical_instrument_retains_released_identity_exactly() -> None:
    released = TradingInstrumentIdentity(symbol="aapl", venue="nasdaq")
    canonical = CanonicalInstrument(
        instrument_id=CanonicalInstrumentId("apple"),
        trading_identity=released,
        asset_class=InstrumentAssetClass.EQUITY,
        trading_currency="USD",
    )
    assert canonical.trading_identity is released
    assert canonical.trading_identity.schema_version == (
        TRADING_INSTRUMENT_IDENTITY_SCHEMA_VERSION
    )
    assert canonical.to_dict()["trading_identity"] == released.to_dict()


def test_descriptor_changes_preserve_stable_id_and_change_fingerprint() -> None:
    old = _canonical(symbol="FB", instrument_id="meta")
    renamed = _canonical(symbol="META", instrument_id="meta")
    moved = _canonical(symbol="META", venue="NYSE", instrument_id="meta")
    assert old.instrument_id == renamed.instrument_id == moved.instrument_id
    assert len({old.fingerprint, renamed.fingerprint, moved.fingerprint}) == 3


def test_canonical_instrument_fingerprint_is_deterministic_and_complete() -> None:
    baseline = _canonical()
    assert baseline == _canonical()
    changes = (
        _canonical(instrument_id="other"),
        _canonical(symbol="MSFT"),
        _canonical(venue="NYSE"),
        _canonical(asset_class=InstrumentAssetClass.ETF),
        _canonical(currency="EUR"),
    )
    assert all(item.fingerprint != baseline.fingerprint for item in changes)
    assert baseline.fingerprint.startswith("sha256:")
    _assert_json_safe(baseline.to_dict())


def test_canonical_instrument_rejects_fabricated_released_fingerprint() -> None:
    released = TradingInstrumentIdentity("AAPL", "NASDAQ")
    object.__setattr__(released, "instrument_fingerprint", "sha256:" + ("0" * 64))
    with pytest.raises(InstrumentValidationError, match="trading identity"):
        CanonicalInstrument(
            instrument_id=CanonicalInstrumentId("apple"),
            trading_identity=released,
            asset_class=InstrumentAssetClass.EQUITY,
            trading_currency="USD",
        )


@pytest.mark.parametrize(
    ("symbol", "venue"),
    [
        ("aapl", "NASDAQ"),
        ("AAPL", "nasdaq"),
        ("aapl", "nasdaq"),
        ("NASDAQ:AAPL", "NASDAQ"),
        (" AAPL", "NASDAQ"),
        ("AAPL ", "NASDAQ"),
        ("AA PL", "NASDAQ"),
        ("AAPL", " NASDAQ"),
        ("AAPL", "NASDAQ "),
        ("AAPL", "NAS DAQ"),
        ("", "NASDAQ"),
        ("AAPL", ""),
    ],
)
def test_canonical_instrument_rejects_self_consistent_noncanonical_released_state(
    symbol: str,
    venue: str,
) -> None:
    released = _fabricated_trading_identity(symbol=symbol, venue=venue)
    with pytest.raises(InstrumentValidationError, match="trading identity"):
        CanonicalInstrument(
            instrument_id=CanonicalInstrumentId("apple"),
            trading_identity=released,
            asset_class=InstrumentAssetClass.EQUITY,
            trading_currency="USD",
        )


def test_canonical_instrument_rejects_fabricated_released_schema() -> None:
    released = _fabricated_trading_identity(
        schema_version="trading_instrument_identity/v2"
    )
    with pytest.raises(InstrumentValidationError, match="trading identity"):
        CanonicalInstrument(
            instrument_id=CanonicalInstrumentId("apple"),
            trading_identity=released,
            asset_class=InstrumentAssetClass.EQUITY,
            trading_currency="USD",
        )


def test_nested_models_reject_self_consistent_noncanonical_released_state() -> None:
    mapping = _mapping()
    released = mapping.canonical_instrument.trading_identity
    object.__setattr__(released, "symbol", "aapl")
    object.__setattr__(
        released,
        "instrument_fingerprint",
        canonical_fingerprint(
            {
                "schema_version": released.schema_version,
                "symbol": released.symbol,
                "venue": released.venue,
            }
        ),
    )
    with pytest.raises(InstrumentValidationError, match="trading identity"):
        mapping._validate()
    with pytest.raises(InstrumentResolutionCorrespondenceError):
        InstrumentResolution._create(
            external_identity=mapping.external_identity,
            mapping=mapping,
            resolved_as_of=_START,
        )


def test_canonical_instrument_rejects_fabricated_stable_id() -> None:
    instrument_id = CanonicalInstrumentId("apple")
    object.__setattr__(instrument_id, "instrument_id", "NASDAQ:AAPL")
    with pytest.raises(InstrumentValidationError, match="instrument_id"):
        CanonicalInstrument(
            instrument_id=instrument_id,
            trading_identity=TradingInstrumentIdentity("AAPL", "NASDAQ"),
            asset_class=InstrumentAssetClass.EQUITY,
            trading_currency="USD",
        )


@pytest.mark.parametrize(
    "namespace",
    ["a", "tradingview", "twelve_data", "internal.test", "a" * 64],
)
def test_external_namespace_accepts_exact_grammar(namespace: str) -> None:
    assert _external(namespace=namespace).namespace == namespace


@pytest.mark.parametrize(
    "namespace",
    ["", "A", "TradingView", "a" * 65, "1vendor", "vendor/name", "vendor:name"],
)
def test_external_namespace_rejects_invalid_grammar(namespace: str) -> None:
    with pytest.raises(InstrumentValidationError):
        _external(namespace=namespace)


def test_external_symbol_and_venue_are_exact_and_case_sensitive() -> None:
    upper = _external(symbol="NASDAQ:AAPL", venue="XNAS")
    lower = _external(symbol="nasdaq:aapl", venue="xnas")
    assert upper.external_symbol == "NASDAQ:AAPL"
    assert upper.external_venue == "XNAS"
    assert upper != lower
    assert upper.fingerprint != lower.fingerprint


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("symbol", ""),
        ("symbol", "A" * 129),
        ("symbol", "AA PL"),
        ("symbol", "AAPL\n"),
        ("symbol", "\uff21\uff21\uff30\uff2c"),
        ("venue", ""),
        ("venue", "X" * 65),
        ("venue", "XN AS"),
        ("venue", "\uff38\uff2e\uff21\uff33"),
    ],
)
def test_external_fields_reject_unbounded_or_non_ascii_values(
    field_name: str,
    value: str,
) -> None:
    kwargs = {"symbol": value} if field_name == "symbol" else {"venue": value}
    with pytest.raises(InstrumentValidationError):
        _external(**kwargs)


def test_external_identity_fingerprint_is_deterministic_and_complete() -> None:
    baseline = _external()
    assert baseline == _external()
    assert _external(namespace="polygon").fingerprint != baseline.fingerprint
    assert _external(symbol="NYSE:AAPL").fingerprint != baseline.fingerprint
    assert _external(venue="XNAS").fingerprint != baseline.fingerprint
    assert baseline.to_dict()["external_venue"] is None
    _assert_json_safe(baseline.to_dict())


@pytest.mark.parametrize(
    ("source_id", "version"),
    [("a", "1"), ("A" * 128, "V" * 64), ("internal/source", "v1:exact")],
)
def test_mapping_source_accepts_bounded_visible_ascii(
    source_id: str,
    version: str,
) -> None:
    source = _source(source_id=source_id, version=version)
    assert source.source_id == source_id
    assert source.source_version == version


@pytest.mark.parametrize(
    ("source_id", "version"),
    [
        ("", "1"),
        ("A" * 129, "1"),
        ("source id", "1"),
        ("source", ""),
        ("source", "V" * 65),
        ("source", "v 1"),
        ("\u6e90", "1"),
    ],
)
def test_mapping_source_rejects_invalid_strings(
    source_id: str,
    version: str,
) -> None:
    with pytest.raises(InstrumentValidationError):
        _source(source_id=source_id, version=version)


def test_mapping_source_configuration_fingerprint_is_exact() -> None:
    assert _source(configuration=None).configuration_fingerprint is None
    assert _source().configuration_fingerprint == _CONFIGURATION_FINGERPRINT
    for malformed in (
        "sha1:" + ("1" * 40),
        "sha256:" + ("A" * 64),
        "sha256:" + ("1" * 63),
        " sha256:" + ("1" * 64),
    ):
        with pytest.raises(InstrumentValidationError):
            _source(configuration=malformed)


def test_mapping_source_fingerprint_covers_all_fields() -> None:
    baseline = _source()
    assert baseline == _source()
    assert _source(source_id="other").fingerprint != baseline.fingerprint
    assert _source(version="2").fingerprint != baseline.fingerprint
    assert _source(configuration=None).fingerprint != baseline.fingerprint
    _assert_json_safe(baseline.to_dict())


class _UndefinedOffset(tzinfo):
    def utcoffset(self, dt: datetime | None) -> None:
        del dt
        return None

    def dst(self, dt: datetime | None) -> None:
        del dt
        return None


@pytest.mark.parametrize(
    "value",
    [
        datetime(2026, 7, 30),
        datetime(2026, 7, 30, tzinfo=_UndefinedOffset()),
    ],
)
def test_mapping_rejects_naive_or_undefined_offset_time(value: datetime) -> None:
    with pytest.raises(InstrumentValidationError):
        _mapping(valid_from=value)


def test_mapping_physically_stores_canonical_utc() -> None:
    offset = timezone(timedelta(hours=8))
    mapping = _mapping(
        valid_from=datetime(2026, 7, 30, 8, tzinfo=offset),
        expires_at=datetime(2026, 8, 29, 8, tzinfo=offset),
    )
    assert mapping.valid_from == _START
    assert mapping.expires_at == _END
    assert mapping.valid_from.tzinfo is UTC
    assert mapping.expires_at is not None and mapping.expires_at.tzinfo is UTC


def test_mapping_supports_open_ended_half_open_validity() -> None:
    mapping = _mapping(expires_at=None)
    assert not mapping.is_active(_START - timedelta(microseconds=1))
    assert mapping.is_active(_START)
    assert mapping.is_active(_START + timedelta(days=100_000))
    assert mapping.to_dict()["expires_at"] is None


def test_mapping_half_open_boundaries_are_exact() -> None:
    mapping = _mapping()
    assert not mapping.is_active(_START - timedelta(microseconds=1))
    assert mapping.is_active(_START)
    assert mapping.is_active(_END - timedelta(microseconds=1))
    assert not mapping.is_active(_END)
    assert not mapping.is_active(_END + timedelta(microseconds=1))


@pytest.mark.parametrize(
    ("valid_from", "expires_at"),
    [(_START, _START), (_START, _START - timedelta(microseconds=1))],
)
def test_mapping_rejects_empty_or_reversed_window(
    valid_from: datetime,
    expires_at: datetime,
) -> None:
    with pytest.raises(InstrumentValidationError, match="later"):
        _mapping(valid_from=valid_from, expires_at=expires_at)


def test_mapping_fingerprint_covers_complete_content() -> None:
    baseline = _mapping()
    changes = (
        _mapping(external=_external(symbol="NYSE:AAPL")),
        _mapping(canonical=_canonical(symbol="MSFT")),
        _mapping(source=_source(version="2")),
        _mapping(valid_from=_START + timedelta(seconds=1)),
        _mapping(expires_at=None),
    )
    assert baseline == _mapping()
    assert all(item.fingerprint != baseline.fingerprint for item in changes)
    _assert_json_safe(baseline.to_dict())


def test_mapping_fingerprint_cannot_be_supplied_or_fabricated() -> None:
    assert "fingerprint" not in {
        item.name for item in fields(InstrumentMapping) if item.init
    }
    mapping = _mapping()
    object.__setattr__(mapping, "fingerprint", "sha256:" + ("0" * 64))
    with pytest.raises(InstrumentValidationError, match="fingerprint"):
        mapping._validate()
    with pytest.raises(InstrumentValidationError, match="fingerprint"):
        mapping.is_active(_START)


def test_resolver_returns_exact_active_mapping_and_canonical_utc() -> None:
    mapping = _mapping()
    as_of = datetime(2026, 7, 31, 8, tzinfo=timezone(timedelta(hours=8)))
    resolution = resolve_instrument_mapping(
        mapping.external_identity,
        (mapping,),
        as_of,
    )
    assert resolution.mapping is mapping
    assert resolution.external_identity is mapping.external_identity
    assert resolution.resolved_as_of == datetime(2026, 7, 31, tzinfo=UTC)
    assert resolution.resolved_as_of.tzinfo is UTC
    assert not hasattr(resolution, "fingerprint")
    _assert_json_safe(resolution.to_dict())


def test_resolver_distinguishes_not_found_and_inactive() -> None:
    mapping = _mapping()
    with pytest.raises(InstrumentMappingNotFoundError):
        resolve_instrument_mapping(_external(symbol="NYSE:MSFT"), (mapping,), _START)
    with pytest.raises(InstrumentMappingInactiveError):
        resolve_instrument_mapping(
            mapping.external_identity,
            (mapping,),
            _START - timedelta(microseconds=1),
        )


def test_resolver_rejects_duplicate_mapping_fingerprint() -> None:
    mapping = _mapping()
    with pytest.raises(InstrumentMappingDuplicateError, match=mapping.fingerprint):
        resolve_instrument_mapping(
            mapping.external_identity,
            (mapping, mapping),
            _START,
        )


def test_resolver_classifies_same_result_as_ambiguous() -> None:
    first = _mapping(source=_source(source_id="registry.a"))
    second = _mapping(source=_source(source_id="registry.b"))
    assert first.canonical_instrument == second.canonical_instrument
    with pytest.raises(InstrumentMappingAmbiguousError):
        resolve_instrument_mapping(
            first.external_identity,
            (first, second),
            _START,
        )


@pytest.mark.parametrize(
    "other",
    [
        _canonical(instrument_id="microsoft", symbol="MSFT"),
        _canonical(instrument_id="us_equity_apple", symbol="APPL"),
        _canonical(
            instrument_id="us_equity_apple",
            asset_class=InstrumentAssetClass.ETF,
        ),
        _canonical(instrument_id="us_equity_apple", currency="EUR"),
    ],
)
def test_resolver_classifies_different_canonical_result_as_conflict(
    other: CanonicalInstrument,
) -> None:
    first = _mapping(source=_source(source_id="registry.a"))
    second = _mapping(
        canonical=other,
        source=_source(source_id="registry.b"),
    )
    with pytest.raises(InstrumentMappingConflictError):
        resolve_instrument_mapping(
            first.external_identity,
            (first, second),
            _START,
        )


@pytest.mark.parametrize(
    "classification",
    ["success", "ambiguous", "conflict", "inactive"],
)
def test_resolver_is_input_order_neutral(classification: str) -> None:
    first = _mapping(
        source=_source(source_id="registry.a"),
        expires_at=_END,
    )
    if classification == "success":
        second = _mapping(
            external=_external(symbol="NYSE:MSFT"),
            canonical=_canonical(instrument_id="microsoft", symbol="MSFT"),
        )
    elif classification == "ambiguous":
        second = _mapping(source=_source(source_id="registry.b"))
    elif classification == "conflict":
        second = _mapping(
            canonical=_canonical(instrument_id="microsoft", symbol="MSFT"),
            source=_source(source_id="registry.b"),
        )
    else:
        second = _mapping(
            source=_source(source_id="registry.b"),
            expires_at=_END,
        )
    orders = ((first, second), (second, first))
    as_of = _END if classification == "inactive" else _START
    if classification == "success":
        results = [
            resolve_instrument_mapping(first.external_identity, order, as_of)
            for order in orders
        ]
        assert results[0] == results[1]
        return
    error_type = {
        "ambiguous": InstrumentMappingAmbiguousError,
        "conflict": InstrumentMappingConflictError,
        "inactive": InstrumentMappingInactiveError,
    }[classification]
    messages: list[str] = []
    for order in orders:
        with pytest.raises(error_type) as captured:
            resolve_instrument_mapping(first.external_identity, order, as_of)
        messages.append(str(captured.value))
    assert messages[0] == messages[1]


def test_resolver_handles_non_overlapping_ticker_rename() -> None:
    external = _external()
    old = _mapping(
        external=external,
        canonical=_canonical(instrument_id="meta", symbol="FB"),
        valid_from=_START,
        expires_at=_END,
    )
    renamed = _mapping(
        external=external,
        canonical=_canonical(instrument_id="meta", symbol="META"),
        valid_from=_END,
        expires_at=None,
    )
    before = resolve_instrument_mapping(external, (renamed, old), _END - timedelta(
        microseconds=1
    ))
    after = resolve_instrument_mapping(external, (old, renamed), _END)
    assert before.mapping.canonical_instrument.trading_identity.symbol == "FB"
    assert after.mapping.canonical_instrument.trading_identity.symbol == "META"
    assert (
        before.mapping.canonical_instrument.instrument_id
        == after.mapping.canonical_instrument.instrument_id
    )


def test_resolver_uses_exact_identity_without_guessing() -> None:
    upper = _mapping(external=_external(symbol="NASDAQ:AAPL"))
    lower = _external(symbol="nasdaq:aapl")
    with pytest.raises(InstrumentMappingNotFoundError):
        resolve_instrument_mapping(lower, (upper,), _START)


class _HostileSequence(Sequence[InstrumentMapping]):
    def __getitem__(self, index: int) -> InstrumentMapping:
        if index == 0:
            return _mapping()
        raise IndexError

    def __len__(self) -> int:
        return 1

    def __iter__(self) -> object:
        raise AssertionError("custom sequence iteration must not execute")


class _HostileIterable:
    def __iter__(self) -> object:
        raise AssertionError("custom iterable iteration must not execute")


class _HostileList(list[InstrumentMapping]):
    def __iter__(self) -> object:
        raise AssertionError("list subclass iteration must not execute")


class _HostileTuple(tuple[InstrumentMapping, ...]):
    def __iter__(self) -> object:
        raise AssertionError("tuple subclass iteration must not execute")


@pytest.mark.parametrize("container_type", [list, tuple])
@pytest.mark.parametrize("populated", [False, True])
def test_resolver_accepts_only_exact_builtin_finite_containers(
    container_type: type[list[InstrumentMapping]]
    | type[tuple[InstrumentMapping, ...]],
    populated: bool,
) -> None:
    mapping = _mapping()
    mappings = container_type([mapping] if populated else [])
    if not populated:
        with pytest.raises(InstrumentMappingNotFoundError):
            resolve_instrument_mapping(mapping.external_identity, mappings, _START)
        return
    resolution = resolve_instrument_mapping(
        mapping.external_identity,
        mappings,
        _START,
    )
    assert resolution.mapping is mapping


def test_resolver_rejects_nonbuiltin_containers_before_iteration() -> None:
    mapping = _mapping()
    rejected: tuple[object, ...] = (
        iter((mapping,)),
        (item for item in (mapping,)),
        {mapping},
        frozenset({mapping}),
        {"mapping": mapping},
        OrderedDict([("mapping", mapping)]),
        "mapping",
        b"mapping",
        bytearray(b"mapping"),
        range(1),
        deque([mapping]),
        _HostileSequence(),
        _HostileIterable(),
        _HostileList([mapping]),
        _HostileTuple((mapping,)),
    )
    for mappings in rejected:
        with pytest.raises(TypeError, match="exact built-in list or tuple"):
            resolve_instrument_mapping(
                mapping.external_identity,
                mappings,  # type: ignore[arg-type]
                _START,
            )


def test_resolver_input_validation_does_not_mask_mapping_failures() -> None:
    with pytest.raises(TypeError):
        resolve_instrument_mapping(
            _external(),
            (object(),),  # type: ignore[list-item]
            _START,
        )


def test_resolution_is_factory_only_and_schema_has_no_fingerprint() -> None:
    with pytest.raises(TypeError, match="resolve_instrument_mapping"):
        InstrumentResolution()
    resolution = resolve_instrument_mapping(_external(), (_mapping(),), _START)
    assert set(resolution.to_dict()) == {
        "schema_version",
        "external_identity",
        "mapping",
        "resolved_as_of",
    }


def test_resolution_rejects_external_mapping_mismatch() -> None:
    mapping = _mapping()
    with pytest.raises(InstrumentResolutionCorrespondenceError, match="does not match"):
        InstrumentResolution._create(
            external_identity=_external(symbol="NYSE:MSFT"),
            mapping=mapping,
            resolved_as_of=_START,
        )


def test_resolution_rejects_inactive_mapping() -> None:
    mapping = _mapping()
    with pytest.raises(InstrumentResolutionCorrespondenceError, match="inactive"):
        InstrumentResolution._create(
            external_identity=mapping.external_identity,
            mapping=mapping,
            resolved_as_of=_END,
        )


def test_resolution_rejects_fabricated_mapping_fingerprint() -> None:
    mapping = _mapping()
    object.__setattr__(mapping, "fingerprint", "sha256:" + ("0" * 64))
    with pytest.raises(InstrumentResolutionCorrespondenceError):
        InstrumentResolution._create(
            external_identity=mapping.external_identity,
            mapping=mapping,
            resolved_as_of=_START,
        )


@pytest.mark.parametrize("field_name", ["resolved_as_of", "mapping_valid_from"])
def test_resolution_rejects_noncanonical_stored_timestamp(
    field_name: str,
) -> None:
    offset_start = _START.astimezone(timezone(timedelta(hours=8)))
    mapping = _mapping()
    if field_name == "mapping_valid_from":
        object.__setattr__(mapping, "valid_from", offset_start)
    with pytest.raises(InstrumentResolutionCorrespondenceError):
        InstrumentResolution._create(
            external_identity=mapping.external_identity,
            mapping=mapping,
            resolved_as_of=(
                offset_start if field_name == "resolved_as_of" else _START
            ),
        )


def test_new_models_are_frozen_slotted_and_derived_fields_are_not_init() -> None:
    models = (
        CanonicalInstrument,
        ExternalInstrumentIdentity,
        InstrumentMappingSourceIdentity,
        InstrumentMapping,
    )
    for model in models:
        assert "__slots__" in model.__dict__
        init_fields = {item.name for item in fields(model) if item.init}
        assert "fingerprint" not in init_fields
        assert "schema_version" not in init_fields


def test_projections_contain_no_snapshot_risk_broker_or_transport_fields() -> None:
    projection = resolve_instrument_mapping(
        _external(),
        (_mapping(),),
        _START,
    ).to_dict()
    text = json.dumps(projection, sort_keys=True).lower()
    for forbidden in (
        "account",
        "position",
        "snapshot",
        "risk",
        "broker",
        "tradingview_payload",
        "credential",
        "metadata",
        "priority",
        "confidence",
    ):
        assert forbidden not in text


def test_released_trading_identity_behavior_remains_exact() -> None:
    identity = TradingInstrumentIdentity(symbol="aapl", venue="nasdaq")
    assert identity.to_dict() == {
        "schema_version": "trading_instrument_identity/v1",
        "symbol": "AAPL",
        "venue": "NASDAQ",
        "instrument_fingerprint": (
            "sha256:dc586683e7966f5f6a9060934d37a28a"
            "594fe22b6cd42f40b5f5228e13cba433"
        ),
    }


def test_new_package_does_not_mutate_released_models() -> None:
    identity = TradingInstrumentIdentity("AAPL", "NASDAQ")
    canonical = _canonical()
    assert canonical.trading_identity == identity
    assert replace(identity, symbol="MSFT").symbol == "MSFT"
