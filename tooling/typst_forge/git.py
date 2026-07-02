from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


VERSION_TAG = re.compile(r"^v?(?P<version>\d+(?:\.\d+){1,2}(?:-[0-9A-Za-z.-]+)?)$")


@dataclass(frozen=True)
class GitState:
    root: Path
    commit: str | None
    tags: tuple[str, ...]


def run_git(args: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def git_available() -> bool:
    return shutil.which("git") is not None


def repo_root(start: Path) -> Path:
    output = run_git(["rev-parse", "--show-toplevel"], cwd=start)
    return Path(output)


def git_state(project_root: Path) -> GitState:
    root = repo_root(project_root)
    try:
        commit = run_git(["rev-parse", "HEAD"], cwd=root)
    except subprocess.CalledProcessError:
        commit = None
    tags_output = ""
    if commit is not None:
        tags_output = run_git(["tag", "--points-at", "HEAD"], cwd=root)
    tags = tuple(sorted(filter(None, tags_output.splitlines())))
    return GitState(root=root, commit=commit, tags=tags)


def normalize_version(tag: str) -> str:
    match = VERSION_TAG.fullmatch(tag)
    if not match:
        raise ValueError(f"tag {tag!r} is not a version-like tag")
    return match.group("version")


def version_key(version: str) -> tuple[object, ...]:
    normalized = normalize_version(version)
    core, *suffix = normalized.split("-", 1)
    parts = tuple(int(part) for part in core.split("."))
    prerelease = suffix[0] if suffix else ""
    return (*parts, 1 if not prerelease else 0, prerelease)


def highest_version(tags: list[str]) -> str | None:
    normalized = []
    for tag in tags:
        try:
            normalized.append((version_key(tag), normalize_version(tag)))
        except ValueError:
            continue
    if not normalized:
        return None
    return max(normalized, key=lambda item: item[0])[1]


def local_version(project_root: Path, requested: str | None = None) -> str:
    manifest_version = None
    if requested is not None:
        return normalize_version(requested)

    try:
        state = git_state(project_root)
    except subprocess.CalledProcessError:
        state = GitState(root=project_root, commit=None, tags=())

    resolved = highest_version(list(state.tags))
    if resolved is not None:
        return resolved

    from .manifest import load_manifest

    manifest_version = load_manifest(project_root).version
    return normalize_version(manifest_version)


def remote_tags(remote_url: str) -> list[str]:
    try:
        output = run_git(["ls-remote", "--tags", "--refs", remote_url])
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"failed to inspect remote tags for {remote_url!r}") from exc
    tags: list[str] = []
    for line in output.splitlines():
        _, ref = line.split("\t", 1)
        if ref.startswith("refs/tags/"):
            tags.append(ref.removeprefix("refs/tags/"))
    return tags


def remote_version(remote_url: str, requested: str | None = None) -> str:
    if requested is not None:
        return normalize_version(requested)
    tag = highest_version(remote_tags(remote_url))
    if tag is None:
        raise ValueError(f"no version-like tags found for {remote_url!r}")
    return tag


def clone_release(remote_url: str, ref: str, destination: Path) -> Path:
    if destination.exists():
        shutil.rmtree(destination)
    subprocess.run(
        ["git", "clone", "--quiet", "--depth", "1", "--branch", ref, remote_url, str(destination)],
        check=True,
        text=True,
        capture_output=True,
    )
    return destination
