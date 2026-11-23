"""scripts/plan-snapshots against a stub factory that answers from a list: fail, or ok with two snapshots."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "plan-snapshots"

STUB = """#!/bin/sh
# Answers each call from the next line of $ANSWERS: `fail`, or `ok <debian> <security>`.
echo "$*" >> "$CALLS"
n=$(wc -l < "$CALLS")
line=$(sed -n "${n}p" "$ANSWERS")
set -- "$@"
while [ "$#" -gt 0 ]; do
  [ "$1" != --out ] || out=$2
  shift
done
case "$line" in
  fail) echo "stub: the plan failed" >&2; exit 1 ;;
  ok*)
    set -- $line
    printf '{"schema": 2, "snapshots": {"debian": "%s", "debian-security": "%s"}, "images": {"debian": {"state": "build"}, "core": {"state": "reuse", "artifact": "sha256:%s"}}}\\n' \\
      "$2" "$3" "$(printf '%064d' 0)" > "$out"
    ;;
  *) echo "stub: no answer for call $n" >&2; exit 3 ;;
esac
"""

D1 = "20261121T203158Z"
S1 = "20261121T005332Z"
S2 = "20261123T141315Z"
D2 = "20261123T084014Z"


class PlanSnapshotsTests(unittest.TestCase):
    def run_script(
        self, answers: list[str], asked: str = "", archive: str = "", max_wait: int = 600
    ) -> tuple[subprocess.CompletedProcess[str], list[str], dict[str, str], Path]:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        factory = root / "factory"
        factory.write_text(STUB, encoding="utf-8")
        factory.chmod(0o755)
        (root / "answers").write_text("".join(f"{line}\n" for line in answers), encoding="utf-8")
        (root / "calls").write_text("", encoding="utf-8")
        env = {
            **os.environ,
            "FACTORY": str(factory),
            "ANSWERS": str(root / "answers"),
            "CALLS": str(root / "calls"),
            "REPO": "example/images",
            "TAG": "v1.2.3",
            "ASKED": asked,
            "ARCHIVE": archive,
            "MAX_WAIT": str(max_wait),
            "PAUSE": "0",
        }
        result = subprocess.run(
            [str(SCRIPT), str(root / "out")], env=env, capture_output=True, text=True, check=False
        )
        calls = (root / "calls").read_text(encoding="utf-8").splitlines()
        outputs: dict[str, str] = {}
        outputs_file = root / "out" / "outputs.txt"
        if outputs_file.is_file():
            for line in outputs_file.read_text(encoding="utf-8").splitlines():
                key, _, value = line.partition("=")
                outputs[key] = value
        return result, calls, outputs, root / "out"

    def test_no_asked_snapshot_plans_once_at_latest(self) -> None:
        result, calls, outputs, _ = self.run_script([f"ok {D2} {S2}"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 1)
        self.assertIn("--snapshot latest", calls[0])
        self.assertEqual(outputs, {"changed": "true", "debian": D2, "debian_security": S2})

    def test_asked_newer_in_security_plans_again_at_once_with_it(self) -> None:
        result, calls, outputs, out = self.run_script(
            [f"ok {D1} {S1}", f"ok {D1} {S2}"], asked=S2, archive="debian-security"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 2)
        self.assertIn("--snapshot latest", calls[0])
        self.assertIn(f"--snapshot debian={D1},debian-security={S2}", calls[1])
        self.assertEqual(outputs["debian_security"], S2)
        self.assertEqual(outputs["debian"], D1)
        self.assertIn("so the plan was repeated", (out / "summary.md").read_text(encoding="utf-8"))

    def test_the_archive_defaults_to_security(self) -> None:
        result, calls, _, _ = self.run_script([f"ok {D1} {S1}", f"ok {D1} {S2}"], asked=S2)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"--snapshot debian={D1},debian-security={S2}", calls[1])

    def test_asked_newer_in_debian_pins_debian_and_keeps_the_listings_security(self) -> None:
        result, calls, outputs, _ = self.run_script(
            [f"ok {D1} {S1}", f"ok {D2} {S1}"], asked=D2, archive="debian"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"--snapshot debian={D2},debian-security={S1}", calls[1])
        self.assertEqual((outputs["debian"], outputs["debian_security"]), (D2, S1))

    def test_asked_older_or_equal_plans_once(self) -> None:
        for asked in (S1, "20260101T000000Z"):
            with self.subTest(asked=asked):
                result, calls, outputs, _ = self.run_script(
                    [f"ok {D2} {S2}"], asked=asked, archive="debian-security"
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(len(calls), 1)
                self.assertEqual(outputs["debian_security"], S2)

    def test_a_failing_plan_is_tried_again_and_then_succeeds(self) -> None:
        result, calls, outputs, _ = self.run_script(["fail", "fail", f"ok {D2} {S2}"], max_wait=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 3)
        self.assertEqual(outputs["debian_security"], S2)

    def test_the_explicit_plan_is_also_tried_again_when_it_fails(self) -> None:
        result, calls, outputs, _ = self.run_script(
            [f"ok {D1} {S1}", "fail", f"ok {D1} {S2}"], asked=S2, max_wait=60
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 3)
        self.assertIn(f"debian={D1},debian-security={S2}", calls[2])
        self.assertEqual(outputs["debian_security"], S2)

    def test_a_plan_that_keeps_failing_ends_clearly(self) -> None:
        result, calls, outputs, _ = self.run_script(["fail"] * 5, max_wait=0)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(len(calls), 1)
        self.assertIn("still fails after 1 attempts", result.stderr)
        self.assertEqual(outputs, {})

    def test_a_plan_without_a_snapshot_for_an_archive_is_refused(self) -> None:
        result, _, _, _ = self.run_script([f"ok {D1} not-an-id"])
        self.assertEqual(result.returncode, 1)
        self.assertIn("debian-security", result.stderr)

    def test_bad_arguments(self) -> None:
        result, calls, _, _ = self.run_script([f"ok {D1} {S1}"], asked="yesterday")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(calls, [])
        result, calls, _, _ = self.run_script([f"ok {D1} {S1}"], asked=S2, archive="security")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
