from __future__ import annotations

import asyncio

import acp

from .agent import CodeCompassAgent


def main() -> None:
    agent = CodeCompassAgent()
    asyncio.run(acp.run_agent(agent))


if __name__ == "__main__":
    main()
