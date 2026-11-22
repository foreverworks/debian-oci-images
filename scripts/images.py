#!/usr/bin/env python3
"""What the factory built, and where each image goes.

Usage:
  images.py repository IMAGE
  images.py tags IMAGE --lock lock.json --definition factory.toml
  images.py layouts OUT
  images.py stage OUT STAGE
  images.py plan PLAN

`stage` is INTERIM. It exists because factory `publish` pushes every layout of an output directory to
each target, with no way to select images (factory gap 1). It goes away when `publish` can select
images: the release then publishes debian and node-* to their repositories with the factory itself.
"""

import argparse
import json
import os
import re
import sys
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import NamedTuple

import lockpin

DEBIAN_MAJOR = {"trixie": "13"}
"""Debian suite to major version. A suite not listed here is refused, so a new release is added on purpose."""

NODE_IMAGE_RE = re.compile(r"node-([0-9]+)")
HEX_RE = re.compile(r"[0-9a-f]+")
PLAN_STATES = ("build", "reuse", "wait")


class ImageError(Exception):
    """An image name, a definition or an output directory that cannot be used."""


class Layout(NamedTuple):
    image: str
    manifest_digest: str  # "sha256:<hex>"
    directory: str  # the layout directory's name inside OUT
    records: str  # the records file's name inside OUT


def repository_of(image: str) -> str:
    """The repository an image is published to: debian, or node for every node-<N>."""
    if image == "core":
        raise ImageError("core is not an OCI image: it publishes as a release asset")
    if image == "debian":
        return "debian"
    if NODE_IMAGE_RE.fullmatch(image):
        return "node"
    raise ImageError(f"unknown image {image}: no repository for it")


def parse_definition(text: str) -> dict[str, object]:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ImageError(f"the definition is not valid TOML: {error}") from error


def load_definition(path: Path) -> dict[str, object]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ImageError(f"cannot read the definition {path}: {error.strerror}") from error
    return parse_definition(text)


def definition_images(definition: Mapping[str, object]) -> dict[str, dict[str, object]]:
    """The definition's [images.*] tables by name."""
    table = definition.get("images")
    if not isinstance(table, dict):
        raise ImageError("the definition has no images table")
    result: dict[str, dict[str, object]] = {}
    for name, body in table.items():
        if not isinstance(body, dict):
            raise ImageError(f"image {name} is not a table")
        result[str(name)] = {str(key): value for key, value in body.items()}
    return result


def suite_of(definition: Mapping[str, object]) -> str:
    """The Debian suite, which must be one DEBIAN_MAJOR knows."""
    section = definition.get("debian")
    suite = section.get("suite") if isinstance(section, dict) else None
    if not isinstance(suite, str):
        raise ImageError("the definition has no debian.suite")
    if suite not in DEBIAN_MAJOR:
        raise ImageError(f"unknown Debian suite {suite}: add it to DEBIAN_MAJOR")
    return suite


def node_majors(definition: Mapping[str, object]) -> list[int]:
    """The N of every node-<N> image of the definition, ascending."""
    majors: list[int] = []
    for name in definition_images(definition):
        match = NODE_IMAGE_RE.fullmatch(name)
        if match:
            majors.append(int(match.group(1)))
    return sorted(majors)


def node_version(lock: Mapping[str, object], image: str, major: int) -> str:
    version = lockpin.pin_of(lock, image).version
    if version.split(".")[0] != str(major):
        raise ImageError(f"lock entry {image} is version {version}, not a {major}.x release")
    return version


def tags_of(
    image: str, lock: Mapping[str, object], definition: Mapping[str, object]
) -> list[str]:
    """The friendly tags of an image, in a fixed order. The identity tag is the factory's own."""
    suite = suite_of(definition)
    if image == "debian":
        snapshot = lock.get("debian_snapshot")
        if not isinstance(snapshot, str) or not snapshot:
            raise ImageError("the lock has no debian_snapshot")
        debian_major = DEBIAN_MAJOR[suite]
        return [debian_major, suite, "latest", f"{debian_major}-{snapshot}"]
    match = NODE_IMAGE_RE.fullmatch(image)
    if match is None:
        repository_of(image)  # names the problem for core and for unknown images
        raise ImageError(f"unknown image {image}")
    major = int(match.group(1))
    if major not in node_majors(definition):
        raise ImageError(f"image {image} is not in the definition")
    version = node_version(lock, image, major)
    tags = [str(major), version, f"{major}-{suite}", f"{version}-{suite}"]
    if major == max(node_majors(definition)):
        tags += ["lts", "latest"]
    return tags


def parse_layout_name(name: str) -> tuple[str, str]:
    """(image, digest12) of `<image>-<suite>-<arch>-<identity16>-<digest12>.oci`, parsed from the right."""
    if not name.endswith(".oci"):
        raise ImageError(f"{name} is not a layout directory name")
    parts = name[: -len(".oci")].rsplit("-", 4)
    if len(parts) != 5 or not parts[0]:
        raise ImageError(f"{name} does not look like <image>-<suite>-<arch>-<identity16>-<digest12>.oci")
    image, _suite, _arch, identity, digest12 = parts
    if len(identity) != 16 or HEX_RE.fullmatch(identity) is None:
        raise ImageError(f"{name} has no 16 hex digit identity")
    if len(digest12) != 12 or HEX_RE.fullmatch(digest12) is None:
        raise ImageError(f"{name} has no 12 hex digit digest")
    return image, digest12


def manifest_digest(index_text: str, where: str) -> str:
    """The digest of the one manifest an OCI layout's index.json lists."""
    try:
        index: object = json.loads(index_text)
    except json.JSONDecodeError as error:
        raise ImageError(f"{where}: index.json is not valid JSON: {error}") from error
    manifests = index.get("manifests") if isinstance(index, dict) else None
    if not isinstance(manifests, list) or len(manifests) != 1:
        raise ImageError(f"{where}: index.json must list exactly one manifest")
    entry = manifests[0]
    digest = entry.get("digest") if isinstance(entry, dict) else None
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        raise ImageError(f"{where}: the manifest has no sha256 digest")
    hex_part = digest[len("sha256:") :]
    if len(hex_part) != 64 or HEX_RE.fullmatch(hex_part) is None:
        raise ImageError(f"{where}: malformed manifest digest {digest}")
    return digest


def read_layouts(out: Path) -> list[Layout]:
    """Every OCI layout directory of OUT, by name."""
    if not out.is_dir():
        raise ImageError(f"{out} is not a directory")
    layouts: list[Layout] = []
    for path in sorted(out.iterdir()):
        if not (path.is_dir() and path.name.endswith(".oci")):
            continue
        image, digest12 = parse_layout_name(path.name)
        try:
            index_text = (path / "index.json").read_text(encoding="utf-8")
        except OSError as error:
            raise ImageError(f"{path.name}: cannot read index.json: {error.strerror}") from error
        digest = manifest_digest(index_text, path.name)
        hex_part = digest[len("sha256:") :]
        if not hex_part.startswith(digest12):
            raise ImageError(f"{path.name}: the name says digest {digest12} but the manifest is {digest}")
        records = f"{hex_part}.intoto.jsonl"
        if not (out / records).is_file():
            raise ImageError(f"{path.name}: its records file {records} is missing")
        layouts.append(Layout(image, digest, path.name, records))
    return layouts


def _link_tree(source: Path, target: Path) -> None:
    for directory, subdirectories, files in os.walk(source):
        relative = Path(directory).relative_to(source)
        for name in subdirectories:
            (target / relative / name).mkdir(parents=True)
        (target / relative).mkdir(parents=True, exist_ok=True)
        for name in files:
            os.link(Path(directory) / name, target / relative / name, follow_symlinks=False)


def stage(out: Path, stage_dir: Path) -> list[tuple[str, Path]]:
    """One directory per repository under stage_dir, made of hard links to the layouts of OUT."""
    if stage_dir.exists() and (not stage_dir.is_dir() or any(stage_dir.iterdir())):
        raise ImageError(f"{stage_dir} exists and is not empty")
    layouts = read_layouts(out)
    placed = [(repository_of(layout.image), layout) for layout in layouts]
    stage_dir.mkdir(parents=True, exist_ok=True)
    repositories: dict[str, Path] = {}
    for repository, layout in placed:
        directory = repositories.setdefault(repository, stage_dir / repository)
        directory.mkdir(exist_ok=True)
        _link_tree(out / layout.directory, directory / layout.directory)
        os.link(out / layout.records, directory / layout.records)
    for directory in repositories.values():
        if (out / "plan.json").is_file():
            os.link(out / "plan.json", directory / "plan.json")
    return sorted(repositories.items())


def plan_lines(plan_text: str) -> list[str]:
    """`<image> <state> [<artifact>]` per image in plan order, then changed=true|false."""
    try:
        plan: object = json.loads(plan_text)
    except json.JSONDecodeError as error:
        raise ImageError(f"the plan is not valid JSON: {error}") from error
    table = plan.get("images") if isinstance(plan, dict) else None
    if not isinstance(table, dict) or not table:
        raise ImageError("the plan has no images")
    lines: list[str] = []
    changed = False
    for name, body in table.items():
        state = body.get("state") if isinstance(body, dict) else None
        if state not in PLAN_STATES:
            raise ImageError(f"image {name} has an unknown state {state!r}")
        if state == "build":
            changed = True
            lines.append(f"{name} {state}")
            continue
        artifact = body.get("artifact") if isinstance(body, dict) else None
        if not isinstance(artifact, str) or not artifact:
            raise ImageError(f"image {name} is {state} but the plan names no artifact")
        lines.append(f"{name} {state} {artifact}")
    lines.append(f"changed={'true' if changed else 'false'}")
    return lines


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="images.py")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("repository").add_argument("image")
    tags = commands.add_parser("tags")
    tags.add_argument("image")
    tags.add_argument("--lock", type=Path, default=Path("lock.json"))
    tags.add_argument("--definition", type=Path, default=Path("factory.toml"))
    commands.add_parser("layouts").add_argument("out", type=Path)
    staging = commands.add_parser("stage")
    staging.add_argument("out", type=Path)
    staging.add_argument("stage", type=Path)
    commands.add_parser("plan").add_argument("plan", type=Path)
    return parser


def run(arguments: argparse.Namespace) -> list[str]:
    command: str = arguments.command
    if command == "repository":
        return [repository_of(arguments.image)]
    if command == "tags":
        lock = lockpin.load_lock(arguments.lock)
        return tags_of(arguments.image, lock, load_definition(arguments.definition))
    if command == "layouts":
        return [
            f"{layout.image} {layout.manifest_digest} {layout.directory} {layout.records}"
            for layout in read_layouts(arguments.out)
        ]
    if command == "stage":
        return [f"{name} {directory}" for name, directory in stage(arguments.out, arguments.stage)]
    try:
        text = arguments.plan.read_text(encoding="utf-8")
    except OSError as error:
        raise ImageError(f"cannot read the plan {arguments.plan}: {error.strerror}") from error
    return plan_lines(text)


def main(argv: Sequence[str]) -> int:
    arguments = _build_parser().parse_args(argv)
    try:
        lines = run(arguments)
    except (ImageError, lockpin.LockError) as error:
        print(f"images: {error}", file=sys.stderr)
        return 1
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
