"""Static checks for bundled frontend assets."""

from __future__ import annotations

import re
from pathlib import Path

from dotfill.icons import SERVICE_ICON_KEYS


STATIC_DIR = Path(__file__).resolve().parents[1] / "src" / "dotfill" / "static"


def _static_text() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(STATIC_DIR.glob("*.*"))
    )


def _sprite_icon_keys() -> set[str]:
    index_text = STATIC_DIR.joinpath("index.html").read_text(encoding="utf-8")
    return set(re.findall(r'id="ic-([^"]+)"', index_text))


def test_frontend_browser_storage_is_limited_to_theme_preference() -> None:
    text_by_file = {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(STATIC_DIR.glob("*.*"))
    }
    text = "\n".join(text_by_file.values())

    forbidden = ["sessionStorage", "indexedDB", "document.cookie"]

    assert [term for term in forbidden if term in text] == []
    assert "localStorage" not in "\n".join(
        content for name, content in text_by_file.items() if name != "theme_state.js"
    )
    assert 'THEME_STORAGE_KEY = "dotfill.theme"' in text_by_file["theme_state.js"]

def test_frontend_renders_generic_config_and_empty_service_text() -> None:
    text = _static_text()

    assert "state.config" in text
    assert "No services configured." in text
    assert "Run a profile wrapper or edit config.toml." in text


def test_frontend_config_disclosure_is_collapsed_and_uses_open_endpoint() -> None:
    text = _static_text()

    assert '"details"' in text
    assert '{ class: "df-config-disclosure" }' in text
    assert "dotfill config" in text
    assert "open-config-folder" in text
    assert "path-open-btn" in text
    assert "df-config-disclosure[open]" in text
    assert "btn-link" not in text


def test_frontend_import_source_state_wiring_is_present() -> None:
    text = _static_text()

    assert "createImportSourceState" in text
    assert "browseImportSource" in text
    assert "dropImportSource" in text
    assert "loadScanFromActiveSource" in text
    assert 'mode: "empty"' in text
    assert 'mode: "browse"' in text
    assert 'mode: "drop"' in text
    assert "Dropped file:" in text


def test_frontend_import_test_wiring_is_present() -> None:
    text = _static_text()

    assert "import_test_state.js" in text
    assert "canTestImportRow" in text
    assert "importTestRequest" in text
    assert "import-test-cell" in text
    assert "import-test-header" in text
    assert '[icon("flask")]' in text
    assert "Test this service using the imported API key" in text
    assert "/api/import/test" in text
    assert "clearImportTestState" in text
    assert "resetImportTestStates" in text


def test_frontend_derived_default_action_wiring_is_present() -> None:
    text = _static_text()

    assert "writeDerivedDefault" in text
    assert "/api/derived/" in text
    assert "Fill with default" in text
    assert "Use default" in text
    assert "derived-action" in text
    assert 'd.status === "missing"' in text
    assert 'd.status === "diverged"' in text


def test_frontend_theme_toggle_wiring_is_present() -> None:
    text = _static_text()

    assert "theme_state.js" in text
    assert "renderThemeToggle" in text
    assert "Switch to dark mode" in text
    assert "Switch to light mode" in text
    assert 'id="ic-sun"' in text
    assert 'id="ic-moon"' in text
    assert '[data-theme="dark"]' in text


def test_frontend_uses_local_svg_favicon() -> None:
    index_text = STATIC_DIR.joinpath("index.html").read_text(encoding="utf-8")
    favicon_text = STATIC_DIR.joinpath("favicon.svg").read_text(encoding="utf-8")

    assert '<link rel="icon" type="image/svg+xml" href="/favicon.svg">' in index_text
    assert 'viewBox="0 0 32 32"' in favicon_text
    assert "stroke=" in favicon_text


def test_public_service_icons_have_bundled_sprite_symbols() -> None:
    sprite_keys = _sprite_icon_keys()

    assert SERVICE_ICON_KEYS <= sprite_keys


def test_private_ui_symbols_are_not_public_service_icons() -> None:
    private_ui_symbols = {
        "alert",
        "arrow-left",
        "arrow-right",
        "check",
        "cloud-upload",
        "moon",
        "refresh",
        "sun",
        "x",
    }

    assert private_ui_symbols <= _sprite_icon_keys()
    assert SERVICE_ICON_KEYS.isdisjoint(private_ui_symbols)


def test_frontend_icon_helper_falls_back_for_missing_symbols() -> None:
    app_text = STATIC_DIR.joinpath("app.js").read_text(encoding="utf-8")

    assert 'const requested = name || "key";' in app_text
    assert "document.getElementById(`ic-${requested}`)" in app_text
    assert 'const safe = document.getElementById(`ic-${requested}`) ? requested : "key";' in app_text
    assert 'u.setAttribute("href", `#ic-${safe}`);' in app_text
