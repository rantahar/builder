import json
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "core" / "schema" / "library.schema.json"


@pytest.fixture
def schema():
    return json.loads(SCHEMA_PATH.read_text())


@pytest.fixture
def lego_library():
    return json.loads((ROOT / "libraries" / "lego_basic" / "library.json").read_text())


@pytest.fixture
def wood_library():
    return json.loads((ROOT / "libraries" / "wood_basic" / "library.json").read_text())


# --- Schema validation ---


def test_lego_library_valid(schema, lego_library):
    jsonschema.validate(lego_library, schema)


def test_wood_library_valid(schema, wood_library):
    jsonschema.validate(wood_library, schema)


def test_missing_required_field_rejected(schema):
    invalid = {"id": "x", "name": "x", "unit": "mm", "attachment_types": {}}
    # missing "pieces"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(invalid, schema)


def test_invalid_unit_rejected(schema):
    invalid = {
        "id": "x",
        "name": "x",
        "unit": "inches",
        "attachment_types": {},
        "pieces": [],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(invalid, schema)


def test_invalid_face_normal_rejected(schema):
    invalid = {
        "id": "x",
        "name": "x",
        "unit": "mm",
        "attachment_types": {"t": {"margin": 1, "spacing": 1, "compatible_with": []}},
        "pieces": [
            {
                "id": "p",
                "name": "p",
                "dimensions": {"width": 1, "height": 1, "length": 1},
                "faces": {"up": {"attachments": ["t"]}},
            }
        ],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(invalid, schema)


def test_zero_dimension_rejected(schema):
    invalid = {
        "id": "x",
        "name": "x",
        "unit": "mm",
        "attachment_types": {},
        "pieces": [
            {
                "id": "p",
                "name": "p",
                "dimensions": {"width": 0, "height": 1, "length": 1},
                "faces": {},
            }
        ],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(invalid, schema)


def test_extra_fields_allowed(schema):
    """additionalProperties: true means new fields don't break validation."""
    lib = {
        "id": "x",
        "name": "x",
        "unit": "mm",
        "attachment_types": {},
        "pieces": [
            {
                "id": "p",
                "name": "p",
                "dimensions": {"width": 1, "height": 1, "length": 1},
                "faces": {},
                "weight_kg": 2.5,
                "grain_direction": "+z",
            }
        ],
        "some_future_field": True,
    }
    jsonschema.validate(lib, schema)


# --- Library content checks ---


def test_lego_piece_count(lego_library):
    assert len(lego_library["pieces"]) == 18


def test_lego_all_pieces_have_studs_and_anti_studs(lego_library):
    for piece in lego_library["pieces"]:
        faces = piece["faces"]
        assert "stud" in faces["+y"]["attachments"], f"{piece['id']} missing stud"
        assert "anti_stud" in faces["-y"]["attachments"], f"{piece['id']} missing anti_stud"


def test_lego_brick_2x4_dimensions(lego_library):
    brick = next(p for p in lego_library["pieces"] if p["id"] == "brick_2x4")
    assert brick["dimensions"] == {"width": 80, "height": 24, "length": 40}
    assert brick["ldraw_id"] == "3001.dat"


def test_wood_posts_have_entry_and_receiver(wood_library):
    for piece in wood_library["pieces"]:
        if piece["category"] == "post":
            for face_name, face in piece["faces"].items():
                assert "screw_entry" in face["attachments"], (
                    f"{piece['id']} {face_name} missing screw_entry"
                )
                assert "screw_receiver" in face["attachments"], (
                    f"{piece['id']} {face_name} missing screw_receiver"
                )


def test_wood_planks_only_have_entry(wood_library):
    for piece in wood_library["pieces"]:
        if piece["category"] == "plank":
            for face_name, face in piece["faces"].items():
                assert "screw_entry" in face["attachments"]
                assert "screw_receiver" not in face["attachments"], (
                    f"{piece['id']} {face_name} should not have screw_receiver"
                )


def test_wood_all_variable_length(wood_library):
    for piece in wood_library["pieces"]:
        assert piece.get("variable_length") is True, f"{piece['id']} not variable_length"


# --- Grid locking ---


def test_lego_studs_are_grid_locked(lego_library):
    for name, atype in lego_library["attachment_types"].items():
        assert atype["grid_locked"] is True, f"{name} should be grid_locked"


def test_wood_screws_are_not_grid_locked(wood_library):
    for name, atype in wood_library["attachment_types"].items():
        assert atype["grid_locked"] is False, f"{name} should not be grid_locked"


# --- Attachment grid computation ---


def grid_positions(face_size, margin, spacing):
    """Compute attachment point positions along one axis."""
    positions = []
    p = margin
    while p <= face_size - margin:
        positions.append(p)
        p += spacing
    return positions


def grid_count(w, h, margin, spacing):
    return len(grid_positions(w, margin, spacing)) * len(grid_positions(h, margin, spacing))


def test_grid_lego_1x1():
    assert grid_count(20, 20, margin=10, spacing=20) == 1


def test_grid_lego_2x4():
    assert grid_count(80, 40, margin=10, spacing=20) == 8


def test_grid_lego_baseplate_16x16():
    assert grid_count(320, 320, margin=10, spacing=20) == 256


def test_grid_wood_plank_flat_face():
    """plank_18x95: flat face is 95 x 2400mm, margin=20, spacing=50."""
    count = grid_count(95, 2400, margin=20, spacing=50)
    assert count > 0


def test_grid_wood_plank_thin_edge():
    """plank_18x95: thin edge is 18mm wide — too narrow for any screw."""
    count = grid_count(18, 2400, margin=20, spacing=50)
    assert count == 0


def test_grid_wood_2x2_side():
    """lumber_2x2: 45mm side, margin=20 → 1 position across."""
    positions = grid_positions(45, margin=20, spacing=50)
    assert len(positions) == 1
    assert positions[0] == 20


# --- Compatibility checks ---


def test_lego_stud_compatible_with_anti_stud(lego_library):
    types = lego_library["attachment_types"]
    assert "anti_stud" in types["stud"]["compatible_with"]
    assert "stud" in types["anti_stud"]["compatible_with"]


def test_lego_stud_not_compatible_with_stud(lego_library):
    types = lego_library["attachment_types"]
    assert "stud" not in types["stud"]["compatible_with"]


def test_wood_entry_compatible_with_receiver(wood_library):
    types = wood_library["attachment_types"]
    assert "screw_receiver" in types["screw_entry"]["compatible_with"]
    assert "screw_entry" in types["screw_receiver"]["compatible_with"]


def test_wood_entry_not_compatible_with_entry(wood_library):
    types = wood_library["attachment_types"]
    assert "screw_entry" not in types["screw_entry"]["compatible_with"]
