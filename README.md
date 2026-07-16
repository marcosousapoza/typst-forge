# Typst Forge

Typst Forge is a small local manager for Typst packages and templates.

It can:

- scaffold a new Typst repo with `git`, `typst.toml`, `src`, and `template/` when needed
- install local development repos into Typst's package directory
- install release repos from GitHub or any git URL
- manage installed packages/templates with versioned registry entries
- fall back between symlink and copy modes for platform-friendly installs
- bump a project's Typst version and create a matching Git commit and tag

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
typst-forge bump patch
typst-forge bump minor
typst-forge bump major
typst-forge bump 2.0.0
```

`init` creates a `.gitignore` and initializes the project as a Git repository.

### Moving a local project

If a symlinked local project moves, install it again from its new location:

```bash
typst-forge install /new/path/to/my-package
```

In a terminal, Typst Forge shows the old and new source paths and asks before
repointing the existing registry symlink. In scripts and CI, pass `--force` to
confirm the relocation explicitly:

```bash
typst-forge install /new/path/to/my-package --force
```

## Versioning

- local repos use the `typst.toml` package version unless a matching git tag is present at `HEAD`
- GitHub and other git URLs install from release tags
- tags can be written as `v1.2.3` or `1.2.3`; the stored Typst version is normalized to `1.2.3`
- installed entries live under `~/.local/share/typst/packages/<namespace>/<package>/<version>`

### Bumping a project

Run `bump` from a clean Typst project repository. It updates the `[package]`
version in `typst.toml`, updates an exact scaffolded self-import when present,
creates a `Release X.Y.Z` commit, and adds an annotated `vX.Y.Z` tag.

Existing local installations of the old project version are preserved. Typst
Forge adds the new version beside them using the same namespace and link mode.
An uninstalled project is not installed as a side effect.

`bump` only changes the local Git repository. To publish the commit and tag to
either GitHub or GitLab, push them with ordinary Git commands:

```bash
git push origin HEAD
git push origin v1.2.3
```

On GitHub, an [Actions workflow](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
can select pushed version tags with `on.push.tags`. On GitLab, a
[tag pipeline](https://docs.gitlab.com/user/project/repository/tags/) can select
them with `if: $CI_COMMIT_TAG`. A hosted GitHub or GitLab Release is separate
from the Git tag and can be created by CI or through the provider UI if desired.

## Tests

Run the in-repo test suite with:

```bash
uv run python -m unittest discover -s tests -v
```

## Publishing

The GitHub Actions workflow in [.github/workflows/publish.yml](./.github/workflows/publish.yml)
publishes tagged releases to PyPI with trusted publishing.

Create and push a version tag like `v0.1.0` to trigger it.
