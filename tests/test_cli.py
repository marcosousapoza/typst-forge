from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]


def git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def forge(
    *args: str,
    home: Path,
    capture_output: bool = False,
    check: bool = True,
    cwd: Path = ROOT,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["XDG_DATA_HOME"] = str(home / ".local" / "share")
    env["XDG_CACHE_HOME"] = str(home / ".cache")
    kwargs: dict[str, object] = {"cwd": cwd, "check": check, "text": True, "env": env}
    if capture_output:
        kwargs["capture_output"] = True
    return subprocess.run(
        ["uv", "run", "--project", str(ROOT), "--no-sync", "typst-forge", *args],
        **kwargs,
    )


def init_repo(root: Path, kind: str, name: str, version: str) -> Path:
    forge("init", str(root), "--kind", kind, "--name", name, "--version", version, home=root.parent)
    git("config", "user.email", "test@example.com", cwd=root)
    git("config", "user.name", "Test User", cwd=root)
    git("add", ".", cwd=root)
    git("commit", "-m", "initial", cwd=root)
    git("tag", f"v{version}", cwd=root)
    return root


class TypstForgeCliTest(unittest.TestCase):
    def test_version_bump_inputs(self) -> None:
        from typst_forge.bump import next_version

        self.assertEqual(next_version("1.2.3", "patch"), "1.2.4")
        self.assertEqual(next_version("1.2.3", "minor"), "1.3.0")
        self.assertEqual(next_version("1.2.3", "major"), "2.0.0")
        self.assertEqual(next_version("1.2.3", "2.1.0"), "2.1.0")
        with self.assertRaisesRegex(ValueError, "must be greater"):
            next_version("1.2.3", "1.2.3")
        with self.assertRaisesRegex(ValueError, "X.Y.Z"):
            next_version("1.2.3", "1.3")

    def test_install_supports_plain_local_folders_without_git_metadata(self) -> None:
        from typst_forge.registry import install_source

        with tempfile.TemporaryDirectory() as tempdir:
            temp = Path(tempdir)
            home = temp / "home"
            home.mkdir()
            project = temp / "plain-package"
            project.mkdir()
            project.joinpath("src").mkdir()
            project.joinpath("typst.toml").write_text(
                "\n".join(
                    [
                        "[package]",
                        'name = "plain-package"',
                        'version = "0.3.0"',
                        'entrypoint = "src/lib.typ"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            project.joinpath("src", "lib.typ").write_text('#let hello(name) = "Hello, " + name\n', encoding="utf-8")

            with patch("typst_forge.git.git_state", side_effect=FileNotFoundError):
                record = install_source(
                    project,
                    registry_root_override=str(home / ".local" / "share" / "typst" / "packages"),
                    cache_root_override=str(home / ".cache" / "typst-forge"),
                    link_mode="copy",
                )

            install_path = home / ".local" / "share" / "typst" / "packages" / "local" / "plain-package" / "0.3.0"
            self.assertEqual(record.package, "plain-package")
            self.assertEqual(record.version, "0.3.0")
            self.assertTrue(install_path.exists())
            self.assertTrue((install_path / "src" / "lib.typ").is_file())

    def test_init_creates_expected_layouts(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            temp = Path(tempdir)
            package_repo = temp / "dummy-package"
            template_repo = temp / "dummy-template"

            init_repo(package_repo, "package", "dummy-package", "0.2.0")
            init_repo(template_repo, "template", "dummy-template", "0.1.0")

            self.assertTrue((package_repo / "typst.toml").is_file())
            self.assertTrue((package_repo / "src" / "lib.typ").is_file())
            self.assertTrue((package_repo / ".gitignore").is_file())
            self.assertTrue((package_repo / ".git").is_dir())
            self.assertFalse((package_repo / "template").exists())

            self.assertTrue((template_repo / "typst.toml").is_file())
            self.assertTrue((template_repo / "src" / "lib.typ").is_file())
            self.assertTrue((template_repo / ".gitignore").is_file())
            self.assertTrue((template_repo / ".git").is_dir())
            self.assertTrue((template_repo / "template" / "main.typ").is_file())

    def test_install_repairs_a_moved_local_symlink_with_confirmation(self) -> None:
        from typst_forge.cli import _cmd_install

        with tempfile.TemporaryDirectory() as tempdir:
            temp = Path(tempdir)
            home = temp / "home"
            home.mkdir()
            original = init_repo(temp / "original", "package", "moved-package", "0.4.0")
            install_path = (
                home
                / ".local"
                / "share"
                / "typst"
                / "packages"
                / "local"
                / "moved-package"
                / "0.4.0"
            )
            registry = home / ".local" / "share" / "typst" / "packages"
            cache = home / ".cache" / "typst-forge"
            forge("install", str(original), "--link-mode", "symlink", home=home)
            moved = original.rename(temp / "moved")

            args = Namespace(
                source=str(moved),
                namespace="local",
                version=None,
                registry_root=str(registry),
                cache_root=str(cache),
                link_mode="symlink",
                force=False,
            )
            fake_stdin = MagicMock()
            fake_stdin.isatty.return_value = True
            with patch("typst_forge.cli.sys.stdin", fake_stdin), patch(
                "builtins.input", return_value="no"
            ):
                declined = _cmd_install(args)

            self.assertEqual(declined, 1)
            self.assertEqual(install_path.resolve(strict=False), original.resolve(strict=False))

            with patch("typst_forge.cli.sys.stdin", fake_stdin), patch(
                "builtins.input", return_value="yes"
            ):
                result = _cmd_install(args)

            self.assertEqual(result, 0)
            self.assertEqual(install_path.resolve(), moved.resolve())
            self.assertIn(
                str(moved.resolve()),
                forge("list", "--json", home=home, capture_output=True).stdout,
            )

    def test_moved_symlink_requires_force_without_a_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            temp = Path(tempdir)
            home = temp / "home"
            home.mkdir()
            original = init_repo(temp / "original", "package", "moved-package", "0.4.0")
            install_path = (
                home
                / ".local"
                / "share"
                / "typst"
                / "packages"
                / "local"
                / "moved-package"
                / "0.4.0"
            )
            forge("install", str(original), "--link-mode", "symlink", home=home)
            moved = original.rename(temp / "moved")

            rejected = forge(
                "install",
                str(moved),
                "--link-mode",
                "symlink",
                home=home,
                capture_output=True,
                check=False,
            )
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("rerun with --force", rejected.stderr)
            self.assertEqual(install_path.resolve(strict=False), original.resolve(strict=False))

            forge(
                "install",
                str(moved),
                "--link-mode",
                "symlink",
                "--force",
                home=home,
            )
            self.assertEqual(install_path.resolve(), moved.resolve())

    def test_bump_commits_tags_updates_self_import_and_adds_registry_version(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            temp = Path(tempdir)
            home = temp / "home"
            home.mkdir()
            repo = init_repo(temp / "release-template", "template", "release-template", "1.2.3")
            template = repo / "template" / "main.typ"
            template.write_text(
                "\n".join(
                    [
                        '#import "@local/release-template:1.2.3": render',
                        '#import "@local/release-template:1.2.30": future',
                        '#import "@other/dependency:1.2.3": helper',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            git("add", "template/main.typ", cwd=repo)
            git("commit", "-m", "use package import", cwd=repo)
            forge("install", str(repo), "--link-mode", "symlink", home=home)

            result = forge(
                "bump",
                "minor",
                home=home,
                cwd=repo,
                capture_output=True,
            )

            self.assertIn("1.2.3 -> 1.3.0", result.stdout)
            self.assertIn('version = "1.3.0"', (repo / "typst.toml").read_text(encoding="utf-8"))
            template_content = template.read_text(encoding="utf-8")
            self.assertIn("@local/release-template:1.3.0", template_content)
            self.assertIn("@local/release-template:1.2.30", template_content)
            self.assertIn("@other/dependency:1.2.3", template_content)
            self.assertEqual(
                subprocess.run(
                    ["git", "log", "-1", "--pretty=%s"],
                    cwd=repo,
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip(),
                "Release 1.3.0",
            )
            self.assertEqual(
                subprocess.run(
                    ["git", "rev-parse", "v1.3.0^{}"],
                    cwd=repo,
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip(),
                subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=repo,
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip(),
            )
            self.assertEqual(
                subprocess.run(
                    ["git", "cat-file", "-t", "v1.3.0"],
                    cwd=repo,
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip(),
                "tag",
            )
            package_root = home / ".local" / "share" / "typst" / "packages" / "local" / "release-template"
            self.assertTrue((package_root / "1.2.3").is_symlink())
            self.assertTrue((package_root / "1.3.0").is_symlink())
            self.assertEqual((package_root / "1.3.0").resolve(), repo.resolve())

    def test_bump_rejects_a_dirty_repository_without_changes(self) -> None:
        from typst_forge.bump import bump_project

        with tempfile.TemporaryDirectory() as tempdir:
            temp = Path(tempdir)
            repo = init_repo(temp / "dirty-package", "package", "dirty-package", "0.1.0")
            manifest_before = (repo / "typst.toml").read_text(encoding="utf-8")
            (repo / "src" / "lib.typ").write_text("changed\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "working tree must be clean"):
                bump_project(repo, "patch", registry_root_override=str(temp / "registry"))

            self.assertEqual((repo / "typst.toml").read_text(encoding="utf-8"), manifest_before)
            self.assertNotIn(
                "v0.1.1",
                subprocess.run(
                    ["git", "tag", "--list"],
                    cwd=repo,
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.splitlines(),
            )

    def test_local_install_update_list_and_remove(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            temp = Path(tempdir)
            home = temp / "home"
            home.mkdir()
            repo = init_repo(temp / "dummy-package", "package", "dummy-package", "0.2.0")
            install_path = home / ".local" / "share" / "typst" / "packages" / "local" / "dummy-package" / "0.2.0"

            forge("install", str(repo), "--link-mode", "copy", home=home)
            self.assertTrue(install_path.exists())
            self.assertTrue((install_path / "src" / "lib.typ").is_file())

            repo.joinpath("src", "lib.typ").write_text('#let hello(name) = "Hi, " + name\n', encoding="utf-8")
            git("add", "src/lib.typ", cwd=repo)
            git("commit", "-m", "update lib", cwd=repo)

            forge("update", "dummy-package", home=home)
            self.assertIn("Hi,", (install_path / "src" / "lib.typ").read_text(encoding="utf-8"))

            list_output = forge("list", home=home, capture_output=True).stdout
            self.assertIn("local/dummy-package/0.2.0", list_output)
            self.assertIn("[copy]", list_output)

            status_output = forge("status", "dummy-package", home=home, capture_output=True).stdout
            self.assertIn("installed: yes", status_output)
            self.assertIn("package: dummy-package", status_output)
            self.assertIn("version: 0.2.0", status_output)

            forge("remove", "dummy-package", home=home)
            self.assertFalse(install_path.exists())

    def test_remote_install_from_git_url_uses_release_tag(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            temp = Path(tempdir)
            home = temp / "home"
            home.mkdir()
            repo = init_repo(temp / "remote-template", "template", "remote-template", "1.0.0")
            remote = temp / "remote-template.git"
            subprocess.run(["git", "clone", "--bare", str(repo), str(remote)], check=True, capture_output=True, text=True)

            forge("install", f"file://{remote}", "--link-mode", "symlink", home=home)
            install_path = home / ".local" / "share" / "typst" / "packages" / "local" / "remote-template" / "1.0.0"
            self.assertTrue(install_path.is_symlink())
            self.assertIn("remote-template", forge("list", home=home, capture_output=True).stdout)

            status_output = forge("status", f"file://{remote}", home=home, capture_output=True).stdout
            self.assertIn("source_kind: remote", status_output)
            self.assertIn("version: 1.0.0", status_output)

    def test_github_style_source_parser_accepts_tagged_refs(self) -> None:
        from typst_forge.source import parse_source

        spec = parse_source("github:example/hello-world@v1.2.3")
        self.assertEqual(spec.kind, "github")
        self.assertEqual(spec.owner, "example")
        self.assertEqual(spec.repo, "hello-world")
        self.assertEqual(spec.ref, "v1.2.3")


if __name__ == "__main__":
    unittest.main()
