"""Pure source-acquisition to Candidate Evidence ingress boundaries."""

from market_platform.evidence_ingress.polygon_completed_daily_ohlcv import (
    MAX_CANONICAL_NUMERIC_TEXT_LENGTH,
    PolygonCompletedDailyOhlcvEvidenceIngressResult,
    PolygonCompletedDailyOhlcvMaterial,
    PolygonCompletedDailyOhlcvMaterialRow,
    create_polygon_completed_daily_ohlcv_evidence,
)

__all__ = [
    "MAX_CANONICAL_NUMERIC_TEXT_LENGTH",
    "PolygonCompletedDailyOhlcvEvidenceIngressResult",
    "PolygonCompletedDailyOhlcvMaterial",
    "PolygonCompletedDailyOhlcvMaterialRow",
    "create_polygon_completed_daily_ohlcv_evidence",
]
