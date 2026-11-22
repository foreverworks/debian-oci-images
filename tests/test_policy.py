import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import images
import policy

SHA = "0123456789abcdef0123456789abcdef01234567"

GOOD_WORKFLOW = f"""\
name: ci
on: [push]
jobs:
  static:
    runs-on: ubuntu-26.04
    steps:
      - uses: actions/checkout@{SHA} # v6.0.1
      - uses: ./.github/actions/thing
      - name: check
        env:
          REF: ${{{{ github.ref }}}}
        run: |
          echo "$REF"
          scripts/check
      - run: scripts/factory lock check
"""

DEFINITION = """
schema = 1
[debian]
suite = "trixie"
[images.core]
kind = "core"
[images.debian]
kind = "oci"
[images.node-26]
kind = "oci"
"""

FACTORY_ENTRY = {"version": "0.6.3", "url": "https://example.com/{version}", "sha256": "a" * 64}


def lock(**node: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "version": "26.13.1",
        "url": "https://example.com/{version}",
        "sha256": "b" * 64,
        "used_by": ["node-26"],
    }
    entry.update(node)
    return {"inputs": {"debian-image-factory": FACTORY_ENTRY, "node-26": entry}}


class WorkflowTests(unittest.TestCase):
    def problems(self, text: str) -> list[str]:
        return policy.check_workflow("w.yml", text)

    def test_good(self) -> None:
        self.assertEqual(self.problems(GOOD_WORKFLOW), [])

    def test_unpinned_uses(self) -> None:
        for value in (
            "actions/checkout@v6",
            f"actions/checkout@{SHA}",
            f"actions/checkout@{SHA} # latest",
            f"actions/checkout@{SHA[:39]} # v6",
            "docker://alpine:3",
            "checkout@" + SHA + " # v6",
        ):
            with self.subTest(value=value):
                problems = self.problems(f"      - uses: {value}\n")
                self.assertEqual(len(problems), 1, problems)
                self.assertIn("w.yml:1", problems[0])

    def test_uses_with_a_path_is_fine(self) -> None:
        self.assertEqual(self.problems(f"    uses: owner/repo/sub/dir@{SHA} # v1.2.3\n"), [])

    def test_commented_uses_is_ignored(self) -> None:
        self.assertEqual(self.problems("      # uses: actions/checkout@v6\n"), [])

    def test_runs_on(self) -> None:
        for value in ("ubuntu-latest", "ubuntu-24.04", "[ubuntu-26.04]", "${{ matrix.os }}", "ubuntu-26.04-arm", ""):
            with self.subTest(value=value):
                self.assertEqual(len(self.problems(f"    runs-on: {value}\n")), 1)
        self.assertEqual(self.problems("    runs-on: 'ubuntu-26.04' # the only one\n"), [])

    def test_forbidden_words(self) -> None:
        self.assertEqual(len(self.problems("    runs-on: self-hosted\n")), 2)
        self.assertEqual(len(self.problems("    if: github.event.repository.private\n")), 1)

    def test_expression_in_run_block(self) -> None:
        text = "      - run: |\n          echo ${{ github.ref }}\n          ls\n"
        problems = self.problems(text)
        self.assertEqual(len(problems), 1)
        self.assertIn("w.yml:2", problems[0])

    def test_expression_in_one_line_run(self) -> None:
        self.assertEqual(len(self.problems("      - run: echo ${{ github.ref }}\n")), 1)

    def test_expression_after_the_block_is_fine(self) -> None:
        text = "      - run: |\n          ls\n\n          pwd\n        env:\n          X: ${{ github.ref }}\n"
        self.assertEqual(self.problems(text), [])

    def test_folded_block(self) -> None:
        self.assertEqual(len(self.problems("    run: >-\n      echo ${{ x }}\n")), 1)

    def test_forbidden_word_inside_run_block(self) -> None:
        self.assertEqual(len(self.problems("    run: |\n      echo self-hosted\n")), 1)



class WritePermissionTests(unittest.TestCase):
    RELEASE = (
        "permissions:\n  contents: read\njobs:\n  build:\n    permissions:\n      contents: read\n"
        "  publish:\n    permissions:\n      contents: write # assets\n      packages: write\n      id-token: write\n"
    )

    def test_only_the_publish_job_of_release_may_write(self) -> None:
        self.assertEqual(policy.check_write_permissions(".github/workflows/release.yml", self.RELEASE), [])

    def test_the_same_job_elsewhere_may_not(self) -> None:
        self.assertEqual(len(policy.check_write_permissions(".github/workflows/ci.yml", self.RELEASE)), 3)

    def test_a_build_job_may_not(self) -> None:
        text = "jobs:\n  build:\n    permissions:\n      packages: write\n"
        problems = policy.check_write_permissions("release.yml", text)
        self.assertEqual(len(problems), 1)
        self.assertIn("release.yml:4", problems[0])
        self.assertIn("job build", problems[0])

    def test_top_level_may_not(self) -> None:
        for text in ("permissions:\n  contents: write\n", "permissions: write-all\n"):
            with self.subTest(text=text):
                self.assertEqual(len(policy.check_write_permissions("release.yml", text)), 1)

    RENOVATE = (
        "permissions:\n  contents: read\njobs:\n  checksums:\n    permissions:\n      contents: write\n"
        "      actions: write\n"
    )

    def test_the_checksums_job_may_write_contents_and_actions(self) -> None:
        self.assertEqual(policy.check_write_permissions(".github/workflows/renovate-checksums.yml", self.RENOVATE), [])

    def test_the_checksums_job_may_write_nothing_else(self) -> None:
        text = self.RENOVATE + "      packages: write\n"
        self.assertEqual(len(policy.check_write_permissions("renovate-checksums.yml", text)), 1)

    def test_a_second_job_of_that_file_may_not(self) -> None:
        text = self.RENOVATE + "  other:\n    permissions:\n      contents: write\n"
        self.assertEqual(len(policy.check_write_permissions("renovate-checksums.yml", text)), 1)

    def test_another_workflow_may_not_write_contents(self) -> None:
        self.assertEqual(len(policy.check_write_permissions(".github/workflows/ci.yml", self.RENOVATE)), 2)

    RELEASE_NEXT = "jobs:\n  tag:\n    permissions:\n      contents: write\n      actions: write\n"
    SNAPSHOT = "jobs:\n  plan:\n    steps: []\n  feed:\n    permissions:\n      contents: write\n      issues: write\n"

    def test_the_tag_job_of_release_next_may_write_contents_and_actions(self) -> None:
        self.assertEqual(policy.check_write_permissions(".github/workflows/release-next.yml", self.RELEASE_NEXT), [])

    def test_the_tag_job_may_not_write_packages(self) -> None:
        text = self.RELEASE_NEXT + "      packages: write\n"
        self.assertEqual(len(policy.check_write_permissions("release-next.yml", text)), 1)

    def test_the_feed_job_of_snapshot_may_write_contents_and_issues_only(self) -> None:
        self.assertEqual(policy.check_write_permissions(".github/workflows/snapshot.yml", self.SNAPSHOT), [])
        text = self.SNAPSHOT + "      actions: write\n"
        self.assertEqual(len(policy.check_write_permissions("snapshot.yml", text)), 1)

    def test_the_plan_job_of_snapshot_may_not_write(self) -> None:
        text = "jobs:\n  plan:\n    permissions:\n      contents: write\n"
        self.assertEqual(len(policy.check_write_permissions("snapshot.yml", text)), 1)


class BuilderRefTests(unittest.TestCase):
    REF = "ghcr.io/example/builder:v0.6.3@sha256:" + "c" * 64

    def test_good(self) -> None:
        self.assertEqual(policy.check_builder_ref(self.REF + "\n", lock()), [])

    def test_tag_mismatch(self) -> None:
        problems = policy.check_builder_ref(self.REF.replace("v0.6.3", "v0.6.1"), lock())
        self.assertEqual(len(problems), 1)
        self.assertIn("v0.6.3", problems[0])

    def test_no_digest(self) -> None:
        self.assertEqual(len(policy.check_builder_ref("ghcr.io/example/builder:v0.6.3", lock())), 1)
        self.assertEqual(len(policy.check_builder_ref(self.REF.replace("sha256", "sha512"), lock())), 1)
        self.assertEqual(len(policy.check_builder_ref(self.REF[:-1], lock())), 1)

    def test_no_factory_in_lock(self) -> None:
        self.assertEqual(len(policy.check_builder_ref(self.REF, {"inputs": {}})), 1)


class DefinitionTests(unittest.TestCase):
    def problems(self, definition: str, the_lock: dict[str, object]) -> list[str]:
        return policy.check_definition(images.parse_definition(definition), the_lock)

    def test_good(self) -> None:
        self.assertEqual(self.problems(DEFINITION, lock()), [])

    def test_missing_entry(self) -> None:
        self.assertEqual(len(self.problems(DEFINITION, {"inputs": {}})), 1)

    def test_wrong_major(self) -> None:
        problems = self.problems(DEFINITION, lock(version="24.22.3"))
        self.assertEqual(len(problems), 1)
        self.assertIn("not a 26.x", problems[0])

    def test_used_by(self) -> None:
        self.assertEqual(len(self.problems(DEFINITION, lock(used_by=["node-26", "node-24"]))), 1)
        self.assertEqual(len(self.problems(DEFINITION, lock(used_by=[]))), 1)

    def test_oci_image_without_repository(self) -> None:
        problems = self.problems(DEFINITION + '[images.python]\nkind = "oci"\n', lock())
        self.assertEqual(len(problems), 1)
        self.assertIn("python", problems[0])

    def test_core_needs_no_repository(self) -> None:
        self.assertEqual(self.problems(DEFINITION, lock()), [])

    def test_no_images(self) -> None:
        self.assertEqual(len(self.problems("schema = 1\n", lock())), 1)


class RepositoryTests(unittest.TestCase):
    def quiet_main(self, directory: str) -> int:
        with contextlib.redirect_stdout(io.StringIO()):
            return policy.main([directory])

    def build(self, root: Path, workflow: str) -> None:
        (root / ".github" / "workflows").mkdir(parents=True)
        (root / ".github" / "workflows" / "ci.yml").write_text(workflow, encoding="utf-8")
        (root / "lock.json").write_text(json.dumps(lock()), encoding="utf-8")
        (root / "factory.toml").write_text(DEFINITION, encoding="utf-8")
        (root / "builder.ref").write_text("ghcr.io/example/builder:v0.6.3@sha256:" + "c" * 64 + "\n", encoding="utf-8")

    def test_good_repository(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.build(Path(directory), GOOD_WORKFLOW)
            self.assertEqual(policy.check_repository(Path(directory)), [])
            self.assertEqual(self.quiet_main(directory), 0)

    def test_bad_repository_lists_every_problem(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build(root, "    runs-on: ubuntu-latest\n      - uses: a/b@v1\n")
            (root / "builder.ref").write_text("x", encoding="utf-8")
            problems = policy.check_repository(root)
            self.assertEqual(len(problems), 3, problems)
            self.assertEqual(self.quiet_main(directory), 1)

    def test_missing_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(self.quiet_main(directory), 1)

    def test_action_files_are_checked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build(root, GOOD_WORKFLOW)
            action = root / ".github" / "actions" / "thing"
            action.mkdir(parents=True)
            (action / "action.yml").write_text("runs:\n  steps:\n    - uses: a/b@v1\n", encoding="utf-8")
            problems = policy.check_repository(root)
            self.assertEqual(len(problems), 1)
            self.assertIn("actions/thing/action.yml:3", problems[0])


if __name__ == "__main__":
    unittest.main()
