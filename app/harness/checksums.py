"""Content-addressable identification for every artifact the harness writes or reads.

A SHA-256 hex digest of a file's own bytes -- the harness's own "immutable artifact identifier"
requirement: two runs that produce byte-identical artifacts always get the same checksum, and
any accidental or intentional mutation of an artifact between stages is immediately detectable
by comparing this value, never by trusting a filename or timestamp alone.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_of_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_of_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


__all__ = ["sha256_of_file", "sha256_of_text"]
