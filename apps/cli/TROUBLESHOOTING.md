# Troubleshooting

## Permission Denied on `python -m toad serve`

**Issue:**
When running `python -m toad serve`, the command fails with a `Permission denied` error referencing `site-packages/toad/__main__.py`.

**Cause:**
The `toad` package attempts to execute `sys.argv[0]` directly using `shlex`. When running via `python -m toad`, `sys.argv[0]` points to the `__main__.py` file, which is not executable by default on Linux systems.

**Solution (Hotfix applied):**
A patch was applied directly to the installed package in `.venv/lib/python3.14/site-packages/toad/cli.py`. The fix detects if the executed command ends with `.py` and prepends the current Python interpreter (`sys.executable`) to the command string, ensuring it is executed properly.

**Patch Details:**

Location: `.venv/lib/python3.14/site-packages/toad/cli.py`

```python
def serve(port: int, host: str, public_url: str | None = None) -> None:
    """Serve Toad as a web application."""
    from textual_serve.server import Server
    import shlex  # <--- Added import

    command = sys.argv[0]
    
    # <--- Patch Start --->
    if command.endswith(".py"):
        command = shlex.join([sys.executable, command])
    # <--- Patch End --->

    server = Server(command, host=host, port=port, title="Toad", public_url=public_url)
    set_process_title("toad serve")
    server.serve()
```

This ensures that `python -m toad serve` works correctly without needing to rely on the `toad` binary being in the PATH or executable permissions on package files.

## Mensagem `Falha ao consultar o MCP`

**Issue:**
No `ask`/`chat`, a CLI mostra erro parecido com:
`Falha ao consultar o MCP. Detalhe técnico: Falha ao gerar embedding via Ollama (...)`

**Cause:**
O agente ACP conseguiu iniciar, mas a tool `ask_code` falhou no backend MCP.
O caso mais comum é endpoint de embedding indisponível (ex.: `EMBEDDING_PROVIDER_CODE_API_URL=http://localhost:11434` fora do ar).

**Checks rápidos:**

```bash
make health
curl -sS http://localhost:11434/api/tags
```

Se o segundo comando falhar, inicie/configure o provider e o modelo de embedding esperado
(`EMBEDDING_MODEL_CODE` e `EMBEDDING_MODEL_DOCS`, padrão `manutic/nomic-embed-code` e `bge-m3`, respectivamente).
