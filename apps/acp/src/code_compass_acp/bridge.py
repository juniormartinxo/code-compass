from __future__ import annotations

import asyncio
import json
import os
import shlex
import signal
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4


@dataclass
class McpBridgeConfig:
    command: list[str]
    llm_model: str | None = None


class McpBridge:
    def __init__(self, config: McpBridgeConfig) -> None:
        self._config = config
        self._process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._stderr_tail: deque[str] = deque(maxlen=30)
        self._pending: dict[str | int, asyncio.Future[dict[str, Any]]] = {}

    async def start(self) -> None:
        if self._process and self._process.returncode is None:
            return

        env = os.environ.copy()
        if self._config.llm_model:
            env["LLM_MODEL"] = self._config.llm_model

        self._stderr_tail.clear()
        self._process = await asyncio.create_subprocess_exec(
            *self._config.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        self._reader_task = asyncio.create_task(self._read_loop())
        self._stderr_task = asyncio.create_task(self._read_stderr_loop())
        try:
            await self._handshake()
        except Exception:
            await self.abort()
            raise

    async def ask_code(
        self,
        arguments: dict[str, Any],
        cancel_event: asyncio.Event,
    ) -> dict[str, Any]:
        await self.start()

        req_id = str(uuid4())
        future: asyncio.Future[dict[str, Any]] = asyncio.get_event_loop().create_future()
        self._pending[req_id] = future

        request = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {"name": "ask_code", "arguments": arguments},
        }
        await self._write(request)

        cancel_task = asyncio.create_task(cancel_event.wait())
        done, _ = await asyncio.wait(
            [future, cancel_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        if cancel_task in done:
            await self.abort()
            raise asyncio.CancelledError()

        cancel_task.cancel()
        response = future.result()
        return self._parse_tools_call_result(response)

    async def abort(self) -> None:
        if not self._process:
            return

        if self._process.returncode is None:
            self._process.send_signal(signal.SIGTERM)
            try:
                await asyncio.wait_for(self._process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                self._process.kill()
        await self._close_io()

    async def close(self) -> None:
        if not self._process:
            return

        if self._process.stdin and not self._process.stdin.is_closing():
            self._process.stdin.close()

        try:
            await asyncio.wait_for(self._process.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            self._process.kill()

        await self._close_io()

    async def _close_io(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
            self._reader_task = None
        if self._stderr_task:
            self._stderr_task.cancel()
            self._stderr_task = None
        self._process = None

    async def _handshake(self) -> None:
        init_req = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        init_resp = await self._request(init_req)
        protocol = init_resp.get("result", {}).get("protocolVersion")
        if not protocol:
            raise RuntimeError("MCP sem protocolVersion no initialize")

        await self._write({"jsonrpc": "2.0", "method": "initialized"})

        tools_resp = await self._request(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        )
        tools = tools_resp.get("result", {}).get("tools", [])
        if not isinstance(tools, list) or not any(t.get("name") == "ask_code" for t in tools):
            raise RuntimeError("MCP sem tool ask_code disponível")

    async def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        req_id = payload.get("id")
        if req_id is None:
            raise RuntimeError("Request MCP sem id")

        future: asyncio.Future[dict[str, Any]] = asyncio.get_event_loop().create_future()
        self._pending[req_id] = future
        await self._write(payload)
        return await future

    async def _write(self, payload: dict[str, Any]) -> None:
        if not self._process or not self._process.stdin:
            raise RuntimeError("Processo MCP não inicializado")

        line = json.dumps(payload, ensure_ascii=False)
        self._process.stdin.write(f"{line}\n".encode("utf-8"))
        await self._process.stdin.drain()

    async def _read_loop(self) -> None:
        if not self._process or not self._process.stdout:
            return

        buffer = b""
        try:
            while True:
                chunk = await self._process.stdout.read(4096)
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        msg = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    msg_id = msg.get("id")
                    if msg_id in self._pending:
                        future = self._pending.pop(msg_id)
                        if not future.done():
                            future.set_result(msg)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            self._fail_pending(exc)
        finally:
            self._fail_pending(self._build_process_exit_error("MCP encerrou stdout"))
            self._process = None

    async def _read_stderr_loop(self) -> None:
        if not self._process or not self._process.stderr:
            return

        try:
            while True:
                chunk = await self._process.stderr.readline()
                if not chunk:
                    break
                line = chunk.decode("utf-8", errors="replace").strip()
                if line:
                    self._stderr_tail.append(line)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            self._stderr_tail.append(f"[stderr-loop] {exc}")

    def _build_process_exit_error(self, message: str) -> RuntimeError:
        details: list[str] = []
        if self._process and self._process.returncode is not None:
            details.append(f"exit={self._process.returncode}")
        if self._stderr_tail:
            stderr_excerpt = " | ".join(self._stderr_tail)
            if len(stderr_excerpt) > 1200:
                stderr_excerpt = f"...{stderr_excerpt[-1200:]}"
            details.append(f"stderr={stderr_excerpt}")
        if details:
            return RuntimeError(f"{message} ({'; '.join(details)})")
        return RuntimeError(message)

    def _fail_pending(self, exc: Exception) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(exc)
        self._pending.clear()

    def _parse_tools_call_result(self, response: dict[str, Any]) -> dict[str, Any]:
        if "error" in response:
            error = response.get("error")
            if isinstance(error, dict):
                message = str(error.get("message", "Erro MCP"))
            else:
                message = "Erro MCP"
            raise RuntimeError(message)

        result = response.get("result")
        if not isinstance(result, dict):
            raise RuntimeError("Resposta MCP sem result válido")

        content = result.get("content")
        if not isinstance(content, list) or not content:
            raise RuntimeError("Resposta MCP sem conteúdo")

        first = content[0]
        if not isinstance(first, dict):
            raise RuntimeError("Resposta MCP sem bloco válido")

        text = first.get("text")
        if not isinstance(text, str):
            raise RuntimeError("Resposta MCP sem texto")

        if response.get("result", {}).get("isError") is True:
            raise RuntimeError(text)

        try:
            output = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Resposta MCP sem JSON válido") from exc

        if not isinstance(output, dict):
            raise RuntimeError("Resposta MCP sem output válido")

        return output


def resolve_mcp_command() -> list[str]:
    raw_command = os.getenv("MCP_COMMAND", "").strip()
    if raw_command:
        try:
            parsed = shlex.split(raw_command)
        except ValueError as exc:
            raise RuntimeError(f"MCP_COMMAND inválido: {exc}") from exc

        if not parsed:
            raise RuntimeError("MCP_COMMAND vazio")

        return parsed

    repo_root = Path(__file__).resolve().parents[4]
    entry = repo_root / "apps" / "mcp-server" / "dist" / "main.js"
    return ["node", str(entry), "--transport", "stdio"]


def build_bridge(llm_model: str | None = None) -> McpBridge:
    return McpBridge(McpBridgeConfig(command=resolve_mcp_command(), llm_model=llm_model))
