#!/usr/bin/env python3
"""Read one pinned input of lock.json: its version, its download URL and its sha256.

Usage: lockpin.py LOCK ENTRY

Prints three lines: the version, the URL with {version} filled in, the sha256.
Exits 1 with one line on stderr when the entry is missing or unusable.
"""

import json
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import NamedTuple

SHA256_RE = re.compile(r"[0-9a-f]{64}")


class LockError(Exception):
    """The lock, or an entry of it, cannot be used."""


class Pin(NamedTuple):
    version: str
    url: str
    sha256: str


def parse_lock(text: str) -> dict[str, object]:
    """The lock's top-level object, or a LockError."""
    try:
        data: object = json.loads(text)
    except json.JSONDecodeError as error:
        raise LockError(f"the lock is not valid JSON: {error}") from error
    if not isinstance(data, dict):
        raise LockError("the lock is not a JSON object")
    return {str(key): value for key, value in data.items()}


def load_lock(path: Path) -> dict[str, object]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise LockError(f"cannot read the lock {path}: {error.strerror}") from error
    return parse_lock(text)


def get_entry(lock: Mapping[str, object], name: str) -> dict[str, object]:
    """The lock's input called `name`, or a LockError."""
    inputs = lock.get("inputs")
    if not isinstance(inputs, dict):
        raise LockError("the lock has no inputs object")
    entry = inputs.get(name)
    if not isinstance(entry, dict):
        raise LockError(f"the lock has no entry {name}")
    return {str(key): value for key, value in entry.items()}


def _text(entry: Mapping[str, object], name: str, key: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value:
        raise LockError(f"entry {name} has no {key}")
    return value


def render_url(template: str, version: str) -> str:
    """Fill {version}, the only placeholder an entry's url may carry."""
    url = template.replace("{version}", version)
    if "{" in url or "}" in url:
        raise LockError(f"url {template} has a placeholder other than {{version}}")
    return url


def pin_of(lock: Mapping[str, object], name: str) -> Pin:
    entry = get_entry(lock, name)
    version = _text(entry, name, "version")
    template = _text(entry, name, "url")
    sha256 = _text(entry, name, "sha256")
    url = render_url(template, version)
    if not url.startswith("https://"):
        raise LockError(f"entry {name} has a url that is not https: {url}")
    if SHA256_RE.fullmatch(sha256) is None:
        raise LockError(f"entry {name} has a malformed sha256: {sha256}")
    if set(sha256) == {"0"}:
        raise LockError(f"entry {name} has an all-zero sha256")
    return Pin(version, url, sha256)


def main(argv: Sequence[str]) -> int:
    if len(argv) != 2:
        print("usage: lockpin.py LOCK ENTRY", file=sys.stderr)
        return 2
    try:
        pin = pin_of(load_lock(Path(argv[0])), argv[1])
    except LockError as error:
        print(f"lockpin: {error}", file=sys.stderr)
        return 1
    print(pin.version)
    print(pin.url)
    print(pin.sha256)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
