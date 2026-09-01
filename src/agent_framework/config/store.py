"""Atomic, lock-protected TOML configuration storage."""

from __future__ import annotations

import os
import stat
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomli_w
from filelock import FileLock
from platformdirs import user_cache_path, user_config_path, user_data_path

from agent_framework.config.schema import CONFIG_SCHEMA_VERSION


@dataclass(frozen=True)
class ConfigPaths:
    user_config: Path
    project_config: Path
    data_dir: Path
    cache_dir: Path

    @classmethod
    def discover(cls, cwd: Path | None = None) -> ConfigPaths:
        current = (cwd or Path.cwd()).resolve()
        project_root = current
        for candidate in (current, *current.parents):
            if (candidate / ".myagen" / "config.toml").exists() or (
                candidate / ".git"
            ).exists():
                project_root = candidate
                break
        return cls(
            user_config=user_config_path("myagen") / "config.toml",
            project_config=project_root / ".myagen" / "config.toml",
            data_dir=user_data_path("myagen"),
            cache_dir=user_cache_path("myagen"),
        )


class ConfigStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = FileLock(str(path) + ".lock")

    def read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": CONFIG_SCHEMA_VERSION}
        with self._lock:
            with self.path.open("rb") as handle:
                payload = tomllib.load(handle)
        if payload.get("schema_version") != CONFIG_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported config schema_version: {payload.get('schema_version')!r}"
            )
        return payload

    def write(self, payload: dict[str, Any]) -> None:
        document = {"schema_version": CONFIG_SCHEMA_VERSION, **payload}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            fd, raw_temp_path = tempfile.mkstemp(
                prefix=f".{self.path.name}.",
                dir=self.path.parent,
            )
            temp_path = Path(raw_temp_path)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(tomli_w.dumps(document).encode("utf-8"))
                    handle.flush()
                    os.fsync(handle.fileno())
                os.chmod(temp_path, stat.S_IRUSR | stat.S_IWUSR)
                os.replace(temp_path, self.path)
                directory_fd = os.open(self.path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            finally:
                if temp_path.exists():
                    temp_path.unlink()

    def initialize(self) -> bool:
        if self.path.exists():
            return False
        self.write({})
        return True


def get_dotted(payload: dict[str, Any], dotted: str) -> Any:
    node: Any = payload
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(dotted)
        node = node[part]
    return node


def set_dotted(payload: dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    node = payload
    for part in parts[:-1]:
        child = node.setdefault(part, {})
        if not isinstance(child, dict):
            raise ValueError(f"Cannot set {dotted}: {part} is not a table")
        node = child
    node[parts[-1]] = value


def unset_dotted(payload: dict[str, Any], dotted: str) -> bool:
    parts = dotted.split(".")
    node = payload
    parents: list[tuple[dict[str, Any], str]] = []
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            return False
        parents.append((node, part))
        node = child
    removed = node.pop(parts[-1], None) is not None
    for parent, key in reversed(parents):
        child = parent.get(key)
        if isinstance(child, dict) and not child:
            parent.pop(key)
    return removed


__all__ = ["ConfigPaths", "ConfigStore", "get_dotted", "set_dotted", "unset_dotted"]
