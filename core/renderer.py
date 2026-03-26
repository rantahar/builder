"""Produces multi-angle PNG images from a design JSON using pyrender and OSMesa."""

from __future__ import annotations

import os

os.environ["PYOPENGL_PLATFORM"] = "osmesa"

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pyrender
import trimesh
from PIL import Image

from core.validator import effective_dims

if TYPE_CHECKING:
    from core.library import Library

ANGLE_NAMES = [
    "iso_front_left", "iso_front_right", "iso_back_left", "iso_back_right",
    "iso_under_front_left", "iso_under_front_right",
    "iso_under_back_left", "iso_under_back_right",
    "top",
]
DEFAULT_RESOLUTION = (800, 600)

_COLOR_MAP: dict[str, tuple[float, float, float]] = {
    "red": (0.85, 0.15, 0.15),
    "blue": (0.15, 0.35, 0.85),
    "green": (0.15, 0.70, 0.25),
    "yellow": (0.95, 0.85, 0.10),
    "white": (0.95, 0.95, 0.95),
    "black": (0.10, 0.10, 0.10),
    "gray": (0.55, 0.55, 0.55),
    "grey": (0.55, 0.55, 0.55),
    "orange": (0.95, 0.55, 0.05),
    "brown": (0.55, 0.35, 0.15),
    "tan": (0.85, 0.75, 0.55),
}
_DEFAULT_COLOR = (0.65, 0.65, 0.65)


def _rotation_matrix(rotation: list[float]) -> np.ndarray:
    """Build a 4×4 homogeneous rotation matrix from [rx, ry, rz] degrees.

    Composed as Rz @ Ry @ Rx (i.e., rx applied first, then ry, then rz).
    """
    rx, ry, rz = np.radians(rotation)

    cx, sx = np.cos(rx), np.sin(rx)
    cy, sy = np.cos(ry), np.sin(ry)
    cz, sz = np.cos(rz), np.sin(rz)

    Rx = np.array([
        [1,   0,   0,  0],
        [0,  cx, -sx,  0],
        [0,  sx,  cx,  0],
        [0,   0,   0,  1],
    ], dtype=float)

    Ry = np.array([
        [ cy,  0,  sy,  0],
        [  0,  1,   0,  0],
        [-sy,  0,  cy,  0],
        [  0,  0,   0,  1],
    ], dtype=float)

    Rz = np.array([
        [cz, -sz,  0,  0],
        [sz,  cz,  0,  0],
        [ 0,   0,  1,  0],
        [ 0,   0,  0,  1],
    ], dtype=float)

    return Rz @ Ry @ Rx


def _piece_transform(piece_data: dict, library: "Library") -> np.ndarray:
    """Compute the 4×4 world-space transform for a piece.

    Geometry is centered at origin, so we rotate around origin first, then
    translate to the world center of the piece's AABB.
    """
    rotation = piece_data.get("rotation", [0, 0, 0])
    R = _rotation_matrix(rotation)

    ew, eh, el = effective_dims(piece_data, library)
    position = piece_data.get("position", [0, 0, 0])

    # Center of the AABB = min corner + half dimensions
    cx = position[0] + ew / 2
    cy = position[1] + eh / 2
    cz = position[2] + el / 2

    T = np.eye(4)
    T[0, 3] = cx
    T[1, 3] = cy
    T[2, 3] = cz

    return T @ R


def _compute_scene_bounds(design: dict, library: "Library") -> np.ndarray:
    """Return [[xmin, ymin, zmin], [xmax, ymax, zmax]] over all pieces in the design."""
    pieces = design.get("pieces", [])
    if not pieces:
        return np.array([[-1.0, -1.0, -1.0], [1.0, 1.0, 1.0]])

    mins = []
    maxs = []
    for piece_data in pieces:
        pos = piece_data.get("position", [0.0, 0.0, 0.0])
        ew, eh, el = effective_dims(piece_data, library)
        mins.append([pos[0], pos[1], pos[2]])
        maxs.append([pos[0] + ew, pos[1] + eh, pos[2] + el])

    return np.array([
        np.min(mins, axis=0),
        np.max(maxs, axis=0),
    ])


def _look_at(eye: np.ndarray, target: np.ndarray, up: np.ndarray) -> np.ndarray:
    """Build a camera-to-world pose matrix (pyrender convention: camera looks along -z)."""
    f = target - eye
    f = f / np.linalg.norm(f)
    r = np.cross(f, up)
    r = r / np.linalg.norm(r)
    u = np.cross(r, f)

    pose = np.eye(4)
    pose[:3, 0] = r
    pose[:3, 1] = u
    pose[:3, 2] = -f  # camera looks along -z
    pose[:3, 3] = eye
    return pose


def _compute_camera_poses(bounds: np.ndarray) -> dict[str, np.ndarray]:
    """Return a dict of 4×4 camera-to-world pose matrices for each named angle."""
    center = (bounds[0] + bounds[1]) / 2
    diagonal = np.linalg.norm(bounds[1] - bounds[0])
    dist = diagonal * 2.5

    up_y = np.array([0.0, 1.0, 0.0])
    d = dist / np.sqrt(3)

    poses = {
        "top": _look_at(
            center + np.array([0.0, dist, 0.0]),
            center,
            np.array([0.0, 0.0, -1.0]),
        ),
    }

    # 4 isometric corners from above, 4 from below
    for label, sx, sz in [
        ("front_left", -1, 1), ("front_right", 1, 1),
        ("back_left", -1, -1), ("back_right", 1, -1),
    ]:
        poses[f"iso_{label}"] = _look_at(
            center + np.array([sx, 1, sz]) * d, center, up_y,
        )
        poses[f"iso_under_{label}"] = _look_at(
            center + np.array([sx, -1, sz]) * d, center, up_y,
        )

    return poses


def _build_scene(design: dict, library: "Library") -> pyrender.Scene:
    """Construct a pyrender scene from the design, with meshes and lighting."""
    scene = pyrender.Scene(ambient_light=[0.3, 0.3, 0.3])

    for piece_data in design.get("pieces", []):
        piece_def = library.get_piece(piece_data["type"])
        mesh = piece_def.get_geometry(library)

        color_name = piece_data.get("color", "")
        r, g, b = _COLOR_MAP.get(color_name, _DEFAULT_COLOR)

        material = pyrender.MetallicRoughnessMaterial(
            baseColorFactor=[r, g, b, 1.0],
            metallicFactor=0.0,
            roughnessFactor=0.7,
        )

        pr_mesh = pyrender.Mesh.from_trimesh(mesh, material=material)
        transform = _piece_transform(piece_data, library)
        scene.add(pr_mesh, pose=transform)

    # Key light: from above-front-right, shining toward origin
    key_light = pyrender.DirectionalLight(color=[1.0, 1.0, 1.0], intensity=3.0)
    key_pose = _look_at(
        np.array([1.0, 1.0, 1.0]),
        np.zeros(3),
        np.array([0.0, 1.0, 0.0]),
    )
    scene.add(key_light, pose=key_pose)

    # Fill light: from above-back-left
    fill_light = pyrender.DirectionalLight(color=[1.0, 1.0, 1.0], intensity=1.5)
    fill_pose = _look_at(
        np.array([-1.0, 0.5, -1.0]),
        np.zeros(3),
        np.array([0.0, 1.0, 0.0]),
    )
    scene.add(fill_light, pose=fill_pose)

    return scene


def render(
    design: dict,
    library: "Library",
    output_dir: Path | str,
    resolution: tuple[int, int] = DEFAULT_RESOLUTION,
) -> dict[str, Path]:
    """Render multi-angle PNG images from a design JSON.

    Produces one PNG per angle in ANGLE_NAMES, written to output_dir.
    Returns a dict mapping angle name to the saved Path.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    scene = _build_scene(design, library)
    bounds = _compute_scene_bounds(design, library)
    camera_poses = _compute_camera_poses(bounds)

    camera = pyrender.PerspectiveCamera(
        yfov=np.radians(60.0),
        aspectRatio=resolution[0] / resolution[1],
    )

    r = pyrender.OffscreenRenderer(resolution[0], resolution[1])
    result = {}

    try:
        for angle_name in ANGLE_NAMES:
            cam_node = scene.add(camera, pose=camera_poses[angle_name])
            color, _ = r.render(scene)
            scene.remove_node(cam_node)

            path = output_dir / f"{angle_name}.png"
            Image.fromarray(color).save(path)
            result[angle_name] = path
    finally:
        r.delete()

    return result
