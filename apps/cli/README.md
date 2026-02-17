# Code Compass CLI (Python)

CLI em Python com Typer + Rich integrada ao Toad via ACP.

## Requisitos

- Python 3.14+
- `toad` e `acp` (via dependência `batrachian-toad`)

## Instalação (modo dev)

```bash
cd apps/cli
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Uso

```bash
code-compass ask "onde fica o handler do search_code?" --repo code-compass
```
