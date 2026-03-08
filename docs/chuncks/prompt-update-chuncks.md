# Prompt para atualização de chunks

Você é um engenheiro de software sênior, pragmático, cuidadoso com regressões e orientado a entrega. Sua tarefa é IMPLEMENTAR o plano abaixo no repositório atual, com mudanças pequenas, seguras e testáveis.

## OBJETIVO

Aplicar correções de robustez e manutenção com foco em:

- evitar armadilhas de refatoração
- impedir poluição do índice de RAG
- remover deprecações e ruído técnico
- corrigir riscos operacionais simples
- preservar legibilidade onde abstração ainda não se paga

## IMPORTANTE

- Não invente escopo novo.
- Não refatore partes não relacionadas.
- Não faça abstrações “bonitas” sem necessidade.
- Preserve comportamento existente, exceto onde o plano explicitamente pede correção.
- Antes de alterar comportamento em `ask-code.tool.ts`, determine se a mudança de “conciso” para “detalhado e estruturado” foi intencional a partir do código e do contexto disponível.
- Faça mudanças incrementais e mantenha os testes passando.
- Ao final, mostre:
  1. resumo curto do que foi alterado
  2. arquivos modificados
  3. testes adicionados/ajustados
  4. limitações ou pontos adiados conscientemente

## ORDEM OBRIGATÓRIA DE EXECUÇÃO

### ETAPA 1

1. Blindar a invariável em `_split_long_paragraph`
2. Filtrar chunks compostos apenas por whitespace em `_split_paragraphs`
3. Corrigir `Pattern` deprecated e limpar imports não usados

### ETAPA 2

1. Tornar `make chat` robusto quando `dist` não existir
2. Adicionar/ajustar testes automatizados dessas correções

### ETAPA 3

1. Revisar a duplicação/comportamento em `ask-code.tool.ts`
   - primeiro determinar se a mudança comportamental foi intencional
   - só depois refatorar a duplicação, se fizer sentido

### ETAPA 4

1. NÃO implementar factory para builders de preferência agora
   - apenas registrar no resultado final como item conscientemente adiado

## DETALHAMENTO DAS MUDANÇAS

1) `_split_long_paragraph`
    Problema:

    - a lógica atual não quebra em produção por causa de guards prévios, mas a ordem das condições é frágil e pode quebrar em refactor futuro.

    Ação:

    - manter a lógica principal
    - adicionar assert defensivo para documentar a invariável de tamanho
    - preferir algo como `assert len(current) <= max_size` em ponto apropriado
    - adicionar teste cobrindo essa invariável

2) `_split_paragraphs`
    Problema:

    - chunks com apenas whitespace podem entrar no pipeline de embedding e poluir o índice

    Ação:

    - aplicar filtro explícito para descartar parágrafos vazios ou só com whitespace antes do retorno
    - implementar algo equivalente a:
    `paragraphs = [p for p in raw_paragraphs if p.strip()]`
    - adicionar teste cobrindo esse comportamento

3) `Pattern` deprecated + imports não usados
    Problema:
    - uso antigo de `Pattern` e imports sem uso geram warning/ruído

    Ação:
    - trocar para `re.Pattern[str]` onde aplicável
    - remover imports não usados
    - manter compatibilidade com a versão de Python do projeto

4) `make chat`
    Problema:
    - o alvo pode depender implicitamente de `dist` existente

    Ação:
   - adicionar verificação simples para garantir robustez
   - evitar dependência circular no Makefile
   - o `MCP_SERVER_DIR` já está definido no Makefile; usar `$(MCP_SERVER_DIR)/dist` na verificação
   - preferir solução simples do tipo:
     `test -d $(MCP_SERVER_DIR)/dist || <comando de build apropriado>`
   - ajustar o comando de build conforme a estrutura real do repositório, sem hardcode de path fora do que o Makefile já define

5) Testes
    Adicionar ou ajustar testes para cobrir no mínimo:
    - invariável de `_split_long_paragraph`
    - descarte de whitespace-only chunks em `_split_paragraphs`
    - uso de `re.Pattern[str]` sem quebrar o módulo
    - robustez de `make chat` ou da lógica equivalente testável
    - comportamento/instrução de `ask-code.tool.ts`, se houver teste adequado para isso

6) `ask-code.tool.ts`
    Problema:
    - há duplicação de instrução e possível mudança silenciosa de comportamento

    Ação:
    - inspecionar o código e determinar se a diferença entre “conciso” e “detalhado e estruturado” parece intencional
    - investigar usando o contexto disponível no repositório, incluindo comentários, nomes, uso no arquivo e, se disponível localmente, histórico relevante
    - se for intencional:
    - manter comportamento
    - extrair para constante compartilhada se isso realmente reduzir duplicação sem esconder a intenção
    - adicionar comentário curto explicando a escolha
    - se não for possível determinar com segurança:
    - preservar o comportamento atual (`detalhado e estruturado`)
    - não introduzir mudança comportamental arbitrária
    - adicionar comentário curto no código com a ideia:
        `Intenção comportamental não confirmada — preservado como encontrado`
    - só reduzir duplicação se isso não mudar o resultado final
    - evitar refactor cosmético sem segurança

7) Factory para builders
    Decisão:
    - não implementar agora
    - manter builders explícitos por legibilidade enquanto testes/golden set ainda estão estabilizando

    EXPECTATIVA DE ESTILO
    - mudanças pequenas
    - comentários curtos e úteis
    - testes claros
    - sem abstração prematura
    - sem “cleanup geral” fora do escopo

    ENTREGA FINAL
    Depois de implementar:
    - mostre resumo curto
    - liste arquivos alterados
    - liste testes adicionados/ajustados
    - diga explicitamente que a factory para builders foi adiada de propósito
