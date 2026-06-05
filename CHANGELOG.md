# Changelog

All notable changes to this project will be documented in this file. The format
is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Release notes are grouped by version and category. Dates use the `YYYY-MM-DD`
format.

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

[1.2.0]: https://github.com/omasoud/dotfill/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/omasoud/dotfill/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/omasoud/dotfill/compare/v0.3.0...v1.0.0
[0.3.0]: https://github.com/omasoud/dotfill/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/omasoud/dotfill/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/omasoud/dotfill/releases/tag/v0.1.0
