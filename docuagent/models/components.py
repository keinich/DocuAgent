"""Data models for API components and documentation structure."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ComponentType(str, Enum):
    """Types of API components."""

    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    PROPERTY = "property"
    CONSTANT = "constant"
    VARIABLE = "variable"


class ParameterInfo(BaseModel):
    """Information about a function/method parameter."""

    name: str
    type_annotation: str | None = None
    default_value: str | None = None
    description: str | None = None


class APIComponent(BaseModel):
    """Base model for all API components."""

    id: str = Field(..., description="Unique identifier for this component")
    name: str = Field(..., description="Name of the component")
    component_type: ComponentType
    file_path: str = Field(..., description="Relative path to the source file")
    line_number: int = Field(..., description="Line number where component is defined")
    docstring: str | None = None
    source_code: str | None = None
    ai_description: str | None = Field(
        None, description="AI-generated description of the component"
    )

    def get_qualified_name(self) -> str:
        """Get the fully qualified name of the component."""
        return f"{self.file_path}:{self.name}"


class PropertyComponent(APIComponent):
    """Model for a class property or attribute."""

    component_type: ComponentType = ComponentType.PROPERTY
    type_annotation: str | None = None
    default_value: str | None = None
    is_class_var: bool = False


class FunctionComponent(APIComponent):
    """Model for a standalone function."""

    component_type: ComponentType = ComponentType.FUNCTION
    parameters: list[ParameterInfo] = Field(default_factory=list)
    return_type: str | None = None
    is_async: bool = False
    decorators: list[str] = Field(default_factory=list)


class MethodComponent(FunctionComponent):
    """Model for a class method."""

    component_type: ComponentType = ComponentType.METHOD
    is_static: bool = False
    is_classmethod: bool = False
    is_property: bool = False
    parent_class: str | None = None


class ClassComponent(APIComponent):
    """Model for a class definition."""

    component_type: ComponentType = ComponentType.CLASS
    base_classes: list[str] = Field(default_factory=list)
    methods: list[MethodComponent] = Field(default_factory=list)
    properties: list[PropertyComponent] = Field(default_factory=list)
    class_variables: list[PropertyComponent] = Field(default_factory=list)
    decorators: list[str] = Field(default_factory=list)


class ModuleComponent(APIComponent):
    """Model for a Python module."""

    component_type: ComponentType = ComponentType.MODULE
    classes: list[ClassComponent] = Field(default_factory=list)
    functions: list[FunctionComponent] = Field(default_factory=list)
    constants: list[PropertyComponent] = Field(default_factory=list)
    imports: list[str] = Field(default_factory=list)
    all_exports: list[str] | None = Field(
        None, description="Contents of __all__ if defined"
    )


class TOCEntry(BaseModel):
    """An entry in the table of contents."""

    id: str = Field(..., description="Unique identifier matching component ID")
    title: str = Field(..., description="Display title for the entry")
    component_type: ComponentType
    level: int = Field(..., description="Nesting level (0 = top level)")
    parent_id: str | None = None
    children: list["TOCEntry"] = Field(default_factory=list)
    file_path: str
    line_number: int

    class Config:
        """Pydantic configuration."""

        arbitrary_types_allowed = True


class TOCSelection(BaseModel):
    """User's selection state for TOC entries."""

    entry_id: str
    included: bool = True
    custom_title: str | None = None
    custom_description: str | None = None

    class Config:
        """Pydantic configuration."""

        arbitrary_types_allowed = True


class DocumentationConfig(BaseModel):
    """Configuration for documentation generation."""

    repo_path: str
    output_dir: str = "docs"
    title: str = "API Documentation"
    include_private: bool = False
    include_source: bool = True
    languages: list[str] = Field(default_factory=lambda: ["python"])
    exclude_patterns: list[str] = Field(default_factory=list)
    selections_file: str = ".docuagent/selections.yaml"


class GeneratedDocumentation(BaseModel):
    """Model for generated documentation output."""

    component_id: str
    title: str
    html_content: str
    markdown_content: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
