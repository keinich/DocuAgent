"""API Extractor for traversing repositories and extracting public API components."""

import fnmatch
from pathlib import Path

from docuagent.analyzer.parser import PythonParser
from docuagent.models.components import ModuleComponent


class APIExtractor:
    """Extract public API components from a repository."""

    # Default patterns to exclude
    DEFAULT_EXCLUDE_PATTERNS = [
        "__pycache__",
        "*.pyc",
        ".git",
        ".venv",
        "venv",
        "env",
        ".env",
        "node_modules",
        "dist",
        "build",
        "*.egg-info",
        ".tox",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "tests",
        "test_*",
        "*_test.py",
        "conftest.py",
        "setup.py",
    ]

    def __init__(
        self,
        repo_path: str | Path,
        include_private: bool = False,
        exclude_patterns: list[str] | None = None,
        include_tests: bool = False,
    ):
        """Initialize the API extractor.

        Args:
            repo_path: Path to the repository root.
            include_private: Whether to include private members.
            exclude_patterns: Additional patterns to exclude.
            include_tests: Whether to include test files.
        """
        self.repo_path = Path(repo_path).resolve()
        self.include_private = include_private
        self.include_tests = include_tests

        # Build exclude patterns
        self.exclude_patterns = list(self.DEFAULT_EXCLUDE_PATTERNS)
        if include_tests:
            # Remove test-related patterns if including tests
            test_patterns = ["tests", "test_*", "*_test.py", "conftest.py"]
            self.exclude_patterns = [p for p in self.exclude_patterns if p not in test_patterns]

        if exclude_patterns:
            self.exclude_patterns.extend(exclude_patterns)

        self.parser = PythonParser(include_private=include_private)

    def extract(self) -> list[ModuleComponent]:
        """Extract all public API components from the repository.

        Returns:
            List of ModuleComponent objects representing each Python module.
        """
        modules = []

        for py_file in self._find_python_files():
            module = self.parser.parse_file(py_file, relative_to=self.repo_path)
            if module and self._has_public_api(module):
                modules.append(module)

        # Sort modules by path for consistent ordering
        modules.sort(key=lambda m: m.file_path)

        return modules

    def _find_python_files(self) -> list[Path]:
        """Find all Python files in the repository, respecting exclude patterns."""
        python_files = []

        for py_file in self.repo_path.rglob("*.py"):
            if not self._should_exclude(py_file):
                python_files.append(py_file)

        return sorted(python_files)

    def _should_exclude(self, file_path: Path) -> bool:
        """Check if a file should be excluded based on patterns."""
        # Get path relative to repo root
        try:
            rel_path = file_path.relative_to(self.repo_path)
        except ValueError:
            return True

        # Check each part of the path against exclude patterns
        parts = list(rel_path.parts)

        for pattern in self.exclude_patterns:
            # Check if any path component matches
            for part in parts:
                if fnmatch.fnmatch(part, pattern):
                    return True

            # Also check the full relative path
            if fnmatch.fnmatch(str(rel_path), pattern):
                return True

        return False

    def _has_public_api(self, module: ModuleComponent) -> bool:
        """Check if a module has any public API to document."""
        # Module has public API if it has any classes, functions, or constants
        return bool(module.classes or module.functions or module.constants)

    def get_statistics(self, modules: list[ModuleComponent]) -> dict:
        """Get statistics about the extracted API.

        Args:
            modules: List of extracted modules.

        Returns:
            Dictionary with statistics about the extracted API.
        """
        stats = {
            "total_modules": len(modules),
            "total_classes": 0,
            "total_functions": 0,
            "total_methods": 0,
            "total_properties": 0,
            "total_constants": 0,
            "modules_with_docstrings": 0,
            "classes_with_docstrings": 0,
            "functions_with_docstrings": 0,
        }

        for module in modules:
            if module.docstring:
                stats["modules_with_docstrings"] += 1

            stats["total_classes"] += len(module.classes)
            stats["total_functions"] += len(module.functions)
            stats["total_constants"] += len(module.constants)

            for func in module.functions:
                if func.docstring:
                    stats["functions_with_docstrings"] += 1

            for cls in module.classes:
                if cls.docstring:
                    stats["classes_with_docstrings"] += 1

                stats["total_methods"] += len(cls.methods)
                stats["total_properties"] += len(cls.properties) + len(cls.class_variables)

        return stats
