"""Private construction boundary for the governed Polygon daily contract."""

from market_platform.evidence.authorization import (
    _POLYGON_COMPLETED_DAILY_OHLCV_AUTHORIZATION,
)
from market_platform.evidence.models import (
    EvidenceArtifact as _EvidenceArtifact,
)
from market_platform.evidence.models import (
    EvidenceProvenance as _EvidenceProvenance,
)
from market_platform.evidence.models import (
    EvidenceTemporalIdentity as _EvidenceTemporalIdentity,
)
from market_platform.evidence.models import (
    _create_evidence_artifact,
)
from market_platform.evidence.references import (
    EvidenceSubjectReference as _EvidenceSubjectReference,
)


def _create_polygon_completed_daily_ohlcv_evidence_artifact(
    *,
    artifact_id: str,
    artifact_version: str,
    subjects: tuple[_EvidenceSubjectReference, ...],
    temporal_identity: _EvidenceTemporalIdentity,
    provenance: _EvidenceProvenance,
    material_fingerprint: str,
) -> _EvidenceArtifact:
    """Mint only the exact production-governed candidate contract."""

    return _create_evidence_artifact(
        artifact_id=artifact_id,
        artifact_version=artifact_version,
        subjects=subjects,
        temporal_identity=temporal_identity,
        provenance=provenance,
        contract_authorization=_POLYGON_COMPLETED_DAILY_OHLCV_AUTHORIZATION,
        material_fingerprint=material_fingerprint,
    )


__all__: list[str] = []
