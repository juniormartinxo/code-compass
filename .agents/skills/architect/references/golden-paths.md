# Golden Paths — Code Compass Architect

## 1) Criar/alterar tool MCP

### Passos macro
1. Mapear contrato atual da tool e consumidores impactados.
2. Definir mudança de contrato (aditiva vs breaking) e versão alvo.
3. Ajustar boundary MCP Server sem acoplar lógica de indexação/storage.
4. Definir estratégia de rollout (flag, dual response ou fallback).
5. Registrar decisão em Decision Record.

### O que validar
- Contrato de entrada/saída mantém compatibilidade ou possui migração explícita.
- Campos de evidência estão presentes (`path`, linhas e score/snippet quando aplicável).
- Segurança preservada (`default deny`, allowlist, proteção de path traversal).
- Validação técnica executada no módulo (lint/typecheck/testes, quando existir).

### Evidências mínimas
- Exemplo de request/response antes e depois.
- Resultado de smoke de chamada da tool com payload real.

## 2) Rodar reindex incremental

### Passos macro
1. Confirmar infra vetorial disponível (`make up`, `make health`).
2. Verificar configuração (`.env`, coleção alvo, provider de embedding).
3. Executar fluxo incremental (`make index-incremental` ou `make index-docker-incremental`).
4. Verificar impacto em pontos/chunks alterados.
5. Validar consulta semântica pós-indexação e rastreabilidade de evidência.

### O que validar
- IDs de chunk permanecem determinísticos.
- Upsert é idempotente (reexecução não duplica dados).
- Filtros por payload continuam funcionando.
- Sem regressão de qualidade evidente nas respostas com evidência.

### Evidências mínimas
- Saída dos comandos de indexação e health.
- Contagem/indicador de mudanças processadas.
- Exemplo de query no Qdrant e resposta correlata no MCP.

## 3) Criar/migrar collection Qdrant

### Passos macro
1. Definir schema alvo (vector size, distance metric, payload mínimo).
2. Planejar migração (coleção paralela, backfill e cutover).
3. Executar carga inicial e validação comparativa.
4. Realizar cutover controlado para nova coleção.
5. Manter rollback disponível até estabilização.

### O que validar
- Nova coleção responde consultas com filtros obrigatórios.
- Contratos de payload consumidos por MCP/Indexer permanecem compatíveis.
- Performance e recall mínimo estão aceitáveis para o caso de uso.
- Rollback foi ensaiado ou está descrito de forma acionável.

### Evidências mínimas
- Configuração final de coleção e payload documentada.
- Resultado de busca antes/depois do cutover.
- Checklist de rollback preenchido.

