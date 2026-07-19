from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .bump import bump_project
from .registry import (
    LocalSourceRelocationError,
    install_source,
    installation_status,
    list_installed_packages,
    remove_installation,
    update_installation,
)
from .scaffold import scaffold_project


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="typst-forge")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create a new Typst project")
    init_parser.add_argument("target", nargs="?", default=".")
    init_parser.add_argument("--kind", choices=["template", "package"], default="package")
    init_parser.add_argument("--namespace", default="local")
    init_parser.add_argument("--version", default="0.1.0")
    init_parser.set_defaults(handler=_cmd_init)

    install_parser = subparsers.add_parser(
        "install", help="Install a local path, GitHub source, or git URL"
    )
    install_parser.add_argument("source")
    install_parser.add_argument("--namespace", default="local")
    install_parser.add_argument("--version")
    install_parser.add_argument("--registry-root", help="Override the Typst packages root")
    install_parser.add_argument("--cache-root", help="Override the Typst Forge cache root")
    install_parser.add_argument(
        "--link-mode",
        choices=["auto", "symlink", "copy"],
        default="auto",
        help="How installed projects should be materialized",
    )
    install_parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing entry, including a moved local source",
    )
    install_parser.set_defaults(handler=_cmd_install)

    update_parser = subparsers.add_parser(
        "update", help="Reinstall an installed package or source"
    )
    update_parser.add_argument("target")
    update_parser.add_argument("--namespace", default="local")
    update_parser.add_argument("--version")
    update_parser.add_argument("--registry-root", help="Override the Typst packages root")
    update_parser.add_argument("--cache-root", help="Override the Typst Forge cache root")
    update_parser.add_argument(
        "--link-mode",
        choices=["auto", "symlink", "copy"],
        default=None,
        help="How installed projects should be materialized",
    )
    update_parser.set_defaults(handler=_cmd_update)

    remove_parser = subparsers.add_parser(
        "remove", help="Remove an installed package or source"
    )
    remove_parser.add_argument("target")
    remove_parser.add_argument("--namespace", default="local")
    remove_parser.add_argument("--version")
    remove_parser.add_argument("--registry-root", help="Override the Typst packages root")
    remove_parser.set_defaults(handler=_cmd_remove)

    list_parser = subparsers.add_parser("list", help="List installed packages and templates")
    list_parser.add_argument("--json", action="store_true")
    list_parser.add_argument("--registry-root", help="Override the Typst packages root")
    list_parser.set_defaults(handler=_cmd_list)

    status_parser = subparsers.add_parser(
        "status", help="Show status for an installed package or source"
    )
    status_parser.add_argument("target")
    status_parser.add_argument("--namespace", default="local")
    status_parser.add_argument("--version")
    status_parser.add_argument("--registry-root", help="Override the Typst packages root")
    status_parser.set_defaults(handler=_cmd_status)

    bump_parser = subparsers.add_parser(
        "bump", help="Bump typst.toml, commit the change, and create a Git tag"
    )
    bump_parser.add_argument("version", help="major, minor, patch, or an exact X.Y.Z version")
    bump_parser.add_argument("--registry-root", help="Override the Typst packages root")
    bump_parser.set_defaults(handler=_cmd_bump)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


def _cmd_init(args: argparse.Namespace) -> int:
    target = Path(args.target)
    if args.target == ".":
        root = Path.cwd()
        name = root.name.replace("_", "-")
    else:
        root = Path.cwd() / target
        name = target.name.replace("_", "-")
    scaffold_project(root, args.kind, name, args.version, namespace=args.namespace)
    print(f"initialized {args.kind} project at {root.resolve()}")
    return 0


def _cmd_install(args: argparse.Namespace) -> int:
    try:
        record = _install(args, force=args.force)
    except LocalSourceRelocationError as exc:
        if not sys.stdin.isatty():
            print(f"{exc}; rerun with --force to repoint it", file=sys.stderr)
            return 2
        answer = input(
            f"{exc.existing.namespace}/{exc.existing.package}/{exc.existing.version} "
            f"is installed from {exc.existing.source_location}.\n"
            f"Repoint it to {exc.new_source}? [y/N] "
        )
        if answer.strip().lower() not in {"y", "yes"}:
            print("installation unchanged")
            return 1
        record = _install(args, force=True)
    print(f"installed {record.package} {record.version} -> {record.installed_root}")
    return 0


def _install(args: argparse.Namespace, force: bool):
    return install_source(
        args.source,
        namespace=args.namespace,
        version=args.version,
        link_mode=args.link_mode,
        registry_root_override=args.registry_root,
        cache_root_override=args.cache_root,
        force=force,
    )


def _cmd_update(args: argparse.Namespace) -> int:
    records = update_installation(
        args.target,
        namespace=args.namespace,
        version=args.version,
        link_mode=args.link_mode,
        registry_root_override=args.registry_root,
        cache_root_override=args.cache_root,
    )
    for record in records:
        print(f"updated {record.package} {record.version} -> {record.installed_root}")
    return 0


def _cmd_remove(args: argparse.Namespace) -> int:
    removed = remove_installation(
        args.target,
        namespace=args.namespace,
        version=args.version,
        registry_root_override=args.registry_root,
    )
    for path in removed:
        print(f"removed {path}")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    items = list_installed_packages(args.registry_root)
    if args.json:
        print(json.dumps(items, indent=2, sort_keys=True))
        return 0
    for item in items:
        print(
            f'{item["namespace"]}/{item["package"]}/{item["version"]} '
            f'[{item["link_mode"]}] <- {item["source"]}'
        )
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    status = installation_status(
        args.target,
        namespace=args.namespace,
        version=args.version,
        registry_root_override=args.registry_root,
    )
    for key in sorted(status):
        print(f"{key}: {status[key]}")
    return 0


def _cmd_bump(args: argparse.Namespace) -> int:
    result = bump_project(
        Path.cwd(),
        args.version,
        registry_root_override=args.registry_root,
    )
    print(f"bumped {result.project} {result.old_version} -> {result.new_version}")
    print(f"created commit and tag {result.tag}")
    for record in result.installations:
        print(f"installed {record.package} {record.version} -> {record.installed_root}")
    return 0
