"""Build designs piece-by-piece through attachment declarations.

The primary entry point is build(), which compiles a build-steps JSON
into a design JSON. Each step mirrors one assembly action: place a piece,
attach a new piece to an existing one, or add a secondary connection.
Positions are computed automatically from attachments.

The lower-level functions (start_design, add_piece, add_connection) are
also available for programmatic use.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import jsonschema

from core.validator import effective_dims

if TYPE_CHECKING:
    from core.library import Library

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema" / "buildsteps.schema.json"

# Maps face label to (axis_index, sign)
_FACE_AXIS: dict[str, tuple[int, int]] = {
    "+x": (0, +1),
    "-x": (0, -1),
    "+y": (1, +1),
    "-y": (1, -1),
    "+z": (2, +1),
    "-z": (2, -1),
}


def build(steps: dict, library: "Library") -> dict:
    """Compile build steps JSON into a design JSON.

    Validates the input against the build steps schema, then executes
    each step in order to produce the design.
    """
    schema = json.loads(_SCHEMA_PATH.read_text())
    jsonschema.validate(steps, schema)

    design = None
    for i, step in enumerate(steps["steps"]):
        action = step["action"]

        if action == "place":
            if i != 0:
                raise ValueError("'place' step must be the first step")
            design = start_design(
                library,
                name=steps["meta"]["name"],
                first_piece_id=step["piece"],
                first_piece_type=step["type"],
                rotation=step.get("rotation"),
                position=step.get("position"),
                length_override=step.get("length"),
                width_override=step.get("width"),
            )
            if steps["meta"].get("description"):
                design["meta"]["description"] = steps["meta"]["description"]

        elif action == "attach":
            if design is None:
                raise ValueError("'attach' step before 'place'")
            add_piece(
                design, library,
                piece_id=step["piece"],
                piece_type=step["type"],
                rotation=step.get("rotation", [0, 0, 0]),
                attach_face=step["face"],
                to_piece=step["to"],
                to_face=step["to_face"],
                offset=tuple(step["offset"]) if "offset" in step else (0.0, 0.0),
                length_override=step.get("length"),
                width_override=step.get("width"),
                fastener=step.get("fastener"),
            )

        elif action == "connect":
            if design is None:
                raise ValueError("'connect' step before 'place'")
            add_connection(
                design,
                piece_id=step["piece"],
                face=step["face"],
                to_piece=step["to"],
                to_face=step["to_face"],
                fastener=step.get("fastener"),
            )

    if design is None:
        raise ValueError("No steps provided")

    # Pass through groups if present
    if "groups" in steps:
        design["groups"] = steps["groups"]

    return design


def start_design(
    library: "Library",
    name: str,
    first_piece_id: str,
    first_piece_type: str,
    rotation: list[float] | None = None,
    position: list[float] | None = None,
    length_override: float | None = None,
    width_override: float | None = None,
) -> dict:
    """Start a new design with the first piece placed at a given position.

    The first piece has no attachment — it establishes the origin.
    """
    piece: dict = {
        "id": first_piece_id,
        "type": first_piece_type,
        "position": list(position) if position else [0.0, 0.0, 0.0],
        "rotation": list(rotation) if rotation else [0.0, 0.0, 0.0],
        "connections": [],
    }
    if length_override is not None:
        piece["length_override"] = length_override
    if width_override is not None:
        piece["width_override"] = width_override

    return {
        "meta": {
            "name": name,
            "library": library.id,
            "version": 1,
        },
        "pieces": [piece],
    }


def add_piece(
    design: dict,
    library: "Library",
    piece_id: str,
    piece_type: str,
    rotation: list[float],
    attach_face: str,
    to_piece: str,
    to_face: str,
    offset: tuple[float, float] = (0.0, 0.0),
    length_override: float | None = None,
    width_override: float | None = None,
    fastener: str | None = None,
) -> dict:
    """Add a piece to the design by declaring how it attaches to an existing piece.

    The position is computed from the attachment:
    - The normal-axis coordinate is set so the two faces are coplanar.
    - The contact-plane coordinates are set from the existing face's
      min corner plus the given offset.

    Also adds the reverse connection on the existing piece.
    """
    # Build the new piece data (position will be filled in)
    new_piece: dict = {
        "id": piece_id,
        "type": piece_type,
        "position": [0.0, 0.0, 0.0],
        "rotation": list(rotation),
        "connections": [],
    }
    if length_override is not None:
        new_piece["length_override"] = length_override
    if width_override is not None:
        new_piece["width_override"] = width_override

    # Find the existing piece
    existing_piece = _find_piece(design, to_piece)

    # Compute effective dimensions
    new_dims = effective_dims(new_piece, library)
    existing_dims = effective_dims(existing_piece, library)
    existing_pos = existing_piece["position"]

    # Compute position from attachment
    position = _compute_position(
        new_dims, attach_face,
        existing_pos, existing_dims, to_face,
        offset,
    )
    new_piece["position"] = position

    # Add forward connection on the new piece
    conn: dict = {"face": attach_face, "to_piece": to_piece, "to_face": to_face}
    if fastener:
        conn["fastener"] = fastener
    new_piece["connections"].append(conn)

    # Add reverse connection on the existing piece
    reverse: dict = {"face": to_face, "to_piece": piece_id, "to_face": attach_face}
    if fastener:
        reverse["fastener"] = fastener
    existing_piece.setdefault("connections", []).append(reverse)

    design["pieces"].append(new_piece)
    return design


def add_connection(
    design: dict,
    piece_id: str,
    face: str,
    to_piece: str,
    to_face: str,
    fastener: str | None = None,
) -> dict:
    """Add a secondary connection between two existing pieces.

    Adds both forward and reverse connection declarations.
    Does not change positions — use this for additional structural
    connections after pieces are already placed.
    """
    piece_a = _find_piece(design, piece_id)
    piece_b = _find_piece(design, to_piece)

    conn_forward: dict = {"face": face, "to_piece": to_piece, "to_face": to_face}
    conn_reverse: dict = {"face": to_face, "to_piece": piece_id, "to_face": face}
    if fastener:
        conn_forward["fastener"] = fastener
        conn_reverse["fastener"] = fastener

    piece_a.setdefault("connections", []).append(conn_forward)
    piece_b.setdefault("connections", []).append(conn_reverse)

    return design


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _find_piece(design: dict, piece_id: str) -> dict:
    """Look up a placed piece by ID. Raises KeyError if not found."""
    for p in design.get("pieces", []):
        if p["id"] == piece_id:
            return p
    raise KeyError(f"Piece '{piece_id}' not found in design")


def _face_surface_coord(
    pos: list[float], dims: tuple[float, float, float], face: str
) -> float:
    """Return the world-space coordinate of a face's surface plane."""
    axis_idx, sign = _FACE_AXIS[face]
    if sign > 0:
        return pos[axis_idx] + dims[axis_idx]
    else:
        return pos[axis_idx]


def _compute_position(
    new_dims: tuple[float, float, float],
    new_face: str,
    existing_pos: list[float],
    existing_dims: tuple[float, float, float],
    existing_face: str,
    offset: tuple[float, float],
) -> list[float]:
    """Compute the world position for a new piece based on its attachment.

    Normal axis: position the new piece so its face is coplanar with the
    existing face.

    Contact plane: position the new piece at the existing face's min corner
    plus the given offset.
    """
    position = [0.0, 0.0, 0.0]

    # --- Normal axis (coplanarity) ---
    existing_surface = _face_surface_coord(existing_pos, existing_dims, existing_face)
    new_axis_idx, new_sign = _FACE_AXIS[new_face]

    if new_sign > 0:
        # New piece's + face must equal existing surface:
        # pos[axis] + dims[axis] = surface → pos[axis] = surface - dims[axis]
        position[new_axis_idx] = existing_surface - new_dims[new_axis_idx]
    else:
        # New piece's - face must equal existing surface:
        # pos[axis] = surface
        position[new_axis_idx] = existing_surface

    # --- Contact plane axes (alignment) ---
    # The two axes that aren't the existing face's normal axis
    existing_axis_idx = _FACE_AXIS[existing_face][0]
    other_axes = [i for i in range(3) if i != existing_axis_idx]
    u_axis, v_axis = other_axes

    position[u_axis] = existing_pos[u_axis] + offset[0]
    position[v_axis] = existing_pos[v_axis] + offset[1]

    return position
