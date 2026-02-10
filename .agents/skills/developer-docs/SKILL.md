---
name: developer-docs
description: Planejar e manter documentação técnica do projeto (README, quickstart, ADRs, docs internas, exemplos de tool calls e troubleshooting) alinhada ao código; usar quando o pedido exigir clareza documental e não usar para implementar lógica de runtime ou infraestrutura.
---

# Developer Docs

## 1) Objetivo e Escopo
Manter documentação técnica acionável, atualizada e consistente com o comportamento real do Code Compass.

### Trigger policy
- Disparar quando o pedido mencionar `README`, `apps/docs/pages`, ADRs, quickstart, runbook, exemplos de tool calls, troubleshooting ou atualização de documentação após mudança técnica.
- Disparar quando houver divergência entre comportamento do sistema e instruções documentadas.
- Não disparar para implementação de feature em runtime (`developer-mcp-server`, `developer-indexer`, `developer-vector-db`, `developer-infra`) sem foco documental explícito.

## 2) Entradas esperadas
- Público-alvo (dev, operação, mantenedor, reviewer).
- Escopo do documento e contexto técnico da mudança.
- Fonte de verdade (arquivos de código, comandos reais, decisões arquiteturais).
- Restrições de formato/idioma e nível de detalhe desejado.

## 3) Workflow (Discovery -> Plan -> Implement -> Validate -> Deliver)
1. Discovery
   - Ler arquivos de código e configs relevantes antes de editar docs.
   - Levantar lacunas, inconsistências e comandos obsoletos.
   - Consultar `references/checklist.md` para padrão de qualidade documental.
2. Plan
   - Definir estrutura mínima por seção (objetivo, pré-requisitos, execução, validação, troubleshooting).
   - Priorizar clareza operacional e exemplos executáveis.
3. Implement
   - Atualizar documentos com linguagem direta e passos verificáveis.
   - Incluir exemplos de tool calls MCP e paths reais quando aplicável.
   - Registrar decisões em ADR quando houver trade-off arquitetural.
4. Validate
   - Verificar se comandos documentados existem e se ordem de execução é coerente.
   - Confirmar consistência entre README, docs específicas e estrutura do repositório.
5. Deliver
   - Entregar plano aplicado, documentos alterados e checklist de verificação final.

## 4) DoD
- Documentação responde "como rodar", "como validar" e "como debugar" sem passos implícitos críticos.
- Comandos, paths e nomes de módulos batem com a base atual.
- ADRs capturam contexto, decisão, trade-offs e consequências.
- Exemplos de tool calls refletem contrato real e limites conhecidos.
- Mudanças documentais preservam consistência de termos e convenções.

## 5) Guardrails
- Não inventar comportamento não confirmado no código/configuração.
- Não manter instruções quebradas por compatibilidade histórica; corrigir ou marcar depreciação.
- Não ocultar pré-requisitos importantes (versões, env vars, serviços).
- Não copiar conteúdo redundante quando referência cruzada resolve melhor.
- Não criar `scripts/` nesta skill sem necessidade determinística comprovada.
- **Localização dos arquivos**: Toda documentação deve residir em `apps/docs/pages/` (ex: `apps/docs/pages/indexer/`, `apps/docs/pages/mcp-server/`, `apps/docs/pages/ADRs/`). Não espalhar docs soltas fora desse diretório; assets de apoio devem ficar em `apps/docs/assets/`.

## 6) Convenções de saída
- Sempre devolver: (1) plano editorial, (2) arquivos alterados por objetivo, (3) validações realizadas, (4) pendências abertas.
- Sempre incluir orientação de uso: onde ler primeiro e como aplicar os exemplos.

## 7) Exemplos de uso (prompts)
- "Atualize o README com quickstart real para subir Qdrant, indexar e iniciar o MCP server."
- "Escreva um ADR justificando a escolha Node/NestJS + Python + Qdrant para o Code Compass."
- "Crie guia de troubleshooting para falhas comuns de indexação e conexão com Qdrant."
- "Documente exemplos de chamadas das tools `search_code`, `open_file` e `list_tree`."

## 8) Anti-exemplos (quando não usar)
- "Implementar validação de path traversal no servidor" -> usar `developer-mcp-server`.
- "Ajustar algoritmo de chunking e embeddings" -> usar `developer-indexer`.
- "Modificar schema da collection e rotina de upsert" -> usar `developer-vector-db`.
- "Reorganizar docker-compose e make targets" -> usar `developer-infra`.
