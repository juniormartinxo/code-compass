# MCP Server (`apps/mcp-server`)

Servidor MCP em NestJS com transporte `stdio` (NDJSON/LSP) e `http` (JSON-RPC em `/mcp`) com tools `search_code`, `open_file` e `ask_code`.

## Rodando

```bash
pnpm -C apps/mcp-server build
pnpm -C apps/mcp-server mcp:stdio
```

Modo dev:

```bash
pnpm -C apps/mcp-server mcp:dev
```

Modo HTTP:

```bash
pnpm -C apps/mcp-server start:http
```

Variáveis HTTP:

- `MCP_HTTP_HOST` (default `0.0.0.0`)
- `MCP_HTTP_PORT` (default `3001`)
- `MCP_SERVER_MODE=http` (alternativa ao `--transport http`)

## Protocolo STDIO (NDJSON)

Cada linha em `stdin` é um request JSON:

```json
{
  "id": "req-1",
  "tool": "search_code",
  "input": {
    "scope": { "type": "repo", "repo": "acme-monorepo" },
    "query": "find qdrant",
    "topK": 10,
    "pathPrefix": "apps/indexer/",
    "vector": [0.12, -0.43, 0.08],
    "contentType": "all",
    "strict": false
  }
}
```

Resposta de sucesso (`stdout`, uma linha):

```json
{
  "id": "req-1",
  "ok": true,
  "output": {
    "results": [
      {
        "repo": "acme-monorepo",
        "score": 0.912,
        "path": "apps/indexer/indexer/qdrant_store.py",
        "startLine": 120,
        "endLine": 168,
        "snippet": "..."
      }
    ],
    "meta": {
      "scope": { "type": "repo", "repos": ["acme-monorepo"] },
      "repo": "acme-monorepo",
      "topK": 10,
      "pathPrefix": "apps/indexer/",
      "contentType": "all",
      "strict": false,
      "collection": "compass__3584__manutic_nomic_embed_code__code",
      "collections": [
        {
          "name": "compass__3584__manutic_nomic_embed_code__code",
          "contentType": "code",
          "hits": 10,
          "latencyMs": 8,
          "status": "ok"
        },
        {
          "name": "compass__3584__manutic_nomic_embed_code__docs",
          "contentType": "docs",
          "hits": 3,
          "latencyMs": 7,
          "status": "ok"
        }
      ]
    }
  }
}
```

Resposta de erro:

```json
{
  "id": "req-1",
  "ok": false,
  "error": {
    "code": "BAD_REQUEST",
    "message": "Campo \"vector\" é obrigatório neste ambiente..."
  }
}
```

## Tool `open_file`

### Input

- `repo` (string, obrigatório, nome do repositório dentro de `CODEBASE_ROOT`)
- `path` (string, obrigatório, relativo ao root do repo resolvido)
- `startLine` (number opcional, default `1`, min `1`)
- `endLine` (number opcional, default `startLine + 50`, clamp para no máximo `200` linhas)
- `maxBytes` (number opcional, default `200000`, max `1000000`)

### Output

- `path` (string normalizada, relativa)
- `startLine` (number)
- `endLine` (number)
- `totalLines` (`number | null`)
- `text` (string com conteúdo no range solicitado)
- `truncated` (boolean)

### Segurança

- Bloqueia path vazio, `\0`, path absoluto e `..`.
- Resolve `realpath` do root e do arquivo para impedir escape por symlink.
- Bloqueia acesso fora de `<CODEBASE_ROOT>/<repo>` com erro `FORBIDDEN`.
- Bloqueia arquivo binário (byte nulo ou decode UTF-8 inválido) com `UNSUPPORTED_MEDIA`.

## Tool `search_code`

### Input

- `scope` (obrigatório):
  - `{ type: "repo", repo: string }`
  - `{ type: "repos", repos: string[] }`
  - `{ type: "all" }` (exige `ALLOW_GLOBAL_SCOPE=true`)
- `query` (string, obrigatório, `trim`, 1..500)
- `topK` (number opcional, default `10`, clamp `1..20`)
- `pathPrefix` (string opcional, `trim`, max 200, bloqueia `\0` e `..`)
- `vector` (fallback operacional obrigatório neste módulo enquanto não houver provider de embeddings em Node)
- `contentType` (string opcional: `code`, `docs`, `all`; default `all`)
- `strict` (boolean opcional; default `false`; quando `true`, falha se alguma coleção estiver indisponível)

### Output

- `results` (máx 20):
  - `repo` (string)
  - `score` (number)
  - `path` (string)
  - `startLine` (`number | null`)
  - `endLine` (`number | null`)
  - `snippet` (string, normalizado e truncado para até 300 chars)
- `meta`: `{ scope, repo?, topK, pathPrefix?, contentType, strict, collection, collections }`

### Regras importantes

- `snippet` vem **somente** de `payload.text` no retorno do Qdrant.
- Se não houver `payload.text`, retorna `"(no snippet)"`.
- Este servidor **não lê arquivos do disco** para montar snippet.

## Tool `ask_code`

Executa o fluxo RAG completo no MCP: embedding da pergunta, busca no Qdrant, enriquecimento de contexto com `open_file` e chamada da LLM.

### Input

- `scope` (obrigatório):
  - `{ type: "repo", repo: string }`
  - `{ type: "repos", repos: string[] }`
  - `{ type: "all" }` (exige `ALLOW_GLOBAL_SCOPE=true`)
- `query` (string, obrigatório)
- `topK` (number opcional, default `5`, clamp `1..20`)
- `pathPrefix` (string opcional)
- `language` (string opcional, ex: `ts`, `py`, `.tsx`)
- `minScore` (number opcional, default `0.6`)
- `llmModel` (string opcional, default `LLM_MODEL`)
- `contentType` (string opcional: `code`, `docs`, `all`; default `all`)
- `strict` (boolean opcional; default `false`)

### Output

- `answer` (string)
- `evidences` (array de evidências no mesmo formato do `search_code`)
- `meta`:
  - `scope`, `repo?`, `topK`, `minScore`, `llmModel`
  - `contentType`, `strict`
  - `collection` (deprecated)
  - `collections`
  - `totalMatches` e `contextsUsed`
  - `elapsedMs`
  - `pathPrefix?`, `language?`

### Regras importantes

- Usa `OLLAMA_URL` + `EMBEDDING_MODEL` para gerar embedding da pergunta.
- Usa `OLLAMA_URL` + `llmModel` para gerar resposta final.
- A política de prompt e seleção de contexto fica centralizada no MCP.

## Qdrant (env vars)

- `QDRANT_URL` (default: `http://localhost:6333`)
- `QDRANT_COLLECTION_BASE` (default: `compass__3584__manutic_nomic_embed_code`)
- `QDRANT_COLLECTION_CODE` (opcional; default: `<base>__code`)
- `QDRANT_COLLECTION_DOCS` (opcional; default: `<base>__docs`)
- `QDRANT_API_KEY` (opcional)

## CODEBASE_ROOT (env var)

- `CODEBASE_ROOT` (obrigatório): pasta contendo múltiplos repositórios (`<CODEBASE_ROOT>/<repo>`).
  - `open_file` só lê dentro de `<CODEBASE_ROOT>/<repo>`.
  - validação de segurança de repo: bloqueia `\0`, `..` e separadores (`/` e `\\`).

## ALLOW_GLOBAL_SCOPE (env var)

- `ALLOW_GLOBAL_SCOPE` (opcional, default `false`):
  - quando `true`, habilita `scope: { type: "all" }` em `search_code`/`ask_code`.
  - quando ausente ou diferente de `true`, `scope: { type: "all" }` retorna `FORBIDDEN`.

### Carregamento de `.env.local`

No bootstrap, o MCP server tenta carregar automaticamente (nesta ordem):

1. `apps/mcp-server/.env.local`
2. `apps/mcp-server/.env`
3. `.env.local` na raiz do monorepo
4. `.env` na raiz do monorepo

Isso permite usar `QDRANT_COLLECTION_BASE=goapice_3584_manutic_nomic_embed_code` em `.env.local` sem precisar exportar no comando.

## Testes

```bash
pnpm -C apps/mcp-server test
pnpm -C apps/mcp-server test:stdio
pnpm -C apps/mcp-server test:open-file
```

`test:stdio` roda um harness que spawna o servidor stdio, envia 1 request NDJSON e valida shape básico da resposta.
