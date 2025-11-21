# DocuAgent

AI-powered documentation generator for git repositories. DocuAgent analyzes your codebase, extracts public API components, generates intelligent descriptions using AI, and creates beautiful static HTML documentation.

## Features

- **Intelligent API Extraction**: Automatically identifies and extracts public classes, methods, functions, and properties from your Python codebase
- **AI-Powered Descriptions**: Uses Claude AI to generate clear, comprehensive documentation for each component
- **Structured Table of Contents**: Creates a hierarchical TOC that can be customized
- **User Selection Persistence**: Choose which components to include in documentation, with selections saved for future regeneration
- **Static HTML Output**: Generates clean, searchable static HTML documentation with dark mode support
- **Source Code Integration**: Optionally includes source code in documentation

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd DocuAgent

# Install the package
pip install -e .

# Or install with development dependencies
pip install -e ".[dev]"
```

## Quick Start

1. **Set up your API key** (required for AI descriptions):
   ```bash
   export ANTHROPIC_API_KEY="your-api-key"
   ```

2. **Generate documentation** for a repository:
   ```bash
   docuagent generate /path/to/your/repo
   ```

3. **View the documentation**:
   Open `docs/index.html` in your browser.

## Commands

### `generate` - Generate Documentation

```bash
docuagent generate [REPO_PATH] [OPTIONS]

Options:
  -o, --output PATH      Output directory (default: docs)
  -t, --title TEXT       Documentation title
  --include-private      Include private members (_prefixed)
  --include-source       Include source code in output (default: true)
  --no-ai                Skip AI description generation
  --use-selections       Use existing selections from .docuagent/
```

**Examples:**
```bash
# Generate docs for current directory
docuagent generate

# Generate with custom output directory and title
docuagent generate ./my-project -o ./documentation -t "My Project API"

# Generate without AI (uses cached descriptions if available)
docuagent generate --no-ai

# Regenerate using previous selections
docuagent generate --use-selections
```

### `analyze` - Analyze Repository Structure

```bash
docuagent analyze [REPO_PATH] [OPTIONS]

Options:
  --include-private      Include private members
```

Displays the repository structure as a tree without generating documentation.

### `toc` - Display Table of Contents

```bash
docuagent toc [REPO_PATH] [OPTIONS]

Options:
  -f, --format [tree|json|flat]  Output format (default: tree)
```

Shows the documentation structure that would be generated.

### `select` - Interactive Selection

```bash
docuagent select [REPO_PATH]
```

Opens an interactive selector to choose which components to include or exclude from documentation. Selections are persisted to `.docuagent/selections.yaml`.

**Interactive Commands:**
- `toggle <id/number>` - Toggle component inclusion
- `include <id/number>` - Include a component
- `exclude <id/number>` - Exclude a component
- `list` - Show all components with current status
- `save` - Save selections
- `quit` - Exit (auto-saves)

### `export-selections` - Export Selections

```bash
docuagent export-selections [REPO_PATH] [-o OUTPUT]
```

Export your selections to a file for sharing or backup.

### `import-selections` - Import Selections

```bash
docuagent import-selections [REPO_PATH] INPUT_FILE
```

Import selections from a previously exported file.

### `clear` - Clear Cached Data

```bash
docuagent clear [REPO_PATH]
```

Clears all cached data including selections and AI-generated descriptions.

## Workflow

### Basic Workflow

1. **Analyze** your repository to understand its structure:
   ```bash
   docuagent analyze ./my-repo
   ```

2. **Generate** documentation:
   ```bash
   docuagent generate ./my-repo -o ./docs
   ```

3. **View** the generated documentation in `./docs/index.html`

### Customization Workflow

1. **Generate** initial documentation:
   ```bash
   docuagent generate ./my-repo
   ```

2. **Select** which components to include:
   ```bash
   docuagent select ./my-repo
   # Interactively exclude components you don't want
   ```

3. **Regenerate** with your selections:
   ```bash
   docuagent generate ./my-repo --use-selections
   ```

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key (required for AI features) |

### Persisted Data

DocuAgent stores its configuration in `.docuagent/` directory:

- `selections.yaml` - User selections for component inclusion
- `descriptions.json` - Cached AI-generated descriptions
- `state.json` - Generation state

Add `.docuagent/` to your `.gitignore` if you don't want to share these files.

## Output Structure

Generated documentation follows this structure:

```
docs/
├── index.html          # Main entry page with TOC
├── style.css           # Stylesheet (supports dark mode)
├── script.js           # Search functionality
├── search.json         # Search index
└── modules/            # Individual module pages
    ├── module1.html
    ├── module2.html
    └── ...
```

## API Usage

DocuAgent can also be used as a library:

```python
from docuagent.analyzer import APIExtractor
from docuagent.toc import TOCGenerator, SelectionManager
from docuagent.agent import DocumentationAgent
from docuagent.html import HTMLGenerator

# Extract API components
extractor = APIExtractor("./my-repo")
modules = extractor.extract()

# Generate TOC
toc_gen = TOCGenerator()
toc_entries = toc_gen.generate(modules)

# Generate AI descriptions
agent = DocumentationAgent()
descriptions = {}
for module in modules:
    descriptions.update(agent.generate_module_documentation(module))

# Generate HTML
html_gen = HTMLGenerator(output_dir="./docs", title="My API Docs")
html_gen.generate(
    modules=modules,
    toc_entries=toc_entries,
    descriptions=descriptions,
)
```

## Supported Languages

Currently, DocuAgent supports:
- **Python** (full support)

Future language support planned:
- TypeScript/JavaScript
- Go
- Rust

## Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.

## License

MIT License - see LICENSE file for details.
