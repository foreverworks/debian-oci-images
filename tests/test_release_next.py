import contextlib
import io
import os
import subprocess
import tempfile
import unittest
from collections.abc import Iterator
from pathlib import Path

import release_next


class VersionTest(unittest.TestCase):
    def test_newest_compares_numbers_not_text(self) -> None:
        self.assertEqual(release_next.newest(["v0.1.9", "v0.1.10", "v0.2.0-rc1", "latest"]), "v0.1.10")

    def test_newest_of_no_version_is_none(self) -> None:
        self.assertIsNone(release_next.newest(["latest", "v1", "v01.2.3"]))

    def test_bump_moves_the_patch(self) -> None:
        self.assertEqual(release_next.bump("v0.1.9"), "v0.1.10")

    def test_bump_refuses_a_non_version(self) -> None:
        with self.assertRaises(release_next.ReleaseError):
            release_next.bump("v1.2")


@contextlib.contextmanager
def repository() -> Iterator[Path]:
    """A throwaway git repository with one commit of every input, tagged v0.1.0, as the cwd."""
    old = Path.cwd()
    with tempfile.TemporaryDirectory() as name:
        root = Path(name)
        os.chdir(root)
        try:
            run("init", "--quiet", "--initial-branch=main")
            for path in release_next.INPUTS:
                (root / path).write_text("one\n", encoding="utf-8")
            commit("inputs")
            run("tag", "v0.1.0")
            yield root
        finally:
            os.chdir(old)


def run(*arguments: str) -> None:
    subprocess.run(["git", *arguments], check=True, capture_output=True)


def commit(message: str) -> None:
    run("add", "--all")
    run("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "--quiet", "--allow-empty", "-m", message)


class HistoryTest(unittest.TestCase):
    def test_the_released_commit_is_not_pending_and_gives_its_own_tag(self) -> None:
        with repository():
            self.assertFalse(release_next.pending("HEAD"))
            self.assertEqual(release_next.next_tag("HEAD"), ("v0.1.0", False))

    def test_a_change_outside_the_inputs_releases_nothing(self) -> None:
        with repository() as root:
            (root / "README.md").write_text("docs\n", encoding="utf-8")
            commit("docs")
            self.assertIsNone(release_next.next_tag("HEAD"))

    def test_a_lock_change_releases_the_next_patch(self) -> None:
        with repository() as root:
            (root / "lock.json").write_text("two\n", encoding="utf-8")
            commit("bump")
            self.assertTrue(release_next.pending("HEAD"))
            self.assertEqual(release_next.next_tag("HEAD"), ("v0.1.1", True))

    def test_a_tagged_commit_gives_its_own_tag_to_release_again(self) -> None:
        with repository() as root:
            (root / "builder.ref").write_text("two\n", encoding="utf-8")
            commit("bump")
            run("tag", "v0.1.1")
            self.assertEqual(release_next.next_tag("HEAD"), ("v0.1.1", False))

    def test_an_older_commit_than_the_newest_release_is_refused(self) -> None:
        with repository() as root:
            (root / "lock.json").write_text("two\n", encoding="utf-8")
            commit("first bump")
            (root / "lock.json").write_text("three\n", encoding="utf-8")
            commit("second bump")
            run("tag", "v0.1.1")
            with self.assertRaises(release_next.ReleaseError):
                release_next.next_tag("HEAD~1")

    def test_no_version_tag_is_an_error(self) -> None:
        with repository():
            run("tag", "--delete", "v0.1.0")
            with self.assertRaises(release_next.ReleaseError):
                release_next.pending("HEAD")

    def test_main_prints_the_tag(self) -> None:
        with repository() as root:
            (root / "factory.toml").write_text("two\n", encoding="utf-8")
            commit("bump")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(release_next.main(["next"]), 0)
            self.assertEqual(out.getvalue(), "tag=v0.1.1\nnew=true\n")


if __name__ == "__main__":
    unittest.main()
