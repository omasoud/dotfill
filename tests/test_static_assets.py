"""Static checks for bundled frontend assets."""

from __future__ import annotations

from pathlib import Path


STATIC_DIR = Path(__file__).resolve().parents[1] / "src" / "dotfill" / "static"


def _static_text() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(STATIC_DIR.glob("*.*"))
    )


def test_frontend_uses_no_browser_storage() -> None:
    text = _static_text()

    forbidden = ["localStorage", "sessionStorage", "indexedDB", "document.cookie"]

    assert [term for term in forbidden if term in text] == []



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
