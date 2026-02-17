# CLI - comando ask (Python)

Este guia descreve o comando `ask` da nova CLI em Python usando Toad via ACP.

## Pre-requisitos

- Python 3.14+
- Dependência `acp`

## Como rodar

```bash
cd apps/cli
python -m venv .venv
source .venv/bin/activate
pip install -e .
code-compass ask "onde fica o handler do search_code?" --repo code-compass

# Abrir a UI do Toad
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

## Configuração via env

- `LLM_MODEL`
- `MCP_COMMAND`
- `TOAD_PROFILE`
- `TOAD_COMMAND` (binário do toad, opcional)
- `TOAD_ARGS` (args extras para o toad)
