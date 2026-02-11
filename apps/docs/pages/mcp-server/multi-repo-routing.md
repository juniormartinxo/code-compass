# MCP Server: Multi-repo e Scope

Este guia documenta o contrato atualizado das tools `search_code`, `ask_code` e `open_file` no MCP Server, incluindo suporte a multi-repo via `scope` e o modo compatível com `repo`.

## Resumo das mudanças

- `search_code` e `ask_code` agora aceitam `scope` (opcional) para buscar em 1 repo, múltiplos repos ou todos.
- `repo` continua aceito por compatibilidade quando `scope` não é enviado.
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

## Regras de compatibilidade

- Se `scope` **não** for enviado, o MCP espera `repo` e equivale a `scope: { type: "repo", repo }`.
- Se `scope` for enviado, ele é a fonte de verdade; `repo` (se existir) é ignorado.

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
    "collection": "compass__3584__manutic_nomic_embed_code"
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
    "collection": "compass__3584__manutic_nomic_embed_code",
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
- O arquivo deve estar dentro de `<CODEBASE_ROOT>/<repo>` ou `REPO_ROOT` (modo compat).
- `path` absoluto e `..` são bloqueados.
- Escape via symlink é bloqueado via `realpath`.

## Observabilidade

Todos os resultados agora carregam `repo` e o `meta.scope` devolve o escopo efetivo. Isso permite rastrear de qual repositório veio cada evidência.

## Nota sobre payload `repo`

O filtro por `scope` depende do payload `repo` estar presente na collection do Qdrant. Se sua indexação ainda grava apenas `repo_root`, o MCP não consegue filtrar por repo de forma precisa. Neste caso:

- `scope: { type: "repo" | "repos" }` funciona como best effort (retorna resultados com `repo` `(unknown)`).
- Para ativar o filtro preciso, ajuste o indexer para gravar `repo` no payload.

## Compatibilidade com clientes antigos

Clientes que enviam apenas `repo` continuam funcionando sem alterações. Para novos clientes, recomenda-se migrar para `scope`.
