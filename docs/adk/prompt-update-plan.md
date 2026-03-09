# PROMPT UPDATE PLAN

Você é um arquiteto de software sênior, pragmático, crítico e orientado a entrega. Sua tarefa é ATUALIZAR o plano abaixo incorporando melhorias arquiteturais e operacionais relacionadas ao uso do Google ADK, memória local/cloud e governança da memória.

## OBJETIVO

Reescrever o plano de forma mais robusta, preservando a estrutura geral e a proposta central, mas incorporando explicitamente as melhorias listadas em "NOVAS EXIGÊNCIAS". Não invente escopo novo fora do que foi pedido. Não remova partes importantes já existentes. Você deve produzir uma NOVA VERSÃO CONSOLIDADA DO PLANO.

## IMPORTANTE

- Mantenha o plano em português do Brasil.
- Mantenha o estilo técnico, direto e sem floreios.
- Preserve a ideia central:
  - ADK como framework obrigatório de orquestração.
  - `local` com SQLite como source of truth da memória longa.
  - Qdrant mantido para busca técnica e opcional para índice semântico da memória local.
  - `cloud` com Vertex Session + Memory Bank.
  - contratos ACP/CLI preservados.
- Não transforme o sistema em "framework-driven". O núcleo continua sendo retrieval técnico de codebase; o ADK é uma camada de runtime/orquestração/memória.
- Onde fizer sentido, atualize:
  - Resumo
  - Contratos públicos e interfaces
  - Arquitetura alvo
  - Implementação arquivo a arquivo
  - Testes e cenários de aceitação
  - Rollout e rollback
  - Assunções e defaults
- Inclua novas seções se necessário, desde que façam sentido arquiteturalmente.
- Seja específico com nomes de campos, regras e arquivos.
- Não use linguagem vaga tipo "considerar futuramente"; defina o que deve ser feito agora e o que pode entrar como extensão posterior.
- Quando precisar definir thresholds, limites ou defaults numéricos, trate-os como valores iniciais configuráveis e calibráveis por teste, não como constantes universais imutáveis.
- Onde houver campo derivado de runtime, deixe explícito se ele é persistido ou calculado no momento do retrieval.

## TAREFA

Pegue o plano fornecido ao final deste prompt e gere uma nova versão consolidada já incorporando as exigências abaixo.

## NOVAS EXIGÊNCIAS

### 1) ADK COM GUARDRAILS DE ARQUITETURA

Incorporar explicitamente que:

- O ADK deve ficar restrito à camada de runtime/orquestração/memória.
- O núcleo do Code Compass continua sendo retrieval técnico da codebase.
- A implementação deve evitar acoplamento espalhado ao ADK.
- `agent.py` deve atuar como fachada/camada de compatibilidade, enquanto a lógica principal fica em módulos dedicados como runtime, builder, memory services e tools.
- A substituição do motor deve ser descrita como adaptação controlada, e não como "substituição direta cega".

### 2) SESSÃO LOCAL PERSISTENTE

Ajustar o plano para deixar claro que, no modo `local`, o histórico imediato/sessão não deve ficar apenas in-memory por padrão.

- Preferir persistência local em SQLite também para sessões, quando viável.
- Justificar isso por previsibilidade, debug, reinício de processo e testes.
- Se o plano mencionar fallback para in-memory, deixar isso como opção secundária, não como default principal.

### 3) ISOLAMENTO E IDENTIDADE

Enriquecer a parte de identidade multiusuário:

- Manter `set_config_option` com `user.id`, `user.tenant`, `memory.long_term.enabled`.
- Adicionar suporte explícito a `memory.scope.mode = session|user`.
- Reforçar que em ambiente cloud/internet a identidade autenticada por sessão é obrigatória para memória longa.
- Manter o cálculo de `memory_user_id` com hash (`sha256(tenant + ":" + user.id)`), mas explicitar também a necessidade de isolamento por aplicação/ambiente via `app_name`, namespace explícito ou equivalente para evitar vazamento de memória entre apps ou ambientes.
- Adicionar cenário de teste cobrindo mesmo `user.id` em tenants diferentes sem vazamento cruzado.

### 4) MEMORY DECAY / ENVELHECIMENTO DA MEMÓRIA

Adicionar ao plano uma estratégia explícita de envelhecimento da memória:

- Incluir os campos `last_confirmed_at` e `times_reinforced` no schema.
- Não sobrescrever o `confidence` bruto original.
- Calcular `effective_confidence` no momento do retrieval, como valor derivado.
- Penalizar memórias antigas no momento da recuperação, sem apagar automaticamente.
- Aplicar decay por categoria/tipo (`kind`), seguindo estas regras:
  - preferências e opiniões técnicas: decay forte.
  - convenções e decisões recorrentes: decay moderado.
  - fatos mais estáveis: decay fraco.
- Incorporar o `effective_confidence` como fator de ranking no retrieval local e documentar o comportamento esperado equivalente no cloud.
- Se houver persistência de score auxiliar, deixar claro que ele não substitui o `confidence` original nem o cálculo final em runtime.

### 5) RESOLUÇÃO DE CONFLITO DE MEMÓRIA

Adicionar estratégia explícita para contradições e sobreposição semântica:

- Não basta dedupe por hash.
- Usar thresholds iniciais configuráveis de similaridade semântica para classificar a relação entre entradas do mesmo `user_id + kind + topic`.
- Sugerir defaults iniciais como referência, por exemplo:
  - similaridade muito alta: classificar como reforço ou contradição, dependendo do conteúdo/polaridade.
  - similaridade intermediária: classificar como complemento.
  - similaridade baixa: nova entrada independente.
- Deixar explícito que esses valores devem ser calibrados com testes reais do projeto e não tratados como constantes absolutas.
- Se for reforço: atualizar `last_confirmed_at` e `times_reinforced`.
- Se for complemento: manter ambas com contexto/escopo adequado, sem desativar nenhuma.
- Se for contradição forte: a nova entrada passa a ser ativa, a anterior recebe `active=false` e o campo `supersedes_entry_id` aponta para a entrada substituída.
- Incluir o campo `supersedes_entry_id` no schema do `memory_entries`.
- Exigir distinção explícita entre:
  - reforço
  - complemento
  - contradição
- Não permitir regra simplista do tipo "similaridade alta => substitui" sem avaliação de conteúdo/intenção.

### 6) GOVERNANÇA, TRANSPARÊNCIA E CONTROLE DA MEMÓRIA

Adicionar suporte a slash command `/memory` com transparência para o usuário.
O plano deve incluir os seguintes comandos obrigatórios:

- `/memory list` → mostrar memórias registradas do usuário atual.
- `/memory forget <termo>` → desativar memórias relacionadas ao termo.
- `/memory clear` → desativar toda a memória longa do usuário.
- `/memory enable` → habilitar gravação de memória longa.
- `/memory disable` → desabilitar gravação de memória longa.
E os seguintes comandos desejáveis:
- `/memory why <id|termo>` → explicar por que determinada memória foi registrada, exibindo no mínimo `source_session_id`, status (`active`, `superseded`, `disabled`) e timestamps relevantes.
- `/memory confirm <id>` → reforçar memória explicitamente, atualizando `last_confirmed_at` e `times_reinforced`.
Esses comandos devem aparecer:
- na seção de contratos públicos/interfaces.
- na implementação (arquivo responsável e comportamento esperado).
- nos testes/cenários de aceitação.
Justificar no plano que esses comandos são essenciais para confiança do usuário, depuração e correção manual de erros da memória.

### 7) EXTRAÇÃO E QUALIDADE DA MEMÓRIA

Refinar a estratégia de `memory_extractor.py`:

- Deixar explícito que ele extrai apenas fatos/preferências técnicas de longo prazo.
- Deixar explícito o que NÃO deve virar memória longa:
  - contexto efêmero do ticket atual.
  - conteúdo facilmente recuperável da codebase.
  - detalhes transitórios da conversa.
- Aplicar threshold mínimo de confiança para gravação, com default inicial sugerido `confidence >= 0.7`, configurável.
- Aplicar dedupe semântico com a classificação de conflito definida na exigência 5.
- Diferenciar claramente sessão/contexto imediato de memória longa do usuário.
- No modo cloud, adotar abordagem híbrida explícita:
  - o extractor grava memórias explícitas por SDK/API como caminho prioritário.
  - sessões concluídas podem ser submetidas ao Memory Bank para extração complementar.
  - regra de precedência: extração explícita tem prioridade sobre derivação automática de sessão.
  - incluir mecanismo de reconciliação/deduplicação para evitar duplicação entre memória explícita e memória derivada automaticamente.
  - documentar essa regra no código e na documentação.

### 8) RETRIEVAL DA MEMÓRIA LOCAL

Detalhar melhor a recuperação da memória local:

- SQLite continua sendo source of truth.
- Qdrant, quando habilitado, serve apenas para shortlist semântico de candidatos.
- Após shortlist semântico, sempre realizar hydrate, validação e filtragem final no SQLite.
- O score final de ranking deve considerar, nesta ordem de fatores:
  1. `active = true`
  2. isolamento por `user_id` + `tenant_id` + `app_name`
  3. `effective_confidence` calculado em runtime com decay
  4. similaridade semântica, quando Qdrant habilitado
  5. recência (`last_confirmed_at` > `updated_at` > `created_at`)
- Quando Qdrant estiver desabilitado, o retrieval deve continuar funcional via consulta estruturada no SQLite usando os mesmos fatores de ranking, exceto similaridade semântica.

### 9) LIMITE DE CONTEXTO DO PreloadMemoryTool

Definir explicitamente no builder e na documentação:

- O `PreloadMemoryTool` deve carregar por padrão no máximo 20 entradas de memória por sessão.
- O total de tokens injetados no contexto pela memória não deve ultrapassar por padrão 1.500 tokens.
- Esses limites devem ser configuráveis, mas com defaults seguros documentados.
- A seleção das entradas deve priorizar as de maior `effective_confidence` e maior recência.
- Entradas acima desse limite são descartadas do contexto da sessão, mas permanecem no SQLite.
- Justificar esse limite como proteção contra degradação de qualidade do contexto em sessões longas ou usuários com histórico extenso.

### 10)  TESTES ADICIONAIS OBRIGATÓRIOS

Expandir a seção de testes para incluir explicitamente:

- decay afetando ranking de memórias antigas vs recentes.
- reforço de memória atualizando `last_confirmed_at` e `times_reinforced`.
- contradição desativando memória anterior e preenchendo `supersedes_entry_id`.
- complemento mantendo ambas as entradas ativas.
- `/memory list`, `/memory forget`, `/memory clear`, `/memory enable`, `/memory disable`.
- isolamento entre tenants com mesmo `user.id` sem vazamento cruzado.
- ausência de memória longa quando `memory.long_term.enabled=false`.
- ausência de gravação de memória longa sem identidade autenticada válida no cloud.
- retomada após reinício do processo no modo local usando SQLite para sessão + memória.
- `PreloadMemoryTool` respeitando limite padrão de 20 entradas e 1.500 tokens.
- reconciliação correta entre memória explícita e memória derivada automaticamente no modo cloud.

### 11)  ESTRUTURA ESPERADA DA RESPOSTA

A sua saída deve ser apenas o plano atualizado, completo e consolidado.
Não explique o que você fez.
Não faça prefácio.
Não escreva "segue a versão".
Não use markdown de citação.
Entregue o texto final já pronto para uso.

PLANO BASE A SER ATUALIZADO: docs/adk/plan.md

## Referências

1. [Memory - Agent Development Kit (ADK)](https://google.github.io/adk-docs/sessions/memory/?utm_source=chatgpt.com)
2. [Manage sessions with Agent Development Kit | Vertex AI](https://docs.cloud.google.com/agent-builder/agent-engine/sessions/manage-sessions-adk?utm_source=chatgpt.com)
3. [ADK CLI 1.26.0 documentation](https://google.github.io/adk-docs/api-reference/cli/?utm_source=chatgpt.com)
4. [Quickstart with Vertex AI Agent Engine SDK](https://docs.cloud.google.com/agent-builder/agent-engine/memory-bank/quickstart-api?utm_source=chatgpt.com)
5. [Agent Development Kit documentation](https://google.github.io/adk-docs/api-reference/python/?utm_source=chatgpt.com)
6. [Vertex AI Agent Engine Memory Bank overview](https://docs.cloud.google.com/agent-builder/agent-engine/memory-bank/overview?utm_source=chatgpt.com)
7. [Vertex AI Agent Engine Sessions overview](https://docs.cloud.google.com/agent-builder/agent-engine/sessions/overview?utm_source=chatgpt.com)
