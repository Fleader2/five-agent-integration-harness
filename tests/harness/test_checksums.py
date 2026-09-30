"""Tests for ``app.harness.checksums``."""

from __future__ import annotations

import hashlib

from app.harness.checksums import sha256_of_file, sha256_of_text


def test_sha256_of_text_matches_hashlib():
    assert sha256_of_text("hello") == hashlib.sha256(b"hello").hexdigest()


def test_sha256_of_file_matches_content(tmp_path):
    path = tmp_path / "artifact.json"
    path.write_text('{"a": 1}')
    assert sha256_of_file(path) == hashlib.sha256(b'{"a": 1}').hexdigest()


def test_sha256_of_file_changes_when_content_changes(tmp_path):
    path = tmp_path / "artifact.json"
    path.write_text("version-1")
    first = sha256_of_file(path)
    path.write_text("version-2")
    second = sha256_of_file(path)
    assert first != second


def test_sha256_of_file_is_deterministic(tmp_path):
    path = tmp_path / "artifact.json"
    path.write_text("stable-content")
    assert sha256_of_file(path) == sha256_of_file(path)
