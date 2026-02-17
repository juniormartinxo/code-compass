# CLI - nova CLI (Python)

Este guia descreve a **nova CLI em Python** (Typer + Rich) integrada ao Toad via ACP.

## Pre-requisitos

- Python 3.12+
- Dependência `agent-client-protocol` (SDK ACP)
- Para `chat`: `batrachian-toad` (requer Python 3.14+)

## Instalação

```bash
cd apps/cli
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Alternativa via Makefile:

```bash
make py:setup
apps/cli/.venv/bin/code-compass ask "onde fica o handler do search_code?" --repo code-compass
```

## Comandos

### `ask`

```bash
code-compass ask "onde fica o handler do search_code?" --repo code-compass
```

### `chat`

```bash
code-compass chat
```

## Flags

- `--topk <n>`: número de evidências (default 10)
- `--path-prefix <prefix>`: filtro por prefixo de path
- `--language <lang>`: filtro por linguagem/extensão
- `--repo <name>`: filtra por repositório
- `--min-score <n>`: score mínimo para considerar evidências
- `--timeout-ms <ms>`: timeout por request
- `--debug`: habilita logs

## Fluxo de execução

- `ask` usa ACP para conversar com o Toad e retornar a resposta.
- `chat` abre a TUI do Toad usando `TOAD_COMMAND`/`TOAD_ARGS` ou `python -m toad`.

## Configuração via env

- `LLM_MODEL`
- `MCP_COMMAND`
- `TOAD_PROFILE`
- `TOAD_COMMAND` (binário do toad, opcional)
- `TOAD_ARGS` (args extras para o toad)

## Observações

- O comando `chat` exige `batrachian-toad` instalado em Python 3.14+ ou `TOAD_COMMAND` apontando para um binário compatível.
