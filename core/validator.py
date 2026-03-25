"""Validates a design JSON against a piece library, reporting all errors."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.library import Library


@dataclass
class ValidationError:
    """A single validation issue."""

    code: str
    severity: str  # "error" or "warning"
    piece_ids: list[str]
    message: str


@dataclass
class ValidationReport:
    """Result of validating a design."""

    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)
    build_steps: dict | None = None

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def add(self, error: ValidationError) -> None:
        if error.severity == "error":
            self.errors.append(error)
        else:
            self.warnings.append(error)


def validate(design: dict, library: "Library") -> ValidationReport:
    """Run all validation checks on a design. Returns a complete report."""
    report = ValidationReport()
    placed = design.get("pieces", [])

    # Build lookup helpers
    pieces_by_id = {p["id"]: p for p in placed}
    all_ids = set(pieces_by_id.keys())

    # Stage 0: structural integrity
    stage0_errors = []
    stage0_errors.extend(_check_piece_references(placed, library))
    stage0_errors.extend(_check_target_piece_exists(placed, all_ids))
    for e in stage0_errors:
        report.add(e)

    # Stage 1: connection semantics
    for e in _check_connection_faces_exist(placed, library):
        report.add(e)
    for e in _check_connection_compatibility(placed, library):
        report.add(e)
    for e in _check_bidirectionality(placed, pieces_by_id):
        report.add(e)
    for e in _check_declaration_order(placed):
        report.add(e)

    # Stages 2-4 only if Stage 0 passed (need valid piece types for spatial checks)
    if not stage0_errors:
        # Stage 2: spatial checks
        for e in _check_aabb_collisions(placed, library, pieces_by_id):
            report.add(e)
        for e in _check_face_coplanarity(placed, library, pieces_by_id):
            report.add(e)
        for e in _check_face_overlap(placed, library, pieces_by_id):
            report.add(e)

        # Stage 3: stability and connectivity
        for e in _run_stability_check(design, library):
            report.add(e)
        for e in _check_connectivity(placed):
            report.add(e)

        # Stage 4: wood-specific
        for e in _check_screw_collisions(placed, library, pieces_by_id):
            report.add(e)

        # Generate build steps from the design
        report.build_steps = _generate_build_steps(design, library, pieces_by_id)

    return report


# ---------------------------------------------------------------------------
# Stage 0
# ---------------------------------------------------------------------------


def _check_piece_references(placed: list[dict], library: "Library") -> list[ValidationError]:
    """Verify every piece's type exists in the library."""
    errors = []
    for piece in placed:
        piece_type = piece.get("type", "")
        try:
            library.get_piece(piece_type)
        except KeyError:
            errors.append(
                ValidationError(
                    code="UNKNOWN_PIECE_TYPE",
                    severity="error",
                    piece_ids=[piece["id"]],
                    message=(
                        f"Piece '{piece['id']}' references unknown type '{piece_type}'"
                        " in the library."
                    ),
                )
            )
    return errors


def _check_target_piece_exists(placed: list[dict], all_ids: set[str]) -> list[ValidationError]:
    """Verify every connection's to_piece references an existing piece ID."""
    errors = []
    for piece in placed:
        for conn in piece.get("connections", []):
            target = conn.get("to_piece", "")
            if target not in all_ids:
                errors.append(
                    ValidationError(
                        code="UNKNOWN_PIECE_ID",
                        severity="error",
                        piece_ids=[piece["id"]],
                        message=(
                            f"Piece '{piece['id']}' has a connection to unknown"
                            f" piece ID '{target}'."
                        ),
                    )
                )
    return errors


# ---------------------------------------------------------------------------
# Stage 1
# ---------------------------------------------------------------------------


def _check_connection_faces_exist(placed: list[dict], library: "Library") -> list[ValidationError]:
    """Verify that faces referenced in connections exist on the respective piece types."""
    errors = []
    for piece in placed:
        try:
            piece_def = library.get_piece(piece["type"])
        except KeyError:
            continue  # already caught by stage 0

        for conn in piece.get("connections", []):
            face = conn.get("face", "")
            if face not in piece_def.faces:
                errors.append(
                    ValidationError(
                        code="FACE_NOT_ON_PIECE",
                        severity="error",
                        piece_ids=[piece["id"]],
                        message=(
                            f"Piece '{piece['id']}' (type '{piece['type']}') references"
                            f" face '{face}', which is not defined for that piece type."
                        ),
                    )
                )
    return errors


def _check_connection_compatibility(
    placed: list[dict], library: "Library"
) -> list[ValidationError]:
    """Verify that each connection's attachment types are mutually compatible."""
    errors = []
    pieces_by_id = {p["id"]: p for p in placed}

    for piece in placed:
        try:
            src_def = library.get_piece(piece["type"])
        except KeyError:
            continue

        for conn in piece.get("connections", []):
            face = conn.get("face", "")
            to_piece_id = conn.get("to_piece", "")
            to_face = conn.get("to_face", "")

            # Skip if source face doesn't exist (caught by stage 1 face check)
            if face not in src_def.faces:
                continue

            # Skip if target piece doesn't exist (caught by stage 0)
            target_piece_data = pieces_by_id.get(to_piece_id)
            if target_piece_data is None:
                continue

            try:
                tgt_def = library.get_piece(target_piece_data["type"])
            except KeyError:
                continue

            # Skip if target face doesn't exist (caught by stage 1 face check)
            if to_face not in tgt_def.faces:
                continue

            src_attachments = src_def.faces[face].attachments
            tgt_attachments = tgt_def.faces[to_face].attachments

            compatible = False
            for src_att_name in src_attachments:
                src_att = library.attachment_types.get(src_att_name)
                if src_att is None:
                    continue
                for tgt_att_name in tgt_attachments:
                    if tgt_att_name in src_att.compatible_with:
                        compatible = True
                        break
                if compatible:
                    break

            if not compatible:
                errors.append(
                    ValidationError(
                        code="INCOMPATIBLE_ATTACHMENT_TYPES",
                        severity="error",
                        piece_ids=[piece["id"], to_piece_id],
                        message=(
                            f"Connection from '{piece['id']}' face '{face}' to"
                            f" '{to_piece_id}' face '{to_face}' has incompatible"
                            f" attachment types ({src_attachments} vs {tgt_attachments})."
                        ),
                    )
                )
    return errors


def _check_bidirectionality(
    placed: list[dict], pieces_by_id: dict[str, dict]
) -> list[ValidationError]:
    """Verify every A→B connection has a matching B→A reverse connection."""
    errors = []
    reported: set[frozenset] = set()

    for piece in placed:
        pid = piece["id"]
        for conn in piece.get("connections", []):
            face_a = conn.get("face", "")
            to_piece_id = conn.get("to_piece", "")
            to_face = conn.get("to_face", "")

            pair_key = frozenset({pid, to_piece_id})
            if pair_key in reported:
                continue

            target = pieces_by_id.get(to_piece_id)
            if target is None:
                continue  # caught by stage 0

            # Look for the reverse connection in target
            reverse_found = any(
                c.get("face") == to_face
                and c.get("to_piece") == pid
                and c.get("to_face") == face_a
                for c in target.get("connections", [])
            )

            if not reverse_found:
                reported.add(pair_key)
                errors.append(
                    ValidationError(
                        code="MISSING_REVERSE_CONNECTION",
                        severity="error",
                        piece_ids=[pid, to_piece_id],
                        message=(
                            f"Connection '{pid}':{face_a} → '{to_piece_id}':{to_face}"
                            f" has no reverse connection '{to_piece_id}':{to_face}"
                            f" → '{pid}':{face_a}."
                        ),
                    )
                )
    return errors


def _check_declaration_order(placed: list[dict]) -> list[ValidationError]:
    """Verify each piece after the first connects to at least one previously declared piece."""
    errors = []
    declared: set[str] = set()

    for i, piece in enumerate(placed):
        pid = piece["id"]
        if i == 0:
            declared.add(pid)
            continue

        has_prior = any(
            conn.get("to_piece") in declared
            for conn in piece.get("connections", [])
        )
        if not has_prior:
            errors.append(
                ValidationError(
                    code="NO_CONNECTION_TO_PRIOR",
                    severity="error",
                    piece_ids=[pid],
                    message=(
                        f"Piece '{pid}' (index {i}) has no connection to any"
                        " previously declared piece."
                    ),
                )
            )
        declared.add(pid)

    return errors


# ---------------------------------------------------------------------------
# Stage 2
# ---------------------------------------------------------------------------


def effective_dims(piece_data: dict, library: "Library") -> tuple[float, float, float]:
    """Get effective (width, height, length) after applying rotation."""
    piece_def = library.get_piece(piece_data["type"])

    if piece_def.variable_width:
        w = piece_data.get("width_override") or piece_def.dimensions["width"]
    else:
        w = piece_def.dimensions["width"]
    h = piece_def.dimensions["height"]
    if piece_def.variable_length:
        l = piece_data.get("length_override") or piece_def.dimensions["length"]
    else:
        l = piece_def.dimensions["length"]

    rotation = piece_data.get("rotation", [0, 0, 0])
    rx, ry, rz = rotation

    # For 90° increments on y-axis, swap width and length
    ry_mod = round(ry) % 360
    if ry_mod in (90, 270):
        w, l = l, w

    # For 90° increments on x-axis, swap height and length
    rx_mod = round(rx) % 360
    if rx_mod in (90, 270):
        h, l = l, h

    # For 90° increments on z-axis, swap width and height
    rz_mod = round(rz) % 360
    if rz_mod in (90, 270):
        w, h = h, w

    return (w, h, l)


def _check_aabb_collisions(
    placed: list[dict], library: "Library", pieces_by_id: dict[str, dict]
) -> list[ValidationError]:
    """Detect pairwise axis-aligned bounding box collisions between non-connected pieces."""
    errors = []

    # Build set of connected pairs so we can skip them
    connected: set[frozenset] = set()
    for piece in placed:
        pid = piece["id"]
        for conn in piece.get("connections", []):
            connected.add(frozenset({pid, conn["to_piece"]}))

    # Pre-compute AABBs
    aabbs: list[tuple[list[float], list[float]]] = []
    for piece in placed:
        pos = piece.get("position", [0.0, 0.0, 0.0])
        dims = effective_dims(piece, library)
        mn = [pos[0], pos[1], pos[2]]
        mx = [pos[0] + dims[0], pos[1] + dims[1], pos[2] + dims[2]]
        aabbs.append((mn, mx))

    n = len(placed)
    for i in range(n):
        for j in range(i + 1, n):
            id_i = placed[i]["id"]
            id_j = placed[j]["id"]

            if frozenset({id_i, id_j}) in connected:
                continue

            mn_a, mx_a = aabbs[i]
            mn_b, mx_b = aabbs[j]

            overlap = all(
                max(mn_a[k], mn_b[k]) < min(mx_a[k], mx_b[k]) for k in range(3)
            )
            if overlap:
                errors.append(
                    ValidationError(
                        code="PIECE_COLLISION",
                        severity="error",
                        piece_ids=[id_i, id_j],
                        message=(
                            f"Pieces '{id_i}' and '{id_j}' have overlapping"
                            " bounding boxes."
                        ),
                    )
                )
    return errors


def _check_face_coplanarity(
    placed: list[dict], library: "Library", pieces_by_id: dict[str, dict]
) -> list[ValidationError]:
    """Verify connected faces are at the same world-space coordinate."""
    errors = []
    reported: set[tuple] = set()

    for piece in placed:
        pid = piece["id"]
        try:
            dims_a = effective_dims(piece, library)
        except KeyError:
            continue
        pos_a = piece.get("position", [0.0, 0.0, 0.0])

        for conn in piece.get("connections", []):
            face = conn.get("face", "")
            to_pid = conn.get("to_piece", "")
            to_face = conn.get("to_face", "")

            # Dedup: only check each directed connection once
            pair_key = (pid, face, to_pid, to_face)
            reverse_key = (to_pid, to_face, pid, face)
            if pair_key in reported or reverse_key in reported:
                continue
            reported.add(pair_key)

            if face not in _FACE_AXIS or to_face not in _FACE_AXIS:
                continue

            target = pieces_by_id.get(to_pid)
            if target is None:
                continue

            try:
                dims_b = effective_dims(target, library)
            except KeyError:
                continue
            pos_b = target.get("position", [0.0, 0.0, 0.0])

            coord_a = _face_surface_coord(pos_a, dims_a, face)
            coord_b = _face_surface_coord(pos_b, dims_b, to_face)

            if abs(coord_a - coord_b) > _COPLANAR_TOL:
                errors.append(
                    ValidationError(
                        code="FACE_NOT_COPLANAR",
                        severity="error",
                        piece_ids=[pid, to_pid],
                        message=(
                            f"Connection '{pid}':{face} (at {coord_a:.1f}) to"
                            f" '{to_pid}':{to_face} (at {coord_b:.1f}): faces"
                            f" are not coplanar (diff {abs(coord_a - coord_b):.1f})."
                        ),
                    )
                )

    return errors


def _check_face_overlap(
    placed: list[dict], library: "Library", pieces_by_id: dict[str, dict]
) -> list[ValidationError]:
    """Verify connected pieces share surface area on the contact plane."""
    errors = []
    reported: set[tuple] = set()

    for piece in placed:
        pid = piece["id"]
        try:
            dims_a = effective_dims(piece, library)
        except KeyError:
            continue
        pos_a = piece.get("position", [0.0, 0.0, 0.0])

        for conn in piece.get("connections", []):
            face = conn.get("face", "")
            to_pid = conn.get("to_piece", "")
            to_face = conn.get("to_face", "")

            pair_key = (pid, face, to_pid, to_face)
            reverse_key = (to_pid, to_face, pid, face)
            if pair_key in reported or reverse_key in reported:
                continue
            reported.add(pair_key)

            if face not in _FACE_AXIS or to_face not in _FACE_AXIS:
                continue
            # Only check overlap if faces are on the same axis
            if _FACE_AXIS[face][0] != _FACE_AXIS[to_face][0]:
                continue

            target = pieces_by_id.get(to_pid)
            if target is None:
                continue

            try:
                dims_b = effective_dims(target, library)
            except KeyError:
                continue
            pos_b = target.get("position", [0.0, 0.0, 0.0])

            rect_a = _face_rect(pos_a, dims_a, face)
            rect_b = _face_rect(pos_b, dims_b, to_face)

            if not _rects_overlap(rect_a, rect_b):
                errors.append(
                    ValidationError(
                        code="FACE_NO_OVERLAP",
                        severity="error",
                        piece_ids=[pid, to_pid],
                        message=(
                            f"Connection '{pid}':{face} to '{to_pid}':{to_face}:"
                            f" pieces have no overlapping area on the contact plane."
                        ),
                    )
                )

    return errors


# ---------------------------------------------------------------------------
# Stage 3
# ---------------------------------------------------------------------------


def _run_stability_check(design: dict, library: "Library") -> list[ValidationError]:
    """Use LegoStabilityChecker if the library has any grid_locked attachment types."""
    # Check if any attachment type is grid_locked
    has_grid_locked = any(
        att.grid_locked for att in library.attachment_types.values()
    )

    if not has_grid_locked:
        return []

    # Import here to avoid module-level import issues
    from core.stability.lego import LegoStabilityChecker  # noqa: PLC0415

    checker = LegoStabilityChecker()
    unstable_ids = checker.check(design, library)

    errors = []
    for pid in unstable_ids:
        errors.append(
            ValidationError(
                code="UNSTABLE_PIECE",
                severity="warning",
                piece_ids=[pid],
                message=f"Piece '{pid}' is not stably supported (no path to ground).",
            )
        )
    return errors


def _check_connectivity(placed: list[dict]) -> list[ValidationError]:
    """Warn about pieces that form disconnected components from the main assembly."""
    if not placed:
        return []

    # Build undirected adjacency via union-find
    parent: dict[str, str] = {p["id"]: p["id"] for p in placed}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for piece in placed:
        pid = piece["id"]
        for conn in piece.get("connections", []):
            target = conn.get("to_piece", "")
            if target in parent:
                union(pid, target)

    # Find all components
    components: dict[str, list[str]] = {}
    for piece in placed:
        pid = piece["id"]
        root = find(pid)
        components.setdefault(root, []).append(pid)

    if len(components) <= 1:
        return []

    # Find the largest component
    largest_root = max(components, key=lambda r: len(components[r]))

    errors = []
    for root, members in components.items():
        if root == largest_root:
            continue
        for pid in members:
            errors.append(
                ValidationError(
                    code="DISCONNECTED_PIECE",
                    severity="warning",
                    piece_ids=[pid],
                    message=(
                        f"Piece '{pid}' is not connected to the main assembly"
                        " (disconnected component)."
                    ),
                )
            )
    return errors


# ---------------------------------------------------------------------------
# Build steps generation
# ---------------------------------------------------------------------------


def _generate_build_steps(
    design: dict, library: "Library", pieces_by_id: dict[str, dict]
) -> dict:
    """Derive build steps JSON from a design, as a byproduct of validation.

    Walks the pieces array in declaration order. The first piece becomes a
    'place' step. Each subsequent piece picks its first connection to a prior
    piece as the primary 'attach' step, with offset reverse-engineered from
    positions. Additional connections to prior pieces become 'connect' steps.
    """
    placed = design.get("pieces", [])
    if not placed:
        return {"meta": design.get("meta", {}), "steps": []}

    steps: list[dict] = []
    declared: set[str] = set()

    for i, piece in enumerate(placed):
        pid = piece["id"]

        if i == 0:
            step: dict = {
                "action": "place",
                "piece": pid,
                "type": piece["type"],
            }
            rotation = piece.get("rotation", [0, 0, 0])
            if rotation != [0, 0, 0]:
                step["rotation"] = rotation
            position = piece.get("position", [0, 0, 0])
            if position != [0, 0, 0] and position != [0.0, 0.0, 0.0]:
                step["position"] = position
            if "length_override" in piece:
                step["length"] = piece["length_override"]
            if "width_override" in piece:
                step["width"] = piece["width_override"]
            steps.append(step)
            declared.add(pid)
            continue

        # Split connections into primary (first to a prior piece) and secondary
        primary_conn = None
        secondary_conns: list[dict] = []

        for conn in piece.get("connections", []):
            target = conn.get("to_piece", "")
            if target in declared:
                if primary_conn is None:
                    primary_conn = conn
                else:
                    secondary_conns.append(conn)

        # Emit the attach step
        if primary_conn is not None:
            target_piece = pieces_by_id[primary_conn["to_piece"]]
            offset = _compute_offset(piece, primary_conn, target_piece, library)

            step = {
                "action": "attach",
                "piece": pid,
                "type": piece["type"],
                "face": primary_conn["face"],
                "to": primary_conn["to_piece"],
                "to_face": primary_conn["to_face"],
            }
            rotation = piece.get("rotation", [0, 0, 0])
            if rotation != [0, 0, 0]:
                step["rotation"] = rotation
            if offset != [0.0, 0.0]:
                step["offset"] = offset
            if "length_override" in piece:
                step["length"] = piece["length_override"]
            if "width_override" in piece:
                step["width"] = piece["width_override"]
            if primary_conn.get("fastener"):
                step["fastener"] = primary_conn["fastener"]
            steps.append(step)
        else:
            # No connection to a prior piece — emit as place (orphan)
            step = {
                "action": "place",
                "piece": pid,
                "type": piece["type"],
            }
            rotation = piece.get("rotation", [0, 0, 0])
            if rotation != [0, 0, 0]:
                step["rotation"] = rotation
            position = piece.get("position", [0, 0, 0])
            if position != [0, 0, 0] and position != [0.0, 0.0, 0.0]:
                step["position"] = position
            if "length_override" in piece:
                step["length"] = piece["length_override"]
            if "width_override" in piece:
                step["width"] = piece["width_override"]
            steps.append(step)

        # Emit connect steps for secondary connections to prior pieces
        for conn in secondary_conns:
            cstep: dict = {
                "action": "connect",
                "piece": pid,
                "face": conn["face"],
                "to": conn["to_piece"],
                "to_face": conn["to_face"],
            }
            if conn.get("fastener"):
                cstep["fastener"] = conn["fastener"]
            steps.append(cstep)

        declared.add(pid)

    result: dict = {"meta": design.get("meta", {}), "steps": steps}
    if "groups" in design:
        result["groups"] = design["groups"]
    return result


def _compute_offset(
    new_piece: dict,
    conn: dict,
    existing_piece: dict,
    library: "Library",
) -> list[float]:
    """Reverse-engineer the offset from known positions."""
    existing_face = conn["to_face"]
    existing_axis_idx = _FACE_AXIS[existing_face][0]
    other_axes = [i for i in range(3) if i != existing_axis_idx]
    u_axis, v_axis = other_axes

    new_pos = new_piece.get("position", [0, 0, 0])
    existing_pos = existing_piece.get("position", [0, 0, 0])

    return [
        round(new_pos[u_axis] - existing_pos[u_axis], 4),
        round(new_pos[v_axis] - existing_pos[v_axis], 4),
    ]


# ---------------------------------------------------------------------------
# Stage 4
# ---------------------------------------------------------------------------

# Maps face normal to (axis_index, direction_sign)
_FACE_AXIS: dict[str, tuple[int, int]] = {
    "+x": (0, +1),
    "-x": (0, -1),
    "+y": (1, +1),
    "-y": (1, -1),
    "+z": (2, +1),
    "-z": (2, -1),
}

# Opposite face pairs
_OPPOSITE_FACE: dict[str, str] = {
    "+x": "-x",
    "-x": "+x",
    "+y": "-y",
    "-y": "+y",
    "+z": "-z",
    "-z": "+z",
}

_COPLANAR_TOL = 0.1  # tolerance for floating-point coordinate comparisons


def _face_surface_coord(
    pos: list[float], dims: tuple[float, float, float], face: str
) -> float:
    """Return the world-space coordinate of a face's surface plane."""
    axis_idx, sign = _FACE_AXIS[face]
    if sign > 0:
        return pos[axis_idx] + dims[axis_idx]
    else:
        return pos[axis_idx]


def _face_rect(
    pos: list[float], dims: tuple[float, float, float], face: str
) -> tuple[float, float, float, float]:
    """Return (u_min, u_max, v_min, v_max) on the plane orthogonal to the face axis."""
    axis_idx = _FACE_AXIS[face][0]
    other_axes = [i for i in range(3) if i != axis_idx]
    u_ax, v_ax = other_axes
    return (pos[u_ax], pos[u_ax] + dims[u_ax], pos[v_ax], pos[v_ax] + dims[v_ax])


def _rects_overlap(
    r1: tuple[float, float, float, float],
    r2: tuple[float, float, float, float],
) -> bool:
    """Check if two 2D rectangles have strictly positive overlap area."""
    u_overlap = min(r1[1], r2[1]) - max(r1[0], r2[0])
    v_overlap = min(r1[3], r2[3]) - max(r1[2], r2[2])
    return u_overlap > _COPLANAR_TOL and v_overlap > _COPLANAR_TOL


def _parse_screw_length(fastener: str) -> float | None:
    """Extract the length (in mm or library units) from a fastener spec like '4x40'."""
    match = re.search(r"\d+x(\d+)", fastener)
    if match:
        return float(match.group(1))
    return None


def _check_screw_collisions(
    placed: list[dict], library: "Library", pieces_by_id: dict[str, dict]
) -> list[ValidationError]:
    """Detect screws from opposite faces colliding inside a post/receiver piece."""
    errors = []

    for piece in placed:
        try:
            piece_def = library.get_piece(piece["type"])
        except KeyError:
            continue

        # Check if this piece is a "post" — has screw_receiver attachment on any face
        is_receiver = any(
            "screw_receiver" in face.attachments
            for face in piece_def.faces.values()
        )
        if not is_receiver:
            continue

        pid = piece["id"]
        receiver_dims = effective_dims(piece, library)

        # For each axis, gather connections entering this piece from + and - faces
        for axis_idx in range(3):
            plus_face = ("+x", "+y", "+z")[axis_idx]
            minus_face = ("-x", "-y", "-z")[axis_idx]
            piece_dim = receiver_dims[axis_idx]

            # Find all pieces connecting INTO this receiver on the + face and - face
            plus_entries: list[dict] = []
            minus_entries: list[dict] = []

            for other in placed:
                if other["id"] == pid:
                    continue
                for conn in other.get("connections", []):
                    if conn.get("to_piece") != pid:
                        continue
                    to_face = conn.get("to_face", "")
                    if to_face == plus_face:
                        plus_entries.append({"piece": other, "conn": conn})
                    elif to_face == minus_face:
                        minus_entries.append({"piece": other, "conn": conn})

            # Check each pair of opposing entries for screw collision
            for p_entry in plus_entries:
                for m_entry in minus_entries:
                    p_conn = p_entry["conn"]
                    m_conn = m_entry["conn"]

                    p_fastener = p_conn.get("fastener", "")
                    m_fastener = m_conn.get("fastener", "")

                    p_screw_len = _parse_screw_length(p_fastener) if p_fastener else None
                    m_screw_len = _parse_screw_length(m_fastener) if m_fastener else None

                    if p_screw_len is None or m_screw_len is None:
                        continue

                    p_piece_data = p_entry["piece"]
                    m_piece_data = m_entry["piece"]

                    p_dims = effective_dims(p_piece_data, library)
                    m_dims = effective_dims(m_piece_data, library)

                    p_thickness = p_dims[axis_idx]
                    m_thickness = m_dims[axis_idx]

                    p_penetration = p_screw_len - p_thickness
                    m_penetration = m_screw_len - m_thickness

                    if p_penetration + m_penetration >= piece_dim:
                        errors.append(
                            ValidationError(
                                code="SCREW_COLLISION",
                                severity="error",
                                piece_ids=[p_piece_data["id"], pid, m_piece_data["id"]],
                                message=(
                                    f"Screws from '{p_piece_data['id']}' and"
                                    f" '{m_piece_data['id']}' collide inside receiver"
                                    f" piece '{pid}' along axis {axis_idx}"
                                    f" (combined penetration"
                                    f" {p_penetration + m_penetration:.1f}"
                                    f" >= piece dimension {piece_dim:.1f})."
                                ),
                            )
                        )
    return errors
