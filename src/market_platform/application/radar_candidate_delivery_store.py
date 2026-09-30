"""Immutable local delivery records under a caller-provisioned trusted root.

One non-overlapping owner per instrument. File fsync and no-clobber hard links
provide process-interruption recovery, not directory fsync, universal power-loss
durability, malicious-tamper protection, or concurrent-writer coordination.
"""

from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from contextlib import suppress
from pathlib import Path

from market_platform._fingerprint import canonical_fingerprint
from market_platform.application.radar_candidate_delivery import (
    AcceptedSource,
    CandidateDecisionRecord,
    DeliveryFailure,
    DeliveryRecord,
    PendingCandidateWork,
    PreparedSourceIntent,
    RadarCandidateDeliveryError,
    SourceRecoveryIdentity,
    _canonical,
    _decode_record,
    _equal,
    _fingerprint,
    _verify_links,
)
from market_platform.instruments.identity import CanonicalInstrumentId


def _instrument_key(instrument: CanonicalInstrumentId) -> str:
    if type(instrument) is not CanonicalInstrumentId:
        raise TypeError("Expected canonical instrument")
    checked = CanonicalInstrumentId(instrument.instrument_id)
    return canonical_fingerprint(
        {
            "schema_version": "radar_delivery_instrument_path/v1",
            "instrument": checked.to_dict(),
        }
    )[7:]


def _identity_key(identity: SourceRecoveryIdentity) -> str:
    if type(identity) is not SourceRecoveryIdentity:
        raise TypeError("Expected recovery identity")
    return _fingerprint(identity.fingerprint)[7:]


def _filename(record: DeliveryRecord) -> str:
    if type(record) is PreparedSourceIntent:
        return (
            f"prepared-{_instrument_key(record.instrument)}-"
            f"{_identity_key(record.identity)}.json"
        )
    if type(record) is AcceptedSource:
        return f"accepted-{_identity_key(record.source_identity)}.json"
    if type(record) is CandidateDecisionRecord:
        return f"decision-{_identity_key(record.source_identity)}.json"
    if type(record) is PendingCandidateWork:
        return f"pending-{_fingerprint(record.candidate_fingerprint)[7:]}.json"
    raise TypeError("Expected delivery record")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate delivery JSON key")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise ValueError("Non-finite delivery JSON number")


def _safe(info: os.stat_result, *, directory: bool = False) -> None:
    valid = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not valid or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError("Delivery entry must be regular and non-reparse")


class RadarCandidateDeliveryUnavailableError(RuntimeError):
    """Pending lookup cannot establish availability; no contradiction is claimed.

    Used only by read-only resolution, without changing publication/recovery errors.
    Missing Pending or a lost/inaccessible trusted owner is not corrupt authority.
    """


class RadarCandidateDeliveryFileStore:
    """No root creation, deletion, secondary index, or generic repository API."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self._root = Path(root)
        if not self._root.is_absolute():
            raise ValueError("Delivery root must be absolute")

    def _check_root(self) -> None:
        _safe(self._root.lstat(), directory=True)
        with os.scandir(self._root):
            pass

    def _read(self, name: str) -> DeliveryRecord | None:
        try:
            self._check_root()
            target = self._root / name
            try:
                info = target.lstat()
            except FileNotFoundError:
                self._check_root()
                return None
            _safe(info)
            with target.open("rb") as stream:
                _safe(os.fstat(stream.fileno()))
                raw = stream.read()
            record = _decode_record(
                json.loads(
                    raw.decode("utf-8"),
                    object_pairs_hook=_unique_object,
                    parse_constant=_reject_constant,
                )
            )
            if name != _filename(record):
                raise ValueError("Delivery filename/content mismatch")
            return record
        except RadarCandidateDeliveryError:
            raise
        except Exception as exc:
            raise RadarCandidateDeliveryError(DeliveryFailure.INVARIANT) from exc

    def _publish(self, record: DeliveryRecord) -> None:
        # Detach/revalidate before any filesystem mutation, including digest fields.
        record = _decode_record(record.to_dict())
        name = _filename(record)
        existing = self._read(name)
        if existing is not None:
            self._same(existing, record)
            return
        temporary: Path | None = None
        try:
            descriptor, path = tempfile.mkstemp(
                prefix=".delivery-", suffix=".tmp", dir=self._root
            )
            temporary = Path(path)
            try:
                stream = os.fdopen(descriptor, "wb")
            except Exception:
                os.close(descriptor)
                raise
            with stream:
                stream.write((_canonical(record.to_dict()) + "\n").encode("utf-8"))
                stream.flush()
                os.fsync(stream.fileno())
            # Same filesystem, create-if-absent. Never replace immutable history.
            with suppress(FileExistsError):
                os.link(temporary, self._root / name)
            published = self._read(name)
            if published is None:
                raise ValueError("Publication missing on read-back")
            self._same(published, record)
        finally:
            if temporary is not None:
                with suppress(OSError):
                    temporary.unlink()

    @staticmethod
    def _same(existing: DeliveryRecord, proposed: DeliveryRecord) -> None:
        if not _equal(existing.to_dict(), proposed.to_dict()):
            raise RadarCandidateDeliveryError(DeliveryFailure.CONFLICT)

    def publish_prepared(self, source: PreparedSourceIntent) -> None:
        self._publish(source)

    def publish_accepted(self, accepted: AcceptedSource) -> None:
        self._publish(accepted)

    def publish_decision(self, decision: CandidateDecisionRecord) -> None:
        self._publish(decision)

    def publish_pending(self, pending: PendingCandidateWork) -> None:
        self._publish(pending)

    def read_prepared(
        self, instrument: CanonicalInstrumentId, identity: SourceRecoveryIdentity
    ) -> PreparedSourceIntent | None:
        result = self._read(
            f"prepared-{_instrument_key(instrument)}-{_identity_key(identity)}.json"
        )
        if result is not None and type(result) is not PreparedSourceIntent:
            raise RadarCandidateDeliveryError(DeliveryFailure.INVARIANT)
        return result

    def read_accepted(self, identity: SourceRecoveryIdentity) -> AcceptedSource | None:
        result = self._read(f"accepted-{_identity_key(identity)}.json")
        if result is not None and type(result) is not AcceptedSource:
            raise RadarCandidateDeliveryError(DeliveryFailure.INVARIANT)
        return result

    def read_decision(
        self, identity: SourceRecoveryIdentity
    ) -> CandidateDecisionRecord | None:
        result = self._read(f"decision-{_identity_key(identity)}.json")
        if result is not None and type(result) is not CandidateDecisionRecord:
            raise RadarCandidateDeliveryError(DeliveryFailure.INVARIANT)
        return result

    def read_pending(self, candidate_fingerprint: str) -> PendingCandidateWork | None:
        result = self._read(f"pending-{_fingerprint(candidate_fingerprint)[7:]}.json")
        if result is not None and type(result) is not PendingCandidateWork:
            raise RadarCandidateDeliveryError(DeliveryFailure.INVARIANT)
        return result

    def resolve_pending(
        self,
        candidate_fingerprint: str,
        source_identity: SourceRecoveryIdentity,
    ) -> PendingCandidateWork | None:
        """Authenticate retained Pending through the complete owned inventory.

        Individual reads and caller records are insufficient. Preserve inventory
        failure precedence, including orphan/corrupt records even when the requested
        Pending is absent. Historical graphs need no current checkpoint or policy.
        This read neither completes publication nor consumes or repairs records.
        """
        try:
            _fingerprint(candidate_fingerprint)
            _identity_key(source_identity)
            try:
                self._check_root()
            except OSError as exc:
                raise RadarCandidateDeliveryUnavailableError(
                    "Trusted delivery root unavailable"
                ) from exc
        except RadarCandidateDeliveryUnavailableError:
            raise
        except Exception as exc:
            raise RadarCandidateDeliveryError(DeliveryFailure.INVARIANT) from exc
        try:
            records = self._inventory()
        except RadarCandidateDeliveryError as exc:
            if isinstance(exc.__cause__, OSError):
                raise RadarCandidateDeliveryUnavailableError(
                    "Retained delivery graph unavailable"
                ) from exc
            raise
        for record in records:
            if (
                type(record) is PendingCandidateWork
                and record.candidate_fingerprint == candidate_fingerprint
            ):
                if record.source_identity != source_identity:
                    raise RadarCandidateDeliveryError(DeliveryFailure.INVARIANT)
                return record
        return None

    def _inventory(self) -> tuple[DeliveryRecord, ...]:
        try:
            self._check_root()
            records = []
            for path in sorted(self._root.iterdir()):
                _safe(path.lstat())
                if re.fullmatch(r"\.delivery-[A-Za-z0-9_-]+\.tmp", path.name):
                    continue  # Unpublished temporary bytes have no authority.
                record = self._read(path.name)
                if record is None:
                    raise ValueError("Delivery entry disappeared")
                records.append(record)
            sources = {
                r.identity: r for r in records if type(r) is PreparedSourceIntent
            }
            accepted = {
                r.source_identity: r for r in records if type(r) is AcceptedSource
            }
            decisions = {
                r.source_identity: r
                for r in records
                if type(r) is CandidateDecisionRecord
            }
            for record in records:
                if isinstance(record, PreparedSourceIntent):
                    continue
                source = sources.get(record.source_identity)
                acceptance = accepted.get(record.source_identity)
                if source is None or acceptance is None:
                    raise ValueError("Orphan delivery record")
                _verify_links(
                    source,
                    acceptance,
                    decisions.get(source.identity),
                    record if type(record) is PendingCandidateWork else None,
                )
            return tuple(records)
        except RadarCandidateDeliveryError:
            raise
        except Exception as exc:
            raise RadarCandidateDeliveryError(DeliveryFailure.INVARIANT) from exc

    def discover_prepared(
        self, instrument: CanonicalInstrumentId
    ) -> tuple[PreparedSourceIntent, ...]:
        _instrument_key(instrument)
        return tuple(
            r
            for r in self._inventory()
            if type(r) is PreparedSourceIntent and r.instrument == instrument
        )

    def is_resolved(self, source: PreparedSourceIntent) -> bool:
        # Check the whole retained graph, including corrupt/orphan pending records.
        records = self._inventory()
        durable = self.read_prepared(source.instrument, source.identity)
        if durable is None:
            raise RadarCandidateDeliveryError(DeliveryFailure.INVARIANT)
        self._same(durable, source)
        accepted = self.read_accepted(source.identity)
        decision = self.read_decision(source.identity)
        if accepted is None or decision is None:
            return False
        candidate = decision.decision.candidate
        if candidate is None:
            return True
        return any(
            type(r) is PendingCandidateWork
            and r.candidate_fingerprint == candidate.fingerprint
            and r.source_identity == source.identity
            for r in records
        )

    def unresolved(
        self, instrument: CanonicalInstrumentId
    ) -> tuple[PreparedSourceIntent, ...]:
        sources = tuple(
            source
            for source in self.discover_prepared(instrument)
            if not self.is_resolved(source)
        )
        if len(sources) > 1:
            raise RadarCandidateDeliveryError(DeliveryFailure.RECOVERY)
        return sources
