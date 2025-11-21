"""Command-line interface for DocuAgent."""

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.tree import Tree

from docuagent.analyzer import APIExtractor
from docuagent.html import HTMLGenerator
from docuagent.toc import SelectionManager, TOCGenerator

console = Console()


@click.group()
@click.version_option(version="0.1.0", prog_name="DocuAgent")
def main():
    """DocuAgent - AI-powered documentation generator for git repositories.

    Generate intelligent API documentation with AI assistance.
    """
    pass


@main.command()
@click.argument("repo_path", type=click.Path(exists=True), default=".")
@click.option(
    "--output", "-o",
    type=click.Path(),
    default="docs",
    help="Output directory for documentation",
)
@click.option(
    "--title", "-t",
    default="API Documentation",
    help="Documentation title",
)
@click.option(
    "--include-private",
    is_flag=True,
    help="Include private members (starting with _)",
)
@click.option(
    "--include-source",
    is_flag=True,
    default=True,
    help="Include source code in documentation",
)
@click.option(
    "--no-ai",
    is_flag=True,
    help="Skip AI description generation",
)
@click.option(
    "--use-selections",
    is_flag=True,
    help="Use existing selections from .docuagent/selections.yaml",
)
@click.option(
    "--editable",
    is_flag=True,
    help="Generate documentation in editable mode with checkboxes to select components",
)
def generate(
    repo_path: str,
    output: str,
    title: str,
    include_private: bool,
    include_source: bool,
    no_ai: bool,
    use_selections: bool,
    editable: bool,
):
    """Generate documentation for a repository.

    This command analyzes the repository, extracts public API components,
    generates AI descriptions (unless --no-ai), and creates static HTML documentation.
    """
    repo_path = Path(repo_path).resolve()

    console.print(Panel(f"[bold blue]DocuAgent[/bold blue] - Generating documentation for [cyan]{repo_path}[/cyan]"))

    # Step 1: Extract API components
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Analyzing repository...", total=None)

        extractor = APIExtractor(
            repo_path=repo_path,
            include_private=include_private,
        )
        modules = extractor.extract()

        progress.update(task, description="Analysis complete!")

    if not modules:
        console.print("[yellow]No Python modules found in the repository.[/yellow]")
        return

    # Show statistics
    stats = extractor.get_statistics(modules)
    stats_table = Table(title="Extracted Components")
    stats_table.add_column("Type", style="cyan")
    stats_table.add_column("Count", style="green")

    stats_table.add_row("Modules", str(stats["total_modules"]))
    stats_table.add_row("Classes", str(stats["total_classes"]))
    stats_table.add_row("Functions", str(stats["total_functions"]))
    stats_table.add_row("Methods", str(stats["total_methods"]))
    stats_table.add_row("Properties", str(stats["total_properties"]))

    console.print(stats_table)

    # Step 2: Generate TOC
    toc_generator = TOCGenerator()
    toc_entries = toc_generator.generate(modules)

    # Step 3: Load or initialize selections
    selection_manager = SelectionManager(config_dir=repo_path / ".docuagent")

    if use_selections:
        selections = selection_manager.load_selections()
        if not selections:
            console.print("[yellow]No existing selections found. Initializing defaults...[/yellow]")
            selections = selection_manager.initialize_from_toc(toc_entries)
    else:
        selections = selection_manager.initialize_from_toc(toc_entries)

    # Step 4: Generate AI descriptions (if enabled)
    descriptions = {}
    if not no_ai:
        try:
            from docuagent.agent import DocumentationAgent

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Generating AI descriptions...", total=len(modules))

                agent = DocumentationAgent()

                for module in modules:
                    progress.update(task, description=f"Documenting {module.name}...")
                    module_descriptions = agent.generate_module_documentation(
                        module,
                        include_source=include_source,
                    )
                    descriptions.update(module_descriptions)
                    progress.advance(task)

                # Cache descriptions
                selection_manager.save_descriptions(descriptions)

        except ValueError as e:
            console.print(f"[yellow]AI generation skipped: {e}[/yellow]")
            console.print("[dim]Set ANTHROPIC_API_KEY environment variable to enable AI descriptions.[/dim]")
    else:
        # Try to load cached descriptions
        descriptions = selection_manager.load_descriptions()

    # Step 5: Generate HTML
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Generating HTML documentation...", total=None)

        html_generator = HTMLGenerator(
            output_dir=output,
            title=title,
            include_source=include_source,
            editable=editable,
        )

        output_path = html_generator.generate(
            modules=modules,
            toc_entries=toc_entries,
            descriptions=descriptions,
            selections=selections,
        )

        progress.update(task, description="HTML generation complete!")

    console.print(f"\n[green]Documentation generated successfully![/green]")
    console.print(f"Output: [cyan]{output_path.resolve()}[/cyan]")
    console.print(f"\nOpen [cyan]{output_path.resolve() / 'index.html'}[/cyan] in a browser to view.")


@main.command()
@click.argument("repo_path", type=click.Path(exists=True), default=".")
@click.option(
    "--include-private",
    is_flag=True,
    help="Include private members",
)
def analyze(repo_path: str, include_private: bool):
    """Analyze a repository and show its structure.

    This command extracts and displays the public API structure without
    generating documentation.
    """
    repo_path = Path(repo_path).resolve()

    console.print(Panel(f"Analyzing [cyan]{repo_path}[/cyan]"))

    extractor = APIExtractor(
        repo_path=repo_path,
        include_private=include_private,
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Extracting API components...", total=None)
        modules = extractor.extract()
        progress.update(task, description="Extraction complete!")

    if not modules:
        console.print("[yellow]No Python modules found.[/yellow]")
        return

    # Display as tree
    tree = Tree("[bold]Repository Structure[/bold]")

    for module in modules:
        module_branch = tree.add(f"[blue]{module.file_path}[/blue]")

        if module.classes:
            classes_branch = module_branch.add("[cyan]Classes[/cyan]")
            for cls in module.classes:
                cls_branch = classes_branch.add(f"[green]{cls.name}[/green]")
                for method in cls.methods:
                    cls_branch.add(f"[dim]{method.name}()[/dim]")

        if module.functions:
            funcs_branch = module_branch.add("[cyan]Functions[/cyan]")
            for func in module.functions:
                funcs_branch.add(f"[yellow]{func.name}()[/yellow]")

    console.print(tree)

    # Show statistics
    stats = extractor.get_statistics(modules)
    console.print(f"\n[bold]Statistics:[/bold]")
    console.print(f"  Modules: {stats['total_modules']}")
    console.print(f"  Classes: {stats['total_classes']}")
    console.print(f"  Functions: {stats['total_functions']}")
    console.print(f"  Methods: {stats['total_methods']}")


@main.command()
@click.argument("repo_path", type=click.Path(exists=True), default=".")
@click.option(
    "--format", "-f",
    type=click.Choice(["tree", "json", "flat"]),
    default="tree",
    help="Output format",
)
def toc(repo_path: str, format: str):
    """Display the table of contents for a repository.

    Shows the documentation structure that would be generated.
    """
    repo_path = Path(repo_path).resolve()

    extractor = APIExtractor(repo_path=repo_path)
    modules = extractor.extract()

    if not modules:
        console.print("[yellow]No Python modules found.[/yellow]")
        return

    toc_generator = TOCGenerator()
    toc_entries = toc_generator.generate(modules)

    if format == "json":
        console.print(json.dumps(toc_generator.to_dict(toc_entries), indent=2))
    elif format == "flat":
        flat_entries = toc_generator.flatten(toc_entries)
        for entry in flat_entries:
            indent = "  " * entry.level
            console.print(f"{indent}[{entry.component_type.value}] {entry.title}")
    else:  # tree
        tree = Tree("[bold]Table of Contents[/bold]")

        def add_entry_to_tree(entry, parent):
            type_colors = {
                "module": "blue",
                "class": "green",
                "function": "yellow",
                "method": "cyan",
                "property": "magenta",
            }
            color = type_colors.get(entry.component_type.value, "white")
            branch = parent.add(f"[{color}]{entry.title}[/{color}]")
            for child in entry.children:
                add_entry_to_tree(child, branch)

        for entry in toc_entries:
            add_entry_to_tree(entry, tree)

        console.print(tree)


@main.command()
@click.argument("repo_path", type=click.Path(exists=True), default=".")
def select(repo_path: str):
    """Interactively select which components to include in documentation.

    Opens an interactive selector to choose what to include/exclude.
    """
    repo_path = Path(repo_path).resolve()

    extractor = APIExtractor(repo_path=repo_path)
    modules = extractor.extract()

    if not modules:
        console.print("[yellow]No Python modules found.[/yellow]")
        return

    toc_generator = TOCGenerator()
    toc_entries = toc_generator.generate(modules)

    selection_manager = SelectionManager(config_dir=repo_path / ".docuagent")
    selections = selection_manager.initialize_from_toc(toc_entries)

    flat_entries = toc_generator.flatten(toc_entries)

    console.print(Panel("[bold]Interactive Selection Mode[/bold]\n"
                       "Toggle components to include/exclude from documentation.\n"
                       "Commands: [cyan]toggle <id>[/cyan], [cyan]include <id>[/cyan], "
                       "[cyan]exclude <id>[/cyan], [cyan]list[/cyan], [cyan]save[/cyan], [cyan]quit[/cyan]"))

    # Show initial list
    _show_selection_list(flat_entries, selections)

    while True:
        try:
            cmd = console.input("\n[bold]> [/bold]").strip().lower()

            if cmd == "quit" or cmd == "q":
                break
            elif cmd == "save" or cmd == "s":
                selection_manager.save_selections(selections)
                console.print("[green]Selections saved![/green]")
            elif cmd == "list" or cmd == "l":
                _show_selection_list(flat_entries, selections)
            elif cmd.startswith("toggle ") or cmd.startswith("t "):
                entry_id = cmd.split(" ", 1)[1]
                _toggle_selection(entry_id, flat_entries, selections)
            elif cmd.startswith("include ") or cmd.startswith("i "):
                entry_id = cmd.split(" ", 1)[1]
                _set_selection(entry_id, flat_entries, selections, True)
            elif cmd.startswith("exclude ") or cmd.startswith("e "):
                entry_id = cmd.split(" ", 1)[1]
                _set_selection(entry_id, flat_entries, selections, False)
            elif cmd == "help" or cmd == "h":
                console.print(
                    "[cyan]Commands:[/cyan]\n"
                    "  toggle <id/number> - Toggle selection\n"
                    "  include <id/number> - Include component\n"
                    "  exclude <id/number> - Exclude component\n"
                    "  list - Show all components\n"
                    "  save - Save selections\n"
                    "  quit - Exit (auto-saves)"
                )
            else:
                console.print("[red]Unknown command. Type 'help' for available commands.[/red]")

        except (KeyboardInterrupt, EOFError):
            break

    # Auto-save on exit
    selection_manager.save_selections(selections)
    console.print("[green]Selections saved![/green]")


def _show_selection_list(entries, selections):
    """Display the selection list."""
    table = Table(title="Components")
    table.add_column("#", style="dim")
    table.add_column("Include", style="cyan")
    table.add_column("Type", style="blue")
    table.add_column("Name")
    table.add_column("ID", style="dim")

    for i, entry in enumerate(entries):
        sel = selections.get(entry.id)
        included = "[green]✓[/green]" if (sel is None or sel.included) else "[red]✗[/red]"
        indent = "  " * entry.level
        table.add_row(
            str(i + 1),
            included,
            entry.component_type.value,
            f"{indent}{entry.title}",
            entry.id[:8],
        )

    console.print(table)


def _toggle_selection(entry_ref, entries, selections):
    """Toggle a selection by ID or number."""
    entry = _find_entry(entry_ref, entries)
    if entry:
        sel = selections.get(entry.id)
        new_value = not (sel is None or sel.included)
        from docuagent.models.components import TOCSelection
        selections[entry.id] = TOCSelection(entry_id=entry.id, included=new_value)
        status = "[green]included[/green]" if new_value else "[red]excluded[/red]"
        console.print(f"{entry.title} is now {status}")
    else:
        console.print(f"[red]Entry not found: {entry_ref}[/red]")


def _set_selection(entry_ref, entries, selections, included):
    """Set a selection to included/excluded."""
    entry = _find_entry(entry_ref, entries)
    if entry:
        from docuagent.models.components import TOCSelection
        selections[entry.id] = TOCSelection(entry_id=entry.id, included=included)
        status = "[green]included[/green]" if included else "[red]excluded[/red]"
        console.print(f"{entry.title} is now {status}")
    else:
        console.print(f"[red]Entry not found: {entry_ref}[/red]")


def _find_entry(entry_ref, entries):
    """Find an entry by number or ID."""
    # Try as number first
    try:
        idx = int(entry_ref) - 1
        if 0 <= idx < len(entries):
            return entries[idx]
    except ValueError:
        pass

    # Try as ID (partial match)
    for entry in entries:
        if entry.id.startswith(entry_ref):
            return entry

    return None


@main.command()
@click.argument("repo_path", type=click.Path(exists=True), default=".")
@click.option(
    "--output", "-o",
    type=click.Path(),
    help="Export file path",
)
def export_selections(repo_path: str, output: str | None):
    """Export selections to a file for sharing or backup."""
    repo_path = Path(repo_path).resolve()
    selection_manager = SelectionManager(config_dir=repo_path / ".docuagent")

    if not output:
        output = "docuagent-selections.yaml"

    selection_manager.export_selections(output)
    console.print(f"[green]Selections exported to {output}[/green]")


@main.command()
@click.argument("repo_path", type=click.Path(exists=True), default=".")
@click.argument("input_file", type=click.Path(exists=True))
def import_selections(repo_path: str, input_file: str):
    """Import selections from a file."""
    repo_path = Path(repo_path).resolve()
    selection_manager = SelectionManager(config_dir=repo_path / ".docuagent")

    selections = selection_manager.import_selections(input_file)
    console.print(f"[green]Imported {len(selections)} selections from {input_file}[/green]")


@main.command()
@click.argument("repo_path", type=click.Path(exists=True), default=".")
def clear(repo_path: str):
    """Clear all cached data and selections."""
    repo_path = Path(repo_path).resolve()
    selection_manager = SelectionManager(config_dir=repo_path / ".docuagent")

    if click.confirm("Are you sure you want to clear all DocuAgent data?"):
        selection_manager.clear()
        console.print("[green]All data cleared.[/green]")


if __name__ == "__main__":
    main()
