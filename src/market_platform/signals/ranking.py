"""Classification ranking helpers."""

from __future__ import annotations

from enum import StrEnum

from market_platform.signals.batch import SignalClassificationSnapshot


class SignalClassificationSort(StrEnum):
    """Supported sort orders for composite signal classifications."""

    INPUT = "input"
    SCORE_DESC = "score-desc"
    SCORE_ASC = "score-asc"


def sort_signal_classifications(
    snapshot: SignalClassificationSnapshot,
    order: SignalClassificationSort = SignalClassificationSort.INPUT,
) -> SignalClassificationSnapshot:
    """Return a classification snapshot ordered according to the requested sort."""

    if order is SignalClassificationSort.INPUT:
        return snapshot

    indexed_classifications = list(enumerate(snapshot.classifications))
    if order is SignalClassificationSort.SCORE_DESC:
        sorted_classifications = tuple(
            classification
            for _, classification in sorted(
                indexed_classifications,
                key=lambda item: (-item[1].score, item[0]),
            )
        )
    elif order is SignalClassificationSort.SCORE_ASC:
        sorted_classifications = tuple(
            classification
            for _, classification in sorted(
                indexed_classifications,
                key=lambda item: (item[1].score, item[0]),
            )
        )
    else:  # pragma: no cover - defensive branch for future enum additions.
        raise ValueError(f"Unsupported classification sort order: {order}")

    return SignalClassificationSnapshot(
        classifications=sorted_classifications,
        thresholds=snapshot.thresholds,
    )
