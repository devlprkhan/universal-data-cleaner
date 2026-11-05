"""Command-line entry point for local batch audits."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ._version import __version__
from .cleaner import DataCleaner
from .contract import DataContract
from .ingestion import read_csv_safe
from .reporting import CleanerReport


def build_parser() -> argparse.ArgumentParser:
    """Build the ``python -m data_cleaner`` argument parser."""
    parser = argparse.ArgumentParser(
        prog="data-cleaner",
        description="Leak-safe data cleaning and batch audits.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit = subparsers.add_parser(
        "audit",
        help="Audit a CSV batch and print a report.",
        description=(
            "Read a CSV safely, then report its profile, contract findings, "
            "and cleaner decisions."
        ),
    )
    audit.add_argument("csv", type=Path, help="CSV file to audit.")
    source = audit.add_mutually_exclusive_group()
    source.add_argument(
        "--contract",
        type=Path,
        help="JSON contract file used for ingestion and drift checks.",
    )
    source.add_argument(
        "--cleaner",
        type=Path,
        help="Fitted DataCleaner artifact; uses its contract and decisions.",
    )
    audit.add_argument(
        "--name",
        default=None,
        help="Dataset name shown in the profile (defaults to the file stem).",
    )
    audit.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Report format written to stdout or --output.",
    )
    audit.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write the report to this file instead of stdout.",
    )
    audit.add_argument(
        "--no-profile",
        action="store_true",
        help="Skip the column-level profile for faster large-file audits.",
    )
    audit.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Exit with status 1 when warnings are present.",
    )
    return parser


def _load_contract(path: Path) -> DataContract:
    return DataContract.from_json(path.read_text(encoding="utf-8"))


def _run_audit(args: argparse.Namespace) -> int:
    contract: DataContract | None = None
    cleaner: DataCleaner | None = None
    if args.contract is not None:
        contract = _load_contract(args.contract)
    if args.cleaner is not None:
        cleaner = DataCleaner.load(args.cleaner)
        contract = cleaner.fitted_contract()

    frame, ingestion = read_csv_safe(
        args.csv,
        contract=contract,
        on_error="ignore",
    )
    dataset_name = args.name or args.csv.stem
    if cleaner is not None:
        report = CleanerReport.from_cleaner(
            cleaner,
            frame,
            source=ingestion.source,
            name=dataset_name,
            ingestion=ingestion,
            include_profile=not args.no_profile,
        )
    else:
        report = CleanerReport.from_frame(
            frame,
            source=ingestion.source,
            name=dataset_name,
            contract=contract,
            ingestion=ingestion,
            include_profile=not args.no_profile,
        )

    rendered = (
        report.to_markdown()
        if args.format == "markdown"
        else report.to_json(indent=2) + "\n"
    )
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(f"Wrote {args.format} report to {args.output}", file=sys.stderr)

    failed = not report.success or (args.fail_on_warning and report.has_warnings)
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return a process exit status."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "audit":
        try:
            return _run_audit(args)
        except (OSError, ValueError, TypeError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    parser.print_help()
    return 2


if __name__ == "__main__":  # pragma: no cover - exercised via `python -m`
    raise SystemExit(main())
