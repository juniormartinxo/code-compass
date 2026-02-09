# Checklist Infra

## Discovery
- Revisar `infra/docker-compose.yml`, `Makefile` e `.env.example`.
- Mapear dependências e ordem de inicialização.
- Identificar comandos críticos de operação.

## Implementação
- Garantir defaults seguros para variáveis obrigatórias.
- Garantir comandos claros para subir/parar/logar/limpar.
- Garantir healthchecks e logs úteis para diagnóstico.

## Validação
- Executar fluxo "do zero" no ambiente local.
- Confirmar funcionamento de `up`, `index`, `dev`, `down`.
- Confirmar troubleshooting mínimo para falhas comuns.

## Entrega
- Registrar pré-requisitos e mudanças de compatibilidade.
- Listar comandos executados e resultado esperado.
- Registrar rollback sugerido.
