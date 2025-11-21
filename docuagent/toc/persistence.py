"""Persistence module for user selections and documentation state."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from docuagent.models.components import TOCEntry, TOCSelection


class SelectionManager:
    """Manage persistence of user TOC selections and documentation state."""

    def __init__(self, config_dir: str | Path = ".docuagent"):
        """Initialize the selection manager.

        Args:
            config_dir: Directory for storing configuration and selections.
        """
        self.config_dir = Path(config_dir)
        self.selections_file = self.config_dir / "selections.yaml"
        self.state_file = self.config_dir / "state.json"
        self.descriptions_file = self.config_dir / "descriptions.json"

    def ensure_config_dir(self) -> None:
        """Ensure the configuration directory exists."""
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # Add to .gitignore if it exists
        gitignore = Path(".gitignore")
        if gitignore.exists():
            content = gitignore.read_text()
            if ".docuagent/" not in content:
                with gitignore.open("a") as f:
                    f.write("\n# DocuAgent configuration\n.docuagent/\n")

    def save_selections(
        self,
        selections: dict[str, TOCSelection],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Save user selections to file.

        Args:
            selections: Dictionary mapping entry IDs to selection objects.
            metadata: Optional metadata to include.
        """
        self.ensure_config_dir()

        data = {
            "version": "1.0",
            "updated_at": datetime.now().isoformat(),
            "metadata": metadata or {},
            "selections": {
                entry_id: {
                    "included": sel.included,
                    "custom_title": sel.custom_title,
                    "custom_description": sel.custom_description,
                }
                for entry_id, sel in selections.items()
            },
        }

        with self.selections_file.open("w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    def load_selections(self) -> dict[str, TOCSelection]:
        """Load user selections from file.

        Returns:
            Dictionary mapping entry IDs to selection objects.
        """
        if not self.selections_file.exists():
            return {}

        with self.selections_file.open() as f:
            data = yaml.safe_load(f) or {}

        selections = {}
        for entry_id, sel_data in data.get("selections", {}).items():
            selections[entry_id] = TOCSelection(
                entry_id=entry_id,
                included=sel_data.get("included", True),
                custom_title=sel_data.get("custom_title"),
                custom_description=sel_data.get("custom_description"),
            )

        return selections

    def update_selection(
        self,
        entry_id: str,
        included: bool | None = None,
        custom_title: str | None = None,
        custom_description: str | None = None,
    ) -> TOCSelection:
        """Update a single selection.

        Args:
            entry_id: The TOC entry ID.
            included: Whether to include in documentation.
            custom_title: Custom title override.
            custom_description: Custom description override.

        Returns:
            The updated selection object.
        """
        selections = self.load_selections()

        if entry_id in selections:
            sel = selections[entry_id]
            if included is not None:
                sel.included = included
            if custom_title is not None:
                sel.custom_title = custom_title
            if custom_description is not None:
                sel.custom_description = custom_description
        else:
            sel = TOCSelection(
                entry_id=entry_id,
                included=included if included is not None else True,
                custom_title=custom_title,
                custom_description=custom_description,
            )
            selections[entry_id] = sel

        self.save_selections(selections)
        return sel

    def initialize_from_toc(
        self,
        entries: list[TOCEntry],
        default_included: bool = True,
    ) -> dict[str, TOCSelection]:
        """Initialize selections from a TOC structure.

        Creates selection entries for all TOC items with default values.

        Args:
            entries: List of TOC entries.
            default_included: Default inclusion state.

        Returns:
            Dictionary of initialized selections.
        """
        existing = self.load_selections()
        selections = {}

        def _process_entry(entry: TOCEntry):
            if entry.id in existing:
                # Preserve existing selection
                selections[entry.id] = existing[entry.id]
            else:
                # Create new selection with default
                selections[entry.id] = TOCSelection(
                    entry_id=entry.id,
                    included=default_included,
                )

            for child in entry.children:
                _process_entry(child)

        for entry in entries:
            _process_entry(entry)

        self.save_selections(selections)
        return selections

    def get_included_ids(self) -> set[str]:
        """Get the set of included entry IDs.

        Returns:
            Set of entry IDs that are included.
        """
        selections = self.load_selections()
        return {
            entry_id
            for entry_id, sel in selections.items()
            if sel.included
        }

    def get_excluded_ids(self) -> set[str]:
        """Get the set of excluded entry IDs.

        Returns:
            Set of entry IDs that are excluded.
        """
        selections = self.load_selections()
        return {
            entry_id
            for entry_id, sel in selections.items()
            if not sel.included
        }

    def save_state(self, state: dict[str, Any]) -> None:
        """Save documentation generation state.

        Args:
            state: State dictionary to persist.
        """
        self.ensure_config_dir()

        state["updated_at"] = datetime.now().isoformat()

        with self.state_file.open("w") as f:
            json.dump(state, f, indent=2)

    def load_state(self) -> dict[str, Any]:
        """Load documentation generation state.

        Returns:
            State dictionary.
        """
        if not self.state_file.exists():
            return {}

        with self.state_file.open() as f:
            return json.load(f)

    def save_descriptions(self, descriptions: dict[str, str]) -> None:
        """Save AI-generated descriptions.

        Args:
            descriptions: Dictionary mapping component IDs to descriptions.
        """
        self.ensure_config_dir()

        data = {
            "version": "1.0",
            "updated_at": datetime.now().isoformat(),
            "descriptions": descriptions,
        }

        with self.descriptions_file.open("w") as f:
            json.dump(data, f, indent=2)

    def load_descriptions(self) -> dict[str, str]:
        """Load cached AI-generated descriptions.

        Returns:
            Dictionary mapping component IDs to descriptions.
        """
        if not self.descriptions_file.exists():
            return {}

        with self.descriptions_file.open() as f:
            data = json.load(f)

        return data.get("descriptions", {})

    def update_descriptions(self, new_descriptions: dict[str, str]) -> None:
        """Update cached descriptions with new ones.

        Args:
            new_descriptions: New descriptions to add/update.
        """
        existing = self.load_descriptions()
        existing.update(new_descriptions)
        self.save_descriptions(existing)

    def clear(self) -> None:
        """Clear all persisted data."""
        if self.selections_file.exists():
            self.selections_file.unlink()
        if self.state_file.exists():
            self.state_file.unlink()
        if self.descriptions_file.exists():
            self.descriptions_file.unlink()

    def export_selections(self, output_path: str | Path) -> None:
        """Export selections to a standalone file.

        Args:
            output_path: Path to export to.
        """
        selections = self.load_selections()
        output_path = Path(output_path)

        data = {
            "version": "1.0",
            "exported_at": datetime.now().isoformat(),
            "selections": {
                entry_id: {
                    "included": sel.included,
                    "custom_title": sel.custom_title,
                    "custom_description": sel.custom_description,
                }
                for entry_id, sel in selections.items()
            },
        }

        if output_path.suffix in (".yaml", ".yml"):
            with output_path.open("w") as f:
                yaml.dump(data, f, default_flow_style=False)
        else:
            with output_path.open("w") as f:
                json.dump(data, f, indent=2)

    def import_selections(self, input_path: str | Path) -> dict[str, TOCSelection]:
        """Import selections from a file.

        Args:
            input_path: Path to import from.

        Returns:
            Dictionary of imported selections.
        """
        input_path = Path(input_path)

        if input_path.suffix in (".yaml", ".yml"):
            with input_path.open() as f:
                data = yaml.safe_load(f)
        else:
            with input_path.open() as f:
                data = json.load(f)

        selections = {}
        for entry_id, sel_data in data.get("selections", {}).items():
            selections[entry_id] = TOCSelection(
                entry_id=entry_id,
                included=sel_data.get("included", True),
                custom_title=sel_data.get("custom_title"),
                custom_description=sel_data.get("custom_description"),
            )

        self.save_selections(selections)
        return selections
