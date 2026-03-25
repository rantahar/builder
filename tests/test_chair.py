"""Test building a wooden chair using the builder API."""

import pytest

from core.builder import add_connection, add_piece, start_design
from core.library import Library
from core.validator import validate


@pytest.fixture
def wood():
    return Library.load("wood_basic")


def test_build_chair(wood):
    """Build a complete wooden chair and validate it has 0 errors.

    Layout (top-down view, +x is right, +z is back):

        bl_leg ----backrest---- br_leg      (back legs are 900mm tall)
          |                       |
        left_rail             right_rail
          |                       |
        fl_leg ---front_rail--- fr_leg      (front legs are 430mm tall)

    The seat (plywood) sits on top of the four rails at y=430.
    The backrest (lumber_2x4) connects the two back legs near the top.
    """

    # -- Step 1: Front left leg at origin (vertical post, 430mm tall) --
    # lumber_2x2 (45x45x2400), rotation [90,0,0] swaps h<->l => eff (45, 430, 45)
    design = start_design(
        wood, "Wooden Chair", "fl_leg", "lumber_2x2",
        rotation=[90, 0, 0], length_override=430,
    )

    # -- Step 2: Left side rail (along z-axis, connecting front-left to back-left) --
    # lumber_2x2 with length 360, rotation [0,0,0] => eff (45, 45, 360)
    # Attach its -z face to fl_leg's +z face.
    # fl_leg +z face contact plane is (x, y). offset=(0, 385) places rail flush
    # with the top of the leg: rail spans y=385..430.
    add_piece(
        design, wood,
        piece_id="left_rail", piece_type="lumber_2x2",
        rotation=[0, 0, 0],
        attach_face="-z", to_piece="fl_leg", to_face="+z",
        length_override=360,
        offset=(0, 385),
        fastener="4x70",
    )
    # left_rail pos: [0, 385, 45], eff (45, 45, 360)

    # -- Step 3: Back left leg (vertical post, 900mm tall) --
    # Attach its -z face to left_rail's +z face.
    # left_rail +z face contact plane is (x, y). offset=(0, -385) places leg
    # base at y=0: leg spans y=0..900.
    add_piece(
        design, wood,
        piece_id="bl_leg", piece_type="lumber_2x2",
        rotation=[90, 0, 0],
        attach_face="-z", to_piece="left_rail", to_face="+z",
        length_override=900,
        offset=(0, -385),
        fastener="4x70",
    )
    # bl_leg pos: [0, 0, 405], eff (45, 900, 45)

    # -- Step 4: Front rail (along x-axis, connecting front-left to front-right) --
    # lumber_2x2 with length 360, rotation [0,90,0] swaps w<->l => eff (360, 45, 45)
    # Attach its -x face to fl_leg's +x face.
    # fl_leg +x face contact plane is (y, z). offset=(385, 0) places rail flush
    # with the top: rail spans y=385..430.
    add_piece(
        design, wood,
        piece_id="front_rail", piece_type="lumber_2x2",
        rotation=[0, 90, 0],
        attach_face="-x", to_piece="fl_leg", to_face="+x",
        length_override=360,
        offset=(385, 0),
        fastener="4x70",
    )
    # front_rail pos: [45, 385, 0], eff (360, 45, 45)

    # -- Step 5: Front right leg (vertical post, 430mm tall) --
    # Attach its -x face to front_rail's +x face.
    # front_rail +x face contact plane is (y, z). offset=(-385, 0) places leg
    # base at y=0.
    add_piece(
        design, wood,
        piece_id="fr_leg", piece_type="lumber_2x2",
        rotation=[90, 0, 0],
        attach_face="-x", to_piece="front_rail", to_face="+x",
        length_override=430,
        offset=(-385, 0),
        fastener="4x70",
    )
    # fr_leg pos: [405, 0, 0], eff (45, 430, 45)

    # -- Step 6: Right side rail (along z-axis, connecting front-right to back-right) --
    # Attach its -z face to fr_leg's +z face, flush with top.
    add_piece(
        design, wood,
        piece_id="right_rail", piece_type="lumber_2x2",
        rotation=[0, 0, 0],
        attach_face="-z", to_piece="fr_leg", to_face="+z",
        length_override=360,
        offset=(0, 385),
        fastener="4x70",
    )
    # right_rail pos: [405, 385, 45], eff (45, 45, 360)

    # -- Step 7: Back rail (along x-axis, connecting back-left to back-right) --
    # Attach its -x face to bl_leg's +x face, flush with seat height.
    # bl_leg +x face contact plane is (y, z). offset=(385, 0) places rail at
    # y=385..430, z=405.
    add_piece(
        design, wood,
        piece_id="back_rail", piece_type="lumber_2x2",
        rotation=[0, 90, 0],
        attach_face="-x", to_piece="bl_leg", to_face="+x",
        length_override=360,
        offset=(385, 0),
        fastener="4x70",
    )
    # back_rail pos: [45, 385, 405], eff (360, 45, 45)

    # -- Step 8: Back right leg (vertical post, 900mm tall) --
    # Attach its -z face to right_rail's +z face.
    # right_rail +z face contact plane is (x, y). offset=(0, -385) places leg
    # base at y=0.
    add_piece(
        design, wood,
        piece_id="br_leg", piece_type="lumber_2x2",
        rotation=[90, 0, 0],
        attach_face="-z", to_piece="right_rail", to_face="+z",
        length_override=900,
        offset=(0, -385),
        fastener="4x70",
    )
    # br_leg pos: [405, 0, 405], eff (45, 900, 45)

    # Secondary connection: br_leg also connects to back_rail
    add_connection(design, "br_leg", "-x", "back_rail", "+x", fastener="4x70")

    # -- Step 9: Plywood seat on top of the rail frame --
    # plywood_18mm, rotation [0,0,0] => eff (450, 18, 405)
    # Attach its -y face to left_rail's +y face.
    # left_rail +y at y=430. Contact plane for +y is (x, z).
    # left_rail pos is [0, 385, 45]. offset=(0, -45) places seat at z=0.
    # Seat spans x=0..450, z=0..405 — covers the frame without overlapping back legs.
    add_piece(
        design, wood,
        piece_id="seat", piece_type="plywood_18mm",
        rotation=[0, 0, 0],
        attach_face="-y", to_piece="left_rail", to_face="+y",
        width_override=450, length_override=405,
        offset=(0, -45),
        fastener="4x50",
    )
    # seat pos: [0, 430, 0], eff (450, 18, 405)

    # Secondary seat connections to other rails
    add_connection(design, "seat", "-y", "right_rail", "+y", fastener="4x50")
    add_connection(design, "seat", "-y", "front_rail", "+y", fastener="4x50")

    # -- Step 10: Backrest rail connecting the two back legs near the top --
    # lumber_2x4 (45x95x2400), rotation [0,90,0] swaps w<->l => eff (360, 95, 45)
    # Attach its -x face to bl_leg's +x face.
    # bl_leg +x face contact plane is (y, z). offset=(805, 0) places backrest
    # at y=805..900, flush with the top of the back legs.
    add_piece(
        design, wood,
        piece_id="backrest", piece_type="lumber_2x4",
        rotation=[0, 90, 0],
        attach_face="-x", to_piece="bl_leg", to_face="+x",
        length_override=360,
        offset=(805, 0),
        fastener="4x70",
    )
    # backrest pos: [45, 805, 405], eff (360, 95, 45)

    # Secondary connection: backrest also connects to br_leg
    add_connection(design, "backrest", "+x", "br_leg", "-x", fastener="4x70")

    # -- Validate the complete chair design --
    report = validate(design, wood)

    # Print any errors for debugging
    for err in report.errors:
        print(f"ERROR [{err.code}]: {err.message}")
    for warn in report.warnings:
        print(f"WARNING [{warn.code}]: {warn.message}")

    assert len(report.errors) == 0, (
        f"Expected 0 errors, got {len(report.errors)}: "
        f"{[(e.code, e.message) for e in report.errors]}"
    )

    # Verify we have the expected number of pieces
    assert len(design["pieces"]) == 10  # 4 legs + 4 rails + seat + backrest
