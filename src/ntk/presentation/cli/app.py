"""Main entry point for cli."""

from __future__ import annotations

import argparse
import asyncio
import inspect
import pathlib
import sys
import typing

import logfire

from ntk import __version__
from ntk.controllers import load_command_groups
from ntk.controllers.registry import COMMAND_REGISTRY
from ntk.database.db import initialize_database
from ntk.logger import setup_logging

if typing.TYPE_CHECKING:
    from ntk.models.output import Output

    class ConsoleRenderable(typing.Protocol):
        """Object that can render itself for CLI output."""

        def to_console(self) -> str:
            """Return the CLI representation."""


logfire.configure()


async def _resolve_output(output: typing.Awaitable[Output]) -> Output:
    """Resolve an async controller output for the synchronous CLI entry point."""
    return await output


def main(args: list[str] | None = None) -> None:
    """Run CLI portion of application."""
    initialize_database()
    if args is None:
        args = sys.argv[1:]
    root = create_root_parser()
    subparser = root.add_subparsers(dest="command", required=True)
    load_command_groups()
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
    result = parsed.func(options)
    if inspect.isawaitable(result):
        output = asyncio.run(
            _resolve_output(typing.cast("typing.Awaitable[Output]", result)),
        )
    else:
        output = typing.cast("Output", result)
    if output.exit_code == 0:
        result = typing.cast("ConsoleRenderable", output.result)
        print(result.to_console())  # noqa: T201
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
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--log-file-interval",
        type=int,
        help="How often (in number of days) to rotate log file",
    )
    parser.add_argument(
        "--log-file-backup-count",
        type=int,
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
