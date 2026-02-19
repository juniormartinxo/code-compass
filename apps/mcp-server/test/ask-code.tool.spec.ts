import { afterEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';

import { AskCodeTool } from '../src/ask-code.tool';
import { OpenFileTool } from '../src/open-file.tool';
import { QdrantService } from '../src/qdrant.service';
import { SearchCodeTool } from '../src/search-code.tool';

function createTool(): AskCodeTool {
  process.env.LLM_MODEL_API_URL = process.env.LLM_MODEL_API_URL || 'http://localhost:11434';
  process.env.EMBEDDING_PROVIDER_CODE = process.env.EMBEDDING_PROVIDER_CODE || 'ollama';
  process.env.EMBEDDING_PROVIDER_DOCS = process.env.EMBEDDING_PROVIDER_DOCS || 'ollama';
  process.env.EMBEDDING_PROVIDER_CODE_API_URL = process.env.EMBEDDING_PROVIDER_CODE_API_URL || 'http://localhost:11434';
  process.env.EMBEDDING_PROVIDER_DOCS_API_URL = process.env.EMBEDDING_PROVIDER_DOCS_API_URL || 'http://localhost:11434';
  process.env.EMBEDDING_MODEL_CODE = process.env.EMBEDDING_MODEL_CODE || 'manutic/nomic-embed-code';
  process.env.EMBEDDING_MODEL_DOCS = process.env.EMBEDDING_MODEL_DOCS || 'bge-m3';
  process.env.LLM_MODEL = process.env.LLM_MODEL || 'gpt-oss:latest';

  process.env.QDRANT_URL = process.env.QDRANT_URL || 'http://localhost:6333';
  process.env.QDRANT_COLLECTION_BASE = process.env.QDRANT_COLLECTION_BASE || 'compass_manutic_nomic_embed';
  process.env.MCP_QDRANT_MOCK_RESPONSE = process.env.MCP_QDRANT_MOCK_RESPONSE || JSON.stringify([
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
    vi.restoreAllMocks();
    delete process.env.ALLOW_GLOBAL_SCOPE;
    delete process.env.LLM_MODEL_PROVIDER;
    delete process.env.LLM_MODEL_API_URL;
    delete process.env.LLM_MODEL_API_KEY;
    delete process.env.LLM_PROVIDER;
    delete process.env.LLM_API_BASE_URL;
    delete process.env.LLM_API_KEY;
    delete process.env.EMBEDDING_PROVIDER_CODE;
    delete process.env.EMBEDDING_PROVIDER_DOCS;
    delete process.env.EMBEDDING_PROVIDER_CODE_API_URL;
    delete process.env.EMBEDDING_PROVIDER_DOCS_API_URL;
    delete process.env.EMBEDDING_PROVIDER_CODE_API_KEY;
    delete process.env.EMBEDDING_PROVIDER_DOCS_API_KEY;
    delete process.env.EMBEDDING_MODEL_CODE;
    delete process.env.EMBEDDING_MODEL_DOCS;
    delete process.env.LLM_MODEL;
    delete process.env.QDRANT_URL;
    delete process.env.MCP_QDRANT_MOCK_RESPONSE;
    delete process.env.QDRANT_COLLECTION_BASE;
  });

  it('deve falhar quando query estiver vazia', async () => {
    const tool = createTool();

    await expect(
      tool.execute({
        scope: { type: 'repo', repo: 'acme-repo' },
        query: '   ',
      }),
    ).rejects.toThrowError();
  });

  it('deve falhar quando scope não for informado', async () => {
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

    vi.spyOn(
      tool as unknown as { embedQuestion: (query: string, contentType: 'code' | 'docs') => Promise<number[]> },
      'embedQuestion',
    )
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

  it('deve usar DeepSeek via API quando LLM_MODEL_PROVIDER=deepseek', async () => {
    process.env.LLM_MODEL_PROVIDER = 'deepseek';
    process.env.LLM_MODEL_API_KEY = 'test-key';
    process.env.LLM_MODEL_API_URL = 'https://api.deepseek.com/v1';
    const tool = createTool();

    vi.spyOn(
      tool as unknown as { embedQuestion: (query: string, contentType: 'code' | 'docs') => Promise<number[]> },
      'embedQuestion',
    )
      .mockResolvedValue([0.1, 0.2]);

    const axiosPostSpy = vi.spyOn(axios, 'post')
      .mockResolvedValue({
        data: {
          choices: [
            {
              message: {
                content: 'resposta via deepseek',
              },
            },
          ],
        },
      } as never);

    const output = await tool.execute({
      scope: { type: 'repo', repo: 'acme-repo' },
      query: 'o que faz este arquivo?',
      topK: 1,
      contentType: 'code',
      minScore: 0.1,
    });

    expect(output.answer).toBe('resposta via deepseek');
    expect(axiosPostSpy).toHaveBeenCalledWith(
      'https://api.deepseek.com/v1/chat/completions',
      expect.objectContaining({
        model: 'gpt-oss:latest',
      }),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: 'Bearer test-key',
        }),
      }),
    );
  });

  it('deve falhar quando LLM_MODEL_PROVIDER=deepseek e chave não estiver configurada', async () => {
    process.env.LLM_MODEL_PROVIDER = 'deepseek';
    delete process.env.LLM_MODEL_API_KEY;
    delete process.env.LLM_API_KEY;
    const tool = createTool();

    vi.spyOn(
      tool as unknown as { embedQuestion: (query: string, contentType: 'code' | 'docs') => Promise<number[]> },
      'embedQuestion',
    )
      .mockResolvedValue([0.1, 0.2]);

    await expect(
      tool.execute({
        scope: { type: 'repo', repo: 'acme-repo' },
        query: 'o que faz este arquivo?',
        topK: 1,
        contentType: 'code',
        minScore: 0.1,
      }),
    ).rejects.toMatchObject({
      code: 'CHAT_FAILED',
    });
  });

  it('deve usar URL/API key de embedding por contentType quando provider=openai-compatible', async () => {
    const tool = createTool();
    process.env.EMBEDDING_PROVIDER_CODE = 'openai-compatible';
    process.env.EMBEDDING_PROVIDER_CODE_API_URL = 'https://embeddings.example/v1';
    process.env.EMBEDDING_PROVIDER_CODE_API_KEY = 'emb-code-key';
    vi.spyOn(tool as unknown as { chat: () => Promise<string> }, 'chat').mockResolvedValue('ok');

    const axiosPostSpy = vi.spyOn(axios, 'post')
      .mockResolvedValue({
        data: {
          data: [
            {
              embedding: [0.1, 0.2, 0.3],
            },
          ],
        },
      } as never);

    const output = await tool.execute({
      scope: { type: 'repo', repo: 'acme-repo' },
      query: 'o que faz este arquivo?',
      topK: 1,
      contentType: 'code',
      minScore: 0.1,
    });

    expect(output.evidences.length).toBeGreaterThan(0);
    expect(axiosPostSpy).toHaveBeenCalledWith(
      'https://embeddings.example/v1/embeddings',
      expect.objectContaining({
        model: 'manutic/nomic-embed-code',
      }),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: 'Bearer emb-code-key',
        }),
      }),
    );
  });
});
