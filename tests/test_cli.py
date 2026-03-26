"""Tests for cli.main.DesignShell — command methods tested directly."""

import json
import shutil
from pathlib import Path

import pytest

from cli.main import DesignShell
from core.library import Library

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture
def lego_shell(tmp_path):
    """A DesignShell with lego_basic library rooted at tmp_path."""
    shutil.copy(FIXTURES / "single_brick_on_baseplate.json", tmp_path)
    return DesignShell(project_dir=tmp_path, library_id="lego_basic")


@pytest.fixture
def wood_shell(tmp_path):
    """A DesignShell with wood_basic library rooted at tmp_path."""
    shutil.copy(FIXTURES / "wood_chair.json", tmp_path)
    return DesignShell(project_dir=tmp_path, library_id="wood_basic")


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


def test_shell_init(lego_shell):
    assert lego_shell.library is not None
    assert lego_shell.library.id == "lego_basic"
    assert lego_shell.design is None


# ---------------------------------------------------------------------------
# do_load
# ---------------------------------------------------------------------------


def test_load_valid_file(lego_shell):
    lego_shell.do_load("single_brick_on_baseplate.json")
    assert lego_shell.design is not None
    assert lego_shell.design["meta"]["name"] == "Single brick on baseplate"


def test_load_nonexistent_file(lego_shell):
    lego_shell.do_load("nonexistent.json")
    assert lego_shell.design is None


def test_load_invalid_json(lego_shell, tmp_path):
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{ this is not valid json }")
    lego_shell.do_load("bad.json")
    assert lego_shell.design is None


def test_load_clears_previous_report(lego_shell):
    """Loading a new file should clear any existing validation report."""
    lego_shell.do_load("single_brick_on_baseplate.json")
    lego_shell.do_validate("")
    assert lego_shell.report is not None
    # Load again — report should be cleared
    lego_shell.do_load("single_brick_on_baseplate.json")
    assert lego_shell.report is None


# ---------------------------------------------------------------------------
# do_validate
# ---------------------------------------------------------------------------


def test_validate(lego_shell):
    lego_shell.do_load("single_brick_on_baseplate.json")
    lego_shell.do_validate("")
    assert lego_shell.report is not None
    assert lego_shell.report.is_valid is True


def test_validate_no_design(lego_shell):
    """Calling validate with no design loaded must not raise."""
    lego_shell.do_validate("")  # should not raise
    assert lego_shell.report is None


# ---------------------------------------------------------------------------
# do_reload
# ---------------------------------------------------------------------------


def test_reload(lego_shell, tmp_path):
    lego_shell.do_load("single_brick_on_baseplate.json")
    original_name = lego_shell.design["meta"]["name"]

    # Modify the file on disk
    design_file = tmp_path / "single_brick_on_baseplate.json"
    data = json.loads(design_file.read_text())
    data["meta"]["name"] = "Modified Name"
    design_file.write_text(json.dumps(data))

    lego_shell.do_reload("")
    assert lego_shell.design["meta"]["name"] == "Modified Name"
    assert lego_shell.design["meta"]["name"] != original_name


# ---------------------------------------------------------------------------
# do_export
# ---------------------------------------------------------------------------


def test_export(lego_shell, tmp_path):
    lego_shell.do_load("single_brick_on_baseplate.json")
    lego_shell.do_export("")
    exports_dir = tmp_path / "exports"
    ldr_files = list(exports_dir.glob("*.ldr"))
    assert len(ldr_files) == 1
    assert ldr_files[0].stat().st_size > 0


# ---------------------------------------------------------------------------
# do_quit
# ---------------------------------------------------------------------------


def test_quit_returns_true(lego_shell):
    assert lego_shell.do_quit("") is True


# ---------------------------------------------------------------------------
# Build-steps compilation (wood_chair fixture)
# ---------------------------------------------------------------------------


def test_load_build_steps(wood_shell):
    """Loading a build-steps design compiles it into a flat design with pieces."""
    wood_shell.do_load("wood_chair.json")
    assert wood_shell.design is not None
    assert "pieces" in wood_shell.design
    assert len(wood_shell.design["pieces"]) > 0
