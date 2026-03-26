"""Rich-formatted terminal display for the BuildScaffold CLI."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

if TYPE_CHECKING:
    from core.library import Library
    from core.validator import ValidationReport

console = Console()


def show_welcome(library: Library) -> None:
    """Show a banner with library name and piece count."""
    piece_count = len(library.list_pieces())
    content = f"Library: [bold]{library.name}[/]\nPieces available: [bold]{piece_count}[/]"
    console.print(Panel(content, title="[bold cyan]BuildScaffold[/]", expand=False))


def show_design_summary(design: dict, library: Library) -> None:
    """Rich Panel showing design name, library, total piece count, and piece breakdown."""
    meta = design.get("meta", {})
    design_name = meta.get("name", "(unnamed)")
    placed = design.get("pieces", [])
    total = len(placed)

    # Count piece types
    type_counts: dict[str, int] = {}
    colors_used: set[str] = set()
    for piece in placed:
        ptype = piece.get("type", "?")
        type_counts[ptype] = type_counts.get(ptype, 0) + 1
        color = piece.get("color")
        if color:
            colors_used.add(color)

    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    table.add_column("Piece Type")
    table.add_column("Count", justify="right")
    for ptype, count in sorted(type_counts.items()):
        table.add_row(ptype, str(count))

    colors_str = ", ".join(sorted(colors_used)) if colors_used else "(none)"
    summary = (
        f"Design: [bold]{design_name}[/]\n"
        f"Library: [bold]{library.name}[/]\n"
        f"Total pieces: [bold]{total}[/]\n"
        f"Colors used: {colors_str}\n"
    )

    console.print(Panel(summary, title="[bold]Design Summary[/]", expand=False))
    console.print(table)


def show_validation_report(report: ValidationReport) -> None:
    """Display a validation report with a Rich table of issues."""
    if report.is_valid:
        console.print("[bold green]✓ Design is valid[/]", end="")
        if report.warnings:
            console.print(f"  ([yellow]{len(report.warnings)} warning(s)[/])")
        else:
            console.print()
    else:
        console.print(
            f"[bold red]✗ Validation failed[/]  "
            f"[red]{len(report.errors)} error(s)[/], "
            f"[yellow]{len(report.warnings)} warning(s)[/]"
        )

    all_issues = report.errors + report.warnings
    if all_issues:
        table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
        table.add_column("Severity", min_width=8)
        table.add_column("Code")
        table.add_column("Pieces")
        table.add_column("Message")

        for issue in all_issues:
            if issue.severity == "error":
                severity_text = "[bold red]error[/]"
            else:
                severity_text = "[yellow]warning[/]"
            pieces_str = ", ".join(issue.piece_ids) if issue.piece_ids else ""
            table.add_row(severity_text, issue.code, pieces_str, issue.message)

        console.print(table)

    if report.build_steps is not None:
        steps = report.build_steps.get("steps", [])
        console.print(f"[cyan]Build steps generated:[/] {len(steps)} step(s)")


def show_piece_list(library: Library, category: str | None = None) -> None:
    """Table of pieces in the library, optionally filtered by category."""
    pieces = library.list_pieces(category)
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Category")
    table.add_column("Dimensions (WxHxL)")
    table.add_column("Colors")

    for piece in pieces:
        dims = piece.dimensions
        dim_str = f"{dims['width']}x{dims['height']}x{dims['length']}"
        colors_str = ", ".join(piece.colors) if piece.colors else "(any)"
        table.add_row(
            piece.id,
            piece.name,
            piece.category or "",
            dim_str,
            colors_str,
        )

    title = f"Pieces — {library.name}"
    if category:
        title += f" [{category}]"
    console.print(Panel(table, title=title, expand=False))


def show_render_result(paths: dict[str, Path]) -> None:
    """List each rendered angle name and its output path."""
    console.print(f"[bold green]Rendered {len(paths)} image(s):[/]")
    for angle, path in paths.items():
        console.print(f"  [cyan]{angle}[/]  →  {path}")


def show_export_result(path: Path) -> None:
    """Green confirmation message with file path and size."""
    size = path.stat().st_size if path.exists() else 0
    console.print(
        f"[bold green]Exported:[/] {path}  "
        f"([cyan]{size:,} bytes[/])"
    )


def show_error(message: str) -> None:
    """Print a bold red error message."""
    console.print(f"[bold red]Error:[/] {message}")


def show_info(message: str) -> None:
    """Print a cyan informational message."""
    console.print(f"[cyan]{message}[/]")
