# MCP Client Quickstart (Local STDIO)

Este repositório usa `apps/mcp-server` em `stdio` com **MCP JSON-RPC 2.0**.

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

- `CODEBASE_ROOT=<raiz>/code-base` (modo multi-repo)
- `QDRANT_URL=http://localhost:6333` (se ausente)
- `QDRANT_COLLECTION_BASE=compass__manutic_nomic_embed` (se ausente)

Se você usa múltiplos repos em `code-base/`, defina:

- `CODEBASE_ROOT=/path/para/code-base`
- Opcional: `ALLOW_GLOBAL_SCOPE=true` para habilitar `scope: { type: "all" }`

## Configuração do cliente (Codex)

Use o template em `apps/docs/assets/codex-config-example.toml` e ajuste o path absoluto para o seu clone local.

Importante sobre escopo em `ask_code`:

- `scope` é obrigatório nas tools `ask_code` e `search_code`.
- Garanta que os dados indexados tenham `payload.repo` preenchido (indexações antigas podem precisar reindexação).

## Fluxo E2E recomendado

1. No cliente, chamar `search_code` com um termo existente (ex.: `bootstrap`).
2. Pegar `path`, `startLine` e `endLine` de um resultado.
3. Chamar `open_file` para esse `path` com range curto.
4. Validar que o texto retornado confere com o arquivo local.
5. Testar segurança com `open_file` usando `../../etc/passwd` (deve retornar bloqueio `FORBIDDEN`).

### Exemplos de input `ask_code`

Escopo por repo (recomendado):

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "ask_code",
    "arguments": {
      "scope": { "type": "repo", "repo": "golyzer" },
      "query": "Como funciona o Modo de Interação?",
      "topK": 5,
      "minScore": 0.6,
      "grounded": true
    }
  }
}
```

## Troubleshooting rápido

- **"Sem evidencia suficiente"**
  - Confirme `QDRANT_COLLECTION_BASE` no cliente/MCP e no indexador.
  - Reindexe para garantir `payload.repo` nos pontos antigos (`make index-all`).
- **"Global scope não está habilitado"**
  - Defina `ALLOW_GLOBAL_SCOPE=true` antes de subir o MCP server.
- **"Campo \"vector\" é obrigatório"**
  - O MCP não conseguiu gerar embeddings.
  - Verifique `OLLAMA_URL` e `EMBEDDING_MODEL` no MCP server.

### Exemplos de input com `scope`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "scope": { "type": "repo", "repo": "repo-a" },
      "query": "bootstrap",
      "topK": 5,
      "vector": [0.1, 0.2]
    }
  }
}
```

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "scope": { "type": "repos", "repos": ["repo-a", "repo-b"] },
      "query": "qdrant",
      "topK": 5,
      "vector": [0.1, 0.2]
    }
  }
}
```

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "scope": { "type": "all" },
      "query": "config",
      "topK": 5,
      "vector": [0.1, 0.2]
    }
  }
}
```
