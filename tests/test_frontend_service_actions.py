"""Frontend service-action availability tests for unresolved service URLs."""

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
    return STATIC_DIR.joinpath("service_actions.js").resolve().as_uri()


def test_resolved_service_actions_are_available() -> None:
    script = f"""
        import assert from "node:assert/strict";
        import {{ serviceMissingHint, testAction, tokenPageAction }} from {json.dumps(_module_url())};

        const svc = {{
          token_present: true,
          resolved_token_url: "https://svc.example.com/tokens",
          resolved_test_url: "https://svc.example.com/me",
          token_url_unresolved_identities: [],
          test_url_unresolved_identities: [],
        }};
        assert.deepEqual(tokenPageAction(svc), {{
          available: true, url: "https://svc.example.com/tokens", reason: "",
        }});
        assert.deepEqual(testAction(svc), {{ visible: true, available: true, reason: "" }});
        assert.equal(serviceMissingHint(svc), "");
    """
    _run_node_module(script)


def test_one_sided_unresolved_urls_disable_only_that_action() -> None:
    script = f"""
        import assert from "node:assert/strict";
        import {{ serviceMissingHint, testAction, tokenPageAction }} from {json.dumps(_module_url())};

        const tokenMissing = {{
          token_present: true,
          resolved_token_url: null,
          resolved_test_url: "https://svc.example.com/me",
          token_url_unresolved_identities: ["WORK_EMAIL"],
          test_url_unresolved_identities: [],
        }};
        assert.deepEqual(tokenPageAction(tokenMissing), {{
          available: false, url: null, reason: "Needs WORK_EMAIL",
        }});
        assert.equal(testAction(tokenMissing).available, true);

        const testMissing = {{
          token_present: true,
          resolved_token_url: "https://svc.example.com/tokens",
          resolved_test_url: null,
          token_url_unresolved_identities: [],
          test_url_unresolved_identities: ["WORK_USER", "WORK_EMAIL"],
        }};
        assert.equal(tokenPageAction(testMissing).available, true);
        assert.deepEqual(testAction(testMissing), {{
          visible: true, available: false, reason: "Needs WORK_USER, WORK_EMAIL",
        }});
        assert.equal(serviceMissingHint(testMissing), "Needs WORK_USER, WORK_EMAIL");

        const both = {{
          ...testMissing,
          resolved_token_url: null,
          token_url_unresolved_identities: ["WORK_EMAIL"],
        }};
        assert.equal(serviceMissingHint(both), "Needs WORK_EMAIL, WORK_USER");
    """
    _run_node_module(script)


def test_test_action_hidden_without_token() -> None:
    script = f"""
        import assert from "node:assert/strict";
        import {{ testAction }} from {json.dumps(_module_url())};

        assert.deepEqual(
          testAction({{ token_present: false, resolved_test_url: "https://x.example.com" }}),
          {{ visible: false, available: false, reason: "" }},
        );
    """
    _run_node_module(script)
