# Roadmap Pós-Chunking

## Contexto

O roadmap de evolução do chunking foi concluído até a Fase 10. O próximo ciclo deixa de ser de expansão funcional e passa a ser de produção:

- hardening do chunker/indexer
- performance do pipeline de ingestão
- observabilidade operacional

Objetivo: tornar o fluxo `scan -> chunk -> embed -> upsert -> search` previsível, auditável e seguro para operação contínua.

## Objetivos

1. reduzir risco de regressão e comportamento destrutivo em indexações incrementais
2. melhorar throughput e custo de indexação
3. permitir diagnóstico rápido de falhas, lentidão e drift de schema/chunking
4. formalizar rollout, validação e rollback em produção

## Frente 1: Hardening

### Prioridades

- consolidar smoke `index -> search` como gate recorrente, não só validação manual
- endurecer proteção contra cleanup indevido em execuções parciais ou diagnósticas
- reforçar isolamento por arquivo durante chunking, embedding e upsert
- registrar falhas por arquivo com saída estruturada para reprocessamento
- validar rebuild completo de schema novo com procedimento operacional explícito
- revisar defaults e feature flags de embedding input mode por tipo de conteúdo

### Entregas esperadas

- suite de smoke operacional reproduzível
- política clara de full rebuild vs incremental
- relatórios de erro por arquivo/repo_root
- checklist de rollout e rollback

## Frente 2: Performance

- **Prioridades**
  - medir custo de chunking por linguagem e estratégia (`line_window`, `python_symbol`, `ts_symbol`, `doc_section`, `config_section`, `sql_statement`)
  - perfilar arquivos grandes e casos de alta cardinalidade de chunks
  - revisar tamanho de payload no Qdrant, especialmente `text`, `summaryText` e `contextText`
  - calibrar batching, paralelismo e uso do embedder por coleção
  - comparar `content` vs `summary_content` em qualidade e custo
  - reduzir churn de reindex incremental e deleção stale

- **Entregas esperadas**
  - baseline de throughput e latência do indexer
  - benchmark por tipo de arquivo
  - plano de otimização dos principais gargalos
  - decisão documentada sobre trade-offs de payload e modo de embedding

## Frente 3: Observabilidade

- **Prioridades**
  - padronizar logs estruturados por etapa: scan, chunk, embed, upsert, delete stale
  - expor métricas por repo, coleção, estratégia e tipo de chunk
  - medir:
    - arquivos escaneados
    - arquivos ignorados
    - chunks gerados por estratégia
    - falhas de parse
    - fallback para `line_window`
    - tempo de embedding
    - tempo de upsert
  - pontos deletados por cleanup incremental
  - registrar distribuição de `chunkSchemaVersion`
  - definir alertas operacionais mínimos para falha de indexação, backlog e degradação de throughput

- **Entregas esperadas**
  - logs úteis para troubleshooting sem reprodução local obrigatória
  - dashboard mínimo de ingestão/indexação
  - alertas para falhas persistentes e anomalias de cardinalidade

## Ordem Recomendada

- **Etapa 1: Baseline Operacional**
  - transformar smoke atual em fluxo repetível
  - capturar baseline de latência, chunks por arquivo e erros por tipo

- **Etapa 2: Hardening de Segurança Operacional**
  - fechar gaps de cleanup incremental
  - endurecer erros parciais e idempotência de reindex
  - revisar contrato de rebuild obrigatório por schema

- **Etapa 3: Performance**
  - atacar gargalos medidos no baseline
  - revisar payload, batching e input mode

- **Etapa 4: Observabilidade de Produção**
  - publicar métricas, dashboards e alertas
  - integrar troubleshooting com docs operacionais

## Critérios de Saída

O ciclo será considerado concluído quando:

- houver smoke automatizado de `index -> search`
- regressões destrutivas de cleanup estiverem cobertas por teste e observáveis em runtime
- existirem métricas mínimas de tempo, volume e erro por etapa
- houver baseline comparável antes/depois para tuning
- rollout e rollback estiverem documentados e reproduzíveis

## Artefatos que devem acompanhar este roadmap

- [docs/chuncks/plan.md](/home/junior/apps/jm/code-compass/docs/chuncks/plan.md)
- [docs/OPERATIONS.md](/home/junior/apps/jm/code-compass/docs/OPERATIONS.md)
- [apps/indexer/README.md](/home/junior/apps/jm/code-compass/apps/indexer/README.md)
