# ADR 0030: Daily technical interpretation and assessment foundation

## Status

Accepted for v0.73 implementation.

## Context

The released v0.70-v0.72 chain produces a deterministic daily technical
snapshot and verifies its instrument-history integrity. v0.73 adds descriptive
interpretation and coherence assessment without strategy or trading authority.

## Decision

The fixed one-way boundary is
`IntegrityCheckedDailyTechnicalResearchResult` ->
`DailyTechnicalInterpretationPolicy` -> `DailyTechnicalInterpretation` ->
`DailyTechnicalAssessmentPolicy` -> `DailyTechnicalAssessment`.

The classic identities are `classic_daily_technical@1.0.0` and
`classic_daily_technical_coherence@1.0.0`. Identity binds the exact policy
kind, ID, revision, typed configuration, configuration schema, and fingerprint.
The supported pairings are closed:

- `daily_technical_interpretation` uses
  `ClassicDailyTechnicalInterpretationConfiguration` with
  `classic_daily_technical_interpretation_configuration/v1`.
- `daily_technical_assessment` uses
  `ClassicDailyTechnicalAssessmentConfiguration` with
  `classic_daily_technical_assessment_configuration/v1`.

### Closed operand grammar

`technical_analysis_snapshot` permits only `ema_8`, `ema_20`, `ema_144`,
`ema_169`, `latest_close`, `macd_line`, `macd_signal`, `rsi_14`,
`realized_volatility`, and
`volatility_references.distance_from_ema20_percent`.

`interpretation_policy_configuration` permits only `rsi_neutral`,
`rsi_elevated`, `rsi_depressed`, `realized_volatility_low`,
`realized_volatility_high`, and `ema20_extension_band_percent`.

`interpretation_policy_derived` permits exactly
`negative_ema20_extension_band_percent`. Its value is the canonical negation
`0.0 - ema20_extension_band_percent` of the validated positive configured
band. There is no expression language, transform, callback, or arbitrary
derivation mechanism.

### Classic comparison inventory

The inventory and order are exact. `snapshot`, `configuration`, and `derived`
refer to the three sources defined above.

| # | Comparison ID | Left operand | Operator | Right operand |
|---:|---|---|---|---|
| 1 | `trend_ema8_above_ema20` | snapshot `ema_8` | `greater_than` | snapshot `ema_20` |
| 2 | `trend_ema8_below_ema20` | snapshot `ema_8` | `less_than` | snapshot `ema_20` |
| 3 | `trend_close_above_ema144` | snapshot `latest_close` | `greater_than` | snapshot `ema_144` |
| 4 | `trend_close_below_ema144` | snapshot `latest_close` | `less_than` | snapshot `ema_144` |
| 5 | `trend_close_above_ema169` | snapshot `latest_close` | `greater_than` | snapshot `ema_169` |
| 6 | `trend_close_below_ema169` | snapshot `latest_close` | `less_than` | snapshot `ema_169` |
| 7 | `momentum_macd_line_above_signal` | snapshot `macd_line` | `greater_than` | snapshot `macd_signal` |
| 8 | `momentum_macd_line_below_signal` | snapshot `macd_line` | `less_than` | snapshot `macd_signal` |
| 9 | `momentum_rsi_at_or_above_neutral` | snapshot `rsi_14` | `greater_than_or_equal` | configuration `rsi_neutral` |
| 10 | `momentum_rsi_below_neutral` | snapshot `rsi_14` | `less_than` | configuration `rsi_neutral` |
| 11 | `rsi_at_or_above_elevated` | snapshot `rsi_14` | `greater_than_or_equal` | configuration `rsi_elevated` |
| 12 | `rsi_at_or_below_depressed` | snapshot `rsi_14` | `less_than_or_equal` | configuration `rsi_depressed` |
| 13 | `volatility_below_low` | snapshot `realized_volatility` | `less_than` | configuration `realized_volatility_low` |
| 14 | `volatility_at_or_above_low` | snapshot `realized_volatility` | `greater_than_or_equal` | configuration `realized_volatility_low` |
| 15 | `volatility_below_high` | snapshot `realized_volatility` | `less_than` | configuration `realized_volatility_high` |
| 16 | `volatility_at_or_above_high` | snapshot `realized_volatility` | `greater_than_or_equal` | configuration `realized_volatility_high` |
| 17 | `extension_above_positive_band` | snapshot `volatility_references.distance_from_ema20_percent` | `greater_than` | configuration `ema20_extension_band_percent` |
| 18 | `extension_below_negative_band` | snapshot `volatility_references.distance_from_ema20_percent` | `less_than` | derived `negative_ema20_extension_band_percent` |

Both satisfied and unsatisfied comparisons are retained. Omission occurs only
when a required snapshot operand is unavailable. Configuration and derived
operands are available after validation. Retained comparisons preserve table
order; omission does not reorder the remainder.

### Classic assessment finding inventory

Every independently true finding is retained in this exact order:

| # | Kind/code | Exact trigger | Exact evidence references |
|---:|---|---|---|
| 1 | `conflict/direction_opposition` | trend positive and momentum negative, or trend negative and momentum positive | the five satisfied comparisons supporting those directions |
| 2 | `caution/rsi_elevated` | `rsi_at_or_above_elevated` satisfied | `rsi_at_or_above_elevated` |
| 3 | `caution/rsi_depressed` | `rsi_at_or_below_depressed` satisfied | `rsi_at_or_below_depressed` |
| 4 | `caution/ema20_above_reference_band` | `extension_above_positive_band` satisfied | `extension_above_positive_band` |
| 5 | `caution/ema20_below_reference_band` | `extension_below_negative_band` satisfied | `extension_below_negative_band` |
| 6 | `caution/high_realized_volatility` | `volatility_at_or_above_high` satisfied | `volatility_at_or_above_high` |
| 7 | `caution/source_quality_degraded` | source quality is `degraded` | none (exactly zero) |
| 8 | `caution/source_warning_insufficient_profile_history` | warnings contain `insufficient_profile_history` | none (exactly zero) |
| 9 | `caution/source_warning_stale_evidence` | warnings contain `stale_evidence` | none (exactly zero) |

Positive-trend/negative-momentum opposition references
`trend_ema8_above_ema20`, `trend_close_above_ema144`,
`trend_close_above_ema169`, `momentum_macd_line_below_signal`, and
`momentum_rsi_below_neutral`. Negative-trend/positive-momentum opposition
references `trend_ema8_below_ema20`, `trend_close_below_ema144`,
`trend_close_below_ema169`, `momentum_macd_line_above_signal`, and
`momentum_rsi_at_or_above_neutral`.

Conflict may coexist with every independent caution. Mixed and unavailable
outcomes do not suppress cautions. Both source warnings may coexist.
`source_quality_degraded` may coexist with source-warning cautions. No finding
is generated solely because a state is mixed or unavailable.

### Outcome predicates and precedence

`has_unavailable` is true when trend, momentum, volatility, or extension is
unavailable. `has_mixed` is true when trend is mixed, momentum is mixed, or
`direction_opposition` exists. `has_caution` is true when any caution exists.

Precedence is exact:

1. `insufficient_data` when `has_unavailable`;
2. `mixed` when `has_mixed`;
3. `caution` when `has_caution`;
4. `aligned` otherwise.

Negative plus negative may be aligned. Aligned is direction-neutral and is not
a trading instruction.

### Configuration compatibility

`classic_daily_technical_coherence@1.0.0` is configuration-value-agnostic
within `classic_daily_technical_interpretation_configuration/v1`. It accepts
non-default valid values and reasons from actual validated states and evidence.
It does not assume 70/30, 0.15/0.30, or 5.0.

### Detached policy identity and source authority

Both runners capture and validate detached pre-call and post-call policy
identities and reject identity drift. Both also establish detached source
authority before invocation. The interpretation runner captures the complete
integrity-checked carrier semantics, including identities, time, source
fingerprints, quality, warnings, and all classic scalar inputs. The assessment
runner captures complete source interpretation semantics and computes classic
compatibility, expected findings, and expected outcome before invocation.

Policy calls may not redefine input source semantics. Each live source is fully
revalidated post-call, its detached post-call projection must equal its pre-call
projection, and persistent source mutation is rejected. Result correspondence
and all evidence, state, finding, and outcome expectations use only detached
pre-call semantics.

### Fingerprint families

v0.73 introduces exactly:

- `technical_policy_identity/v1`
- `daily_technical_interpretation/v1`
- `daily_technical_assessment/v1`

v0.73 does not create an evidence fingerprint, finding fingerprint,
configuration fingerprint, or verified-carrier fingerprint.

## Consequences

- Policy behavior and configuration are explicit and fingerprint-visible.
- Source quality and the complete ordered warning tuple remain exact upstream
  facts.
- Result fingerprints do not replace explicit source correspondence checks.
- There is no CLI, persistence, expression engine, strategy, trading,
  watchlist, UI, AI, recommendation, signal, order, or portfolio scope.
