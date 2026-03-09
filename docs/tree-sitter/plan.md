# Plano de Implementação do Tree-sitter no Code Compass

## Resumo

Objetivo: substituir o parsing atual de chunks de código por uma base Tree-sitter no indexer, mantendo o pipeline `scan -> chunk -> embed -> upsert -> search` e preservando os contratos já consumidos pelo MCP e pelo Qdrant.

Decisões já travadas:

1. rollout direto: o backend padrão passa a ser Tree-sitter
2. arquitetura ampla para múltiplas linguagens
3. primeira entrega funcional cobre as linguagens já presentes no repositório: `python`, `typescript`, `typescriptreact`, `javascript`, `javascriptreact`
4. `docs`, `config` e `sql` permanecem com os chunkers especializados atuais
5. haverá rebuild completo obrigatório do índice por mudança material de chunking e identidade estrutural

Base técnica validada via Context7:

- usar os bindings Python oficiais com `Language(...)`, `Parser`, `Query` e `QueryCursor`
- carregar grammars por pacotes pré-compilados por linguagem, evitando build manual de grammars no primeiro ciclo

## Estado Atual

Hoje o Code Compass usa:

1. `ast` nativo em [chunk_python.py](/home/junior/apps/jm/code-compass/apps/indexer/indexer/chunk_python.py)
2. parser heurístico com regex e balanceamento estrutural em [chunk_ts.py](/home/junior/apps/jm/code-compass/apps/indexer/indexer/chunk_ts.py)
3. dispatch por linguagem em [chunk.py](/home/junior/apps/jm/code-compass/apps/indexer/indexer/chunk.py)
4. schema atual `v5` em [chunk_models.py](/home/junior/apps/jm/code-compass/apps/indexer/indexer/chunk_models.py)

Problema que este plano resolve:

- custo crescente de manutenção do parser heurístico
- fragilidade em edge cases de TS/TSX/JS moderno
- ausência de fundação real para expansão multi-linguagem
- necessidade de unificar a extração estrutural de símbolos e chamadas

## Escopo

Em escopo:

- chunking semântico de código via Tree-sitter
- Python
- TypeScript / TSX / JavaScript / JSX
- extração de símbolos, imports, exports, callers e callees
- fallback controlado para `line_window`
- rollout operacional e testes

Fora de escopo:

- migrar `markdown`, `config` ou `sql` para Tree-sitter
- adicionar suporte semântico completo a Go, Rust ou Java na primeira entrega
- mudar contratos do MCP
- mudar estrutura do payload além do necessário para rollout e observabilidade

## Mudanças de Interface e Contrato

Mudanças explícitas:

1. adicionar dependências do indexer para Tree-sitter e grammars oficiais das linguagens da primeira entrega em [requirements.txt](/home/junior/apps/jm/code-compass/apps/indexer/requirements.txt)
2. adicionar `CODE_CHUNK_PARSER_BACKEND=tree_sitter|legacy` em [config.py](/home/junior/apps/jm/code-compass/apps/indexer/indexer/config.py), com default `tree_sitter`
3. subir `CHUNK_SCHEMA_VERSION` de `v5` para `v6` em [chunk_models.py](/home/junior/apps/jm/code-compass/apps/indexer/indexer/chunk_models.py)
4. documentar rebuild completo obrigatório no rollout

Mudanças que não serão feitas:

1. não mudar nomes atuais de `chunkStrategy` para linguagens já suportadas
2. não mudar nomes de campos de payload já persistidos no Qdrant
3. não mudar o contrato do comando `indexer chunk` além de warnings adicionais de fallback quando aplicável

Defaults escolhidos:

1. `python` continua emitindo `chunkStrategy=python_symbol`
2. `typescript/js` continuam emitindo `chunkStrategy=ts_symbol`
3. linguagens sem adapter Tree-sitter continuam no comportamento atual e, se não houver parser dedicado, caem em `line_window`
4. `CODE_CHUNK_PARSER_BACKEND=legacy` existe apenas como escape hatch operacional temporário para rollback

## Arquitetura Proposta

### 1. Camada Tree-sitter interna

Criar um pacote novo em `apps/indexer/indexer/tree_sitter/` com estes módulos:

1. `runtime.py`
   - carrega grammars
   - cria e reutiliza `Parser`
   - centraliza `Language`, `Query`, `QueryCursor`
   - expõe helpers para bytes, ranges e texto de nó

2. `registry.py`
   - mapeia `language` do indexer para adapter Tree-sitter
   - resolve qual adapter usar para `python`, `typescript`, `typescriptreact`, `javascript`, `javascriptreact`

3. `types.py`
   - define um `SyntaxChunkSpec` compartilhado para parsing estrutural
   - mantém o shape necessário para virar `ChunkDocument`

4. `adapters/python.py`
   - faz parse, consulta e montagem dos chunks Python

5. `adapters/typescript.py`
   - faz parse, consulta e montagem dos chunks TS/TSX/JS/JSX

6. `queries/python.scm`
7. `queries/typescript.scm`
8. `queries/tsx.scm`
9. `queries/javascript.scm`
10. `queries/jsx.scm`

Regra arquitetural:

- nenhum módulo fora de `tree_sitter/` importa grammar packages diretamente
- `chunk.py` só enxerga a registry e objetos de saída normalizados

### 2. Estratégia de migração do código atual

Antes da troca:

1. mover a implementação atual de [chunk_python.py](/home/junior/apps/jm/code-compass/apps/indexer/indexer/chunk_python.py) para `chunk_python_legacy.py`
2. mover a implementação atual de [chunk_ts.py](/home/junior/apps/jm/code-compass/apps/indexer/indexer/chunk_ts.py) para `chunk_ts_legacy.py`

Depois:

1. [chunk_python.py](/home/junior/apps/jm/code-compass/apps/indexer/indexer/chunk_python.py) vira wrapper Tree-sitter
2. [chunk_ts.py](/home/junior/apps/jm/code-compass/apps/indexer/indexer/chunk_ts.py) vira wrapper Tree-sitter
3. o backend `legacy` chama os módulos congelados antigos
4. o backend `tree_sitter` chama a nova registry

Isso permite rollout direto com fallback operacional sem deixar o restante do indexer tomar decisões.

## Plano de Implementação

### Fase 1 — Fundação e dependências

Arquivos:

- [requirements.txt](/home/junior/apps/jm/code-compass/apps/indexer/requirements.txt)
- [config.py](/home/junior/apps/jm/code-compass/apps/indexer/indexer/config.py)
- novos módulos em `apps/indexer/indexer/tree_sitter/`

Implementar:

1. dependências Tree-sitter do indexer
2. `load_runtime_config()` passando a ler `CODE_CHUNK_PARSER_BACKEND`
3. `runtime.py` com cache de `Language`, `Parser` e `Query`
4. `registry.py` com resolução por linguagem do indexer
5. utilitários de range:
   - `node.start_point` / `node.end_point` para `startLine` e `endLine`
   - helpers de slice do texto original por byte range
6. política de erro de grammar loading:
   - se backend for `tree_sitter` e grammar não carregar, falhar cedo com erro explícito
   - se backend for `legacy`, não tentar inicializar Tree-sitter

### Fase 2 — Backend Tree-sitter para Python

Arquivos:

- [chunk_python.py](/home/junior/apps/jm/code-compass/apps/indexer/indexer/chunk_python.py)
- `apps/indexer/indexer/tree_sitter/adapters/python.py`
- [chunk_graph.py](/home/junior/apps/jm/code-compass/apps/indexer/indexer/chunk_graph.py)

Implementar:

1. captura de top-level:
   - `function_definition`
   - `decorated_definition`
   - `class_definition`
2. captura de membros de classe:
   - métodos
   - `async def`
   - decorators
3. regras de chunk:
   - função -> chunk
   - método -> chunk
   - classe pequena -> chunk único
   - classe grande -> chunk-resumo + métodos + contextos lexicais não cobertos
4. extração de metadados:
   - `symbolName`
   - `qualifiedSymbolName`
   - `symbolType`
   - `parentSymbol`
   - `signature`
5. grafo:
   - visitar o subtree do símbolo para chamadas
   - incluir decorators no conjunto de `callees`
   - preservar as correções já conquistadas: não promover temporários para símbolo local e não mapear `super.method` para a classe atual
6. regra de fallback:
   - se `root_node.has_error`
   - ou houver nós `missing/error` dentro de um símbolo emitido
   - ou a cobertura estrutural útil do arquivo ficar abaixo de `INDEX_MIN_FILE_COVERAGE`
   - então voltar para `line_window`

### Fase 3 — Backend Tree-sitter para TypeScript / TSX / JS / JSX

Arquivos:

- [chunk_ts.py](/home/junior/apps/jm/code-compass/apps/indexer/indexer/chunk_ts.py)
- `apps/indexer/indexer/tree_sitter/adapters/typescript.py`
- [chunk_graph.py](/home/junior/apps/jm/code-compass/apps/indexer/indexer/chunk_graph.py)

Implementar:

1. captura de símbolos:
   - `class_declaration`
   - `method_definition`
   - `function_declaration`
   - `lexical_declaration` cujo valor seja `arrow_function` ou `function`
   - `export default` nomeado ou anônimo
   - getters e setters
2. regras semânticas:
   - `hook` por nome `use[A-Z]`
   - `component` por PascalCase e retorno JSX
   - `helper` para função/arrow top-level não classificada como hook/component
   - `class` e `method` como hoje
3. casos obrigatórios:
   - overloads: assinatura sem implementação vira `code_context`; implementação vira `code_symbol`
   - decorators de classe e método, inclusive multiline
   - `export default memo(function Name() {})`
   - `export default () => ...`
   - `export default function() {}`
   - `export default class extends Base {}`
4. grafo:
   - extrair chamadas apenas do subtree do símbolo
   - incluir decorators
   - manter proteção contra `new Client().run()` virar símbolo local `run`
   - manter proteção contra `super.load()` virar método da classe atual
5. fallback:
   - mesma regra da Fase 2 com base em erros e cobertura

### Fase 4 — Integração no pipeline

Arquivos:

- [chunk.py](/home/junior/apps/jm/code-compass/apps/indexer/indexer/chunk.py)
- [__main__.py](/home/junior/apps/jm/code-compass/apps/indexer/indexer/__main__.py)

Implementar:

1. `chunk.py` deixa de decidir parsing por módulos específicos e passa a consultar a registry Tree-sitter para linguagens de código
2. `docs/config/sql` continuam com os chunkers atuais
3. o backend é resolvido assim:
   - `tree_sitter`: usa registry para código
   - `legacy`: usa `chunk_python_legacy.py` e `chunk_ts_legacy.py`
4. manter `summaryText`, `contextText`, `contentType`, `collectionContentType`, `callers`, `callees` e `chunkId` com a mesma estrutura atual
5. warnings adicionais:
   - parser backend usado
   - motivo de fallback para `line_window`, quando ocorrer

### Fase 5 — Schema, rollout e documentação

Arquivos:

- [chunk_models.py](/home/junior/apps/jm/code-compass/apps/indexer/indexer/chunk_models.py)
- [README.md](/home/junior/apps/jm/code-compass/apps/indexer/README.md)
- [OPERATIONS.md](/home/junior/apps/jm/code-compass/docs/OPERATIONS.md)
- [ROADMAP.md](/home/junior/apps/jm/code-compass/docs/ROADMAP.md)

Implementar:

1. `CHUNK_SCHEMA_VERSION = "v6"`
2. preflight de legado continua bloqueando mistura de schema
3. documentar:
   - rebuild completo obrigatório
   - novo backend default
   - escape hatch `CODE_CHUNK_PARSER_BACKEND=legacy`
   - smoke de validação do rollout
4. manter `legacy` por um ciclo de estabilização
5. remover `legacy` em follow-up posterior, não neste trabalho

### Fase 6 — Expansão arquitetural pós-primeira entrega

Objetivo:

- deixar o pacote Tree-sitter pronto para novas linguagens sem retrabalho estrutural

Implementar já nesta fase:

1. contrato interno de adapter por linguagem
2. registry preparada para idiomas novos
3. convenção de query files por linguagem

Não implementar agora:

1. chunking semântico de Go
2. chunking semântico de Rust
3. chunking semântico de Java

Essas linguagens entram apenas em roadmap futuro, depois de estabilizar a primeira entrega.

## Estratégia de `chunkId` e Schema

Regras:

1. manter a lógica atual de `make_chunk_id()` baseada em símbolo quando existir
2. não criar novo formato especial de `chunkId` só porque o parser mudou
3. aceitar que a troca de parser muda ranges, cobertura e, em alguns casos, identidade estrutural prática
4. por isso, o rollout exige `chunkSchemaVersion=v6` e rebuild completo obrigatório

## Testes e Cenários Obrigatórios

### Testes unitários

Arquivos:

- [test_chunk_python.py](/home/junior/apps/jm/code-compass/apps/indexer/tests/test_chunk_python.py)
- [test_chunk_ts.py](/home/junior/apps/jm/code-compass/apps/indexer/tests/test_chunk_ts.py)
- [test_chunk.py](/home/junior/apps/jm/code-compass/apps/indexer/tests/test_chunk.py)
- [test_config.py](/home/junior/apps/jm/code-compass/apps/indexer/tests/test_config.py)

Cobertura mínima:

1. Python:
   - função simples
   - `async def`
   - classe pequena
   - classe grande
   - decorators
   - comentários e contexto lexical não coberto
   - fallback em arquivo inválido
2. TS/TSX/JS:
   - helper
   - hook
   - component
   - classe grande
   - overloads
   - default export nomeado
   - default export anônimo
   - wrappers `memo` e `forwardRef`
   - decorators multiline
   - getters e setters
   - fallback em arquivo inválido
3. grafo:
   - `self/this.method`
   - temporário `get_client().load()` não promovido
   - `new Client().run()` não promovido
   - `super.load()` não promovido
4. runtime Tree-sitter:
   - grammar load
   - parser cache
   - query compilation

### Testes de integração

Arquivos:

- [test_cli.py](/home/junior/apps/jm/code-compass/apps/indexer/tests/test_cli.py)
- smoke de indexação/search já existente

Cobertura mínima:

1. `indexer chunk` para Python e TSX usando backend default `tree_sitter`
2. `indexer chunk` com `CODE_CHUNK_PARSER_BACKEND=legacy`
3. `indexer index` com rebuild limpo em collection temporária
4. `indexer search` retornando payload coerente após indexação Tree-sitter

### Critérios de aceitação

1. nenhum campo público de payload atual é removido
2. `python_symbol` e `ts_symbol` continuam sendo emitidos
3. `summaryText` e `contextText` continuam preenchidos
4. `callers` e `callees` continuam presentes e sem reabrir regressões já corrigidas
5. `indexer chunk`, `indexer index` e `indexer search` continuam funcionando ponta a ponta
6. `legacy` funciona como rollback emergencial
7. rollout `v6` bloqueia mistura com schemas antigos

## Rollout, Validação e Rollback

Rollout:

1. publicar dependências novas
2. subir `CHUNK_SCHEMA_VERSION` para `v6`
3. recriar ou limpar collections antigas
4. rodar `index` completo
5. validar `search` em repo de smoke e repo real pequeno

Validação operacional:

1. `make health`
2. smoke `index -> search`
3. checagem de `chunk_strategy`, `chunk_content_type`, `symbol_name`, `callers`, `callees`
4. checagem de taxa de fallback para `line_window`

Rollback:

1. se houver regressão funcional imediata, usar `CODE_CHUNK_PARSER_BACKEND=legacy`
2. manter essa rota apenas durante o ciclo de estabilização
3. não reutilizar points `v6` como se fossem equivalentes aos de `v5`; o rollback operacional exige rebuild compatível com o backend selecionado

## Assunções e Defaults

1. o plano usa a API oficial do `py-tree-sitter`, validada via Context7
2. a primeira entrega Tree-sitter cobre só linguagens de código já existentes no repositório atual
3. `markdown`, `config` e `sql` não entram nessa migração
4. a troca do parser é considerada mudança estrutural suficiente para exigir `v6`
5. o backend `legacy` é temporário e existe só para estabilização operacional
6. o objetivo não é “suportar todas as linguagens já”, e sim criar a fundação multi-linguagem correta sem reabrir a fragilidade atual

## Arquivos-Alvo

1. [apps/indexer/requirements.txt](/home/junior/apps/jm/code-compass/apps/indexer/requirements.txt)
2. [apps/indexer/indexer/config.py](/home/junior/apps/jm/code-compass/apps/indexer/indexer/config.py)
3. [apps/indexer/indexer/chunk.py](/home/junior/apps/jm/code-compass/apps/indexer/indexer/chunk.py)
4. [apps/indexer/indexer/chunk_python.py](/home/junior/apps/jm/code-compass/apps/indexer/indexer/chunk_python.py)
5. [apps/indexer/indexer/chunk_ts.py](/home/junior/apps/jm/code-compass/apps/indexer/indexer/chunk_ts.py)
6. [apps/indexer/indexer/chunk_graph.py](/home/junior/apps/jm/code-compass/apps/indexer/indexer/chunk_graph.py)
7. [apps/indexer/indexer/chunk_models.py](/home/junior/apps/jm/code-compass/apps/indexer/indexer/chunk_models.py)
8. [apps/indexer/indexer/__main__.py](/home/junior/apps/jm/code-compass/apps/indexer/indexer/__main__.py)
9. `apps/indexer/indexer/tree_sitter/`
10. [apps/indexer/tests/test_chunk_python.py](/home/junior/apps/jm/code-compass/apps/indexer/tests/test_chunk_python.py)
11. [apps/indexer/tests/test_chunk_ts.py](/home/junior/apps/jm/code-compass/apps/indexer/tests/test_chunk_ts.py)
12. [apps/indexer/tests/test_chunk.py](/home/junior/apps/jm/code-compass/apps/indexer/tests/test_chunk.py)
13. [apps/indexer/tests/test_cli.py](/home/junior/apps/jm/code-compass/apps/indexer/tests/test_cli.py)
14. [apps/indexer/tests/test_config.py](/home/junior/apps/jm/code-compass/apps/indexer/tests/test_config.py)
15. [apps/indexer/README.md](/home/junior/apps/jm/code-compass/apps/indexer/README.md)
16. [docs/OPERATIONS.md](/home/junior/apps/jm/code-compass/docs/OPERATIONS.md)
17. [docs/tree-sitter/plan.md](/home/junior/apps/jm/code-compass/docs/tree-sitter/plan.md)
