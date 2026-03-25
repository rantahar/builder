"""Tests for core.builder — position solver and build-steps compiler."""

import json
from pathlib import Path

import jsonschema
import pytest

from core.builder import add_connection, add_piece, build, start_design
from core.library import Library
from core.validator import validate

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def wood():
    return Library.load("wood_basic")


# ---------------------------------------------------------------------------
# start_design
# ---------------------------------------------------------------------------


def test_start_design(wood):
    design = start_design(
        wood, "test", "leg", "lumber_2x2",
        rotation=[90, 0, 0], length_override=430,
    )
    assert design["meta"]["name"] == "test"
    assert design["meta"]["library"] == "wood_basic"
    assert len(design["pieces"]) == 1
    p = design["pieces"][0]
    assert p["id"] == "leg"
    assert p["position"] == [0.0, 0.0, 0.0]
    assert p["rotation"] == [90, 0, 0]
    assert p["length_override"] == 430


def test_start_design_custom_position(wood):
    design = start_design(
        wood, "test", "p1", "lumber_2x2",
        position=[100, 0, 200],
    )
    assert design["pieces"][0]["position"] == [100, 0, 200]


# ---------------------------------------------------------------------------
# add_piece — position computation
# ---------------------------------------------------------------------------


def test_add_piece_on_top(wood):
    """Seat on top of a vertical leg: leg +y connects to seat -y."""
    design = start_design(
        wood, "test", "leg", "lumber_2x2",
        rotation=[90, 0, 0], length_override=430,
    )
    # Leg effective dims: (45, 430, 45). +y face at y=430.
    add_piece(
        design, wood,
        piece_id="seat", piece_type="plywood_18mm",
        rotation=[0, 0, 0],
        attach_face="-y", to_piece="leg", to_face="+y",
        width_override=400, length_override=400,
    )
    seat = design["pieces"][1]
    # Seat -y should be at y=430 → position y=430
    assert seat["position"][1] == pytest.approx(430.0)
    # Seat x,z should match leg's position (offset [0,0])
    assert seat["position"][0] == pytest.approx(0.0)
    assert seat["position"][2] == pytest.approx(0.0)


def test_add_piece_side(wood):
    """Rail attached to the +z face of a vertical leg."""
    design = start_design(
        wood, "test", "leg", "lumber_2x2",
        rotation=[90, 0, 0], length_override=430,
    )
    # Leg effective dims: (45, 430, 45). +z face at z=45.
    add_piece(
        design, wood,
        piece_id="rail", piece_type="lumber_2x2",
        rotation=[0, 0, 0],
        attach_face="-z", to_piece="leg", to_face="+z",
        length_override=310,
        offset=(0, 385),  # flush with leg top
    )
    rail = design["pieces"][1]
    # Rail effective dims: (45, 45, 310)
    # Rail -z at z=45 (coplanar with leg +z at z=45)
    assert rail["position"][2] == pytest.approx(45.0)
    # x = leg_x + offset_u = 0 + 0 = 0
    assert rail["position"][0] == pytest.approx(0.0)
    # y = leg_y + offset_v = 0 + 385 = 385
    assert rail["position"][1] == pytest.approx(385.0)


def test_add_piece_negative_face_attach(wood):
    """Attach new piece's +x face to existing piece's -x face."""
    design = start_design(
        wood, "test", "post_a", "lumber_2x2",
        rotation=[90, 0, 0], length_override=500,
    )
    # post_a at [0,0,0], effective (45, 500, 45). -x face at x=0.
    add_piece(
        design, wood,
        piece_id="rail", piece_type="lumber_2x2",
        rotation=[0, 90, 0],
        attach_face="+x", to_piece="post_a", to_face="-x",
        length_override=300,
    )
    rail = design["pieces"][1]
    # Rail effective dims: (300, 45, 45) after ry=90
    # Rail +x face at x = pos_x + 300 = 0 → pos_x = 0 - 300 = -300
    assert rail["position"][0] == pytest.approx(-300.0)


def test_add_piece_with_offset(wood):
    """Offset positions the piece within the contact plane."""
    design = start_design(
        wood, "test", "base", "lumber_2x2",
        rotation=[0, 0, 0], length_override=600,
    )
    # base effective dims: (45, 45, 600). +y face at y=45.
    add_piece(
        design, wood,
        piece_id="top", piece_type="lumber_2x2",
        rotation=[0, 90, 0],
        attach_face="-y", to_piece="base", to_face="+y",
        length_override=200,
        offset=(10, 100),
    )
    top = design["pieces"][1]
    # Top effective dims: (200, 45, 45) after ry=90
    # Normal axis (y): top -y at y=45 → pos_y = 45
    assert top["position"][1] == pytest.approx(45.0)
    # Contact plane for +y face: axes are x, z
    # x = base_x + offset_u = 0 + 10 = 10
    assert top["position"][0] == pytest.approx(10.0)
    # z = base_z + offset_v = 0 + 100 = 100
    assert top["position"][2] == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------


def test_reverse_connection_added(wood):
    """add_piece adds both forward and reverse connections."""
    design = start_design(
        wood, "test", "a", "lumber_2x2", length_override=100,
    )
    add_piece(
        design, wood,
        piece_id="b", piece_type="lumber_2x2",
        rotation=[0, 0, 0],
        attach_face="-y", to_piece="a", to_face="+y",
        length_override=100,
        fastener="4x50",
    )
    piece_a = design["pieces"][0]
    piece_b = design["pieces"][1]

    # Forward on b
    assert any(
        c["face"] == "-y" and c["to_piece"] == "a" and c["to_face"] == "+y"
        and c.get("fastener") == "4x50"
        for c in piece_b["connections"]
    )
    # Reverse on a
    assert any(
        c["face"] == "+y" and c["to_piece"] == "b" and c["to_face"] == "-y"
        and c.get("fastener") == "4x50"
        for c in piece_a["connections"]
    )


def test_add_secondary_connection(wood):
    """add_connection adds forward+reverse without changing position."""
    design = start_design(
        wood, "test", "a", "lumber_2x2",
        rotation=[90, 0, 0], length_override=400,
    )
    add_piece(
        design, wood,
        piece_id="b", piece_type="lumber_2x2",
        rotation=[0, 0, 0],
        attach_face="-z", to_piece="a", to_face="+z",
        length_override=300,
    )
    add_piece(
        design, wood,
        piece_id="c", piece_type="lumber_2x2",
        rotation=[90, 0, 0],
        attach_face="-z", to_piece="b", to_face="+z",
        length_override=400,
    )
    # Add secondary connection: c connects to a via +x/-x or similar
    # c is at end of rail b, a is at start — they may not share a face.
    # Instead, add a structural connection between a and c (e.g. diagonal brace).
    # For testing, just verify the connection entries are added.
    pos_before = [p["position"][:] for p in design["pieces"]]

    add_connection(design, "c", "+x", "a", "-x", fastener="4x70")

    # Positions unchanged
    for i, p in enumerate(design["pieces"]):
        assert p["position"] == pos_before[i]

    # Forward on c
    piece_c = next(p for p in design["pieces"] if p["id"] == "c")
    assert any(
        c["face"] == "+x" and c["to_piece"] == "a" for c in piece_c["connections"]
    )
    # Reverse on a
    piece_a = next(p for p in design["pieces"] if p["id"] == "a")
    assert any(
        c["face"] == "-x" and c["to_piece"] == "c" for c in piece_a["connections"]
    )


# ---------------------------------------------------------------------------
# Integration: build and validate
# ---------------------------------------------------------------------------


def test_build_wood_cross_and_validate(wood):
    """Build a simple wood cross (two lumber pieces) and validate it."""
    design = start_design(
        wood, "Wood cross", "horizontal", "lumber_2x4",
        rotation=[0, 0, 0], length_override=600,
    )
    # horizontal: effective (45, 95, 600) at [0, 0, 0]
    # +y face at y=95. Place vertical piece on top at midpoint.
    add_piece(
        design, wood,
        piece_id="vertical", piece_type="lumber_2x4",
        rotation=[0, 90, 0],
        attach_face="-y", to_piece="horizontal", to_face="+y",
        length_override=600,
        offset=(-277.5, 277.5),
    )

    report = validate(design, wood)
    assert report.is_valid, f"Errors: {[(e.code, e.message) for e in report.errors]}"


def test_build_rectangular_frame_and_validate(wood):
    """Build a rectangular frame from 4 posts and 4 rails, validate it."""
    design = start_design(
        wood, "Frame", "fl_leg", "lumber_2x2",
        rotation=[90, 0, 0], length_override=430,
    )
    # fl_leg: effective (45, 430, 45) at [0, 0, 0]

    # Left side rail: attaches to fl_leg +z face
    add_piece(
        design, wood,
        piece_id="left_rail", piece_type="lumber_2x2",
        rotation=[0, 0, 0],
        attach_face="-z", to_piece="fl_leg", to_face="+z",
        length_override=310,
        offset=(0, 385),
        fastener="4x70",
    )
    # left_rail: effective (45, 45, 310) at [0, 385, 45]

    # Back left leg: attaches to left_rail +z face
    add_piece(
        design, wood,
        piece_id="bl_leg", piece_type="lumber_2x2",
        rotation=[90, 0, 0],
        attach_face="-z", to_piece="left_rail", to_face="+z",
        length_override=430,
        offset=(0, -385),
        fastener="4x70",
    )
    # bl_leg: effective (45, 430, 45) at [0, 0, 355]

    # Front rail: attaches to fl_leg +x face
    add_piece(
        design, wood,
        piece_id="front_rail", piece_type="lumber_2x2",
        rotation=[0, 90, 0],
        attach_face="-x", to_piece="fl_leg", to_face="+x",
        length_override=310,
        offset=(385, 0),
        fastener="4x70",
    )
    # front_rail: effective (310, 45, 45) at [45, 385, 0]

    # Front right leg: attaches to front_rail +x face
    add_piece(
        design, wood,
        piece_id="fr_leg", piece_type="lumber_2x2",
        rotation=[90, 0, 0],
        attach_face="-x", to_piece="front_rail", to_face="+x",
        length_override=430,
        offset=(-385, 0),
        fastener="4x70",
    )
    # fr_leg: effective (45, 430, 45) at [355, 0, 0]

    # Right side rail: attaches to fr_leg +z face
    add_piece(
        design, wood,
        piece_id="right_rail", piece_type="lumber_2x2",
        rotation=[0, 0, 0],
        attach_face="-z", to_piece="fr_leg", to_face="+z",
        length_override=310,
        offset=(0, 385),
        fastener="4x70",
    )
    # right_rail: effective (45, 45, 310) at [355, 385, 45]

    # Back rail: attaches to bl_leg +x face
    add_piece(
        design, wood,
        piece_id="back_rail", piece_type="lumber_2x2",
        rotation=[0, 90, 0],
        attach_face="-x", to_piece="bl_leg", to_face="+x",
        length_override=310,
        offset=(385, 0),
        fastener="4x70",
    )
    # back_rail: effective (310, 45, 45) at [45, 385, 355]

    # Back right leg: attaches to right_rail +z
    add_piece(
        design, wood,
        piece_id="br_leg", piece_type="lumber_2x2",
        rotation=[90, 0, 0],
        attach_face="-z", to_piece="right_rail", to_face="+z",
        length_override=430,
        offset=(0, -385),
        fastener="4x70",
    )
    # br_leg at [355, 0, 355]

    # Secondary connections: br_leg also connects to back_rail
    add_connection(design, "br_leg", "-x", "back_rail", "+x", fastener="4x70")

    # Seat on top of the frame
    # left_rail is at [0, 385, 45]. Its +y contact plane axes are (x, z).
    # Seat should be at x=0, z=0 → offset from rail's (x=0, z=45) is (0, -45).
    add_piece(
        design, wood,
        piece_id="seat", piece_type="plywood_18mm",
        rotation=[0, 0, 0],
        attach_face="-y", to_piece="left_rail", to_face="+y",
        width_override=400, length_override=400,
        offset=(0, -45),
        fastener="4x50",
    )

    # Secondary seat connections to other rails
    add_connection(design, "seat", "-y", "right_rail", "+y", fastener="4x50")
    add_connection(design, "seat", "-y", "front_rail", "+y", fastener="4x50")
    add_connection(design, "seat", "-y", "back_rail", "+y", fastener="4x50")

    report = validate(design, wood)
    assert report.is_valid, f"Errors: {[(e.code, e.message) for e in report.errors]}"
    assert len(design["pieces"]) == 9


# ---------------------------------------------------------------------------
# build() — compile build steps JSON into design JSON
# ---------------------------------------------------------------------------


def load_fixture(name: str) -> dict:
    return json.loads((ROOT / "tests" / "fixtures" / name).read_text())


def test_build_steps_schema_valid():
    """The wood_chair.json fixture validates against the build steps schema."""
    schema = json.loads(
        (ROOT / "core" / "schema" / "buildsteps.schema.json").read_text()
    )
    steps = load_fixture("wood_chair.json")
    jsonschema.validate(steps, schema)


def test_build_simple_cross(wood):
    """Build a wood cross from build steps JSON."""
    steps = {
        "meta": {"name": "Cross", "library": "wood_basic"},
        "steps": [
            {"action": "place", "piece": "h", "type": "lumber_2x4", "length": 600},
            {"action": "attach", "piece": "v", "type": "lumber_2x4",
             "rotation": [0, 90, 0],
             "face": "-y", "to": "h", "to_face": "+y",
             "length": 600, "offset": [-277.5, 277.5]},
        ],
    }
    design = build(steps, wood)
    assert len(design["pieces"]) == 2
    report = validate(design, wood)
    assert report.is_valid, f"Errors: {[(e.code, e.message) for e in report.errors]}"


def test_build_chair_from_steps(wood):
    """Load wood_chair.json build steps, compile, and validate."""
    steps = load_fixture("wood_chair.json")
    design = build(steps, wood)
    assert len(design["pieces"]) == 10
    assert design["meta"]["name"] == "Wooden Chair"
    assert "groups" in design
    report = validate(design, wood)
    assert report.is_valid, f"Errors: {[(e.code, e.message) for e in report.errors]}"


def test_build_passes_groups_through(wood):
    """Groups from build steps are copied to the output design."""
    steps = {
        "meta": {"name": "Test", "library": "wood_basic"},
        "steps": [
            {"action": "place", "piece": "a", "type": "lumber_2x2", "length": 100},
        ],
        "groups": [{"id": "g1", "pieces": ["a"]}],
    }
    design = build(steps, wood)
    assert design["groups"] == [{"id": "g1", "pieces": ["a"]}]
