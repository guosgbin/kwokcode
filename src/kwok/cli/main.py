from __future__ import annotations

import asyncio
import sys

from kwok.cli.arg_parser import build_parser
from kwok.cli.cmd.cmd_base_rpc import run
from kwok.cli.cmd.cmd_interactive import run_interactive
from kwok.cli.cmd.cmd_prompt import run_prompt
from kwok.cli.cmd.cmd_server import run_server_action
from kwok.config import init_config


def main() -> None:
    config = init_config()
    args = build_parser().parse_args()
    if args.command == "server":
        sys.exit(run_server_action(args.server_action, config))
    if args.command == "prompt":
        sys.exit(asyncio.run(run_prompt(args.prompt, config.port, config.llm.timeout)))
    if args.command == "interactive":
        sys.exit(asyncio.run(run_interactive(config.port, config.llm.timeout)))
    sys.exit(asyncio.run(run(args.method, config.port)))


if __name__ == "__main__":
    main()