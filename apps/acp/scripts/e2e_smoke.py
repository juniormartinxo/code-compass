from __future__ import annotations

import asyncio
import os
import shlex
import sys
from pathlib import Path

import acp


async def main() -> None:
    default_cmd = Path(__file__).resolve().parents[1] / ".venv" / "bin" / "code-compass-acp"
    agent_cmd = os.getenv("ACP_AGENT_CMD", str(default_cmd))
    question = os.getenv("ACP_SMOKE_QUESTION", "onde fica o handler do search_code?")

    cmd_parts = shlex.split(agent_cmd)
    if not cmd_parts:
        raise RuntimeError("ACP_AGENT_CMD vazio")
    command, *args = cmd_parts

    async with acp.spawn_agent_process(
        lambda _client: None,
        command,
        *args,
        env=os.environ,
        transport_kwargs={"stderr": None},
    ) as (conn, _proc):
        await conn.initialize(protocol_version=acp.PROTOCOL_VERSION)
        session = await conn.new_session(cwd=os.getcwd(), mcp_servers=[])
        response = await conn.prompt([acp.text_block(question)], session_id=session.session_id)
        print(response.model_dump())
        if response.stop_reason == "refusal":
            print("Aviso: resposta recusada (verifique MCP_COMMAND, Qdrant e indexação).", file=sys.stderr)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        sys.exit(1)
