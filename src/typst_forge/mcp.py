from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from mcp.server import MCPServer

from .bump import bump_project
from .registry import (
    install_source,
    installation_status,
    list_installed_packages,
    remove_installation,
    update_installation,
)
from .scaffold import scaffold_project


mcp = MCPServer(
    "typst-forge",
    description="Create and manage local Typst packages and templates.",
)


@mcp.tool()
def init_project(
    target: str = ".",
    kind: str = "package",
    namespace: str = "local",
    version: str = "0.1.0",
) -> dict[str, str]:
    """Create a Typst package or template and initialize its Git repository."""
    if kind not in {"package", "template"}:
        raise ValueError("kind must be 'package' or 'template'")
    root = Path(target).expanduser().resolve()
    name = root.name.replace("_", "-")
    scaffold_project(root, kind, name, version, namespace=namespace)
    return {"kind": kind, "name": name, "path": str(root)}


@mcp.tool()
def install(
    source: str,
    namespace: str = "local",
    version: str | None = None,
    link_mode: str = "auto",
    registry_root: str | None = None,
    cache_root: str | None = None,
    force: bool = False,
) -> dict[str, str]:
    """Install a local path, GitHub source, or Git URL into Typst's registry."""
    record = install_source(
        source,
        namespace=namespace,
        version=version,
        link_mode=link_mode,
        registry_root_override=registry_root,
        cache_root_override=cache_root,
        force=force,
    )
    return asdict(record)


@mcp.tool()
def update(
    target: str,
    namespace: str = "local",
    version: str | None = None,
    link_mode: str | None = None,
    registry_root: str | None = None,
    cache_root: str | None = None,
) -> list[dict[str, str]]:
    """Reinstall matching installed packages from their recorded sources."""
    return [
        asdict(record)
        for record in update_installation(
            target,
            namespace=namespace,
            version=version,
            link_mode=link_mode,
            registry_root_override=registry_root,
            cache_root_override=cache_root,
        )
    ]


@mcp.tool()
def remove(
    target: str,
    namespace: str = "local",
    version: str | None = None,
    registry_root: str | None = None,
) -> list[str]:
    """Remove matching packages from Typst's registry."""
    return [
        str(path)
        for path in remove_installation(
            target,
            namespace=namespace,
            version=version,
            registry_root_override=registry_root,
        )
    ]


@mcp.tool(name="list")
def list_packages(registry_root: str | None = None) -> list[dict[str, str]]:
    """List installed Typst packages and templates."""
    return list_installed_packages(registry_root)


@mcp.tool()
def status(
    target: str,
    namespace: str = "local",
    version: str | None = None,
    registry_root: str | None = None,
) -> dict[str, str]:
    """Show installation status for a package or source."""
    return installation_status(
        target,
        namespace=namespace,
        version=version,
        registry_root_override=registry_root,
    )


@mcp.tool()
def bump(version: str, project_root: str = ".", registry_root: str | None = None) -> dict[str, object]:
    """Bump a project version, commit it, tag it, and refresh local installs."""
    result = bump_project(project_root, version, registry_root_override=registry_root)
    return {
        "project": result.project,
        "old_version": result.old_version,
        "new_version": result.new_version,
        "tag": result.tag,
        "installations": [asdict(record) for record in result.installations],
    }


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run("stdio")


if __name__ == "__main__":
    main()
