import { describe, expect, it } from 'vitest';

import { AskCodeTool } from '../src/ask-code.tool';
import { McpHttpController } from '../src/mcp-http.controller';
import { McpProtocolHandler } from '../src/mcp-protocol.handler';
import { OpenFileTool } from '../src/open-file.tool';
import { QdrantService } from '../src/qdrant.service';
import { SearchCodeTool } from '../src/search-code.tool';

function createController(): McpHttpController {
  const qdrantService = new QdrantService();
  const searchCodeTool = new SearchCodeTool(qdrantService);
  const openFileTool = {
    execute: async () => ({
      path: 'README.md',
      startLine: 1,
      endLine: 1,
      totalLines: 1,
      text: '',
      truncated: false,
    }),
  } as unknown as OpenFileTool;
  const askCodeTool = new AskCodeTool(searchCodeTool, openFileTool);
  const protocolHandler = new McpProtocolHandler(searchCodeTool, openFileTool, askCodeTool);
  return new McpHttpController(protocolHandler);
}

function createResponseSink() {
  return {
    statusCode: 200,
    payload: undefined as unknown,
    status(code: number) {
      this.statusCode = code;
      return this;
    },
    json(data: unknown) {
      this.payload = data;
      return this;
    },
    send() {
      this.payload = undefined;
      return this;
    },
  };
}

describe('McpHttpController', () => {
  it('deve retornar erro -32600 para payload inválido', async () => {
    const controller = createController();
    const res = createResponseSink();

    await controller.handle({ invalid: true }, res as never);

    expect(res.statusCode).toBe(400);
    expect((res.payload as { error: { code: number } }).error.code).toBe(-32600);
  });

  it('deve responder initialize via HTTP', async () => {
    const controller = createController();
    const res = createResponseSink();

    await controller.handle(
      {
        jsonrpc: '2.0',
        id: 1,
        method: 'initialize',
        params: {},
      },
      res as never,
    );

    expect(res.statusCode).toBe(200);
    expect((res.payload as { result: { protocolVersion: string } }).result.protocolVersion).toBe(
      '2024-11-05',
    );
  });
});
