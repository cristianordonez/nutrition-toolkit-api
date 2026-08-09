"""Main entry point for cli."""

from __future__ import annotations

import argparse
import pathlib
import sys

from ntk import VERSION
from ntk.controllers import load_commands
from ntk.controllers.registry import COMMAND_REGISTRY
from ntk.logger import setup_logging


def main(args: list[str] | None = None) -> None:
    """Run CLI portion of application."""
    if args is None:
        args: list[str] = sys.argv[1:]
    root = create_root_parser()
    subparser = root.add_subparsers(dest="command", required=True)
    load_commands("ntk.controllers")
    controllers = COMMAND_REGISTRY.values()
    for controller in controllers:
        cmd_instance = controller()
        cmd_instance.register(subparser)
    parsed = root.parse_args(args)
    logger = setup_logging(
        parsed.log_file,
        parsed.log_file_interval,
        parsed.log_file_backup_count,
        debug=parsed.debug,
    )
    logger.debug("Controllers: %s", controllers)
    logger.debug("Options: %s", parsed)
    logger.debug("args: %s", args)
    options = parsed.options_model.model_validate(vars(parsed))
    output = parsed.func(options)
    if output.exit_code == 0:
        print(output.result.to_console())  # noqa: T201
    raise SystemExit(output.exit_code)


def create_root_parser() -> argparse.ArgumentParser:
    """Create root parser with global options.

    :return: ArgumentParser
    """
    parser = argparse.ArgumentParser(
        prog="ntk",
        description="Application description",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    parser.add_argument(
        "--log-file-interval",
        type=int,
        help="How often (in number of days) to rotate log file",
    )
    parser.add_argument(
        "--log-file-backup-count",
        type=str,
        help="Number of backup log files to keep",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--log-file",
        help="Path to log file",
        type=pathlib.Path,
        required=False,
    )
    return parser


if __name__ == "__main__":
    main()
