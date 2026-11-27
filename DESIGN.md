# Design

This document is for maintainers and reviewers. It says what the repository holds, why the images are
what they are, and what is deliberately temporary. For what the images give you and how to check them,
see the [README](README.md). The factory that does the building is
[debian-image-factory](https://github.com/foreverworks/debian-image-factory), pinned here at v0.8.0; its
sections are cited as "factory DESIGN n".

**Status.** Built and live: the four images (`debian`, `node` 22, 24 and 26) published by release v0.1.0
with their SBOM, provenance and test records and a signature on every image digest; the hourly Debian
snapshot check, the Renovate pull requests that merge themselves, and the release that follows a merge
(section 6). Not built: arm64 images, signed records and releases that reuse images (sections 8 and 9).
Release v0.1.0 was tagged by hand and no update has been released automatically yet.

## 1. Purpose and non-goals

The purpose is to publish a small set of Debian 13 (trixie) and Node.js images that a stranger can
audit: what is in them, where it came from, how it was built and what was tested, each answered by a
record attached to the image.

This repository holds only:

- the definition, `factory.toml`;
- the lock, `lock.json`, with the builder reference `builder.ref`;
- small glue scripts, their checks, the workflows and the docs.

Non-goals:

- **No second build system.** The factory decides package sets, input identities, the SBOM, the
  provenance and the test records. Nothing here resolves a package, writes a layer or composes a
  record. If a behaviour is missing, the fix goes into the factory (section 8), and this repository
  carries an interim glue script that is marked as such and removed when the factory catches up.
- **No images for Node.js lines before they reach LTS** (the Current phase), no application images and no variants (slim,
  alpine, with build tools). Every image has to be worth auditing, and each one costs a nightly build.
- **No byte-for-byte reproducibility promise.** The inputs are reproducible; the output digest is not
  promised to be.
- **No own signing keys.** Signing is keyless, through the workflow's OIDC identity.

## 2. Images and why these

| Image | Kind | Parent | Published as |
|---|---|---|---|
| `core` | rootfs tarball | none | a GitHub release asset of the version tag, with its records |
| `debian` | OCI, one layer | `core` | `ghcr.io/foreverworks/debian` |
| `node-26`, `node-24`, `node-22` | OCI | `debian` | `ghcr.io/foreverworks/node` |

**The minimal base.** `core` is `mmdebstrap --variant=apt` plus two packages that the definition names:

- `apt` (from the variant): an image people cannot extend with `apt-get install` is an image they will
  replace with a larger one. The variant has no more than apt needs.
- `ca-certificates`: without it no program can verify a TLS server, and every user would add it as the
  first line of their Dockerfile. Adding it here once is smaller than being asked for it a thousand times.
- `tzdata`: time zones are data, and a program that is given `TZ=Europe/Berlin` should not silently run
  in UTC. It is small and has no code.

Nothing else is in it: no shell tools beyond what the variant brings, no `curl`, no compilers. A user who
needs more extends the image and gets that package's record in their own SBOM.

**`debian` equals `core`.** The OCI image has exactly one layer, and that layer is core's tarball byte for
byte. So the OCI image and the release asset describe the same bits, the `ancestry` check can compare them
by digest, and there is no step between "the rootfs we tested" and "the layer you pull". Its command is
`/bin/bash` and it sets `LANG=C.UTF-8`.

**Node.js from nodejs.org tarballs, not Debian's `nodejs` package.** Debian packages one Node.js
major for a whole release and keeps it for the life of that release, while upstream cuts new majors on its own
schedule, promotes them to LTS in October and supports each LTS line for about two and a half years. An image
for "the active LTS" and one for each maintenance LTS that upstream still supports needs the upstream builds. The cost is that the
tarball is not covered by Debian's archive signature, so the factory's `builtin:node-tarball` module
checks it at fetch against Node.js's signed `SHASUMS256.txt.asc`, with the release keyring pinned in
the lock (`node-release-keys`, a commit of `nodejs/release-keys` with its sha256). The tarball is
unpacked into `/usr/local`, the place Debian leaves free for local software. The Node.js image therefore
has two sources, Debian for the base and Node.js for the runtime, and the SBOM and the `locked-inputs`
check name both.

**Root, and `node` as the command.** The default user is root, as in the official Debian image. A
non-root default would be a promise about every downstream use that a base image cannot keep: file
ownership in bind mounts, binding low ports, installing packages. A user who wants non-root says so in
the next Dockerfile. The Node.js images set `node` as the default command, with no entrypoint:
`docker run -it image` opens the REPL, and a script runs as `docker run image node script.js`.

## 3. Versions

**Node.js policy.** Every Node.js LTS line still supported upstream has an image. A line is added by
hand when it becomes LTS (in October of its year), and removed on its end-of-life date, from the
[nodejs/release schedule](https://github.com/nodejs/release). A line in its Current phase gets no image.
From Node.js 27 on, upstream makes every major an LTS line (the schedule gives 27 LTS on 2027-10-20),
so "even numbers only" is not a rule here: the schedule is.

State at 2026-11-22:

| Line | Codename | Status | Version in the lock | End of life |
|---|---|---|---|---|
| 26 | Lithium | active LTS (the first `lts` entry of `https://nodejs.org/dist/index.json`, read 2026-11-22) | 26.13.1 | 2029-04-30 |
| 24 | Krypton | maintenance LTS | 24.22.3 | 2028-04-30 |
| 22 | Jod | maintenance LTS | 22.23.5 | 2027-04-30 |

Adding and removing a line is a manual, reviewed change: a block in `factory.toml`, an entry in
`lock.json`, and the tag rules. It is not automated, because the decision to carry a line is a support
commitment, and because the end of life of a line is a date a person should notice and not a version
string a bot can compare. The highest line is the one tagged `lts` and `latest`.

**Debian snapshots.** `debian_snapshots` in the lock pins the two archives apart: `debian` (today
`20261121T203158Z`) and `debian-security` (`20261121T005332Z`). Packages are resolved at the pair. The two
are separate because snapshot.debian.org records the main archive about every six hours and the security
archive each time it changes, often several times a day: one shared ID would make a security fix wait for
the slower archive's next snapshot, or hold the main archive at a time it never had. Each ID is usable as
soon as its own archive lists it. The pair moves by `lock snapshot --latest`, or one archive at a time by
`lock snapshot --id debian-security=ID`, and a move changes the identity of every image whose package set
changed, so only those rebuild (factory DESIGN 7). Debian security updates reach the images this way: the
snapshot check (section 6) looks at the newest snapshot of each archive, and one pull request moves the
lock to both.

**Renovate rules:**

- patch and minor versions of Node.js inside a line are opened as pull requests;
  majors are never proposed, because a new line is a decision (above);
- the `debian-image-factory` entry moves by the `github-releases` datasource, and the pull request
  must also move `builder.ref` to the same release (section 4);
- GitHub Actions are pinned by commit, with the version as a comment, and Renovate bumps both;
- `node-release-keys` has no datasource. It is a trust root and moves by hand, as a reviewed diff.

A Renovate change merges itself once CI passes, and the release that follows is described in section 6.

## 4. The lock and how the factory is pinned

`lock.json` is the single source of every version and checksum (factory DESIGN 6.1). `factory.toml`
holds no versions, so a version has one home.

**The factory itself.** The `debian-image-factory` entry names the release (0.8.0), the URL of its `.pyz`
and its sha256 `dc742777...82a3`. `scripts/factory install` downloads that file and refuses any other
bytes. The `.pyz` is the only code that runs the build, so its checksum is the root of the chain.

**The builder.** The factory builds in a container image. `builder.ref` is one line, a reference with the
tag for readers and the digest for the machine:

```
ghcr.io/foreverworks/debian-image-factory-builder:v0.8.0@sha256:e8afb458...6b9f
```

`scripts/policy.py` checks that its tag equals the factory version in the lock, so one pull request moves
both and the two never drift. The line goes away when the `.pyz` pins its own builder (factory DESIGN
5.4, planned).

**Verified, not trusted.** Both the `.pyz` and the builder are signed keyless by the factory's release
workflow. Anyone can check them with the identity
`https://github.com/foreverworks/debian-image-factory/.github/workflows/release.yml@refs/tags/v<version>`
and the issuer `https://token.actions.githubusercontent.com`. The builder reference was verified this way
with cosign 3.1.4 when it was pinned.

**Why the factory's GitHub Action is not used.** In v0.8.0 the Action builds its builder from the
factory's own checkout and has no input to name another one. This repository wants the published builder,
by digest, so it cannot use the Action: `scripts/factory` calls the `.pyz` directly. When the `.pyz` pins
its builder (section 8, gap 2), the Action can be used, and `builder.ref` and `scripts/factory` go away.

## 5. Repositories and tags

| Image | Where |
|---|---|
| `debian` | `ghcr.io/foreverworks/debian` |
| `node-26`, `node-24`, `node-22` | `ghcr.io/foreverworks/node` |
| `core` | a release asset of the version tag, with its `<sha256>.intoto.jsonl` records |

**Tags.**

- every image: `identity-<64 hex>`, the factory's own tag, derived from every input of the build.
  It is how the plan asks a registry "is this already built?" (factory DESIGN 7.4);
- `debian`: `13`, `trixie`, `latest`, and `13-<debian>-<security>`, the two snapshot IDs the image was
  built at, for example `13-20261121T203158Z-20261121T005332Z`;
- `node`, for each line N: `N`, `<version>`, `N-trixie` and `<version>-trixie`; the highest N also gets
  `lts` and `latest`.

**Who moves them, and when.** Only `release.yml`, and only after the image's required checks have all
passed, its records verify and its digest is signed (section 6). Nothing else, a person included, moves a
friendly tag. The identity tag is not friendly: it names one set of inputs. While the release rebuilds the
whole chain (section 6, release.yml), a release that rebuilds an image whose inputs did not change pushes a new
digest under the same identity tag: the bytes differ only in the commit annotation (factory DESIGN 5.3).

**Why `latest` and `lts` are both on the newest LTS.** Users who pick no tag get the newest supported
line, and users who want "whatever is LTS" get it. A major that stops being the active LTS loses these
two tags and keeps `N` and its version tags.

**Pull by digest.** The README tells users to pin digests. Tags exist so people can find an image and
read its name.

## 6. Workflows

All jobs run on GitHub-hosted `ubuntu-26.04` runners, and every Action is pinned by its full commit SHA
with the version in a comment. Pull requests from forks run only after a maintainer approves them (the repository requires approval
for every outside contributor, a repository setting) and get a read-only token;
no secret is available to them. The build runs package scripts in a privileged container (the factory
runs the build in a container with no network; under a rootful Docker, `--privileged` is root on the host,
factory DESIGN 5.4). The runner is a throwaway machine, and the one job that holds a write token never
runs a build.

Four other jobs may write, each only the scopes `scripts/policy.py` allows it, and none runs a build:

- `checksums` in `renovate-checksums.yml` (`contents`, `actions`). It runs only `actions/checkout` and the
  pinned input-lock Action, never this repository's scripts or a package's, and it runs only on pushes to
  Renovate's branches and commits only to the branch it was started on. It needs `actions` to dispatch
  `ci.yml` on that branch.
- `tag` in `release-next.yml` (`contents`, `actions`), on `main` only. It runs `git` and
  `scripts/release_next.py`, creates one version tag and dispatches `release.yml` on it.
- `feed` in `snapshot.yml` (`contents`). It checks nothing out; it force-pushes one orphan
  commit holding `debian-snapshot.json` and `debian-security-snapshot.json` to the branch `snapshot-feed`.
- `ask-renovate` in `snapshot.yml` (`issues`). It checks nothing out; it ticks the "run again" box of
  Renovate's Dependency Dashboard issue.

**How an update reaches the images.** Every update is a pull request that merges itself once CI passes,
and every merge that changes an input (`lock.json`, `factory.toml`, `builder.ref`) is released:

1. Renovate opens the pull request: a Node.js version, a factory release (its `.pyz` in the lock and
   its builder in `builder.ref`, together), a pinned Action, or the Debian snapshots (`snapshot.yml`
   below). `renovate-checksums.yml` commits new checksums to the branch and dispatches CI on it.
2. Renovate enables GitHub's auto-merge (`platformAutomerge`). The ruleset `protect main` requires both
   CI jobs, so the pull request merges only when the static checks and the build and test of every
   image pass on its last commit.
3. Renovate's merge is a push to `main` by its App, which starts `ci.yml` and `release-next.yml`.
   `release-next.yml` tags the merge with the next patch version when an input changed, and dispatches
   `release.yml` on that tag (a tag the workflow token creates starts no workflow by itself). Only the
   head of `main` releases, and only a commit that descends from the newest release.

When something stops halfway:

- The tag was made but the dispatch failed: re-run `release-next.yml` on `main`; it finds the tag on the
  commit and dispatches again, unless the tag already has its GitHub release.
- The release failed: re-run its failed jobs (every step before the tags move is idempotent). Until a
  release of the newest inputs succeeds, `snapshot.yml` skips its plan and says so in its summary.
- A factory release whose builder image is not yet in the registry when Renovate looks gives a pull
  request that moves only the `.pyz`. `scripts/policy.py` fails it (builder.ref must name the same
  version), so it waits, red, until Renovate's next run adds the builder.
- Action bumps wait three days after their release (`minimumReleaseAge`); image inputs do not.

### ci.yml

On every push to `main` and every pull request:

1. static checks: `scripts/check` (section 10);
2. build and test every image from the lock's snapshots, with nothing published: `plan` with no
   `--against`, `fetch`, `build`, `test`, then `verify --require-checks` on every layout, one `verify`
   per image, side by side.

The two jobs do not depend on each other, so they run side by side.

CI shows that the definition, the lock and the scripts build the images and that every check passes. It
holds a read-only token.

### nightly.yml

On a schedule and on demand. It plans at the **newest** snapshot of each archive against a target that persists in the
Actions cache: a local zot registry on `127.0.0.1` for the OCI images and a `dir://` directory for
`core`. It builds and tests what changed, "publishes" only that into the cache, and prunes the cache. A child
that builds alone (a Node.js bump, with `debian` reused) reads its parent from the cache for both `build`
and `test`, so its `ancestry` check runs and the child passes and is kept as good.

- A quiet night (no relevant Debian upload, no new Node.js release) gives `changed=false` and builds
  nothing, at the cost of a few index downloads.
- It never publishes to `ghcr.io` and never moves a tag. Its role is to tell a maintainer, by a failing run,
  that the next release would not build or pass.
- It does not move the lock: `snapshot.yml` and Renovate do.

### snapshot.yml

Every hour, on demand, and when told that something changed. One read-only job plans at the **newest**
snapshot of each archive against what the last release published: `oci://ghcr.io/foreverworks/debian`,
`oci://ghcr.io/foreverworks/node` and the core tarball on the newest GitHub release. The plan is
`scripts/plan-snapshots`, which runs the factory's `plan --snapshot latest` and reads the two IDs it used
from `plan.json` (`snapshots`). `changed=true` means a release now would build something new: a Debian
upload touched a package of an image. A second job then writes the two IDs to `debian-snapshot.json` and
`debian-security-snapshot.json` on the branch `snapshot-feed`, in one orphan commit and only when either
file does not already hold its ID. Renovate reads each file as its own custom datasource
(`debian-snapshot`, `debian-security-snapshot`) and turns them into one pull request, because one
package rule groups them, that moves both lines of `debian_snapshots` in the lock. A third job ticks the
Dependency Dashboard's "run again" box, so Renovate reads the feed at once instead of on its own schedule.

The branch must exist before the first run, holding both files with the lock's two IDs: without the
files Renovate reports `no-result` for the datasource on the dashboard, and a pull request could move one
archive alone. Seed it with one orphan commit right after the change that introduces
`debian-security-snapshot.json` lands on `main` (an earlier run of the old workflow would otherwise write
a branch with the main archive's file only):

```sh
git init --initial-branch=snapshot-feed seed && cd seed
printf '{"releases": [{"version": "%s"}]}\n' "$DEBIAN_ID" > debian-snapshot.json
printf '{"releases": [{"version": "%s"}]}\n' "$SECURITY_ID" > debian-security-snapshot.json
git add . && git commit -m "Debian snapshots $DEBIAN_ID and $SECURITY_ID"
git push --force https://github.com/foreverworks/debian-oci-images snapshot-feed
```

`DEBIAN_ID` and `SECURITY_ID` are the two values of `debian_snapshots` in the lock at that moment.

What starts it. The hourly schedule is the fallback and needs nobody to call it. An outside poller that
watches upstream starts it within a minute or two of a change, with a `repository_dispatch` event of type
`upstream-changed` or a `workflow_dispatch`. Both carry four optional keys (`client_payload` or the
inputs): `source` (`debian`, `node` or `manual`), `snapshot` (the newest completed snapshot the caller
saw, `YYYYMMDDTHHMMSSZ`), `archive` (`debian` or `debian-security`: the archive that snapshot belongs to,
`debian-security` when it is left out) and `seen_at` (the RFC 3339 time it saw the change). A key with a bad
format is ignored with a warning, and a snapshot whose archive is bad goes with it, since it would be read
as the wrong archive's. With `seen_at` the run's summary records the dispatch latency.

With `snapshot`, the plan does not wait for snapshot.debian.org's listing cache (ten minutes). When the
snapshot of the caller's archive in the listing is older than the caller's, `plan-snapshots` plans again at
once with `--snapshot debian=ID,debian-security=ID`, naming the caller's ID for its archive and the
listing's ID for the other. A snapshot named explicitly is confirmed by a read that bypasses the cache, so
it is usable as soon as its own archive lists it. A plan that fails is tried again, a minute apart, for
about ten minutes: a snapshot that is listed but whose files a mirror does not serve yet is a 404, and a
rate limit looks the same. After that the run fails with the last error. The end of every `release.yml`
run also starts the workflow, because a dispatch that arrives during a release is skipped (below) and
would otherwise wait for the next hour.

A Node.js release changes no Debian snapshot: for `source` `node` the plan and the feed are skipped and
the third job ticks the box at once, so Renovate's `node-version` datasource opens that pull request. A
plan that was skipped or found nothing ticks nothing.

The plan is skipped while a release is due or under way (`scripts/release_next.py pending`, or a
`release-next.yml` or `release.yml` run not yet finished): until it finishes the registry holds the old
images, and the plan would propose snapshots for changes already on their way. snapshot.debian.org
records the main archive about every six hours and the security archive each time it changes, often
several times a day, so a security fix reaches a pull request within minutes of its snapshot when the
poller reports it, and within the hour otherwise.

Renovate is set to open a snapshot pull request whatever it opened in the last hour (`prHourlyLimit` is
0, set by the shared preset), because a pull request held back by that limit would delay a security fix by up to an hour.

The nightly keeps its own target in a cache and does not plan against the registry (section 9).

### release.yml

On a push of a tag `v*` by a maintainer, or dispatched on a tag by `release-next.yml`; the tag must be
`vMAJOR.MINOR.PATCH` on `main`. Two jobs, with permissions split:

1. **build**: read-only token. Builds and tests everything and uploads the output as an artifact.
2. **publish**: `packages: write`, `contents: write` and `id-token: write`, in the environment `release`.
   It downloads the artifact and then:
   - publishes `debian` to `ghcr.io/foreverworks/debian` and the `node-*` images to
     `ghcr.io/foreverworks/node`, one `publish --image ... --to` per repository, run side by side
     (`scripts/images.py repositories` says which images go to which repository), and `core` to the
     tag's GitHub release;
   - runs `verify --require-checks` on each pushed image, from the registry, with `--pull`, one
     image per job, side by side;
   - signs each image manifest digest with `cosign sign`, keyless, side by side;
   - and only then moves the friendly tags, with `oras`, one image at a time.

**Why the release builds the whole chain.** The factory can reuse an image from a registry and check
its child against it (`plan --against`, `test --parents`), as the nightly does. The release does not:
it is one set of images at one pair of snapshots, and an image reused from an earlier release would be tagged
`13-<debian>-<security>` for snapshots it was not built at. Reusing images in a release is a decision for the maintainers
(section 9).

**Why two jobs.** The build runs package scripts as root in a privileged container. A job that does so
must never hold a token that can write packages or releases, or sign as this repository: a hostile
package script could use it. The second job holds the write permissions and runs only the factory's
publish and verify, cosign and oras, on bytes the first job produced. The `release` environment accepts
deployments from `v*` tags only, and a tag ruleset lets only repository administrators move or delete
`v*` tags; both are repository settings (section 6.1). Creating a `v*` tag needs write access: only the
administrators have it, and among the workflows only `release-next.yml`'s `tag` job uses it for tags
(GitHub does not accept GitHub Actions as a bypass actor of a repository ruleset, so creation cannot be
limited to it by a rule). A `release.yml` on any other ref therefore never reaches the write
permissions, and a published tag never moves to other bytes.

**The order matters.** Tags move last. If the build fails, the checks fail, the verification fails or
the signature fails, the old tags stay where they are and nothing a user pulls by tag has changed.
Tags then move one image at a time: a failure inside that last loop leaves some images on new tags and
some on old ones, and a re-run of the publish job completes the set (every step before it is idempotent).

The first release, v0.1.0, was tagged by hand; every later one follows a merge (above).

### 6.1 Repository settings the files cannot enforce

- Actions: every Action pinned by full SHA (required), the workflow token read-only by default, and
  approval required for every outside contributor's pull request.
- Ruleset `protect main`: no deletion, no force push, and the status checks `static checks` and
  `build and test every image` (from GitHub Actions) required on every change; repository administrators
  may bypass it. Ruleset `release tags`: only repository administrators update or delete tags matching
  `v*`; creating one needs write access, which only administrators have. **Write access is release
  access**: anyone who can push a branch can dispatch a workflow from it and create a `v*` tag, so grant
  write only to people trusted to sign releases.
- Pull requests: auto-merge allowed, branches deleted after merge.
- Renovate: the Renovate App has access to this repository.
- Environment `release`: deployments only from tags matching `v*`.
- Packages: `ghcr.io/foreverworks/debian` and `ghcr.io/foreverworks/node` are public. A package GitHub
  creates from a workflow starts private, so an administrator set them after the first release and
  checked an anonymous `docker pull`. The images carry
  `org.opencontainers.image.source`, so GitHub links each package to this repository.
- GitHub disables a scheduled workflow after 60 days without activity in the repository, and evicts a
  cache entry unused for 7 days. The first costs nightly runs until someone re-enables it; the second only
  makes the next night build everything again.

## 7. Signing and records

**Signed today:** each image's manifest digest, keyless with Sigstore through the release workflow's
GitHub OIDC identity, `cosign sign`. That is how the factory signs its own builder image.
The verification command, with the exact identity regular expression, is in the README.

**Not signed today:** the records (provenance, SBOM, test results). The release publishes with
`--sign none`, so they are DSSE envelopes with an empty signature list, attached to the image
as OCI referrers and, for `core`, in `<sha256>.intoto.jsonl` beside the asset. Their protection is the
registry's authentication and, by digest, the fact that the signed image names the same bits the records
describe.

**What waits here:** the factory has `publish --sign keyless` since 0.7.0 (factory DESIGN 8.3). When this
repository switches it on, the README says that records are signed. Nothing in a record changes shape
when signing is switched on.

**The claim.** The provenance is SLSA Build L1, written by the build and not by the platform
(factory DESIGN 8.3). This repository does not claim more, and does not add GitHub's own attestation
beside it. It could, and that statement would carry whatever level GitHub claims.

## 8. Open gaps

Two gaps remain, each with its effect here, the interim, and the change that removes it.

**1. Records are unsigned.**
- *Interim:* the image digest is signed (section 7).
- *Removal:* `publish --sign keyless`, in the factory since 0.7.0 (its DESIGN 8.3); this repository's
  publish jobs still have to switch it on.

**2. The `.pyz` does not pin its builder, and the Action has no builder input** (factory DESIGN 5.4).
- *Interim:* `builder.ref` and `scripts/factory`, with the policy check that keeps the tag equal to the
  factory version.
- *Removal:* the `.pyz` carries the digest of its own builder, and the Action uses it. Later factory work.
  Then this repository uses the Action and drops `builder.ref` and `scripts/factory`.

**Closed in v0.6.3.** Two gaps of the earlier releases are gone, and so is the glue they needed:

- `publish` could not select images, so `scripts/images.py stage` linked one directory of the build per
  repository. `publish --image NAME` replaces it: the release runs one `publish` per repository. The
  factory's `{image}` template does not fit here (it names a repository per image, and the `node-*`
  images share `node`), so `scripts/images.py repositories` still says which images go where, and the
  factory does the rest.
- `test` could not check `ancestry` for a parent reused from a registry, so every release rebuilt the
  whole chain and a nightly child stayed a candidate. `test --parents` reads the parent's manifest from
  the registry, and the nightly passes it. The release still builds the whole chain, for the reason in
  section 6, and no longer for this one.

The factory's own repository tracks what is left. A release that fixes one is adopted by moving the lock
and deleting the interim code in the same pull request, never by leaving both.

## 9. Later work

- **arm64.** The factory v0.8.0 supports amd64 only, and architecture is part of every identity, so other
  architectures can follow. This needs the factory first; then `architectures` in `factory.toml` grows by
  one and the nightly and the release build two sets.
- **Nightly planning against `ghcr.io`.** The nightly plans against a cache. Now that releases exist, it
  could ask `ghcr.io` which identities are already published and build only what a release would add, as
  the factory's design intends. The
  `{image}` template does not name the shared `node` repository, so that is one `--against` per
  repository.
- **Releases that reuse images.** A release could plan against `ghcr.io` and build only what changed
  (section 6 says why it does not).
- **New LTS lines.** Node.js 27 is scheduled to become LTS on 2027-10-20 (nodejs/release schedule). It gets a block in `factory.toml`, an entry
  in the lock and a row in the tables, as a reviewed change.
- **Signed records**, when the factory supports them (section 8, gap 1).
- **Checksums on Renovate branches.** Renovate edits only the `version` of a lock entry. The
  `renovate-checksums` workflow runs on pushes to `renovate/**` branches and uses the input-lock
  Action (the same version as the Renovate preset) to rewrite the checksums of the entries Renovate
  bumped. Renovate's branch gets a second commit with the new checksums, and CI's `fetch` then passes.
  Node.js entries carry `signed_by`, so their checksums come from the release's signed list and the
  signature is checked first. A commit pushed with the workflow's own token gets a `pull_request` run of
  `ci.yml` that waits for approval, and that waiting run hides any other CI run on the commit, so the
  required checks never report (PR #4 sat blocked this way on 2026-11-25). The job's last step approves
  that run when checksums changed, and dispatches `ci.yml` only if no such run appears within 3 minutes. The lock must stay in the
  form `input-lock format` writes, or the Action fails.

## 10. Checks this repository adds

The factory checks the images. These checks keep the repository itself honest. `scripts/check` runs all of
them, side by side (`scripts/jobs.sh`), and prints each one's output in a fixed order. It is what CI runs
in the static job:

- **shellcheck** on every shell script;
- **`mypy --strict`** on every Python script. The scripts use only the standard library, are fully typed
  and are pure functions over explicit state, with dataclasses and named tuples for data;
- **unit tests** for the scripts;
- **`policy.py`**, which enforces this repository's rules, among them that `builder.ref` is one line whose
  tag equals the lock's factory version, that workflows run only on `ubuntu-26.04` (no self-hosted label,
  no switch on the repository's visibility), that every Action is pinned by a full commit SHA with a
  version comment, that no `${{ }}` expression appears inside a `run:` script, that every `node-<N>`
  image has a lock entry of major N used by that image alone, and that every OCI image maps to a
  repository;
- **actionlint** on the workflows;
- **the lock check**: `lock check` of the factory, which re-resolves the snapshot and confirms that the
  lock and the definition agree.

Run `scripts/check` before every push. It needs no network except for the lock check.

**Side by side.** Steps that do not depend on each other run in parallel: the checks above, the
`verify` of each image in CI and in the release, and the publish, verify and sign steps of
`scripts/release`. `scripts/jobs.sh` holds the one helper: start a job per item, wait for all, print each log in
the order started, fail if any failed. Moving the tags stays serial, on purpose (section 6).
