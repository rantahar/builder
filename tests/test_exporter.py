"""Tests for core.exporter.export_ldr and _ldraw_color."""

import json
import warnings
from pathlib import Path

import pytest

from core.exporter import export_ldr, _ldraw_color
from core.library import Library

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture(scope="module")
def lego():
    return Library.load("lego_basic")


@pytest.fixture(scope="module")
def wood():
    return Library.load("wood_basic")


@pytest.fixture(scope="module")
def single_brick_design():
    return json.loads((FIXTURES / "single_brick_on_baseplate.json").read_text())


# ---------------------------------------------------------------------------
# export_ldr — file creation and return value
# ---------------------------------------------------------------------------


def test_export_creates_file(single_brick_design, lego, tmp_path):
    out = tmp_path / "test_output.ldr"
    export_ldr(single_brick_design, lego, out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_export_returns_path(single_brick_design, lego, tmp_path):
    out = tmp_path / "test_output.ldr"
    result = export_ldr(single_brick_design, lego, out)
    assert result == out


# ---------------------------------------------------------------------------
# export_ldr — LDraw file structure
# ---------------------------------------------------------------------------


def test_export_header(single_brick_design, lego, tmp_path):
    out = tmp_path / "test_output.ldr"
    export_ldr(single_brick_design, lego, out)
    lines = out.read_text().splitlines()
    assert lines[0].startswith("0 FILE")
    assert lines[1] == "0 Single brick on baseplate"
    assert lines[2] == "0 Author: BuildScaffold"


def test_export_footer(single_brick_design, lego, tmp_path):
    out = tmp_path / "test_output.ldr"
    export_ldr(single_brick_design, lego, out)
    lines = out.read_text().splitlines()
    # Strip trailing blank line if present
    last = lines[-1] if lines[-1].strip() else lines[-2]
    assert last == "0 NOFILE"


def test_export_piece_lines(single_brick_design, lego, tmp_path):
    out = tmp_path / "test_output.ldr"
    export_ldr(single_brick_design, lego, out)
    content = out.read_text()
    type1_lines = [ln for ln in content.splitlines() if ln.startswith("1 ")]
    assert len(type1_lines) == 2

    part_ids = [ln.split()[-1] for ln in type1_lines]
    assert "3867.dat" in part_ids   # baseplate_16x16
    assert "3001.dat" in part_ids   # brick_2x4


def test_export_color_mapping(single_brick_design, lego, tmp_path):
    out = tmp_path / "test_output.ldr"
    export_ldr(single_brick_design, lego, out)
    type1_lines = [ln for ln in out.read_text().splitlines() if ln.startswith("1 ")]

    # Each type-1 line: "1 <color> <x> <y> <z> <3x3 matrix> <part>"
    colors_by_part = {ln.split()[-1]: int(ln.split()[1]) for ln in type1_lines}
    assert colors_by_part["3867.dat"] == 2   # green -> 2
    assert colors_by_part["3001.dat"] == 4   # red -> 4


# ---------------------------------------------------------------------------
# export_ldr — missing ldraw_id handling
# ---------------------------------------------------------------------------


def test_export_no_ldraw_id_warns(wood, tmp_path):
    """Pieces with no ldraw_id should be skipped with a warning."""
    design = {
        "meta": {"name": "Test", "library": "wood_basic"},
        "pieces": [
            {
                "id": "post1",
                "type": "lumber_2x2",
                "position": [0, 0, 0],
                "rotation": [0, 0, 0],
                "color": "brown",
                "connections": [],
            }
        ],
    }
    out = tmp_path / "no_ldraw.ldr"
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        export_ldr(design, wood, out)

    assert any("ldraw_id" in str(w.message).lower() or "no ldraw" in str(w.message).lower()
               for w in caught), f"Expected a warning; got: {[str(w.message) for w in caught]}"

    # The piece should have been skipped — no type-1 lines
    type1_lines = [ln for ln in out.read_text().splitlines() if ln.startswith("1 ")]
    assert type1_lines == []


# ---------------------------------------------------------------------------
# _ldraw_color — standalone colour mapping
# ---------------------------------------------------------------------------


def test_ldraw_color_red():
    assert _ldraw_color("red") == 4


def test_ldraw_color_green():
    assert _ldraw_color("green") == 2


def test_ldraw_color_case_insensitive():
    assert _ldraw_color("RED") == 4
    assert _ldraw_color("Green") == 2


def test_ldraw_color_unknown():
    assert _ldraw_color("fuschia_dream") == 16


def test_ldraw_color_none():
    assert _ldraw_color(None) == 16
