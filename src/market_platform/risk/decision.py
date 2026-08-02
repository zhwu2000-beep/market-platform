"""Factory-only bounded structural risk decision evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from market_platform._fingerprint import canonical_fingerprint
from market_platform.instruments import CanonicalInstrumentId
from market_platform.risk._canonical import (
    require_canonical_timestamp,
    required_fingerprint,
    timestamp_text,
)
from market_platform.risk.context import (
    EvidenceCoverageScope,
    RiskEvaluationContext,
    require_context_correspondence,
)
from market_platform.risk.errors import (
    RiskCorrespondenceError,
    RiskValidationError,
)
from market_platform.risk.findings import (
    RiskDecisionOutcome,
    RiskFinding,
    RiskReasonCode,
    canonical_findings,
    create_finding,
)
from market_platform.risk.policy import QuoteEvidenceRequirement
from market_platform.trading_state import (
    SnapshotFreshness,
    SnapshotSkew,
    TradingAccountIdentity,
    evaluate_snapshot_freshness,
    evaluate_snapshot_skew,
)

RISK_DECISION_SCHEMA_VERSION = "risk_decision/v1"
_DECISION_TOKEN = object()
_REJECTED_REASONS = {
    RiskReasonCode.INTENT_NOT_YET_VALID,
    RiskReasonCode.INTENT_EXPIRED,
}
_RESOLUTION_REASONS = {
    RiskReasonCode.RESOLUTION_FUTURE_DATED,
    RiskReasonCode.MAPPING_INACTIVE,
    RiskReasonCode.INSTRUMENT_MISMATCH,
}
_FINDING_SPEC: dict[RiskReasonCode, tuple[str, tuple[str, ...] | None]] = {
    RiskReasonCode.INTENT_NOT_YET_VALID: ("intent", ("order_intent_fingerprint",)),
    RiskReasonCode.INTENT_EXPIRED: ("intent", ("order_intent_fingerprint",)),
    RiskReasonCode.RESOLUTION_FUTURE_DATED: ("mapping", ("mapping_fingerprint",)),
    RiskReasonCode.MAPPING_INACTIVE: ("mapping", ("mapping_fingerprint",)),
    RiskReasonCode.INSTRUMENT_MISMATCH: ("instrument", None),
    RiskReasonCode.ACCOUNT_MISMATCH: (
        "account",
        (
            "cash_account_fingerprint",
            "position_account_fingerprint",
            "open_order_account_fingerprint",
        ),
    ),
    RiskReasonCode.CASH_FUTURE_DATED: ("cash", ("cash_snapshot_fingerprint",)),
    RiskReasonCode.CASH_STALE: ("cash", ("cash_snapshot_fingerprint",)),
    RiskReasonCode.POSITION_FUTURE_DATED: (
        "positions",
        ("position_snapshot_fingerprint",),
    ),
    RiskReasonCode.POSITION_STALE: ("positions", ("position_snapshot_fingerprint",)),
    RiskReasonCode.OPEN_ORDER_FUTURE_DATED: (
        "open_orders",
        ("open_order_snapshot_fingerprint",),
    ),
    RiskReasonCode.OPEN_ORDER_STALE: (
        "open_orders",
        ("open_order_snapshot_fingerprint",),
    ),
    RiskReasonCode.QUOTE_FUTURE_DATED: ("quotes", ("quote_snapshot_fingerprint",)),
    RiskReasonCode.QUOTE_STALE: ("quotes", ("quote_snapshot_fingerprint",)),
    RiskReasonCode.EXCESSIVE_STATE_SKEW: (
        "state",
        (
            "cash_snapshot_fingerprint",
            "position_snapshot_fingerprint",
            "open_order_snapshot_fingerprint",
            "quote_snapshot_fingerprint",
        ),
    ),
    RiskReasonCode.CASH_COVERAGE_INADEQUATE: (
        "cash",
        ("cash_snapshot_fingerprint",),
    ),
    RiskReasonCode.POSITION_COVERAGE_INADEQUATE: (
        "positions",
        ("position_snapshot_fingerprint",),
    ),
    RiskReasonCode.OPEN_ORDER_COVERAGE_INADEQUATE: (
        "open_orders",
        ("open_order_snapshot_fingerprint",),
    ),
    RiskReasonCode.QUOTE_COVERAGE_INADEQUATE: (
        "quotes",
        ("quote_snapshot_fingerprint",),
    ),
    RiskReasonCode.QUOTE_MISSING: ("quotes", ("quote_snapshot_fingerprint",)),
    RiskReasonCode.QUOTE_INSUFFICIENT: ("quotes", ("quote_snapshot_fingerprint",)),
}

def _finding_subject(reason: RiskReasonCode) -> str:
    return _FINDING_SPEC[reason][0]


def _finding_reference_fields(
    reason: RiskReasonCode,
) -> tuple[str, ...] | None:
    return _FINDING_SPEC[reason][1]


_CANONICAL_RESULT_TOKEN = object()
_CANONICAL_RESULT_CONSTRUCTION_SENTINEL = object()


@dataclass(frozen=True, slots=True, init=False)
class _CanonicalRiskResult:
    context_fingerprint: str
    outcome: RiskDecisionOutcome
    findings: tuple[RiskFinding, ...]
    common_account_fingerprint: str | None
    _constructor_state: tuple[object, ...] = field(repr=False, compare=False)
    _constructor_binding: tuple[object, object] = field(repr=False, compare=False)
    _token: object = field(repr=False, compare=False)

    def __init__(self) -> None:
        raise TypeError("canonical structural risk results are evaluator-owned")

    @classmethod
    def _create(
        cls,
        *,
        context: RiskEvaluationContext,
        outcome: RiskDecisionOutcome,
        findings: list[RiskFinding] | tuple[RiskFinding, ...],
        _token: object,
    ) -> _CanonicalRiskResult:
        if _token is not _CANONICAL_RESULT_TOKEN:
            raise TypeError("canonical structural risk result token is invalid")
        if type(context) is not RiskEvaluationContext:
            raise RiskCorrespondenceError(
                "canonical structural risk result context is invalid"
            )
        if type(outcome) is not RiskDecisionOutcome:
            raise RiskCorrespondenceError(
                "canonical structural risk result outcome is invalid"
            )
        ordered = canonical_findings(findings)
        accounts = (
            context.cash_snapshot.account,
            context.position_snapshot.account,
            context.open_order_snapshot.account,
        )
        common = (
            accounts[0].fingerprint
            if _accounts_correspond(*accounts)
            else None
        )
        constructor_findings = tuple(
            create_finding(
                finding.reason_code,
                finding.subject,
                *finding.evidence_fingerprints,
            )
            for finding in ordered
        )
        constructor_state = (
            context.fingerprint,
            outcome,
            constructor_findings,
            common,
        )
        constructor_binding = (
            _CANONICAL_RESULT_CONSTRUCTION_SENTINEL,
            constructor_state,
        )
        result = object.__new__(cls)
        object.__setattr__(result, "context_fingerprint", context.fingerprint)
        object.__setattr__(result, "outcome", outcome)
        object.__setattr__(result, "findings", ordered)
        object.__setattr__(result, "common_account_fingerprint", common)
        object.__setattr__(result, "_constructor_state", constructor_state)
        object.__setattr__(result, "_constructor_binding", constructor_binding)
        object.__setattr__(result, "_token", _CANONICAL_RESULT_TOKEN)
        return result


def _require_canonical_result(value: object) -> _CanonicalRiskResult:
    if type(value) is not _CanonicalRiskResult:
        raise RiskCorrespondenceError("canonical structural risk result is invalid")
    token = _required_canonical_result_attribute(value, "_token")
    constructor_binding = _required_canonical_result_attribute(
        value, "_constructor_binding"
    )
    constructor_state = _required_canonical_result_attribute(
        value, "_constructor_state"
    )
    context_fingerprint = _required_canonical_result_attribute(
        value, "context_fingerprint"
    )
    outcome = _required_canonical_result_attribute(value, "outcome")
    findings = _required_canonical_result_attribute(value, "findings")
    common_account_fingerprint = _required_canonical_result_attribute(
        value, "common_account_fingerprint"
    )
    if token is not _CANONICAL_RESULT_TOKEN:
        raise RiskCorrespondenceError("canonical structural risk result is invalid")
    if type(constructor_binding) is not tuple or len(constructor_binding) != 2:
        raise RiskCorrespondenceError(
            "canonical structural risk constructor binding is invalid"
        )
    binding_sentinel, bound_constructor_state = constructor_binding
    if (
        binding_sentinel is not _CANONICAL_RESULT_CONSTRUCTION_SENTINEL
        or bound_constructor_state is not constructor_state
    ):
        raise RiskCorrespondenceError(
            "canonical structural risk constructor binding is invalid"
        )
    if type(constructor_state) is not tuple or len(constructor_state) != 4:
        raise RiskCorrespondenceError(
            "canonical structural risk constructor state is invalid"
        )
    (
        constructed_context_fingerprint,
        constructed_outcome,
        constructed_findings,
        constructed_common_account_fingerprint,
    ) = constructor_state
    try:
        required_fingerprint(
            constructed_context_fingerprint,
            "canonical result context fingerprint",
        )
        if type(constructed_outcome) is not RiskDecisionOutcome:
            raise RiskCorrespondenceError(
                "canonical structural risk constructor outcome is invalid"
            )
        if type(constructed_findings) is not tuple:
            raise RiskCorrespondenceError(
                "canonical structural risk constructor findings are invalid"
            )
        ordered = canonical_findings(constructed_findings)
        if ordered != constructed_findings:
            raise RiskCorrespondenceError(
                "canonical structural risk constructor findings are not canonical"
            )
        if constructed_common_account_fingerprint is not None:
            required_fingerprint(
                constructed_common_account_fingerprint,
                "canonical result common account fingerprint",
            )
    except RiskValidationError as error:
        raise RiskCorrespondenceError(
            "canonical structural risk constructor state is invalid"
        ) from error
    if (
        context_fingerprint != constructed_context_fingerprint
        or outcome is not constructed_outcome
        or findings != constructed_findings
        or common_account_fingerprint
        != constructed_common_account_fingerprint
    ):
        raise RiskCorrespondenceError(
            "canonical structural risk result contradicts constructor state"
        )
    return value


def _required_canonical_result_attribute(
    value: _CanonicalRiskResult,
    attribute_name: str,
) -> object:
    try:
        return object.__getattribute__(value, attribute_name)
    except AttributeError as error:
        raise RiskCorrespondenceError(
            "canonical structural risk result is incomplete"
        ) from error


def _canonical_structural_risk_result(
    context: RiskEvaluationContext,
) -> _CanonicalRiskResult:
    context = require_context_correspondence(context)
    findings: list[RiskFinding] = []
    _evaluate_intent(context, findings)
    if findings:
        return _result(context, RiskDecisionOutcome.REJECTED, findings)
    _evaluate_resolution(context, findings)
    if findings:
        return _result(context, RiskDecisionOutcome.INDETERMINATE, findings)
    _evaluate_account(context, findings)
    if findings:
        return _result(context, RiskDecisionOutcome.INDETERMINATE, findings)
    _evaluate_freshness_and_skew(context, findings)
    _evaluate_coverage(context, findings)
    _evaluate_quote(context, findings)
    outcome = (
        RiskDecisionOutcome.INDETERMINATE if findings else RiskDecisionOutcome.APPROVED
    )
    return _result(context, outcome, findings)


def _result(
    context: RiskEvaluationContext,
    outcome: RiskDecisionOutcome,
    findings: list[RiskFinding],
) -> _CanonicalRiskResult:
    return _CanonicalRiskResult._create(
        context=context,
        outcome=outcome,
        findings=findings,
        _token=_CANONICAL_RESULT_TOKEN,
    )


def _evaluate_intent(
    context: RiskEvaluationContext,
    findings: list[RiskFinding],
) -> None:
    intent = context.order_intent
    as_of = context.evaluation_as_of
    if as_of < intent.decision_as_of or as_of < intent.source_signal.valid_from:
        findings.append(
            create_finding(
                RiskReasonCode.INTENT_NOT_YET_VALID,
                "intent",
                intent.intent_fingerprint,
            )
        )
    elif as_of >= intent.source_signal.expires_at:
        findings.append(
            create_finding(
                RiskReasonCode.INTENT_EXPIRED,
                "intent",
                intent.intent_fingerprint,
            )
        )


def _evaluate_resolution(
    context: RiskEvaluationContext,
    findings: list[RiskFinding],
) -> None:
    resolution = context.instrument_resolution
    mapping = resolution.mapping
    if resolution.resolved_as_of > context.evaluation_as_of:
        findings.append(
            create_finding(
                RiskReasonCode.RESOLUTION_FUTURE_DATED,
                "mapping",
                mapping.fingerprint,
            )
        )
    if not mapping.is_active(context.evaluation_as_of):
        findings.append(
            create_finding(
                RiskReasonCode.MAPPING_INACTIVE,
                "mapping",
                mapping.fingerprint,
            )
        )
    expected = mapping.canonical_instrument.trading_identity
    actual = context.order_intent.instrument
    if type(actual) is not type(expected) or actual.to_dict() != expected.to_dict():
        findings.append(
            create_finding(
                RiskReasonCode.INSTRUMENT_MISMATCH,
                "instrument",
                actual.instrument_fingerprint,
                expected.instrument_fingerprint,
            )
        )


def _evaluate_account(
    context: RiskEvaluationContext,
    findings: list[RiskFinding],
) -> None:
    accounts = (
        context.cash_snapshot.account,
        context.position_snapshot.account,
        context.open_order_snapshot.account,
    )
    if not _accounts_correspond(*accounts):
        findings.append(
            create_finding(
                RiskReasonCode.ACCOUNT_MISMATCH,
                "account",
                *tuple(sorted({account.fingerprint for account in accounts})),
            )
        )


def _evaluate_freshness_and_skew(
    context: RiskEvaluationContext,
    findings: list[RiskFinding],
) -> None:
    checks = (
        (
            context.cash_snapshot,
            context.policy.maximum_cash_age,
            RiskReasonCode.CASH_FUTURE_DATED,
            RiskReasonCode.CASH_STALE,
            "cash",
        ),
        (
            context.position_snapshot,
            context.policy.maximum_position_age,
            RiskReasonCode.POSITION_FUTURE_DATED,
            RiskReasonCode.POSITION_STALE,
            "positions",
        ),
        (
            context.open_order_snapshot,
            context.policy.maximum_open_order_age,
            RiskReasonCode.OPEN_ORDER_FUTURE_DATED,
            RiskReasonCode.OPEN_ORDER_STALE,
            "open_orders",
        ),
        (
            context.quote_snapshot,
            context.policy.maximum_quote_age,
            RiskReasonCode.QUOTE_FUTURE_DATED,
            RiskReasonCode.QUOTE_STALE,
            "quotes",
        ),
    )
    for snapshot, maximum, future_code, stale_code, subject in checks:
        freshness = evaluate_snapshot_freshness(
            snapshot.as_of, context.evaluation_as_of, maximum
        )
        if freshness is SnapshotFreshness.FUTURE_DATED:
            findings.append(create_finding(future_code, subject, snapshot.fingerprint))
        elif freshness is SnapshotFreshness.STALE:
            findings.append(create_finding(stale_code, subject, snapshot.fingerprint))
    snapshots = (
        context.cash_snapshot,
        context.position_snapshot,
        context.open_order_snapshot,
        context.quote_snapshot,
    )
    skew = evaluate_snapshot_skew(
        [snapshot.as_of for snapshot in snapshots],
        context.policy.maximum_state_skew,
    )
    if skew is SnapshotSkew.EXCESSIVE_SKEW:
        findings.append(
            create_finding(
                RiskReasonCode.EXCESSIVE_STATE_SKEW,
                "state",
                *(snapshot.fingerprint for snapshot in snapshots),
            )
        )


def _evaluate_coverage(
    context: RiskEvaluationContext,
    findings: list[RiskFinding],
) -> None:
    checks = (
        (
            context.coverage.cash,
            EvidenceCoverageScope.COMPLETE_ACCOUNT,
            RiskReasonCode.CASH_COVERAGE_INADEQUATE,
            "cash",
            context.cash_snapshot.fingerprint,
        ),
        (
            context.coverage.positions,
            EvidenceCoverageScope.COMPLETE_ACCOUNT,
            RiskReasonCode.POSITION_COVERAGE_INADEQUATE,
            "positions",
            context.position_snapshot.fingerprint,
        ),
        (
            context.coverage.open_orders,
            EvidenceCoverageScope.COMPLETE_ACCOUNT,
            RiskReasonCode.OPEN_ORDER_COVERAGE_INADEQUATE,
            "open_orders",
            context.open_order_snapshot.fingerprint,
        ),
        (
            context.coverage.quotes,
            EvidenceCoverageScope.TARGET_INSTRUMENT,
            RiskReasonCode.QUOTE_COVERAGE_INADEQUATE,
            "quotes",
            context.quote_snapshot.fingerprint,
        ),
    )
    for actual, expected, reason, subject, fingerprint in checks:
        if actual is not expected:
            findings.append(create_finding(reason, subject, fingerprint))


def _evaluate_quote(
    context: RiskEvaluationContext,
    findings: list[RiskFinding],
) -> None:
    if context.coverage.quotes is not EvidenceCoverageScope.TARGET_INSTRUMENT:
        return
    target = context.instrument_resolution.mapping.canonical_instrument.instrument_id
    quote = next(
        (
            item
            for item in context.quote_snapshot.quotes
            if item.instrument_id == target
            and item.instrument_id.to_dict() == target.to_dict()
        ),
        None,
    )
    if quote is None:
        findings.append(
            create_finding(
                RiskReasonCode.QUOTE_MISSING,
                "quotes",
                context.quote_snapshot.fingerprint,
            )
        )
        return
    requirement = context.policy.quote_requirement
    insufficient = (
        requirement is QuoteEvidenceRequirement.LAST and quote.last is None
    ) or (
        requirement is QuoteEvidenceRequirement.BID_AND_ASK
        and (quote.bid is None or quote.ask is None)
    )
    if insufficient:
        findings.append(
            create_finding(
                RiskReasonCode.QUOTE_INSUFFICIENT,
                "quotes",
                context.quote_snapshot.fingerprint,
            )
        )


@dataclass(frozen=True, slots=True, init=False)
class RiskDecision:
    """Point-in-time structural eligibility evidence, never submission authority."""

    outcome: RiskDecisionOutcome
    context_fingerprint: str
    order_intent_fingerprint: str
    source_signal_fingerprint: str
    mapping_fingerprint: str
    canonical_instrument_id: CanonicalInstrumentId
    canonical_instrument_fingerprint: str
    cash_account_fingerprint: str
    position_account_fingerprint: str
    open_order_account_fingerprint: str
    common_account_fingerprint: str | None
    cash_snapshot_fingerprint: str
    position_snapshot_fingerprint: str
    open_order_snapshot_fingerprint: str
    quote_snapshot_fingerprint: str
    policy_fingerprint: str
    evaluation_as_of: datetime
    findings: tuple[RiskFinding, ...]
    _canonical_result: _CanonicalRiskResult = field(repr=False, compare=False)
    schema_version: str = field(init=False)
    fingerprint: str = field(init=False)

    def __init__(self) -> None:
        raise TypeError("RiskDecision must be created by evaluate_structural_risk()")

    @classmethod
    def _create(
        cls,
        *,
        context: RiskEvaluationContext,
        canonical_result: _CanonicalRiskResult,
        _token: object,
    ) -> RiskDecision:
        if _token is not _DECISION_TOKEN:
            raise TypeError("RiskDecision construction is evaluator-owned")
        result = _require_canonical_result(canonical_result)
        if result.context_fingerprint != context.fingerprint:
            raise RiskCorrespondenceError(
                "canonical result does not belong to risk context"
            )
        mapping = context.instrument_resolution.mapping
        canonical = mapping.canonical_instrument
        cash_account = context.cash_snapshot.account
        position_account = context.position_snapshot.account
        order_account = context.open_order_snapshot.account
        decision = object.__new__(cls)
        values: dict[str, object] = {
            "outcome": result.outcome,
            "context_fingerprint": context.fingerprint,
            "order_intent_fingerprint": context.order_intent.intent_fingerprint,
            "source_signal_fingerprint": context.order_intent.source_signal_fingerprint,
            "mapping_fingerprint": mapping.fingerprint,
            "canonical_instrument_id": canonical.instrument_id,
            "canonical_instrument_fingerprint": canonical.fingerprint,
            "cash_account_fingerprint": cash_account.fingerprint,
            "position_account_fingerprint": position_account.fingerprint,
            "open_order_account_fingerprint": order_account.fingerprint,
            "common_account_fingerprint": result.common_account_fingerprint,
            "cash_snapshot_fingerprint": context.cash_snapshot.fingerprint,
            "position_snapshot_fingerprint": context.position_snapshot.fingerprint,
            "open_order_snapshot_fingerprint": context.open_order_snapshot.fingerprint,
            "quote_snapshot_fingerprint": context.quote_snapshot.fingerprint,
            "policy_fingerprint": context.policy.fingerprint,
            "evaluation_as_of": context.evaluation_as_of,
            "findings": result.findings,
            "_canonical_result": result,
            "schema_version": RISK_DECISION_SCHEMA_VERSION,
        }
        for name, value in values.items():
            object.__setattr__(decision, name, value)
        object.__setattr__(
            decision,
            "fingerprint",
            canonical_fingerprint(decision._fingerprint_payload()),
        )
        decision._validate(context, canonical_result=result)
        return decision

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "outcome": self.outcome.value,
            "context_fingerprint": self.context_fingerprint,
            "order_intent_fingerprint": self.order_intent_fingerprint,
            "source_signal_fingerprint": self.source_signal_fingerprint,
            "mapping_fingerprint": self.mapping_fingerprint,
            "canonical_instrument_id": self.canonical_instrument_id.to_dict(),
            "canonical_instrument_fingerprint": self.canonical_instrument_fingerprint,
            "cash_account_fingerprint": self.cash_account_fingerprint,
            "position_account_fingerprint": self.position_account_fingerprint,
            "open_order_account_fingerprint": self.open_order_account_fingerprint,
            "common_account_fingerprint": self.common_account_fingerprint,
            "cash_snapshot_fingerprint": self.cash_snapshot_fingerprint,
            "position_snapshot_fingerprint": self.position_snapshot_fingerprint,
            "open_order_snapshot_fingerprint": self.open_order_snapshot_fingerprint,
            "quote_snapshot_fingerprint": self.quote_snapshot_fingerprint,
            "policy_fingerprint": self.policy_fingerprint,
            "evaluation_as_of": timestamp_text(self.evaluation_as_of),
            "findings": [finding.to_dict() for finding in self.findings],
        }

    def _validate(
        self,
        context: RiskEvaluationContext | None = None,
        *,
        canonical_result: _CanonicalRiskResult | None = None,
    ) -> None:
        try:
            retained_result = object.__getattribute__(self, "_canonical_result")
        except AttributeError as error:
            raise RiskCorrespondenceError(
                "risk decision canonical result attestation is missing"
            ) from error
        retained_result = _require_canonical_result(retained_result)
        if retained_result.context_fingerprint != self.context_fingerprint:
            raise RiskCorrespondenceError(
                "risk decision canonical result belongs to another context"
            )
        if (
            self.outcome is not retained_result.outcome
            or self.findings != retained_result.findings
            or self.common_account_fingerprint
            != retained_result.common_account_fingerprint
        ):
            raise RiskCorrespondenceError(
                "risk decision contradicts its canonical result attestation"
            )
        if self.schema_version != RISK_DECISION_SCHEMA_VERSION:
            raise RiskCorrespondenceError("risk decision schema_version is invalid")
        if type(self.outcome) is not RiskDecisionOutcome:
            raise RiskCorrespondenceError("risk decision outcome is invalid")
        if type(self.canonical_instrument_id) is not CanonicalInstrumentId:
            raise RiskCorrespondenceError("canonical instrument ID has invalid type")
        try:
            reconstructed_id = CanonicalInstrumentId(
                self.canonical_instrument_id.instrument_id
            )
            require_canonical_timestamp(self.evaluation_as_of, "evaluation_as_of")
            for name in _REQUIRED_FINGERPRINT_FIELDS:
                required_fingerprint(getattr(self, name), name)
            if self.common_account_fingerprint is not None:
                required_fingerprint(
                    self.common_account_fingerprint,
                    "common_account_fingerprint",
                )
            ordered = canonical_findings(self.findings)
        except (TypeError, ValueError) as error:
            raise RiskCorrespondenceError(
                "risk decision retains invalid canonical state"
            ) from error
        if reconstructed_id.to_dict() != self.canonical_instrument_id.to_dict():
            raise RiskCorrespondenceError("canonical instrument ID is not canonical")
        if ordered != self.findings:
            raise RiskCorrespondenceError("risk decision findings are not canonical")
        self._validate_finding_references()
        reasons = {finding.reason_code for finding in self.findings}
        rejected = bool(reasons & _REJECTED_REASONS)
        account_mismatch = RiskReasonCode.ACCOUNT_MISMATCH in reasons
        accounts_match = (
            self.cash_account_fingerprint
            == self.position_account_fingerprint
            == self.open_order_account_fingerprint
        )
        if self.outcome is RiskDecisionOutcome.APPROVED:
            if self.findings or not accounts_match:
                raise RiskCorrespondenceError("approved decision state is impossible")
        elif self.outcome is RiskDecisionOutcome.REJECTED:
            if len(self.findings) != 1 or not rejected:
                raise RiskCorrespondenceError(
                    "rejected decision must contain one intent reason"
                )
        elif not self.findings or rejected:
            raise RiskCorrespondenceError("indeterminate decision state is impossible")
        elif reasons & _RESOLUTION_REASONS:
            if not reasons <= _RESOLUTION_REASONS:
                raise RiskCorrespondenceError(
                    "resolution-stage decision contains downstream findings"
                )
        elif account_mismatch:
            if reasons != {RiskReasonCode.ACCOUNT_MISMATCH} or accounts_match:
                raise RiskCorrespondenceError(
                    "account-stage decision state is impossible"
                )
        elif not accounts_match:
            raise RiskCorrespondenceError(
                "downstream decision has mismatched accounts without a finding"
            )
        expected_common = self.cash_account_fingerprint if accounts_match else None
        if self.common_account_fingerprint != expected_common:
            raise RiskCorrespondenceError(
                "common account fingerprint does not match individual accounts"
            )
        expected = canonical_fingerprint(self._fingerprint_payload())
        if self.fingerprint != expected:
            raise RiskCorrespondenceError(
                "risk decision fingerprint does not match content"
            )
        if context is not None:
            result = (
                _canonical_structural_risk_result(context)
                if canonical_result is None
                else _require_canonical_result(canonical_result)
            )
            if retained_result != result:
                raise RiskCorrespondenceError(
                    "risk decision attestation contradicts canonical context evaluation"
                )
            if result.context_fingerprint != context.fingerprint:
                raise RiskCorrespondenceError(
                    "canonical result does not belong to risk context"
                )
            self._validate_context_references(context)
            if (
                self.outcome is not result.outcome
                or self.findings != result.findings
                or self.common_account_fingerprint
                != result.common_account_fingerprint
            ):
                raise RiskCorrespondenceError(
                    "risk decision contradicts canonical context evaluation"
                )

    def _validate_finding_references(self) -> None:
        for finding in self.findings:
            reason = finding.reason_code
            if finding.subject != _finding_subject(reason):
                raise RiskCorrespondenceError(
                    "risk decision finding subject is inconsistent"
                )
            field_names = _finding_reference_fields(reason)
            if field_names is None:
                if len(finding.evidence_fingerprints) != 2:
                    raise RiskCorrespondenceError(
                        "instrument mismatch evidence is inconsistent"
                    )
                continue
            expected = tuple(sorted({getattr(self, name) for name in field_names}))
            if finding.evidence_fingerprints != expected:
                raise RiskCorrespondenceError(
                    "risk decision finding evidence is inconsistent"
                )

    def _validate_context_references(self, context: RiskEvaluationContext) -> None:
        expected = {
            "context_fingerprint": context.fingerprint,
            "order_intent_fingerprint": context.order_intent.intent_fingerprint,
            "source_signal_fingerprint": context.order_intent.source_signal_fingerprint,
            "mapping_fingerprint": context.instrument_resolution.mapping.fingerprint,
            "canonical_instrument_fingerprint": (
                context.instrument_resolution.mapping.canonical_instrument.fingerprint
            ),
            "cash_account_fingerprint": context.cash_snapshot.account.fingerprint,
            "position_account_fingerprint": (
                context.position_snapshot.account.fingerprint
            ),
            "open_order_account_fingerprint": (
                context.open_order_snapshot.account.fingerprint
            ),
            "cash_snapshot_fingerprint": context.cash_snapshot.fingerprint,
            "position_snapshot_fingerprint": context.position_snapshot.fingerprint,
            "open_order_snapshot_fingerprint": context.open_order_snapshot.fingerprint,
            "quote_snapshot_fingerprint": context.quote_snapshot.fingerprint,
            "policy_fingerprint": context.policy.fingerprint,
        }
        if any(getattr(self, name) != value for name, value in expected.items()):
            raise RiskCorrespondenceError(
                "risk decision evidence references context incorrectly"
            )
        canonical_id = (
            context.instrument_resolution.mapping.canonical_instrument.instrument_id
        )
        if self.canonical_instrument_id.to_dict() != canonical_id.to_dict():
            raise RiskCorrespondenceError("risk decision instrument ID is inconsistent")
        if self.evaluation_as_of != context.evaluation_as_of:
            raise RiskCorrespondenceError(
                "risk decision evaluation time is inconsistent"
            )
        canonical = context.instrument_resolution.mapping.canonical_instrument
        expected_instrument_evidence = tuple(
            sorted(
                {
                    context.order_intent.instrument.instrument_fingerprint,
                    canonical.trading_identity.instrument_fingerprint,
                }
            )
        )
        for finding in self.findings:
            if (
                finding.reason_code is RiskReasonCode.INSTRUMENT_MISMATCH
                and finding.evidence_fingerprints != expected_instrument_evidence
            ):
                raise RiskCorrespondenceError(
                    "instrument mismatch evidence is inconsistent"
                )

    def to_dict(self) -> dict[str, object]:
        """Return the bounded deterministic decision projection."""

        self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


_REQUIRED_FINGERPRINT_FIELDS = (
    "context_fingerprint",
    "order_intent_fingerprint",
    "source_signal_fingerprint",
    "mapping_fingerprint",
    "canonical_instrument_fingerprint",
    "cash_account_fingerprint",
    "position_account_fingerprint",
    "open_order_account_fingerprint",
    "cash_snapshot_fingerprint",
    "position_snapshot_fingerprint",
    "open_order_snapshot_fingerprint",
    "quote_snapshot_fingerprint",
    "policy_fingerprint",
)


def create_risk_decision(
    context: RiskEvaluationContext,
    outcome: RiskDecisionOutcome,
    findings: list[RiskFinding] | tuple[RiskFinding, ...],
) -> RiskDecision:
    if type(outcome) is not RiskDecisionOutcome:
        raise RiskValidationError("outcome must be a RiskDecisionOutcome")
    canonical_result = _canonical_structural_risk_result(context)
    supplied = canonical_findings(findings)
    if type(findings) not in (list, tuple) or tuple(findings) != supplied:
        raise RiskCorrespondenceError("supplied findings are not canonically ordered")
    if outcome is not canonical_result.outcome or supplied != canonical_result.findings:
        raise RiskCorrespondenceError(
            "supplied decision result contradicts canonical context evaluation"
        )
    return RiskDecision._create(
        context=context,
        canonical_result=canonical_result,
        _token=_DECISION_TOKEN,
    )


def _create_risk_decision_from_canonical_result(
    context: RiskEvaluationContext,
    canonical_result: _CanonicalRiskResult,
) -> RiskDecision:
    result = _require_canonical_result(canonical_result)
    if result.context_fingerprint != context.fingerprint:
        raise RiskCorrespondenceError(
            "canonical result does not belong to risk context"
        )
    return RiskDecision._create(
        context=context,
        canonical_result=result,
        _token=_DECISION_TOKEN,
    )


def _accounts_correspond(
    first: TradingAccountIdentity,
    second: TradingAccountIdentity,
    third: TradingAccountIdentity,
) -> bool:
    return (
        type(first) is type(second)
        and type(first) is type(third)
        and first == second
        and first == third
        and first.to_dict() == second.to_dict() == third.to_dict()
    )


__all__ = ["RISK_DECISION_SCHEMA_VERSION", "RiskDecision"]
