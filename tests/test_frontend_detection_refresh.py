"""Frontend identity-detection refresh scheduling tests."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC_DIR = Path(__file__).resolve().parents[1] / "src" / "dotfill" / "static"


def _run_node_module(script: str) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not available")
    result = subprocess.run(
        [node, "--input-type=module", "--eval", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def _module_url() -> str:
    return STATIC_DIR.joinpath("detection_refresh.js").resolve().as_uri()


_FAKE_TIMERS = """
class FakeTimers {
  constructor() { this.now = 0; this.nextId = 1; this.timers = new Map(); }
  setTimer = (fn, delay) => {
    const id = this.nextId++;
    this.timers.set(id, { fn, at: this.now + delay });
    return id;
  };
  clearTimer = (id) => { this.timers.delete(id); };
  advance(ms) {
    this.now += ms;
    for (const [id, t] of [...this.timers]) {
      if (t.at <= this.now) { this.timers.delete(id); t.fn(); }
    }
  }
}
"""


def test_polls_while_pending_until_server_deadline_reaches_zero() -> None:
    script = f"""
        import assert from "node:assert/strict";
        import {{ createDetectionScheduler, POLL_INTERVAL_MS }} from {json.dumps(_module_url())};
        {_FAKE_TIMERS}
        const timers = new FakeTimers();
        let refreshes = 0;
        const scheduler = createDetectionScheduler({{
          setTimer: timers.setTimer, clearTimer: timers.clearTimer,
          refresh: () => {{ refreshes += 1; }},
        }});

        assert.deepEqual(
          scheduler.update({{ pending: true, pending_deadline_seconds: 4 }}),
          {{ kind: "poll", delayMs: POLL_INTERVAL_MS }},
        );
        timers.advance(2000);
        assert.equal(refreshes, 1);
        assert.equal(scheduler.update({{ pending: true, pending_deadline_seconds: 2 }}).kind, "poll");
        timers.advance(2000);
        assert.equal(refreshes, 2);
        assert.equal(
          scheduler.update({{ pending: true, pending_deadline_seconds: 0 }}),
          null,
          "stop once the server deadline is exhausted",
        );
        assert.equal(timers.timers.size, 0);
    """
    _run_node_module(script)


def test_chained_pass_keeps_polling_while_server_reports_time() -> None:
    script = f"""
        import assert from "node:assert/strict";
        import {{ nextDetectionRefresh }} from {json.dumps(_module_url())};

        assert.equal(nextDetectionRefresh({{ pending: true, pending_deadline_seconds: 40 }}).kind, "poll");
        assert.equal(nextDetectionRefresh({{ pending: true, pending_deadline_seconds: 19 }}).kind, "poll");
        assert.equal(nextDetectionRefresh({{ pending: false, next_retry_seconds: null }}), null);
    """
    _run_node_module(script)


def test_schedules_single_refresh_when_retry_becomes_due() -> None:
    script = f"""
        import assert from "node:assert/strict";
        import {{ createDetectionScheduler, RETRY_MARGIN_MS }} from {json.dumps(_module_url())};
        {_FAKE_TIMERS}
        const timers = new FakeTimers();
        let refreshes = 0;
        const scheduler = createDetectionScheduler({{
          setTimer: timers.setTimer, clearTimer: timers.clearTimer,
          refresh: () => {{ refreshes += 1; }},
        }});

        const next = scheduler.update({{ pending: false, next_retry_seconds: 60 }});
        assert.deepEqual(next, {{ kind: "retry", delayMs: 60000 + RETRY_MARGIN_MS }});
        timers.advance(60000);
        assert.equal(refreshes, 0);
        timers.advance(RETRY_MARGIN_MS);
        assert.equal(refreshes, 1);
    """
    _run_node_module(script)


def test_updates_replace_timers_without_duplicates() -> None:
    script = f"""
        import assert from "node:assert/strict";
        import {{ createDetectionScheduler }} from {json.dumps(_module_url())};
        {_FAKE_TIMERS}
        const timers = new FakeTimers();
        let refreshes = 0;
        const scheduler = createDetectionScheduler({{
          setTimer: timers.setTimer, clearTimer: timers.clearTimer,
          refresh: () => {{ refreshes += 1; }},
        }});

        scheduler.update({{ pending: false, next_retry_seconds: 30 }});
        scheduler.update({{ pending: false, next_retry_seconds: 30 }});
        scheduler.update({{ pending: true, pending_deadline_seconds: 10 }});
        assert.equal(timers.timers.size, 1);
        scheduler.update({{ pending: false, next_retry_seconds: null }});
        assert.equal(timers.timers.size, 0);
        scheduler.update({{ pending: false, next_retry_seconds: 5 }});
        scheduler.cancel();
        timers.advance(100000);
        assert.equal(refreshes, 0);
    """
    _run_node_module(script)


def test_missing_detection_payload_schedules_nothing() -> None:
    script = f"""
        import assert from "node:assert/strict";
        import {{ nextDetectionRefresh }} from {json.dumps(_module_url())};

        assert.equal(nextDetectionRefresh(undefined), null);
        assert.equal(nextDetectionRefresh({{}}), null);
        assert.equal(nextDetectionRefresh({{ pending: true }}), null);
    """
    _run_node_module(script)
