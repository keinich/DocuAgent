"""Table of Contents generator for API documentation."""

from docuagent.models.components import (
    ClassComponent,
    ComponentType,
    FunctionComponent,
    ModuleComponent,
    TOCEntry,
)


class TOCGenerator:
    """Generate a structured table of contents from extracted API components."""

    def __init__(
        self,
        group_by_module: bool = True,
        include_methods: bool = True,
        include_properties: bool = True,
    ):
        """Initialize the TOC generator.

        Args:
            group_by_module: Whether to group entries by module.
            include_methods: Whether to include class methods in TOC.
            include_properties: Whether to include properties in TOC.
        """
        self.group_by_module = group_by_module
        self.include_methods = include_methods
        self.include_properties = include_properties

    def generate(self, modules: list[ModuleComponent]) -> list[TOCEntry]:
        """Generate table of contents from extracted modules.

        Args:
            modules: List of extracted module components.

        Returns:
            List of TOC entries representing the documentation structure.
        """
        toc_entries = []

        for module in modules:
            module_entry = self._create_module_entry(module)
            toc_entries.append(module_entry)

        return toc_entries

    def _create_module_entry(self, module: ModuleComponent) -> TOCEntry:
        """Create a TOC entry for a module and its contents."""
        module_entry = TOCEntry(
            id=module.id,
            title=self._format_module_title(module),
            component_type=ComponentType.MODULE,
            level=0,
            file_path=module.file_path,
            line_number=module.line_number,
            children=[],
        )

        # Add classes
        for cls in module.classes:
            class_entry = self._create_class_entry(cls, parent_id=module.id)
            module_entry.children.append(class_entry)

        # Add standalone functions
        for func in module.functions:
            func_entry = self._create_function_entry(func, parent_id=module.id)
            module_entry.children.append(func_entry)

        # Add module-level constants (if any significant ones)
        for const in module.constants:
            if self._is_significant_constant(const.name):
                const_entry = TOCEntry(
                    id=const.id,
                    title=const.name,
                    component_type=ComponentType.CONSTANT,
                    level=1,
                    parent_id=module.id,
                    file_path=const.file_path,
                    line_number=const.line_number,
                )
                module_entry.children.append(const_entry)

        return module_entry

    def _create_class_entry(self, cls: ClassComponent, parent_id: str) -> TOCEntry:
        """Create a TOC entry for a class and its members."""
        class_entry = TOCEntry(
            id=cls.id,
            title=self._format_class_title(cls),
            component_type=ComponentType.CLASS,
            level=1,
            parent_id=parent_id,
            file_path=cls.file_path,
            line_number=cls.line_number,
            children=[],
        )

        # Add methods
        if self.include_methods:
            for method in cls.methods:
                method_entry = TOCEntry(
                    id=method.id,
                    title=self._format_method_title(method),
                    component_type=ComponentType.METHOD,
                    level=2,
                    parent_id=cls.id,
                    file_path=method.file_path,
                    line_number=method.line_number,
                )
                class_entry.children.append(method_entry)

        # Add properties
        if self.include_properties:
            for prop in cls.properties:
                prop_entry = TOCEntry(
                    id=prop.id,
                    title=prop.name,
                    component_type=ComponentType.PROPERTY,
                    level=2,
                    parent_id=cls.id,
                    file_path=prop.file_path,
                    line_number=prop.line_number,
                )
                class_entry.children.append(prop_entry)

            for var in cls.class_variables:
                var_entry = TOCEntry(
                    id=var.id,
                    title=var.name,
                    component_type=ComponentType.VARIABLE,
                    level=2,
                    parent_id=cls.id,
                    file_path=var.file_path,
                    line_number=var.line_number,
                )
                class_entry.children.append(var_entry)

        return class_entry

    def _create_function_entry(
        self, func: FunctionComponent, parent_id: str
    ) -> TOCEntry:
        """Create a TOC entry for a function."""
        return TOCEntry(
            id=func.id,
            title=self._format_function_title(func),
            component_type=ComponentType.FUNCTION,
            level=1,
            parent_id=parent_id,
            file_path=func.file_path,
            line_number=func.line_number,
        )

    def _format_module_title(self, module: ModuleComponent) -> str:
        """Format the title for a module entry."""
        # Convert file path to module-style notation
        path = module.file_path.replace("/", ".").replace("\\", ".")
        if path.endswith(".py"):
            path = path[:-3]
        return path

    def _format_class_title(self, cls: ClassComponent) -> str:
        """Format the title for a class entry."""
        title = cls.name
        if cls.base_classes:
            bases = ", ".join(cls.base_classes[:2])  # Show first 2 bases
            if len(cls.base_classes) > 2:
                bases += ", ..."
            title = f"{cls.name}({bases})"
        return title

    def _format_function_title(self, func: FunctionComponent) -> str:
        """Format the title for a function entry."""
        params = []
        for p in func.parameters[:3]:  # Show first 3 params
            if p.default_value:
                params.append(f"{p.name}=...")
            else:
                params.append(p.name)

        if len(func.parameters) > 3:
            params.append("...")

        prefix = "async " if func.is_async else ""
        return f"{prefix}{func.name}({', '.join(params)})"

    def _format_method_title(self, method) -> str:
        """Format the title for a method entry."""
        params = []
        for p in method.parameters[:2]:  # Show first 2 params
            params.append(p.name)

        if len(method.parameters) > 2:
            params.append("...")

        prefix = ""
        if method.is_static:
            prefix = "@staticmethod "
        elif method.is_classmethod:
            prefix = "@classmethod "
        elif method.is_async:
            prefix = "async "

        return f"{prefix}{method.name}({', '.join(params)})"

    def _is_significant_constant(self, name: str) -> bool:
        """Determine if a constant is significant enough to include in TOC."""
        # Include uppercase constants and version info
        if name.isupper():
            return True
        if name in ("__version__", "__author__", "__all__"):
            return True
        return False

    def flatten(self, entries: list[TOCEntry]) -> list[TOCEntry]:
        """Flatten a nested TOC structure into a single list.

        Args:
            entries: Nested TOC entries.

        Returns:
            Flattened list of all TOC entries.
        """
        flat = []

        def _flatten(entry: TOCEntry):
            flat.append(entry)
            for child in entry.children:
                _flatten(child)

        for entry in entries:
            _flatten(entry)

        return flat

    def get_entry_by_id(
        self, entries: list[TOCEntry], entry_id: str
    ) -> TOCEntry | None:
        """Find a TOC entry by its ID.

        Args:
            entries: List of TOC entries (can be nested).
            entry_id: The ID to search for.

        Returns:
            The matching TOC entry or None.
        """
        for entry in self.flatten(entries):
            if entry.id == entry_id:
                return entry
        return None

    def filter_by_selections(
        self,
        entries: list[TOCEntry],
        selections: dict[str, bool],
    ) -> list[TOCEntry]:
        """Filter TOC entries based on user selections.

        Args:
            entries: List of TOC entries.
            selections: Dictionary mapping entry IDs to inclusion status.

        Returns:
            Filtered list of TOC entries.
        """
        def _filter_entry(entry: TOCEntry) -> TOCEntry | None:
            # Check if this entry is selected
            if entry.id in selections and not selections[entry.id]:
                return None

            # Filter children recursively
            filtered_children = []
            for child in entry.children:
                filtered_child = _filter_entry(child)
                if filtered_child:
                    filtered_children.append(filtered_child)

            # Create new entry with filtered children
            if entry.id not in selections or selections[entry.id]:
                return TOCEntry(
                    id=entry.id,
                    title=entry.title,
                    component_type=entry.component_type,
                    level=entry.level,
                    parent_id=entry.parent_id,
                    file_path=entry.file_path,
                    line_number=entry.line_number,
                    children=filtered_children,
                )

            return None

        filtered = []
        for entry in entries:
            filtered_entry = _filter_entry(entry)
            if filtered_entry:
                filtered.append(filtered_entry)

        return filtered

    def to_dict(self, entries: list[TOCEntry]) -> list[dict]:
        """Convert TOC entries to a dictionary representation.

        Args:
            entries: List of TOC entries.

        Returns:
            List of dictionaries representing the TOC.
        """
        def _entry_to_dict(entry: TOCEntry) -> dict:
            return {
                "id": entry.id,
                "title": entry.title,
                "type": entry.component_type.value,
                "level": entry.level,
                "file_path": entry.file_path,
                "line_number": entry.line_number,
                "children": [_entry_to_dict(child) for child in entry.children],
            }

        return [_entry_to_dict(entry) for entry in entries]
