# Architecture Charter — Code Compass

## Objetivo
Estabelecer princípios e limites de arquitetura para evolução do Code Compass com decisões rastreáveis, seguras e operáveis.

## Objetivos arquiteturais
- Entregar respostas evidence-first em tools MCP com `path`, intervalo de linhas e contexto verificável.
- Preservar contratos públicos entre MCP Server, Indexer e Qdrant.
- Garantir pipeline de indexação idempotente, incremental e previsível em custo.
- Permitir evolução incremental sem big-bang e com rollback explícito.
- Manter operação reproduzível local com Docker Compose + Makefile.

## Não-objetivos
- Não otimizar prematuramente para escala global sem necessidade do roadmap.
- Não acoplar MCP Server a responsabilidades de chunking/embeddings.
- Não aceitar mudanças breaking sem plano de migração e comunicação.
- Não introduzir dependência operacional sem runbook mínimo e validação local.

## Pilares

### Performance
- Priorizar latência previsível em consultas (`search_code`) e throughput estável no indexador.
- Medir impacto de decisões em p95, custo de indexação e taxa de no-hit.
- Favorecer estratégias incrementais e filtros de payload para reduzir custo total.

### Segurança
- Aplicar `default deny` no MCP Server e permitir apenas operações em allowlist.
- Proteger leitura de arquivos com normalização de path e bloqueio de traversal.
- Evitar exposição de segredos em logs, payloads e exemplos.
- Tratar ingestão de documentos com validação defensiva e limites claros.

### DX (Developer Experience)
- Manter boundaries explícitos entre Node/NestJS, Python e Qdrant.
- Facilitar reprodução local por comandos canônicos (`make up`, `make index*`, `make dev`).
- Documentar decisões estruturais com Decision Record curto e checklist de rollout.

## Owners por domínio
- MCP Server (Node/NestJS): ownership de tools MCP e contratos de interface.
- Indexer/Worker (Python): ownership de ingestão, chunking, embeddings e idempotência.
- Vector DB (Qdrant): ownership de schema de coleção, payload e migração vetorial.
- Infra (Docker Compose/Makefile/.env): ownership de bootstrap e operação local.
- Quality/Docs: ownership de validação transversal e registro de decisões.

## Critérios de sucesso
- Mudanças estruturais possuem decisão registrada com opções e trade-offs.
- Rollout e rollback estão definidos antes de execução em produção.
- Contratos críticos têm exemplos e estratégia de compatibilidade explícita.
- Fluxo local ponta-a-ponta é reproduzível sem passos ocultos.

