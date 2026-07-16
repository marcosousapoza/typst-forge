from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .git import normalize_version, repo_root, run_git, version_key
from .manifest import ProjectManifest, load_manifest
from .registry import InstallRecord, install_source, local_installations, package_registry_path


STABLE_VERSION = re.compile(r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")
EXACT_VERSION = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
VERSION_LINE = re.compile(r'^(?P<prefix>\s*version\s*=\s*)(?P<quote>["\'])(?P<value>.*?)(?P=quote)(?P<suffix>\s*(?:#.*)?)$')


@dataclass(frozen=True)
class BumpResult:
    project: str
    old_version: str
    new_version: str
    tag: str
    installations: tuple[InstallRecord, ...]


def bump_project(
    project_root: str | Path,
    requested: str,
    registry_root_override: str | None = None,
) -> BumpResult:
    project = Path(project_root).expanduser().resolve()
    manifest = load_manifest(project)
    new_version = next_version(manifest.version, requested)
    tag = f"v{new_version}"
    git_root = repo_root(project)

    _preflight_git(git_root, new_version)
    old_installations = _unique_installations(
        local_installations(
            project,
            version=manifest.version,
            registry_root_override=registry_root_override,
        )
    )
    _preflight_installations(old_installations, project, new_version, registry_root_override)

    changed = [_update_manifest(project / "typst.toml", manifest.version, new_version)]
    template = project / "template" / "main.typ"
    if template.is_file() and _update_self_import(template, manifest, new_version):
        changed.append(template)

    relative_paths = [str(path.relative_to(git_root)) for path in changed]
    run_git(["add", "--", *relative_paths], cwd=git_root)
    run_git(["commit", "-m", f"Release {new_version}"], cwd=git_root)
    run_git(["tag", "-a", tag, "-m", f"Release {new_version}"], cwd=git_root)

    installed: list[InstallRecord] = []
    for record in old_installations:
        installed.append(
            install_source(
                project,
                namespace=record.namespace,
                version=new_version,
                link_mode=record.link_mode,
                registry_root_override=registry_root_override,
            )
        )

    return BumpResult(
        project=manifest.name,
        old_version=manifest.version,
        new_version=new_version,
        tag=tag,
        installations=tuple(installed),
    )


def next_version(current: str, requested: str) -> str:
    current = normalize_version(current)
    if requested in {"major", "minor", "patch"}:
        match = STABLE_VERSION.fullmatch(current)
        if match is None:
            raise ValueError(
                "major/minor/patch bumps require a stable X.Y.Z version; "
                "provide the next version explicitly"
            )
        major, minor, patch = (int(match.group(name)) for name in ("major", "minor", "patch"))
        if requested == "major":
            return f"{major + 1}.0.0"
        if requested == "minor":
            return f"{major}.{minor + 1}.0"
        return f"{major}.{minor}.{patch + 1}"

    new_version = normalize_version(requested)
    if EXACT_VERSION.fullmatch(new_version) is None:
        raise ValueError("explicit versions must use X.Y.Z or X.Y.Z-prerelease")
    if version_key(new_version) <= version_key(current):
        raise ValueError(f"new version {new_version!r} must be greater than {current!r}")
    return new_version


def _preflight_git(git_root: Path, version: str) -> None:
    if run_git(["status", "--porcelain"], cwd=git_root):
        raise ValueError("git working tree must be clean before bumping")
    for tag in (version, f"v{version}"):
        if run_git(["tag", "--list", tag], cwd=git_root):
            raise ValueError(f"git tag {tag!r} already exists")
    run_git(["var", "GIT_AUTHOR_IDENT"], cwd=git_root)
    run_git(["var", "GIT_COMMITTER_IDENT"], cwd=git_root)


def _unique_installations(records: list[InstallRecord]) -> list[InstallRecord]:
    by_namespace: dict[str, InstallRecord] = {}
    for record in records:
        by_namespace.setdefault(record.namespace, record)
    return list(by_namespace.values())


def _preflight_installations(
    records: list[InstallRecord],
    project: Path,
    new_version: str,
    registry_root_override: str | None,
) -> None:
    for record in records:
        target = package_registry_path(
            registry_root_override,
            record.namespace,
            record.package,
            new_version,
        )
        if target.exists() or target.is_symlink():
            if not target.is_symlink() or target.resolve(strict=False) != project:
                raise FileExistsError(f"new registry entry already exists: {target}")


def _update_manifest(path: Path, old_version: str, new_version: str) -> Path:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    in_package = False
    replaced = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_package = stripped == "[package]"
            continue
        if not in_package:
            continue
        ending = "\n" if line.endswith("\n") else ""
        content = line[:-1] if ending else line
        match = VERSION_LINE.fullmatch(content)
        if match is None:
            continue
        if normalize_version(match.group("value")) != old_version:
            raise ValueError("typst.toml version changed while preparing the bump")
        lines[index] = (
            f'{match.group("prefix")}{match.group("quote")}{new_version}'
            f'{match.group("quote")}{match.group("suffix")}{ending}'
        )
        replaced = True
        break
    if not replaced:
        raise ValueError("typst.toml [package] table has no version field")
    path.write_text("".join(lines), encoding="utf-8")
    return path


def _update_self_import(path: Path, manifest: ProjectManifest, new_version: str) -> bool:
    namespace = _manifest_namespace(manifest)
    old = f"@{namespace}/{manifest.name}:{manifest.version}"
    new = f"@{namespace}/{manifest.name}:{new_version}"
    content = path.read_text(encoding="utf-8")
    updated = re.sub(rf"{re.escape(old)}(?![0-9A-Za-z.-])", new, content)
    if updated == content:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def _manifest_namespace(manifest: ProjectManifest) -> str:
    tool = manifest.raw.get("tool")
    if isinstance(tool, dict):
        forge = tool.get("typst_forge")
        if isinstance(forge, dict):
            namespace = forge.get("namespace")
            if isinstance(namespace, str) and namespace:
                return namespace
    return "local"
