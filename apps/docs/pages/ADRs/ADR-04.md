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