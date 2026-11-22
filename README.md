# Debian and Node.js images you can check

Public Debian 13 (trixie) and Node.js base images, built from pinned inputs, with a software bill of
materials, build provenance and test results attached to every image.

> **Status: nothing is published yet.** The first release is pending. The images below will appear at
> `ghcr.io/foreverworks/debian` and `ghcr.io/foreverworks/node` when the first release tag is
> approved. Until then, everything here describes what the release will do, and you can build the
> images yourself (see [Build it yourself](#build-it-yourself)).

## The problem

A base image is the thing every other layer stands on, and most of them cannot be audited. If you ask
which packages are inside, where they came from, how the image was built and what was tested before it
was published, the honest answer is usually "trust the publisher". A Node.js image is worse: the
tarball it contains came from somewhere, and nobody has to say whether it was checked against the
signature Node.js publishes for it.

These images answer those questions in a form a machine can check:

- **Which packages?** Every installed package and every other input is listed in an SPDX 2.3 software
  bill of materials attached to the image.
- **From where?** Debian packages come from one dated snapshot of snapshot.debian.org. Every input,
  down to the Node.js tarball, is named with its checksum in [`lock.json`](lock.json).
- **Built how?** A SLSA provenance record names the lock by its sha256, the snapshot, the recipe, the
  parent image and the builder.
- **Tested how?** One test result per check is attached: the package set matches the plan, no machine
  identity or secret is baked in, the image runs, the Node.js version equals the lock, and more.
- **Was the Node.js tarball genuine?** Every tarball is checked at fetch against Node.js's signed
  `SHASUMS256.txt.asc`, with the release keyring pinned in the lock.

## What you get

| Image | Pull | Contents |
|---|---|---|
| `ghcr.io/foreverworks/debian` | `13`, `trixie`, `latest` | Debian 13 with `apt`, `ca-certificates` and `tzdata`, in one layer. Starts `/bin/bash`. |
| `ghcr.io/foreverworks/node` | `26`, `lts`, `latest` | Node.js 26 (Lithium, the active LTS line) in `/usr/local`. Starts `node`. |
| `ghcr.io/foreverworks/node` | `24` | Node.js 24 (Krypton, maintenance LTS, supported until 2028-04-30). |
| `ghcr.io/foreverworks/node` | `22` | Node.js 22 (Jod, maintenance LTS, supported until 2027-04-30). |

All images are `linux/amd64`. The factory that builds them supports only amd64 today, and it keeps
the architecture in every image identity so others can follow; arm64 is later work.

Every supported Node.js LTS line has an image. A line is added when it becomes LTS and removed on its
end-of-life date. A line still in its Current phase gets none. The reasoning is in
[DESIGN.md](DESIGN.md#3-versions).

The images run as `root` by default, as the official Debian image does. Set `USER` in your own
Dockerfile for anything that does not need root.

### Tags

| Image | Tags |
|---|---|
| debian | `13`, `trixie`, `latest`, `13-<snapshot>` (for example `13-20261121T203158Z`) |
| node | `<major>` (for example `26`), `<version>` (`26.13.1`), `<major>-trixie`, `<version>-trixie`; the newest LTS also `lts` and `latest` |
| every image | `identity-<64 hex>`: the factory's own tag, derived from every input of the build |

Tags move only when a release is published, and only to builds whose required checks all passed.
Tags are for discovery. Pin what you deploy by digest.

## Pull

By tag, to try it:

```sh
docker pull ghcr.io/foreverworks/node:26
docker run --rm ghcr.io/foreverworks/node:26 node --version
```

By digest, for anything you ship:

```sh
oras resolve ghcr.io/foreverworks/node:26
# sha256:...
docker pull ghcr.io/foreverworks/node@sha256:<digest>
```

In a Dockerfile:

```dockerfile
FROM ghcr.io/foreverworks/node:26@sha256:<digest>
```

The tag in front of the digest is only a label for people. Docker uses the digest.

## Verify

You need [`cosign`](https://github.com/sigstore/cosign), and for the records
[`oras`](https://oras.land) and Python 3.13 or newer. Use any `<digest>` you resolved above.

### 1. The signature

The release signs each image's manifest digest with Sigstore, keyless, from the release workflow of this
repository. The certificate identity names that workflow at a release tag, so an image pushed by any
other workflow, branch or fork does not verify.

```sh
cosign verify ghcr.io/foreverworks/node@sha256:<digest> \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  --certificate-identity-regexp '^https://github\.com/foreverworks/debian-oci-images/\.github/workflows/release\.yml@refs/tags/v[0-9]'
```

### 2. The records

The records are checked by the factory itself. Take its `.pyz` from the
[v0.6.2 release](https://github.com/foreverworks/debian-image-factory/releases/tag/v0.6.2), check its
sha256 against `lock.json` in this repository and its Sigstore bundle, then, from a checkout of
this repository at the release tag:

```sh
sha256sum debian-image-factory-0.6.2.pyz   # f718b927fac4a3159cf75a62e3ce657a9c87e851fc5097b553198b360534ce00
cosign verify-blob debian-image-factory-0.6.2.pyz \
  --bundle debian-image-factory-0.6.2.pyz.sigstore.json \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  --certificate-identity https://github.com/foreverworks/debian-image-factory/.github/workflows/release.yml@refs/tags/v0.6.2
python3 debian-image-factory-0.6.2.pyz verify \
  oci://ghcr.io/foreverworks/node@sha256:<digest> \
  --pull --require-checks --lock lock.json --definition factory.toml
```

`--pull` downloads the whole image and checks every layer against its digest. The command then checks
that the records are about exactly these bits, that there is exactly one provenance and it names this
repository's `lock.json` by sha256, that there is exactly one SBOM, and that every check the
definition requires has a passing result. It names every problem it finds and exits 1, or prints a
short summary and exits 0.

### 3. List the records

```sh
oras discover ghcr.io/foreverworks/node@sha256:<digest>
```

This shows the provenance, the SBOM and the test results attached to the image. They are DSSE
envelopes of in-toto Statements; `oras pull` fetches them if you want to read them.

## What each record proves, and what it does not

| Record | Proves | Does not prove |
|---|---|---|
| SBOM (SPDX 2.3) | Which packages and locked inputs are in the image. A check compares it with what is installed. | That the packages are free of vulnerabilities. |
| Provenance (SLSA v1) | Which lock, snapshot, recipe, parent and builder produced the image. | More than SLSA Build level 1. The build wrote this record itself, and the build platform did not. |
| Test results | Each named check passed on exactly this image. | Anything about checks that are not listed. |
| Signature on the digest | That this repository's release workflow pushed this digest. | That the workflow was free of mistakes: read it. |

Two limits are worth knowing:

- **The records are unsigned for now.** The factory release these images use (v0.6.2) writes records
  without a signature, and the registry's authentication is what protects them. What is signed today is
  the image manifest digest. Signed records need a later factory release
  ([DESIGN.md, section 7](DESIGN.md#7-signing-and-records)).
- **The images are not promised to be byte-for-byte reproducible.** The build is deterministic in its
  inputs: the same lock gives the same package set, and a test checks it. A second build is not
  promised to give the same digest. The identity tag says "same inputs", and the digest says "these
  bytes".

SLSA Build L1 means the provenance exists and says what the build used. Build L2 needs a build platform
that generates and signs the provenance on its own, and L3 needs a hardened, isolated platform. The
factory's own wording is in its
[DESIGN, section 8.3](https://github.com/foreverworks/debian-image-factory/blob/v0.6.2/DESIGN.md).

## How the images stay current

- **Nightly.** A scheduled workflow plans at the newest Debian snapshot and builds only the images
  whose inputs changed. A quiet night builds nothing. Nightly builds go to a cache and are never pushed
  to `ghcr.io`: they exist to show that the next release would build and pass its checks.
- **Renovate** opens a pull request for each new Node.js patch or minor version inside a supported line,
  and for a new factory release. It never moves a line to the next major version.
- **Releases are deliberate.** A person creates a version tag. The release workflow builds and tests
  everything, publishes, verifies what it pushed, signs it, and only then moves the tags. Debian
  security updates reach the images through the snapshot the nightly plan found, in the next release.
- **Tags move only to builds that passed.** If a check fails, the old tag stays where it is.

[DESIGN.md, section 6](DESIGN.md#6-workflows) has the details.

## Build it yourself

You need Docker, Python 3.13 or newer, `apt` and `gpgv`. The factory runs the build in a container
with no network, using Debian's own tools from a pinned snapshot.

```sh
git clone https://github.com/foreverworks/debian-oci-images
cd debian-oci-images
scripts/factory install                 # downloads the pinned factory and checks its sha256
scripts/factory plan --out plan.json    # which images need building, at the lock's snapshot
scripts/factory fetch plan.json         # downloads and verifies every input
scripts/factory build plan.json --out out/   # in the builder that builder.ref pins by digest
scripts/factory test out/               # runs the built-in checks on every image
scripts/factory verify out/node-26-trixie-amd64-*.oci --require-checks --lock lock.json --definition factory.toml
```

`scripts/factory` refuses any factory bytes other than the ones in `lock.json`, and passes everything
else to it. The factory's [command line reference](https://github.com/foreverworks/debian-image-factory/blob/v0.6.2/DESIGN.md)
(section 9.1) lists every option. The factory builds everything from this repository's definition, and
nothing here runs a package script on your machine outside the builder container.

The builder runs package scripts as root in a privileged container. Under a rootful Docker, that is
root on the host. Build on a machine, or a CI runner, that you do not mind running those scripts on.

## What is in this repository

| File | Role |
|---|---|
| `factory.toml` | The images: kinds, parents, start command, labels. No versions. |
| `lock.json` | Every version and checksum: the Debian snapshot, the factory, each Node.js tarball, the release keyring. |
| `builder.ref` | The builder image, by digest. |
| `scripts/` | Small glue around the factory, and the checks that keep this repository honest. |
| `.github/workflows/` | CI, the nightly plan and the release. |
| [DESIGN.md](DESIGN.md) | Why it is built this way. |
| [SECURITY.md](SECURITY.md) | How to report a vulnerability. |

The factory is [debian-image-factory](https://github.com/foreverworks/debian-image-factory). It decides
the package sets, the identities and the records. This repository only says which images to build.

## License

[MIT](LICENSE). The images contain software under other licenses: Debian's packages carry theirs in
`/usr/share/doc/<package>/copyright`, and Node.js is under its own license.
