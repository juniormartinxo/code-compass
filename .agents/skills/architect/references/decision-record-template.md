# Decision Record Template (ADR curto)

Use este template para qualquer decisão estrutural que afete contratos, boundaries, dados, segurança ou operação.

## DR-XX — Título curto da decisão

### 1) Contexto
- Problema atual:
- Drivers da decisão (negócio/técnico):
- Escopo impactado (paths reais):
- Contratos públicos afetados:
- Restrições e premissas:

### 2) Opções consideradas (1–3)
Para cada opção:
- Descrição:
- Vantagens:
- Desvantagens:
- Riscos:
- Custo/complexidade:

### 3) Decisão recomendada
- Opção escolhida:
- Justificativa objetiva:
- Impacto esperado em performance/custo/confiabilidade:
- Compatibilidade (backward/breaking):

### 4) Contratos e boundaries
- Request/response alterados:
- Payload/schema alterados:
- Estratégia de versionamento:
- Regras de compatibilidade:

### 5) Plano de rollout (incremental)
- Fase 1:
- Fase 2:
- Fase 3:
- Critério de avanço entre fases:

### 6) Plano de rollback
- Gatilhos de rollback:
- Procedimento de reversão:
- Impacto esperado durante rollback:

### 7) Validação e evidências
- Comandos executados:
- Resultados observados:
- Smoke test index -> upsert -> query -> tool MCP:
- Riscos residuais:

### 8) Owners e acompanhamento
- Dono da decisão:
- Donos por domínio:
- Próxima revisão da decisão (data/marco):

