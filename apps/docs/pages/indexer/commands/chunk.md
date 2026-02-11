
# Code Compass Indexer - Chunk Command

O comando `chunk` é responsável por dividir um arquivo de código em pedaços menores (chunks) para processamento e indexação vetorial.

## Visão Geral

O indexer processa arquivos individuais e retorna uma estrutura JSON contendo os metadados do arquivo e seus respectivos chunks. Ele suporta:
- Definição customizada do tamanho do chunk e overlap.
- Detecção automática de linguagem baseada na extensão.
- Cálculo de hash SHA256 para controle de duplicidade.
- Normalização de caminhos relativos ao `repo-root`.

## Uso Básico

```bash
python -m indexer chunk --file <caminho_do_arquivo> [opções]
```

### Argumentos Obrigatórios

| Argumento | Descrição |
|-----------|-----------|
| `--file` | Caminho absoluto ou relativo do arquivo a ser processado. |

### Opções Configuráveis

| Opção | Default | Descrição |
|-------|---------|-----------|
| `--chunk-lines` | 120 | Número máximo de linhas por chunk. |
| `--overlap-lines` | 20 | Número de linhas sobrepostas entre chunks adjacentes. |
| `--repo-root` | `..` | Diretório raiz do repositório para cálculo de caminhos relativos. |
| `--no-as-posix` | `false` | Desabilita a normalização de caminhos para o formato POSIX (útil em Windows se necessário). |

## Exemplo de Saída (JSON)

Ao executar o comando:
```bash
python -m indexer chunk --file ./src/app.ts --chunk-lines 50
```

A saída será um JSON estruturado:

```json
{
  "file": "/abs/path/to/src/app.ts",
  "repoRoot": "/abs/path/to/repo",
  "path": "src/app.ts",
  "pathIsRelative": true,
  "asPosix": true,
  "chunkLines": 50,
  "overlapLines": 20,
  "totalLines": 145,
  "encoding": "utf-8",
  "stats": {
    "chunks": 4
  },
  "chunks": [
    {
      "chunkId": "hash_sha256_unico",
      "contentHash": "hash_conteudo_chunk",
      "path": "src/app.ts",
      "startLine": 1,
      "endLine": 50,
      "language": "typescript",
      "content": "import ..."
    },
    ...
  ],
  "warnings": []
}
```

## Comportamento de Erro

- Se o arquivo não existir ou não for um arquivo válido, o processo retorna exit code `1` e imprime o erro no `stderr`.
- Se `overlap-lines` for maior ou igual a `chunk-lines`, um erro de validação será retornado.
