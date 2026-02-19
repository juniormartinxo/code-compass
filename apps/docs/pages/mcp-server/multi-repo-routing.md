# MCP Server: Multi-repo e Scope

Este guia documenta o contrato atual das tools `search_code`, `ask_code` e `open_file` no MCP Server, com escopo obrigatório via `scope`.

## Resumo das mudanças

- `search_code` e `ask_code` exigem `scope` para buscar em 1 repo, múltiplos repos ou todos.
- `open_file` **não mudou**: continua exigindo `repo` e aplica as mesmas regras de segurança de filesystem.
- `scope: { type: "all" }` depende de `ALLOW_GLOBAL_SCOPE=true`.
- Resultados e evidências agora incluem `repo` para observabilidade.

## Tipos de `scope`

```json
{ "type": "repo", "repo": "nome-repo" }
```

```json
{ "type": "repos", "repos": ["repo-a", "repo-b"] }
```

```json
{ "type": "all" }
```

## Feature flag: `ALLOW_GLOBAL_SCOPE`

- Quando `ALLOW_GLOBAL_SCOPE=true`, `scope: { type: "all" }` é permitido.
- Quando ausente ou diferente de `true`, `scope: { type: "all" }` retorna `FORBIDDEN`.

## Contrato por tool

### `search_code`

Input (campos principais):

```json
{
  "scope": { "type": "repos", "repos": ["repo-a", "repo-b"] },
  "query": "find qdrant",
  "topK": 10,
  "pathPrefix": "apps/indexer/",
  "vector": [0.12, -0.43, 0.08]
}
```

Output (trecho relevante):

```json
{
  "results": [
    {
      "repo": "repo-a",
      "score": 0.912,
      "path": "apps/indexer/indexer/qdrant_store.py",
      "startLine": 120,
      "endLine": 168,
      "snippet": "..."
    }
  ],
  "meta": {
    "scope": { "type": "repos", "repos": ["repo-a", "repo-b"] },
    "topK": 10,
    "pathPrefix": "apps/indexer/",
    "collection": "compass_manutic_nomic_embed"
  }
}
```

### `ask_code`

Input (campos principais):

```json
{
  "scope": { "type": "repo", "repo": "repo-a" },
  "query": "qual banco de dados vetorial é usado?",
  "topK": 5,
  "minScore": 0.6
}
```

Output (trecho relevante):

```json
{
  "answer": "...",
  "evidences": [
    {
      "repo": "repo-a",
      "score": 0.87,
      "path": "apps/indexer/indexer/qdrant_store.py",
      "startLine": 120,
      "endLine": 168,
      "snippet": "..."
    }
  ],
  "meta": {
    "scope": { "type": "repo", "repos": ["repo-a"] },
    "topK": 5,
    "minScore": 0.6,
    "llmModel": "gpt-oss:latest",
    "collection": "compass_manutic_nomic_embed",
    "totalMatches": 12,
    "contextsUsed": 3,
    "elapsedMs": 1234
  }
}
```

### `open_file`

Input (continua igual):

```json
{
  "repo": "repo-a",
  "path": "apps/indexer/indexer/qdrant_store.py",
  "startLine": 120,
  "endLine": 168
}
```

Regras de segurança permanecem:

- `repo` obrigatório.
- O arquivo deve estar dentro de `<CODEBASE_ROOT>/<repo>`.
- `path` absoluto e `..` são bloqueados.
- Escape via symlink é bloqueado via `realpath`.

## Observabilidade

Todos os resultados agora carregam `repo` e o `meta.scope` devolve o escopo efetivo. Isso permite rastrear de qual repositório veio cada evidência.

## Nota sobre payload `repo`

O filtro por `scope` depende do payload `repo` estar consistente na collection do Qdrant. O MCP filtra por esse campo em `search_code` e `ask_code`.

Regras práticas:

- O indexador define `payload.repo` como o nome do `REPO_ROOT` de cada execução.
- Se você indexar com `REPO_ROOT=/.../code-base` (pasta agregadora), todos os pontos recebem `repo="code-base"`.
- Nesse cenário, `scope: { type: "repo" | "repos" }` não separa os sub-repos corretamente.
- Para multi-repo real, indexe cada subdiretório (`code-base/<repo>`) individualmente (ex.: `scripts/index-all.sh`).
- Para dados antigos sem `payload.repo`, reindexe para restaurar o filtro preciso por repositório.

## Observação de migração

Clientes que ainda enviavam apenas `repo` em `search_code`/`ask_code` devem migrar para `scope`.
