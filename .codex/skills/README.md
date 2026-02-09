# Skills de desenvolvimento do Code Compass

Este índice resume quando usar cada skill do repositório.

- `$developer-mcp-server`: use para mudanças no servidor MCP em Node/NestJS (tools, contratos, validação, segurança de paths e performance de resposta).
- `$developer-indexer`: use para pipeline Python de ingestão/indexação (chunking, embeddings, full/incremental, IDs e payload).
- `$developer-vector-db`: use para modelagem e operação do Qdrant (collections, métricas vetoriais, filtros, migrações e deletes).
- `$developer-infra`: use para infraestrutura local e operação (docker-compose, env, make targets, bootstrap e observabilidade).
- `$developer-quality`: use para estratégia e implementação de qualidade (testes, lint, typecheck, regressão e gates).
- `$developer-tester`: use para execução de testes de mudança específica (repro antes/depois, regressão unit/integration/e2e, smoke suite e evidências de validação).
- `$developer-docs`: use para documentação técnica (README, ADR, quickstart, runbook, troubleshooting e exemplos).

Regra de ativação implícita: além da invocação explícita (`$nome-da-skill`), cada skill deve disparar automaticamente quando o pedido cair no escopo descrito no campo `description` do frontmatter.
