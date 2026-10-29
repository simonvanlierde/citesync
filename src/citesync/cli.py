"""Command line: ``citesync check|config``.

Exit codes: 0 when the files agree, 1 on any finding, 2 when citesync couldn't check.
"""

import argparse
import json
import sys
from pathlib import Path

from citesync.check import Finding, check
from citesync.config import load_config, render
from citesync.errors import CheckError

JSON_SCHEMA_VERSION = "1.0"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="citesync", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    root = argparse.ArgumentParser(add_help=False)
    root.add_argument("--root", type=Path, default=Path(), help="repo root (default: the current directory)")
    root.add_argument("--source", help="the file the others must agree with; overrides config")
    run = sub.add_parser("check", parents=[root], help="report where the files disagree")
    run.add_argument("--format", choices=("text", "json", "github"), default="text")
    run.add_argument("--json", action="store_const", const="json", dest="format", help="alias of --format json")
    run.add_argument("-v", "--verbose", action="store_true", help="also print NOT_CHECKED info")
    sub.add_parser("config", parents=[root], help="print the config in use and where it came from")
    sub.add_parser("write", parents=[root], help="not implemented in this build")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the command line and return its exit code."""
    args = _parser().parse_args(argv)
    try:
        config = load_config(args.root, args.source)
        if args.command == "config":
            print(render(config))
            return 0
        if args.command == "write":
            print("citesync: write is not implemented in this build", file=sys.stderr)
            return 2
        findings, info = check(args.root, config)
    except CheckError as err:
        print(f"citesync: {err}", file=sys.stderr)
        return 2
    _report(findings, info, args.format, verbose=args.verbose)
    return 1 if findings else 0


def _report(findings: list[Finding], info: list[Finding], fmt: str, *, verbose: bool) -> None:
    if fmt == "json":
        print(
            json.dumps(
                {
                    "schema_version": JSON_SCHEMA_VERSION,
                    "findings": [f.as_dict() for f in findings],
                    "info": [f.as_dict() for f in info],
                },
                indent=2,
            )
        )
        return
    shown = findings + (info if verbose else [])
    if fmt == "github":
        for f in shown:
            level = "notice" if f.code == "NOT_CHECKED" else "error"
            where = f"file={f.file}," if f.file else ""
            message = f"{f.term}: {f.detail}".replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
            print(f"::{level} {where}title=citesync {f.code}::{message}")
        return
    for f in shown:
        print(f)


if __name__ == "__main__":
    sys.exit(main())
