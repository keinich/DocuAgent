"""AI Agent for generating intelligent documentation."""

import json
import os
from typing import Any

from anthropic import Anthropic

from docuagent.models.components import (
    APIComponent,
    ClassComponent,
    ComponentType,
    FunctionComponent,
    MethodComponent,
    ModuleComponent,
    PropertyComponent,
)


class DocumentationAgent:
    """AI Agent that generates intelligent documentation for code components."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-20250514",
    ):
        """Initialize the documentation agent.

        Args:
            api_key: Anthropic API key. If None, uses ANTHROPIC_API_KEY env var.
            model: The Claude model to use.
        """
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Anthropic API key required. Set ANTHROPIC_API_KEY environment variable "
                "or pass api_key parameter."
            )

        self.client = Anthropic(api_key=self.api_key)
        self.model = model

    def generate_description(
        self,
        component: APIComponent,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Generate an AI description for a component.

        Args:
            component: The API component to document.
            context: Additional context (parent class, module info, etc.).

        Returns:
            AI-generated description of the component.
        """
        prompt = self._build_description_prompt(component, context)

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
            system=self._get_system_prompt(),
        )

        return response.content[0].text.strip()

    def generate_module_documentation(
        self,
        module: ModuleComponent,
        include_source: bool = False,
    ) -> dict[str, str]:
        """Generate documentation for an entire module.

        Args:
            module: The module to document.
            include_source: Whether to include source code analysis.

        Returns:
            Dictionary mapping component IDs to their AI-generated descriptions.
        """
        descriptions = {}

        # Document the module itself
        descriptions[module.id] = self.generate_description(
            module,
            context={"type": "module", "include_source": include_source},
        )

        # Document classes
        for cls in module.classes:
            descriptions[cls.id] = self.generate_description(
                cls,
                context={
                    "type": "class",
                    "module": module.name,
                    "include_source": include_source,
                },
            )

            # Document methods
            for method in cls.methods:
                descriptions[method.id] = self.generate_description(
                    method,
                    context={
                        "type": "method",
                        "class": cls.name,
                        "module": module.name,
                        "include_source": include_source,
                    },
                )

            # Document properties
            for prop in cls.properties:
                descriptions[prop.id] = self.generate_description(
                    prop,
                    context={
                        "type": "property",
                        "class": cls.name,
                        "module": module.name,
                    },
                )

        # Document standalone functions
        for func in module.functions:
            descriptions[func.id] = self.generate_description(
                func,
                context={
                    "type": "function",
                    "module": module.name,
                    "include_source": include_source,
                },
            )

        return descriptions

    def generate_batch_descriptions(
        self,
        components: list[APIComponent],
        batch_size: int = 10,
    ) -> dict[str, str]:
        """Generate descriptions for multiple components efficiently.

        Uses batching to reduce API calls by documenting multiple simple
        components in a single request.

        Args:
            components: List of components to document.
            batch_size: Number of simple components per batch.

        Returns:
            Dictionary mapping component IDs to descriptions.
        """
        descriptions = {}

        # Separate complex and simple components
        complex_components = []
        simple_components = []

        for comp in components:
            if isinstance(comp, ClassComponent | ModuleComponent):
                complex_components.append(comp)
            else:
                simple_components.append(comp)

        # Document complex components individually
        for comp in complex_components:
            descriptions[comp.id] = self.generate_description(comp)

        # Batch document simple components
        for i in range(0, len(simple_components), batch_size):
            batch = simple_components[i : i + batch_size]
            batch_descriptions = self._generate_batch(batch)
            descriptions.update(batch_descriptions)

        return descriptions

    def _generate_batch(self, components: list[APIComponent]) -> dict[str, str]:
        """Generate descriptions for a batch of components in one API call."""
        if not components:
            return {}

        prompt = self._build_batch_prompt(components)

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
            system=self._get_system_prompt(),
        )

        # Parse the JSON response
        try:
            result_text = response.content[0].text.strip()
            # Extract JSON from markdown code block if present
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()

            results = json.loads(result_text)
            return {item["id"]: item["description"] for item in results}
        except (json.JSONDecodeError, KeyError, IndexError):
            # Fall back to individual generation if batch parsing fails
            descriptions = {}
            for comp in components:
                descriptions[comp.id] = self.generate_description(comp)
            return descriptions

    def _get_system_prompt(self) -> str:
        """Get the system prompt for the documentation agent."""
        return """You are an expert technical documentation writer specializing in API documentation.

Your task is to write clear, concise, and helpful documentation for code components.

Guidelines:
1. Write in a professional, technical tone
2. Focus on WHAT the component does and WHY someone would use it
3. Include information about parameters, return values, and exceptions when relevant
4. Mention important behavior, side effects, or constraints
5. Keep descriptions concise but complete (typically 1-3 sentences for simple items, more for complex ones)
6. Use proper technical terminology
7. If the component has a docstring, enhance it rather than replace it
8. Do not include code examples unless specifically requested

When documenting:
- Functions/Methods: Explain purpose, parameters, return value, and any notable behavior
- Classes: Explain the class's role, key features, and typical usage patterns
- Properties: Explain what data they represent and any validation/transformation
- Modules: Provide an overview of the module's purpose and main components
- Constants: Explain the purpose and typical usage of the constant"""

    def _build_description_prompt(
        self,
        component: APIComponent,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Build the prompt for generating a component description."""
        context = context or {}

        prompt_parts = [
            f"Generate documentation for the following {component.component_type.value}:\n",
            f"Name: {component.name}",
            f"File: {component.file_path}:{component.line_number}",
        ]

        # Add context
        if "module" in context:
            prompt_parts.append(f"Module: {context['module']}")
        if "class" in context:
            prompt_parts.append(f"Class: {context['class']}")

        # Add existing docstring if present
        if component.docstring:
            prompt_parts.append(f"\nExisting docstring:\n{component.docstring}")

        # Add source code for analysis
        if context.get("include_source") and component.source_code:
            prompt_parts.append(f"\nSource code:\n```python\n{component.source_code}\n```")

        # Add type-specific information
        if isinstance(component, FunctionComponent | MethodComponent):
            if component.parameters:
                params_str = ", ".join(
                    f"{p.name}: {p.type_annotation or 'Any'}"
                    + (f" = {p.default_value}" if p.default_value else "")
                    for p in component.parameters
                )
                prompt_parts.append(f"Parameters: {params_str}")

            if component.return_type:
                prompt_parts.append(f"Return type: {component.return_type}")

            if component.is_async:
                prompt_parts.append("Note: This is an async function/method")

            if isinstance(component, MethodComponent):
                if component.is_static:
                    prompt_parts.append("Note: This is a static method")
                elif component.is_classmethod:
                    prompt_parts.append("Note: This is a class method")

        elif isinstance(component, ClassComponent):
            if component.base_classes:
                prompt_parts.append(f"Base classes: {', '.join(component.base_classes)}")

            method_names = [m.name for m in component.methods[:10]]  # First 10 methods
            if method_names:
                prompt_parts.append(f"Key methods: {', '.join(method_names)}")

        elif isinstance(component, PropertyComponent):
            if component.type_annotation:
                prompt_parts.append(f"Type: {component.type_annotation}")
            if component.default_value:
                prompt_parts.append(f"Default: {component.default_value}")

        elif isinstance(component, ModuleComponent):
            class_names = [c.name for c in component.classes]
            func_names = [f.name for f in component.functions]

            if class_names:
                prompt_parts.append(f"Classes: {', '.join(class_names)}")
            if func_names:
                prompt_parts.append(f"Functions: {', '.join(func_names)}")

        prompt_parts.append("\nWrite a clear, concise documentation description:")

        return "\n".join(prompt_parts)

    def _build_batch_prompt(self, components: list[APIComponent]) -> str:
        """Build a prompt for batch documentation generation."""
        prompt_parts = [
            "Generate documentation for the following components.",
            "Return a JSON array with objects containing 'id' and 'description' fields.",
            "\nComponents to document:\n",
        ]

        for comp in components:
            comp_info = [
                f"- ID: {comp.id}",
                f"  Name: {comp.name}",
                f"  Type: {comp.component_type.value}",
            ]

            if comp.docstring:
                # Truncate long docstrings
                docstring = comp.docstring[:200] + "..." if len(comp.docstring) > 200 else comp.docstring
                comp_info.append(f"  Docstring: {docstring}")

            if isinstance(comp, FunctionComponent | MethodComponent):
                if comp.parameters:
                    params = [p.name for p in comp.parameters]
                    comp_info.append(f"  Parameters: {', '.join(params)}")
                if comp.return_type:
                    comp_info.append(f"  Returns: {comp.return_type}")

            prompt_parts.append("\n".join(comp_info))
            prompt_parts.append("")

        prompt_parts.append(
            "\nRespond with only a JSON array, no additional text. "
            'Format: [{"id": "...", "description": "..."}]'
        )

        return "\n".join(prompt_parts)

    def suggest_structure(
        self,
        modules: list[ModuleComponent],
    ) -> dict[str, Any]:
        """Suggest an intelligent documentation structure based on the codebase.

        Args:
            modules: List of extracted modules.

        Returns:
            Dictionary with suggested structure and groupings.
        """
        # Build a summary of the codebase
        summary = self._build_codebase_summary(modules)

        prompt = f"""Analyze this codebase structure and suggest an intelligent documentation organization:

{summary}

Provide suggestions for:
1. How to group related modules/classes
2. Recommended documentation order
3. Which components are most important to document
4. Any architectural insights that should be highlighted

Respond in JSON format with the following structure:
{{
    "groups": [
        {{"name": "Group Name", "description": "...", "modules": ["module1", "module2"]}}
    ],
    "priority_components": ["component_id1", "component_id2"],
    "architectural_notes": "...",
    "recommended_sections": ["Section 1", "Section 2"]
}}"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
            system="You are a software architect analyzing a codebase to create optimal documentation structure.",
        )

        try:
            result_text = response.content[0].text.strip()
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()

            return json.loads(result_text)
        except (json.JSONDecodeError, IndexError):
            return {"error": "Could not parse structure suggestions", "raw": response.content[0].text}

    def _build_codebase_summary(self, modules: list[ModuleComponent]) -> str:
        """Build a summary of the codebase for structure analysis."""
        summary_parts = ["Codebase Overview:", ""]

        for module in modules:
            summary_parts.append(f"Module: {module.file_path}")

            if module.docstring:
                summary_parts.append(f"  Description: {module.docstring[:100]}...")

            if module.classes:
                for cls in module.classes:
                    base_info = f" ({', '.join(cls.base_classes)})" if cls.base_classes else ""
                    summary_parts.append(f"  Class: {cls.name}{base_info}")
                    summary_parts.append(f"    Methods: {len(cls.methods)}")

            if module.functions:
                func_names = [f.name for f in module.functions]
                summary_parts.append(f"  Functions: {', '.join(func_names)}")

            summary_parts.append("")

        return "\n".join(summary_parts)
