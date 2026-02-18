# AGENTS.md — Code Compass

## 1) Objetivo
Este arquivo define as regras globais para qualquer agente (Codex/ChatGPT) operar neste monorepo com previsibilidade.
Leia este arquivo no início de cada tarefa, antes de planejar mudanças e antes de abrir/editar múltiplas áreas.
Use as skills por domínio para detalhes de implementação; este documento fica acima delas como política comum.

## 2) Mapa do Repositório

### 2.1 Estado atual (versionado hoje)
```text
code-compass/
  AGENTS.md
  README.md
  apps/
    docs/
      pages/
        ARCHITECTURE.md
        STRUCTURE.md
        ADRs/
  .agents/
    skills/
      developer-*/
```

### 2.2 Estrutura alvo (fonte: `apps/docs/pages/STRUCTURE.md`)
```text
code-compass/
  apps/
    mcp-server/      # ownership: MCP Server
    indexer/         # ownership: Indexer/Worker
    docs/            # ownership: documentação técnica/ADR/runbooks
  packages/shared/   # ownership: contratos/schemas
  infra/             # ownership: infra + qdrant + observabilidade
  scripts/           # ownership: bootstrap/ci/ops
```

### 2.3 Ownership por área
- MCP Server: `apps/mcp-server`.
- Indexer/Worker: `apps/indexer`.
- Vector DB: `infra/qdrant` + contratos de payload em `packages/shared`.
- Infra: `infra/`, `.env.example`, `Makefile`, `scripts/dev`, `scripts/ops`.
- Quality: testes/lint/typecheck em `apps/*/test*`, `scripts/ci`, `.github/workflows`.
- Docs: `README.md`, `apps/docs/pages/ARCHITECTURE.md`, `apps/docs/pages/STRUCTURE.md`, `apps/docs/pages/**`, `apps/docs/pages/ADRs/**`, `apps/docs/assets/**`.

## 3) Como escolher a skill certa

### 3.1 Local canônico de skills
- Caminho canônico: `.agents/skills/<skill>/SKILL.md`.
- Metadados de UI por skill: `.agents/skills/<skill>/agents/openai.yaml`.
- Regra: manter cada skill autocontida em `.agents/skills/<skill>/` com `SKILL.md` obrigatório.
- Por quê: centraliza discovery/trigger e evita divergência de instrução.

### 3.2 Skills por domínio (nomes padrão)
- `developer-mcp-server`: usar para changes em NestJS/MCP tools/contratos.
- `developer-indexer`: usar para ingestão Python, chunking, embeddings e incremental/full.
- `developer-vector-db`: usar para schema/operação Qdrant e migrações de coleção/payload.
- `developer-infra`: usar para docker-compose, env, bootstrap local e observabilidade.
- `developer-quality`: usar para testes/lint/typecheck/regressão e gates.
- `developer-docs`: usar para README/ADR/runbook/troubleshooting.

### 3.3 Regra de ouro para mudanças cruzadas
- Regra: começar pela skill mais core da mudança e chamar as demais por handoff explícito.
- Por quê: reduz retrabalho e mantém sequência causal correta.

Formato de handoff obrigatório:
```text
Handoff para <skill-destino>
- Contexto recebido: <1-2 linhas>
- Decisão já tomada: <contrato/assunção>
- Arquivos afetados: <paths>
- Validação já executada: <comandos + resultado>
- Risco aberto: <curto>
```

## 4) Workflow padrão (global)

### Discovery
- Deve produzir: escopo, assunções explícitas e riscos.
- Por quê: evita implementação em hipótese oculta.

### Plan
- Deve produzir: passos ordenados, arquivos alvo e estratégia de validação.
- Por quê: garante execução verificável e reversível.

### Implement
- Deve produzir: mudanças mínimas, coesas e com impacto declarado.
- Por quê: reduz risco de regressão e facilita review.

### Validate
- Deve produzir: comandos executados + evidências (pass/fail) + cobertura do escopo.
- Por quê: sem evidência não há conclusão técnica confiável.

### Deliver
- Deve produzir: resumo final, arquivos alterados e "como testar".
- Por quê: permite handoff humano sem ambiguidade.

## 5) Definition of Done (DoD) global
- Build/lint/typecheck do escopo passam (quando existirem no repo).
- Testes relevantes (unit/integration/e2e) do escopo passam (quando existirem).
- Documentação mínima atualizada (`README.md`, `apps/docs/pages/**`, `apps/docs/pages/ADRs/**`) quando houver mudança de comportamento/arquitetura.
- Contratos públicos (API/schemas/payloads/tools) permanecem compatíveis ou têm plano explícito de migração.
- Não há regressão conhecida sem registro claro de risco e próximo passo.

## 6) Guardrails globais (alta prioridade)
- Não quebrar contratos públicos; por quê: consumidores MCP dependem de estabilidade.
- Não commitar segredos/chaves/tokens; por quê: risco imediato de segurança.
- Infra deve subir do zero com passos reproduzíveis; por quê: reduz tempo de incidentes/onboarding.
- Evitar big-bang refactor; por quê: mudanças incrementais são auditáveis e reversíveis.
- Garantir logging/observabilidade mínima; por quê: sem sinais não há debug confiável.
- Preferir defaults seguros (`read-only`, allowlist, validação forte); por quê: minimiza superfície de falha.

## 7) Convenções de contribuição
- Commits: na ausência de padrão versionado, usar Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`); por quê: melhora rastreabilidade.
- Branches: na ausência de padrão versionado, usar `feat/*`, `fix/*`, `chore/*`, `docs/*`; por quê: facilita triagem no remoto.
- Naming: `kebab-case` para arquivos/pastas, `UPPER_SNAKE_CASE` para env vars, nomes de módulos explícitos; por quê: previsibilidade de busca.
- Configs: manter valores de exemplo em `.env.example` na raiz; por quê: bootstrap consistente sem vazar segredo.
- Mudanças arquiteturais: registrar em `apps/docs/pages/ADRs/ADR-XX.md`; por quê: preservar contexto de decisão.

## 8) Comandos padrão (copiáveis)

### 8.1 Estado atual do repositório
- `Makefile`, `apps/*`, `infra/docker-compose.yml`, `package.json` e `requirements.txt` estão versionados.
- Comandos canônicos abaixo estão disponíveis e validados.

### 8.2 Comandos canônicos
```bash
# subir infra local
make up

# indexação inicial
make index

# servidor MCP em dev
make dev

# logs da infra
make logs

# derrubar infra
make down
```

```bash
# Node/NestJS (exemplo por módulo)
cd apps/mcp-server
npm run lint
npm run typecheck
npm test
```

```bash
# Python indexer (exemplo por módulo)
cd apps/indexer
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
```

## 9) Padrões por linguagem

### 9.1 Node/NestJS (MCP Server)
- Organizar por módulo (`modules/`, `services/`, `adapters/`, `config/`); por quê: separa domínio, integração e infraestrutura.
- Usar DI nativa do NestJS e validação de DTO; por quê: reduz acoplamento e erro de runtime.
- Padronizar logging estruturado por requisição/tool; por quê: acelera auditoria e debug.
- Cobrir handlers críticos com testes unitários + integração; por quê: protege contratos MCP.

### 9.2 Python (Indexer/Worker)
- Usar ambiente virtual local (`.venv`) e dependências explícitas; por quê: reprodutibilidade.
- Separar ingestão, chunking, embeddings e storage por pacote; por quê: facilita evolução incremental.
- Tratar arquivos grandes e exclusões cedo no pipeline; por quê: controla custo e memória.
- Garantir IDs determinísticos para chunks/pontos; por quê: evita duplicidade e quebra de incremental.

### 9.3 Qdrant (Vector DB)
- Nome padrão inicial de coleção: `code_chunks`; por quê: consistência com README/ADR.
- Payload mínimo com `repo`, `branch`, `commit`, `path`, `language`, `startLine`, `endLine`; por quê: filtros e evidência auditável.
- Alterações de schema precisam de migração/rollback explícitos; por quê: evita perda de busca/compatibilidade.
- Evitar delete destrutivo sem critério e backup; por quê: preserva recuperabilidade operacional.

## 10) Handoff e escalonamento

### 10.1 Quando parar e perguntar
- Requisito ambíguo que muda contrato público.
- Risco de breaking change sem estratégia de migração.
- Decisão arquitetural nova sem ADR/decisor definido.
- Falta de artefato essencial para validar (ex.: scripts, Makefile, módulo inexistente).

### 10.2 Checklist mínimo de perguntas (3–5)
1. Qual é o contrato público que não pode quebrar?
2. Qual área é source of truth para esta mudança (MCP, Indexer, Vector DB, Infra, Docs)?
3. Quais comandos/provas definem "validado" neste PR/tarefa?
4. A mudança precisa de migração/backfill/rollback? Qual janela de risco?
5. A decisão exige ADR? Se sim, qual número/escopo?
