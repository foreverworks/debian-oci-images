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

Fixed Debian security updates reach the images through the nightly snapshot plan: the nightly workflow
plans at the newest Debian snapshot and builds the images whose package set changed. A release then moves
the lock to that snapshot and publishes the images and their tags, signed. A new Node.js patch release is
picked up through a Renovate pull request and the same release process.

Between a fix and a release, the images you already pulled are unchanged. Pin by digest, and update your
pin when a release is published.

## Verifying what you run

Each image's digest is signed and carries a software bill of materials, build provenance and test results.
The [README](README.md#verify) shows how to check all of them.

## Supported versions

The latest release of each image line described in the README. Node.js lines that have reached their
upstream end-of-life date are removed.
