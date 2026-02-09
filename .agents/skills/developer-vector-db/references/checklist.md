# Checklist Vector DB

## Discovery
- Confirmar collection, objetivo e volume de dados.
- Levantar filtros críticos por payload.
- Validar dependências de schema no indexador e MCP server.

## Schema e Migração
- Registrar `vector_size` e `distance metric` alvo.
- Definir estratégia de migração e rollback.
- Definir versionamento de pontos e compatibilidade de payload.

## Validação
- Testar upsert/delete idempotentes.
- Testar queries com filtros representativos.
- Validar integridade pós-migração.

## Entrega
- Descrever plano aplicado e riscos.
- Informar impacto em contratos de busca.
- Listar comandos e verificações executadas.
