---
name: developer-indexer
description: Planejar e implementar mudanças no indexador Python (chunking, embeddings, indexação full/incremental, IDs de chunk e payload rico); usar quando o pedido tocar `apps/indexer` ou pipeline RAG de ingestão e não usar para handlers MCP, schema Qdrant, infra ou documentação.
---

# Developer Indexer

## 1) Objetivo e Escopo
Evoluir o pipeline de ingestão e indexação para manter alta qualidade semântica, custo previsível e consistência entre full e incremental.

### Trigger policy
- Disparar quando o pedido mencionar `apps/indexer`, chunking, embeddings, ingestão de arquivos, full/incremental, tratamento de arquivos grandes ou exclusões de diretórios.
- Disparar quando houver alteração em ID de chunk, payload de metadados, estratégia de deduplicação ou rerank pré-indexação.
- Não disparar para contratos de tools MCP (`developer-mcp-server`), modelagem da collection Qdrant (`developer-vector-db`), bootstrap de ambiente (`developer-infra`) ou escrita de documentação (`developer-docs`).

## 2) Entradas esperadas
- Escopo de indexação (repositórios, pastas, branch/commit, modo full ou incremental).
- Parâmetros de chunking (`CHUNK_MAX_TOKENS`, `CHUNK_OVERLAP_TOKENS`, heurística/AST).
- Provider/modelo de embedding e limites de custo/latência.
- Regras de exclusão (ex.: `node_modules`, `dist`, `build`, `.git`, binários).

## 3) Workflow (Discovery -> Plan -> Implement -> Validate -> Deliver)
1. Discovery
   - Mapear fluxo atual em `code_compass/index`, `chunking`, `embeddings` e `storage`.
   - Confirmar como o ID de chunk é composto e onde ocorre deduplicação.
   - Consultar `references/checklist.md` para critérios de consistência e performance.
2. Plan
   - Definir plano com impacto em qualidade de recuperação, custo de embedding e compatibilidade de payload.
   - Diferenciar claramente comportamento full vs incremental.
3. Implement
   - Aplicar mudança mínima por etapa (scan -> chunk -> embed -> upsert).
   - Garantir IDs determinísticos para evitar duplicidade em reindexações.
   - Preservar payload rico (`repo`, `branch`, `commit`, `path`, `language`, `startLine`, `endLine`).
4. Validate
   - Executar testes e smoke tests da indexação (principalmente incremental idempotente).
   - Validar exclusões obrigatórias e tratamento de arquivos grandes sem explodir memória.
5. Deliver
   - Entregar plano executado, mudanças por arquivo, comandos usados e limitações conhecidas.

## 4) DoD
- Full e incremental produzem estado consistente para o mesmo commit alvo.
- IDs de chunk são determinísticos e estáveis sob reexecução.
- Diretórios bloqueados não entram no índice.
- Payload contém metadados suficientes para rastreabilidade e filtros.
- Fluxo trata arquivos grandes e tipos não suportados com fallback explícito.

## 5) Guardrails
- Não indexar segredos, artefatos binários ou diretórios de build/cache.
- Não alterar formato de ID de chunk sem plano de migração e limpeza.
- Não acoplar lógica de negócio a provider específico sem fallback/configuração.
- Não aumentar custo de embedding sem justificar ganho de qualidade.
- Não criar `scripts/` nesta skill sem necessidade determinística comprovada.

## 6) Convenções de saída
- Sempre devolver: (1) plano, (2) alterações, (3) comandos de validação, (4) impacto em qualidade/custo.
- Sempre declarar se houve mudança em ID, payload ou política de exclusão.

## 7) Exemplos de uso (prompts)
- "No indexador Python, implemente chunking AST para TypeScript com fallback heurístico."
- "Ajuste a indexação incremental para atualizar apenas arquivos alterados no commit atual."
- "Crie IDs de chunk estáveis e evite duplicação ao reindexar a mesma branch."
- "Melhore o tratamento de arquivos grandes sem estourar memória durante a ingestão."

## 8) Anti-exemplos (quando não usar)
- "Adicionar validação de input em uma tool MCP" -> usar `developer-mcp-server`.
- "Mudar vector size da collection Qdrant" -> usar `developer-vector-db`.
- "Configurar docker-compose para subir tudo local" -> usar `developer-infra`.
- "Escrever seção de troubleshooting no README" -> usar `developer-docs`.
