import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import images

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
[images.node-22]
kind = "oci"
[images.node-24]
kind = "oci"
"""

LOCK: dict[str, object] = {
    "debian_snapshot": "20261121T203158Z",
    "inputs": {
        "node-26": {"version": "26.13.1", "url": "https://example.com/{version}", "sha256": "a" * 64},
        "node-24": {"version": "24.22.3", "url": "https://example.com/{version}", "sha256": "a" * 64},
        "node-22": {"version": "22.23.5", "url": "https://example.com/{version}", "sha256": "a" * 64},
    },
}

HEX = "0123456789abcdef" * 4
IDENTITY = "f" * 16


def definition() -> dict[str, object]:
    return images.parse_definition(DEFINITION)


class RepositoryTests(unittest.TestCase):
    def test_known(self) -> None:
        self.assertEqual(images.repository_of("debian"), "debian")
        self.assertEqual(images.repository_of("node-26"), "node")
        self.assertEqual(images.repository_of("node-8"), "node")

    def test_core_is_not_an_image(self) -> None:
        with self.assertRaisesRegex(images.ImageError, "release asset"):
            images.repository_of("core")

    def test_unknown(self) -> None:
        for name in ("node", "node-", "node-x", "node-26a", "python-3", "Debian", ""):
            with self.subTest(name=name), self.assertRaisesRegex(images.ImageError, "unknown image"):
                images.repository_of(name)


class TagTests(unittest.TestCase):
    def test_debian(self) -> None:
        self.assertEqual(
            images.tags_of("debian", LOCK, definition()),
            ["13", "trixie", "latest", "13-20261121T203158Z"],
        )

    def test_highest_node_is_lts_and_latest(self) -> None:
        self.assertEqual(
            images.tags_of("node-26", LOCK, definition()),
            ["26", "26.13.1", "26-trixie", "26.13.1-trixie", "lts", "latest"],
        )

    def test_older_node(self) -> None:
        self.assertEqual(
            images.tags_of("node-22", LOCK, definition()),
            ["22", "22.23.5", "22-trixie", "22.23.5-trixie"],
        )

    def test_unknown_suite(self) -> None:
        other = images.parse_definition(DEFINITION.replace("trixie", "forky"))
        with self.assertRaisesRegex(images.ImageError, "unknown Debian suite forky"):
            images.tags_of("debian", LOCK, other)

    def test_wrong_major_in_lock(self) -> None:
        lock: dict[str, object] = {
            "inputs": {"node-26": {"version": "25.1.0", "url": "https://example.com/{version}", "sha256": "a" * 64}}
        }
        with self.assertRaisesRegex(images.ImageError, "not a 26.x"):
            images.tags_of("node-26", lock, definition())

    def test_image_not_in_definition(self) -> None:
        with self.assertRaisesRegex(images.ImageError, "not in the definition"):
            images.tags_of("node-20", LOCK, definition())

    def test_core_and_unknown(self) -> None:
        with self.assertRaisesRegex(images.ImageError, "release asset"):
            images.tags_of("core", LOCK, definition())
        with self.assertRaisesRegex(images.ImageError, "unknown image"):
            images.tags_of("python", LOCK, definition())

    def test_missing_snapshot(self) -> None:
        with self.assertRaisesRegex(images.ImageError, "debian_snapshot"):
            images.tags_of("debian", {}, definition())


class LayoutNameTests(unittest.TestCase):
    def test_dashes_in_image(self) -> None:
        name = f"node-26-trixie-amd64-{IDENTITY}-{HEX[:12]}.oci"
        self.assertEqual(images.parse_layout_name(name), ("node-26", HEX[:12]))

    def test_plain(self) -> None:
        name = f"debian-trixie-amd64-{IDENTITY}-{HEX[:12]}.oci"
        self.assertEqual(images.parse_layout_name(name), ("debian", HEX[:12]))

    def test_bad_names(self) -> None:
        for name in (
            "debian.oci",
            f"debian-trixie-amd64-{IDENTITY}-{HEX[:12]}",
            f"debian-trixie-amd64-short-{HEX[:12]}.oci",
            f"debian-trixie-amd64-{IDENTITY}-xyz.oci",
            f"-trixie-amd64-{IDENTITY}-{HEX[:12]}.oci",
        ):
            with self.subTest(name=name), self.assertRaises(images.ImageError):
                images.parse_layout_name(name)


class ManifestDigestTests(unittest.TestCase):
    def test_one_manifest(self) -> None:
        text = json.dumps({"manifests": [{"digest": f"sha256:{HEX}"}]})
        self.assertEqual(images.manifest_digest(text, "x"), f"sha256:{HEX}")

    def test_bad_indexes(self) -> None:
        for text in (
            "{",
            "[]",
            json.dumps({"manifests": []}),
            json.dumps({"manifests": [{"digest": f"sha256:{HEX}"}, {"digest": f"sha256:{HEX}"}]}),
            json.dumps({"manifests": [{"digest": "md5:abc"}]}),
            json.dumps({"manifests": [{"digest": "sha256:abc"}]}),
            json.dumps({"manifests": [{}]}),
        ):
            with self.subTest(text=text), self.assertRaises(images.ImageError):
                images.manifest_digest(text, "x")


def make_layout(out: Path, image: str, hex_digest: str = HEX, records: bool = True) -> str:
    name = f"{image}-trixie-amd64-{IDENTITY}-{hex_digest[:12]}.oci"
    layout = out / name
    (layout / "blobs" / "sha256").mkdir(parents=True)
    (layout / "oci-layout").write_text('{"imageLayoutVersion":"1.0.0"}', encoding="utf-8")
    (layout / "index.json").write_text(
        json.dumps({"manifests": [{"digest": f"sha256:{hex_digest}"}]}), encoding="utf-8"
    )
    (layout / "blobs" / "sha256" / "blob").write_text(image, encoding="utf-8")
    if records:
        (out / f"{hex_digest}.intoto.jsonl").write_text("records", encoding="utf-8")
    return name


class LayoutsAndRepositoriesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.out = self.root / "out"
        self.out.mkdir()

    def test_layouts(self) -> None:
        debian = make_layout(self.out, "debian", "a" * 64)
        node = make_layout(self.out, "node-26", "b" * 64)
        (self.out / "core-trixie-amd64-x-y.tar.gz").write_text("not a layout", encoding="utf-8")
        self.assertEqual(
            images.read_layouts(self.out),
            [
                images.Layout("debian", "sha256:" + "a" * 64, debian, "a" * 64 + ".intoto.jsonl"),
                images.Layout("node-26", "sha256:" + "b" * 64, node, "b" * 64 + ".intoto.jsonl"),
            ],
        )

    def test_missing_records(self) -> None:
        make_layout(self.out, "debian", records=False)
        with self.assertRaisesRegex(images.ImageError, "records file"):
            images.read_layouts(self.out)

    def test_digest_prefix_mismatch(self) -> None:
        name = make_layout(self.out, "debian", "a" * 64)
        (self.out / name).rename(self.out / f"debian-trixie-amd64-{IDENTITY}-bbbbbbbbbbbb.oci")
        with self.assertRaisesRegex(images.ImageError, "name says digest"):
            images.read_layouts(self.out)

    def test_missing_index(self) -> None:
        name = make_layout(self.out, "debian")
        (self.out / name / "index.json").unlink()
        with self.assertRaisesRegex(images.ImageError, "index.json"):
            images.read_layouts(self.out)

    def test_not_a_directory(self) -> None:
        with self.assertRaisesRegex(images.ImageError, "not a directory"):
            images.read_layouts(self.root / "missing")

    def test_repositories_group_the_node_images(self) -> None:
        make_layout(self.out, "node-26", "b" * 64)
        make_layout(self.out, "debian", "a" * 64)
        make_layout(self.out, "node-24", "c" * 64)
        self.assertEqual(
            images.repositories(images.read_layouts(self.out)),
            [("debian", ["debian"]), ("node", ["node-24", "node-26"])],
        )

    def test_repositories_of_one_image(self) -> None:
        make_layout(self.out, "node-22")
        self.assertEqual(images.repositories(images.read_layouts(self.out)), [("node", ["node-22"])])

    def test_repositories_refuse_an_unknown_image(self) -> None:
        make_layout(self.out, "python")
        with self.assertRaisesRegex(images.ImageError, "unknown image"):
            images.repositories(images.read_layouts(self.out))


def plan_text(**states: dict[str, str]) -> str:
    return json.dumps({"images": states})


class PlanTests(unittest.TestCase):
    def test_changed(self) -> None:
        text = plan_text(core={"state": "reuse", "artifact": "sha256:" + "ab" * 32}, debian={"state": "build"})
        self.assertEqual(
            images.plan_lines(text), ["core reuse sha256:" + "ab" * 32, "debian build", "changed=true"]
        )

    def test_quiet(self) -> None:
        text = plan_text(core={"state": "reuse", "artifact": "sha256:" + "ab" * 32}, debian={"state": "wait", "artifact": "sha256:" + "cd" * 32})
        self.assertEqual(
            images.plan_lines(text),
            ["core reuse sha256:" + "ab" * 32, "debian wait sha256:" + "cd" * 32, "changed=false"],
        )

    def test_refusals(self) -> None:
        for text in (
            "{",
            "[]",
            "{}",
            json.dumps({"images": {}}),
            plan_text(core={"state": "fresh"}),
            plan_text(core={}),
            plan_text(core={"state": "reuse"}),
            plan_text(core={"state": "reuse", "artifact": "ab" * 32}),
            plan_text(core={"state": "reuse", "artifact": "sha256:" + "AB" * 32}),
        ):
            with self.subTest(text=text), self.assertRaises(images.ImageError):
                images.plan_lines(text)


class MainTests(unittest.TestCase):
    def run_main(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = images.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_repository(self) -> None:
        self.assertEqual(self.run_main("repository", "node-24"), (0, "node\n", ""))
        code, _, err = self.run_main("repository", "core")
        self.assertEqual(code, 1)
        self.assertIn("release asset", err)

    def test_tags_and_plan_and_layouts_and_repositories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "lock.json").write_text(json.dumps(LOCK), encoding="utf-8")
            (root / "factory.toml").write_text(DEFINITION, encoding="utf-8")
            code, out, _ = self.run_main(
                "tags", "node-24", "--lock", str(root / "lock.json"), "--definition", str(root / "factory.toml")
            )
            self.assertEqual((code, out.splitlines()), (0, ["24", "24.22.3", "24-trixie", "24.22.3-trixie"]))
            (root / "plan.json").write_text(plan_text(debian={"state": "build"}), encoding="utf-8")
            self.assertEqual(self.run_main("plan", str(root / "plan.json"))[1], "debian build\nchanged=true\n")
            outdir = root / "out"
            outdir.mkdir()
            name = make_layout(outdir, "debian")
            code, out, _ = self.run_main("layouts", str(outdir))
            self.assertEqual(out, f"debian sha256:{HEX} {name} {HEX}.intoto.jsonl\n")
            code, out, _ = self.run_main("repositories", str(outdir))
            self.assertEqual((code, out), (0, "debian debian\n"))
            self.assertEqual(self.run_main("plan", str(root / "none.json"))[0], 1)


if __name__ == "__main__":
    unittest.main()
