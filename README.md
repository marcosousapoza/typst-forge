# Typst Forge

Typst Forge is a small local manager for Typst packages and templates.

It can:

- scaffold a new Typst repo with `git`, `typst.toml`, `src`, and `template/` when needed
- install local development repos into Typst's package directory
- install release repos from GitHub or any git URL
- manage installed packages/templates with versioned registry entries
- fall back between symlink and copy modes for platform-friendly installs

## Install

This repo is meant to be run with `uv`:

```bash
uv run typst-forge --help
```

To run it without installing from a checkout, use `uvx`:

```bash
uvx --from . typst-forge --help
```

You can also install directly from GitHub:

```bash
uvx --from git+https://github.com/<owner>/typst-forge typst-forge --help
```

## Commands

```bash
typst-forge init ./my-template --kind template --name my-template --version 0.1.0
typst-forge init ./my-package --kind package --name my-package --version 0.1.0
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

## Tests

Run the in-repo test suite with:

```bash
uv run python -m unittest discover -s tooling/typst_forge/tests -t tooling -v
```
