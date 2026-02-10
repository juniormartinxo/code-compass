# CLI - comando ask

Este guia descreve o modo interativo e o modo one-shot do comando `ask` no Code Compass.

## Pre-requisitos

- Qdrant rodando (`make up`)
- Indexacao realizada (`make index`)
- Build do MCP server (`pnpm -C apps/mcp-server build`)
- Ollama rodando localmente para embeddings e LLM

## Como rodar

### Interativo (TUI)

```bash
pnpm ask
```

Ou, se estiver usando o binario:

```bash
code-compass ask
```

### One-shot

```bash
pnpm ask "onde fica o handler do search_code?"
```

## Atalhos e comandos na TUI

- `Enter`: envia
- `Shift+Enter` ou `Ctrl+Enter`: quebra de linha
- `1..9`: abre a evidencia correspondente

Comandos:

- `/help`
- `/exit`
- `/clear`
- `/config`
- `/open <path>:<start>-<end>`
- `/sources`

## Evidencias

A resposta sempre inclui um bloco de evidencias com:

- `path:startLine-endLine (score)`
- snippet (ate 16 linhas)

Use `/open` ou a tecla numerica para abrir o trecho via `open_file`.

## Flags

- `--topk <n>`: numero de evidencias (default 10)
- `--pathPrefix <prefix>`: filtro por prefixo de path
- `--language <lang>`: filtro por linguagem/extensao (ex: `ts`, `tsx`, `.py`)
- `--repo <name>`: reservado (nao suportado no MCP MVP)
- `--debug`: habilita logs de debug
- `--timeout-ms <ms>`: timeout por request

## Configuracao via env

- `OLLAMA_URL` (default `http://localhost:11434`)
- `EMBEDDING_MODEL` (default `manutic/nomic-embed-code`)
- `LLM_MODEL` (default `gpt-oss:latest`)
- `MCP_COMMAND` (override do comando para iniciar o MCP server)
- `CODE_COMPASS_TIMEOUT_MS` (default `120000`)

O `MCP_COMMAND` deve apontar para o server em modo stdio. Exemplo:

```bash
MCP_COMMAND="node apps/mcp-server/dist/main.js --transport stdio"
```

## Troubleshooting rapido

- `Sem evidencia suficiente`: refine a pergunta ou use `--pathPrefix` e `--language`.
- `MCP server nao iniciado`: verifique se o build do MCP server existe em `apps/mcp-server/dist`.
- `Erro ao gerar embedding`: confirme que o Ollama esta rodando e o modelo existe.
