"""Command line: ``citesync check|write|config|rules|explain``.

Exit codes: 0 when the files agree (after ``write``, once it has written), 1 on any error
finding (that ``write`` may not fix), 2 when citesync couldn't run (and ``write`` wrote nothing).
"""

import argparse
import json
import os
import sys
from dataclasses import replace
from importlib.metadata import version
from pathlib import Path

from citesync.check import Finding, check
from citesync.config import load_config, render
from citesync.errors import CheckError
from citesync.rules import DOCS_URL, RULES, explain
from citesync.write import advice, write

JSON_VERSION = 1
_ANSI = {"error": "1;31", "warning": "1;33", "info": "1;34"}
_GITHUB_LEVEL = {"error": "error", "warning": "warning", "info": "notice"}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="citesync", description=__doc__.splitlines()[0])
    parser.add_argument("--version", action="version", version=f"%(prog)s {version('citesync')}")
    sub = parser.add_subparsers(dest="command", required=True)
    root = argparse.ArgumentParser(add_help=False)
    root.add_argument("--root", type=Path, default=Path(), help="repo root (default: the current directory)")
    root.add_argument("--source", help="the file the others must agree with; overrides config")
    report = argparse.ArgumentParser(add_help=False, parents=[root])
    report.add_argument("--format", choices=("text", "json", "github"), default="text")
    report.add_argument("--json", action="store_const", const="json", dest="format", help="alias of --format json")
    shown = report.add_mutually_exclusive_group()
    shown.add_argument("-v", "--verbose", action="store_true", help="also print not-checked info")
    shown.add_argument("-q", "--quiet", action="store_true", help="print only errors, and no summary")
    sub.add_parser("check", parents=[report], help="report where the files disagree")
    sub.add_parser("write", parents=[report], help="rewrite the files to agree with the source")
    sub.add_parser("config", parents=[root], help="print the config in use and where it came from")
    rules = sub.add_parser("rules", help="list the rules")
    rules.add_argument("--format", choices=("text", "json"), default="text")
    sub.add_parser("explain", help="print a rule's documentation").add_argument("rule", help="a rule id")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the command line and return its exit code."""
    args = _parser().parse_args(argv)
    if args.command in {"rules", "explain"}:
        return _rules(args)
    try:
        config = load_config(args.root, args.source)
        if args.command == "config":
            print(render(config))
            return 0
        written = write(args.root, config) if args.command == "write" else []
        findings, files = check(args.root, config)
    except CheckError as err:
        print(f"citesync: {err}", file=sys.stderr)
        return 2
    except Exception as err:  # noqa: BLE001 - a crash is "couldn't check", never exit 1 ("they disagree")
        print(f"citesync: {args.root}: unexpected error: {type(err).__name__}: {err}", file=sys.stderr)
        return 2
    for rule in config.ignore:
        if not any(f.rule == rule for f in findings):
            print(f"citesync: warning: ignore entry {rule!r} matched no finding", file=sys.stderr)
    findings = [f for f in findings if f.rule not in config.ignore]
    if args.command == "write":
        if not args.quiet:  # stdout stays one document in the json and github formats
            for path in written:
                print(f"wrote {path}", file=sys.stdout if args.format == "text" else sys.stderr)
        findings = [
            f if f.severity == "info" else replace(f, message=f"{f.message} ({advice(f, config)})") for f in findings
        ]
    _report(findings, files, args)
    return 1 if any(f.severity == "error" for f in findings) else 0


def _report(findings: list[Finding], files: int, args: argparse.Namespace) -> None:
    counts = {s: sum(f.severity == s for f in findings) for s in ("error", "warning", "info")}
    if args.format == "json":
        summary = {"files": files, "errors": counts["error"], "warnings": counts["warning"], "info": counts["info"]}
        report = {
            "version": JSON_VERSION,
            "tool": {"name": "citesync", "version": version("citesync")},
            "summary": summary,
            "findings": [f.as_dict() for f in findings],
        }
        print(json.dumps(report, indent=2))
        return
    if args.quiet:
        findings = [f for f in findings if f.severity == "error"]
    elif not args.verbose:
        findings = [f for f in findings if f.severity != "info"]
    total = f"{_count(counts['error'], 'error')}, {_count(counts['warning'], 'warning')} in {_count(files, 'file')}"
    if args.format == "github":
        for f in findings:
            where = f"file={_escape(f.file, property_=True)}," if f.file else ""
            where += f"line={f.line},col={f.column}," if f.line else ""
            message = _escape(f"{f.term}: {f.message}" if f.term else f.message)
            print(f"::{_GITHUB_LEVEL[f.severity]} {where}title=citesync {f.rule}::{message}")
        if not args.quiet:  # GitHub shows only the first 10 annotations of a level, so give the totals
            print(f"::notice::citesync: {total}")
        return
    colour = _colour()
    for f in findings:
        where = f"{f.file}{f':{f.line}:{f.column}' if f.line else ''}: " if f.file else ""
        severity = f"\033[{_ANSI[f.severity]}m{f.severity}\033[0m" if colour else f.severity
        print(f"{where}{severity}[{f.rule}] " + (f"{f.term}: {f.message}" if f.term else f.message))
    if not args.quiet:
        print(total)


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def _colour() -> bool:
    """Colour on a terminal. ``NO_COLOR`` turns it off; ``FORCE_COLOR`` turns it on, or off as 0 or false."""
    if os.environ.get("NO_COLOR"):
        return False
    if force := os.environ.get("FORCE_COLOR"):
        return force.lower() not in {"0", "false"}
    return sys.stdout.isatty()


def _rules(args: argparse.Namespace) -> int:
    """``citesync rules`` and ``citesync explain``."""
    if args.command == "explain":
        if args.rule not in RULES:
            print(f"citesync: unknown rule {args.rule!r}; `citesync rules` lists them", file=sys.stderr)
            return 2
        print(explain(args.rule), end="")
        return 0
    if args.format == "json":
        rules = [
            {"rule": rule, "severity": r.severity, "summary": r.summary, "url": f"{DOCS_URL}#{rule}"}
            for rule, r in RULES.items()
        ]
        print(json.dumps(rules, indent=2))
        return 0
    width = max(map(len, RULES))
    for rule, r in RULES.items():
        print(f"{rule:<{width}}  {r.severity:<7}  {r.summary}")
    return 0


def _escape(text: str, *, property_: bool = False) -> str:
    """Escape for a workflow command; a property value also escapes ``:`` and ``,``."""
    text = text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    return text.replace(":", "%3A").replace(",", "%2C") if property_ else text


if __name__ == "__main__":
    sys.exit(main())
