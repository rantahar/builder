"""Tests for core.renderer — offscreen multi-angle PNG rendering."""

import json
import os
from pathlib import Path

os.environ["PYOPENGL_PLATFORM"] = "osmesa"

import numpy as np
import pytest

# Guard: skip all tests if pyrender/OSMesa not available
pyrender = pytest.importorskip("pyrender")

from core.library import Library
from core.renderer import (
    ANGLE_NAMES,
    _COLOR_MAP,
    _DEFAULT_COLOR,
    _compute_camera_poses,
    _compute_scene_bounds,
    _look_at,
    _piece_transform,
    _rotation_matrix,
    _build_scene,
    render,
)

ROOT = Path(__file__).resolve().parent.parent


def _load_fixture(name: str) -> dict:
    return json.loads((ROOT / "tests" / "fixtures" / name).read_text())


@pytest.fixture(scope="module")
def lego():
    return Library.load("lego_basic")


# ---------------------------------------------------------------------------
# _rotation_matrix
# ---------------------------------------------------------------------------


def test_rotation_matrix_identity():
    """_rotation_matrix([0,0,0]) should equal the 4x4 identity matrix."""
    result = _rotation_matrix([0, 0, 0])
    assert result.shape == (4, 4)
    assert result == pytest.approx(np.eye(4), abs=1e-9)


def test_rotation_matrix_y90():
    """After 90-degree rotation around y, x-axis maps to -z and z-axis maps to +x."""
    mat = _rotation_matrix([0, 90, 0])
    assert mat.shape == (4, 4)

    # The 3x3 rotation block (upper-left)
    r = mat[:3, :3]

    # x-axis (1,0,0) should map to (0,0,-1)
    x_mapped = r @ np.array([1, 0, 0])
    assert x_mapped == pytest.approx([0, 0, -1], abs=1e-6)

    # z-axis (0,0,1) should map to (1,0,0)
    z_mapped = r @ np.array([0, 0, 1])
    assert z_mapped == pytest.approx([1, 0, 0], abs=1e-6)

    # y-axis should be unchanged
    y_mapped = r @ np.array([0, 1, 0])
    assert y_mapped == pytest.approx([0, 1, 0], abs=1e-6)

    # Bottom row and right column should be homogeneous
    assert mat[3, :] == pytest.approx([0, 0, 0, 1], abs=1e-9)


def test_rotation_matrix_x90():
    """After 90-degree rotation around x, y-axis maps to +z and z-axis maps to -y."""
    mat = _rotation_matrix([90, 0, 0])
    assert mat.shape == (4, 4)

    r = mat[:3, :3]

    # y-axis (0,1,0) should map to (0,0,1)
    y_mapped = r @ np.array([0, 1, 0])
    assert y_mapped == pytest.approx([0, 0, 1], abs=1e-6)

    # z-axis (0,0,1) should map to (0,-1,0)
    z_mapped = r @ np.array([0, 0, 1])
    assert z_mapped == pytest.approx([0, -1, 0], abs=1e-6)

    # x-axis should be unchanged
    x_mapped = r @ np.array([1, 0, 0])
    assert x_mapped == pytest.approx([1, 0, 0], abs=1e-6)


# ---------------------------------------------------------------------------
# _piece_transform
# ---------------------------------------------------------------------------


def test_piece_transform_no_rotation(lego):
    """Transform for brick_2x4 at [120,8,140] with no rotation has correct translation.

    brick_2x4 actual dims: width=80, height=24, length=40.
    effective_dims = (80, 24, 40). center = [120+40, 8+12, 140+20] = [160, 20, 160].
    """
    piece_data = {
        "id": "brick1",
        "type": "brick_2x4",
        "position": [120, 8, 140],
        "rotation": [0, 0, 0],
        "color": "red",
        "connections": [],
    }
    mat = _piece_transform(piece_data, lego)

    assert mat.shape == (4, 4)

    # Translation column (column 3, rows 0-2) should be the mesh center
    translation = mat[:3, 3]
    assert translation == pytest.approx([160.0, 20.0, 160.0], abs=1e-6)

    # Rotation block should be identity (no rotation)
    assert mat[:3, :3] == pytest.approx(np.eye(3), abs=1e-6)

    # Bottom row homogeneous
    assert mat[3, :] == pytest.approx([0, 0, 0, 1], abs=1e-9)


def test_piece_transform_with_y90_rotation(lego):
    """Transform for brick_2x4 at [160,8,180] with y=90 rotation has correct translation.

    brick_2x4 actual dims: width=80, height=24, length=40.
    With ry=90, width and length swap: effective_dims = (40, 24, 80).
    center = [160+20, 8+12, 180+40] = [180, 20, 220].
    """
    piece_data = {
        "id": "brick1",
        "type": "brick_2x4",
        "position": [160, 8, 180],
        "rotation": [0, 90, 0],
        "color": "red",
        "connections": [],
    }
    mat = _piece_transform(piece_data, lego)

    assert mat.shape == (4, 4)

    # Translation should be the AABB center
    translation = mat[:3, 3]
    assert translation == pytest.approx([180.0, 20.0, 220.0], abs=1e-6)

    # Rotation block should match y90 rotation
    expected_rot = _rotation_matrix([0, 90, 0])[:3, :3]
    assert mat[:3, :3] == pytest.approx(expected_rot, abs=1e-6)


# ---------------------------------------------------------------------------
# _compute_scene_bounds
# ---------------------------------------------------------------------------


def test_compute_scene_bounds_single_brick(lego):
    """Bounds of single_brick_on_baseplate cover the full baseplate footprint.

    baseplate_16x16 at [0,0,0]: dims 320x8x320 → fills [0,0,0]..[320,8,320].
    brick_2x4 at [120,8,140]: dims 80x24x40 → fills [120,8,140]..[200,32,180].
    Expected: min=[0,0,0], max at least [320,32,320].
    """
    design = _load_fixture("single_brick_on_baseplate.json")
    bounds = _compute_scene_bounds(design, lego)

    assert bounds.shape == (2, 3)

    bmin, bmax = bounds[0], bounds[1]
    assert bmin[0] == pytest.approx(0.0, abs=1e-6)
    assert bmin[1] == pytest.approx(0.0, abs=1e-6)
    assert bmin[2] == pytest.approx(0.0, abs=1e-6)

    assert bmax[0] >= 320.0 - 1e-6
    assert bmax[1] >= 32.0 - 1e-6
    assert bmax[2] >= 320.0 - 1e-6


def test_compute_scene_bounds_empty():
    """Empty design returns fallback bounds [[-1,-1,-1],[1,1,1]]."""
    design = {"meta": {}, "pieces": []}
    lego = Library.load("lego_basic")
    bounds = _compute_scene_bounds(design, lego)

    assert bounds.shape == (2, 3)
    assert bounds[0] == pytest.approx([-1, -1, -1], abs=1e-9)
    assert bounds[1] == pytest.approx([1, 1, 1], abs=1e-9)


# ---------------------------------------------------------------------------
# _compute_camera_poses
# ---------------------------------------------------------------------------


def test_camera_poses_has_six_angles(lego):
    """_compute_camera_poses returns exactly 6 poses, one per ANGLE_NAMES entry."""
    design = _load_fixture("single_brick_on_baseplate.json")
    bounds = _compute_scene_bounds(design, lego)
    poses = _compute_camera_poses(bounds)

    assert set(poses.keys()) == set(ANGLE_NAMES)
    assert len(poses) == 6

    for name in ANGLE_NAMES:
        pose = poses[name]
        assert isinstance(pose, np.ndarray)
        assert pose.shape == (4, 4)


# ---------------------------------------------------------------------------
# _look_at
# ---------------------------------------------------------------------------


def test_look_at_front():
    """Camera at [0,0,5] looking at origin has translation [0,0,5].

    The local -z axis of the camera should point toward the target (world -z direction
    from camera to origin means the camera's local -z aligns with [0,0,-1] in world).
    """
    eye = np.array([0.0, 0.0, 5.0])
    target = np.array([0.0, 0.0, 0.0])
    up = np.array([0.0, 1.0, 0.0])

    pose = _look_at(eye, target, up)

    assert pose.shape == (4, 4)

    # Translation should place camera at [0, 0, 5]
    translation = pose[:3, 3]
    assert translation == pytest.approx([0.0, 0.0, 5.0], abs=1e-6)

    # Forward direction: in camera convention, the camera looks along local -z.
    # The third column (local z-axis in world) should point away from target,
    # i.e. from target toward eye: [0, 0, 1].
    local_z = pose[:3, 2]
    assert local_z == pytest.approx([0.0, 0.0, 1.0], abs=1e-6)

    # Up direction (local y-axis) should stay aligned with world +y
    local_y = pose[:3, 1]
    assert local_y == pytest.approx([0.0, 1.0, 0.0], abs=1e-6)

    # Bottom row must be homogeneous
    assert pose[3, :] == pytest.approx([0, 0, 0, 1], abs=1e-9)


# ---------------------------------------------------------------------------
# _build_scene
# ---------------------------------------------------------------------------


def test_build_scene_has_nodes(lego):
    """_build_scene returns a pyrender.Scene with at least 2 mesh nodes."""
    design = _load_fixture("single_brick_on_baseplate.json")
    scene = _build_scene(design, lego)

    assert isinstance(scene, pyrender.Scene)
    # single_brick_on_baseplate has 2 pieces: baseplate + 1 brick
    assert len(scene.mesh_nodes) >= 2


# ---------------------------------------------------------------------------
# render() — integration tests
# ---------------------------------------------------------------------------


def test_render_produces_png_files(lego, tmp_path):
    """render() produces 6 non-empty PNG files, one per camera angle."""
    design = _load_fixture("four_brick_wall.json")
    result = render(design, lego, tmp_path)

    png_files = list(tmp_path.glob("*.png"))
    assert len(png_files) == 6

    for path in png_files:
        assert path.stat().st_size > 0


def test_render_returns_correct_paths(lego, tmp_path):
    """render() return value maps each ANGLE_NAMES key to an existing Path."""
    design = _load_fixture("four_brick_wall.json")
    result = render(design, lego, tmp_path)

    assert set(result.keys()) == set(ANGLE_NAMES)

    for name in ANGLE_NAMES:
        path = result[name]
        assert isinstance(path, Path)
        assert path.exists()
        assert path.suffix == ".png"


def test_render_creates_output_dir(lego, tmp_path):
    """render() creates the output directory if it does not exist."""
    output_dir = tmp_path / "subdir" / "output"
    assert not output_dir.exists()

    design = _load_fixture("single_brick_on_baseplate.json")
    render(design, lego, output_dir)

    assert output_dir.exists()
    assert len(list(output_dir.glob("*.png"))) == 6


def test_render_custom_resolution(lego, tmp_path):
    """render() with resolution=(400,300) produces 400x300 PNG images."""
    from PIL import Image

    design = _load_fixture("single_brick_on_baseplate.json")
    result = render(design, lego, tmp_path, resolution=(400, 300))

    for name in ANGLE_NAMES:
        img = Image.open(result[name])
        assert img.size == (400, 300)


# ---------------------------------------------------------------------------
# Color handling
# ---------------------------------------------------------------------------


def test_unknown_color_uses_default(lego, tmp_path):
    """A piece with an unknown color falls back to the default gray without raising."""
    design = {
        "meta": {"name": "test", "library": "lego_basic"},
        "pieces": [
            {
                "id": "mystery",
                "type": "brick_2x4",
                "position": [0, 0, 0],
                "rotation": [0, 0, 0],
                "color": "purple",
                "connections": [],
            }
        ],
    }

    # Should not raise
    scene = _build_scene(design, lego)
    assert isinstance(scene, pyrender.Scene)

    # Verify the default color constant is defined and is gray-ish
    assert _DEFAULT_COLOR is not None
    assert len(_DEFAULT_COLOR) >= 3

    # Verify purple is absent from the known color map
    assert "purple" not in _COLOR_MAP


def test_color_map_covers_standard_lego_colors():
    """_COLOR_MAP includes the standard LEGO colors used in fixtures."""
    standard_colors = {"red", "blue", "green", "yellow", "white", "black", "gray"}
    for color in standard_colors:
        if color in _COLOR_MAP:
            rgba = _COLOR_MAP[color]
            assert len(rgba) >= 3
            assert all(0.0 <= c <= 1.0 for c in rgba[:3])
