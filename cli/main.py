"""Interactive REPL for loading, validating, rendering, and exporting designs."""

from __future__ import annotations

import argparse
import cmd
import json
from pathlib import Path

from rich.table import Table

from cli import display
from core.builder import build
from core.library import Library
from core.validator import validate


class DesignShell(cmd.Cmd):
    """Interactive BuildScaffold shell."""

    prompt = "buildscaffold> "

    def __init__(self, project_dir: Path, library_id: str) -> None:
        super().__init__()
        self.project_dir: Path = project_dir
        self.library: Library = Library.load(library_id)
        self.design: dict | None = None
        self.design_path: Path | None = None
        self.report = None
        display.show_welcome(self.library)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def do_load(self, arg: str) -> None:
        """Load a design JSON file: load <path>"""
        arg = arg.strip()
        if not arg:
            display.show_error("Usage: load <path-to-design.json>")
            return

        path = Path(arg)
        if not path.is_absolute():
            path = self.project_dir / path

        try:
            text = path.read_text()
        except FileNotFoundError:
            display.show_error(f"File not found: {path}")
            return

        try:
            design = json.loads(text)
        except json.JSONDecodeError as exc:
            display.show_error(f"Invalid JSON: {exc}")
            return

        # Compile build-steps format if needed
        if "steps" in design:
            try:
                design = build(design, self.library)
            except Exception as exc:
                display.show_error(f"Failed to compile build steps: {exc}")
                return

        self.design = design
        self.design_path = path
        self.report = None

        try:
            display.show_design_summary(self.design, self.library)
        except Exception as exc:
            display.show_error(f"Could not render design summary: {exc}")

    def do_validate(self, arg: str) -> None:
        """Validate the loaded design: validate"""
        if self.design is None:
            display.show_error("No design loaded. Use 'load <file>' first.")
            return

        try:
            self.report = validate(self.design, self.library)
            display.show_validation_report(self.report)
        except Exception as exc:
            display.show_error(f"Validation failed unexpectedly: {exc}")

    def do_render(self, arg: str) -> None:
        """Render the loaded design to PNG images: render"""
        if self.design is None:
            display.show_error("No design loaded. Use 'load <file>' first.")
            return

        output_dir = self.project_dir / "renders"
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            from core.renderer import render  # noqa: PLC0415 — lazy import avoids OSMesa at startup
        except ImportError as exc:
            display.show_error(
                f"Renderer unavailable (pyrender/OSMesa not installed): {exc}"
            )
            return

        try:
            paths = render(self.design, self.library, output_dir)
            display.show_render_result(paths)
        except Exception as exc:
            display.show_error(f"Render failed: {exc}")

    def do_export(self, arg: str) -> None:
        """Export the loaded design to an LDraw file: export"""
        if self.design is None:
            display.show_error("No design loaded. Use 'load <file>' first.")
            return

        try:
            from core.exporter import export_ldr  # noqa: PLC0415
        except ImportError as exc:
            display.show_error(f"Exporter unavailable: {exc}")
            return

        meta = self.design.get("meta", {})
        design_name = meta.get("name", "design")
        exports_dir = self.project_dir / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        out_path = exports_dir / f"{design_name}.ldr"

        try:
            export_ldr(self.design, self.library, out_path)
            display.show_export_result(out_path)
        except Exception as exc:
            display.show_error(f"Export failed: {exc}")

    def do_reload(self, arg: str) -> None:
        """Reload the currently loaded design file: reload"""
        if self.design_path is None:
            display.show_error("No design loaded. Use 'load <file>' first.")
            return

        try:
            text = self.design_path.read_text()
        except FileNotFoundError:
            display.show_error(f"File not found: {self.design_path}")
            return

        try:
            design = json.loads(text)
        except json.JSONDecodeError as exc:
            display.show_error(f"Invalid JSON: {exc}")
            return

        if "steps" in design:
            try:
                design = build(design, self.library)
            except Exception as exc:
                display.show_error(f"Failed to compile build steps: {exc}")
                return

        self.design = design
        self.report = None

        try:
            display.show_design_summary(self.design, self.library)
        except Exception as exc:
            display.show_error(f"Could not render design summary: {exc}")

    def do_pieces(self, arg: str) -> None:
        """List pieces in the library, optionally filtered: pieces [category]"""
        category = arg.strip() or None
        try:
            display.show_piece_list(self.library, category=category)
        except Exception as exc:
            display.show_error(f"Could not list pieces: {exc}")

    def do_quit(self, arg: str) -> bool:
        """Exit the shell: quit"""
        return True

    def do_exit(self, arg: str) -> bool:
        """Exit the shell: exit"""
        return True

    def do_help(self, arg: str) -> None:
        """Show available commands."""
        table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
        table.add_column("Command")
        table.add_column("Description")

        commands = [
            ("load <file>", "Load a design JSON (build-steps or flat format)"),
            ("validate", "Validate the loaded design against the library"),
            ("render", "Render the design to PNG images in renders/"),
            ("export", "Export the design to an LDraw .ldr file in exports/"),
            ("reload", "Reload the currently loaded design file from disk"),
            ("pieces [category]", "List library pieces, optionally filtered by category"),
            ("help", "Show this help table"),
            ("quit / exit", "Exit BuildScaffold"),
        ]
        for name, description in commands:
            table.add_row(f"[bold cyan]{name}[/]", description)

        display.console.print(table)


def main() -> None:
    """Parse CLI arguments and start the interactive shell."""
    parser = argparse.ArgumentParser(description="BuildScaffold CLI")
    parser.add_argument("--project", type=Path, default=Path("."))
    parser.add_argument("--library", default="lego_basic")
    args = parser.parse_args()

    shell = DesignShell(args.project, args.library)
    try:
        shell.cmdloop()
    except KeyboardInterrupt:
        print()
