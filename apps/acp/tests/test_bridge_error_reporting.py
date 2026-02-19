from __future__ import annotations

from code_compass_acp.bridge import McpBridge, McpBridgeConfig


def _bridge() -> McpBridge:
    return McpBridge(McpBridgeConfig(command=["python", "-c", "print('ok')"]))


def test_process_exit_error_includes_exit_code_and_stderr() -> None:
    bridge = _bridge()
    bridge._stderr_tail.extend(["line one", "line two"])  # type: ignore[attr-defined]
    bridge._process = type("Proc", (), {"returncode": 1})()  # type: ignore[attr-defined]

    error = bridge._build_process_exit_error("MCP encerrou stdout")  # type: ignore[attr-defined]

    message = str(error)
    assert "MCP encerrou stdout" in message
    assert "exit=1" in message
    assert "stderr=line one | line two" in message


def test_process_exit_error_without_details() -> None:
    bridge = _bridge()
    bridge._process = type("Proc", (), {"returncode": None})()  # type: ignore[attr-defined]

    error = bridge._build_process_exit_error("MCP encerrou stdout")  # type: ignore[attr-defined]

    assert str(error) == "MCP encerrou stdout"
