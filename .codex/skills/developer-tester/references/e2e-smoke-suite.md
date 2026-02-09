# E2E Smoke Suite (mínimo)

## Objetivo
Executar uma verificação rápida de ponta a ponta do fluxo essencial do Code Compass sem transformar smoke em suite pesada.

## Pré-condições
- `infra/docker-compose.yml` disponível.
- Qdrant disponível em `http://localhost:6333`.
- Artefatos da aplicação existentes no snapshot (quando houver):
  - `apps/indexer`
  - `apps/mcp-server`

## Sequência sugerida
1. Infra mínima
   - `docker compose -f infra/docker-compose.yml up -d`
   - `curl -s http://localhost:6333/readyz`
2. Indexação (se módulo existir)
   - executar fluxo mínimo do indexer (full ou incremental de amostra)
   - validar ausência de duplicidade quando o fluxo rodar duas vezes.
3. Consulta MCP (se módulo existir)
   - executar uma busca básica com evidência.
   - validar retorno com `path` e linhas quando disponível.

## Casos de smoke obrigatórios
- Smoke 1: serviço de vetor acessível
  - Esperado: endpoint de prontidão responde com sucesso.
- Smoke 2: indexação mínima executável
  - Esperado: operação conclui sem erro fatal e gera pontos pesquisáveis.
- Smoke 3: consulta essencial
  - Esperado: resposta estruturada e auditável com metadados mínimos.

## Verificações específicas de qualidade
- Não falhar por dependência de internet externa.
- Não depender de ordem de execução entre testes.
- Não usar dados sensíveis em logs.

## Resultado padrão para reportar
- Status por smoke (`PASS`/`FAIL`).
- Tempo aproximado por etapa.
- Evidência de comando e saída resumida.
- Risco residual (ex.: sem e2e real por ausência de módulo no snapshot).
