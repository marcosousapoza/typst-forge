from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import cache_root, metadata_root, registry_root
from .git import clone_release, local_version, remote_version
from .manifest import ProjectManifest, load_manifest
from .source import SourceSpec, parse_source, source_label


@dataclass(frozen=True)
class InstallRecord:
    namespace: str
    package: str
    version: str
    source_raw: str
    source_kind: str
    source_location: str
    link_mode: str
    installed_root: str
    installed_at: str

    @property
    def install_path(self) -> Path:
        return Path(self.installed_root)


class LocalSourceRelocationError(FileExistsError):
    def __init__(self, existing: InstallRecord, new_source: Path) -> None:
        self.existing = existing
        self.new_source = new_source
        super().__init__(
            f"{existing.namespace}/{existing.package}/{existing.version} is already "
            f"installed from {existing.source_location}; new source is {new_source}"
        )


def package_registry_path(root: str | None, namespace: str, package_name: str, version: str) -> Path:
    return registry_root(root) / namespace / package_name / version


def metadata_path(root: str | None, namespace: str, package_name: str, version: str) -> Path:
    return metadata_root(root) / namespace / package_name / f"{version}.json"


def install_source(
    source: str | Path,
    namespace: str = "local",
    version: str | None = None,
    link_mode: str = "auto",
    registry_root_override: str | None = None,
    cache_root_override: str | None = None,
    force: bool = False,
) -> InstallRecord:
    spec = _normalize_source(source)
    source_id = source_label(spec)
    install_root, manifest, resolved_version, source_location = _resolve_source(
        spec,
        requested_version=version,
        cache_root_override=cache_root_override,
    )
    target = package_registry_path(registry_root_override, namespace, manifest.name, resolved_version)
    existing = _record_at(
        target,
        namespace,
        manifest.name,
        resolved_version,
        registry_root_override,
    )
    if (
        not force
        and spec.kind == "local"
        and existing is not None
        and existing.source_kind == "local"
        and existing.install_path.is_symlink()
        and not _same_path(existing.source_location, source_location)
    ):
        raise LocalSourceRelocationError(existing, install_root)
    _install_tree(install_root, target, link_mode=link_mode, force=force)
    record = InstallRecord(
        namespace=namespace,
        package=manifest.name,
        version=resolved_version,
        source_raw=source_id,
        source_kind=spec.kind,
        source_location=source_location,
        link_mode=link_mode,
        installed_root=str(target),
        installed_at=datetime.now(timezone.utc).isoformat(),
    )
    _write_record(record, registry_root_override)
    return record


def update_installation(
    target: str | Path,
    namespace: str = "local",
    version: str | None = None,
    link_mode: str | None = None,
    registry_root_override: str | None = None,
    cache_root_override: str | None = None,
) -> list[InstallRecord]:
    records = resolve_records(target, namespace=namespace, version=version, registry_root_override=registry_root_override)
    updated: list[InstallRecord] = []
    for record in records:
        source = _source_from_record(record)
        updated.append(
            install_source(
                source,
                namespace=record.namespace,
                version=record.version,
                link_mode=link_mode or record.link_mode,
                registry_root_override=registry_root_override,
                cache_root_override=cache_root_override,
                force=True,
            )
        )
    return updated


def local_installations(
    source: str | Path,
    version: str | None = None,
    registry_root_override: str | None = None,
) -> list[InstallRecord]:
    source_path = Path(source).expanduser().resolve(strict=False)
    records = _load_records(registry_root_override)
    if not records:
        records = _scan_registry(registry_root_override)
    matching = [
        record
        for record in records
        if record.source_kind == "local"
        and _same_path(record.source_location, source_path)
        and (version is None or record.version == version)
    ]
    return sorted(matching, key=lambda item: (item.namespace, item.package, item.version))


def remove_installation(
    target: str | Path,
    namespace: str = "local",
    version: str | None = None,
    registry_root_override: str | None = None,
) -> list[Path]:
    removed: list[Path] = []
    for record in resolve_records(target, namespace=namespace, version=version, registry_root_override=registry_root_override):
        install_path = record.install_path
        if install_path.is_symlink() or install_path.is_file():
            install_path.unlink()
        elif install_path.exists():
            shutil.rmtree(install_path)
        _remove_record(record, registry_root_override)
        _prune_empty_dirs(install_path.parent)
        removed.append(install_path)
    return removed


def list_installed_packages(registry_root_override: str | None = None) -> list[dict[str, str]]:
    records = _load_records(registry_root_override)
    if not records:
        records = _scan_registry(registry_root_override)
    return [
        {
            "namespace": record.namespace,
            "package": record.package,
            "version": record.version,
            "source": record.source_raw,
            "source_kind": record.source_kind,
            "link_mode": record.link_mode,
            "target": record.installed_root,
        }
        for record in sorted(records, key=lambda item: (item.namespace, item.package, item.version))
    ]


def installation_status(
    target: str | Path,
    namespace: str = "local",
    version: str | None = None,
    registry_root_override: str | None = None,
) -> dict[str, str]:
    records = resolve_records(target, namespace=namespace, version=version, registry_root_override=registry_root_override)
    if not records:
        return {"installed": "no"}
    if len(records) == 1:
        record = records[0]
        return {
            "installed": "yes",
            "namespace": record.namespace,
            "package": record.package,
            "version": record.version,
            "source": record.source_raw,
            "source_kind": record.source_kind,
            "link_mode": record.link_mode,
            "target": record.installed_root,
        }
    return {
        "installed": "yes",
        "count": str(len(records)),
        "packages": ",".join(f"{record.package}:{record.version}" for record in records),
    }


def resolve_records(
    target: str | Path,
    namespace: str = "local",
    version: str | None = None,
    registry_root_override: str | None = None,
) -> list[InstallRecord]:
    try:
        spec = _normalize_source(target)
    except (ValueError, TypeError):
        spec = None

    records = _load_records(registry_root_override)
    if spec is not None:
        source_id = source_label(spec)
        matching = [record for record in records if record.source_raw == source_id]
        if version is not None:
            matching = [record for record in matching if record.version == version]
        return matching

    package_name = str(target)
    matching = [record for record in records if record.namespace == namespace and record.package == package_name]
    if version is not None:
        matching = [record for record in matching if record.version == version]
    if matching:
        return matching

    package_dir = registry_root(registry_root_override) / namespace / package_name
    if package_dir.exists():
        if version is not None:
            child = package_dir / version
            if child.exists() or child.is_symlink():
                return [_record_from_path(child, namespace, package_name)]
        else:
            return [_record_from_path(child, namespace, package_name) for child in package_dir.iterdir() if child.name and not child.name.startswith(".")]
    return []


def _normalize_source(source: str | Path) -> SourceSpec:
    if isinstance(source, Path):
        return parse_source(str(source))
    return parse_source(str(source))


def _resolve_source(
    spec: SourceSpec,
    requested_version: str | None,
    cache_root_override: str | None,
) -> tuple[Path, ProjectManifest, str, str]:
    if spec.kind == "local":
        if spec.path is None:
            raise ValueError("local source is missing a path")
        manifest = load_manifest(spec.path)
        resolved_version = local_version(spec.path, requested_version)
        if requested_version is not None and manifest.version != resolved_version:
            raise ValueError(
                f"manifest version {manifest.version!r} does not match requested version {resolved_version!r}"
            )
        if manifest.version != resolved_version:
            raise ValueError(
                f"manifest version {manifest.version!r} does not match resolved version {resolved_version!r}"
            )
        return spec.path, manifest, resolved_version, str(spec.path)

    if spec.kind == "github":
        remote_url = _github_url(spec)
        release = _resolve_remote_release(remote_url, spec.ref or requested_version)
        checkout = _checkout_cache_path(cache_root_override, spec, release.version)
        clone_release(remote_url, release.ref, checkout)
        manifest = load_manifest(checkout)
        if manifest.version != release.version:
            raise ValueError(
                f"manifest version {manifest.version!r} does not match release {release.version!r}"
            )
        return checkout, manifest, release.version, remote_url

    if spec.kind == "remote":
        if spec.url is None:
            raise ValueError("remote source is missing a url")
        release = _resolve_remote_release(spec.url, requested_version)
        checkout = _checkout_cache_path(cache_root_override, spec, release.version)
        clone_release(spec.url, release.ref, checkout)
        manifest = load_manifest(checkout)
        if manifest.version != release.version:
            raise ValueError(
                f"manifest version {manifest.version!r} does not match release {release.version!r}"
            )
        return checkout, manifest, release.version, spec.url

    raise ValueError(f"unsupported source kind: {spec.kind}")


@dataclass(frozen=True)
class _RemoteRelease:
    ref: str
    version: str


def _resolve_remote_release(remote_url: str, requested_version: str | None) -> _RemoteRelease:
    version = remote_version(remote_url, requested_version)
    return _RemoteRelease(ref=_version_ref(remote_url, version), version=version)


def _version_ref(remote_url: str, version: str) -> str:
    tags = _remote_tag_map(remote_url)
    if version in tags:
        return tags[version]
    prefixed = f"v{version}"
    if prefixed in tags:
        return tags[prefixed]
    raise ValueError(f"version {version!r} is not available on {remote_url!r}")


def _remote_tag_map(remote_url: str) -> dict[str, str]:
    from .git import remote_tags

    tags = remote_tags(remote_url)
    mapping: dict[str, str] = {}
    for tag in tags:
        try:
            mapping.setdefault(tag, tag)
            mapping.setdefault(tag.removeprefix("v"), tag)
        except Exception:
            continue
    return mapping


def _github_url(spec: SourceSpec) -> str:
    if not spec.owner or not spec.repo:
        raise ValueError("github source is missing owner or repo")
    return f"https://github.com/{spec.owner}/{spec.repo}.git"


def _checkout_cache_path(cache_root_override: str | None, spec: SourceSpec, version: str) -> Path:
    root = cache_root(cache_root_override) / "checkouts"
    source_id = spec.owner or spec.url or spec.raw
    safe = source_id.replace(":", "_").replace("/", "_")
    return root / safe / version


def _install_tree(source_root: Path, target: Path, link_mode: str, force: bool) -> None:
    if target.exists() or target.is_symlink():
        if not force:
            if target.is_symlink() and target.resolve(strict=False) == source_root.resolve(strict=False):
                return
            raise FileExistsError(f"registry entry already exists: {target}")
        if target.is_symlink() or target.is_file():
            target.unlink()
        else:
            shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if link_mode == "symlink":
        target.symlink_to(source_root, target_is_directory=True)
        return
    if link_mode == "copy":
        shutil.copytree(source_root, target, symlinks=True, ignore=_copy_ignore)
        return
    try:
        target.symlink_to(source_root, target_is_directory=True)
    except OSError:
        shutil.copytree(source_root, target, symlinks=True, ignore=_copy_ignore)


def _copy_ignore(_: str, names: list[str]) -> set[str]:
    ignored = {".git", "__pycache__", ".typst-forge"}
    return {name for name in names if name in ignored}


def _write_record(record: InstallRecord, registry_root_override: str | None) -> None:
    path = metadata_path(registry_root_override, record.namespace, record.package, record.version)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(record)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _record_at(
    target: Path,
    namespace: str,
    package: str,
    version: str,
    registry_root_override: str | None,
) -> InstallRecord | None:
    for record in _load_records(registry_root_override):
        if (
            record.namespace == namespace
            and record.package == package
            and record.version == version
        ):
            return record
    if target.exists() or target.is_symlink():
        return _record_from_path(target, namespace, package)
    return None


def _same_path(left: str | Path, right: str | Path) -> bool:
    return Path(left).expanduser().resolve(strict=False) == Path(right).expanduser().resolve(
        strict=False
    )


def _remove_record(record: InstallRecord, registry_root_override: str | None) -> None:
    path = metadata_path(registry_root_override, record.namespace, record.package, record.version)
    if path.exists():
        path.unlink()
        _prune_metadata_dirs(path.parent)


def _load_records(registry_root_override: str | None) -> list[InstallRecord]:
    root = metadata_root(registry_root_override)
    if not root.exists():
        return []
    records: list[InstallRecord] = []
    for meta in root.rglob("*.json"):
        try:
            payload = json.loads(meta.read_text(encoding="utf-8"))
            records.append(InstallRecord(**payload))
        except Exception:
            continue
    return records


def _scan_registry(registry_root_override: str | None) -> list[InstallRecord]:
    root = registry_root(registry_root_override)
    if not root.exists():
        return []
    records: list[InstallRecord] = []
    for namespace_dir in root.iterdir():
        if not namespace_dir.is_dir() or namespace_dir.name.startswith("."):
            continue
        for package_dir in namespace_dir.iterdir():
            if not package_dir.is_dir() or package_dir.name.startswith("."):
                continue
            for version_dir in package_dir.iterdir():
                if version_dir.name.startswith("."):
                    continue
                records.append(_record_from_path(version_dir, namespace_dir.name, package_dir.name))
    return records


def _record_from_path(path: Path, namespace: str, package: str) -> InstallRecord:
    if path.is_symlink():
        source_location = str(path.resolve(strict=False))
        source_kind = "local"
    else:
        source_location = str(path)
        source_kind = "copy"
    return InstallRecord(
        namespace=namespace,
        package=package,
        version=path.name,
        source_raw=source_location,
        source_kind=source_kind,
        source_location=source_location,
        link_mode="copy" if source_kind == "copy" else "symlink",
        installed_root=str(path),
        installed_at="",
    )


def _source_from_record(record: InstallRecord) -> str | Path:
    if record.source_kind == "local":
        return Path(record.source_location)
    if record.source_kind in {"github", "remote"}:
        return record.source_raw
    return record.source_location


def _prune_empty_dirs(path: Path) -> None:
    current = path
    while True:
        if current.name in {"packages", ".forge"}:
            break
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def _prune_metadata_dirs(path: Path) -> None:
    current = path
    while True:
        if current.name == ".forge":
            break
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent
