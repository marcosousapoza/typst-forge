from __future__ import annotations

import os
from pathlib import Path


def default_registry_root() -> Path:
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home).expanduser() / "typst" / "packages"
    return Path.home() / ".local" / "share" / "typst" / "packages"


def default_cache_root() -> Path:
    xdg_cache_home = os.environ.get("XDG_CACHE_HOME")
    if xdg_cache_home:
        return Path(xdg_cache_home).expanduser() / "typst-forge"
    return Path.home() / ".cache" / "typst-forge"


def registry_root(override: str | None = None) -> Path:
    if override:
        return Path(override).expanduser()
    return default_registry_root()


def metadata_root(override: str | None = None) -> Path:
    return registry_root(override) / ".forge"


def cache_root(override: str | None = None) -> Path:
    if override:
        return Path(override).expanduser()
    return default_cache_root()
