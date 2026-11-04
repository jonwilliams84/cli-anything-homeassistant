"""Regression test for the v1.61.2 release-pipeline failure.

The Release workflow ("Tag and release" / "Read the version main declares")
refuses to cut a release when ``cli_anything/*/__init__.py`` disagrees with
``setup.py``. The v1.61.1 commit bumped only setup.py, leaving
``__version__`` at 1.61.0, so every push to main failed the release job.

This test asserts the *behaviour* the gate checks: the package metadata
version and the runtime ``__version__`` must be identical semver strings.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SETUP_PY = REPO_ROOT / "setup.py"
INIT_PY = REPO_ROOT / "cli_anything" / "homeassistant" / "__init__.py"


def _declared_setup_version() -> str:
    match = re.search(
        r'^\s*version\s*=\s*["\']([^"\']+)["\']', SETUP_PY.read_text(), re.M
    )
    assert match, "setup.py declares no version="
    return match.group(1)


def _declared_init_version() -> str:
    match = re.search(
        r'^__version__\s*=\s*["\']([^"\']+)["\']', INIT_PY.read_text(), re.M
    )
    assert match, f"{INIT_PY} declares no __version__"
    return match.group(1)


def test_setup_and_init_declare_the_same_version() -> None:
    assert _declared_init_version() == _declared_setup_version()


def test_declared_version_is_semver() -> None:
    version = _declared_setup_version()
    assert re.fullmatch(r"\d+\.\d+\.\d+", version), (
        f"setup.py version {version!r} is not MAJOR.MINOR.PATCH"
    )
