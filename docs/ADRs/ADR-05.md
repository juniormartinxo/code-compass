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