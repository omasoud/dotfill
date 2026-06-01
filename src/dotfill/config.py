"""Generic effective configuration helpers."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from .config_models import EffectiveConfig
from .errors import UnresolvedIdentityError, UrlTemplateError

_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def resolve_url_template(
    template: str,
    identity_values: Mapping[str, str | None],
    *,
    allowed_identities: Iterable[str] | None = None,
) -> str:
    """Substitute `{IDENTITY_NAME}` placeholders in a URL template."""
    allowed = set(identity_values if allowed_identities is None else allowed_identities)
    result = template
    for placeholder in _PLACEHOLDER_RE.findall(template):
        if placeholder not in allowed:
            raise UrlTemplateError(
                f"URL template references unknown identity variable {{{placeholder}}}"
            )
        value = identity_values.get(placeholder)
        if value is None or value == "":
            raise UnresolvedIdentityError(
                f"URL template requires identity {placeholder}, which is unresolved"
            )
        result = result.replace(f"{{{placeholder}}}", value)
    return result


def collect_managed_variable_names(config: EffectiveConfig) -> set[str]:
    """Return variable names dotfill manages or reads as identity overrides."""
    names: set[str] = set(config.identities)
    names.update(config.derived_variables)
    for service in config.services.values():
        names.add(service.token_var)
    return names
