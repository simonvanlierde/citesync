# Contributing

Thank you for your interest in citesync. Bug reports, feature requests and pull
requests are welcome. Please read the [Code of Conduct](CODE_OF_CONDUCT.md) first, and
report vulnerabilities as [SECURITY.md](SECURITY.md) describes, not in a public issue.

## Report a bug or ask for a feature

Open an [issue](https://github.com/simonvanlierde/citesync/issues) with the bug or
feature form. For a bug, say what you did, what you expected and what happened, with the
release or commit you used. A question the README and docs don't answer is a gap in the docs: open
a feature request for it.

## Scope and response

One person maintains citesync, in their own time. Expect a reply to an issue or
pull request within about two weeks.

Before a large pull request, such as a new feature or a change to how something works,
open an issue and agree on the change there first. A small fix needs no issue. A pull
request outside what the project sets out to do is closed with a link to this section.

## Set up and check

The [README](../README.md) says how to install the tools, the dependencies
and the git hooks. `just check` runs the checks CI runs, and `just fmt` fixes and
formats.

Add automated tests for new functionality and regression tests for fixes.
Run a regression test before the fix and check that it fails for the reported reason.
Fix every lint and type warning, or suppress it with a stated reason.

uv locks only releases at least a week old. If `just check` fails on
a security fix newer than that, add the package to `exclude-newer-package` under `[tool.uv]` in `pyproject.toml`,
and remove it a week later ([how](https://github.com/simonvanlierde/project-templates/blob/main/docs/tooling.md#dependencies)).

## Profile

`just bench` times `citesync check` on this repo. `just profile` shows where the time
goes, for `check` on this repo and `write --diff` on `tests/write/planted`: the slowest
imports, a sampling CPU profile with full call stacks, and peak memory. It saves the
results in `profile/`, which git ignores; open `profile/check.html` in a browser to explore
the CPU profile. Most of a run is Python starting and importing modules, so a fix usually
moves an import into the function that needs it, and `tests/test_rules.py` checks that
`check` doesn't import those modules. CI doesn't time anything: run times on shared
machines vary too much to fail a build on.

## When you change a compared field

1. Change its comparison and message in `src/citesync/rules.py`. Keep normalisation detail only there.
2. Change its row in `src/citesync/mapping-local.json` if where the field sits in a file changes.
3. Update the fixtures: `uv run pytest --update-expected` rewrites the expected `cases.json` and `record.json` from actual output. Read the git diff before you commit. [tests/fixtures/README.md](../tests/fixtures/README.md) says how the files are made.
4. Update the docs. `docs/config.md` lists the fields, and `tests/test_docs.py` fails if one is missing there.
5. Run `just mutation`, as the README describes.

## Write commits and pull requests

- **Commits** follow [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/):
  `type(scope): summary`, in the imperative, lower case, with no period. Add a body only
  when the change needs one, with a bullet per logical chunk.
- **The pull request title** becomes the squash commit subject, so it follows the same rule.
- **Both are checked** against [`committed.toml`](../committed.toml): a commit-msg
  hook (installed by `prek install`) refuses a commit message that breaks the rule, and
  the `pull request title` check fails a pull request whose title does. Lower case isn't
  checked. A revert is titled `revert: <original subject>`: rename the
  `Revert "..."` title that GitHub's Revert button writes.
- **The pull request body** has the shape of
  [the pull request template](pull_request_template.md): what it fixes and why, three or
  four bullets, a `Tested:` line with the proof (the command and its result, or a test
  that fails without the change), and a `Not checked:` line with what did not run and why,
  and any design choice or security path that only a person can judge. "Nothing" is fine.
- **The changelog** ([CHANGELOG.md](../CHANGELOG.md)) follows
  [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/). Write each entry for
  the people who use the project, not as a commit subject. Mark breaking changes
  **Breaking**, and put upgrade steps first under the version.
- **The release notes** are that version's changelog section.

## Make a release

The maintainer runs `just release X.Y.Z`. [Publishing](https://github.com/simonvanlierde/project-templates/blob/main/docs/setup.md#publishing) has the steps and the one-time setup.

## Sign off your commits

Every commit in a pull request carries a `Signed-off-by:` line, which says you wrote the
change or have the right to submit it under this project's license: the
[Developer Certificate of Origin 1.1](https://developercertificate.org/). `git commit -s`
adds the line, and the commit-msg hook refuses a commit without it.

To add it to commits you already made, run `git fetch origin`, then
`git rebase --signoff origin/main`. That works in a clone of this repository, where `origin`
is the only remote. If you work from a fork, use the remote that points at this repository
(often `upstream`) in place of `origin`. If you have not pushed the branch yet, that is all.
If you pushed it already, update it with `git push --force-with-lease`, which refuses to
overwrite work you have not seen. Do not use a plain `git push --force`.

The `dco` workflow checks every pull request from a fork and fails on a commit without the line. Pull requests from a branch in this repository skip it: pushing that branch already needed write access.

## Who maintains this

Simon van Lierde maintains citesync: reviews pull requests, merges them and
makes releases. The repository belongs to [simonvanlierde](https://github.com/simonvanlierde)
on GitHub. A release sets the version in pyproject.toml and CITATION.cff, updates the citation release date, and runs `uv lock` and `uv run citesync write` to keep the lockfile and codemeta.json in step. Update the pinned versions in the README and playground snippets and add a dated `## [X.Y.Z]` section to CHANGELOG.md. After the release-wide review and checks pass, push the tag `vX.Y.Z`;
the [release workflow](https://github.com/simonvanlierde/project-templates/blob/main/docs/tooling.md#release-workflows) does the rest.
Only maintainers can merge to `main`. A new maintainer is added by an existing one, by name in this section.
If no maintainer can continue, the repository is archived with a note in the README,
and anyone may fork it under its license.
