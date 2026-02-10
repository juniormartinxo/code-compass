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

---
