import pytest
from pathlib import Path
from fastapi import HTTPException
import os

from app.utils.path import safe_join


def test_safe_join_absolute_path(tmp_path):
    base = tmp_path
    subdir = "subdir"
    file = "file.txt"

    # Create a subdirectory and a file for testing
    (base / subdir).mkdir()
    (base / subdir / file).touch()

    # Test joining with a subdirectory and file
    result = safe_join(base, subdir, file)
    assert result == base / subdir / file


def test_safe_join_relative_path(tmp_path):
    backup_path = Path.cwd()
    os.chdir(tmp_path)
    base = Path("base_dir")
    base.mkdir()
    subdir = "subdir"
    file = "file.txt"

    (base / subdir).mkdir()
    (base / subdir / file).touch()

    # Test with relative=True
    result = safe_join(base, subdir, file, relative=True)
    expected = Path(base / subdir) / file
    assert result == expected
    os.chdir(backup_path)


def test_safe_join_path_traversal_attempt(tmp_path):
    base = tmp_path
    malicious_path = "../../../etc/passwd"

    # Test path traversal attempt
    with pytest.raises(HTTPException) as excinfo:
        safe_join(base, malicious_path)
    assert excinfo.value.status_code == 500


def test_safe_join_same_directory(tmp_path):
    base = tmp_path
    file = "file.txt"

    (base / file).touch()

    # Test joining with a file in the same directory
    result = safe_join(base, file)
    assert result == base / file


def test_safe_join_nested_subdirectories(tmp_path):
    base = tmp_path
    nested = Path("a/b/c")
    file = "file.txt"

    (base / nested).mkdir(parents=True)
    (base / nested / file).touch()

    # Test joining with nested subdirectories
    result = safe_join(base, "a", "b", "c", file)
    assert result == base / nested / file


def test_safe_join_relative_nested(tmp_path):
    backup_path = Path.cwd()
    os.chdir(tmp_path)
    base = Path("base_dir")
    base.mkdir()

    nested = Path("a/b/c")
    file = "file.txt"

    (base / nested).mkdir(parents=True)
    (base / nested / file).touch()

    # Test with relative=True and nested subdirectories
    result = safe_join(base, "a", "b", "c", file, relative=True)
    assert result == Path(base / "a/b/c/file.txt")
    os.chdir(backup_path)


def test_safe_join_empty_paths(tmp_path):
    base = tmp_path

    # Test with no additional paths
    result = safe_join(base)
    assert result == base


def test_safe_join_relative_empty_paths(tmp_path):
    backup_path = Path.cwd()
    os.chdir(tmp_path)
    base = Path(".")

    # Test with no additional paths and relative=True
    result = safe_join(base, relative=True)
    assert result == Path(".")
    os.chdir(backup_path)


def test_safe_join_symlink_traversal_outside_base(tmp_path):
    base = tmp_path
    subdir = base / "subdir"
    subdir.mkdir()
    # Symlink pointing outside the base directory
    outside_target = base.parent / "outside"
    outside_target.touch()
    symlink = subdir / "symlink"
    symlink.symlink_to(outside_target)

    # This should raise an HTTPException
    with pytest.raises(HTTPException) as excinfo:
        safe_join(base, "subdir", "symlink")
    assert excinfo.value.status_code == 500


def test_safe_join_symlink_inside_base(tmp_path):
    base = tmp_path
    subdir = base / "subdir"
    subdir.mkdir()
    target = base / "target"
    target.touch()
    symlink = subdir / "symlink"
    symlink.symlink_to(target)

    # This should work (target is inside the base)
    result = safe_join(base, "subdir", "symlink")
    assert result == target
