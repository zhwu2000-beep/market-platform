# ADR 0031: Daily technical strategy foundation

## Status

Accepted for v0.74 implementation.

## Context

The v0.73 domain chain produces a deterministic daily technical interpretation
and a matching coherence assessment. v0.74 adds Strategy Foundation as a
descriptive domain layer above Interpretation and Assessment and below future
Trade Planning. It does not add trading, execution, portfolio, application, or
CLI authority.

Interpretation answers what market state exists. Assessment answers how
coherent, conflicting, incomplete, or cautionary that state is. Strategy
answers what strategy logic is applicable to the interpreted and assessed
state. A future Trade Planning layer may translate Strategy into concrete trade
parameters; that translation is not part of Strategy Foundation.

## Decision

The fixed one-way domain boundary is
`IntegrityCheckedDailyTechnicalResearchResult` ->
`DailyTechnicalInterpretationPolicy` -> `DailyTechnicalInterpretation` ->
`DailyTechnicalAssessmentPolicy` -> `DailyTechnicalAssessment` ->
`DailyTechnicalStrategyPolicy` -> `DailyTechnicalStrategy`.

A Strategy policy consumes a `DailyTechnicalInterpretation` and its matching
`DailyTechnicalAssessment`. Assessment alone is insufficient because it does
not retain every directional semantic required by Strategy. Strategy policies
must not consume raw research or raw technical indicators.

### Strategy value and lineage

`DailyTechnicalStrategy` uses schema `daily_technical_strategy/v1` and retains
exactly:

- `canonical_instrument_id`
- `analysis_as_of`
- `source_assessment_fingerprint`
- `strategy_policy_identity`
- `mode`
- `rule_code`
- fixed `schema_version`
- computed `fingerprint`

Only `source_assessment_fingerprint` is retained as the immediate parent
lineage. Assessment already binds Interpretation, and Interpretation
transitively binds the integrity-checked research lineage. Strategy therefore
does not duplicate `source_interpretation_fingerprint`.

### Typed policy identity

Strategy reuses `technical_policy_identity/v1` and adds
`TechnicalPolicyKind.DAILY_TECHNICAL_STRATEGY`. The classic typed configuration
is `ClassicDailyTechnicalStrategyConfiguration`, with schema
`classic_daily_technical_strategy_configuration/v1`.

The classic policy identity is
`classic_daily_technical_strategy@1.0.0`. Its empty default configuration has
the deterministic identity fingerprint
`sha256:acbdd8c9ac7ba7d336f5f5e74b7484b05d0fc15b3a6f24bc81288d1fc8ea817e`.

### Classic v1 mapping

The mapping is exact:

| Assessment and direction state | Strategy mode | Rule code |
|---|---|---|
| `INSUFFICIENT_DATA` | `NO_ACTIVE_STRATEGY` | `INSUFFICIENT_DATA_NO_ACTIVE_STRATEGY` |
| `MIXED` | `NO_ACTIVE_STRATEGY` | `MIXED_NO_ACTIVE_STRATEGY` |
| `CAUTION` | `NO_ACTIVE_STRATEGY` | `CAUTION_NO_ACTIVE_STRATEGY` |
| `ALIGNED` + positive trend + positive momentum | `POSITIVE_DIRECTIONAL_CONTINUATION` | `ALIGNED_POSITIVE_CONTINUATION` |
| `ALIGNED` + negative trend + negative momentum | `NEGATIVE_DIRECTIONAL_CONTINUATION` | `ALIGNED_NEGATIVE_CONTINUATION` |

The classic policy fails closed for an unsupported `ALIGNED` direction state
or an unsupported future Assessment outcome.

### Semantic authority

`derive_daily_technical_strategy()` validates source coherence and integrity,
but does not independently recompute the classic mode/rule mapping. The
Strategy policy is authoritative for Strategy mode and rule semantics. This
avoids duplicate semantic authority between the hardened runner and the policy.

The hardened runner currently supports the frozen v0.73 classic
Interpretation/Assessment semantic compatibility matrix. This is the current
support matrix, not a permanent claim that the API can only support classic
policies. A future compatible semantic family may require an explicit contract
extension and versioned support decision.

### Integrity boundary

The hardened composition boundary establishes:

- exact Interpretation and Assessment source types and internal validity;
- coherent instrument, time, fingerprint, and finding-evidence source links;
- reconstruction of the complete classic Assessment findings and outcome;
- detached pre-call and post-call source state comparisons;
- exact typed Strategy policy identity validity and identity-drift rejection;
- rejection of changed source semantics even when fingerprints are coherently
  recomputed;
- exactly one `determine()` invocation;
- an exact `DailyTechnicalStrategy` result type, with result/source and
  result/policy correspondence.

These checks use semantic equality rather than Python object identity, so a
canonically identical reconstructed source value is acceptable. Fingerprints
prove deterministic semantic integrity; they do not prove cryptographic
authorship or constructor provenance. A temporary mutation restored exactly
before a successful return remains acceptable. Policy exceptions propagate
unchanged, and the boundary provides no transactional rollback guarantee when
a policy raises.

### Non-actionable vocabulary

`NO_ACTIVE_STRATEGY` means only that the current Strategy policy supports no
active strategy logic for the state. It does not mean `HOLD`, `EXIT`, stay flat,
close a position, retain a position, or any execution or portfolio action.

Positive and negative directional continuation are descriptive Strategy modes.
They are not `BUY`, `SELL`, `LONG`, `SHORT`, position, portfolio, or order
instructions.

## Consequences

- Strategy is a separate domain layer above matching Interpretation and
  Assessment values and below future Trade Planning.
- Strategy policies receive official semantic objects, not raw technical data.
- Immediate-parent lineage remains explicit without duplicating transitive
  lineage.
- The classic Strategy policy remains the sole authority for the classic
  mode/rule mapping; the hardened runner remains mapping-neutral.
- Strategy Foundation creates no broker API, auto trading, order creation,
  order intent, `TradingSignal` integration, position sizing, risk allocation,
  portfolio management, entry price, stop loss, profit target, quantity,
  execution side, `BUY`/`SELL`/`HOLD`, TradingView webhook, AI recommendation,
  application workflow, CLI Strategy command, legacy
  `market_platform.strategy` integration, `ResearchResult.strategy_candidates`
  integration, `ResearchResult.position_actions` integration, or Trade
  Planning scope.
- A later application boundary may compose the domain pipeline. Trade Planning
  remains a separate future layer.
