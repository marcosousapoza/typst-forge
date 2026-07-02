from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class SourceSpec:
    raw: str
    kind: str
    path: Path | None = None
    url: str | None = None
    owner: str | None = None
    repo: str | None = None
    ref: str | None = None


def parse_source(raw: str, cwd: Path | None = None) -> SourceSpec:
    if not raw:
        raise ValueError("source cannot be empty")

    cwd = cwd or Path.cwd()
    candidate = Path(raw).expanduser()
    if candidate.exists():
        return SourceSpec(raw=raw, kind="local", path=candidate.resolve())

    if raw.startswith("github:"):
        return _parse_github(raw[len("github:") :], raw)

    parsed = urlparse(raw)
    if parsed.scheme:
        if parsed.scheme in {"http", "https", "ssh", "git", "file"}:
            return SourceSpec(raw=raw, kind="remote", url=raw)
        raise ValueError(f"unsupported source url scheme: {parsed.scheme}")

    if raw.startswith("git@") or raw.endswith(".git"):
        return SourceSpec(raw=raw, kind="remote", url=raw)

    if "/" in raw:
        return _parse_github(raw, raw)

    maybe_path = (cwd / raw).expanduser()
    if maybe_path.exists():
        return SourceSpec(raw=raw, kind="local", path=maybe_path.resolve())

    raise ValueError(f"cannot parse source: {raw!r}")


def _parse_github(value: str, raw: str) -> SourceSpec:
    ref: str | None = None
    repo_part = value
    if "@" in value:
        repo_part, ref = value.rsplit("@", 1)
    if repo_part.startswith("https://github.com/"):
        repo_part = repo_part.removeprefix("https://github.com/")
    if repo_part.startswith("http://github.com/"):
        repo_part = repo_part.removeprefix("http://github.com/")
    if repo_part.endswith(".git"):
        repo_part = repo_part[:-4]
    owner, _, repo = repo_part.partition("/")
    if not owner or not repo:
        raise ValueError(f"invalid github source: {raw!r}")
    return SourceSpec(raw=raw, kind="github", owner=owner, repo=repo, ref=ref)


def source_label(spec: SourceSpec) -> str:
    if spec.kind == "local" and spec.path is not None:
        return str(spec.path)
    if spec.kind == "github" and spec.owner and spec.repo:
        label = f"github:{spec.owner}/{spec.repo}"
        if spec.ref:
            label += f"@{spec.ref}"
        return label
    if spec.url:
        return spec.url
    return spec.raw

