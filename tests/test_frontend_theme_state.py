"""Frontend theme-state unit tests."""

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
    return STATIC_DIR.joinpath("theme_state.js").resolve().as_uri()


def test_theme_state_resolves_and_persists_allowed_values_only() -> None:
    script = f"""
        import assert from "node:assert/strict";
        import {{
          THEME_STORAGE_KEY,
          nextTheme,
          readStoredTheme,
          resolveInitialTheme,
          storeTheme,
        }} from {json.dumps(_module_url())};

        const data = new Map();
        const storage = {{
          getItem: (key) => data.has(key) ? data.get(key) : null,
          setItem: (key, value) => data.set(key, value),
        }};
        const darkSystem = (query) => {{
          assert.equal(query, "(prefers-color-scheme: dark)");
          return {{ matches: true }};
        }};

        assert.equal(THEME_STORAGE_KEY, "dotfill.theme");
        assert.equal(resolveInitialTheme({{ storage, matchMedia: darkSystem }}), "dark");
        assert.equal(storeTheme("dark", storage), true);
        assert.equal(data.get(THEME_STORAGE_KEY), "dark");
        assert.equal(readStoredTheme(storage), "dark");
        assert.equal(resolveInitialTheme({{ storage, matchMedia: () => {{ throw new Error("unused"); }} }}), "dark");
        assert.equal(storeTheme("sepia", storage), false);
        assert.equal(data.get(THEME_STORAGE_KEY), "dark");
        assert.equal(nextTheme("dark"), "light");
        assert.equal(nextTheme("light"), "dark");
        assert.equal(nextTheme("unknown"), "dark");
    """

    _run_node_module(textwrap.dedent(script))


def test_theme_state_handles_unavailable_storage() -> None:
    script = f"""
        import assert from "node:assert/strict";
        import {{
          applyTheme,
          readStoredTheme,
          resolveInitialTheme,
          storeTheme,
        }} from {json.dumps(_module_url())};

        const brokenStorage = {{
          getItem: () => {{ throw new Error("blocked"); }},
          setItem: () => {{ throw new Error("blocked"); }},
        }};
        const doc = {{
          documentElement: {{
            dataset: {{}},
            style: {{}},
          }},
        }};

        assert.equal(readStoredTheme(brokenStorage), null);
        assert.equal(storeTheme("light", brokenStorage), false);
        assert.equal(resolveInitialTheme({{ storage: brokenStorage, matchMedia: () => ({{ matches: false }}) }}), "light");
        assert.equal(applyTheme("dark", doc), "dark");
        assert.equal(doc.documentElement.dataset.theme, "dark");
        assert.equal(doc.documentElement.style.colorScheme, "dark");
        assert.equal(applyTheme("invalid", doc), "light");
    """

    _run_node_module(textwrap.dedent(script))
