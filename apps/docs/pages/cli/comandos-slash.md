# Comandos Slash: Histórico e Extensão

Este documento consolida:

- histórico das mudanças recentes no fluxo de slash commands (ACP + Toad + CLI);
- passo a passo para adicionar novos comandos com segurança.

## Resumo das alterações implementadas

### 1) Publicação de comandos ACP no menu fuzzy do Toad

Antes, o agente tratava `/repo`, `/config`, `/model` e `/grounded`, mas eles não apareciam no palette do Toad.

Foi implementado anúncio via `available_commands_update` no `new_session` do ACP Agent.

Arquivos:

- `apps/acp/src/code_compass_acp/agent.py`
- `apps/acp/tests/test_smoke_loopback.py`

### 2) Descrições dos comandos em português

As descrições dos comandos anunciados pelo ACP foram traduzidas para português para melhor UX no menu `/`.

Arquivo:

- `apps/acp/src/code_compass_acp/agent.py`

### 3) Formatação do `/config` em bloco JSON

O retorno de `/config` passou a usar bloco Markdown com ` ```json ` para evitar saída “achatada” no render do Toad.

Arquivo:

- `apps/acp/src/code_compass_acp/agent.py`

Teste ajustado para extrair JSON de bloco:

- `apps/acp/tests/test_smoke_loopback.py`

### 4) Aliases locais `/clear` e `/close` no chat

Além dos comandos nativos do Toad (`/toad:clear`, `/toad:session-close`), o launcher do CLI agora injeta aliases:

- `/clear` → `/toad:clear`
- `/close` → `/toad:session-close`

Arquivos:

- `apps/cli/src/code_compass_cli/toad_patched.py`
- `apps/cli/src/code_compass_cli/app.py`

### 5) Correção de erro ao fechar sessão

Foi corrigido o crash de fechamento de sessão (store com `project_dir=None`) garantindo que `code-compass chat` sempre passe `PATH` para `toad acp`.

- default: `cwd`
- override: `TOAD_PROJECT_DIR`

Arquivo:

- `apps/cli/src/code_compass_cli/app.py`

### 6) Documentação atualizada

Os guias abaixo foram alinhados ao comportamento atual:

- `apps/docs/pages/cli/toad-chat-acp.md`
- `apps/docs/pages/cli/ask-cli.md`
- `apps/docs/pages/acp-agent.md`
- `apps/acp/README.md`

### 7) Comando de sessão para `contentType`

Foi adicionado comando de runtime para `contentType` no ACP:

- `/content-type <code|docs|all|reset>`
- `/contentType` (alias aceito)

Com isso, o valor de `contentType` pode ser alterado por sessão sem reiniciar o chat.

## Como adicionar novos comandos

Existem dois tipos de comando no fluxo atual:

- comando ACP (executado pelo `code-compass-acp`);
- alias local do Toad (executado no cliente, sem passar pelo ACP).

## Fluxo A: adicionar comando ACP (ex.: `/foo`)

### Passo 1: anunciar no handshake ACP

No `apps/acp/src/code_compass_acp/agent.py`, adicione entrada em `AVAILABLE_SLASH_COMMANDS`.

Regras:

- `name` sem `/` (ex.: `foo`);
- `description` clara e curta;
- `input.hint` opcional para argumentos.

Exemplo:

```python
{
    "name": "foo",
    "description": "Executa ação foo na sessão atual.",
    "input": {"hint": "<arg1|arg2>"},
}
```

### Passo 2: implementar handler

Crie função no mesmo arquivo:

```python
async def _handle_foo_command(
    conn: acp.Client | None,
    session_id: str,
    state: SessionState,
    question: str,
) -> acp.PromptResponse | None:
    ...
```

Padrão recomendado:

- retorne `None` se não for comando `/foo`;
- para comando válido, envie mensagem com `conn.session_update(...)`;
- finalize com `acp.PromptResponse(stop_reason="end_turn")`.

### Passo 3: registrar no pipeline de `prompt`

No método `prompt(...)`, chame o handler antes do `ask_code`.

Ordem importa:

- comandos administrativos primeiro;
- consulta ao MCP por último.

Exemplo real no projeto:

- `_handle_content_type_command(...)`

### Passo 4: validar via testes

Atualize `apps/acp/tests/test_smoke_loopback.py` com:

- cenário feliz (`/foo` válido);
- cenário inválido (argumento ausente/inválido, se aplicável);
- impacto em `/config` (se houver novo estado de sessão).

### Passo 5: atualizar docs

Atualize no mínimo:

- `apps/docs/pages/acp-agent.md`
- `apps/docs/pages/cli/toad-chat-acp.md`
- este documento (`apps/docs/pages/cli/comandos-slash.md`)

## Fluxo B: adicionar alias local do Toad (ex.: `/bar`)

Use este fluxo quando o comando já existe no Toad e você quer nome curto.

### Passo 1: adicionar no menu fuzzy

Arquivo:

- `apps/cli/src/code_compass_cli/toad_patched.py`

No `patched_build(...)`, inclua:

```python
SlashCommand("/bar", "Descrição do alias")
```

### Passo 2: mapear no dispatcher local

No `patched_slash_command(...)`, converta para comando nativo:

```python
if command == "bar":
    return await original_slash_command(self, "/toad:algum-comando")
```

### Passo 3: validar inicialização

Confirme que o `chat` usa o launcher patchado:

- `apps/cli/src/code_compass_cli/app.py` deve montar `python -m code_compass_cli.toad_patched`.

## Checklist de PR para comandos

- comando aparece no fuzzy (`/`);
- comando executa sem quebrar fluxo da sessão;
- mensagens de erro são claras para entrada inválida;
- testes relevantes passam;
- docs atualizadas.

## Referências de código

- ACP Agent: `apps/acp/src/code_compass_acp/agent.py`
- Testes ACP: `apps/acp/tests/test_smoke_loopback.py`
- Launcher patchado do Toad: `apps/cli/src/code_compass_cli/toad_patched.py`
- Entrada do chat CLI: `apps/cli/src/code_compass_cli/app.py`
