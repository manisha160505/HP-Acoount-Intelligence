"""Regression tests for the dataset path resolver.

`find_file_path` walked up from its own `__file__` looking for a stored
relative path, but the deepest walk stopped at `src/`:

    here = src/app/services/extractors
    here/../../..  ->  src/          # not the backend root

Datasets live at `hp-backend/data/accounts/...`, one level above `src/`, so no
`__file__` walk ever reached them. The only candidate that resolved was
`os.getcwd()`, which meant every entry point had to be started from
`hp-backend/` or it found no dataset files at all.

That failure is silent. `read_dataset_records(strict=False)` treats "not on
this machine" the same as "not registered", so a retrieval build started one
directory up dropped all 8 of an account's filings and indexed 7 documents
instead of 19 - a dashboard with no filed evidence behind it, built without
error.

These tests pin the two properties that matter: a file is found from a working
directory that knows nothing about it, and the working directory still wins
when both could resolve.

Run: python -m pytest tests/test_find_file_path.py -v
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.extractors.datasets import find_file_path


def same_path(a, b):
    """Compare two paths as paths, not as strings.

    The candidates are built differently - the working-directory one by
    `os.path.join`, the rest by `os.path.abspath` - so on Windows one keeps the
    forward slashes of the stored relative path and the other normalises them
    to backslashes. Both name the same file.
    """
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(
        os.path.normpath(b))


BACKEND_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


@pytest.fixture
def probe_under_backend_root(tmp_path):
    """A real file under the backend root, removed afterwards.

    Written for real rather than mocked: the resolver's whole job is to decide
    whether a path exists on this machine, so a fake filesystem would test the
    mock and not the bug.
    """
    rel = "data/__resolver_probe__/probe.txt"
    full = os.path.join(BACKEND_ROOT, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as fh:
        fh.write("probe")
    yield rel, full
    Path(full).unlink()
    Path(full).parent.rmdir()


def test_resolves_from_an_unrelated_working_directory(probe_under_backend_root,
                                                      tmp_path, monkeypatch):
    """The bug. From anywhere but hp-backend/, this used to return None."""
    rel, full = probe_under_backend_root
    monkeypatch.chdir(tmp_path)
    assert same_path(find_file_path(rel), full)


def test_resolves_from_the_repository_root(probe_under_backend_root,
                                           monkeypatch):
    """The exact directory that produced the truncated build."""
    rel, full = probe_under_backend_root
    monkeypatch.chdir(os.path.dirname(BACKEND_ROOT))
    assert same_path(find_file_path(rel), full)


def test_working_directory_still_wins(tmp_path, monkeypatch):
    """CWD stays first, so the seeder's relative writes keep resolving to it.

    Both locations hold the same relative path here; the resolver must return
    the working directory's copy, not the backend root's.
    """
    rel = "data/__resolver_probe__/probe.txt"
    backend_copy = os.path.join(BACKEND_ROOT, rel)
    os.makedirs(os.path.dirname(backend_copy), exist_ok=True)
    with open(backend_copy, "w", encoding="utf-8") as fh:
        fh.write("backend")

    cwd_copy = tmp_path / rel
    cwd_copy.parent.mkdir(parents=True)
    cwd_copy.write_text("cwd", encoding="utf-8")

    try:
        monkeypatch.chdir(tmp_path)
        assert same_path(find_file_path(rel), os.path.join(str(tmp_path), rel))
    finally:
        Path(backend_copy).unlink()
        Path(backend_copy).parent.rmdir()


def test_absent_file_is_still_absent(tmp_path, monkeypatch):
    """A widened search must not start inventing matches."""
    monkeypatch.chdir(tmp_path)
    assert find_file_path("data/nothing/here/at/all.csv") is None


def test_empty_path_is_none():
    assert find_file_path("") is None
    assert find_file_path(None) is None
