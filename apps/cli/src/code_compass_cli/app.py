from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

from .config import CliConfig
from .toad_acp import ToadAcpClient

app = typer.Typer(add_completion=False, help="CLI do Code Compass (Toad + ACP + Rich)")
console = Console()


@app.callback()
def main() -> None:
    """CLI do Code Compass."""
    return None


@app.command()
def ask(
    question: str = typer.Argument(..., help="Pergunta para o Code Compass"),
    repo: Optional[str] = typer.Option(None, "--repo", help="Filtro por repo"),
    path_prefix: Optional[str] = typer.Option(None, "--path-prefix", help="Filtro por prefixo"),
    language: Optional[str] = typer.Option(None, "--language", help="Filtro por linguagem"),
    top_k: int = typer.Option(10, "--topk", help="Número de evidências"),
    min_score: float = typer.Option(0.6, "--min-score", help="Score mínimo"),
    grounded: bool = typer.Option(False, "--grounded", help="Restringe resposta ao contexto"),
    show_meta: bool = typer.Option(False, "--show-meta", help="Exibe metadados do MCP"),
    show_context: bool = typer.Option(False, "--show-context", help="Exibe evidências usadas"),
    timeout_ms: int = typer.Option(120_000, "--timeout-ms", help="Timeout em ms"),
    debug: bool = typer.Option(False, "--debug", help="Debug"),
):
    config = CliConfig(
        repo=repo,
        path_prefix=path_prefix,
        language=language,
        top_k=top_k,
        min_score=min_score,
        timeout_ms=timeout_ms,
        llm_model=os.getenv("LLM_MODEL"),
        debug=debug,
        mcp_command=os.getenv("MCP_COMMAND"),
        toad_profile=os.getenv("TOAD_PROFILE"),
    )

    client = ToadAcpClient(
        profile=config.toad_profile,
        debug=config.debug,
        repo=config.repo,
        path_prefix=config.path_prefix,
        language=config.language,
        top_k=config.top_k,
        min_score=config.min_score,
        llm_model=config.llm_model,
        grounded=grounded,
        show_meta=show_meta,
        show_context=show_context,
    )

    console.print(Panel.fit("Enviando pergunta ao Toad (ACP)...", style="cyan"))

    try:
        response = client.ask(question)
    except RuntimeError as exc:
        console.print(Panel.fit(str(exc), style="red"))
        raise typer.Exit(code=1)

    if client.chunks:
        console.print("\n".join(client.chunks))
    else:
        console.print(response)

    if show_meta or show_context:
        passthrough = response.get("_passthrough") if isinstance(response, dict) else None
        if isinstance(passthrough, dict):
            if show_meta:
                meta = passthrough.get("meta")
                if isinstance(meta, dict):
                    console.print(meta)
            if show_context:
                evidences = passthrough.get("evidences")
                if isinstance(evidences, list):
                    console.print(evidences)


@app.command()
def chat() -> None:
    """Abre a interface TUI do Toad."""
    command = os.getenv("TOAD_COMMAND", "")
    args = os.getenv("TOAD_ARGS", "").split()
    if not command:
        command = os.getenv("PYTHON_COMMAND", "python")
        args = ["-m", "toad", *args]

        check = subprocess.run(
            [command, "-c", "import toad"],
            capture_output=True,
            text=True,
        )
        if check.returncode != 0:
            console.print(
                Panel.fit(
                    "Módulo 'toad' não encontrado neste Python. Instale batrachian-toad "
                    "em um Python 3.14+ ou configure TOAD_COMMAND para o binário do Toad.",
                    style="red",
                )
            )
            raise typer.Exit(code=1)

    agent_cmd = _resolve_acp_agent_command()
    if agent_cmd:
        if len(args) >= 2 and args[0] == "-m" and args[1] == "toad":
            args = ["-m", "toad", "acp", *agent_cmd, *args[2:]]
        else:
            args = ["acp", *agent_cmd, *args]

    try:
        subprocess.run([command, *args], check=True)
    except FileNotFoundError as exc:
        console.print(Panel.fit(f"Comando não encontrado: {exc}", style="red"))
        raise typer.Exit(code=1)
    except subprocess.CalledProcessError as exc:
        console.print(Panel.fit(f"Erro ao executar Toad: {exc}", style="red"))
        raise typer.Exit(code=1)


def _resolve_acp_agent_command() -> list[str] | None:
    command = os.getenv("ACP_AGENT_CMD", "").strip()
    args = os.getenv("ACP_AGENT_ARGS", "").split()
    if not command:
        repo_root = Path(__file__).resolve().parents[4]
        default = repo_root / "apps" / "acp" / ".venv" / "bin" / "code-compass-acp"
        if default.exists():
            command = str(default)
    if not command:
        return None
    return [command, *args]
