"""Abstract base class for stability checkers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.library import Library


class StabilityChecker(ABC):
    """Interface for checking structural stability of a design."""

    @abstractmethod
    def check(self, design: dict, library: Library) -> list[str]:
        """Return piece IDs that are not stably supported.

        A piece is stable if it has a support path to the ground.
        What constitutes 'ground' depends on the library (e.g. baseplates for Lego).
        """
        ...
