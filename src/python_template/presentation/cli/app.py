"""Main entry point for cli"""

from __future__ import annotations

import argparse
import pathlib
import sys

from python_template import VERSION
from python_template.commands import load_commands
from python_template.commands.registry import COMMAND_REGISTRY
from python_template.logger import setup_logging


def main(args: list[str] | None = None) -> None:
    """Main entry point to CLI portion of application"""
    if args is None:
        args: list[str] = sys.argv[1:]
    root = create_root_parser()
    subparser = root.add_subparsers(dest="command", required=True)
    load_commands("python_template.commands")
    commands = COMMAND_REGISTRY.values()
    print("commands: ", commands)
    for command in commands:
        cmd_instance = command()
        cmd_instance.register(subparser)
    options = root.parse_args(args)
    logger = setup_logging(
        options.debug,
        options.log_file,
        options.log_file_interval,
        options.log_file_backup_count,
    )
    logger.info(f"Options: {options}")
    logger.info(f"args: {args}")
    raise SystemExit(options.func(options))


def create_root_parser() -> argparse.ArgumentParser:
    """Create root parser with global options

    :return: ArgumentParser
    """
    parser = argparse.ArgumentParser(
        prog="python_template", description="Application description"
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
        "--log-file", help="Path to log file", type=pathlib.Path, required=False
    )
    return parser


if __name__ == "__main__":
    main()
