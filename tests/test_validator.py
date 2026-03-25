"""Tests for core.validator — validate() function and ValidationReport/ValidationError."""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def lego():
    from core.library import Library
    return Library.load("lego_basic")


@pytest.fixture
def wood():
    from core.library import Library
    return Library.load("wood_basic")


def load_fixture(name: str) -> dict:
    return json.loads((ROOT / "tests" / "fixtures" / name).read_text())


# ---------------------------------------------------------------------------
# Valid fixture tests (0 errors expected)
# ---------------------------------------------------------------------------


def test_validate_single_brick(lego):
    from core.validator import validate
    design = load_fixture("single_brick_on_baseplate.json")
    report = validate(design, lego)
    assert report.is_valid, f"Unexpected errors: {[e.code for e in report.errors]}"


def test_validate_four_brick_wall(lego):
    from core.validator import validate
    design = load_fixture("four_brick_wall.json")
    report = validate(design, lego)
    assert report.is_valid, f"Unexpected errors: {[e.code for e in report.errors]}"


def test_validate_l_shape(lego):
    from core.validator import validate
    design = load_fixture("l_shape.json")
    report = validate(design, lego)
    assert report.is_valid, f"Unexpected errors: {[e.code for e in report.errors]}"


def test_validate_wood_cross(wood):
    from core.validator import validate
    design = load_fixture("wood_cross.json")
    report = validate(design, wood)
    # Wood has no stability checker yet, so no stability errors
    # But wood_cross has only 2 pieces with no baseplate, should be valid
    assert report.is_valid, f"Unexpected errors: {[e.code for e in report.errors]}"


# ---------------------------------------------------------------------------
# Broken design tests
# ---------------------------------------------------------------------------


def test_unknown_piece_type(lego):
    from core.validator import validate
    design = {
        "meta": {"name": "test", "library": "lego_basic"},
        "pieces": [
            {"id": "p1", "type": "brick_999x999", "position": [0, 0, 0]}
        ]
    }
    report = validate(design, lego)
    assert not report.is_valid
    assert any(e.code == "UNKNOWN_PIECE_TYPE" for e in report.errors)
    assert "p1" in report.errors[0].piece_ids


def test_unknown_to_piece(lego):
    from core.validator import validate
    design = {
        "meta": {"name": "test", "library": "lego_basic"},
        "pieces": [
            {
                "id": "base", "type": "baseplate_16x16", "position": [0, 0, 0],
                "connections": [{"face": "+y", "to_piece": "ghost", "to_face": "-y"}]
            }
        ]
    }
    report = validate(design, lego)
    assert not report.is_valid
    assert any(e.code == "UNKNOWN_PIECE_ID" for e in report.errors)


def test_missing_reverse_connection(lego):
    from core.validator import validate
    design = {
        "meta": {"name": "test", "library": "lego_basic"},
        "pieces": [
            {
                "id": "base", "type": "baseplate_16x16", "position": [0, 0, 0],
                "connections": [{"face": "+y", "to_piece": "b1", "to_face": "-y"}]
            },
            {
                "id": "b1", "type": "brick_2x4", "position": [120, 8, 140],
                "connections": []  # missing reverse!
            }
        ]
    }
    report = validate(design, lego)
    assert not report.is_valid
    assert any(e.code == "MISSING_REVERSE_CONNECTION" for e in report.errors)


def test_incompatible_connection(lego):
    from core.validator import validate
    design = {
        "meta": {"name": "test", "library": "lego_basic"},
        "pieces": [
            {
                "id": "b1", "type": "brick_2x4", "position": [0, 0, 0],
                "connections": [{"face": "+y", "to_piece": "b2", "to_face": "+y"}]
            },
            {
                "id": "b2", "type": "brick_2x4", "position": [0, 24, 0],
                "connections": [{"face": "+y", "to_piece": "b1", "to_face": "+y"}]
            }
        ]
    }
    report = validate(design, lego)
    assert not report.is_valid
    assert any(e.code == "INCOMPATIBLE_ATTACHMENT_TYPES" for e in report.errors)


def test_collision(lego):
    from core.validator import validate
    design = {
        "meta": {"name": "test", "library": "lego_basic"},
        "pieces": [
            {
                "id": "base", "type": "baseplate_16x16", "position": [0, 0, 0],
                "connections": [
                    {"face": "+y", "to_piece": "b1", "to_face": "-y"},
                    {"face": "+y", "to_piece": "b2", "to_face": "-y"}
                ]
            },
            {
                "id": "b1", "type": "brick_2x4", "position": [120, 8, 140],
                "connections": [{"face": "-y", "to_piece": "base", "to_face": "+y"}]
            },
            {
                "id": "b2", "type": "brick_2x4", "position": [120, 8, 140],
                "connections": [{"face": "-y", "to_piece": "base", "to_face": "+y"}]
            }
        ]
    }
    report = validate(design, lego)
    assert not report.is_valid
    assert any(e.code == "PIECE_COLLISION" for e in report.errors)
    collision_error = next(e for e in report.errors if e.code == "PIECE_COLLISION")
    assert "b1" in collision_error.piece_ids
    assert "b2" in collision_error.piece_ids


def test_floating_brick(lego):
    from core.validator import validate
    design = {
        "meta": {"name": "test", "library": "lego_basic"},
        "pieces": [
            {
                "id": "base", "type": "baseplate_16x16", "position": [0, 0, 0],
                "connections": [{"face": "+y", "to_piece": "b1", "to_face": "-y"}]
            },
            {
                "id": "b1", "type": "brick_2x4", "position": [120, 8, 140],
                "connections": [{"face": "-y", "to_piece": "base", "to_face": "+y"}]
            },
            {
                "id": "floater", "type": "brick_1x1", "position": [0, 100, 0]
            }
        ]
    }
    report = validate(design, lego)
    # Should have UNSTABLE_PIECE warning
    assert any(e.code == "UNSTABLE_PIECE" and "floater" in e.piece_ids for e in report.warnings)
    # Should have DISCONNECTED_PIECE warning
    assert any(e.code == "DISCONNECTED_PIECE" and "floater" in e.piece_ids for e in report.warnings)


def test_face_not_on_piece(lego):
    from core.validator import validate
    design = {
        "meta": {"name": "test", "library": "lego_basic"},
        "pieces": [
            {
                "id": "b1", "type": "brick_2x4", "position": [0, 0, 0],
                "connections": [{"face": "+x", "to_piece": "b2", "to_face": "-x"}]
            },
            {
                "id": "b2", "type": "brick_2x4", "position": [80, 0, 0],
                "connections": [{"face": "-x", "to_piece": "b1", "to_face": "+x"}]
            }
        ]
    }
    report = validate(design, lego)
    assert not report.is_valid
    assert any(e.code == "FACE_NOT_ON_PIECE" for e in report.errors)


# ---------------------------------------------------------------------------
# Position validation tests
# ---------------------------------------------------------------------------


def test_face_not_coplanar(lego):
    """Brick placed at wrong y so +y/-y faces don't meet."""
    from core.validator import validate
    design = {
        "meta": {"name": "test", "library": "lego_basic"},
        "pieces": [
            {
                "id": "base", "type": "baseplate_16x16", "position": [0, 0, 0],
                "connections": [{"face": "+y", "to_piece": "b1", "to_face": "-y"}]
            },
            {
                "id": "b1", "type": "brick_2x4", "position": [120, 50, 140],
                "connections": [{"face": "-y", "to_piece": "base", "to_face": "+y"}]
            }
        ]
    }
    report = validate(design, lego)
    assert not report.is_valid
    assert any(e.code == "FACE_NOT_COPLANAR" for e in report.errors)


def test_face_no_overlap(lego):
    """Two bricks coplanar but with no xz overlap on contact plane."""
    from core.validator import validate
    design = {
        "meta": {"name": "test", "library": "lego_basic"},
        "pieces": [
            {
                "id": "base", "type": "baseplate_16x16", "position": [0, 0, 0],
                "connections": [{"face": "+y", "to_piece": "b1", "to_face": "-y"}]
            },
            {
                "id": "b1", "type": "brick_2x4", "position": [500, 8, 500],
                "connections": [{"face": "-y", "to_piece": "base", "to_face": "+y"}]
            }
        ]
    }
    report = validate(design, lego)
    assert not report.is_valid
    assert any(e.code == "FACE_NO_OVERLAP" for e in report.errors)


def test_no_connection_to_prior(lego):
    """Second piece only connects to the third (declared after it)."""
    from core.validator import validate
    design = {
        "meta": {"name": "test", "library": "lego_basic"},
        "pieces": [
            {
                "id": "base", "type": "baseplate_16x16", "position": [0, 0, 0],
                "connections": [{"face": "+y", "to_piece": "b2", "to_face": "-y"}]
            },
            {
                "id": "b1", "type": "brick_2x4", "position": [120, 32, 140],
                "connections": [
                    {"face": "-y", "to_piece": "b2", "to_face": "+y"}
                ]
            },
            {
                "id": "b2", "type": "brick_2x4", "position": [120, 8, 140],
                "connections": [
                    {"face": "-y", "to_piece": "base", "to_face": "+y"},
                    {"face": "+y", "to_piece": "b1", "to_face": "-y"}
                ]
            }
        ]
    }
    report = validate(design, lego)
    assert any(e.code == "NO_CONNECTION_TO_PRIOR" and "b1" in e.piece_ids for e in report.errors)


def test_broken_chair_coplanarity(wood):
    """The broken chair fixture should fail: seat at y=430 vs back leg top at y=900."""
    from core.validator import validate
    design = load_fixture("wood_chair_broken.json")
    report = validate(design, wood)
    assert not report.is_valid
    assert any(e.code == "FACE_NOT_COPLANAR" for e in report.errors)
