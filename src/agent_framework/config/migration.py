"""Legacy dotenv to versioned config/secret migration helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from agent_framework.config.schema import FIELD_MAPPINGS, FieldKind
from agent_framework.config.secrets import SecretStore
from agent_framework.config.sources import parse_settings_value
from agent_framework.config.store import ConfigPaths


@dataclass(frozen=True)
class MigrationItem:
    env_key: str
    field: str
    destination: str
    secret: bool
    value: Any


def plan_dotenv_migration(path: Path) -> list[MigrationItem]:
    raw = dotenv_values(path)
    items: list[MigrationItem] = []
    for field, mapping in FIELD_MAPPINGS.items():
        env_key = field.upper()
        value = raw.get(env_key)
        if value is None:
            continue
        items.append(
            MigrationItem(
                env_key=env_key,
                field=field,
                destination=mapping.key,
                secret=mapping.kind is FieldKind.SECRET,
                value=parse_settings_value(field, value),
            )
        )
    return items


def apply_dotenv_migration(
    items: list[MigrationItem],
    *,
    paths: ConfigPaths,
    secret_store: SecretStore,
) -> None:
    from agent_framework.cli.commands.config import update_config_value

    for item in items:
        if item.secret:
            secret_store.set(item.destination, str(item.value))
        else:
            update_config_value(
                paths=paths,
                secret_store=secret_store,
                key=item.destination,
                value=item.value,
            )


__all__ = ["MigrationItem", "apply_dotenv_migration", "plan_dotenv_migration"]
