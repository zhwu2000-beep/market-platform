"""Source and account identities for immutable trading-state snapshots."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from market_platform._fingerprint import canonical_fingerprint
from market_platform.trading_state._canonical import (
    optional_fingerprint,
    require_pattern_text,
    require_visible_ascii,
)
from market_platform.trading_state.errors import (
    TradingStateCorrespondenceError,
    TradingStateValidationError,
)

STATE_SNAPSHOT_SOURCE_SCHEMA_VERSION = "state_snapshot_source/v1"
TRADING_ACCOUNT_IDENTITY_SCHEMA_VERSION = "trading_account_identity/v1"

_INSTITUTION_NAMESPACE_PATTERN = re.compile(
    r"[a-z][a-z0-9._-]{0,63}",
    flags=re.ASCII,
)
_CURRENCY_PATTERN = re.compile(r"[A-Z]{3}", flags=re.ASCII)


class TradingEnvironment(StrEnum):
    """Exact account environments supported by trading-state schema v1."""

    PAPER = "paper"
    LIVE = "live"


@dataclass(frozen=True, slots=True)
class StateSnapshotSourceIdentity:
    """Versioned provenance identity for one state snapshot source."""

    source_id: str
    source_version: str
    configuration_fingerprint: str | None = None
    schema_version: str = field(
        init=False,
        default=STATE_SNAPSHOT_SOURCE_SCHEMA_VERSION,
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        source_id = require_visible_ascii(self.source_id, "source_id", 128)
        source_version = require_visible_ascii(
            self.source_version,
            "source_version",
            64,
        )
        configuration = optional_fingerprint(
            self.configuration_fingerprint,
            "configuration_fingerprint",
        )
        object.__setattr__(self, "source_id", source_id)
        object.__setattr__(self, "source_version", source_version)
        object.__setattr__(self, "configuration_fingerprint", configuration)
        object.__setattr__(
            self,
            "fingerprint",
            canonical_fingerprint(self._fingerprint_payload()),
        )

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_id": self.source_id,
            "source_version": self.source_version,
            "configuration_fingerprint": self.configuration_fingerprint,
        }

    def to_dict(self) -> dict[str, object]:
        """Return the bounded source-identity projection."""

        return {
            **self._fingerprint_payload(),
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True, slots=True)
class TradingAccountIdentity:
    """Stable opaque account identity supplied by trusted orchestration."""

    institution_namespace: str
    account_id: str
    environment: TradingEnvironment
    base_currency: str
    schema_version: str = field(
        init=False,
        default=TRADING_ACCOUNT_IDENTITY_SCHEMA_VERSION,
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        namespace = require_pattern_text(
            self.institution_namespace,
            "institution_namespace",
            _INSTITUTION_NAMESPACE_PATTERN,
            "[a-z][a-z0-9._-]{0,63}",
        )
        account_id = require_visible_ascii(self.account_id, "account_id", 128)
        if type(self.environment) is not TradingEnvironment:
            raise TypeError("environment must be a TradingEnvironment")
        currency = require_pattern_text(
            self.base_currency,
            "base_currency",
            _CURRENCY_PATTERN,
            "[A-Z]{3}",
        )
        object.__setattr__(self, "institution_namespace", namespace)
        object.__setattr__(self, "account_id", account_id)
        object.__setattr__(self, "base_currency", currency)
        object.__setattr__(
            self,
            "fingerprint",
            canonical_fingerprint(self._fingerprint_payload()),
        )

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "institution_namespace": self.institution_namespace,
            "account_id": self.account_id,
            "environment": self.environment.value,
            "base_currency": self.base_currency,
        }

    def to_dict(self) -> dict[str, object]:
        """Return the complete auditable account-identity projection."""

        return {
            **self._fingerprint_payload(),
            "fingerprint": self.fingerprint,
        }


def require_source_correspondence(
    source: object,
) -> StateSnapshotSourceIdentity:
    """Require exact public-constructor source identity state."""

    if type(source) is not StateSnapshotSourceIdentity:
        raise TradingStateCorrespondenceError(
            "snapshot source has invalid runtime type"
        )
    try:
        reconstructed = StateSnapshotSourceIdentity(
            source_id=source.source_id,
            source_version=source.source_version,
            configuration_fingerprint=source.configuration_fingerprint,
        )
    except (TypeError, TradingStateValidationError) as error:
        raise TradingStateCorrespondenceError(
            "snapshot source cannot be reconstructed canonically"
        ) from error
    if (
        source.schema_version != reconstructed.schema_version
        or source.source_id != reconstructed.source_id
        or source.source_version != reconstructed.source_version
        or source.configuration_fingerprint != reconstructed.configuration_fingerprint
        or source.fingerprint != reconstructed.fingerprint
        or source.to_dict() != reconstructed.to_dict()
    ):
        raise TradingStateCorrespondenceError(
            "snapshot source does not match canonical reconstructed state"
        )
    return source


def require_account_correspondence(
    account: object,
) -> TradingAccountIdentity:
    """Require exact public-constructor account identity state."""

    if type(account) is not TradingAccountIdentity:
        raise TradingStateCorrespondenceError(
            "snapshot account has invalid runtime type"
        )
    try:
        reconstructed = TradingAccountIdentity(
            institution_namespace=account.institution_namespace,
            account_id=account.account_id,
            environment=account.environment,
            base_currency=account.base_currency,
        )
    except (TypeError, TradingStateValidationError) as error:
        raise TradingStateCorrespondenceError(
            "snapshot account cannot be reconstructed canonically"
        ) from error
    if (
        account.schema_version != reconstructed.schema_version
        or account.institution_namespace != reconstructed.institution_namespace
        or account.account_id != reconstructed.account_id
        or account.environment is not reconstructed.environment
        or account.base_currency != reconstructed.base_currency
        or account.fingerprint != reconstructed.fingerprint
        or account.to_dict() != reconstructed.to_dict()
    ):
        raise TradingStateCorrespondenceError(
            "snapshot account does not match canonical reconstructed state"
        )
    return account


__all__ = [
    "STATE_SNAPSHOT_SOURCE_SCHEMA_VERSION",
    "TRADING_ACCOUNT_IDENTITY_SCHEMA_VERSION",
    "StateSnapshotSourceIdentity",
    "TradingAccountIdentity",
    "TradingEnvironment",
]
