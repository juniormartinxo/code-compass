# Checklist Indexer

## Discovery
- Confirmar escopo de pastas, branch e modo (full/incremental).
- Mapear pipeline scan -> chunk -> embed -> upsert.
- Verificar formato atual do ID de chunk.

## Qualidade de Dados
- Confirmar exclusão de `node_modules`, `dist`, `.git`, `build` e binários.
- Garantir payload rico com metadados de rastreabilidade.
- Validar tratamento de arquivos grandes e fallback de parser.

## Validação
- Executar smoke test de indexação.
- Executar cenário incremental idempotente.
- Verificar ausência de duplicidades por ID.

## Entrega
- Registrar impacto em qualidade de recuperação.
- Registrar impacto de custo/latência de embeddings.
- Listar comandos de validação e resultados.
