"""Execution-local lazy facts, with no Evidence or investment authority."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Generic, TypeVar, cast

from market_platform.instruments.identity import CanonicalInstrumentId

T_co = TypeVar("T_co", covariant=True)


class RadarContextError(Exception):
    """Invalid fact wiring or access; never a Gate disposition."""


@dataclass(frozen=True, slots=True)
class RadarFactKey(Generic[T_co]):  # noqa: UP046 -- explicit covariance for mypy
    """Immutable fact identity and exact runtime class, independent of any Gate.

    Only plain runtime classes are supported, not parameterized types, unions,
    protocols or custom metaclasses. Class references are type tokens, not
    executable configuration. No fingerprint or provider identity is implied.
    """

    fact_id: str
    value_type: type[T_co]

    def __post_init__(self) -> None:
        if type(self.fact_id) is not str:
            raise TypeError("fact_id must be a string")
        if not self.fact_id.strip():
            raise ValueError("fact_id must not be empty")
        if type(self.value_type) is not type:
            raise TypeError("value_type must be a plain runtime class")


class RadarEvaluationContext:
    """One instrument execution's facts; no concurrency guarantee is provided.

    Loaders are injected application/runtime dependencies, never Profile
    configuration. Bind instrument/as_of and external clients in their closures.
    Construction copies wiring without invoking loaders. Ordinary exceptions,
    including value-type failures, are retained without automatic retries;
    process-control BaseExceptions propagate without retention.

    The context retains resolved references, without copying/freezing values.
    Loaders must supply values appropriate for read-only Gate consumption;
    Gates must not mutate them. Private memoization is not a Gate output channel,
    durable state, Evidence freshness/admission, or execution authority.
    """

    __slots__ = (
        "_instrument",
        "_as_of",
        "_loaders",
        "_values",
        "_failures",
        "_resolving",
    )

    def __init__(
        self,
        instrument: CanonicalInstrumentId,
        as_of: datetime,
        loaders: Mapping[RadarFactKey[object], Callable[[], object]],
    ) -> None:
        if type(instrument) is not CanonicalInstrumentId:
            raise TypeError("instrument must be a CanonicalInstrumentId")
        if not isinstance(as_of, datetime):
            raise TypeError("as_of must be a datetime")
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        if not isinstance(loaders, Mapping):
            raise TypeError("loaders must be a mapping")
        detached = dict(loaders)
        identifiers: set[str] = set()
        for key, loader in detached.items():
            if type(key) is not RadarFactKey:
                raise TypeError("loader keys must be RadarFactKey values")
            if not callable(loader):
                raise TypeError("fact loaders must be callable")
            if key.fact_id in identifiers:
                raise RadarContextError(f"Conflicting fact identity: {key.fact_id}")
            identifiers.add(key.fact_id)
        self._instrument = instrument
        self._as_of = as_of
        self._loaders = detached
        self._values: dict[RadarFactKey[object], object] = {}
        self._failures: dict[RadarFactKey[object], Exception] = {}
        self._resolving: set[RadarFactKey[object]] = set()

    @property
    def instrument(self) -> CanonicalInstrumentId:
        return self._instrument

    @property
    def as_of(self) -> datetime:
        return self._as_of

    def get_fact[T](self, key: RadarFactKey[T]) -> T:
        """Resolve on first access and retain the value or ordinary exception.

        Exact class equality intentionally rejects subclasses, including bool
        for int. Equal reconstructed keys share the same retained resolution.
        """
        if type(key) is not RadarFactKey:
            raise TypeError("key must be a RadarFactKey")
        if key not in self._loaders:
            raise RadarContextError(f"Unconfigured fact: {key.fact_id}")
        if key in self._failures:
            raise self._failures[key].with_traceback(None)
        if key in self._values:
            return cast(T, self._values[key])
        if key in self._resolving:
            raise RadarContextError(f"Recursive fact resolution: {key.fact_id}")
        self._resolving.add(key)
        try:
            value = self._loaders[key]()
            if type(value) is not key.value_type:
                raise RadarContextError(
                    f"Fact {key.fact_id} requires exact type "
                    f"{key.value_type.__name__}; "
                    f"got {type(value).__name__}"
                )
        except Exception as exc:
            self._failures[key] = exc
            raise
        finally:
            self._resolving.remove(key)
        self._values[key] = value
        return value
