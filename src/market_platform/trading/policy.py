"""Fixed deterministic signal-to-intent policy."""

from __future__ import annotations

from dataclasses import dataclass, field

from market_platform._fingerprint import canonical_fingerprint

EXACT_TARGET_POSITION_INTENT_POLICY_SCHEMA_VERSION = (
    "exact_target_position_intent_policy/v1"
)
_METHODOLOGY = "exact_target_position"
_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class ExactTargetPositionIntentPolicy:
    """Copy one active signal target into a pre-risk Order Intent."""

    schema_version: str = field(
        init=False,
        default=EXACT_TARGET_POSITION_INTENT_POLICY_SCHEMA_VERSION,
    )
    methodology: str = field(init=False, default=_METHODOLOGY)
    version: str = field(init=False, default=_VERSION)
    policy_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "policy_fingerprint",
            canonical_fingerprint(
                {
                    "schema_version": self.schema_version,
                    "methodology": self.methodology,
                    "version": self.version,
                    "configuration": {},
                }
            ),
        )

    def to_dict(self) -> dict[str, object]:
        """Return the fixed policy identity."""

        return {
            "schema_version": self.schema_version,
            "methodology": self.methodology,
            "version": self.version,
            "policy_fingerprint": self.policy_fingerprint,
        }


__all__ = [
    "EXACT_TARGET_POSITION_INTENT_POLICY_SCHEMA_VERSION",
    "ExactTargetPositionIntentPolicy",
]
