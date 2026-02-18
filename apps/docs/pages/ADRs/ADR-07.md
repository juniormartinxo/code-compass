## ADR-07 — Split Code/Docs no Qdrant com Merge por RRF

**Status:** Aceito  
**Data:** 2026-02-18

### Contexto
- A busca semântica operava em uma coleção única.
- Documentação e código têm distribuições de score diferentes.
- Era necessário separar fisicamente os dados e manter distinção explícita de tipo.

### Decisão
- Adotar duas coleções no Qdrant:
  - `<stem>__code`
  - `<stem>__docs`
- Persistir `content_type` (`code` ou `docs`) no payload de todos os pontos.
- Em `contentType=all`, fazer busca paralela nas duas coleções e merge por **RRF**.
- Expor `contentType` e `strict` em `search_code` e `ask_code`.
- Retornar metadados por coleção (`name`, `contentType`, `hits`, `latencyMs`, `status`).

### Consequências
**Positivas**
- Melhor governança de dados (code vs docs).
- Merge mais estável entre fontes heterogêneas (RRF).
- Operação observável por coleção.

**Negativas**
- Aumento de complexidade em runtime e indexação.
- Necessidade de manter compatibilidade temporária de `meta.collection` (deprecated).

### Operação e rollback
- `strict=false`: permite retorno parcial quando uma coleção falha.
- `strict=true`: falha se qualquer coleção estiver indisponível.
- Manter coleção legada como fallback operacional durante janela de estabilização.
