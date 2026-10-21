# Maintaining filmwright

How issues, pull requests and releases are run. Contributors only need the first section; the rest is for
maintainers, written down so the project runs the same way whoever is triaging.

## Reporting issues: the standard pattern

Every bug, feature and docs change starts as an issue, opened with one of the
[issue forms](https://github.com/dassjaylabs/filmwright/issues/new/choose) (blank issues are off).

- **Title:** `area: what goes wrong` for bugs, `area: what you'd like` for features, all lower case after the
  colon. The area is one of `voice`, `read-back`, `music`, `demo`, `explainer`, `hybrid`, `presenter`, `export`,
  `cli`, `setup`, `ci`, `docs`.
  Examples: `read-back: Japanese lines always score a perfect match`, `export: OTIO timeline export`.
- **Body:** what happened, what you expected, the smallest `reel.yaml` and command that show it, and
  `filmwright doctor` output. Remove tokens, private URLs and personal data.
- **One problem per issue.** Questions and early ideas go to [Discussions](https://github.com/dassjaylabs/filmwright/discussions).
- **Security problems** never go in a public issue: use a [private advisory](https://github.com/dassjaylabs/filmwright/security/advisories/new).

Problems that come in somewhere else (a comment, a post, an email) get an issue too, written up by a maintainer in
the same pattern, so every fix has a record. Credit the reporter as "reported by a community member" unless they
ask to be named.

## Labels

Defined in [`.github/labels.yml`](../.github/labels.yml) and applied with `scripts/sync-labels.sh`. Edit the file,
not the GitHub UI.

| Group | Labels | Rule |
|---|---|---|
| Type | `type: bug`, `type: feature`, `type: docs`, `type: question`, `type: chore`, `type: performance` | exactly one |
| Area | `area: voice`, `area: read-back`, `area: music`, `area: demo`, `area: explainer`, `area: hybrid`, `area: presenter`, `area: export`, `area: cli`, `area: setup`, `area: ci` | one or more |
| Status | `status: needs triage`, `status: needs info`, `status: confirmed`, `status: in progress`, `status: blocked` | exactly one while open |
| Priority | `priority: P1`, `priority: P2`, `priority: P3` | set at triage |
| Other | `platform: macos`, `platform: linux`, `platform: windows`, `i18n`, `good first issue`, `help wanted`, `dependencies`, `accessibility`, `duplicate`, `invalid`, `wontfix` | as they apply |

Priorities:

- **P1:** broken for most users, wrong or unsafe output (including a check that silently passes everything), data
  loss, or security. Fix before anything else and ship in a patch release.
- **P2:** a real problem or an important feature. Planned into the next minor release's milestone.
- **P3:** nice to have. Open to contributors; no date.

## Triage (weekly)

1. Go through issues labelled `status: needs triage`.
2. Reproduce bugs. If you can't, ask for what's missing and set `status: needs info`; close after 30 days without a
   reply, with a note that it can be reopened.
3. Set `type:`, `area:`, `priority:` and `status: confirmed` (or `duplicate` / `invalid` / `wontfix`, with a
   comment explaining why, then close).
4. Put P1 and P2 items in a milestone. Mark small, well-understood ones `good first issue`, and ones you'd like
   help with `help wanted`.
5. Add the issue to the [project board](https://github.com/users/dassjaylabs/projects/1) and set its status:
   Triage → Backlog (accepted, no date) → Planned (in a milestone) → In progress → In review (pull request open) →
   Done. Closed issues and merged pull requests move to Done automatically.

## Pull requests

- Every pull request links its issue (`Fixes #12`) so merging closes it.
- CI must pass (lint, tests and the smoke build on Ubuntu and macOS). Contributions come in under the project's
  MIT license; there is no CLA.
- Squash-merge with a message that says what changed and why. User-visible changes get a line in
  [CHANGELOG.md](../CHANGELOG.md) under the next version.
- Keep everything generic: fictional Acme examples only, no real products, people or brands.

## Releases

1. Every issue in the milestone is closed or moved on.
2. Move the CHANGELOG's unreleased section under the version number, bump `__version__`, commit.
3. Tag `vX.Y.Z` on `main` and publish a GitHub release whose notes are that CHANGELOG section.
4. Close the milestone and open the next one.

Versions follow [semantic versioning](https://semver.org): while the major version is 0, a minor release may change
options, and the CHANGELOG says how to migrate.

## Repository settings

- `main` requires the CI checks to pass; force pushes and deletion are blocked.
- `cla-signatures` is the archive of the retired CLA bot's records (the CLA was dropped in 0.1.0).
- Dependabot opens weekly pull requests for GitHub Actions and Python dependencies, and security updates as needed.
- Private vulnerability reporting is on; advisories are handled per [SECURITY.md](../SECURITY.md).
- Secret scanning with push protection and CodeQL code scanning are on.
- `CODEOWNERS` requests the maintainer's review on every pull request.
- `stale.yml` marks `status: needs info` issues stale after 23 days and closes them 7 days later; nothing else is
  ever marked stale.
- Merges are squash-only, and merged branches are deleted.
