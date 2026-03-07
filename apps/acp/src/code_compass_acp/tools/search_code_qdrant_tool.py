from __future__ import annotations

from typing import Any


class SearchCodeQdrantTool:
    """
    Wrapper fino para manter compatibilidade entre runtime ADK e stack atual.

    O MCP server segue sendo o caminho principal de retrieval técnico.
    """

    def search(self, *, query: str, limit: int = 8) -> dict[str, Any]:
        _ = (query, limit)
        return {
            "answer": "",
            "evidences": [],
            "meta": {
                "status": "not_implemented",
                "reason": "Use o pipeline ask_code existente no MCP server.",
            },
        }
