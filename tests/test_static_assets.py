"""Static checks for bundled frontend assets."""

from __future__ import annotations

from pathlib import Path


STATIC_DIR = Path(__file__).resolve().parents[1] / "src" / "dotfill" / "static"


def _static_text() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(STATIC_DIR.glob("*.*"))
    )


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
    assert "editImportSource" in text
    assert "loadScanFromActiveSource" in text
    assert 'mode: "path"' in text
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
    assert "Test this service using the imported API key" in text
    assert "/api/import/test" in text
    assert "clearImportTestState" in text
    assert "resetImportTestStates" in text


def test_frontend_theme_toggle_wiring_is_present() -> None:
    text = _static_text()

    assert "theme_state.js" in text
    assert "renderThemeToggle" in text
    assert "Switch to dark mode" in text
    assert "Switch to light mode" in text
    assert 'id="ic-sun"' in text
    assert 'id="ic-moon"' in text
    assert '[data-theme="dark"]' in text
