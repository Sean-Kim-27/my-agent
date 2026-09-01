"""Stable process exit codes for automation consumers."""

from enum import IntEnum


class ExitCode(IntEnum):
    OK = 0
    USAGE = 2
    CONFIG = 3
    CONNECTION = 4
    POLICY = 5
    STORAGE = 6
    INTERRUPTED = 130


__all__ = ["ExitCode"]
