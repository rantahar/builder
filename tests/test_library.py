from pathlib import Path

import pytest

from core.library import Library

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def lego():
    return Library.load("lego_basic")


@pytest.fixture
def wood():
    return Library.load("wood_basic")


def test_load_lego_basic(lego):
    assert len(lego.list_pieces()) == 18


def test_load_wood_basic(wood):
    assert len(wood.list_pieces()) == 6


def test_library_properties(lego):
    assert lego.id == "lego_basic"
    assert lego.name == "Lego Basic Bricks"
    assert lego.unit == "ldu"


def test_get_piece(lego):
    piece = lego.get_piece("brick_2x4")
    assert piece.id == "brick_2x4"
    assert piece.name == "Brick 2x4"
    assert piece.dimensions == {"width": 80, "height": 24, "length": 40}
    assert piece.ldraw_id == "3001.dat"
    assert len(piece.colors) == 6


def test_get_piece_not_found(lego):
    with pytest.raises(KeyError):
        lego.get_piece("nonexistent")


def test_list_pieces_by_category(lego):
    assert len(lego.list_pieces(category="brick")) == 11
    assert len(lego.list_pieces(category="plate")) == 5
    assert len(lego.list_pieces(category="baseplate")) == 2


def test_grid_positions_brick_2x4(lego):
    piece = lego.get_piece("brick_2x4")
    positions = piece.grid_positions("+y", lego)
    # width=80 → positions at 10,30,50,70 (4); length=40 → positions at 10,30 (2)
    assert len(positions) == 8


def test_grid_positions_baseplate(lego):
    piece = lego.get_piece("baseplate_16x16")
    positions = piece.grid_positions("+y", lego)
    # 320×320 with margin=10, spacing=20 → 16×16=256 positions
    assert len(positions) == 256


def test_variable_length_pieces(wood):
    piece = wood.get_piece("lumber_2x4")
    assert piece.variable_length is True


def test_attachment_type_properties(lego):
    stud = lego.attachment_types["stud"]
    assert stud.margin == 10
    assert stud.spacing == 20
    assert stud.grid_locked is True
    assert stud.compatible_with == ["anti_stud"]


def test_face_attachments(lego):
    piece = lego.get_piece("brick_2x4")
    assert piece.faces["+y"].attachments == ["stud"]
    assert piece.faces["-y"].attachments == ["anti_stud"]


# --- Geometry tests ---


def test_get_geometry_returns_trimesh(lego):
    import trimesh

    piece = lego.get_piece("brick_2x4")
    mesh = piece.get_geometry(lego)
    assert isinstance(mesh, trimesh.Trimesh)
    assert len(mesh.vertices) > 0
    assert len(mesh.faces) > 0


def test_geometry_bounding_box_matches_dimensions(lego):
    piece = lego.get_piece("brick_2x4")
    mesh = piece.get_geometry(lego)
    extents = mesh.bounding_box.extents
    # Should roughly match width=80, height=24, length=40
    assert abs(extents[0] - 80) < 1
    assert abs(extents[1] - 24) < 1
    assert abs(extents[2] - 40) < 1


def test_geometry_for_piece_without_ldraw(wood):
    piece = wood.get_piece("lumber_2x4")
    mesh = piece.get_geometry(wood)
    # Wood pieces have no ldraw_id, should get bounding-box fallback
    assert mesh is not None
    assert len(mesh.vertices) > 0


def test_geometry_is_cached(lego):
    piece = lego.get_piece("brick_1x1")
    mesh1 = piece.get_geometry(lego)
    mesh2 = piece.get_geometry(lego)
    assert mesh1 is mesh2
