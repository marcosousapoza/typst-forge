from __future__ import annotations

import subprocess
from pathlib import Path

from .git import git_available


def scaffold_project(root: Path, kind: str, name: str, version: str, namespace: str = "local") -> None:
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)

    (root / "src").mkdir(exist_ok=True)
    if kind == "template":
        (root / "template").mkdir(exist_ok=True)

    (root / "typst.toml").write_text(_typst_toml(kind, name, version, namespace), encoding="utf-8")
    (root / "src" / "lib.typ").write_text(_lib_typ(kind), encoding="utf-8")
    if kind == "template":
        (root / "template" / "main.typ").write_text(
            _template_main_typ(name, version, namespace),
            encoding="utf-8",
        )

    (root / ".gitignore").write_text(
        "\n".join(
            [
                ".typst-forge",
                "build",
                "__pycache__",
                "",
            ]
        ),
        encoding="utf-8",
    )

    if not git_available():
        raise RuntimeError("git is required to initialize Typst Forge projects")
    subprocess.run(["git", "init"], cwd=root, check=True, text=True, capture_output=True)


def _typst_toml(kind: str, name: str, version: str, namespace: str) -> str:
    entrypoint = "src/lib.typ"
    return "\n".join(
        [
            "[package]",
            f'name = "{name}"',
            f'version = "{version}"',
            f'entrypoint = "{entrypoint}"',
            "",
            "[tool.typst_forge]",
            f'kind = "{kind}"',
            f'namespace = "{namespace}"',
            "",
        ]
    )


def _lib_typ(kind: str) -> str:
    if kind == "template":
        return (
            "#let render(title, body) = [\n"
            "= #title\n\n"
            "#body\n"
            "]\n"
        )
    return '#let hello(name) = "Hello, " + name\n'


def _template_main_typ(name: str, version: str, namespace: str) -> str:
    return (
        f'#import "@{namespace}/{name}:{version}": render\n\n'
        '#render("Typst Forge", "template scaffold")\n'
    )
