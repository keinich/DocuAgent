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
    ):
        """Initialize the HTML generator.

        Args:
            output_dir: Directory for output files.
            title: Documentation title.
            include_source: Whether to include source code in output.
            custom_css: Optional custom CSS to include.
        """
        self.output_dir = Path(output_dir)
        self.title = title
        self.include_source = include_source
        self.custom_css = custom_css

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
<body>
    <nav class="sidebar">
        <div class="sidebar-header">
            <h1>{{ title }}</h1>
            <div class="search-box">
                <input type="text" id="search-input" placeholder="Search...">
            </div>
        </div>
        <div class="toc">
            <h2>Table of Contents</h2>
            <ul class="toc-list">
            {% for entry in toc_entries %}
                {% if not selections or entry.id not in selections or selections[entry.id].included %}
                <li class="toc-item toc-level-{{ entry.level }}">
                    {% set module_filename = entry.file_path.replace("/", "_").replace("\\\\", "_") %}
                    {% if module_filename.endswith(".py") %}
                        {% set module_filename = module_filename[:-3] %}
                    {% endif %}
                    <a href="modules/{{ module_filename }}.html">{{ entry.title }}</a>
                    {% if entry.children %}
                    <ul class="toc-children">
                        {% for child in entry.children %}
                            {% if not selections or child.id not in selections or selections[child.id].included %}
                            <li class="toc-item toc-level-{{ child.level }}">
                                <a href="modules/{{ module_filename }}.html#{{ child.component_type.value }}-{{ child.title.split('(')[0] }}">
                                    {{ child.title }}
                                </a>
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
        </header>
        <section class="overview">
            <h2>Overview</h2>
            <p>Welcome to the API documentation. Use the table of contents on the left to navigate through the modules, classes, and functions.</p>

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
<body>
    <nav class="sidebar">
        <div class="sidebar-header">
            <a href="../index.html" class="back-link">&larr; Back to Index</a>
            <h2>{{ module.name }}</h2>
        </div>
        <div class="module-toc">
            <h3>Contents</h3>
            <ul>
                {% for cls in classes %}
                <li>
                    <a href="#class-{{ cls.name }}">{{ cls.name }}</a>
                    <ul>
                        {% for method in cls.methods %}
                            {% if method.id in included_ids or not selections %}
                            <li><a href="#method-{{ cls.name }}-{{ method.name }}">{{ method.name }}()</a></li>
                            {% endif %}
                        {% endfor %}
                    </ul>
                </li>
                {% endfor %}
                {% if functions %}
                <li class="functions-header">Functions</li>
                {% for func in functions %}
                <li><a href="#function-{{ func.name }}">{{ func.name }}()</a></li>
                {% endfor %}
                {% endif %}
            </ul>
        </div>
    </nav>
    <main class="content">
        <header class="module-header">
            <h1>{{ module_title }}</h1>
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
                    {% if method.id in included_ids or not selections %}
                    <div class="method" id="method-{{ cls.name }}-{{ method.name }}">
                        <h4 class="method-signature">
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
            <div class="function" id="function-{{ func.name }}">
                <h3 class="function-signature">
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
}
'''

    def _get_default_js(self) -> str:
        """Get default JavaScript for search functionality."""
        return '''// DocuAgent Search Functionality
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
});
'''
