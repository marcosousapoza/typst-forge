from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from .git import normalize_version


@dataclass(frozen=True)
class ProjectManifest:
    name: str
    version: str
    entrypoint: str
    kind: str
    raw: dict[str, object]


def load_manifest(project_root: Path) -> ProjectManifest:
    path = project_root / "typst.toml"
    if not path.is_file():
        raise FileNotFoundError(f"missing manifest: {path}")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    package = data.get("package")
    if not isinstance(package, dict):
        raise ValueError("typst.toml is missing a [package] table")

    name = _require_string(package, "name")
    version = normalize_version(_require_string(package, "version"))
    entrypoint = _require_string(package, "entrypoint", default="src/lib.typ")

    tool = data.get("tool")
    kind = "package"
    if isinstance(tool, dict):
        forge = tool.get("typst_forge")
        if isinstance(forge, dict):
            maybe_kind = forge.get("kind", "package")
            if isinstance(maybe_kind, str) and maybe_kind:
                kind = maybe_kind
    if entrypoint.startswith("template/"):
        kind = "template"

    return ProjectManifest(name=name, version=version, entrypoint=entrypoint, kind=kind, raw=data)


def _require_string(values: dict[str, object], key: str, default: str | None = None) -> str:
    value = values.get(key, default)
    if not isinstance(value, str) or not value:
        raise ValueError(f"typst.toml [{key}] must be a non-empty string")
    return value
