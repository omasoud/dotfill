# Changelog

All notable changes to this project will be documented in this file. The format
is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Release notes are grouped by version and category. Dates use the `YYYY-MM-DD`
format.

## [1.3.0] - 2026-06-06

### Added

- Added dashboard actions and a guarded API path to fill missing derived
  variables or reset diverged derived variables to their computed defaults.
- Added import-commit fill-in behavior for missing derived variables when a
  computed default is available.
- Added user-facing guidance for creating a first `config.toml` from a
  sanitized existing `.env` file with help from an AI coding agent.
- Added README guidance and a public example-repo link for wrapper-package use
  cases.

### Changed

- Clarified identity and derived variable states in maintainer documentation.
- Improved dashboard state refresh handling so a successful refresh clears a
  previous load error.

## [1.2.0] - 2026-06-05

### Added

- Added a practical security policy with supported-version and private
  vulnerability reporting guidance.
- Added a PyPI project metadata link to the repository security policy.

### Changed

- Hardened local API error responses so service-test transport and URL-template
  failures do not expose raw exception details to the web UI.
- Removed the typed-path import endpoint and UI flow. Import now uses browser
  Browse or drag-and-drop file content instead of asking the localhost server to
  read arbitrary paths.

### Security

- Addressed CodeQL findings for DOM XSS, path injection, and stack-trace
  exposure in the local web UI and API.

## [1.1.0] - 2026-06-05

### Added

- Added a public service icon registry with documented service icon keys.
- Added bundled service icon symbols for server, database, terminal, shield,
  search, globe, and lock use cases.

### Changed

- Unknown configured service icon names now raise config schema errors instead
  of rendering as blank icons.
- Frontend icon rendering now falls back to the key icon if a bundled SVG
  symbol is unavailable.

## [1.0.0] - 2026-06-05

### Added

- Added local SVG favicon support for the web UI.
- Added expanded service-test authentication coverage and documentation.

### Changed

- Enhanced service authentication support with multiple auth types.
- Updated user and maintainer documentation for service-test authentication.

## [0.3.0] - 2026-06-03

### Added

- Added the import testing feature for validating import aliases and source
  variables.
- Added web UI theme toggle support.

## [0.2.0] - 2026-06-01

### Added

- Added display and comparison metadata for identity and derived variable
  configuration.
- Added design and implementation specs for locked profiles and identity
  metadata.

### Changed

- Documented `run_dotfill` parameters in more detail.

## [0.1.0] - 2026-06-01

### Added

- Added the initial local-only dotfill CLI, API, configuration, documentation,
  and web UI.
- Added MIT licensing and PyPI publishing project metadata.

[1.3.0]: https://github.com/omasoud/dotfill/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/omasoud/dotfill/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/omasoud/dotfill/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/omasoud/dotfill/compare/v0.3.0...v1.0.0
[0.3.0]: https://github.com/omasoud/dotfill/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/omasoud/dotfill/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/omasoud/dotfill/releases/tag/v0.1.0
