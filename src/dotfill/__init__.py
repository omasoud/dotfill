"""dotfill — local-only API token/identity .env helper."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("dotfill")
except PackageNotFoundError:
    __version__ = "0.0.0"
