---
name: developer-tester
description: Executar testes de mudança específica no Code Compass com reprodução de bug antes/depois, testes de regressão unit/integration/e2e, smoke suite e evidências objetivas de validação quando houver bugfix, mudança de contrato API, indexação/busca, schema/payload Qdrant, UX crítica ou pipeline de ingestão; não usar para governança transversal de qualidade/CI/gates e política global de cobertura (usar `developer-quality`), nem para mudanças só de doc/markdown, renome sem efeito, cosmética visual, arquitetura ou refactor sem bug/feature.
---

# Developer Tester

## 1) Objetivo e Escopo
Esta skill é dona da execução de testes, validação de comportamento e reprodução de bugs para mudanças específicas do Code Compass.

Inclui:
- criação/ajuste de testes unit/integration/e2e;
- reprodução de bug com evidência antes/depois;
- execução de smoke suite de fluxo crítico;
- validação de comandos e coleta de evidências objetivas.

Não inclui:
- mudanças de arquitetura;
- refactors sem bug/feature;
- gestão de infraestrutura (delegar para `developer-infra`);
- implementação de feature de domínio fora do necessário para testar (delegar para skill core).

## 2) Trigger Policy (quando disparar / quando NÃO disparar)
Disparar esta skill quando houver:
- bugfix;
- mudança em contrato API;
- mudança em indexação/busca;
- mudança em schema/payload Qdrant;
- alteração em modos de interação/UX crítica;
- mudanças em pipeline de ingestão.

Não disparar esta skill quando houver apenas:
- alteração de doc/markdown;
- rename de variável sem efeito comportamental;
- mudanças puramente cosméticas.

Escopo de atuação para evitar over-triggering:
- focar em testes, qualidade e evidência de validação;
- delegar implementação de domínio para `developer-mcp-server`, `developer-indexer`, `developer-vector-db` ou `developer-infra`;
- se precisar atuar em múltiplos domínios, executar handoff explícito por skill.

## 3) Workflow padrão: Discovery -> Plan -> Implement -> Validate -> Deliver
1. Discovery
   - Mapear comportamento afetado e caminho de execução do bug/caso.
   - Levantar contratos críticos (MCP, Indexer, Qdrant) impactados.
   - Descobrir comandos reais do repositório (não assumir comandos por memória).
   - Consultar `references/test-strategy-checklist.md` para checklist de execução.
2. Plan
   - Selecionar cenários de teste: happy path, edge case principal e erro esperado.
   - Definir smoke suite mínima, dados de teste, fixtures e mocks.
   - Definir repro de bug com baseline antes da correção.
   - Definir proteção anti-flakiness (determinismo, isolamento, timeout realista).
3. Implement
   - Escrever/ajustar testes, fixtures, helpers e mocks necessários.
   - Registrar repro em `references/bug-repro-template.md` (ou equivalente no PR).
   - Proteger contrato e cenários de regressão com assert claro.
4. Validate
   - Executar comandos reais de lint/typecheck/test do repo.
   - Coletar evidência de resultado (pass/fail + contexto do comando).
   - Rodar e2e smoke quando aplicável (`references/e2e-smoke-suite.md`).
5. Deliver
   - Entregar resumo do que foi protegido por teste.
   - Entregar passo-a-passo de reprodução do bug e da validação.
   - Entregar riscos residuais e próximo passo recomendado.

## 4) DoD (Definition of Done) global tester
- Todo bugfix tem repro (antes) e teste (depois), quando viável.
- Não há flakiness conhecido introduzido pela mudança.
- Testes cobrem: happy path + edge case principal + erro esperado.
- Para RAG/Qdrant: existe teste de consulta/filtro e garantia de idempotência (sem duplicar chunks).
- Evidências de validação estão registradas com comandos reais do repo.

## 5) Guardrails tester
- Não aumentar tempo de pipeline sem motivo claro.
- Preferir testes determinísticos e bloquear dependência externa (rede) por padrão.
- Não usar dados sensíveis em fixtures, snapshots, logs ou prints.
- Não mascarar problema com `skip`, retry cego ou mock irreal.
- Evitar acoplamento entre testes por ordem de execução.

## 6) Golden Checks (comandos e evidências)
Regra obrigatória: descobrir comandos reais antes de validar.

Checklist de descoberta:
- `rg --files -g 'Makefile'`
- `rg --files -g '**/package.json'`
- `rg --files -g '**/pyproject.toml' -g '**/requirements.txt'`
- `rg --files -g 'infra/docker-compose.yml'`

Se os artefatos não existirem no snapshot atual, reportar explicitamente “não validado por ausência de artefato” e não inventar execução.

Comandos-alvo (usar somente se existirem):
- Node/NestJS (`apps/mcp-server`): `npm run lint`, `npm run typecheck`, `npm test`.
- Python Indexer (`apps/indexer`): `pytest` (e lint/typecheck quando houver ferramenta configurada).
- Infra/Qdrant: `docker compose -f infra/docker-compose.yml up -d` + `curl -s http://localhost:6333/readyz`.

Evidências mínimas em toda entrega QA:
- comando executado;
- resultado (pass/fail);
- cobertura de escopo validada;
- risco aberto que ficou fora da execução.

## 7) Templates e exemplos
Exemplos de prompts que devem ativar esta skill:
- "Corrija este bug no `search_code` e garanta repro antes/depois com teste de regressão."
- "Mudamos payload do Qdrant; ajuste testes de filtro e verifique idempotência da indexação incremental."
- "Incluímos nova regra na ingestão Python; monte plano QA com unit+integration+smoke e valide comandos reais."
- "Houve mudança de contrato de API MCP; atualize testes de contrato e reporte riscos residuais."

Anti-exemplos (não ativar esta skill):
- "Reescreva o README para onboarding de novos devs."
- "Renomeie variáveis para seguir padrão de estilo sem alterar comportamento."
- "Ajuste cor e espaçamento do texto em documentação Markdown."
- "Defina nova arquitetura de módulos do MCP server."

Referências da skill (carregar sob demanda):
- `references/test-strategy-checklist.md`: checklist operacional para discovery/plan/validate.
- `references/bug-repro-template.md`: template padrão para reprodução e evidência de bug.
- `references/e2e-smoke-suite.md`: suíte mínima de smoke e2e para MCP + Indexer + Qdrant.
