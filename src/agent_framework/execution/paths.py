"""Safe filesystem path resolution.

All file access performed by an ExecutionBackend must go through
``resolve_safe_path`` so ``..`` traversal, absolute paths, and symlinks
that point outside the configured safe root are rejected fail-closed.
"""

from __future__ import annotations

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
