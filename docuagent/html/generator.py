"""HTML generator for creating static documentation files."""

import html
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from docuagent.models.components import (
    ClassComponent,
    ComponentType,
    FunctionComponent,
    MethodComponent,
    ModuleComponent,
    PropertyComponent,
    TOCEntry,
    TOCSelection,
)


class HTMLGenerator:
    """Generate static HTML documentation from API components."""

    def __init__(
        self,
        output_dir: str | Path = "docs",
        title: str = "API Documentation",
        include_source: bool = True,
        custom_css: str | None = None,
        editable: bool = False,
    ):
        """Initialize the HTML generator.

        Args:
            output_dir: Directory for output files.
            title: Documentation title.
            include_source: Whether to include source code in output.
            custom_css: Optional custom CSS to include.
            editable: Whether to generate editable documentation with checkboxes.
        """
        self.output_dir = Path(output_dir)
        self.title = title
        self.include_source = include_source
        self.custom_css = custom_css
        self.editable = editable

        # Set up Jinja2 environment with built-in templates
        self.env = Environment(
            loader=FileSystemLoader(Path(__file__).parent / "templates"),
            autoescape=select_autoescape(["html", "xml"]),
        )

        # Register custom filters
        self.env.filters["escape_html"] = html.escape
        self.env.filters["format_type"] = self._format_type

    def generate(
        self,
        modules: list[ModuleComponent],
        toc_entries: list[TOCEntry],
        descriptions: dict[str, str],
        selections: dict[str, TOCSelection] | None = None,
    ) -> Path:
        """Generate complete HTML documentation.

        Args:
            modules: List of module components to document.
            toc_entries: Table of contents entries.
            descriptions: AI-generated descriptions by component ID.
            selections: User selections for what to include.

        Returns:
            Path to the generated documentation root.
        """
        self._ensure_output_dir()
        self._copy_static_assets()

        # Build lookup dictionaries
        components_by_id = self._build_component_lookup(modules)
        selections = selections or {}

        # Filter based on selections
        included_ids = {
            entry_id
            for entry_id, sel in selections.items()
            if sel.included
        } if selections else set(components_by_id.keys())

        # Generate index page
        self._generate_index(toc_entries, selections)

        # Generate module pages
        for module in modules:
            if module.id in included_ids or not selections:
                self._generate_module_page(
                    module,
                    descriptions,
                    selections,
                    included_ids,
                )

        # Generate search index
        self._generate_search_index(modules, descriptions, included_ids)

        return self.output_dir

    def _ensure_output_dir(self) -> None:
        """Ensure output directory exists and is clean."""
        if self.output_dir.exists():
            # Don't remove if it has non-doc files
            for item in self.output_dir.iterdir():
                if item.name not in ("index.html", "search.json", "style.css", "script.js", "modules"):
                    continue
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "modules").mkdir(exist_ok=True)

    def _copy_static_assets(self) -> None:
        """Copy static assets (CSS, JS) to output directory."""
        # Write default CSS
        css_content = self._get_default_css()
        if self.custom_css:
            css_content += f"\n\n/* Custom CSS */\n{self.custom_css}"

        (self.output_dir / "style.css").write_text(css_content)
        (self.output_dir / "script.js").write_text(self._get_default_js())

    def _generate_index(
        self,
        toc_entries: list[TOCEntry],
        selections: dict[str, TOCSelection],
    ) -> None:
        """Generate the index/landing page."""
        template = self._get_index_template()

        html_content = template.render(
            title=self.title,
            toc_entries=toc_entries,
            selections=selections,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            editable=self.editable,
        )

        (self.output_dir / "index.html").write_text(html_content)

    def _generate_module_page(
        self,
        module: ModuleComponent,
        descriptions: dict[str, str],
        selections: dict[str, TOCSelection],
        included_ids: set[str],
    ) -> None:
        """Generate documentation page for a module."""
        template = self._get_module_template()

        # Filter module contents based on selections
        filtered_classes = [
            cls for cls in module.classes
            if cls.id in included_ids or not selections
        ]
        filtered_functions = [
            func for func in module.functions
            if func.id in included_ids or not selections
        ]

        # Get custom titles/descriptions from selections
        def get_display_info(component_id: str, default_title: str, default_desc: str | None):
            if component_id in selections:
                sel = selections[component_id]
                title = sel.custom_title or default_title
                desc = sel.custom_description or descriptions.get(component_id, default_desc)
            else:
                title = default_title
                desc = descriptions.get(component_id, default_desc)
            return title, desc

        # Build module context
        module_title, module_desc = get_display_info(
            module.id, module.name, module.docstring
        )

        html_content = template.render(
            title=self.title,
            module=module,
            module_title=module_title,
            module_description=module_desc or descriptions.get(module.id, ""),
            classes=filtered_classes,
            functions=filtered_functions,
            descriptions=descriptions,
            selections=selections,
            included_ids=included_ids,
            include_source=self.include_source,
            get_display_info=get_display_info,
            editable=self.editable,
        )

        # Create module filename from path
        module_filename = module.file_path.replace("/", "_").replace("\\", "_")
        if module_filename.endswith(".py"):
            module_filename = module_filename[:-3]

        output_path = self.output_dir / "modules" / f"{module_filename}.html"
        output_path.write_text(html_content)

    def _generate_search_index(
        self,
        modules: list[ModuleComponent],
        descriptions: dict[str, str],
        included_ids: set[str],
    ) -> None:
        """Generate search index JSON file."""
        import json

        search_data = []

        for module in modules:
            if module.id not in included_ids:
                continue

            module_filename = module.file_path.replace("/", "_").replace("\\", "_")
            if module_filename.endswith(".py"):
                module_filename = module_filename[:-3]

            # Add module entry
            search_data.append({
                "type": "module",
                "name": module.name,
                "path": module.file_path,
                "description": descriptions.get(module.id, module.docstring or ""),
                "url": f"modules/{module_filename}.html",
            })

            # Add class entries
            for cls in module.classes:
                if cls.id in included_ids:
                    search_data.append({
                        "type": "class",
                        "name": cls.name,
                        "path": f"{module.file_path}:{cls.name}",
                        "description": descriptions.get(cls.id, cls.docstring or ""),
                        "url": f"modules/{module_filename}.html#class-{cls.name}",
                    })

                    # Add method entries
                    for method in cls.methods:
                        if method.id in included_ids:
                            search_data.append({
                                "type": "method",
                                "name": f"{cls.name}.{method.name}",
                                "path": f"{module.file_path}:{cls.name}.{method.name}",
                                "description": descriptions.get(method.id, method.docstring or ""),
                                "url": f"modules/{module_filename}.html#method-{cls.name}-{method.name}",
                            })

            # Add function entries
            for func in module.functions:
                if func.id in included_ids:
                    search_data.append({
                        "type": "function",
                        "name": func.name,
                        "path": f"{module.file_path}:{func.name}",
                        "description": descriptions.get(func.id, func.docstring or ""),
                        "url": f"modules/{module_filename}.html#function-{func.name}",
                    })

        with (self.output_dir / "search.json").open("w") as f:
            json.dump(search_data, f, indent=2)

    def _build_component_lookup(
        self, modules: list[ModuleComponent]
    ) -> dict[str, Any]:
        """Build a lookup dictionary of all components by ID."""
        lookup = {}

        for module in modules:
            lookup[module.id] = module

            for cls in module.classes:
                lookup[cls.id] = cls
                for method in cls.methods:
                    lookup[method.id] = method
                for prop in cls.properties:
                    lookup[prop.id] = prop

            for func in module.functions:
                lookup[func.id] = func

            for const in module.constants:
                lookup[const.id] = const

        return lookup

    def _format_type(self, type_str: str | None) -> str:
        """Format a type annotation for display."""
        if not type_str:
            return ""
        # Add syntax highlighting hints
        return type_str

    def _get_index_template(self):
        """Get or create the index page template."""
        template_str = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    <link rel="stylesheet" href="style.css">
</head>
<body{% if editable %} class="editable-mode"{% endif %}>
    <nav class="sidebar">
        <div class="sidebar-header">
            <h1>{{ title }}</h1>
            <div class="search-box">
                <input type="text" id="search-input" placeholder="Search...">
            </div>
        </div>
        {% if editable %}
        <div class="edit-controls">
            <h3>Selection Controls</h3>
            <div class="edit-buttons">
                <button id="select-all-btn" class="edit-btn">Select All</button>
                <button id="deselect-all-btn" class="edit-btn">Deselect All</button>
            </div>
            <div class="edit-buttons">
                <button id="export-selections-btn" class="edit-btn primary">Export Selections</button>
            </div>
            <p class="edit-hint">Check/uncheck components to include in documentation, then export selections.</p>
        </div>
        {% endif %}
        <div class="toc">
            <h2>Table of Contents</h2>
            <ul class="toc-list">
            {% for entry in toc_entries %}
                {% set entry_included = not selections or entry.id not in selections or selections[entry.id].included %}
                {% if editable or entry_included %}
                <li class="toc-item toc-level-{{ entry.level }}{% if not entry_included %} excluded{% endif %}">
                    {% set module_filename = entry.file_path.replace("/", "_").replace("\\\\", "_") %}
                    {% if module_filename.endswith(".py") %}
                        {% set module_filename = module_filename[:-3] %}
                    {% endif %}
                    {% if editable %}
                    <label class="toc-checkbox-label">
                        <input type="checkbox" class="component-checkbox"
                               data-id="{{ entry.id }}"
                               data-type="{{ entry.component_type.value }}"
                               data-title="{{ entry.title }}"
                               {% if entry_included %}checked{% endif %}>
                        <a href="modules/{{ module_filename }}.html">{{ entry.title }}</a>
                    </label>
                    {% else %}
                    <a href="modules/{{ module_filename }}.html">{{ entry.title }}</a>
                    {% endif %}
                    {% if entry.children %}
                    <ul class="toc-children">
                        {% for child in entry.children %}
                            {% set child_included = not selections or child.id not in selections or selections[child.id].included %}
                            {% if editable or child_included %}
                            <li class="toc-item toc-level-{{ child.level }}{% if not child_included %} excluded{% endif %}">
                                {% if editable %}
                                <label class="toc-checkbox-label">
                                    <input type="checkbox" class="component-checkbox"
                                           data-id="{{ child.id }}"
                                           data-type="{{ child.component_type.value }}"
                                           data-title="{{ child.title }}"
                                           {% if child_included %}checked{% endif %}>
                                    <a href="modules/{{ module_filename }}.html#{{ child.component_type.value }}-{{ child.title.split('(')[0] }}">
                                        {{ child.title }}
                                    </a>
                                </label>
                                {% else %}
                                <a href="modules/{{ module_filename }}.html#{{ child.component_type.value }}-{{ child.title.split('(')[0] }}">
                                    {{ child.title }}
                                </a>
                                {% endif %}
                            </li>
                            {% endif %}
                        {% endfor %}
                    </ul>
                    {% endif %}
                </li>
                {% endif %}
            {% endfor %}
            </ul>
        </div>
    </nav>
    <main class="content">
        <header>
            <h1>{{ title }}</h1>
            <p class="generated-at">Generated on {{ generated_at }}</p>
            {% if editable %}
            <p class="edit-mode-badge">Editable Mode</p>
            {% endif %}
        </header>
        <section class="overview">
            <h2>Overview</h2>
            {% if editable %}
            <p>This documentation is in <strong>editable mode</strong>. Use the checkboxes in the sidebar and on each component to select which items to include in the final documentation.</p>
            <p>When you're done, click <strong>Export Selections</strong> to download a <code>selections.yaml</code> file. Then regenerate documentation using:</p>
            <pre><code>docuagent generate --use-selections</code></pre>
            {% else %}
            <p>Welcome to the API documentation. Use the table of contents on the left to navigate through the modules, classes, and functions.</p>
            {% endif %}

            <h3>Quick Stats</h3>
            <ul>
                <li><strong>Modules:</strong> {{ toc_entries|length }}</li>
            </ul>
        </section>
        <div id="search-results" class="search-results" style="display: none;">
            <h2>Search Results</h2>
            <ul id="results-list"></ul>
        </div>
    </main>
    <script src="script.js"></script>
</body>
</html>'''
        return self.env.from_string(template_str)

    def _get_module_template(self):
        """Get or create the module page template."""
        template_str = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ module.name }} - {{ title }}</title>
    <link rel="stylesheet" href="../style.css">
</head>
<body{% if editable %} class="editable-mode"{% endif %}>
    <nav class="sidebar">
        <div class="sidebar-header">
            <a href="../index.html" class="back-link">&larr; Back to Index</a>
            <h2>{{ module.name }}</h2>
        </div>
        {% if editable %}
        <div class="edit-controls">
            <h3>Selection Controls</h3>
            <div class="edit-buttons">
                <button id="select-all-btn" class="edit-btn">Select All</button>
                <button id="deselect-all-btn" class="edit-btn">Deselect All</button>
            </div>
            <div class="edit-buttons">
                <button id="export-selections-btn" class="edit-btn primary">Export Selections</button>
            </div>
        </div>
        {% endif %}
        <div class="module-toc">
            <h3>Contents</h3>
            <ul>
                {% for cls in classes %}
                <li>
                    {% if editable %}
                    <label class="toc-checkbox-label">
                        <input type="checkbox" class="component-checkbox"
                               data-id="{{ cls.id }}"
                               data-type="class"
                               data-title="{{ cls.name }}"
                               {% if cls.id in included_ids or not selections %}checked{% endif %}>
                        <a href="#class-{{ cls.name }}">{{ cls.name }}</a>
                    </label>
                    {% else %}
                    <a href="#class-{{ cls.name }}">{{ cls.name }}</a>
                    {% endif %}
                    <ul>
                        {% for method in cls.methods %}
                            {% if editable or method.id in included_ids or not selections %}
                            <li>
                                {% if editable %}
                                <label class="toc-checkbox-label">
                                    <input type="checkbox" class="component-checkbox"
                                           data-id="{{ method.id }}"
                                           data-type="method"
                                           data-title="{{ cls.name }}.{{ method.name }}"
                                           {% if method.id in included_ids or not selections %}checked{% endif %}>
                                    <a href="#method-{{ cls.name }}-{{ method.name }}">{{ method.name }}()</a>
                                </label>
                                {% else %}
                                <a href="#method-{{ cls.name }}-{{ method.name }}">{{ method.name }}()</a>
                                {% endif %}
                            </li>
                            {% endif %}
                        {% endfor %}
                    </ul>
                </li>
                {% endfor %}
                {% if functions %}
                <li class="functions-header">Functions</li>
                {% for func in functions %}
                <li>
                    {% if editable %}
                    <label class="toc-checkbox-label">
                        <input type="checkbox" class="component-checkbox"
                               data-id="{{ func.id }}"
                               data-type="function"
                               data-title="{{ func.name }}"
                               {% if func.id in included_ids or not selections %}checked{% endif %}>
                        <a href="#function-{{ func.name }}">{{ func.name }}()</a>
                    </label>
                    {% else %}
                    <a href="#function-{{ func.name }}">{{ func.name }}()</a>
                    {% endif %}
                </li>
                {% endfor %}
                {% endif %}
            </ul>
        </div>
    </nav>
    <main class="content">
        <header class="module-header">
            <h1>
                {% if editable %}
                <label class="header-checkbox-label">
                    <input type="checkbox" class="component-checkbox"
                           data-id="{{ module.id }}"
                           data-type="module"
                           data-title="{{ module.name }}"
                           {% if module.id in included_ids or not selections %}checked{% endif %}>
                    {{ module_title }}
                </label>
                {% else %}
                {{ module_title }}
                {% endif %}
            </h1>
            <p class="file-path">{{ module.file_path }}</p>
        </header>

        <section class="module-description">
            {% if module_description %}
            <p>{{ module_description }}</p>
            {% endif %}
            {% if module.docstring %}
            <div class="docstring">
                <pre>{{ module.docstring }}</pre>
            </div>
            {% endif %}
        </section>

        {% for cls in classes %}
        <section class="class-section" id="class-{{ cls.name }}">
            <h2 class="class-title">
                {% if editable %}
                <label class="component-checkbox-label">
                    <input type="checkbox" class="component-checkbox"
                           data-id="{{ cls.id }}"
                           data-type="class"
                           data-title="{{ cls.name }}"
                           {% if cls.id in included_ids or not selections %}checked{% endif %}>
                </label>
                {% endif %}
                <span class="keyword">class</span> {{ cls.name }}
                {% if cls.base_classes %}
                <span class="bases">({{ cls.base_classes | join(", ") }})</span>
                {% endif %}
            </h2>

            {% set cls_title, cls_desc = get_display_info(cls.id, cls.name, cls.docstring) %}
            {% if cls_desc %}
            <div class="description">{{ cls_desc }}</div>
            {% endif %}

            {% if cls.docstring %}
            <div class="docstring">
                <pre>{{ cls.docstring }}</pre>
            </div>
            {% endif %}

            {% if cls.class_variables %}
            <div class="class-variables">
                <h3>Class Variables</h3>
                <table class="params-table">
                    <thead>
                        <tr><th>Name</th><th>Type</th><th>Default</th></tr>
                    </thead>
                    <tbody>
                    {% for var in cls.class_variables %}
                        <tr>
                            <td><code>{{ var.name }}</code></td>
                            <td><code>{{ var.type_annotation or '-' }}</code></td>
                            <td><code>{{ var.default_value or '-' }}</code></td>
                        </tr>
                    {% endfor %}
                    </tbody>
                </table>
            </div>
            {% endif %}

            <div class="methods">
                <h3>Methods</h3>
                {% for method in cls.methods %}
                    {% if editable or method.id in included_ids or not selections %}
                    <div class="method{% if editable and method.id not in included_ids and selections %} excluded{% endif %}" id="method-{{ cls.name }}-{{ method.name }}">
                        <h4 class="method-signature">
                            {% if editable %}
                            <label class="component-checkbox-label">
                                <input type="checkbox" class="component-checkbox"
                                       data-id="{{ method.id }}"
                                       data-type="method"
                                       data-title="{{ cls.name }}.{{ method.name }}"
                                       {% if method.id in included_ids or not selections %}checked{% endif %}>
                            </label>
                            {% endif %}
                            {% if method.is_static %}<span class="decorator">@staticmethod</span><br>{% endif %}
                            {% if method.is_classmethod %}<span class="decorator">@classmethod</span><br>{% endif %}
                            {% if method.is_async %}<span class="keyword">async </span>{% endif %}
                            <span class="keyword">def</span>
                            <span class="method-name">{{ method.name }}</span>(<span class="params">
                            {%- for param in method.parameters -%}
                                {{ param.name }}
                                {%- if param.type_annotation %}: {{ param.type_annotation }}{% endif -%}
                                {%- if param.default_value %} = {{ param.default_value }}{% endif -%}
                                {%- if not loop.last %}, {% endif -%}
                            {%- endfor -%}
                            </span>)
                            {% if method.return_type %}<span class="return-type"> -&gt; {{ method.return_type }}</span>{% endif %}
                        </h4>

                        {% if descriptions.get(method.id) %}
                        <div class="description">{{ descriptions.get(method.id) }}</div>
                        {% endif %}

                        {% if method.docstring %}
                        <div class="docstring">
                            <pre>{{ method.docstring }}</pre>
                        </div>
                        {% endif %}

                        {% if method.parameters %}
                        <div class="parameters">
                            <h5>Parameters</h5>
                            <table class="params-table">
                                <thead>
                                    <tr><th>Name</th><th>Type</th><th>Default</th></tr>
                                </thead>
                                <tbody>
                                {% for param in method.parameters %}
                                    <tr>
                                        <td><code>{{ param.name }}</code></td>
                                        <td><code>{{ param.type_annotation or 'Any' }}</code></td>
                                        <td>{{ param.default_value or '-' }}</td>
                                    </tr>
                                {% endfor %}
                                </tbody>
                            </table>
                        </div>
                        {% endif %}

                        {% if include_source and method.source_code %}
                        <details class="source-code">
                            <summary>View Source</summary>
                            <pre><code class="language-python">{{ method.source_code | escape_html }}</code></pre>
                        </details>
                        {% endif %}
                    </div>
                    {% endif %}
                {% endfor %}
            </div>
        </section>
        {% endfor %}

        {% if functions %}
        <section class="functions-section">
            <h2>Functions</h2>
            {% for func in functions %}
            <div class="function{% if editable and func.id not in included_ids and selections %} excluded{% endif %}" id="function-{{ func.name }}">
                <h3 class="function-signature">
                    {% if editable %}
                    <label class="component-checkbox-label">
                        <input type="checkbox" class="component-checkbox"
                               data-id="{{ func.id }}"
                               data-type="function"
                               data-title="{{ func.name }}"
                               {% if func.id in included_ids or not selections %}checked{% endif %}>
                    </label>
                    {% endif %}
                    {% if func.is_async %}<span class="keyword">async </span>{% endif %}
                    <span class="keyword">def</span>
                    <span class="function-name">{{ func.name }}</span>(<span class="params">
                    {%- for param in func.parameters -%}
                        {{ param.name }}
                        {%- if param.type_annotation %}: {{ param.type_annotation }}{% endif -%}
                        {%- if param.default_value %} = {{ param.default_value }}{% endif -%}
                        {%- if not loop.last %}, {% endif -%}
                    {%- endfor -%}
                    </span>)
                    {% if func.return_type %}<span class="return-type"> -&gt; {{ func.return_type }}</span>{% endif %}
                </h3>

                {% if descriptions.get(func.id) %}
                <div class="description">{{ descriptions.get(func.id) }}</div>
                {% endif %}

                {% if func.docstring %}
                <div class="docstring">
                    <pre>{{ func.docstring }}</pre>
                </div>
                {% endif %}

                {% if func.parameters %}
                <div class="parameters">
                    <h4>Parameters</h4>
                    <table class="params-table">
                        <thead>
                            <tr><th>Name</th><th>Type</th><th>Default</th></tr>
                        </thead>
                        <tbody>
                        {% for param in func.parameters %}
                            <tr>
                                <td><code>{{ param.name }}</code></td>
                                <td><code>{{ param.type_annotation or 'Any' }}</code></td>
                                <td>{{ param.default_value or '-' }}</td>
                            </tr>
                        {% endfor %}
                        </tbody>
                    </table>
                </div>
                {% endif %}

                {% if include_source and func.source_code %}
                <details class="source-code">
                    <summary>View Source</summary>
                    <pre><code class="language-python">{{ func.source_code | escape_html }}</code></pre>
                </details>
                {% endif %}
            </div>
            {% endfor %}
        </section>
        {% endif %}
    </main>
    <script src="../script.js"></script>
</body>
</html>'''
        return self.env.from_string(template_str)

    def _get_default_css(self) -> str:
        """Get default CSS styles."""
        return '''/* DocuAgent Default Styles */
:root {
    --bg-color: #ffffff;
    --text-color: #333333;
    --sidebar-bg: #f5f5f5;
    --border-color: #e0e0e0;
    --link-color: #0066cc;
    --link-hover: #004499;
    --code-bg: #f8f8f8;
    --keyword-color: #0000ff;
    --string-color: #008000;
    --comment-color: #808080;
    --decorator-color: #aa22ff;
}

@media (prefers-color-scheme: dark) {
    :root {
        --bg-color: #1a1a1a;
        --text-color: #e0e0e0;
        --sidebar-bg: #252525;
        --border-color: #404040;
        --link-color: #66b3ff;
        --link-hover: #99ccff;
        --code-bg: #2d2d2d;
    }
}

* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
    line-height: 1.6;
    color: var(--text-color);
    background: var(--bg-color);
    display: flex;
    min-height: 100vh;
}

/* Sidebar */
.sidebar {
    width: 300px;
    min-width: 300px;
    background: var(--sidebar-bg);
    border-right: 1px solid var(--border-color);
    padding: 20px;
    position: sticky;
    top: 0;
    height: 100vh;
    overflow-y: auto;
}

.sidebar-header h1,
.sidebar-header h2 {
    font-size: 1.25rem;
    margin-bottom: 15px;
}

.back-link {
    display: block;
    margin-bottom: 15px;
    color: var(--link-color);
    text-decoration: none;
}

.back-link:hover {
    color: var(--link-hover);
}

.search-box {
    margin-bottom: 20px;
}

.search-box input {
    width: 100%;
    padding: 8px 12px;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    background: var(--bg-color);
    color: var(--text-color);
}

.toc h2, .toc h3,
.module-toc h3 {
    font-size: 0.9rem;
    text-transform: uppercase;
    color: #666;
    margin-bottom: 10px;
}

.toc-list,
.module-toc ul {
    list-style: none;
}

.toc-list li,
.module-toc li {
    margin-bottom: 5px;
}

.toc-list a,
.module-toc a {
    color: var(--text-color);
    text-decoration: none;
    font-size: 0.9rem;
}

.toc-list a:hover,
.module-toc a:hover {
    color: var(--link-color);
}

.toc-children {
    margin-left: 15px;
    margin-top: 5px;
}

.module-toc ul ul {
    margin-left: 15px;
}

.functions-header {
    font-weight: bold;
    margin-top: 15px !important;
}

/* Main Content */
.content {
    flex: 1;
    padding: 40px;
    max-width: 900px;
}

.content header {
    margin-bottom: 30px;
    padding-bottom: 20px;
    border-bottom: 1px solid var(--border-color);
}

.content h1 {
    font-size: 2rem;
    margin-bottom: 10px;
}

.generated-at,
.file-path {
    color: #666;
    font-size: 0.9rem;
}

/* Sections */
.module-description,
.class-section,
.functions-section,
.function,
.method {
    margin-bottom: 30px;
    padding-bottom: 20px;
    border-bottom: 1px solid var(--border-color);
}

.class-title,
.function-signature,
.method-signature {
    font-family: 'SF Mono', Monaco, 'Courier New', monospace;
    font-size: 1rem;
    background: var(--code-bg);
    padding: 12px 15px;
    border-radius: 4px;
    margin-bottom: 15px;
    overflow-x: auto;
}

.keyword {
    color: var(--keyword-color);
    font-weight: bold;
}

.decorator {
    color: var(--decorator-color);
}

.bases,
.return-type {
    color: #666;
}

.method-name,
.function-name,
.class-title .keyword + span {
    font-weight: bold;
}

/* Description and Docstring */
.description {
    margin-bottom: 15px;
    padding: 10px 15px;
    background: #f0f7ff;
    border-left: 3px solid var(--link-color);
    border-radius: 0 4px 4px 0;
}

@media (prefers-color-scheme: dark) {
    .description {
        background: #1a2a3a;
    }
}

.docstring {
    margin-bottom: 15px;
}

.docstring pre {
    background: var(--code-bg);
    padding: 15px;
    border-radius: 4px;
    overflow-x: auto;
    font-size: 0.85rem;
    white-space: pre-wrap;
}

/* Parameters Table */
.parameters h4,
.parameters h5,
.class-variables h3 {
    font-size: 0.9rem;
    margin-bottom: 10px;
}

.params-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9rem;
}

.params-table th,
.params-table td {
    padding: 8px 12px;
    text-align: left;
    border-bottom: 1px solid var(--border-color);
}

.params-table th {
    background: var(--sidebar-bg);
    font-weight: 600;
}

.params-table code {
    background: var(--code-bg);
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 0.85em;
}

/* Source Code */
.source-code {
    margin-top: 15px;
}

.source-code summary {
    cursor: pointer;
    color: var(--link-color);
    font-size: 0.9rem;
}

.source-code pre {
    background: var(--code-bg);
    padding: 15px;
    border-radius: 4px;
    overflow-x: auto;
    font-size: 0.8rem;
    margin-top: 10px;
}

/* Search Results */
.search-results {
    padding: 20px;
}

.search-results h2 {
    margin-bottom: 15px;
}

#results-list {
    list-style: none;
}

#results-list li {
    padding: 10px;
    border-bottom: 1px solid var(--border-color);
}

#results-list a {
    color: var(--link-color);
    text-decoration: none;
    font-weight: 500;
}

#results-list .result-type {
    font-size: 0.8rem;
    color: #666;
    margin-left: 10px;
}

#results-list .result-desc {
    font-size: 0.9rem;
    color: #666;
    margin-top: 5px;
}

/* ==================== EDITABLE MODE STYLES ==================== */

/* Edit Controls Panel */
.edit-controls {
    background: var(--code-bg);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 15px;
    margin-bottom: 20px;
}

.edit-controls h3 {
    font-size: 0.85rem;
    text-transform: uppercase;
    color: #666;
    margin-bottom: 12px;
}

.edit-buttons {
    display: flex;
    gap: 8px;
    margin-bottom: 10px;
}

.edit-btn {
    flex: 1;
    padding: 8px 12px;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    background: var(--bg-color);
    color: var(--text-color);
    font-size: 0.85rem;
    cursor: pointer;
    transition: all 0.2s ease;
}

.edit-btn:hover {
    background: var(--sidebar-bg);
    border-color: var(--link-color);
}

.edit-btn.primary {
    background: var(--link-color);
    color: white;
    border-color: var(--link-color);
}

.edit-btn.primary:hover {
    background: var(--link-hover);
    border-color: var(--link-hover);
}

.edit-hint {
    font-size: 0.75rem;
    color: #888;
    margin-top: 10px;
    line-height: 1.4;
}

/* Edit Mode Badge */
.edit-mode-badge {
    display: inline-block;
    background: #ff9800;
    color: white;
    padding: 4px 12px;
    border-radius: 4px;
    font-size: 0.8rem;
    font-weight: 600;
    margin-top: 10px;
}

/* Checkbox Labels */
.toc-checkbox-label,
.component-checkbox-label,
.header-checkbox-label {
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
}

.toc-checkbox-label a,
.header-checkbox-label {
    flex: 1;
}

.component-checkbox {
    width: 18px;
    height: 18px;
    cursor: pointer;
    accent-color: var(--link-color);
}

.component-checkbox-label {
    display: inline-flex;
    margin-right: 10px;
}

/* Excluded Items Styling */
.excluded {
    opacity: 0.5;
}

.excluded a {
    text-decoration: line-through;
    color: #999 !important;
}

.toc-item.excluded > .toc-checkbox-label > a,
.toc-item.excluded > a {
    text-decoration: line-through;
    color: #999;
}

.method.excluded,
.function.excluded,
.class-section.excluded {
    background: repeating-linear-gradient(
        45deg,
        transparent,
        transparent 10px,
        rgba(128, 128, 128, 0.05) 10px,
        rgba(128, 128, 128, 0.05) 20px
    );
    border-left: 3px solid #ccc;
    padding-left: 15px;
    margin-left: -18px;
}

/* Header checkbox in module pages */
.header-checkbox-label input {
    margin-right: 10px;
}

/* Editable mode specific overrides */
.editable-mode .class-title,
.editable-mode .method-signature,
.editable-mode .function-signature {
    display: flex;
    align-items: flex-start;
    gap: 10px;
}

.editable-mode .component-checkbox-label {
    flex-shrink: 0;
}

/* Dark mode adjustments for edit mode */
@media (prefers-color-scheme: dark) {
    .edit-mode-badge {
        background: #f57c00;
    }

    .excluded a {
        color: #666 !important;
    }

    .method.excluded,
    .function.excluded,
    .class-section.excluded {
        background: repeating-linear-gradient(
            45deg,
            transparent,
            transparent 10px,
            rgba(128, 128, 128, 0.1) 10px,
            rgba(128, 128, 128, 0.1) 20px
        );
    }
}

/* Responsive */
@media (max-width: 768px) {
    body {
        flex-direction: column;
    }

    .sidebar {
        width: 100%;
        min-width: 100%;
        height: auto;
        position: relative;
    }

    .content {
        padding: 20px;
    }

    .edit-buttons {
        flex-direction: column;
    }
}
'''

    def _get_default_js(self) -> str:
        """Get default JavaScript for search functionality."""
        return '''// DocuAgent Search and Edit Functionality
document.addEventListener('DOMContentLoaded', function() {
    const searchInput = document.getElementById('search-input');
    const searchResults = document.getElementById('search-results');
    const resultsList = document.getElementById('results-list');
    const mainContent = document.querySelector('.content > *:not(#search-results)');

    let searchData = [];

    // Load search index
    fetch(window.location.pathname.includes('/modules/') ? '../search.json' : 'search.json')
        .then(response => response.json())
        .then(data => {
            searchData = data;
        })
        .catch(err => console.log('Search index not available'));

    if (searchInput) {
        searchInput.addEventListener('input', function() {
            const query = this.value.toLowerCase().trim();

            if (query.length < 2) {
                searchResults.style.display = 'none';
                return;
            }

            const results = searchData.filter(item => {
                return item.name.toLowerCase().includes(query) ||
                       item.description.toLowerCase().includes(query) ||
                       item.path.toLowerCase().includes(query);
            }).slice(0, 20);

            if (results.length > 0) {
                resultsList.innerHTML = results.map(item => {
                    const basePath = window.location.pathname.includes('/modules/') ? '../' : '';
                    return `
                        <li>
                            <a href="${basePath}${item.url}">${item.name}</a>
                            <span class="result-type">${item.type}</span>
                            <div class="result-desc">${item.description.substring(0, 100)}...</div>
                        </li>
                    `;
                }).join('');
                searchResults.style.display = 'block';
            } else {
                resultsList.innerHTML = '<li>No results found</li>';
                searchResults.style.display = 'block';
            }
        });
    }

    // ==================== EDITABLE MODE FUNCTIONALITY ====================

    // Check if we're in editable mode
    const isEditableMode = document.body.classList.contains('editable-mode');

    if (isEditableMode) {
        // Storage key for selections (use localStorage to persist across pages)
        const STORAGE_KEY = 'docuagent_selections';

        // Load existing selections from localStorage
        function loadSelections() {
            try {
                const stored = localStorage.getItem(STORAGE_KEY);
                return stored ? JSON.parse(stored) : {};
            } catch (e) {
                console.error('Error loading selections:', e);
                return {};
            }
        }

        // Save selections to localStorage
        function saveSelections(selections) {
            try {
                localStorage.setItem(STORAGE_KEY, JSON.stringify(selections));
            } catch (e) {
                console.error('Error saving selections:', e);
            }
        }

        // Get all selections from the current page
        function getSelectionsFromPage() {
            const selections = loadSelections();
            document.querySelectorAll('.component-checkbox').forEach(checkbox => {
                const id = checkbox.dataset.id;
                if (id) {
                    selections[id] = {
                        included: checkbox.checked,
                        type: checkbox.dataset.type,
                        title: checkbox.dataset.title
                    };
                }
            });
            return selections;
        }

        // Sync checkboxes with stored selections
        function syncCheckboxesWithStorage() {
            const selections = loadSelections();
            document.querySelectorAll('.component-checkbox').forEach(checkbox => {
                const id = checkbox.dataset.id;
                if (id && selections[id] !== undefined) {
                    checkbox.checked = selections[id].included;
                    updateVisualState(checkbox);
                }
            });
        }

        // Update visual state of component based on checkbox
        function updateVisualState(checkbox) {
            const parent = checkbox.closest('.toc-item, .method, .function, .class-section');
            if (parent) {
                if (checkbox.checked) {
                    parent.classList.remove('excluded');
                } else {
                    parent.classList.add('excluded');
                }
            }
        }

        // Handle checkbox changes
        document.querySelectorAll('.component-checkbox').forEach(checkbox => {
            checkbox.addEventListener('change', function() {
                const selections = getSelectionsFromPage();
                saveSelections(selections);
                updateVisualState(this);

                // Sync same component across sidebar and content
                const id = this.dataset.id;
                document.querySelectorAll(`.component-checkbox[data-id="${id}"]`).forEach(cb => {
                    if (cb !== this) {
                        cb.checked = this.checked;
                        updateVisualState(cb);
                    }
                });
            });
        });

        // Sync on page load
        syncCheckboxesWithStorage();

        // Select All button
        const selectAllBtn = document.getElementById('select-all-btn');
        if (selectAllBtn) {
            selectAllBtn.addEventListener('click', function() {
                document.querySelectorAll('.component-checkbox').forEach(checkbox => {
                    checkbox.checked = true;
                    updateVisualState(checkbox);
                });
                const selections = getSelectionsFromPage();
                saveSelections(selections);
            });
        }

        // Deselect All button
        const deselectAllBtn = document.getElementById('deselect-all-btn');
        if (deselectAllBtn) {
            deselectAllBtn.addEventListener('click', function() {
                document.querySelectorAll('.component-checkbox').forEach(checkbox => {
                    checkbox.checked = false;
                    updateVisualState(checkbox);
                });
                const selections = getSelectionsFromPage();
                saveSelections(selections);
            });
        }

        // Export Selections button
        const exportBtn = document.getElementById('export-selections-btn');
        if (exportBtn) {
            exportBtn.addEventListener('click', function() {
                const selections = loadSelections();

                // Convert to YAML format compatible with DocuAgent
                const yamlContent = generateYAML(selections);

                // Create and download file
                const blob = new Blob([yamlContent], { type: 'text/yaml' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'selections.yaml';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);

                // Show confirmation
                alert('Selections exported!\\n\\nTo use these selections:\\n1. Move selections.yaml to your project\\'s .docuagent/ folder\\n2. Run: docuagent generate --use-selections');
            });
        }

        // Generate YAML content from selections
        function generateYAML(selections) {
            const now = new Date().toISOString();
            let yaml = `# DocuAgent Selections\\n`;
            yaml += `# Generated from editable documentation mode\\n`;
            yaml += `# To use: place in .docuagent/selections.yaml and run: docuagent generate --use-selections\\n\\n`;
            yaml += `version: "1.0"\\n`;
            yaml += `updated_at: "${now}"\\n`;
            yaml += `metadata: {}\\n`;
            yaml += `selections:\\n`;

            for (const [id, data] of Object.entries(selections)) {
                yaml += `  ${id}:\\n`;
                yaml += `    included: ${data.included}\\n`;
                yaml += `    custom_title: null\\n`;
                yaml += `    custom_description: null\\n`;
            }

            return yaml;
        }
    }
});
'''
