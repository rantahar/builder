"""Loads piece library JSON files and provides piece lookup."""

from __future__ import annotations

import json
import logging
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import jsonschema
import numpy as np
import trimesh

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SCHEMA_PATH = Path(__file__).resolve().parent / "schema" / "library.schema.json"


@dataclass
class AttachmentType:
    name: str
    margin: float
    spacing: float
    compatible_with: list[str]
    grid_locked: bool = False


@dataclass
class Face:
    normal: str
    attachments: list[str]


@dataclass
class Piece:
    id: str
    name: str
    dimensions: dict
    category: str | None
    faces: dict[str, Face]
    variable_length: bool
    variable_width: bool
    ldraw_id: str | None
    colors: list[str]

    def grid_positions(self, face_normal: str, library: "Library") -> list[tuple[float, float]]:
        """Compute attachment grid positions for a face.

        Uses the first attachment type listed for the face to determine
        margin and spacing. Returns all (u, v) pairs on the face grid.
        """
        face = self.faces.get(face_normal)
        if face is None or not face.attachments:
            return []

        attachment_type = library.attachment_types[face.attachments[0]]
        margin = attachment_type.margin
        spacing = attachment_type.spacing

        w = self.dimensions["width"]
        h = self.dimensions["height"]
        length = self.dimensions["length"]

        axis = face_normal[1]  # 'x', 'y', or 'z'
        if axis == "y":
            size1, size2 = w, length
        elif axis == "x":
            size1, size2 = length, h
        else:  # z
            size1, size2 = w, h

        u_positions = _axis_positions(size1, margin, spacing)
        v_positions = _axis_positions(size2, margin, spacing)

        return [(u, v) for u in u_positions for v in v_positions]

    def get_geometry(self, library: "Library") -> trimesh.Trimesh | None:
        """Return a Trimesh mesh for this piece.

        Attempts to parse the LDraw .dat file. If the file is missing or
        contains mostly subfile references we can't resolve, falls back to
        a bounding-box mesh derived from the piece dimensions.
        """
        if self.id in _geometry_cache:
            return _geometry_cache[self.id]

        mesh = None
        if self.ldraw_id:
            parts_dir = _PROJECT_ROOT / "libraries" / library.id / "parts"
            dat_path = parts_dir / self.ldraw_id
            if dat_path.exists():
                mesh = _parse_ldraw_dat(dat_path)

        # Fall back to bounding box if no usable geometry from .dat
        if mesh is None or len(mesh.vertices) < 4:
            mesh = _bounding_box_mesh(self.dimensions)

        _geometry_cache[self.id] = mesh
        return mesh


_geometry_cache: dict[str, trimesh.Trimesh] = {}


def _bounding_box_mesh(dimensions: dict) -> trimesh.Trimesh:
    """Create a box mesh from piece dimensions, centered at origin."""
    w = dimensions["width"]
    h = dimensions["height"]
    l = dimensions["length"]
    return trimesh.creation.box(extents=[w, h, l])


def _parse_ldraw_dat(path: Path) -> trimesh.Trimesh | None:
    """Parse triangles and quads from an LDraw .dat file.

    LDraw convention: y is vertical (negative = up). We negate y to convert
    to our +y = up convention. Only parses type 3 (triangle) and type 4 (quad)
    lines — subfile references (type 1) are skipped.
    """
    vertices = []
    faces = []

    for line in path.read_text().splitlines():
        parts = line.strip().split()
        if not parts:
            continue

        if parts[0] == "3" and len(parts) >= 11:
            # Triangle: 3 color x1 y1 z1 x2 y2 z2 x3 y3 z3
            idx = len(vertices)
            for i in range(3):
                x = float(parts[2 + i * 3])
                y = -float(parts[3 + i * 3])  # negate y
                z = float(parts[4 + i * 3])
                vertices.append([x, y, z])
            faces.append([idx, idx + 1, idx + 2])

        elif parts[0] == "4" and len(parts) >= 14:
            # Quad: 4 color x1 y1 z1 x2 y2 z2 x3 y3 z3 x4 y4 z4
            idx = len(vertices)
            for i in range(4):
                x = float(parts[2 + i * 3])
                y = -float(parts[3 + i * 3])  # negate y
                z = float(parts[4 + i * 3])
                vertices.append([x, y, z])
            faces.append([idx, idx + 1, idx + 2])
            faces.append([idx, idx + 2, idx + 3])

    if not vertices or not faces:
        return None

    return trimesh.Trimesh(
        vertices=np.array(vertices, dtype=np.float64),
        faces=np.array(faces, dtype=np.int64),
    )


def _axis_positions(face_size: float, margin: float, spacing: float) -> list[float]:
    positions = []
    p = margin
    while p <= face_size - margin:
        positions.append(p)
        p += spacing
    return positions


class Library:
    """A loaded piece library."""

    def __init__(self, data: dict) -> None:
        self._id: str = data["id"]
        self._name: str = data["name"]
        self._unit: str = data["unit"]

        self._attachment_types: dict[str, AttachmentType] = {
            name: AttachmentType(
                name=name,
                margin=atype["margin"],
                spacing=atype["spacing"],
                compatible_with=atype["compatible_with"],
                grid_locked=atype.get("grid_locked", False),
            )
            for name, atype in data["attachment_types"].items()
        }

        self._pieces: dict[str, Piece] = {}
        for p in data["pieces"]:
            faces = {
                normal: Face(normal=normal, attachments=face_data["attachments"])
                for normal, face_data in p["faces"].items()
            }
            piece = Piece(
                id=p["id"],
                name=p["name"],
                dimensions=p["dimensions"],
                category=p.get("category"),
                faces=faces,
                variable_length=p.get("variable_length", False),
                variable_width=p.get("variable_width", False),
                ldraw_id=p.get("ldraw_id"),
                colors=p.get("colors", []),
            )
            self._pieces[piece.id] = piece

    @classmethod
    def load(cls, library_id: str) -> "Library":
        """Load a library by ID from the libraries/ directory in the project root."""
        path = _PROJECT_ROOT / "libraries" / library_id / "library.json"
        return cls.load_file(path)

    @classmethod
    def load_file(cls, path: Path) -> "Library":
        """Load a library from an arbitrary path, validated against the JSON schema."""
        schema = json.loads(_SCHEMA_PATH.read_text())
        data = json.loads(Path(path).read_text())
        jsonschema.validate(data, schema)
        return cls(data)

    def get_piece(self, piece_id: str) -> Piece:
        """Look up a piece by ID. Raises KeyError if not found."""
        if piece_id not in self._pieces:
            raise KeyError(f"Piece '{piece_id}' not found in library '{self._id}'")
        return self._pieces[piece_id]

    def list_pieces(self, category: str | None = None) -> list[Piece]:
        """List all pieces, optionally filtered by category."""
        pieces = list(self._pieces.values())
        if category is not None:
            pieces = [p for p in pieces if p.category == category]
        return pieces

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @property
    def unit(self) -> str:
        return self._unit

    @property
    def attachment_types(self) -> dict[str, AttachmentType]:
        return self._attachment_types
