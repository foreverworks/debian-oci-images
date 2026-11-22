import subprocess
import tempfile
import unittest
from pathlib import Path

JOBS = Path(__file__).resolve().parent.parent / "scripts" / "jobs.sh"


def run_script(body: str) -> subprocess.CompletedProcess[str]:
    """Run `body` in sh with scripts/jobs.sh sourced and an empty log directory in $LOGS."""
    with tempfile.TemporaryDirectory() as logs:
        script = f'. "{JOBS}"\nLOGS="{logs}"\nexport LOGS\njobs_begin "$LOGS"\n{body}'
        return subprocess.run(["sh", "-c", script], capture_output=True, text=True, check=False)


class JobsTests(unittest.TestCase):
    def test_logs_come_in_start_order_and_success_returns_zero(self) -> None:
        result = run_script(
            "job slow sh -c 'sleep 0.2; echo slow done'\n"
            "job fast echo fast done\n"
            "jobs_settle\n"
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "== slow: ok\nslow done\n== fast: ok\nfast done\n")

    def test_a_failing_job_is_named_and_fails_the_settle(self) -> None:
        result = run_script(
            "job good echo fine\n"
            "job bad sh -c 'echo broken >&2; exit 3'\n"
            "jobs_settle\n"
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "== good: ok\nfine\n== bad: FAILED\nbroken\n")

    def test_jobs_run_side_by_side(self) -> None:
        # The first job can only finish after the second has started: one after the other, it would give up.
        result = run_script(
            "job waits sh -c 'for _ in $(seq 100); do [ -e \"$LOGS/flag\" ] && exit 0; sleep 0.02; done; exit 1'\n"
            "job starts touch \"$LOGS/flag\"\n"
            "jobs_settle\n"
        )
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_a_job_does_not_read_the_callers_input(self) -> None:
        result = run_script(
            "printf 'a\\nb\\n' | { read -r first; job eat cat; read -r second; jobs_settle >/dev/null; echo \"$first$second\"; }\n"
        )
        self.assertEqual(result.stdout, "ab\n")

    def test_settle_can_be_reused(self) -> None:
        result = run_script("job one echo 1\njobs_settle\njob two echo 2\njobs_settle\n")
        self.assertEqual(result.stdout, "== one: ok\n1\n== two: ok\n2\n")


if __name__ == "__main__":
    unittest.main()
