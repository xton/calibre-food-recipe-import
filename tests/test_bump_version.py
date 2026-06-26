import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bump_version import bump, read_version, write_version

_SAMPLE = """\
    version = (0, 1, 0)
    minimum_calibre_version = (5, 0, 0)
"""


def test_read_version():
    assert read_version(_SAMPLE) == (0, 1, 0)


def test_read_ignores_other_tuples():
    # minimum_calibre_version must not be parsed as the version
    assert read_version(_SAMPLE) == (0, 1, 0)


def test_bump_patch():
    assert bump((0, 1, 0), "patch") == (0, 1, 1)


def test_bump_minor():
    assert bump((0, 1, 0), "minor") == (0, 2, 0)
    assert bump((0, 1, 5), "minor") == (0, 2, 0)   # patch resets to 0


def test_bump_major():
    assert bump((0, 1, 0), "major") == (1, 0, 0)
    assert bump((1, 3, 7), "major") == (2, 0, 0)   # minor + patch reset


def test_write_version_roundtrip():
    updated = write_version(_SAMPLE, (0, 2, 0))
    assert read_version(updated) == (0, 2, 0)
    # other tuples untouched
    assert "minimum_calibre_version = (5, 0, 0)" in updated


def test_write_version_leaves_surrounding_text():
    updated = write_version(_SAMPLE, (1, 0, 0))
    assert "minimum_calibre_version = (5, 0, 0)" in updated
    assert "version = (1, 0, 0)" in updated


def test_init_file_version_parseable():
    """Smoke-test that the real __init__.py has a readable version."""
    init = (Path(__file__).parent.parent / "calibre_plugin" / "__init__.py").read_text()
    major, minor, patch = read_version(init)
    assert major >= 0 and minor >= 0 and patch >= 0
