"""Frontend import-row service-test state unit tests."""

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
    return STATIC_DIR.joinpath("import_test_state.js").resolve().as_uri()


def test_import_test_state_eligibility_and_request_payload() -> None:
    script = f"""
        import assert from "node:assert/strict";
        import {{
          canTestImportRow,
          importTestRequest,
          serviceIdForTarget,
        }} from {json.dumps(_module_url())};

        const services = [
          {{ service_id: "SERVICE_A", token_var: "SERVICE_A_TOKEN" }},
          {{ service_id: "SERVICE_B", token_var: "SERVICE_B_TOKEN" }},
        ];
        const scan = {{ scan_id: "scan-1" }};
        const row = {{
          source_key: "SOURCE_TOKEN",
          target_key: "SERVICE_A_TOKEN",
          status: "replace",
        }};

        assert.equal(serviceIdForTarget("SERVICE_A_TOKEN", services), "SERVICE_A");
        assert.equal(serviceIdForTarget("WORK_USERNAME", services), null);
        assert.equal(canTestImportRow(row, services), true);
        assert.equal(canTestImportRow({{ ...row, status: "no_change" }}, services), false);
        assert.equal(canTestImportRow({{ ...row, status: "unmapped" }}, services), false);
        assert.equal(canTestImportRow({{ ...row, target_key: null }}, services), false);
        assert.equal(canTestImportRow({{ ...row, target_key: "WORK_USERNAME" }}, services), false);
        assert.deepEqual(importTestRequest(scan, row), {{
          path: "/api/import/test",
          body: {{
            scanId: "scan-1",
            sourceKey: "SOURCE_TOKEN",
            targetKey: "SERVICE_A_TOKEN",
          }},
        }});
    """

    _run_node_module(textwrap.dedent(script))


def test_import_test_state_status_updates_and_resets() -> None:
    script = f"""
        import assert from "node:assert/strict";
        import {{
          clearImportTestState,
          importTestStatus,
          resetImportTestStates,
          setImportTestState,
        }} from {json.dumps(_module_url())};

        const row = {{ source_key: "SOURCE_TOKEN" }};
        let states = resetImportTestStates();
        assert.equal(importTestStatus(states, row), "untested");

        states = setImportTestState(states, "SOURCE_TOKEN", "testing");
        assert.equal(importTestStatus(states, row), "testing");
        states = setImportTestState(states, "SOURCE_TOKEN", "working");
        assert.equal(importTestStatus(states, row), "working");
        states = clearImportTestState(states, "SOURCE_TOKEN");
        assert.equal(importTestStatus(states, row), "untested");

        states = setImportTestState(states, "SOURCE_TOKEN", "failed");
        states = resetImportTestStates();
        assert.equal(importTestStatus(states, row), "untested");
    """

    _run_node_module(textwrap.dedent(script))
