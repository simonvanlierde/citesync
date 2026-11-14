# Task runner: https://just.systems. `just` lists the recipes, `just <name>` runs one.
#
# Each stack's recipes are in just/, prefixed (`py-`) because
# imports share one namespace, except the few only one kind has, such as `pipeline` or `up`.
import? 'just/python.just'

# List the recipes (what a bare `just` runs).
default:
    @just --list

# The stack checks CI runs. `just hooks` runs the git hooks, which CI also runs.
check:
    @just py-check
    @pnpm run check
    @if just --show local-check >/dev/null 2>&1; then just local-check; fi

# Mutation-test the modules in pyproject's [tool.mutmut]. Fails on a survivor not in
# tests/mutation-baseline.txt, and on a listed one that no longer survives, so the list stays true.
mutation:
    #!/usr/bin/env bash
    set -euo pipefail
    # Byte order, so sort and comm agree on the ǁ in class method names.
    export LC_ALL=C
    # mutmut reuses results from mutants/ even after the tests change, so start clean.
    rm -rf mutants
    uv run mutmut run >/dev/null
    survivors=$(uv run mutmut results | sed -n 's/^ *\(.*\): survived$/\1/p' | sort)
    listed=$(grep -v '^#' tests/mutation-baseline.txt | awk '{ print $1 }' | sort)
    new=$(comm -23 <(echo "$survivors" | sed '/^$/d') <(echo "$listed"))
    gone=$(comm -13 <(echo "$survivors") <(echo "$listed" | sed '/^$/d'))
    echo "$(echo "$survivors" | grep -c . || true) survivors; not in tests/mutation-baseline.txt:"
    echo "${new:-none}"
    echo "listed but no longer surviving (drop them):"
    echo "${gone:-none}"
    [ -z "$new$gone" ]

# Time `citesync check` on this repo's own files: 30 runs after 3 warm-ups, median in the table.
# Runs the venv's script directly, since `uv run` adds more than check itself takes.
bench:
    uv sync -q
    hyperfine -N -w 3 -r 30 '.venv/bin/citesync check'

# Profile `check` on this repo and `write --diff` on tests/write/planted: the slowest imports,
# a CPU profile (text here, html in profile/) and peak memory. Output goes to profile/.
profile:
    #!/usr/bin/env bash
    set -uo pipefail
    uv sync -q
    mkdir -p profile
    py=.venv/bin/python
    for run in "check:check" "write:write --diff --root tests/write/planted"; do
        name=${run%%:*} args=${run#*:}
        echo "== citesync $args"
        # Exit 1 is a finding or a diff, not a failed run.
        $py -X importtime -m citesync $args >/dev/null 2>profile/$name.importtime
        echo "-- slowest imports (cumulative us)"
        grep '^import time:' profile/$name.importtime | sort -t'|' -k2 -rn | head -8
        $py -m pyinstrument -i 0.0001 -r session -o profile/$name.pyisession -m citesync $args >/dev/null
        $py -m pyinstrument --load profile/$name.pyisession -r html -o profile/$name.html
        $py -m pyinstrument --load profile/$name.pyisession -r text | head -40
        $py -m memray run -q -f -o profile/$name.memray -m citesync $args >/dev/null 2>&1
        echo "-- peak memory: $($py -m memray stats profile/$name.memray 2>/dev/null | grep -A1 'Peak memory' | tail -1 | tr -d '\t')"
    done
    echo "HTML profiles: profile/check.html profile/write.html"

# Fix and format every stack here, as each stack's `fmt` recipe does.
fmt:
    @just py-fmt
    @pnpm exec biome check --write playground/*.mjs playwright.config.mjs

# The checks workflow skips the hooks in its SKIP list, which the stack workflows run
# instead. Here they all run, so this can fail where the checks workflow passes.

# Run every git hook over the whole repo, not just staged files.
hooks:
    prek run -a

# The writer exits 1 whenever it changes a file, so the check that follows decides
# the result.

# Rewrite codemeta.json to agree with CITATION.cff, then check.
citation:
    -prek run citesync-write --hook-stage manual --all-files
    prek run citesync --all-files

# Release X.Y.Z. First run: cut CHANGELOG's [Unreleased] into [X.Y.Z] and commit it; merge that to main. Second run, on up-to-date main: sign and push tag vX.Y.Z.
release version:
    #!/usr/bin/env bash
    set -euo pipefail
    version={{ version }}
    [[ $version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "not a version: $version" >&2; exit 1; }
    tag=v$version
    repo=https://github.com/simonvanlierde/citesync
    # The build takes its version from the manifest and refuses a tag that differs.
    [ "$(uv version --short --no-sync --directory .)" = "$version" ] || { echo "pyproject.toml is not at $version" >&2; exit 1; }
    # citesync fails while the manifests and citation files disagree. Run it before any file changes.
    prek run citesync --all-files
    git fetch --quiet origin main
    # Not grep -q: it stops reading early, and under pipefail git show then fails on a
    # changelog bigger than the pipe buffer.
    if git show origin/main:CHANGELOG.md | grep "^## \[$version\] - " >/dev/null; then
        .github/scripts/tag-release.sh "$version"
        echo "Archive it in Software Heritage: https://archive.softwareheritage.org/save/ (git, $repo). The README badge then links to the SWHID."
        exit 0
    fi
    prev=$(sed -n 's/^## \[\([0-9][0-9.]*\)\].*/\1/p' CHANGELOG.md | head -1)
    if [ -n "$prev" ]; then link=$repo/compare/v$prev...$tag; else link=$repo/releases/tag/$tag; fi
    tmp=$(mktemp)
    trap 'rm -f "$tmp"' EXIT
    awk -v v="$version" -v d="$(date +%F)" -v repo="$repo" -v link="$link" '
        /^## \[Unreleased\]/ && !h { print; print ""; print "## [" v "] - " d; h = 1; next }
        /^\[Unreleased\]: / { print "[Unreleased]: " repo "/compare/v" v "...HEAD"; print "[" v "]: " link; l = 1; next }
        { print }
        END { if (!h) exit 1; if (!l) { print ""; print "[Unreleased]: " repo "/compare/v" v "...HEAD"; print "[" v "]: " link } }
    ' CHANGELOG.md >"$tmp" || { echo "CHANGELOG.md has no [Unreleased] section" >&2; exit 1; }
    .github/scripts/release-notes.sh "$tag" "$tmp" >/dev/null || { echo "[Unreleased] has no entries to release" >&2; exit 1; }
    cp "$tmp" CHANGELOG.md
    git add CHANGELOG.md
    git commit -s -m "chore: release $version" -- CHANGELOG.md
    echo "Merge this commit to main, then run: just release $version"

# Protect the default branch (no deletion, no force-push, linear history, PRs squash-merged after the always-on checks pass and one approval) and the v* tags. Turn on secret scanning with push protection, private vulnerability reporting, CodeQL default setup and Dependabot alerts. Set up release environments with required review. Safe to rerun.
repo-settings:
    #!/usr/bin/env bash
    set -euo pipefail
    err=$(mktemp)
    trap 'rm -f "$err"' EXIT
    fail() {
        cat "$err" >&2
        grep -qE 'HTTP (403|404)' "$err" && echo "Rulesets on a private repo need a paid GitHub plan (or the repo does not exist, or you lack admin rights)." >&2
        grep -q 'must be part of the ruleset source' "$err" && echo "The main ruleset lets the Renovate app bypass the review, and GitHub accepts that only once the app is installed on this repo: add it at https://github.com/apps/renovate, then rerun." >&2
        exit 1
    }
    # Merge-method switches live on the repo itself; the ruleset also limits the PR button.
    gh api -X PATCH repos/{owner}/{repo} -F allow_squash_merge=true -F allow_merge_commit=false -F allow_rebase_merge=false -F delete_branch_on_merge=true -F web_commit_signoff_required=true >/dev/null 2>"$err" || fail
    # Push protection refuses a push that holds a known secret format, before it reaches the repo.
    # A private repo without Secret Protection refuses this, so it warns instead of failing.
    if gh api -X PATCH repos/{owner}/{repo} -f 'security_and_analysis[secret_scanning][status]=enabled' -f 'security_and_analysis[secret_scanning_push_protection][status]=enabled' >/dev/null 2>"$err"; then
        echo "Turned on secret scanning and push protection."
    else
        echo "Warning: secret scanning could not be turned on (a private repo needs Secret Protection): $(cat "$err")" >&2
    fi
    # Adopt an existing ruleset by name, else one with the same target that protects the same
    # refs as the file, updating it in place. The list has no conditions, so each candidate is read.
    for name in main main-checks tags; do
        file=.github/rulesets/$name.json
        case "$name" in
            main) want='["~DEFAULT_BRANCH"]' filter='.[] | select(.target == "branch" and (.name | test("checks?") | not)) | .id' ;;
            main-checks) want='["~DEFAULT_BRANCH"]' filter='.[] | select(.target == "branch" and (.name | test("checks?"))) | .id' ;;
            tags) want='["refs/tags/v*"]' filter='.[] | select(.target == "tag") | .id' ;;
        esac
        id=$(gh api "repos/{owner}/{repo}/rulesets?includes_parents=false" --jq "first(.[] | select(.name == \"$name\") | .id) // empty" 2>"$err") || fail
        if [ -z "$id" ]; then
            candidates=$(gh api "repos/{owner}/{repo}/rulesets?includes_parents=false" --jq "$filter" 2>"$err") || fail
            for candidate in $candidates; do
                same=$(gh api "repos/{owner}/{repo}/rulesets/$candidate" --jq ".conditions.ref_name.include == $want" 2>"$err") || fail
                if [ "$same" = true ]; then
                    id=$candidate
                    break
                fi
            done
        fi
        if [ -n "$id" ]; then
            gh api -X PUT "repos/{owner}/{repo}/rulesets/$id" --input "$file" >"$err" 2>&1 || fail
            echo "Updated ruleset '$name' ($id)."
        else
            # gh prints GitHub's reason for a refusal on stdout, so fail() needs both.
            gh api -X POST repos/{owner}/{repo}/rulesets --input "$file" >"$err" 2>&1 || fail
            echo "Created ruleset '$name'."
        fi
    done
    # SECURITY.md sends reports to a private security advisory, which this turns on.
    gh api -X PUT repos/{owner}/{repo}/private-vulnerability-reporting >/dev/null 2>"$err" || fail
    echo "Turned on private vulnerability reporting."
    # CodeQL default setup scans every PR and push to main.
    if gh api -X PATCH repos/{owner}/{repo}/code-scanning/default-setup -f state=configured >"$err" 2>&1; then
        echo "Turned on CodeQL default setup."
    else
        echo "Warning: CodeQL default setup could not be turned on, so code scanning stays off: $(cat "$err")" >&2
    fi
    # Dependabot alerts let Renovate open security PRs and turn on the dependency graph.
    gh api -X PUT repos/{owner}/{repo}/vulnerability-alerts >/dev/null 2>"$err" || fail
    echo "Turned on Dependabot alerts."
    # Environments limit publishing to version tags and require review before release.
    user_id=$(gh api user --jq .id 2>"$err") || fail
    for env in pypi; do
        gh api -X PUT "repos/{owner}/{repo}/environments/$env" \
            -F "reviewers[][type]=User" \
            -F "reviewers[][id]=$user_id" \
            -F "deployment_branch_policy[protected_branches]=false" \
            -F "deployment_branch_policy[custom_branch_policies]=true" >/dev/null 2>"$err" || fail
        policies=$(gh api "repos/{owner}/{repo}/environments/$env/deployment-branch-policies" --jq '.branch_policies[].name' 2>/dev/null || true)
        if ! echo "$policies" | grep -qxF 'v*'; then
            gh api -X POST "repos/{owner}/{repo}/environments/$env/deployment-branch-policies" -f name="v*" -f type="tag" >/dev/null 2>"$err" || fail
        fi
        if [ "$env" = "ghcr" ] && ! echo "$policies" | grep -qxF 'main'; then
            gh api -X POST "repos/{owner}/{repo}/environments/$env/deployment-branch-policies" -f name="main" -f type="branch" >/dev/null 2>"$err" || fail
        fi
        echo "Configured environment '$env'."
    done
    repo_full_name=$(gh api repos/{owner}/{repo} --jq .full_name 2>"$err") || fail
    owner=${repo_full_name%%/*}
    repo=${repo_full_name##*/}
    echo "PyPI pending publisher: https://pypi.org/manage/account/publishing/?provider=github&project_name=citesync&owner=$owner&repository=$repo&workflow_filename=python-release.yml&environment=pypi"
    echo "Zenodo: https://zenodo.org/account/settings/github/"
    if [ -f .github/first-release.md ]; then echo "First-release checklist: gh issue create --title 'First release' --body-file .github/first-release.md"; fi
# Set the GitHub About box from your answers: description and a topic per stack. Adds topics, never removes yours. Safe to rerun.
repo-about:
    gh repo edit --description 'Generate and synchronize software citation files from package metadata. CLI, pre-commit hook and browser playground.' --homepage 'https://simonvanlierde.com/citesync/' --add-topic python --add-topic citation --add-topic codemeta --add-topic zenodo --add-topic software-metadata --add-topic pre-commit

# Build the current Python wheel and its locked browser dependencies.
playground-build:
    uv run playground/build.py

# Build and serve the playground locally; no citation data leaves the browser.
playground: playground-build
    uv run --no-project python -m http.server 8468 --bind 127.0.0.1 --directory playground

# Frontend checks; browser tests start their own server.
playground-check:
    pnpm run check
    pnpm run test:browser

# A repo's own recipes that copier updates never touch. A `local-check` recipe there runs
# at the end of `just check`.
import? 'just/local.just'
