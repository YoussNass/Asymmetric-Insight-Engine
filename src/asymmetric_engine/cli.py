"""Command-line diagnostics for the Asymmetric Insight Engine."""

from __future__ import annotations

import argparse
import json
import platform
from collections.abc import Sequence

from asymmetric_engine import __version__


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="asymmetric-engine")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor", help="Validate the local package installation.")
    subparsers.add_parser("version", help="Print the package version.")
    return parser


def doctor_payload() -> dict[str, str]:
    """Return a deterministic, machine-readable installation diagnostic."""

    return {
        "package": "asymmetric-insight-engine",
        "python": platform.python_version(),
        "status": "ok",
        "version": __version__,
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface and return a process exit code."""

    args = _build_parser().parse_args(argv)
    if args.command == "doctor":
        print(json.dumps(doctor_payload(), sort_keys=True))
        return 0
    if args.command == "version":
        print(__version__)
        return 0
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
