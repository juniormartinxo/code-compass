---
name: developer-vector-db
description: Planejar e implementar mudanças na camada vetorial Qdrant (collections, distance metric, vector size, payload filters, upsert/delete e migração de schema); usar quando o pedido tocar modelagem ou operação de vetor e não usar para lógica do indexador, handlers MCP, infra geral ou documentação.
---

# Developer Vector DB

## 1) Objetivo e Escopo
Projetar e manter o armazenamento vetorial em Qdrant com schema claro, filtros eficientes e operações seguras de evolução.

### Trigger policy
- Disparar quando o pedido mencionar Qdrant, collection, métrica de distância, tamanho de vetor, filtros por payload, upsert/delete, snapshots, migração de schema ou versionamento de pontos.
- Disparar quando houver ajuste em contrato de payload que impacta busca semântica e filtros.
- Não disparar para lógica de chunking/embedding (`developer-indexer`), handlers MCP (`developer-mcp-server`), bootstrap docker/env (`developer-infra`) ou documentação (`developer-docs`).

## 2) Entradas esperadas
- Nome da collection e objetivo da mudança.
- `vector_size`, `distance metric`, índices de payload e filtros necessários.
- Estratégia de versionamento/migração de schema e compatibilidade.
- Política de retenção, delete lógico/físico e rollback.

## 3) Workflow (Discovery -> Plan -> Implement -> Validate -> Deliver)
1. Discovery
   - Mapear configuração atual de collection e contratos de payload consumidos.
   - Levantar consultas e filtros críticos para performance e precisão.
   - Consultar `references/checklist.md` para garantir segurança de migração.
2. Plan
   - Definir plano de migração (in-place, shadow collection ou backfill) com rollback.
   - Explicitar impacto em indexador e servidor MCP.
3. Implement
   - Aplicar ajustes de schema e operações de upsert/delete de forma idempotente.
   - Preservar compatibilidade dos campos de payload usados por filtros existentes.
4. Validate
   - Validar queries com filtros representativos e checar precisão mínima esperada.
   - Validar rotina de delete/versionamento para evitar pontos órfãos ou inconsistentes.
5. Deliver
   - Entregar plano executado, mudanças por arquivo/config, comandos de validação e riscos.

## 4) DoD
- Collection final documenta `vector_size`, `distance metric` e índices de payload.
- Migração tem plano de rollback e não perde rastreabilidade dos pontos.
- Upsert e delete são idempotentes para reprocessamentos.
- Filtros por payload relevantes funcionam com cobertura mínima de casos.
- Versionamento evita mistura de schemas incompatíveis na mesma consulta.

## 5) Guardrails
- Não remover collection produtiva sem backup/snapshot e aprovação explícita.
- Não alterar `vector_size`/métrica sem migrar dados existentes de forma segura.
- Não quebrar filtros existentes ao renomear campos de payload sem compat layer.
- Não executar limpeza destrutiva sem critério observável e reversível.
- Não criar `scripts/` nesta skill sem necessidade determinística comprovada.

## 6) Convenções de saída
- Sempre devolver: (1) plano de migração, (2) mudanças aplicadas, (3) comandos de validação, (4) risco residual.
- Sempre explicitar impacto em compatibilidade de payload e queries.

## 7) Exemplos de uso (prompts)
- "Ajuste a collection `code_chunks` para suportar novos filtros por `branch` e `language`."
- "Proponha migração segura ao trocar `distance` para `Cosine` mantendo rollback."
- "Implemente versionamento de pontos para evitar conflito entre schemas antigos e novos."
- "Reveja política de deletes para remover chunks obsoletos sem perder histórico útil."

## 8) Anti-exemplos (quando não usar)
- "Melhorar chunking AST de arquivos Python" -> usar `developer-indexer`.
- "Alterar tool MCP para retornar mais campos" -> usar `developer-mcp-server`.
- "Configurar make targets e compose local" -> usar `developer-infra`.
- "Atualizar ADR explicando a escolha do Qdrant" -> usar `developer-docs`.
