import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import lockpin

GOOD = "a" * 64


def lock_with(**changes: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "version": "1.2.3",
        "url": "https://example.com/tool-{version}.pyz",
        "sha256": GOOD,
    }
    entry.update(changes)
    return {"inputs": {"tool": entry}}


class PinOfTests(unittest.TestCase):
    def test_renders_the_url(self) -> None:
        pin = lockpin.pin_of(lock_with(), "tool")
        self.assertEqual(pin, ("1.2.3", "https://example.com/tool-1.2.3.pyz", GOOD))

    def test_missing_entry(self) -> None:
        with self.assertRaisesRegex(lockpin.LockError, "no entry other"):
            lockpin.pin_of(lock_with(), "other")

    def test_missing_inputs(self) -> None:
        with self.assertRaisesRegex(lockpin.LockError, "no inputs"):
            lockpin.pin_of({}, "tool")

    def test_not_https(self) -> None:
        with self.assertRaisesRegex(lockpin.LockError, "not https"):
            lockpin.pin_of(lock_with(url="http://example.com/{version}"), "tool")

    def test_other_placeholder(self) -> None:
        with self.assertRaisesRegex(lockpin.LockError, "placeholder"):
            lockpin.pin_of(lock_with(url="https://example.com/{name}"), "tool")

    def test_all_zero_sha(self) -> None:
        with self.assertRaisesRegex(lockpin.LockError, "all-zero"):
            lockpin.pin_of(lock_with(sha256="0" * 64), "tool")

    def test_malformed_sha(self) -> None:
        for bad in ("abc", "A" * 64, "g" * 64, GOOD + "a"):
            with self.subTest(bad=bad), self.assertRaisesRegex(lockpin.LockError, "malformed"):
                lockpin.pin_of(lock_with(sha256=bad), "tool")

    def test_missing_field(self) -> None:
        with self.assertRaisesRegex(lockpin.LockError, "no version"):
            lockpin.pin_of(lock_with(version=""), "tool")


class ParseLockTests(unittest.TestCase):
    def test_invalid_json(self) -> None:
        with self.assertRaisesRegex(lockpin.LockError, "not valid JSON"):
            lockpin.parse_lock("{")

    def test_not_an_object(self) -> None:
        with self.assertRaisesRegex(lockpin.LockError, "not a JSON object"):
            lockpin.parse_lock("[]")


class MainTests(unittest.TestCase):
    def run_main(self, lock: object, entry: str) -> tuple[int, str, str]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lock.json"
            path.write_text(json.dumps(lock), encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = lockpin.main([str(path), entry])
        return code, out.getvalue(), err.getvalue()

    def test_prints_three_lines(self) -> None:
        code, out, _ = self.run_main(lock_with(), "tool")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), ["1.2.3", "https://example.com/tool-1.2.3.pyz", GOOD])

    def test_one_line_error(self) -> None:
        code, out, err = self.run_main(lock_with(), "nope")
        self.assertEqual((code, out), (1, ""))
        self.assertEqual(len(err.splitlines()), 1)
        self.assertIn("nope", err)

    def test_unreadable_lock(self) -> None:
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = lockpin.main(["/nonexistent/lock.json", "tool"])
        self.assertEqual(code, 1)

    def test_usage(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(lockpin.main([]), 2)


if __name__ == "__main__":
    unittest.main()
