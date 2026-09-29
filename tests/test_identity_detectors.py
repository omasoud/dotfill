"""Tests for identity detector ordering, background passes, and caching."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

import pytest

from dotfill.config_models import (
    EffectiveConfig,
    EntraDetectorConfig,
    IdentityDefinition,
    IdentityDetectorConfig,
    TargetConfig,
    WindowsAdDetectorConfig,
)
from dotfill.config_paths import resolve_config_context
from dotfill.identity_detectors import (
    DetectionRequest,
    DetectorRunner,
    DetectorSpec,
    build_detection_request,
)
from dotfill.identity_facts import (
    DetectorOutcome,
    DetectorResult,
    IdentityFacts,
    make_identity_facts,
)
from dotfill.models import SessionState
from dotfill.resolver import build_app_state


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class FakeDetector:
    """Configurable detector that records calls and can block until released."""

    def __init__(
        self,
        name: str,
        facts: IdentityFacts | None = None,
        outcome: DetectorOutcome = "complete",
        *,
        timeout_seconds: float = 10.0,
        block: bool = False,
    ) -> None:
        self.name = name
        self.facts = facts or IdentityFacts()
        self.outcome: DetectorOutcome = outcome
        self.calls = 0
        self.started = threading.Event()
        self.release = threading.Event()
        if not block:
            self.release.set()
        self.timeout_seconds = timeout_seconds

    def spec(self) -> DetectorSpec:
        return DetectorSpec(self.name, self._run, self.timeout_seconds)

    def _run(self, _settings: object) -> DetectorResult:
        self.calls += 1
        self.started.set()
        assert self.release.wait(5), f"{self.name} was never released"
        return DetectorResult(detector=self.name, facts=self.facts, outcome=self.outcome)


def _runner(*detectors: FakeDetector, clock: Callable[[], float] | None = None) -> DetectorRunner:
    kwargs = {"clock": clock} if clock is not None else {}
    return DetectorRunner({d.name: d.spec() for d in detectors}, **kwargs)


def _request(
    *,
    order: tuple[str, ...] = ("entra", "windows_ad"),
    domains: tuple[str, ...] = ("example.com",),
    pinned: tuple[str, ...] = (),
    settings: dict[str, object] | None = None,
) -> DetectionRequest:
    return DetectionRequest(
        order=list(order),
        settings=settings
        or {"entra": EntraDetectorConfig(enabled=True), "windows_ad": WindowsAdDetectorConfig()},
        pinned=frozenset(pinned),
        needed_domains=frozenset(domains),
    )


def _config(identities: dict[str, IdentityDefinition]) -> EffectiveConfig:
    return EffectiveConfig(
        name=None,
        target=TargetConfig(),
        identity_detectors=IdentityDetectorConfig(entra=EntraDetectorConfig(enabled=True)),
        identities=identities,
        derived_variables={},
        services={},
        import_aliases={},
    )


# ---- request construction ----------------------------------------------------


def test_build_detection_request_collects_domains_pins_and_overrides() -> None:
    config = _config(
        {
            "WORK_EMAIL": IdentityDefinition("WORK_EMAIL", "email_by_domain", {"domain": "@Example.com"}),
            "OTHER_EMAIL": IdentityDefinition("OTHER_EMAIL", "email_by_domain", {"domain": "other.example"}),
            "WORK_SAM": IdentityDefinition("WORK_SAM", "windows_ad.sam"),
            "LITERAL": IdentityDefinition("LITERAL", "literal", {"value": "x"}),
        }
    )

    request = build_detection_request(config, {"OTHER_EMAIL": "manual@other.example"})

    assert request.order == ["entra", "windows_ad"]
    assert request.needed_domains == frozenset({"example.com"})
    assert request.pinned == frozenset({"windows_ad"})


def test_empty_request_runs_nothing() -> None:
    entra = FakeDetector("entra")
    runner = _runner(entra)

    snapshot = runner.detect(_request(domains=()), wait=None)

    assert entra.calls == 0
    assert snapshot.results == {}
    assert snapshot.pending == frozenset()


# ---- lazy chaining -------------------------------------------------------------


def test_lower_priority_detector_skipped_when_domains_satisfied() -> None:
    entra = FakeDetector("entra", make_identity_facts(mail="user@example.com"))
    ad = FakeDetector("windows_ad", make_identity_facts(mail="ad@example.com"))
    runner = _runner(entra, ad)

    snapshot = runner.detect(_request(), wait=None)

    assert entra.calls == 1
    assert ad.calls == 0
    assert set(snapshot.results) == {"entra"}


def test_next_detector_runs_in_same_pass_for_unmatched_domain() -> None:
    entra = FakeDetector("entra", make_identity_facts(mail="user@example.com"))
    ad = FakeDetector("windows_ad", make_identity_facts(mail="user@other.example"))
    runner = _runner(entra, ad)

    snapshot = runner.detect(_request(domains=("example.com", "other.example")), wait=None)

    assert (entra.calls, ad.calls) == (1, 1)
    assert set(snapshot.results) == {"entra", "windows_ad"}


def test_pinned_detector_runs_even_when_domains_satisfied() -> None:
    entra = FakeDetector("entra", make_identity_facts(mail="user@example.com"))
    ad = FakeDetector("windows_ad", make_identity_facts(sam="jdoe"))
    runner = _runner(entra, ad)

    runner.detect(_request(pinned=("windows_ad",)), wait=None)

    assert ad.calls == 1


def test_slow_entra_failure_then_slow_ad_resolves_without_new_request() -> None:
    entra = FakeDetector(
        "entra",
        IdentityFacts(diagnostics=["entra: sign-in interaction required"]),
        "failed",
        timeout_seconds=20.0,
        block=True,
    )
    ad = FakeDetector(
        "windows_ad",
        make_identity_facts(mail="user@example.com"),
        timeout_seconds=15.0,
        block=True,
    )
    runner = DetectorRunner(
        {"entra": entra.spec(), "windows_ad": ad.spec()}, deadline_margin_seconds=5.0
    )
    request = _request()

    first = runner.detect(request, wait=0.05)
    assert first.pending == frozenset({"entra", "windows_ad"})
    assert first.pending_deadline_seconds is not None
    assert first.pending_deadline_seconds >= 20.0 + 15.0
    assert first.next_retry_seconds is None

    entra.release.set()
    assert ad.started.wait(5), "AD must start without another detect() call"
    during_ad = runner.detect(request, wait=0.05)
    assert during_ad.pending == frozenset({"windows_ad"})
    assert during_ad.pending_deadline_seconds is not None
    assert during_ad.pending_deadline_seconds >= 15.0
    assert during_ad.results["entra"].outcome == "failed"

    ad.release.set()
    final = runner.detect(request, wait=None)
    assert final.pending == frozenset()
    assert final.results["windows_ad"].facts.emails == ["user@example.com"]
    assert (entra.calls, ad.calls) == (1, 1)


def test_pending_deadline_is_absolute_and_shrinks_to_zero() -> None:
    clock = FakeClock()
    entra = FakeDetector("entra", IdentityFacts(), "failed", timeout_seconds=20.0, block=True)
    runner = DetectorRunner(
        {"entra": entra.spec()}, clock=clock, deadline_margin_seconds=5.0
    )
    request = _request(order=("entra",))

    assert runner.detect(request, wait=0.01).pending_deadline_seconds == 25.0
    clock.now += 10
    assert runner.detect(request, wait=0.01).pending_deadline_seconds == 15.0
    clock.now += 100
    hung = runner.detect(request, wait=0.01)
    assert hung.pending == frozenset({"entra"})
    assert hung.pending_deadline_seconds == 0.0
    entra.release.set()
    runner.detect(request, wait=None)


def test_concurrent_requests_share_one_pass() -> None:
    entra = FakeDetector("entra", make_identity_facts(mail="user@example.com"), block=True)
    runner = _runner(entra)
    request = _request(order=("entra",))
    snapshots: list[object] = []

    threads = [
        threading.Thread(target=lambda: snapshots.append(runner.detect(request, wait=None)))
        for _ in range(3)
    ]
    for thread in threads:
        thread.start()
    assert entra.started.wait(5)
    entra.release.set()
    for thread in threads:
        thread.join(5)

    assert entra.calls == 1
    assert len(snapshots) == 3


def test_detector_change_mid_pass_reports_pending_and_chains_new_pass() -> None:
    entra = FakeDetector("entra", IdentityFacts(), "failed", timeout_seconds=20.0, block=True)
    ad = FakeDetector("windows_ad", make_identity_facts(mail="user@example.com"))
    runner = _runner(entra, ad)
    entra_only = _request(order=("entra",))
    ad_only = _request(
        order=("windows_ad",), settings={"windows_ad": WindowsAdDetectorConfig()}
    )

    runner.detect(entra_only, wait=0.05)
    assert entra.started.wait(5)
    during = runner.detect(ad_only, wait=0.05)

    assert during.pending == frozenset({"windows_ad"})
    assert during.pending_deadline_seconds is not None
    assert during.pending_deadline_seconds > 0
    assert during.results == {}
    assert ad.calls == 0

    entra.release.set()
    assert ad.started.wait(5), "AD pass must chain without another detect() call"
    final = runner.detect(ad_only, wait=None)

    assert final.pending == frozenset()
    assert final.results["windows_ad"].facts.emails == ["user@example.com"]
    assert ad.calls == 1


def test_queued_request_deadline_expires_while_previous_pass_is_stalled() -> None:
    """Repeated requests must not renew the timeout of a queued detector."""
    clock = FakeClock()
    entra = FakeDetector(
        "entra", IdentityFacts(), "failed", timeout_seconds=20.0, block=True
    )
    ad = FakeDetector("windows_ad", timeout_seconds=15.0)
    runner = _runner(entra, ad, clock=clock)
    started_at = clock.now
    ad_only = _request(order=("windows_ad",))

    try:
        runner.detect(_request(order=("entra",)), wait=0)
        assert entra.started.wait(5)
        countdown = ((0, 40), (10, 30), (25, 15), (35, 5), (40, 0), (1000, 0))
        for elapsed, remaining in countdown:
            clock.now = started_at + elapsed
            # State builds reconstruct the request, so equivalent new requests
            # must retain the same absolute deadline too.
            snapshot = runner.detect(_request(order=("windows_ad",)), wait=0)
            assert snapshot.pending == frozenset({"windows_ad"})
            assert snapshot.pending_deadline_seconds == remaining
            assert snapshot.next_retry_seconds is None
            assert ad.calls == 0
    finally:
        entra.release.set()
        final = runner.detect(ad_only, wait=None)

    assert final.pending == frozenset()
    assert final.results["windows_ad"].outcome == "complete"
    assert ad.calls == 1


def test_unbounded_wait_runs_own_detectors_after_other_pass() -> None:
    entra = FakeDetector("entra", IdentityFacts(), "failed", block=True)
    ad = FakeDetector("windows_ad", make_identity_facts(mail="user@example.com"))
    runner = _runner(entra, ad)
    ad_only = _request(
        order=("windows_ad",), settings={"windows_ad": WindowsAdDetectorConfig()}
    )
    runner.detect(_request(order=("entra",)), wait=0.05)
    assert entra.started.wait(5)
    results: list[object] = []

    waiter = threading.Thread(target=lambda: results.append(runner.detect(ad_only, wait=None)))
    waiter.start()
    entra.release.set()
    waiter.join(5)

    assert not waiter.is_alive()
    snapshot = results[0]
    assert snapshot.results["windows_ad"].outcome == "complete"  # type: ignore[attr-defined]


def test_detector_exception_becomes_failed_result() -> None:
    def boom(_settings: object) -> DetectorResult:
        raise RuntimeError("secret-bearing message")

    runner = DetectorRunner({"entra": DetectorSpec("entra", boom, 1.0)})

    snapshot = runner.detect(_request(order=("entra",)), wait=None)

    result = snapshot.results["entra"]
    assert result.outcome == "failed"
    assert result.facts.diagnostics == ["entra: detector failed (RuntimeError)"]


# ---- caching and backoff -----------------------------------------------------


def test_complete_result_is_cached_for_process_lifetime() -> None:
    clock = FakeClock()
    entra = FakeDetector("entra", make_identity_facts(mail="user@example.com"))
    runner = _runner(entra, clock=clock)
    request = _request(order=("entra",))

    runner.detect(request, wait=None)
    clock.now += 10_000
    snapshot = runner.detect(request, wait=None)

    assert entra.calls == 1
    assert snapshot.next_retry_seconds is None


def test_failed_result_retries_with_exponential_backoff() -> None:
    clock = FakeClock()
    entra = FakeDetector("entra", IdentityFacts(diagnostics=["entra: x"]), "failed")
    runner = _runner(entra, clock=clock)
    request = _request(order=("entra",))

    first = runner.detect(request, wait=None)
    assert entra.calls == 1
    assert first.next_retry_seconds == 60.0

    clock.now += 59
    assert runner.detect(request, wait=None).next_retry_seconds == 1.0
    assert entra.calls == 1

    clock.now += 1
    second = runner.detect(request, wait=None)
    assert entra.calls == 2
    assert second.next_retry_seconds == 120.0

    for _ in range(10):
        clock.now += 10_000
        capped = runner.detect(request, wait=None)
    assert capped.next_retry_seconds == 900.0


@pytest.mark.parametrize("outcome", ["failed", "partial"])
def test_long_failure_streak_keeps_backoff_capped(outcome: DetectorOutcome) -> None:
    """Exercise long histories without spawning workers if storage regresses."""
    clock = FakeClock()
    facts = make_identity_facts(sam="jdoe") if outcome == "partial" else IdentityFacts()
    entra = FakeDetector("entra", facts, outcome)
    runner = _runner(entra, clock=clock)
    request = _request(order=("entra",))
    result = DetectorResult("entra", facts, outcome)

    for delay in (60.0, 120.0, 240.0, 480.0) + (900.0,) * 1096:
        # Store synchronously: the old overflow leaves the entry overdue and
        # would otherwise cause the background runner to restart continuously.
        with runner._changed:
            runner._store("entra", request, result)
        snapshot = runner.detect(request, wait=0)
        assert snapshot.next_retry_seconds == delay
        assert snapshot.pending == frozenset()
        assert snapshot.results["entra"].outcome == outcome
        clock.now += delay

    assert entra.calls == 0


def test_detector_config_change_resets_retry_backoff() -> None:
    """A detector's failure history must not carry over to new settings."""
    clock = FakeClock()
    entra = FakeDetector("entra", IdentityFacts(), "failed")
    runner = _runner(entra, clock=clock)
    request = _request(order=("entra",))

    for delay in (60.0, 120.0, 240.0, 480.0, 900.0):
        assert runner.detect(request, wait=None).next_retry_seconds == delay
        clock.now += delay

    changed = _request(
        order=("entra",),
        settings={"entra": EntraDetectorConfig(enabled=True, tenant="other.example")},
    )
    assert runner.detect(changed, wait=None).next_retry_seconds == 60.0
    assert entra.calls == 6


def test_partial_result_upgrades_to_complete_after_retry() -> None:
    clock = FakeClock()
    ad = FakeDetector(
        "windows_ad",
        make_identity_facts(
            user_principal_name="user@example.com",
            diagnostics=["windows_ad: directory lookup timed out after 15s"],
        ),
        "partial",
    )
    runner = _runner(ad, clock=clock)
    request = _request(order=("windows_ad",), domains=("example.com", "other.example"))

    partial = runner.detect(request, wait=None)
    assert partial.results["windows_ad"].facts.emails == ["user@example.com"]
    assert partial.next_retry_seconds == 60.0

    ad.facts = make_identity_facts(
        mail="user@example.com", proxy_addresses=["smtp:user@other.example"]
    )
    ad.outcome = "complete"
    clock.now += 60
    recovered = runner.detect(request, wait=None)

    assert ad.calls == 2
    assert "user@other.example" in recovered.results["windows_ad"].facts.emails
    assert recovered.next_retry_seconds is None


def test_complete_result_after_failures_stops_retries() -> None:
    clock = FakeClock()
    entra = FakeDetector("entra", IdentityFacts(), "failed")
    runner = _runner(entra, clock=clock)
    request = _request(order=("entra",))

    runner.detect(request, wait=None)
    clock.now += 60
    runner.detect(request, wait=None)
    entra.outcome = "complete"
    entra.facts = make_identity_facts(mail="user@example.com")
    clock.now += 120
    recovered = runner.detect(request, wait=None)
    clock.now += 10_000
    later = runner.detect(request, wait=None)

    assert entra.calls == 3
    assert recovered.next_retry_seconds is None
    assert later.results["entra"].outcome == "complete"


def test_config_change_invalidates_cached_result() -> None:
    entra = FakeDetector("entra", make_identity_facts(mail="user@example.com"))
    runner = _runner(entra)

    runner.detect(_request(order=("entra",)), wait=None)
    runner.detect(
        _request(
            order=("entra",),
            settings={
                "entra": EntraDetectorConfig(
                    enabled=True, client_id="00000000-0000-0000-0000-000000000001"
                )
            },
        ),
        wait=None,
    )

    assert entra.calls == 2


def test_next_retry_only_reported_for_needed_detectors() -> None:
    clock = FakeClock()
    entra = FakeDetector("entra", make_identity_facts(mail="user@example.com"))
    ad = FakeDetector("windows_ad", IdentityFacts(), "failed")
    runner = _runner(entra, ad, clock=clock)

    runner.detect(_request(domains=("example.com", "other.example")), wait=None)
    snapshot = runner.detect(_request(domains=("example.com",)), wait=None)

    assert snapshot.next_retry_seconds is None


# ---- state pipeline integration ---------------------------------------------


def test_state_reports_pending_detection_then_attribution(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("", encoding="utf-8")
    root = tmp_path / "config"
    root.mkdir()
    (root / "config.toml").write_text(
        f"""
version = 1

[target]
default_env_path = "{env.as_posix()}"

[identity.detectors.entra]
enabled = true

[identities.WORK_EMAIL]
source = "email_by_domain"
domain = "example.com"

[derived.WORK_USERNAME]
from_identity = "WORK_EMAIL"
""".strip(),
        encoding="utf-8",
    )
    entra = FakeDetector("entra", make_identity_facts(mail="user@example.com"), block=True)
    ad = FakeDetector("windows_ad", IdentityFacts(), "failed")
    session = SessionState(token="t", detector_runner=_runner(entra, ad))
    context = resolve_config_context(config_root=root, environ={})

    pending_state = build_app_state(context, session, detection_wait=0.05)

    identity = pending_state.identities[0]
    assert identity.source == "unresolved"
    assert "entra: detection pending" in identity.diagnostics
    assert pending_state.identity_detection.pending is True
    assert pending_state.derived[0].status == "unresolved"

    entra.release.set()
    final_state = build_app_state(context, session, detection_wait=None)

    identity = final_state.identities[0]
    assert identity.effective_value == "user@example.com"
    assert identity.detector == "entra"
    assert identity.diagnostics == []
    assert final_state.identity_detection.pending is False
    assert ad.calls == 0
