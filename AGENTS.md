# AGENTS.md — Code Compass

## Regras obrigatorias

- Fazer apenas mudancas minimas no escopo solicitado.
- Nao quebrar contratos publicos (tools/API/schemas/payloads) sem plano explicito de migracao.
- Nunca commitar segredos, chaves ou tokens.
- Se houver ambiguidade com risco de breaking change, parar e perguntar.
- Só implemente código após receber aprovação do usuário com o comando `implemente`.

## Skills

- `developer-mcp-server`: mudancas no MCP server.
- `developer-indexer`: ingestao, chunking, embeddings e indexacao.
- `developer-vector-db`: collections, schema, payload e migracoes no Qdrant.
- `developer-infra`: docker-compose, env, make targets e observabilidade.
- `developer-quality`: qualidade transversal (gates, politica de testes, estabilidade).
- `developer-tester`: reproducao antes/depois e regressao de mudanca especifica.
- `developer-docs`: README, ADR, runbook e troubleshooting.

## Fluxo minimo

1. Discovery: declarar escopo, assuncoes e riscos.
2. Implement: aplicar alteracoes pequenas e coesas.
3. Validate: executar comandos do escopo e registrar resultado.
4. Deliver: listar arquivos alterados e como validar.

## Tooling canonico

### Instalar dependencias

```bash
pnpm install
pnpm -C apps/mcp-server install
make py-setup
```

### Infra e execucao local

```bash
make up
make health
make index
make dev
make down
```

### Testes

```bash
pnpm -C apps/mcp-server test
pnpm -C apps/mcp-server test:unit
pnpm -C apps/mcp-server test:integration
make py-test
```

### Lint e typecheck

```bash
make py-lint
make py-typecheck
pnpm -C apps/mcp-server build
```
