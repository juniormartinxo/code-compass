## ADR-001 — Separar MCP Server (Node/NestJS) do Indexer/ML Worker (Python)

**Status:** Aceito  
**Data:** 2026-02-08

### Contexto
O Code Compass precisa:
- expor ferramentas MCP com baixa latência e alta confiabilidade (gateway),
- executar ingestão/indexação pesada e mutável (chunking, embeddings, incremental),
- evoluir rapidamente sem afetar disponibilidade de consulta.

Misturar gateway + batch/ML no mesmo processo cria acoplamento de carga, observabilidade confusa e risco operacional.

### Decisão
Adotar arquitetura de **dois serviços**:
- **MCP Server** em **Node/NestJS** (gateway MCP, validação, governança, audit trail, consulta no vector DB e filesystem).
- **Indexer/ML Worker** em **Python** (ingestão, chunking, embeddings, rerank futuro, incremental e avaliação).

### Consequências
**Positivas**
- Isolamento de carga: indexação não degrada consultas.
- Evolução independente: chunking/ML itera rápido sem “quebrar” o gateway.
- Observabilidade e SLOs claros por componente.

**Negativas**
- Mais um serviço para operar (deploy/configuração).
- Necessidade de contratos claros (schema de payload e convenções de IDs).