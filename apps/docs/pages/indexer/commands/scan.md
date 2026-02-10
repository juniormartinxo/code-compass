
# Code Compass Indexer - Scan Command

O comando `scan` é responsável por varrer recursivamente um diretório (repositório) e listar todos os arquivos de código válidos para indexação, respeitando regras de inclusão e exclusão.

## Visão Geral

O scanner percorre a árvore de diretórios a partir do `repo-root` e retorna uma lista de caminhos de arquivos relativos. Ele aplica filtros para:
- Ignorar diretórios configurados (ex: `.git`, `node_modules`).
- Filtrar por extensões de arquivo permitidas (ex: `.ts`, `.py`).
- Detectar e ignorar arquivos binários.
- Limitar o número máximo de arquivos retornados (opcional).

## Uso Básico

```bash
python -m indexer scan [opções]
```

### Opções Configuráveis

| Opção | Variável de Ambiente | Default | Descrição |
|-------|----------------------|---------|-----------|
| `--repo-root` | `REPO_ROOT` | `cwd` | Diretório raiz a ser escaneado. |
| `--ignore-dirs` | `SCAN_IGNORE_DIRS` | `.git,node_modules,...` | Lista de diretórios a serem ignorados (separados por vírgula). |
| `--allow-exts` | `SCAN_ALLOW_EXTS` | `.ts,.py,.js,...` | Lista de extensões de arquivo a serem incluídas (separadas por vírgula). |
| `--max-files` | - | `None` | Limita o número máximo de arquivos retornados na lista. |

### Valores Padrão

Caso não sejam fornecidos argumentos ou variáveis de ambiente, os seguintes valores padrão (definidos em `config.py`) são utilizados:

**Diretórios Ignorados (`DEFAULT_IGNORE_DIRS`):**
- `.git`, `node_modules`, `dist`, `build`, `.next`, `.qdrant_storage`, `coverage`

**Extensões Permitidas (`DEFAULT_ALLOW_EXTS`):**
- `.ts`, `.tsx`, `.js`, `.jsx`, `.py`, `.md`, `.json`, `.yaml`, `.yml`

## Exemplo de Saída (JSON)

Ao executar o comando:
```bash
python -m indexer scan --repo-root ./meu-projeto --allow-exts .py,.ts
```

A saída será um JSON contendo a lista de arquivos e estatísticas da varredura:

```json
{
  "repoRoot": "/abs/path/to/meu-projeto",
  "ignoreDirs": [".git", "node_modules", "dist", ...],
  "allowExts": [".py", ".ts"],
  "stats": {
    "total_files_seen": 150,
    "total_dirs_seen": 20,
    "files_kept": 45,
    "files_ignored_ext": 100,
    "files_ignored_binary": 5,
    "dirs_ignored": 2,
    "elapsed_ms": 12
  },
  "files": [
    "src/main.py",
    "src/utils/helper.ts",
    "tests/test_main.py"
  ]
}
```

## Detalhes de Implementação

- **Detecção de Binários:** O scanner lê os primeiros 4096 bytes de cada arquivo. Se encontrar um byte nulo (`\x00`), o arquivo é considerado binário e ignorado.
- **Performance:** O scan utiliza `os.scandir` para maior eficiência em diretórios grandes.
- **Symlinks:** O scanner **não** segue links simbólicos (`follow_symlinks=False`) para evitar loops infinitos ou indexação duplicada.

## Comportamento de Erro

- Se o `--repo-root` fornecido não existir ou não for um diretório, o comando retorna exit code `1` e imprime uma mensagem de erro no `stderr`.
