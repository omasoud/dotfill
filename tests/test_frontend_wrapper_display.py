"""Frontend package/wrapper version display unit tests."""

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
    return STATIC_DIR.joinpath("wrapper_display.js").resolve().as_uri()


def test_version_display_handles_direct_wrapped_and_markup_like_values() -> None:
    script = f"""
        import assert from "node:assert/strict";
        import {{ formatVersionDisplay }} from {json.dumps(_module_url())};

        assert.equal(formatVersionDisplay("1.3.2", null), "v1.3.2");
        assert.equal(
          formatVersionDisplay("1.3.2", {{ name: "team-dotfill", version: "1.0.1" }}),
          "v1.3.2 (team-dotfill v1.0.1)",
        );
        assert.equal(
          formatVersionDisplay("1.3.2", {{ name: "<tool>", version: "1&2" }}),
          "v1.3.2 (<tool> v1&2)",
        );
    """

    _run_node_module(textwrap.dedent(script))
