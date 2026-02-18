import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

import { afterEach, describe, expect, it } from 'vitest';

import { FileService } from '../src/file.service';
import { McpProtocolHandler } from '../src/mcp-protocol.handler';
import { McpStdioServer } from '../src/mcp-stdio.server';
import { OpenFileTool } from '../src/open-file.tool';
import { QdrantService } from '../src/qdrant.service';
import { SearchCodeTool } from '../src/search-code.tool';
import { AskCodeTool } from '../src/ask-code.tool';

function createWritableMemorySink(): {
  write: (chunk: string) => void;
  getLines: () => string[];
} {
  const lines: string[] = [];

  return {
    write: (chunk: string): void => {
      const normalized = chunk.trim();
      if (normalized) {
        lines.push(normalized);
      }
    },
    getLines: (): string[] => lines,
  };
}

function createServer(): McpStdioServer {
  const qdrantService = new QdrantService();
  const searchCodeTool = new SearchCodeTool(qdrantService);
  const fileService = new FileService();
  const openFileTool = new OpenFileTool(fileService);
  const askCodeTool = new AskCodeTool(searchCodeTool, openFileTool);
  const protocolHandler = new McpProtocolHandler(searchCodeTool, openFileTool, askCodeTool);
  return new McpStdioServer(protocolHandler);
}

describe('MCP stdio harness', () => {
  const baseCollection = 'compass__3584__manutic_nomic_embed_code';
  const codeCollection = `${baseCollection}__code`;
  const tempRoots: string[] = [];

  afterEach(async () => {
    delete process.env.CODEBASE_ROOT;
    delete process.env.REPO_ROOT;
    delete process.env.MCP_QDRANT_MOCK_RESPONSE;
    delete process.env.QDRANT_COLLECTION_BASE;
    delete process.env.QDRANT_URL;
    await Promise.all(tempRoots.splice(0).map((dir) => rm(dir, { recursive: true, force: true })));
  });

  it('deve validar fluxo NDJSON para search_code', async () => {
    process.env.QDRANT_URL = 'http://localhost:6333';
    process.env.QDRANT_COLLECTION_BASE = baseCollection;
    process.env.MCP_QDRANT_MOCK_RESPONSE = JSON.stringify([
      {
        score: 0.88,
        payload: {
          repo: 'acme-repo',
          path: 'apps/mcp-server/src/main.ts',
          startLine: 1,
          endLine: 30,
          text: 'async function bootstrap() { /* ... */ }',
          content_type: 'code',
        },
      },
    ]);

    const server = createServer();
    const sink = createWritableMemorySink();
    const stdoutWrite = process.stdout.write;

    process.stdout.write = ((chunk: string | Uint8Array): boolean => {
      sink.write(typeof chunk === 'string' ? chunk : Buffer.from(chunk).toString('utf8'));
      return true;
    }) as typeof process.stdout.write;

    try {
      await (server as unknown as { handleLine: (line: string) => Promise<void> }).handleLine(
        JSON.stringify({
          id: 'req-h1',
          tool: 'search_code',
          input: {
            scope: { type: 'repo', repo: 'acme-repo' },
            query: 'bootstrap',
            topK: 10,
            pathPrefix: 'apps/mcp-server/',
            vector: [0.1, 0.2],
          },
        }),
      );
    } finally {
      process.stdout.write = stdoutWrite;
    }

    const firstLine = sink.getLines()[0];
    expect(firstLine).toBeDefined();

    const parsed = JSON.parse(firstLine) as Record<string, unknown>;
    expect(parsed.id).toBe('req-h1');
    expect(parsed.ok).toBe(true);

    const responseOutput = parsed.output as {
      results: Array<Record<string, unknown>>;
      meta: Record<string, unknown>;
    };

    expect(Array.isArray(responseOutput.results)).toBe(true);
    expect(responseOutput.results[0].repo).toBe('acme-repo');
    expect(responseOutput.results[0].path).toBe('apps/mcp-server/src/main.ts');
    expect(responseOutput.meta.repo).toBe('acme-repo');
    expect(responseOutput.meta.scope).toEqual({ type: 'repo', repos: ['acme-repo'] });
    expect(responseOutput.meta.collection).toBe(codeCollection);
    expect(Array.isArray(responseOutput.meta.collections)).toBe(true);
  });

  it('deve aceitar scope repo no fluxo NDJSON de search_code', async () => {
    process.env.QDRANT_URL = 'http://localhost:6333';
    process.env.QDRANT_COLLECTION_BASE = baseCollection;
    process.env.MCP_QDRANT_MOCK_RESPONSE = JSON.stringify([
      {
        score: 0.88,
        payload: {
          repo: 'shared-lib',
          path: 'src/shared.ts',
          startLine: 1,
          endLine: 10,
          text: 'export const shared = true;',
          content_type: 'code',
        },
      },
    ]);

    const server = createServer();
    const sink = createWritableMemorySink();
    const stdoutWrite = process.stdout.write;

    process.stdout.write = ((chunk: string | Uint8Array): boolean => {
      sink.write(typeof chunk === 'string' ? chunk : Buffer.from(chunk).toString('utf8'));
      return true;
    }) as typeof process.stdout.write;

    try {
      await (server as unknown as { handleLine: (line: string) => Promise<void> }).handleLine(
        JSON.stringify({
          id: 'req-scope-1',
          tool: 'search_code',
          input: {
            scope: { type: 'repo', repo: 'shared-lib' },
            query: 'shared',
            topK: 10,
            vector: [0.1, 0.2],
          },
        }),
      );
    } finally {
      process.stdout.write = stdoutWrite;
    }

    const firstLine = sink.getLines()[0];
    expect(firstLine).toBeDefined();

    const parsed = JSON.parse(firstLine) as Record<string, unknown>;
    expect(parsed.id).toBe('req-scope-1');
    expect(parsed.ok).toBe(true);

    const responseOutput = parsed.output as {
      results: Array<Record<string, unknown>>;
      meta: Record<string, unknown>;
    };

    expect(responseOutput.results[0].repo).toBe('shared-lib');
    expect(responseOutput.meta.scope).toEqual({ type: 'repo', repos: ['shared-lib'] });
    expect(responseOutput.meta.repo).toBe('shared-lib');
  });

  it('deve validar fluxo NDJSON para open_file', async () => {
    const codebaseRoot = mkdtempSync(join(tmpdir(), 'mcp-open-file-stdio-'));
    const repoRoot = join(codebaseRoot, 'single-repo');
    tempRoots.push(codebaseRoot);
    mkdirSync(repoRoot, { recursive: true });
    writeFileSync(join(repoRoot, 'safe.txt'), 'a\nb\nc\nd\n', 'utf8');
    process.env.CODEBASE_ROOT = codebaseRoot;

    const server = createServer();
    const sink = createWritableMemorySink();
    const stdoutWrite = process.stdout.write;

    process.stdout.write = ((chunk: string | Uint8Array): boolean => {
      sink.write(typeof chunk === 'string' ? chunk : Buffer.from(chunk).toString('utf8'));
      return true;
    }) as typeof process.stdout.write;

    try {
      await (server as unknown as { handleLine: (line: string) => Promise<void> }).handleLine(
        JSON.stringify({
          id: 'req-open-file-1',
          tool: 'open_file',
          input: {
            repo: 'single-repo',
            path: 'safe.txt',
            startLine: 2,
            endLine: 3,
          },
        }),
      );
    } finally {
      process.stdout.write = stdoutWrite;
    }

    const firstLine = sink.getLines()[0];
    expect(firstLine).toBeDefined();

    const parsed = JSON.parse(firstLine) as Record<string, unknown>;
    expect(parsed.id).toBe('req-open-file-1');
    expect(parsed.ok).toBe(true);

    const responseOutput = parsed.output as Record<string, unknown>;
    expect(responseOutput.path).toBe('safe.txt');
    expect(responseOutput.startLine).toBe(2);
    expect(responseOutput.endLine).toBe(3);
    expect(responseOutput.text).toBe('b\nc\n');
    expect(responseOutput.truncated).toBe(false);
  });
});
