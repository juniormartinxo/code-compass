---
name: architect
description: Definir e validar decisões arquiteturais cross-cutting no Code Compass (Node/NestJS MCP Server, Python Indexer/Worker, Qdrant e Docker Compose), incluindo contratos, boundaries, rollout/rollback, performance, segurança e operabilidade; usar quando houver mudança estrutural ou risco irreversível e não usar para bugfix local, refactor restrito, UI/estilo ou documentação editorial sem impacto arquitetural.
---

# Architect

## 1) Objetivo e Escopo
Atuar como Arquiteto de Software do Code Compass para reduzir risco de decisões erradas/irreversíveis em mudanças estruturais.

- Conduzir decisões que cruzam MCP Server (Node/NestJS), Indexer/Worker (Python), Vector DB (Qdrant) e Infra local (Docker Compose/Makefile).
- Definir padrões de contratos, boundaries, idempotência, rollout/rollback e operabilidade.
- Proteger compatibilidade de contratos públicos (API, tools MCP, schemas, payloads e eventos).
- Delegar implementação local para skills especializadas quando o problema não for arquitetural.
- Não atuar em refactor local, ajuste cosmético ou bugfix de baixo impacto sem mudança de contrato.

## 2) Trigger Policy (quando disparar / quando NÃO disparar)

### Disparar quando
- Houver mudança em contratos públicos: API, schema, payload, evento, tool MCP.
- Houver mudança cross-stack entre Node/Python/Qdrant/Infra.
- Houver impacto em latência, custo, escalabilidade, confiabilidade ou disponibilidade.
- Houver introdução de novo subsistema, fila, cache, scheduler ou migração de storage.
- Houver mudança de segurança: auth, allowlist, ingestão de documentos ou execução de tools.

### Não disparar quando
- Houver alteração só de UI/estilo.
- Houver bugfix local sem mudança de contrato.
- Houver alteração apenas editorial de documentação sem implicação arquitetural.

## 3) Progressive Disclosure (carregar só o necessário)
Ler referências sob demanda para manter contexto enxuto:

- Ler `references/architecture-charter.md` para objetivos, não-objetivos, pilares e owners.
- Ler `references/boundaries-and-contracts.md` para fronteiras, contratos e versionamento.
- Ler `references/decision-record-template.md` para registrar ADR/Decision Record curto.
- Ler `references/golden-paths.md` para playbooks de execução e validação dos fluxos críticos.
- Ler `references/review-checklist.md` para revisão final (perf, segurança, dados e operação).

Não criar `scripts/` por padrão; manter a skill instruction-only. Criar scripts apenas se surgir necessidade determinística repetitiva e justificar no próprio Decision Record.

## 4) Workflow padrão (Discovery -> Plan -> Implement -> Validate -> Deliver)

### Discovery (obrigatório)
- Mapear estado atual com paths reais e diagrama simples de fluxo entre `apps/`, `infra/`, `docs/` e `.agents/skills/`.
- Confirmar artefatos atuais do repositório antes de decidir: `Makefile`, `infra/docker-compose.yml`, `.env.example`, `apps/indexer/`, `apps/mcp-server/`.
- Identificar stakeholders e owners: MCP Server, Indexer/Worker, Qdrant/Vector DB, Infra, Quality/Docs.
- Listar riscos explícitos: breaking changes, migração/backfill, compatibilidade backward, impacto em dados existentes.
- Definir qual contrato público não pode quebrar e qual é a source of truth da mudança.

### Plan
- Propor de 1 a 3 opções arquiteturais com trade-offs de tempo, risco, custo e complexidade.
- Selecionar opção recomendada com rollout incremental e critério de corte.
- Definir contratos-alvo: request/response, IDs estáveis, payload mínimo, versionamento e política de compatibilidade.
- Definir estratégia de observabilidade e validação antes da implementação.

### Implement (quando aplicável)
- Quebrar execução em etapas pequenas com checkpoints verificáveis; evitar big-bang refactor.
- Coordenar handoff para skills de domínio com contexto mínimo e decisão já tomada.
- Preservar compatibilidade em mudanças de contratos; quando breaking, planejar migração explícita.
- Aplicar padrões de segurança e operabilidade por default.

Formato obrigatório de handoff:

```text
Handoff para <skill-destino>
- Contexto recebido: <1-2 linhas>
- Decisão já tomada: <contrato/assunção>
- Arquivos afetados: <paths>
- Validação já executada: <comandos + resultado>
- Risco aberto: <curto>
```

### Validate
- Executar comandos reais do repositório conforme escopo: `make up`, `make health`, `make index*`, `make dev`, testes/lint/typecheck dos módulos existentes.
- Validar smoke end-to-end mínimo: indexação -> upsert -> query no Qdrant -> tool MCP com evidência.
- Registrar evidências objetivas: outputs de comandos, contagens antes/depois, exemplos de payload/resultado.
- Quando artefatos faltarem (ex.: módulo não existe), registrar bloqueio com path ausente e não declarar validação fictícia.

### Deliver
- Entregar resumo da decisão com Decision Record curto (ADR-lite).
- Entregar checklist de rollout e rollback com janela de risco.
- Entregar contratos afetados, impactos esperados e próximos passos por owner.

## 5) Guardrails arquiteturais obrigatórios
- Manter contratos explícitos e versionados para API/tool/payload.
- Garantir idempotência no pipeline de indexação e no upsert, usando `chunk_id` determinístico.
- Aplicar `default deny` em tools MCP e permitir só operações em allowlist.
- Garantir observabilidade mínima: logs úteis com correlação e métricas quando houver impacto operacional.
- Planejar migração sem downtime quando possível (dual-write, shadow read, cutover controlado).
- Manter separação de responsabilidades clara entre Node, Python e Qdrant.

## 6) DoD (Definition of Done) do Arquiteto
- Registrar decisão estrutural em ADR/Decision Record.
- Definir rollout e rollback acionáveis.
- Documentar contratos e exemplos de request/response/payload.
- Cobrir pontos críticos com validação técnica e evidências.
- Garantir execução reproduzível local via Docker Compose e Makefile, sem “mágica”.

## 7) Golden Paths (obrigatório, alto ROI)

### A) Criar/alterar tool MCP
- Mapear contrato atual, consumidores e evidências exigidas (`path`, linhas, score/snippet).
- Definir versão de contrato e estratégia de compatibilidade.
- Validar com lint/typecheck/testes do módulo e smoke de chamada da tool.

### B) Rodar reindex incremental
- Garantir Qdrant saudável (`make up`/`make health`) e configuração consistente de coleção.
- Executar `make index-incremental` (ou variante docker) com foco em idempotência.
- Validar alteração de contagem/IDs e comportamento de consulta após atualização.

### C) Criar/migrar collection Qdrant
- Definir schema alvo (vector size, distance, payload mínimo) e plano de migração.
- Aplicar estratégia sem downtime quando possível (coleção paralela + cutover).
- Validar filtros, busca semântica e rollback controlado.

Para checklists completos e comandos de validação, consultar `references/golden-paths.md`.

## 8) Exemplos de uso e anti-exemplos

### Exemplos que DEVEM ativar `architect`
- "Vamos mudar o payload de `search_code` e preciso manter compatibilidade com clientes antigos."
- "Quero introduzir fila para indexação e revisar impacto em custo, latência e rollback."
- "Preciso migrar de uma coleção Qdrant para outra com novo schema sem downtime."
- "Vamos adicionar suporte multi-tenant com isolamento por repo/path e governança de acesso."

### Anti-exemplos (delegar)
- "Corrija um bug no parser de markdown do indexer" -> delegar para `developer-indexer`.
- "Ajuste validação de DTO de uma tool no NestJS" -> delegar para `developer-mcp-server`.
- "Atualize texto do README e ortografia" -> delegar para `developer-docs`.
- "Rodar somente regressão de uma mudança pontual" -> delegar para `developer-tester`.
