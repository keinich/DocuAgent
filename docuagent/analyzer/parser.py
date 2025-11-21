"""AST-based Python code parser for extracting API components."""

import ast
import hashlib
from pathlib import Path

from docuagent.models.components import (
    ClassComponent,
    ComponentType,
    FunctionComponent,
    MethodComponent,
    ModuleComponent,
    ParameterInfo,
    PropertyComponent,
)


def generate_id(file_path: str, name: str, line_number: int) -> str:
    """Generate a unique ID for a component."""
    content = f"{file_path}:{name}:{line_number}"
    return hashlib.sha256(content.encode()).hexdigest()[:12]


class PythonParser:
    """Parse Python source files and extract API components."""

    def __init__(self, include_private: bool = False):
        """Initialize the parser.

        Args:
            include_private: Whether to include private members (starting with _).
        """
        self.include_private = include_private

    def parse_file(self, file_path: Path, relative_to: Path | None = None) -> ModuleComponent | None:
        """Parse a Python file and extract its public API.

        Args:
            file_path: Path to the Python file.
            relative_to: Base path for computing relative paths.

        Returns:
            ModuleComponent with all extracted API components, or None if parsing fails.
        """
        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(file_path))
        except (SyntaxError, UnicodeDecodeError) as e:
            print(f"Warning: Could not parse {file_path}: {e}")
            return None

        rel_path = str(file_path.relative_to(relative_to)) if relative_to else str(file_path)

        module = ModuleComponent(
            id=generate_id(rel_path, file_path.stem, 1),
            name=file_path.stem,
            file_path=rel_path,
            line_number=1,
            docstring=ast.get_docstring(tree),
            source_code=source,
        )

        # Extract __all__ if defined
        module.all_exports = self._extract_all_exports(tree)

        # Extract imports
        module.imports = self._extract_imports(tree)

        # Extract module-level components
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                if self._should_include(node.name, module.all_exports):
                    class_comp = self._parse_class(node, rel_path, source)
                    if class_comp:
                        module.classes.append(class_comp)

            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                if self._should_include(node.name, module.all_exports):
                    func_comp = self._parse_function(node, rel_path, source)
                    if func_comp:
                        module.functions.append(func_comp)

            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        if self._should_include(target.id, module.all_exports):
                            const = self._parse_assignment(node, target, rel_path, source)
                            if const:
                                module.constants.append(const)

            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if self._should_include(node.target.id, module.all_exports):
                    const = self._parse_annotated_assignment(node, rel_path, source)
                    if const:
                        module.constants.append(const)

        return module

    def _should_include(self, name: str, all_exports: list[str] | None) -> bool:
        """Determine if a component should be included based on naming and __all__."""
        # If __all__ is defined, only include what's in it
        if all_exports is not None:
            return name in all_exports

        # Otherwise, include based on naming convention
        if self.include_private:
            return True

        # Exclude private and dunder (except special ones)
        if name.startswith("_") and not name.startswith("__"):
            return False

        return True

    def _extract_all_exports(self, tree: ast.Module) -> list[str] | None:
        """Extract the __all__ list if defined."""
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "__all__":
                        if isinstance(node.value, ast.List | ast.Tuple):
                            exports = []
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                    exports.append(elt.value)
                            return exports
        return None

    def _extract_imports(self, tree: ast.Module) -> list[str]:
        """Extract import statements from the module."""
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    imports.append(f"{module}.{alias.name}" if module else alias.name)
        return imports

    def _parse_class(
        self, node: ast.ClassDef, file_path: str, source: str
    ) -> ClassComponent | None:
        """Parse a class definition."""
        class_comp = ClassComponent(
            id=generate_id(file_path, node.name, node.lineno),
            name=node.name,
            file_path=file_path,
            line_number=node.lineno,
            docstring=ast.get_docstring(node),
            source_code=self._get_source_segment(source, node),
            base_classes=[self._get_base_class_name(base) for base in node.bases],
            decorators=[self._get_decorator_name(d) for d in node.decorator_list],
        )

        # Parse class body
        for item in node.body:
            if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                if self._should_include_method(item.name):
                    method = self._parse_method(item, file_path, source, node.name)
                    if method:
                        if method.is_property:
                            prop = PropertyComponent(
                                id=method.id,
                                name=method.name,
                                file_path=file_path,
                                line_number=method.line_number,
                                docstring=method.docstring,
                                source_code=method.source_code,
                                type_annotation=method.return_type,
                            )
                            class_comp.properties.append(prop)
                        else:
                            class_comp.methods.append(method)

            elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                if self._should_include_method(item.target.id):
                    prop = self._parse_class_variable(item, file_path, source)
                    if prop:
                        class_comp.class_variables.append(prop)

            elif isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and self._should_include_method(target.id):
                        prop = self._parse_assignment(item, target, file_path, source)
                        if prop:
                            prop.is_class_var = True
                            class_comp.class_variables.append(prop)

        return class_comp

    def _should_include_method(self, name: str) -> bool:
        """Determine if a method/attribute should be included."""
        if self.include_private:
            return True

        # Include special methods that are commonly documented
        special_methods = {"__init__", "__new__", "__call__", "__enter__", "__exit__"}
        if name in special_methods:
            return True

        # Exclude other dunder methods and private methods
        if name.startswith("_"):
            return False

        return True

    def _parse_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, file_path: str, source: str
    ) -> FunctionComponent | None:
        """Parse a function definition."""
        return FunctionComponent(
            id=generate_id(file_path, node.name, node.lineno),
            name=node.name,
            file_path=file_path,
            line_number=node.lineno,
            docstring=ast.get_docstring(node),
            source_code=self._get_source_segment(source, node),
            parameters=self._parse_parameters(node.args),
            return_type=self._get_annotation(node.returns),
            is_async=isinstance(node, ast.AsyncFunctionDef),
            decorators=[self._get_decorator_name(d) for d in node.decorator_list],
        )

    def _parse_method(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        file_path: str,
        source: str,
        parent_class: str,
    ) -> MethodComponent | None:
        """Parse a method definition."""
        decorators = [self._get_decorator_name(d) for d in node.decorator_list]

        return MethodComponent(
            id=generate_id(file_path, f"{parent_class}.{node.name}", node.lineno),
            name=node.name,
            file_path=file_path,
            line_number=node.lineno,
            docstring=ast.get_docstring(node),
            source_code=self._get_source_segment(source, node),
            parameters=self._parse_parameters(node.args),
            return_type=self._get_annotation(node.returns),
            is_async=isinstance(node, ast.AsyncFunctionDef),
            decorators=decorators,
            is_static="staticmethod" in decorators,
            is_classmethod="classmethod" in decorators,
            is_property="property" in decorators,
            parent_class=parent_class,
        )

    def _parse_parameters(self, args: ast.arguments) -> list[ParameterInfo]:
        """Parse function/method parameters."""
        params = []

        # Calculate defaults offset
        num_defaults = len(args.defaults)
        num_args = len(args.args)
        defaults_offset = num_args - num_defaults

        for i, arg in enumerate(args.args):
            # Skip 'self' and 'cls'
            if arg.arg in ("self", "cls"):
                continue

            default = None
            if i >= defaults_offset:
                default_node = args.defaults[i - defaults_offset]
                default = self._get_constant_value(default_node)

            params.append(
                ParameterInfo(
                    name=arg.arg,
                    type_annotation=self._get_annotation(arg.annotation),
                    default_value=default,
                )
            )

        # Handle *args
        if args.vararg:
            params.append(
                ParameterInfo(
                    name=f"*{args.vararg.arg}",
                    type_annotation=self._get_annotation(args.vararg.annotation),
                )
            )

        # Handle keyword-only args
        for i, arg in enumerate(args.kwonlyargs):
            default = None
            if i < len(args.kw_defaults) and args.kw_defaults[i] is not None:
                default = self._get_constant_value(args.kw_defaults[i])

            params.append(
                ParameterInfo(
                    name=arg.arg,
                    type_annotation=self._get_annotation(arg.annotation),
                    default_value=default,
                )
            )

        # Handle **kwargs
        if args.kwarg:
            params.append(
                ParameterInfo(
                    name=f"**{args.kwarg.arg}",
                    type_annotation=self._get_annotation(args.kwarg.annotation),
                )
            )

        return params

    def _parse_assignment(
        self, node: ast.Assign, target: ast.Name, file_path: str, source: str
    ) -> PropertyComponent | None:
        """Parse an assignment statement as a constant/variable."""
        return PropertyComponent(
            id=generate_id(file_path, target.id, node.lineno),
            name=target.id,
            file_path=file_path,
            line_number=node.lineno,
            source_code=self._get_source_segment(source, node),
            default_value=self._get_constant_value(node.value),
        )

    def _parse_annotated_assignment(
        self, node: ast.AnnAssign, file_path: str, source: str
    ) -> PropertyComponent | None:
        """Parse an annotated assignment."""
        if not isinstance(node.target, ast.Name):
            return None

        return PropertyComponent(
            id=generate_id(file_path, node.target.id, node.lineno),
            name=node.target.id,
            file_path=file_path,
            line_number=node.lineno,
            source_code=self._get_source_segment(source, node),
            type_annotation=self._get_annotation(node.annotation),
            default_value=self._get_constant_value(node.value) if node.value else None,
        )

    def _parse_class_variable(
        self, node: ast.AnnAssign, file_path: str, source: str
    ) -> PropertyComponent | None:
        """Parse a class variable with annotation."""
        if not isinstance(node.target, ast.Name):
            return None

        return PropertyComponent(
            id=generate_id(file_path, node.target.id, node.lineno),
            name=node.target.id,
            file_path=file_path,
            line_number=node.lineno,
            source_code=self._get_source_segment(source, node),
            type_annotation=self._get_annotation(node.annotation),
            default_value=self._get_constant_value(node.value) if node.value else None,
            is_class_var=True,
        )

    def _get_annotation(self, node: ast.expr | None) -> str | None:
        """Get the string representation of a type annotation."""
        if node is None:
            return None
        return ast.unparse(node)

    def _get_constant_value(self, node: ast.expr | None) -> str | None:
        """Get the string representation of a constant value."""
        if node is None:
            return None

        try:
            return ast.unparse(node)
        except Exception:
            return None

    def _get_base_class_name(self, node: ast.expr) -> str:
        """Get the name of a base class."""
        return ast.unparse(node)

    def _get_decorator_name(self, node: ast.expr) -> str:
        """Get the name of a decorator."""
        return ast.unparse(node)

    def _get_source_segment(self, source: str, node: ast.AST) -> str | None:
        """Get the source code for a node."""
        try:
            return ast.get_source_segment(source, node)
        except Exception:
            return None
