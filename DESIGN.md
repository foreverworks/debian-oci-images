# Design

This document is for maintainers and reviewers. It says what the repository holds, why the images are
what they are, and what is deliberately temporary. For what the images give you and how to check them,
see the [README](README.md). The factory that does the building is
[debian-image-factory](https://github.com/foreverworks/debian-image-factory), pinned here at v0.6.3; its
sections are cited as "factory DESIGN n".

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
the next Dockerfile. The Node.js images start `node`, so `docker run image script.js` and
`docker run image --version` do what people expect.

## 3. Versions

**Node.js policy.** Every Node.js LTS line still supported upstream has an image. A line is added by
hand when it becomes LTS (in October of its year), and removed on its end-of-life date, from the
[nodejs/release schedule](https://github.com/nodejs/release). A line in its Current phase gets no image.
From Node.js 27 on, upstream makes every major an LTS line (the schedule gives 27 LTS on 2027-10-20),
so "even numbers only" is not a rule here: the schedule is.

State at 2026-11-22:

| Line | Codename | Status | Version in the lock | End of life |
|---|---|---|---|---|
| 26 | Lithium | active LTS (the first `lts` entry of `https://nodejs.org/dist/index.json`, read 2026-11-22) | 26.13.1 | see the schedule |
| 24 | Krypton | maintenance LTS | 24.22.3 | 2028-04-30 |
| 22 | Jod | maintenance LTS | 22.23.5 | 2027-04-30 |

Adding and removing a line is a manual, reviewed change: a block in `factory.toml`, an entry in
`lock.json`, and the tag rules. It is not automated, because the decision to carry a line is a support
commitment, and because the end of life of a line is a date a person should notice and not a version
string a bot can compare. The highest line is the one tagged `lts` and `latest`.

**Debian snapshot.** `debian_snapshot` in the lock (today `20261121T203158Z`) is the one build snapshot
all packages are resolved at. It moves by `lock snapshot --latest`, and a snapshot move changes the
identity of every image whose package set changed, so only those rebuild (factory DESIGN 7). Debian
security updates reach the images this way: the nightly plan looks at the newest snapshot, and a release
that follows moves the lock to it.

**Renovate rules:**

- patch and minor versions of Node.js inside a line are opened as pull requests;
  majors are never proposed, because a new line is a decision (above);
- the `debian-image-factory` entry moves by the `github-releases` datasource, and the pull request
  must also move `builder.ref` to the same release (section 4);
- GitHub Actions are pinned by commit, with the version as a comment, and Renovate bumps both;
- `node-release-keys` has no datasource. It is a trust root and moves by hand, as a reviewed diff.

A Renovate change is not a release. It builds and tests in CI and waits for a person to tag.

## 4. The lock and how the factory is pinned

`lock.json` is the single source of every version and checksum (factory DESIGN 6.1). `factory.toml`
holds no versions, so a version has one home.

**The factory itself.** The `debian-image-factory` entry names the release (0.6.3), the URL of its `.pyz`
and its sha256 `a2dab616...5c62`. `scripts/factory install` downloads that file and refuses any other
bytes. The `.pyz` is the only code that runs the build, so its checksum is the root of the chain.

**The builder.** The factory builds in a container image. `builder.ref` is one line, a reference with the
tag for readers and the digest for the machine:

```
ghcr.io/foreverworks/debian-image-factory-builder:v0.6.3@sha256:c9734c73...41b3
```

`scripts/policy.py` checks that its tag equals the factory version in the lock, so one pull request moves
both and the two never drift. The line goes away when the `.pyz` pins its own builder (factory DESIGN
5.4, planned).

**Verified, not trusted.** Both the `.pyz` and the builder are signed keyless by the factory's release
workflow. Anyone can check them with the identity
`https://github.com/foreverworks/debian-image-factory/.github/workflows/release.yml@refs/tags/v<version>`
and the issuer `https://token.actions.githubusercontent.com`. The builder reference was verified this way
with cosign 3.1.4 when it was pinned.

**Why the factory's GitHub Action is not used.** In v0.6.3 the Action builds its builder from the
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
- `debian`: `13`, `trixie`, `latest`, and `13-<debian_snapshot>`, for example `13-20261121T203158Z`;
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

The one other job that may write is `checksums` in `renovate-checksums.yml` (`contents` and `actions`,
enforced by `scripts/policy.py`). It runs only `actions/checkout` and the pinned input-lock Action, never
this repository's scripts or a package's, and it runs only on pushes to Renovate's branches and
commits only to the branch it was started on. It needs `actions` to dispatch `ci.yml` on that branch.

### ci.yml

On every push to `main` and every pull request:

1. static checks: `scripts/check` (section 10);
2. build and test every image from the lock's snapshot, with nothing published: `plan` with no
   `--against`, `fetch`, `build`, `test`, then `verify --require-checks` on every layout, one `verify`
   per image, side by side.

The two jobs do not depend on each other, so they run side by side.

CI shows that the definition, the lock and the scripts build the images and that every check passes. It
holds a read-only token.

### nightly.yml

On a schedule and on demand. It plans at the **newest** snapshot against a target that persists in the
Actions cache: a local zot registry on `127.0.0.1` for the OCI images and a `dir://` directory for
`core`. It builds and tests what changed, "publishes" only that into the cache, and prunes the cache. A child
that builds alone (a Node.js bump, with `debian` reused) reads its parent from the cache for both `build`
and `test`, so its `ancestry` check runs and the child passes and is kept as good.

- A quiet night (no relevant Debian upload, no new Node.js release) gives `changed=false` and builds
  nothing, at the cost of a few index downloads.
- It never publishes to `ghcr.io` and never moves a tag. Its role is to tell a maintainer, by a failing run,
  that the next release would not build or pass.
- It does not move the lock: a person does, when a release is wanted.

The cache stands in for the registry because the real target does not exist before the first release
(section 9).

### release.yml

On a push of a tag `v*`, which only maintainers create; the tag must be `vMAJOR.MINOR.PATCH` on `main`. Two jobs, with permissions split:

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
it is one set of images at one snapshot, and an image reused from an earlier release would be tagged
`13-<snapshot>` for a snapshot it was not built at. The first release also has nothing to reuse.
Reusing images in a release is a decision for the maintainers (section 9).

**Why two jobs.** The build runs package scripts as root in a privileged container. A job that does so
must never hold a token that can write packages or releases, or sign as this repository: a hostile
package script could use it. The second job holds the write permissions and runs only the factory's
publish and verify, cosign and oras, on bytes the first job produced. The `release` environment accepts
deployments from `v*` tags only, and a tag ruleset lets only repository administrators create, move or
delete `v*` tags; both are repository settings (section 6.1). A `release.yml` on any other ref, or a tag
someone without that role pushed, therefore never reaches the write permissions.

**The order matters.** Tags move last. If the build fails, the checks fail, the verification fails or
the signature fails, the old tags stay where they are and nothing a user pulls by tag has changed.
Tags then move one image at a time: a failure inside that last loop leaves some images on new tags and
some on old ones, and a re-run of the publish job completes the set (every step before it is idempotent).

Nothing is published to any registry before the owner approves the first release tag.

### 6.1 Repository settings the files cannot enforce

- Actions: every Action pinned by full SHA (required), the workflow token read-only by default, and
  approval required for every outside contributor's pull request.
- Ruleset `protect main`: no deletion, no force push. Ruleset `release tags`: only repository
  administrators create, update or delete tags matching `v*`.
- Environment `release`: deployments only from tags matching `v*`.
- Packages: after the first release, `ghcr.io/foreverworks/debian` and `ghcr.io/foreverworks/node` are
  set to public by an administrator (a package GitHub creates from a workflow starts private), and an
  anonymous `docker pull` is checked before the release is announced. The images carry
  `org.opencontainers.image.source`, so GitHub links each package to this repository.
- GitHub disables a scheduled workflow after 60 days without activity in the repository, and evicts a
  cache entry unused for 7 days. The first costs nightly runs until someone re-enables it; the second only
  makes the next night build everything again.

## 7. Signing and records

**Signed today:** each image's manifest digest, keyless with Sigstore through the release workflow's
GitHub OIDC identity, `cosign sign`. That is how the factory signs its own builder image.
The verification command, with the exact identity regular expression, is in the README.

**Not signed today:** the records (provenance, SBOM, test results). Factory v0.6.3 accepts only
`publish --sign none`, so they are DSSE envelopes with an empty signature list, attached to the image
as OCI referrers and, for `core`, in `<sha256>.intoto.jsonl` beside the asset. Their protection is the
registry's authentication and, by digest, the fact that the signed image names the same bits the records
describe.

**What waits on the factory:** `publish --sign keyless` (factory DESIGN 8.3). When it exists, this
repository adds the flag, and the README says that records are signed. Nothing in a record changes shape
when signing is switched on.

**The claim.** The provenance is SLSA Build L1, written by the build and not by the platform
(factory DESIGN 8.3). This repository does not claim more, and does not add GitHub's own attestation
beside it. It could, and that statement would carry whatever level GitHub claims.

## 8. Waiting on the factory

Two gaps remain, each with its effect here, the interim, and the factory change that removes it.

**1. Records are unsigned.**
- *Interim:* the image digest is signed (section 7).
- *Removal:* `publish --sign keyless`, planned in factory DESIGN 8.3. Later factory work.

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

- **arm64.** The factory v0.6.3 supports amd64 only, and architecture is part of every identity, so other
  architectures can follow. This needs the factory first; then `architectures` in `factory.toml` grows by
  one and the nightly and the release build two sets.
- **Nightly planning against `ghcr.io`.** Today the nightly plans against a cache, because nothing exists
  on the registry. Once the first release exists, the nightly can ask `ghcr.io` which identities are
  already published and build only what a release would add, as the factory's design intends. The
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
  signature is checked first. A commit pushed with the workflow's own token starts no workflow, so the
  job's last step dispatches `ci.yml` on the branch when checksums changed. The lock must stay in the
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
