# Security policy

## Reporting a vulnerability

Please report it privately, not in a public issue or pull request. Use GitHub's private vulnerability
reporting on this repository: open the **Security** tab, choose **Report a vulnerability**, and describe
what you found, how to reproduce it and which image tag or digest, or which file, it affects.

You will get an answer here. If the report is valid, the fix is released and the advisory published
once images carrying the fix are available.

## What is in scope

- the definitions and inputs: `factory.toml`, `lock.json` and `builder.ref`;
- the workflows in `.github/workflows/` and the scripts in `scripts/`, including anything that could let
  a pull request, a fork or a tag run with more permission than it should, or move a tag to a build that
  did not pass its checks;
- the contents of the published images (`ghcr.io/foreverworks/debian` and `ghcr.io/foreverworks/node`)
  as far as they are the result of this repository's choices: a secret or machine identity baked in,
  a layer that does not match its records, an input that is not what the lock names;
- the records and signatures attached to the images: a record that does not describe the image it is
  attached to, or a signature that verifies when it should not.

## What is not in scope

- **A vulnerability in a Debian package** belongs to Debian. Report it through the
  [Debian security process](https://www.debian.org/security/faq#contact) so every user gets the fix.
- **A vulnerability in Node.js** belongs to Node.js. Report it through the
  [Node.js security policy](https://github.com/nodejs/node/blob/main/SECURITY.md).
- **A vulnerability in the factory** (the tool that does the building) belongs in
  [its repository](https://github.com/foreverworks/debian-image-factory).
- Findings that need an attacker who already controls the machine that runs the image.

## How fixes reach the images

Fixed Debian security updates reach the images on their own. Every hour a workflow plans the
newest snapshot of the Debian main archive and of the Debian security archive against the published
images; when an upload changes one of them, Renovate opens a pull request that moves the lock to both
snapshots. The security archive is pinned on its own, and snapshot.debian.org records it each time it
changes, so a security fix reaches a pull request within minutes of its snapshot when an outside poller
reports it, and within the hour otherwise. The pull request merges itself once CI has built and tested
every image, and the merge is released at once: published, verified, signed, then tagged. A new Node.js
patch release takes the same path through its own Renovate pull request. Release v0.1.0 was tagged by
hand and no update has gone through this path yet, so the time from a snapshot to a release is not
measured. GitHub may start a scheduled run later than asked; an outside poller also starts the check
when upstream changes. Nothing merges on a red check.

Between a fix and a release, the images you already pulled are unchanged. Pin by digest, and update your
pin when a release is published.

## Verifying what you run

Each image's digest is signed and carries a software bill of materials, build provenance and test results.
The [README](README.md#verify) shows how to check all of them.

## Supported versions

The latest release of each image line described in the [README](README.md#how-long-a-line-is-supported):
`debian` (Debian 13) and `node` 22, 24 and 26. A Node.js line is removed on its upstream end-of-life
date, and older releases get no fixes.
