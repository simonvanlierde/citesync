# Task runner: https://just.systems. `just` lists the recipes, `just <name>` runs one.
#
# `import?` skips a recipe file you did not scaffold. Recipes are prefixed
# (`py-`, `ts-`, `rs-`, `go-`) because imports share one namespace, except the few only
# one kind has, such as `pipeline` or `up`.
import? 'just/python.just'
import? 'just/ts.just'
import? 'just/rust.just'
import? 'just/go.just'
import? 'just/docker.just'

# List the recipes (what a bare `just` runs).
default:
    @just --list

# The stack checks CI runs. `just hooks` runs the git hooks, which CI also runs.
check:
    @just py-check

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

# Fix and format every stack here, as each stack's `fmt` recipe does.
fmt:
    @just py-fmt

# Run every git hook over the whole repo, not just staged files.
hooks:
    prek run -a

# Protect the default branch (no deletion, no force-push, linear history, PRs squash-merged after the always-on checks pass and one approval) and the v* tags. Turn on private vulnerability reporting. Safe to rerun.
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
    gh api -X PATCH repos/{owner}/{repo} -F allow_squash_merge=true -F allow_merge_commit=false -F allow_rebase_merge=false >/dev/null 2>"$err" || fail
    # Each file's "name" matches its file name, so the recipe needs no jq to read it.
    for name in main main-checks tags; do
        file=.github/rulesets/$name.json
        id=$(gh api "repos/{owner}/{repo}/rulesets?includes_parents=false" --jq ".[] | select(.name == \"$name\") | .id" 2>"$err") || fail
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

# Set the GitHub About box from your answers: description and a topic per stack. Adds topics, never removes yours. Safe to rerun.
repo-about:
    gh repo edit --description 'Keep CITATION.cff, codemeta.json, .zenodo.json and package manifests in step, mapped through CodeMeta crosswalks' --add-topic python
