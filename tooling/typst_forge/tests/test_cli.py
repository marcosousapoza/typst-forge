from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def forge(*args: str, home: Path, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["XDG_DATA_HOME"] = str(home / ".local" / "share")
    env["XDG_CACHE_HOME"] = str(home / ".cache")
    kwargs: dict[str, object] = {"cwd": ROOT, "check": True, "text": True, "env": env}
    if capture_output:
        kwargs["capture_output"] = True
    return subprocess.run(["uv", "run", "typst-forge", *args], **kwargs)


def init_repo(root: Path, kind: str, name: str, version: str) -> Path:
    forge("init", str(root), "--kind", kind, "--name", name, "--version", version, home=root.parent)
    git("config", "user.email", "test@example.com", cwd=root)
    git("config", "user.name", "Test User", cwd=root)
    git("add", ".", cwd=root)
    git("commit", "-m", "initial", cwd=root)
    git("tag", f"v{version}", cwd=root)
    return root


class TypstForgeCliTest(unittest.TestCase):
    def test_init_creates_expected_layouts(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            temp = Path(tempdir)
            package_repo = temp / "dummy-package"
            template_repo = temp / "dummy-template"

            init_repo(package_repo, "package", "dummy-package", "0.2.0")
            init_repo(template_repo, "template", "dummy-template", "0.1.0")

            self.assertTrue((package_repo / "typst.toml").is_file())
            self.assertTrue((package_repo / "src" / "lib.typ").is_file())
            self.assertFalse((package_repo / "template").exists())

            self.assertTrue((template_repo / "typst.toml").is_file())
            self.assertTrue((template_repo / "src" / "lib.typ").is_file())
            self.assertTrue((template_repo / "template" / "main.typ").is_file())

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
