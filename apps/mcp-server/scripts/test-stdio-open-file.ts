import { mkdtempSync, writeFileSync } from 'node:fs';
import { rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

import { McpProtocolHandler } from '../src/mcp-protocol.handler';
import { McpStdioServer } from '../src/mcp-stdio.server';
import { OpenFileTool } from '../src/open-file.tool';
import { SearchCodeTool } from '../src/search-code.tool';
import { QdrantService } from '../src/qdrant.service';
import { FileService } from '../src/file.service';
import { AskCodeTool } from '../src/ask-code.tool';

function createServer(): McpStdioServer {
  const qdrantService = new QdrantService();
  const searchCodeTool = new SearchCodeTool(qdrantService);
  const fileService = new FileService();
  const openFileTool = new OpenFileTool(fileService);
  const askCodeTool = new AskCodeTool(searchCodeTool, openFileTool);
  const protocolHandler = new McpProtocolHandler(searchCodeTool, openFileTool, askCodeTool);
  return new McpStdioServer(protocolHandler);
}

async function run(): Promise<void> {
  const tempRepoRoot = mkdtempSync(join(tmpdir(), 'mcp-open-file-stdio-'));

  try {
    writeFileSync(join(tempRepoRoot, 'safe.txt'), 'a\nb\nc\nd\n', 'utf8');
    delete process.env.CODEBASE_ROOT;
    process.env.REPO_ROOT = tempRepoRoot;

    const server = createServer();
    let captured = '';
    const stdoutWrite = process.stdout.write;

    process.stdout.write = ((chunk: string | Uint8Array): boolean => {
      captured += typeof chunk === 'string' ? chunk : Buffer.from(chunk).toString('utf8');
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

    const firstLine = captured
      .split('\n')
      .map((line) => line.trim())
      .find((line) => line.length > 0);
    if (!firstLine) {
      throw new Error('mcp:stdio encerrou sem responder NDJSON');
    }

    const parsed = JSON.parse(firstLine) as Record<string, unknown>;
    if (parsed.ok !== true) {
      throw new Error(`Resposta de erro inesperada: ${firstLine}`);
    }

    const output = parsed.output as Record<string, unknown>;
    if (output.path !== 'safe.txt') {
      throw new Error(`Path inesperado: ${String(output.path)}`);
    }
    if (output.text !== 'b\nc\n') {
      throw new Error(`Texto inesperado: ${String(output.text)}`);
    }

    stdoutWrite.call(process.stdout, `${firstLine}\n`);
  } finally {
    delete process.env.CODEBASE_ROOT;
    delete process.env.REPO_ROOT;
    rmSync(tempRepoRoot, { recursive: true, force: true });
  }
}

run().catch((error) => {
  const message = error instanceof Error ? error.message : String(error);
  process.stderr.write(`${message}\n`);
  process.exitCode = 1;
});
