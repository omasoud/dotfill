"""Frontend refresh error-state regression tests."""

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


def _app_url() -> str:
    return STATIC_DIR.joinpath("app.js").resolve().as_uri()


def test_refresh_success_clears_previous_state_error() -> None:
    script = f"""
        import assert from "node:assert/strict";

        class FakeNode {{
          constructor(tagName = "") {{
            this.tagName = tagName;
            this.children = [];
            this.attributes = new Map();
            this.listeners = new Map();
            this.className = "";
            this.dataset = {{}};
            this.style = {{}};
          }}

          setAttribute(name, value) {{
            this.attributes.set(name, String(value));
            if (name === "class") this.className = String(value);
          }}

          append(...items) {{
            this.children.push(...items);
          }}

          appendChild(child) {{
            this.append(child);
            return child;
          }}

          addEventListener(type, listener) {{
            const listeners = this.listeners.get(type) || [];
            listeners.push(listener);
            this.listeners.set(type, listeners);
          }}

          async click() {{
            for (const listener of this.listeners.get("click") || []) {{
              await listener({{
                currentTarget: this,
                target: this,
                preventDefault() {{}},
              }});
            }}
          }}

          set innerHTML(_value) {{
            this.children = [];
          }}

          get innerHTML() {{
            return this.textContent;
          }}

          set textContent(value) {{
            this.children = [String(value)];
          }}

          get textContent() {{
            return this.children
              .map((child) => child instanceof FakeNode ? child.textContent : String(child))
              .join("");
          }}
        }}

        const ids = new Map();
        const root = new FakeNode("div");
        const errorRegion = new FakeNode("div");
        ids.set("root", root);
        ids.set("error-region", errorRegion);

        function createNode(tagName) {{
          return new FakeNode(tagName);
        }}

        globalThis.Node = FakeNode;
        globalThis.document = {{
          documentElement: new FakeNode("html"),
          querySelector(selector) {{
            return selector.startsWith("#") ? ids.get(selector.slice(1)) || null : null;
          }},
          createElement: createNode,
          createElementNS: (_namespace, tagName) => createNode(tagName),
          getElementById(id) {{
            return id.startsWith("ic-") ? new FakeNode("symbol") : ids.get(id) || null;
          }},
        }};
        globalThis.localStorage = {{
          getItem() {{ return null; }},
          setItem() {{}},
        }};
        globalThis.matchMedia = () => ({{ matches: false }});
        globalThis.window = {{
          location: {{ href: "http://127.0.0.1:41235/?session=session-token-x" }},
          history: {{ replaceState() {{}} }},
        }};

        function statePayload(envPath) {{
          return {{
            config: {{ config_dir: "C:/dotfill/config" }},
            identities: [],
            derived: [],
            services: [],
            env_path: envPath,
            session: {{ backup_path: null, backup_created: false }},
          }};
        }}

        const responses = [
          {{ ok: true, status: 200, json: async () => ({{ session_token: "session-token-x", version: "test" }}) }},
          {{ ok: true, status: 200, json: async () => statePayload("C:/env/first.env") }},
          {{ ok: false, status: 400, statusText: "Bad Request", json: async () => ({{ error: "ConfigSchemaError", message: "bad config" }}) }},
          {{ ok: true, status: 200, json: async () => statePayload("C:/env/fixed.env") }},
        ];
        const requests = [];
        globalThis.fetch = async (path, options) => {{
          requests.push({{ path, options }});
          const response = responses.shift();
          assert.ok(response, `unexpected fetch ${{path}}`);
          return response;
        }};

        async function waitFor(predicate) {{
          for (let i = 0; i < 30; i += 1) {{
            if (predicate()) return;
            await new Promise((resolve) => setTimeout(resolve, 0));
          }}
          assert.fail("condition was not met");
        }}

        function findButtonByText(node, text) {{
          if (node.tagName === "button" && node.textContent.includes(text)) return node;
          for (const child of node.children) {{
            if (child instanceof FakeNode) {{
              const found = findButtonByText(child, text);
              if (found) return found;
            }}
          }}
          return null;
        }}

        await import({json.dumps(_app_url())});
        await waitFor(() => requests.length === 2 && root.textContent.includes("first.env"));
        assert.equal(errorRegion.textContent, "");
        assert.match(root.textContent, /first\\.env/);

        const refresh = findButtonByText(root, "Refresh");
        assert.ok(refresh);
        await refresh.click();
        await waitFor(() => requests.length === 3);
        assert.match(errorRegion.textContent, /Failed to load state: 400 bad config/);

        await refresh.click();
        await waitFor(() => requests.length === 4 && root.textContent.includes("fixed.env"));
        assert.match(root.textContent, /fixed\\.env/);
        assert.equal(errorRegion.textContent, "");
    """

    _run_node_module(textwrap.dedent(script))
