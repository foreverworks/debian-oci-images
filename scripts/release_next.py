#!/usr/bin/env python3
"""Whether main holds inputs no release has published yet, and the version tag that releases them.

Usage:
  release_next.py pending [REV]   prints pending=true|false
  release_next.py next [REV]      prints tag=vX.Y.Z and new=true|false, or tag= when there is nothing to release

REV defaults to HEAD. The inputs are the files the images are built from (INPUTS): a commit that
changes none of them since the newest version tag has nothing to release. The next version moves the
patch number of the newest tag (new=true). A commit that already carries a version tag gives that tag
with new=false, so a run whose dispatch failed after the tag was made can start the release again.
REV must descend from the newest version tag: an older commit is refused, so a re-run of an old push
never releases older inputs over newer images.

Runs git in the current directory, which must be a clone holding the tags.
"""

import re
import subprocess
import sys
from collections.abc import Iterable, Sequence

# What an image is built from. Everything else (the workflows, the scripts' tests, the docs) changes
# no image, so a merge that touches only those releases nothing.
INPUTS = ("lock.json", "factory.toml", "builder.ref")

VERSION_RE = re.compile(r"v(?P<major>0|[1-9][0-9]*)\.(?P<minor>0|[1-9][0-9]*)\.(?P<patch>0|[1-9][0-9]*)")


class ReleaseError(Exception):
    """The tags or the history cannot answer."""


def version_of(tag: str) -> tuple[int, int, int] | None:
    match = VERSION_RE.fullmatch(tag)
    if match is None:
        return None
    return int(match["major"]), int(match["minor"]), int(match["patch"])


def newest(tags: Iterable[str]) -> str | None:
    """The highest vMAJOR.MINOR.PATCH among tags; other tags are ignored."""
    versions = [(version, tag) for tag in tags if (version := version_of(tag)) is not None]
    return max(versions)[1] if versions else None


def bump(tag: str) -> str:
    version = version_of(tag)
    if version is None:
        raise ReleaseError(f"{tag} is not vMAJOR.MINOR.PATCH")
    major, minor, patch = version
    return f"v{major}.{minor}.{patch + 1}"


def git(*arguments: str) -> str:
    result = subprocess.run(["git", *arguments], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ReleaseError(f"git {' '.join(arguments)}: {result.stderr.strip()}")
    return result.stdout


def inputs_changed(since: str, rev: str) -> bool:
    return git("diff", "--name-only", since, rev, "--", *INPUTS).strip() != ""


def pending(rev: str) -> bool:
    last = newest(git("tag", "--list", "v*").split())
    if last is None:
        raise ReleaseError("no version tag yet: the first release is made by hand")
    return inputs_changed(last, rev)


def descends_from(ancestor: str, rev: str) -> bool:
    result = subprocess.run(["git", "merge-base", "--is-ancestor", ancestor, rev], capture_output=True, check=False)
    if result.returncode not in (0, 1):
        raise ReleaseError(f"git merge-base --is-ancestor {ancestor} {rev}: {result.stderr.decode().strip()}")
    return result.returncode == 0


def next_tag(rev: str) -> tuple[str, bool] | None:
    """(tag, new): the version tag that releases rev, and whether it still has to be created."""
    own = newest(git("tag", "--list", "v*", "--points-at", rev).split())
    if own is not None:
        return own, False
    last = newest(git("tag", "--list", "v*").split())
    if last is None:
        raise ReleaseError("no version tag yet: the first release is made by hand")
    if not descends_from(last, rev):
        raise ReleaseError(f"{rev} does not descend from {last}, the newest release")
    if not inputs_changed(last, rev):
        return None
    return bump(last), True


def main(argv: Sequence[str]) -> int:
    if len(argv) not in (1, 2) or argv[0] not in ("pending", "next"):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    rev = argv[1] if len(argv) == 2 else "HEAD"
    try:
        if argv[0] == "pending":
            print(f"pending={'true' if pending(rev) else 'false'}")
        else:
            found = next_tag(rev)
            print(f"tag={found[0]}\nnew={'true' if found[1] else 'false'}" if found else "tag=\nnew=false")
    except ReleaseError as error:
        print(f"release_next: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
