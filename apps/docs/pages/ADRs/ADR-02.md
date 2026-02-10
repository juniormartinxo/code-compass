## ADR-002 — Usar Qdrant como Vector DB (Local-first, scale-ready)

**Status:** Aceito  
**Data:** 2026-02-08

### Contexto
Requisitos:
- Rodar **local/offline** no MVP,
- escalar para serviço compartilhado sem trocar stack no meio,
- suportar filtros por metadados (repo/path/lang/commit) com boa performance.

Alternativas:
- Chroma (muito bom para POC local, menos previsível como base corporativa).
- Mongo Atlas Vector Search (cloud-first, exige adoção Atlas/Search).
- pgvector (depende de Postgres gerenciado/padrão corporativo, que não existe hoje).

### Decisão
Adotar **Qdrant** como vector store:
- MVP: Qdrant via Docker local com volume persistente.
- Escala: Qdrant como serviço compartilhado mantendo a mesma API e modelo de dados.

### Consequências
**Positivas**
- Mesma API do MVP ao production-like.
- Boa filtragem por payload (crucial para codebase).
- Infra simples (um serviço principal) e operação previsível.

**Negativas**
- Um serviço a mais para empresa padronizar no futuro.
- Integração via SDK HTTP/gRPC (não é ORM como Prisma).

---

## ADR-003 — “Evidence-first” como regra do produto

**Status:** Aceito  
**Data:** 2026-02-08

### Contexto
Agentes de IA podem “alucinar” quando o contexto é fraco ou ambíguo. Em ambiente corporativo, confiança é requisito: o usuário precisa ver **de onde veio** a resposta.

### Decisão
Toda tool de recuperação deve retornar **evidência auditável**:
- `path`
- `startLine` / `endLine`
- `snippet` (ou referência para o trecho)
- `score` (ranking)

Se não houver evidência suficiente, o sistema deve preferir retornar “não encontrado/baixa confiança” em vez de inventar.

### Consequências
**Positivas**
- Aumenta confiança e adoção interna.
- Facilita code review e validação humana.
- Reduz risco de decisões erradas baseadas em resposta inventada.

**Negativas**
- Requer disciplina no chunking e no retorno das tools.
- Pode “parecer” menos mágico (mas é mais correto).

---

## ADR-004 — Payload rico no Vector DB (metadados no Qdrant)

**Status:** Aceito  
**Data:** 2026-02-08

### Contexto
Codebase exige filtros e recortes:
- repo específico, módulo, pathPrefix, linguagem, commit/branch, tipo de conteúdo (code/doc).
Sem metadados no índice, consultas viram “tiro no escuro” e o recall explode com baixa precisão.

### Decisão
Armazenar metadados no **payload** do Qdrant junto com o vetor.  
Padrão mínimo do payload:
- `repo`, `branch`, `commit`
- `path`, `language`
- `startLine`, `endLine`
- `kind` (`code`|`doc`)
- `symbols` (quando disponível)
- `text` (MVP) ou `textRef` (escala)

### Consequências
**Positivas**
- Consultas com filtro forte (melhor precisão).
- Suporta governança futura (ACL por repo/path).
- Suporta indexação incremental e limpeza por path/commit.

**Negativas**
- Payload cresce (custo de storage).
- Exige padronização rígida (schema e validação).

---

## ADR-005 — Indexação incremental por hash + commit (IDs determinísticos)

**Status:** Aceito  
**Data:** 2026-02-08

### Contexto
Reindexar toda a codebase constantemente é caro e lento. Precisamos atualizar “só o que mudou” e manter rastreabilidade.

### Decisão
- Calcular `file_hash` (conteúdo) para detectar mudanças.
- Gerar `chunk_hash` por chunk.
- Gerar `point_id` determinístico:
  - `<repo>:<commit>:<path>:<chunkHash>`
- Em mudança de arquivo, reindexar chunks e:
  - `upsert` dos novos
  - opcionalmente remover chunks antigos por filtro (`path` + `commit` anterior)

### Consequências
**Positivas**
- Performance e custo previsíveis.
- Rastreabilidade forte por commit/artefato.
- Facilita rollback (apontar para commit anterior).

**Negativas**
- Precisa de housekeeping (limpeza de chunks antigos) para não inflar.
- Requer cuidado com renames/moves (mapeamento de path).

---

## ADR-006 (Futuro) — Busca híbrida + rerank (V1)

**Status:** Proposto  
**Data:** 2026-02-08

### Contexto
Busca apenas vetorial pode falhar em:
- símbolos exatos, stack traces, strings, paths.
Rerank melhora precisão dos top resultados e reduz “resultado irrelevante” no topo.

### Decisão (proposta)
- V1: adicionar estratégia híbrida (dense + sparse/lexical) e rerank top-N.
- Implementar como passo adicional no Python worker ou no MCP server (dependendo do SLA).

### Consequências
**Positivas**
- Aumenta precisão de resultados.
- Melhor UX e menos frustração.

**Negativas**
- Mais custo computacional.
- Mais complexidade de tuning e avaliação.