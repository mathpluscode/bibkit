#!/usr/bin/env python3
from __future__ import annotations

"""Logging helper that tees stdout/stderr to a .bib.log file."""

import sys


class _Tee:
    """Write to both the original stream and a log file."""

    def __init__(self, original: object, log_file: object) -> None:
        self.original = original
        self.log_file = log_file

    def write(self, data: str) -> int:
        self.original.write(data)
        self.log_file.write(data)
        return len(data)

    def flush(self) -> None:
        self.original.flush()
        self.log_file.flush()


def setup(bib_path: str) -> None:
    """Tee stdout and stderr to ``<bib_path>.log`` (append mode)."""
    log_path = bib_path + ".log"
    log_file = open(log_path, "a", encoding="utf-8")  # noqa: SIM115
    sys.stdout = _Tee(sys.stdout, log_file)  # type: ignore[assignment]
    sys.stderr = _Tee(sys.stderr, log_file)  # type: ignore[assignment]
