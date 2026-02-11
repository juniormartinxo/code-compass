# ARCHITECTURE.md — Code Compass

## 1) Visão geral

**Code Compass** é um **Context Platform** para codebases: um **MCP Server** (Node/NestJS) expõe ferramentas padronizadas para agentes (Codex/Gemini/Claude) consultarem a base com **evidência** (trecho + path + linhas). Um **Indexer/ML Worker** (Python) faz ingestão, chunking, embeddings e atualizações incrementais. A camada de vetores é o **Qdrant** (local no MVP; service-ready depois).

**Pilares**
- **Evidence-first**: resposta boa = tem *path + linha + snippet*.
- **Local-first, scale-ready**: começa offline, vira serviço compartilhado sem replatform.
- **Governança**: read-only por default, allowlist, audit trail e política de acesso por contexto.

---

## 2) Componentes

### 2.1 MCP Server (Node/NestJS)
Responsável por:
- Expor **tools MCP**: `search_code`, `open_file`, `ask_code` (MVP).
- Validar inputs (anti path traversal), aplicar allowlist/blocklist.
- Consultar Qdrant, enriquecer com contexto do filesystem/git quando necessário.
- Emitir **audit logs** para rastreabilidade.

**Não faz**:
- chunking, embeddings, rerank pesado (isso é do Python worker).
- escrita no repo (read-only).

### 2.2 Indexer / ML Worker (Python)
Responsável por:
- Descobrir arquivos (repo root + allowlist/blocklist).
- Chunking semântico:
  - AST onde possível (foco: TS/JS, Python, etc.).
  - fallback heurístico (markdown/seções; split por funções/blocos).
- Gerar embeddings (provider pluggable).
- Upsert no Qdrant com payload rico.
- Indexação incremental: reprocessar **somente o que mudou**.

### 2.3 Vector DB (Qdrant)
Responsável por:
- Armazenar vetores e payload (metadados).
- Executar busca semântica com filtros por payload.
- Retornar topK com score.

### 2.4 (Opcional) Metastore local (SQLite)
Recomendado para MVP/Dev:
- Estado operacional: checkpoints, hashes por arquivo, runs de indexação, auditoria local.
- Pode ser substituído por Postgres gerenciado quando virar serviço.

> Se não existir metastore no MVP, o worker pode derivar estado via `.index_state.json` + hashes; mas SQLite facilita governança e debug.

---

## 3) Fluxos principais

### 3.1 Ingestão e indexação (full)
1. Operator roda `make up` (sobe Qdrant).
2. Operator roda `make index`.
3. Python worker:
   - varre `REPO_ROOT` respeitando allowlist/blocklist.
   - gera chunks.
   - gera embeddings.
   - upsert no Qdrant (collection configurável via `QDRANT_COLLECTION`).
4. Resultado: repositório indexado e pronto para consultas via MCP.

### 3.2 Indexação incremental
Objetivo: custo previsível e atualização rápida.

Estratégia (padrão):
- Para cada arquivo elegível, calcular `file_hash` (conteúdo).
- Se o hash mudou (ou commit mudou), reindexar.
- Para cada chunk, gerar `chunk_hash` e compor o `point_id`.

Pseudo:
- `file_changed = (hash_atual != hash_armazenado)`
- `chunk_id = <repo>:<commit>:<path>:<chunk_hash>`

Ações:
- `upsert` pontos novos/atualizados.
- (Opcional) apagar pontos antigos daquele arquivo/commit com `filter` por `path` + `commit`.

### 3.3 Consulta (RAG via MCP)
1. Agent chama `search_code` com query e filtros.
2. MCP Server:
   - valida query e filtros
   - consulta embeddings (ou chama serviço de embeddings, se necessário)
   - consulta Qdrant com `search + filter`
3. Resposta retorna:
   - `path`, `startLine`, `endLine`
   - `snippet` (ou `textRef`)
   - `score`
4. Se necessário, agent chama `open_file` para confirmar fonte de verdade.

---

## 4) Modelo de dados

### 4.1 Qdrant: collection configurável (`QDRANT_COLLECTION`)
**Vector**
- `size`: conforme embeddings (ex.: 1536/3072)
- `distance`: `Cosine` (default recomendado)

**Point**
- `id`: string única (determinística)
  - formato: `<repo>:<commit>:<path>:<chunkHash>`
- `vector`: embedding do chunk
- `payload` (metadados, JSON):
  - `repo`: string
  - `branch`: string (opcional)
  - `commit`: string (`HEAD` ou SHA)
  - `path`: string
  - `language`: string (`ts`, `js`, `py`, `md`, etc.)
  - `startLine`: number
  - `endLine`: number
  - `symbols`: string[] (opcional)
  - `kind`: `"code" | "doc"`
  - `text`: string (MVP) **OU** `textRef`: string (escala)

**Filtros típicos**
- `repo == X`
- `pathPrefix == "apps/api"`
- `language in ["ts","tsx"]`
- `commit == "HEAD"` (ou sha fixo)

### 4.2 Metastore (opcional)
Tabelas sugeridas:
- `index_runs(id, mode, started_at, finished_at, status, error)`
- `files(path, repo, file_hash, last_commit, last_indexed_at)`
- `chunks(chunk_id, path, chunk_hash, start_line, end_line, last_commit)`
- `audit_log(ts, tool, user, query, filters, result_count)`

---

## 5) Tools MCP (contrato)

### 5.1 `search_code`
**Objetivo:** localizar trechos relevantes com evidência.
- Input:
  - `query: string`
  - `filters?: { repo?, pathPrefix?, language?, commit? }`
  - `topK?: number`
- Output:
  - `results: Array<{ path, startLine, endLine, score, snippet? }>`
  - `queryId` (opcional) para auditoria

### 5.2 `open_file`
**Objetivo:** fonte de verdade.
- Input:
  - `path: string`
  - `range?: { startLine, endLine }`
- Output:
  - `path`
  - `content`
  - `startLine`, `endLine`

### 5.3 `ask_code`
**Objetivo:** responder perguntas sobre o código com evidências (RAG no MCP).
- Input:
  - `query: string`
  - `scope?: { type: "repo"|"repos"|"all", ... }`
  - `repo?: string` (modo compatível quando `scope` não é enviado)
  - `topK?: number`
  - `pathPrefix?: string`
  - `language?: string`
  - `minScore?: number`
  - `llmModel?: string`
- Output:
  - `answer: string`
  - `evidences: Array<{ repo, path, startLine, endLine, score, snippet }>`
  - `meta: { scope, topK, minScore, llmModel, collection, totalMatches, contextsUsed, elapsedMs }`

> V1: `find_symbol`, `git_log`, `git_blame`, `search_docs`, rerank.

---

## 6) Chunking strategy (diretrizes)

### 6.1 Objetivo do chunking
- preservar unidade semântica
- garantir “context window fit”
- reduzir duplicação (overlap controlado)
- otimizar recall sem perder precisão

### 6.2 Regras recomendadas
- Código:
  - preferir chunk por **função/classe** (AST)
  - fallback: split por blocos e limites de tokens
- Docs:
  - chunk por heading/seção (Markdown)
- Overlap:
  - 10–20% do tamanho do chunk para capturar contexto adjacente
- Metadados:
  - sempre guardar `startLine/endLine`
  - guardar `symbols` quando detectável

---

## 7) Retrieval strategy (diretrizes)

### 7.1 MVP (sem rerank)
- Dense vector search no Qdrant
- filtros por payload (repo/path/lang)
- topK baixo (5–12)

### 7.2 V1 (qualidade)
- Híbrido: dense + sparse (ou lexical paralelo)
- Rerank topN (ex.: 50 → rerank → 10)
- Deduplicação por path e “proximidade” de linhas

---

## 8) Segurança e governança

### 8.1 Guardrails obrigatórios
- **READ_ONLY=true** por default
- Allowlist/blocklist rígidos
- Anti path traversal (`../`, symlinks, normalização de path)
- Nunca executar shell com input do usuário sem sanitização
- Logs de auditoria (tool calls)

### 8.2 Escopo e multi-tenant (quando virar serviço)
- Namespaces por time/projeto
- ACL por repo/pathPrefix
- Auditoria por usuário e client

---

## 9) Observabilidade

Métricas mínimas:
- Latência P95 do `search_code`
- `no_hit_rate` (queries sem resultado)
- `evidence_rate` (respostas com path/linha)
- volume de indexação por dia (arquivos/chunks)
- erro por provider (embeddings, qdrant)

Logs:
- requests por tool (sem vazar conteúdo sensível)
- queryId correlacionando tool calls

---

## 10) Ambientes e escalabilidade

### 10.1 Local (MVP)
- Qdrant via Docker (volume local)
- Python worker local
- MCP server local
- ideal para prova de valor

### 10.2 Shared (V1/V2)
- Qdrant como serviço em infra da empresa
- Worker rodando em CI ou job schedule (incremental por merge)
- MCP server em cluster (stateless)
- metastore em Postgres gerenciado (quando existir)

---

## 11) Decisões de design (ADR-lite)

### Decisão 1 — Separar MCP server e indexer
**Motivo:** isolamento de carga e responsabilidades.  
MCP server precisa ser estável e previsível; indexer é batch pesado e evolui rápido.

### Decisão 2 — Qdrant como vector store
**Motivo:** local-first com runway para virar serviço sem trocar API/stack.

### Decisão 3 — Evidence-first
**Motivo:** reduzir alucinação e melhorar confiança do time.

---

## 12) Backlog técnico recomendado (próximos passos)

MVP:
- Implementar `search_code/open_file/ask_code`
- Indexer full + incremental
- Payload padrão no Qdrant
- Guardrails (allowlist, traversal, read-only)
- Makefile + quickstart

V1:
- Rerank e dedupe
- Hybrid retrieval
- git integration (`blame/log`)
- avaliação automática (golden queries)
- metastore consolidado (SQLite → Postgres quando houver)

V2:
- symbol graph (def/ref)
- multi-tenant e ACL
- policy packs e compliance
- cache e warming
