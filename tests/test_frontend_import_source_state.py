"""Frontend import-source state unit tests."""

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
    return STATIC_DIR.joinpath("import_source_state.js").resolve().as_uri()


def test_import_source_state_transitions_and_requests() -> None:
    script = f"""
        import assert from "node:assert/strict";
        import {{
          browseImportSource,
          createImportSourceState,
          dropImportSource,
          importSourceLabel,
          importSourceRequest,
        }} from {json.dumps(_module_url())};

        let source = createImportSourceState();
        assert.equal(source.mode, "empty");
        assert.deepEqual(importSourceRequest(source), {{
          path: "/api/import/scan-dropped",
          body: {{ filename: "", content: "" }},
        }});

        source = browseImportSource(source, "picked.env", "A=1\\n");
        assert.equal(source.mode, "browse");
        assert.equal(source.displayValue, "Selected file: picked.env");
        assert.equal(importSourceLabel(source, {{ source_label: "server-label" }}), "Selected file: picked.env");
        assert.deepEqual(importSourceRequest(source), {{
          path: "/api/import/scan-dropped",
          body: {{ filename: "picked.env", content: "A=1\\n" }},
        }});

        source = dropImportSource(source, "dropped.env", "A=2\\n");
        assert.equal(source.mode, "drop");
        assert.equal(source.displayValue, "Dropped file: dropped.env");
        assert.equal(importSourceLabel(source, {{ source_label: "server-label" }}), "Dropped file: dropped.env");
        assert.deepEqual(importSourceRequest(source), {{
          path: "/api/import/scan-dropped",
          body: {{ filename: "dropped.env", content: "A=2\\n" }},
        }});
    """

    _run_node_module(textwrap.dedent(script))


def test_import_source_reuses_latest_file_content_for_rescan() -> None:
    script = f"""
        import assert from "node:assert/strict";
        import {{
          browseImportSource,
          createImportSourceState,
          dropImportSource,
          importSourceRequest,
        }} from {json.dumps(_module_url())};

        let source = createImportSourceState();
        source = browseImportSource(source, "same.env", "A=old\\n");
        source = browseImportSource(source, "same.env", "A=new\\n");
        assert.deepEqual(importSourceRequest(source), {{
          path: "/api/import/scan-dropped",
          body: {{ filename: "same.env", content: "A=new\\n" }},
        }});

        source = dropImportSource(source, "same.env", "A=drop\\n");
        assert.deepEqual(importSourceRequest(source), {{
          path: "/api/import/scan-dropped",
          body: {{ filename: "same.env", content: "A=drop\\n" }},
        }});
    """

    _run_node_module(textwrap.dedent(script))
