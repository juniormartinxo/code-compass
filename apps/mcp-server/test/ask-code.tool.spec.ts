import { describe, expect, it } from 'vitest';

import { AskCodeTool } from '../src/ask-code.tool';
import { OpenFileTool } from '../src/open-file.tool';
import { QdrantService } from '../src/qdrant.service';
import { SearchCodeTool } from '../src/search-code.tool';

function createTool(): AskCodeTool {
  process.env.OLLAMA_URL = 'http://localhost:11434';
  process.env.EMBEDDING_MODEL = 'manutic/nomic-embed-code';
  process.env.LLM_MODEL = 'gpt-oss:latest';

  process.env.QDRANT_URL = 'http://localhost:6333';
  process.env.QDRANT_COLLECTION = 'code_chunks';
  process.env.MCP_QDRANT_MOCK_RESPONSE = JSON.stringify([
    {
      score: 0.95,
      payload: {
        path: 'src/constants/operators.ts',
        startLine: 1,
        endLine: 4,
        text: 'export const OPERATORS = ["eq", "neq"];',
      },
    },
  ]);

  const qdrant = new QdrantService();
  const search = new SearchCodeTool(qdrant);
  const openFile = {
    execute: async () => ({
      path: 'src/constants/operators.ts',
      startLine: 1,
      endLine: 4,
      totalLines: 4,
      text: 'export const OPERATORS = ["eq", "neq"];\n',
      truncated: false,
    }),
  } as unknown as OpenFileTool;

  return new AskCodeTool(search, openFile);
}

describe('AskCodeTool', () => {
  it('deve falhar quando query estiver vazia', async () => {
    const tool = createTool();

    await expect(
      tool.execute({
        repo: 'acme-repo',
        query: '   ',
      }),
    ).rejects.toThrowError();
  });

  it('deve falhar quando repo não for informado', async () => {
    const tool = createTool();

    await expect(
      tool.execute({
        query: 'o que faz este arquivo?',
      }),
    ).rejects.toThrowError();
  });
});
