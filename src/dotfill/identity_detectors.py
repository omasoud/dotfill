"""Identity detector ordering, background execution, and caching."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from .config_models import EffectiveConfig
from .identity_facts import DetectorResult, IdentityFacts

log = logging.getLogger(__name__)

DetectorRun = Callable[[object], DetectorResult]

DEFAULT_WAIT_BUDGET_SECONDS = 2.0
BASE_BACKOFF_SECONDS = 60.0
MAX_BACKOFF_SECONDS = 900.0
DEADLINE_MARGIN_SECONDS = 5.0


@dataclass(frozen=True)
class DetectorSpec:
    """One runnable detector and its worst-case run time."""

    name: str
    run: DetectorRun
    timeout_seconds: float


@dataclass(frozen=True)
class DetectionRequest:
    """What the current config needs from identity detectors."""

    order: list[str]
    settings: Mapping[str, object]
    pinned: frozenset[str] = frozenset()
    needed_domains: frozenset[str] = frozenset()

    @property
    def is_empty(self) -> bool:
        """Return whether no detector is needed at all."""
        return not self.order or (not self.pinned and not self.needed_domains)


@dataclass(frozen=True)
class DetectionSnapshot:
    """Detector results and progress visible to one state build."""

    results: dict[str, DetectorResult] = field(default_factory=dict)
    pending: frozenset[str] = frozenset()
    pending_deadline_seconds: float | None = None
    next_retry_seconds: float | None = None


def build_detection_request(
    config: EffectiveConfig,
    explicit_values: Mapping[str, str | None],
) -> DetectionRequest:
    """Derive detector needs from enabled identities and explicit overrides."""
    detectors = config.identity_detectors
    pinned: set[str] = set()
    domains: set[str] = set()
    for name, definition in config.identities.items():
        source = definition.source
        if source == "email_by_domain":
            if not explicit_values.get(name):
                domains.add(_normalize_domain(str(definition.params.get("domain", ""))))
        elif "." in source:
            pinned.add(source.split(".", 1)[0])
    order = detectors.enabled_in_priority_order()
    return DetectionRequest(
        order=list(order),
        settings={name: detectors.settings(name) for name in order},
        pinned=frozenset(pinned),
        needed_domains=frozenset(domains),
    )


def default_detector_specs() -> dict[str, DetectorSpec]:
    """Return the built-in Windows AD and Entra detectors."""
    from .identity import WINDOWS_AD_TIMEOUT_SECONDS, detect_windows_ad
    from .identity_entra import ENTRA_TIMEOUT_SECONDS, detect_entra

    return {
        "windows_ad": DetectorSpec(
            "windows_ad", detect_windows_ad, WINDOWS_AD_TIMEOUT_SECONDS
        ),
        "entra": DetectorSpec("entra", detect_entra, ENTRA_TIMEOUT_SECONDS),
    }


@dataclass
class _CacheEntry:
    fingerprint: str
    result: DetectorResult
    retry_delay: float | None = None
    next_retry_at: float | None = None


@dataclass
class _Pass:
    request: DetectionRequest
    queued: list[str]
    deadline_at: float
    current: str | None = None


class DetectorRunner:
    """Run identity detectors as single-flight background passes.

    A pass walks the requested detectors in priority order and starts the
    next needed detector as soon as the previous one finishes. Complete
    results are cached for the process lifetime; partial and failed results
    are retried with exponential backoff.
    """

    def __init__(
        self,
        specs: Mapping[str, DetectorSpec] | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        base_backoff_seconds: float = BASE_BACKOFF_SECONDS,
        max_backoff_seconds: float = MAX_BACKOFF_SECONDS,
        deadline_margin_seconds: float = DEADLINE_MARGIN_SECONDS,
    ) -> None:
        self._specs = dict(specs) if specs is not None else None
        self._clock = clock
        self._base_backoff = base_backoff_seconds
        self._max_backoff = max_backoff_seconds
        self._margin = deadline_margin_seconds
        self._lock = threading.Lock()
        self._changed = threading.Condition(self._lock)
        self._cache: dict[str, _CacheEntry] = {}
        self._pass: _Pass | None = None
        self._latest: DetectionRequest | None = None

    def detect(
        self,
        request: DetectionRequest,
        *,
        wait: float | None = DEFAULT_WAIT_BUDGET_SECONDS,
    ) -> DetectionSnapshot:
        """Start a pass if one is needed, wait up to *wait* seconds, then report.

        `wait=None` waits until this request's detectors have run, including
        after any in-flight pass for a different configuration.
        """
        if request.is_empty:
            return DetectionSnapshot()
        end = None if wait is None else time.monotonic() + max(wait, 0.0)
        with self._changed:
            self._latest = request
            while True:
                if self._pass is None:
                    if self._first_runnable(request) is None:
                        break
                    self._start_pass(request)
                if end is None:
                    self._changed.wait()
                    continue
                remaining = end - time.monotonic()
                if remaining <= 0:
                    break
                self._changed.wait(remaining)
            return self._snapshot(request)

    # ---- pass execution --------------------------------------------------

    def _start_pass(self, request: DetectionRequest) -> None:
        queued = [name for name in request.order if self._is_runnable(name, request)]
        budget = sum(self._spec(name).timeout_seconds for name in queued) + self._margin
        self._pass = _Pass(
            request=request, queued=queued, deadline_at=self._clock() + budget
        )
        thread = threading.Thread(
            target=self._run_pass,
            args=(request,),
            name="dotfill-identity-detection",
            daemon=True,
        )
        thread.start()

    def _run_pass(self, request: DetectionRequest) -> None:
        try:
            for name in request.order:
                with self._changed:
                    assert self._pass is not None
                    if name in self._pass.queued:
                        self._pass.queued.remove(name)
                    if not self._should_run(name, request):
                        self._changed.notify_all()
                        continue
                    self._pass.current = name
                result = self._invoke(name, request.settings[name])
                with self._changed:
                    self._store(name, request, result)
                    assert self._pass is not None
                    self._pass.current = None
                    self._changed.notify_all()
        finally:
            with self._changed:
                self._pass = None
                # A config change during this pass queues the latest request next.
                latest = self._latest
                if latest is not None and self._first_runnable(latest) is not None:
                    self._start_pass(latest)
                self._changed.notify_all()

    def _invoke(self, name: str, settings: object) -> DetectorResult:
        spec = self._spec(name)
        try:
            return spec.run(settings)
        except Exception as exc:  # noqa: BLE001 - detectors must never break state
            log.warning("Identity detector %s failed: %s", name, type(exc).__name__)
            return DetectorResult(
                detector=name,
                facts=IdentityFacts(
                    diagnostics=[f"{name}: detector failed ({type(exc).__name__})"]
                ),
                outcome="failed",
            )

    def _spec(self, name: str) -> DetectorSpec:
        if self._specs is None:
            self._specs = default_detector_specs()
        return self._specs[name]

    def _store(self, name: str, request: DetectionRequest, result: DetectorResult) -> None:
        entry = self._cache.get(name)
        fingerprint = _fingerprint(request.settings[name])
        if result.outcome == "complete":
            self._cache[name] = _CacheEntry(fingerprint, result)
            return
        delay = self._base_backoff
        if entry and entry.fingerprint == fingerprint and entry.retry_delay is not None:
            # Double the capped delay rather than exponentiating a failure count.
            delay = entry.retry_delay * 2
        delay = min(delay, self._max_backoff)
        self._cache[name] = _CacheEntry(
            fingerprint, result, retry_delay=delay, next_retry_at=self._clock() + delay
        )

    # ---- scheduling decisions (caller holds the lock) ---------------------

    def _entry(self, name: str, request: DetectionRequest) -> _CacheEntry | None:
        entry = self._cache.get(name)
        if entry is None or entry.fingerprint != _fingerprint(request.settings[name]):
            return None
        return entry

    def _is_runnable(self, name: str, request: DetectionRequest) -> bool:
        entry = self._entry(name, request)
        if entry is None:
            return True
        if entry.result.outcome == "complete" or entry.next_retry_at is None:
            return False
        return self._clock() >= entry.next_retry_at

    def _is_needed(self, name: str, request: DetectionRequest) -> bool:
        if name in request.pinned:
            return True
        return bool(self._unmatched_domains_before(name, request))

    def _should_run(self, name: str, request: DetectionRequest) -> bool:
        return self._is_runnable(name, request) and self._is_needed(name, request)

    def _first_runnable(self, request: DetectionRequest) -> str | None:
        return next(
            (name for name in request.order if self._should_run(name, request)), None
        )

    def _unmatched_domains_before(self, name: str, request: DetectionRequest) -> set[str]:
        remaining = set(request.needed_domains)
        for earlier in request.order:
            if earlier == name or not remaining:
                break
            entry = self._entry(earlier, request)
            if entry is not None:
                remaining -= _matched_domains(entry.result.facts, remaining)
        return remaining

    def _snapshot(self, request: DetectionRequest) -> DetectionSnapshot:
        results = {
            name: entry.result
            for name in request.order
            if (entry := self._entry(name, request)) is not None
        }
        pending: frozenset[str] = frozenset()
        deadline: float | None = None
        if self._pass is not None:
            in_pass = set(self._pass.queued)
            if self._pass.current is not None:
                in_pass.add(self._pass.current)
            waiting = {
                name
                for name in request.order
                if name not in in_pass and self._should_run(name, request)
            }
            pending = frozenset((in_pass & set(request.order)) | waiting)
            if pending:
                # Anchor queued work to the pass's fixed deadline so an overdue
                # pass cannot renew the queued timeout on every snapshot.
                deadline_at = self._pass.deadline_at + sum(
                    self._spec(name).timeout_seconds for name in waiting
                )
                deadline = max(deadline_at - self._clock(), 0.0)
        return DetectionSnapshot(
            results=results,
            pending=pending,
            pending_deadline_seconds=deadline,
            next_retry_seconds=None if pending else self._next_retry_seconds(request),
        )

    def _next_retry_seconds(self, request: DetectionRequest) -> float | None:
        now = self._clock()
        waits = [
            max(entry.next_retry_at - now, 0.0)
            for name in request.order
            if (entry := self._entry(name, request)) is not None
            and entry.next_retry_at is not None
            and self._is_needed(name, request)
        ]
        return min(waits) if waits else None


def _fingerprint(settings: object) -> str:
    return repr(settings)


def _normalize_domain(domain: str) -> str:
    return domain.strip().lower().removeprefix("@")


def _matched_domains(facts: IdentityFacts, domains: set[str]) -> set[str]:
    return {d for d in domains if any(email.endswith("@" + d) for email in facts.emails)}
