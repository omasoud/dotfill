"""Shared pytest fixtures: keep real directory and Graph probes out of tests."""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from dotfill import identity_detectors
from dotfill.identity_detectors import DetectorSpec
from dotfill.identity_facts import DetectorResult, IdentityFacts


def fixed_detector(result: DetectorResult, timeout_seconds: float = 1.0) -> DetectorSpec:
    """Return a detector spec that always yields *result*."""
    return DetectorSpec(result.detector, lambda _settings: result, timeout_seconds)


def unavailable_specs() -> Mapping[str, DetectorSpec]:
    """Return detector specs that fail fast without touching the system."""
    return {
        name: fixed_detector(
            DetectorResult(
                detector=name,
                facts=IdentityFacts(diagnostics=[f"{name}: unavailable in tests"]),
                outcome="failed",
            )
        )
        for name in ("windows_ad", "entra")
    }


@pytest.fixture(autouse=True)
def _no_real_identity_probes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(identity_detectors, "default_detector_specs", unavailable_specs)
