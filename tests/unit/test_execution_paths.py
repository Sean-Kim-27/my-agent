"""Path safety tests for the execution backend (Phase 4)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from agent_framework.execution.paths import PathSafetyError, resolve_safe_path


def test_resolves_relative_path_within_safe_root(tmp_path: Path) -> None:
    safe_root = tmp_path / "root"
    safe_root.mkdir()
    (safe_root / "notes.txt").write_text("hi")

    resolved = resolve_safe_path("notes.txt", safe_root=safe_root)

    assert resolved == (safe_root / "notes.txt").resolve()


def test_rejects_absolute_path_outside_safe_root(tmp_path: Path) -> None:
    safe_root = tmp_path / "root"
    safe_root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")

    with pytest.raises(PathSafetyError):
        resolve_safe_path(str(outside), safe_root=safe_root)


def test_rejects_parent_directory_traversal(tmp_path: Path) -> None:
    safe_root = tmp_path / "root"
    safe_root.mkdir()

    with pytest.raises(PathSafetyError):
        resolve_safe_path("../escape.txt", safe_root=safe_root)


def test_rejects_symlink_escape(tmp_path: Path) -> None:
    safe_root = tmp_path / "root"
    safe_root.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "secret.txt").write_text("secret")
    symlink = safe_root / "link"
    os.symlink(outside_dir, symlink)

    with pytest.raises(PathSafetyError):
        resolve_safe_path("link/secret.txt", safe_root=safe_root)


def test_allows_nested_symlink_inside_safe_root(tmp_path: Path) -> None:
    safe_root = tmp_path / "root"
    safe_root.mkdir()
    target = safe_root / "inner"
    target.mkdir()
    (target / "ok.txt").write_text("ok")
    link = safe_root / "alias"
    os.symlink(target, link)

    resolved = resolve_safe_path("alias/ok.txt", safe_root=safe_root)
    assert resolved == (target / "ok.txt").resolve()
