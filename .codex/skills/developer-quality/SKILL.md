---
name: developer-quality
description: Planejar e executar qualidade técnica transversal (testes unit/integration/e2e, contratos, lint, typecheck, cobertura e regressão) com foco em prevenir quebras; usar quando o pedido envolver validação, confiabilidade e gates de entrega e não usar para implementar features de domínio específicas.
---

# Developer Quality

## 1) Objetivo e Escopo
Garantir que mudanças em MCP server, indexer, infra e docs técnicas passem por validação proporcional ao risco com feedback rápido e reproduzível.

### Trigger policy
- Disparar quando o pedido mencionar testes, cobertura, regressão, lint, typecheck, pre-commit, qualidade de PR, estabilidade de pipeline ou contrato entre módulos.
- Disparar quando houver suspeita de quebra silenciosa ou necessidade de ampliar matriz de validação.
- Não disparar para implementar lógica de negócio principal sem foco de validação (delegar para skill de domínio: `developer-mcp-server`, `developer-indexer`, `developer-vector-db`, `developer-infra`, `developer-docs`).

## 2) Entradas esperadas
- Escopo da mudança e risco esperado (baixo/médio/alto).
- Componentes afetados (MCP server, indexer, Qdrant schema, infra).
- Estado atual de testes/lint/typecheck e lacunas conhecidas.
- Critério de aceite mínimo (ex.: sem regressão, contrato preservado, cobertura mínima).

## 3) Workflow (Discovery -> Plan -> Implement -> Validate -> Deliver)
1. Discovery
   - Mapear tipos de teste existentes e pontos sem cobertura.
   - Identificar contratos críticos que devem ser protegidos.
   - Consultar `references/checklist.md` para matriz mínima por risco.
2. Plan
   - Definir plano de validação incremental (rápido -> profundo).
   - Priorizar testes próximos da mudança antes de suites globais custosas.
3. Implement
   - Criar/ajustar testes unitários, integração, e2e e de contrato quando necessário.
   - Ajustar lint/typecheck/pre-commit de forma objetiva e sem ruído.
4. Validate
   - Executar comandos planejados e registrar resultado de cada etapa.
   - Confirmar ausência de regressão funcional e de compatibilidade.
5. Deliver
   - Entregar plano executado, artefatos de validação e próximos passos para cobertura remanescente.

## 4) DoD
- Mudança crítica tem teste automatizado cobrindo caminho feliz e falhas relevantes.
- Contratos entre módulos sensíveis têm validação explícita.
- Lint e typecheck passam sem ignorar erros novos.
- Regressões conhecidas estão bloqueadas por teste ou documentadas com plano de mitigação.
- Comandos de validação são reproduzíveis no ambiente local/CI.

## 5) Guardrails
- Não mascarar falhas com skips indiscriminados ou mocks irreais.
- Não inflar cobertura com testes sem assert relevante.
- Não quebrar suites existentes para aprovar mudança pontual.
- Não misturar refatoração ampla com correção de teste sem necessidade.
- Não criar `scripts/` nesta skill sem necessidade determinística comprovada.

## 6) Convenções de saída
- Sempre devolver: (1) plano de validação, (2) mudanças de teste/lint/typecheck, (3) comandos e resultados, (4) risco residual.
- Sempre indicar o que foi validado localmente e o que depende de CI.

## 7) Exemplos de uso (prompts)
- "Crie uma matriz mínima de testes para a nova tool MCP e evite regressões de contrato."
- "Ajuste lint e typecheck do módulo alterado sem mexer em áreas não relacionadas."
- "Adicione testes de integração para indexação incremental e operação no Qdrant."
- "Defina gates de qualidade para PR com foco em feedback rápido e confiável."

## 8) Anti-exemplos (quando não usar)
- "Implementar endpoint/tool nova no NestJS" -> usar `developer-mcp-server`.
- "Refatorar algoritmo de chunking" -> usar `developer-indexer`.
- "Mudar configuração da collection Qdrant" -> usar `developer-vector-db`.
- "Escrever guia de onboarding técnico" -> usar `developer-docs`.
