"""Frontend derived-default in-flight state unit tests."""

from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
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
    return STATIC_DIR.joinpath("derived_default_state.js").resolve().as_uri()


def test_derived_default_state_suppresses_reentry_until_request_finishes() -> None:
    script = f"""
        import assert from "node:assert/strict";
        import {{
          beginDerivedDefault,
          createDerivedDefaultState,
          finishDerivedDefault,
          isDerivedDefaultInFlight,
        }} from {json.dumps(_module_url())};

        const state = createDerivedDefaultState();
        assert.equal(isDerivedDefaultInFlight(state, "WORK_USERNAME"), false);
        assert.equal(beginDerivedDefault(state, "WORK_USERNAME"), true);
        assert.equal(isDerivedDefaultInFlight(state, "WORK_USERNAME"), true);
        assert.equal(beginDerivedDefault(state, "WORK_USERNAME"), false);

        finishDerivedDefault(state, "WORK_USERNAME");
        assert.equal(isDerivedDefaultInFlight(state, "WORK_USERNAME"), false);
        assert.equal(beginDerivedDefault(state, "WORK_USERNAME"), true);
    """

    _run_node_module(textwrap.dedent(script))
