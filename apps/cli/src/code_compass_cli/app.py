from __future__ import annotations

import os
import subprocess
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
        llm_model=os.getenv("LLM_MODEL", "gpt-oss:latest"),
        debug=debug,
        mcp_command=os.getenv("MCP_COMMAND"),
        toad_profile=os.getenv("TOAD_PROFILE"),
    )

    client = ToadAcpClient(profile=config.toad_profile, debug=config.debug)

    console.print(Panel.fit("Enviando pergunta ao Toad (ACP)...", style="cyan"))

    try:
        response = client.ask(question)
    except RuntimeError as exc:
        console.print(Panel.fit(str(exc), style="red"))
        raise typer.Exit(code=1)

    console.print(response)


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

    try:
        subprocess.run([command, *args], check=True)
    except FileNotFoundError as exc:
        console.print(Panel.fit(f"Comando não encontrado: {exc}", style="red"))
        raise typer.Exit(code=1)
    except subprocess.CalledProcessError as exc:
        console.print(Panel.fit(f"Erro ao executar Toad: {exc}", style="red"))
        raise typer.Exit(code=1)
