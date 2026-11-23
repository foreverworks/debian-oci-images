"""renovate.json moves each archive's snapshot in lock.json, and both in one pull request."""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "renovate.json").read_text(encoding="utf-8"))
LOCK_TEXT = (ROOT / "lock.json").read_text(encoding="utf-8")
LOCK = json.loads(LOCK_TEXT)
ARCHIVES = {"debian": "debian-snapshot", "debian-security": "debian-security-snapshot"}


def managers_for(dep_name: str) -> list[dict[str, object]]:
    found = [m for m in CONFIG["customManagers"] if m.get("depNameTemplate") == dep_name]
    return [{str(key): value for key, value in m.items()} for m in found]


class SnapshotManagerTests(unittest.TestCase):
    def test_each_archive_has_one_manager_that_matches_only_its_line(self) -> None:
        for archive, dep_name in ARCHIVES.items():
            with self.subTest(archive=archive):
                found = managers_for(dep_name)
                self.assertEqual(len(found), 1)
                strings = found[0]["matchStrings"]
                assert isinstance(strings, list) and len(strings) == 1
                # Renovate's named groups are (?<name>...), Python's are (?P<name>...).
                pattern = re.compile(str(strings[0]).replace("(?<", "(?P<"))
                self.assertEqual(pattern.findall(LOCK_TEXT), [LOCK["debian_snapshots"][archive]])

    def test_each_manager_has_its_own_datasource_reading_its_own_feed_file(self) -> None:
        for dep_name in ARCHIVES.values():
            with self.subTest(dep_name=dep_name):
                self.assertEqual(managers_for(dep_name)[0]["datasourceTemplate"], f"custom.{dep_name}")
                source = CONFIG["customDatasources"][dep_name]
                self.assertTrue(source["defaultRegistryUrlTemplate"].endswith(f"/snapshot-feed/{dep_name}.json"))

    def test_both_snapshots_move_in_one_pull_request(self) -> None:
        groups = [rule for rule in CONFIG["packageRules"] if "debian-snapshot" in rule.get("matchDepNames", [])]
        self.assertEqual(len(groups), 1)
        self.assertEqual(sorted(groups[0]["matchDepNames"]), sorted(ARCHIVES.values()))
        self.assertTrue(groups[0]["groupName"])


class FeedFileNamesTests(unittest.TestCase):
    def test_the_workflow_writes_the_files_the_datasources_read(self) -> None:
        text = (ROOT / ".github" / "workflows" / "snapshot.yml").read_text(encoding="utf-8")
        for dep_name in ARCHIVES.values():
            self.assertIn(f"{dep_name}.json", text)


if __name__ == "__main__":
    unittest.main()
