# Plano Completo de Integração do Tree-sitter no Code Compass

## Resumo

Este plano substitui a base atual de parsing semântico de código do indexer por Tree-sitter, mantendo os contratos externos do Code Compass e preservando a arquitetura atual do pipeline `scan -> chunk -> embed -> upsert -> search`.

Adoção decidida:

- rollout direto: `tree_sitter` será o backend default
- arquitetura preparada para múltiplas linguagens
- primeira entrega funcional cobre apenas as linguagens já presentes no repositório: `python`, `typescript`, `typescriptreact`, `javascript`, `javascriptreact`
- `docs`, `config` e `sql` continuam com os chunkers especializados atuais
- haverá rebuild completo obrigatório do índice por mudança estrutural de chunking
- `legacy` será mantido apenas como escape hatch operacional temporário

Base técnica:

- usar os bindings oficiais Python do Tree-sitter
- carregar grammars por pacotes pré-compilados por linguagem
- usar `Parser`, `Language`, `Query` e `QueryCursor` como fundação do parsing e da extração semântica

## Objetivo

Trocar o parser atual por uma base estrutural real para:

- reduzir manutenção heurística em `TS/TSX/JS`
- unificar o modelo de parsing semântico de código
- preparar expansão futura para outras linguagens
- preservar `chunkId`, `contentHash`, `summaryText`, `contextText`, `callers`, `callees` e o payload já consumido pelo MCP/Qdrant

## Fora de Escopo

- migrar `markdown`, `config` ou `sql` para Tree-sitter
- entregar suporte semântico completo a Go, Rust ou Java neste ciclo
- mudar contrato público do MCP
- redesenhar payload do Qdrant fora do estritamente necessário
- remover o backend `legacy` neste mesmo trabalho

## Estado Atual

Hoje o indexer usa:

- `ast` nativo para Python em [chunk_python.py](apps/indexer/indexer/chunk_python.py)
- parser heurístico com regex e balanceamento estrutural para TS/TSX/JS em [chunk_ts.py](apps/indexer/indexer/chunk_ts.py)
- dispatch por linguagem em [chunk.py](apps/indexer/indexer/chunk.py)
- schema atual `v5` em [chunk_models.py](apps/indexer/indexer/chunk_models.py)

Problemas atuais:

- manutenção alta do parser heurístico
- edge cases frequentes em TS/TSX/JS moderno
- pouca extensibilidade multi-linguagem
- dificuldade de observabilidade sobre fallback, cobertura estrutural e custo do parsing

## Mudanças de Interface, Tipos e Contratos

### Mudanças explícitas

1. Adicionar `CODE_CHUNK_PARSER_BACKEND=tree_sitter|legacy` em [config.py](apps/indexer/indexer/config.py), com default `tree_sitter`.
2. Subir `CHUNK_SCHEMA_VERSION` de `v5` para `v6` em [chunk_models.py](apps/indexer/indexer/chunk_models.py).
3. Adicionar logs estruturados de parsing e fallback no runtime do indexer.
4. Documentar rebuild completo obrigatório e rollback operacional.

### Mudanças que não serão feitas

1. Não renomear `chunkStrategy` existente:
   - `python_symbol`
   - `ts_symbol`
2. Não remover campos atuais do payload:
   - `chunk_schema_version`
   - `chunk_strategy`
   - `content_type`
   - `chunk_content_type`
   - `symbol_name`
   - `qualified_symbol_name`
   - `symbol_type`
   - `parent_symbol`
   - `imports`
   - `exports`
   - `callers`
   - `callees`
   - `summary_text`
   - `context_text`
3. Não registrar estado de fallback no payload do Qdrant.
   - fallback será observabilidade de runtime, não contrato de armazenamento.

## Estratégia de Dependências e Compatibilidade

### Dependências novas

Adicionar em [requirements.txt](apps/indexer/requirements.txt):

- binding principal de Tree-sitter
- grammar package Python
- grammar package TypeScript/TSX
- grammar package JavaScript/JSX, se necessário separado

### Regra de versionamento

1. Fixar versões exatas dos bindings e grammars na primeira entrega.
2. Documentar uma matriz de compatibilidade mínima em [apps/indexer/README.md](apps/indexer/README.md).
3. Não permitir upgrade implícito solto de grammars neste ciclo.
4. Atualizar versões apenas via follow-up controlado com regressão de fixtures.

### Matriz inicial de compatibilidade

Documentar:

- versão do binding Python Tree-sitter usada
- versão das grammars Python/TypeScript/JavaScript
- linguagens efetivamente suportadas semanticamente neste ciclo
- linguagens fora de suporte semântico continuam em fallback atual

## Arquitetura Proposta

### Camada interna `tree_sitter/`

Criar `apps/indexer/indexer/tree_sitter/` com:

1. `runtime.py`
   - carrega grammars
   - cria e reutiliza `Language`
   - cria e reutiliza `Parser`
   - compila e reutiliza `Query`
   - expõe helpers de bytes, texto e linhas

2. `registry.py`
   - resolve adapter por linguagem do indexer
   - mapeia:
     - `python`
     - `typescript`
     - `typescriptreact`
     - `javascript`
     - `javascriptreact`

3. `types.py`
   - define `SyntaxChunkSpec` compartilhado
   - shape compatível com `ChunkDocument`

4. `adapters/python.py`
   - parse e extração semântica Python

5. `adapters/typescript.py`
   - parse e extração semântica TS/TSX/JS/JSX

6. `queries/python.scm`
7. `queries/typescript.scm`
8. `queries/tsx.scm`
9. `queries/javascript.scm`
10. `queries/jsx.scm`

### Regra arquitetural

- módulos fora de `tree_sitter/` não importam grammars diretamente
- [chunk.py](apps/indexer/indexer/chunk.py) só enxerga a registry e specs normalizados
- `legacy` e `tree_sitter` devem produzir a mesma estrutura de saída pública

## Estratégia de Migração do Código Atual

### Congelamento dos parsers atuais

Criar:
- `chunk_python_legacy.py`
- `chunk_ts_legacy.py`

Esses módulos recebem o código atual, sem refactor funcional adicional.

### Wrappers públicos

- [chunk_python.py](apps/indexer/indexer/chunk_python.py) vira wrapper que resolve backend e chama:
  - `tree_sitter/adapters/python.py`
  - ou `chunk_python_legacy.py`
- [chunk_ts.py](apps/indexer/indexer/chunk_ts.py) idem

### Regra de seleção de backend

1. `CODE_CHUNK_PARSER_BACKEND=tree_sitter`
   - usa Tree-sitter
2. `CODE_CHUNK_PARSER_BACKEND=legacy`
   - usa parsers antigos
3. default:
   - `tree_sitter`

## Fase 0 — Baseline e Benchmark Pré-Migração

### Objetivo

Criar baseline comparável antes da troca do parser.

### Entregas

1. benchmark do backend atual em repo real e fixture repo
2. relatório base com:
   - tempo total de `indexer chunk`
   - tempo total de `index`
   - quantidade de chunks por arquivo
   - distribuição de `chunkStrategy`
   - taxa de fallback atual
   - cobertura por arquivo
3. salvar baseline em documento técnico de apoio em `docs/tree-sitter/`

### Cenários de benchmark

1. fixture repo em [fixtures/chunking](apps/indexer/tests/fixtures/chunking)
2. repo atual em amostra controlada
3. arquivos grandes e arquivos com alta cardinalidade de símbolos

### Critério de saída

Ter números objetivos antes de implementar Tree-sitter.

## Fase 1 — Fundação Tree-sitter

### Arquivos

- [requirements.txt](apps/indexer/requirements.txt)
- [config.py](apps/indexer/indexer/config.py)
- `apps/indexer/indexer/tree_sitter/`

### Implementação

1. adicionar dependências fixadas
2. adicionar `CODE_CHUNK_PARSER_BACKEND`
3. implementar cache de:
   - `Language`
   - `Parser`
   - `Query`
4. padronizar helpers de:
   - `startLine`
   - `endLine`
   - byte ranges
   - slice de conteúdo
5. falhar cedo se backend for `tree_sitter` e grammar não carregar

### Testes

1. grammar load por linguagem
2. parser cache
3. query cache
4. erro explícito quando grammar faltar

## Fase 2 — Python com Tree-sitter

### Arquivos

- [chunk_python.py](apps/indexer/indexer/chunk_python.py)
- `chunk_python_legacy.py`
- `tree_sitter/adapters/python.py`
- [chunk_graph.py](apps/indexer/indexer/chunk_graph.py)

### Implementação

1. capturar:
   - `function_definition`
   - `decorated_definition`
   - `class_definition`
2. extrair:
   - funções
   - métodos
   - classes pequenas
   - classes grandes com resumo + métodos
3. incluir contexto lexical não coberto
4. extrair:
   - `symbolName`
   - `qualifiedSymbolName`
   - `symbolType`
   - `parentSymbol`
   - `signature`
5. grafo:
   - chamadas no subtree do símbolo
   - decorators entram em `callees`
   - manter proteção contra:
     - `get_client().load()` virar símbolo local
     - `super.load()` virar método da classe atual

### Fallback

Voltar para `line_window` se:
1. houver erro sintático relevante
2. houver nós missing/error em símbolo emitido
3. cobertura estrutural útil do arquivo ficar abaixo de `INDEX_MIN_FILE_COVERAGE`

### Testes obrigatórios

1. função simples
2. `async def`
3. classe pequena
4. classe grande
5. decorators
6. comentários fora do AST relevante
7. `get_client().load()`
8. `super.load()`
9. arquivo inválido com fallback

## Fase 3 — TypeScript / TSX / JS / JSX com Tree-sitter

### Arquivos

- [chunk_ts.py](apps/indexer/indexer/chunk_ts.py)
- `chunk_ts_legacy.py`
- `tree_sitter/adapters/typescript.py`
- [chunk_graph.py](apps/indexer/indexer/chunk_graph.py)

### Implementação

1. capturar:
   - `class_declaration`
   - `method_definition`
   - `function_declaration`
   - `lexical_declaration` com `arrow_function` ou `function`
   - `export default` nomeado e anônimo
   - getters e setters
2. classificar semântica:
   - `hook` por nome `useX`
   - `component` por PascalCase com JSX
   - `helper` para função top-level restante
3. tratar casos obrigatórios:
   - overloads
   - decorators de classe e método
   - decorators multiline
   - `export default memo(function Name() {})`
   - `export default forwardRef(function Name() {})`
   - `export default () => ...`
   - `export default async () => ...`
   - `export default function() {}`
   - `export default class extends Base {}`
   - `abstract class`
   - fragments JSX `<>...</>`
   - JSX condicional e aninhado
4. grafo:
   - chamadas só no subtree do símbolo
   - incluir decorators
   - manter proteção contra:
     - `new Client().run()` virar símbolo local
     - `super.load()` virar método da classe atual

### Compatibilidade de decorators

Documentar e testar:
1. decorators legacy
2. decorators Stage-3 suportados pela grammar escolhida
3. explicitar no README qual variante é assumida como suportada

### Testes obrigatórios

1. helper
2. hook
3. component
4. classe pequena
5. classe grande
6. overloads
7. getters/setters
8. default export nomeado
9. default export anônimo
10. wrappers `memo` / `forwardRef`
11. decorators multiline
12. JSX fragment
13. JSX condicional aninhado
14. arquivo inválido com fallback

## Fase 4 — Integração no Pipeline

### Arquivos

- [chunk.py](apps/indexer/indexer/chunk.py)
- [__main__.py](apps/indexer/indexer/__main__.py)

### Implementação

1. [chunk.py](apps/indexer/indexer/chunk.py) passa a resolver backend de código via registry
2. `docs`, `config` e `sql` permanecem como estão
3. manter construção atual de:
   - `ChunkDocument`
   - `summaryText`
   - `contextText`
   - `chunkId`
   - `contentHash`
4. warnings estruturados de fallback por arquivo
5. nenhuma mudança no contrato do payload final além do bump de schema

## Fase 5 — Schema, Observabilidade e Operação

### Schema

1. subir `CHUNK_SCHEMA_VERSION` para `v6`
2. manter bloqueio de mistura de schema legado
3. exigir rebuild completo obrigatório

### Observabilidade

Adicionar logs estruturados por arquivo com este shape mínimo:

```json
{
  "event": "chunk_parse",
  "parser_backend": "tree_sitter",
  "language": "typescriptreact",
  "path": "src/product-card.tsx",
  "fallback": false,
  "fallback_reason": null,
  "chunk_count": 4,
  "duration_ms": 12
}
```

Em fallback:

```json
{
  "event": "chunk_parse",
  "parser_backend": "tree_sitter",
  "language": "python",
  "path": "src/broken.py",
  "fallback": true,
  "fallback_reason": "parse_error",
  "chunk_count": 1,
  "duration_ms": 3
}
```

Métricas mínimas a emitir/agrupar:
1. arquivos parseados por backend
2. taxa de fallback por linguagem
3. duração média e p95 por linguagem
4. chunks gerados por linguagem
5. erros de grammar loading
6. cobertura estrutural média por arquivo

### Regra explícita

Fallback não entra no payload do Qdrant.

## Fase 6 — Benchmark Pós-Migração e Gate de Qualidade

### Comparação obrigatória

Comparar `legacy` vs `tree_sitter` em:
1. tempo de `indexer chunk`
2. tempo de `index`
3. número de chunks por arquivo
4. distribuição de `chunkStrategy`
5. taxa de fallback
6. preservação dos campos do payload

### Gate de qualidade

1. 100% dos campos de payload preservados
2. smoke `index -> search` aprovado
3. taxa de fallback em repos conhecidos abaixo de um threshold inicial documentado
4. tempo de parsing `tree_sitter` não pode degradar sem explicação documentada

Default escolhido:
- meta inicial de performance: `tree_sitter` deve ficar até `1.5x` do legacy em parsing puro nos cenários conhecidos
- isso é gate inicial de engenharia, não contrato público

## Estratégia de Regressão

### Reuso de fixtures existentes

Usar como base principal:
- [fixtures/chunking](apps/indexer/tests/fixtures/chunking)

Expandir com novas fixtures específicas de Tree-sitter:
1. Python com decorators complexos
2. TS com overloads
3. TSX com wrappers
4. TSX com JSX fragment e JSX aninhado
5. default exports anônimos
6. decorators Stage-3 e legacy
7. arquivos quebrados para fallback

### Estratégia de comparação legacy vs tree_sitter

Não usar diff textual cego como verdade absoluta.

Usar três níveis:
1. invariantes obrigatórios
   - campo presente
   - payload compatível
   - `chunkStrategy` correta
2. regressão estrutural
   - conjunto de símbolos
   - cardinalidade esperada
   - ranges coerentes
3. revisão manual só dos casos divergentes relevantes

## Testes e Cenários

### Testes unitários

Arquivos:
- [test_chunk_python.py](apps/indexer/tests/test_chunk_python.py)
- [test_chunk_ts.py](apps/indexer/tests/test_chunk_ts.py)
- [test_chunk.py](apps/indexer/tests/test_chunk.py)
- [test_config.py](apps/indexer/tests/test_config.py)

Cobertura mínima:
1. grammar loading
2. query execution
3. parsing por linguagem
4. fallback por parse error
5. `chunkId` estável
6. `contentHash` mutável
7. `summaryText` e `contextText`
8. `callers` e `callees`
9. casos de borda já corrigidos historicamente

### Testes de integração

Arquivos:
- [test_cli.py](apps/indexer/tests/test_cli.py)
- smoke do indexer

Cobertura mínima:
1. `indexer chunk` com backend default
2. `indexer chunk` com backend `legacy`
3. `indexer index` em collection temporária
4. `indexer search` após indexação
5. bloqueio de mistura `v5/v6`

## Runbook Operacional

### Rollout

1. backup lógico do estado operacional atual
2. atualizar dependências Python do indexer
3. validar grammar loading
4. recriar ou limpar collections antigas
5. rodar rebuild completo
6. rodar smoke `index -> search`
7. validar taxa de fallback e cardinalidade de chunks
8. liberar uso padrão com backend `tree_sitter`

### Sequência operacional documentada

1. `make py-setup`
2. validar ambiente do indexer
3. `make health`
4. rebuild completo do índice
5. smoke controlado de busca
6. checagem de logs estruturados de parsing

### Rollback

1. setar `CODE_CHUNK_PARSER_BACKEND=legacy`
2. recriar/reindexar com backend compatível com o estado desejado
3. repetir smoke `index -> search`
4. manter rollback só como mecanismo de estabilização temporária

### Remoção do backend legacy

Planejar como follow-up separado.

Critério de remoção:
1. ciclo de estabilização de 2 sprints
2. zero incidentes críticos de parsing em produção
3. taxa de fallback controlada
4. benchmark e smoke estáveis

## Critérios de Aceitação Finais

1. `tree_sitter` é o backend default para código
2. `legacy` permanece disponível para rollback temporário
3. `v6` bloqueia mistura com schemas antigos
4. Python e TS/TSX/JS/JSX continuam emitindo payload compatível com o ecossistema atual
5. o pipeline `index -> search` funciona ponta a ponta
6. existem métricas e logs suficientes para diagnosticar fallback e degradação
7. benchmark antes/depois está documentado
8. fixtures cobrindo casos reais foram ampliadas e aprovadas

## Assunções e Defaults

1. A primeira entrega semântica Tree-sitter cobre apenas linguagens de código já presentes no repositório.
2. `docs`, `config` e `sql` permanecem nos parsers atuais.
3. O payload do Qdrant não receberá campos extras de fallback.
4. `CODE_CHUNK_PARSER_BACKEND=legacy` é temporário.
5. A troca de parser é mudança estrutural suficiente para exigir `v6`.
6. O objetivo deste ciclo é robustez e fundação multi-linguagem, não suporte amplo imediato a outras linguagens.

## Arquivos-Alvo

1. [apps/indexer/requirements.txt](apps/indexer/requirements.txt)
2. [apps/indexer/indexer/config.py](apps/indexer/indexer/config.py)
3. [apps/indexer/indexer/chunk.py](apps/indexer/indexer/chunk.py)
4. [apps/indexer/indexer/chunk_python.py](apps/indexer/indexer/chunk_python.py)
5. [apps/indexer/indexer/chunk_ts.py](apps/indexer/indexer/chunk_ts.py)
6. [apps/indexer/indexer/chunk_graph.py](apps/indexer/indexer/chunk_graph.py)
7. [apps/indexer/indexer/chunk_models.py](apps/indexer/indexer/chunk_models.py)
8. [apps/indexer/indexer/__main__.py](apps/indexer/indexer/__main__.py)
9. `apps/indexer/indexer/tree_sitter/`
10. `apps/indexer/indexer/chunk_python_legacy.py`
11. `apps/indexer/indexer/chunk_ts_legacy.py`
12. [apps/indexer/tests/test_chunk_python.py](apps/indexer/tests/test_chunk_python.py)
13. [apps/indexer/tests/test_chunk_ts.py](apps/indexer/tests/test_chunk_ts.py)
14. [apps/indexer/tests/test_chunk.py](apps/indexer/tests/test_chunk.py)
15. [apps/indexer/tests/test_cli.py](apps/indexer/tests/test_cli.py)
16. [apps/indexer/tests/test_config.py](apps/indexer/tests/test_config.py)
17. [apps/indexer/tests/fixtures/chunking](apps/indexer/tests/fixtures/chunking)
18. [apps/indexer/README.md](apps/indexer/README.md)
19. [docs/OPERATIONS.md](docs/OPERATIONS.md)
20. [docs/ROADMAP.md](docs/ROADMAP.md)
21. [docs/tree-sitter/plan.md](docs/tree-sitter/plan.md)
