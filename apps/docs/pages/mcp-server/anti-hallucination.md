# Anti-Alucinação — Estratégia do `ask_code`

## Objetivo

Documentar **como e onde** o Code Compass delimita o LLM para evitar alucinação (fabricação de informações não existentes na base de código).

O pilar central é o **Evidence-first** (ver [Arquitetura](/ARCHITECTURE#decisão-3--evidence-first)): toda resposta válida **deve** conter `path + linha + snippet` verificável. Se não houver evidência suficiente, o sistema **não chama o LLM**.

---

## Camadas de proteção

A estratégia anti-alucinação é distribuída em **6 camadas** complementares, ordenadas pelo fluxo de execução.

### 1. Validação rigorosa de input

Antes de qualquer busca, todos os campos são validados e sanitizados.

| Campo        | Restrição                              | Referência                    |
|-------------|----------------------------------------|-------------------------------|
| `query`     | `string`, não vazio, máx 500 chars     | `ask-code.tool.ts:146-158`   |
| `topK`      | `number`, clamp entre 1 e 20           | `ask-code.tool.ts:160-168`   |
| `pathPrefix`| sem `..`, sem `\0`, máx 200 chars      | `ask-code.tool.ts:170-190`   |
| `language`  | `string`, máx 32 chars, lowercase      | `ask-code.tool.ts:192-206`   |
| `minScore`  | `number` finito                         | `ask-code.tool.ts:208-216`   |

Isso impede que inputs malformados ou maliciosos gerem resultados imprevisíveis.

### 2. Filtro de score mínimo (relevância semântica)

Após a busca vetorial no Qdrant, apenas resultados com **score ≥ `minScore`** (default: `0.6`) são considerados:

```typescript
// ask-code.tool.ts:66-69
const ranked = searchOutput.results
  .filter((result) => this.matchesLanguage(result.path, input.language))
  .filter((result) => result.score >= input.minScore)
  .slice(0, input.topK);
```

**Por que isso importa:** sem esse filtro, trechos irrelevantes poderiam entrar no contexto e induzir o LLM a fabricar conexões inexistentes.

### 3. Limites de contexto por escopo

A quantidade de evidências injetadas no prompt é controlada por constantes:

| Constante                         | Valor | Efeito                                                        |
|----------------------------------|-------|---------------------------------------------------------------|
| `DEFAULT_TOP_K`                  | 5     | Quantidade padrão de resultados                               |
| `MAX_TOP_K`                      | 20    | Limite absoluto de resultados                                 |
| `MAX_CONTEXTS_PER_REPO_WIDE_SCOPE` | 2   | Máximo de contextos por repo em buscas multi-repo           |
| `MAX_PER_REPO_ON_ALL_SCOPE`     | 3     | Máximo por repo em buscas "all" (`search-code.tool.ts:15`)  |

Esses limites evitam **diluição de contexto**: poucos trechos relevantes são melhores do que muitos trechos medianos.

### 4. Fail-safe: sem evidência = sem LLM

Se **nenhuma** evidência sobrevive aos filtros, o sistema retorna uma resposta fixa **sem chamar o LLM**:

```typescript
// ask-code.tool.ts:73-91
if (enriched.length === 0) {
  return {
    answer: 'Sem evidencia suficiente. Tente refinar a pergunta ou ajustar os filtros.',
    evidences: [],
    meta: { /* ... */ contextsUsed: 0 },
  };
}
```

Esse é o guardrail mais importante: **0 contexto = 0 chance de alucinação**.

### 5. Enriquecimento via filesystem (fonte de verdade)

Antes de montar o prompt, cada evidência é **verificada contra o arquivo real** no disco via `openFileTool.execute()`:

```typescript
// ask-code.tool.ts:272-278
const file = await this.openFileTool.execute({
  repo: evidence.repo,
  path: evidence.path,
  startLine,
  endLine,
});
const snippet = file.text.trim();
```

Isso garante que o snippet enviado ao LLM é a **versão atual do código**, não uma versão potencialmente desatualizada do índice vetorial.

### 6. System prompt com grounding rígido

O prompt de sistema instrui o LLM com **3 regras anti-alucinação**:

```typescript
// ask-code.tool.ts:331-336
const system = [
  'Voce e um assistente especializado em analisar codigo-fonte.',
  'Responda as perguntas do usuario baseando-se APENAS no contexto fornecido.',
  'Se a informacao nao estiver no contexto, diga que nao encontrou essa informacao no codigo indexado.',
  'Seja conciso e direto. Responda em portugues brasileiro.',
].join('\n');
```

| Regra                    | Efeito                                                  |
|--------------------------|----------------------------------------------------------|
| `APENAS no contexto`    | Proíbe o LLM de usar conhecimento externo               |
| `diga que nao encontrou`| Instrui admissão de ignorância em vez de fabricação      |
| `Seja conciso e direto` | Reduz margem para elaboração inventiva                   |

O prompt do usuário complementa com **evidências concretas** (path + linhas + snippet em code blocks), fornecendo a referência verificável.

---

## Fluxo completo

```
Query do Agente
    │
    ▼
┌──────────────────────────┐
│  1. Validação de Input   │ ← rejeita inputs malformados
└──────────┬───────────────┘
           ▼
┌──────────────────────────┐
│  2. Busca Vetorial       │ ← Qdrant retorna topK com scores
│     (search_code)        │
└──────────┬───────────────┘
           ▼
┌──────────────────────────┐
│  3. Filtro minScore ≥ 0.6│ ← descarta resultados irrelevantes
│  + filtro de linguagem   │
│  + limites por escopo    │
└──────────┬───────────────┘
           ▼
      ┌────┴────┐
      │ 0 hits? │
      └────┬────┘
     SIM   │   NÃO
      │    │    │
      ▼    │    ▼
 Resposta  │  ┌──────────────────────────┐
  fixa ✋  │  │  4. Enriquecimento       │ ← open_file confirma snippet real
           │  └──────────┬───────────────┘
           │             ▼
           │  ┌──────────────────────────┐
           │  │  5. Monta prompt         │ ← system prompt + contexto real
           │  │     com grounding        │
           │  └──────────┬───────────────┘
           │             ▼
           │  ┌──────────────────────────┐
           │  │  6. LLM responde         │ ← baseado APENAS nas evidências
           │  └──────────┬───────────────┘
           │             ▼
           └────────►  Output
                    answer + evidences[]
                    com path/linhas/score
```

---

## Referências no código

| Arquivo                              | Linhas      | Responsabilidade                          |
|--------------------------------------|-------------|-------------------------------------------|
| `apps/mcp-server/src/ask-code.tool.ts`   | 10-21     | Constantes de limites (topK, minScore)   |
| `apps/mcp-server/src/ask-code.tool.ts`   | 66-69     | Filtros de score e linguagem             |
| `apps/mcp-server/src/ask-code.tool.ts`   | 73-91     | Fail-safe sem evidência                  |
| `apps/mcp-server/src/ask-code.tool.ts`   | 251-292   | Enriquecimento via open_file             |
| `apps/mcp-server/src/ask-code.tool.ts`   | 330-357   | Construção do prompt (grounding)         |
| `apps/mcp-server/src/search-code.tool.ts`| 15        | `MAX_PER_REPO_ON_ALL_SCOPE`             |
| `apps/mcp-server/src/search-code.tool.ts`| 216-243   | Guardas de escopo nos resultados         |
| `apps/docs/pages/ARCHITECTURE.md`        | 8, 266-267| Pilar Evidence-first e ADR               |

---

## Troubleshooting

### O LLM está respondendo coisas que não existem no código

1. **Verifique o `minScore`:** um valor muito baixo (ex: `0.1`) permite contextos irrelevantes. O default `0.6` é um bom equilíbrio.
2. **Verifique o `topK`:** valores muito altos podem diluir o contexto com trechos pouco relevantes.
3. **Verifique o índice:** se o repositório mudou significativamente desde a última indexação, os snippets enriquecidos podem estar desatualizados. Rode `make index` ou `make index-all`.

### O LLM responde "Sem evidência suficiente" para tudo

1. **Verifique se o Qdrant está rodando:** `make up` ou `docker ps`.
2. **Verifique se a collection tem pontos:** use o dashboard do Qdrant em `http://localhost:6333/dashboard`.
3. **Reduza o `minScore`:** se o valor está muito alto, trechos relevantes podem estar sendo descartados.
4. **Verifique o modelo de embeddings:** o modelo no MCP server (`EMBEDDING_MODEL`) deve ser o **mesmo** usado na indexação.

### O contexto enviado ao LLM está desatualizado

O `enrichEvidences` re-lê o arquivo do filesystem antes de enviar ao LLM. Se o snippet ainda está desatualizado:
1. Verifique se o `REPO_ROOT` aponta para o diretório correto.
2. Rode `make index` para reindexar.
