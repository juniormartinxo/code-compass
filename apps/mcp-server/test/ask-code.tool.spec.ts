import { afterEach, describe, expect, it, vi } from 'vitest';

import { AskCodeTool } from '../src/ask-code.tool';
import { OpenFileTool } from '../src/open-file.tool';
import { QdrantService } from '../src/qdrant.service';
import { SearchCodeTool } from '../src/search-code.tool';

function createTool(): AskCodeTool {
  process.env.OLLAMA_URL = 'http://localhost:11434';
  process.env.EMBEDDING_MODEL = 'manutic/nomic-embed-code';
  process.env.LLM_MODEL = 'gpt-oss:latest';

  process.env.QDRANT_URL = 'http://localhost:6333';
  process.env.QDRANT_COLLECTION = 'compass__3584__manutic_nomic_embed_code';
  process.env.MCP_QDRANT_MOCK_RESPONSE = JSON.stringify([
    {
      score: 0.95,
      payload: {
        repo: 'acme-repo',
        path: 'src/constants/operators.ts',
        startLine: 1,
        endLine: 4,
        text: 'export const OPERATORS = ["eq", "neq"];',
        content_type: 'code',
      },
    },
  ]);

  const qdrant = new QdrantService();
  const search = new SearchCodeTool(qdrant);
  const openFile = {
    execute: async (input: { repo: string }) => ({
      path: 'src/constants/operators.ts',
      startLine: 1,
      endLine: 4,
      totalLines: 4,
      text: `// repo: ${input.repo}\nexport const OPERATORS = ["eq", "neq"];\n`,
      truncated: false,
    }),
  } as unknown as OpenFileTool;

  return new AskCodeTool(search, openFile);
}

describe('AskCodeTool', () => {
  afterEach(() => {
    delete process.env.ALLOW_GLOBAL_SCOPE;
    delete process.env.MCP_QDRANT_MOCK_RESPONSE;
  });

  it('deve falhar quando query estiver vazia', async () => {
    const tool = createTool();

    await expect(
      tool.execute({
        repo: 'acme-repo',
        query: '   ',
      }),
    ).rejects.toThrowError();
  });

  it('deve falhar quando repo/scope não for informado', async () => {
    const tool = createTool();

    await expect(
      tool.execute({
        query: 'o que faz este arquivo?',
      }),
    ).rejects.toThrowError();
  });

  it('deve bloquear scope all sem feature flag', async () => {
    const tool = createTool();

    await expect(
      tool.execute({
        scope: { type: 'all' },
        query: 'o que faz este arquivo?',
      }),
    ).rejects.toMatchObject({
      code: 'FORBIDDEN',
    });
  });

  it('deve aceitar scope all com feature flag', async () => {
    process.env.ALLOW_GLOBAL_SCOPE = 'true';
    const tool = createTool();

    vi.spyOn(tool as unknown as { embedQuestion: (query: string) => Promise<number[]> }, 'embedQuestion')
      .mockResolvedValue([0.1, 0.2]);
    vi.spyOn(tool as unknown as { chat: () => Promise<string> }, 'chat').mockResolvedValue('ok');

    const output = await tool.execute({
      scope: { type: 'all' },
      query: 'o que faz este arquivo?',
      topK: 1,
      minScore: 0.1,
    });

    expect(output.meta.scope).toEqual({ type: 'all' });
    expect(output.evidences[0].repo).toBe('acme-repo');
  });
});
