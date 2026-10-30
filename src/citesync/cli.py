"""Command line: ``citesync check|write|init|config|rules|explain``.

Exit codes: 0 when the files agree (after ``write``, once it has written), 1 on any error
finding (that ``write`` may not fix), 2 when citesync couldn't run. ``write --diff`` exits 1
when it would change a file or can't read one, as ``ruff format --diff`` does. ``write`` then wrote nothing,
unless moving a written file into place failed: files moved before it stay written.
"""

import argparse
import io
import json
import os
import re
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from citesync.check import Finding, check
from citesync.config import Config, did_you_mean, find_root, git_top, load_config, render
from citesync.errors import CheckError
from citesync.rules import DOCS_URL, RULES, explain, url

JSON_VERSION = 1
_ANSI = {"error": "1;31", "warning": "1;33", "info": "1;34"}
_GITHUB_LEVEL = {"error": "error", "warning": "warning", "info": "notice"}
_SARIF_LEVEL = {"error": "error", "warning": "warning", "info": "note"}
_CONTROL = re.compile("[\x00-\x1f\x7f-\x9f]")  # C0 and C1: a file's ESC could retitle the terminal or hide lines


# Imports that only `write`, `--version` or the JSON report need wait until they're used:
# importlib.metadata and the writer's tomlkit cost check about a quarter of its run.


def _version() -> str:
    from importlib.metadata import version  # noqa: PLC0415

    return version("citesync")


class _VersionAction(argparse.Action):
    """``--version``, reading the installed version only when asked."""

    def __init__(self, option_strings: list[str], dest: str = argparse.SUPPRESS, **_: object) -> None:
        super().__init__(option_strings, dest, nargs=0, default=argparse.SUPPRESS, help="show the version and exit")

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,  # noqa: ARG002
        values: object,  # noqa: ARG002
        option_string: str | None = None,  # noqa: ARG002
    ) -> None:
        print(f"{parser.prog} {_version()}")
        parser.exit()


class _Formatter(argparse.RawDescriptionHelpFormatter):
    """argparse's formatter, sized as ``shutil.get_terminal_size`` would size it, without importing shutil.

    Raw, so the epilog's exit-code table keeps its lines.

    argparse builds one for every argument it adds, and shutil's imports cost 3 ms a run.
    """

    def __init__(
        self, prog: str, indent_increment: int = 2, max_help_position: int = 24, width: int | None = None
    ) -> None:
        if width is None:
            try:
                columns = int(os.environ["COLUMNS"])
            except (KeyError, ValueError):
                columns = 0
            if columns <= 0:
                try:
                    columns = os.get_terminal_size(sys.__stdout__.fileno()).columns  # ty: ignore[unresolved-attribute]
                except (AttributeError, ValueError, OSError):
                    columns = 0
            width = (columns if columns > 0 else 80) - 2
        super().__init__(prog, indent_increment, max_help_position, width)


class _Parser(argparse.ArgumentParser):
    def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        kwargs.setdefault("formatter_class", _Formatter)
        if sys.version_info >= (3, 14):
            kwargs.setdefault("suggest_on_error", True)
        super().__init__(*args, **kwargs)


def _directory(value: str) -> Path:
    path = Path(value)
    if not path.is_dir():
        msg = f"not a directory: {value}"
        raise argparse.ArgumentTypeError(msg)
    return path


_DESCRIPTION = """Check that CITATION.cff, codemeta.json, .zenodo.json and the package manifests
(pyproject.toml, Cargo.toml, package.json) agree, and rewrite them to match one source file."""
_EPILOG = f"""exit codes:
  0  no error finding (warnings and info don't fail)
  1  an error finding; with write --diff, a change to make or a file it can't read
  2  citesync couldn't run: a bad config or option, a missing source file

config: the first of citesync.toml, .citesync.toml, [tool.citesync] in pyproject.toml,
[workspace.metadata.citesync] or [package.metadata.citesync] in Cargo.toml, or "citesync" in package.json

docs: {DOCS_URL.rsplit("/", 1)[0]}"""


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="citesync", description=_DESCRIPTION, epilog=_EPILOG)
    parser.add_argument("-V", "--version", action=_VersionAction)
    sub = parser.add_subparsers(dest="command", metavar="command")
    root = _Parser(add_help=False)
    root.add_argument(
        "--root",
        type=_directory,
        help="repo root (default: the nearest directory up with a citation file or config, else the git repo's top)",
    )
    root.add_argument("--source", help="the file the others must agree with; overrides config")
    report = _Parser(add_help=False, parents=[root])
    report.add_argument(
        "--format", choices=("text", "json", "github", "sarif"), default="text", help="output format (default: text)"
    )
    report.add_argument("--json", action="store_const", const="json", dest="format", help="alias of --format json")
    report.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="colour the text output (default: auto, on a terminal unless NO_COLOR or FORCE_COLOR say otherwise)",
    )
    shown = report.add_mutually_exclusive_group()
    shown.add_argument(
        "-v", "--verbose", action="store_true", help="also print info: fields not compared, manifests left out"
    )
    shown.add_argument("-q", "--quiet", action="store_true", help="print only errors, and no summary")
    check = "report where the files disagree with the source"
    sub.add_parser("check", parents=[report], help=check, description=f"{check.capitalize()}.", epilog=_EPILOG)
    write = "rewrite the files to agree with the source"
    write_ = sub.add_parser(
        "write",
        parents=[report],
        help=write,
        description=f"{write.capitalize()}, changing only what check reports,\nand a manifest only for the fields"
        " in write-manifests.",
        epilog=_EPILOG,
    )
    write_.add_argument("--diff", action="store_true", help="print the changes as a unified diff and write nothing")
    init = "write a CITATION.cff from codemeta.json, .zenodo.json and the manifests"
    init_ = sub.add_parser(
        "init",
        parents=[root],
        help=init,
        description=f"W{init[1:]}, when the repo has none.\nEach field comes from the first file that"
        " holds it: --source, then the files in the order above.",
    )
    init_.add_argument("--diff", action="store_true", help="print the new file as a unified diff and write nothing")
    sub.add_parser("config", parents=[root], help="print the config in use and where it came from")
    rules = sub.add_parser("rules", help="list the rules")
    rules.add_argument("--format", choices=("text", "json"), default="text", help="output format (default: text)")
    sub.add_parser("explain", help="print a rule's documentation").add_argument("rule", help="a rule id")
    return parser


def main(argv: list[str] | None = None) -> int:  # noqa: C901, PLR0911 - a return per command
    """Run the command line and return its exit code."""
    _utf8_streams()
    args = _parse(argv)
    if args.command in {"rules", "explain"}:
        return _rules(args)
    try:
        args.root = args.root or find_root(Path.cwd())
        config = load_config(args.root, args.source)
        if args.command == "config":
            print(f"# root: {args.root}\n{render(config)}")
            return 0
        if args.command == "init":
            return _init(args.root, config, diff=args.diff)
        if getattr(args, "diff", False):
            return _write_diff(args.root, config)
        written, skipped, fixed = _write(args.root, config) if args.command == "write" else ({}, {}, None)
        findings, files, unused = check(args.root, config)
    except CheckError as err:
        print(f"citesync: {err}", file=sys.stderr)
        return 2
    except Exception as err:  # noqa: BLE001 - a crash is "couldn't check", never exit 1 ("they disagree")
        print(f"citesync: {args.root}: unexpected error: {type(err).__name__}: {err}", file=sys.stderr)
        return 2
    failed = any(f.severity == "error" for f in findings)
    if args.command == "check" and failed and args.format == "text" and not args.quiet:
        fixed = _fixable(args.root, config)  # only a failing check pays for write's imports
    if not args.quiet:
        for rule in unused:
            print(f"citesync: warning: ignore entry {rule!r} matched no finding", file=sys.stderr)
    if args.command == "write":
        findings = _written(findings, written, skipped, config, args)
    _report(findings, files, args, None if fixed is None else len(fixed))
    return 1 if failed else 0


def _written(
    findings: list[Finding],
    written: dict[str, str],
    skipped: dict[tuple[str, str], str],
    config: Config,
    args: argparse.Namespace,
) -> list[Finding]:
    """Print what write wrote, and return ``findings`` with what to do about each."""
    from citesync.write import advice  # noqa: PLC0415

    if not args.quiet:  # stdout stays one document in the json and github formats
        shown = {(f.file, f.term) for f in findings}
        for path in written:  # a field left out of a created file has no finding to carry its reason
            left = [f"{t}: {why}" for (p, t), why in sorted(skipped.items()) if p == path and (p, t) not in shown]
            wrote = f"wrote {path}" + (f", leaving out {'; '.join(left)}" if left else "")
            print(wrote, file=sys.stdout if args.format == "text" else sys.stderr)
    return [
        f if f.severity == "info" else replace(f, message=f"{f.message} ({advice(f, config, skipped)})")
        for f in findings
    ]


def _parse(argv: list[str] | None) -> argparse.Namespace:
    """The parsed command line; with no command, the help on stderr and exit 2."""
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help(sys.stderr)
        parser.exit(2)
    if getattr(args, "diff", False) and getattr(args, "format", "text") != "text":
        parser.error("--diff prints a unified diff; it takes no --format")
    return args


def _utf8_streams() -> None:
    """Print UTF-8 whatever the streams were opened with: a Windows pipe is cp1252, which can't print most names."""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper) and stream.encoding.lower().replace("-", "") != "utf8":
            stream.reconfigure(encoding="utf-8")


def _write(
    root: Path, config: Config, *, dry_run: bool = False
) -> tuple[dict[str, str], dict[tuple[str, str], str], list[Finding]]:
    from citesync.write import write  # noqa: PLC0415

    written, skipped, _, fixed = write(root, config, dry_run=dry_run)
    return written, skipped, fixed


def _fixable(root: Path, config: Config) -> list[Finding] | None:
    """The findings write would fix, or None when it would fail: the count is a hint, not the check."""
    try:
        return _write(root, config, dry_run=True)[2]
    except Exception:  # noqa: BLE001
        return None


def _write_diff(root: Path, config: Config) -> int:
    """Print the edits write would make as a unified diff, and any file it can't read on stderr."""
    from citesync.write import write  # noqa: PLC0415

    texts, _, unreadable, fixed = write(root, config, dry_run=True)
    sys.stdout.write(_diff(root, texts))
    if texts:
        print(f"would fix {_count(len(fixed), 'finding')} in {_count(len(texts), 'file')}", file=sys.stderr)
    for f in unreadable:  # the diff can't show a file write never touches, so say so
        print(f"{f.where}: error[unreadable] {f.message}", file=sys.stderr)
    return 1 if texts or unreadable else 0


def _init(root: Path, config: Config, *, diff: bool) -> int:
    """Write a new CITATION.cff, or with ``diff`` print it as a diff from nothing."""
    from citesync.write import init  # noqa: PLC0415

    text, skipped, splits = init(root, config, dry_run=diff)
    left = "; ".join(f"{term}: {why}" for term, why in skipped.items())
    notes = [
        f"check the name split: {name!r} became given {given!r}, family {family!r}" for name, given, family in splits
    ]
    if diff:  # the notes go to stderr, so stdout stays a diff a tool can read
        sys.stdout.write(_diff(root, {"CITATION.cff": text}))
        for line in ([f"leaving out {left}"] if left else []) + notes:
            print(line, file=sys.stderr)
        return 0
    print("wrote CITATION.cff" + (f", leaving out {left}" if left else ""))
    for line in notes:
        print(line)
    return 0


def _report(findings: list[Finding], files: int, args: argparse.Namespace, fixed: int | None) -> None:
    """Print ``findings`` in ``args.format``.

    ``fixed`` counts what write fixed, or what it could fix after a failed check; None when not counted.
    """
    counts = {s: sum(f.severity == s for f in findings) for s in ("error", "warning", "info")}
    if args.format == "json":
        summary = {"files": files, "errors": counts["error"], "warnings": counts["warning"], "info": counts["info"]}
        report = {
            "version": JSON_VERSION,
            "tool": {"name": "citesync", "version": _version()},
            "summary": summary,
            "findings": [f.as_dict() for f in findings],
        }
        print(json.dumps(report, indent=2))
        return
    if args.quiet:
        findings = [f for f in findings if f.severity == "error"]
    elif not args.verbose:
        findings = [f for f in findings if f.severity != "info"]
    # Code scanning and annotations place a file by its path in the repo, not under citesync's root.
    top, root = git_top(args.root), args.root.resolve()
    prefix = f"{root.relative_to(top).as_posix()}/" if top and top != root else ""
    if args.format == "sarif":
        print(json.dumps(_sarif(findings, prefix), indent=2))
        return
    total = _total(counts, files, args.command, fixed)
    if args.format == "github":
        for f in findings:
            where = f"file={_escape(prefix + f.file, property_=True)}," if f.file else ""
            where += f"line={f.line},col={f.column}," if f.line else ""
            message = _escape(f"{_printable(f.text)}\nhelp: {RULES[f.rule].help}")
            print(f"::{_GITHUB_LEVEL[f.severity]} {where}title=citesync {f.rule}::{message}")
        if not args.quiet:  # GitHub shows only the first 10 annotations of a level, so give the totals
            print(f"::notice::citesync: {total}")
        return
    colour = _colour(args.color)
    for f in findings:
        where = _printable(f"{f.where}: ") if f.file else ""
        severity = f"\033[{_ANSI[f.severity]}m{f.severity}\033[0m" if colour else f.severity
        print(f"{where}{severity}[{f.rule}] {_printable(f.text)}\n  help: {RULES[f.rule].help}")
    if not args.quiet:
        print(total)


def _total(counts: dict[str, int], files: int, command: str, fixed: int | None) -> str:
    """The summary line: what is left, and what write fixed or could fix."""
    if command == "write":
        return f"{fixed} fixed, {counts['error'] + counts['warning']} left in {_count(files, 'file')}"
    total = f"{_count(counts['error'], 'error')}, {_count(counts['warning'], 'warning')} in {_count(files, 'file')}"
    return total if fixed is None else f"{total}\n{fixed} fixable with `citesync write`"


def _sarif(findings: list[Finding], prefix: str) -> dict[str, Any]:
    """One SARIF 2.1.0 log: a rule entry for each rule that appears, a result for each finding on a file.

    ``prefix`` is the root's path in its git repo, ending in ``/``, or empty at the repo's top.
    """
    findings = [f for f in findings if f.file]  # code scanning may refuse a result with no location
    results = []
    for f in findings:
        result: dict[str, Any] = {
            "ruleId": f.rule,
            "level": _SARIF_LEVEL[f.severity],
            "message": {"text": f.text},
        }
        location: dict[str, Any] = {"artifactLocation": {"uri": f"{prefix}{f.file}"}}
        if f.line:
            location["region"] = {"startLine": f.line, "startColumn": f.column or 1}
        result["locations"] = [{"physicalLocation": location}]
        results.append(result)
    driver = {
        "name": "citesync",
        "version": _version(),
        "informationUri": "https://github.com/simonvanlierde/citesync",
        "rules": [
            {
                "id": rule,
                "shortDescription": {"text": RULES[rule].summary},
                "helpUri": url(rule),
                "help": {"text": RULES[rule].help},
                "defaultConfiguration": {"level": _SARIF_LEVEL[RULES[rule].severity]},
            }
            for rule in sorted({f.rule for f in findings})
        ],
    }
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        # positions counts code points; SARIF would read columns as UTF-16 units
        "runs": [{"tool": {"driver": driver}, "columnKind": "unicodeCodePoints", "results": results}],
    }


def _diff(root: Path, texts: dict[str, str]) -> str:
    """The unified diff from each file to its new text, with git's ``a/`` and ``b/`` prefixes.

    A file write would create is diffed from ``/dev/null``, as git shows a new file.
    """
    import difflib  # noqa: PLC0415

    return "".join(
        line
        for rel, new in texts.items()
        for line in difflib.unified_diff(
            (root / rel).read_bytes().decode("utf-8").splitlines(keepends=True) if (root / rel).exists() else [],
            new.splitlines(keepends=True),
            f"a/{rel}" if (root / rel).exists() else "/dev/null",
            f"b/{rel}",
        )
    )


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def _colour(when: str) -> bool:
    """Colour by ``--color``; with ``auto``, on a terminal.

    Under ``auto``, ``NO_COLOR`` turns it off; ``FORCE_COLOR`` turns it on, or off as 0 or false.
    """
    if when != "auto":
        return when == "always"
    if os.environ.get("NO_COLOR"):
        return False
    if force := os.environ.get("FORCE_COLOR"):
        return force.lower() not in {"0", "false"}
    return sys.stdout.isatty()


def _rules(args: argparse.Namespace) -> int:
    """``citesync rules`` and ``citesync explain``."""
    if args.command == "explain":
        if args.rule not in RULES:
            hint = did_you_mean(args.rule, RULES)
            print(f"citesync: unknown rule {args.rule!r}; `citesync rules` lists them{hint}", file=sys.stderr)
            return 2
        print(explain(args.rule), end="")
        return 0
    if args.format == "json":
        rules = [
            {"rule": rule, "severity": r.severity, "summary": r.summary, "url": url(rule)} for rule, r in RULES.items()
        ]
        print(json.dumps(rules, indent=2))
        return 0
    width = max(map(len, RULES))
    for rule, r in RULES.items():
        print(f"{rule:<{width}}  {r.severity:<7}  {r.summary}")
    return 0


def _printable(text: str) -> str:
    r"""``text`` with each control character written as ``\xNN``."""
    return _CONTROL.sub(lambda m: f"\\x{ord(m[0]):02x}", text)


def _escape(text: str, *, property_: bool = False) -> str:
    """Escape for a workflow command; a property value also escapes ``:`` and ``,``."""
    text = text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    return text.replace(":", "%3A").replace(",", "%2C") if property_ else text


if __name__ == "__main__":
    sys.exit(main())
