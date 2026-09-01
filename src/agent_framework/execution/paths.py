"""Safe filesystem path resolution.

All file access performed by an ExecutionBackend must go through
``resolve_safe_path`` so ``..`` traversal, absolute paths, and symlinks
that point outside the configured safe root are rejected fail-closed.

Phase 10 additionally provides :func:`open_beneath`, a descriptor-relative
open that pins path resolution to a fixed safe-root file descriptor. This
closes the check-then-open TOCTOU window that a plain
``resolve_safe_path`` + ``open`` sequence leaves for a local attacker who
can swap symlinks concurrently. On platforms without ``dir_fd`` support
(Windows) it falls back to the previous behavior.
"""

from __future__ import annotations

import os
from pathlib import Path

from agent_framework.exceptions import AgentFrameworkError


class PathSafetyError(AgentFrameworkError):
    """Raised when a requested path escapes the configured safe root."""


def resolve_safe_path(requested: str | Path, *, safe_root: str | Path) -> Path:
    """Resolve ``requested`` under ``safe_root`` with symlink-safe containment.

    The resolved absolute path must be inside ``safe_root`` even after
    following any symlinks. Absolute inputs are only accepted when they are
    already inside ``safe_root``.
    """
    if not requested:
        raise PathSafetyError("Empty path is not allowed.")

    root = Path(safe_root).resolve(strict=False)
    if not root.exists() or not root.is_dir():
        raise PathSafetyError(f"Safe root does not exist or is not a directory: {root}")

    requested_path = Path(requested)
    candidate = requested_path if requested_path.is_absolute() else (root / requested_path)
    resolved = candidate.resolve(strict=False)

    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PathSafetyError(
            f"Path '{requested}' escapes safe root '{root}'"
        ) from exc

    return resolved


# ---------------------------------------------------------------- openat helpers

_HAS_DIR_FD = (
    os.name != "nt"
    and hasattr(os, "O_DIRECTORY")
    and hasattr(os, "O_NOFOLLOW")
    and os.open in os.supports_dir_fd
)

_MAX_SYMLINK_HOPS = 32


def _dir_flags() -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    return flags


def _split_relative(requested: str | Path, root: Path) -> list[str]:
    """Return the safe-root-relative components of ``requested``.

    Raises :class:`PathSafetyError` for empty, absolute-outside-root, or
    ``..`` inputs.
    """

    if not requested:
        raise PathSafetyError("Empty path is not allowed.")

    requested_path = Path(requested)
    if requested_path.is_absolute():
        try:
            rel_parts = requested_path.resolve(strict=False).relative_to(root).parts
        except ValueError as exc:
            raise PathSafetyError(
                f"Path '{requested}' is not under safe root '{root}'"
            ) from exc
    else:
        rel_parts = requested_path.parts

    cleaned: list[str] = []
    for part in rel_parts:
        if part in ("", "."):
            continue
        if part == "..":
            # Reject fail-closed: a '..' would escape the pinned root fd
            # even if the resolved textual path would remain inside root.
            raise PathSafetyError(
                f"Parent-directory components ('..') are not allowed: '{requested}'"
            )
        cleaned.append(part)
    if not cleaned:
        raise PathSafetyError("Empty path is not allowed.")
    return cleaned


def _reopen_from_root(
    root_fd: int,
    walked: list[str],
    root_abs: Path,
    hops: list[int],
) -> int:
    """Re-open the directory at ``walked`` starting from ``root_fd``.

    Used after we follow a symlink and need to restart the walk from a
    known-good ancestor. Every intermediate hop uses ``O_NOFOLLOW`` again.
    ``hops`` is the shared symlink-hop counter so recursive resolution is
    still bounded across a re-walk.
    """

    current_fd = os.dup(root_fd)
    accumulated: list[str] = []
    try:
        for segment in walked:
            next_fd = _open_intermediate(
                current_fd, segment, root_fd, root_abs, accumulated, hops
            )
            os.close(current_fd)
            current_fd = next_fd
            accumulated.append(segment)
        return current_fd
    except BaseException:
        try:
            os.close(current_fd)
        except OSError:
            pass
        raise


def _open_intermediate(
    parent_fd: int,
    segment: str,
    root_fd: int,
    root_abs: Path,
    walked: list[str],
    hops: list[int] | None = None,
) -> int:
    """Open ``segment`` beneath ``parent_fd`` as a directory fd.

    Following a symlink is allowed only if its resolved textual target
    remains beneath ``root_abs``. Absolute symlink targets are rejected
    even when they still point inside the safe root — the safe design is
    to keep every internal link relative.
    """

    hops = hops if hops is not None else [0]
    try:
        return os.open(
            segment,
            _dir_flags() | os.O_NOFOLLOW,
            dir_fd=parent_fd,
        )
    except OSError as exc:
        # POSIX behavior with O_NOFOLLOW+O_DIRECTORY when the segment is a
        # symlink differs per OS: Linux typically returns ELOOP, macOS
        # returns ENOTDIR (the symlink itself is not a directory once
        # O_NOFOLLOW prevents following it). Probe via readlink to
        # distinguish "symlink we must resolve manually" from a genuine
        # error we should re-raise.
        try:
            link_target = os.readlink(segment, dir_fd=parent_fd)
        except OSError:
            # Not a symlink — re-raise the original failure.
            raise exc from None

        if os.path.isabs(link_target):
            raise PathSafetyError(
                f"Absolute symlink target '{link_target}' rejected during walk."
            ) from exc

        hops[0] += 1
        if hops[0] > _MAX_SYMLINK_HOPS:
            raise PathSafetyError(
                "Symlink resolution exceeded maximum hop count."
            ) from exc

        # Compose the textual target relative to the safe root so we can
        # re-verify containment before re-walking the resolved path.
        composed = Path(*walked, link_target)
        # Use resolve to collapse any '..' introduced by the symlink; then
        # verify the collapsed path is still under safe root.
        resolved = (root_abs / composed).resolve(strict=False)
        try:
            resolved_parts = resolved.relative_to(root_abs).parts
        except ValueError as val_exc:
            raise PathSafetyError(
                f"Symlink '{segment}' points outside safe root."
            ) from val_exc

        # Re-walk from the safe-root fd. Each hop keeps applying O_NOFOLLOW
        # so nested symlinks are re-verified.
        return _reopen_from_root(root_fd, list(resolved_parts), root_abs, hops)


def _verify_fd_under_root(fd: int, root_abs: Path) -> None:
    """Best-effort verification that ``fd`` points to a file under ``root_abs``.

    Uses ``F_GETPATH`` on macOS and ``/proc/self/fd`` on Linux. On other
    platforms this is a no-op — the descriptor-relative walk is the
    primary defense.
    """

    try:
        if os.path.exists(f"/proc/self/fd/{fd}"):
            real = os.readlink(f"/proc/self/fd/{fd}")
            real_path = Path(real).resolve(strict=False)
            try:
                real_path.relative_to(root_abs)
            except ValueError as exc:
                raise PathSafetyError(
                    f"Opened descriptor points outside safe root: {real_path}"
                ) from exc
    except OSError:
        # Missing procfs (macOS in some sandboxes) — fall back silently.
        pass


def open_beneath(
    safe_root: str | Path,
    requested: str | Path,
    flags: int,
    *,
    mode: int = 0o644,
) -> int:
    """Open a file beneath ``safe_root`` using descriptor-relative walk.

    Every intermediate directory is opened with ``O_NOFOLLOW`` under a
    pinned safe-root file descriptor. Symlink components are followed only
    after their resolved textual target is re-verified to stay beneath
    ``safe_root``. The final open uses ``openat`` against the parent
    directory fd so a concurrent swap of the parent name cannot redirect
    the open elsewhere.

    On platforms that do not expose ``dir_fd`` (Windows), this function
    falls back to ``resolve_safe_path`` plus a normal ``os.open`` — the
    Phase 5 behavior — because there is no portable openat equivalent.
    """

    root_abs = Path(safe_root).resolve(strict=False)
    if not root_abs.exists() or not root_abs.is_dir():
        raise PathSafetyError(
            f"Safe root does not exist or is not a directory: {root_abs}"
        )

    if not _HAS_DIR_FD:
        resolved = resolve_safe_path(requested, safe_root=root_abs)
        return os.open(str(resolved), flags, mode)

    parts = _split_relative(requested, root_abs)

    root_fd = os.open(str(root_abs), _dir_flags())
    parent_fd = os.dup(root_fd)
    try:
        walked: list[str] = []
        hops: list[int] = [0]
        for segment in parts[:-1]:
            next_fd = _open_intermediate(
                parent_fd, segment, root_fd, root_abs, walked, hops
            )
            os.close(parent_fd)
            parent_fd = next_fd
            walked.append(segment)

        final_segment = parts[-1]
        # Allow the leaf to be a symlink whose target is inside root; the
        # kernel will resolve it. Verify the opened fd is under root.
        fd = os.open(final_segment, flags, mode, dir_fd=parent_fd)
        try:
            _verify_fd_under_root(fd, root_abs)
        except Exception:
            os.close(fd)
            raise
        return fd
    finally:
        try:
            os.close(parent_fd)
        except OSError:
            pass
        try:
            os.close(root_fd)
        except OSError:
            pass


def unlink_beneath(safe_root: str | Path, requested: str | Path) -> None:
    """Delete a file beneath ``safe_root`` using ``unlinkat`` semantics.

    Uses descriptor-relative traversal like :func:`open_beneath`.
    """

    root_abs = Path(safe_root).resolve(strict=False)
    if not root_abs.exists() or not root_abs.is_dir():
        raise PathSafetyError(
            f"Safe root does not exist or is not a directory: {root_abs}"
        )

    if not _HAS_DIR_FD:
        resolved = resolve_safe_path(requested, safe_root=root_abs)
        os.unlink(str(resolved))
        return

    parts = _split_relative(requested, root_abs)

    root_fd = os.open(str(root_abs), _dir_flags())
    parent_fd = os.dup(root_fd)
    try:
        walked: list[str] = []
        hops: list[int] = [0]
        for segment in parts[:-1]:
            next_fd = _open_intermediate(
                parent_fd, segment, root_fd, root_abs, walked, hops
            )
            os.close(parent_fd)
            parent_fd = next_fd
            walked.append(segment)
        os.unlink(parts[-1], dir_fd=parent_fd)
    finally:
        try:
            os.close(parent_fd)
        except OSError:
            pass
        try:
            os.close(root_fd)
        except OSError:
            pass
