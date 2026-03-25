"""Lego stability checker — BFS reachability from baseplates."""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from core.stability.base import StabilityChecker

if TYPE_CHECKING:
    from core.library import Library


class LegoStabilityChecker(StabilityChecker):
    """Check stability via graph reachability from baseplate pieces."""

    def check(self, design: dict, library: Library) -> list[str]:
        placed = design.get("pieces", [])
        if not placed:
            return []

        adjacency = _build_adjacency(placed)
        ground = _find_ground_pieces(placed, library)

        if not ground:
            # No baseplates — all pieces are unstable
            return [p["id"] for p in placed]

        # BFS from ground pieces
        visited = set()
        queue = deque(ground)
        visited.update(ground)

        while queue:
            current = queue.popleft()
            for neighbor in adjacency.get(current, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)

        # Unreachable pieces are unstable
        all_ids = {p["id"] for p in placed}
        return sorted(all_ids - visited)


def _build_adjacency(placed: list[dict]) -> dict[str, set[str]]:
    """Build undirected adjacency map from declared connections."""
    adj: dict[str, set[str]] = {}
    for piece in placed:
        pid = piece["id"]
        if pid not in adj:
            adj[pid] = set()
        for conn in piece.get("connections", []):
            target = conn["to_piece"]
            adj.setdefault(pid, set()).add(target)
            adj.setdefault(target, set()).add(pid)
    return adj


def _find_ground_pieces(placed: list[dict], library: Library) -> set[str]:
    """Return IDs of pieces whose type has category == 'baseplate'."""
    ground = set()
    for piece in placed:
        try:
            piece_def = library.get_piece(piece["type"])
            if piece_def.category == "baseplate":
                ground.add(piece["id"])
        except KeyError:
            pass
    return ground
