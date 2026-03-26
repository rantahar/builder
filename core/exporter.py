"""Exports a design JSON to LDraw .ldr format for viewing in LDraw-compatible editors."""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np

from core.library import Library
from core.validator import effective_dims

_LDRAW_COLORS = {
    "red": 4, "blue": 1, "green": 2, "yellow": 14,
    "white": 15, "black": 0, "gray": 7, "grey": 7,
    "orange": 25, "brown": 6, "tan": 19,
}
_DEFAULT_LDRAW_COLOR = 16  # "main color"


def _rotation_matrix_3x3(rotation: list[float]) -> np.ndarray:
    """Build a 3x3 rotation matrix from [rx, ry, rz] degrees.

    Composed as Rz @ Ry @ Rx (same convention as renderer.py).
    """
    rx, ry, rz = np.radians(rotation)

    cx, sx = np.cos(rx), np.sin(rx)
    cy, sy = np.cos(ry), np.sin(ry)
    cz, sz = np.cos(rz), np.sin(rz)

    Rx = np.array([
        [1,   0,   0],
        [0,  cx, -sx],
        [0,  sx,  cx],
    ], dtype=float)

    Ry = np.array([
        [ cy,  0,  sy],
        [  0,  1,   0],
        [-sy,  0,  cy],
    ], dtype=float)

    Rz = np.array([
        [cz, -sz,  0],
        [sz,  cz,  0],
        [ 0,   0,  1],
    ], dtype=float)

    return Rz @ Ry @ Rx


def _ldraw_rotation(rotation: list[float]) -> np.ndarray:
    """Build the LDraw rotation matrix with y-axis flip applied.

    LDraw uses -y = up, so we negate row 1 and col 1 of the 3x3 matrix.
    """
    R = _rotation_matrix_3x3(rotation)
    # Flip y: negate row index 1 and column index 1
    R[1, :] *= -1
    R[:, 1] *= -1
    return R


def _ldraw_color(color: str | None) -> int:
    """Map a color name to an LDraw color code."""
    if color is None:
        return _DEFAULT_LDRAW_COLOR
    return _LDRAW_COLORS.get(color.lower(), _DEFAULT_LDRAW_COLOR)


def export_ldr(design: dict, library: Library, output_path: Path) -> Path:
    """Convert a BuildScaffold design JSON to an LDraw .ldr file.

    Pieces without an ``ldraw_id`` in the library definition are skipped with
    a :func:`warnings.warn` warning. Returns the resolved output path.
    """
    output_path = Path(output_path)
    design_name = design.get("meta", {}).get("name", "Untitled")

    lines: list[str] = []

    # Header
    lines.append(f"0 FILE {output_path.name}")
    lines.append(f"0 {design_name}")
    lines.append("0 Author: BuildScaffold")

    for piece_data in design.get("pieces", []):
        piece_type = piece_data["type"]
        piece_def = library.get_piece(piece_type)

        if not piece_def.ldraw_id:
            warnings.warn(
                f"Piece '{piece_data.get('id', piece_type)}' (type '{piece_type}') "
                f"has no ldraw_id — skipping.",
                stacklevel=2,
            )
            continue

        # Compute center position in our coordinate system (+y = up)
        dims = effective_dims(piece_data, library)
        position = piece_data.get("position", [0.0, 0.0, 0.0])
        cx = position[0] + dims[0] / 2
        cy = position[1] + dims[1] / 2
        cz = position[2] + dims[2] / 2

        # Convert to LDraw coordinates (negate y)
        lx, ly, lz = cx, -cy, cz

        # Build rotation matrix with LDraw y-flip
        rotation = piece_data.get("rotation", [0, 0, 0])
        R = _ldraw_rotation(rotation)

        # Row-major elements: a b c / d e f / g h i
        a, b, c = R[0]
        d, e, f = R[1]
        g, h, i = R[2]

        color = _ldraw_color(piece_data.get("color"))

        lines.append(
            f"1 {color} "
            f"{lx:g} {ly:g} {lz:g} "
            f"{a:g} {b:g} {c:g} "
            f"{d:g} {e:g} {f:g} "
            f"{g:g} {h:g} {i:g} "
            f"{piece_def.ldraw_id}"
        )

    lines.append("0 NOFILE")

    output_path.write_text("\n".join(lines) + "\n")
    return output_path
