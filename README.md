# Typst Forge

Typst Forge is a small local manager for Typst packages and templates.

It can:

- scaffold a new Typst repo with `git`, `typst.toml`, `src`, and `template/` when needed
- install local development repos into Typst's package directory
- install release repos from GitHub or any git URL
- manage installed packages/templates with versioned registry entries
- fall back between symlink and copy modes for platform-friendly installs

## Install

Run the CLI from a checkout with `uv`:

```bash
uv run typst-forge --help
```

To run the published package from PyPI, use `uvx`:

```bash
uvx typst-forge --help
```

To run directly from this checkout without installing it, use `uvx`:

```bash
uvx --from . typst-forge --help
```

You can also run it directly from GitHub:

```bash
uvx --from git+https://github.com/marcosousapoza/typst-forge typst-forge --help
```

## Commands

```bash
typst-forge init my-template --kind template --namespace local --version 0.1.0
typst-forge init my-package --kind package --version 0.1.0
typst-forge init . --kind template --namespace local --version 0.1.0
typst-forge install ./my-package --link-mode copy
typst-forge install github:owner/repo@v1.2.3
typst-forge list
typst-forge status my-package
typst-forge update my-package
typst-forge remove my-package
```

## Versioning

- local repos use the `typst.toml` package version unless a matching git tag is present at `HEAD`
- GitHub and other git URLs install from release tags
- tags can be written as `v1.2.3` or `1.2.3`; the stored Typst version is normalized to `1.2.3`
- installed entries live under `~/.local/share/typst/packages/<namespace>/<package>/<version>`
- template scaffolds import their library through Typst’s package path, for example `@local/<package>:<version>`

## Tests

Run the in-repo test suite with:

```bash
uv run python -m unittest discover -s tests -v
```

## Publishing

The GitHub Actions workflow in [.github/workflows/publish.yml](./.github/workflows/publish.yml)
publishes tagged releases to PyPI with trusted publishing.

Create and push a version tag like `v0.1.0` to trigger it.
