"""Governed semantic and source authorization for candidate Evidence."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from market_platform._fingerprint import canonical_fingerprint
from market_platform.evidence.classification import (
    EvidenceAuthority,
    EvidenceInformationClass,
)
from market_platform.evidence.references import (
    EvidenceContractReference,
    EvidenceSourceReference,
)

EVIDENCE_MATERIAL_SCHEMA_REFERENCE_SCHEMA_VERSION = (
    "evidence_material_schema_reference/v1"
)
EVIDENCE_CONTRACT_DEFINITION_SCHEMA_VERSION = "evidence_contract_definition/v1"
EVIDENCE_CONTRACT_AUTHORIZATION_SCHEMA_VERSION = "evidence_contract_authorization/v1"

_AUTHORIZATION_RECORD_SEAL = object()
_FINGERPRINT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}", flags=re.ASCII)
_IDENTITY_PATTERN = re.compile(r"[a-z][a-z0-9._-]{0,127}", flags=re.ASCII)

_POLYGON_COMPLETED_DAILY_OHLCV_GOVERNING_ADR = (
    "docs/adr/0037-polygon-completed-daily-ohlcv-evidence-ingress.md@"
    "d9c30a57fef451eb7b5e66850af2d94be128f5fb"
)
_POLYGON_COMPLETED_DAILY_OHLCV_SOURCE_DEFINITION: Mapping[str, object] = (
    MappingProxyType(
        {
            "schema_version": "evidence_source_definition/v1",
            "governing_adr": _POLYGON_COMPLETED_DAILY_OHLCV_GOVERNING_ADR,
            "vendor_service": "massive.com_formerly_polygon.io",
            "source_namespace": "massive",
            "source_id": "stocks_custom_bars_1_day_adjusted_api_polygon_io",
            "source_version": "1.0.0",
            "capability": "stocks_custom_bars_aggregates",
            "http_method": "GET",
            "api_base": "https://api.polygon.io",
            "route_template": (
                "/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from}/{to}"
            ),
            "multiplier": 1,
            "timespan": "day",
            "adjusted": True,
            "sort": "asc",
            "limit": 50000,
            "adjusted_response_proof": "exact_boolean_true",
            "market_timezone": "America/New_York",
            "aggregate_window_semantics": "provider_documented_eastern_time",
            "session_scope": "polygon_qualifying_trades_all_sessions",
            "timestamp_semantics": "unix_milliseconds_window_start",
            "completion_filter": (
                "session_date_before_query_as_of_america_new_york_date"
            ),
            "price_adjustment": "split_adjusted_not_dividend_adjusted",
            "split_adjustment_formula": (
                "provider_internal_undocumented_not_asserted_or_reconstructed"
            ),
            "volume_semantics": (
                "provider_reported_split_adjusted_aggregate_decimal_capable"
            ),
            "numeric_semantics": "finite_decimal_compatible_exact_value",
            "completeness": (
                "bounded_single_response_no_unconsumed_next_url_consistent_counts"
            ),
        }
    )
)
_POLYGON_COMPLETED_DAILY_OHLCV_SOURCE_DEFINITION_FINGERPRINT = canonical_fingerprint(
    _POLYGON_COMPLETED_DAILY_OHLCV_SOURCE_DEFINITION
)

_POLYGON_COMPLETED_DAILY_OHLCV_MATERIAL_DEFINITION: Mapping[str, object] = (
    MappingProxyType(
        {
            "schema_version": "evidence_material_definition/v1",
            "governing_adr": _POLYGON_COMPLETED_DAILY_OHLCV_GOVERNING_ADR,
            "schema_id": "polygon_completed_daily_ohlcv_material",
            "schema_version_id": "1.0.0",
            "source_definition_fingerprint": (
                _POLYGON_COMPLETED_DAILY_OHLCV_SOURCE_DEFINITION_FINGERPRINT
            ),
            "vendor_service": "massive.com_formerly_polygon.io",
            "api_base": "https://api.polygon.io",
            "route_template": (
                "/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from}/{to}"
            ),
            "multiplier": 1,
            "timespan": "1_day",
            "adjusted": True,
            "sort": "asc",
            "limit": 50000,
            "market_timezone": "America/New_York",
            "session_scope": "polygon_qualifying_trades_all_sessions",
            "price_adjustment": "split_adjusted_not_dividend_adjusted",
            "adjusted_response": True,
            "volume_semantics": (
                "provider_reported_split_adjusted_aggregate_decimal_capable"
            ),
            "split_adjustment_formula": (
                "provider_internal_undocumented_not_asserted_or_reconstructed"
            ),
            "envelope_fields": (
                "material_schema",
                "source_reference",
                "vendor_service",
                "api_base",
                "route_template",
                "multiplier",
                "timespan",
                "adjusted",
                "sort",
                "limit",
                "external_instrument_identity",
                "canonical_subject",
                "mapping_resolution_provenance",
                "start_session_date",
                "end_session_date",
                "query_as_of",
                "market_timezone",
                "session_scope",
                "price_adjustment",
                "adjusted_response",
                "request_provenance",
                "provider_request_id",
                "rows",
                "row_count",
            ),
            "row_fields": (
                "session_date",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ),
            "date_bounds": "inclusive_start_and_end_start_not_after_end",
            "row_order": "strictly_ascending_session_date",
            "duplicate_policy": "reject_duplicate_session_date",
            "missing_session_policy": "absence_only_no_synthesis",
            "numeric_normalization": (
                "finite_base10_no_exponent_no_trailing_fractional_zero_"
                "nonnegative_zero_no_rounding"
            ),
            "volume_type": "decimal_capable_provider_reported_value",
            "timestamp_to_session_date": "convert_source_t_to_america_new_york",
            "completion_filter": (
                "exclude_current_and_future_america_new_york_calendar_dates"
            ),
            "empty_material": "permitted_and_not_completeness_proof",
            "credentials_in_provenance": False,
            "material_fingerprint": "complete_envelope_excluding_fingerprint",
        }
    )
)
_POLYGON_COMPLETED_DAILY_OHLCV_MATERIAL_DEFINITION_FINGERPRINT = canonical_fingerprint(
    _POLYGON_COMPLETED_DAILY_OHLCV_MATERIAL_DEFINITION
)

_POLYGON_COMPLETED_DAILY_OHLCV_CONTRACT_DEFINITION: Mapping[str, object] = (
    MappingProxyType(
        {
            "schema_version": "governing_evidence_contract_definition/v1",
            "governing_adr": _POLYGON_COMPLETED_DAILY_OHLCV_GOVERNING_ADR,
            "contract_namespace": "market_platform.evidence",
            "contract_id": "polygon_completed_daily_ohlcv",
            "contract_version": "1.0.0",
            "evidence_type": "polygon_completed_daily_ohlcv",
            "information_class": "source_measurement",
            "authority": "external_origin",
            "source_definition_fingerprint": (
                _POLYGON_COMPLETED_DAILY_OHLCV_SOURCE_DEFINITION_FINGERPRINT
            ),
            "material_definition_fingerprint": (
                _POLYGON_COMPLETED_DAILY_OHLCV_MATERIAL_DEFINITION_FINGERPRINT
            ),
            "subject_scope": (
                "one_canonically_resolved_us_equity_or_etf_per_bounded_interval"
            ),
            "observation_interval": (
                "requested_session_bounds_as_half_open_america_new_york_midnights_utc"
            ),
            "observed_at": "absent_for_multi_row_interval",
            "effective_interval": "absent",
            "published_at": "absent_provider_does_not_supply",
            "source_revision": "material_fingerprint",
            "platform_received_at": "explicit_utc_response_receipt",
            "artifact_created_at": "explicit_utc_not_before_receipt",
            "query_as_of": "material_provenance_and_completion_cutoff_only",
            "lifecycle": "candidate_unvalidated_unadmitted_not_consumable",
        }
    )
)
_POLYGON_COMPLETED_DAILY_OHLCV_CONTRACT_DEFINITION_FINGERPRINT = canonical_fingerprint(
    _POLYGON_COMPLETED_DAILY_OHLCV_CONTRACT_DEFINITION
)


@dataclass(frozen=True, slots=True)
class EvidenceMaterialSchemaReference:
    """Exact identity of the bounded source-material representation."""

    schema_id: str
    schema_version_id: str
    schema_fingerprint: str
    schema_version: str = field(
        init=False,
        default=EVIDENCE_MATERIAL_SCHEMA_REFERENCE_SCHEMA_VERSION,
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_id", _identity(self.schema_id, "schema_id"))
        object.__setattr__(
            self,
            "schema_version_id",
            _visible_ascii(self.schema_version_id, "schema_version_id", 128),
        )
        object.__setattr__(
            self,
            "schema_fingerprint",
            _fingerprint(self.schema_fingerprint, "schema_fingerprint"),
        )
        object.__setattr__(
            self,
            "fingerprint",
            canonical_fingerprint(self._fingerprint_payload()),
        )

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "schema_id": self.schema_id,
            "schema_version_id": self.schema_version_id,
            "schema_fingerprint": self.schema_fingerprint,
        }

    def _validate(self) -> None:
        reconstructed = EvidenceMaterialSchemaReference(
            schema_id=self.schema_id,
            schema_version_id=self.schema_version_id,
            schema_fingerprint=self.schema_fingerprint,
        )
        if self.schema_version != EVIDENCE_MATERIAL_SCHEMA_REFERENCE_SCHEMA_VERSION:
            raise ValueError("Evidence material schema reference version is invalid")
        if _fingerprint(self.fingerprint, "fingerprint") != reconstructed.fingerprint:
            raise ValueError("Evidence material schema reference is not canonical")

    def to_dict(self) -> dict[str, object]:
        """Return the canonical immutable schema identity."""

        self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


@dataclass(frozen=True, slots=True)
class EvidenceContractDefinition:
    """The dimensions one governed Evidence contract authorizes together."""

    governing_contract: EvidenceContractReference
    evidence_type: str
    information_class: EvidenceInformationClass
    material_schema: EvidenceMaterialSchemaReference
    schema_version: str = field(
        init=False,
        default=EVIDENCE_CONTRACT_DEFINITION_SCHEMA_VERSION,
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if type(self.information_class) is not EvidenceInformationClass:
            raise TypeError(
                "information_class must be an exact EvidenceInformationClass"
            )
        object.__setattr__(
            self,
            "governing_contract",
            _copy_contract_reference(self.governing_contract),
        )
        object.__setattr__(
            self,
            "evidence_type",
            _identity(self.evidence_type, "evidence_type"),
        )
        object.__setattr__(
            self,
            "material_schema",
            _copy_material_schema(self.material_schema),
        )
        if self.governing_contract.information_class is not self.information_class:
            raise ValueError(
                "governing contract reference must match the authorized "
                "information class"
            )
        object.__setattr__(
            self,
            "fingerprint",
            canonical_fingerprint(self._fingerprint_payload()),
        )

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "governing_contract": self.governing_contract.to_dict(),
            "evidence_type": self.evidence_type,
            "information_class": self.information_class.value,
            "material_schema": self.material_schema.to_dict(),
        }

    def _validate(self) -> None:
        reconstructed = EvidenceContractDefinition(
            governing_contract=self.governing_contract,
            evidence_type=self.evidence_type,
            information_class=self.information_class,
            material_schema=self.material_schema,
        )
        if self.schema_version != EVIDENCE_CONTRACT_DEFINITION_SCHEMA_VERSION:
            raise ValueError("Evidence contract definition version is invalid")
        if _fingerprint(self.fingerprint, "fingerprint") != reconstructed.fingerprint:
            raise ValueError("Evidence contract definition is not canonical")

    def to_dict(self) -> dict[str, object]:
        """Return the canonical immutable contract definition."""

        self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


@dataclass(frozen=True, slots=True, init=False)
class EvidenceContractAuthorization:
    """Immutable description of one contract, exact source, and origin class.

    Construction of this record does not establish governance approval. Only
    exact membership in the closed governed catalog grants artifact-minting
    authority.
    """

    authorization_id: str
    authorization_version: str
    contract_definition: EvidenceContractDefinition
    authorized_source: EvidenceSourceReference
    authority: EvidenceAuthority
    schema_version: str = field(init=False)
    fingerprint: str = field(init=False)

    def __init__(self) -> None:
        raise TypeError("EvidenceContractAuthorization must be factory-created")

    @classmethod
    def _create(
        cls,
        *,
        authorization_id: str,
        authorization_version: str,
        contract_definition: EvidenceContractDefinition,
        authorized_source: EvidenceSourceReference,
        authority: EvidenceAuthority,
        seal: object,
    ) -> EvidenceContractAuthorization:
        if seal is not _AUTHORIZATION_RECORD_SEAL:
            raise TypeError("Evidence contract authorization construction is private")
        if type(authority) is not EvidenceAuthority:
            raise TypeError("authority must be an exact EvidenceAuthority")
        instance = object.__new__(cls)
        values: dict[str, object] = {
            "authorization_id": _visible_ascii(
                authorization_id, "authorization_id", 256
            ),
            "authorization_version": _visible_ascii(
                authorization_version, "authorization_version", 128
            ),
            "contract_definition": _copy_contract_definition(contract_definition),
            "authorized_source": _copy_source_reference(authorized_source),
            "authority": authority,
            "schema_version": EVIDENCE_CONTRACT_AUTHORIZATION_SCHEMA_VERSION,
        }
        for name, value in values.items():
            object.__setattr__(instance, name, value)
        if instance.authorized_source.authority is not instance.authority:
            raise ValueError(
                "authorized source must retain the governed origin authority"
            )
        object.__setattr__(
            instance,
            "fingerprint",
            canonical_fingerprint(instance._fingerprint_payload()),
        )
        instance._validate()
        return instance

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "authorization_id": self.authorization_id,
            "authorization_version": self.authorization_version,
            "contract_definition": self.contract_definition.to_dict(),
            "authorized_source": self.authorized_source.to_dict(),
            "authority": self.authority.value,
        }

    def _validate(self) -> None:
        _visible_ascii(self.authorization_id, "authorization_id", 256)
        _visible_ascii(self.authorization_version, "authorization_version", 128)
        _copy_contract_definition(self.contract_definition)
        _copy_source_reference(self.authorized_source)
        if type(self.authority) is not EvidenceAuthority:
            raise ValueError("Evidence contract authorization authority is invalid")
        if self.schema_version != EVIDENCE_CONTRACT_AUTHORIZATION_SCHEMA_VERSION:
            raise ValueError("Evidence contract authorization version is invalid")
        if _fingerprint(self.fingerprint, "fingerprint") != canonical_fingerprint(
            self._fingerprint_payload()
        ):
            raise ValueError("Evidence contract authorization is not canonical")

    def to_dict(self) -> dict[str, object]:
        """Return the canonical immutable authorization description."""

        self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


@dataclass(frozen=True, slots=True)
class _EvidenceAuthorizationApprovalCatalog:
    """Closed immutable set of exact authorization records approved by governance."""

    authorizations: tuple[EvidenceContractAuthorization, ...]

    def __post_init__(self) -> None:
        if type(self.authorizations) is not tuple:
            raise TypeError("governed authorizations must be an exact tuple")
        copied = tuple(
            _copy_contract_authorization(authorization)
            for authorization in self.authorizations
        )
        fingerprints = tuple(authorization.fingerprint for authorization in copied)
        if len(set(fingerprints)) != len(fingerprints):
            raise ValueError("governed authorizations must not contain duplicates")
        object.__setattr__(self, "authorizations", copied)

    def resolve(
        self,
        authorization: EvidenceContractAuthorization,
    ) -> EvidenceContractAuthorization:
        """Return the governed record matching one exact authorization identity."""

        candidate = _copy_contract_authorization(authorization)
        for approved in self.authorizations:
            if candidate.fingerprint == approved.fingerprint and candidate == approved:
                return _copy_contract_authorization(approved)
        raise ValueError("Evidence contract authorization is not governed/approved")


def _create_evidence_contract_authorization_record(
    *,
    authorization_id: str,
    authorization_version: str,
    contract_definition: EvidenceContractDefinition,
    authorized_source: EvidenceSourceReference,
    authority: EvidenceAuthority,
) -> EvidenceContractAuthorization:
    """Construct an immutable description; this does not approve it."""

    return EvidenceContractAuthorization._create(
        authorization_id=authorization_id,
        authorization_version=authorization_version,
        contract_definition=contract_definition,
        authorized_source=authorized_source,
        authority=authority,
        seal=_AUTHORIZATION_RECORD_SEAL,
    )


def _resolve_governed_evidence_contract_authorization(
    authorization: EvidenceContractAuthorization,
) -> EvidenceContractAuthorization:
    """Resolve one exact authorization against the production trust root."""

    return _GOVERNED_EVIDENCE_AUTHORIZATION_CATALOG.resolve(authorization)


def _copy_contract_reference(value: object) -> EvidenceContractReference:
    if type(value) is not EvidenceContractReference:
        raise TypeError("governing_contract must be an EvidenceContractReference")
    value._validate()
    return EvidenceContractReference(
        namespace=value.namespace,
        contract_id=value.contract_id,
        contract_version=value.contract_version,
        information_class=value.information_class,
        contract_fingerprint=value.contract_fingerprint,
    )


def _copy_source_reference(value: object) -> EvidenceSourceReference:
    if type(value) is not EvidenceSourceReference:
        raise TypeError("authorized_source must be an EvidenceSourceReference")
    value._validate()
    return EvidenceSourceReference(
        namespace=value.namespace,
        source_id=value.source_id,
        source_version=value.source_version,
        authority=value.authority,
        source_fingerprint=value.source_fingerprint,
    )


def _copy_material_schema(value: object) -> EvidenceMaterialSchemaReference:
    if type(value) is not EvidenceMaterialSchemaReference:
        raise TypeError("material_schema must be an EvidenceMaterialSchemaReference")
    value._validate()
    return EvidenceMaterialSchemaReference(
        schema_id=value.schema_id,
        schema_version_id=value.schema_version_id,
        schema_fingerprint=value.schema_fingerprint,
    )


def _copy_contract_definition(value: object) -> EvidenceContractDefinition:
    if type(value) is not EvidenceContractDefinition:
        raise TypeError("contract_definition must be an EvidenceContractDefinition")
    value._validate()
    return EvidenceContractDefinition(
        governing_contract=value.governing_contract,
        evidence_type=value.evidence_type,
        information_class=value.information_class,
        material_schema=value.material_schema,
    )


def _copy_contract_authorization(value: object) -> EvidenceContractAuthorization:
    if type(value) is not EvidenceContractAuthorization:
        raise TypeError(
            "contract_authorization must be an EvidenceContractAuthorization"
        )
    value._validate()
    return EvidenceContractAuthorization._create(
        authorization_id=value.authorization_id,
        authorization_version=value.authorization_version,
        contract_definition=value.contract_definition,
        authorized_source=value.authorized_source,
        authority=value.authority,
        seal=_AUTHORIZATION_RECORD_SEAL,
    )


def _identity(value: object, field_name: str) -> str:
    if type(value) is not str or _IDENTITY_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must match [a-z][a-z0-9._-]{{0,127}}")
    return value


def _visible_ascii(value: object, field_name: str, maximum_length: int) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string")
    if not value:
        raise ValueError(f"{field_name} must not be empty")
    if len(value) > maximum_length:
        raise ValueError(f"{field_name} exceeds maximum length {maximum_length}")
    if any(not 0x21 <= ord(character) <= 0x7E for character in value):
        raise ValueError(f"{field_name} must contain visible ASCII without whitespace")
    return value


def _fingerprint(value: object, field_name: str) -> str:
    if type(value) is not str or _FINGERPRINT_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a lowercase sha256 fingerprint")
    return value


_POLYGON_COMPLETED_DAILY_OHLCV_SOURCE = EvidenceSourceReference(
    namespace="massive",
    source_id="stocks_custom_bars_1_day_adjusted_api_polygon_io",
    source_version="1.0.0",
    authority=EvidenceAuthority.EXTERNAL_ORIGIN,
    source_fingerprint=(_POLYGON_COMPLETED_DAILY_OHLCV_SOURCE_DEFINITION_FINGERPRINT),
)
_POLYGON_COMPLETED_DAILY_OHLCV_MATERIAL_SCHEMA = EvidenceMaterialSchemaReference(
    schema_id="polygon_completed_daily_ohlcv_material",
    schema_version_id="1.0.0",
    schema_fingerprint=(_POLYGON_COMPLETED_DAILY_OHLCV_MATERIAL_DEFINITION_FINGERPRINT),
)
_POLYGON_COMPLETED_DAILY_OHLCV_GOVERNING_CONTRACT = EvidenceContractReference(
    namespace="market_platform.evidence",
    contract_id="polygon_completed_daily_ohlcv",
    contract_version="1.0.0",
    information_class=EvidenceInformationClass.SOURCE_MEASUREMENT,
    contract_fingerprint=(
        _POLYGON_COMPLETED_DAILY_OHLCV_CONTRACT_DEFINITION_FINGERPRINT
    ),
)
_POLYGON_COMPLETED_DAILY_OHLCV_AUTHORIZATION = (
    _create_evidence_contract_authorization_record(
        authorization_id="production.polygon_completed_daily_ohlcv",
        authorization_version="1.0.0",
        contract_definition=EvidenceContractDefinition(
            governing_contract=(_POLYGON_COMPLETED_DAILY_OHLCV_GOVERNING_CONTRACT),
            evidence_type="polygon_completed_daily_ohlcv",
            information_class=EvidenceInformationClass.SOURCE_MEASUREMENT,
            material_schema=_POLYGON_COMPLETED_DAILY_OHLCV_MATERIAL_SCHEMA,
        ),
        authorized_source=_POLYGON_COMPLETED_DAILY_OHLCV_SOURCE,
        authority=EvidenceAuthority.EXTERNAL_ORIGIN,
    )
)

# ADR0037 approves exactly this one production Evidence semantic conjunction.
# Future governed adapters must add exact immutable records here through a
# separately reviewed source-code change; runtime callers cannot supply a
# replacement catalog to artifact construction.
_GOVERNED_EVIDENCE_AUTHORIZATION_CATALOG = _EvidenceAuthorizationApprovalCatalog(
    authorizations=(_POLYGON_COMPLETED_DAILY_OHLCV_AUTHORIZATION,)
)


__all__ = [
    "EVIDENCE_CONTRACT_AUTHORIZATION_SCHEMA_VERSION",
    "EVIDENCE_CONTRACT_DEFINITION_SCHEMA_VERSION",
    "EVIDENCE_MATERIAL_SCHEMA_REFERENCE_SCHEMA_VERSION",
    "EvidenceContractAuthorization",
    "EvidenceContractDefinition",
    "EvidenceMaterialSchemaReference",
]
