# Boundaries and Contracts — Code Compass

## 1) Boundaries por domínio

### MCP Server (Node/NestJS)
- Responsável por expor tools MCP e validar input/output.
- Responsável por políticas de segurança de acesso a arquivos e allowlist.
- Não responsável por chunking, embeddings ou escrita vetorial pesada.

### Indexer/Worker (Python)
- Responsável por ingestão, chunking, embeddings e upsert/delete no Qdrant.
- Responsável por idempotência e IDs determinísticos de chunk.
- Não responsável por contrato de transporte MCP com clientes finais.

### Qdrant (Vector DB)
- Responsável por persistência vetorial e filtros por payload.
- Responsável por estabilidade da coleção e schema de payload.
- Não responsável por regras de negócio do MCP nem parsing de arquivos.

### Infra local (Docker Compose + Makefile + env)
- Responsável por bootstrap reprodutível do ambiente.
- Responsável por comandos operacionais canônicos e healthcheck.
- Não responsável por semântica de contratos de tool/payload.

## 2) Contratos públicos críticos

### Tools MCP
- `search_code`: não remover campos de evidência sem migração explícita.
- `open_file`: preservar semântica de range e validação de path.
- `list_tree`: preservar comportamento de listagem dentro de allowlist.

### Payload vetorial (mínimo)
- Campos esperados: `repo`, `branch`, `commit`, `path`, `language`, `startLine`, `endLine`.
- Campos opcionais devem ser aditivos; remoção requer versão/migração.

### IDs determinísticos
- Padrão recomendado: `<repo>:<commit>:<path>:<chunkHash>`.
- Mudança no algoritmo de ID exige plano de coexistência/backfill.

## 3) Versionamento e compatibilidade

### Regras gerais
- Preferir evolução aditiva antes de breaking change.
- Quando breaking for inevitável, definir versão, data de corte e janela de compatibilidade.
- Documentar exemplos antes/depois e estratégia de migração.

### Estratégias recomendadas
- Dual-read/dual-write para transições de contrato ou schema.
- Feature flag para rollout progressivo de comportamento novo.
- Cutover controlado com critérios objetivos de sucesso/falha.

## 4) Matriz rápida de decisão
- Mudança só em parser/chunking interno sem contrato: não versionar API, validar regressão funcional.
- Mudança em payload consumido por filtros: versionar schema/payload e planejar migração.
- Mudança em saída de tool MCP: manter compatibilidade ou publicar versão nova da tool.
- Mudança de coleção Qdrant/distance/vector size: tratar como migração estrutural com rollback.

