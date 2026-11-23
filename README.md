# Debian and Node.js base images you can check

Pull a minimal Debian 13 (trixie) or Node.js (22, 24 or 26) base image from `ghcr.io/foreverworks`,
pin it by digest in your `FROM` line, and check, from the image alone, which packages are inside,
what they were built from and what was tested.

> **Latest release: v0.1.0**, published on 2026-11-22. It is the only release so far. The workflows
> that turn a new Debian snapshot or Node.js version into a release are in this repository and running,
> but no update has gone through them yet (see [How updates arrive](#how-updates-arrive)).

## Who it is for

Use these images when you ship containers and want to know, and be able to prove to someone else,
what your base layer holds. Every image carries a software bill of materials (SBOM), a build
provenance record and test results, and its digest is signed.

Use Docker Hub's official [`debian`](https://hub.docker.com/_/debian) or
[`node`](https://hub.docker.com/_/node) instead when you need any of these:

- an architecture other than `linux/amd64`. These images are amd64 only today;
- a `node` user, `yarn`, an entrypoint script or the `slim` and `alpine` variants. The official `node`
  image has them (it is built on `buildpack-deps`, which also brings `curl`, `git` and compilers). These
  images have none of them;
- a Node.js line this project does not carry, such as the Current line (27, in alpha) or one that has
  reached its end of life;
- another Debian release, such as bookworm;
- a project with a long track record and a large maintainer team. This one is young and has one
  release.

## What you need

- Docker, or another OCI runtime, on `linux/amd64`. The images are public: no login, no cost.
- To verify them: `git`, `curl`, `sha256sum` and Python 3.13 or newer for the records (step 2 below),
  and [`cosign`](https://github.com/sigstore/cosign) 3.x for the signatures (step 1 and the factory
  check in step 2). [`oras`](https://oras.land) is optional: it only lists the records (step 3) and
  resolves a digest, which `docker` can do too.

## Quick start

```sh
docker pull ghcr.io/foreverworks/node:26
docker run --rm ghcr.io/foreverworks/node:26 node --version
# v26.13.1

docker run --rm ghcr.io/foreverworks/debian:13 cat /etc/os-release
# PRETTY_NAME="Debian GNU/Linux 13 (trixie)"
# ...
```

The Node.js images start `node`: `docker run -it ghcr.io/foreverworks/node:26` opens the REPL. To run a
script, name `node` and the script: `docker run --rm -v "$PWD":/app -w /app ghcr.io/foreverworks/node:26
node script.js`. The Debian image starts `/bin/bash`.

### Pin by digest

A tag moves when a release is published. A digest never does. Read the digest of a tag with Docker, or
with `oras resolve`:

```sh
docker buildx imagetools inspect ghcr.io/foreverworks/node:26 --format '{{.Manifest.Digest}}'
# sha256:dc55ea94c04ec98e231340ade2174bbf3a95fc6682d5323c3cfb3da38f066fd0
```

The digests of release v0.1.0, as the registry held them on 2026-11-23:

| Image | Digest |
|---|---|
| `ghcr.io/foreverworks/debian:13` | `sha256:d0afc5fc4678a6bd3ea206abcadbd1664d32397322732795a1737609168c0ab0` |
| `ghcr.io/foreverworks/node:26` | `sha256:dc55ea94c04ec98e231340ade2174bbf3a95fc6682d5323c3cfb3da38f066fd0` |
| `ghcr.io/foreverworks/node:24` | `sha256:fa9faffbbbdec8755287d209b61763b3c9a877f6e09408b314087657ee244070` |
| `ghcr.io/foreverworks/node:22` | `sha256:c1731b13bede2f569813af5e1c78360c2ad074bbd759205e20bfd23db0e533c5` |

Put the digest after the tag in your Dockerfile. Docker uses the digest and ignores the tag, which is
only a label for the people who read the file:

```dockerfile
FROM ghcr.io/foreverworks/node:26@sha256:dc55ea94c04ec98e231340ade2174bbf3a95fc6682d5323c3cfb3da38f066fd0

# The package lists are empty in the image: run apt-get update before an install.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

# The images run as root. 65534 is the `nobody` user that Debian ships.
WORKDIR /app
COPY --chown=65534:65534 server.js .
USER 65534:65534
CMD ["node", "server.js"]
```

A dependency bot such as Renovate or Dependabot can keep a pinned `FROM` line current: it opens a pull
request when a new release moves the tag to another digest.

## Tags

| Image | Tags |
|---|---|
| `debian` | `13`, `trixie`, `latest`, and `13-<debian>-<security>` for the two Debian snapshots it was built at: the main archive's first, then the security archive's (`13-20261121T203158Z-20261121T005332Z`) |
| `node` | `<major>` (`26`), `<version>` (`26.13.1`), `<major>-trixie`, `<version>-trixie`. The newest LTS line also has `lts` and `latest` |
| every image | `identity-<64 hex>`: the factory's own tag, derived from every input of the build |

Tags move only when a release is published, and only to builds whose required checks all passed. Tags
are for finding an image. Pin what you deploy by digest.

The registry also holds `sha256-<hex>` tags. They are not images: each is an index of the records and
the signature of the image with that digest (the OCI fallback for referrers). `cosign` and `oras` read
them for you.

## How long a line is supported

| Image | Line | Upstream support ends | Source |
|---|---|---|---|
| `debian` | Debian 13 (trixie) | security support 2028-08-09, then Debian LTS until 2030-06-30 | [debian.org/releases](https://www.debian.org/releases/) |
| `node` | 26 (Lithium, active LTS since 2026-10-28) | 2029-04-30 | [nodejs/release schedule](https://github.com/nodejs/release/blob/main/schedule.json) |
| `node` | 24 (Krypton, maintenance LTS) | 2028-04-30 | same |
| `node` | 22 (Jod, maintenance LTS) | 2027-04-30 | same |

An image line is carried while upstream supports it. A Node.js line is added when it becomes LTS and
removed on its end-of-life date, so `node:22` stops receiving releases after 2027-04-30. A line in
its Current phase has no image. The Debian image is rebuilt only from Debian's own archive, so it can
carry a fix only for as long as Debian publishes fixes for trixie. When a new Debian release becomes the
base is a maintainers' decision that is not scheduled here. Details are in [DESIGN.md](DESIGN.md#3-versions).

Only the latest release of each line is supported. [SECURITY.md](SECURITY.md) says how to report a
problem.

## What is in the image, and what is not

**`debian`** is Debian 13 reduced to what `apt` needs, plus `ca-certificates` and `tzdata`: 72 Debian
packages in one layer of about 114 MB. It includes `bash`, `apt`, `perl`, `tar` and `gzip`. It sets
`LANG=C.UTF-8` and starts `/bin/bash`. Its `apt` sources are Debian's main archive, `trixie-updates` and
`trixie-security`, with the package lists left out, so run `apt-get update` first.

**`node`** is that image plus the Node.js release from nodejs.org, unpacked in `/usr/local`, with the
`npm` and `npx` that come with it, and one more Debian package, `libatomic1`, which the `node` binary
links against: 73 Debian packages in all. It starts `node`. The Node.js tarball is checked at build time
against the signature Node.js publishes for it.

Not in either image:

- `curl`, `wget`, `git`, a compiler, `make`, `python3`, `ps`, `sudo`. Install what you need with `apt-get`;
  it then appears in the SBOM of your own image;
- `useradd` and `adduser` (install the `passwd` package for `useradd`), and any user besides the
  system ones. The images run as `root`, as the official Debian image does: set `USER` in your own
  Dockerfile;
- `yarn`, `corepack`, and a Node.js `node` user;
- anything for another architecture.

## Verify

Run these steps against a digest you resolved above. The first shows who pushed the image, the second
checks the records, the third lists them.

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

The factory that builds the images also checks them. Download its `.pyz`, check it, and run it from a
checkout of this repository at the release tag (v0.1.0 here, and the factory is v0.6.3):

```sh
git clone --depth 1 --branch v0.1.0 https://github.com/foreverworks/debian-oci-images
cd debian-oci-images
base=https://github.com/foreverworks/debian-image-factory/releases/download/v0.6.3
curl -fsSLO $base/debian-image-factory-0.6.3.pyz
curl -fsSLO $base/debian-image-factory-0.6.3.pyz.sigstore.json
sha256sum debian-image-factory-0.6.3.pyz   # a2dab6168fd098e19c7b3aba6b3029c25f9e770484b47b1fcc1158d2e5965c62, the sha256 in lock.json
cosign verify-blob debian-image-factory-0.6.3.pyz \
  --bundle debian-image-factory-0.6.3.pyz.sigstore.json \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  --certificate-identity https://github.com/foreverworks/debian-image-factory/.github/workflows/release.yml@refs/tags/v0.6.3
python3 debian-image-factory-0.6.3.pyz verify \
  oci://ghcr.io/foreverworks/node@sha256:<digest> \
  --pull --require-checks --lock lock.json --definition factory.toml
```

`--pull` downloads the whole image and checks every layer against its digest. It needs only Python and
the network: no `cosign`, no `oras`. The command then checks
that the records are about exactly these bits, that there is exactly one provenance and it names this
repository's `lock.json` by sha256, that there is exactly one SBOM, and that every check the
definition requires has a passing result. It names every problem it finds and exits 1, or prints a
short summary and exits 0. For `node:26` it printed:

```
oci://ghcr.io/foreverworks/node@sha256:dc55...fd0: verified
  node-26 identity bf7e097f...b798: 10 records (1 provenance, 1 SBOM, 8 test results)
  lock.json sha256:4e8d1abae496ea4389e6e9bf2876cd01fd9d12bb5ff493df8639012fd5bd14e0
  required checks all passing: ancestry, locked-inputs, no-build-snapshot, no-machine-identity, oci-run, package-set, sbom-complete, two-clones
```

The `lock.json` and `factory.toml` must be the ones of the release that built the digest. For a later
release, check out its tag.

### 3. List the records

```sh
oras discover ghcr.io/foreverworks/node@sha256:<digest>
```

This shows the provenance, the SBOM, the test results and the signature attached to the image. The
records are DSSE envelopes of in-toto Statements; `oras pull` fetches them if you want to read them.

### What each record proves, and what it does not

| Record | Proves | Does not prove |
|---|---|---|
| SBOM (SPDX 2.3) | Which packages and locked inputs are in the image. A check compares it with what is installed. | That the packages are free of vulnerabilities. |
| Provenance (SLSA v1) | Which lock, snapshot, recipe, parent and builder produced the image. | More than SLSA Build level 1. The build wrote this record itself, and the build platform did not. |
| Test results | Each named check passed on exactly this image: the package set matches the plan, no machine identity or secret is baked in, the image runs, and more. | Anything about checks that are not listed. |
| Signature on the digest | That this repository's release workflow pushed this digest. | That the workflow was free of mistakes: read it. |

Two limits are worth knowing:

- **The records are unsigned for now.** The release publishes them
  without a signature, and the registry's authentication is what protects them. What is signed today is
  the image manifest digest. Signing the records too is not switched on yet
  ([DESIGN.md, section 7](DESIGN.md#7-signing-and-records)).
- **The images are not promised to be byte-for-byte reproducible.** The build is deterministic in its
  inputs: the same lock gives the same package set, and a test checks it. A second build is not
  promised to give the same digest. The identity tag says "same inputs", and the digest says "these
  bytes".

SLSA Build L1 means the provenance exists and says what the build used. Build L2 needs a build platform
that generates and signs the provenance on its own, and L3 needs a hardened, isolated platform. The
factory's own wording is in its
[DESIGN, section 8.3](https://github.com/foreverworks/debian-image-factory/blob/v0.8.0/DESIGN.md).

## What you can check, and where it comes from

- **Which packages?** Every installed package and every other input is listed in an SPDX 2.3 software
  bill of materials attached to the image.
- **From where?** Debian packages come from dated snapshots of snapshot.debian.org, one for the main
  archive and one for the security archive, each pinned in its own right. Every input,
  down to the Node.js tarball, is named with its checksum in [`lock.json`](lock.json).
- **Built how?** A SLSA provenance record names the lock by its sha256, the two snapshots, the recipe, the
  parent image and the builder.
- **Tested how?** One test result per check is attached. The checks run on the built image, and the
  Node.js one compares the version with the lock.
- **Was the Node.js tarball genuine?** Every tarball is checked at fetch against Node.js's signed
  `SHASUMS256.txt.asc`, with the release keyring pinned in the lock.

## How updates arrive

A new image reaches you in three steps: an input changes, a release is built and published, and you move
your pin.

- **Debian updates.** The main archive and the security archive are pinned apart, each at its own
  snapshot, because the security archive changes several times a day and the main one about every six
  hours. A workflow plans the newest snapshot of each against what the last release
  published. It is scheduled every hour and also runs within a minute or two when an outside poller
  reports a change, naming the snapshot it saw so that the plan does not wait for snapshot.debian.org's
  listing cache. GitHub starts scheduled runs when it can, and in a quiet repository it starts them
  less often than asked, so the poller is the dependable path. When a Debian upload (often a security
  fix) changes one of the images, Renovate opens one pull request that moves the lock to both snapshots.
  Snapshots that touch none of their packages change nothing.
- **Node.js and the rest.** Renovate also opens a pull request for each new Node.js patch or minor
  version inside a supported line, for a new factory release and for the pinned GitHub Actions. A
  workflow then commits the new checksums to Renovate's branch. Renovate never moves a line to the
  next major version.
- **Every Renovate pull request merges itself once CI passes**, and CI builds and tests every image.
  Nothing merges on a red check. Pull requests from people are merged by a maintainer.
- **Every merge that changes an input is released.** A workflow tags the merge with the next patch
  version, and the release workflow builds and tests everything, publishes, verifies what it pushed,
  signs it, and only then moves the tags. A maintainer can still tag a release by hand.
- **Tags move only to builds that passed.** If a check fails, the old tag stays where it is.
- **A nightly build** plans at the newest snapshots, builds only the images whose inputs changed, and
  keeps the result in a cache. It never publishes: it shows that the next release would build and pass
  its checks.

Between a fix and a release, the images you already pulled are unchanged. When a release is published,
the tags move and your pinned digest stays: update the pin to take the new image. You can watch this
repository's releases on GitHub (Watch, Custom, Releases) to hear about each one.

What has run so far: release v0.1.0 was tagged by hand. The hourly check, the pull requests and the
automatic release were added after it, and no update has yet gone through them, so none has been
measured. [DESIGN.md, section 6](DESIGN.md#6-workflows) has the details.

## Build it yourself

You need Docker, Python 3.13 or newer, `apt`, `gpgv`, Debian's archive keyring (the
`debian-archive-keyring` package, at `/usr/share/keyrings/debian-archive-keyring.pgp`), `curl` and
`sha256sum`, and `cosign` if you want the factory's signatures checked too. The factory runs the build in a container
with no network, using Debian's own tools from a pinned snapshot.

```sh
git clone https://github.com/foreverworks/debian-oci-images
cd debian-oci-images
scripts/factory install                 # downloads the pinned factory and checks its sha256
scripts/factory plan --out plan.json    # which images need building: on a first run, all five (core, debian, node-22, -24, -26)
scripts/factory fetch plan.json         # downloads and verifies every input
scripts/factory build plan.json --out out/   # in the builder that builder.ref pins by digest
scripts/factory test out/               # runs the built-in checks on every image
scripts/factory verify out/node-26-trixie-amd64-*.oci --require-checks --lock lock.json --definition factory.toml
```

`scripts/factory` refuses any factory bytes other than the ones in `lock.json`, and passes everything
else to it. The factory's [command line reference](https://github.com/foreverworks/debian-image-factory/blob/v0.8.0/DESIGN.md)
(section 9.1) lists every option. The factory builds everything from this repository's definition, and
nothing here runs a package script on your machine outside the builder container.

The builder runs package scripts as root in a privileged container. Under a rootful Docker, that is
root on the host. Build on a machine, or a CI runner, that you do not mind running those scripts on.

`scripts/check` runs this repository's own checks (shellcheck, mypy, the unit tests, the policy check,
actionlint if installed, and a lock check). It needs `shellcheck` and `mypy`, which
`requirements-dev.txt` pins for `pip install --require-hashes`.

## What is in this repository

| File | Role |
|---|---|
| `factory.toml` | The images: kinds, parents, start command, labels. No versions. |
| `lock.json` | Every version and checksum: the two Debian snapshots, the factory, each Node.js tarball, the release keyring. |
| `builder.ref` | The builder image, by digest. |
| `scripts/` | Small glue around the factory, and the checks that keep this repository honest. |
| `.github/workflows/` | CI, the nightly plan, the snapshot check, the automatic release and the release itself. |
| [DESIGN.md](DESIGN.md) | Why it is built this way. |
| [SECURITY.md](SECURITY.md) | How to report a vulnerability. |

The factory is [debian-image-factory](https://github.com/foreverworks/debian-image-factory). It decides
the package sets, the identities and the records. This repository only says which images to build.

## Questions and problems

Ask or report a bug in [the issues](https://github.com/foreverworks/debian-oci-images/issues). Report a
vulnerability privately, as [SECURITY.md](SECURITY.md) describes.

## License

[MIT](LICENSE). The images contain software under other licenses: Debian's packages carry theirs in
`/usr/share/doc/<package>/copyright`, and Node.js is under its own license.
