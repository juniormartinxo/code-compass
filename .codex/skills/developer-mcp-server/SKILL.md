---
name: developer-mcp-server
description: Planejar e implementar mudanças no servidor MCP em Node/NestJS (tools, handlers, validação, allowlist, contratos de retorno com evidência e performance P95); usar quando o pedido tocar `apps/mcp-server` ou integração MCP e não usar para indexação Python, schema Qdrant, infra ou documentação.
---

# Developer MCP Server

## 1) Objetivo e Escopo
Implementar e evoluir o servidor MCP com foco em contratos estáveis de tools, segurança de acesso a arquivos e respostas com evidência verificável.

### Trigger policy
- Disparar quando o pedido mencionar `apps/mcp-server`, tools MCP, handlers NestJS, transport MCP, validação de entrada/saída ou performance de busca/retorno.
- Disparar quando houver mudança em contrato de tool (`search_code`, `open_file`, `list_tree`) ou em governança (`allowlist`, `audit trail`, `read-only`).
- Não disparar para chunking/embeddings/indexação (delegar para `developer-indexer`), schema Qdrant (delegar para `developer-vector-db`), infra local (delegar para `developer-infra`) ou documentação editorial (delegar para `developer-docs`).

## 2) Entradas esperadas
- Caminho ou módulo alvo (ex.: `apps/mcp-server/src/mcp`, `apps/mcp-server/src/services`).
- Requisito funcional e contrato esperado de entrada/saída.
- Restrições de compatibilidade (ex.: manter nome de tool e campos existentes).
- Limites operacionais (latência P95, volume de resultados, filtros obrigatórios).

## 3) Workflow (Discovery -> Plan -> Implement -> Validate -> Deliver)
1. Discovery
   - Mapear handlers, schemas, adapters e pontos de auditoria.
   - Identificar contratos atuais e consumidores impactados.
   - Consultar `references/checklist.md` antes de alterar tool pública.
2. Plan
   - Definir plano curto, risco de quebra e estratégia de rollback.
   - Explicitar mudanças de contrato e impacto backward-compatible.
3. Implement
   - Aplicar mudança mínima no NestJS preservando interfaces públicas.
   - Manter validação forte de input/output e política de allowlist.
   - Garantir payload com `path`, `startLine`, `endLine` e `score` quando aplicável.
4. Validate
   - Executar validações específicas do módulo (`lint`, `test`, `typecheck`, testes de contrato).
   - Medir impacto de latência quando alterar fluxo de busca; evitar regressão de P95 sem justificativa.
5. Deliver
   - Entregar plano executado, arquivos alterados, comandos de verificação e riscos residuais.

## 4) DoD
- Tool alterada mantém contrato backward-compatible ou inclui plano explícito de migração.
- Validação de input/output cobre casos inválidos, limites e erros esperados.
- Segurança de filesystem mantém allowlist e proteção de path traversal.
- Resposta de busca inclui evidências consumíveis (`path` e linhas) sem ambiguidade.
- Logs/auditoria não expõem segredos e permitem rastreabilidade por requisição.

## 5) Guardrails
- Preservar `READ_ONLY=true` por padrão; não introduzir escrita sem requisito explícito.
- Não enfraquecer validação de caminho, filtros de acesso ou política de segurança.
- Não quebrar consumidores MCP alterando campos obrigatórios sem estratégia de migração.
- Evitar I/O desnecessário em hot paths; priorizar neutralidade ou ganho de P95.
- Não criar `scripts/` nesta skill sem necessidade determinística comprovada.

## 6) Convenções de saída
- Sempre devolver: (1) plano curto, (2) mudanças por arquivo, (3) comandos de validação, (4) riscos/pendências.
- Sempre explicitar decisões de compatibilidade e segurança.

## 7) Exemplos de uso (prompts)
- "No `apps/mcp-server`, adicione paginação em `search_code` sem quebrar o contrato atual."
- "Refatore o handler de `open_file` para endurecer allowlist e bloquear path traversal."
- "Padronize o retorno de evidências das tools MCP para incluir linhas e score de forma consistente."
- "Investigue e reduza latência P95 da tool `search_code` mantendo a mesma assinatura."

## 8) Anti-exemplos (quando não usar)
- "Ajuste chunking e overlap de embeddings" -> usar `developer-indexer`.
- "Mude vector size e distance metric da coleção" -> usar `developer-vector-db`.
- "Suba ambiente local com docker-compose e observabilidade" -> usar `developer-infra`.
- "Atualize README e ADR da feature" -> usar `developer-docs`.
