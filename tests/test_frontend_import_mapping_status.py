"""Frontend import mapping status unit tests."""

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
    return STATIC_DIR.joinpath("import_mapping_status.js").resolve().as_uri()


def test_import_mapping_status_uses_backend_no_change_for_manual_remap() -> None:
    script = f"""
        import assert from "node:assert/strict";
        import {{
          recomputeImportRowStatus,
        }} from {json.dumps(_module_url())};

        const row = {{
          source_key: "JENKINS_API_TOKEN",
          target_key: null,
          status: "unmapped",
          target_statuses: {{
            JENKINS_CCC_API_TOKEN: "no_change",
          }},
          _originalTarget: null,
          _originalStatus: "unmapped",
        }};
        const scan = {{ occupied_targets: ["JENKINS_CCC_API_TOKEN"] }};

        row.target_key = "JENKINS_CCC_API_TOKEN";

        assert.equal(recomputeImportRowStatus(row, scan), "no_change");
        assert.equal(row.status, "no_change");
    """

    _run_node_module(textwrap.dedent(script))


def test_import_mapping_status_falls_back_for_older_scan_payloads() -> None:
    script = f"""
        import assert from "node:assert/strict";
        import {{
          recomputeImportRowStatus,
        }} from {json.dumps(_module_url())};

        const row = {{
          source_key: "SOURCE_TOKEN",
          target_key: "SERVICE_TOKEN",
          status: "unmapped",
        }};
        const scan = {{ occupied_targets: ["SERVICE_TOKEN"] }};

        assert.equal(recomputeImportRowStatus(row, scan), "replace");
        assert.equal(row.status, "replace");

        row.target_key = "EMPTY_SERVICE_TOKEN";
        assert.equal(recomputeImportRowStatus(row, scan), "new");
        assert.equal(row.status, "new");
    """

    _run_node_module(textwrap.dedent(script))
