"""Path safety tests for the execution backend (Phase 4 + Phase 10)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from agent_framework.execution.paths import (
    PathSafetyError,
    open_beneath,
    resolve_safe_path,
    unlink_beneath,
)


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


# ---------------------------------------------------------------- Phase 10


@pytest.mark.skipif(os.name == "nt", reason="dir_fd is POSIX-only")
def test_open_beneath_reads_regular_file(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "hello.txt").write_text("hi there")

    fd = open_beneath(root, "hello.txt", os.O_RDONLY)
    try:
        assert os.read(fd, 32) == b"hi there"
    finally:
        os.close(fd)


@pytest.mark.skipif(os.name == "nt", reason="dir_fd is POSIX-only")
def test_open_beneath_rejects_absolute_symlink_intermediate(tmp_path: Path) -> None:
    """An intermediate symlink whose target is an absolute path must fail.

    Even if that absolute path currently resolves inside safe_root, the
    descriptor-relative walk rejects absolute link targets to keep the walk
    unambiguously bounded by the pinned root fd.
    """
    root = tmp_path / "root"
    root.mkdir()
    inner = root / "inner"
    inner.mkdir()
    (inner / "leaf.txt").write_text("leaf")

    absolute_link = root / "abs_link"
    os.symlink(str(inner.resolve()), absolute_link)

    with pytest.raises(PathSafetyError):
        open_beneath(root, "abs_link/leaf.txt", os.O_RDONLY)


@pytest.mark.skipif(os.name == "nt", reason="dir_fd is POSIX-only")
def test_open_beneath_rejects_parent_traversal(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (tmp_path / "escape.txt").write_text("nope")

    with pytest.raises(PathSafetyError):
        open_beneath(root, "../escape.txt", os.O_RDONLY)


@pytest.mark.skipif(os.name == "nt", reason="dir_fd is POSIX-only")
def test_open_beneath_rejects_intermediate_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "leak.txt").write_text("leaked")
    # Relative symlink whose resolved target sits outside the safe root.
    os.symlink("../outside", root / "escape")

    with pytest.raises(PathSafetyError):
        open_beneath(root, "escape/leak.txt", os.O_RDONLY)


@pytest.mark.skipif(os.name == "nt", reason="dir_fd is POSIX-only")
def test_open_beneath_follows_relative_intermediate_symlink(tmp_path: Path) -> None:
    """Relative symlinks that stay inside safe_root are still followed."""
    root = tmp_path / "root"
    root.mkdir()
    target = root / "real"
    target.mkdir()
    (target / "note.txt").write_text("kept")
    os.symlink("real", root / "alias")

    fd = open_beneath(root, "alias/note.txt", os.O_RDONLY)
    try:
        assert os.read(fd, 32) == b"kept"
    finally:
        os.close(fd)


@pytest.mark.skipif(os.name == "nt", reason="dir_fd is POSIX-only")
def test_unlink_beneath_removes_file_only_inside_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    victim = root / "gone.txt"
    victim.write_text("bye")
    unlink_beneath(root, "gone.txt")
    assert not victim.exists()

    outside = tmp_path / "outside.txt"
    outside.write_text("keep")
    with pytest.raises(PathSafetyError):
        unlink_beneath(root, str(outside))
    assert outside.exists()
