"""Resolve defaults, TOML, secrets, environment, and CLI overrides."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from pydantic import TypeAdapter

from agent_framework.config.schema import FIELD_MAPPINGS, FieldKind
from agent_framework.config.secrets import SecretStore
from agent_framework.config.settings import Settings
from agent_framework.config.store import ConfigPaths, ConfigStore, get_dotted


@dataclass(frozen=True)
class EffectiveSettings:
    settings: Settings
    sources: dict[str, str]


def _read_config_values(path: Path) -> dict[str, Any]:
    document = ConfigStore(path).read()
    values: dict[str, Any] = {}
    known_config_keys = {
        mapping.key
        for mapping in FIELD_MAPPINGS.values()
        if mapping.kind is not FieldKind.SECRET
    }

    def walk(node: dict[str, Any], prefix: str = "") -> None:
        for key, value in node.items():
            if not prefix and key == "schema_version":
                continue
            dotted = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict) and dotted not in known_config_keys:
                walk(value, dotted)
                continue
            if dotted not in known_config_keys:
                raise ValueError(f"Unknown config key: {dotted}")

    walk(document)
    for field, mapping in FIELD_MAPPINGS.items():
        if mapping.kind is FieldKind.SECRET:
            continue
        try:
            values[field] = get_dotted(document, mapping.key)
        except KeyError:
            continue
    return values


def resolve_settings(
    *,
    paths: ConfigPaths | None = None,
    secret_store: SecretStore | None = None,
    cli_overrides: dict[str, Any] | None = None,
    environ: dict[str, str] | None = None,
    dotenv_path: Path | None = None,
) -> EffectiveSettings:
    """Resolve the documented precedence chain and record each winning source."""
    resolved_paths = paths or ConfigPaths.discover()
    values = Settings(_env_file=None).model_dump()
    sources = dict.fromkeys(Settings.model_fields, "default")

    for label, path in (
        ("user", resolved_paths.user_config),
        ("project", resolved_paths.project_config),
    ):
        for field, value in _read_config_values(path).items():
            values[field] = value
            sources[field] = label

    if secret_store is not None:
        for field, mapping in FIELD_MAPPINGS.items():
            if mapping.kind is not FieldKind.SECRET:
                continue
            value = secret_store.get(mapping.key)
            if value is not None:
                values[field] = value
                sources[field] = "secret"

    env = dict(os.environ if environ is None else environ)
    dotenv_values_map = {
        key.upper(): value
        for key, value in dotenv_values(dotenv_path or Path(".env")).items()
        if value is not None
    }
    env_keys = dotenv_values_map | {key.upper(): value for key, value in env.items()}
    for field in Settings.model_fields:
        raw = env_keys.get(field.upper())
        if raw is None:
            continue
        values[field] = parse_settings_value(field, raw)
        sources[field] = "environment"

    for field, value in (cli_overrides or {}).items():
        if field not in Settings.model_fields:
            raise ValueError(f"Unknown CLI settings override: {field}")
        if value is not None:
            values[field] = value
            sources[field] = "cli"

    return EffectiveSettings(settings=Settings(_env_file=None, **values), sources=sources)


def parse_settings_value(field: str, raw: str) -> Any:
    """Parse one environment/config scalar using the Settings field annotation."""
    if field not in Settings.model_fields:
        raise ValueError(f"Unknown Settings field: {field}")
    parsed: Any = raw
    if raw.lstrip().startswith(("[", "{")):
        parsed = json.loads(raw)
    return TypeAdapter(Settings.model_fields[field].annotation).validate_python(parsed)


__all__ = ["EffectiveSettings", "parse_settings_value", "resolve_settings"]
