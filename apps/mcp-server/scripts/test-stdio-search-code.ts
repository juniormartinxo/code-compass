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
  process.env.QDRANT_URL = process.env.QDRANT_URL || 'http://localhost:6333';
  process.env.QDRANT_COLLECTION_BASE =
    process.env.QDRANT_COLLECTION_BASE || 'compass_manutic_nomic_embed';
  process.env.MCP_QDRANT_MOCK_RESPONSE = JSON.stringify([
    {
      score: 0.88,
      payload: {
        repo: 'acme-repo',
        path: 'apps/mcp-server/src/main.ts',
        startLine: 1,
        endLine: 30,
        text: 'async function bootstrap() { /* ... */ }',
      },
    },
  ]);

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

  const firstLine = captured
    .split('\n')
    .map((line) => line.trim())
    .find((line) => line.length > 0);

  if (!firstLine) {
    throw new Error('mcp:stdio encerrou sem responder NDJSON');
  }

  const parsed = JSON.parse(firstLine) as Record<string, unknown>;
  const ok = parsed.ok === true;
  const hasOutput = typeof parsed.output === 'object' && parsed.output !== null;
  if (!ok || !hasOutput) {
    throw new Error(`Resposta inválida: ${firstLine}`);
  }

  stdoutWrite.call(process.stdout, `${firstLine}\n`);
}

run().catch((error) => {
  const message = error instanceof Error ? error.message : String(error);
  process.stderr.write(`${message}\n`);
  process.exitCode = 1;
});
