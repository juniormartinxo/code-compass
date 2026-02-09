# Test Strategy Checklist (Code Compass)

## Objetivo
Definir uma estratégia mínima e objetiva de QA para mudanças no ecossistema MCP Server + Indexer Python + Qdrant, com foco em reduzir regressão e evitar overtesting.

## 1) Discovery
- Classificar risco da mudança: baixo, médio ou alto.
- Identificar superfícies afetadas:
  - MCP Server (tools, handlers, DTOs, contratos)
  - Indexer (chunking, embeddings, incremental/full)
  - Qdrant (collection, payload, filtros)
  - Fluxo operacional (docker compose, readiness, bootstrap)
- Identificar contrato público impactado e consumidores.
- Confirmar comandos reais disponíveis no snapshot:
  - `rg --files -g 'Makefile'`
  - `rg --files -g '**/package.json'`
  - `rg --files -g '**/pyproject.toml' -g '**/requirements.txt'`

## 2) Plano por tipo de teste
- Unit:
  - regra de negócio isolada;
  - transformação de payload/dados;
  - validação de erro esperado.
- Integration:
  - integração entre camadas (ex.: handler -> adapter -> storage);
  - filtros de consulta e mapeamento de metadados.
- E2E/Smoke:
  - caminho crítico completo com componentes mínimos ativos.

## 3) Cobertura mínima obrigatória
- Happy path principal.
- Edge case principal (dado limite ou estado parcialmente inconsistente).
- Erro esperado (input inválido, recurso ausente, falha controlada).

## 4) Regressão e bugfix
- Registrar repro do bug antes da correção.
- Converter repro em teste automatizado quando viável.
- Garantir que a correção não degrade comportamento adjacente.

## 5) Regras para RAG/Qdrant
- Validar consulta com filtro de payload (`repo`, `path`, `language`, `commit` quando aplicável).
- Garantir idempotência na indexação incremental (não duplicar chunks/pontos).
- Conferir coerência de evidência (`path`, `startLine`, `endLine`, `score`).

## 6) Anti-flakiness
- Congelar fontes de não-determinismo (tempo/ordem/rede) com mock controlado.
- Evitar dependência de estado global e ordem entre testes.
- Usar dados de teste mínimos e reprodutíveis.

## 7) Evidências da validação
- Para cada comando executado, registrar:
  - comando;
  - resultado (pass/fail);
  - interpretação rápida (o que foi coberto).
- Quando algo não puder ser validado, registrar motivo objetivo (ex.: artefato ausente no snapshot).

## 8) Saída esperada do QA
- Resumo do escopo validado.
- Lista de testes adicionados/alterados.
- Comandos executados e status.
- Risco residual e próximo passo.
