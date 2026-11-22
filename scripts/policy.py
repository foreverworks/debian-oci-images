#!/usr/bin/env python3
"""This repository's own rules, checked line by line (no YAML library).

Usage: policy.py [ROOT]     (ROOT defaults to the current directory)

Rules:
- every `uses:` of a workflow or action is `owner/repo[/path]@<40 hex> # v<version>`, or a local ./ path;
- every `runs-on:` is exactly ubuntu-26.04, and nothing mentions self-hosted or
  github.event.repository.private;
- no `${{` expression inside a `run:` (pass values through env: instead);
- builder.ref names the tag v<lock's factory version> and a sha256 digest;
- every node-<N> image of factory.toml has a lock entry node-<N> of Node.js N, used by that image only;
- every oci image of factory.toml has a repository to be published to.
- a `<scope>: write` permission appears only in the publish job of release.yml.

Prints every problem found and exits 1, or prints nothing and exits 0.
"""

import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import images
import lockpin

USES_RE = re.compile(r"^\s*(?:-\s+)?uses:\s*(.*?)\s*$")
PINNED_RE = re.compile(
    r"""^(?P<ref>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_./-]+)?@[0-9a-f]{40})\s+\#\s+v[0-9][0-9A-Za-z.+-]*$"""
)
RUNS_ON_RE = re.compile(r"""^\s*(?:-\s+)?runs-on:\s*(['"]?)([^'"#\s]*)\1\s*(?:#.*)?$""")
RUN_KEY_RE = re.compile(r"^(?P<lead>\s*(?:-\s+)?)run:\s*(?P<value>.*?)\s*$")
BLOCK_SCALAR_RE = re.compile(r"^[|>][-+0-9]*\s*(?:#.*)?$")
RUNNER = "ubuntu-26.04"
FORBIDDEN = ("self-hosted", "github.event.repository.private")
BUILDER_REF_RE = re.compile(r"^(?P<repo>[^@\s]+):(?P<tag>[^:@/\s]+)@sha256:(?P<hex>[0-9a-f]{64})$")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


WRITE_RE = re.compile(r"^\s*(?P<scope>[a-z-]+):\s*write(?:-all)?\s*(?:#.*)?$")
JOB_RE = re.compile(r"^  (?P<job>[A-Za-z0-9_-]+):\s*(?:#.*)?$")
WRITER = ("release.yml", "publish")  # the one job that may hold a write permission


def check_write_permissions(name: str, text: str) -> list[str]:
    """A `<scope>: write` permission anywhere but the publish job of release.yml. The jobs that build run
    package scripts as root, so they must never hold a token that writes (DESIGN.md, section 6)."""
    problems: list[str] = []
    in_jobs = False
    job: str | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        if line and not line.startswith((" ", "#")):
            in_jobs = line.rstrip() == "jobs:"
            job = None
        found = JOB_RE.match(line) if in_jobs else None
        if found:
            job = found.group("job")
            continue
        write = WRITE_RE.match(line)
        if write and (Path(name).name, job) != WRITER:
            where = "top level" if job is None else f"job {job}"
            problems.append(
                f"{name}:{number}: {write.group('scope')}: write in {where}: only the publish job of release.yml may write"
            )
    return problems


def check_workflow(name: str, text: str) -> list[str]:
    """Problems in one workflow or action file, as `name:line: message`."""
    problems: list[str] = check_write_permissions(name, text)
    lines = text.splitlines()
    block_indent: int | None = None  # the key column of the run: block we are inside
    for number, line in enumerate(lines, start=1):
        where = f"{name}:{number}"
        for word in FORBIDDEN:
            if word in line:
                problems.append(f"{where}: {word} is not allowed")
        if block_indent is not None:
            if not line.strip() or _indent(line) > block_indent:
                if "${{" in line:
                    problems.append(f"{where}: a ${{{{ }}}} expression inside run: pass it through env: instead")
                continue
            block_indent = None
        uses = USES_RE.match(line)
        if uses and not line.lstrip().startswith("#"):
            value = uses.group(1)
            if not (value.startswith("./") or PINNED_RE.match(value)):
                problems.append(f"{where}: uses: {value} is not owner/repo@<40 hex> # v<version> or a ./ path")
        if RUNS_ON_RE.match(line):
            if RUNS_ON_RE.sub(r"\2", line) != RUNNER:
                problems.append(f"{where}: runs-on must be exactly {RUNNER}")
        elif re.match(r"^\s*(?:-\s+)?runs-on:", line):
            problems.append(f"{where}: runs-on must be exactly {RUNNER}")
        run = RUN_KEY_RE.match(line)
        if run:
            value = run.group("value")
            if BLOCK_SCALAR_RE.match(value):
                block_indent = len(run.group("lead"))
            elif "${{" in value:
                problems.append(f"{where}: a ${{{{ }}}} expression inside run: pass it through env: instead")
    return problems


def check_builder_ref(text: str, lock: Mapping[str, object]) -> list[str]:
    """builder.ref has the factory's version as its tag and a sha256 digest."""
    ref = text.strip()
    match = BUILDER_REF_RE.match(ref)
    if match is None:
        return ["builder.ref is not <repository>:v<version>@sha256:<64 hex>"]
    try:
        version = lockpin.pin_of(lock, "debian-image-factory").version
    except lockpin.LockError as error:
        return [f"builder.ref cannot be compared with the lock: {error}"]
    if match.group("tag") != f"v{version}":
        return [f"builder.ref tag {match.group('tag')} is not v{version}, the factory version in the lock"]
    return []


def check_definition(definition: Mapping[str, object], lock: Mapping[str, object]) -> list[str]:
    """factory.toml and lock.json agree about the Node.js images, and every oci image has a repository."""
    problems: list[str] = []
    try:
        table = images.definition_images(definition)
    except images.ImageError as error:
        return [str(error)]
    for name, body in table.items():
        if body.get("kind") == "oci":
            try:
                images.repository_of(name)
            except images.ImageError as error:
                problems.append(str(error))
        match = images.NODE_IMAGE_RE.fullmatch(name)
        if match is None:
            continue
        try:
            entry = lockpin.get_entry(lock, name)
        except lockpin.LockError as error:
            problems.append(str(error))
            continue
        version = entry.get("version")
        if not isinstance(version, str) or version.split(".")[0] != match.group(1):
            problems.append(f"lock entry {name} is version {version}, not a {match.group(1)}.x release")
        if entry.get("used_by") != [name]:
            problems.append(f"lock entry {name} must be used_by exactly [{name}]")
    return problems


def workflow_files(root: Path) -> list[Path]:
    github = root / ".github"
    found = [*github.glob("workflows/*.yml"), *github.glob("workflows/*.yaml")]
    found += [*github.glob("actions/**/action.yml"), *github.glob("actions/**/action.yaml")]
    return sorted(found)


def check_repository(root: Path) -> list[str]:
    problems: list[str] = []
    for path in workflow_files(root):
        problems += check_workflow(str(path.relative_to(root)), path.read_text(encoding="utf-8"))
    try:
        lock = lockpin.load_lock(root / "lock.json")
        definition = images.load_definition(root / "factory.toml")
        problems += check_definition(definition, lock)
        problems += check_builder_ref((root / "builder.ref").read_text(encoding="utf-8"), lock)
    except (lockpin.LockError, images.ImageError, OSError) as error:
        problems.append(str(error))
    return problems


def main(argv: Sequence[str]) -> int:
    if len(argv) > 1:
        print("usage: policy.py [ROOT]", file=sys.stderr)
        return 2
    problems = check_repository(Path(argv[0] if argv else "."))
    for problem in problems:
        print(f"policy: {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
