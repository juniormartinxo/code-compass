# MCP Client Quickstart (Local STDIO)

Este repositório usa `apps/mcp-server` em `stdio` com protocolo NDJSON próprio das tools (`search_code` e `open_file`).

## Golden Path adotado

- Cliente: **Codex (config TOML)**.
- Motivo: já existe padrão de configuração versionado no projeto para Codex (`mcp_servers` em TOML).

## Pré-requisitos

1. `pnpm` instalado.
2. Qdrant rodando (`make up`).
3. Indexação já executada (`make index` ou equivalente), para `search_code` retornar hits reais.

## Subir MCP server local

```bash
pnpm mcp:start
```

O script `bin/dev-mcp` define defaults seguros:

- `REPO_ROOT=<raiz do repositório>`
- `QDRANT_URL=http://localhost:6333` (se ausente)
- `QDRANT_COLLECTION=code_chunks` (se ausente)

## Configuração do cliente (Codex)

Use o template em `apps/docs/assets/codex-config-example.toml` e ajuste o path absoluto para o seu clone local.

## Fluxo E2E recomendado

1. No cliente, chamar `search_code` com um termo existente (ex.: `bootstrap`).
2. Pegar `path`, `startLine` e `endLine` de um resultado.
3. Chamar `open_file` para esse `path` com range curto.
4. Validar que o texto retornado confere com o arquivo local.
5. Testar segurança com `open_file` usando `../../etc/passwd` (deve retornar bloqueio `FORBIDDEN`).
