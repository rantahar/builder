import json
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "core" / "schema" / "design.schema.json"
FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture
def schema():
    return json.loads(SCHEMA_PATH.read_text())


@pytest.fixture(params=["single_brick_on_baseplate", "four_brick_wall", "l_shape"])
def fixture_design(request):
    return json.loads((FIXTURES / f"{request.param}.json").read_text())


# --- Schema validation ---


def test_fixtures_valid(schema, fixture_design):
    jsonschema.validate(fixture_design, schema)


def test_missing_meta_rejected(schema):
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"pieces": []}, schema)


def test_missing_pieces_rejected(schema):
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"meta": {"name": "x", "library": "x"}}, schema)


def test_piece_missing_position_rejected(schema):
    design = {
        "meta": {"name": "x", "library": "x"},
        "pieces": [{"id": "p1", "type": "brick_1x1"}],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(design, schema)


def test_invalid_face_in_connection_rejected(schema):
    design = {
        "meta": {"name": "x", "library": "x"},
        "pieces": [
            {
                "id": "p1",
                "type": "brick_1x1",
                "position": [0, 0, 0],
                "connections": [{"face": "top", "to_piece": "p2", "to_face": "+y"}],
            }
        ],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(design, schema)


def test_extra_fields_allowed(schema):
    design = {
        "meta": {"name": "x", "library": "x", "author": "test"},
        "pieces": [
            {
                "id": "p1",
                "type": "brick_1x1",
                "position": [0, 0, 0],
                "weight_kg": 0.5,
            }
        ],
        "notes": "some future field",
    }
    jsonschema.validate(design, schema)


# --- Fixture content checks ---


def test_single_brick_has_two_pieces():
    design = json.loads((FIXTURES / "single_brick_on_baseplate.json").read_text())
    assert len(design["pieces"]) == 2


def test_four_brick_wall_has_five_pieces():
    design = json.loads((FIXTURES / "four_brick_wall.json").read_text())
    assert len(design["pieces"]) == 5  # baseplate + 4 bricks


def test_four_brick_wall_connections_are_consistent():
    """Every connection A->B should have a matching B->A."""
    design = json.loads((FIXTURES / "four_brick_wall.json").read_text())
    pieces_by_id = {p["id"]: p for p in design["pieces"]}

    for piece in design["pieces"]:
        for conn in piece.get("connections", []):
            other = pieces_by_id[conn["to_piece"]]
            reverse = [
                c
                for c in other.get("connections", [])
                if c["to_piece"] == piece["id"]
                and c["face"] == conn["to_face"]
                and c["to_face"] == conn["face"]
            ]
            assert len(reverse) == 1, (
                f"Missing reverse connection: {piece['id']}:{conn['face']} -> "
                f"{conn['to_piece']}:{conn['to_face']}"
            )


def test_l_shape_has_rotation():
    design = json.loads((FIXTURES / "l_shape.json").read_text())
    arm_b = next(p for p in design["pieces"] if p["id"] == "arm_b")
    assert arm_b["rotation"] == [0, 90, 0]


def test_all_fixtures_reference_lego_basic():
    for name in ["single_brick_on_baseplate", "four_brick_wall", "l_shape"]:
        design = json.loads((FIXTURES / f"{name}.json").read_text())
        assert design["meta"]["library"] == "lego_basic"


def test_all_pieces_have_unique_ids():
    for name in ["single_brick_on_baseplate", "four_brick_wall", "l_shape"]:
        design = json.loads((FIXTURES / f"{name}.json").read_text())
        ids = [p["id"] for p in design["pieces"]]
        assert len(ids) == len(set(ids)), f"Duplicate IDs in {name}"
