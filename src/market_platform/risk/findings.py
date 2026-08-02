"""Bounded evaluator-owned structural risk findings."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from market_platform.risk._canonical import required_fingerprint
from market_platform.risk.errors import (
    RiskCorrespondenceError,
    RiskValidationError,
)


class RiskDecisionOutcome(StrEnum):
    """Fail-closed structural risk outcome."""

    APPROVED = "approved"
    REJECTED = "rejected"
    INDETERMINATE = "indeterminate"


class RiskReasonCode(StrEnum):
    """Exact reason codes implemented by the v1 structural evaluator."""

    INTENT_NOT_YET_VALID = "intent_not_yet_valid"
    INTENT_EXPIRED = "intent_expired"
    RESOLUTION_FUTURE_DATED = "resolution_future_dated"
    MAPPING_INACTIVE = "mapping_inactive"
    INSTRUMENT_MISMATCH = "instrument_mismatch"
    ACCOUNT_MISMATCH = "account_mismatch"
    CASH_FUTURE_DATED = "cash_future_dated"
    CASH_STALE = "cash_stale"
    POSITION_FUTURE_DATED = "position_future_dated"
    POSITION_STALE = "position_stale"
    OPEN_ORDER_FUTURE_DATED = "open_order_future_dated"
    OPEN_ORDER_STALE = "open_order_stale"
    QUOTE_FUTURE_DATED = "quote_future_dated"
    QUOTE_STALE = "quote_stale"
    EXCESSIVE_STATE_SKEW = "excessive_state_skew"
    CASH_COVERAGE_INADEQUATE = "cash_coverage_inadequate"
    POSITION_COVERAGE_INADEQUATE = "position_coverage_inadequate"
    OPEN_ORDER_COVERAGE_INADEQUATE = "open_order_coverage_inadequate"
    QUOTE_COVERAGE_INADEQUATE = "quote_coverage_inadequate"
    QUOTE_MISSING = "quote_missing"
    QUOTE_INSUFFICIENT = "quote_insufficient"


_REASON_ORDER = {reason: index for index, reason in enumerate(RiskReasonCode)}
_SUBJECTS = frozenset(
    {
        "intent",
        "mapping",
        "instrument",
        "account",
        "cash",
        "positions",
        "open_orders",
        "quotes",
        "state",
    }
)
_FINDING_TOKEN = object()
MAX_RISK_FINDINGS = 32


@dataclass(frozen=True, slots=True, init=False)
class RiskFinding:
    """One evaluator-owned bounded structural finding."""

    reason_code: RiskReasonCode
    subject: str
    evidence_fingerprints: tuple[str, ...]

    def __init__(self) -> None:
        raise TypeError("RiskFinding is created by structural risk evaluation")

    @classmethod
    def _create(
        cls,
        *,
        reason_code: RiskReasonCode,
        subject: str,
        evidence_fingerprints: tuple[str, ...] = (),
        _token: object,
    ) -> RiskFinding:
        if _token is not _FINDING_TOKEN:
            raise TypeError("RiskFinding construction is evaluator-owned")
        if type(reason_code) is not RiskReasonCode:
            raise RiskValidationError("reason_code must be a RiskReasonCode")
        if type(subject) is not str or subject not in _SUBJECTS:
            raise RiskValidationError("finding subject is invalid")
        if type(evidence_fingerprints) is not tuple:
            raise RiskValidationError("evidence_fingerprints must be a tuple")
        if len(evidence_fingerprints) > 4:
            raise RiskValidationError("finding may retain at most 4 fingerprints")
        fingerprints = tuple(
            sorted(
                required_fingerprint(value, "evidence fingerprint")
                for value in evidence_fingerprints
            )
        )
        if len(set(fingerprints)) != len(fingerprints):
            raise RiskValidationError("finding evidence fingerprints must be unique")
        finding = object.__new__(cls)
        object.__setattr__(finding, "reason_code", reason_code)
        object.__setattr__(finding, "subject", subject)
        object.__setattr__(finding, "evidence_fingerprints", fingerprints)
        return finding

    def to_dict(self) -> dict[str, object]:
        """Return the bounded JSON-safe finding projection."""

        return {
            "reason_code": self.reason_code.value,
            "subject": self.subject,
            "evidence_fingerprints": list(self.evidence_fingerprints),
        }


def create_finding(
    reason_code: RiskReasonCode,
    subject: str,
    *fingerprints: str,
) -> RiskFinding:
    return RiskFinding._create(
        reason_code=reason_code,
        subject=subject,
        evidence_fingerprints=tuple(fingerprints),
        _token=_FINDING_TOKEN,
    )


def finding_sort_key(finding: RiskFinding) -> tuple[int, str]:
    return (_REASON_ORDER[finding.reason_code], finding.subject)


def canonical_findings(value: object) -> tuple[RiskFinding, ...]:
    if type(value) not in (list, tuple):
        raise RiskValidationError("findings must be an exact list or tuple")
    items = cast("list[object] | tuple[object, ...]", value)
    if len(items) > MAX_RISK_FINDINGS:
        raise RiskValidationError("findings may contain at most 32 records")
    reconstructed: list[RiskFinding] = []
    for finding in items:
        reconstructed.append(require_finding_correspondence(finding))
    ordered = tuple(sorted(reconstructed, key=finding_sort_key))
    keys = [(item.reason_code, item.subject) for item in ordered]
    if len(set(keys)) != len(keys):
        raise RiskValidationError("findings contain a duplicate reason and subject")
    return ordered


def require_finding_correspondence(value: object) -> RiskFinding:
    if type(value) is not RiskFinding:
        raise RiskCorrespondenceError("finding has invalid runtime type")
    finding = value
    try:
        reconstructed = create_finding(
            finding.reason_code,
            finding.subject,
            *finding.evidence_fingerprints,
        )
    except (TypeError, ValueError) as error:
        raise RiskCorrespondenceError(
            "finding retains invalid canonical state"
        ) from error
    if (
        finding.reason_code is not reconstructed.reason_code
        or finding.subject != reconstructed.subject
        or finding.evidence_fingerprints != reconstructed.evidence_fingerprints
        or finding.to_dict() != reconstructed.to_dict()
    ):
        raise RiskCorrespondenceError("finding does not match guarded reconstruction")
    return finding


__all__ = ["RiskDecisionOutcome", "RiskFinding", "RiskReasonCode"]
