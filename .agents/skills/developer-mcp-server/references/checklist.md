# Checklist MCP Server

## Discovery
- Confirmar arquivos-alvo em `apps/mcp-server`.
- Identificar contrato atual de entrada/saída da tool.
- Levantar consumidores que dependem do contrato.

## Segurança e Contrato
- Validar allowlist/path traversal.
- Garantir erros com mensagens seguras e consistentes.
- Garantir evidência (`path`, linhas, score) quando aplicável.

## Validação
- Rodar lint/test/typecheck do módulo.
- Verificar backward compatibility de campos obrigatórios.
- Verificar impacto de latência em fluxo alterado.

## Entrega
- Resumir mudanças por arquivo.
- Listar comandos executados.
- Registrar risco residual e follow-ups.
