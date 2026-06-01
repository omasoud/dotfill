"""dotfill error hierarchy."""

from __future__ import annotations


class DotfillError(Exception):
    """Base class for all dotfill errors."""


class EnvParseError(DotfillError):
    """The `.env` file could not be parsed."""

    def __init__(self, message: str, *, line_number: int | None = None) -> None:
        super().__init__(message)
        self.line_number = line_number


class DuplicateManagedVariableError(DotfillError):
    """A managed variable appears more than once in `.env`."""

    def __init__(self, key: str, line_numbers: list[int]) -> None:
        self.key = key
        self.line_numbers = line_numbers
        super().__init__(
            f"Managed variable {key!r} is defined multiple times "
            f"(lines: {', '.join(str(n) for n in line_numbers)}). "
            "Remove the extras and re-run dotfill."
        )


class ConfigValidationError(DotfillError):
    """The effective configuration is invalid."""


class ConfigLoadError(ConfigValidationError):
    """A TOML configuration file could not be read or parsed."""


class ConfigSchemaError(ConfigValidationError):
    """A TOML configuration file has an invalid schema."""


class ConfigMergeError(ConfigValidationError):
    """TOML configuration layers could not be merged."""


class InvalidProfileNameError(DotfillError):
    """The requested config profile name is not safe to use as a directory."""


class IdentityDetectionError(DotfillError):
    """Identity detection failed in a non-fatal way (diagnostics-only)."""


class UnresolvedIdentityError(DotfillError):
    """No effective value can be resolved for a primary identity variable."""


class UrlTemplateError(DotfillError):
    """A URL template references an unknown variable or fails to resolve."""


class SaveError(DotfillError):
    """A save/write to `.env` failed."""


class ImportScanError(DotfillError):
    """An import scan was rejected or failed."""


class ServiceTestError(DotfillError):
    """A service test request failed unexpectedly."""


class ApiAuthError(DotfillError):
    """An API request was rejected due to invalid session token or Origin."""
